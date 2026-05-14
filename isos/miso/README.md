# MISO market-reports driver

Implements the `isos.base.ISODriver` protocol for MISO, pulling day-ahead
LMP rows from the public market-reports CSV drops. Parallel to
`isos/pjm/`, `isos/caiso/`, and `isos/nyiso/`.

## Files

| File | Purpose |
|------|---------|
| `client.py` | `MISOClient`: HTTP fetcher for daily wide-format LMP CSVs (ExPost and ExAnte). |
| `driver.py` | `MISODriver`: ISODriver implementation. `fetch_da_hourly()` melts HE columns, pivots Value rows, and returns the canonical (pnode, hour) shape. |

## Endpoint & auth

- Base URL: `https://docs.misoenergy.org/marketreports` (verified live 2026-04-20).
- Auth: **none**. Public, no-key feed.
- Response format: plain CSV per day.
- TLS: standard HTTPS.

## Feeds we use

| Feed | URL pattern | Called from |
|------|-------------|-------------|
| DA LMP, ExPost | `YYYYMMDD_da_expost_lmp.csv` | `MISOClient.fetch_da_lmp_day(..., variant="expost")` |
| DA LMP, ExAnte | `YYYYMMDD_da_exante_lmp.csv` | `MISOClient.fetch_da_lmp_day(..., variant="exante")` |

**ExPost** is the authoritative post-clear price used for settlement and
should be the default for pilot math. **ExAnte** is the pre-clear price
offered into the market and is useful for forecast validation only.

## Response schema

The first four rows of each daily CSV are human prose
(`Day Ahead Market ExPost LMPs`, the operating date, a blank row, and a
timezone note). The actual header is on the fifth line:

```
Node, Type, Value, HE 1, HE 2, ..., HE 24
```

- `Node` — pnode name (e.g. `AECI.ALTW`, `MICHIGAN.HUB`, `AEP.PSGC1.AMP`).
- `Type` — one of `Gennode`, `Hub`, `Interface`, `Loadzone`.
- `Value` — one of `LMP`, `MCC` (congestion), `MLC` (loss).
- `HE 1..HE 24` — price in $/MWh for that hour-ending slot.

A typical day file is ~7,700 rows (2,500+ unique nodes × 3 values). We
derive the energy price at emit time: `energy = LMP - MCC - MLC`.

## Node-type counts (2026-04-19 sample)

| Type | Count |
|------|-------|
| Gennode   | 1,700 |
| Hub       | 414  |
| Interface | 46   |
| Loadzone  | 436  |
| **Total unique nodes** | **2,596** |

## `list_load_nodes(pricing_zone)` semantics

MISO loadzone names use a `PREFIX.SUBZONE` pattern. The driver treats
`pricing_zone` as the balancing-authority prefix and returns every
`Loadzone` row whose Node starts with `{pricing_zone}.` (or equals
`{pricing_zone}` exactly). Examples:

| Input | Returns |
|-------|---------|
| `"AECI"` | 3 loadzones: `AECI.ALTW`, `AECI.AMMO`, `AECI.CWLD` |
| `"CONS"` | All `CONS.*` loadzones (DTE / Consumers Energy service territory) |
| `"MICHIGAN.HUB"` | `[]` from `list_load_nodes` (not a loadzone). Use `fetch_da_hourly` directly for hub pulls. |

## `fetch_da_hourly(operating_date, pricing_zone)` behavior

1. Prefix scan: filter `Type == "Loadzone"` and Node starts-with
   `{pricing_zone}.` (or equals exactly). If any rows match, return them
   melted + pivoted.
2. Exact-Node fallback: if the prefix scan is empty, match `Node ==
   pricing_zone` (any Type). This lets callers pull a single hub or
   interface by name without a second code path.
3. Unknown input: returns an empty canonical frame (not an error).

## Gotchas

1. **Timezone is EST, year-round** — the daily CSV states explicitly:
   `All Hours-Ending are Eastern Standard Time (EST)`. MISO does not
   shift to EDT in summer. We emit `hour_ending_ept` to match the
   schema used by the PJM/CAISO drivers, but the underlying clock is
   EST. Consumers crossing DST boundaries should treat this column as
   EST and convert explicitly rather than inferring from the name.
2. **Header rows must be skipped** — `pd.read_csv(..., skiprows=4)` is
   required. The first four lines are prose; row five is the header.
3. **Congestion sign** — MISO uses the standard convention: positive
   `MCC` means congestion cost at that pnode (buyer pays more). Same
   sign as PJM, CAISO, NYISO's raw feed. No flip applied.
4. **ExPost vs ExAnte** — the public archive keeps both. ExPost is the
   settled price and is the correct choice for pilot revenue math.
   ExAnte is the cleared price; using it for settlement will drift.
5. **Blank trailing rows** — some files end with one or two blank
   lines; the client filters `Node.isna()` defensively.
6. **Backfill cadence** — `docs.misoenergy.org/marketreports/` holds
   several years of daily files. No separate monthly zip equivalent
   (unlike NYISO) is needed.

## Smoke-test output (2026-04-20)

Verified against DAM 2026-04-19 over the live HTTPS feed:

| Call | Result |
|------|--------|
| `MISOClient.fetch_da_lmp_day(...)` | 7,788 rows × 27 cols. Types: 5,100 Gennode / 1,308 Loadzone / 1,242 Hub / 138 Interface (each × LMP/MCC/MLC). |
| `list_load_nodes("AECI")` | 3 NodeMetas: `AECI.ALTW`, `AECI.AMMO`, `AECI.CWLD`. |
| `fetch_da_hourly(date(2026,4,19), "AECI")` | 72 rows = 3 loadzones × 24 HE. All 7 columns non-null. |
| `fetch_da_hourly(date(2026,4,19), "MICHIGAN.HUB")` | 24 rows via exact-Node fallback. `lmp - energy - congestion - loss` residual = 0 exactly. |
| `fetch_da_hourly(date(2026,4,19), "NONEXISTENT_ZONE_XYZ")` | Empty canonical frame (7 columns, 0 rows). |
| System-lambda cross-check | At HE 2, `AECI.ALTW.energy = 26.82` and `MICHIGAN.HUB.energy = 26.82` (identical across pnodes, as expected for a single-reference-bus market). |

## Reference

- MISO market reports catalog:
  https://www.misoenergy.org/markets-and-operations/market-reports/
- Day-ahead LMP field definitions:
  https://cdn.misoenergy.org/Market%20Data%20Manual%20-%20Market%20Reports79017.pdf
- Loadzone and hub map:
  https://www.misoenergy.org/markets-and-operations/
