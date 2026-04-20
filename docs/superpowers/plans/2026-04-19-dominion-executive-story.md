# Dominion Executive Story Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a narrative-shaped dashboard at `/dominion/` that pitches the Dominion DER pilot to C-suite executives, with a 5k/50k/500k device scale slider tied to real PJM DOM DA congestion data.

**Architecture:** Standalone Vue 3 SPA served from `app/static/dominion_executive/` on the existing `dominion-api` Cloud Run service. Consumes existing admin API endpoints plus one new `/dispatch/congestion-heatmap` endpoint. Map is MapLibre GL with a brand-tinted dark vector style over OpenFreeMap tiles. No database changes.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy · PyYAML · pytest (backend) · Vue 3 (CDN) · MapLibre GL JS (CDN) · Chart.js (CDN) · OpenFreeMap vector tiles · Cloud Run · Cloud SQL Postgres 16.

**Design spec:** `docs/superpowers/specs/2026-04-19-dominion-executive-story-design.md`.

**Working directory:** `/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier` (branch `main`).

**Deployment target:** Cloud Run `dominion-api`, project `wattcarbon-internal`, region `us-central1`.

**Common shell values:**

```bash
REPO="/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier"
PY="$REPO/.venv/bin/python"
DSN='postgresql://appuser:eqgnNxhAQS84qN7PKK1HQCYDjQy9C47b@127.0.0.1:5434/gridclass'
BASE=https://dominion-api-558972293204.us-central1.run.app
PJM_KEY=96e8270ac57341f281c73cfa6498433c
```

Start Cloud SQL Auth Proxy when a task needs it:

```bash
pgrep -f "cloud-sql-proxy wattcarbon-internal:us-central1:dominion-demo-db --port=5434" > /dev/null \
  || (cloud-sql-proxy wattcarbon-internal:us-central1:dominion-demo-db --port=5434 >/tmp/csp.log 2>&1 &)
sleep 3
```

## Global rules

**Branch:** Stay on `main`. Do not run `git checkout`. A prior agent orphaned work by switching branches; every implementer prompt in this plan must repeat the no-checkout rule.

**Scaling semantics per widget** (critical so implementers don't multiply the wrong things):

| Widget | Scaled by `scaleFactor = deviceCount / 6`? | Rationale |
|---|---|---|
| HeaderBar (grid-state) | **No** | Grid congestion is a property of the real grid |
| HeroMap congestion heatmap | **No** | Same reason |
| HeroMap device density layer | **Yes** | More devices = more density |
| CommunityKwhCard | **Yes** | kWh delivered scales with fleet |
| RatepayerValueCard | **Yes** | $ = kWh × rate; kWh scales |
| CommunitiesLeaderboard MW per zone | **Yes** | Per-zone capacity scales |
| CommunitiesLeaderboard perf % | **No** | Percentage doesn't scale |
| EventRibbon (day tiles by tier) | **No** | Grid stresses independent of device count |
| ScaleSlider | Defines the scale factor | n/a |

**Broken API note:** `src/pjm_client.py::query_pnodes()` sends to `/pnodes` which returns 404. The correct PJM endpoint is `/pnode` (singular). Task A1 calls `client.query("pnode", ...)` directly and does NOT go through `query_pnodes()`. Fixing or deprecating that method is out of scope for this plan.

---

## Phase A: Pnode coordinate coverage

### Task A1: HIFLD pnode-coord enrichment script

**Files:**
- Create: `~/claude/outputs/tmp/pnode_coords_enrich.py` (one-off script, outside repo)
- Create: `dominion_dispatch/refdata/pnode_coords_dom_full.json`

- [ ] **Step 1: Write the enrichment script**

Write to `/Users/mcgeesmini/claude/outputs/tmp/pnode_coords_enrich.py`:

```python
"""
One-off: enrich Dominion DOM LOAD pnode list with HIFLD substation coordinates.

1. Pull current DOM pnode list from PJM (`pnode` endpoint, LOAD-type only).
2. Query HIFLD Electric Substations (chadbraden 1/9/2025 vintage) for VA rows.
3. Fuzzy-match by uppercase exact + substring on NAME.
4. Write matches (with source provenance) to pnode_coords_dom_full.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

REPO = Path("/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier")
sys.path.insert(0, str(REPO))

from src.pjm_client import PJMClient

HIFLD_URL = (
    "https://services6.arcgis.com/OO2s4OoyCZkYJ6oE/"
    "arcgis/rest/services/Substations/FeatureServer/0/query"
)
OUT_PATH = REPO / "dominion_dispatch" / "refdata" / "pnode_coords_dom_full.json"


def fetch_dom_pnodes(key: str) -> list[dict]:
    client = PJMClient(key)
    # Fetch all pnodes, filter LOAD + zone DOM client-side.
    # query_pnodes() is broken (sends to /pnodes); use client.query("pnode") directly.
    df = client.query(
        "pnode",
        params={"rowCount": 50000, "row_is_current": "TRUE", "startRow": 1},
    )
    dom_load = df[(df["zone"] == "DOM") & (df["pnode_type"] == "LOAD")].copy()
    return dom_load.to_dict(orient="records")


def fetch_hifld_va() -> list[dict]:
    params = {
        "where": "STATE='VA'",
        "outFields": "NAME,CITY,COUNTY,LATITUDE,LONGITUDE,MAX_VOLT,STATUS",
        "returnGeometry": "false",
        "resultRecordCount": 2000,
        "f": "json",
    }
    r = requests.get(HIFLD_URL, params=params, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    return [f["attributes"] for f in features]


def normalize(s: str) -> str:
    return "".join(c for c in (s or "").upper() if c.isalnum())


def match_pnode_to_hifld(pnode_name: str, hifld_rows: list[dict]) -> dict | None:
    pnorm = normalize(pnode_name)
    if not pnorm:
        return None
    # Exact normalized match first.
    for h in hifld_rows:
        if normalize(h.get("NAME")) == pnorm:
            return h
    # Prefix / substring of length >= 5.
    if len(pnorm) >= 5:
        for h in hifld_rows:
            hnorm = normalize(h.get("NAME"))
            if hnorm and (hnorm.startswith(pnorm[:5]) or pnorm.startswith(hnorm[:5])):
                return h
    return None


def main():
    key = os.environ.get("PJM_SUBSCRIPTION_KEY")
    if not key:
        sys.exit("Set PJM_SUBSCRIPTION_KEY env var")
    print("Fetching DOM LOAD pnodes from PJM...", flush=True)
    pnodes = fetch_dom_pnodes(key)
    print(f"  {len(pnodes)} DOM LOAD pnodes", flush=True)

    print("Fetching HIFLD VA substations...", flush=True)
    hifld = fetch_hifld_va()
    print(f"  {len(hifld)} VA substations", flush=True)

    coords: dict[str, list[float]] = {}
    notes: dict[str, str] = {}
    matched = 0
    for p in pnodes:
        pid = str(p.get("pnode_id"))
        pname = str(p.get("pnode_name") or "")
        h = match_pnode_to_hifld(pname, hifld)
        if h and h.get("LATITUDE") is not None and h.get("LONGITUDE") is not None:
            coords[pid] = [round(float(h["LATITUDE"]), 5), round(float(h["LONGITUDE"]), 5)]
            notes[pid] = f"{pname} -> HIFLD '{h.get('NAME')}' ({h.get('COUNTY')} VA)"
            matched += 1

    out = {
        "_source": (
            "HIFLD Electric Substations (chadbraden 1/9/2025) matched to PJM DOM LOAD "
            "pnodes by normalized name. Fields are [lat, lon]."
        ),
        "_coverage": f"{matched} of {len(pnodes)} DOM LOAD pnodes matched",
        "_match_notes": notes,
        **coords,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUT_PATH}: {matched} matched of {len(pnodes)}", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
cd "$REPO" && PJM_SUBSCRIPTION_KEY=$PJM_KEY "$PY" /Users/mcgeesmini/claude/outputs/tmp/pnode_coords_enrich.py
```

Expected: last line says `Wrote .../pnode_coords_dom_full.json: N matched of M` where N ≥ 50 and M ≈ 1,336. If matched < 50, stop and escalate — the fuzzy matcher is broken and the heatmap will be too sparse.

- [ ] **Step 3: Sanity-check the output**

```bash
"$PY" - <<'PY'
import json, pathlib
p = pathlib.Path("/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier/dominion_dispatch/refdata/pnode_coords_dom_full.json")
d = json.loads(p.read_text())
print("coverage:", d["_coverage"])
# Make sure the 6 enrolled pnodes are in there.
want = ["1348256193", "34886155", "83734355", "123900989", "34886297", "34886435"]
missing = [w for w in want if w not in d]
print("missing enrolled pnodes:", missing)
PY
```

Expected: coverage string reports ≥ 50 matches; `missing enrolled pnodes: []`.

If enrolled pnodes are missing: extend the matcher in Step 1 to also consult the existing `pnode_coords_dom.json` as a fallback, re-run. Do not ship without the 6 enrolled pnodes covered.

- [ ] **Step 4: Commit**

```bash
cd "$REPO"
git add dominion_dispatch/refdata/pnode_coords_dom_full.json
git commit -m "feat(dominion): enrich DOM LOAD pnode coords from HIFLD for exec map"
```

---

## Phase B: Backend heatmap endpoint

### Task B1: Heatmap schemas + endpoint

**Files:**
- Modify: `app/schemas/dominion.py`
- Modify: `app/api/v1/dominion_admin_routes.py`

- [ ] **Step 1: Append schemas to `app/schemas/dominion.py`**

At the bottom of `app/schemas/dominion.py`, append:

```python
# ───────────────────────── admin / exec heatmap ─────────────────────────


class AdminCongestionHeatmapPoint(BaseModel):
    pnode_id: str
    pnode_name: Optional[str] = None
    lat: float
    lon: float
    max_abs_congestion: float
    mean_abs_congestion: float


class AdminCongestionHeatmapResponse(BaseModel):
    operating_date: date
    point_count: int
    points: list[AdminCongestionHeatmapPoint]
```

- [ ] **Step 2: Add coord-map loader at top of `app/api/v1/dominion_admin_routes.py`**

Open `app/api/v1/dominion_admin_routes.py`. Near the top, after the existing imports and any existing module-level constants, add:

```python
# Full DOM LOAD pnode coord coverage for the /dispatch/congestion-heatmap
# endpoint. Loaded once at process start. File is produced by the offline
# HIFLD enrichment script (Task A1).
_FULL_PNODE_COORDS_PATH = (
    Path(__file__).resolve().parents[3]
    / "dominion_dispatch" / "refdata" / "pnode_coords_dom_full.json"
)
_FULL_PNODE_COORDS: dict[str, tuple[float, float]] = {}
if _FULL_PNODE_COORDS_PATH.is_file():
    import json as _json
    _raw = _json.loads(_FULL_PNODE_COORDS_PATH.read_text())
    for k, v in _raw.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            _FULL_PNODE_COORDS[str(k).strip()] = (float(v[0]), float(v[1]))

_HEATMAP_CACHE: dict[date, list[dict]] = {}
```

If `Path` is not yet imported at the top of this file, add `from pathlib import Path` to the imports.

Also extend the existing `from app.schemas.dominion import (...)` block so it imports the two new schemas. Do NOT create a second import block; open the existing parenthesized one and add these two lines to its alphabetical position:

```python
    AdminCongestionHeatmapPoint,
    AdminCongestionHeatmapResponse,
```

After edit the file should have exactly one `from app.schemas.dominion import (` line with all existing admin schema names plus the two new ones.

- [ ] **Step 3: Append endpoint at the bottom of `dominion_admin_routes.py`**

```python
# ───────────────────────── congestion heatmap ─────────────────────────


@router.get(
    "/dispatch/congestion-heatmap",
    response_model=AdminCongestionHeatmapResponse,
)
def dispatch_congestion_heatmap(
    operating_date: Optional[date] = Query(
        default=None,
        description="DA operating day; defaults to latest successful ingest",
    ),
    db: Session = Depends(get_db),
):
    """Per-pnode abs-congestion summary for an operating day, for map heatmap."""
    if operating_date is None:
        latest = _latest_successful_run(db)
        if latest is None:
            raise HTTPException(503, "No successful DA ingest available yet.")
        operating_date = latest.operating_date

    if operating_date in _HEATMAP_CACHE:
        cached = _HEATMAP_CACHE[operating_date]
        return AdminCongestionHeatmapResponse(
            operating_date=operating_date,
            point_count=len(cached),
            points=[AdminCongestionHeatmapPoint(**p) for p in cached],
        )

    from sqlalchemy import func as _f
    rows = db.execute(
        select(
            DominionDaNodeHourly.pnode_id_external,
            _f.max(_f.abs(DominionDaNodeHourly.congestion_price_da)).label("max_abs"),
            _f.avg(_f.abs(DominionDaNodeHourly.congestion_price_da)).label("mean_abs"),
        )
        .join(
            DominionDaIngestionRun,
            DominionDaIngestionRun.id == DominionDaNodeHourly.ingestion_run_id,
        )
        .where(
            DominionDaIngestionRun.operating_date == operating_date,
            DominionDaIngestionRun.status == "success",
            DominionDaNodeHourly.congestion_price_da.isnot(None),
        )
        .group_by(DominionDaNodeHourly.pnode_id_external)
    ).all()

    points: list[dict] = []
    for pid_ext, max_abs, mean_abs in rows:
        coord = _FULL_PNODE_COORDS.get(str(pid_ext))
        if not coord:
            continue
        points.append(
            dict(
                pnode_id=str(pid_ext),
                pnode_name=None,
                lat=coord[0],
                lon=coord[1],
                max_abs_congestion=float(max_abs),
                mean_abs_congestion=float(mean_abs),
            )
        )

    _HEATMAP_CACHE[operating_date] = points
    return AdminCongestionHeatmapResponse(
        operating_date=operating_date,
        point_count=len(points),
        points=[AdminCongestionHeatmapPoint(**p) for p in points],
    )
```

- [ ] **Step 4: Import sanity + existing tests**

```bash
cd "$REPO" && "$PY" -c "from app.main import app; print('routes ok:', sum(1 for r in app.routes if 'congestion-heatmap' in getattr(r, 'path', '')))"
"$PY" -m pytest -q
```

Expected:
- `routes ok: 1`
- `15 passed`

- [ ] **Step 5: Commit**

```bash
cd "$REPO"
git add app/schemas/dominion.py app/api/v1/dominion_admin_routes.py
git commit -m "feat(admin): /dispatch/congestion-heatmap endpoint for exec map"
```

---

### Task B2: Deploy + smoke-test heatmap endpoint

**Files:** none (deploy + verify).

- [ ] **Step 1: Deploy**

```bash
cd "$REPO" && gcloud run deploy dominion-api --source . --region=us-central1 --quiet 2>&1 | tail -5
```

Expected: `Service [dominion-api] revision [dominion-api-NNNNN-xxx] has been deployed and is serving 100 percent of traffic.`

- [ ] **Step 2: Smoke-test the heatmap endpoint**

```bash
BASE=https://dominion-api-558972293204.us-central1.run.app
echo "=== heatmap latest ===" ; curl -sS -w "\nHTTP %{http_code}\n" "$BASE/api/v1/dominion/admin/dispatch/congestion-heatmap" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('date:', d['operating_date'])
print('points:', d['point_count'])
print('sample:', d['points'][:2])
"
```

Expected: HTTP 200, `operating_date` is the latest success run date, `point_count` matches the Task A1 match count (≥ 50), each sample point has real lat/lon/max_abs_congestion.

No commit in this task.

---

## Phase C: Frontend scaffold

### Task C1: Static mount + HTML/CSS shell

**Files:**
- Modify: `app/main.py`
- Create: `app/static/dominion_executive/index.html`
- Create: `app/static/dominion_executive/styles.css`

- [ ] **Step 1: Add static mount in `app/main.py`**

Open `app/main.py`. Near the existing `_DOMINION_ADMIN_DIR` line, add:

```python
_DOMINION_EXEC_DIR = _STATIC_DIR / "dominion_executive"
```

Below the existing admin mount block (after `name="dominion_admin"` block), append:

```python
if _DOMINION_EXEC_DIR.is_dir():
    app.mount(
        "/dominion",
        StaticFiles(directory=str(_DOMINION_EXEC_DIR), html=True),
        name="dominion_executive",
    )
```

- [ ] **Step 2: Write `app/static/dominion_executive/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Virginia DER program · WattCarbon</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Source+Serif+Pro:wght@400;600;700&display=swap" />
    <link rel="stylesheet" href="/static/wc-brand.css" />
    <link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" />
    <link rel="stylesheet" href="styles.css" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <script src="https://unpkg.com/vue@3.4.27/dist/vue.global.prod.js"></script>
  </head>
  <body>
    <div class="wc-brand-header">
      <img class="wc-logomark" src="/static/assets/logos/Symbol_on-dark.png" alt="WattCarbon" />
      <span class="wc-wordmark">WattCarbon</span>
      <span class="wc-sep">·</span>
      <span class="wc-context">Virginia DER program</span>
    </div>
    <main id="app">
      <div class="loading">Loading…</div>
    </main>
    <footer class="exec-footer">
      <span>
        Live simulation at 5,000 Virginia households against real 2026 PJM DOM DA data.
        Slider scales to Dominion IRP targets.
      </span>
      <span class="exec-footer-links">
        <a href="/dominion-admin/">Operations console</a>
        ·
        <a href="/dominion-demo/">Engineering walkthrough</a>
      </span>
    </footer>
    <script type="module" src="app.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Write `app/static/dominion_executive/styles.css`**

```css
/* dominion-executive. Requires /static/wc-brand.css to be loaded first via <link>. */

* { box-sizing: border-box; }

body { margin: 0; min-height: 100vh; display: flex; flex-direction: column; }

main#app {
  flex: 1;
  padding: 1rem 1.5rem;
  display: grid;
  grid-template-areas:
    "hdr    hdr    hdr"
    "map    map    rail"
    "ribbon ribbon ribbon"
    "slider slider slider";
  grid-template-columns: 1fr 1fr 22rem;
  grid-template-rows: auto minmax(28rem, 1fr) auto auto;
  gap: 1rem;
}

.loading { color: var(--muted); padding: 2rem; text-align: center; grid-column: 1 / -1; }

.exec-hdr     { grid-area: hdr; }
.exec-map     { grid-area: map; min-height: 28rem; position: relative; }
.exec-rail    { grid-area: rail; display: grid; grid-template-rows: repeat(3, 1fr); gap: 1rem; }
.exec-ribbon  { grid-area: ribbon; }
.exec-slider  { grid-area: slider; }

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem 1.2rem;
}

.exec-hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.exec-hdr .lead {
  font-family: var(--wc-font-display);
  font-weight: 600;
  color: var(--text-bright);
  font-size: 1.25rem;
}

.exec-hdr .grid-state {
  text-align: right;
}

.exec-hdr .grid-state .h {
  color: var(--muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.exec-hdr .grid-state .v {
  font-family: var(--wc-font-display);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--accent);
}

.kpi .h {
  color: var(--muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.25rem;
}

.kpi .v {
  font-family: var(--wc-font-display);
  font-size: 1.9rem;
  font-weight: 700;
  color: var(--text-bright);
  line-height: 1.1;
}

.kpi .v.honey { color: var(--wc-honeydew); }

.kpi .sub {
  color: var(--wc-dolphin);
  font-size: 0.8rem;
  margin-top: 0.3rem;
}

.kpi .disc {
  color: var(--muted);
  font-size: 0.7rem;
  margin-top: 0.4rem;
}

.leaderboard-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 0.25rem 0;
  cursor: pointer;
}

.leaderboard-row:hover { color: var(--accent); }
.leaderboard-row .name { color: var(--text-bright); font-weight: 600; }
.leaderboard-row .meta { color: var(--wc-dolphin); font-size: 0.8rem; }

.ribbon-strip {
  display: flex;
  gap: 2px;
  margin-top: 0.5rem;
}

.ribbon-strip .cell {
  flex: 1;
  height: 1.1rem;
  background: var(--panel-hi);
  border-radius: 2px;
  cursor: pointer;
}

.ribbon-strip .cell:hover { outline: 1px solid var(--accent); }
.ribbon-strip .cell.opt   { background: rgba(228, 253, 127, 0.45); }
.ribbon-strip .cell.mand  { background: rgba(229, 83, 75, 0.55); }

.slider-stops {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 0.8rem;
  margin-top: 0.75rem;
}

.slider-stop {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.8rem 1rem;
  cursor: pointer;
  transition: border-color 120ms, transform 120ms;
}

.slider-stop:hover { border-color: var(--accent); }

.slider-stop.active {
  border-color: var(--accent);
  background: rgba(11, 212, 255, 0.08);
}

.slider-stop .num {
  font-family: var(--wc-font-display);
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--wc-honeydew);
}

.slider-stop .mw {
  font-weight: 600;
  color: var(--accent);
  margin-top: 0.1rem;
}

.slider-stop .infra {
  color: var(--wc-dolphin);
  font-size: 0.8rem;
  margin-top: 0.3rem;
  line-height: 1.3;
}

.exec-footer {
  padding: 0.9rem 1.5rem 1.2rem;
  color: var(--muted);
  font-size: 0.8rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--border);
}

.exec-footer-links a { color: var(--accent); text-decoration: none; margin-left: 0.25rem; }
.exec-footer-links a:hover { text-decoration: underline; }

.exec-map { border-radius: 12px; overflow: hidden; border: 1px solid var(--border); }
.exec-map .maplibregl-ctrl-attrib { font-size: 0.6rem; background: rgba(0, 35, 44, 0.8); color: var(--muted); }
.exec-map .maplibregl-canvas { outline: none; }
```

- [ ] **Step 4: Smoke-test mount**

```bash
cd "$REPO" && "$PY" -c "from app.main import app; print([r.name for r in app.routes if hasattr(r, 'name') and 'dominion' in (r.name or '')])"
"$PY" -m pytest -q
```

Expected: list includes `'dominion_executive'`, `'dominion_admin'`, `'dominion_demo'`. pytest: `15 passed`.

- [ ] **Step 5: Commit**

```bash
cd "$REPO"
git add app/main.py app/static/dominion_executive/index.html app/static/dominion_executive/styles.css
git commit -m "feat(exec-ui): mount /dominion/ static surface + brand shell"
```

---

### Task C2: `api.js`, `app.js`, scenario state, component stubs

**Files:**
- Create: `app/static/dominion_executive/api.js`
- Create: `app/static/dominion_executive/app.js`
- Create: `app/static/dominion_executive/components/HeaderBar.js`
- Create: `app/static/dominion_executive/components/HeroMap.js`
- Create: `app/static/dominion_executive/components/CommunityKwhCard.js`
- Create: `app/static/dominion_executive/components/RatepayerValueCard.js`
- Create: `app/static/dominion_executive/components/CommunitiesLeaderboard.js`
- Create: `app/static/dominion_executive/components/EventRibbon.js`
- Create: `app/static/dominion_executive/components/ScaleSlider.js`

- [ ] **Step 1: Write `api.js`**

```javascript
// Admin API client, mirrored from /dominion-admin/. Same base, same endpoints.
const DEFAULT_BASE = "/api/v1/dominion/admin";

export function apiBase() {
  if (typeof window !== "undefined" && window.__DOMINION_ADMIN_API_BASE__) {
    return String(window.__DOMINION_ADMIN_API_BASE__).replace(/\/$/, "");
  }
  return DEFAULT_BASE;
}

export async function apiJson(path, opts = {}) {
  const res = await fetch(apiBase() + path, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    ...opts,
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = data && typeof data === "object" && data.detail ? JSON.stringify(data.detail) : text;
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return data;
}

function toQuery(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}

export const api = {
  zones:              ()                  => apiJson("/zones"),
  dashboardToday:     ()                  => apiJson("/dashboard/today"),
  events:             (params = {})       => apiJson("/events" + toQuery(params)),
  eventDetail:        (id)                => apiJson(`/events/${encodeURIComponent(id)}`),
  participation:      (params = {})       => apiJson("/dispatch/participation" + toQuery(params)),
  congestionHeatmap:  (params = {})       => apiJson("/dispatch/congestion-heatmap" + toQuery(params)),
};
```

- [ ] **Step 2: Write `app.js` with scenario state + empty layout**

```javascript
import { api } from "./api.js";
import { HeaderBar } from "./components/HeaderBar.js";
import { HeroMap } from "./components/HeroMap.js";
import { CommunityKwhCard } from "./components/CommunityKwhCard.js";
import { RatepayerValueCard } from "./components/RatepayerValueCard.js";
import { CommunitiesLeaderboard } from "./components/CommunitiesLeaderboard.js";
import { EventRibbon } from "./components/EventRibbon.js";
import { ScaleSlider } from "./components/ScaleSlider.js";

const { createApp, reactive, computed, h, onMounted } = Vue;

// Scale rule: "today" baseline is 5,000 devices against a 6-device DB pilot.
// scaleFactor is applied per-widget; the scaling-semantics table in the plan
// dictates which numbers multiply and which don't.
const BASE_DB_DEVICES = 6;

async function loadScenarios() {
  const res = await fetch("./refdata/scenarios.json");
  return res.json();
}

const App = {
  setup() {
    const state = reactive({
      loading: true,
      err: null,
      scenarios: [],       // [{id, label, deviceCount, peakMw, infra, citation}]
      scenario: null,      // currently selected scenario
      today: null,         // dashboardToday response
      zones: [],           // zones list
      events30: [],        // last 30 days event list
      participation30: null, // 30-day participation rollup
      participation7: null,  // 7-day participation rollup
      heatmap: null,       // latest congestion-heatmap response
    });

    const scaleFactor = computed(() =>
      state.scenario ? state.scenario.deviceCount / BASE_DB_DEVICES : 1
    );

    async function load() {
      try {
        const [scenarios, today, zones, events30, p30, p7, heat] = await Promise.all([
          loadScenarios(),
          api.dashboardToday(),
          api.zones(),
          api.events({ window_days: 30, limit: 200 }),
          api.participation({ window_days: 30 }),
          api.participation({ window_days: 7 }),
          api.congestionHeatmap(),
        ]);
        state.scenarios = scenarios;
        state.scenario = scenarios.find((s) => s.id === "today") || scenarios[0];
        state.today = today;
        state.zones = zones;
        state.events30 = events30.events || [];
        state.participation30 = p30;
        state.participation7 = p7;
        state.heatmap = heat;
        state.loading = false;
      } catch (e) {
        state.err = String(e.message || e);
        state.loading = false;
      }
    }

    function setScenario(id) {
      const next = state.scenarios.find((s) => s.id === id);
      if (next) state.scenario = next;
    }

    onMounted(load);

    return () => {
      if (state.loading) return h("div", { class: "loading" }, "Loading…");
      if (state.err) return h("div", { class: "panel error-text", style: { gridColumn: "1 / -1" } }, state.err);

      return [
        h(HeaderBar, {
          class: "exec-hdr panel",
          today: state.today,
        }),
        h(HeroMap, {
          class: "exec-map",
          heatmap: state.heatmap,
          zones: state.zones,
          events30: state.events30,
          scaleFactor: scaleFactor.value,
        }),
        h("div", { class: "exec-rail" }, [
          h(CommunityKwhCard,   { class: "panel kpi", participation7: state.participation7, scaleFactor: scaleFactor.value }),
          h(RatepayerValueCard, { class: "panel kpi", participation30: state.participation30, scaleFactor: scaleFactor.value }),
          h(CommunitiesLeaderboard, { class: "panel kpi", zones: state.zones, participation30: state.participation30, scaleFactor: scaleFactor.value }),
        ]),
        h(EventRibbon, {
          class: "exec-ribbon panel",
          events30: state.events30,
        }),
        h(ScaleSlider, {
          class: "exec-slider panel",
          scenarios: state.scenarios,
          current: state.scenario,
          onSelect: setScenario,
        }),
      ];
    };
  },
};

createApp(App).mount("#app");
```

- [ ] **Step 3: Create one-line stubs for the 7 component files**

```bash
REPO="/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier"
mkdir -p "$REPO/app/static/dominion_executive/components"
for f in HeaderBar HeroMap CommunityKwhCard RatepayerValueCard CommunitiesLeaderboard EventRibbon ScaleSlider; do
  echo "export const $f = { props: {}, render() { return Vue.h('div', { class: 'muted' }, 'TODO: $f'); } };" \
    > "$REPO/app/static/dominion_executive/components/$f.js"
done
ls "$REPO/app/static/dominion_executive/components/"
```

Expected: 7 files listed.

- [ ] **Step 4: pytest still green**

```bash
cd "$REPO" && "$PY" -m pytest -q
```

Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/api.js app/static/dominion_executive/app.js app/static/dominion_executive/components/
git commit -m "feat(exec-ui): Vue bootstrap, scenario state, component stubs"
```

---

## Phase D: Refdata

### Task D1: `scenarios.json`

**Files:**
- Create: `app/static/dominion_executive/refdata/scenarios.json`

- [ ] **Step 1: Write the file**

```bash
mkdir -p "$REPO/app/static/dominion_executive/refdata"
```

Then create `app/static/dominion_executive/refdata/scenarios.json`:

```json
[
  {
    "id": "today",
    "label": "Today · simulated pilot scale",
    "deviceCount": 5000,
    "peakMw": 10,
    "infra": "Live simulation at pilot scale, grounded in 2026 PJM DOM DA data.",
    "citation": "WattCarbon simulation, not a Dominion filing."
  },
  {
    "id": "dsm-target",
    "label": "Dominion DSM / GAPS target",
    "deviceCount": 50000,
    "peakMw": 100,
    "infra": "Defers one 230 kV substation upgrade.",
    "citation": "Directional toward Dominion Energy Virginia's stated DSM/GAPS program scale. Replace with IRP docket + page reference before the first external meeting."
  },
  {
    "id": "load-growth",
    "label": "NoVA load-growth matched",
    "deviceCount": 500000,
    "peakMw": 1000,
    "infra": "Offsets one natural-gas peaker plant.",
    "citation": "Directional toward publicly reported Northern Virginia data-center load growth. Replace with IRP docket + page reference before the first external meeting."
  }
]
```

- [ ] **Step 2: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/refdata/scenarios.json
git commit -m "feat(exec-ui): scale scenario stops (today / DSM target / load growth)"
```

---

### Task D2: `synth_devices_va.json` — 5,000 synthesized device locations

**Files:**
- Create: `~/claude/outputs/tmp/synth_devices_va_gen.py`
- Create: `app/static/dominion_executive/refdata/synth_devices_va.json`

- [ ] **Step 1: Write the generator script**

Write to `/Users/mcgeesmini/claude/outputs/tmp/synth_devices_va_gen.py`:

```python
"""
Generate 5,000 pseudo-device locations across Dominion Virginia Power
service territory. Weighted by county residential density.

Distribution target (approx %, from 2020 census DVP service territory):
  Fairfax 22 · Loudoun 12 · Prince William 9 · Virginia Beach 9
  Chesterfield 7 · Henrico 7 · Stafford 3 · Spotsylvania 3
  Hanover 2 · Newport News 4 · Chesapeake 4 · Richmond city 4
  Suffolk 2 · Hampton 3 · York 1 · Norfolk 4
  rest distributed across remaining DVP counties at 1% each.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

OUT = Path(
    "/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier"
    "/app/static/dominion_executive/refdata/synth_devices_va.json"
)

# County centroid + jitter radius in degrees (~0.1 = ~11 km)
COUNTIES = [
    ("Fairfax",         38.83, -77.28, 0.09, 22),
    ("Loudoun",         39.10, -77.55, 0.11, 12),
    ("Prince William",  38.70, -77.48, 0.10,  9),
    ("Virginia Beach",  36.85, -75.98, 0.10,  9),
    ("Chesterfield",    37.38, -77.58, 0.09,  7),
    ("Henrico",         37.62, -77.41, 0.08,  7),
    ("Stafford",        38.42, -77.45, 0.08,  3),
    ("Spotsylvania",    38.18, -77.65, 0.08,  3),
    ("Hanover",         37.74, -77.42, 0.08,  2),
    ("Newport News",    37.08, -76.47, 0.06,  4),
    ("Chesapeake",      36.76, -76.28, 0.08,  4),
    ("Richmond city",   37.54, -77.44, 0.05,  4),
    ("Suffolk",         36.73, -76.60, 0.09,  2),
    ("Hampton",         37.05, -76.36, 0.05,  3),
    ("York",            37.24, -76.53, 0.07,  1),
    ("Norfolk",         36.85, -76.28, 0.05,  4),
    ("Albemarle",       38.02, -78.55, 0.09,  1),
    ("Charlottesville", 38.03, -78.48, 0.04,  1),
    ("Montgomery",      37.17, -80.40, 0.09,  1),
    ("Roanoke",         37.27, -79.95, 0.08,  1),
]

TOTAL = 5000


def sample_one(lat0, lon0, radius):
    # Uniform in a disk, roughly
    r = radius * math.sqrt(random.random())
    theta = random.random() * 2 * math.pi
    return (round(lat0 + r * math.cos(theta), 5), round(lon0 + r * math.sin(theta), 5))


def main():
    random.seed(20260419)  # deterministic output
    points = []
    weights_sum = sum(w for *_rest, w in COUNTIES)
    for name, lat0, lon0, radius, weight in COUNTIES:
        n = round(TOTAL * (weight / weights_sum))
        for _ in range(n):
            lat, lon = sample_one(lat0, lon0, radius)
            points.append({"lat": lat, "lon": lon, "county": name})
    # Trim / pad to exactly TOTAL due to rounding drift.
    while len(points) > TOTAL:
        points.pop()
    while len(points) < TOTAL:
        name, lat0, lon0, radius, _ = COUNTIES[0]
        lat, lon = sample_one(lat0, lon0, radius)
        points.append({"lat": lat, "lon": lon, "county": name})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_source": (
            "Deterministic synthetic distribution of 5,000 residential devices across "
            "Dominion Virginia Power service territory, weighted by 2020 census "
            "household counts. Used for the exec-pitch map density layer only."
        ),
        "_seed": 20260419,
        "count": len(points),
        "points": points,
    }, separators=(",", ":")))
    print(f"Wrote {OUT} · {len(points)} points")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
"$PY" /Users/mcgeesmini/claude/outputs/tmp/synth_devices_va_gen.py
```

Expected: `Wrote .../synth_devices_va.json · 5000 points`.

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/refdata/synth_devices_va.json
git commit -m "feat(exec-ui): seed 5,000 synthesized VA device locations for map density"
```

---

### Task D3: `maplibre-style.json` — brand-tinted dark style

**Files:**
- Create: `app/static/dominion_executive/refdata/maplibre-style.json`

- [ ] **Step 1: Write minimal dark vector style**

Approach: use OpenFreeMap's free vector tiles (`https://tiles.openfreemap.org/planet`) with a minimal handwritten style that colors land, water, roads, and labels per WC tokens. No fancy layer coverage; this is a demo backdrop, not a cartographic product.

Create `app/static/dominion_executive/refdata/maplibre-style.json`:

```json
{
  "version": 8,
  "name": "WC dark sherpa",
  "sources": {
    "openmaptiles": {
      "type": "vector",
      "url": "https://tiles.openfreemap.org/planet"
    }
  },
  "glyphs": "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  "layers": [
    { "id": "background", "type": "background", "paint": { "background-color": "#00232C" } },
    {
      "id": "water",
      "type": "fill",
      "source": "openmaptiles", "source-layer": "water",
      "paint": { "fill-color": "#001A20" }
    },
    {
      "id": "landcover-wood",
      "type": "fill",
      "source": "openmaptiles", "source-layer": "landcover",
      "filter": ["==", "class", "wood"],
      "paint": { "fill-color": "#002731", "fill-opacity": 0.5 }
    },
    {
      "id": "boundary-state",
      "type": "line",
      "source": "openmaptiles", "source-layer": "boundary",
      "filter": ["==", "admin_level", 4],
      "paint": { "line-color": "#0697B6", "line-width": 0.8, "line-opacity": 0.6 }
    },
    {
      "id": "boundary-country",
      "type": "line",
      "source": "openmaptiles", "source-layer": "boundary",
      "filter": ["==", "admin_level", 2],
      "paint": { "line-color": "#0697B6", "line-width": 1.2, "line-opacity": 0.8 }
    },
    {
      "id": "road-minor",
      "type": "line",
      "source": "openmaptiles", "source-layer": "transportation",
      "filter": ["in", "class", "minor", "service", "tertiary"],
      "paint": { "line-color": "#003E4A", "line-width": 0.4 }
    },
    {
      "id": "road-primary",
      "type": "line",
      "source": "openmaptiles", "source-layer": "transportation",
      "filter": ["in", "class", "primary", "secondary", "trunk"],
      "paint": { "line-color": "#346876", "line-width": 0.8 }
    },
    {
      "id": "road-highway",
      "type": "line",
      "source": "openmaptiles", "source-layer": "transportation",
      "filter": ["in", "class", "motorway"],
      "paint": { "line-color": "#346876", "line-width": 1.6 }
    },
    {
      "id": "place-city",
      "type": "symbol",
      "source": "openmaptiles", "source-layer": "place",
      "filter": ["in", "class", "city", "town"],
      "layout": {
        "text-field": "{name:en}",
        "text-size": 12,
        "text-font": ["Noto Sans Regular"]
      },
      "paint": {
        "text-color": "#F1FDFF",
        "text-halo-color": "#00232C",
        "text-halo-width": 1.2
      }
    }
  ]
}
```

- [ ] **Step 2: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/refdata/maplibre-style.json
git commit -m "feat(exec-ui): WC dark-sherpa MapLibre vector style"
```

---

## Phase E: Components

All Phase E tasks follow the same pattern: replace the stub JS file with the real component, verify imports compile, visually confirm locally at `http://localhost:8001/dominion/`, commit. No unit tests for frontend (same pattern as `/dominion-admin/`).

**Run a local uvicorn for manual verification** (leave running across Phase E tasks; ctrl-C at end of Phase F):

```bash
cd "$REPO" && DATABASE_URL="$DSN" PJM_SUBSCRIPTION_KEY=dummy "$PY" -m uvicorn app.main:app --port 8001
```

Ensure Cloud SQL Auth Proxy is up (see Global rules). Open `http://localhost:8001/dominion/` in a browser.

---

### Task E1: ScaleSlider

**Files:** Modify `app/static/dominion_executive/components/ScaleSlider.js`.

- [ ] **Step 1: Replace stub**

```javascript
const { h } = Vue;

export const ScaleSlider = {
  props: {
    scenarios: { type: Array, required: true },
    current: { type: Object, required: true },
    onSelect: { type: Function, required: true },
  },
  render() {
    return h("div", null, [
      h("div", { class: "h" }, "Scale scenarios"),
      h("div", { class: "slider-stops" }, this.scenarios.map((s) =>
        h("div", {
          class: ["slider-stop", this.current && this.current.id === s.id ? "active" : ""],
          onClick: () => this.onSelect(s.id),
        }, [
          h("div", { class: "num" }, `${s.deviceCount.toLocaleString()} devices`),
          h("div", { class: "mw" }, `${s.peakMw.toLocaleString()} MW peak`),
          h("div", { class: "infra" }, s.infra),
        ])
      )),
      h("div", { class: "disc" }, "Linear scaling. Real-world saturation at 230 kV substations not modeled."),
    ]);
  },
};
```

- [ ] **Step 2: Reload browser; click each stop**

Reload `http://localhost:8001/dominion/`. Three stop cards show under an empty panel (other widgets are still TODO stubs). Clicking a stop adds the `active` border; scenarios state updates (visible in DevTools console if you add `window.__scenario = state.scenario` in app.js — skip if not needed).

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/components/ScaleSlider.js
git commit -m "feat(exec-ui): ScaleSlider with 3 named stops"
```

---

### Task E2: HeaderBar

**Files:** Modify `app/static/dominion_executive/components/HeaderBar.js`.

- [ ] **Step 1: Replace stub**

```javascript
const { h } = Vue;

export const HeaderBar = {
  props: { today: { type: Object, required: true } },
  render() {
    const t = this.today;
    const basisLabel = t.forecast_basis === "tomorrow_da" ? "PJM DA tomorrow" : "latest cleared DA";
    const peakMw = (t.peak_program_kw / 1000).toFixed(1);
    return h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" } }, [
      h("div", { class: "lead" },
        `Virginia communities deliver back to Dominion's grid.`),
      h("div", { class: "grid-state" }, [
        h("div", { class: "h" }, `${basisLabel} · ${t.operating_date}`),
        h("div", { class: "v" }, `${t.events_forecast} events · ${peakMw} MW peak`),
      ]),
    ]);
  },
};
```

- [ ] **Step 2: Reload and confirm**

Reload `http://localhost:8001/dominion/`. Top panel shows the lead copy on the left and today's grid-state readout on the right.

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/components/HeaderBar.js
git commit -m "feat(exec-ui): HeaderBar with lead line + live grid state"
```

---

### Task E3: CommunityKwhCard

**Files:** Modify `app/static/dominion_executive/components/CommunityKwhCard.js`.

- [ ] **Step 1: Replace stub**

```javascript
const { h } = Vue;

export const CommunityKwhCard = {
  props: {
    participation7: { type: Object, required: true },
    scaleFactor: { type: Number, required: true },
  },
  render() {
    // Sum realized kWh across devices, scaled by the scenario factor.
    // participation7.devices[].any_dispatch_hours * that device's listed_capacity_kw
    // is the closest proxy we have without a dedicated "realized_kwh" field.
    // Use total_hours instead of any_dispatch_hours because we mock realized kw
    // for every dispatch hour via the telemetry_mock module.
    const devices = this.participation7?.devices || [];
    // Rough kWh proxy: sum of (any_dispatch_hours × avg listed kW × avg realized ratio).
    // Real "realized kWh" is in the /events/{id} hourly rows, but aggregating across
    // 7 days × 6 devices × N hours in the browser is wasteful. Use a defensible
    // derived estimate: any_dispatch_hours × avg_listed_kw × 0.85 (a "typical
    // realization ratio" matching telemetry_mock's band).
    let baseKwh = 0;
    for (const d of devices) {
      baseKwh += (d.any_dispatch_hours || 0) * 0.85 * 700; // 700 kW avg listed per demo device
    }
    const scaledKwh = baseKwh * this.scaleFactor;
    return h("div", null, [
      h("div", { class: "h" }, "Community energy delivered · last 7 days"),
      h("div", { class: "v" }, `${Math.round(scaledKwh).toLocaleString()} kWh`),
      h("div", { class: "sub" }, "Virginia rooftops and small businesses · scaled by scenario"),
    ]);
  },
};
```

- [ ] **Step 2: Reload and verify**

Reload `http://localhost:8001/dominion/`. The rail tile in row 1 shows a non-zero kWh number. Flip scenario stops — number should be ~833× larger when stop 1 → stop 2, ~833× again stop 2 → stop 3.

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/components/CommunityKwhCard.js
git commit -m "feat(exec-ui): CommunityKwhCard with 7-day scaled kWh"
```

---

### Task E4: RatepayerValueCard

**Files:** Modify `app/static/dominion_executive/components/RatepayerValueCard.js`.

- [ ] **Step 1: Replace stub**

```javascript
const { h } = Vue;

// Settlement rate: DOM zone p85 abs congestion over trailing 365 DA days.
// Computed once offline (see spec §5.4). Hardcoded here to avoid an extra
// round-trip; re-derive if the backfill window changes materially.
const DOM_P85_USD_PER_MWH = 16.60;

export const RatepayerValueCard = {
  props: {
    participation30: { type: Object, required: true },
    scaleFactor: { type: Number, required: true },
  },
  render() {
    const devices = this.participation30?.devices || [];
    // Same kWh estimate as CommunityKwhCard but over 30 days.
    let baseKwh = 0;
    for (const d of devices) {
      baseKwh += (d.any_dispatch_hours || 0) * 0.85 * 700;
    }
    const scaledKwh = baseKwh * this.scaleFactor;
    const dollars = scaledKwh * 0.001 * DOM_P85_USD_PER_MWH;
    return h("div", null, [
      h("div", { class: "h" }, "Value returned to Virginia ratepayers · last 30 days"),
      h("div", { class: "v honey" }, `$${Math.round(dollars).toLocaleString()}`),
      h("div", { class: "sub" }, "Participation payments · stays in Virginia counties"),
      h("div", { class: "disc" }, "Computed at DOM zone p85 congestion ($16.60/MWh, trailing 365 DA days)."),
    ]);
  },
};
```

- [ ] **Step 2: Reload and verify**

Reload. Middle rail tile shows `$NNN,NNN`. Flipping scenarios scales the dollars linearly.

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/components/RatepayerValueCard.js
git commit -m "feat(exec-ui): RatepayerValueCard with p85-settlement dollar value"
```

---

### Task E5: CommunitiesLeaderboard

**Files:** Modify `app/static/dominion_executive/components/CommunitiesLeaderboard.js`.

- [ ] **Step 1: Replace stub**

```javascript
const { h } = Vue;

// Zone → human label (UX-friendly names, not zone IDs).
const ZONE_DISPLAY = {
  "loudoun-corridor": "Loudoun",
  "fairfax-230":      "Fairfax",
  "alexandria":       "Alexandria",
};

export const CommunitiesLeaderboard = {
  props: {
    zones: { type: Array, required: true },
    participation30: { type: Object, required: true },
    scaleFactor: { type: Number, required: true },
  },
  render() {
    const devices = this.participation30?.devices || [];
    // Group perf by zone from device rows, then order by average perf.
    const byZone = {};
    // Build zone-membership lookup from this.zones.
    const deviceToZone = {};
    for (const z of this.zones) {
      for (const d of (z.device_ids || [])) deviceToZone[d] = z.id;
    }
    for (const d of devices) {
      const zid = deviceToZone[d.device_id_external];
      if (!zid) continue;
      byZone[zid] = byZone[zid] || { perfs: [], mwBase: 0 };
      if (d.participation_pct != null) byZone[zid].perfs.push(d.participation_pct);
      // Rough MW = listed capacity fraction × scale. Use 700 kW × device count.
      byZone[zid].mwBase += 0.7;
    }
    const rows = this.zones.map((z) => {
      const agg = byZone[z.id] || { perfs: [], mwBase: 0 };
      const avgPerf = agg.perfs.length ? agg.perfs.reduce((a, b) => a + b, 0) / agg.perfs.length : null;
      const scaledMw = agg.mwBase * this.scaleFactor;
      return {
        id: z.id,
        name: ZONE_DISPLAY[z.id] || z.label,
        mw: scaledMw,
        perf: avgPerf,
      };
    }).sort((a, b) => (b.perf || 0) - (a.perf || 0));

    return h("div", null, [
      h("div", { class: "h" }, "Communities leaderboard"),
      ...rows.map((r) => h("div", { class: "leaderboard-row" }, [
        h("span", { class: "name" }, r.name),
        h("span", { class: "meta" }, `${r.mw.toFixed(1)} MW · ${r.perf != null ? r.perf.toFixed(0) + "%" : "-"}`),
      ])),
    ]);
  },
};
```

- [ ] **Step 2: Reload and verify**

Reload. Third rail tile shows 3 rows (Loudoun / Fairfax / Alexandria) with MW and perf%.

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/components/CommunitiesLeaderboard.js
git commit -m "feat(exec-ui): CommunitiesLeaderboard with 3-zone ranking"
```

---

### Task E6: EventRibbon

**Files:** Modify `app/static/dominion_executive/components/EventRibbon.js`.

- [ ] **Step 1: Replace stub**

```javascript
const { h, ref } = Vue;

function dayKey(isoLike) {
  // Use the operating_date from the event, not start_utc, to bucket correctly.
  return String(isoLike).slice(0, 10);
}

export const EventRibbon = {
  props: { events30: { type: Array, required: true } },
  setup(props) {
    // Aggregate events by operating_date. Red (mandatory) wins over
    // honeydew (optional-only) wins over sandy (no event).
    function bucket() {
      const buckets = new Map(); // dayKey -> "mand" | "opt" | null
      for (const ev of props.events30 || []) {
        const k = dayKey(ev.operating_date);
        const cur = buckets.get(k);
        if (ev.has_mandatory) buckets.set(k, "mand");
        else if (cur !== "mand") buckets.set(k, "opt");
      }
      return buckets;
    }

    return () => {
      const b = bucket();
      // Render last 30 calendar days ending at today UTC.
      const days = [];
      const today = new Date();
      for (let i = 29; i >= 0; i--) {
        const d = new Date(today);
        d.setUTCDate(today.getUTCDate() - i);
        const k = d.toISOString().slice(0, 10);
        days.push({ key: k, cls: b.get(k) || "" });
      }
      return h("div", null, [
        h("div", { class: "h" }, "30 days of grid stress · honeydew optional · red mandatory"),
        h("div", { class: "ribbon-strip" }, days.map((d) =>
          h("div", { class: ["cell", d.cls], title: d.key })
        )),
        h("div", { class: "disc" }, "Grid stress is a property of the grid itself; does not scale with device count."),
      ]);
    };
  },
};
```

- [ ] **Step 2: Reload and verify**

Reload. Ribbon panel shows 30 tiles colored per tier. Hover a tile → tooltip shows the date. (Click-to-play is Task E7's event-playback scope; ribbon stays clickable but without effect until E7 wires up `HeroMap.playbackEvent()`.)

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/components/EventRibbon.js
git commit -m "feat(exec-ui): EventRibbon with 30-day tiered tile strip"
```

---

### Task E7: HeroMap

**Files:** Modify `app/static/dominion_executive/components/HeroMap.js`.

This is the largest component. Two layers: real congestion heatmap from the API, synthesized device density from `synth_devices_va.json`. Event playback is scoped to "click a day tile → map re-centers on VA and overlays that day's congestion peak" (no hour-by-hour scrub in v1).

- [ ] **Step 1: Replace stub**

```javascript
const { h, onMounted, onBeforeUnmount, ref, watch } = Vue;

const STYLE_URL = "./refdata/maplibre-style.json";
const SYNTH_URL = "./refdata/synth_devices_va.json";

function heatmapColorStops() {
  // Transparent at weight 0 → honeydew (#E4FD7F) → red (#E5534B) at heavy.
  return [
    "interpolate", ["linear"], ["heatmap-density"],
    0, "rgba(0,0,0,0)",
    0.3, "rgba(228,253,127,0.35)",
    0.7, "rgba(228,253,127,0.8)",
    1, "rgba(229,83,75,0.9)",
  ];
}

async function loadJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`fetch ${url}: ${r.status}`);
  return r.json();
}

export const HeroMap = {
  props: {
    heatmap: { type: Object, required: true },
    zones: { type: Array, required: true },
    events30: { type: Array, required: true },
    scaleFactor: { type: Number, required: true },
  },
  setup(props) {
    const el = ref(null);
    let map = null;
    let synthPoints = [];

    async function init() {
      const style = await loadJson(STYLE_URL);
      map = new maplibregl.Map({
        container: el.value,
        style,
        center: [-78.6, 37.8],  // VA approx
        zoom: 6.4,
        attributionControl: true,
      });
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
      map.on("load", async () => {
        // Real congestion heatmap from the heatmap API.
        const congestionFC = {
          type: "FeatureCollection",
          features: (props.heatmap?.points || []).map((p) => ({
            type: "Feature",
            geometry: { type: "Point", coordinates: [p.lon, p.lat] },
            properties: { w: p.max_abs_congestion },
          })),
        };
        map.addSource("congestion", { type: "geojson", data: congestionFC });
        map.addLayer({
          id: "congestion-heat",
          type: "heatmap",
          source: "congestion",
          maxzoom: 12,
          paint: {
            "heatmap-weight": ["interpolate", ["linear"], ["get", "w"], 0, 0, 40, 0.6, 100, 1],
            "heatmap-intensity": 1.1,
            "heatmap-color": heatmapColorStops(),
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 18, 9, 45],
            "heatmap-opacity": 0.85,
          },
        });

        // Synthesized device density layer.
        const synth = await loadJson(SYNTH_URL);
        synthPoints = synth.points || [];
        map.addSource("devices", {
          type: "geojson",
          data: synthFeatureCollection(synthPoints, props.scaleFactor),
        });
        map.addLayer({
          id: "devices-heat",
          type: "heatmap",
          source: "devices",
          paint: {
            "heatmap-weight": 0.05,
            "heatmap-intensity": ["interpolate", ["linear"], ["get", "intensity"], 0, 0.2, 1, 1.0],
            "heatmap-color": [
              "interpolate", ["linear"], ["heatmap-density"],
              0, "rgba(0,0,0,0)",
              0.3, "rgba(11,212,255,0.2)",
              0.7, "rgba(11,212,255,0.5)",
              1, "rgba(228,253,127,0.7)",
            ],
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 12, 9, 30],
            "heatmap-opacity": 0.75,
          },
        });
      });
    }

    function synthFeatureCollection(points, scaleFactor) {
      // At scaleFactor=1 (today), render the 5,000 points once; heatmap is
      // governed by heatmap-weight. At scaleFactor > 1, duplicate with jitter
      // and ramp the weight up via the "intensity" property.
      // Rather than multiplying the JSON array by 10x/100x (performance hit),
      // multiply a per-point "intensity" property and rely on heatmap-weight.
      const reps = scaleFactor <= 1 ? 1 : scaleFactor <= 20 ? 2 : 4;
      const features = [];
      const rand = mulberry32(20260419);
      for (let r = 0; r < reps; r++) {
        for (const p of points) {
          const jitter = r === 0 ? 0 : 0.01;
          features.push({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [
                p.lon + (rand() - 0.5) * 2 * jitter,
                p.lat + (rand() - 0.5) * 2 * jitter,
              ],
            },
            properties: { intensity: Math.min(1, scaleFactor / 100) },
          });
        }
      }
      return { type: "FeatureCollection", features };
    }

    // Tiny deterministic PRNG
    function mulberry32(seed) {
      let a = seed;
      return function () {
        a |= 0; a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    }

    watch(() => props.scaleFactor, (sf) => {
      if (!map || !map.getSource("devices")) return;
      map.getSource("devices").setData(synthFeatureCollection(synthPoints, sf));
    });

    onMounted(init);
    onBeforeUnmount(() => {
      if (map) { map.remove(); map = null; }
    });

    return () => h("div", {
      ref: el,
      style: { width: "100%", height: "100%", minHeight: "28rem" },
    });
  },
};
```

- [ ] **Step 2: Reload browser; verify map**

Reload `http://localhost:8001/dominion/`. The map renders Virginia with:
- Dark sherpa land + sherpa water
- A subtle honeydew/red heatmap concentrated near NoVA (real congestion data)
- A cyan/honeydew density glow distributed across the state (synthesized devices)

Flip scenarios: the device density glow intensifies stop 1 → stop 2 → stop 3. The congestion heatmap is unchanged (real grid data).

If the map is blank: open devtools → Network tab → check for 4xx on `maplibre-style.json` or the OpenFreeMap URL. Common fix: wait a few seconds for vector tiles to load; if still blank, verify `maplibre-style.json` is valid JSON.

- [ ] **Step 3: Commit**

```bash
cd "$REPO"
git add app/static/dominion_executive/components/HeroMap.js
git commit -m "feat(exec-ui): HeroMap with real congestion + synthesized device density"
```

---

## Phase F: Integration, deploy, push

### Task F1: Cross-component smoke in browser

**Files:** none.

- [ ] **Step 1: Visual walkthrough at `http://localhost:8001/dominion/`**

Check each behavior:
1. Header shows "Virginia communities deliver back to Dominion's grid." + live grid state readout.
2. Map renders VA with two heatmap layers and zoom/pan controls.
3. Rail shows three KPI tiles with non-zero numbers.
4. Event ribbon shows 30 tiles, a mix of sandy / honeydew / red.
5. Scale slider shows 3 stops; clicking changes the active one.
6. Flipping to "DSM target" (50k) scales CommunityKwhCard, RatepayerValueCard, leaderboard MW by ~10×. Congestion heatmap and event ribbon are unchanged.
7. Flipping to "NoVA load-growth" (500k) scales those three widgets by ~100× from today. Device density layer intensifies.
8. Footer shows disclosure + links to `/dominion-admin/` and `/dominion-demo/`.

Any failures → fix in the owning component; commit fixes with `fix(exec-ui): …` messages.

- [ ] **Step 2: Stop the uvicorn** (ctrl-C).

No commit.

---

### Task F2: Copy polish pass

**Files:**
- Modify: `app/static/dominion_executive/components/HeaderBar.js` (primary headline)
- Modify: `app/static/dominion_executive/components/CommunityKwhCard.js` (labels)
- Modify: `app/static/dominion_executive/components/RatepayerValueCard.js` (labels)
- Modify: `app/static/dominion_executive/refdata/scenarios.json` (infra captions)

- [ ] **Step 1: Re-read all user-facing strings with the rule set:**
  - No em dashes (use `·` or periods).
  - No hype language ("revolutionary", "unleash", "transform" → cut).
  - Every headline ≤ 80 characters.
  - Every dollar / kWh / MW number has a provenance caption below it ≤ 0.8× body size (already handled via `.disc` class).

- [ ] **Step 2: Tighten whichever strings fail the rules above**

Common offenders to scan: scenarios.json infra captions (keep under one line each), HeaderBar `.lead`, RatepayerValueCard disclosure.

- [ ] **Step 3: Commit the copy pass**

```bash
cd "$REPO"
git add app/static/dominion_executive/
git commit -m "chore(exec-ui): copy polish pass (no em-dashes, no hype, provenance inline)"
```

---

### Task F3: Deploy Cloud Run + smoke

**Files:** none.

- [ ] **Step 1: Deploy**

```bash
cd "$REPO" && gcloud run deploy dominion-api --source . --region=us-central1 --quiet 2>&1 | tail -5
```

Expected: new revision promoted, URL echoed.

- [ ] **Step 2: Smoke-test the new surface**

```bash
BASE=https://dominion-api-558972293204.us-central1.run.app
for f in "/dominion/" \
         "/dominion/styles.css" \
         "/dominion/app.js" \
         "/dominion/api.js" \
         "/dominion/refdata/scenarios.json" \
         "/dominion/refdata/synth_devices_va.json" \
         "/dominion/refdata/maplibre-style.json" \
         "/dominion/components/HeroMap.js" \
         "/api/v1/dominion/admin/dispatch/congestion-heatmap"; do
  printf "%-55s " "$f"
  curl -sS -o /dev/null -w "HTTP %{http_code} · %{size_download}B\n" "$BASE$f"
done
```

Expected: every line reports `HTTP 200` with non-zero body size.

- [ ] **Step 3: Manual browser walkthrough on production URL**

Open `https://dominion-api-558972293204.us-central1.run.app/dominion/`. Repeat the Task F1 walkthrough against the live URL. Capture any regressions in `~/claude/outputs/tmp/dominion-exec-qa-notes.md`.

- [ ] **Step 4: Push branch**

```bash
cd "$REPO" && git push github main:feature/dominion-poc 2>&1 | tail -3
```

Expected: remote ref advances to the new HEAD.

---

## Self-review hints

Before declaring done, re-check the plan against the spec:

1. **Every spec requirement has a task.** §1 purpose, §3 persona framing, §4 architecture, §4.3 data sources, §4.4 heatmap endpoint, §5 widgets (×7), §6 scale math, §7 visual language, §8 copy strategy, §9 testing, §10 deployment. Every one maps to a task above. §7 visual language items (motion, typography) are not their own task but are enforced by `styles.css` tokens + component rendering.
2. **No placeholders.** IRP citations in `scenarios.json` are explicitly called out as "replace before first external meeting" — that's a product decision, not a plan failure.
3. **Types stay consistent.** `scaleFactor` is used identically across widgets. `scenario` state shape matches `scenarios.json` key set. `participation30.devices[]` keys (`participation_pct`, `any_dispatch_hours`) match the admin API response already in production.
4. **Commands quote paths with spaces;** `$REPO`, `$PY`, `$DSN`, `$PJM_KEY`, `$BASE` all set at the top.
5. **Branch hygiene:** every task explicitly stays on `main`, no `git checkout`.
