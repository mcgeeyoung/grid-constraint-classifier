"""
WattCarbon API client with OAuth2 token caching and auto-refresh.

Connects to the WattCarbon production API to pull enrolled assets
and metered timeseries data for retrospective valuation.
"""

import logging
import time
from datetime import datetime
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

# Token lifetime buffer: refresh 5 minutes before expiry
TOKEN_REFRESH_BUFFER_SEC = 300


class WattCarbonClient:
    """OAuth2 client for the WattCarbon API."""

    def __init__(
        self,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self._email = email or settings.WATTCARBON_EMAIL
        self._api_key = api_key or settings.WATTCARBON_API_KEY
        self._base_url = (base_url or settings.WATTCARBON_API_URL).rstrip("/")
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def authenticate(self) -> str:
        """Obtain an OAuth2 bearer token via password grant.

        Caches the token and returns it. Raises on auth failure.
        """
        if self._token and time.time() < self._token_expiry:
            return self._token

        if not self._email or not self._api_key:
            raise ValueError(
                "WATTCARBON_EMAIL and WATTCARBON_API_KEY must be set "
                "(env vars or constructor args)"
            )

        resp = self._session.post(
            f"{self._base_url}/auth/token",
            data={
                "grant_type": "password",
                "username": self._email,
                "password": self._api_key,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data["access_token"]
        # Token lifetime is 1 day; refresh 5 min early
        expires_in = data.get("expires_in", 86400)
        self._token_expiry = time.time() + expires_in - TOKEN_REFRESH_BUFFER_SEC

        self._session.headers["Authorization"] = f"Bearer {self._token}"
        logger.info("WattCarbon: authenticated successfully")
        return self._token

    def _ensure_auth(self):
        """Ensure we have a valid token before making requests."""
        if not self._token or time.time() >= self._token_expiry:
            self.authenticate()

    def list_assets(
        self,
        status: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> list[dict]:
        """List all enrolled assets, optionally filtered by status or kind.

        Args:
            status: Filter by asset status (e.g. "active")
            kind: Filter by asset kind (e.g. "solar")

        Returns:
            List of asset dicts from the WattCarbon API.
        """
        self._ensure_auth()

        params = {}
        if status:
            params["status"] = status
        if kind:
            params["kind"] = kind

        resp = self._session.get(
            f"{self._base_url}/assets",
            params=params,
        )
        resp.raise_for_status()
        assets = resp.json()

        logger.info(f"WattCarbon: fetched {len(assets)} assets")
        return assets

    def get_asset(self, asset_id: str) -> dict:
        """Get a single asset by ID.

        Args:
            asset_id: WattCarbon asset identifier.

        Returns:
            Asset dict from the WattCarbon API.
        """
        self._ensure_auth()

        resp = self._session.get(f"{self._base_url}/assets/{asset_id}")
        resp.raise_for_status()
        return resp.json()

    def get_meter_timeseries(
        self,
        meter_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """Get hourly meter timeseries data for a meter.

        Args:
            meter_id: WattCarbon meter identifier.
            start: Period start (inclusive).
            end: Period end (inclusive).

        Returns:
            List of interval dicts with timestamp and value_mwh fields.
        """
        self._ensure_auth()

        params = {
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
        }
        resp = self._session.get(
            f"{self._base_url}/meters/{meter_id}/timeseries",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        intervals = data if isinstance(data, list) else data.get("intervals", [])
        logger.info(
            f"WattCarbon: fetched {len(intervals)} intervals "
            f"for meter {meter_id} ({start.date()} to {end.date()})"
        )
        return intervals
