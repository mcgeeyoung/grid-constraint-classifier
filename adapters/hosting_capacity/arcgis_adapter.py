"""
Generic ArcGIS FeatureServer hosting capacity adapter.

Covers ~60% of utilities that publish hosting capacity data via
standard ArcGIS FeatureServer endpoints with no special auth or
URL rotation.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from adapters.arcgis_client import ArcGISClient

from .base import HostingCapacityAdapter, UtilityHCConfig

logger = logging.getLogger(__name__)


class ArcGISHostingCapacityAdapter(HostingCapacityAdapter):
    """Generic adapter for public ArcGIS FeatureServer HC endpoints."""

    def pull_hosting_capacity(self, force: bool = False) -> pd.DataFrame:
        cache = self.get_cache_path()
        if cache.exists() and not force:
            logger.info(f"Loading cached HC data for {self.config.utility_code}")
            return pd.read_parquet(cache)

        url = self.resolve_current_url()
        logger.info(
            f"Fetching HC data for {self.config.utility_code} from {url}"
        )

        features = self.client.query_features(
            url=url,
            page_size=self.config.page_size,
            out_sr=self.config.out_sr,
        )

        if not features:
            logger.warning(f"No features returned for {self.config.utility_code}")
            return pd.DataFrame()

        df = self._features_to_dataframe(features)

        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
        logger.info(
            f"Cached {len(df)} HC records for {self.config.utility_code}"
        )
        return df

    def _features_to_dataframe(self, features: list[dict]) -> pd.DataFrame:
        """Convert raw ArcGIS features to DataFrame with geometry columns."""
        records = []
        for feat in features:
            attrs = feat.get("attributes", {})
            geom = feat.get("geometry")

            row = dict(attrs)
            if geom:
                row["_geometry"] = geom
                row["_geometry_type"] = self._detect_geometry_type(geom)
                lat, lon = ArcGISClient.compute_centroid(geom)
                row["_centroid_lat"] = round(lat, 6) if lat else None
                row["_centroid_lon"] = round(lon, 6) if lon else None

            records.append(row)

        return pd.DataFrame(records)

    @staticmethod
    def _detect_geometry_type(geom: dict) -> str:
        if "x" in geom:
            return "Point"
        if "paths" in geom:
            return "MultiLineString"
        if "rings" in geom:
            return "Polygon"
        return geom.get("type", "Unknown")
