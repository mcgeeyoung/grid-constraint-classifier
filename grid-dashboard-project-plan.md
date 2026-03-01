# Plan: Create Grid Dashboard Reference Document

## Context

The grid-constraint-classifier project at `/Users/mcgeesmini/grid-constraint-classifier/` is entering a major multi-phase expansion: infrastructure refactor (PostGIS, vector tiles, MapLibre), utility data pipeline (EIA registry, PUC scrapers, LLM extraction), hosting capacity integration (97 utilities via ArcGIS), and GeoPackage data integration (1.7GB USA.gpkg with 538K power lines, 68K substations, 15K power plants, 7.2M towers). Work will span many sessions with context compression between them.

The user needs a persistent reference document that:
1. Consolidates all plan documents into one scannable source of truth
2. Tracks progress at the sub-step level (not just phase level)
3. Captures learnings and blockers that survive context compression
4. Enables any new session to pick up work mid-stream via a startup checklist

## Deliverable

Create `~/claude/inputs/context/grid-dashboard-reference.md` (~450-500 lines) with these sections:

### Document Structure

| # | Section | Content | Lines |
|---|---------|---------|-------|
| 1 | **Project Overview** | What the project does, WattCarbon connection, four major expansions planned | 8-10 |
| 2 | **Architecture & Tech Stack** | Table: backend (FastAPI/SQLAlchemy/PG16), frontend (Vue3/Vuetify/Leaflet/Pinia), infra (Docker/Heroku), env vars | 20-25 |
| 3 | **Directory Map** | Two-column table mapping every directory to purpose + key files | 25-30 |
| 4 | **Database Schema** | Table of all 18 models with key columns and relationships. Note: no PostGIS yet, all geometry as JSON/floats | 20-25 |
| 4.5 | **API Endpoint Inventory** | Compact table of all existing endpoints: method, path, route module, auth required | 15-20 |
| 5 | **Current State (Sub-Step Tracking)** | Phase + sub-step completion table with status, date, and blocker columns. Granularity at 1.1/1.2/1.3 level, not phase level | 25-35 |
| 6 | **Plan Documents Index** | Cross-reference of all 4 active plan docs with file paths, phase summaries, key decisions. Note phase-4b-plan.md is legacy/ignored | 25-30 |
| 7 | **Data Sources & GeoPackage** | ISOs table, GeoPackage layer inventory with feature counts/columns, and GeoPackage integration sub-plan (schema mapping decisions, dedup strategy, data cleaning, scale decisions, voltage normalization) | 35-45 |
| 8 | **Known Issues & Blockers** | Two sub-sections: (A) Performance issues from redesign plan with fix status; (B) Active blockers with discovered date, severity, and workaround | 15-20 |
| 9 | **Environment, Dev Setup & Deployment Constraints** | Quick-start commands, docker-compose, ports, DB creds, PLUS Heroku constraints: PostGIS plan support, Redis addon, dyno memory, ephemeral filesystem | 15-18 |
| 10 | **Conventions & Patterns** | Model style, route pattern, adapter pattern, store pattern, normalization pattern, PLUS testing section (framework or lack thereof, how to run) | 18-22 |
| 11 | **Work Queue (by Workstream)** | Organized by parallel workstreams (Infra, HC, Data) instead of linear priority. Each item shows workstream, step, dependency, status | 15-20 |
| 12 | **Session Start Checklist** | Step-by-step protocol for cold-starting a session: read this doc, git log, git status, git branch, check Section 5 for active sub-step, read relevant plan doc section | 10-12 |
| 13 | **External Resources** | Key URLs: DOE Atlas, HIFLD, EIA-861, PUDL, GridStatus, ArcGIS endpoints | 8-10 |
| 14 | **Session Log** | Dated one-liners, newest first. Append-only rolling log | 5+ |

### Key Improvements Over Original Plan

1. **Sub-step tracking (Section 5):** Track at 1.1/1.2/1.3 granularity with status + blocker columns, not phase-level blocks
2. **Session handoff protocol (Section 12):** Explicit startup checklist so Claude knows how to orient
3. **Active blockers (Section 8B):** Dedicated space for failures/issues that must survive sessions
4. **GeoPackage integration scope (Section 7):** Expanded with schema mapping decisions, dedup against existing GRIP/HIFLD data, data cleaning notes, scale decisions (do we load 7.2M towers?), voltage unit normalization (V to kV)
5. **Parallel workstreams (Section 11):** Labeled by workstream (Infra/HC/Data) to show what can run concurrently
6. **Deployment constraints (Section 9):** Heroku PostGIS availability, Redis plan, dyno memory, ephemeral FS for GeoPackage
7. **API endpoint inventory (Section 4.5):** All existing endpoints in one table
8. **Testing conventions (Section 10):** Document test framework or absence thereof
9. **Line target increased:** 450-500 lines to accommodate the additional sections
10. **Auto-update trigger (CLAUDE.md):** Tied to working directory `/Users/mcgeesmini/grid-constraint-classifier/`, not session intent

### Source Documents

All content synthesized from:
- `grid-infrastructure-redesign-plan.md` (dashboard refactor, 7 phases)
- `grid-value-extraction-guide.md` (PDF extraction pipeline)
- `utility-data-pipeline-plan.md` (national utility data pipeline, 6 phases)
- `docs/hosting-capacity-integration-plan.md` (hosting capacity, 8 phases, 97 utilities)
- `docs/hosting-capacity-detailed-phase-plans.md` (implementation-ready phase details)
- Codebase exploration results (directory structure, models, routes, frontend components)

Note: `docs/phase-4b-plan.md` is legacy and should be ignored.

### Auto-Update Rules (for CLAUDE.md)

Add to CLAUDE.md:
```
## Grid Dashboard Project

**Trigger:** When the working directory is `/Users/mcgeesmini/grid-constraint-classifier/`, read `~/claude/inputs/context/grid-dashboard-reference.md` at session start.

**Update rules:**
1. After completing any sub-step: update Section 5 status and Section 14 (Session Log)
2. When a blocker is discovered: add to Section 8B (Active Blockers)
3. When a blocker is resolved: move from Section 8B to Section 14 with resolution note
4. When priorities shift: update Section 11 (Work Queue)
5. Before context compaction: save all unsaved learnings to Section 14
```

### Work Queue by Workstream (Section 11 content)

**Infra workstream** (sequential):

| Step | Item | Depends On | Status |
|------|------|------------|--------|
| I-0 | Phase 0: Quick wins (geometry separation, indexes, pagination, workers) | -- | NOT STARTED |
| I-1 | Phase 1: PostGIS migration (GeoAlchemy2, geometry columns, spatial indexes) | I-0 | NOT STARTED |
| I-1.5 | GeoPackage integration: Load USA.gpkg priority layers into PostGIS | I-1 | NOT STARTED |
| I-2 | Phase 2: MVT tiles + MapLibre GL JS | I-1 | NOT STARTED |
| I-3 | Phase 3: Redis caching | I-0 | NOT STARTED |
| I-4 | Phase 4: Server-side clustering | I-1 + I-2 | NOT STARTED |
| I-5 | Phase 5: Transmission lines + linear features | I-1 + I-2 | NOT STARTED |
| I-6 | Phase 6: Time-series at scale | -- | NOT STARTED |
| I-7 | Phase 7: Multi-ISO support | All above | NOT STARTED |

**Hosting Capacity workstream** (independent, can run in parallel with Infra):

| Step | Item | Depends On | Status |
|------|------|------------|--------|
| HC-1 | Phase 1: DB schema (Utility, HostingCapacityRecord models) | -- | NOT STARTED |
| HC-2 | Phase 2: ArcGIS REST client library | HC-1 | NOT STARTED |
| HC-3 | Phase 3: Utility adapter + YAML config system | HC-2 | NOT STARTED |
| HC-4 | Phase 4: Normalization pipeline | HC-3 | NOT STARTED |
| HC-5 | Phase 5: CLI ingestion command | HC-4 | NOT STARTED |
| HC-6 | Phase 6: API endpoints | HC-5 | NOT STARTED |
| HC-7 | Phase 7: Frontend map layer | HC-6 + I-2 (needs MapLibre or Leaflet) | NOT STARTED |
| HC-8 | Phase 8: Utility rollout waves (7 waves) | HC-7 | NOT STARTED |

**Data Pipeline workstream** (independent, can run in parallel):

| Step | Item | Depends On | Status |
|------|------|------------|--------|
| DP-0 | Phase 0: Foundation (EIA-861 registry, PUC registry, federal data, Postgres schema) | -- | NOT STARTED |
| DP-1 | Phase 1: Hosting capacity from structured sources | DP-0 | NOT STARTED |
| DP-2 | Phase 2: State PUC docket scrapers (5 tier-1 states) | DP-0 | NOT STARTED |
| DP-3 | Phase 3: Document parsing + LLM extraction | DP-2 | NOT STARTED |
| DP-4 | Phase 4: National coverage scaling | DP-3 | NOT STARTED |
| DP-5 | Phase 5: Ongoing operations | DP-4 | NOT STARTED |

### GeoPackage Integration Sub-Plan (Section 7 content)

Source: `Rfa5yiDWUQ/USA.gpkg` (1.7GB, SRS 4326, OpenStreetMap-derived)

**Layer inventory:**

| Layer | Features | Key Columns | Dashboard Use |
|-------|----------|-------------|---------------|
| power_line | 538,500 | name, operator, max_voltage (volts), voltages, circuits, cables, location | Transmission line rendering, voltage filtering |
| power_substation_polygon | 68,851 | name, substation_type, operator, voltages, max_voltage | Substation boundaries, voltage overlay |
| power_plant | 15,387 | name, operator, source, method, output (watts) | Generation facility layer |
| power_generator_point | 135,000 | name, operator, source, output, method | Individual generator locations |
| power_generator_polygon | 1,642,587 | (same schema) | Solar/wind farm boundaries |
| power_tower | 7,216,175 | ref, type, operator, transition | Tower locations (very dense) |
| power_transformer | 60,998 | (basic) | Transformer locations |
| power_switch | 68,858 | (basic) | Switch gear locations |
| power_compensator | 4,899 | (basic) | Reactive compensation |

Non-power layers (telecom, pipeline, petroleum, water): available but lower priority.

**Open decisions to resolve before implementation:**

| Decision | Options | Notes |
|----------|---------|-------|
| Schema mapping for power_line | (A) Load into existing `transmission_lines` table (add missing columns) or (B) New `gpkg_power_lines` table | Existing table has `geometry_json`, `iso_id` FK, dashboard fields. GeoPackage has different columns (max_voltage in V not kV, operator, circuits). Option B avoids schema conflicts. |
| Schema mapping for substations | (A) Merge with existing `substations` or (B) New `gpkg_substations` table | Existing has GRIP data (PG&E-specific, loading_pct). GeoPackage has 68K from OSM. Different sources, different schema. Likely Option B with spatial join linking. |
| power_tower inclusion | (A) Load all 7.2M or (B) Skip entirely or (C) Load but only serve at zoom 13+ | 7.2M rows is significant DB size. Towers are visually informative for line tracing but very dense. Recommend C. |
| Voltage normalization | GeoPackage uses volts (115000.0), existing app uses kV (115) | Normalize on ingest to kV |
| Output normalization | GeoPackage uses watts, existing app uses MW | Normalize on ingest to MW |
| Data quality filtering | Many NULL name/operator fields in GeoPackage | Accept NULLs, filter in queries. Don't discard features just because OSM metadata is incomplete. |
| Dedup against HIFLD | Existing `transmission_lines` table may have HIFLD-sourced data | Need to assess overlap. GeoPackage (OSM) and HIFLD are different sources with different coverage. May keep both with a `source` column. |

**Priority layers for initial load:** power_line, power_substation_polygon, power_plant (combined ~622K features, manageable). Defer power_tower (7.2M) and power_generator_polygon (1.6M) until MVT tiles are working.

### Session Start Checklist (Section 12 content)

```
1. Read ~/claude/inputs/context/grid-dashboard-reference.md
2. cd /Users/mcgeesmini/grid-constraint-classifier
3. git log --oneline -10  (see recent work)
4. git status  (check for uncommitted changes)
5. git branch  (identify active branch)
6. Check Section 5 for the current active sub-step and any blockers in Section 8B
7. Read the relevant plan document section for the active sub-step
8. If docker needed: docker-compose ps (check if services are running)
```

## Steps

1. Write `~/claude/inputs/context/grid-dashboard-reference.md` with all 14 sections populated from the source documents and codebase exploration
2. Add Grid Dashboard Project section to `~/.claude/CLAUDE.md` with working-directory trigger and update rules
3. Add a line to the Learnings section of `~/.claude/CLAUDE.md` pointing to the new reference doc
4. Verify the document is scannable and complete

## Verification

- Document exists at `~/claude/inputs/context/grid-dashboard-reference.md`
- All 14 sections populated with accurate data from source documents
- Section 5 tracks at sub-step level (1.1, 1.2, 1.3) with status + blocker columns
- Section 7 includes GeoPackage integration sub-plan with open decisions table
- Section 8 has both performance issues (8A) and active blockers (8B) sub-sections
- Section 9 includes Heroku deployment constraints
- Section 11 organized by workstream showing parallelism
- Section 12 has session start checklist
- CLAUDE.md has Grid Dashboard Project section with working-directory trigger
- CLAUDE.md learnings section updated with reference doc path
