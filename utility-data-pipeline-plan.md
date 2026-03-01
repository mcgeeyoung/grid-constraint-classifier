# Utility Regulatory Filing Data Pipeline: Implementation Plan

## Project Overview

Build a system that systematically discovers, retrieves, parses, and structures data from utility regulatory filings (IRPs, distribution plans, hosting capacity analyses, load forecasts, etc.) across every US utility. The goal is to create a usable dataset of grid constraints, load growth forecasts, and resource needs that WattCarbon can use to identify high-value locations for capacity swaps and DER deployment.

This is a large project. The plan is structured in phases so you can ship value incrementally rather than trying to boil the ocean.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Source Discovery Layer                    │
│  (Registry of utilities, PUCs, docket systems, open data)    │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼──────────┐  ┌────────────────▼──────────────┐
│   Structured Data APIs   │  │   Unstructured Filing Scrapers │
│  (EIA, HIFLD, OEDI,     │  │  (PUC docket systems, utility  │
│   hosting capacity APIs) │  │   IRP sites, PDF attachments)  │
└──────────────┬──────────┘  └────────────────┬──────────────┘
               │                              │
               └──────────────┬───────────────┘
                              │
               ┌──────────────▼──────────────┐
               │      Document Store          │
               │  (S3/GCS: raw PDFs, Excel,   │
               │   HTML snapshots, metadata)  │
               └──────────────┬──────────────┘
                              │
               ┌──────────────▼──────────────┐
               │     Extraction & Parsing     │
               │  (PDF→text, table extraction,│
               │   LLM-assisted structuring)  │
               └──────────────┬──────────────┘
                              │
               ┌──────────────▼──────────────┐
               │    Structured Data Store     │
               │  (Postgres: utilities, filings│
               │   constraints, forecasts)    │
               └──────────────┬──────────────┘
                              │
               ┌──────────────▼──────────────┐
               │      API / Query Layer       │
               │  (REST API + spatial queries) │
               └──────────────────────────────┘
```

---

## Phase 0: Foundation — Utility Registry & Structured Federal Data

**Goal:** Build a comprehensive registry of every US utility and pull in all the structured data that's already available from federal sources. This gives you the skeleton that everything else hangs on.

### 0.1 Utility Registry (EIA Form 861)

EIA publishes annual data on every US electric utility. This is your master list.

```
Source: https://www.eia.gov/electricity/data/eia861/
Format: ZIP of Excel files, updated annually
Key files:
  - Service_Territory_{year}.xlsx (utility → county/state mapping)
  - Sales_Ult_Cust_{year}.xlsx (customer counts, sales by sector)
  - Utility_Data_{year}.xlsx (utility name, ID, type, state)
```

**Implementation:**
- Download and parse the latest EIA-861 dataset
- Build a `utilities` table: `eia_utility_id`, `name`, `state`, `type` (IOU/coop/muni/federal), `parent_company`, `service_territory_counties`
- Cross-reference with HIFLD utility boundaries (GIS shapefiles): https://hifld-geoplatform.opendata.arcgis.com/datasets/electric-retail-service-territories
- This gives you ~3,200 utilities with geographic boundaries

### 0.2 State PUC Registry

Map each utility to its regulatory body. IOUs are regulated by state PUCs; coops and munis generally are not (but some states require IRP filings from them too).

```
Build a `regulators` table:
  - state
  - puc_name (e.g., "California Public Utilities Commission")
  - puc_website
  - efiling_system_url
  - efiling_system_type (enum: custom, eService, eFilings, etc.)
  - api_available (boolean)
  - notes
```

There are ~50 state PUCs plus DC and some territorial regulators. This table is manually curated but only needs to be done once. You can start from NARUC's directory: https://www.naruc.org/about-naruc/regulatory-commissions/

### 0.3 Federal Structured Datasets

Pull in everything that's already machine-readable:

| Source | Data | Format | URL |
|--------|------|--------|-----|
| EIA-861 | Utility territories, customers, sales | Excel | eia.gov/electricity/data/eia861 |
| EIA-860 | Generator inventory (capacity, fuel, location) | Excel | eia.gov/electricity/data/eia860 |
| EIA-923 | Generation and fuel consumption | Excel | eia.gov/electricity/data/eia923 |
| EIA-930 | Hourly grid demand by BA | API | api.eia.gov |
| FERC 714 | Annual load forecasts by planning area | Excel/CSV | ferc.gov/industries-data |
| OEDI | DOE Open Energy Data Initiative | Various | data.openei.org |
| GridStatus.io | ISO-level real-time + historical data | API | gridstatus.io |
| NREL ATB | Technology cost projections | Excel/CSV | atb.nrel.gov |
| EPA eGRID | Emissions data by plant/BA/state | Excel | epa.gov/egrid |

**Implementation:**
- Write individual scrapers/parsers for each source (most are stable URLs with predictable file naming)
- Load into Postgres tables with foreign keys to the utility registry
- Set up scheduled jobs to check for annual updates

### 0.4 Data Model (Postgres)

```sql
-- Core registry
CREATE TABLE utilities (
    id SERIAL PRIMARY KEY,
    eia_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    state TEXT,
    utility_type TEXT, -- IOU, cooperative, municipal, federal
    parent_company TEXT,
    regulator_id INTEGER REFERENCES regulators(id),
    geometry GEOMETRY(MultiPolygon, 4326) -- service territory
);

CREATE TABLE regulators (
    id SERIAL PRIMARY KEY,
    state TEXT,
    name TEXT,
    website TEXT,
    efiling_url TEXT,
    efiling_type TEXT
);

-- Filing tracking
CREATE TABLE filings (
    id SERIAL PRIMARY KEY,
    utility_id INTEGER REFERENCES utilities(id),
    regulator_id INTEGER REFERENCES regulators(id),
    docket_number TEXT,
    filing_type TEXT, -- IRP, DRP, GNA, rate_case, hosting_capacity, etc.
    title TEXT,
    filed_date DATE,
    source_url TEXT,
    raw_document_path TEXT, -- S3/GCS path to original
    status TEXT, -- discovered, downloaded, parsed, structured, reviewed
    metadata JSONB
);

CREATE TABLE filing_documents (
    id SERIAL PRIMARY KEY,
    filing_id INTEGER REFERENCES filings(id),
    document_type TEXT, -- main_filing, appendix, testimony, data_request, etc.
    filename TEXT,
    mime_type TEXT,
    raw_path TEXT,
    extracted_text TEXT,
    parsed_data JSONB,
    status TEXT
);

-- Extracted structured data
CREATE TABLE grid_constraints (
    id SERIAL PRIMARY KEY,
    utility_id INTEGER REFERENCES utilities(id),
    filing_id INTEGER REFERENCES filings(id),
    constraint_type TEXT, -- thermal, voltage, capacity, reliability
    location_type TEXT, -- substation, feeder, circuit, zone, planning_area
    location_name TEXT,
    location_geometry GEOMETRY(Point, 4326),
    current_capacity_mw NUMERIC,
    forecasted_load_mw NUMERIC,
    constraint_year INTEGER,
    headroom_mw NUMERIC,
    notes TEXT,
    raw_source_reference TEXT, -- page/table in source doc
    confidence TEXT -- high, medium, low
);

CREATE TABLE load_forecasts (
    id SERIAL PRIMARY KEY,
    utility_id INTEGER REFERENCES utilities(id),
    filing_id INTEGER REFERENCES filings(id),
    forecast_year INTEGER,
    area_name TEXT,
    area_type TEXT, -- system, zone, substation
    peak_demand_mw NUMERIC,
    energy_gwh NUMERIC,
    growth_rate_pct NUMERIC,
    scenario TEXT -- base, high, low
);

CREATE TABLE resource_needs (
    id SERIAL PRIMARY KEY,
    utility_id INTEGER REFERENCES utilities(id),
    filing_id INTEGER REFERENCES filings(id),
    need_type TEXT, -- capacity, energy, flexibility, reliability
    need_mw NUMERIC,
    need_year INTEGER,
    location_type TEXT,
    location_name TEXT,
    eligible_resource_types TEXT[], -- solar, storage, DR, EE, etc.
    notes TEXT
);
```

---

## Phase 1: Hosting Capacity Data (Structured, High Value)

**Goal:** Many large utilities now publish hosting capacity maps with downloadable data. This is the lowest-hanging fruit because it's already structured and directly relevant to DER siting.

### 1.1 Hosting Capacity Map Inventory

The following utilities publish hosting capacity data in machine-readable formats. This list is not exhaustive but covers the largest ones:

**California (CPUC-mandated, most mature):**
- PG&E: Integration Capacity Analysis (ICA) maps, downloadable as CSV/GIS
- SCE: DER Integration maps
- SDG&E: Integration Capacity Analysis

**Other states with hosting capacity requirements:**
- National Grid (MA, NY)
- Eversource (MA, CT, NH)
- ConEd (NY)
- PSEG (NJ)
- ComEd (IL)
- Xcel Energy (MN, CO)
- Duke Energy (NC, SC) — GridFWD platform
- Dominion Energy (VA)
- DTE Energy (MI)
- Consumers Energy (MI)
- Hawaiian Electric

**Implementation:**
- Build a `hosting_capacity_sources` table mapping each utility to its data portal URL, data format, and update frequency
- Write per-utility scrapers (these are mostly GIS downloads or API endpoints, but each is different)
- Normalize into a common schema:

```sql
CREATE TABLE hosting_capacity (
    id SERIAL PRIMARY KEY,
    utility_id INTEGER REFERENCES utilities(id),
    feeder_id TEXT,
    substation_name TEXT,
    geometry GEOMETRY, -- line or point
    generation_capacity_kw NUMERIC, -- how much gen can be added
    load_capacity_kw NUMERIC, -- how much load can be added
    thermal_limit_kw NUMERIC,
    voltage_limit_kw NUMERIC,
    protection_limit_kw NUMERIC,
    last_updated DATE,
    source_url TEXT
);
```

### 1.2 DSIRE + Interconnection Queue Data

Complement hosting capacity with:
- DSIRE database (dsireusa.org) for state-level DER policies and incentives
- Interconnection queue data (many utilities publish this; LBNL also aggregates it)

---

## Phase 2: State PUC Docket Scrapers (Priority States)

**Goal:** Build scrapers for the PUC filing systems in your highest-priority states to automatically discover and download IRP and distribution planning filings.

### 2.1 Priority State Ranking

Rank states by WattCarbon relevance (current partnerships, market opportunity, data availability):

**Tier 1 (build first):**
1. California (CPUC) — most mature, richest data, current partnerships
2. Virginia (SCC) — Dominion partnership
3. North Carolina (NCUC) — Duke partnership
4. New York (NYPSC) — large market, good data access
5. California municipal (SMUD, LADWP) — SMUD partnership

**Tier 2:**
6. Massachusetts (DPU)
7. Colorado (PUC)
8. Minnesota (PUC)
9. Illinois (ICC)
10. New Jersey (BPU)

**Tier 3 (scale later):**
- Remaining states with active DER/IRP proceedings

### 2.2 PUC Scraper Architecture

Each state PUC has a different eFiling system, but they share common patterns. Build a modular scraper framework:

```python
# Pseudocode for the scraper framework

class PUCScraper:
    """Base class for state PUC scrapers."""

    def __init__(self, state: str, config: dict):
        self.state = state
        self.config = config

    def search_dockets(self, utility_name: str = None,
                       filing_type: str = None,
                       date_range: tuple = None) -> list[DocketResult]:
        """Search for relevant dockets/proceedings."""
        raise NotImplementedError

    def list_filings(self, docket_number: str) -> list[FilingResult]:
        """List all filings within a docket."""
        raise NotImplementedError

    def download_document(self, filing_id: str,
                          dest_path: str) -> DocumentResult:
        """Download a specific filing document."""
        raise NotImplementedError


class CPUCScraper(PUCScraper):
    """
    California PUC eFiling system.
    Base URL: https://apps.cpuc.ca.gov/apex/f?p=401
    Has a searchable interface but no public API.
    Key docket types:
      - R. (Rulemaking) — e.g., R.14-08-013 (DRP)
      - A. (Application) — e.g., utility rate cases, IRP applications
      - I. (Investigation)
    """
    pass


class VASCC_Scraper(PUCScraper):
    """
    Virginia State Corporation Commission.
    Base URL: https://scc.virginia.gov/pages/Case-Information
    """
    pass

# ... etc for each state
```

### 2.3 Docket Monitoring

Rather than scraping everything, focus on specific docket types:

| Filing Type | What It Contains | Priority |
|-------------|-----------------|----------|
| Integrated Resource Plan (IRP) | System-level load forecasts, resource needs, capacity shortfalls | High |
| Distribution Resource Plan (DRP) / Grid Needs Assessment (GNA) | Circuit-level constraints, DER hosting needs | Very High |
| Rate Case (GRC) | Load forecasts, capital plans, demand-side budgets | Medium |
| Demand Response / EE Program Filings | Program designs, deemed savings, avoided costs | Medium |
| Interconnection Proceedings | Queue data, upgrade costs, system limits | Medium |
| Resource Adequacy Filings | Qualifying capacity, NQC values, RA requirements | High |

**Implementation:**
- For each priority state, identify the active docket numbers for each filing type
- Set up a docket watchlist table and a cron job that checks for new filings in watched dockets
- Download new documents to cloud storage
- Tag documents with metadata (utility, filing type, docket, date)

### 2.4 Known Docket System Patterns

Here's what you're dealing with for each Tier 1 state:

**California (CPUC):**
- System: Custom Oracle APEX app
- Search: Full-text and by proceeding number
- Key active proceedings: R.21-06-017 (DER), R.20-05-003 (IRP), A.22-xx-xxx (utility GRCs)
- Also: CPUC publishes structured data via its "Data & Reports" page and the CPUC Data Portal
- Grid Needs Assessment data: Published by each IOU as part of DRP, available as Excel/CSV

**Virginia (SCC):**
- System: Custom web app
- Search: By case number, party name, or keyword
- Key filings: Dominion IRP (filed every 3 years, most recent PUR-2024-00063 or similar)

**North Carolina (NCUC):**
- System: Custom eFiling portal
- Duke Energy IRP: Filed every 2 years, Docket E-100 Sub xxx
- Carbon Plan proceedings

**New York (NYPSC):**
- System: Document & Matter Management System (DMM)
- URL: documents.dps.ny.gov
- Relatively well-organized; matters searchable by keyword/utility
- Key: REV proceedings, utility rate cases, DER-related orders

**SMUD:**
- Not regulated by CPUC (municipal utility)
- Board agendas and reports: smud.org
- IRP and resource plans published directly
- More straightforward to scrape since it's one website

---

## Phase 3: Document Parsing & LLM-Assisted Extraction

**Goal:** Turn raw PDFs and Excel files into structured data.

### 3.1 Document Triage Pipeline

Not every document in a docket is worth parsing. Build a triage step:

```
Raw Document → Classify (filing type, relevance) → Route

Routes:
  1. Excel/CSV attachments → Direct parsing (pandas, openpyxl)
  2. Short PDFs (<20 pages) with tables → Table extraction + LLM
  3. Long narrative PDFs (testimony, reports) → Text extraction + LLM summarization
  4. Irrelevant (procedural motions, etc.) → Skip
```

### 3.2 Table Extraction

Most of the valuable quantitative data lives in tables within PDFs and Excel attachments. Use a multi-tool approach:

**Tools:**
- `camelot-py` or `tabula-py` for PDF table extraction
- `pdfplumber` as a fallback for complex table layouts
- `openpyxl` / `pandas` for Excel files
- `pytesseract` + `pdf2image` for scanned documents (last resort)

**Implementation:**
```python
class DocumentParser:
    def extract_tables(self, doc_path: str) -> list[DataFrame]:
        """Extract all tables from a document."""
        if doc_path.endswith('.xlsx') or doc_path.endswith('.xls'):
            return self._parse_excel(doc_path)
        elif doc_path.endswith('.pdf'):
            return self._parse_pdf_tables(doc_path)

    def _parse_pdf_tables(self, pdf_path: str) -> list[DataFrame]:
        # Try camelot first (best for well-structured tables)
        tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
        if not tables:
            tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
        # Fall back to pdfplumber for complex layouts
        if not tables:
            tables = self._pdfplumber_extract(pdf_path)
        return tables
```

### 3.3 LLM-Assisted Structuring

For narrative documents and tables that resist automated parsing, use Claude via the API to extract structured data. This is where the pipeline gets its real leverage.

**Key extraction tasks:**

1. **Load Forecast Extraction:** Given an IRP chapter on load forecasting, extract the forecast table (year, peak MW, energy GWh, growth rate) into structured JSON.

2. **Constraint Identification:** Given a Grid Needs Assessment, extract each identified constraint (location, type, magnitude, year, proposed solution).

3. **Resource Need Extraction:** Given an IRP resource plan chapter, extract what the utility says it needs (MW of capacity by year, eligible resource types, preferred locations).

**Implementation pattern:**
```python
async def extract_with_llm(document_text: str,
                           extraction_type: str,
                           utility_name: str) -> dict:
    """
    Use Claude to extract structured data from document text.
    """
    prompts = {
        "load_forecast": """
            Extract the load forecast data from this utility filing.
            Return JSON with this structure:
            {
                "utility": "...",
                "forecast_type": "peak_demand|energy|both",
                "base_year": YYYY,
                "scenarios": [
                    {
                        "name": "base|high|low",
                        "data": [
                            {"year": YYYY, "peak_mw": N, "energy_gwh": N,
                             "growth_rate_pct": N}
                        ]
                    }
                ],
                "notes": "any caveats or methodology notes"
            }
        """,
        "grid_constraint": """
            Extract grid constraints from this distribution planning document.
            Return JSON with this structure:
            {
                "constraints": [
                    {
                        "location_name": "substation or feeder name",
                        "location_type": "substation|feeder|circuit|zone",
                        "constraint_type": "thermal|voltage|capacity|protection",
                        "current_capacity_mw": N,
                        "forecasted_load_mw": N,
                        "year_of_constraint": YYYY,
                        "proposed_solution": "description",
                        "proposed_solution_cost": N,
                        "der_eligible": true|false,
                        "notes": "..."
                    }
                ]
            }
        """,
        # ... more extraction types
    }

    response = await anthropic.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system="You are a utility regulatory analyst. Extract structured "
               "data from utility filings. Be precise about numbers and "
               "units. If data is ambiguous, note it. Only extract what "
               "is explicitly stated in the document.",
        messages=[{
            "role": "user",
            "content": f"Utility: {utility_name}\n\n"
                       f"Document text:\n{document_text}\n\n"
                       f"{prompts[extraction_type]}"
        }]
    )
    return json.loads(response.content[0].text)
```

### 3.4 Human-in-the-Loop Review

LLM extraction will not be perfect, especially for complex tables and edge cases. Build a review queue:

- Flag all LLM-extracted data with a `confidence` score
- Low-confidence extractions go into a review queue
- Build a simple web UI (or even a spreadsheet workflow) for reviewing and correcting extractions
- Corrections feed back as examples for improved prompts

---

## Phase 4: Scaling to National Coverage

### 4.1 FERC-Jurisdictional Data

FERC's eLibrary (elibrary.ferc.gov) contains filings from all FERC-jurisdictional utilities. This includes:
- FERC Form 714 (annual load data for all planning areas)
- Transmission planning studies
- Generator interconnection studies
- Market reports from ISOs/RTOs

FERC eLibrary has a search API and relatively consistent document formats.

### 4.2 ISO/RTO Data

Each ISO/RTO publishes substantial planning data:

| ISO/RTO | Key Data | Access |
|---------|----------|--------|
| CAISO | Transmission Plan, local capacity requirements | caiso.com/planning |
| PJM | Regional Transmission Expansion Plan, load forecast | pjm.com/planning |
| ERCOT | Long-term system assessment, CDR reports | ercot.com/gridinfo |
| NYISO | Gold Book (load forecast), RNA, CARIS | nyiso.com/planning |
| ISO-NE | Regional System Plan, Forward Capacity Market data | iso-ne.com/system-planning |
| MISO | MTEP (transmission plan), resource adequacy | misoenergy.org/planning |
| SPP | ITP studies, generation interconnection queue | spp.org/engineering |

Many of these have structured data downloads. Build ISO-specific parsers.

### 4.3 Cooperative and Municipal Utilities

The ~900 cooperatives and ~2,000 municipal utilities are trickier:
- Most are not regulated by state PUCs
- Many don't publish IRPs at all
- Some file through their G&T cooperatives (e.g., Basin Electric, Tri-State)
- APPA (American Public Power Association) and NRECA (National Rural Electric Cooperative Association) aggregate some data

For these, rely more heavily on EIA data and selectively target the larger ones that do publish planning documents.

### 4.4 Third-Party Aggregators

Some commercial and nonprofit sources aggregate utility data and may be worth integrating or licensing:

| Source | Data | Cost |
|--------|------|------|
| S&P Global / Platts | Utility filings, IRP data | $$$$ (enterprise) |
| ABB Velocity Suite / Hitachi | Utility data, circuit maps | $$$$ |
| Clean Energy States Alliance | State program data | Free/membership |
| RMI Utility Transition Hub | IRP tracking, clean energy commitments | Free |
| GridLab | IRP analysis and data | Free |
| LBNL Electricity Markets & Policy | Utility-scale solar/wind cost data, interconnection | Free |
| Catalyst Cooperative (PUDL) | EIA + FERC data cleaned and integrated | Free/open source |

**Catalyst Cooperative's PUDL (Public Utility Data Liberation) project is particularly valuable.** It's an open-source effort to clean and integrate EIA, FERC, and EPA datasets into a unified database. Definitely use this as a starting point rather than reimplementing their work: https://catalyst.coop/pudl/

---

## Phase 5: Ongoing Operations

### 5.1 Update Cadence

| Data Type | Typical Update Frequency | Monitoring Approach |
|-----------|------------------------|---------------------|
| IRPs | Every 2-3 years per utility | Docket watchlist |
| Distribution plans / GNAs | Annual or biennial | Docket watchlist |
| Hosting capacity maps | Quarterly to annual | URL monitoring |
| EIA data | Annual | Scheduled download |
| ISO/RTO planning data | Annual (some quarterly) | URL monitoring |
| Rate case filings | Every 3-5 years per utility | Docket watchlist |

### 5.2 Monitoring & Alerting

```python
# Daily job pseudocode
for source in active_sources:
    new_documents = source.check_for_updates()
    for doc in new_documents:
        store_raw_document(doc)
        classify_document(doc)
        if doc.is_high_priority:
            queue_for_parsing(doc)
            notify_team(doc)
```

### 5.3 Quality Metrics

Track:
- Coverage: % of US load served by utilities in the database
- Freshness: Average age of most recent filing per utility
- Completeness: % of utilities with IRP data, hosting capacity data, etc.
- Extraction accuracy: % of LLM-extracted data confirmed correct in review

---

## Implementation Sequence for Claude Code

Here's the order I'd recommend building this in Claude Code:

### Sprint 1: Foundation (Week 1-2)
1. Set up Postgres schema (the data model above)
2. Ingest EIA-861 utility registry
3. Ingest HIFLD service territory geometries
4. Build the `regulators` reference table (manual, ~50 rows)
5. Ingest PUDL data (Catalyst Cooperative) as baseline

### Sprint 2: Hosting Capacity (Week 3-4)
1. Inventory hosting capacity data sources for top 20 utilities
2. Build scrapers for California IOU hosting capacity data (PG&E, SCE, SDG&E)
3. Build scrapers for Duke, Dominion, National Grid hosting capacity
4. Normalize into common schema

### Sprint 3: Priority PUC Scrapers (Week 5-8)
1. Build CPUC docket scraper
2. Build Virginia SCC scraper
3. Build North Carolina NCUC scraper
4. Build New York DPS/DMM scraper
5. Build SMUD board document scraper
6. Set up docket watchlists for active IRP and DRP proceedings

### Sprint 4: Document Parsing (Week 9-12)
1. Build PDF table extraction pipeline
2. Build Excel parsing pipeline
3. Develop LLM extraction prompts for each data type (load forecasts, constraints, resource needs)
4. Build extraction pipeline with confidence scoring
5. Build review queue (even if it's just a CSV export workflow initially)
6. Process backlog of downloaded documents from Sprint 3

### Sprint 5: ISO/RTO + FERC Data (Week 13-16)
1. Build FERC eLibrary scraper
2. Build ISO/RTO data parsers (start with CAISO, PJM)
3. Ingest FERC 714 load data
4. Integrate ISO planning documents

### Sprint 6: Scale + API (Week 17-20)
1. Add Tier 2 state PUC scrapers
2. Build REST API for querying the dataset
3. Build spatial query support (find constraints near a given location)
4. Build dashboard/reporting for coverage metrics
5. Set up ongoing monitoring and alerting

---

## Key Technical Decisions

### Language & Framework
- **Python** for scrapers and data processing (requests, BeautifulSoup/Playwright, pandas, camelot)
- **Playwright** over Selenium for JavaScript-heavy PUC sites (CPUC's Oracle APEX, etc.)
- **PostgreSQL + PostGIS** for storage (spatial queries are important for the use case)
- **S3 or GCS** for raw document storage
- **FastAPI** for the query API
- **Claude API** (Sonnet for extraction, Haiku for classification/triage)

### Scraping Considerations
- Respect robots.txt and rate limits (these are government sites, don't hammer them)
- Cache aggressively; most filings never change once posted
- Use headless browser (Playwright) for JavaScript-rendered sites; simple HTTP for static sites
- Store raw HTML/PDF alongside extracted data for auditability
- Some PUC sites are fragile and change frequently; build scrapers to fail gracefully and alert on structural changes

### Cost Estimates (Rough)
- Cloud storage: Low (maybe a few TB of PDFs total, ~$50-100/month)
- LLM extraction costs: Moderate (depends on volume; budget ~$500-2000/month for steady-state processing with Sonnet)
- Compute: Low to moderate (scraping is I/O bound; parsing is CPU bound for OCR cases)
- The main cost is engineering time

---

## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| PUC websites change structure, breaking scrapers | High | Monitoring + alerts on scraper failures; modular design so fixes are localized |
| Some filings are scanned PDFs (no text layer) | Medium | OCR pipeline (pytesseract) as fallback; flag for manual review |
| LLM extraction errors on complex tables | Medium | Human review queue; track accuracy metrics; iterative prompt improvement |
| Rate limiting or blocking by PUC sites | Low | Respectful crawling, caching, rotate user agents if needed |
| Data licensing/TOS issues | Low | These are public regulatory filings; check TOS on each site but generally this is public record |
| Scope creep (too many states/utilities at once) | High | Phase 1-2 focus on the 5-10 utilities that matter most for current partnerships |

---

## Open Questions

1. **Build vs. Buy for docket monitoring?** Services like Docket Alarm and Westlaw provide PUC docket monitoring. Worth evaluating whether licensing one of these is cheaper than building and maintaining 50 state scrapers.

2. **PUDL integration depth:** Catalyst Cooperative's PUDL project has already cleaned a lot of EIA and FERC data. Fork and extend, or just use their published data and build on top?

3. **Hosting capacity API partnerships:** Some utilities or their vendors (e.g., Kevala, which does hosting capacity analysis for many utilities) may offer API access. Worth exploring before building custom scrapers.

4. **Data sharing with OpenEAC Alliance:** Could this dataset (or parts of it) be published as an open resource through the Alliance? Would create goodwill and potentially attract contributors.

5. **Geospatial resolution:** For WattCarbon's capacity swap use case, how granular does the constraint data need to be? Substation-level? Feeder-level? This affects which data sources to prioritize.
