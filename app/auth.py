"""API key authentication dependency.

Fail-closed: when GCC_API_KEYS is not configured, requests are rejected
unless GCC_AUTH_DISABLED=true is explicitly set for dev/test. Prevents
accidental wide-open admin routes in production if the env var is ever
cleared.
"""

import logging
import os
from typing import Optional, Set

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_api_keys() -> Set[str]:
    """Load valid API keys from GCC_API_KEYS env var (comma-separated)."""
    raw = os.environ.get("GCC_API_KEYS", "")
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def _auth_disabled() -> bool:
    """Check if auth is explicitly disabled (requires GCC_AUTH_DISABLED=true)."""
    return os.environ.get("GCC_AUTH_DISABLED", "").lower() == "true"


def require_api_key(
    api_key: Optional[str] = Security(_api_key_header),
) -> str:
    """FastAPI dependency enforcing X-API-Key authentication.

    Fail-closed: when GCC_API_KEYS is not configured, requests are
    rejected unless GCC_AUTH_DISABLED=true is explicitly set.
    """
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    valid_keys = _load_api_keys()
    if not valid_keys:
        if _auth_disabled():
            return api_key
        raise HTTPException(
            status_code=403,
            detail="API key auth not configured. Set GCC_API_KEYS or GCC_AUTH_DISABLED=true.",
        )

    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return api_key
