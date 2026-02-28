"""MVT (Mapbox Vector Tile) endpoints for MapLibre GL JS.

Serves vector tiles directly from PostGIS using ST_AsMVT.
Each layer returns geometry + key attributes for data-driven styling.
"""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Header, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/api/v1/tiles")

# Cached ETag value (recomputed when pipeline runs complete)
_etag_cache: dict[str, str] = {}

# Valid layer names and their configurations
LAYER_CONFIG = {
    "zones": {
        "table": "zones",
        "geom_col": "boundary_geom",
        "srid": 4326,
        "attributes": "zone_code, zone_name",
        "id_col": "id",
    },
    "pnodes": {
        "table": "pnodes",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "node_id_external, node_name",
        "id_col": "id",
    },
    "data_centers": {
        "table": "data_centers",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "facility_name, status, capacity_mw, operator, state_code",
        "id_col": "id",
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
    },
    "transmission_lines": {
        "table": "transmission_lines",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "voltage_kv, owner, sub_1, sub_2",
        "id_col": "id",
    },
    "feeders": {
        "table": "feeders",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "feeder_id_external, capacity_mw, peak_loading_pct, voltage_kv",
        "id_col": "id",
    },
    "der_locations": {
        "table": "der_locations",
        "geom_col": "geom",
        "srid": 4326,
        "attributes": "der_type, eac_category, capacity_mw, source",
        "id_col": "id",
    },
}

# Transmission line zoom-level rules: (min_zoom, max_zoom, min_voltage_kv, simplify_tolerance)
TX_LINE_ZOOM_RULES = [
    (0, 6, 345, 0.05),
    (7, 8, 230, 0.01),
    (9, 10, 115, 0.005),
    (11, 99, 0, None),  # All voltages, full resolution
]

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


def _build_tile_query(
    layer: str,
    z: int,
    x: int,
    y: int,
) -> str:
    """Build the SQL query for a vector tile."""
    config = LAYER_CONFIG[layer]
    table = config["table"]
    geom_col = config["geom_col"]
    attrs = config["attributes"]
    id_col = config["id_col"]

    # Geometry transform: clip to tile envelope and convert to MVT coordinates
    geom_expr = f"t.{geom_col}"

    # Apply simplification for transmission lines based on zoom level
    extra_where = ""
    if layer == "transmission_lines":
        for min_z, max_z, min_voltage, tolerance in TX_LINE_ZOOM_RULES:
            if min_z <= z <= max_z:
                if min_voltage > 0:
                    extra_where = f"AND COALESCE(t.voltage_kv, 0) >= {min_voltage}"
                if tolerance is not None:
                    geom_expr = f"ST_Simplify(t.{geom_col}, {tolerance})"
                break

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
        )
        SELECT ST_AsMVT(tile_data, :layer_name, 4096, 'geom', '{id_col}')
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
    if_none_match: str = Header(None),
    db: Session = Depends(get_db),
):
    """Serve a Mapbox Vector Tile for the given layer and tile coordinates.

    Layers: zones, pnodes, data_centers, substations, transmission_lines,
    feeders, der_locations.

    Supports ETag/If-None-Match for conditional requests. Returns 304
    when the client's cached tile is still valid.
    """
    if layer not in LAYER_CONFIG:
        raise HTTPException(
            404,
            f"Unknown layer '{layer}'. Valid layers: {', '.join(LAYER_CONFIG.keys())}",
        )

    etag = _get_etag(db)

    # Return 304 if client has a matching ETag
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    sql = _build_tile_query(layer, z, x, y)
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
