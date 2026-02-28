"""Redis caching layer for API responses.

Provides a `cache_response` decorator for FastAPI endpoints and
helper functions for cache invalidation.

Falls back gracefully when Redis is unavailable (no caching, no errors).
"""

import hashlib
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
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if request is None:
                # Try to find Request in positional args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            r = get_redis()
            cache_key = None

            # Try to read from cache
            if r and request:
                cache_key = _build_cache_key(prefix, request)
                try:
                    cached = r.get(cache_key)
                    if cached is not None:
                        return JSONResponse(
                            content=json.loads(cached),
                            headers={"X-Cache": "HIT"},
                        )
                except Exception as e:
                    logger.debug("Cache read error: %s", e)

            # Execute the actual endpoint
            result = func(*args, **kwargs)

            # Store in cache
            if r and cache_key and result is not None:
                try:
                    # Convert Pydantic models / lists to JSON-serializable form
                    if isinstance(result, list):
                        serialized = [
                            item.model_dump() if hasattr(item, 'model_dump')
                            else item.dict() if hasattr(item, 'dict')
                            else item
                            for item in result
                        ]
                    elif hasattr(result, 'model_dump'):
                        serialized = result.model_dump()
                    elif hasattr(result, 'dict'):
                        serialized = result.dict()
                    else:
                        serialized = result

                    r.setex(cache_key, ttl, json.dumps(serialized, default=str))
                except Exception as e:
                    logger.debug("Cache write error: %s", e)

            return result
        return wrapper
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
