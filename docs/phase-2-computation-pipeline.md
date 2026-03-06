# Phase 2: Computation Pipeline

## Goal

Build the unified computation pipeline that reads from existing raw tables and produces constraint profiles, DER intersections, location value stacks, and constraint annotations. This is where the existing scattered logic in `constraint_classifier.py`, `pnode_analyzer.py`, `valuation_engine.py`, `congestion_calculator.py`, and `hierarchy_scorer.py` gets refactored into a single coherent pipeline that writes to the new tables.

## Prerequisites

- Phase 1 complete (all 6 new tables exist, BA data merged into ISOs, DER profiles seeded)
- Raw data tables populated (zone_lmps, ba_hourly_data, substation_load_profiles, hosting_capacity_records)

---

## Architecture: `core/profile_engine.py` (NEW)

A single orchestrator module that replaces the scattered computation logic. Four sub-pipelines, each producing `constraint_profiles` rows, followed by intersection and stacking computations.

### Pipeline Overview

```
Raw Data → Profile Builders → constraint_profiles
                                    ↓
                          DER Profiles (from DB)
                                    ↓
                          Intersection Computer → constraint_der_intersections
                                    ↓
                          Value Stacker → location_value_stacks
                                    ↓
                          Annotation Linker → constraint_annotations
                                    ↓
                          Matview Refresh → mv_zone_constraint_summary,
                                           mv_location_rankings
```

---

## Step 2.1: Profile Builders

Each builder reads from a raw table and produces `constraint_profiles` rows. All builders share a common interface.

### 2.1.1: Zone Congestion Profile Builder

**Source**: `zone_lmps` (current table, no rename needed yet)
**Replaces**: `constraint_classifier.py` zone classification logic

```python
def build_zone_congestion_profiles(session, iso_id: int, year: int,
                                    run: ComputationRun) -> list[ConstraintProfile]:
    """
    For each zone in the ISO:
    1. Query zone_lmps for the year
    2. Aggregate: AVG(ABS(congestion)) by month, hour_local -> 12x24
    3. Compute summary stats (peak, mean, constrained hours)
    4. Compute severity score (reuse existing weighted scoring from
       constraint_classifier.py, but output a single severity_score
       instead of separate transmission/generation scores)
    5. Compute avg_marginal_cost = AVG(ABS(congestion)) for congested hours
    6. Compute annual_cost = avg_marginal_cost * constrained_hours
    """
```

**SQL for 12x24 aggregation** (executed per zone):
```sql
SELECT month, hour_local,
       AVG(ABS(congestion)) as avg_intensity,
       MAX(ABS(congestion)) as max_intensity,
       COUNT(*) FILTER (WHERE ABS(congestion) > 2.0) as congested_count,
       COUNT(*) as total_count
FROM zone_lmps
WHERE zone_id = :zone_id
  AND timestamp_utc >= :year_start
  AND timestamp_utc < :year_end
GROUP BY month, hour_local
ORDER BY month, hour_local
```

**Severity scoring** (adapted from existing `constraint_classifier.py`):
- Compute all 4 transmission metrics (congestion_ratio, congestion_volatility, congested_hours_pct, peak_offpeak_ratio) using the same weights and thresholds
- severity_score = the existing transmission_score (0-1)
- We drop the generation_score distinction. Congestion is congestion regardless of whether it's transmission or generation driven. The 12x24 profile captures the temporal pattern, which is what matters.
- Normalize severity_score across all zones in the ISO (min-max) so scores are relative

**Constants preserved from existing code**:
- CONGESTION_THRESHOLD_DOLLARS = 2.0
- Peak hours: 7-22 (for peak/off-peak ratio)
- Weights: 30/25/25/20 for the four metrics

### 2.1.2: Pnode Congestion Profile Builder

**Source**: pnode LMP data (currently fetched during pipeline but not persisted)
**Replaces**: `pnode_analyzer.py` scoring and loadshape logic

```python
def build_pnode_congestion_profiles(session, iso_id: int, year: int,
                                     run: ComputationRun) -> list[ConstraintProfile]:
    """
    For each pnode with LMP data:
    1. Build 12x24 from hourly node congestion: AVG(ABS(congestion)) by month/hour
    2. Compute 5-metric severity score (existing pnode_analyzer weights)
    3. Normalize within-zone (relative to other pnodes in same zone)
    4. Write constraint_profile with location_level='pnode'
    """
```

**Key difference from zone profiles**: Pnode profiles are normalized within their zone, not across the entire ISO. A critical pnode in a lightly-constrained zone still shows up as critical relative to its peers.

**Data gap**: Pnode LMPs are currently not persisted. Two options:
- **Option A**: Build a `pnode_lmp_raw` table and persist during ingestion (preferred, enables recomputation)
- **Option B**: Compute profiles on-the-fly during pipeline run (current approach, loses raw data)

Recommendation: **Option A**. Add `pnode_lmp_raw` table in Phase 1 migration. Modify the pipeline's pnode drilldown step to write raw LMPs before computing profiles.

**Severity scoring** (preserved from existing `pnode_analyzer.py`):
- 5 metrics: magnitude (30%), volatility (20%), congested_hours (25%), peak/offpeak (15%), extreme_events (10%)
- Tier cutoffs: critical >=0.75, elevated >=0.50, moderate >=0.25, low <0.25

### 2.1.3: Substation Loading Profile Builder

**Source**: `substation_load_profiles` (current table)
**Replaces**: substation loading portion of `hierarchy_scorer.py` and `valuation_engine.py`

```python
def build_substation_loading_profiles(session, iso_id: int,
                                       run: ComputationRun) -> list[ConstraintProfile]:
    """
    For each substation with load profile data:
    1. Read SubstationLoadProfile rows (month, hour, load_low_kw, load_high_kw)
    2. Compute loading_pct = load_high_kw / (facility_rating_mw * 1000) per (month, hour)
    3. Build 12x24 from loading_pct values
    4. Severity = based on peak_loading_pct thresholds
       (>=100% critical, >=90% elevated, >=80% moderate, <80% low)
    5. avg_marginal_cost = avoided_capacity_cost * loading_factor
       where loading_factor = min(1.0, (peak_loading_pct - 80) / 40)
       and avoided_capacity_cost = $80/kW-yr
    """
```

**Note**: Currently only PG&E GRIP data has load profiles. When more utilities provide time-series loading data, the same builder handles them.

### 2.1.4: Feeder Capacity Profile Builder

**Source**: `hosting_capacity_records` (current table)
**Replaces**: feeder portion of `valuation_engine.py`

```python
def build_feeder_capacity_profiles(session, iso_id: int,
                                    run: ComputationRun) -> list[ConstraintProfile]:
    """
    For each feeder with hosting capacity data:
    1. Compute utilization = installed_dg_mw / hosting_capacity_mw
    2. If parent substation has a load profile, scale by substation's 12x24 pattern
       (constraint is worst when substation load is highest AND feeder is near capacity)
    3. If no parent substation profile: use a flat profile scaled by utilization
    4. Severity based on remaining_capacity_mw / hosting_capacity_mw
       (<=5% remaining = critical, <=15% elevated, <=30% moderate, >30% low)
    5. avg_marginal_cost = $50/kW-yr * utilization_factor
    """
```

**Hosting capacity is typically a snapshot, not time-series.** The 12x24 profile is synthetic: we use the parent substation's temporal pattern (if available) scaled by the feeder's utilization ratio. This gives a reasonable approximation of when the capacity constraint is binding.

### 2.1.5: BA Import Stress Profile Builder

**Source**: `ba_hourly_data` (current table, FK now points to isos)
**Replaces**: `congestion_calculator.py`

```python
def build_ba_import_stress_profiles(session, iso_id: int, year: int,
                                     run: ComputationRun) -> list[ConstraintProfile]:
    """
    For each BA (iso record where ba_code is not NULL):
    1. Query ba_hourly_data for the year
    2. Compute import_utilization = net_imports_mw / transfer_limit_mw per hour
    3. Aggregate: AVG(import_utilization) by month, hour -> 12x24
    4. Severity based on hours_above_80/90/95 thresholds (from congestion_calculator)
    5. avg_marginal_cost = avg_congestion_premium from interface LMPs (if available)
    """
```

**SQL for 12x24**:
```sql
SELECT
    EXTRACT(MONTH FROM timestamp_utc) as month,
    EXTRACT(HOUR FROM timestamp_utc) as hour,
    AVG(CASE WHEN net_imports_mw > 0
         THEN net_imports_mw / NULLIF(:transfer_limit_mw, 0)
         ELSE 0 END) as avg_utilization,
    COUNT(*) FILTER (WHERE net_imports_mw / NULLIF(:transfer_limit_mw, 0) > 0.80) as hours_above_80
FROM ba_hourly_data
WHERE ba_id = :iso_id
  AND timestamp_utc >= :year_start AND timestamp_utc < :year_end
GROUP BY 1, 2
ORDER BY 1, 2
```

---

## Step 2.2: Intersection Computer

After all constraint profiles are built, compute intersections with each canonical DER profile.

```python
def compute_intersections(session, run: ComputationRun) -> int:
    """
    For each constraint_profile created in this run:
      For each canonical der_profile (8 types):
        1. If DER is dispatchable: coincidence_factor = 1.0, overlap_hours = constrained_hours
        2. Else: flatten both 12x24s to 288 vectors, compute cosine similarity
        3. overlap_hours = count of (month, hour) slots where both > threshold
        4. overlap_12x24 = element-wise product
        5. value_per_kw_year = constraint.avg_marginal_cost * coincidence_factor
           * (constrained_hours / 8760)
        6. value_tier from thresholds: premium >=150, high >=80, moderate >=30, low <30
        7. Insert constraint_der_intersections row
    Returns count of intersections created.
    """
```

**Performance**: 288-element cosine similarity is trivially fast. Even 100K profiles x 8 DER types = 800K intersections takes seconds with NumPy vectorization.

**Reuse from existing code**: The cosine similarity computation in `core/der_profiles.py` `compute_coincidence_factor()` is exactly what we need. Extract the vector math into a utility function.

---

## Step 2.3: Value Stacker

For each unique (location_level, location_id), stack all applicable constraint layers.

```python
def compute_value_stacks(session, run: ComputationRun) -> int:
    """
    For each location that has constraint_profiles:
      For each canonical der_profile:
        1. Find all constraint_profiles at this location (may be multiple types)
        2. For each constraint type, look up the intersection value
        3. Stack: total = congestion_value + loading_value + capacity_value + import_stress_value
        4. composite_coincidence = weighted average of per-layer coincidence factors
        5. value_tier from total
        6. Upsert location_value_stacks row
    """
```

**Stacking also inherits parent values**: A feeder inherits its zone's congestion value (if the feeder doesn't have its own congestion profile). A substation inherits its zone's congestion value plus adds its own loading value.

**Inheritance rules**:
- Zone: congestion (from zone profile), import_stress (from parent BA if zone has one)
- Pnode: congestion (from pnode profile, replaces zone congestion for precision)
- Substation: congestion (inherited from zone), loading (from substation profile)
- Feeder: congestion (inherited from zone), loading (inherited from substation), capacity (from feeder profile)
- Circuit: same as feeder plus circuit-level data if available (private partnership feature)

---

## Step 2.4: Annotation Linker

Link existing regulatory data to constraint profiles.

```python
def link_annotations(session, run: ComputationRun) -> int:
    """
    Scan existing tables for linkable data:

    1. grid_constraints table:
       - Match by utility_id -> utility -> iso_id -> zones in that ISO
       - If grid_constraint.location_name matches a substation name, link to
         the substation-level constraint_profile
       - Create annotation with type based on constraint_type

    2. load_forecasts table:
       - Match by utility_id -> zones
       - If growth_rate_pct > 2%, create 'grid_plan' annotation noting high growth

    3. resource_needs table:
       - Match by utility_id -> zones
       - Create 'resource_need' annotation with need_mw and eligible_resource_types

    4. filings table (where filing_type IN ('irp', 'drp', 'grid_mod')):
       - Match by utility_id -> zones
       - Create 'irp_citation' annotation with filing title and source_url
    """
```

**Matching logic**: The primary link is through the utility's service territory. A utility serves certain zones. When a filing from that utility mentions a constraint, it annotates all constraint profiles in that utility's zones. If the filing has a specific location_name (e.g., a substation), we match to the substation-level profile.

---

## Step 2.5: Materialized View Refresh

```python
def refresh_materialized_views(session):
    session.execute(text("REFRESH MATERIALIZED VIEW mv_zone_constraint_summary"))
    session.execute(text("REFRESH MATERIALIZED VIEW mv_location_rankings"))
    session.commit()
```

---

## Step 2.6: CLI Orchestrator

### `cli/compute_profiles.py` (NEW)

Replaces the profile-computation portions of `cli/run_pipeline.py`.

```
Usage:
  python -m cli.compute_profiles --iso caiso --year 2024
  python -m cli.compute_profiles --iso all --year 2024
  python -m cli.compute_profiles --iso caiso --year 2024 --only congestion
  python -m cli.compute_profiles --iso caiso --year 2024 --only loading
  python -m cli.compute_profiles --recompute-intersections
  python -m cli.compute_profiles --recompute-stacks
  python -m cli.compute_profiles --link-annotations
  python -m cli.compute_profiles --full  # all steps
```

**Full pipeline sequence**:
1. Create ComputationRun record (status=running)
2. Build zone congestion profiles (Step 2.1.1)
3. Build pnode congestion profiles (Step 2.1.2) [if pnode LMP data available]
4. Build substation loading profiles (Step 2.1.3) [if substation data available for this ISO]
5. Build feeder capacity profiles (Step 2.1.4) [if hosting capacity data available]
6. Build BA import stress profiles (Step 2.1.5) [if BA data available]
7. Compute intersections (Step 2.2)
8. Compute value stacks (Step 2.3)
9. Link annotations (Step 2.4)
10. Refresh materialized views (Step 2.5)
11. Update ComputationRun (status=success, metrics)

---

## Key Constants (Preserved from Existing Code)

All thresholds and weights are preserved from the existing codebase to ensure consistency. They move into `core/profile_engine.py` as module-level constants:

```python
# Congestion thresholds
CONGESTION_THRESHOLD_DOLLARS = 2.0
ENERGY_DEVIATION_THRESHOLD = 3.0
PEAK_HOURS = range(7, 23)

# Zone severity weights (from constraint_classifier.py)
ZONE_WEIGHTS = {
    "congestion_ratio": 0.30,
    "congestion_volatility": 0.25,
    "congested_hours_pct": 0.25,
    "peak_offpeak_ratio": 0.20,
}

# Pnode severity weights (from pnode_analyzer.py)
PNODE_WEIGHTS = {
    "magnitude": 0.30,
    "volatility": 0.20,
    "congested_hours": 0.25,
    "peak_offpeak": 0.15,
    "extreme_events": 0.10,
}

# Severity tier cutoffs
TIER_CRITICAL = 0.75
TIER_ELEVATED = 0.50
TIER_MODERATE = 0.25

# Valuation constants (from valuation_engine.py)
AVOIDED_CAPACITY_COST_PER_KW_YEAR = 80.0  # substation
AVOIDED_FEEDER_COST_PER_KW_YEAR = 50.0    # feeder
SUBSTATION_LOADING_THRESHOLD = 0.80
LOADING_FACTOR_RANGE = 0.40  # scales linearly from 80% to 120%

# Value tier thresholds
VALUE_PREMIUM = 150.0   # $/kW-yr
VALUE_HIGH = 80.0
VALUE_MODERATE = 30.0
```

---

## What Existing Code Gets Replaced

| Existing File | What's Extracted | What Remains |
|---|---|---|
| `core/constraint_classifier.py` | Zone metric computation, weighted scoring -> zone congestion profile builder | Deleted after Phase 3 |
| `core/pnode_analyzer.py` | Pnode metrics, severity scoring, loadshape computation -> pnode congestion profile builder | Deleted after Phase 3 |
| `core/valuation_engine.py` | Per-level value computation -> value stacker. Coincidence factor -> intersection computer | Deleted after Phase 3 |
| `core/congestion_calculator.py` | Import utilization metrics -> BA import stress profile builder | Deleted after Phase 3 |
| `core/hierarchy_scorer.py` | Combined TX/DX scoring -> subsumed by value stacker (stacks across layers naturally) | Deleted after Phase 3 |
| `core/der_profiles.py` | Canonical profile data -> seeded in DB. Cosine similarity -> utility function | Data portion deleted, math utility kept |
| `core/retrospective_valuator.py` | WattCarbon-specific logic | Kept as-is (plugin, not core) |

---

## Verification

After Phase 2:
- [ ] `constraint_profiles` populated for all zones with LMP data (7 ISOs)
- [ ] `constraint_profiles` populated for pnodes (where pnode LMP data exists)
- [ ] `constraint_profiles` populated for substations (PG&E GRIP data)
- [ ] `constraint_profiles` populated for feeders (utilities with hosting capacity)
- [ ] `constraint_profiles` populated for BAs (65 records with EIA-930 data)
- [ ] `constraint_der_intersections` populated (profiles x 8 DER types)
- [ ] `location_value_stacks` populated with correct inheritance
- [ ] `constraint_annotations` linked where regulatory data exists
- [ ] Materialized views refreshed with data
- [ ] Spot-check: zone severity scores match existing `zone_classifications` within tolerance
- [ ] Spot-check: value stacks match existing `der_valuations` for same locations within tolerance
- [ ] Spot-check: 12x24 profiles match existing loadshape endpoint output visually

## Files Created/Modified

| File | Action |
|---|---|
| `core/profile_engine.py` | CREATE (main computation module) |
| `core/profile_utils.py` | CREATE (12x24 math: flatten, cosine similarity, normalize) |
| `cli/compute_profiles.py` | CREATE (CLI orchestrator) |
| `core/constraint_classifier.py` | NO CHANGE yet (kept for v1 API backward compat) |
| `core/pnode_analyzer.py` | NO CHANGE yet |
| `core/valuation_engine.py` | NO CHANGE yet |
| `core/congestion_calculator.py` | NO CHANGE yet |
| `core/hierarchy_scorer.py` | NO CHANGE yet |
