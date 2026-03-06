# Phase 3: Replace API

## Goal

Replace the existing v1 API routes with new routes organized around three question types: constraints, values, and profiles. Drop old computed tables. Move reference/visual tables to separate schemas. Since the API is not deployed and has no external users, this is a clean replacement.

## Prerequisites

- Phase 2 complete (all new tables populated, materialized views refreshed)
- Verified that new computed data matches old data within tolerance

---

## Step 3.1: New Route Modules

Replace the 11 existing route modules with 6 focused modules.

### `app/api/constraints.py` (NEW) - "What constraints exist here?"

```python
router = APIRouter(prefix="/api", tags=["constraints"])

@router.get("/resolve")
async def resolve_location(lat: float, lon: float, db = Depends(get_db)):
    """
    Resolve lat/lon to grid hierarchy + constraint summary.
    Reuses existing geo_resolver.py logic.
    Returns:
      - hierarchy: {iso_code, zone_code, substation_name, feeder_id, nearest_pnode}
      - constraints: list of constraint_profiles at each resolved level
      - annotations: list of constraint_annotations for those profiles
      - best_der: highest-value DER type from location_value_stacks
    """

@router.get("/zones/{iso_code}")
@cache_response("zones", ttl=3600)
async def list_zones(iso_code: str, db = Depends(get_db)):
    """
    List zones with constraint summaries.
    Source: mv_zone_constraint_summary
    Returns per zone:
      - zone_code, zone_name, centroid_lat/lon
      - primary_constraint_type, severity_score, severity_tier
      - peak_month, peak_hour, constrained_hours_pct
      - best_der_type, best_der_value_per_kw_year
      - annotation_count (number of linked annotations)
    """

@router.get("/zones/{iso_code}/geometry")
@cache_response("zone-geometries", ttl=86400)
async def zone_geometries(iso_code: str, db = Depends(get_db)):
    """Keep existing zone boundary GeoJSON endpoint."""

@router.get("/zones/{iso_code}/{zone_code}/constraints")
@cache_response("zone-constraints", ttl=300)
async def zone_constraints(iso_code: str, zone_code: str, db = Depends(get_db)):
    """
    All constraint profiles for a zone, with annotations inline.
    Returns:
      - profiles: list of constraint_profiles (congestion, loading, etc.)
        each with its 12x24, severity, and economic value
      - annotations: list of constraint_annotations grouped by profile
      - pnode_hotspots: top 10 pnodes by severity in this zone (from
        constraint_profiles where level=pnode and zone matches)
      - substation_constraints: substations in this zone with loading profiles
    """

@router.get("/zones/{iso_code}/{zone_code}/lmps")
@cache_response("zone-lmps", ttl=300)
async def zone_lmps(iso_code: str, zone_code: str,
                     limit: int = 500, offset: int = 0,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     db = Depends(get_db)):
    """
    Raw hourly LMP data for a zone. Keep existing query against zone_lmps.
    This is the drill-down for users who want to see the underlying data.
    """

@router.get("/locations/{level}/{location_id}/profile")
@cache_response("location-profile", ttl=300)
async def location_profile(level: str, location_id: int, db = Depends(get_db)):
    """
    Composite constraint profile for any location.
    Aggregates all constraint types at this location into a single view.
    Returns:
      - location: {level, id, name, lat, lon, hierarchy_path}
      - profiles: list of constraint_profiles at this location
      - composite_12x24: merged profile (max across types per hour)
      - annotations: linked regulatory context
    """

@router.get("/isos")
@cache_response("isos", ttl=3600)
async def list_isos(db = Depends(get_db)):
    """List ISOs and BAs. Add is_rto filter."""
```

### `app/api/valuations.py` (NEW) - "What DER is most valuable here?"

```python
router = APIRouter(prefix="/api/valuations", tags=["valuations"])

@router.post("/prospective")
async def prospective_valuation(request: ProspectiveValuationRequest,
                                 db = Depends(get_db)):
    """
    Compute value stack for a DER at a lat/lon.
    1. Resolve location via geo_resolver
    2. Look up location_value_stacks for that location + DER type
    3. If pre-computed stack exists: return it
    4. If not: compute on-the-fly from constraint_profiles
    Returns:
      - geo_resolution (hierarchy)
      - value_stack (per-layer breakdown + total $/kW-yr + tier)
      - constraint_profiles (the 12x24s that drive the value)
      - coincidence_factor
      - annotations (regulatory context)
    """

@router.get("/compare")
async def compare_der_types(lat: float, lon: float, db = Depends(get_db)):
    """
    Compare all DER types at a location.
    1. Resolve location
    2. Look up location_value_stacks for all DER types at that location
    3. Return ranked list: [{der_type, total_value, coincidence_factor, tier}]
    Answers: "Which DER type is most valuable here?"
    """

@router.get("/rankings")
@cache_response("rankings", ttl=600)
async def value_rankings(iso_code: str, der_type: str,
                          limit: int = 50, offset: int = 0,
                          db = Depends(get_db)):
    """
    Top locations by value for a given DER type.
    Source: mv_location_rankings filtered by der_type
    Returns: [{location_level, location_id, name, lat, lon,
               total_value_per_kw_year, value_tier, coincidence_factor}]
    Answers: "Where should I deploy solar?"
    """

@router.post("/batch")
@limiter.limit("10/minute")
async def batch_valuation(request: BatchValuationRequest,
                           api_key = Depends(require_api_key),
                           db = Depends(get_db)):
    """
    Batch valuation for up to 100 locations.
    Same as prospective but batched. Returns list of results.
    """
```

### `app/api/profiles.py` (NEW) - "Show me the temporal overlap"

```python
router = APIRouter(prefix="/api/profiles", tags=["profiles"])

@router.get("/constraint/{profile_id}")
async def get_constraint_profile(profile_id: int, db = Depends(get_db)):
    """
    Full constraint profile detail.
    Returns the 12x24, severity, economic value, location context,
    and annotations.
    """

@router.get("/der/{der_type}")
async def get_der_profile(der_type: str, db = Depends(get_db)):
    """
    Canonical DER output profile.
    Returns the 12x24 (or dispatch parameters for dispatchable types),
    eac_category, capacity_factor.
    """

@router.get("/intersection")
async def get_intersection(constraint_profile_id: int, der_type: str,
                            db = Depends(get_db)):
    """
    Intersection analysis between a constraint profile and DER type.
    Returns:
      - constraint_12x24
      - der_12x24
      - overlap_12x24 (element-wise product, for chart rendering)
      - coincidence_factor
      - overlap_hours
      - value_per_kw_year
    The frontend renders this as an overlaid heatmap chart.
    """

@router.get("/zone/{iso_code}/{zone_code}/loadshape")
@cache_response("loadshape", ttl=300)
async def zone_loadshape(iso_code: str, zone_code: str,
                          month: Optional[int] = None,
                          db = Depends(get_db)):
    """
    Backward-compatible loadshape endpoint.
    Reads from constraint_profiles (type=congestion, level=zone)
    instead of the old materialized view.
    Returns: [{hour, avg_congestion}]
    """
```

### `app/api/enrichment.py` (NEW) - Supporting context

```python
router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])

@router.get("/hosting-capacity")
async def nearby_hosting_capacity(lat: float, lon: float,
                                    radius_km: float = 10.0,
                                    db = Depends(get_db)):
    """
    Feeders with hosting capacity near a lat/lon.
    Reuses existing PostGIS ST_DWithin query from hosting_capacity_routes.py.
    Returns: [{feeder_name, hosting_capacity_mw, remaining_capacity_mw,
               constraining_metric, distance_km}]
    """

@router.get("/interconnection-queue")
async def nearby_interconnection(lat: float, lon: float,
                                  radius_km: float = 50.0,
                                  db = Depends(get_db)):
    """
    Interconnection queue projects near a lat/lon.
    Returns: [{project_name, generation_type, capacity_mw, queue_status,
               proposed_online_date, distance_km}]
    """

@router.get("/filings/{utility_code}")
async def utility_filings(utility_code: str,
                           filing_type: Optional[str] = None,
                           db = Depends(get_db)):
    """
    Full filing history for a utility (deep-dive beyond inline annotations).
    Returns: [{docket_number, filing_type, title, filed_date, source_url,
               extracted_constraints, extracted_forecasts}]
    """

@router.get("/utilities")
@cache_response("utilities", ttl=3600)
async def list_utilities(state: Optional[str] = None,
                          iso_code: Optional[str] = None,
                          db = Depends(get_db)):
    """
    Utility registry with hosting capacity summary.
    Merged from existing /utilities and /hosting-capacity/summary endpoints.
    """
```

### `app/api/tiles.py` (KEEP, modify)

Keep existing `tile_routes.py` with these changes:
- Remove data_centers layer from default (move to enrichment)
- Update zones layer to include severity_score from constraint_profiles instead of classification from zone_classifications
- Add constraint intensity to substation tile attributes (from constraint_profiles where level=substation)
- Update pnode tile attributes to use severity_score from constraint_profiles instead of pnode_scores
- Keep all other layers (transmission_lines, feeders, gpkg_*)

### `app/api/admin.py` (KEEP, simplify)

```python
router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.post("/recompute")
async def recompute_profiles(iso_code: Optional[str] = None,
                              year: Optional[int] = None,
                              api_key = Depends(require_api_key),
                              db = Depends(get_db)):
    """Trigger profile recomputation via profile_engine."""

@router.post("/refresh-matviews")
async def refresh_matviews(api_key = Depends(require_api_key),
                            db = Depends(get_db)):
    """Refresh materialized views."""

@router.get("/computation-runs")
async def list_runs(limit: int = 20, db = Depends(get_db)):
    """List recent computation runs with metrics."""
```

---

## Step 3.2: New Pydantic Schemas

### `app/schemas/constraint_schemas.py` (NEW)

```python
class ConstraintProfileResponse(BaseModel):
    id: int
    location_level: str
    location_id: int
    location_name: Optional[str]  # resolved from the appropriate table
    constraint_type: str
    period_year: int
    profile_12x24: dict
    peak_intensity: float
    peak_month: int
    peak_hour: int
    mean_intensity: float
    total_constrained_hours: int
    constrained_hours_pct: float
    severity_score: float
    severity_tier: str
    avg_marginal_cost: Optional[float]
    annual_cost: Optional[float]
    annotations: list["AnnotationResponse"] = []

class AnnotationResponse(BaseModel):
    id: int
    annotation_type: str
    title: str
    summary: Optional[str]
    planned_solution: Optional[str]
    deferral_value_estimate: Optional[float]
    source_url: Optional[str]
    confidence: float

class ZoneConstraintSummaryResponse(BaseModel):
    iso_code: str
    zone_code: str
    zone_name: str
    centroid_lat: Optional[float]
    centroid_lon: Optional[float]
    primary_constraint_type: Optional[str]
    severity_score: Optional[float]
    severity_tier: Optional[str]
    peak_month: Optional[int]
    peak_hour: Optional[int]
    constrained_hours_pct: Optional[float]
    best_der_type: Optional[str]
    best_der_value_per_kw_year: Optional[float]
    annotation_count: int = 0

class GeoResolutionResponse(BaseModel):
    lat: float
    lon: float
    iso_code: Optional[str]
    zone_code: Optional[str]
    substation_name: Optional[str]
    nearest_pnode_name: Optional[str]
    feeder_id: Optional[str]
    resolution_depth: str
    constraints: list[ConstraintProfileResponse]
    best_der: Optional[str]
    total_value_per_kw_year: Optional[float]
```

### `app/schemas/valuation_schemas.py` (REPLACE existing)

```python
class ProspectiveValuationRequest(BaseModel):
    lat: float
    lon: float
    der_type: str
    capacity_mw: float = 1.0

class ValueStackResponse(BaseModel):
    geo_resolution: GeoResolutionResponse
    congestion_value_per_kw_year: float
    loading_value_per_kw_year: float
    capacity_value_per_kw_year: float
    import_stress_value_per_kw_year: float
    total_value_per_kw_year: float
    composite_coincidence_factor: float
    value_tier: str
    constraint_layers: list[dict]
    annotations: list[AnnotationResponse]

class DERComparisonResponse(BaseModel):
    geo_resolution: GeoResolutionResponse
    comparisons: list["DERComparisonItem"]

class DERComparisonItem(BaseModel):
    der_type: str
    eac_category: str
    total_value_per_kw_year: float
    coincidence_factor: float
    value_tier: str
    is_dispatchable: bool

class LocationRankingResponse(BaseModel):
    location_level: str
    location_id: int
    location_name: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    total_value_per_kw_year: float
    value_tier: str
    coincidence_factor: float
```

### `app/schemas/profile_schemas.py` (NEW)

```python
class DERProfileResponse(BaseModel):
    id: int
    der_type: str
    eac_category: str
    profile_12x24: Optional[dict]
    is_dispatchable: bool
    max_dispatch_hours: Optional[float]
    dispatch_power_mw: Optional[float]
    capacity_factor: Optional[float]

class IntersectionResponse(BaseModel):
    constraint_profile: ConstraintProfileResponse
    der_profile: DERProfileResponse
    coincidence_factor: float
    overlap_hours: int
    overlap_12x24: Optional[dict]
    value_per_kw_year: float
    value_tier: str

class LoadshapeHourResponse(BaseModel):
    hour: int
    avg_congestion: float
```

---

## Step 3.3: Update `app/main.py`

```python
# Remove old routers:
# - v1_router (routes.py)
# - valuation_router
# - hierarchy_router
# - wattcarbon_router (keep as optional plugin)
# - batch_router (folded into valuations)
# - hc_router (folded into enrichment)
# - congestion_router (folded into constraints)
# - monitor_router (folded into admin)
# - gpkg_router (folded into tiles)
# - review_router (keep for internal use)

# Add new routers:
from app.api.constraints import router as constraints_router
from app.api.valuations import router as valuations_router
from app.api.profiles import router as profiles_router
from app.api.enrichment import router as enrichment_router
from app.api.tiles import router as tiles_router
from app.api.admin import router as admin_router

app.include_router(constraints_router)
app.include_router(valuations_router)
app.include_router(profiles_router)
app.include_router(enrichment_router)
app.include_router(tiles_router)
app.include_router(admin_router)

# Optional: keep wattcarbon_router and review_router for plugin use
```

---

## Step 3.4: Drop Old Computed Tables

Alembic migration to drop tables that are fully replaced:

```python
# Tables to drop (all data now lives in constraint_profiles / location_value_stacks):
op.drop_table("zone_classifications")
op.drop_table("pnode_scores")
op.drop_table("hierarchy_scores")
op.drop_table("der_valuations")
op.drop_table("der_recommendations")
op.drop_table("congestion_scores")
op.drop_table("hosting_capacity_summaries")
op.drop_table("pipeline_runs")
op.drop_table("hc_ingestion_runs")

# Move to reference schema (if using schemas; otherwise just leave in place):
# op.execute("ALTER TABLE transmission_lines SET SCHEMA reference")
# op.execute("ALTER TABLE gpkg_power_lines SET SCHEMA reference")
# etc.
```

Also delete corresponding model files:
- `app/models/zone_classification.py`
- `app/models/pnode_score.py`
- `app/models/hierarchy_score.py`
- `app/models/der_valuation.py`
- `app/models/der_recommendation.py`
- `app/models/pipeline_run.py`
- `app/models/hosting_capacity.py` (HCIngestionRun, HostingCapacitySummary classes only; keep HostingCapacityRecord)

Delete old core modules:
- `core/constraint_classifier.py`
- `core/pnode_analyzer.py`
- `core/hierarchy_scorer.py`
- `core/congestion_calculator.py`

Keep but mark as plugin:
- `core/valuation_engine.py` (backward compat for WattCarbon retrospective)
- `core/retrospective_valuator.py` (WattCarbon plugin)

---

## Step 3.5: Update Tile Routes

In `app/api/tiles.py`, update LAYER_CONFIG to read from new tables:

```python
LAYER_CONFIG = {
    "zones": {
        "table": "zones",
        "join": """
            LEFT JOIN constraint_profiles cp
              ON cp.location_level = 'zone'
              AND cp.location_id = zones.id
              AND cp.constraint_type = 'congestion'
        """,
        "attributes": ["zone_code", "zone_name", "cp.severity_score",
                        "cp.severity_tier", "cp.constrained_hours_pct"],
    },
    "pnodes": {
        "table": "pnodes",
        "join": """
            LEFT JOIN constraint_profiles cp
              ON cp.location_level = 'pnode'
              AND cp.location_id = pnodes.id
              AND cp.constraint_type = 'congestion'
        """,
        "attributes": ["node_id_external", "node_name",
                        "cp.severity_score", "cp.severity_tier"],
    },
    "substations": {
        # Same pattern: join to constraint_profiles for loading severity
    },
    # Keep: transmission_lines, feeders, der_locations, gpkg_* layers
}
```

---

## Step 3.6: Update Cache Configuration

```python
# New cache prefixes and TTLs:
CACHE_CONFIG = {
    "isos": 3600,
    "zones": 3600,
    "zone-geometries": 86400,
    "zone-constraints": 300,
    "zone-lmps": 300,
    "loadshape": 300,
    "location-profile": 300,
    "rankings": 600,
    "utilities": 3600,
}
```

---

## Verification

After Phase 3:
- [ ] `GET /api/resolve?lat=37.7749&lon=-122.4194` returns hierarchy + constraints + annotations
- [ ] `GET /api/zones/caiso` returns zones with severity scores and best DER recommendations
- [ ] `GET /api/zones/caiso/PGAE/constraints` returns all constraint profiles with annotations
- [ ] `POST /api/valuations/prospective` returns value stack with per-layer breakdown
- [ ] `GET /api/valuations/compare?lat=37.7749&lon=-122.4194` ranks all DER types
- [ ] `GET /api/valuations/rankings?iso_code=caiso&der_type=solar` returns top locations
- [ ] `GET /api/profiles/der/solar` returns the canonical 12x24 solar profile
- [ ] `GET /api/profiles/intersection?constraint_profile_id=1&der_type=solar` returns overlap data
- [ ] `GET /api/enrichment/hosting-capacity?lat=37.7749&lon=-122.4194` returns nearby feeders
- [ ] `GET /api/tiles/zones/5/9/12.mvt` returns MVT with severity_score attribute
- [ ] Old tables dropped successfully
- [ ] Old API routes return 404 (confirming clean replacement)

## Files Created/Modified/Deleted

| File | Action |
|---|---|
| `app/api/constraints.py` | CREATE |
| `app/api/valuations.py` | CREATE |
| `app/api/profiles.py` | CREATE |
| `app/api/enrichment.py` | CREATE |
| `app/api/admin.py` | CREATE |
| `app/api/tiles.py` | MODIFY (update LAYER_CONFIG to read from constraint_profiles) |
| `app/schemas/constraint_schemas.py` | CREATE |
| `app/schemas/valuation_schemas.py` | REPLACE |
| `app/schemas/profile_schemas.py` | CREATE |
| `app/main.py` | MODIFY (swap routers) |
| `app/api/v1/routes.py` | DELETE |
| `app/api/v1/valuation_routes.py` | DELETE |
| `app/api/v1/hierarchy_routes.py` | DELETE |
| `app/api/v1/congestion_routes.py` | DELETE |
| `app/api/v1/hosting_capacity_routes.py` | DELETE |
| `app/api/v1/batch_routes.py` | DELETE |
| `app/api/v1/monitor_routes.py` | DELETE |
| `app/api/v1/gpkg_routes.py` | DELETE |
| `app/models/zone_classification.py` | DELETE |
| `app/models/pnode_score.py` | DELETE |
| `app/models/hierarchy_score.py` | DELETE |
| `app/models/der_valuation.py` | DELETE |
| `app/models/der_recommendation.py` | DELETE |
| `app/models/pipeline_run.py` | DELETE |
| `core/constraint_classifier.py` | DELETE |
| `core/pnode_analyzer.py` | DELETE |
| `core/hierarchy_scorer.py` | DELETE |
| `core/congestion_calculator.py` | DELETE |
| `alembic/versions/u3o5i8e94l2m_drop_old_tables.py` | CREATE |
