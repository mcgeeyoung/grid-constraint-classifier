"""API key authentication dependency."""

import logging
import os
from typing import Optional, Set

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_api_keys() -> Set[str]:
    """Load valid API keys from GCC_API_KEYS env var (comma-separated)."""
    raw = os.environ.get("GCC_API_KEYS", "")
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def require_api_key(
    api_key: Optional[str] = Security(_api_key_header),
) -> str:
    """FastAPI dependency that enforces API key authentication.

    Returns the validated key on success.
    """
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    valid_keys = _load_api_keys()
    if not valid_keys:
        logger.warning("GCC_API_KEYS not configured: API key auth disabled (dev mode)")
        return api_key

    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return api_key
