# Plan: Import Congestion Index Data Pipeline

## Context

WattCarbon needs a methodology to quantify the opportunity for dispatchable DERs in non-RTO balancing authorities. Rather than producing a settlement price (which requires unobservable internal generation costs), we produce an **Import Congestion Index** that measures how often and how severely a BA's import paths are stressed, paired with a **Congestion Opportunity Score** that translates that stress into an economic magnitude.

This pipeline fits into the grid-constraint-classifier project as a new workstream (IC) that can run in parallel with Infra, HC, and Data Pipeline workstreams. It depends only on Postgres (no PostGIS required) and the EIA API.

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
| `electricity/rto/interchange-data/data/` | Hourly interchange between BA pairs (MW) | Hourly | Net import calculation per BA |
| `electricity/rto/region-data/data/` | Hourly demand and net generation by BA | Hourly | Load and import-as-%-of-load |
| `electricity/rto/fuel-type-data/data/` | Hourly generation by fuel type per BA | Hourly | Marginal fuel identification (optional, Phase 2) |

**API notes:**
- Base URL: `https://api.eia.gov/v2/`
- Auth: `api_key` query parameter (register free at https://www.eia.gov/opendata/)
- Pagination: max 5000 rows per request, use `offset` parameter
- Rate limit: ~100 req/min, no hard enforcement
- Data coverage: July 2015 to present (interchange by BA pair available from ~2018)
- EIA-930 convention: **negative interchange = inflows (imports), positive = outflows (exports)**, but the API `interchange-data` endpoint reports the `value` as the flow FROM `fromba` TO `toba`, so a positive value at `fromba=CISO, toba=BANC` means BANC is importing from CAISO

### Secondary: RTO Interface LMPs (all 7 RTOs)

| RTO | Source | Auth | Format | Interface Nodes | Non-RTO BAs Served |
|-----|--------|------|--------|-----------------|--------------------|
| CAISO | OASIS (oasis.caiso.com) | None | CSV/XML | MALIN, NOB, PVERDE, ELDORADO, MEAD, SYLMARDC | BANC, AZPS, SRP, NEVP, LDWP, IID, WALC, TIDC, PACW, BPAT, AVA, CHPD, DOPD, GCPD, TPWR, PGE, PSEI, SCL |
| PJM | Data Miner 2 (dataminer2.pjm.com) | Free API key | JSON | SOUTH, MISO, NYIS, IMO, NEPTUNE, LINDENVFT, HUDSONTP | SOCO, DUK, CPLE, CPLW, SC, SCEG, SEC, FPC, FPL, JEA, TEC, TAL, NSB, GVL, HST |
| MISO | Market Reports (misoenergy.org) | None | CSV | Interface nodes at PJM, SPP, TVA, AECI, LGEE, MH borders | TVA, AECI, LGEE, OVEC, plus MISO-adjacent munis |
| SPP | Market Data (spp.org) | None | CSV | Interface nodes at MISO, ERCOT (DC ties), AECI, WAPA borders | PSCO, WACM, SWPA, GRDA, CLEC, EDE, KACY, KCPL, OKGE, SPS |
| NYISO | OASIS (nyiso.com) | None | CSV | PJM, ISO-NE, HQ (Hydro-Quebec), IESO (Ontario) proxy buses | HQ, IESO (cross-border; lower priority for US-only analysis) |
| ISO-NE | Web Services (iso-ne.com) | None | JSON/XML | External nodes at NYISO, NB (New Brunswick), HQ interfaces | NBSO (New Brunswick; cross-border, lowest priority) |
| ERCOT | MIS (ercot.com) | Free account | CSV | DC tie scheduling points (SPP, MISO connections) | None directly (ERCOT is a single BA; DC tie prices useful for SPP/MISO border analysis) |

**Priority for implementation:** CAISO and PJM are Tier 1 (cover the highest-value target BAs for capacity swaps). MISO and SPP are Tier 2 (cover central US BAs with no other price signal). NYISO, ISO-NE, and ERCOT are Tier 3 (cross-border or edge cases).

| GridStatus.io | Aggregated LMP data across all ISOs | API key (free tier available) | JSON | All of the above | Convenience wrapper; can substitute for individual RTO clients if API coverage is sufficient |

### Reference: BA-to-Interface Mapping

The mapping of all 61 US balancing authorities to their neighboring RTO interface pricing nodes was developed in a prior session and exists as `ba_interface_map.xlsx`. This file has four tabs:

1. Complete BA mapping (BA code, name, region, RTO neighbor, interface pricing points)
2. CAISO scheduling points detail
3. PJM interface pricing points detail
4. Data sources and methodology

**This file must be loaded into the project as a reference table before the pipeline runs.**

---

## Architecture

### Where It Fits

```
grid-constraint-classifier/
├── backend/
│   ├── models/
│   │   └── congestion.py          # NEW: SQLAlchemy models
│   ├── routes/
│   │   └── congestion.py          # NEW: FastAPI endpoints
│   ├── services/
│   │   └── congestion/            # NEW: Pipeline logic
│   │       ├── __init__.py
│   │       ├── eia_client.py      # EIA API v2 client (interchange + region data)
│   │       ├── lmp/               # RTO interface LMP clients
│   │       │   ├── __init__.py    # Exports abstract BaseLMPClient + registry
│   │       │   ├── base.py        # Abstract base: fetch_interface_lmp(node, start, end)
│   │       │   ├── caiso.py       # CAISO OASIS scheduling point LMPs
│   │       │   ├── pjm.py         # PJM Data Miner 2 interface LMPs
│   │       │   ├── miso.py        # MISO market reports interface LMPs
│   │       │   ├── spp.py         # SPP market data interface LMPs
│   │       │   ├── nyiso.py       # NYISO proxy generator bus LMPs (Tier 3)
│   │       │   ├── isone.py       # ISO-NE external node LMPs (Tier 3)
│   │       │   └── ercot.py       # ERCOT DC tie pricing (Tier 3)
│   │       ├── calculator.py      # Congestion index computation
│   │       └── ingestion.py       # Orchestrator: fetch, compute, store
│   └── cli/
│       └── congestion.py          # NEW: CLI commands for ingestion
├── data/
│   └── reference/
│       └── ba_interface_map.json  # NEW: BA-to-interface mapping (from xlsx)
└── frontend/
    └── src/
        └── components/
            └── CongestionMap.vue   # NEW: Dashboard visualization (Phase 3)
```

### Database Models

```python
# models/congestion.py

class BalancingAuthority(Base):
    """Reference table: all US balancing authorities with RTO interface mappings."""
    __tablename__ = 'balancing_authorities'

    id = Column(Integer, primary_key=True)
    ba_code = Column(String(10), unique=True, nullable=False, index=True)  # e.g. "BANC"
    ba_name = Column(String(200))                                          # e.g. "Balancing Authority of Northern California"
    region = Column(String(50))                                            # e.g. "Western"
    interconnection = Column(String(20))                                   # "Eastern", "Western", "ERCOT"
    is_rto = Column(Boolean, default=False)
    rto_neighbor = Column(String(10))                                      # Primary RTO neighbor code
    rto_neighbor_secondary = Column(String(10))                            # Secondary RTO (e.g., TVA borders both PJM and MISO)
    interface_points = Column(JSON)                                        # List of {rto, node_id, node_name} dicts
    latitude = Column(Float)                                               # Approximate centroid for map
    longitude = Column(Float)
    transfer_limit_mw = Column(Float)                                      # Estimated, from OASIS or empirical max
    metadata = Column(JSON)                                                # Flexible field for notes, data quality flags

    # Relationships
    hourly_data = relationship('BAHourlyData', back_populates='ba')
    congestion_scores = relationship('CongestionScore', back_populates='ba')


class InterfaceLMP(Base):
    """Raw hourly LMP data at RTO interface/scheduling points.
    
    Stored separately from BA hourly data because multiple BAs may reference
    the same interface node (e.g., many SE BAs all use PJM SOUTH).
    """
    __tablename__ = 'interface_lmps'

    id = Column(BigInteger, primary_key=True)
    rto = Column(String(10), nullable=False, index=True)         # "CAISO", "PJM", "MISO", "SPP", "NYISO", "ISONE", "ERCOT"
    node_id = Column(String(50), nullable=False, index=True)     # e.g. "MALIN_5_N101", "SOUTH", "MISO_AECI"
    timestamp_utc = Column(DateTime, nullable=False, index=True)
    lmp = Column(Float)                                           # Total LMP ($/MWh)
    energy_component = Column(Float)                              # Energy component ($/MWh)
    congestion_component = Column(Float)                          # Congestion component ($/MWh)
    loss_component = Column(Float)                                # Loss component ($/MWh)
    market_type = Column(String(5), default='DA')                 # "DA" (day-ahead) or "RT" (real-time)

    __table_args__ = (
        Index('ix_interface_lmp_rto_node_ts', 'rto', 'node_id', 'timestamp_utc', unique=True),
    )


class BAHourlyData(Base):
    """Hourly operational data per BA from EIA-930, enriched with interface LMP."""
    __tablename__ = 'ba_hourly_data'

    id = Column(BigInteger, primary_key=True)
    ba_id = Column(Integer, ForeignKey('balancing_authorities.id'), nullable=False, index=True)
    timestamp_utc = Column(DateTime, nullable=False, index=True)
    demand_mw = Column(Float)
    net_generation_mw = Column(Float)
    total_interchange_mw = Column(Float)          # Positive = net exports, negative = net imports
    net_imports_mw = Column(Float)                 # Derived: -total_interchange_mw (positive when importing)
    import_utilization = Column(Float)             # net_imports_mw / transfer_limit_mw (0 to 1+)
    interface_lmp = Column(Float)                  # LMP at the relevant RTO interface node ($/MWh)
    congestion_component = Column(Float)           # Congestion portion of interface LMP ($/MWh)
    lmp_rto_source = Column(String(10))            # Which RTO provided this LMP ("CAISO", "PJM", etc.)
    lmp_node_id = Column(String(50))               # Which interface node was used

    # Composite index for time-series queries
    __table_args__ = (
        Index('ix_ba_hourly_ba_ts', 'ba_id', 'timestamp_utc', unique=True),
    )

    ba = relationship('BalancingAuthority', back_populates='hourly_data')


class CongestionScore(Base):
    """Computed congestion metrics per BA per period (monthly or annual)."""
    __tablename__ = 'congestion_scores'

    id = Column(Integer, primary_key=True)
    ba_id = Column(Integer, ForeignKey('balancing_authorities.id'), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(String(10))              # "month" or "year"

    # Duration metrics
    hours_importing = Column(Integer)
    pct_hours_importing = Column(Float)
    hours_above_80 = Column(Integer)              # Import utilization > 80%
    hours_above_90 = Column(Integer)
    hours_above_95 = Column(Integer)

    # Economic metrics
    avg_import_pct_of_load = Column(Float)        # Avg net_imports / demand during import hours
    max_import_pct_of_load = Column(Float)
    avg_congestion_premium = Column(Float)        # Avg (interface_lmp - regional_baseline) during >80% hours
    congestion_opportunity_score = Column(Float)  # Sum of premium * hours, in $/kW-year

    # Metadata
    transfer_limit_used = Column(Float)           # The TL value used for this computation
    lmp_rto_source = Column(String(10))           # Which RTO's LMP was used
    data_quality_flag = Column(String(20))        # "good", "partial", "no_lmp", "sparse"
    hours_with_lmp_data = Column(Integer)         # How many hours had interface LMP available

    ba = relationship('BalancingAuthority', back_populates='congestion_scores')
```

### API Endpoints

```
GET /api/congestion/scores
    ?period_type=year&year=2024
    Returns: ranked list of BAs by congestion_opportunity_score

GET /api/congestion/scores/{ba_code}
    ?period_type=month&year=2024
    Returns: monthly scores for a specific BA

GET /api/congestion/duration-curve/{ba_code}
    ?year=2024
    Returns: sorted import_utilization array (8760 values) for charting

GET /api/congestion/hourly/{ba_code}
    ?start=2024-07-15&end=2024-07-22
    Returns: hourly detail (load, imports, utilization, interface_lmp)

GET /api/congestion/bas
    Returns: all BAs with metadata, transfer limits, RTO neighbors
```

---

## Implementation Phases

### Phase IC-0: Foundation (estimated 2-3 sessions)

**Goal:** EIA API client, reference data loaded, raw interchange flowing into Postgres.

| Step | Task | Details |
|------|------|---------|
| IC-0.1 | Register EIA API key | https://www.eia.gov/opendata/ -- store in `.env` as `EIA_API_KEY` |
| IC-0.2 | Create database models | `models/congestion.py` with the three tables above. Run Alembic migration. |
| IC-0.3 | Load BA reference data | Convert `ba_interface_map.xlsx` to JSON. Write seed script that populates `balancing_authorities` table with all 61 BAs, their RTO neighbors, and interface points. |
| IC-0.4 | Build EIA API client | `services/congestion/eia_client.py`. Handles pagination (5000-row limit), rate limiting, error retry. Two methods: `fetch_interchange(ba_code, start, end)` and `fetch_region_data(ba_code, start, end)`. |
| IC-0.5 | Build ingestion CLI | `cli/congestion.py` with Click or Typer. Command: `ingest-eia --ba BANC --start 2024-01-01 --end 2024-12-31`. Fetches demand + interchange, computes `net_imports_mw`, stores in `ba_hourly_data`. |
| IC-0.6 | Estimate transfer limits | For each BA: query the max observed net import across the full history as an empirical proxy for transfer limit. Store in `balancing_authorities.transfer_limit_mw`. Add a CLI command: `estimate-transfer-limits`. |
| IC-0.7 | Backfill 2024 data | Run ingestion for all 61 BAs for calendar year 2024. This is ~61 BAs x 8760 hours = ~534K rows. EIA API will require ~61 x 2 calls (interchange + region) x ~2 pages each = ~250 API calls. Should complete in under 10 minutes. |

**Verification:**
- `ba_hourly_data` table has ~534K rows covering all BAs for 2024
- `balancing_authorities` table has 61 rows with transfer limits populated
- `SELECT ba_code, count(*), avg(net_imports_mw) FROM ba_hourly_data JOIN balancing_authorities ON ... GROUP BY ba_code` returns reasonable results

### Phase IC-1: Congestion Calculation (estimated 1-2 sessions)

**Goal:** Compute Import Congestion Index and Congestion Opportunity Score for all BAs.

| Step | Task | Details |
|------|------|---------|
| IC-1.1 | Compute import utilization | Batch update: `ba_hourly_data.import_utilization = net_imports_mw / transfer_limit_mw` for all rows. Clip to [-0.5, 1.0] range. |
| IC-1.2 | Build calculator module | `services/congestion/calculator.py`. Input: hourly data for one BA + one period. Output: `CongestionScore` record. Implements the formulas from our analysis: hours above thresholds, avg import as % of load, congestion opportunity score. |
| IC-1.3 | Compute annual scores (no LMP) | Run calculator for all 61 BAs for 2024, using duration metrics only (no interface LMP yet). This produces the "physical congestion" metrics: utilization hours, duration curves. Store in `congestion_scores` with `data_quality_flag = 'no_lmp'`. |
| IC-1.4 | Build API endpoints | `routes/congestion.py`. Implement the five endpoints listed above. Start with `/scores` and `/duration-curve/{ba_code}` since those are the most immediately useful. |
| IC-1.5 | Validate against known patterns | Check: BPAT should show near-zero import congestion (hydro exporter). SOCO/DUK should show summer-concentrated congestion. BANC/AZPS should show tight summer peaks. If not, investigate transfer limit estimates or data issues. |

**Verification:**
- `GET /api/congestion/scores?period_type=year&year=2024` returns ranked list
- Top-ranked BAs are plausible (Southeast, California non-RTO, Arizona)
- BPAT/WAPA hydro BAs rank near bottom
- Duration curve endpoint returns 8760-point arrays that look right

### Phase IC-2: Interface LMP Integration — All RTOs (estimated 3-4 sessions)

**Goal:** Build LMP clients for all 7 RTOs, backfill interface pricing data, and layer economics onto the physical congestion metrics. Tiered approach: CAISO + PJM first (highest-value BAs), then MISO + SPP (fills remaining gaps), then NYISO + ISO-NE + ERCOT (completeness).

#### IC-2a: Abstract Client + Tier 1 (CAISO, PJM)

| Step | Task | Details |
|------|------|---------|
| IC-2.1 | Define abstract LMP client interface | `services/congestion/lmp/base.py`. Abstract base class `BaseLMPClient` with method: `fetch_interface_lmp(node_id: str, start: datetime, end: datetime, market: str = 'DA') -> DataFrame[timestamp_utc, lmp, energy, congestion, loss]`. All RTO clients implement this. Also define a client registry: `get_lmp_client(rto: str) -> BaseLMPClient`. |
| IC-2.2 | Build CAISO OASIS client | `services/congestion/lmp/caiso.py`. Fetch scheduling point LMPs from CAISO OASIS (public CSV, no auth). Target nodes: `MALIN_5_N101`, `PVERDE_5_N101`, `ELDORADO_5_N101`, `NOB_5_N101`, `MEAD_5_N101`, `SYLMARDC_5_N101`. OASIS API uses XML query parameters; LMP data returned as CSV. Parse and normalize to common schema. Handles CAISO's 25-day max query window by chunking. |
| IC-2.3 | Build PJM Data Miner 2 client | `services/congestion/lmp/pjm.py`. Fetch interface pricing point LMPs from PJM Data Miner 2 (free API key required, register at dataminer2.pjm.com). Target nodes: `SOUTH` (serves most SE BAs), `MISO` (PJM-MISO seam), `NYIS` (PJM-NYISO), `IMO` (Ontario), plus cable interfaces `NEPTUNE`, `LINDENVFT`, `HUDSONTP`. PJM uses a JSON REST API with pagination. Decomposition into energy/congestion/loss available. |
| IC-2.4 | Backfill Tier 1 LMP data for 2024 | Fetch all CAISO scheduling point + PJM interface point LMPs for calendar year 2024. Store in `interface_lmps` table. ~6 CAISO nodes x 8760h + ~7 PJM nodes x 8760h = ~114K rows. |
| IC-2.5 | Map Tier 1 BAs to LMP series | Use `ba_interface_map` reference data. For each BA with a CAISO or PJM neighbor, join the appropriate interface LMP series to `ba_hourly_data`. Update `interface_lmp`, `congestion_component`, `lmp_rto_source`, and `lmp_node_id`. This covers ~35-40 of the 61 BAs. |

**Verification (Tier 1):**
- `interface_lmps` table has ~114K rows for 2024
- `ba_hourly_data` rows for BANC show CAISO MALIN LMP populated
- `ba_hourly_data` rows for SOCO show PJM SOUTH LMP populated
- LMPs are in plausible range ($20-200/MWh, with occasional spikes)

#### IC-2b: Tier 2 (MISO, SPP)

| Step | Task | Details |
|------|------|---------|
| IC-2.6 | Build MISO client | `services/congestion/lmp/miso.py`. MISO publishes LMP data through market reports (CSV downloads) and a data portal. Interface nodes are labeled by neighboring BA/RTO (e.g., MISO-PJM, MISO-SPP, MISO-TVA). Historical data available as bulk CSV downloads by month. Key challenge: MISO's node naming conventions differ from PJM/CAISO; requires a mapping table from MISO interface node IDs to BA-facing labels. |
| IC-2.7 | Build SPP client | `services/congestion/lmp/spp.py`. SPP publishes LMP data through its market data portal. Interface nodes at MISO, ERCOT (DC ties), AECI, and WAPA borders. SPP's data is organized by settlement location; interface points are a subset. Available as CSV. Key challenge: SPP's market footprint expanded significantly in recent years (RTO West), so some interface nodes are new. |
| IC-2.8 | Backfill Tier 2 LMP data for 2024 | Fetch MISO + SPP interface LMPs for 2024. Store in `interface_lmps`. Estimated ~8-12 MISO interface nodes + ~6-8 SPP interface nodes x 8760h = ~120-175K rows. |
| IC-2.9 | Map Tier 2 BAs to LMP series | Associate MISO- and SPP-adjacent BAs with their interface LMPs. Key BAs: TVA (MISO interface), AECI (MISO interface), LGEE (MISO interface), PSCO (SPP interface), WACM (SPP interface), SWPA (SPP interface). This fills in ~15-20 additional BAs. |

**Verification (Tier 2):**
- TVA hours now show MISO interface LMP (not PJM SOUTH)
- PSCO hours show SPP interface LMP
- BAs that border multiple RTOs (e.g., TVA borders both PJM and MISO) use the interface with the larger import flow for that hour, or the primary RTO neighbor as default

#### IC-2c: Tier 3 (NYISO, ISO-NE, ERCOT) + Baselines + Final Scoring

| Step | Task | Details |
|------|------|---------|
| IC-2.10 | Build NYISO client | `services/congestion/lmp/nyiso.py`. Proxy generator bus LMPs at interfaces with PJM, ISO-NE, HQ, IESO. Lower priority because most NYISO neighbors are already in an RTO. Useful for cross-border analysis with Canadian BAs. |
| IC-2.11 | Build ISO-NE client | `services/congestion/lmp/isone.py`. External node LMPs at NYISO, New Brunswick, Quebec interfaces. Lowest US priority; mainly relevant for NBSO (New Brunswick). |
| IC-2.12 | Build ERCOT client | `services/congestion/lmp/ercot.py`. DC tie scheduling point pricing. ERCOT connects to SPP and MISO only via DC ties with limited capacity. Published through ERCOT MIS. Not critical for congestion analysis since ERCOT is a single BA, but useful for completeness and for analyzing SPP/MISO border economics from the ERCOT side. |
| IC-2.13 | Compute regional baselines per RTO | For each RTO, compute the system-average or hub LMP as the baseline for congestion premium calculations. CAISO: use SP15 or NP15 trading hub average. PJM: use Western Hub. MISO: use Indiana Hub. SPP: use South Hub. NYISO: use Zone J or system. ISO-NE: use Mass Hub. ERCOT: use Houston Hub. Store as a simple time series in `interface_lmps` with a special `node_id` like `{RTO}_SYSTEM_AVG`. |
| IC-2.14 | Recompute all scores with economics | Re-run calculator across all BAs for 2024 with LMP data. `congestion_opportunity_score = sum(interface_lmp - baseline) for hours where utilization > 0.80`, expressed as $/kW-year. Update `congestion_scores` records. Change `data_quality_flag` to `'with_lmp'` for BAs with LMP coverage, keep `'no_lmp'` for any BAs where no RTO interface LMP was available. |
| IC-2.15 | Monthly score computation | Run calculator at monthly granularity for all BAs. 61 BAs x 12 months = 732 `congestion_scores` rows. |

**Verification (full IC-2):**
- `interface_lmps` table covers all 7 RTOs
- Every non-RTO BA in `ba_hourly_data` has `lmp_rto_source` populated for the vast majority of hours
- `congestion_scores` for all BAs have `data_quality_flag` of `'with_lmp'` (except possibly a few very small BAs with no clear RTO neighbor)
- Congestion opportunity scores in plausible range ($5-120/kW-year for non-RTO BAs)
- Summer months score much higher than winter for summer-peaking BAs
- Rankings stable: SE BAs and desert SW BAs near top, hydro exporters near bottom

### Phase IC-3: Dashboard Visualization (estimated 2-3 sessions)

**Goal:** Map-based visualization of congestion scores with drill-down.

| Step | Task | Details |
|------|------|---------|
| IC-3.1 | BA boundary GeoJSON | Obtain or create approximate BA boundary polygons. EIA publishes a BA boundary shapefile. Convert to GeoJSON, store in `data/reference/ba_boundaries.geojson`. |
| IC-3.2 | Choropleth map layer | `CongestionMap.vue`. Color BAs by congestion_opportunity_score (graduated color scale). Uses existing Leaflet setup (no MapLibre dependency). Click a BA to see detail panel. |
| IC-3.3 | Detail panel | On BA click: show duration curve chart (import utilization sorted descending), monthly congestion score bar chart, summer week stack chart (load/internal gen/imports with congestion shading). Use Chart.js or lightweight charting. |
| IC-3.4 | Comparison view | Side-by-side comparison of 2-3 BAs. Useful for pitch decks: "BANC vs BPAT" shows the contrast between congested and uncongested systems. |
| IC-3.5 | Export for pitch materials | "Download as PNG" for duration curves and congestion charts. "Download CSV" for raw hourly data. These support WattCarbon pitch deck preparation. |

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
| IC-0.1 | Register EIA API key | -- | NOT STARTED |
| IC-0.2 | Create congestion DB models + migration | -- | NOT STARTED |
| IC-0.3 | Load BA reference data (ba_interface_map) | IC-0.2 | NOT STARTED |
| IC-0.4 | EIA API v2 client (interchange + region data) | -- | NOT STARTED |
| IC-0.5 | Ingestion CLI (fetch + store hourly data) | IC-0.2, IC-0.4 | NOT STARTED |
| IC-0.6 | Estimate transfer limits from historical max imports | IC-0.5 | NOT STARTED |
| IC-0.7 | Backfill all BAs for 2024 | IC-0.5, IC-0.6 | NOT STARTED |
| IC-1.1 | Compute import utilization for all hourly records | IC-0.7 | NOT STARTED |
| IC-1.2 | Build congestion calculator module | -- | NOT STARTED |
| IC-1.3 | Compute annual congestion scores (no LMP) | IC-1.1, IC-1.2 | NOT STARTED |
| IC-1.4 | API endpoints for scores and duration curves | IC-1.3 | NOT STARTED |
| IC-1.5 | Validate against known BA patterns | IC-1.3 | NOT STARTED |
| IC-2.1 | Abstract LMP client interface + registry | -- | NOT STARTED |
| IC-2.2 | CAISO OASIS scheduling point LMP client | IC-2.1 | NOT STARTED |
| IC-2.3 | PJM Data Miner 2 interface LMP client | IC-2.1 | NOT STARTED |
| IC-2.4 | Backfill Tier 1 (CAISO + PJM) LMP data for 2024 | IC-2.2, IC-2.3 | NOT STARTED |
| IC-2.5 | Map Tier 1 BAs to LMP series | IC-0.3, IC-2.4 | NOT STARTED |
| IC-2.6 | MISO market reports interface LMP client | IC-2.1 | NOT STARTED |
| IC-2.7 | SPP market data interface LMP client | IC-2.1 | NOT STARTED |
| IC-2.8 | Backfill Tier 2 (MISO + SPP) LMP data for 2024 | IC-2.6, IC-2.7 | NOT STARTED |
| IC-2.9 | Map Tier 2 BAs to LMP series | IC-0.3, IC-2.8 | NOT STARTED |
| IC-2.10 | NYISO proxy bus LMP client (Tier 3) | IC-2.1 | NOT STARTED |
| IC-2.11 | ISO-NE external node LMP client (Tier 3) | IC-2.1 | NOT STARTED |
| IC-2.12 | ERCOT DC tie pricing client (Tier 3) | IC-2.1 | NOT STARTED |
| IC-2.13 | Compute regional baseline LMPs per RTO | IC-2.4, IC-2.8 | NOT STARTED |
| IC-2.14 | Recompute all scores with economic data | IC-1.3, IC-2.5, IC-2.9, IC-2.13 | NOT STARTED |
| IC-2.15 | Monthly score computation | IC-2.14 | NOT STARTED |
| IC-3.1 | BA boundary GeoJSON | -- | NOT STARTED |
| IC-3.2 | Choropleth map layer (Vue/Leaflet) | IC-1.4, IC-3.1 | NOT STARTED |
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

Transfer limit is estimated as the observed historical maximum net import over the full data history, which approximates the effective path rating. Can be refined later with OASIS TTC postings where available.

### Congestion Opportunity Score (annual, per BA)

```
For each hour h where import_utilization(h) > 0.80:
    premium(h) = interface_lmp(h) - regional_baseline_lmp(h)

COS = sum(premium(h)) for all h where utilization > 0.80
    expressed as $/kW-year (divide by 1000 if computed in $/MW-year)
```

The 80% threshold is configurable. The score represents: "If you deployed 1 kW of dispatchable DER in this BA, how much congestion-related value was available during stressed import hours over the year?"

### Shadow Price for Weather-Sensitive DERs (separate from this pipeline, for Aristotle)

```
IF BA is net importer in hour h:
    DER_value(h) = DER_output(h) * interface_lmp(h)

IF BA is net exporter or self-sufficient in hour h:
    DER_value(h) = 0
```

This is the settlement methodology from our earlier discussion. The congestion pipeline provides the data infrastructure that makes this calculation possible.

---

## EIA API Specifics

### Interchange Data Request

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

Returns rows with: `period`, `fromba`, `toba`, `value` (MW).

To get net imports for a BA, you need two queries:
1. `facets[toba][]={ba_code}` gives flows INTO the BA (imports)
2. `facets[fromba][]={ba_code}` gives flows OUT of the BA (exports)

Or use the region-level total interchange from the region-data endpoint, which gives the net directly.

### Region Data Request (simpler, gives net interchange directly)

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

**Recommended approach:** Use region-data for demand/generation/total interchange (simpler, one call per BA). Use interchange-data only when you need the BA-pair breakdown (e.g., to see BANC's imports specifically from CAISO vs. from TIDC).

---

## RTO LMP API Reference

### CAISO OASIS

```
Base URL: http://oasis.caiso.com/oasisapi/SingleZip

Query parameters:
  queryname=PRC_INTVL_LMP
  market_run_id=DAM          # DAM (day-ahead) or RTM (real-time)
  node={node_id}             # e.g. MALIN_5_N101
  startdatetime={YYYYMMDDTHH:MM-0000}
  enddatetime={YYYYMMDDTHH:MM-0000}
  version=1

Returns: ZIP containing CSV with columns:
  INTERVALSTARTTIME_GMT, INTERVALENDTIME_GMT, OPR_DT, OPR_HR,
  NODE, LMP_TYPE (LMP/MCC/MCE/MCL), MW, GROUP
  
  LMP_TYPE decomposition:
    LMP = total locational marginal price
    MCC = marginal cost of congestion
    MCE = marginal cost of energy
    MCL = marginal cost of losses

Max query window: 31 days. Chunk longer requests.
Timezone: Results in GMT. Convert to UTC (same).
Auth: None required.
Rate limit: Informal, ~1 req/sec recommended.
```

**Key scheduling point node IDs:**
MALIN_5_N101, NOB_5_N101, PVERDE_5_N101, ELDORADO_5_N101, MEAD_5_N101, SYLMARDC_5_N101

### PJM Data Miner 2

```
Base URL: https://api.pjm.com/api/v1

Endpoint: /rt_hrl_lmps or /da_hrl_lmps
Headers:
  Ocp-Apim-Subscription-Key: {api_key}

Query parameters:
  datetime_beginning_ept={YYYY-MM-DD HH:MM}
  datetime_ending_ept={YYYY-MM-DD HH:MM}
  pnode_id={pnode_id}
  fields=datetime_beginning_ept,pnode_id,pnode_name,
         total_lmp_da,energy_lmp_da,congestion_lmp_da,loss_lmp_da
  format=json
  
Pagination: Returns max 50,000 rows. Use $skip and $top for pagination.
  Response includes `totalRows` in metadata.
Auth: Free API key from dataminer2.pjm.com/register
Rate limit: ~5 req/sec
```

**Key interface pricing point pnode IDs:**
Query the pnode list endpoint filtered by `pnode_type=INTERFACE` to get current IDs for SOUTH, MISO, NYIS, IMO, NEPTUNE, LINDENVFT, HUDSONTP.

### MISO

```
Data portal: https://www.misoenergy.org/markets-and-operations/
  real-time--market-data/market-reports/

LMP data: Published as CSV downloads organized by date.
  Day-ahead: "da_exante_lmp" report
  Real-time: "rt_lmp_5min" or "rt_lmp_final"

File naming: {YYYYMMDD}_da_exante_lmp.csv
Columns: Node, Type, Value, HourEnding (HE01-HE24)
  Type = LMP, MLC (loss), MCC (congestion)

Interface nodes: Filter by node name containing "INTERFACE" 
  or by MISO's published interface node list.
  Key interfaces: MISO.IPMISO (PJM), MISO.ISPMISO (SPP),
                  MISO.ITVA (TVA), MISO.IAECI (AECI)

Auth: None for bulk CSV downloads.
Rate limit: Standard web download throttling.
Challenge: Must download individual daily CSVs and concatenate.
  Consider using GridStatus.io as a cleaner source for MISO LMPs.
```

### SPP

```
Data portal: https://marketplace.spp.org/

LMP data: Published in "LMP by Location" reports.
  Day-ahead and real-time available.

File format: CSV with columns:
  Interval, Pnode, LMP, MLC, MCC
  
Interface nodes: Settlement locations at SPP borders.
  Key interfaces: nodes at MISO, ERCOT (DC ties),
  AECI, and WAPA boundaries.

Auth: None for public market data.
Challenge: SPP's node naming is less standardized than
  CAISO/PJM. Requires manual identification of interface
  settlement locations from SPP's node catalog.
  SPP RTO West expansion (2024) added new western interface nodes.
```

### NYISO (Tier 3)

```
Data portal: https://www.nyiso.com/custom-reports

LMP data: "DAM LBMP" and "HAM LBMP" reports.
Columns: Timestamp, Name, LBMP, Marginal Cost Losses,
         Marginal Cost Congestion

Interface proxy buses:
  PJM: multiple proxy buses (HUDVL, LINDEN, NEPTUNE, etc.)
  ISO-NE: Northport-Norwalk, Cross-Sound Cable
  HQ: Chateauguay
  IESO: multiple Ontario interfaces

Auth: None.
```

### ISO-NE (Tier 3)

```
Web services: https://www.iso-ne.com/isoexpress/web/reports/pricing

LMP data: Published in "Hourly LMPs" reports.
External interface nodes: .I.SALBRYNB345, .I.HQHIGATE120,
  .I.SHOREHAM138 (NYISO interfaces)

Auth: None for public data.
```

### ERCOT (Tier 3)

```
MIS portal: https://www.ercot.com/mp/data-products

DC tie data: "Historical DC Tie Flows" and 
  "DC Tie Scheduled Flow" reports.
  
ERCOT doesn't publish "interface LMPs" the same way other RTOs do.
Instead, use the LMP at the settlement point nearest the DC tie 
as a proxy. DC ties connect to SPP (2 ties) and MISO (1 tie, 
limited capacity).

Auth: Free ERCOT MIS account.
```

---

## Data Quality Considerations

| Issue | Impact | Mitigation |
|-------|--------|------------|
| EIA-930 data has reporting gaps | Missing hours for some BAs | Interpolate gaps < 3 hours; flag longer gaps in data_quality_flag |
| Asymmetric interchange reporting | BA A says it sent 100 MW to BA B, but B says it received 50 MW | Use TI (total interchange) from region-data endpoint, which is the BA's own reported net. Don't try to reconcile BA-pair asymmetries. |
| Transfer limit estimation from max historical import | Underestimates true TTC if path was never fully loaded | Conservative bias (overstates utilization). Acceptable for opportunity sizing. Can refine with OASIS TTC data later. |
| Some BAs have very sparse EIA-930 data | Small BAs may report inconsistently | Flag with data_quality_flag = 'sparse' if < 7000 hours have data in a year. Exclude from rankings or show with caveat. |
| Heat wave spikes can push imports above estimated TL | Utilization > 1.0 in some hours | Allow values > 1.0 in the data (don't clip). This actually strengthens the congestion signal. Only clip for duration curve display. |
| **CAISO OASIS query window limit** | OASIS limits single queries to 25 days | Chunk requests into 25-day windows and concatenate results. Handle timezone alignment (OASIS returns Pacific time). |
| **PJM Data Miner pagination** | Large result sets are paginated | Handle pagination in client; PJM returns `totalRows` in response metadata. Rate limit: ~5 req/sec recommended. |
| **MISO data format changes** | MISO has changed CSV column layouts over time | Version-check column headers on ingest; log warnings if schema drift detected. Historical data before 2019 may have different formats. |
| **SPP market expansion** | SPP RTO West (2024) added new interface nodes | Some interface nodes have < 1 year of history. Flag these BAs with shorter LMP coverage in `hours_with_lmp_data`. |
| **Dual-RTO border BAs** | TVA, LGEE, and a few others border two RTOs | Default to primary RTO neighbor from ba_interface_map. Future refinement: use the RTO with the larger import flow for each hour. |
| **LMP decomposition availability** | Not all RTOs publish congestion component separately | CAISO, PJM, MISO all publish energy/congestion/loss decomposition. SPP publishes MCC (marginal congestion component). ERCOT structure is different (no congestion component at DC ties). Fall back to total LMP where decomposition unavailable. |
| **Day-ahead vs real-time LMP** | DA and RT prices can diverge significantly | Default to DA LMP for consistency (more stable, fewer data quality issues). Store `market_type` in InterfaceLMP to enable RT analysis later. |

---

## Session Planning for Claude Code

### Session 1: Foundation
```
1. Read this plan document
2. cd /Users/mcgeesmini/grid-constraint-classifier
3. Create models/congestion.py with four models (BA, InterfaceLMP, BAHourlyData, CongestionScore)
4. Run alembic migration
5. Create services/congestion/eia_client.py
6. Create data/reference/ba_interface_map.json (from xlsx)
7. Create services/congestion/ingestion.py (seed BA reference data)
8. Test: seed BAs, verify 61 rows in balancing_authorities
```

### Session 2: EIA Data Ingestion
```
1. Read this plan, check Section 5 / session log
2. Build CLI command: ingest-eia
3. Test with single BA (BANC) for one month
4. Verify data in ba_hourly_data
5. Run estimate-transfer-limits
6. Backfill all BAs for 2024
7. Spot-check: BPAT should be net exporter, BANC net importer
```

### Session 3: Congestion Calculator + API
```
1. Read this plan, check progress
2. Build services/congestion/calculator.py
3. Compute annual scores for all BAs (no LMP)
4. Build routes/congestion.py with /scores and /duration-curve endpoints
5. Test endpoints, validate against expected patterns
6. Commit and push
```

### Session 4: LMP Client Framework + Tier 1 (CAISO, PJM)
```
1. Build services/congestion/lmp/base.py (abstract client + registry)
2. Build services/congestion/lmp/caiso.py (OASIS scheduling point LMPs)
3. Build services/congestion/lmp/pjm.py (Data Miner 2 interface LMPs)
4. Test both clients independently: fetch 1 week of data, verify schema
5. Backfill all CAISO + PJM interface LMPs for 2024 into interface_lmps table
6. Map Tier 1 BAs to LMP series, update ba_hourly_data
7. Spot-check: BANC has CAISO MALIN LMP, SOCO has PJM SOUTH LMP
```

### Session 5: Tier 2 (MISO, SPP)
```
1. Build services/congestion/lmp/miso.py (market reports CSV parsing)
2. Build services/congestion/lmp/spp.py (market data CSV parsing)
3. Test both clients: fetch 1 week, verify schema
4. Backfill MISO + SPP interface LMPs for 2024
5. Map Tier 2 BAs to LMP series
6. Spot-check: TVA has MISO interface LMP, PSCO has SPP interface LMP
7. Handle dual-RTO BAs (e.g., TVA borders both PJM and MISO): use primary neighbor
```

### Session 6: Baselines + Full Economic Scoring
```
1. Compute regional baseline LMPs for each RTO (system avg or hub)
2. Recompute congestion_opportunity_score for all BAs with economics
3. Compute monthly scores (732 rows)
4. Validate rankings, seasonal patterns, economic plausibility
5. Build Tier 3 clients if time permits (NYISO, ISO-NE, ERCOT)
6. Commit and push
```

### Session 7+: Dashboard
```
1. Obtain BA boundary GeoJSON
2. Build CongestionMap.vue choropleth
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

Full mapping of all 61 BAs is in `ba_interface_map.xlsx` / `ba_interface_map.json`.

---

## Update Rules for grid-dashboard-reference.md

When this workstream starts, add to Section 11 (Work Queue):

```markdown
**Import Congestion workstream** (independent):

| Step | Item | Depends On | Status |
|------|------|------------|--------|
| IC-0 | Foundation (EIA client, models, BA reference data) | -- | NOT STARTED |
| IC-1 | Congestion calculation (scores, API endpoints) | IC-0 | NOT STARTED |
| IC-2a | Tier 1 LMP integration (CAISO, PJM) | IC-1 | NOT STARTED |
| IC-2b | Tier 2 LMP integration (MISO, SPP) | IC-2a | NOT STARTED |
| IC-2c | Tier 3 LMP + baselines + full scoring (NYISO, ISO-NE, ERCOT) | IC-2b | NOT STARTED |
| IC-3 | Dashboard visualization (choropleth, drill-down) | IC-1 + Leaflet | NOT STARTED |
```

Add to Section 13 (External Resources):

```markdown
- EIA API v2: https://api.eia.gov/v2/
- EIA API docs: https://www.eia.gov/opendata/documentation.php
- EIA Grid Monitor: https://www.eia.gov/electricity/gridmonitor/
- CAISO OASIS: http://oasis.caiso.com/
- PJM Data Miner 2: https://dataminer2.pjm.com/
- MISO Market Reports: https://www.misoenergy.org/markets-and-operations/real-time--market-data/market-reports/
- SPP Market Data: https://marketplace.spp.org/
- NYISO OASIS: https://www.nyiso.com/oasis
- ISO-NE Web Services: https://www.iso-ne.com/isoexpress/
- ERCOT MIS: https://www.ercot.com/mp/data-products
- GridStatus.io: https://www.gridstatus.io/
```
