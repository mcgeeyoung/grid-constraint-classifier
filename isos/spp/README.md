# SPP file-browser driver

Implements the `isos.base.ISODriver` protocol for SPP (Southwest Power
Pool), pulling day-ahead hourly LMP rows from the public file-browser
API on portal.spp.org. Parallel to `isos/pjm/`, `isos/caiso/`,
`isos/nyiso/`, `isos/miso/`, and `isos/isone/`.

## Files

| File | Purpose |
|------|---------|
| `client.py` | `SPPClient`: HTTP fetcher for the public file-browser API. Day-ahead LMP and latest-RTBM helpers. |
| `driver.py` | `SPPDriver`: ISODriver implementation. `fetch_da_hourly()` returns the canonical (settlement_location, hour) shape. `list_load_nodes()` resolves system hubs / entity prefixes / exact SL names. |

## Endpoint & auth

- Base URL: `https://portal.spp.org/file-browser-api/download` (verified live 2026-04-20).
- Auth: **none**. Public, no-key. SPP also offers an authenticated
  Marketplace Portal (SOAP) for member-only data and offer submission;
  none of that is needed for read-only price analysis.
- Response format: plain CSV per day. Daily DA LMP file is ~4 MB
  / ~37,920 rows.
- Retention: SPP keeps several years of daily files in the
  `By_Day` tree; very old data may be in monthly zips under the same
  feed root.
- WAF: portal.spp.org is fronted by a WAF that occasionally rejects
  default `requests` UAs. The client sends a browser-like UA
  defensively.

## Feeds we use

| Feed | Endpoint | Path pattern |
|------|----------|--------------|
| DA hourly LMP, by Settlement Location | `da-lmp-by-settlement-location` | `/{YYYY}/{MM}/By_Day/DA-LMP-SL-{YYYYMMDD}0100.csv` |
| RTBM 5-min LMP, latest snapshot | `rtbm-lmp-by-location` | `/RTBM-LMP-SL-latestInterval.csv` (helper only; not used by the protocol path) |

The `0100` suffix on the DA filename is a SPP filename quirk -- the
daily file already contains all 24 HE slots for that operating date.
There is **no** "latest" variant for the day-ahead file; you must pass
a specific operating date.

The endpoint id is `da-lmp-by-settlement-location` (not the shorter
`da-lmp-by-location` form that appears in some older docs -- that
endpoint 404s).

## Response schema (DA LMP CSV)

Columns:

```
Interval, GMTIntervalEnd, BAA, Settlement Location, Pnode,
LMP, MLC, MCC, MEC
```

| Column | Notes |
|--------|-------|
| `Interval` | Hour-ending in **Central Prevailing Time**. Follows DST. |
| `GMTIntervalEnd` | Same instant in GMT (useful for DST-safe joining). |
| `BAA` | Balancing-authority code. Mostly `SPP`; some rows tagged `SWPW`. |
| `Settlement Location` | The user-facing pricing point. ~1,580 distinct values per day. |
| `Pnode` | The underlying physical pnode that backs the SL (often differs from SL name; not used by the canonical schema). |
| `LMP` | Total $/MWh. |
| `MLC` | Marginal Loss Component. |
| `MCC` | Marginal Congestion Component. |
| `MEC` | Marginal Energy Component. |

Identity holds exactly: `LMP == MEC + MCC + MLC` (verified 0.000000
residual across all 37,920 rows of DAM 2026-04-19).

## Hubs and entities

SPP does not publish "load zones" in the PJM/ISO-NE sense; settlement
locations and hubs are the canonical priced points. Two SPP-wide
system hubs are the standard reference prices:

| Settlement Location | Notes |
|---------------------|-------|
| `SPPSOUTH_HUB` | South-region system hub. The reference price most contracts settle against in the SPP South footprint. |
| `SPPNORTH_HUB` | North-region system hub. |

Per-entity sub-hubs and SLs follow naming conventions. A few of
interest:

| Prefix | Approximate territory |
|--------|-----------------------|
| `KCPL.*` / `KCPLHUB*` | Kansas City Power & Light (now Evergy Metro). 40 SLs as of 2026-04-19. |
| `WR*` / `WRHUB*` | Westar (now Evergy West). |
| `OPPD.*` | Omaha Public Power. |
| `LES_*` / `LES.*` | Lincoln Electric System. |
| `NPPD.*` | Nebraska Public Power District. |
| `OMPA*` | Oklahoma Municipal Power Authority. |
| `WAUE.*` | WAPA Upper Great Plains. |

## `list_load_nodes(pricing_zone)` semantics

| Input | Returns |
|-------|---------|
| `"SPP"` | All ~1,580 settlement locations. |
| `"SPPSOUTH"` / `"SPP_SOUTH"` / `"SOUTH"` | `SPPSOUTH_HUB` (1 row). |
| `"SPPNORTH"` / `"SPP_NORTH"` / `"NORTH"` | `SPPNORTH_HUB` (1 row). |
| Exact SL name (e.g. `"SPPSOUTH_HUB"`, `"KCPL.HAW10"`) | That single SL. |
| Prefix (e.g. `"KCPL"`, `"WR"`, `"OPPD"`) | Every SL whose name starts with the prefix followed by `.`, `_`, a digit, or `HUB`. |
| Anything else | `[]`. |

Prefix matching is regex-anchored to avoid accidental mid-string hits
(e.g. `"WR"` matches `WRHUB24` but not `MIDWREL.X`).

Snapshots the catalog from yesterday's daily file because SPP does not
publish a standalone catalog endpoint.

## `fetch_da_hourly(operating_date, pricing_zone)` behavior

1. Download `/{YYYY}/{MM}/By_Day/DA-LMP-SL-{YYYYMMDD}0100.csv`.
2. Build the SL catalog from the day file, apply the `pricing_zone`
   matching rules above to pick the SLs to keep.
3. Return one row per (settlement_location, hour_ending_ept) with the
   canonical column set. `Interval` is parsed as a naive datetime and
   emitted as `hour_ending_ept` (see timezone caveat below).
4. Unknown pricing_zone or missing day file: empty canonical frame
   (no error).

## Gotchas

1. **Endpoint name typo in some docs** -- use
   `da-lmp-by-settlement-location` (the shorter `da-lmp-by-location`
   404s for DA). RT uses `rtbm-lmp-by-location`. Do not assume
   parallelism.
2. **`0100` filename suffix** -- daily file is named with `0100`
   appended even though it covers all 24 HE slots. Do not treat it as
   an hour-of-day index.
3. **Timezone is Central Prevailing Time, not EPT** -- the canonical
   output column is named `hour_ending_ept` for schema parity with the
   other ISO drivers, but the underlying clock is CPT and follows DST.
   Cross-reference `GMTIntervalEnd` if you need a DST-safe absolute
   timestamp. The MISO driver uses the same naming convention; the
   docstring on `SPPDriver` repeats the warning.
4. **Daily file is ~4 MB** -- a year backfill is ~365 requests at
   ~4 MB each (~1.5 GB). Sequential pulls take ~5 s each through the
   WAF; expect ~30 minutes for a year. There is no monthly-zip
   shortcut for recent dates (older years sometimes have monthly
   archives in the same tree).
5. **No native catalog** -- `list_load_nodes` snapshots yesterday's
   daily file. If the catalog query fires before the daily file
   publishes, fall back to passing the pricing_zone through to
   `fetch_da_hourly` directly with a known good prior date.
6. **WAF behavior** -- portal.spp.org occasionally rate-limits or
   returns transient 403s under heavy use. The client logs and raises;
   add retries / backoff at the caller for production backfills. (The
   protocol-level driver intentionally stays thin.)
7. **`Pnode` vs `Settlement Location`** -- the SL is the pricing
   point most contracts reference; the underlying `Pnode` (e.g. `SOUC`
   behind `AEC`) is provided for traceability but the canonical schema
   uses Settlement Location as both `pnode_id_external` and
   `pnode_name`.
8. **`BAA` column is mostly SPP** -- a small number of rows are tagged
   `SWPW` (Southwest Power Pool West, the WEIS area). They are
   included in the SL catalog but the BAA value flows through to the
   `NodeMeta.zone` field for traceability.

## Smoke-test output (2026-04-20)

Verified against DAM 2026-04-19 over the live HTTPS feed:

| Call | Result |
|------|--------|
| `client.fetch_da_lmp_day(date(2026,4,19))` | 37,920 rows x 9 cols. |
| `list_load_nodes("SPPSOUTH")` | 1 NodeMeta -> `SPPSOUTH_HUB`. |
| `list_load_nodes("SPPNORTH")` | 1 NodeMeta -> `SPPNORTH_HUB`. |
| `list_load_nodes("KCPL")` | 40 NodeMetas (Evergy/KCP&L territory). |
| `list_load_nodes("BOGUSZONE")` | `[]`. |
| `fetch_da_hourly(date(2026,4,19), "SPPSOUTH")` | 24 rows, single hub. HE range `01:00 -> next-day 00:00` CPT. |
| `fetch_da_hourly(date(2026,4,19), "KCPL")` | 960 rows = 40 SLs x 24 HE. |
| `fetch_da_hourly(date(2026,4,19), "SPP")` | 37,920 rows = 1,580 SLs x 24 HE. **Identity `lmp_da == energy_price_da + congestion_price_da + loss_price_da` holds exactly (max residual 0.000000) across all 37,920 rows.** |
| `fetch_da_hourly(date(2026,4,19), "NONEXISTENT_ZONE_XYZ")` | Empty canonical frame. |

Live smoke-test script: `~/claude-tmp/spp_smoke.py`.

## Reference

- SPP file-browser portal: https://portal.spp.org/
- SPP Markets Public Data Guide (canonical catalog of public files):
  https://www.spp.org/documents/37657
- Integrated Marketplace External Stakeholder Data Points:
  https://www.spp.org/documents/56542
- gridstatus reference implementation:
  https://github.com/gridstatus/gridstatus/blob/main/gridstatus/spp.py
- ArcGIS price-contour map (geospatial alternative, not used here):
  https://pricecontourmap.spp.org/arcgis/rest/services/MarketMaps/RTBM_FeatureData/MapServer/1/query
