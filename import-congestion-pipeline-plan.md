# Plan: Import Congestion Index Data Pipeline (v2)

## Context

WattCarbon needs a methodology to quantify the opportunity for dispatchable DERs in non-RTO balancing authorities. Rather than producing a settlement price (which requires unobservable internal generation costs), we produce an **Import Congestion Index** that measures how often and how severely a BA's import paths are stressed, paired with a **Congestion Opportunity Score** that translates that stress into an economic magnitude.

This pipeline fits into the grid-constraint-classifier project as a new workstream (IC) that can run in parallel with Infra, HC, and Data Pipeline workstreams. It depends on Postgres (PostGIS is available) and the EIA API.

### WattCarbon Use Cases

1. **Prospecting tool**: Rank all 60+ BAs by congestion opportunity to identify where capacity swap programs have the strongest value proposition.
2. **Utility pitch material**: Show a specific BA (e.g., SMUD, Duke, Southern Company) their own import utilization duration curve and congestion hours.
3. **Aristotle M&V input**: For weather-sensitive DERs, use interface LMP during import hours as the shadow price. For dispatchable DERs, use the congestion index as the opportunity sizing metric (not the settlement price).
4. **Dashboard visualization**: Map layer showing BA-level congestion scores, clickable to duration curves and hourly profiles.

---

## Data Sources

### Primary: EIA API v2 (free, requires API key registration)

| Endpoint | Data | Frequency | Use |
|----------|------|-----------|-----|
| `electricity/rto/region-data/data/` | Hourly demand, net generation, total interchange by BA | Hourly | Load, import calculation, import-as-%-of-load |
| `electricity/rto/interchange-data/data/` | Hourly interchange between BA pairs (MW) | Hourly | BA-pair breakdown (optional enrichment) |

**API notes:**
- Base URL: `https://api.eia.gov/v2/`
- Auth: `api_key` query parameter (register free at https://www.eia.gov/opendata/)
- Pagination: max 5000 rows per request, use `offset` parameter
- Rate limit: ~100 req/min, no hard enforcement
- Data coverage: July 2015 to present (interchange by BA pair available from ~2018)
- EIA-930 convention: Total Interchange (TI) is positive for net exports, negative for net imports

**Recommended approach:** Use region-data for demand/generation/total interchange (simpler, one call per BA). Use interchange-data only when you need the BA-pair breakdown (e.g., to see BANC's imports specifically from CAISO vs. from TIDC).

### Secondary: RTO Interface LMPs via GridStatus.io

The project already integrates `gridstatus` (v0.29.1) through `adapters/gridstatus_adapter.py`. The `get_lmp()` method supports `locations` and `location_type` parameters that can fetch LMPs for specific interface/scheduling point nodes.

**Implementation approach:** Extend or wrap the existing gridstatus adapter to fetch interface point LMPs by node name. This avoids building 7 separate RTO-specific API clients from scratch. Only build a direct client for an RTO if gridstatus coverage proves insufficient for that RTO's interface nodes.

**Fallback clients (build only if gridstatus gaps found):**

| RTO | Priority | Direct Client Needed? | Notes |
|-----|----------|----------------------|-------|
| CAISO | Tier 1 | Evaluate first | gridstatus supports `locations` param; test with MALIN_5_N101 etc. |
| PJM | Tier 1 | Evaluate first | gridstatus supports `locations` param; test with SOUTH, MISO etc. |
| MISO | Tier 2 | Likely needed | MISO interface node naming in gridstatus may not match expected labels |
| SPP | Tier 2 | Likely needed | SPP node naming is least standardized |
| NYISO/ISO-NE/ERCOT | Skip | No | Cross-border or no non-RTO BAs served; zero business value |

### Reference: BA-to-Interface Mapping

The mapping of non-RTO balancing authorities to their neighboring RTO interface pricing nodes needs to be created as a JSON reference file (`data/reference/ba_interface_map.json`). The mapping tables at the end of this document provide the source data.

This mapping has four dimensions per BA:
1. BA code and name
2. Region and interconnection
3. Primary and secondary RTO neighbors
4. Interface pricing point node IDs for each RTO neighbor

---

## Architecture

### Where It Fits

The pipeline follows existing project conventions:
- **Models** in `app/models/` (SQLAlchemy 2.0 `mapped_column` style)
- **Data adapters** in `adapters/` (adapter pattern with ABC base + registry)
- **Analysis logic** in `core/` (pure-computation modules, pandas-based)
- **CLI orchestration** in `cli/` (argparse-based scripts)
- **API routes** in `app/api/v1/` (FastAPI routers)
- **Reference data** in `data/reference/`

```
grid-constraint-classifier/
├── app/
│   ├── models/
│   │   └── congestion.py               # NEW: 3 SQLAlchemy models
│   └── api/v1/
│       └── congestion_routes.py         # NEW: FastAPI endpoints
├── adapters/
│   ├── eia_client.py                    # NEW: EIA API v2 client
│   └── congestion_lmp/                  # NEW: Interface LMP adapters
│       ├── __init__.py                  #   Exports registry + base
│       ├── base.py                      #   ABC: BaseCongestionLMPAdapter
│       ├── gridstatus_lmp.py            #   Primary: wraps gridstatus for interface LMPs
│       ├── caiso_oasis.py               #   Fallback: direct CAISO OASIS client (if needed)
│       └── pjm_dataminer.py             #   Fallback: direct PJM Data Miner 2 (if needed)
├── core/
│   └── congestion_calculator.py         # NEW: Import congestion computation
├── cli/
│   └── ingest_congestion.py             # NEW: CLI for ingestion + scoring
└── data/
    └── reference/
        └── ba_interface_map.json        # NEW: BA-to-interface mapping
```

### Database Models

Three tables. `InterfaceLMP` stores raw LMP data from RTO scheduling points. `BAHourlyData` stores EIA-930 operational data (no LMP columns; LMPs are joined at query time). `CongestionScore` stores pre-computed metrics per BA per period.

```python
# app/models/congestion.py
# Uses SQLAlchemy 2.0 mapped_column style, matching existing models

from typing import Optional
from datetime import date, datetime

from sqlalchemy import String, Float, Integer, Boolean, Date, DateTime, JSON, ForeignKey, Index, UniqueConstraint, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class BalancingAuthority(Base):
    """Reference table: all US non-RTO balancing authorities with interface mappings."""
    __tablename__ = "balancing_authorities"
    __table_args__ = (
        Index("ix_ba_code", "ba_code", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ba_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    ba_name: Mapped[Optional[str]] = mapped_column(String(200))
    region: Mapped[Optional[str]] = mapped_column(String(50))
    interconnection: Mapped[Optional[str]] = mapped_column(String(20))
    is_rto: Mapped[bool] = mapped_column(Boolean, default=False)
    rto_neighbor: Mapped[Optional[str]] = mapped_column(String(10))
    rto_neighbor_secondary: Mapped[Optional[str]] = mapped_column(String(10))
    interface_points: Mapped[Optional[dict]] = mapped_column(JSON)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    transfer_limit_mw: Mapped[Optional[float]] = mapped_column(Float)
    transfer_limit_method: Mapped[Optional[str]] = mapped_column(String(20))  # "p99", "oasis_ttc", "manual"
    ba_extra: Mapped[Optional[dict]] = mapped_column(JSON)  # Flexible field for notes, data quality flags

    # Relationships
    hourly_data: Mapped[list["BAHourlyData"]] = relationship(back_populates="ba")
    congestion_scores: Mapped[list["CongestionScore"]] = relationship(back_populates="ba")


class InterfaceLMP(Base):
    """Raw hourly LMP data at RTO interface/scheduling points.

    Stored separately from BA hourly data because multiple BAs may reference
    the same interface node (e.g., many SE BAs all use PJM SOUTH).
    """
    __tablename__ = "interface_lmps"
    __table_args__ = (
        Index("ix_interface_lmp_rto_node_ts", "rto", "node_id", "timestamp_utc", unique=True),
        Index("ix_interface_lmp_ts", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rto: Mapped[str] = mapped_column(String(10), nullable=False)
    node_id: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lmp: Mapped[Optional[float]] = mapped_column(Float)
    energy_component: Mapped[Optional[float]] = mapped_column(Float)
    congestion_component: Mapped[Optional[float]] = mapped_column(Float)
    loss_component: Mapped[Optional[float]] = mapped_column(Float)
    market_type: Mapped[str] = mapped_column(String(5), default="DA")


class BAHourlyData(Base):
    """Hourly operational data per BA from EIA-930.

    LMP data is NOT stored here. Join to InterfaceLMP via the BA's
    interface_points mapping + timestamp for economic analysis.
    """
    __tablename__ = "ba_hourly_data"
    __table_args__ = (
        Index("ix_ba_hourly_ba_ts", "ba_id", "timestamp_utc", unique=True),
        Index("ix_ba_hourly_ts", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ba_id: Mapped[int] = mapped_column(ForeignKey("balancing_authorities.id"), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    demand_mw: Mapped[Optional[float]] = mapped_column(Float)
    net_generation_mw: Mapped[Optional[float]] = mapped_column(Float)
    total_interchange_mw: Mapped[Optional[float]] = mapped_column(Float)
    net_imports_mw: Mapped[Optional[float]] = mapped_column(Float)  # Derived: -total_interchange_mw

    ba: Mapped["BalancingAuthority"] = relationship(back_populates="hourly_data")


class CongestionScore(Base):
    """Computed congestion metrics per BA per period (monthly or annual)."""
    __tablename__ = "congestion_scores"
    __table_args__ = (
        Index("ix_congestion_score_ba_period", "ba_id", "period_start", "period_type", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ba_id: Mapped[int] = mapped_column(ForeignKey("balancing_authorities.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[Optional[str]] = mapped_column(String(10))  # "month" or "year"

    # Duration metrics (computed from EIA data alone)
    hours_total: Mapped[Optional[int]] = mapped_column(Integer)
    hours_importing: Mapped[Optional[int]] = mapped_column(Integer)
    pct_hours_importing: Mapped[Optional[float]] = mapped_column(Float)
    hours_above_80: Mapped[Optional[int]] = mapped_column(Integer)
    hours_above_90: Mapped[Optional[int]] = mapped_column(Integer)
    hours_above_95: Mapped[Optional[int]] = mapped_column(Integer)

    # Import intensity
    avg_import_pct_of_load: Mapped[Optional[float]] = mapped_column(Float)
    max_import_pct_of_load: Mapped[Optional[float]] = mapped_column(Float)

    # Economic metrics (require LMP data)
    avg_congestion_premium: Mapped[Optional[float]] = mapped_column(Float)
    congestion_opportunity_score: Mapped[Optional[float]] = mapped_column(Float)  # $/kW-year

    # Metadata
    transfer_limit_used: Mapped[Optional[float]] = mapped_column(Float)
    lmp_coverage: Mapped[Optional[str]] = mapped_column(String(10))  # "none", "partial", "full"
    hours_with_lmp_data: Mapped[Optional[int]] = mapped_column(Integer)
    data_quality_flag: Mapped[Optional[str]] = mapped_column(String(20))  # "good", "partial", "sparse"

    ba: Mapped["BalancingAuthority"] = relationship(back_populates="congestion_scores")
```

**Key design decision: no LMP columns in BAHourlyData.** The original plan embedded `interface_lmp`, `congestion_component`, `lmp_rto_source`, and `lmp_node_id` in BAHourlyData. This creates update headaches when LMP data is re-ingested or interface mappings change. Instead, join at query time:

```sql
-- Example: BA hourly data enriched with interface LMP
SELECT h.*, i.lmp as interface_lmp, i.congestion_component
FROM ba_hourly_data h
JOIN balancing_authorities ba ON h.ba_id = ba.id
LEFT JOIN interface_lmps i
  ON i.node_id = (ba.interface_points->0->>'node_id')
  AND i.timestamp_utc = h.timestamp_utc
  AND i.rto = ba.rto_neighbor
WHERE ba.ba_code = 'BANC'
```

If this join proves too slow for the dashboard, create a materialized view (the project already uses `app/matviews.py` for this pattern).

### API Endpoints

```
GET /api/v1/congestion/scores
    ?period_type=year&year=2024
    Returns: ranked list of BAs by congestion_opportunity_score

GET /api/v1/congestion/scores/{ba_code}
    ?period_type=month&year=2024
    Returns: monthly scores for a specific BA

GET /api/v1/congestion/duration-curve/{ba_code}
    ?year=2024
    Returns: sorted import_utilization array (8760 values) for charting

GET /api/v1/congestion/hourly/{ba_code}
    ?start=2024-07-15&end=2024-07-22
    Returns: hourly detail (load, imports, utilization, interface_lmp via join)

GET /api/v1/congestion/bas
    Returns: all BAs with metadata, transfer limits, RTO neighbors
```

---

## Implementation Phases

### Phase IC-0: Foundation (estimated 2-3 sessions)

**Goal:** EIA API client, reference data loaded, raw interchange flowing into Postgres.

| Step | Task | Details |
|------|------|---------|
| IC-0.1 | Register EIA API key | https://www.eia.gov/opendata/ . Store in `.env` as `EIA_API_KEY`. Add `EIA_API_KEY` to `app/config.py` Settings class. |
| IC-0.2 | Create database models | `app/models/congestion.py` with the four models above. Add imports to `app/models/__init__.py`. Run Alembic migration. |
| IC-0.3 | Build BA reference mapping | Create `data/reference/ba_interface_map.json` from the reference tables at the end of this plan (all 61 BAs, their RTO neighbors, and interface point node IDs). Write a seed script in `cli/ingest_congestion.py` that populates `balancing_authorities` table. |
| IC-0.4 | Build EIA API client | `adapters/eia_client.py`. Handles pagination (5000-row limit), rate limiting, error retry. Two methods: `fetch_region_data(ba_code, start, end)` (returns demand, generation, interchange) and `fetch_interchange_pairs(ba_code, start, end)` (optional, returns BA-pair flows). |
| IC-0.5 | Build ingestion CLI | `cli/ingest_congestion.py` with argparse (matching existing CLI pattern). Command: `python -m cli.ingest_congestion ingest-eia --ba BANC --start 2024-01-01 --end 2024-12-31`. Fetches demand + interchange via region-data endpoint, computes `net_imports_mw = -total_interchange_mw`, stores in `ba_hourly_data`. **Supports incremental mode:** `--since` flag defaults to last timestamp in DB + 1 hour, so ongoing ingestion doesn't re-fetch. |
| IC-0.6 | Estimate transfer limits | For each BA: compute the 99th percentile of hourly net imports across the full history as a robust proxy for transfer limit (avoids outlier sensitivity of using absolute max). Store in `balancing_authorities.transfer_limit_mw` with `transfer_limit_method = 'p99'`. CLI command: `python -m cli.ingest_congestion estimate-limits`. |
| IC-0.7 | Backfill 2024 data | Run ingestion for all 61 BAs for calendar year 2024. ~61 BAs x 8760 hours = ~534K rows. EIA API will require ~61 x ~2 pages each = ~130 API calls. Should complete in under 10 minutes. |

**Verification:**
- `balancing_authorities` table has 61 rows with interface_points populated
- `ba_hourly_data` table has ~534K rows covering all BAs for 2024
- Transfer limits populated with `transfer_limit_method = 'p99'`
- Spot-check: `SELECT ba_code, count(*), avg(net_imports_mw) FROM ba_hourly_data JOIN balancing_authorities ON ... GROUP BY ba_code` returns reasonable results
- BPAT avg should be negative (net exporter), BANC avg should be positive (net importer)

### Phase IC-1: Congestion Calculation + API (estimated 1-2 sessions)

**Goal:** Compute Import Congestion Index and physical congestion metrics for all BAs. Expose via API.

| Step | Task | Details |
|------|------|---------|
| IC-1.1 | Build calculator module | `core/congestion_calculator.py`. Pure-computation module (pandas-based, matching `core/constraint_classifier.py` pattern). Input: hourly data DataFrame for one BA + one period + transfer limit. Output: dict of metrics that maps to a `CongestionScore` record. Computes: import_utilization per hour (no clipping in data; only clip for display), hours above thresholds, avg import as % of load. |
| IC-1.2 | Add calculator unit tests | `tests/test_congestion_calculator.py`. Since this is pure computation with no DB or API dependencies, it's straightforward to test. Cover: zero-import BA produces zero scores, fully-importing BA produces high scores, partial-year data is handled correctly (metrics scaled appropriately, not called "annual"). |
| IC-1.3 | Compute annual scores (no LMP) | Run calculator for all 61 BAs for 2024 using duration metrics only (no interface LMP yet). Store in `congestion_scores` with `lmp_coverage = 'none'`. CLI command: `python -m cli.ingest_congestion compute-scores --year 2024 --period-type year`. |
| IC-1.4 | Build API endpoints | `app/api/v1/congestion_routes.py`. Implement five endpoints listed above. Register router in `app/main.py`. Start with `/scores` and `/duration-curve/{ba_code}` since those are the most immediately useful for prospecting. |
| IC-1.5 | Validate against known patterns | Check: BPAT should show near-zero import congestion (hydro exporter). SOCO/DUK should show summer-concentrated congestion. BANC/AZPS should show tight summer peaks. If not, investigate transfer limit estimates or data issues. |

**Verification:**
- `GET /api/v1/congestion/scores?period_type=year&year=2024` returns ranked list
- Top-ranked BAs are plausible (Southeast, California non-RTO, Arizona)
- BPAT/WAPA hydro BAs rank near bottom
- Duration curve endpoint returns 8760-point arrays that look right

### Phase IC-2: Interface LMP Integration (estimated 2-3 sessions)

**Goal:** Fetch interface pricing data and layer economics onto the physical congestion metrics. GridStatus-first approach: evaluate gridstatus coverage before building any direct API clients.

#### IC-2a: Evaluate GridStatus + Tier 1 (CAISO, PJM)

| Step | Task | Details |
|------|------|---------|
| IC-2.1 | Test gridstatus interface LMP coverage | Write a short test script that calls `gridstatus.CAISO().get_lmp(locations=[list of scheduling point node IDs])` and `gridstatus.PJM().get_lmp(locations=[interface pnode IDs])`. Document which interface nodes return data and which don't. This determines whether we need direct API clients. |
| IC-2.2 | Build congestion LMP adapter | `adapters/congestion_lmp/base.py` with ABC `BaseCongestionLMPAdapter` (method: `fetch_interface_lmp(node_id, start, end, market='DA') -> DataFrame`). `adapters/congestion_lmp/gridstatus_lmp.py` wraps the existing gridstatus adapter. If IC-2.1 shows gaps, build `caiso_oasis.py` and/or `pjm_dataminer.py` as fallbacks. Registry in `adapters/congestion_lmp/__init__.py`. |
| IC-2.3 | Backfill Tier 1 LMP data for 2024 | Fetch all CAISO scheduling point + PJM interface point LMPs for calendar year 2024. Store in `interface_lmps` table. ~6 CAISO nodes x 8760h + ~7 PJM nodes x 8760h = ~114K rows. CLI command: `python -m cli.ingest_congestion ingest-lmp --rto CAISO --year 2024`. |
| IC-2.4 | Validate Tier 1 LMP data | Spot-check: LMPs in plausible range ($20-200/MWh, with occasional spikes). CAISO scheduling point LMPs should track SP15/NP15 with congestion spread. PJM SOUTH should show Southeast premium during summer peaks. |

**Verification (Tier 1):**
- `interface_lmps` table has ~114K rows for 2024
- LMPs have energy/congestion/loss decomposition where available
- Node IDs match expected scheduling point names

#### IC-2b: Tier 2 (MISO, SPP) + Economic Scoring

| Step | Task | Details |
|------|------|---------|
| IC-2.5 | Evaluate gridstatus for MISO + SPP | Same as IC-2.1 but for MISO and SPP interface nodes. MISO interface naming in gridstatus may differ from expected (e.g., MISO.ITVA vs TVA_INTERFACE). SPP is least standardized. If gridstatus gaps exist, build direct clients: `adapters/congestion_lmp/miso_reports.py` (CSV downloads) or `adapters/congestion_lmp/spp_market.py` (CSV downloads). |
| IC-2.6 | Backfill Tier 2 LMP data for 2024 | Fetch MISO + SPP interface LMPs for 2024. Store in `interface_lmps`. ~15-20 interface nodes x 8760h = ~130-175K rows. |
| IC-2.7 | Compute regional baselines per RTO | For each RTO, compute a hub/system-average LMP as the baseline for congestion premium calculations. CAISO: NP15/SP15 avg. PJM: Western Hub. MISO: Indiana Hub. SPP: South Hub. Store as time series in `interface_lmps` with node_id like `{RTO}_HUB_BASELINE`. |
| IC-2.8 | Recompute all scores with economics | Re-run calculator across all BAs for 2024 with LMP data. The join is: for each BA, look up its primary interface node, join hourly LMP, compute `congestion_opportunity_score = sum(interface_lmp - baseline) for hours where utilization > 0.80`, expressed as $/kW-year. Update `congestion_scores` with `lmp_coverage = 'full'` or `'partial'`. |
| IC-2.9 | Monthly score computation | Run calculator at monthly granularity for all BAs. 61 BAs x 12 months = 732 `congestion_scores` rows. |
| IC-2.10 | Handle dual-RTO border BAs | TVA, LGEE, and a few others border two RTOs. Default to primary RTO neighbor from ba_interface_map. Future refinement: use the RTO with the larger import flow for each hour. |

**Verification (full IC-2):**
- `interface_lmps` covers CAISO, PJM, MISO, SPP interface nodes
- BAs with LMP data have `lmp_coverage = 'full'` in their CongestionScore
- Congestion opportunity scores in plausible range ($5-120/kW-year for non-RTO BAs)
- Summer months score higher than winter for summer-peaking BAs
- Rankings stable: SE BAs and desert SW BAs near top, hydro exporters near bottom

### Phase IC-3: Dashboard Visualization (estimated 2-3 sessions)

**Goal:** Map-based visualization of congestion scores with drill-down.

**Note:** The project plans to migrate from Leaflet to MapLibre GL JS (Phase I-2 of Infra). If MapLibre is available by the time IC-3 starts, build on MapLibre. If not, build on Leaflet with awareness that it will be migrated.

| Step | Task | Details |
|------|------|---------|
| IC-3.1 | BA boundary GeoJSON | Obtain or create approximate BA boundary polygons. EIA publishes a BA boundary shapefile. Convert to GeoJSON, store in `data/reference/ba_boundaries.geojson`. If PostGIS is ready (Phase I-1), load directly into a geometry column on `balancing_authorities`. |
| IC-3.2 | Choropleth map layer | New Vue component for congestion visualization. Color BAs by congestion_opportunity_score (graduated color scale). Click a BA to see detail panel. |
| IC-3.3 | Detail panel | On BA click: show duration curve chart (import utilization sorted descending), monthly congestion score bar chart, summer week stack chart (load/internal gen/imports with congestion shading). |
| IC-3.4 | Comparison view | Side-by-side comparison of 2-3 BAs. Useful for pitch decks: "BANC vs BPAT" shows the contrast between congested and uncongested systems. |
| IC-3.5 | Export for pitch materials | "Download as PNG" for duration curves and congestion charts. "Download CSV" for raw hourly data. |

**Verification:**
- Dashboard loads BA choropleth map with graduated colors
- Clicking BANC shows duration curve with clear summer peak
- Clicking BPAT shows flat/zero congestion
- Export produces clean PNG/CSV files

---

## Work Queue (for Section 11 of grid-dashboard-reference.md)

**Import Congestion workstream** (independent, can run in parallel with all other workstreams):

| Step | Item | Depends On | Status |
|------|------|------------|--------|
| IC-0.1 | Register EIA API key + add to config.py | -- | NOT STARTED |
| IC-0.2 | Create congestion DB models + migration | -- | NOT STARTED |
| IC-0.3 | Build BA reference mapping (ba_interface_map.json) + seed script | IC-0.2 | NOT STARTED |
| IC-0.4 | EIA API v2 client (adapters/eia_client.py) | -- | NOT STARTED |
| IC-0.5 | Ingestion CLI with incremental mode | IC-0.2, IC-0.4 | NOT STARTED |
| IC-0.6 | Estimate transfer limits (99th percentile) | IC-0.5 | NOT STARTED |
| IC-0.7 | Backfill all BAs for 2024 | IC-0.5, IC-0.6 | NOT STARTED |
| IC-1.1 | Build congestion calculator module (core/) | -- | NOT STARTED |
| IC-1.2 | Calculator unit tests | IC-1.1 | NOT STARTED |
| IC-1.3 | Compute annual congestion scores (no LMP) | IC-0.7, IC-1.1 | NOT STARTED |
| IC-1.4 | API endpoints for scores and duration curves | IC-1.3 | NOT STARTED |
| IC-1.5 | Validate against known BA patterns | IC-1.3 | NOT STARTED |
| IC-2.1 | Test gridstatus interface LMP coverage (CAISO, PJM) | -- | NOT STARTED |
| IC-2.2 | Congestion LMP adapter (gridstatus-first + fallbacks) | IC-2.1 | NOT STARTED |
| IC-2.3 | Backfill Tier 1 (CAISO + PJM) LMP data for 2024 | IC-2.2 | NOT STARTED |
| IC-2.4 | Validate Tier 1 LMP data | IC-2.3 | NOT STARTED |
| IC-2.5 | Evaluate gridstatus for MISO + SPP; build direct clients if needed | IC-2.1 | NOT STARTED |
| IC-2.6 | Backfill Tier 2 (MISO + SPP) LMP data for 2024 | IC-2.5 | NOT STARTED |
| IC-2.7 | Compute regional baseline LMPs per RTO | IC-2.3, IC-2.6 | NOT STARTED |
| IC-2.8 | Recompute all scores with economic data | IC-1.3, IC-2.3, IC-2.7 | NOT STARTED |
| IC-2.9 | Monthly score computation | IC-2.8 | NOT STARTED |
| IC-2.10 | Handle dual-RTO border BAs | IC-2.8 | NOT STARTED |
| IC-3.1 | BA boundary GeoJSON | -- | NOT STARTED |
| IC-3.2 | Choropleth map layer | IC-1.4, IC-3.1 | NOT STARTED |
| IC-3.3 | Detail panel (duration curves, monthly charts) | IC-3.2 | NOT STARTED |
| IC-3.4 | Comparison view | IC-3.3 | NOT STARTED |
| IC-3.5 | Export for pitch materials | IC-3.3 | NOT STARTED |

---

## Key Formulas

### Import Utilization (hourly)

```
import_utilization(h) = net_imports_mw(h) / transfer_limit_mw
```

Where `net_imports_mw = -total_interchange_mw` (EIA convention: negative interchange = inflows).

Transfer limit is estimated as the **99th percentile** of hourly net imports over the full data history, which approximates the effective path rating while being robust to outliers and data errors. Can be refined later with OASIS TTC postings where available (set `transfer_limit_method = 'oasis_ttc'`).

**No clipping in stored data.** Values above 1.0 are allowed and represent genuine stress events. Only clip for display purposes (e.g., duration curve y-axis cap at 1.2).

### Congestion Opportunity Score (per BA, per period)

```
For each hour h in the period where import_utilization(h) > 0.80:
    premium(h) = interface_lmp(h) - regional_baseline_lmp(h)

COS_raw = sum(premium(h)) for all qualifying hours
    units: $/MWh * hours = $/MW over the period

COS = COS_raw / 1000
    units: $/kW over the period
```

The 80% threshold is configurable. The score represents: "If you deployed 1 kW of dispatchable DER in this BA, how much congestion-related value was available during stressed import hours over this period?"

**Partial-year handling:** If the period has fewer hours than expected (e.g., data only starts in March), `hours_total` tracks actual coverage. The score is the raw sum over available hours (not annualized), and `data_quality_flag` is set to `'partial'`. Annualization is done at the presentation layer if needed.

### Shadow Price for Weather-Sensitive DERs (for Aristotle, separate from this pipeline)

```
IF BA is net importer in hour h:
    DER_value(h) = DER_output(h) * interface_lmp(h)

IF BA is net exporter or self-sufficient in hour h:
    DER_value(h) = 0
```

The congestion pipeline provides the data infrastructure that makes this calculation possible.

---

## EIA API Specifics

### Region Data Request (primary method, gives net interchange directly)

```
GET https://api.eia.gov/v2/electricity/rto/region-data/data/
    ?api_key={key}
    &frequency=hourly
    &data[0]=value
    &facets[respondent][]={ba_code}
    &facets[type][]=D        # Demand
    &facets[type][]=NG       # Net Generation
    &facets[type][]=TI       # Total Interchange
    &start={YYYY-MM-DDTHH}
    &end={YYYY-MM-DDTHH}
    &sort[0][column]=period
    &sort[0][direction]=asc
    &length=5000
```

Returns separate rows for D, NG, and TI for each hour. Pivot by type to get one row per hour with demand, generation, and net interchange.

### Interchange Pair Data Request (optional, for BA-pair breakdown)

```
GET https://api.eia.gov/v2/electricity/rto/interchange-data/data/
    ?api_key={key}
    &frequency=hourly
    &data[0]=value
    &facets[fromba][]={ba_code}
    &start={YYYY-MM-DDTHH}
    &end={YYYY-MM-DDTHH}
    &sort[0][column]=period
    &sort[0][direction]=asc
    &length=5000
    &offset={offset}
```

To get net imports for a BA from a specific neighbor, you need both:
1. `facets[toba][]={ba_code}` (flows INTO the BA)
2. `facets[fromba][]={ba_code}` (flows OUT of the BA)

---

## Data Quality Considerations

| Issue | Impact | Mitigation |
|-------|--------|------------|
| EIA-930 data has reporting gaps | Missing hours for some BAs | Interpolate gaps < 3 hours; flag longer gaps in data_quality_flag |
| Asymmetric interchange reporting | BA A says it sent 100 MW to BA B, but B says it received 50 MW | Use TI (total interchange) from region-data endpoint, which is the BA's own reported net. Don't try to reconcile BA-pair asymmetries. |
| Transfer limit estimation | Both over- and under-estimation possible | 99th percentile is more robust than absolute max. Track method in `transfer_limit_method`. Refine with OASIS TTC data where available. |
| Some BAs have very sparse EIA-930 data | Small BAs may report inconsistently | Flag with data_quality_flag = 'sparse' if < 7000 hours have data in a year. Exclude from rankings or show with caveat. |
| Heat wave spikes can push imports above estimated TL | Utilization > 1.0 in some hours | Allow values > 1.0 in the data. This strengthens the congestion signal. |
| Day-ahead vs real-time LMP | DA and RT prices can diverge significantly | Default to DA LMP for consistency (more stable, fewer data quality issues). Store `market_type` in InterfaceLMP to enable RT analysis later. |
| Dual-RTO border BAs | TVA, LGEE border two RTOs | Default to primary RTO neighbor from ba_interface_map. |
| GridStatus node name mismatches | gridstatus may use different node IDs than RTO OASIS | Map gridstatus location names to expected interface node IDs in the adapter. Document mappings found during IC-2.1 evaluation. |

---

## Session Planning for Claude Code

### Session 1: Foundation
```
1. Read this plan document
2. cd /Users/mcgeesmini/grid-constraint-classifier
3. Add EIA_API_KEY to app/config.py Settings class
4. Create app/models/congestion.py (4 models, SQLAlchemy 2.0 style)
5. Update app/models/__init__.py with new imports
6. Run alembic migration
7. Create data/reference/ba_interface_map.json (from reference tables in this plan)
8. Create adapters/eia_client.py
9. Create seed command in cli/ingest_congestion.py
10. Test: seed BAs, verify 61 rows in balancing_authorities
```

### Session 2: EIA Data Ingestion
```
1. Read this plan, check Section 5 / session log
2. Build ingest-eia CLI command with --since incremental support
3. Test with single BA (BANC) for one month
4. Verify data in ba_hourly_data
5. Run estimate-limits (99th percentile)
6. Backfill all BAs for 2024
7. Spot-check: BPAT should be net exporter, BANC net importer
```

### Session 3: Congestion Calculator + API
```
1. Read this plan, check progress
2. Build core/congestion_calculator.py
3. Write tests/test_congestion_calculator.py
4. Compute annual scores for all BAs (no LMP)
5. Build app/api/v1/congestion_routes.py with /scores and /duration-curve endpoints
6. Register router in app/main.py
7. Test endpoints, validate against expected patterns
8. Commit and push
```

### Session 4: GridStatus Evaluation + LMP Integration
```
1. Test gridstatus interface LMP coverage for CAISO + PJM nodes
2. Document which nodes return data, which need fallback clients
3. Build adapters/congestion_lmp/ (base + gridstatus_lmp + any needed fallbacks)
4. Backfill CAISO + PJM interface LMPs for 2024
5. Test: BANC shows CAISO scheduling point LMP, SOCO shows PJM SOUTH LMP
6. If time: evaluate MISO + SPP gridstatus coverage
```

### Session 5: Tier 2 + Economic Scoring
```
1. Complete MISO + SPP LMP ingestion (gridstatus or direct clients)
2. Compute regional baseline LMPs per RTO
3. Recompute congestion_opportunity_score for all BAs with economics
4. Compute monthly scores (732 rows)
5. Validate rankings, seasonal patterns, economic plausibility
6. Handle dual-RTO BAs
7. Commit and push
```

### Session 6+: Dashboard
```
1. Obtain BA boundary GeoJSON
2. Build choropleth map component
3. Build detail panel with charts
4. Build comparison view
5. Add export functionality
```

---

## Reference: BA-to-Interface Mapping (subset)

These are the BAs most relevant for WattCarbon capacity swap targeting, organized by RTO neighbor:

**CAISO-adjacent (Western):**

| BA Code | BA Name | Interface Point(s) | Notes |
|---------|---------|-------------------|-------|
| BANC | Balancing Auth of N. California | MALIN, NOB | SMUD territory, COTP path |
| AZPS | Arizona Public Service | PVERDE, MEAD | Extreme summer peaking |
| SRP | Salt River Project | PVERDE | Phoenix metro |
| NEVP | NV Energy (North) | ELDORADO | Las Vegas area |
| LDWP | LA Dept of Water & Power | SYLMARDC | Large muni |
| IID | Imperial Irrigation District | ELDORADO | Imperial Valley |
| WALC | Western Area Power (Desert SW) | PVERDE, MEAD | Federal PMA |
| BPAT | Bonneville Power Admin | MALIN | Hydro exporter (control case) |
| PACW | PacifiCorp West | MALIN | Oregon territory |
| PGE | Portland General Electric | MALIN | Oregon territory |

**PJM-adjacent (Southeast):**

| BA Code | BA Name | Interface Point(s) | Notes |
|---------|---------|-------------------|-------|
| SOCO | Southern Company | SOUTH | Largest non-RTO BA in SE |
| DUK | Duke Energy Carolinas | SOUTH | NC/SC territory |
| CPLE | Duke Energy Progress East | SOUTH | Eastern NC |
| CPLW | Duke Energy Progress West | SOUTH | Western NC |
| SCEG | Dominion Energy SC | SOUTH | South Carolina |
| SC | South Carolina Pub Svc Auth | SOUTH | Santee Cooper |
| FPC | Duke Energy Florida | SOUTH (distant) | FL, weaker signal |
| FPL | Florida Power & Light | SOUTH (distant) | FL, weaker signal |
| SEC | Seminole Electric | SOUTH (distant) | FL co-op |

**MISO-adjacent (Central):**

| BA Code | BA Name | Interface Point(s) | Notes |
|---------|---------|-------------------|-------|
| TVA | Tennessee Valley Authority | MISO interface (+ PJM SOUTH) | Large federal PMA, dual-RTO border |
| AECI | Associated Electric Coop | MISO interface | Missouri co-op |
| LGEE | Louisville Gas & Electric/KU | MISO interface | Kentucky, PPL subsidiary |

**SPP-adjacent (Great Plains / Interior West):**

| BA Code | BA Name | Interface Point(s) | Notes |
|---------|---------|-------------------|-------|
| PSCO | Public Service Co of Colorado | SPP interface | Xcel territory |
| WACM | Western Area Power (CO/MT) | SPP interface | Federal PMA |
| SWPA | Southwestern Power Admin | SPP interface | Federal PMA, AR/OK/MO |
| GRDA | Grand River Dam Authority | SPP interface | Oklahoma |
| EDE | Empire District Electric | SPP interface | MO/KS/OK |

Full mapping of all 61 BAs should be compiled into `data/reference/ba_interface_map.json` during IC-0.3.

---

## Changes from v1

| Change | Rationale |
|--------|-----------|
| Directory structure rewritten to match actual project (`app/`, `core/`, `adapters/`, `cli/`) | v1 used `backend/services/` which doesn't exist |
| Models use SQLAlchemy 2.0 `mapped_column` style | Matches all existing models in the project |
| Removed LMP columns from `BAHourlyData` | Avoids update headaches; join at query time or use materialized view |
| GridStatus-first approach for LMP integration | Project already uses gridstatus (v0.29.1) with `get_lmp(locations=...)` support; avoid building 7 RTO clients from scratch |
| Dropped Tier 3 RTOs (NYISO, ISO-NE, ERCOT) | Zero business value: cross-border Canadian BAs or no non-RTO BAs served |
| Transfer limit uses 99th percentile instead of absolute max | More robust to outliers and data errors |
| Removed utilization clipping contradiction | v1 said "clip to [-0.5, 1.0]" in IC-1.1 but "don't clip" in Data Quality section |
| Added incremental ingestion (`--since` flag) | Essential for ongoing data updates, not just one-time backfill |
| Added `EIA_API_KEY` to `app/config.py` | v1 only mentioned `.env` but config.py is how the app loads settings |
| Added calculator unit tests (IC-1.2) | Pure-computation module is easy to test; project has 0% test coverage |
| Renamed `metadata` column to `ba_extra` | Avoids collision with SQLAlchemy MetaData reserved name |
| Added `transfer_limit_method` column | Tracks provenance of transfer limit estimate (p99 vs OASIS TTC vs manual) |
| Added `hours_total` to CongestionScore | Needed to distinguish partial-year data from full-year |
| Added `lmp_coverage` to CongestionScore | Replaces overloaded `data_quality_flag` for LMP availability tracking |
| Explicit partial-year handling in COS formula | v1 didn't address how to handle periods with incomplete data |
| Reduced estimated sessions from ~7 to ~6 | Dropping Tier 3 and using gridstatus saves 1-2 sessions |

---

## Update Rules for grid-dashboard-reference.md

When this workstream starts, add to Section 11 (Work Queue):

```markdown
**Import Congestion workstream** (independent):

| Step | Item | Depends On | Status |
|------|------|------------|--------|
| IC-0 | Foundation (EIA client, models, BA reference data) | -- | NOT STARTED |
| IC-1 | Congestion calculation (scores, tests, API endpoints) | IC-0 | NOT STARTED |
| IC-2a | Tier 1 LMP integration (CAISO, PJM via gridstatus) | IC-1 | NOT STARTED |
| IC-2b | Tier 2 LMP + baselines + full scoring (MISO, SPP) | IC-2a | NOT STARTED |
| IC-3 | Dashboard visualization (choropleth, drill-down) | IC-1 + map layer | NOT STARTED |
```

Add to Section 13 (External Resources):

```markdown
- EIA API v2: https://api.eia.gov/v2/
- EIA API docs: https://www.eia.gov/opendata/documentation.php
- EIA Grid Monitor: https://www.eia.gov/electricity/gridmonitor/
- GridStatus.io: https://www.gridstatus.io/ (already integrated via adapters/gridstatus_adapter.py)
```
