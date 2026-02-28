"""
Reusable ArcGIS REST API client.

Extracted from scraping/grip_fetcher.py to support hosting capacity
data ingestion across ~50 utility ArcGIS endpoints.
"""

import logging
import math
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class ArcGISClient:
    """Generic ArcGIS FeatureServer/MapServer query client with pagination."""

    def __init__(
        self,
        user_agent: str = "grid-constraint-classifier/2.0",
        rate_limit_sec: float = 0.5,
        max_retries: int = 3,
        timeout: int = 120,
    ):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.rate_limit_sec = rate_limit_sec
        self.max_retries = max_retries
        self.timeout = timeout

    def query_features(
        self,
        url: str,
        where: str = "1=1",
        out_fields: str = "*",
        return_geometry: bool = True,
        out_sr: int = 4326,
        page_size: int = 2000,
        max_records: Optional[int] = None,
        auth_token: Optional[str] = None,
    ) -> list[dict]:
        """
        Paginated feature query. Returns list of raw feature dicts.

        Pagination uses resultOffset/resultRecordCount with exceededTransferLimit
        detection. Includes retry with exponential backoff and rate limiting.

        Args:
            url: ArcGIS layer query endpoint (e.g. .../FeatureServer/0/query).
            where: SQL WHERE clause for filtering.
            out_fields: Comma-separated field names or "*" for all.
            return_geometry: Whether to include geometry in results.
            out_sr: Output spatial reference WKID (default 4326/WGS84).
            page_size: Records per page (default 2000, ArcGIS max varies).
            max_records: Stop after this many total records (None = all).
            auth_token: Optional ArcGIS token for authenticated services.

        Returns:
            List of raw ESRI feature dicts with "attributes" and "geometry" keys.
        """
        all_features: list[dict] = []
        offset = 0

        while True:
            params = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": str(return_geometry).lower(),
                "outSR": out_sr,
                "f": "json",
                "resultRecordCount": page_size,
                "resultOffset": offset,
            }
            if auth_token:
                params["token"] = auth_token

            data = self._request_with_retry(url, params)
            if data is None:
                break

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)
            logger.info(f"  Fetched {len(all_features)} features (offset {offset})...")

            if max_records and len(all_features) >= max_records:
                all_features = all_features[:max_records]
                break

            # Check if more pages exist
            exceeded = data.get("exceededTransferLimit", False)
            if len(features) < page_size and not exceeded:
                break
            offset += page_size

            time.sleep(self.rate_limit_sec)

        return all_features

    def query_features_geojson(self, url: str, **kwargs) -> dict:
        """Query and return as GeoJSON FeatureCollection.

        Accepts the same keyword arguments as query_features().
        Geometry is converted from ESRI JSON to GeoJSON format.
        """
        features = self.query_features(url, **kwargs)
        geojson_features = []
        for feat in features:
            geom = feat.get("geometry")
            attrs = feat.get("attributes", {})
            geojson_features.append({
                "type": "Feature",
                "properties": attrs,
                "geometry": self._esri_to_geojson_geometry(geom) if geom else None,
            })
        return {"type": "FeatureCollection", "features": geojson_features}

    def discover_layers(self, service_url: str) -> list[dict]:
        """List available layers and tables from a FeatureServer/MapServer.

        Args:
            service_url: Service root URL (without /query suffix).

        Returns:
            List of dicts with "id", "name", and "type" ("layer" or "table").
        """
        data = self._request_with_retry(service_url, {"f": "json"})
        if not data:
            return []
        layers = data.get("layers", [])
        tables = data.get("tables", [])
        return (
            [{"id": l["id"], "name": l["name"], "type": "layer"} for l in layers]
            + [{"id": t["id"], "name": t["name"], "type": "table"} for t in tables]
        )

    def get_field_schema(self, layer_url: str) -> list[dict]:
        """Get field definitions for a specific layer.

        Args:
            layer_url: Layer URL (e.g. .../FeatureServer/0) without /query.

        Returns:
            List of field definition dicts with "name", "type", "alias", etc.
        """
        data = self._request_with_retry(layer_url, {"f": "json"})
        if not data:
            return []
        return data.get("fields", [])

    def get_record_count(self, url: str, where: str = "1=1") -> int:
        """Get total record count for a layer query.

        Args:
            url: Layer query endpoint.
            where: SQL WHERE clause.

        Returns:
            Feature count, or 0 on error.
        """
        data = self._request_with_retry(url, {
            "where": where, "returnCountOnly": "true", "f": "json",
        })
        return data.get("count", 0) if data else 0

    def _request_with_retry(self, url: str, params: dict) -> Optional[dict]:
        """HTTP GET with exponential backoff retry (1s, 2s, 4s)."""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                # ArcGIS returns 200 with error body for many failures
                if "error" in data:
                    err = data["error"]
                    logger.warning(f"ArcGIS error: {err.get('message', err)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                return data
            except requests.exceptions.Timeout:
                logger.warning(
                    f"Timeout (attempt {attempt + 1}/{self.max_retries})"
                )
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    @staticmethod
    def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
        """Convert Web Mercator (EPSG:3857) to WGS84 (lat, lon)."""
        lon = x / 20037508.34 * 180.0
        lat = (
            math.atan(math.exp(y / 20037508.34 * math.pi)) * 360.0 / math.pi - 90.0
        )
        return lat, lon

    @staticmethod
    def compute_centroid(
        geometry: dict,
    ) -> tuple[Optional[float], Optional[float]]:
        """Compute centroid (lat, lon) from ArcGIS or GeoJSON geometry.

        Handles ESRI point (x/y), polyline (paths), polygon (rings),
        and GeoJSON Point, LineString, Polygon, Multi* types.

        Returns:
            (lat, lon) tuple, or (None, None) if geometry is empty/invalid.
        """
        if not geometry:
            return None, None

        # ArcGIS point geometry
        if "x" in geometry and "y" in geometry:
            return geometry["y"], geometry["x"]

        # ArcGIS polyline (paths) or polygon (rings)
        coords: list = []
        for key in ("paths", "rings"):
            for ring_or_path in geometry.get(key, []):
                coords.extend(ring_or_path)

        # GeoJSON coordinates
        if "coordinates" in geometry:
            gtype = geometry.get("type", "")
            if gtype == "Point":
                c = geometry["coordinates"]
                return c[1], c[0]  # GeoJSON is [lon, lat]
            elif gtype in ("LineString", "MultiPoint"):
                coords = geometry["coordinates"]
            elif gtype in ("Polygon", "MultiLineString"):
                for ring in geometry["coordinates"]:
                    coords.extend(ring)
            elif gtype == "MultiPolygon":
                for poly in geometry["coordinates"]:
                    for ring in poly:
                        coords.extend(ring)

        if not coords:
            return None, None

        # Average all coordinate points
        if isinstance(coords[0], (list, tuple)) and len(coords[0]) >= 2:
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            return sum(lats) / len(lats), sum(lons) / len(lons)

        return None, None

    @staticmethod
    def _esri_to_geojson_geometry(geom: dict) -> Optional[dict]:
        """Convert ESRI JSON geometry to GeoJSON geometry.

        Handles point (x/y), polyline (paths), and polygon (rings).
        """
        if not geom:
            return None
        if "x" in geom and "y" in geom:
            return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
        if "paths" in geom:
            paths = geom["paths"]
            if len(paths) == 1:
                return {"type": "LineString", "coordinates": paths[0]}
            return {"type": "MultiLineString", "coordinates": paths}
        if "rings" in geom:
            return {"type": "Polygon", "coordinates": geom["rings"]}
        return None
