"""
Hosting capacity normalization pipeline.

Transforms raw utility-specific DataFrames into the canonical schema
expected by HostingCapacityRecord. Handles field renaming, unit conversion
(kW to MW), constraint name mapping, remaining capacity computation,
and centroid extraction.
"""

import logging
from typing import Optional

import pandas as pd

from .base import UtilityHCConfig

logger = logging.getLogger(__name__)

# Canonical output columns (matches HostingCapacityRecord model fields)
CANONICAL_COLUMNS = [
    "feeder_id_external", "feeder_name", "substation_name",
    "hosting_capacity_mw", "hosting_capacity_min_mw", "hosting_capacity_max_mw",
    "installed_dg_mw", "queued_dg_mw", "remaining_capacity_mw",
    "constraining_metric", "voltage_kv", "phase_config",
    "is_overhead", "is_network",
    "geometry_type", "geometry_json", "centroid_lat", "centroid_lon",
    "record_date", "raw_attributes",
]

# MW capacity columns that may need kW -> MW conversion
MW_COLUMNS = [
    "hosting_capacity_mw", "hosting_capacity_min_mw", "hosting_capacity_max_mw",
    "installed_dg_mw", "queued_dg_mw", "remaining_capacity_mw",
]

# Map diverse constraint names to canonical values
CONSTRAINT_MAP = {
    # Thermal variants
    "thermal": "thermal",
    "thermal limit": "thermal",
    "thermal_discharging": "thermal",
    "overload": "thermal",
    "conductor thermal": "thermal",
    "thermal loading": "thermal",
    "equipment thermal": "thermal",
    # Voltage variants
    "voltage": "voltage",
    "voltage rise": "voltage",
    "primary_over_voltage": "voltage",
    "voltage_deviation": "voltage",
    "regulator_deviation": "voltage",
    "steady state voltage": "voltage",
    "voltage variation": "voltage",
    "overvoltage": "voltage",
    "undervoltage": "voltage",
    "voltage flicker": "voltage",
    # Protection variants
    "protection": "protection",
    "fault current": "protection",
    "additional_element_fault": "protection",
    "breaker_reach": "protection",
    "sympathetic trip": "protection",
    "fuse coordination": "protection",
    "relay coordination": "protection",
    # Islanding variants
    "islanding": "islanding",
    "unintentional_islanding": "islanding",
    "anti-islanding": "islanding",
    "unintentional islanding": "islanding",
    # Reverse power
    "reverse power": "reverse_power",
    "backfeed": "reverse_power",
    "reverse power flow": "reverse_power",
}


def normalize_hosting_capacity(
    df: pd.DataFrame,
    config: UtilityHCConfig,
) -> pd.DataFrame:
    """Full normalization pipeline for hosting capacity data.

    Steps:
        1. Save raw attributes before transformation
        2. Apply field_map renaming from YAML config
        3. Convert kW to MW if capacity_unit == "kw"
        4. Normalize constraint names to canonical values
        5. Compute remaining capacity if missing
        6. Extract centroids from adapter geometry columns
        7. Convert geometry to GeoJSON for storage
        8. Validate: drop rows missing feeder_id_external

    Args:
        df: Raw DataFrame from adapter (with utility-specific column names).
        config: Utility config with field_map and capacity_unit.

    Returns:
        Normalized DataFrame with canonical column names.
    """
    if df.empty:
        return df

    df = df.copy()

    # 1. Save raw attributes before any transformation
    # Exclude internal geometry columns to keep raw_attributes clean
    raw_cols = [c for c in df.columns if not c.startswith("_")]
    df["raw_attributes"] = df[raw_cols].apply(
        lambda row: {k: v for k, v in row.items() if pd.notna(v)}, axis=1,
    )

    # 2. Apply field_map renaming
    rename_map = {}
    for src_field, dst_field in config.field_map.items():
        if src_field in df.columns:
            rename_map[src_field] = dst_field
    if rename_map:
        df = df.rename(columns=rename_map)
        logger.debug(f"Renamed {len(rename_map)} columns: {rename_map}")

    # 3. Unit conversion (kW -> MW)
    if config.capacity_unit == "kw":
        mw_cols = [c for c in MW_COLUMNS if c in df.columns]
        for col in mw_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce") / 1000.0
        if mw_cols:
            logger.debug(f"Converted {len(mw_cols)} columns from kW to MW")

    # 4. Normalize constraint names
    if "constraining_metric" in df.columns:
        df["constraining_metric"] = (
            df["constraining_metric"]
            .fillna("")
            .str.strip()
            .str.lower()
            .map(lambda v: CONSTRAINT_MAP.get(v, v if v else None))
        )

    # 5. Compute remaining capacity if not present or all null
    if (
        "remaining_capacity_mw" not in df.columns
        or df["remaining_capacity_mw"].isna().all()
    ):
        if "hosting_capacity_mw" in df.columns:
            installed = (
                df["installed_dg_mw"].fillna(0)
                if "installed_dg_mw" in df.columns
                else 0
            )
            queued = (
                df["queued_dg_mw"].fillna(0)
                if "queued_dg_mw" in df.columns
                else 0
            )
            df["remaining_capacity_mw"] = (
                df["hosting_capacity_mw"] - installed - queued
            )

    # 6. Extract centroids from adapter geometry columns
    if "_centroid_lat" in df.columns:
        df["centroid_lat"] = df["_centroid_lat"]
        df["centroid_lon"] = df["_centroid_lon"]
    if "_geometry_type" in df.columns:
        df["geometry_type"] = df["_geometry_type"]

    # 7. Convert ESRI geometry to GeoJSON for storage
    if "_geometry" in df.columns:
        from adapters.arcgis_client import ArcGISClient
        df["geometry_json"] = df["_geometry"].apply(
            lambda g: ArcGISClient._esri_to_geojson_geometry(g) if g else None,
        )

    # 8. Validate: require feeder_id_external
    if "feeder_id_external" in df.columns:
        before = len(df)
        df = df.dropna(subset=["feeder_id_external"])
        dropped = before - len(df)
        if dropped > 0:
            logger.warning(
                f"{config.utility_code}: dropped {dropped} rows "
                f"missing feeder_id_external"
            )
    else:
        logger.warning(
            f"{config.utility_code}: no feeder_id_external column after "
            f"field_map rename. Check field_map in config."
        )

    # Drop internal columns
    internal_cols = [c for c in df.columns if c.startswith("_")]
    if internal_cols:
        df = df.drop(columns=internal_cols)

    logger.info(
        f"{config.utility_code}: normalized {len(df)} records "
        f"({len([c for c in CANONICAL_COLUMNS if c in df.columns])}/{len(CANONICAL_COLUMNS)} "
        f"canonical columns present)"
    )

    return df
