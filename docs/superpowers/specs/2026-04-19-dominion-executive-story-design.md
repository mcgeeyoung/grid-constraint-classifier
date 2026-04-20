# Dominion Executive Story — design spec

**Date:** 2026-04-19
**Status:** Brainstormed; pending implementation plan
**Audience:** Dominion Energy C-suite decision makers, pitched in a live WattCarbon-driven meeting. Non-technical; they need a story, not a dashboard.
**Adds to:** `feature/dominion-poc` branch of `grid-constraint-classifier`. Coexists with the existing `/dominion-demo/` technical walkthrough and `/dominion-admin/` program-manager dashboard.

---

## 1. Purpose

The existing `/dominion-demo/` and `/dominion-admin/` surfaces are for technical and operational audiences respectively. Neither sells the story.

This new surface is a narrative-shaped dashboard for non-technical Dominion decision makers. Its three jobs:

1. **Make grid optimization visceral** — "the grid stresses here, on this rhythm, and this is what it costs."
2. **Frame community energy as value creation** — "Virginia rooftops deliver back to the grid; capital and payments stay in the community."
3. **Show scale in a single gesture** — a slider that lets the exec watch the demo pilot grow into a program that defers a substation or a natural-gas peaker.

Driven live by a WattCarbon presenter; the exec follows. The URL is sent afterward for self-exploration.

## 2. Non-goals (out of v1)

- Real DER telemetry (still mocked; same as admin)
- Auth / multi-tenant (single-tenant demo surface)
- Mobile / tablet (desktop and projector only)
- Live WebSocket updates (page refresh only; header updates on scheduled poll)
- i18n
- Recording / export buttons (the whole page is screenshot-ready; no built-in export needed)
- Dominion co-branding (this is WattCarbon pitching; WC brand stays)
- Persona toggles (one persona: C-suite; tailor copy and emphasis accordingly)

## 3. Audience and framing

**Primary persona:** C-suite / SVP / strategic decision maker at Dominion.

Characteristics:
- Not technically proficient (doesn't read pnode IDs, $/MWh, quantile math)
- Wants "all three angles but short": reliability, program economics, customer equity
- Believes in real data but doesn't want to be buried in it
- Asks "what does this become?" more than "how does this work?"

**Implication:** every widget on screen answers one executive question, in big type, with a sub-line of defensible provenance for any analyst who's also in the room.

## 4. Architecture

**Placement:** Standalone static mount at `/dominion/` on the existing `dominion-api` Cloud Run service.

No new backend service. Same FastAPI app. Same Cloud SQL. Same `wc-brand.css`. Frontend consumes the existing `/api/v1/dominion/admin/*` endpoints plus one small new endpoint for per-pnode congestion heatmap data.

### 4.1 File structure

```
app/static/dominion_executive/
  index.html                    # brand header + Vue root + CDN imports (Vue, MapLibre, Chart.js)
  styles.css                    # pitch-specific layout + typography; consumes wc-brand.css tokens
  app.js                        # Vue app; global scenario state; component composition
  api.js                        # admin API client (mirrors admin's api.js)
  refdata/
    scenarios.json              # 3 scenario stops with real IRP-sourced numbers
    maplibre-style.json         # brand-tinted dark vector style
  components/
    HeaderBar.js                # brand + live grid-state readout + simulation disclosure line
    HeroMap.js                  # MapLibre map: heat density layer + pnode markers + event playback
    CommunityKwhCard.js         # "Community energy delivered this week"
    RatepayerValueCard.js       # "$ returned to Virginia ratepayers"
    CommunitiesLeaderboard.js   # 3 zones ranked
    EventRibbon.js              # 30-day ribbon; click day -> HeroMap plays back
    ScaleSlider.js              # 3 named stops; drives global scenario state
```

### 4.2 Global state

A single `scenario` reactive state object owned by `app.js`:

```js
{
  stopId: "today",                  // "today" | "dsm-target" | "load-growth"
  deviceCount: 5000,                // current stop's device count
  scaleFactor: 5000 / 6,            // derived: deviceCount / base_device_count
  peakMw: 10.0,                     // current stop's peak MW
  label: "Today · simulated pilot scale",
  infraCaption: "Live simulation grounded in 2026 PJM DOM DA data"
}
```

All widgets read from this state and scale their headline numbers by `scaleFactor`. Changing the slider updates all widgets in the same frame.

### 4.3 Data sources

| Widget | Endpoint | Scaling |
|---|---|---|
| Header live grid-state | existing `/api/v1/dominion/admin/dashboard/today` + computed p50 abs congestion from latest run | not scaled (grid state is real) |
| Hero map | new `GET /api/v1/dominion/admin/dispatch/congestion-heatmap?operating_date=YYYY-MM-DD` | not scaled (congestion is real); device density layer scaled via `scenario.scaleFactor` |
| Community kWh | `/api/v1/dominion/admin/dispatch/participation?window_days=7` | realized_kwh × scaleFactor |
| Ratepayer $ | derived: total_realized_kwh × 0.001 × 16.60 × scaleFactor | disclosure inline |
| Communities leaderboard | `/api/v1/dominion/admin/zones` + participation scoped per-zone | per-zone MW × scaleFactor |
| 30-day ribbon | `/api/v1/dominion/admin/events?window_days=30&limit=200` | tile colors real; tile counts real |
| Event playback | `/api/v1/dominion/admin/events/{id}` (hours detail) | realized_kw × scaleFactor for the replay overlay |

### 4.4 New backend endpoint

`GET /api/v1/dominion/admin/dispatch/congestion-heatmap`

Query params:
- `operating_date` (default: latest successful run's date)

Returns a flat JSON array:

```json
[
  {"pnode_id": "1348256193", "lat": 39.058, "lon": -77.540,
   "max_abs_congestion": 42.3, "mean_abs_congestion": 18.2},
  ...
]
```

One row per pnode for which we have DA hourly rows on that operating_date, restricted to DOM LOAD nodes AND for which we have lat/lon coordinates.

**Coordinate coverage caveat.** Today the repo has lat/lon for only 6 enrolled pnodes (`dominion_dispatch/refdata/pnode_coords_dom.json`, HIFLD + OSM sourced). The full DOM LOAD node set is ~1,336 pnodes. Implementation must extend coord coverage using one of:
- (a) HIFLD Electric Substations dataset (same source as the 6 enrolled pnodes): match all DOM LOAD pnodes by name or spatial proximity; write the result to `pnode_coords_dom_full.json`.
- (b) PJM's pnode metadata feed if it includes coordinates.
- (c) Fallback: return only the pnodes we have coords for (small, clustered near NoVA); map looks sparse but defensible.

Preferred: (a), one-time offline job, committed as a JSON asset. Fallback to (c) if (a) isn't feasible in the window.

Cached at service level per (operating_date). ~1,336 rows × ~35 bytes each = ~50 KB per day.

## 5. Widget specifications

### 5.1 HeaderBar (full-width top)

**Role:** Set the tone. Live grid-state readout. Quiet-but-present simulation disclosure.

**Content:**
- Left: WattCarbon logomark + "Virginia DER program" context label
- Right: "Right now on the grid" + single number like `$18.20/MWh · 1.3× p85` with color matching stress tier (sandy if < p85, neon if ≥ p85, red-tinted if ≥ p95)
- Below main row (small, muted): "Live simulation at 5,000 Virginia households against real 2026 PJM DOM DA data. Slider scales to Dominion IRP targets."

Refreshes every 5 minutes via `setInterval`. No WebSocket.

### 5.2 HeroMap (centerpiece)

**Role:** Geographic anchor. Shows where the grid stresses and where communities respond.

**Base:** MapLibre GL JS via CDN, initialized with a custom brand style (`refdata/maplibre-style.json`) backed by OpenFreeMap vector tiles (no API key needed).

**Brand style highlights:**
- Land: `#00232C` (Dark Sherpa)
- Water: `#001A20`
- Roads: `#003E4A` → `#346876` by class
- Labels: `#F1FDFF` with subtle glow
- State / county borders: `#0697B6` (Lake) at low opacity

**Layers (z-order bottom to top):**
1. **Congestion heatmap** — GL heatmap layer fed from `/congestion-heatmap` endpoint. Weight = max_abs_congestion; radius scales with zoom; color ramp from transparent → honeydew → red.
2. **Participation density** — GL heatmap layer synthesized client-side from the scenario. The 5,000 "today" points are pre-generated once and committed to `refdata/synth_devices_va.json` as `[{lat, lon, county}, ...]`, weighted by Dominion Virginia Power residential density (county-level weights: Fairfax 22%, Loudoun 12%, Prince William 9%, Chesterfield 7%, Henrico 7%, Virginia Beach 9%, remaining distributed per 2020 census households served by DVP). At the 50k stop, the same 5k points are replicated 10× with small Gaussian jitter (±0.01°); at 500k, 100× with the same jitter. Intensity scales with `scaleFactor`. Color ramp: honeydew at low density, brightening to neon at higher.
3. **Communities leaderboard markers** — 3 labeled markers (Loudoun, Fairfax, Alexandria) at their centroids, clickable to re-center + zoom and highlight in leaderboard.

**Event playback:** when a day tile in EventRibbon is clicked, HeroMap enters playback mode:
- Freeze view on VA
- Play the 24 hourly frames of that day
- Congestion heatmap updates per hour
- Device markers pulse red on mandatory hours, honeydew on stressed
- "Scrub" affordance at the bottom of the map to pause / step
- Exit button returns to live view

### 5.3 CommunityKwhCard (rail tile 1)

**Role:** Frame "community energy value creation" tangibly.

**Content:**
- Label: "Community energy delivered this week"
- Value: e.g. `2,847 kWh` (Source Serif Pro, large)
- Sub: `Virginia rooftops and small businesses · up X% vs last week`

**Data:** sum of realized_kwh over the last 7 DA days × scaleFactor. Sub-line computed vs prior 7 days.

### 5.4 RatepayerValueCard (rail tile 2)

**Role:** "Capital stays in Virginia" angle.

**Content:**
- Label: "Value returned to Virginia ratepayers"
- Value: e.g. `$14,200` (honeydew color; matches community framing)
- Sub: `Participation payments · stays in Loudoun, Fairfax, Alexandria`
- Small disclosure: `Computed at DOM zone p85 congestion ($16.60/MWh, trailing 365 DA days)`

**Data:** `total_realized_kwh × 0.001 × 16.60 × scaleFactor`.

### 5.5 CommunitiesLeaderboard (rail tile 3)

**Role:** Local pride; community framing.

**Content:** 3 rows, one per zone, ranked by participation performance:
- `Loudoun · 1.2 MW · 96%`
- `Fairfax · 2.6 MW · 91%`
- `Alexandria · 0.6 MW · 94%`

Click a row → HeroMap zooms to that zone and highlights its marker.

### 5.6 EventRibbon (full-width below map)

**Role:** Grid-optimization cadence. "The grid stresses on this rhythm."

**Content:**
- Label: "30 days of grid stress · honeydew optional · red mandatory"
- Ribbon: 30 (or more) tiles, one per DA operating day in window. Tile color: sandy (no event that day), honeydew (only stressed events that day), red (at least one mandatory/extreme event that day — red wins over honeydew on mixed days).
- Click a tile → HeroMap plays back that day.

**Data:** `/api/v1/dominion/admin/events?window_days=30&limit=200` aggregated by operating_date.

### 5.7 ScaleSlider (full-width bottom)

**Role:** The pitch moment. "This is a new kind of utility asset class."

**Content:** Three segmented stops rendered as cards. Selecting a stop updates global `scenario` state; all widgets re-render in the same frame.

Each stop card has three lines:
- **Count:** `5,000 devices` / `50,000 devices` / `500,000 devices`
- **MW:** `10 MW peak` / `100 MW peak` / `1 GW peak`
- **Infrastructure:** caption describing what this capacity defers

Small inline disclosure: `Linear scaling; real-world saturation at 230 kV substations not modeled.`

**Stops (placeholder, to be grounded in IRP at implementation):**

| Stop | Count | MW peak | Infrastructure-defer caption |
|---|---|---|---|
| Today | 5,000 devices | 10 MW | `Live simulation at pilot scale, grounded in 2026 PJM DOM DA data` |
| Dominion DSM / GAPS target | 50,000 devices | 100 MW | `Defers one 230 kV substation upgrade · IRP docket TBC p.XX` |
| NoVA load-growth matched | 500,000 devices | 1 GW | `Offsets one natural-gas peaker plant · NoVA load-growth forecast, IRP p.YY` |

At implementation: pull real numbers from Dominion Energy Virginia's most recent IRP filing; update docket + page references in `scenarios.json` so the citations are defensible. If IRP numbers aren't public or are embargoed, degrade gracefully to "Dominion's public DR target as of [date]" language.

## 6. Scale simulator math

Client-side multiplication against a single factor:

```js
scenario.scaleFactor = scenario.deviceCount / 6;
// 5000/6 ≈ 833.33  (today)
// 50000/6 ≈ 8333.33 (stop 2)
// 500000/6 ≈ 83333.33 (stop 3)
```

All headline numbers on the page are computed as `base × scaleFactor` where `base` is whatever the live admin API returns for the 6-device pilot.

Honest about what this doesn't model:
- PJM node saturation (a single 230 kV bus has a transfer limit)
- Per-device heterogeneity (performance curve varies by device type)
- Participation-payment rate elasticity (settlement $/MWh may compress at scale)

Disclosure line near the slider makes these limits explicit for any analyst reading closely.

## 7. Visual language

**Typography:**
- Headlines / big numbers: Source Serif Pro (700 weight), already in brand
- Body / KPI labels: Inter (400 / 600), already in brand
- Monospace never used here (unlike admin)

**Colors:** WC brand tokens only (Dark Sherpa / Sherpa / Light Sherpa / Pastel Azure / Sandy / Lake / Frost / Neon / Honeydew). No admin-specific overrides.

**Motion:**
- Counter numbers tick up on scenario-stop change (250ms ease-out)
- Map layers fade between scenarios (350ms)
- Device markers pulse during event playback (1s sine)
- No gratuitous animation; if it doesn't communicate information, cut it

**Spacing and density:**
- Bigger than admin: header 56px tall, card padding 24px, map minimum height 420px
- Negative space around numbers; no tight tables anywhere

## 8. Copy strategy

Placeholder copy now; locked before first Dominion meeting. Rules:
- No em dashes (per CLAUDE.md)
- No hype language (no "revolutionary", "transform", "unleash")
- Every number has a provenance line below it at 0.75× body size
- Headline lines are ≤ 80 characters

Primary headline (working draft): *"Virginia communities delivered 2,847 kWh back to Dominion's grid this week."*

Before ship: stop-slop and copywriting skills on the full page text.

## 9. Testing

- **Backend** unit test for `/dispatch/congestion-heatmap` (boundary cases: empty date, date with 0 rows, date with real data). Matches existing pytest pattern.
- **API smoke** on deployed Cloud Run revision against all 9 admin endpoints this UI depends on (existing 8 + the new heatmap endpoint).
- **Frontend manual** walkthrough in Chrome at three screen sizes (13" MBP, 27" desk monitor, 1080p projector) before any real meeting.
- **Scale math sanity** — spot-check that toggling between scenario stops produces expected ratios on every widget; automated with a small browser-driven script (optional v1 nice-to-have).

## 10. Deployment

Same path as existing Dominion work:
1. Edit + commit on `main`.
2. `gcloud run deploy dominion-api --source . --region=us-central1` from the Dropbox working tree.
3. Hit `/dominion/` in Chrome + smoke-curl endpoints.
4. Push to `github feature/dominion-poc`.

No new env vars. No schema changes. No migrations.

## 11. Future work (explicit defer)

- Real telemetry feed (replaces mocked realized)
- Auth + IAP (public demo for now)
- Customer names / enrollment UI (currently pnode labels stand in)
- Per-utility adaptation (DOMSE, PEPCO, BGE, PJM-wide) — v2
- Live real-time (sub-DA) congestion overlay — v2
- Dominion co-branding toggle — only when we have a signed contract
- Recording / export button — fold into a future "send-to-stakeholders" feature
- Mobile / tablet layout
