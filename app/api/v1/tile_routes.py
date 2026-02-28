"""MVT (Mapbox Vector Tile) endpoints for MapLibre GL JS.

Serves vector tiles directly from PostGIS using ST_AsMVT.
Each layer returns geometry + key attributes for data-driven styling.
"""

import hashlib

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/api/v1/tiles")

# Cached ETag value (recomputed when pipeline runs complete)
_etag_cache: dict[str, str] = {}

# Valid layer names and their configurations
# iso_filter: how to filter by ISO. "direct" = t.iso_id, "join:table" = join through another table
LAYER_CONFIG = {
    "zones": {
        "table": "zones",
        "geom_col": "boundary_geom",
        "srid": 4326,
        "attributes": "zone_code, zone_name",
        "id_col": "id",
        "iso_filter": "direct",
    },
    "pnodes": {
        "table": "pnodes",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "node_id_external, node_name",
        "id_col": "id",
        "iso_filter": "direct",
    },
    "data_centers": {
        "table": "data_centers",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "facility_name, status, capacity_mw, operator, state_code",
        "id_col": "id",
        "iso_filter": "direct",
    },
    "substations": {
        "table": "substations",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": (
            "substation_name, bank_name, facility_rating_mw, "
            "facility_loading_mw, peak_loading_pct, facility_type"
        ),
        "id_col": "id",
        "iso_filter": "direct",
    },
    "transmission_lines": {
        "table": "transmission_lines",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "voltage_kv, owner, sub_1, sub_2",
        "id_col": "id",
        "iso_filter": "direct",
    },
    "feeders": {
        "table": "feeders",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "feeder_id_external, capacity_mw, peak_loading_pct, voltage_kv",
        "id_col": "id",
        "iso_filter": "join:substations",
    },
    "der_locations": {
        "table": "der_locations",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "der_type, eac_category, capacity_mw, source",
        "id_col": "id",
        "iso_filter": "direct",
    },
    "gpkg_power_lines": {
        "table": "gpkg_power_lines",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "name, operator, max_voltage_kv, circuits, location",
        "id_col": "id",
        "iso_filter": None,
    },
    "gpkg_substations": {
        "table": "gpkg_substations",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "name, operator, substation_type, max_voltage_kv",
        "id_col": "id",
        "iso_filter": None,
    },
    "gpkg_power_plants": {
        "table": "gpkg_power_plants",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "name, operator, source, method, output_mw",
        "id_col": "id",
        "iso_filter": None,
    },
}

# Clustering config for point layers: which layers cluster, and at what zoom threshold
# eps is the DBSCAN distance in degrees (approximate; 0.1 deg ~ 11km at equator)
CLUSTER_CONFIG = {
    "pnodes": {
        "cluster_below_zoom": 10,
        "eps_by_zoom": {0: 0.5, 3: 0.2, 5: 0.1, 7: 0.05, 9: 0.02},
        "aggregate_attrs": "COUNT(*) AS point_count, AVG(scores.severity_score) AS avg_severity",
        "extra_join": "pnode_scores",  # signals we need the pnode join
    },
    "data_centers": {
        "cluster_below_zoom": 9,
        "eps_by_zoom": {0: 0.5, 3: 0.2, 5: 0.1, 7: 0.05},
        "aggregate_attrs": "COUNT(*) AS point_count, SUM(t.capacity_mw) AS total_capacity_mw",
        "extra_join": None,
    },
    "substations": {
        "cluster_below_zoom": 10,
        "eps_by_zoom": {0: 0.5, 3: 0.2, 5: 0.1, 7: 0.05, 9: 0.02},
        "aggregate_attrs": "COUNT(*) AS point_count, AVG(t.peak_loading_pct) AS avg_loading_pct",
        "extra_join": None,
    },
    "der_locations": {
        "cluster_below_zoom": 10,
        "eps_by_zoom": {0: 0.5, 3: 0.2, 5: 0.1, 7: 0.05, 9: 0.02},
        "aggregate_attrs": "COUNT(*) AS point_count, SUM(t.capacity_mw) AS total_capacity_mw",
        "extra_join": None,
    },
}


def _get_cluster_eps(eps_by_zoom: dict, z: int) -> float:
    """Get the DBSCAN epsilon for a given zoom level."""
    eps = 0.5
    for threshold_z in sorted(eps_by_zoom.keys()):
        if z >= threshold_z:
            eps = eps_by_zoom[threshold_z]
    return eps


# Transmission line zoom-level rules: (min_zoom, max_zoom, min_voltage_kv, simplify_tolerance)
TX_LINE_ZOOM_RULES = [
    (0, 6, 345, 0.05),
    (7, 8, 230, 0.01),
    (9, 10, 115, 0.005),
    (11, 99, 0, None),  # All voltages, full resolution
]

# GeoPackage power lines use same zoom-level filtering (voltage in kV)
GPKG_LINE_ZOOM_RULES = TX_LINE_ZOOM_RULES

# Pnodes: join with pnode_scores for severity data
PNODE_JOIN_SQL = """
    LEFT JOIN LATERAL (
        SELECT ps.severity_score, ps.tier
        FROM pnode_scores ps
        JOIN pipeline_runs pr ON ps.pipeline_run_id = pr.id
        WHERE ps.pnode_id = t.id AND pr.status = 'completed'
        ORDER BY pr.completed_at DESC
        LIMIT 1
    ) scores ON true
"""

# Zones: join with zone_classifications for classification data
ZONE_JOIN_SQL = """
    LEFT JOIN LATERAL (
        SELECT zc.classification, zc.transmission_score, zc.generation_score
        FROM zone_classifications zc
        JOIN pipeline_runs pr ON zc.pipeline_run_id = pr.id
        WHERE zc.zone_id = t.id AND pr.status = 'completed'
        ORDER BY pr.completed_at DESC
        LIMIT 1
    ) cls ON true
"""


def _build_iso_where(layer: str, iso_ids: list[int] | None) -> str:
    """Build an ISO filter WHERE clause for a layer."""
    if not iso_ids:
        return ""
    iso_filter = LAYER_CONFIG[layer].get("iso_filter", "direct")
    if iso_filter is None:
        # GeoPackage layers have no ISO association
        return ""
    id_list = ", ".join(str(i) for i in iso_ids)
    if iso_filter == "direct":
        return f"AND t.iso_id IN ({id_list})"
    elif iso_filter.startswith("join:"):
        # Feeders: join through substations
        join_table = iso_filter.split(":")[1]
        return f"AND t.substation_id IN (SELECT id FROM {join_table} WHERE iso_id IN ({id_list}))"
    return ""


def _build_tile_query(
    layer: str,
    z: int,
    x: int,
    y: int,
    iso_ids: list[int] | None = None,
) -> str:
    """Build the SQL query for a vector tile."""
    config = LAYER_CONFIG[layer]
    table = config["table"]
    geom_col = config["geom_col"]
    attrs = config["attributes"]
    id_col = config["id_col"]

    # Geometry transform: clip to tile envelope and convert to MVT coordinates
    geom_expr = f"t.{geom_col}"

    # Apply simplification for line layers based on zoom level
    extra_where = ""
    if layer == "transmission_lines":
        for min_z, max_z, min_voltage, tolerance in TX_LINE_ZOOM_RULES:
            if min_z <= z <= max_z:
                if min_voltage > 0:
                    extra_where = f"AND COALESCE(t.voltage_kv, 0) >= {min_voltage}"
                if tolerance is not None:
                    geom_expr = f"ST_Simplify(t.{geom_col}, {tolerance})"
                break
    elif layer == "gpkg_power_lines":
        for min_z, max_z, min_voltage, tolerance in GPKG_LINE_ZOOM_RULES:
            if min_z <= z <= max_z:
                if min_voltage > 0:
                    extra_where = f"AND COALESCE(t.max_voltage_kv, 0) >= {min_voltage}"
                if tolerance is not None:
                    geom_expr = f"ST_Simplify(t.{geom_col}, {tolerance})"
                break

    # ISO filter
    iso_where = _build_iso_where(layer, iso_ids)

    # Build MVT geometry expression
    mvt_geom = (
        f"ST_AsMVTGeom("
        f"  ST_Transform({geom_expr}, 3857),"
        f"  ST_TileEnvelope(:z, :x, :y),"
        f"  4096, 64, true"
        f")"
    )

    # Extra joins and attributes for enriched layers
    extra_join = ""
    extra_attrs = ""

    if layer == "pnodes":
        extra_join = PNODE_JOIN_SQL
        extra_attrs = ", scores.severity_score, scores.tier"
    elif layer == "zones":
        extra_join = ZONE_JOIN_SQL
        extra_attrs = ", cls.classification, cls.transmission_score, cls.generation_score"

    sql = f"""
        WITH tile_data AS (
            SELECT
                t.{id_col},
                {mvt_geom} AS geom,
                {attrs}{extra_attrs}
            FROM {table} t
            {extra_join}
            WHERE t.{geom_col} IS NOT NULL
              AND ST_Intersects(
                  ST_Transform(t.{geom_col}, 3857),
                  ST_TileEnvelope(:z, :x, :y)
              )
              {extra_where}
              {iso_where}
        )
        SELECT ST_AsMVT(tile_data, :layer_name, 4096, 'geom', '{id_col}')
        FROM tile_data
    """
    return sql


def _build_clustered_tile_query(
    layer: str,
    z: int,
    x: int,
    y: int,
    iso_ids: list[int] | None = None,
) -> str:
    """Build a clustered MVT query using ST_ClusterDBSCAN for point layers at low zoom.

    Clusters nearby points and returns centroids with aggregate attributes.
    Unclustered points (noise) are returned individually.
    """
    config = LAYER_CONFIG[layer]
    cluster_config = CLUSTER_CONFIG[layer]
    table = config["table"]
    geom_col = config["geom_col"]
    eps = _get_cluster_eps(cluster_config["eps_by_zoom"], z)

    # Per-layer: define the value column to aggregate and any extra joins
    if layer == "pnodes":
        value_col = "scores.severity_score"
        agg_col = "avg_value"
        extra_join = PNODE_JOIN_SQL
    elif layer == "substations":
        value_col = "t.peak_loading_pct"
        agg_col = "avg_value"
        extra_join = ""
    elif layer in ("data_centers", "der_locations"):
        value_col = "t.capacity_mw"
        agg_col = "total_value"
        extra_join = ""
    else:
        value_col = "1"
        agg_col = "avg_value"
        extra_join = ""

    agg_fn = "SUM" if agg_col == "total_value" else "AVG"

    # ISO filter
    iso_where = _build_iso_where(layer, iso_ids)

    sql = f"""
        WITH filtered AS (
            SELECT
                t.{geom_col} AS geom,
                COALESCE({value_col}, 0) AS val,
                ST_ClusterDBSCAN(t.{geom_col}, eps := {eps}, minpoints := 2)
                    OVER () AS cid
            FROM {table} t
            {extra_join}
            WHERE t.{geom_col} IS NOT NULL
              AND ST_Intersects(
                  ST_Transform(t.{geom_col}, 3857),
                  ST_TileEnvelope(:z, :x, :y)
              )
              {iso_where}
        ),
        merged AS (
            SELECT
                ST_Centroid(ST_Collect(geom)) AS geom,
                COUNT(*) AS point_count,
                {agg_fn}(val) AS {agg_col},
                true AS is_cluster
            FROM filtered
            WHERE cid IS NOT NULL
            GROUP BY cid
          UNION ALL
            SELECT
                geom,
                1 AS point_count,
                val AS {agg_col},
                false AS is_cluster
            FROM filtered
            WHERE cid IS NULL
        ),
        tile_data AS (
            SELECT
                ST_AsMVTGeom(
                    ST_Transform(geom, 3857),
                    ST_TileEnvelope(:z, :x, :y),
                    4096, 64, true
                ) AS geom,
                point_count,
                {agg_col},
                is_cluster
            FROM merged
            WHERE geom IS NOT NULL
        )
        SELECT ST_AsMVT(tile_data, :layer_name, 4096, 'geom')
        FROM tile_data
    """
    return sql


def _get_etag(db: Session) -> str:
    """Compute an ETag based on the latest pipeline run completion time.

    Cached in-process so we don't query on every tile request.
    """
    if "current" in _etag_cache:
        return _etag_cache["current"]

    row = db.execute(
        text(
            "SELECT MAX(completed_at) FROM pipeline_runs WHERE status = 'completed'"
        )
    ).scalar()
    tag_source = str(row) if row else "empty"
    etag = hashlib.md5(tag_source.encode()).hexdigest()
    _etag_cache["current"] = etag
    return etag


def clear_tile_etag():
    """Clear the cached ETag (called after pipeline run completes)."""
    _etag_cache.pop("current", None)


@router.get(
    "/{layer}/{z}/{x}/{y}.mvt",
    response_class=Response,
    responses={
        200: {"content": {"application/vnd.mapbox-vector-tile": {}}},
        404: {"description": "Unknown layer"},
    },
)
def get_vector_tile(
    layer: str,
    z: int,
    x: int,
    y: int,
    iso_id: Optional[str] = Query(
        None,
        description="Comma-separated ISO codes to filter by (e.g. 'pjm,miso')",
    ),
    if_none_match: str = Header(None),
    db: Session = Depends(get_db),
):
    """Serve a Mapbox Vector Tile for the given layer and tile coordinates.

    Layers: zones, pnodes, data_centers, substations, transmission_lines,
    feeders, der_locations.

    Supports optional iso_id filter (comma-separated ISO codes) and
    ETag/If-None-Match for conditional requests.
    """
    if layer not in LAYER_CONFIG:
        raise HTTPException(
            404,
            f"Unknown layer '{layer}'. Valid layers: {', '.join(LAYER_CONFIG.keys())}",
        )

    # Resolve ISO codes to numeric IDs for SQL filtering
    iso_ids: list[int] | None = None
    if iso_id:
        codes = [c.strip().lower() for c in iso_id.split(",") if c.strip()]
        if codes:
            rows = db.execute(
                text("SELECT id FROM isos WHERE iso_code IN :codes"),
                {"codes": tuple(codes)},
            ).fetchall()
            iso_ids = [row[0] for row in rows] if rows else []

    etag = _get_etag(db)

    # Return 304 if client has a matching ETag
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    # Use clustered query for point layers at low zoom
    cluster_cfg = CLUSTER_CONFIG.get(layer)
    if cluster_cfg and z < cluster_cfg["cluster_below_zoom"]:
        sql = _build_clustered_tile_query(layer, z, x, y, iso_ids)
    else:
        sql = _build_tile_query(layer, z, x, y, iso_ids)

    result = db.execute(
        text(sql),
        {"z": z, "x": x, "y": y, "layer_name": layer},
    ).scalar()

    # ST_AsMVT returns bytes; empty tile if no features
    tile_bytes = bytes(result) if result else b""

    return Response(
        content=tile_bytes,
        media_type="application/vnd.mapbox-vector-tile",
        headers={
            "Cache-Control": "public, max-age=3600",
            "ETag": f'"{etag}"',
            "Access-Control-Allow-Origin": "*",
        },
    )
