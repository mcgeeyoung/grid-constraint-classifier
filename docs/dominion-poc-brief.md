# Dominion DER Program — Proof of Concept Brief

**Audience:** Dominion Energy stakeholders  
**Purpose:** Describe what is being demonstrated, how the deployed application works, and how it could support operational thinking around day-ahead (DA) congestion and dispatch signals.

---

## 1. What this proof of concept is

This proof of concept (PoC) shows an **end-to-end technical path** from **PJM day-ahead market data** to **per-device, per-hour dispatch guidance** for distributed energy resources (DERs) enrolled in a **Dominion Virginia Power (DOM)** settlement context.

It is **not** a production operations system. It is a **working slice** intended to:

- Show how **DA congestion prices at PJM pricing nodes (pnodes)** can be joined to **enrolled DERs** mapped to those (or neighboring) pnodes.
- Illustrate a **two-tier dispatch posture**: optional intensity during **stressed** grid periods and **mandatory** full response during **extreme** periods—both derived from the same DA congestion signal family you already use in planning analytics.
- Provide a **browser-based demo** so stakeholders can trigger a fresh PJM pull, inspect results, and visualize dispatch intensity over time.

The PoC aligns with the idea that **nodal DA congestion** is an observable, repeatable input that can be combined with **program rules** (curves, neighbors, time-of-day policy) to produce a transparent **dispatch schedule** tied to a specific market snapshot.

---

## 2. Why PJM DOM and pnodes matter for Dominion DER

In PJM, **Dominion Virginia Power** load is settled in the **DOM** commercial zone. Day-ahead **hourly node LMPs** include a **congestion component** (`congestion_price_da`) at each **pricing node**. For a DER program, that congestion is a practical proxy for **when and where the DA market is pricing binding transmission / overload risk** at the node level.

The PoC therefore:

- Pulls **DA hourly node LMPs for zone DOM** (LOAD-type nodes, consistent with retail/load settlement geography).
- Associates each enrolled device with a **primary pnode** (and optional **ordered neighbor pnodes** if the primary is missing in a given hour).
- Converts resolved congestion into a **dispatch signal** using a **piecewise curve** defined per device (program design parameter).

---

## 3. What we built (three layers)

### A. Data layer (authoritative store)

- **Cloud SQL for PostgreSQL** holds:
  - **Ingestion runs** — one row per PJM pull (operating date, zone, LMP type, status, row counts, timestamps for provenance).
  - **Hourly node rows** — pnode, interval (UTC), congestion and related LMP components for that run.
  - **Enrollment** — devices with primary pnode, optional neighbors, optional asset location for maps, effective dates, and piecewise curves.
  - **Dispatch schedule** — per device, per hour: raw vs resolved congestion, resolution strategy, raw signal, **period tier** (normal / stressed / extreme), **mandatory flag**, and **program signal** (the intensity actually recommended after policy).

### B. Application programming interface (API)

- **Google Cloud Run** hosts a **FastAPI** service that exposes REST endpoints to:
  - Trigger **ingest** for a chosen operating date (live PJM call, then persist).
  - List **ingestion runs** and **active devices**.
  - **Rebuild** the dispatch schedule for a run and **query** hourly rows for charts.
  - Render an **asset / pnode map** (Folium HTML) for spatial context.

### C. Demo surface (optional but intended for meetings)

- **Static web content** (for example on **Google Cloud Storage**) loads a small **interactive dashboard** in the browser.
- That page calls the **HTTPS Cloud Run API** (cross-origin, with explicit CORS configuration).
- Charts show **resolved DA congestion** alongside the **program dispatch signal** after stressed/extreme policy.

---

## 4. How the application works (conceptual flow)

1. **Enroll devices** in the database with a **primary pnode id** (and optional **neighbor pnode ids** in priority order), **effective dates**, and a **piecewise curve** mapping congestion dollars per MWh to a normalized dispatch signal.
2. For a selected **operating day**, the system **fetches PJM DA hourly node LMPs** for **DOM** and stores them under a new **ingestion run id** (idempotent per day/zone/LMP type unless a “replace” path is used).
3. For that run, the **dispatch engine** walks each device and each hour in the snapshot:
   - Reads **congestion** at the primary pnode; if missing, walks **neighbors** until a value is found or marks the hour as missing.
   - Applies the device **piecewise curve** to produce a **raw dispatch signal**.
4. A **period policy** then classifies each hour:
   - **Normal** — program signal intensity treated as **zero** for dispatch purposes (no dispatch call).
   - **Stressed** — congestion magnitude exceeds a **fixed dollar-per-MWh floor** (PoC default aligned with historical classifier-style stress). Dispatch is **optional**: program signal is a **fraction** of the raw signal (configurable).
   - **Extreme** — congestion magnitude exceeds a **per-device, per-day tail threshold** (PoC default: high quantile of the day’s absolute congestion, floored at the stress threshold). Dispatch is **mandatory**: program signal equals the **full** raw signal for that hour.
5. Optional **peak window** for stressed-only hours (e.g. business-peak HE in Eastern Prevailing Time) can be enabled so **stressed** response is limited to peak while **extreme** still applies any hour of the day—useful if you want optional curtailment concentrated in high-load periods.

**Interpretation for stakeholders:** the PoC separates **“should consider”** (stressed / optional) from **“must execute”** (extreme / mandatory) while keeping a **single transparent congestion trace** per device-hour.

---

## 5. What Dominion would see in a demo

Typical walkthrough:

1. **Ingest** — Pick a recent operating date; the system pulls PJM and shows run id, row count, and timestamps.
2. **Enrollment table** — Active devices, primary pnode, optional asset label.
3. **Rebuild dispatch** — Computes schedule rows for that run and persists them.
4. **Chart** — For a selected device (or aggregate view), shows **resolved congestion** vs **program signal** after policy; summary counts show how many hours fell into **normal / stressed / extreme** and how many hours are **mandatory**.
5. **Asset map** — Opens a map linking **physical asset** coordinates (when provided) to **primary pnode** locations for intuitive geography.

---

## 6. Scope boundaries (important)

| In scope for PoC | Out of scope (examples) |
|------------------|-------------------------|
| DA congestion–driven schedule generation | Real-time SCADA control, telemetry loop closure |
| DOM zone, PJM Data Miner–style pulls | Full market simulation, co-optimization with energy bids |
| Transparent rules (thresholds, quantiles, curves) | Regulatory filing or tariff language |
| Cloud-hosted API + optional static UI | Customer billing, settlement reconciliation, ADR with end devices |

The PoC **does not** send commands to field equipment. It produces a **reference schedule and intensity** that a future operational stack could consume (for example via your existing vendor platforms), subject to program design and regulatory review.

---

## 7. How this could inform a future operating model (illustrative)

If Dominion chose to move beyond PoC, a plausible path would be:

1. **Freeze program parameters** — stress floor, extreme quantile, stressed fraction, peak window, neighbor lists, and curves—under change control.
2. **Daily job** — after DA clears, run **ingest → rebuild**; archive ingestion run ids for audit.
3. **Downstream integration** — map `dispatch_signal_program` and `dispatch_mandatory` to whatever interface your DERMS / aggregator / program operator requires (file, API, message bus).
4. **Monitoring** — dashboards on ingestion success, row counts, missing pnode rates, and distribution of tier counts across the fleet.

None of the above is committed by the PoC; it is a **conversation starter** grounded in working software.

---

## 8. Glossary (short)

| Term | Meaning |
|------|--------|
| **DA** | Day-ahead (PJM cleared auction before the operating day). |
| **DOM** | PJM commercial load zone for Dominion Virginia Power. |
| **Pnode** | Pricing node at which PJM publishes LMP components. |
| **Congestion price** | DA LMP congestion component at the node ($/MWh). |
| **Ingestion run** | One immutable snapshot of PJM data stored for traceability. |
| **Resolved congestion** | Congestion used after primary / neighbor resolution logic. |
| **Program signal** | Intensity after period policy (what the PoC recommends for dispatch messaging). |

---

## 9. Document control

| Field | Value |
|-------|--------|
| **Artifact** | Technical + product brief for external stakeholder meeting |
| **Repository** | `grid-constraint-classifier` (Dominion dispatch module + API + static demo) |
| **Contact** | WattCarbon project lead (update with name and email before distribution) |

*This brief describes intent and architecture. Production use would require Dominion security review, vendor alignment, and program-specific legal and operational approval.*

---

## 10. Internal deployment references (WattCarbon)

Engineering runbooks for Cloud SQL, Cloud Run, and GCS static demo live under the repository **`deploy/`** directory (for example `deploy/cloud-sql-postgres-setup.txt`, `deploy/cloud-run-dominion.txt`, `deploy/dominion-gcs.txt`). Those files are **not** required reading for Dominion stakeholders; they support operators deploying the PoC.
