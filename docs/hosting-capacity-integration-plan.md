# Hosting Capacity Data Integration Plan

## Context

The DOE's US Atlas of Electric Distribution System Hosting Capacity Maps lists 97 utility resources across 26 states, DC, and Puerto Rico. These contain feeder-level hosting capacity data (how much new DER each circuit can accept) that directly complements the grid-constraint-classifier's existing LMP-based constraint analysis and DER valuation engine. Integrating this data would add a critical distribution-level dimension: the project currently has wholesale market constraints (ISO/zone/pnode) and some GRIP substation loading, but lacks utility-published hosting capacity at the feeder/circuit level across the country.

**Key finding from research:** Nearly all utilities use ArcGIS/ESRI technology. A single reusable ArcGIS REST client with per-utility YAML configs can cover ~80% of resources.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  YAML Configs (1 per utility, ~50 files)                │
│  adapters/hosting_capacity/configs/*.yaml               │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  ArcGIS REST Client (reusable, extracted from           │
│  scraping/grip_fetcher.py pagination pattern)           │
│  adapters/arcgis_client.py                              │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  Hosting Capacity Adapters                              │
│  adapters/hosting_capacity/base.py (abstract)           │
│  adapters/hosting_capacity/arcgis_adapter.py (generic)  │
│  adapters/hosting_capacity/exelon_adapter.py (6 utils)  │
│  adapters/hosting_capacity/registry.py (factory)        │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  Normalizer                                             │
│  adapters/hosting_capacity/normalizer.py                │
│  field renaming, kW→MW, constraint mapping, centroids   │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  DB Writer + Parquet Cache                              │
│  data/hosting_capacity/{utility_code}/*.parquet         │
│  PostgreSQL: utilities, hosting_capacity_records,       │
│              hc_ingestion_runs, hosting_capacity_summaries│
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  API: /api/v1/utilities/*, /api/v1/hosting-capacity/*   │
│  Frontend: HostingCapacityLayer.vue + store + API client│
└─────────────────────────────────────────────────────────┘
```

---

## Phase 1: Database Schema (New Models + Migration)

### New models (4 tables)

**`Utility`** (`app/models/utility.py`)
- `utility_code` (unique, e.g. "pge", "pepco")
- `utility_name`, `parent_company` (e.g. "Exelon")
- `iso_id` (FK to isos) -- links utility to its wholesale market
- `states` (JSON), `data_source_type`, `requires_auth`
- `last_ingested_at`, `config_json`

**`HostingCapacityRecord`** (`app/models/hosting_capacity.py`)
- `utility_id` (FK), `ingestion_run_id` (FK)
- Feeder identification: `feeder_id_external`, `feeder_name`, `substation_name`
- Optional link to existing hierarchy: `feeder_id` (FK), `substation_id` (FK)
- **Canonical capacity fields** (all normalized to MW): `hosting_capacity_mw`, `hosting_capacity_min_mw`, `hosting_capacity_max_mw`, `installed_dg_mw`, `queued_dg_mw`, `remaining_capacity_mw`
- `constraining_metric` (thermal/voltage/protection/islanding)
- Feeder characteristics: `voltage_kv`, `phase_config`, `is_overhead`, `is_network`
- Geometry: `geometry_type`, `geometry_json`, `centroid_lat`, `centroid_lon`
- Provenance: `record_date`, `raw_attributes` (JSON, original unmodified fields)
- Unique on `(utility_id, feeder_id_external, record_date)`
- Spatial index on `(centroid_lat, centroid_lon)`

**`HCIngestionRun`** (same file)
- `utility_id`, `started_at`, `completed_at`, `status`, `records_fetched`, `records_written`, `error_message`, `source_url`

**`HostingCapacitySummary`** (same file)
- Pre-aggregated per-utility stats: `total_feeders`, `total_hosting_capacity_mw`, `total_installed_dg_mw`, `total_remaining_capacity_mw`, `constrained_feeders_count`, `constraint_breakdown` (JSON), `computed_at`

### Design decision: New models, not extending Feeder/Substation

The existing Feeder/Substation models store GRIP operational data from one source (PG&E). Hosting capacity data comes from 97 utilities with different schemas, IDs, and update cadences. HostingCapacityRecord links back to existing Feeder/Substation via optional FKs when spatial matching succeeds, keeping both data pipelines independent.

### Files to modify
- Create `app/models/utility.py`, `app/models/hosting_capacity.py`
- Update `app/models/__init__.py` to export new models
- Create Alembic migration in `alembic/versions/`

---

## Phase 2: ArcGIS REST Client Library

**File:** `adapters/arcgis_client.py`

Extract the pagination pattern from `scraping/grip_fetcher.py` (lines 82-112) into a reusable class:

- `query_features(url, where, out_fields, return_geometry, out_sr, page_size, max_records, auth_token)` -- paginated feature query with offset/count
- `query_features_geojson(...)` -- same but returns GeoJSON FeatureCollection
- `discover_layers(service_url)` -- hit `?f=json` to list layers and field schemas
- `get_field_schema(layer_url)` -- field names and types for a specific layer
- `web_mercator_to_wgs84(x, y)` -- extracted from `grip_fetcher._web_mercator_to_wgs84`
- `compute_centroid(geometry)` -- centroid from any GeoJSON geometry type (Point, MultiLineString, Polygon)

Key behaviors: exponential backoff retry (3 attempts), configurable rate limiting (0.5s default between requests), coordinate reprojection to WGS84, `exceededTransferLimit` detection, 120s timeout.

After building this, refactor `scraping/grip_fetcher.py` to use it (reducing ~70 lines of duplicated pagination code).

---

## Phase 3: Utility Adapter + Config System

### Config format (YAML, one per utility)

**Directory:** `adapters/hosting_capacity/configs/`

Following the existing pattern in `adapters/configs/caiso.yaml`:

```yaml
# Example: adapters/hosting_capacity/configs/pge.yaml
utility_code: pge
utility_name: "Pacific Gas & Electric"
parent_company: null
iso_id: caiso
states: [CA]
data_source_type: arcgis_feature
requires_auth: false

service_url: "https://services2.arcgis.com/mJaJSax0KPHoCNB6/ArcGIS/rest/services/DRPComplianceRelProd/FeatureServer"
layer_index: 7   # ICAEstimatedCapacitySummary
page_size: 2000
out_sr: 4326
capacity_unit: kw

url_discovery_method: static

field_map:
  FeederId: feeder_id_external
  FeederName: feeder_name
  SubstationName: substation_name
  ICA_kW: hosting_capacity_mw
  Existing_Gen_kW: installed_dg_mw
  Queued_Gen_kW: queued_dg_mw
  Limiting_Factor: constraining_metric
  Voltage: voltage_kv
```

### Adapter hierarchy

- `adapters/hosting_capacity/base.py` -- `UtilityHCConfig` dataclass + `HostingCapacityAdapter` ABC with `pull_hosting_capacity()` and `resolve_current_url()` abstract methods
- `adapters/hosting_capacity/arcgis_adapter.py` -- Generic ArcGIS FeatureServer adapter (covers ~60% of utilities)
- `adapters/hosting_capacity/exelon_adapter.py` -- Extends arcgis_adapter for the 6 Exelon utilities sharing org `agWTKEK7X5K1Bx7o`, handles ComEd's quarterly URL rotation
- `adapters/hosting_capacity/registry.py` -- Factory that loads YAML and returns appropriate adapter

### Caching

Following existing Parquet cache pattern: `data/hosting_capacity/{utility_code}/hosting_capacity.parquet`

---

## Phase 4: Normalization Pipeline

**File:** `adapters/hosting_capacity/normalizer.py`

Follows the pattern of `GridstatusAdapter._normalize_zone_lmps()` (gridstatus_adapter.py lines 64-119):

1. **Field renaming** -- apply `field_map` from YAML config
2. **Unit conversion** -- kW to MW when `capacity_unit: kw`
3. **Constraint normalization** -- map diverse names ("Thermal", "thermal limit", "Voltage", "voltage rise", "Protection", "fault current", "Islanding") to canonical values
4. **Remaining capacity computation** -- `remaining = hosting - installed - queued` when not already provided
5. **Centroid extraction** -- compute `centroid_lat`/`centroid_lon` from geometry (handles Point, MultiLineString, Polygon)
6. **Validation** -- drop rows without `feeder_id_external`, log warnings for anomalies

---

## Phase 5: CLI Ingestion Command

**File:** `cli/ingest_hosting_capacity.py`

Following the pattern of `cli/run_pipeline.py` and `cli/ingest_load_profiles.py`:

```
python -m cli.ingest_hosting_capacity --utility pge              # Single utility
python -m cli.ingest_hosting_capacity --utility all              # All configured
python -m cli.ingest_hosting_capacity --utility all --category arcgis_feature
python -m cli.ingest_hosting_capacity --utility pge --force      # Force re-download
python -m cli.ingest_hosting_capacity --utility pge --dry-run    # Fetch only, no DB
python -m cli.ingest_hosting_capacity --list-utilities           # Show configured utilities
python -m cli.ingest_hosting_capacity --utility pge --discover   # Discover layers/fields
```

**DB Writer:** New `HostingCapacityWriter` class (in `app/hc_writer.py`) following `PipelineWriter` patterns: batch insert, rollback on error, ingestion run tracking.

---

## Phase 6: API Endpoints

**File:** `app/api/v1/hosting_capacity_routes.py`

| Endpoint | Purpose |
|----------|---------|
| `GET /utilities` | List all configured utilities with ingestion status |
| `GET /utilities/{code}` | Detail for one utility |
| `GET /utilities/{code}/hosting-capacity` | Feeder-level HC records (filterable by capacity, constraint, bbox) |
| `GET /utilities/{code}/hosting-capacity/summary` | Pre-aggregated stats |
| `GET /utilities/{code}/hosting-capacity/geojson` | GeoJSON FeatureCollection for map layer |
| `GET /hosting-capacity/nearby?lat=X&lon=Y&radius_km=10` | Cross-utility spatial search |
| `GET /hosting-capacity/ingestion-runs` | Ingestion history / freshness |

**Schemas:** `app/schemas/hosting_capacity_schemas.py`
**Registration:** Add router to `app/main.py`

---

## Phase 7: Frontend Map Layer

### New files
- `frontend/src/api/hostingCapacity.ts` -- API client functions
- `frontend/src/stores/hostingCapacityStore.ts` -- Pinia store (following `hierarchyStore.ts` pattern)
- `frontend/src/components/map/HostingCapacityLayer.vue` -- Map component (following `SubstationMarkers.vue` pattern)

### Modified files
- `frontend/src/stores/mapStore.ts` -- add `showHostingCapacity` ref
- `frontend/src/components/map/GridMap.vue` -- add `<HostingCapacityLayer v-if="mapStore.showHostingCapacity" />`
- `frontend/src/views/DashboardView.vue` -- add layer toggle checkbox + utility selector dropdown
- `frontend/src/components/map/MapLegend.vue` -- add HC color legend

### Color scale
Green (>5MW remaining) -> Yellow (2-5MW) -> Orange (0.5-2MW) -> Red (<0.5MW), matching existing severity patterns.

### Interaction
- Circle markers at feeder centroids
- Popup shows: feeder name, hosting capacity, remaining capacity, constraint type, utility
- Click selects feeder and shows detail in side panel
- Utility dropdown filters which utility's data to display

---

## Phase 8: Utility Rollout Waves

### Wave 1: Foundation + PG&E (proof of concept)
All infrastructure + PG&E config. PG&E is ideal because the project already fetches from the same ArcGIS FeatureServer (DRPComplianceRelProd) for GRIP substation data, so we can validate the new pipeline against known data.

**ArcGIS endpoints confirmed:**
- PG&E: `services2.arcgis.com/.../DRPComplianceRelProd/FeatureServer` (26+ layers, public, 2000/page)

### Wave 2: California IOUs
- SCE: `drpep.sce.com/arcgis_server/rest/services/Hosted` (18 FeatureServers, public, also has Open Data Hub with WMS/WFS)
- SDG&E: Custom portal, requires registration. Config as `data_source_type: custom_auth`, implement later or mark as unavailable initially.

### Wave 3: Exelon Family (6 utilities, 1 adapter)
All share ArcGIS org `agWTKEK7X5K1Bx7o` at `services3.arcgis.com`:
- **Pepco/DPL/ACE**: `PHI_Hosting_Capacity_Public/FeatureServer` (6 layers, 3500/page, feeder polylines)
- **BGE**: `BGE_HOSTING_CAPACITY_AGOL/FeatureServer` (grid squares, 1000/page)
- **ComEd**: Quarterly URL rotation (e.g. `ComEd_PV_Hosting_Capacity_JUN2024`), needs URL discovery

### Wave 4: Major East Coast
- Dominion: `services.arcgis.com/.../Primary_Hosting_Capacity_Available_EB/FeatureServer` (public, 2000/page, simple schema)
- National Grid: `systemdataportal.nationalgrid.com/arcgis/rest/services/.../MapServer` (self-hosted, 2000/page)
- Eversource: `epochprodgasdist.eversource.com/wamgasgis/rest/services/.../MapServer` (self-hosted, 1000/page)
- Con Edison: ArcGIS Online MapSeries (endpoints discoverable from map config JSON)

### Wave 5: Midwest + Mountain West
- Xcel Energy: `services1.arcgis.com/.../NSPM_may2025_popUps/FeatureServer` (38 fields per feeder, very data-rich)
- Ameren, DTE, Consumers Energy
- Duke Energy: HDR Gateway hosted, may need special handling

### Wave 6: Frontend
Build the map layer, store, and API client after backend has data from Waves 1-4.

### Wave 7: Remaining + Non-ArcGIS
- Portland General (Mapbox, needs reverse engineering)
- Hawaiian Electric (proprietary, needs network inspection)
- Authentication flows for SDG&E, NV Energy, Georgia Power
- Small co-ops (limited/no data)

---

## Utility Resource Catalog (97 resources from DOE Atlas)

| State | Utility | Type | Parent | ISO | Access | Priority |
|-------|---------|------|--------|-----|--------|----------|
| AZ | Garkane Energy | Asset Map | - | - | Public | Low (no HC data) |
| CA | PG&E | ArcGIS FS | - | CAISO | Public | Wave 1 |
| CA | SCE | ArcGIS Ent | - | CAISO | Public | Wave 2 |
| CA | SDG&E | Custom | Sempra | CAISO | Auth required | Wave 7 |
| CA | CEC EDGE Tool | Custom | - | CAISO | Public | Wave 7 |
| CA | LADWP | Custom | - | - | Public | Wave 7 |
| CO | Xcel Energy | ArcGIS FS | - | - | Public | Wave 5 |
| CT | Eversource (DG) | ArcGIS | - | ISO-NE | Public | Wave 4 |
| CT | Eversource (EV) | ArcGIS | - | ISO-NE | Public | Wave 4 |
| CT | United Illuminating (DG) | ArcGIS | Avangrid | ISO-NE | Public | Wave 5 |
| CT | United Illuminating (EV) | Custom | Avangrid | ISO-NE | Public | Wave 7 |
| DE | Delmarva Power (DG) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| DE | Delmarva Power (EV) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| DC | Pepco (DG) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| DC | Pepco (EV) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| GA | Georgia Power | ArcGIS | Southern Co | - | Auth required | Wave 7 |
| HI | Hawaiian Electric (DG) | Proprietary | - | - | Public | Wave 7 |
| HI | Hawaiian Electric (EV) | Proprietary | - | - | Public | Wave 7 |
| ID | Avista | Custom | - | - | Public | Wave 7 |
| IL | Ameren (DG) | ArcGIS | - | MISO | Public | Wave 5 |
| IL | Ameren (EV) | ArcGIS | - | MISO | Public | Wave 5 |
| IL | ComEd (DG) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| IL | ComEd (EV) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| ME | CMP (DG) | ArcGIS | Avangrid | ISO-NE | Public | Wave 5 |
| ME | CMP (EV) | Custom | Avangrid | ISO-NE | Public | Wave 7 |
| ME | Versant Power | Custom | - | ISO-NE | Public | Wave 7 |
| MD | BGE | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| MD | Choptank EC | Custom | - | PJM | Public | Wave 7 |
| MD | Delmarva Power (DG) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| MD | Delmarva Power (EV) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| MD | Pepco (DG) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| MD | Pepco (EV) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| MD | Potomac Edison | ArcGIS | FirstEnergy | PJM | Public | Wave 5 |
| MD | SMECO | Custom | - | PJM | Public | Wave 7 |
| MA | Eversource | ArcGIS | - | ISO-NE | Public | Wave 4 |
| MA | National Grid | ArcGIS MS | - | ISO-NE | Public | Wave 4 |
| MA | Unitil | Custom | - | ISO-NE | Public | Wave 7 |
| MI | Consumers Energy | ArcGIS | - | MISO | Public | Wave 5 |
| MI | DTE | ArcGIS | - | MISO | Public | Wave 5 |
| MN | Xcel Energy (DG) | ArcGIS FS | - | MISO | Public | Wave 5 |
| MN | Xcel Energy (EV) | ArcGIS FS | - | MISO | Public | Wave 5 |
| NV | NV Energy | Custom | - | - | Auth required | Wave 7 |
| NH | Eversource | ArcGIS | - | ISO-NE | Public | Wave 4 |
| NH | Liberty Utilities | Custom | - | ISO-NE | Public | Wave 7 |
| NH | NH Electric Co-op | Custom | - | ISO-NE | Public | Wave 7 |
| NJ | ACE (DG) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| NJ | ACE (EV) | ArcGIS FS | Exelon | PJM | Public | Wave 3 |
| NJ | JCP&L (DG) | ArcGIS | FirstEnergy | PJM | Public | Wave 5 |
| NJ | JCP&L (EV) | ArcGIS | FirstEnergy | PJM | Public | Wave 5 |
| NJ | O&R | ArcGIS | Con Edison | NYISO | Public | Wave 4 |
| NJ | PSE&G (DG) | Iframe | - | PJM | Public | Wave 7 |
| NJ | PSE&G (EV) | Iframe | - | PJM | Public | Wave 7 |
| NY | Central Hudson | ArcGIS | - | NYISO | Public | Wave 4 |
| NY | Con Edison | ArcGIS | - | NYISO | Public | Wave 4 |
| NY | National Grid | ArcGIS | - | NYISO | Public | Wave 4 |
| NY | NYSEG/RG&E | ArcGIS | Avangrid | NYISO | Public | Wave 5 |
| NY | O&R | ArcGIS | Con Edison | NYISO | Public | Wave 4 |
| NY | PSEG Long Island | ArcGIS | - | NYISO | Auth required | Wave 7 |
| NC | Dominion (DG) | ArcGIS FS | - | PJM | Public | Wave 4 |
| NC | Dominion (EV) | ArcGIS FS | - | PJM | Public | Wave 4 |
| NC | Duke Energy | ArcGIS MS | - | - | Public | Wave 5 |
| OR | Idaho Power | Custom | - | - | Public | Wave 7 |
| OR | Pacific Power | Custom | - | - | Public | Wave 7 |
| OR | Portland General | Mapbox | - | - | Public | Wave 7 |
| PR | LUMA | Custom | - | - | Public | Wave 7 |
| RI | Rhode Island Energy | Custom | - | ISO-NE | Public | Wave 7 |
| SC | Duke Energy | ArcGIS MS | - | - | Public | Wave 5 |
| UT | Garkane Energy | Asset Map | - | - | Public | Low |
| VT | Burlington Electric | Custom | - | ISO-NE | Public | Wave 7 |
| VT | Green Mountain Power | Custom | - | ISO-NE | Public | Wave 7 |
| VA | Dominion (DG) | ArcGIS FS | - | PJM | Public | Wave 4 |
| VA | Dominion (EV) | ArcGIS FS | - | PJM | Public | Wave 4 |
| WA | Avista | Custom | - | - | Public | Wave 7 |
| WA | Puget Sound Energy | Custom | - | - | Public | Wave 7 |

---

## Verification

1. **Unit tests**: ArcGIS client pagination, normalizer field mapping + unit conversion, adapter cache hit/miss
2. **Integration smoke test**: Fetch 1 page from PG&E FeatureServer layer 7, normalize, write to DB, query via API
3. **Full PG&E ingestion**: End-to-end pipeline, verify record count matches ArcGIS feature count
4. **Cross-utility validation**: Ingest PG&E + Pepco + Dominion, verify all normalize to same canonical schema
5. **Frontend**: Toggle HC layer, verify markers render at feeder centroids with correct colors
6. **Freshness**: Run `--list-utilities` and verify `last_ingested_at` timestamps

### Test commands
```bash
# Run migration
alembic upgrade head

# Discover PG&E layers
python -m cli.ingest_hosting_capacity --utility pge --discover

# Dry run (fetch + normalize, no DB write)
python -m cli.ingest_hosting_capacity --utility pge --dry-run

# Full ingestion
python -m cli.ingest_hosting_capacity --utility pge

# Verify via API
curl http://localhost:8000/api/v1/utilities
curl http://localhost:8000/api/v1/utilities/pge/hosting-capacity/summary

# Start frontend dev server and toggle "Hosting Capacity" layer
```

---

## Key Files Reference

| Purpose | File | Notes |
|---------|------|-------|
| Adapter pattern to follow | `adapters/base.py` | ISOAdapter ABC, ISOConfig dataclass |
| ArcGIS pagination to extract | `scraping/grip_fetcher.py` | Lines 82-112, also `_web_mercator_to_wgs84` |
| Normalization pattern | `adapters/gridstatus_adapter.py` | `_normalize_zone_lmps()` candidate-list column mapping |
| DB writer pattern | `app/pipeline_writer.py` | Batch insert, rollback, run tracking |
| ISO config format | `adapters/configs/caiso.yaml` | YAML structure to follow |
| Map layer pattern | `frontend/src/components/map/SubstationMarkers.vue` | Circle markers, color coding, popup |
| Store pattern | `frontend/src/stores/hierarchyStore.ts` | Load-on-ISO-select, selected entity |
| API route pattern | `app/api/v1/hierarchy_routes.py` | FastAPI router, Pydantic response schemas |
| Model pattern | `app/models/substation.py` | SQLAlchemy 2.0 mapped_column style |
