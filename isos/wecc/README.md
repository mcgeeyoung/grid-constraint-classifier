# WECC OASIS driver

Implements the `isos.base.ISODriver` protocol for the broader WECC
region (the EIM/EDAM-participating BAAs), pulling day-ahead aggregate
prices from CAISO OASIS via the `DGAP_<BAA>` APnodes. Shares the
HTTP layer with `isos/caiso/` (both wrap `CAISOClient`).

This is the **regional** view. For in-CAISO LAP-level pricing
(PG&E / SCE / SDG&E SLAPs and DLAPs) use `isos/caiso/` instead.

## Files

| File | Purpose |
|------|---------|
| `baas.py` | `WECC_BAAS` registry (23 BAAs), aliases, CAISO-internal-label redirect rules. |
| `driver.py` | `WECCDriver`: ISODriver implementation. `list_load_nodes()` resolves BAA codes/aliases to DGAPs. `fetch_da_hourly()` batches across the OASIS 10-node cap. |

There is no `wecc/client.py` -- the driver wraps the existing
`isos.caiso.client.CAISOClient`. (Backoff and 429-retry live there;
CAISODriver and WECCDriver both benefit.)

## Coverage: 23 WECC BAAs

| Code | Utility / BAA | Common aliases |
|------|---------------|----------------|
| `CISO` | California ISO (control area) | -- |
| `BANC` | Balancing Authority of Northern California | `SMUD` |
| `TIDC` | Turlock Irrigation District | `TURLOCK` |
| `LADWP` | Los Angeles DWP | `LA_DWP` |
| `PACE` | PacifiCorp East | `PACIFICORP_EAST` |
| `PACW` | PacifiCorp West | `PACIFICORP_WEST` |
| `PGE` | **Portland General Electric** (Oregon) | `PORTLAND`, `PGE_OR` |
| `AVA` | Avista | `AVISTA` |
| `PSEI` | Puget Sound Energy | `PUGET` |
| `SCL` | Seattle City Light | `SEATTLE_CL` |
| `TPWR` | Tacoma Power | `TACOMA` |
| `BPAT` | Bonneville Power Administration | `BPA`, `BONNEVILLE` |
| `BCHA` | BC Hydro Authority | `BC_HYDRO`, `BCHYDRO` |
| `IPCO` | Idaho Power | `IDAHO_POWER` |
| `NWMT` | NorthWestern Energy MT | `NORTHWESTERN_MT` |
| `NEVP` | NV Energy / Nevada Power | `NV_ENERGY`, `NVE` |
| `AZPS` | Arizona Public Service | `APS` |
| `SRP`  | Salt River Project | `SALT_RIVER` |
| `TEPC` | Tucson Electric Power | `TUCSON`, `TEP` |
| `PNM`  | Public Service of New Mexico | `PUBLIC_SERVICE_NM` |
| `EPE`  | El Paso Electric | `EL_PASO` |
| `WALC` | WAPA Lower Colorado | `WAPA_LC` |
| `AVRN` | Avangrid Renewables | `AVANGRID` |

## Endpoint & auth

Same as CAISO OASIS. See `isos/caiso/README.md` for endpoint, auth,
zip parsing, 31-day window cap, and rate-limit details. WECCDriver
benefits from the same client backoff (5 s min interval; 10/30/60 s
retry on 429/5xx).

## `list_load_nodes(pricing_zone)` semantics

| Input | Returns |
|-------|---------|
| `"WECC"` (or empty) | All 23 BAAs as `NodeMeta(pnode_type="DGAP")`. |
| BAA code (e.g. `"PACE"`, `"BANC"`, `"AZPS"`) | 1 DGAP. |
| Alias (e.g. `"SMUD"`, `"BPA"`, `"BC_HYDRO"`, `"PACIFICORP_EAST"`, `"PORTLAND"`) | 1 DGAP. |
| `"PG&E"` / `"PGAE"` / `"SCE"` / `"SDGE"` / `"SDG&E"` | **Raises `ValueError`** with a CAISODriver redirect hint. |
| Anything else | `[]`. |

The catalog is a static registry compiled from a 2026-04 snapshot of
OASIS `ATL_APNODE`. Adding a BAA requires editing `baas.py` -- there
is no live catalog refresh. (CAISO's published BAA list is stable
quarter-to-quarter; checking `ATL_APNODE` for `APNODE_TYPE=DASP` rows
is how to verify.)

## `fetch_da_hourly(operating_date, pricing_zone)` behavior

1. Resolve `pricing_zone` to a list of `BAAEntry`s (1 for a single BAA,
   23 for `"WECC"`).
2. Build a UTC-midnight 1-day window for `operating_date`.
3. Batch the DGAP node ids in groups of 10 (OASIS cap), make one
   `PRC_LMP` call per batch. The client's 5 s min interval handles
   pacing; expect ~3 calls and ~15 s for a full WECC pull.
4. Pivot OASIS `LMP_TYPE` rows (`LMP`/`MCE`/`MCC`/`MCL`) into the
   canonical price columns. Emit `hour_ending_ept` from `OPR_HR`.
5. Empty canonical frame on 0 matches or all-empty responses.

## Gotchas

1. **PGE collision (Portland General vs California PG&E)** -- the
   biggest footgun. `pricing_zone="PGE"` here is **Portland General
   Electric** (Oregon, BAA code `PGE`). California PG&E is a CAISO
   internal LAP, not a WECC external BAA; query it via
   `CAISODriver` with `pricing_zone="DLAP_PGAE-APND"`. The driver
   raises with a redirect hint if you pass `"PG&E"`, `"PGAE"`,
   `"SCE"`, `"SDGE"`, or `"SDG&E"`.
2. **Some BAA DGAPs do not publish DA prices.** As of DAM 2026-04-18,
   `DGAP_PACE-APND` and `DGAP_PACW-APND` (PacifiCorp) return an
   OASIS error 1000 to PRC_LMP queries -- they are EIM (RT) participants
   with no DA price published through this report yet. The driver
   treats this as "no data" and skips the BAA in the output rather
   than raising. A whole-WECC pull on that date returns 21 of 23 BAAs.
3. **UTC-window operating-date drift** -- inherited from CAISODriver.
   The PPT operating date does not align with a UTC-midnight window.
   `operating_date=2026-04-18` produces hour-ending values 18..24 then
   1..17, all stamped 2026-04-18 in `hour_ending_ept`. For pilot use
   this is fine; production ingest should pass PPT-midnight aligned UTC
   timestamps (07:00 UTC PST, 08:00 UTC PDT) when operating-date
   semantics matter.
4. **Energy-component identity has float noise** -- CAISO publishes
   `MCE` (energy) directly rather than deriving it. Identity
   `lmp = energy + cong + loss` holds to ~1e-5, not exact (compare
   PJM/MISO/ISO-NE/SPP which sum exactly).
5. **OASIS response is gzipped XML on errors** -- CAISOClient parses
   the error page as a 19-row "DataFrame" with one column. The driver
   detects this via the missing `MW`/`NODE` columns in
   `_to_canonical` and returns an empty canonical frame. Logs may
   show 200 OK with garbage payload.
6. **Per-utility queries == one BAA's `pricing_zone`** -- there are no
   per-utility driver subclasses (`PACEDriver`, `IPCODriver`, etc.).
   `WECCDriver.fetch_da_hourly(date, "PACE")` is the per-utility
   "connector"; one extra string parameter beats 23 driver classes.

## Smoke-test output (2026-04-20)

Verified against DAM 2026-04-18 over the live OASIS feed:

| Call | Result |
|------|--------|
| `list_load_nodes("WECC")` | 23 NodeMetas. |
| `list_load_nodes("BANC")` / `"SMUD"` | Both -> `DGAP_BANC-APND`. |
| `list_load_nodes("BPA")` / `"BPAT"` | Both -> `DGAP_BPAT-APND`. |
| `list_load_nodes("PG&E")` | Raises `ValueError` with CAISODriver hint. |
| `fetch_da_hourly(date(2026,4,18), "BANC")` | 24 rows, canonical schema, identity residual ~1e-5. |
| `fetch_da_hourly(date(2026,4,18), "WECC")` | 504 rows = **21** BAAs x 24 HE (PACE and PACW returned no DA data on this date; see gotcha 2). 3 OASIS calls in ~15 s. |
| `fetch_da_hourly(date(2026,4,18), "NONEXISTENT_BAA")` | Empty canonical frame. |

Live smoke-test script: `~/claude-tmp/wecc_smoke.py`.

## Reference

- CAISO OASIS interface spec v5.1.2:
  https://www.caiso.com/Documents/OASIS-InterfaceSpecification_v5_1_2Clean_Fall2017Release.pdf
- WEIM (Western Energy Imbalance Market) participant map:
  https://www.westerneim.com/Pages/About/QuickFacts.aspx
- EDAM (Extended Day-Ahead Market) status:
  https://www.caiso.com/initiative/extended-day-ahead-market/
- Companion CAISO driver: `isos/caiso/README.md`
