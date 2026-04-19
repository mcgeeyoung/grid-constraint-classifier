# Dominion Admin Dashboard — design spec

**Date:** 2026-04-18
**Status:** Brainstormed; pending implementation plan
**Audience:** Demo / pitch prop for Dominion Energy stakeholders. Not a production operator UI. Real PJM DA data; mocked device capacity and realized telemetry.
**Adds to:** `feature/dominion-poc` branch of `grid-constraint-classifier`. Coexists with the existing `/dominion-demo/` engineering walkthrough at a new path `/dominion-admin/`.

---

## 1. Goal and frame

A program-manager-facing dashboard that lets a Dominion stakeholder see, on one screen, what the DOM DER program is doing today and how it has performed historically.

Five surfaces, all on one Cloud Run service:

1. **Zonal view of day-ahead forecast** — events expected today and tomorrow, broken down by zone.
2. **Available capacity** — listed kW per zone (aggregated) and per device.
3. **Performance score** — realized vs listed capacity averaged per dispatch event, per device, per zone, per fleet.
4. **Expected next-day dispatch** — uses tomorrow's PJM DA when ingested; falls back to most recent ingested DA.
5. **Historical records** — every prior event, filterable, drillable.

The goal is to **make the program design tangible to non-engineers** so a Dominion conversation can move past "could we?" to "here's what we'd see."

## 2. Non-goals (out of v1)

- **Auth / multi-tenant** — single-tenant demo, no login.
- **Real DER telemetry** — mocked; integration with a real M&V feed is a separate spec.
- **Operator actions** — no dispatch override, no opt-in/opt-out, no enrollment CRUD.
- **Notifications** — no email, no SMS, no PagerDuty hooks.
- **Mobile** — desktop / tablet only.
- **Sub-DA real-time** — DA only. RT (5-min) congestion is out.

## 3. Components

### 3.1 Backend (FastAPI service `dominion-api` on Cloud Run)

| Module | Purpose |
|---|---|
| `dominion_dispatch/zones.py` | Load `refdata/zones_dom.yaml`. Map pnode_id → zone_id. Aggregate stats per zone. |
| `dominion_dispatch/events.py` | Materialize events from `dominion_dispatch_device_hourly`: walk per (device, operating_date), emit contiguous non-normal blocks. Provide rollups (listed avg, realized avg, perf %). |
| `dominion_dispatch/telemetry_mock.py` | Deterministic per-(device, hour) realized-kW generator. Seeded so reloads return identical data. |
| `app/api/v1/dominion_admin_routes.py` | New REST surface under `/api/v1/dominion/admin/*`. Kept separate from existing `dominion_routes.py` to avoid coupling. |
| `app/models/dominion_admin.py` | SQLAlchemy ORM additions (just `listed_capacity_kw` column on `dominion_devices`). |
| `alembic/versions/k3l4m5n6o7p8_dominion_listed_capacity.py` | Migration. |
| `dominion_dispatch/refdata/zones_dom.yaml` | Zone taxonomy (id, label, pnode_ids). |

### 3.2 Frontend (Vue 3 SPA, no build)

Static files under `app/static/dominion_admin/`, mounted at `/dominion-admin/` in `app/main.py` alongside the existing `/dominion-demo/` mount.

| File | Role |
|---|---|
| `index.html` | Vue app root, Chart.js + Leaflet + Vue 3 + Alpine-free, all CDN. |
| `app.js` | Vue app: router (hash-based), shared state (zones, devices), API client. |
| `pages/Dashboard.vue.js` | Landing: hero banner, zone cards, fleet 24h chart, zone map, recent events strip. |
| `pages/EventDetail.vue.js` | KPIs, hourly chart (signal vs listed band vs realized bars), mini-map, per-zone + per-device tables. |
| `pages/DeviceDetail.vue.js` | Device KPIs, 30-day chart, recent events table. |
| `pages/History.vue.js` | Filters (zone, time range, has-mandatory, perf threshold), sortable event table, pagination/load-more. |
| `components/ZoneCard.vue.js` | Reusable zone summary card. |
| `components/DispatchChart.vue.js` | Chart.js wrapper for the program-signal vs capacity vs realized chart. |
| `components/ZoneMap.vue.js` | Leaflet wrapper with zone polygons (or pnode points) + device pins. |
| `components/PerfBar.vue.js` | Inline performance bar (color-graded green / amber / red). |
| `components/EventRow.vue.js` | Row used in dashboard recent-events strip and history table. |
| `styles.css` | Same dark theme as `/dominion-demo/`. |

### 3.3 URL routing

| URL | View |
|---|---|
| `/dominion-admin/` | Dashboard |
| `/dominion-admin/#/events/:event_id` | Event detail |
| `/dominion-admin/#/devices/:device_id_external` | Device detail |
| `/dominion-admin/#/history` | Event history |

Hash-based router so the static mount doesn't need server-side rewrites.

## 4. Data model changes

### 4.1 `dominion_devices.listed_capacity_kw` (new column)

```sql
ALTER TABLE dominion_devices
  ADD COLUMN listed_capacity_kw NUMERIC(10,2);
```

Seeded for the 6 demo devices via a one-off script (run via Cloud SQL Auth Proxy). Initial values:

| Device | kW |
|---|---|
| demo-bmtdom-001 (BLMNTDOM) | 600 |
| demo-hamiltn-001 (HAMILTN) | 600 |
| demo-braddock-001 (BRADDOCK) | 700 |
| demo-idylwoo4-001 (IDYLWOO4) | 500 |
| demo-tysons-001 (TYSONS) | 800 |
| demo-jeffrson-001 (JEFFRSON) | 600 |
| **Fleet total** | **3,800 kW (3.8 MW)** |

### 4.2 Zone taxonomy (`refdata/zones_dom.yaml`)

```yaml
zones:
  - id: loudoun-corridor
    label: "Loudoun corridor"
    description: "Loudoun County 230/500 kV substation group"
    pnode_ids: ["1348256193", "83734355"]
  - id: fairfax-230
    label: "Fairfax 230 kV"
    description: "Fairfax County 230 kV substation group"
    pnode_ids: ["34886155", "123900989", "34886435"]
  - id: alexandria
    label: "Alexandria"
    description: "Alexandria 230 kV substation group"
    pnode_ids: ["34886297"]
```

Loaded once at API startup; cached in module-level dict.

### 4.3 No new tables

Events and telemetry are derived, not stored. Trade-off documented in §6 and §7.

## 5. API surface

All endpoints under `/api/v1/dominion/admin/`. JSON in/out. Same FastAPI service, no auth.

### 5.1 `GET /zones`

Returns one row per zone with aggregates.

```jsonc
[
  {
    "id": "loudoun-corridor",
    "label": "Loudoun corridor",
    "device_count": 2,
    "listed_capacity_kw": 1200,
    "next_event_count_24h": 2,
    "last_event_perf_pct": 92.4
  },
  ...
]
```

### 5.2 `GET /zones/{zone_id}`

Single zone with its full pnode + device list and recent-event summary.

### 5.3 `GET /dashboard/today`

Headline + current-day forecast. Picks DA for tomorrow if ingested (after ~4 pm EPT day-of), else most recent ingested DA. Always labels which.

```jsonc
{
  "operating_date": "2026-04-19",
  "forecast_basis": "tomorrow_da",            // or "most_recent_da"
  "events_forecast": 2,
  "peak_program_kw": 3200,
  "peak_window_ept": ["14:00", "18:00"],
  "by_zone": [
    {"zone_id": "loudoun-corridor", "events": 2, "peak_kw": 1140},
    {"zone_id": "fairfax-230",      "events": 2, "peak_kw": 1660},
    {"zone_id": "alexandria",       "events": 0, "peak_kw": 0}
  ],
  "fleet_24h_signal": [{"hour_utc": "...", "program_signal": 0.0}, ...]
}
```

### 5.4 `GET /events`

Query params: `window_days` (1–365, default 30), `zone_id` (optional), `has_mandatory` (bool), `min_perf` (0–100), `device_id_external` (optional), `limit` (≤200), `offset`.

Returns paginated list of events sorted by start descending. Each row is per-device unless `aggregate=fleet` is passed.

```jsonc
{
  "window_start": "2026-03-19",
  "window_end":   "2026-04-17",
  "total":        184,
  "events": [
    {
      "event_id": "E-2026-04-17-demo-tysons-001-14",
      "device_id_external": "demo-tysons-001",
      "zone_id": "fairfax-230",
      "operating_date": "2026-04-17",
      "start_utc": "2026-04-17T18:00:00Z",
      "end_utc":   "2026-04-17T22:00:00Z",
      "duration_hours": 4,
      "stressed_hours": 2, "extreme_hours": 2,
      "has_mandatory": true,
      "listed_capacity_kw_avg":   800,
      "realized_capacity_kw_avg": 720,
      "performance_pct": 90.0,
      "mandatory_performance_pct": 96.2
    },
    ...
  ]
}
```

### 5.5 `GET /events/{event_id}`

Single event with hourly arrays (signal, listed band, realized) plus per-zone and per-device tables for fleet events.

### 5.6 `GET /devices/{device_id_external}/summary`

Query params: `window_days` (default 30), `recent_limit` (default 10).

```jsonc
{
  "device_id_external": "demo-tysons-001",
  "primary_pnode_id": "34886435",
  "primary_pnode_name": "TYSONS",
  "zone_id": "fairfax-230",
  "listed_capacity_kw": 800,
  "asset_lat": 38.9320, "asset_lon": -77.2369,
  "window_start": "2026-03-19", "window_end": "2026-04-17",
  "event_count": 14,
  "total_dispatch_hours": 27,
  "avg_performance_pct": 89.2,
  "mandatory_performance_pct": 94.1,
  "total_realized_energy_mwh": 19.2,    // sum(realized_kw)/1000 over dispatched hours
  "rank_in_fleet": 2,                    // 1 = best avg performance
  "recent_events": [ { ...event row... }, ... ]
}
```

## 6. Event materialization

Events are walked on-demand from `dominion_dispatch_device_hourly`. Algorithm in `events.py`:

```
For each (device_id_external, operating_date):
    hours = sorted by interval_start_utc, period_tier in {stressed, extreme}
    Group consecutive hours where interval_start_utc[i] - interval_start_utc[i-1] == 1h
    Each group = one event
    Compute:
      duration_hours = len(group)
      stressed_hours / extreme_hours = counts by tier
      has_mandatory = any extreme
      avg_program_signal = mean(program_signal_program)
      listed_capacity_kw_avg = device.listed_capacity_kw  (constant)
      realized_capacity_kw_avg = mean(telemetry_mock(device, hour) for hour in group)
      performance_pct = realized / listed * 100
      mandatory_performance_pct = mean(realized/listed) over extreme hours only
```

**Performance**: at 364 days × 6 devices × ~25 dispatch hrs/day = ~55K dispatch rows. Materializing all events is sub-second on Cloud SQL. Cache per-window in API process memory; invalidate on new ingest. If it gets slow with more devices, move to a materialized table.

**Fleet aggregation**: when the dashboard needs a "fleet event" (overlapping per-device events grouped), `events.py` provides a helper that merges by overlapping windows on the same operating_date.

## 7. Telemetry simulation

`telemetry_mock.py` exports `mock_realized_kw(device_id, hour_index_in_event, period_tier, listed_kw, dispatch_signal_program, event_start_date) -> float`.

Deterministic via `seed = hash((device_id_external, operating_date, hour_index_in_event))` so reloads on the same operating day return identical telemetry.

```
baseline       = DEVICE_BASELINE[device_id]            # see table below
zone_factor    = ZONE_PERFORMANCE[zone_id_for(device)] # see table below
duration_decay = max(0.6, 1.0 - 0.04 * max(0, hour_index_in_event - 1))
mandatory_bump = 0.05 if period_tier == 'extreme' else 0.0
ratio          = clamp(baseline * zone_factor * duration_decay + mandatory_bump, 0.50, 1.05)
noise          = normal(0, 0.03, seed)
ratio_noisy    = clamp(ratio + noise, 0.40, 1.10)
realized_kw    = listed_kw * dispatch_signal_program * ratio_noisy
```

**Device baselines**:

| Device | Baseline | Story |
|---|---|---|
| demo-bmtdom-001 | 0.94 | residential thermostat fleet |
| demo-hamiltn-001 | 0.91 | mixed residential |
| demo-jeffrson-001 | 0.92 | small steady residential |
| demo-tysons-001 | 0.88 | commercial mix |
| demo-idylwoo4-001 | 0.84 | older commercial |
| demo-braddock-001 | 0.78 | data center DR, opportunistic |

**Zone factors**:

| Zone | Factor | Story |
|---|---|---|
| loudoun-corridor | 1.00 | exurban residential, predictable |
| fairfax-230 | 0.92 | growing commercial / data center, more variable |
| alexandria | 0.97 | small sample, stable |

Effect across a 4-hr event: BLMNTDOM ≈ 92%, BRADDOCK ≈ 70–78%, fleet ≈ 85–90%. Long events (≥6h) show visible decay. Mandatory hours run ~5 pts above optional. Identical values across reloads.

## 8. Forecast methodology

`/dashboard/today` picks the operating-day basis as follows:

1. If a `dominion_da_ingestion_runs` row exists for (today + 1) with `status='success'` and `row_count > 0`, use it. Set `forecast_basis = "tomorrow_da"`.
2. Otherwise, use the most recent `success` run with rows. Set `forecast_basis = "most_recent_da"`.

The dashboard hero always labels which basis it's using. No statistical / ML forecast; we want the demo's accuracy claim to be "what PJM cleared."

## 9. Frontend pages (recap of mocks)

Mockups committed under `.superpowers/brainstorm/56219-1776575735/content/`:

- `landing-layout.html` — Dashboard layout A.
- `event-detail.html` — Event detail page.
- `secondary-pages.html` — Device detail and event history pages.

The implementation should match these mocks in structure and information density. Visual polish matches the existing `/dominion-demo/` dark theme.

## 10. Demo seeding

One-off script at `~/claude/outputs/tmp/dominion_admin_seed.py`:

1. `UPDATE dominion_devices SET listed_capacity_kw = ?` for each of 6 demo devices.
2. Confirm `refdata/zones_dom.yaml` is committed and present.

No data migration of existing dispatch rows required; events and telemetry are derived.

## 11. Testing

- **Backend unit tests** for `events.py` (boundary cases: 1-hour event, multi-hour event, full-day event, gap of 1 hour, multiple events per day, mixed stressed+extreme).
- **Backend unit tests** for `telemetry_mock.py` (determinism: same inputs → same output across calls; bounds: ratio always in [0.40, 1.10]).
- **Backend unit tests** for `zones.py` (each enrolled pnode maps to exactly one zone; aggregation totals match per-device sums).
- **API smoke tests** hitting each endpoint shape on the deployed Cloud Run service after deploy.
- **Frontend manual** verification by loading `/dominion-admin/` and walking each page. No automated UI tests in v1.

## 12. Deployment

Same path as the existing service:

1. Edit + commit on `feature/dominion-poc`.
2. `gcloud run deploy dominion-api --source . --region=us-central1` from the Dropbox working tree.
3. Run alembic upgrade against Cloud SQL via Cloud SQL Auth Proxy.
4. Run the seed script.
5. Smoke-test endpoints.

Existing env vars (DATABASE_URL, PJM_SUBSCRIPTION_KEY, CORS_EXTRA_ORIGINS) carry over.

## 13. Future work (explicit defer)

- Real DER telemetry feed (replaces `telemetry_mock.py`).
- Auth + multi-tenant (Cloud Run IAP + per-utility tenant scoping).
- Operator actions (force-call, force-skip, opt-in/opt-out).
- Notifications (event start, underperformance alerts).
- Sub-DA real-time congestion overlay.
- Statistical forecasts beyond DA (ML model trained on weather + historical).
- Mobile responsive layout.
- Per-utility / per-zone admin CRUD for taxonomy.
