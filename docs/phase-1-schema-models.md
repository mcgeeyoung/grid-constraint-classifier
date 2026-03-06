# Phase 1: Schema + Models

## Goal

Create the 6 new tables that form the product layer, unify BAs into ISOs, and seed DER profiles. No computation logic changes yet. The existing system continues to work throughout this phase.

## Prerequisites

- PostgreSQL running with `gridclass` database
- Alembic migration chain at head (`s1m3g6c92j0k`)
- All existing data preserved

---

## Step 1.1: Create New Model Files

### `app/models/constraint_profile.py` (NEW)

```python
class ConstraintProfile(Base):
    __tablename__ = "constraint_profiles"
    __table_args__ = (
        UniqueConstraint("location_level", "location_id", "constraint_type",
                         "source_type", "period_year",
                         name="uq_constraint_profile"),
        Index("ix_cp_location", "location_level", "location_id"),
        Index("ix_cp_type_year", "constraint_type", "period_year"),
        Index("ix_cp_severity", "severity_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_level: Mapped[str] = mapped_column(String(20), nullable=False)
        # zone, pnode, substation, feeder, circuit, ba
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(20), nullable=False)
        # congestion, loading, capacity, import_stress
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
        # lmp_zone, lmp_pnode, grip, hosting_capacity, eia930
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # The 12x24 profile (288 values)
    profile_12x24: Mapped[dict] = mapped_column(JSON, nullable=False)
        # {"1": [24 floats], "2": [24 floats], ..., "12": [24 floats]}

    # Summary statistics
    peak_intensity: Mapped[float] = mapped_column(Float, nullable=False)
    peak_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    peak_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mean_intensity: Mapped[float] = mapped_column(Float, nullable=False)
    total_constrained_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    constrained_hours_pct: Mapped[float] = mapped_column(Float, nullable=False)

    # Severity scoring
    severity_score: Mapped[float] = mapped_column(Float, nullable=False)
        # 0-1, normalized within (location_level, constraint_type)
    severity_tier: Mapped[str] = mapped_column(String(20), nullable=False)
        # critical (>=0.75), elevated (>=0.50), moderate (>=0.25), low

    # Economic valuation
    avg_marginal_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
        # $/MWh for congestion, $/kW-yr for loading/capacity
    annual_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Provenance
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    computation_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("computation_runs.id"), nullable=True)

    # Relationships
    annotations: Mapped[list["ConstraintAnnotation"]] = relationship(
        back_populates="constraint_profile")
    intersections: Mapped[list["ConstraintDERIntersection"]] = relationship(
        back_populates="constraint_profile")
```

### `app/models/constraint_annotation.py` (NEW)

```python
class ConstraintAnnotation(Base):
    __tablename__ = "constraint_annotations"
    __table_args__ = (
        Index("ix_ca_profile", "constraint_profile_id"),
        Index("ix_ca_type", "annotation_type"),
        Index("ix_ca_utility", "utility_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    constraint_profile_id: Mapped[int] = mapped_column(
        ForeignKey("constraint_profiles.id"), nullable=False)
    annotation_type: Mapped[str] = mapped_column(String(30), nullable=False)
        # irp_citation, grid_plan, deferral_opportunity, rate_case, resource_need
    utility_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("utilities.id"), nullable=True)
    filing_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("filings.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    planned_solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deferral_value_estimate: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True)  # $/year
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    constraint_profile: Mapped["ConstraintProfile"] = relationship(
        back_populates="annotations")
    utility: Mapped[Optional["Utility"]] = relationship()
    filing: Mapped[Optional["Filing"]] = relationship()
```

### `app/models/der_profile.py` (NEW)

```python
class DERProfile(Base):
    __tablename__ = "der_profiles"
    __table_args__ = (
        UniqueConstraint("der_type", "profile_source", "location_id",
                         name="uq_der_profile"),
        Index("ix_dp_type", "der_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    der_type: Mapped[str] = mapped_column(String(50), nullable=False)
        # solar, wind, storage, demand_response, energy_efficiency,
        # weatherization, combined_heat_power, fuel_cell
    eac_category: Mapped[str] = mapped_column(String(20), nullable=False)
        # variable, consistent, dispatchable
    profile_source: Mapped[str] = mapped_column(String(50), nullable=False)
        # canonical, nrel_sam, wattcarbon_metered, custom
    location_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        # NULL for canonical profiles; set for location-specific (e.g., actual solar)

    # The 12x24 profile (normalized 0-1), NULL for dispatchable types
    profile_12x24: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Dispatchable DER parameters
    is_dispatchable: Mapped[bool] = mapped_column(Boolean, default=False)
    max_dispatch_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dispatch_power_mw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ramp_rate_mw_per_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Performance
    capacity_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    intersections: Mapped[list["ConstraintDERIntersection"]] = relationship(
        back_populates="der_profile")
```

### `app/models/constraint_der_intersection.py` (NEW)

```python
class ConstraintDERIntersection(Base):
    __tablename__ = "constraint_der_intersections"
    __table_args__ = (
        UniqueConstraint("constraint_profile_id", "der_profile_id",
                         name="uq_cdi"),
        Index("ix_cdi_constraint", "constraint_profile_id"),
        Index("ix_cdi_der", "der_profile_id"),
        Index("ix_cdi_value", "value_per_kw_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    constraint_profile_id: Mapped[int] = mapped_column(
        ForeignKey("constraint_profiles.id"), nullable=False)
    der_profile_id: Mapped[int] = mapped_column(
        ForeignKey("der_profiles.id"), nullable=False)

    # Intersection results
    coincidence_factor: Mapped[float] = mapped_column(Float, nullable=False)
        # 0-1 cosine similarity
    overlap_hours: Mapped[int] = mapped_column(Integer, nullable=False)
        # Hours where both profiles > threshold
    overlap_12x24: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
        # Element-wise product of the two 12x24s

    # Dollar value
    value_per_kw_year: Mapped[float] = mapped_column(Float, nullable=False)
    value_tier: Mapped[str] = mapped_column(String(20), nullable=False)
        # premium (>=150), high (>=80), moderate (>=30), low (<30)
    value_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    constraint_profile: Mapped["ConstraintProfile"] = relationship(
        back_populates="intersections")
    der_profile: Mapped["DERProfile"] = relationship(
        back_populates="intersections")
```

### `app/models/location_value_stack.py` (NEW)

```python
class LocationValueStack(Base):
    __tablename__ = "location_value_stacks"
    __table_args__ = (
        UniqueConstraint("location_level", "location_id", "der_profile_id",
                         "period_year", name="uq_lvs"),
        Index("ix_lvs_location", "location_level", "location_id"),
        Index("ix_lvs_value", "total_value_per_kw_year"),
        Index("ix_lvs_tier", "value_tier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_level: Mapped[str] = mapped_column(String(20), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    der_profile_id: Mapped[int] = mapped_column(
        ForeignKey("der_profiles.id"), nullable=False)

    # Per-layer values
    congestion_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)
    loading_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)
    capacity_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)
    import_stress_value_per_kw_year: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=0.0)

    # Composite
    total_value_per_kw_year: Mapped[float] = mapped_column(Float, nullable=False)
    composite_coincidence_factor: Mapped[float] = mapped_column(Float, nullable=False)
    value_tier: Mapped[str] = mapped_column(String(20), nullable=False)

    # Which constraint layers contributed
    constraint_layers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
        # [{type, profile_id, contribution_pct}, ...]

    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    der_profile: Mapped["DERProfile"] = relationship()
```

### `app/models/computation_run.py` (NEW)

```python
class ComputationRun(Base):
    __tablename__ = "computation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
        # lmp_congestion, pnode_congestion, substation_loading,
        # hosting_capacity, ba_import_stress, intersection, value_stack,
        # annotation, full_recompute
    iso_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("isos.id"), nullable=True)
    period_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
        # running, success, failed
    parameters_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
        # {rows_processed, profiles_created, errors, duration_sec}
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    iso: Mapped[Optional["ISO"]] = relationship()
    constraint_profiles: Mapped[list["ConstraintProfile"]] = relationship(
        back_populates="computation_run")
```

---

## Step 1.2: Modify ISO Model to Absorb BAs

Add these columns to `app/models/iso.py`:

```python
# New columns for BA unification
ba_code: Mapped[Optional[str]] = mapped_column(String(10), unique=True, nullable=True)
    # NULL for pure ISOs (pjm, caiso), set for BAs (BANC, LADWP)
ba_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
is_rto: Mapped[bool] = mapped_column(Boolean, default=False)
parent_iso_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("isos.id"), nullable=True)
    # For BAs within an RTO: points to the parent ISO record
region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
interconnection: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
rto_neighbor: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
rto_neighbor_secondary: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
interface_points: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
transfer_limit_mw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
transfer_limit_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
ba_extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

# New relationships
parent_iso: Mapped[Optional["ISO"]] = relationship(remote_side=[id])
child_bas: Mapped[list["ISO"]] = relationship(back_populates="parent_iso")
ba_hourly_data: Mapped[list["BAHourlyData"]] = relationship(back_populates="iso")
congestion_scores: Mapped[list["CongestionScore"]] = relationship(back_populates="iso")
```

Mark existing ISOs: set `is_rto = True` for the 7 existing ISOs (they are all RTOs).

---

## Step 1.3: Rewire BA Foreign Keys

In `app/models/congestion.py`:

1. **Delete** the `BalancingAuthority` class entirely
2. **Update** `BAHourlyData.ba_id` FK from `balancing_authorities.id` to `isos.id`
3. **Update** `CongestionScore.ba_id` FK from `balancing_authorities.id` to `isos.id`
4. Rename the relationship from `ba` to `iso` in both models

---

## Step 1.4: Update `app/models/__init__.py`

```python
# Remove:
from .congestion import BalancingAuthority

# Add:
from .constraint_profile import ConstraintProfile
from .constraint_annotation import ConstraintAnnotation
from .der_profile import DERProfile
from .constraint_der_intersection import ConstraintDERIntersection
from .location_value_stack import LocationValueStack
from .computation_run import ComputationRun
```

---

## Step 1.5: Alembic Migration

Single migration file with these operations in order:

```
1. Add BA columns to isos table (13 new columns)
2. Create computation_runs table
3. Create constraint_profiles table
4. Create constraint_annotations table
5. Create der_profiles table
6. Create constraint_der_intersections table
7. Create location_value_stacks table
8. Migrate BA data: INSERT INTO isos (iso_code, iso_name, ba_code, ba_name, ...)
   SELECT ba_code, ba_name, ba_code, ba_name, ... FROM balancing_authorities
9. Update ba_hourly_data: SET ba_id = (SELECT i.id FROM isos i WHERE i.ba_code =
   (SELECT ba.ba_code FROM balancing_authorities ba WHERE ba.id = ba_hourly_data.ba_id))
10. Update congestion_scores: same FK rewiring
11. Drop balancing_authorities table
12. Set is_rto = True for existing 7 ISOs
```

**Downgrade**: reverse operations (recreate BA table, migrate data back, drop new tables, drop ISO columns).

---

## Step 1.6: Seed DER Profiles

After migration, run a seed script (or data migration) that reads from `core/der_profiles.py` and populates the `der_profiles` table:

| der_type | eac_category | profile_source | is_dispatchable | profile_12x24 | capacity_factor |
|---|---|---|---|---|---|
| solar | variable | canonical | false | {12x24 from DER_PROFILES["solar"]} | 0.4 |
| wind | variable | canonical | false | {12x24 from DER_PROFILES["wind"]} | 0.4 |
| storage | dispatchable | canonical | true | NULL | 1.0 |
| demand_response | dispatchable | canonical | true | NULL | 1.0 |
| energy_efficiency | consistent | canonical | false | {all 1.0} | 0.5 |
| weatherization | consistent | canonical | false | {all 1.0} | 0.5 |
| combined_heat_power | consistent | canonical | false | {all 1.0} | 0.5 |
| fuel_cell | dispatchable | canonical | true | NULL | 1.0 |

For dispatchable types, also set:
- storage: max_dispatch_hours=4.0, dispatch_power_mw=1.0
- demand_response: max_dispatch_hours=2.0, dispatch_power_mw=1.0
- fuel_cell: max_dispatch_hours=24.0, dispatch_power_mw=1.0

---

## Step 1.7: Create Materialized Views (DDL only, no data yet)

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_zone_constraint_summary AS
SELECT
    i.iso_code,
    z.zone_code,
    z.zone_name,
    cp.constraint_type AS primary_constraint_type,
    cp.severity_score,
    cp.severity_tier,
    cp.peak_month,
    cp.peak_hour,
    cp.constrained_hours_pct,
    cp.avg_marginal_cost,
    best.der_type AS best_der_type,
    best.value_per_kw_year AS best_der_value
FROM constraint_profiles cp
JOIN zones z ON cp.location_id = z.id AND cp.location_level = 'zone'
JOIN isos i ON z.iso_id = i.id
LEFT JOIN LATERAL (
    SELECT dp.der_type, cdi.value_per_kw_year
    FROM constraint_der_intersections cdi
    JOIN der_profiles dp ON cdi.der_profile_id = dp.id
    WHERE cdi.constraint_profile_id = cp.id
    ORDER BY cdi.value_per_kw_year DESC
    LIMIT 1
) best ON true
WHERE cp.constraint_type = 'congestion'
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_location_rankings AS
SELECT
    lvs.location_level,
    lvs.location_id,
    dp.der_type,
    lvs.total_value_per_kw_year,
    lvs.value_tier,
    lvs.composite_coincidence_factor,
    lvs.period_year
FROM location_value_stacks lvs
JOIN der_profiles dp ON lvs.der_profile_id = dp.id
WHERE dp.profile_source = 'canonical'
WITH NO DATA;
```

---

## Verification

After Phase 1:
- [ ] All 6 new tables exist in PostgreSQL with correct columns and indexes
- [ ] `isos` table contains the original 7 ISOs (is_rto=true) plus ~65 BA records (is_rto=false)
- [ ] `ba_hourly_data` and `congestion_scores` FKs point to `isos.id` correctly
- [ ] `balancing_authorities` table is dropped
- [ ] `der_profiles` table has 8 canonical profiles seeded
- [ ] `circuits` table still exists and functions normally
- [ ] Materialized views exist (empty, WITH NO DATA)
- [ ] Existing v1 API still works (no endpoints broken)
- [ ] `alembic current` shows the new migration as head

## Files Created/Modified

| File | Action |
|---|---|
| `app/models/constraint_profile.py` | CREATE |
| `app/models/constraint_annotation.py` | CREATE |
| `app/models/der_profile.py` | CREATE |
| `app/models/constraint_der_intersection.py` | CREATE |
| `app/models/location_value_stack.py` | CREATE |
| `app/models/computation_run.py` | CREATE |
| `app/models/iso.py` | MODIFY (add 13 BA columns + relationships) |
| `app/models/congestion.py` | MODIFY (delete BalancingAuthority, rewire FKs) |
| `app/models/__init__.py` | MODIFY (update imports) |
| `alembic/versions/t2n4h7d83k1l_refocused_schema.py` | CREATE |
| `cli/seed_der_profiles.py` | CREATE |
