"""ERCOT public REST API client (api.ercot.com).

Auth: Azure B2C ROPC (Resource Owner Password Credentials) flow. The
caller provides username + password + subscription key:

    client = ERCOTClient(username=USER, password=PASS, subscription_key=KEY)
    df = client.fetch_dam_spp_day(date(2026, 4, 18))

Bearer tokens last 1 hour; the client caches the current token and
refreshes 5 minutes before expiry. All requests carry both the bearer
token (`Authorization: Bearer ...`) and the APIM subscription key
(`Ocp-Apim-Subscription-Key: ...`) -- the API gateway requires both.

Endpoints we use:

  np4-190-cd / dam_stlmnt_pnt_prices   -- DAM Settlement Point Prices
  np4-183-cd / dam_hourly_lmp          -- DAM hourly LMPs by electrical bus

The driver layer maps the SPP report (np4-190-cd) onto the canonical
ISODriver schema. The bus-level LMP report is exposed for advanced use
but not used by `fetch_da_hourly`.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

OAUTH_URL = (
    "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/"
    "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
)
OAUTH_CLIENT_ID = "fec253ea-0d06-4272-a5e6-b478baeecd70"
OAUTH_SCOPE = f"openid {OAUTH_CLIENT_ID} offline_access"

API_BASE = "https://api.ercot.com/api/public-reports"

# Confirmed empirically: 30000 returns the entire DAM SPP day (~26,304 rows)
# in one page. Larger sizes are accepted but waste bandwidth. Smaller pages
# would force pagination at higher cost.
DEFAULT_PAGE_SIZE = 30000

# Refresh token this many seconds before its `expires_in` deadline.
TOKEN_REFRESH_MARGIN_S = 300

DEFAULT_TIMEOUT_S = 60


class ERCOTClient:
    """REST client for the ERCOT public-reports API."""

    def __init__(
        self,
        username: str,
        password: str,
        subscription_key: str,
        *,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        session: Optional[requests.Session] = None,
    ):
        if not (username and password and subscription_key):
            raise ValueError(
                "ERCOTClient requires username, password, and subscription_key."
            )
        self._username = username
        self._password = password
        self._subscription_key = subscription_key
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    # --- auth ---------------------------------------------------------------

    def _fetch_token(self) -> None:
        """Run the ROPC flow and cache the bearer token."""
        logger.info("ERCOT OAuth: requesting bearer token")
        r = self.session.post(
            OAUTH_URL,
            data={
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
                "scope": OAUTH_SCOPE,
                "client_id": OAUTH_CLIENT_ID,
                "response_type": "id_token",
            },
            timeout=self.timeout_s,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    def _ensure_token(self) -> str:
        if self._token is None or self._token_expires_at is None:
            self._fetch_token()
        else:
            now = datetime.now(timezone.utc)
            if (self._token_expires_at - now).total_seconds() < TOKEN_REFRESH_MARGIN_S:
                self._fetch_token()
        assert self._token is not None
        return self._token

    def _headers(self) -> dict:
        token = self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Ocp-Apim-Subscription-Key": self._subscription_key,
        }

    # --- requests -----------------------------------------------------------

    def _get_json(self, path: str, params: dict) -> dict:
        url = f"{API_BASE}/{path}"
        logger.info("ERCOT GET %s %s", url, {k: v for k, v in params.items() if k != "size"})
        r = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout_s)
        if r.status_code == 401:
            # Token expired mid-call (clock skew, etc.). Refresh once.
            logger.warning("ERCOT 401; refreshing token and retrying once")
            self._fetch_token()
            r = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()

    # --- reports ------------------------------------------------------------

    def fetch_dam_spp_day(
        self,
        operating_date: date,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> pd.DataFrame:
        """Pull the full DAM Settlement Point Prices file for one operating day.

        Returns a DataFrame with columns
        `deliveryDate, hourEnding, settlementPoint, settlementPointPrice, DSTFlag`.
        Empty frame on no data. Walks pagination if `totalPages` > 1, but
        with the default page size the whole day fits in one call.
        """
        rows: list[list] = []
        cols: list[str] = []
        page = 1
        while True:
            data = self._get_json(
                "np4-190-cd/dam_stlmnt_pnt_prices",
                {
                    "size": page_size,
                    "page": page,
                    "deliveryDateFrom": operating_date.strftime("%Y-%m-%d"),
                    "deliveryDateTo": operating_date.strftime("%Y-%m-%d"),
                },
            )
            if not cols and "fields" in data:
                cols = [f["name"] for f in data["fields"]]
            rows.extend(data.get("data", []))
            meta = data.get("_meta", {})
            total_pages = int(meta.get("totalPages") or 1)
            logger.info(
                "ERCOT DAM SPP %s: page %d/%d, %d rows so far / %d total",
                operating_date.isoformat(),
                page,
                total_pages,
                len(rows),
                meta.get("totalRecords"),
            )
            if page >= total_pages:
                break
            page += 1
            # Be polite between pages.
            time.sleep(0.2)

        if not rows:
            return pd.DataFrame(columns=cols or [
                "deliveryDate", "hourEnding", "settlementPoint",
                "settlementPointPrice", "DSTFlag",
            ])
        df = pd.DataFrame(rows, columns=cols)
        df["settlementPointPrice"] = pd.to_numeric(df["settlementPointPrice"], errors="coerce")
        return df
