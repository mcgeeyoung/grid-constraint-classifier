# ISO-NE static-CSV driver

Implements the `isos.base.ISODriver` protocol for ISO New England,
pulling day-ahead hourly LMP rows from the public daily-CSV archive on
iso-ne.com. Parallel to `isos/pjm/`, `isos/caiso/`, `isos/nyiso/`, and
`isos/miso/`.

## Files

| File | Purpose |
|------|---------|
| `client.py` | `ISONEClient`: HTTP fetcher for the daily DA LMP CSV with C/H/D/T record-type handling. |
| `driver.py` | `ISONEDriver`: ISODriver implementation. `fetch_da_hourly()` returns the canonical (pnode, hour) shape. `list_load_nodes()` snapshots the eight ISO-NE load zones. |

## Endpoint & auth

- Base URL: `https://www.iso-ne.com/static-transform/csv/histRpts/da-lmp` (verified live 2026-04-20).
- Auth: **none**. Public, no-key. The interactive download button on the
  ISOExpress page hides behind a CAPTCHA, but the underlying static CSV
  URL serves directly with a browser-like User-Agent.
- Response format: plain CSV per day (~2.5 MB, ~29k rows).
- Retention: ISO-NE keeps the last seven years of daily files. There is
  no monthly zip equivalent; backfill loops by day.

## Feeds we use

| Feed | URL pattern | Called from |
|------|-------------|-------------|
| DA hourly LMP | `WW_DALMP_ISO_YYYYMMDD.csv` | `ISONEClient.fetch_da_lmp_day(date)` |

(There is also a "Hourly Day-Ahead with Preliminary RT" feed at a
similar path; we don't read it. The clean DA LMP file above is the
authoritative settlement price.)

## Response schema

The daily file mixes four record types in one CSV. Each row's first
column is a literal `"C"`, `"H"`, `"D"`, or `"T"` marker:

| Marker | Meaning | Width | Count |
|--------|---------|-------|-------|
| `C` | Comment / header prose | 2 cols | 4 lines (title, filename, report-for, generated-at) |
| `H` | Column header rows | 10 cols | 2 lines (column names, then column data types) |
| `D` | Data row | 10 cols | ~29,060 lines (~1,210 locations x 24 HE) |
| `T` | Trailer (line count) | 2 cols | 1 line at end |

Data-row columns:

```
"D", Date, Hour Ending, Location ID, Location Name, Location Type,
     Locational Marginal Price, Energy Component, Congestion Component,
     Marginal Loss Component
```

`Location Type` is one of `HUB`, `HUB NODE`, `LOAD ZONE`, `NETWORK
NODE`, `EXT. NODE`, `DRRAZ`. Names use ISO-NE's dotted-prefix
convention: `.Z.<zone>` for load zones, `.H.<hub>` for hubs, `.I.<x>`
for interfaces, plant-style names (e.g. `UN.FRNKLNSQ13.810CC`) for
network nodes.

`Hour Ending` is `01..24` in hour-ending EPT. The driver converts to a
naive datetime by adding HE hours to the operating date (HE 24 = next
day 00:00). DST days have 23 (spring-forward) or 25 (fall-back) HE
slots per location.

## Load zones

Eight ISO-NE load zones with stable PTIDs:

| PTID | Canonical name | Notes |
|------|----------------|-------|
| 4001 | `.Z.MAINE` | Maine |
| 4002 | `.Z.NEWHAMPSHIRE` | New Hampshire |
| 4003 | `.Z.VERMONT` | Vermont |
| 4004 | `.Z.CONNECTICUT` | Connecticut |
| 4005 | `.Z.RHODEISLAND` | Rhode Island |
| 4006 | `.Z.SEMASS` | Southeast Massachusetts |
| 4007 | `.Z.WCMASS` | West/Central Massachusetts |
| 4008 | `.Z.NEMASSBOST` | Northeast Mass / Boston |

The internal hub `.H.INTERNAL_HUB` (PTID 4000) is also reliably
present; pull it via the exact-name fallback in `fetch_da_hourly`.

## `list_load_nodes(pricing_zone)` semantics

| Input | Returns |
|-------|---------|
| `"ISONE"` (or empty) | All eight LOAD ZONE rows. |
| `"MAINE"` / `"WCMASS"` / `"NEMASSBOST"` | Single zone via case-insensitive suffix match against the `.Z.` name. |
| `".Z.MAINE"` | Single zone via full name match. |
| `"4007"` | Single zone via exact PTID match. |
| Anything else | `[]`. |

Snapshots the catalog from yesterday's daily file because ISO-NE does
not publish a standalone catalog endpoint.

## `fetch_da_hourly(operating_date, pricing_zone)` behavior

1. Download `WW_DALMP_ISO_YYYYMMDD.csv` for `operating_date`.
2. If `pricing_zone` matches one or more LOAD ZONE rows (per the rules
   above), return those zones x 24 HE.
3. Exact-name fallback: if no LOAD ZONE matches, look for a row whose
   `Location Name` equals `pricing_zone` exactly. This lets callers
   pull a hub or network node by its full ISO-NE name without a second
   code path.
4. Unknown input or 404 day file: empty canonical frame (no error).

## Gotchas

1. **Mixed record-type column** — pandas's column-count inference picks
   2 from the first `"C"` row and discards every wider row. The client
   pre-filters to lines that start with `"D"` before parsing; do not
   reach for `pd.read_csv(..., on_bad_lines="skip")` as a shortcut, it
   silently throws away the data rows.
2. **CAPTCHA on the interactive page only** — the `static-transform/`
   CSV URL serves directly. A default `requests` User-Agent works in
   practice, but the client sends a browser UA defensively in case the
   CDN tightens.
3. **Hour-ending native** — unlike NYISO (hour-beginning), ISO-NE
   publishes HE directly. No shift required.
4. **Energy is published, not derived** — the `Energy Component`
   column is included verbatim. We don't recompute it from `LMP - cong
   - loss` even though they sum exactly today, so any future
   rounding-asymmetry would stay sourced rather than computed.
5. **Per-day calls, no monthly zip** — backfills loop by day. ISO-NE
   keeps seven years of files, so a year-long pull is 365 requests at
   ~2.5 MB each (~900 MB).
6. **`location_id` is numeric in the CSV** — cast to string on the way
   out so the canonical schema stays string-keyed and matches the other
   ISO drivers.
7. **No standalone catalog endpoint** — `list_load_nodes` snapshots
   yesterday's daily file. If yesterday's file is missing (rare), pass
   an explicit working day via constructor or fall back to the eight
   PTIDs hard-coded above.

## Smoke-test output (2026-04-20)

Verified against DAM 2026-04-18 over the live HTTPS feed:

| Call | Result |
|------|--------|
| `client.fetch_da_lmp_day(date(2026,4,18))` | ~29,064 D rows x 9 cols. ~1,210 unique locations across 5 location types. |
| `list_load_nodes("ISONE")` | 8 NodeMetas, PTIDs 4001-4008. |
| `list_load_nodes("MAINE")` | 1 NodeMeta, `.Z.MAINE` PTID 4001. |
| `list_load_nodes("4007")` | 1 NodeMeta, `.Z.WCMASS`. |
| `list_load_nodes("BOGUSZONE")` | `[]`. |
| `fetch_da_hourly(date(2026,4,18), "ISONE")` | 192 rows = 8 zones x 24 HE. All 7 canonical columns populated. HE range `01:00 -> next-day 00:00`. **Identity `lmp_da == energy_price_da + congestion_price_da + loss_price_da` holds exactly (max residual 0.000000) across all 192 rows.** |
| `fetch_da_hourly(date(2026,4,18), "NEMASSBOST")` | 24 rows, single zone. |
| `fetch_da_hourly(date(2026,4,18), ".H.INTERNAL_HUB")` | 24 rows via exact-name fallback. |
| `fetch_da_hourly(date(2026,4,18), "NONEXISTENT_ZONE_XYZ")` | Empty canonical frame. |

Live smoke-test script: `~/claude-tmp/isone_smoke.py`.

## Reference

- DA LMP report page (interactive):
  https://www.iso-ne.com/isoexpress/web/reports/pricing/-/tree/lmps-da-hourly
- ISO-NE Web Services (auth-required, alternate JSON/XML feed):
  https://www.iso-ne.com/participate/support/web-services-data
- Web Services REST docs (v1.1):
  https://webservices.iso-ne.com/docs/v1.1/
- Zone map (8 load zones):
  https://www.iso-ne.com/about/key-stats/maps-and-diagrams
