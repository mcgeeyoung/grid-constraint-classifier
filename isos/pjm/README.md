# PJM Data Miner 2 driver

Implements the `isos.base.ISODriver` protocol for PJM, pulling day-ahead
hourly LMP rows from the Data Miner 2 REST API. Parallel to
`isos/caiso/`, `isos/nyiso/`, and `isos/miso/`.

## Files

| File | Purpose |
|------|---------|
| `client.py` | `PJMClient`: rate-limited HTTP layer with auto-pagination, `da_hrl_lmps` and `pnode` helpers. |
| `driver.py` | `PJMDriver`: ISODriver implementation. `fetch_da_hourly()` pulls one zone-day of LOAD pnodes and returns the canonical (pnode, hour) shape. |

## Endpoint & auth

- Base URL: `https://api.pjm.com/api/v1/` (verified live 2026-04-20).
- Auth: **subscription key** in the `Ocp-Apim-Subscription-Key` header.
  Provisioned via PJM's developer portal. Read from
  `PJM_SUBSCRIPTION_KEY` env var (also lives in `~/.zshrc.secrets`).
- Response format: JSON. Pages link via the `links[rel=next]` href.
- TLS: standard HTTPS.

## Feeds we use

| Feed | Endpoint | Called from |
|------|----------|-------------|
| DA hourly LMP | `da_hrl_lmps` | `PJMClient.query_lmps(...)` -> `PJMDriver.fetch_da_hourly()` |
| Pnode catalog | `pnode` | `PJMClient.query("pnode", ...)` -> `PJMDriver.list_load_nodes()` |

The legacy `query_pnodes()` helper points at `/pnodes` (plural) which
returns 404; `list_load_nodes()` calls `query("pnode", ...)` directly to
work around it. Don't reach for `query_pnodes` until that bug is fixed.

## Rate limiting

PJM's non-member tier enforces both a minimum-delay and a sliding-window
constraint, and `PJMClient` enforces both before every request:

- **Minimum delay:** 10s between consecutive requests.
- **Sliding window:** max 6 requests per 60s.
- **429 backoff:** 30s -> 60s -> 120s, then one final retry.

Practical implication: a full DOM zone-day (one `da_hrl_lmps` page at
`rowCount=50000`) is one request, so a single-day pull is fast. Multi-day
backfills should chunk by day and let the client throttle naturally.

## Response schema (`da_hrl_lmps`)

Columns we request via `fields=`:

```
datetime_beginning_ept,
pnode_id, pnode_name,
total_lmp_da, system_energy_price_da,
congestion_price_da, marginal_loss_price_da
```

PJM publishes hourly rows in **hour-beginning EPT**. The driver shifts to
hour-ending when emitting `hour_ending_ept` so the schema stays parallel
with CAISO/NYISO/MISO. A typical DOM-zone day at `lmp_type=LOAD` returns
several thousand rows (tens of LOAD pnodes x 24 hours).

Column mapping:

| PJM raw | Canonical |
|---------|-----------|
| `pnode_id` | `pnode_id_external` (cast to str) |
| `pnode_name` | `pnode_name` |
| `datetime_beginning_ept + 1h` | `hour_ending_ept` |
| `total_lmp_da` | `lmp_da` |
| `system_energy_price_da` | `energy_price_da` |
| `congestion_price_da` | `congestion_price_da` (no rename) |
| `marginal_loss_price_da` | `loss_price_da` |

## `list_load_nodes(pricing_zone)` semantics

The PJM `pnode` catalog uses `pnode_type` in `{BUS, AGGREGATE, LOCALE}`
and stores LOAD as a `pnode_subtype`. The driver returns every catalog
row where `zone == pricing_zone` and `pnode_subtype == "LOAD"`. Typical
results:

| Input | Returns |
|-------|---------|
| `"DOM"` | All Dominion-zone LOAD pnodes (the set the dispatch pilot draws from). |
| `"PEPCO"` | All PEPCO LOAD pnodes. |
| Unknown zone | `[]` (empty list, no error). |

For zone- or hub-level pricing (rather than load-bus) call
`PJMClient.query_lmps(..., lmp_type="ZONE", zone=...)` directly; the
driver's load-node convention deliberately mirrors the Dominion-pilot
data shape.

## `fetch_da_hourly(operating_date, pricing_zone)` behavior

1. Build a `M/D/YYYY 00:00toM/D/YYYY 23:00` window for the operating
   date (HE 1..24 == HB 0..23).
2. Call `query_lmps(lmp_type="LOAD", zone=pricing_zone, ...)` with the
   restricted `fields=` set above.
3. Rename PJM columns to the canonical schema, shift HB -> HE, cast
   `pnode_id` to string, coerce prices to float.
4. Return one row per (pnode, hour_ending_ept). Empty input -> empty
   canonical frame (7 columns, 0 rows).

## Gotchas

1. **Hour-beginning vs hour-ending** — PJM publishes HB EPT; the driver
   shifts +1h to emit HE. Spring-forward day has 23 rows per pnode,
   fall-back has 25.
2. **`/pnodes` 404** — the plural endpoint returns 404. Use `/pnode`
   (singular). `query_pnodes()` is broken; `list_load_nodes()` works
   around it.
3. **Subscription-key required** — unauthenticated calls return 401. The
   non-member key is fine for current pilot volume.
4. **Rate-limit silence** — the client logs but does not raise on
   throttle waits. A "stuck" multi-day backfill is usually waiting on
   the 60s sliding window, not hung.
5. **`pnode_id` is numeric in the JSON** — cast to string on the way out
   so the canonical schema stays string-keyed and matches CAISO/NYISO.
6. **Zone congestion can be zero** — `lmp_type="ZONE"` LOAD-zone rows
   often have `congestion_price_da == 0` even on a constrained day.
   Use `lmp_type="LOAD"` (bus-level LOAD pnodes) when congestion sign
   matters; that's also why the driver defaults to LOAD.
7. **Page cap** — `query()` defaults to `max_pages=20` at
   `rowCount=50000` per page, i.e. up to 1M rows per call. Single-day
   zone pulls fit in one page; chunk explicitly by day for backfills
   rather than raising the cap.

## Smoke-test output (2026-04-20)

Verified against DOM zone, DAM 2026-04-19 over the live Data Miner 2 feed:

| Call | Result |
|------|--------|
| `list_load_nodes("DOM")` | 1,667 LOAD pnodes (full DOM-zone LOAD catalog, e.g. `ACCA`, `ALTAVSTA13 KV`, `CARSON4 35 KV`). Catalog page = 23,480 rows across all PJM zones. |
| `fetch_da_hourly(date(2026,4,19), "DOM")` | 32,064 rows = 1,336 unique pnodes x 24 hour-ending slots. (DAM prices the active subset of LOAD pnodes on a given day; not every catalog pnode clears.) Schema matches canonical `OUTPUT_COLUMNS`. HE range 01:00 -> next-day 00:00 confirms the HB->HE shift. **Identity `lmp_da == energy_price_da + congestion_price_da + loss_price_da` holds to floating-point exact (max residual 0.000000) across all 32,064 rows.** |
| `fetch_da_hourly(date(2026,4,19), "NONEXISTENT_ZONE_XYZ")` | Empty canonical frame (7 columns, 0 rows). |

Offline verification of the column mapping and HE shift is in
`isos/pjm/driver.py::_to_canonical` — passing `pd.DataFrame` fixtures
through `_to_canonical` reproduces the canonical schema without an
HTTP round-trip. Live smoke-test script: `~/claude-tmp/pjm_smoke.py`.

## Reference

- Data Miner 2 portal: https://dataminer2.pjm.com/
- API spec & subscription-key signup:
  https://api.pjm.com/api/v1/
- DOM zone LOAD pnode catalog seed (in this repo):
  `dominion_dispatch/refdata/`
