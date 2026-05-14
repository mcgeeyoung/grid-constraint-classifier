# NYISO MIS driver

Implements the `isos.base.ISODriver` protocol for NYISO, pulling day-ahead
LBMP rows from the public MIS CSV drops. Parallel to `isos/pjm/` and
`isos/caiso/`.

## Files

| File | Purpose |
|------|---------|
| `client.py` | `NYISOClient`: HTTP fetcher for daily CSVs and monthly zip archives. |
| `driver.py` | `NYISODriver`: ISODriver implementation. `fetch_da_hourly()` returns the canonical (pnode, hour) shape. Also exposes `fetch_da_hourly_buses()` for generator-bus pulls. |

## Endpoint & auth

- Base URL: `http://mis.nyiso.com/public/csv` (verified live 2026-04-20).
- Auth: **none**. Public, no-key feed.
- HTTP (not HTTPS); MIS does not 302 to HTTPS, plain `http://` is the documented URL.
- Response format: plain CSV per day, monthly zip archives for backfill.

## Feeds we use

| Feed | URL pattern | Called from |
|------|-------------|-------------|
| DA LBMP, zonal (15 names) | `damlbmp/YYYYMMDDdamlbmp_zone.csv` | `NYISOClient.fetch_da_lbmp_day(..., feed="zone")` |
| DA LBMP, generator bus (~700) | `damlbmp/YYYYMMDDdamlbmp_gen.csv` | `NYISOClient.fetch_da_lbmp_day(..., feed="gen")` |
| DA LBMP, monthly zip (zone) | `damlbmp/YYYYMM01damlbmp_zone_csv.zip` | `NYISOClient.fetch_da_lbmp_month(..., feed="zone")` |
| DA LBMP, monthly zip (gen) | `damlbmp/YYYYMM01damlbmp_gen_csv.zip` | `NYISOClient.fetch_da_lbmp_month(..., feed="gen")` |

## Response schema (daily CSV)

Both the `_zone` and `_gen` daily files share this layout:

```
Time Stamp, Name, PTID,
LBMP ($/MWHr),
Marginal Cost Losses ($/MWHr),
Marginal Cost Congestion ($/MWHr)
```

A typical day-ahead zonal file is 360 rows: 15 names × 24 hours. The
generator file is ~18,000 rows (~700 pnodes × 24). Energy price is
derived: `energy = LBMP - losses - congestion`.

## Zones we return from `list_load_nodes`

Only the 11 NYISO load zones are treated as load nodes. The zonal CSV
also contains four external proxy generators, which we deliberately
exclude from `list_load_nodes` since they are not NYISO load pricing:

| Canonical name | PTID | Notes |
|----------------|------|-------|
| CAPITL | 61757 | Albany / Capital District |
| CENTRL | 61754 | Central NY |
| DUNWOD | 61760 | Lower Hudson / Dunwoodie |
| GENESE | 61753 | Genesee / Rochester |
| HUD VL | 61758 | Hudson Valley |
| LONGIL | 61762 | Long Island (LIPA) |
| MHK VL | 61756 | Mohawk Valley |
| MILLWD | 61759 | Millwood |
| N.Y.C. | 61761 | NYC proper (Zone J) |
| NORTH  | 61755 | North Country |
| WEST   | 61752 | Western NY / Buffalo |

The proxy names we ignore: `H Q` (Hydro Quebec), `NPX` (New England),
`O H` (Ontario Hydro), `PJM`.

## Gotchas

1. **Hour-beginning vs hour-ending** — NYISO publishes `Time Stamp` in
   hour-beginning EPT (`00:00..23:00`). The canonical output uses
   hour-ending, so the driver adds one hour when emitting
   `hour_ending_ept`. DST days will have 23 (spring-forward) or 25
   (fall-back) rows per zone; upstream ingest should tolerate.
2. **Congestion sign** — The raw CSV uses the same convention as
   PJM/CAISO: positive congestion = cost at the sink. The driver does
   **not** flip the sign. The older `adapters/nyiso_adapter.py` flipped
   it when going through `gridstatus`, but that was correcting for a
   `gridstatus` inversion, not the MIS CSV itself. If downstream tools
   expect the NYISO-native convention (negative = cost at sink), flip
   at the ingest layer.
3. **Zone name spellings** — Three of the eleven names contain spaces
   or punctuation: `HUD VL`, `MHK VL`, `N.Y.C.`. We match case- and
   whitespace-sensitively against NYISO's canonical forms.
4. **Catalog latency** — NYISO does not publish a standalone pnode
   catalog feed. `NYISOClient.list_zone_ptids()` reads a daily zonal
   CSV and deduplicates to build the 15-row catalog. Defaults to
   yesterday's file to avoid mid-publish races on today's.
5. **Monthly zips** — NYISO's monthly archives are `YYYYMM01..._csv.zip`
   (first-of-month stamp). The archive contains one CSV per day in the
   month. Concatenation preserves per-day ordering but you must dedupe
   on `(Name, Time Stamp)` if calling on a month that has been patched.
6. **No load-bus pricing** — NYISO only publishes generator-bus pricing
   in the public feeds; there is no load-bus or sub-zonal equivalent
   to PJM's LOAD pnodes or CAISO's SLAPs. Use the zone for load, the
   generator feed for asset-level reference.

## Smoke-test output (2026-04-20)

Verified against DAM 2026-04-19 over the live HTTP MIS feed:

| Call | Result |
|------|--------|
| `list_load_nodes("CAPITL")` | 1 NodeMeta, PTID `61757`. |
| `list_load_nodes("H Q")` | `[]` (proxy correctly excluded). |
| `fetch_da_hourly(date(2026,4,19), "N.Y.C.")` | 24 rows, all 7 columns non-null, `lmp = energy + congestion + loss` holds exactly. |
| Round-trip all 11 load zones | 264 rows = 11 × 24. |
| `fetch_da_hourly_buses(date(2026,4,19), [...])` | 48 rows = 2 gen pnodes × 24. |

## Reference

- NYISO MIS (Market Information System):
  http://mis.nyiso.com/public/
- Market & Operational Data (file catalog):
  https://www.nyiso.com/custom-reports
- Zone map (Load Zones A–K):
  https://www.nyiso.com/documents/20142/1397960/nyca_zonemaps.pdf
