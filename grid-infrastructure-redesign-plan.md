# Data Infrastructure Redesign: Scalable Geospatial Dashboard

## Context

The grid constraint classifier dashboard has accumulated nine compounding performance problems through incremental feature additions. A debugging session exposed the root causes:

1. **41-second data-centers query**: SQLAlchemy loads full Zone ORM objects (including 12MB `boundary_geojson` JSON columns) for every row in a join, even though only `zone_code` is needed
2. **11.9MB zones response**: Every zone's full GeoJSON polygon is serialized inline on every ISO selection
3. **Single-threaded uvicorn**: One slow response blocks all concurrent requests
4. **No spatial indexing**: Coordinates stored as individual lat/lon FLOAT columns with no PostGIS, no GiST indexes, no spatial queries
5. **DOM node per marker**: Each of 565 pnodes + 1,179 data centers is an individual Vue `LCircleMarker` component with its own DOM element and popup
6. **No server-side clustering or pagination**: Unbounded result sets sent to the browser in full
7. **No caching**: Every request hits PostgreSQL directly
8. **No vector tiles**: All geometry shipped as raw JSON payloads
9. **Map pan race conditions**: Vue-Leaflet prop bindings fight with Leaflet's internal state management

The user wants to scale to 1000x (500K pnodes, 1M+ data centers, transmission lines, power plants) and render complex linear infrastructure like high-voltage power lines. The current architecture cannot support this.

## Current Architecture

### Database (PostgreSQL, no PostGIS)
- 16 tables, 13 JSON columns across 9 tables
- `Zone.boundary_geojson` (JSON): full GeoJSON polygons, ~600KB each
- `TransmissionLine.geometry_json` (JSON): linestring geometries (model exists, not rendered)
- `Feeder.geometry_json` (JSON): distribution feeder paths
- Point data (Pnode, DataCenter, Substation, DERLocation, Circuit): individual `lat`/`lon` FLOAT columns
- Missing indexes on `data_centers.iso_id`, `data_centers.zone_id`, `pnodes.iso_id`
- No spatial indexes of any kind

### API (FastAPI, single worker)
- Zones endpoint returns full ORM objects with boundary_geojson inline
- Pnodes endpoint returns all scores for an ISO with no pagination
- Data-centers query joins Zone table (loading 12MB boundary_geojson per row)
- No caching (no Redis, no ETags, no query-level cache)
- Uvicorn runs single worker

### Frontend (Vue 3 + Leaflet SVG renderer)
- `@vue-leaflet/vue-leaflet` with `LCircleMarker` per data point
- `LGeoJson` per zone boundary
- Full dataset loaded on ISO selection via `isoStore.selectISO()`
- No clustering, no canvas/WebGL, no tile-based loading
- No debouncing on filter changes

## Approach: PostGIS + Vector Tiles + MapLibre GL JS

The redesign separates **geometry rendering** (vector tiles via PostGIS `ST_AsMVT`) from **attribute serving** (JSON API without geometry). The map renders geometry from tiles using WebGL (MapLibre GL JS), while the API returns lightweight metadata and scores.

### Key Design Decisions

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Spatial database | PostGIS | Heroku PostgreSQL supports it natively. Spatial indexes (GiST) are mandatory at 500K+ points. `ST_AsMVT` generates vector tiles directly from SQL. `shapely` already in requirements.txt. |
| Tile server | Custom `ST_AsMVT` endpoints in FastAPI | Avoids separate Martin/pg_tileserv dyno on Heroku. Full SQLAlchemy query control for joining scores with geometry. Simpler ops. |
| Map library | MapLibre GL JS | WebGL renders 100K-1M+ features natively. Native MVT support. Data-driven styling (color/size by attribute without re-rendering). Leaflet maxes out at ~5K markers even with Canvas renderer. |
| Clustering | Server-side via PostGIS `ST_ClusterDBSCAN` | Cannot send 1M points to browser. Clustering in SQL within tile generation query. Zero client overhead. |
| Time-series | PostgreSQL partitioning + materialized views | Avoids TimescaleDB addon cost. Sufficient for the access patterns (hourly aggregations, monthly filters). |
| Caching | Redis + HTTP cache headers | Need server-side invalidation when pipeline runs complete. Redis available as Heroku addon ($3-15/month). |

## Phased Implementation

### Phase 0: Quick Wins (2-3 days, 10-50x improvement)

No architectural changes. Fixes the acute problems.

**0.1 Separate geometry from zone metadata**

Split the zones endpoint so boundary GeoJSON is never loaded unless explicitly requested.

| File | Change |
|------|--------|
| `app/schemas/responses.py` | Add `ZoneMetadataResponse` (without `boundary_geojson`) |
| `app/api/v1/routes.py` | Change `list_zones` to column-level SELECT excluding `boundary_geojson`. Add new `GET /isos/{iso_id}/zones/boundaries` endpoint. |
| `frontend/src/api/isos.ts` | Add `fetchZoneBoundaries()` function |
| `frontend/src/stores/isoStore.ts` | Store boundaries separately, load lazily after metadata |
| `frontend/src/components/map/ZoneLayer.vue` | Source boundaries from separate ref |

Expected: zones metadata response drops from 11.9MB/41s to ~10KB/100ms.

**0.2 Add missing database indexes**

New Alembic migration adding indexes on: `data_centers.iso_id`, `data_centers.zone_id`, `pnodes.iso_id`, `substations.iso_id`, `substations.zone_id`, `der_locations.iso_id`, `pnode_scores.pipeline_run_id`, `zone_classifications.pipeline_run_id`, `der_recommendations.pipeline_run_id`.

**0.3 Add pagination to unbounded endpoints**

Add `limit`/`offset` parameters to `get_all_pnode_scores`, `get_classifications`, `get_recommendations`.

**0.4 Multiple uvicorn workers**

Update Procfile: add `--workers 3` for Standard-1X dyno (512MB). Local dev: use `--workers 2`.

**0.5 Fix frontend rendering issues**

Remove `v-if` conditional mounting on DataCenterMarkers (already done). Fix map panning to use direct `setView` with ISO_VIEW lookup (already done). Add 150ms debounce on filter changes.

---

### Phase 1: PostGIS Migration (1-2 weeks)

**1.1 Enable PostGIS and add geometry columns**

New dependency: `geoalchemy2>=0.14`

Alembic migration:
1. `CREATE EXTENSION IF NOT EXISTS postgis`
2. Add `boundary_geom Geometry('MULTIPOLYGON', 4326)` to zones
3. Add `geom Geometry('MULTILINESTRING', 4326)` to transmission_lines
4. Add `geom Geometry('LINESTRING', 4326)` to feeders
5. Add `geom Geometry('POINT', 4326)` to pnodes, data_centers, substations, circuits, der_locations
6. Populate from existing JSON/float columns
7. Create GiST spatial indexes on all geometry columns
8. Keep original columns for backward compatibility during transition

**1.2 Spatial query endpoints**

New endpoint: `GET /isos/{iso_id}/pnodes/bbox?west=&south=&east=&north=&limit=500`

Uses `ST_MakeEnvelope` for efficient spatial query with GiST index. Enables viewport-based data loading on the frontend (only request what's visible).

Similar bbox endpoints for data-centers, substations, der-locations.

**1.3 Update model files**

Add GeoAlchemy2 `Geometry` mapped columns alongside existing `lat`/`lon` floats. Add trigger or application-level sync to keep both representations in sync on INSERT/UPDATE.

| File | Change |
|------|--------|
| `app/models/zone.py` | Add `boundary_geom` column |
| `app/models/pnode.py` | Add `geom` column |
| `app/models/data_center.py` | Add `geom` column |
| `app/models/substation.py` | Add `geom` column |
| `app/models/transmission_line.py` | Add `geom` column |
| `app/models/feeder.py` | Add `geom` column |
| `app/models/der_location.py` | Add `geom` column |
| `app/models/circuit.py` | Add `geom` column |

---

### Phase 2: Vector Tiles + MapLibre (1-2 weeks, can overlap Phase 1)

**2.1 MVT tile endpoint**

New file: `app/api/v1/tile_routes.py`

`GET /tiles/{layer}/{z}/{x}/{y}.mvt` where layer is one of: zones, pnodes, data_centers, transmission_lines, substations, feeders, der_locations.

Implementation:
- Compute tile bbox using `ST_TileEnvelope(z, x, y)`
- Query geometries within bbox using `ST_AsMVTGeom` + `ST_AsMVT`
- Apply zoom-level simplification: `ST_Simplify(geom, tolerance)` at low zoom
- Include relevant attributes (severity_score, tier, capacity_mw, voltage_kv)
- Return as `application/vnd.mapbox-vector-tile`
- Add `Cache-Control: public, max-age=3600` headers

Zoom-level rules for transmission lines:

| Zoom | Min voltage | Simplification |
|------|------------|----------------|
| 5-6 | 345 kV+ | `ST_Simplify(geom, 0.05)` |
| 7-8 | 230 kV+ | `ST_Simplify(geom, 0.01)` |
| 9-10 | 115 kV+ | `ST_Simplify(geom, 0.005)` |
| 11+ | All | Full resolution |

**2.2 MapLibre GL JS frontend**

New dependencies: `maplibre-gl`, `vue-maplibre-gl`

New component: `frontend/src/components/map/GridMapGL.vue`

Uses `<MglMap>` with `<MglVectorTileSource>` and declarative layer components:
- `<MglFillLayer>` for zone boundaries (colored by classification)
- `<MglLineLayer>` for transmission lines (colored/sized by voltage_kv)
- `<MglCircleLayer>` for pnodes (sized by severity_score, colored by tier)
- `<MglCircleLayer>` for data centers (sized by capacity_mw, colored by status)

All styling is data-driven (MapLibre expressions). Zero Vue component instances per marker. All features rendered by WebGL.

Base map: CartoDB GL Positron (`https://basemaps.cartocdn.com/gl/positron-gl-style/style.json`)

**2.3 Migration strategy**

Add MapLibre alongside Leaflet with a feature flag in mapStore (`mapEngine: 'leaflet' | 'maplibre'`). Migrate one layer at a time. Remove Leaflet components once MapLibre is validated.

| File | Change |
|------|--------|
| `frontend/package.json` | Add `maplibre-gl`, `vue-maplibre-gl` |
| `frontend/src/components/map/GridMapGL.vue` | New MapLibre map component |
| `frontend/src/stores/mapStore.ts` | Add `mapEngine` toggle |
| `frontend/src/views/DashboardView.vue` | Conditional rendering of GridMap vs GridMapGL |

---

### Phase 3: Caching (1 week, can start after Phase 0)

**3.1 Redis caching layer**

New dependency: `redis>=5.0`

New file: `app/cache.py` with `cache_response(prefix, ttl)` decorator.

| Endpoint | TTL | Rationale |
|----------|-----|-----------|
| `/tiles/{layer}/{z}/{x}/{y}.mvt` | 1 hour (HTTP header) | Geometry rarely changes |
| `/isos/{iso_id}/zones` | 1 hour | Zone metadata is near-static |
| `/isos/{iso_id}/zones/boundaries` | 24 hours | Boundary polygons never change |
| `/isos/{iso_id}/classifications` | 5 minutes | Changes when pipeline runs |
| `/isos/{iso_id}/pnodes` | 5 minutes | Changes when pipeline runs |
| `/data-centers` | 1 hour | Scraped data updates infrequently |

**3.2 Cache invalidation**

Add pipeline-run webhook that clears caches for affected ISO when a pipeline run completes.

**3.3 ETag support for tiles**

Compute ETag from most recent `pipeline_run.completed_at` for the ISO. Return `304 Not Modified` when client sends matching `If-None-Match`.

---

### Phase 4: Server-Side Clustering (3-5 days, requires Phase 1+2)

Implemented inside the MVT tile generation query, not as a separate service.

At zoom < 10: cluster points with `ST_ClusterDBSCAN`, return cluster centroids with count + aggregate attributes (avg severity, dominant tier).

At zoom >= 10: return individual points.

```sql
-- Low zoom: cluster within tile
WITH clustered AS (
  SELECT
    ST_ClusterDBSCAN(geom, eps := {distance}, minpoints := 2) OVER () AS cid,
    severity_score, tier, geom
  FROM pnodes
  WHERE ST_Intersects(geom, ST_TileEnvelope({z}, {x}, {y}))
)
SELECT
  ST_AsMVTGeom(ST_Centroid(ST_Collect(geom)), bounds) AS geom,
  COUNT(*) as point_count,
  AVG(severity_score) as avg_score
FROM clustered GROUP BY cid
```

---

### Phase 5: Transmission Lines and Linear Features (1 week, requires Phase 1+2)

TransmissionLine and Feeder models already exist. After PostGIS migration, their `geometry_json` columns become proper `Geometry` types with spatial indexes.

MVT tiles serve them with zoom-dependent voltage filtering and simplification (see Phase 2.1 table).

MapLibre line styling uses data-driven expressions for color by voltage_kv and width by voltage_kv. Click/hover interaction uses `queryRenderedFeatures`.

---

### Phase 6: Time-Series at Scale (1 week, independent)

**6.1 PostgreSQL range partitioning**

Partition `zone_lmps` by `iso_id` (list partitioning). Each ISO's LMP data in its own partition.

**6.2 Materialized views for aggregations**

```sql
CREATE MATERIALIZED VIEW zone_lmp_hourly_avg AS
SELECT iso_id, zone_id, hour_local, month,
       AVG(congestion) as avg_congestion,
       AVG(ABS(congestion)) as avg_abs_congestion,
       MAX(ABS(congestion)) as max_congestion
FROM zone_lmps
GROUP BY iso_id, zone_id, hour_local, month;
```

Replaces real-time aggregation in `/loadshape` endpoint. Refresh after each pipeline run.

---

### Phase 7: Multi-ISO Support (3-5 days, requires all above)

- Change `isoStore.selectedISO` from `string | null` to `string[]`
- Tile endpoints work across ISOs (spatial, not ISO-filtered by default)
- Add optional `iso_id` filter parameter to tile endpoints

---

## Implementation Sequencing

```
Phase 0 (2-3 days)   Quick wins, no architectural changes
  |
Phase 1 (1-2 weeks)  PostGIS migration
  |
Phase 2 (1-2 weeks)  MVT tiles + MapLibre (can overlap Phase 1)
  |   |
  |   Phase 3 (1 week)  Caching (can start after Phase 0, parallel with Phase 2)
  |
Phase 4 (3-5 days)   Server-side clustering
  |
Phase 5 (1 week)     Linear features
  |
Phase 6 (1 week)     Time-series scaling (independent, can run in parallel)
  |
Phase 7 (3-5 days)   Multi-ISO
```

Total: 6-8 weeks for full implementation.

## Backward Compatibility

At no point does the existing dashboard break:
- Phase 0-1: Existing API endpoints continue to work. New geometry columns coexist with JSON columns.
- Phase 2: New `/tiles/` endpoints are additive. Leaflet components remain until MapLibre is validated.
- Phase 3: Caching is transparent to the API contract.
- Phase 4-7: All additive changes.

## Verification

After Phase 0:
- `curl /api/v1/isos/pjm/zones` returns < 50KB (no boundary_geojson)
- Data centers query completes in < 1 second
- Dashboard loads PJM in < 3 seconds

After Phase 2:
- `curl /tiles/pnodes/7/37/48.mvt` returns binary MVT data
- MapLibre renders 500K+ pnodes without frame drops
- Transmission lines visible at zoom 7+ with voltage coloring

After Phase 4:
- At zoom 5, pnode clusters show counts (e.g., "347 nodes")
- At zoom 10+, individual pnodes appear

## Critical Files

| File | Role |
|------|------|
| `app/api/v1/routes.py` | All current API endpoints (geometry separation, pagination) |
| `app/schemas/responses.py` | Response models (add ZoneMetadataResponse) |
| `app/models/zone.py` | Zone model (add PostGIS boundary_geom column) |
| `app/models/transmission_line.py` | TransmissionLine model (add PostGIS geom column) |
| `app/models/pnode.py` | Pnode model (add PostGIS geom column) |
| `app/models/data_center.py` | DataCenter model (add PostGIS geom column) |
| `app/database.py` | Database config (pool sizing for multiple workers) |
| `frontend/src/components/map/GridMap.vue` | Current Leaflet map (add MapLibre toggle) |
| `frontend/src/components/map/ZoneLayer.vue` | Zone boundary rendering (separate from metadata) |
| `frontend/src/stores/isoStore.ts` | Data loading on ISO selection (viewport-based loading) |
| `frontend/src/stores/mapStore.ts` | Map state (add mapEngine toggle) |
| `alembic/versions/` | Migration files for PostGIS + indexes |
