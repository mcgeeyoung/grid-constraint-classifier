# Grid Constraint Classifier: Refocused Architecture

## Context

The grid-constraint-classifier has grown to 33 database models, 30+ API endpoints, and 18 CLI tools spanning LMP analysis, hosting capacity ingestion, regulatory document parsing, PUC docket monitoring, GeoPackage/OSM data, interconnection queues, data center scraping, and federal data pipelines. While each piece is useful, the system doesn't hang together because it lacks a central organizing principle.

The core thesis: DER value is defined by **temporal coincidence** between grid constraints and DER performance. When a constraint occurs and where it occurs are what determine which DER types are most valuable. The entire system should be built to answer one question:

**"At this location, what constraints exist, when do they peak, and which DER types best match those constraint patterns?"**

## Key Design Decisions

1. **Regulatory data as annotations on constraints** - filings, IRP citations, and grid plans surface directly on constraint profiles (e.g., "PG&E IRP identifies this substation for $12M upgrade in 2028"), not as a separate drill-down
2. **BAs unified with ISOs** - balancing authorities fold into the ISO table as a location level, simplifying the hierarchy
3. **All constraint types from day one** - build the profile framework for congestion, loading, capacity, and import stress simultaneously
4. **Standalone tool** - WattCarbon integration (asset sync, retrospective valuation) is a plugin, not a dependency. Any DER developer can use this tool independently

## The Central Abstraction: Constraint Profiles

Every grid constraint, regardless of source, can be normalized into a **12x24 profile** (month x hour matrix) representing constraint intensity. This is the intermediate representation that unifies all data:

| Source Data | Constraint Type | Profile Derivation |
|---|---|---|
| Zone LMP congestion component | `congestion` | `AVG(ABS(congestion))` by month/hour |
| Pnode LMP congestion | `congestion` | Same, at node granularity |
| Substation loading (GRIP) | `loading` | `AVG(loading_pct)` by month/hour |
| Hosting capacity limits | `capacity` | Feeder remaining capacity scaled by substation load pattern |
| BA import utilization (EIA-930) | `import_stress` | `AVG(import_pct_of_load)` by month/hour |

Every DER type also has a 12x24 output profile (solar peaks summer afternoons, wind peaks winter nights, efficiency is flat, storage is dispatchable).

**The product = constraint profile x DER profile = coincidence factor + $/kW-yr value.**

## Three-Layer Data Architecture

### Layer 1: Raw Ingestion (store upstream data as-is)

These tables store time-series and reference data from external sources. They are the "data lake" feeding computations.

**Location Hierarchy (keep existing tables, simplify):**
- `isos` - 7 ISOs + 65 BAs unified (add `is_rto`, `ba_code`, `parent_iso_id`, `transfer_limit_mw` fields). BAs that are within an RTO get `parent_iso_id` pointing to the RTO. Independent BAs stand alone. This means constraint profiles for BAs use the same framework as everything else.
- `zones` - pricing zones within ISOs (no change)
- `pnodes` - pricing nodes within zones (no change)
- `substations` - distribution substations (remove inline loading data, it moves to raw time-series)
- `feeders` - distribution feeders (remove inline loading data)

**Hourly Time Series (the backbone):**
- `zone_lmp_raw` - current `zone_lmps`, renamed for clarity. Partitioned by iso_id. No structural change.
- `pnode_lmp_raw` - **NEW**. Currently pnode LMPs are computed during pipeline runs but not persisted. Persisting them enables recomputation without re-fetching.
- `substation_loading_raw` - replaces `substation_load_profiles`. Generalized to accept multiple sources (GRIP, utility portals, etc.)
- `ba_hourly_raw` - current `ba_hourly_data`, renamed
- `interface_lmp_raw` - current `interface_lmps`, renamed
- `hosting_capacity_raw` - current `hosting_capacity_records`, simplified
- `interconnection_queue` - keep, simplify to core fields

**Remove from core:**
- `transmission_lines` - visual reference only, move to `reference` schema
- `data_centers` - enrichment data, move to `enrichment` schema
- `gpkg_*` (3 tables) - OSM reference data, move to `reference` schema
- `balancing_authorities` - merge into `isos` table

### Layer 2: Computed Profiles (the product)

This is the heart of the redesign. Six new tables replace eight current tables.

**`constraint_profiles`** - the central table
```
id, location_level (zone/pnode/substation/feeder/circuit/ba),
location_id, constraint_type (congestion/loading/capacity/import_stress),
source_type, period_year,
profile_12x24 (JSON: 12 arrays of 24 floats),
peak_intensity, peak_month, peak_hour, mean_intensity,
total_constrained_hours, constrained_hours_pct,
severity_score (0-1), severity_tier,
avg_marginal_cost ($/MWh or $/kW-yr), annual_cost,
computed_at, computation_run_id
```

Replaces: `zone_classifications`, `pnode_scores`, `hierarchy_scores`, `congestion_scores`

**`constraint_annotations`** - regulatory context linked directly to constraint profiles
```
id, constraint_profile_id (FK),
annotation_type (irp_citation/grid_plan/deferral_opportunity/rate_case/resource_need),
utility_id (FK, nullable), filing_id (FK, nullable),
title, summary (text),
planned_solution (text, e.g. "Substation rebuild, $12M, 2028"),
deferral_value_estimate (float, $/year, nullable),
source_url, source_document,
confidence (float, 0-1),
created_at
```

This is the key integration point for regulatory data. When a user views a constrained zone or substation, annotations surface alongside the time-series profile: "This constraint has been identified in PG&E's 2024 IRP. The utility plans a $12M substation rebuild by 2028. A 5 MW solar+storage project could defer this investment." The annotations don't drive the profile computation, they enrich it with context about why the constraint exists and what the grid operator plans to do about it.

**`der_profiles`** - DER output patterns
```
id, der_type, eac_category (variable/consistent/dispatchable),
profile_source (canonical/nrel/wattcarbon_metered/custom),
location_id (nullable, for location-specific profiles),
profile_12x24 (JSON),
is_dispatchable, max_dispatch_hours, dispatch_power_mw,
capacity_factor, notes
```

Replaces: hardcoded profiles in `core/der_profiles.py`

**`constraint_der_intersections`** - pre-computed value
```
id, constraint_profile_id (FK), der_profile_id (FK),
coincidence_factor (0-1), overlap_hours,
overlap_12x24 (JSON: element-wise product),
value_per_kw_year, value_tier,
value_breakdown (JSON), computed_at
```

Replaces: `der_recommendations`

**`location_value_stack`** - composite value across all constraint layers
```
id, location_level, location_id, der_profile_id (FK),
congestion_value_per_kw_year, loading_value_per_kw_year,
capacity_value_per_kw_year, import_stress_value_per_kw_year,
total_value_per_kw_year, composite_coincidence_factor,
value_tier, constraint_layers (JSON),
period_year, computed_at
```

Replaces: `der_valuations`, `hierarchy_scores`

**`computation_runs`** - general-purpose run tracking
```
id, run_type, iso_id (nullable), period_year,
started_at, completed_at, status,
parameters_json, metrics_json, error_message
```

Replaces: `pipeline_runs`, `hc_ingestion_runs`

### Layer 3: Presentation (materialized views for fast API reads)

- `mv_zone_constraint_summary` - per-zone: primary constraint type, severity, best DER type, top 3 recommendations
- `mv_location_rankings` - all locations ranked by value for a given DER type (powers the map)
- Keep existing matviews: `zone_lmp_hourly_avg`, `zone_lmp_daily_avg`

## API Restructuring

Reorganize around three question types. Since the existing API is not deployed and has no external users, we replace it directly.

### A. "What constraints exist here?" (Location-first)
- `GET /resolve?lat=&lon=` - resolve to grid hierarchy + constraint summary
- `GET /zones/{iso_code}` - zones with constraint summaries
- `GET /zones/{iso_code}/{zone_code}/constraints` - all constraint profiles for a zone, with annotations (IRP citations, grid plans, deferral opportunities) surfaced inline
- `GET /locations/{level}/{id}/profile` - composite constraint profile (the 12x24) + annotations

### B. "What DER is most valuable here?" (Value-first)
- `POST /valuations/prospective` - value stack for a DER at a lat/lon
- `GET /valuations/compare?lat=&lon=` - compare all DER types at a location
- `GET /valuations/rankings?iso_code=&der_type=` - top locations for a DER type

### C. "Show me the temporal overlap" (Profile-first)
- `GET /profiles/constraint/{id}` - full 12x24 constraint profile
- `GET /profiles/der/{der_type}` - canonical DER output profile
- `GET /profiles/intersection?constraint_id=&der_type=` - overlap analysis with chart data

### D. Enrichment (supporting context)
- `GET /enrichment/hosting-capacity?lat=&lon=` - can you interconnect here?
- `GET /enrichment/interconnection-queue?lat=&lon=` - what's already planned nearby?
- `GET /enrichment/filings/{utility_id}` - full filing history for a utility (deep-dive beyond annotations)

### E. Keep for maps
- `GET /tiles/{layer}/{z}/{x}/{y}.pbf` - vector tiles (zones, pnodes, substations)

## What Stays, What Goes

### Keep (core to the product)
| Current | Action |
|---|---|
| `isos`, `zones`, `pnodes`, `substations`, `feeders` | Keep. Simplify substations/feeders (remove inline loading data) |
| `zone_lmps` | Keep as `zone_lmp_raw`. No structural change |
| `substation_load_profiles` | Keep as `substation_loading_raw`. Generalize |
| `ba_hourly_data`, `interface_lmps` | Keep, rename with `_raw` suffix |
| `hosting_capacity_records` | Keep as `hosting_capacity_raw`. Simplify |
| `interconnection_queue` | Keep, simplify to core fields |
| `utilities` | Keep as registry (simplify) |

### Replace with new profile tables
| Current | Replaced By |
|---|---|
| `zone_classifications` | `constraint_profiles` (type=congestion) |
| `pnode_scores` | `constraint_profiles` (type=congestion, level=pnode) |
| `hierarchy_scores` | `location_value_stack` |
| `der_valuations` | `location_value_stack` |
| `der_recommendations` | `constraint_der_intersections` |
| `congestion_scores` | `constraint_profiles` (type=import_stress) |
| `pipeline_runs` | `computation_runs` |
| `hc_ingestion_runs` | `computation_runs` |
| `hosting_capacity_summaries` | Materialized view |

### Keep as supporting tables (feed constraint_annotations)
| Current | Role |
|---|---|
| `utilities` | Registry. Links hosting capacity, filings, and annotations to utilities |
| `regulators` | Reference data for state PUCs |
| `filings`, `filing_documents` | Source material for constraint annotations |
| `grid_constraints`, `load_forecasts`, `resource_needs` | Extracted data that populates constraint_annotations |
| `extraction_reviews` | Review queue for LLM-extracted data before promotion to annotations |
| `docket_watches` | Monitoring for new filings that may create new annotations |

### Move to separate schema (visual/operational, not core product)
| Current | Destination |
|---|---|
| `transmission_lines`, `gpkg_*` (3 tables) | `reference` schema (map visualization only) |
| `data_centers` | `enrichment` schema |
| `data_coverage`, `monitor_events` | `operational` schema |

### Keep as private/internal (utility partnership feature)
| Current | Role |
|---|---|
| `circuits` | Circuit-level constraint data for utility partnerships. Not exposed in public API. Available when a utility provides detailed distribution data under partnership agreement. Constraint profiles at the circuit level use the same 12x24 framework. |

## Migration Phases

Detailed plans for each phase are in separate documents:

- [Phase 1: Schema + Models](./phase-1-schema-models.md)
- [Phase 2: Computation Pipeline](./phase-2-computation-pipeline.md)
- [Phase 3: Replace API](./phase-3-replace-api.md)
- [Phase 4: Frontend](./phase-4-frontend.md)

## Verification
- Compare `constraint_profiles` severity scores against existing `zone_classifications` for the same zones/year
- Compare `location_value_stack` totals against existing `der_valuations` for the same DER locations
- Verify 12x24 profiles visually match existing loadshape endpoint output
- Confirm annotations surface correctly on constrained zones that have associated filings
