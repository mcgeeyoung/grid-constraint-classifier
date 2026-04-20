# CAISO OASIS driver

Implements the `isos.base.ISODriver` protocol for CAISO, fetching day-ahead LMP
rows from the public OASIS API. Parallel to `isos/pjm/`, which handles PJM Data
Miner 2.

## Files

| File | Purpose |
|------|---------|
| `client.py` | `CAISOClient`: HTTP layer, zip/CSV parsing, PRC_LMP fetcher, catalog fetchers. |
| `driver.py` | `CAISODriver`: ISODriver implementation. `fetch_da_hourly()` returns the canonical (pnode, hour) shape used by the rest of the app. |

## Endpoint & auth

- Base URL: `https://oasis.caiso.com/oasisapi` (verified live 2026-04-20).
- Auth: **none**. Public, no-key API.
- Response format: every endpoint returns a zip. We always request
  `resultformat=6` (CSV); the zip contains one `.csv` file.
- HTTP to HTTPS: OASIS 302-redirects `http://` to `https://`, so we hit
  HTTPS directly and leave `allow_redirects=True`.

## Queries we use

| Report | queryname | Called from |
|--------|-----------|-------------|
| Day-ahead hourly LMP | `PRC_LMP` with `market_run_id=DAM&version=1` | `CAISOClient.fetch_da_lmp()` |
| APNODE catalog (DLAPs, SLAPs, trading hubs) | `ATL_APNODE` | `CAISOClient.list_apnodes()` |
| Full PNODE catalog (bus-level nodes) | `ATL_PNODE` with `Pnode_type=ALL` | `CAISOClient.list_pnodes()` |

## 31-day window cap

OASIS enforces a **hard 31-day window** on `PRC_LMP` queries (error code 1004
if exceeded). `CAISOClient.fetch_da_lmp()` raises `ValueError` on over-wide
windows so the caller can chunk its own loop rather than silently losing
tail data. For multi-year backfills, chunk by calendar month (31-day max).

The catalog queries (`ATL_APNODE`, `ATL_PNODE`) also require `startdatetime`/
`enddatetime`, but the payload is reference data and doesn't vary by date.
We pass a 1-day window ending at `utcnow()` for both.

## Response schema (PRC_LMP CSV)

Columns returned:

```
INTERVALSTARTTIME_GMT, INTERVALENDTIME_GMT,
OPR_DT, OPR_HR, OPR_INTERVAL,
NODE_ID_XML, NODE_ID, NODE,
MARKET_RUN_ID,
LMP_TYPE,           # LMP | MCC | MCL | MCE | MGHG
XML_DATA_ITEM,      # LMP_PRC | LMP_CONG_PRC | LMP_LOSS_PRC | LMP_ENE_PRC | LMP_GHG_PRC
PNODE_RESMRID,
GRP_TYPE,
POS, MW, GROUP
```

Price is in the `MW` column (naming inherited from CAISO's unified settlement
schema). A 1-day single-node pull returns 120 rows: 24 hours x 5 components
(LMP total, MCC congestion, MCL loss, MCE energy, MGHG GHG adder). The
research notes list 4 components; in practice we see 5 on current-day data.
The driver pivots the 4 canonical components into columns and ignores MGHG
(not modeled by the downstream ingest yet).

## Gotchas

1. **HTTP to HTTPS redirect** — follow redirects (default for `requests`).
2. **Rate limiting** — OASIS has no published QPS, but practical guidance is
   ~1 request per 5-10 seconds. Expect occasional 5xx; retry with exponential
   backoff. We do *not* yet wire in backoff at the client layer. The Dominion
   ingest's outer loop should sleep between per-pnode calls (see
   `isos/pjm/client.py` for the pattern we will likely mirror).
3. **Timezone** — boundary timestamps are GMT (`YYYYMMDDTHH:MM-0000`).
   Response `OPR_DT`/`OPR_HR` are in Pacific Prevailing Time (PPT), which
   shifts with DST. `OPR_HR` uses hour-ending 1..24. DST-fall-back day has
   a hour 25 (repeated HE03); DST-spring-forward day skips HE03.
4. **UTC-boundary operating-date drift** — `CAISODriver.fetch_da_hourly()`
   uses a UTC-midnight window for the given `operating_date`. Because PPT is
   UTC-7 / UTC-8, a UTC-midnight window maps to PPT HE17-HE16 across two
   trade dates. For pilot smoke-tests this is fine; production ingest should
   pass PPT-midnight aligned UTC timestamps (07:00 UTC PST, 08:00 UTC PDT)
   when the operating date semantics matter.
5. **Error 1000 on unknown pnode IDs** — CAISO returns a zip containing an
   XML error payload, which the CSV parser still reads as a 19-row "file"
   (the XML lines). Check `"LMP_TYPE" in df.columns` to detect real LMP data.
6. **Pilot ID drift** — `METCALF_2_N101` (from prior research) is not a
   valid OASIS pnode; it returned error 1000. Corrected to `METCALF_1_N018`
   on 2026-04-19 after checking ATL_PNODE; `METCALF_1_N018` is CB-eligible
   and returns 120 rows/day in DAM. Pilot JSON at
   `~/claude/outputs/tmp/pge-pilot-6.json` has been updated in place.
7. **Node list vs APNODE list** — `ATL_PNODE` is ~21k bus-level nodes;
   `ATL_APNODE` is ~2,500 aggregated pricing nodes (DLAPs/SLAPs/hubs). Use
   APNODE when the caller wants zone-level pricing, PNODE for bus-level
   precision. Pilot uses bus-level pnodes for parity with the Dominion pilot.
8. **10-node cap per call** — OASIS caps `node=` at 10 comma-separated
   values per request (error 1017 if exceeded). The client raises
   `ValueError` before the HTTP call. Loop over pnodes for bigger batches.

## Smoke-test output (2026-04-19)

Verified against DAM 2026-04-15:

| Pnode | Rows | Notes |
|-------|------|-------|
| `DLAP_PGAE-APND` | 120 | DLAP, works as expected. |
| `METCALF_1_N018` | 120 | Substituted for `METCALF_2_N101`. |
| `MISSION_6_N001` | 120 | SF urban. |
| `OAKLND3_7_N001` | 120 | East Bay. |
| `BELMONT_1_N001` | 120 | Peninsula. |
| `PANOCHE_7_N001` | 120 | Central Valley / Path 15. |
| `FULTON_2_B1` | 120 | North Bay. `_B1` suffix confirmed correct. |

`CAISODriver.fetch_da_hourly(date(2026, 4, 15), "DLAP_PGAE-APND")` returned
24 rows with the 7 canonical columns (`pnode_id_external`, `pnode_name`,
`hour_ending_ept`, `lmp_da`, `energy_price_da`, `congestion_price_da`,
`loss_price_da`), all non-null.

## Reference

- Interface spec v5.1.2 (Fall 2017):
  https://www.caiso.com/Documents/OASIS-InterfaceSpecification_v5_1_2Clean_Fall2017Release.pdf
- Prior-research notes: `~/claude/outputs/tmp/caiso-oasis-notes.md`
- PG&E sub-LAP map: https://www.pge.com/assets/pge/docs/save-energy-and-money/energy-savings-programs/PGE-SubLap.pdf
