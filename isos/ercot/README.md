# ERCOT public-API driver

Implements the `isos.base.ISODriver` protocol for ERCOT, pulling
day-ahead hourly Settlement Point Prices from the public REST API at
`api.ercot.com`. Parallel to `isos/pjm/`, `isos/caiso/`, `isos/nyiso/`,
`isos/miso/`, `isos/isone/`, `isos/spp/`, and `isos/wecc/`.

## Files

| File | Purpose |
|------|---------|
| `client.py` | `ERCOTClient`: OAuth ROPC flow + REST helpers. Caches bearer token (1h TTL, 5min refresh margin). |
| `driver.py` | `ERCOTDriver`: ISODriver implementation. Hub-derived congestion (Option B). |

## Endpoint & auth

ERCOT is the **only ISO in this package that requires authentication**.
The public-reports gateway needs both a bearer token (OAuth ROPC) and
a developer subscription key on every request:

| Credential | Source | Env var read by `_ercot_factory` |
|------------|--------|----------------------------------|
| Username   | apiexplorer.ercot.com signup | `ERCOT_API_USERNAME` |
| Password   | same | `ERCOT_API_PASSWORD` |
| Subscription key | developer.ercot.com signup | `ERCOT_API_SUBSCRIPTION_KEY` |

OAuth flow (Azure B2C, ROPC):

```
POST https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/
     B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token
     grant_type=password & username & password &
     scope=openid <client_id> offline_access &
     client_id=fec253ea-0d06-4272-a5e6-b478baeecd70 &
     response_type=id_token
```

Returns `access_token` (1h TTL) + `refresh_token`. The client caches
and auto-refreshes 5 minutes before expiry; one-shot 401s during a
window race trigger a single retry with a fresh token.

API base: `https://api.ercot.com/api/public-reports`.

## Feeds we use

| Feed | Endpoint | Called from |
|------|----------|-------------|
| DAM Settlement Point Prices | `np4-190-cd/dam_stlmnt_pnt_prices` | `ERCOTClient.fetch_dam_spp_day(date)` |

(`np4-183-cd/dam_hourly_lmp` — bus-level DAM LMPs — is **not** used
by `fetch_da_hourly`. SPs are the canonical priced points for
contracts; bus LMPs are a few orders of magnitude more rows and serve
a different question. The endpoint can be added to `ERCOTClient` if
needed.)

A full DAM SPP day is ~26,304 rows (~1,096 SPs x 24 HE). With
`page_size=30000` it fits in one HTTP call; the client walks pagination
defensively if a future schema bump grows the day past 30k rows.

## Schema mapping (Option B: hub-derived congestion)

ERCOT publishes total Settlement Point Prices only -- no MEC/MCC/MCL
split. The canonical 4-column schema is filled like this:

| Canonical column | ERCOT source | Note |
|------------------|--------------|------|
| `lmp_da` | SPP for the requested SP | total Settlement Point Price |
| `energy_price_da` | SPP for `HB_HUBAVG` (per hour) | reference hub average across HB_NORTH/SOUTH/HOUSTON/WEST/PAN |
| `congestion_price_da` | `lmp_da - energy_price_da` | derived; equals what ERCOT analysts call "basis" |
| `loss_price_da` | `0.0` | ERCOT is a lossless market by design |

Identity `lmp_da == energy_price_da + congestion_price_da + loss_price_da`
holds **exactly** by construction (no rounding noise).

`HB_HUBAVG` itself naturally yields `congestion_price_da == 0` since
it is its own reference.

This is the same decomposition the spec the user pasted recommends
("congestion_at_node = RN_LMP - HB_HUBAVG"). It is **not** the
official ERCOT settlement decomposition (no such thing exists for
ERCOT) -- it's a useful approximation that maps cleanly onto the
schema used by the other ISO drivers.

## ERCOT settlement-point namespace

| Prefix | Type | Count (2026-04-18) | Examples |
|--------|------|---------------------|----------|
| `LZ_*` | Load Zone | 8 | `LZ_HOUSTON`, `LZ_NORTH`, `LZ_SOUTH`, `LZ_WEST`, `LZ_AEN`, `LZ_CPS`, `LZ_LCRA`, `LZ_RAYBN` |
| `HB_*` | Hub | 7 | `HB_HOUSTON`, `HB_NORTH`, `HB_SOUTH`, `HB_WEST`, `HB_PAN`, `HB_HUBAVG`, `HB_BUSAVG` |
| `DC_*` | DC tie | 4 | `DC_E` (East), `DC_L` (Laredo), `DC_N`, `DC_R` |
| (no prefix) | Resource Node | 1,077 | `7RNCHSLR_ALL`, `A4_DGR1_RN`, ... |

## `list_load_nodes(pricing_zone)` semantics

Case-insensitive matching:

| Input | Returns |
|-------|---------|
| `"ERCOT"` (or empty) | All 8 `LZ_*` load zones. |
| Hub alias (`HOUSTON`, `NORTH`, `SOUTH`, `WEST`, `PAN`, `PANHANDLE`, `HUBAVG`, `BUSAVG`) | The matching `HB_*` SP. |
| Load-zone alias (`AEN`, `AUSTIN`, `CPS`, `LCRA`, `RAYBN`, `RAYBURN`, `HOUSTON_LZ`, etc.) | The matching `LZ_*` SP. |
| Exact SP name (`LZ_HOUSTON`, `HB_NORTH`, `DC_E`, `7RNCHSLR_ALL`) | That SP if it appears in yesterday's catalog snapshot. |
| Anything else | `[]`. |

There is no standalone settlement-point catalog endpoint, so the
driver snapshots from yesterday's day file (one `np4-190-cd` call).
The cost is one full-day pull (~3 MB / ~1 sec).

## `fetch_da_hourly(operating_date, pricing_zone)` behavior

1. Resolve `pricing_zone` to a set of SP names (per the rules above).
2. Pull the full DAM SPP file for `operating_date` (one
   `np4-190-cd` call -- no per-SP server-side filter; cheaper to
   filter in-memory on the full day).
3. Always include `HB_HUBAVG` in the in-memory subset, even if not
   requested, so the energy-component derivation has its reference.
4. Pivot, derive `congestion_price_da` and set `loss_price_da = 0.0`,
   return rows for the requested SPs only.
5. `pricing_zone` doesn't match anything -> empty canonical frame.

## Gotchas

1. **Auth required, not optional** -- unlike every other driver in
   this package, ERCOT needs a username + password + subscription key.
   `get_driver("ERCOT")` raises `RuntimeError` with the missing-vars
   list if any of the three env vars is unset.
2. **Hub-derived congestion is an approximation, not a settlement
   decomposition.** ERCOT does not publish MCC/MCE/MLC. If a downstream
   consumer needs an authoritative congestion figure (e.g. for CRR
   settlement), they should pull NP4-191-CD (DAM Shadow Prices at
   binding constraints) directly via the client and compute against
   transmission element shadow prices, not against `HB_HUBAVG`.
3. **`loss_price_da` is `0.0`, not `NaN`.** ERCOT is a lossless market
   (no Marginal Loss Component published anywhere). Treat zero as a
   real value, not a missing one.
4. **`hourEnding` is a `HH:MM` string** valued `01:00` ... `24:00` in
   Central Prevailing Time. The driver parses the leading `HH` and
   adds it to `operating_date`, so `24:00` correctly becomes the next
   day's `00:00` in `hour_ending_ept`. The MISO/SPP convention of
   keeping the column name `hour_ending_ept` for schema parity even
   though the underlying clock is CPT applies here too.
5. **DST is not modeled.** ERCOT publishes a `DSTFlag` boolean to
   disambiguate the duplicated 02:00 hour on fall-back day. The
   current driver drops the flag and (on fall-back day) collapses the
   two `HE 02:00` rows into one `hour_ending_ept` value via the
   `hourEnding` parse alone -- a duplicate timestamp that can hash
   the wrong way in downstream merges. Production ingest should
   propagate `DSTFlag` and use it to add a half-hour offset on
   fall-back day. Spring-forward day naturally skips HE 03 with no
   special handling.
6. **OAuth tokens are 1h** -- the client refreshes 5 minutes before
   expiry and retries once on a 401 race. For very long-running
   processes (multi-day backfills), this is transparent.
7. **Per-SP server-side filter exists but is unused** -- the
   `np4-190-cd` endpoint accepts a `settlementPointName` query
   parameter, but pulling the whole day is cheaper than 8+ filtered
   calls and gives us `HB_HUBAVG` for free in the same response.
8. **Bus-level LMPs are a separate report** -- if you need bus-level
   resolution (`np4-183-cd/dam_hourly_lmp`), the client doesn't
   currently expose it. ~tens of thousands of buses per day; out of
   scope for the canonical SP-level schema.

## Smoke-test output (2026-04-20)

Verified against DAM 2026-04-18 over the live API:

| Call | Result |
|------|--------|
| OAuth ROPC token | 200, `access_token` length 1056, `expires_in=3600`. |
| `client.fetch_dam_spp_day(date(2026,4,18))` | 26,304 rows in 1 page. 1,096 unique SPs (8 LZ + 7 HB + 4 DC + 1,077 RN). |
| `list_load_nodes("ERCOT")` | 8 NodeMetas (`LZ_AEN`, `LZ_CPS`, `LZ_HOUSTON`, `LZ_LCRA`, `LZ_NORTH`, `LZ_RAYBN`, `LZ_SOUTH`, `LZ_WEST`). |
| `list_load_nodes("HOUSTON")` | 1 NodeMeta -> `HB_HOUSTON` (HUB). |
| `list_load_nodes("AUSTIN")` | 1 NodeMeta -> `LZ_AEN`. |
| `list_load_nodes("BOGUSZONE")` | `[]`. |
| `fetch_da_hourly(date(2026,4,18), "HB_HOUSTON")` | 24 rows, canonical schema, **identity residual 0.000000 by construction**, HE range `01:00 -> next-day 00:00`. |
| `fetch_da_hourly(date(2026,4,18), "HB_HUBAVG")` | 24 rows, `congestion_price_da == 0` everywhere (energy reference). |
| `fetch_da_hourly(date(2026,4,18), "ERCOT")` | 192 rows = 8 LZ x 24 HE. Mean LMPs span `LZ_WEST` $13.89 -> `LZ_HOUSTON` $29.33 (typical west-wind discount pattern). |
| `fetch_da_hourly(date(2026,4,18), "NONEXISTENT_XYZ")` | Empty canonical frame. |

Live smoke-test script: `~/claude-tmp/ercot_smoke.py`.

## Reference

- API explorer: https://apiexplorer.ercot.com/
- Developer portal (subscription keys): https://developer.ercot.com/
- Public-reports OpenAPI: https://api.ercot.com/api/public-reports
- ERCOT Public Data on MIS (legacy, no auth): https://mis.ercot.com/misapp/GetReports.do
- gridstatus reference implementation:
  https://github.com/gridstatus/gridstatus/blob/main/gridstatus/ercot.py
