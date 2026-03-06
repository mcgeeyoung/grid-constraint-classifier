"""Redis caching layer for API responses.

Provides a `cache_response` decorator for FastAPI endpoints and
helper functions for cache invalidation.

Falls back gracefully when Redis is unavailable (no caching, no errors).
"""

import asyncio
import hashlib
import inspect
import json
import logging
from functools import wraps
from typing import Optional

import redis
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy-initialized Redis client (None if unavailable)
_redis_client: Optional[redis.Redis] = None
_redis_checked = False


def get_redis() -> Optional[redis.Redis]:
    """Get the Redis client, or None if Redis is unavailable."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        _redis_client = client
        logger.info("Redis connected: %s", settings.REDIS_URL)
    except Exception as e:
        logger.warning("Redis unavailable, caching disabled: %s", e)
        _redis_client = None
    return _redis_client


def _build_cache_key(prefix: str, request: Request) -> str:
    """Build a cache key from the prefix and full request URL (path + query)."""
    url = str(request.url)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return f"gcc:{prefix}:{url_hash}"


def cache_response(prefix: str, ttl: int = 300):
    """Decorator that caches JSON endpoint responses in Redis.

    Args:
        prefix: Cache key prefix (e.g. "zones", "classifications")
        ttl: Time-to-live in seconds (default 5 minutes)

    Usage:
        @router.get("/endpoint")
        @cache_response("my-prefix", ttl=3600)
        def my_endpoint(request: Request, ...):
            ...

    Note: The decorated function MUST accept a `request: Request` parameter
    (FastAPI injects this automatically when declared).
    """
    def _extract_request(args, kwargs):
        request = kwargs.get("request")
        if request is None:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        return request

    def _try_cache_read(request):
        r = get_redis()
        if r and request:
            cache_key = _build_cache_key(prefix, request)
            try:
                cached = r.get(cache_key)
                if cached is not None:
                    return JSONResponse(
                        content=json.loads(cached),
                        headers={"X-Cache": "HIT"},
                    ), cache_key, r
            except Exception as e:
                logger.debug("Cache read error: %s", e)
            return None, cache_key, r
        return None, None, r

    def _serialize(obj):
        """Recursively serialize Pydantic models and ORM objects within dicts/lists."""
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        elif hasattr(obj, 'dict') and not hasattr(obj, '__table__'):
            return obj.dict()
        elif hasattr(obj, '__table__'):
            # SQLAlchemy ORM object: extract column values
            return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
        elif isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_serialize(item) for item in obj]
        return obj

    def _try_cache_write(r, cache_key, result):
        if r and cache_key and result is not None:
            try:
                serialized = _serialize(result)
                r.setex(cache_key, ttl, json.dumps(serialized, default=str))
            except Exception as e:
                logger.debug("Cache write error: %s", e)

    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                request = _extract_request(args, kwargs)
                cached_response, cache_key, r = _try_cache_read(request)
                if cached_response:
                    return cached_response
                result = await func(*args, **kwargs)
                _try_cache_write(r, cache_key, result)
                return result
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                request = _extract_request(args, kwargs)
                cached_response, cache_key, r = _try_cache_read(request)
                if cached_response:
                    return cached_response
                result = func(*args, **kwargs)
                _try_cache_write(r, cache_key, result)
                return result
            return sync_wrapper
    return decorator


def invalidate_iso_cache(iso_code: str):
    """Invalidate all cached responses for a specific ISO.

    Clears caches that depend on pipeline run results:
    classifications, pnode scores, hierarchy scores.
    """
    r = get_redis()
    if not r:
        return

    prefixes = [
        f"gcc:classifications:*",
        f"gcc:pnodes:*",
        f"gcc:hierarchy-scores:*",
        f"gcc:overview:*",
    ]

    cleared = 0
    try:
        for pattern in prefixes:
            keys = list(r.scan_iter(match=pattern, count=200))
            if keys:
                r.delete(*keys)
                cleared += len(keys)
        if cleared:
            logger.info("Cleared %d cache keys for ISO %s", cleared, iso_code)
    except Exception as e:
        logger.warning("Cache invalidation error: %s", e)


def invalidate_hc_cache():
    """Invalidate all hosting capacity caches.

    Call after HC data ingestion to refresh utility/feeder listings.
    """
    r = get_redis()
    if not r:
        return

    prefixes = [
        "gcc:hc-utilities:*",
        "gcc:hc-records:*",
        "gcc:hc-geojson:*",
        "gcc:hc-summary:*",
        "gcc:hc-ingestion-runs:*",
        "gcc:hc-profile:*",
    ]

    cleared = 0
    try:
        for pattern in prefixes:
            keys = list(r.scan_iter(match=pattern, count=200))
            if keys:
                r.delete(*keys)
                cleared += len(keys)
        if cleared:
            logger.info("Cleared %d HC cache keys", cleared)
    except Exception as e:
        logger.warning("HC cache invalidation error: %s", e)


def invalidate_all():
    """Clear the entire GCC cache namespace."""
    r = get_redis()
    if not r:
        return

    try:
        keys = list(r.scan_iter(match="gcc:*", count=1000))
        if keys:
            r.delete(*keys)
            logger.info("Cleared all %d GCC cache keys", len(keys))
    except Exception as e:
        logger.warning("Cache clear error: %s", e)
