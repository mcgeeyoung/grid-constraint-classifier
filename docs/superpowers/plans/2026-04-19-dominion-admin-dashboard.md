# Dominion Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dominion-facing admin dashboard at `/dominion-admin/` that shows zonal day-ahead forecast, listed capacity, per-event performance score, expected next-day dispatch, and historical events. Demo prop, not production.

**Architecture:** New FastAPI admin routes under `/api/v1/dominion/admin/` plus a Vue 3 SPA served at `/dominion-admin/`. Zone taxonomy in YAML refdata. Events materialized on-demand from existing `dominion_dispatch_device_hourly` rows. Telemetry mocked deterministically per (device, operating_date, hour_index). One new column (`listed_capacity_kw`) on `dominion_devices`. Coexists with the existing `/dominion-demo/` engineering walkthrough.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy · Alembic · psycopg2 · PyYAML · pytest · Vue 3 (CDN) · Chart.js · Leaflet · Cloud Run · Cloud SQL Postgres 16.

**Design spec:** `docs/superpowers/specs/2026-04-18-dominion-admin-dashboard-design.md`.

**Working directory:** `/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier` (branch `main`, tracks `github feature/dominion-poc`).

**Deployment target:** Cloud Run service `dominion-api`, project `wattcarbon-internal`, region `us-central1`. Cloud SQL instance `dominion-demo-db` (connection name `wattcarbon-internal:us-central1:dominion-demo-db`).

**Common environment values for local scripts:**

```bash
REPO="/Users/mcgeesmini/WattCarbon Dropbox/McGee Young/Claude/grid-constraint-classifier"
PY="$REPO/.venv/bin/python"
DSN='postgresql://appuser:eqgnNxhAQS84qN7PKK1HQCYDjQy9C47b@127.0.0.1:5434/gridclass'
BASE=https://dominion-api-558972293204.us-central1.run.app
```

Start Cloud SQL Auth Proxy once per session when the plan says "ensure proxy running":

```bash
pgrep -f "cloud-sql-proxy wattcarbon-internal:us-central1:dominion-demo-db --port=5434" > /dev/null \
  || (cloud-sql-proxy wattcarbon-internal:us-central1:dominion-demo-db --port=5434 >/tmp/csp.log 2>&1 &)
sleep 3
```

---

## Phase A: Test scaffolding + zone taxonomy

### Task A1: Add pytest + tests directory

**Files:**
- Modify: `requirements.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/dominion_dispatch/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add pytest to requirements.txt**

Append these two lines to `requirements.txt`:

```text
pytest>=8.0
pytest-asyncio>=0.23
```

- [ ] **Step 2: Install into venv**

```bash
"$PY" -m pip install 'pytest>=8.0' 'pytest-asyncio>=0.23'
"$PY" -m pytest --version
```

Expected: prints `pytest 8.x.x`.

- [ ] **Step 3: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers
```

- [ ] **Step 4: Write `tests/__init__.py` and `tests/dominion_dispatch/__init__.py`**

Both files: empty (just create them).

- [ ] **Step 5: Write `tests/conftest.py`**

```python
"""Shared fixtures for dominion_dispatch unit tests."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

- [ ] **Step 6: Smoke-run pytest**

```bash
cd "$REPO" && "$PY" -m pytest -q
```

Expected: `no tests ran` with exit code 5 (pytest's "no tests collected"). That's fine for an empty scaffold.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini tests/__init__.py tests/dominion_dispatch/__init__.py tests/conftest.py
git commit -m "chore: add pytest scaffold for dominion admin work"
```

---

### Task A2: Zone taxonomy YAML + loader

**Files:**
- Create: `dominion_dispatch/refdata/zones_dom.yaml`
- Create: `dominion_dispatch/zones.py`
- Test: `tests/dominion_dispatch/test_zones.py`

- [ ] **Step 1: Write zone YAML**

Create `dominion_dispatch/refdata/zones_dom.yaml`:

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

- [ ] **Step 2: Write the failing tests**

Create `tests/dominion_dispatch/test_zones.py`:

```python
from dominion_dispatch.zones import Zone, load_zones, zone_for_pnode, ZoneIndex


def test_load_zones_returns_three_zones():
    idx = load_zones()
    assert len(idx.zones) == 3
    ids = [z.id for z in idx.zones]
    assert ids == ["loudoun-corridor", "fairfax-230", "alexandria"]


def test_zone_for_pnode_maps_each_enrolled_pnode():
    idx = load_zones()
    cases = {
        "1348256193": "loudoun-corridor",
        "83734355": "loudoun-corridor",
        "34886155": "fairfax-230",
        "123900989": "fairfax-230",
        "34886435": "fairfax-230",
        "34886297": "alexandria",
    }
    for pid, zid in cases.items():
        assert zone_for_pnode(idx, pid).id == zid


def test_zone_for_pnode_returns_none_for_unknown():
    idx = load_zones()
    assert zone_for_pnode(idx, "999999") is None


def test_zone_index_has_stable_ordering():
    idx = load_zones()
    assert [z.label for z in idx.zones] == [
        "Loudoun corridor",
        "Fairfax 230 kV",
        "Alexandria",
    ]
```

- [ ] **Step 3: Run and verify failure**

```bash
cd "$REPO" && "$PY" -m pytest tests/dominion_dispatch/test_zones.py -q
```

Expected: ImportError or collection failure (module does not exist yet).

- [ ] **Step 4: Implement `dominion_dispatch/zones.py`**

```python
"""Zone taxonomy for Dominion DER program: loads ``refdata/zones_dom.yaml``
and provides pnode -> zone lookups."""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

REFDATA_PATH = Path(__file__).resolve().parent / "refdata" / "zones_dom.yaml"


@dataclass(frozen=True)
class Zone:
    id: str
    label: str
    description: str
    pnode_ids: tuple[str, ...]


@dataclass(frozen=True)
class ZoneIndex:
    zones: tuple[Zone, ...]
    by_pnode: dict[str, Zone]

    def by_id(self, zone_id: str) -> Optional[Zone]:
        for z in self.zones:
            if z.id == zone_id:
                return z
        return None


@lru_cache(maxsize=1)
def load_zones(path: Path = REFDATA_PATH) -> ZoneIndex:
    with open(path) as f:
        raw = yaml.safe_load(f)
    zones = tuple(
        Zone(
            id=z["id"],
            label=z["label"],
            description=z.get("description", ""),
            pnode_ids=tuple(str(p) for p in z["pnode_ids"]),
        )
        for z in raw["zones"]
    )
    by_pnode: dict[str, Zone] = {}
    for z in zones:
        for pid in z.pnode_ids:
            by_pnode[pid] = z
    return ZoneIndex(zones=zones, by_pnode=by_pnode)


def zone_for_pnode(idx: ZoneIndex, pnode_id: str) -> Optional[Zone]:
    return idx.by_pnode.get(str(pnode_id))
```

- [ ] **Step 5: Run tests to verify pass**

```bash
cd "$REPO" && "$PY" -m pytest tests/dominion_dispatch/test_zones.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add dominion_dispatch/refdata/zones_dom.yaml dominion_dispatch/zones.py tests/dominion_dispatch/test_zones.py
git commit -m "feat(dominion): zone taxonomy loader + pnode lookup"
```

---

## Phase B: Capacity column + ORM + seed

### Task B1: Alembic migration for `listed_capacity_kw`

**Files:**
- Create: `alembic/versions/k3l4m5n6o7p8_dominion_listed_capacity.py`

- [ ] **Step 1: Write migration**

```python
"""Add listed_capacity_kw to dominion_devices

Revision ID: k3l4m5n6o7p8
Revises: j2k3l4m5n6o7
Create Date: 2026-04-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k3l4m5n6o7p8"
down_revision: Union[str, Sequence[str], None] = "j2k3l4m5n6o7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dominion_devices",
        sa.Column("listed_capacity_kw", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dominion_devices", "listed_capacity_kw")
```

- [ ] **Step 2: Ensure Cloud SQL Auth Proxy is running**

```bash
pgrep -f "cloud-sql-proxy wattcarbon-internal:us-central1:dominion-demo-db --port=5434" > /dev/null \
  || (cloud-sql-proxy wattcarbon-internal:us-central1:dominion-demo-db --port=5434 >/tmp/csp.log 2>&1 &)
sleep 3
nc -z 127.0.0.1 5434 && echo "proxy up"
```

Expected: `proxy up`.

- [ ] **Step 3: Apply migration**

```bash
cd "$REPO" && DATABASE_URL="$DSN" "$PY" -m alembic upgrade head
```

Expected: last line shows `Running upgrade j2k3l4m5n6o7 -> k3l4m5n6o7p8, Add listed_capacity_kw to dominion_devices`.

- [ ] **Step 4: Verify column exists**

```bash
"$PY" - <<'PY'
import os, psycopg2
with psycopg2.connect(os.environ["DSN"]) as c, c.cursor() as cur:
    cur.execute("""
      SELECT column_name, data_type, numeric_precision, numeric_scale, is_nullable
      FROM information_schema.columns
      WHERE table_name='dominion_devices' AND column_name='listed_capacity_kw'
    """)
    print(cur.fetchall())
PY
```

Make sure `DSN` is exported first: `export DSN="$DSN"`.

Expected: `[('listed_capacity_kw', 'numeric', 10, 2, 'YES')]`.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/k3l4m5n6o7p8_dominion_listed_capacity.py
git commit -m "feat(db): add listed_capacity_kw to dominion_devices"
```

---

### Task B2: Update ORM model + schema

**Files:**
- Modify: `app/models/dominion_der.py`
- Modify: `app/schemas/dominion.py`

- [ ] **Step 1: Add column to ORM**

Open `app/models/dominion_der.py` and find the `DominionDevice` class. Add a `listed_capacity_kw` column. If the existing file has columns declared via `Mapped[...]` style, use that; otherwise mirror the surrounding style. For the standard SQLAlchemy 2.0 pattern present in this repo:

```python
listed_capacity_kw: Mapped[Optional[Decimal]] = mapped_column(
    Numeric(10, 2), nullable=True
)
```

If `Decimal`/`Numeric` imports are not already present at the top of the file, add:

```python
from decimal import Decimal
from typing import Optional
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column
```

(Keep each import only if not already present.)

- [ ] **Step 2: Update response schema**

Open `app/schemas/dominion.py`. Find `DominionDeviceResponse`. Add the field:

```python
listed_capacity_kw: Optional[float] = None
```

The class already has `from_attributes = True` so SQLAlchemy's Decimal is coerced on the way out.

- [ ] **Step 3: Run existing tests to make sure nothing broke**

```bash
cd "$REPO" && "$PY" -m pytest -q
```

Expected: all existing tests still pass (`4 passed` from the zones test).

- [ ] **Step 4: Commit**

```bash
git add app/models/dominion_der.py app/schemas/dominion.py
git commit -m "feat(api): expose listed_capacity_kw on device response"
```

---

### Task B3: Seed listed capacity for 6 demo devices

**Files:**
- Create: `~/claude/outputs/tmp/dominion_admin_seed_kw.py`

- [ ] **Step 1: Write seed script**

Write to `/Users/mcgeesmini/claude/outputs/tmp/dominion_admin_seed_kw.py`:

```python
"""One-off: seed listed_capacity_kw on the 6 demo Dominion devices.

Requires cloud-sql-proxy on 127.0.0.1:5434 and DSN in env.
"""
import os
import psycopg2

CAPACITY = {
    "demo-bmtdom-001": 600,
    "demo-hamiltn-001": 600,
    "demo-braddock-001": 700,
    "demo-idylwoo4-001": 500,
    "demo-tysons-001": 800,
    "demo-jeffrson-001": 600,
}

with psycopg2.connect(os.environ["DSN"]) as c, c.cursor() as cur:
    for dev_id, kw in CAPACITY.items():
        cur.execute(
            "UPDATE dominion_devices SET listed_capacity_kw = %s, updated_at_utc = NOW() "
            "WHERE device_id_external = %s",
            (kw, dev_id),
        )
        print(f"  {dev_id}: {kw} kW  (rows: {cur.rowcount})")
    c.commit()
    cur.execute(
        "SELECT device_id_external, listed_capacity_kw FROM dominion_devices "
        "WHERE device_id_external = ANY(%s) ORDER BY device_id_external",
        (list(CAPACITY.keys()),),
    )
    print("\nVerify:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} kW")
```

- [ ] **Step 2: Ensure Cloud SQL Auth Proxy is running**

(Same as Task B1 step 2.)

- [ ] **Step 3: Run seed**

```bash
export DSN="$DSN"
"$PY" /Users/mcgeesmini/claude/outputs/tmp/dominion_admin_seed_kw.py
```

Expected: 6 `rows: 1` lines, then a verify block listing each device with its kW.

- [ ] **Step 4: Commit (script lives outside repo — no git step)**

Nothing to commit for this task. Seed is idempotent; re-running is safe.

---

## Phase C: Telemetry mock + event materialization

### Task C1: `telemetry_mock.py` with tests

**Files:**
- Create: `dominion_dispatch/telemetry_mock.py`
- Test: `tests/dominion_dispatch/test_telemetry_mock.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for dominion_dispatch.telemetry_mock."""
from datetime import date

from dominion_dispatch.telemetry_mock import (
    DEVICE_BASELINE,
    ZONE_PERFORMANCE,
    mock_realized_kw,
)


def test_every_demo_device_has_baseline():
    expected = {
        "demo-bmtdom-001",
        "demo-hamiltn-001",
        "demo-braddock-001",
        "demo-idylwoo4-001",
        "demo-tysons-001",
        "demo-jeffrson-001",
    }
    assert expected.issubset(set(DEVICE_BASELINE.keys()))


def test_every_zone_has_factor():
    assert set(ZONE_PERFORMANCE.keys()) == {
        "loudoun-corridor",
        "fairfax-230",
        "alexandria",
    }


def test_deterministic_same_inputs_same_output():
    kw1 = mock_realized_kw(
        device_id_external="demo-tysons-001",
        operating_date=date(2026, 4, 15),
        hour_index_in_event=0,
        period_tier="stressed",
        listed_kw=800.0,
        dispatch_signal_program=0.4,
    )
    kw2 = mock_realized_kw(
        device_id_external="demo-tysons-001",
        operating_date=date(2026, 4, 15),
        hour_index_in_event=0,
        period_tier="stressed",
        listed_kw=800.0,
        dispatch_signal_program=0.4,
    )
    assert kw1 == kw2


def test_mandatory_bump_raises_output():
    stressed = mock_realized_kw(
        "demo-tysons-001", date(2026, 4, 15), 0, "stressed", 800.0, 0.5
    )
    extreme = mock_realized_kw(
        "demo-tysons-001", date(2026, 4, 15), 0, "extreme", 800.0, 0.5
    )
    assert extreme > stressed


def test_duration_decay_kicks_in_after_first_hour():
    hr0 = mock_realized_kw(
        "demo-bmtdom-001", date(2026, 4, 15), 0, "stressed", 600.0, 0.5
    )
    hr5 = mock_realized_kw(
        "demo-bmtdom-001", date(2026, 4, 15), 5, "stressed", 600.0, 0.5
    )
    assert hr5 < hr0


def test_realized_never_exceeds_110_percent_of_asked():
    asked_kw = 800.0 * 0.4  # listed * signal
    for i in range(24):
        kw = mock_realized_kw(
            "demo-tysons-001", date(2026, 4, 15), i, "extreme", 800.0, 0.4
        )
        assert kw <= asked_kw * 1.10 + 1e-6
        assert kw >= asked_kw * 0.40 - 1e-6
```

- [ ] **Step 2: Run and verify failure**

```bash
cd "$REPO" && "$PY" -m pytest tests/dominion_dispatch/test_telemetry_mock.py -q
```

Expected: import error (module missing).

- [ ] **Step 3: Implement `telemetry_mock.py`**

```python
"""Deterministic mocked telemetry for Dominion demo.

Produces realized kW per (device, hour-within-event) in a way that's
reproducible across reloads and tells a zone x duration story on the
dashboard.
"""

from __future__ import annotations

import hashlib
import math
import struct
from datetime import date
from typing import Dict

from dominion_dispatch.zones import load_zones, zone_for_pnode

# Per-device baseline performance factor. See spec §7.
DEVICE_BASELINE: Dict[str, float] = {
    "demo-bmtdom-001":   0.94,
    "demo-hamiltn-001":  0.91,
    "demo-jeffrson-001": 0.92,
    "demo-tysons-001":   0.88,
    "demo-idylwoo4-001": 0.84,
    "demo-braddock-001": 0.78,
}

# Per-zone multiplier. Applied on top of device baseline.
ZONE_PERFORMANCE: Dict[str, float] = {
    "loudoun-corridor": 1.00,
    "fairfax-230":      0.92,
    "alexandria":       0.97,
}

DEFAULT_BASELINE = 0.85
DEFAULT_ZONE = 1.00
DURATION_DECAY_PER_HOUR = 0.04
DURATION_DECAY_FLOOR = 0.60
MANDATORY_BUMP = 0.05
NOISE_SIGMA = 0.03
RATIO_MIN = 0.40
RATIO_MAX = 1.10


def _seed_int(device_id_external: str, operating_date: date, hour_index: int) -> int:
    key = f"{device_id_external}|{operating_date.isoformat()}|{hour_index}".encode()
    digest = hashlib.blake2b(key, digest_size=8).digest()
    return struct.unpack("<Q", digest)[0]


def _normal_from_seed(seed: int, sigma: float) -> float:
    """Box-Muller normal sample, deterministic from a single 64-bit seed."""
    u1 = ((seed & 0xFFFFFFFF) + 1) / (2**32 + 1)
    u2 = ((seed >> 32) + 1) / (2**32 + 1)
    return sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _zone_id_for_device(
    device_id_external: str, pnode_id_external: str | None
) -> str | None:
    if pnode_id_external is None:
        return None
    idx = load_zones()
    z = zone_for_pnode(idx, str(pnode_id_external))
    return z.id if z else None


def mock_realized_kw(
    device_id_external: str,
    operating_date: date,
    hour_index_in_event: int,
    period_tier: str,
    listed_kw: float,
    dispatch_signal_program: float,
    *,
    pnode_id_external: str | None = None,
) -> float:
    """Return deterministic realized kW for one hour of a mocked event."""
    if dispatch_signal_program <= 0 or listed_kw <= 0:
        return 0.0

    baseline = DEVICE_BASELINE.get(device_id_external, DEFAULT_BASELINE)
    zone_id = _zone_id_for_device(device_id_external, pnode_id_external)
    zone_factor = ZONE_PERFORMANCE.get(zone_id or "", DEFAULT_ZONE)

    decay = max(
        DURATION_DECAY_FLOOR,
        1.0 - DURATION_DECAY_PER_HOUR * max(0, hour_index_in_event - 1),
    )
    bump = MANDATORY_BUMP if period_tier == "extreme" else 0.0

    ratio = baseline * zone_factor * decay + bump
    noise = _normal_from_seed(
        _seed_int(device_id_external, operating_date, hour_index_in_event),
        NOISE_SIGMA,
    )
    ratio_noisy = max(RATIO_MIN, min(RATIO_MAX, ratio + noise))

    return float(listed_kw) * float(dispatch_signal_program) * ratio_noisy
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd "$REPO" && "$PY" -m pytest tests/dominion_dispatch/test_telemetry_mock.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add dominion_dispatch/telemetry_mock.py tests/dominion_dispatch/test_telemetry_mock.py
git commit -m "feat(dominion): deterministic mocked telemetry for admin demo"
```

---

### Task C2: `events.py` materialization with tests

**Files:**
- Create: `dominion_dispatch/events.py`
- Test: `tests/dominion_dispatch/test_events.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for dominion_dispatch.events.build_events_from_rows."""
from datetime import datetime, timezone
from decimal import Decimal

from dominion_dispatch.events import (
    DispatchHourRow,
    DeviceEvent,
    build_events_from_rows,
)


def H(hour: int, tier: str, signal: float = 0.4, cong: float = 18.0):
    """Shorthand to build a DispatchHourRow on 2026-04-15 UTC."""
    return DispatchHourRow(
        device_id_external="d1",
        primary_pnode_id="p1",
        pjm_load_zone_code="DOM",
        operating_date=datetime(2026, 4, 15).date(),
        interval_start_utc=datetime(2026, 4, 15, hour, tzinfo=timezone.utc),
        period_tier=tier,
        dispatch_signal=signal,
        dispatch_signal_program=signal,
        resolved_congestion=Decimal(str(cong)),
        dispatch_mandatory=(tier == "extreme"),
    )


def test_normal_hours_produce_no_events():
    events = build_events_from_rows([H(8, "normal"), H(9, "normal")])
    assert events == []


def test_contiguous_stressed_block_becomes_one_event():
    rows = [H(8, "normal"), H(9, "stressed"), H(10, "stressed"), H(11, "normal")]
    events = build_events_from_rows(rows)
    assert len(events) == 1
    e = events[0]
    assert e.duration_hours == 2
    assert e.stressed_hours == 2
    assert e.extreme_hours == 0
    assert e.has_mandatory is False


def test_gap_splits_into_two_events():
    rows = [
        H(8, "stressed"), H(9, "stressed"),
        H(10, "normal"),
        H(11, "extreme"), H(12, "extreme"),
    ]
    events = build_events_from_rows(rows)
    assert len(events) == 2
    assert events[0].duration_hours == 2
    assert events[0].has_mandatory is False
    assert events[1].duration_hours == 2
    assert events[1].has_mandatory is True


def test_mixed_stressed_extreme_stays_one_event():
    rows = [
        H(14, "stressed"), H(15, "stressed"),
        H(16, "extreme"),  H(17, "extreme"),
        H(18, "stressed"),
    ]
    events = build_events_from_rows(rows)
    assert len(events) == 1
    e = events[0]
    assert e.duration_hours == 5
    assert e.stressed_hours == 3
    assert e.extreme_hours == 2
    assert e.has_mandatory is True


def test_event_id_is_deterministic():
    rows = [H(14, "extreme"), H(15, "extreme")]
    events = build_events_from_rows(rows)
    assert events[0].event_id == "E-2026-04-15-d1-14"
```

- [ ] **Step 2: Run and verify failure**

```bash
cd "$REPO" && "$PY" -m pytest tests/dominion_dispatch/test_events.py -q
```

Expected: import error.

- [ ] **Step 3: Implement `events.py`**

```python
"""Materialize dispatch events from hourly schedule rows.

An "event" for this program is a contiguous run of non-normal dispatch
hours (stressed or extreme, with stressed and extreme hours allowed to
mix) for one device on one operating date. A 1-hour gap of normal
hours ends the event.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional

from dominion_dispatch.telemetry_mock import mock_realized_kw


@dataclass(frozen=True)
class DispatchHourRow:
    device_id_external: str
    primary_pnode_id: str
    pjm_load_zone_code: str
    operating_date: date
    interval_start_utc: datetime
    period_tier: Optional[str]
    dispatch_signal: Optional[float]
    dispatch_signal_program: Optional[float]
    resolved_congestion: Optional[Decimal]
    dispatch_mandatory: Optional[bool]


@dataclass
class DeviceEvent:
    event_id: str
    device_id_external: str
    primary_pnode_id: str
    operating_date: date
    start_utc: datetime
    end_utc: datetime
    duration_hours: int
    stressed_hours: int
    extreme_hours: int
    has_mandatory: bool
    avg_program_signal: float
    listed_capacity_kw: Optional[float]
    realized_capacity_kw_avg: Optional[float]
    performance_pct: Optional[float]
    mandatory_performance_pct: Optional[float]
    hours: list[dict] = field(default_factory=list)


def _signal(v) -> float:
    if v is None:
        return 0.0
    return float(v)


def build_events_from_rows(
    rows: Iterable[DispatchHourRow],
    *,
    listed_capacity_kw: Optional[float] = None,
    include_hourly_detail: bool = False,
) -> list[DeviceEvent]:
    """Walk hourly rows (sorted) and emit contiguous non-normal events.

    When ``listed_capacity_kw`` is provided, realized telemetry is mocked
    and aggregated into performance columns on each event.
    """
    rows = sorted(rows, key=lambda r: (r.device_id_external, r.interval_start_utc))
    events: list[DeviceEvent] = []

    cur: list[DispatchHourRow] = []

    def close_current():
        if not cur:
            return
        first = cur[0]
        last = cur[-1]
        end_utc = last.interval_start_utc + timedelta(hours=1)
        start_local_hr = _ept_hour(first.interval_start_utc)
        stressed = sum(1 for r in cur if r.period_tier == "stressed")
        extreme = sum(1 for r in cur if r.period_tier == "extreme")
        avg_signal = (
            statistics.mean(_signal(r.dispatch_signal_program) for r in cur)
            if cur else 0.0
        )
        ev = DeviceEvent(
            event_id=f"E-{first.operating_date.isoformat()}-{first.device_id_external}-{start_local_hr:02d}",
            device_id_external=first.device_id_external,
            primary_pnode_id=first.primary_pnode_id,
            operating_date=first.operating_date,
            start_utc=first.interval_start_utc,
            end_utc=end_utc,
            duration_hours=len(cur),
            stressed_hours=stressed,
            extreme_hours=extreme,
            has_mandatory=extreme > 0,
            avg_program_signal=avg_signal,
            listed_capacity_kw=listed_capacity_kw,
            realized_capacity_kw_avg=None,
            performance_pct=None,
            mandatory_performance_pct=None,
        )
        if listed_capacity_kw is not None and listed_capacity_kw > 0:
            _attach_perf(ev, cur, float(listed_capacity_kw), include_hourly_detail)
        elif include_hourly_detail:
            ev.hours = [_hour_dict(i, r, None, None) for i, r in enumerate(cur)]
        events.append(ev)

    for r in rows:
        if r.period_tier in ("stressed", "extreme"):
            if cur and _is_contiguous(cur[-1], r):
                cur.append(r)
            else:
                close_current()
                cur = [r]
        else:
            close_current()
            cur = []
    close_current()
    return events


def _is_contiguous(prev: DispatchHourRow, nxt: DispatchHourRow) -> bool:
    return (
        nxt.device_id_external == prev.device_id_external
        and nxt.operating_date == prev.operating_date
        and nxt.interval_start_utc - prev.interval_start_utc == timedelta(hours=1)
    )


def _ept_hour(ts_utc: datetime) -> int:
    """Hour-of-day in Eastern Prevailing Time."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None
    if ZoneInfo is not None:
        return ts_utc.astimezone(ZoneInfo("America/New_York")).hour
    # Fallback: UTC-5 rough approximation; acceptable for event naming only.
    return (ts_utc - timedelta(hours=5)).hour


def _attach_perf(
    ev: DeviceEvent,
    rows: list[DispatchHourRow],
    listed_kw: float,
    include_hourly_detail: bool,
) -> None:
    hour_rows: list[dict] = []
    realized_per_hour: list[float] = []
    realized_mandatory: list[float] = []

    for i, r in enumerate(rows):
        signal = _signal(r.dispatch_signal_program)
        realized_kw = mock_realized_kw(
            device_id_external=r.device_id_external,
            operating_date=r.operating_date,
            hour_index_in_event=i,
            period_tier=r.period_tier or "normal",
            listed_kw=listed_kw,
            dispatch_signal_program=signal,
            pnode_id_external=r.primary_pnode_id,
        )
        realized_per_hour.append(realized_kw)
        if r.period_tier == "extreme":
            realized_mandatory.append(realized_kw)
        hour_rows.append(_hour_dict(i, r, listed_kw * signal, realized_kw))

    listed_avg_kw = listed_kw * ev.avg_program_signal
    realized_avg_kw = statistics.mean(realized_per_hour) if realized_per_hour else 0.0

    ev.realized_capacity_kw_avg = realized_avg_kw
    ev.performance_pct = (
        100.0 * realized_avg_kw / listed_avg_kw if listed_avg_kw > 0 else None
    )

    if realized_mandatory:
        mand_signals = [
            _signal(r.dispatch_signal_program) for r in rows if r.period_tier == "extreme"
        ]
        mand_listed = listed_kw * (statistics.mean(mand_signals) if mand_signals else 0)
        mand_realized = statistics.mean(realized_mandatory)
        ev.mandatory_performance_pct = (
            100.0 * mand_realized / mand_listed if mand_listed > 0 else None
        )

    if include_hourly_detail:
        ev.hours = hour_rows


def _hour_dict(
    idx: int,
    r: DispatchHourRow,
    listed_kw_ask: Optional[float],
    realized_kw: Optional[float],
) -> dict:
    return {
        "hour_index": idx,
        "interval_start_utc": r.interval_start_utc.isoformat(),
        "period_tier": r.period_tier,
        "dispatch_signal_program": _signal(r.dispatch_signal_program),
        "listed_kw_ask": listed_kw_ask,
        "realized_kw": realized_kw,
    }
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd "$REPO" && "$PY" -m pytest tests/dominion_dispatch/test_events.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add dominion_dispatch/events.py tests/dominion_dispatch/test_events.py
git commit -m "feat(dominion): event materialization from hourly dispatch rows"
```

---

### Task C3: DB loader that produces `DispatchHourRow` + `build_events_for_device`

**Files:**
- Modify: `dominion_dispatch/events.py` (add DB-facing helpers)

- [ ] **Step 1: Add DB helpers at the end of `events.py`**

Append to `dominion_dispatch/events.py`:

```python
from datetime import timedelta  # noqa: E402  (already imported above, keep to be safe)

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.dominion_der import (  # noqa: E402
    DominionDaIngestionRun,
    DominionDevice,
    DominionDispatchDeviceHour,
)


def fetch_hours_for_window(
    session: Session,
    *,
    window_start: date,
    window_end: date,
    device_ids: Optional[list[str]] = None,
) -> list[DispatchHourRow]:
    """Pull dispatch hours joined to ingestion-run operating_date.

    Returns non-normal hours only (stressed or extreme), sorted by
    (device_id_external, interval_start_utc).
    """
    q = (
        select(
            DominionDispatchDeviceHour.device_id_external,
            DominionDispatchDeviceHour.primary_pnode_id,
            DominionDispatchDeviceHour.pjm_load_zone_code,
            DominionDaIngestionRun.operating_date,
            DominionDispatchDeviceHour.interval_start_utc,
            DominionDispatchDeviceHour.period_tier,
            DominionDispatchDeviceHour.dispatch_signal,
            DominionDispatchDeviceHour.dispatch_signal_program,
            DominionDispatchDeviceHour.resolved_congestion,
            DominionDispatchDeviceHour.dispatch_mandatory,
        )
        .join(
            DominionDaIngestionRun,
            DominionDaIngestionRun.id == DominionDispatchDeviceHour.ingestion_run_id,
        )
        .where(
            and_(
                DominionDaIngestionRun.operating_date >= window_start,
                DominionDaIngestionRun.operating_date <= window_end,
                DominionDispatchDeviceHour.period_tier.in_(("stressed", "extreme")),
            )
        )
        .order_by(
            DominionDispatchDeviceHour.device_id_external,
            DominionDispatchDeviceHour.interval_start_utc,
        )
    )
    if device_ids:
        q = q.where(DominionDispatchDeviceHour.device_id_external.in_(device_ids))

    return [DispatchHourRow(**dict(r._mapping)) for r in session.execute(q).all()]


def device_capacity_map(session: Session, device_ids: list[str]) -> dict[str, float]:
    if not device_ids:
        return {}
    rows = session.execute(
        select(DominionDevice.device_id_external, DominionDevice.listed_capacity_kw)
        .where(DominionDevice.device_id_external.in_(device_ids))
    ).all()
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def build_events_for_window(
    session: Session,
    *,
    window_start: date,
    window_end: date,
    device_ids: Optional[list[str]] = None,
    include_hourly_detail: bool = False,
) -> list[DeviceEvent]:
    """Fetch hours, group by device, materialize events per device."""
    rows = fetch_hours_for_window(
        session,
        window_start=window_start,
        window_end=window_end,
        device_ids=device_ids,
    )
    if not rows:
        return []

    all_ids = sorted({r.device_id_external for r in rows})
    caps = device_capacity_map(session, all_ids)

    events: list[DeviceEvent] = []
    cur_id: Optional[str] = None
    cur_rows: list[DispatchHourRow] = []
    for r in rows:
        if r.device_id_external != cur_id:
            if cur_rows:
                events.extend(
                    build_events_from_rows(
                        cur_rows,
                        listed_capacity_kw=caps.get(cur_id or ""),
                        include_hourly_detail=include_hourly_detail,
                    )
                )
            cur_id = r.device_id_external
            cur_rows = []
        cur_rows.append(r)
    if cur_rows:
        events.extend(
            build_events_from_rows(
                cur_rows,
                listed_capacity_kw=caps.get(cur_id or ""),
                include_hourly_detail=include_hourly_detail,
            )
        )
    return events
```

- [ ] **Step 2: Verify existing unit tests still pass**

```bash
cd "$REPO" && "$PY" -m pytest tests/dominion_dispatch/ -q
```

Expected: `15 passed` (4 zones + 6 telemetry + 5 events).

- [ ] **Step 3: Commit**

```bash
git add dominion_dispatch/events.py
git commit -m "feat(dominion): DB loader + per-window event builder"
```

---

## Phase D: Admin API

### Task D1: Response schemas

**Files:**
- Modify: `app/schemas/dominion.py`

- [ ] **Step 1: Append new schemas after `DominionParticipationResponse`**

Open `app/schemas/dominion.py` and append:

```python
# ───────────────────────── admin dashboard ─────────────────────────


class AdminZoneSummary(BaseModel):
    id: str
    label: str
    description: str
    pnode_ids: list[str]
    device_ids: list[str]
    device_count: int
    listed_capacity_kw: float
    next_event_count_24h: int = 0
    last_event_perf_pct: Optional[float] = None


class AdminZoneDetail(AdminZoneSummary):
    devices: list["DominionDeviceResponse"] = []


class AdminEventSummary(BaseModel):
    event_id: str
    device_id_external: str
    primary_pnode_id: str
    primary_pnode_name: Optional[str] = None
    zone_id: Optional[str] = None
    operating_date: date
    start_utc: datetime
    end_utc: datetime
    duration_hours: int
    stressed_hours: int
    extreme_hours: int
    has_mandatory: bool
    listed_capacity_kw_avg: Optional[float] = None
    realized_capacity_kw_avg: Optional[float] = None
    performance_pct: Optional[float] = None
    mandatory_performance_pct: Optional[float] = None


class AdminEventListResponse(BaseModel):
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    total: int
    events: list[AdminEventSummary]


class AdminEventHour(BaseModel):
    hour_index: int
    interval_start_utc: datetime
    period_tier: Optional[str]
    dispatch_signal_program: float
    listed_kw_ask: Optional[float] = None
    realized_kw: Optional[float] = None


class AdminEventDetail(AdminEventSummary):
    hours: list[AdminEventHour] = []


class AdminDashboardZoneSlice(BaseModel):
    zone_id: str
    events: int
    peak_kw: float


class AdminDashboardHour(BaseModel):
    hour_utc: datetime
    program_signal: float


class AdminDashboardToday(BaseModel):
    operating_date: date
    forecast_basis: str  # "tomorrow_da" | "most_recent_da"
    ingestion_run_id: Optional[int] = None
    events_forecast: int
    peak_program_kw: float
    peak_window_ept: Optional[list[str]] = None
    by_zone: list[AdminDashboardZoneSlice]
    fleet_24h_signal: list[AdminDashboardHour]


class AdminDeviceRecentEvent(AdminEventSummary):
    pass


class AdminDeviceSummary(BaseModel):
    device_id_external: str
    primary_pnode_id: str
    primary_pnode_name: Optional[str] = None
    zone_id: Optional[str] = None
    listed_capacity_kw: Optional[float] = None
    asset_lat: Optional[float] = None
    asset_lon: Optional[float] = None
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    event_count: int
    total_dispatch_hours: int
    avg_performance_pct: Optional[float] = None
    mandatory_performance_pct: Optional[float] = None
    total_realized_energy_mwh: float
    rank_in_fleet: Optional[int] = None
    recent_events: list[AdminDeviceRecentEvent] = []


AdminZoneDetail.model_rebuild()
```

- [ ] **Step 2: Sanity compile**

```bash
cd "$REPO" && "$PY" -c "from app.schemas import dominion as m; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add app/schemas/dominion.py
git commit -m "feat(api): pydantic schemas for Dominion admin dashboard"
```

---

### Task D2: Admin router with `/zones` + `/dashboard/today`

**Files:**
- Create: `app/api/v1/dominion_admin_routes.py`
- Modify: `app/api/v1/routes.py`

- [ ] **Step 1: Create the admin router**

```python
"""Dominion admin dashboard API (demo prop)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dominion_der import (
    DominionDaIngestionRun,
    DominionDaNodeHourly,
    DominionDevice,
    DominionDispatchDeviceHour,
)
from app.schemas.dominion import (
    AdminDashboardHour,
    AdminDashboardToday,
    AdminDashboardZoneSlice,
    AdminDeviceRecentEvent,
    AdminDeviceSummary,
    AdminEventDetail,
    AdminEventHour,
    AdminEventListResponse,
    AdminEventSummary,
    AdminZoneDetail,
    AdminZoneSummary,
    DominionDeviceResponse,
)
from dominion_dispatch.events import (
    build_events_for_window,
    fetch_hours_for_window,
)
from dominion_dispatch.zones import Zone, load_zones, zone_for_pnode

logger = logging.getLogger(__name__)

router = APIRouter()


# ───────────────────────── helpers ─────────────────────────


def _active_devices(session: Session, as_of: date) -> list[DominionDevice]:
    from sqlalchemy import or_
    rows = session.execute(
        select(DominionDevice).where(
            DominionDevice.effective_from <= as_of,
            or_(DominionDevice.effective_to.is_(None), DominionDevice.effective_to >= as_of),
        )
    ).scalars().all()
    return list(rows)


def _device_response(d: DominionDevice) -> DominionDeviceResponse:
    return DominionDeviceResponse.model_validate(d, from_attributes=True)


def _latest_successful_run(session: Session) -> Optional[DominionDaIngestionRun]:
    return session.execute(
        select(DominionDaIngestionRun)
        .where(
            DominionDaIngestionRun.status == "success",
            DominionDaIngestionRun.row_count > 0,
        )
        .order_by(DominionDaIngestionRun.operating_date.desc())
        .limit(1)
    ).scalar_one_or_none()


def _run_for_date(session: Session, d: date) -> Optional[DominionDaIngestionRun]:
    return session.execute(
        select(DominionDaIngestionRun)
        .where(
            DominionDaIngestionRun.operating_date == d,
            DominionDaIngestionRun.status == "success",
            DominionDaIngestionRun.row_count > 0,
        )
        .order_by(DominionDaIngestionRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _utcnow_date() -> date:
    return datetime.now(timezone.utc).date()


# ───────────────────────── zones ─────────────────────────


@router.get("/zones", response_model=list[AdminZoneSummary])
def list_zones(db: Session = Depends(get_db)):
    idx = load_zones()
    as_of = _utcnow_date()
    devices = _active_devices(db, as_of)
    caps = {
        d.device_id_external: float(d.listed_capacity_kw) if d.listed_capacity_kw is not None else 0.0
        for d in devices
    }
    by_pnode = {d.primary_pnode_id: d for d in devices}

    out: list[AdminZoneSummary] = []
    for z in idx.zones:
        zone_devices = [by_pnode[pid] for pid in z.pnode_ids if pid in by_pnode]
        listed = sum(caps.get(d.device_id_external, 0.0) for d in zone_devices)
        out.append(
            AdminZoneSummary(
                id=z.id,
                label=z.label,
                description=z.description,
                pnode_ids=list(z.pnode_ids),
                device_ids=[d.device_id_external for d in zone_devices],
                device_count=len(zone_devices),
                listed_capacity_kw=listed,
            )
        )
    return out


@router.get("/zones/{zone_id}", response_model=AdminZoneDetail)
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    idx = load_zones()
    z = idx.by_id(zone_id)
    if z is None:
        raise HTTPException(404, f"Zone {zone_id} not found")
    as_of = _utcnow_date()
    devices = _active_devices(db, as_of)
    zone_devices = [d for d in devices if d.primary_pnode_id in z.pnode_ids]
    listed = sum(
        float(d.listed_capacity_kw) if d.listed_capacity_kw is not None else 0.0
        for d in zone_devices
    )
    return AdminZoneDetail(
        id=z.id,
        label=z.label,
        description=z.description,
        pnode_ids=list(z.pnode_ids),
        device_ids=[d.device_id_external for d in zone_devices],
        device_count=len(zone_devices),
        listed_capacity_kw=listed,
        devices=[_device_response(d) for d in zone_devices],
    )


# ───────────────────────── dashboard/today ─────────────────────────


@router.get("/dashboard/today", response_model=AdminDashboardToday)
def dashboard_today(db: Session = Depends(get_db)):
    idx = load_zones()
    as_of = _utcnow_date()

    tomorrow_run = _run_for_date(db, as_of + timedelta(days=1))
    if tomorrow_run:
        run = tomorrow_run
        basis = "tomorrow_da"
    else:
        run = _latest_successful_run(db)
        basis = "most_recent_da"
    if run is None:
        raise HTTPException(503, "No successful DA ingest available yet.")

    events = build_events_for_window(
        db,
        window_start=run.operating_date,
        window_end=run.operating_date,
    )

    # Per-zone rollups
    by_zone_buf: dict[str, dict] = {z.id: {"events": 0, "peak_kw": 0.0} for z in idx.zones}
    for ev in events:
        zone = zone_for_pnode(idx, ev.primary_pnode_id)
        zid = zone.id if zone else None
        if not zid:
            continue
        by_zone_buf[zid]["events"] += 1
        peak = (ev.listed_capacity_kw or 0.0) * max(
            (h["dispatch_signal_program"] for h in (ev.hours or [{"dispatch_signal_program": ev.avg_program_signal}])),
            default=0.0,
        )
        if peak > by_zone_buf[zid]["peak_kw"]:
            by_zone_buf[zid]["peak_kw"] = peak

    # Fleet 24-hour signal series
    hour_rows = fetch_hours_for_window(
        db, window_start=run.operating_date, window_end=run.operating_date
    )
    hour_map: dict[datetime, list[float]] = {}
    for r in hour_rows:
        hour_map.setdefault(r.interval_start_utc, []).append(r.dispatch_signal_program or 0.0)
    fleet_series = [
        AdminDashboardHour(hour_utc=ts, program_signal=sum(vals) / len(vals))
        for ts, vals in sorted(hour_map.items())
    ]

    events_forecast = sum(1 for ev in events)
    peak_kw = max(
        (
            (ev.listed_capacity_kw or 0.0) * ev.avg_program_signal
            for ev in events
        ),
        default=0.0,
    )

    return AdminDashboardToday(
        operating_date=run.operating_date,
        forecast_basis=basis,
        ingestion_run_id=run.id,
        events_forecast=events_forecast,
        peak_program_kw=peak_kw,
        peak_window_ept=None,  # filled in by frontend or future task
        by_zone=[
            AdminDashboardZoneSlice(zone_id=zid, events=v["events"], peak_kw=v["peak_kw"])
            for zid, v in by_zone_buf.items()
        ],
        fleet_24h_signal=fleet_series,
    )
```

- [ ] **Step 2: Mount the admin router**

Open `app/api/v1/routes.py`. Find the line that mounts the existing `dominion_router`:

```python
from app.api.v1.dominion_routes import router as dominion_router

router = APIRouter(prefix="/api/v1")
router.include_router(dominion_router, prefix="/dominion", tags=["Dominion DER demo"])
```

Add two lines just after it:

```python
from app.api.v1.dominion_admin_routes import router as dominion_admin_router
router.include_router(dominion_admin_router, prefix="/dominion/admin", tags=["Dominion admin"])
```

- [ ] **Step 3: Quick import sanity**

```bash
cd "$REPO" && "$PY" -c "from app.main import app; print(sum(1 for r in app.routes if '/admin' in getattr(r, 'path', '')))"
```

Expected: a number `>= 3` (zones, zones/{id}, dashboard/today — more once later tasks add more).

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/dominion_admin_routes.py app/api/v1/routes.py
git commit -m "feat(admin): /zones and /dashboard/today endpoints"
```

---

### Task D3: `/events` list + `/events/{event_id}`

**Files:**
- Modify: `app/api/v1/dominion_admin_routes.py`

- [ ] **Step 1: Append to `dominion_admin_routes.py`**

At the bottom:

```python
# ───────────────────────── events list + detail ─────────────────────────


def _zone_id_for(primary_pnode_id: str) -> Optional[str]:
    z = zone_for_pnode(load_zones(), str(primary_pnode_id))
    return z.id if z else None


def _pnode_name_for(session: Session, primary_pnode_id: str) -> Optional[str]:
    row = session.execute(
        select(DominionDevice.primary_pnode_name)
        .where(DominionDevice.primary_pnode_id == str(primary_pnode_id))
        .limit(1)
    ).scalar_one_or_none()
    return row


def _event_to_summary(ev, session: Session) -> AdminEventSummary:
    return AdminEventSummary(
        event_id=ev.event_id,
        device_id_external=ev.device_id_external,
        primary_pnode_id=ev.primary_pnode_id,
        primary_pnode_name=_pnode_name_for(session, ev.primary_pnode_id),
        zone_id=_zone_id_for(ev.primary_pnode_id),
        operating_date=ev.operating_date,
        start_utc=ev.start_utc,
        end_utc=ev.end_utc,
        duration_hours=ev.duration_hours,
        stressed_hours=ev.stressed_hours,
        extreme_hours=ev.extreme_hours,
        has_mandatory=ev.has_mandatory,
        listed_capacity_kw_avg=(
            ev.listed_capacity_kw * ev.avg_program_signal
            if ev.listed_capacity_kw is not None else None
        ),
        realized_capacity_kw_avg=ev.realized_capacity_kw_avg,
        performance_pct=ev.performance_pct,
        mandatory_performance_pct=ev.mandatory_performance_pct,
    )


@router.get("/events", response_model=AdminEventListResponse)
def list_events(
    window_days: int = Query(default=30, ge=1, le=365),
    zone_id: Optional[str] = None,
    has_mandatory: Optional[bool] = None,
    min_perf: Optional[float] = Query(default=None, ge=0, le=100),
    device_id_external: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    latest = _latest_successful_run(db)
    if latest is None:
        return AdminEventListResponse(total=0, events=[])
    window_end = latest.operating_date
    window_start = window_end - timedelta(days=window_days - 1)

    device_ids: Optional[list[str]] = None
    if zone_id:
        z = load_zones().by_id(zone_id)
        if z is None:
            raise HTTPException(404, f"Zone {zone_id} not found")
        rows = db.execute(
            select(DominionDevice.device_id_external).where(
                DominionDevice.primary_pnode_id.in_(z.pnode_ids)
            )
        ).all()
        device_ids = [r[0] for r in rows]
        if not device_ids:
            return AdminEventListResponse(
                window_start=window_start, window_end=window_end, total=0, events=[]
            )
    if device_id_external:
        device_ids = [device_id_external] if device_ids is None else (
            [device_id_external] if device_id_external in device_ids else []
        )
        if not device_ids:
            return AdminEventListResponse(
                window_start=window_start, window_end=window_end, total=0, events=[]
            )

    events = build_events_for_window(
        db,
        window_start=window_start,
        window_end=window_end,
        device_ids=device_ids,
    )
    if has_mandatory is not None:
        events = [e for e in events if e.has_mandatory == has_mandatory]
    if min_perf is not None:
        events = [e for e in events if (e.performance_pct or 0) >= min_perf]

    events.sort(key=lambda e: e.start_utc, reverse=True)
    total = len(events)
    page = events[offset : offset + limit]
    return AdminEventListResponse(
        window_start=window_start,
        window_end=window_end,
        total=total,
        events=[_event_to_summary(e, db) for e in page],
    )


@router.get("/events/{event_id}", response_model=AdminEventDetail)
def get_event(event_id: str, db: Session = Depends(get_db)):
    # Event IDs are shaped: E-YYYY-MM-DD-<device_id>-<hh>
    # Parse the operating_date and device_id to scope the lookup cheaply.
    parts = event_id.split("-")
    if len(parts) < 6 or parts[0] != "E":
        raise HTTPException(400, f"Bad event_id: {event_id}")
    try:
        op_date = date.fromisoformat(f"{parts[1]}-{parts[2]}-{parts[3]}")
    except ValueError as e:
        raise HTTPException(400, f"Bad event_id date: {e}") from e
    start_hour_ept = parts[-1]
    device_id = "-".join(parts[4:-1])

    events = build_events_for_window(
        db,
        window_start=op_date,
        window_end=op_date,
        device_ids=[device_id],
        include_hourly_detail=True,
    )
    match = next((e for e in events if e.event_id == event_id), None)
    if match is None:
        raise HTTPException(404, f"Event {event_id} not found")

    summary = _event_to_summary(match, db)
    return AdminEventDetail(
        **summary.model_dump(),
        hours=[AdminEventHour(**h) for h in match.hours],
    )
```

- [ ] **Step 2: Sanity import**

```bash
cd "$REPO" && "$PY" -c "from app.main import app; print(sum(1 for r in app.routes if '/admin/events' in getattr(r, 'path', '')))"
```

Expected: `2`.

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/dominion_admin_routes.py
git commit -m "feat(admin): /events list + /events/{id} detail"
```

---

### Task D4: `/devices/{id}/summary`

**Files:**
- Modify: `app/api/v1/dominion_admin_routes.py`

- [ ] **Step 1: Append device summary endpoint**

At the bottom of `app/api/v1/dominion_admin_routes.py`:

```python
# ───────────────────────── devices/{id}/summary ─────────────────────────


@router.get(
    "/devices/{device_id_external}/summary", response_model=AdminDeviceSummary
)
def device_summary(
    device_id_external: str,
    window_days: int = Query(default=30, ge=1, le=365),
    recent_limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    dev = db.execute(
        select(DominionDevice).where(
            DominionDevice.device_id_external == device_id_external
        )
    ).scalar_one_or_none()
    if dev is None:
        raise HTTPException(404, f"Device {device_id_external} not found")

    latest = _latest_successful_run(db)
    if latest is None:
        return AdminDeviceSummary(
            device_id_external=dev.device_id_external,
            primary_pnode_id=dev.primary_pnode_id,
            primary_pnode_name=dev.primary_pnode_name,
            zone_id=_zone_id_for(dev.primary_pnode_id),
            listed_capacity_kw=float(dev.listed_capacity_kw) if dev.listed_capacity_kw else None,
            asset_lat=float(dev.asset_lat) if dev.asset_lat is not None else None,
            asset_lon=float(dev.asset_lon) if dev.asset_lon is not None else None,
            event_count=0,
            total_dispatch_hours=0,
            total_realized_energy_mwh=0.0,
            recent_events=[],
        )
    window_end = latest.operating_date
    window_start = window_end - timedelta(days=window_days - 1)

    my_events = build_events_for_window(
        db,
        window_start=window_start,
        window_end=window_end,
        device_ids=[device_id_external],
        include_hourly_detail=True,
    )
    total_hours = sum(e.duration_hours for e in my_events)
    total_energy_mwh = sum(
        sum(h.get("realized_kw") or 0.0 for h in e.hours) / 1000.0
        for e in my_events
    )
    perfs = [e.performance_pct for e in my_events if e.performance_pct is not None]
    mand_perfs = [
        e.mandatory_performance_pct
        for e in my_events
        if e.mandatory_performance_pct is not None
    ]
    avg_perf = sum(perfs) / len(perfs) if perfs else None
    avg_mand = sum(mand_perfs) / len(mand_perfs) if mand_perfs else None

    # Fleet ranking: avg perf across all devices
    all_events = build_events_for_window(
        db, window_start=window_start, window_end=window_end
    )
    per_device: dict[str, list[float]] = {}
    for e in all_events:
        if e.performance_pct is not None:
            per_device.setdefault(e.device_id_external, []).append(e.performance_pct)
    fleet_avg = {d: sum(v) / len(v) for d, v in per_device.items() if v}
    rank = None
    if avg_perf is not None and fleet_avg:
        ordered = sorted(fleet_avg.items(), key=lambda kv: kv[1], reverse=True)
        rank = next((i + 1 for i, (d, _) in enumerate(ordered) if d == device_id_external), None)

    my_events.sort(key=lambda e: e.start_utc, reverse=True)
    recent = [
        AdminDeviceRecentEvent(**_event_to_summary(e, db).model_dump())
        for e in my_events[:recent_limit]
    ]

    return AdminDeviceSummary(
        device_id_external=dev.device_id_external,
        primary_pnode_id=dev.primary_pnode_id,
        primary_pnode_name=dev.primary_pnode_name,
        zone_id=_zone_id_for(dev.primary_pnode_id),
        listed_capacity_kw=float(dev.listed_capacity_kw) if dev.listed_capacity_kw else None,
        asset_lat=float(dev.asset_lat) if dev.asset_lat is not None else None,
        asset_lon=float(dev.asset_lon) if dev.asset_lon is not None else None,
        window_start=window_start,
        window_end=window_end,
        event_count=len(my_events),
        total_dispatch_hours=total_hours,
        avg_performance_pct=avg_perf,
        mandatory_performance_pct=avg_mand,
        total_realized_energy_mwh=total_energy_mwh,
        rank_in_fleet=rank,
        recent_events=recent,
    )
```

- [ ] **Step 2: Sanity import**

```bash
cd "$REPO" && "$PY" -c "from app.main import app; print('routes ok:', len([r for r in app.routes if '/admin' in getattr(r, 'path', '')]))"
```

Expected: `routes ok: 6` (zones, zones/{id}, dashboard/today, events, events/{id}, devices/{id}/summary).

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/dominion_admin_routes.py
git commit -m "feat(admin): /devices/{id}/summary endpoint"
```

---

### Task D5: Deploy backend + smoke-test endpoints

**Files:**
- None (deploy only)

- [ ] **Step 1: Deploy**

```bash
cd "$REPO" && gcloud run deploy dominion-api --source . --region=us-central1 --quiet | tail -5
```

Expected: `Service [dominion-api] revision [...] has been deployed and is serving 100 percent of traffic.`

- [ ] **Step 2: Hit each admin endpoint**

```bash
for path in \
  "/api/v1/dominion/admin/zones" \
  "/api/v1/dominion/admin/zones/loudoun-corridor" \
  "/api/v1/dominion/admin/dashboard/today" \
  "/api/v1/dominion/admin/events?window_days=30&limit=3" \
  "/api/v1/dominion/admin/devices/demo-tysons-001/summary"; do
  echo "=== $path ==="
  curl -sS -w "\nHTTP %{http_code}\n" "$BASE$path" | head -40
done
```

Expected: each returns `HTTP 200` with JSON body matching its schema.

- [ ] **Step 3: Commit reminder (backend only, no frontend yet)**

Nothing to commit in this task. Smoke test is verification only.

---

## Phase E: Frontend scaffold

### Task E1: Static mount + shell

**Files:**
- Modify: `app/main.py`
- Create: `app/static/dominion_admin/index.html`
- Create: `app/static/dominion_admin/styles.css`

- [ ] **Step 1: Mount the new static dir**

Open `app/main.py`. Find the existing Dominion demo mount (`/dominion-demo`). Immediately below it, add an admin mount.

Add this import near the top if not already present:

```python
_DOMINION_ADMIN_DIR = Path(__file__).resolve().parent / "static" / "dominion_admin"
```

Below the `/dominion-demo` mount:

```python
if _DOMINION_ADMIN_DIR.is_dir():
    app.mount(
        "/dominion-admin",
        StaticFiles(directory=str(_DOMINION_ADMIN_DIR), html=True),
        name="dominion_admin",
    )
```

- [ ] **Step 2: Write `app/static/dominion_admin/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Dominion DER program · Admin</title>
    <link rel="stylesheet" href="styles.css" />
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/vue@3.4.27/dist/vue.global.prod.js"></script>
    <script src="config.js" onerror="/* config.js is optional; see app.js */"></script>
  </head>
  <body>
    <header class="hero">
      <div class="brand">
        <span class="logo">D</span>
        <span class="name">Dominion DER program <span class="badge">Admin · demo</span></span>
      </div>
      <nav>
        <a href="#/" data-route="/">Dashboard</a>
        <a href="#/history" data-route="/history">History</a>
      </nav>
    </header>
    <main id="app">
      <div class="loading">Loading…</div>
    </main>
    <script type="module" src="app.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Write `app/static/dominion_admin/styles.css`**

```css
:root {
  --bg: #0f1419;
  --panel: #1a222c;
  --text: #e7ecf1;
  --muted: #8b98a5;
  --accent: #3d8bfd;
  --ok: #3fb950;
  --warn: #d29922;
  --bad: #e5534b;
  --border: #2d3844;
  --hover: rgba(61, 139, 253, 0.08);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.45;
}

.hero {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand { display: flex; align-items: center; gap: 0.75rem; }
.brand .logo {
  width: 2rem; height: 2rem;
  border-radius: 6px;
  background: var(--accent); color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-weight: 700;
}
.brand .name { font-weight: 600; }
.brand .badge {
  font-size: 0.7rem; color: var(--muted); font-weight: 400; margin-left: 0.25rem;
  padding: 0.1rem 0.4rem; background: var(--panel); border-radius: 4px;
}

nav a {
  color: var(--muted); text-decoration: none; font-size: 0.85rem;
  margin-left: 1rem;
}
nav a.active { color: var(--text); border-bottom: 2px solid var(--accent); padding-bottom: 0.2rem; }

main { padding: 1rem 1.5rem 3rem; }
.loading { color: var(--muted); padding: 2rem; text-align: center; }

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.1rem;
  margin-bottom: 1rem;
}

.hero-banner {
  background: linear-gradient(135deg, #1a2a3e, var(--panel));
  border: 1px solid var(--accent);
}

.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
.grid-2-1 { display: grid; grid-template-columns: 2fr 1fr; gap: 1rem; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }

.kpi .label { color: var(--muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem; }
.kpi .val { font-size: 1.4rem; font-weight: 700; }
.kpi .sub { color: var(--muted); font-size: 0.75rem; }

table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { text-align: left; color: var(--muted); font-weight: 500; padding: 0.5rem; border-bottom: 1px solid var(--border); }
td { padding: 0.5rem; border-bottom: 1px solid var(--border); }
tbody tr:hover { background: var(--hover); cursor: pointer; }

.perfbar { display: inline-flex; align-items: center; gap: 0.4rem; width: 100%; }
.perfbar .track { background: var(--border); height: 0.5rem; border-radius: 3px; flex: 1; overflow: hidden; }
.perfbar .fill { height: 100%; background: var(--ok); }
.perfbar .fill.warn { background: var(--warn); }
.perfbar .fill.bad { background: var(--bad); }

.pill { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.7rem; }
.pill.mand { background: rgba(229, 83, 75, 0.15); color: var(--bad); }
.pill.opt { background: rgba(210, 153, 34, 0.15); color: var(--warn); }
.pill.norm { background: rgba(61, 185, 80, 0.15); color: var(--ok); }

.crumb { color: var(--accent); font-size: 0.8rem; margin-bottom: 0.5rem; }
.crumb a { color: var(--accent); text-decoration: none; }
.crumb a:hover { text-decoration: underline; }

.filters { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
.filter { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 0.3rem 0.6rem; font-size: 0.75rem; cursor: pointer; }
.filter.active { background: var(--accent); color: #fff; border-color: var(--accent); }

#map-leaflet, #mini-map { background: #1a222c; border: 1px solid var(--border); border-radius: 8px; min-height: 20rem; }
#mini-map { min-height: 14rem; }

.chart-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; }
.chart-wrap canvas { width: 100%; height: 16rem; }

.v-green { color: var(--ok); }
.v-warn { color: var(--warn); }
.v-bad { color: var(--bad); }
.muted { color: var(--muted); }
```

- [ ] **Step 3: Commit**

```bash
git add app/main.py app/static/dominion_admin/index.html app/static/dominion_admin/styles.css
git commit -m "feat(admin-ui): mount /dominion-admin and add shell HTML + styles"
```

---

### Task E2: API client + app bootstrap with Vue + router

**Files:**
- Create: `app/static/dominion_admin/api.js`
- Create: `app/static/dominion_admin/app.js`

- [ ] **Step 1: Write `api.js`**

```javascript
// Thin fetch wrapper for the Dominion admin API.
const DEFAULT_BASE = "/api/v1/dominion/admin";

export function apiBase() {
  if (typeof window !== "undefined" && window.__DOMINION_ADMIN_API_BASE__) {
    return String(window.__DOMINION_ADMIN_API_BASE__).replace(/\/$/, "");
  }
  return DEFAULT_BASE;
}

export async function apiJson(path, opts = {}) {
  const res = await fetch(apiBase() + path, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    ...opts,
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = data && typeof data === "object" && data.detail ? JSON.stringify(data.detail) : text;
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return data;
}

export const api = {
  zones:           ()                       => apiJson("/zones"),
  zone:            (zoneId)                 => apiJson(`/zones/${encodeURIComponent(zoneId)}`),
  dashboardToday:  ()                       => apiJson("/dashboard/today"),
  events:          (params = {})            => apiJson("/events" + toQuery(params)),
  eventDetail:     (id)                     => apiJson(`/events/${encodeURIComponent(id)}`),
  deviceSummary:   (id, params = {})        => apiJson(`/devices/${encodeURIComponent(id)}/summary` + toQuery(params)),
};

function toQuery(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}
```

- [ ] **Step 2: Write `app.js`**

```javascript
import { api } from "./api.js";
import { Dashboard } from "./pages/Dashboard.js";
import { EventDetail } from "./pages/EventDetail.js";
import { DeviceDetail } from "./pages/DeviceDetail.js";
import { History } from "./pages/History.js";

const { createApp, reactive, ref, computed, h, onMounted, watch } = Vue;

const ROUTES = [
  { re: /^\/?$/,                     name: "dashboard",    component: Dashboard,   params: () => ({}) },
  { re: /^\/events\/([^/]+)\/?$/,    name: "event-detail", component: EventDetail, params: (m) => ({ eventId: decodeURIComponent(m[1]) }) },
  { re: /^\/devices\/([^/]+)\/?$/,   name: "device-detail",component: DeviceDetail,params: (m) => ({ deviceId: decodeURIComponent(m[1]) }) },
  { re: /^\/history\/?$/,            name: "history",      component: History,     params: () => ({}) },
];

function match(hash) {
  const path = (hash || "#/").replace(/^#/, "") || "/";
  for (const r of ROUTES) {
    const m = path.match(r.re);
    if (m) return { route: r, params: r.params(m) };
  }
  return { route: ROUTES[0], params: {} };
}

const App = {
  setup() {
    const current = ref(match(window.location.hash));
    const onHash = () => { current.value = match(window.location.hash); };
    window.addEventListener("hashchange", onHash);
    watch(current, () => {
      document.querySelectorAll("nav a").forEach((a) => {
        a.classList.toggle("active", a.dataset.route === (window.location.hash.replace(/^#/, "") || "/"));
      });
    }, { immediate: true });

    return () => h(current.value.route.component, { api, ...current.value.params });
  },
};

createApp(App).mount("#app");
```

- [ ] **Step 3: Create empty page/component files as stubs (filled in later tasks)**

Each of these files gets a one-line export so `app.js` imports don't throw when frontend is first loaded.

```bash
mkdir -p "$REPO/app/static/dominion_admin/pages" "$REPO/app/static/dominion_admin/components"
for f in pages/Dashboard.js pages/EventDetail.js pages/DeviceDetail.js pages/History.js \
         components/ZoneCard.js components/DispatchChart.js components/ZoneMap.js \
         components/PerfBar.js components/EventRow.js; do
  name=$(basename "$f" .js)
  echo "export const $name = { props: [], render() { return Vue.h('div', { class: 'muted' }, 'TODO: $name'); } };" \
    > "$REPO/app/static/dominion_admin/$f"
done
```

- [ ] **Step 4: Commit**

```bash
git add app/static/dominion_admin/api.js app/static/dominion_admin/app.js app/static/dominion_admin/pages app/static/dominion_admin/components
git commit -m "feat(admin-ui): Vue app bootstrap, router, API client, page stubs"
```

---

### Task E3: Shared components — `PerfBar`, `EventRow`, `ZoneCard`

**Files:**
- Modify: `app/static/dominion_admin/components/PerfBar.js`
- Modify: `app/static/dominion_admin/components/EventRow.js`
- Modify: `app/static/dominion_admin/components/ZoneCard.js`

- [ ] **Step 1: PerfBar**

Replace `components/PerfBar.js`:

```javascript
const { h } = Vue;

export const PerfBar = {
  props: { pct: { type: [Number, null], default: null } },
  render() {
    const pct = this.pct == null ? null : Math.max(0, Math.min(100, this.pct));
    const cls = pct == null ? "" : pct >= 90 ? "" : pct >= 75 ? "warn" : "bad";
    return h("span", { class: "perfbar" }, [
      h("span", { class: "track" }, [
        h("span", {
          class: `fill ${cls}`,
          style: { width: pct == null ? "0%" : `${pct}%` },
        }),
      ]),
      h("span",
        { class: pct == null ? "muted" : `v-${cls || "green"}`, style: { minWidth: "3rem", textAlign: "right" } },
        pct == null ? "—" : `${pct.toFixed(0)}%`),
    ]);
  },
};
```

- [ ] **Step 2: EventRow**

Replace `components/EventRow.js`:

```javascript
import { PerfBar } from "./PerfBar.js";
const { h } = Vue;

function fmtEPT(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      timeZone: "America/New_York",
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export const EventRow = {
  components: { PerfBar },
  props: { ev: { type: Object, required: true }, showZone: { type: Boolean, default: true } },
  render() {
    const ev = this.ev;
    return h("tr", { onClick: () => (window.location.hash = `#/events/${encodeURIComponent(ev.event_id)}`) }, [
      h("td", null, ev.event_id),
      h("td", null, fmtEPT(ev.start_utc) + ` · ${ev.duration_hours}h`),
      this.showZone ? h("td", null, ev.zone_id || "—") : null,
      h("td", null, ev.primary_pnode_name || ev.primary_pnode_id),
      h("td", null, ev.has_mandatory
        ? h("span", { class: "pill mand" }, `${ev.extreme_hours}h mand`)
        : h("span", { class: "pill opt" }, `${ev.stressed_hours}h opt`)),
      h("td", null, ev.listed_capacity_kw_avg ? `${(ev.listed_capacity_kw_avg).toFixed(0)} kW` : "—"),
      h("td", null, ev.realized_capacity_kw_avg ? `${(ev.realized_capacity_kw_avg).toFixed(0)} kW` : "—"),
      h("td", null, h(PerfBar, { pct: ev.performance_pct })),
    ].filter(Boolean));
  },
};
```

- [ ] **Step 3: ZoneCard**

Replace `components/ZoneCard.js`:

```javascript
const { h } = Vue;

export const ZoneCard = {
  props: { zone: { type: Object, required: true }, slice: { type: Object, default: () => ({}) }, lastPerf: { type: [Number, null], default: null } },
  render() {
    const z = this.zone;
    const sl = this.slice || {};
    const peakMw = (sl.peak_kw || 0) / 1000;
    const listedMw = (z.listed_capacity_kw || 0) / 1000;
    return h("div", { class: "panel" }, [
      h("div", { class: "kpi" }, [
        h("div", { class: "label" }, z.label),
        h("div", { class: "val" }, `${listedMw.toFixed(1)} MW`),
        h("div", { class: "sub" },
          `${z.device_count} devices · ${sl.events || 0} events fcst · peak ${peakMw.toFixed(1)} MW`),
        this.lastPerf != null
          ? h("div", { class: "sub" }, `last event perf ${this.lastPerf.toFixed(0)}%`)
          : null,
      ]),
    ]);
  },
};
```

- [ ] **Step 4: Commit**

```bash
git add app/static/dominion_admin/components/
git commit -m "feat(admin-ui): shared components (PerfBar, EventRow, ZoneCard)"
```

---

### Task E4: Chart + map components

**Files:**
- Modify: `app/static/dominion_admin/components/DispatchChart.js`
- Modify: `app/static/dominion_admin/components/ZoneMap.js`

- [ ] **Step 1: DispatchChart**

Replace `components/DispatchChart.js`:

```javascript
const { h, onMounted, onBeforeUnmount, ref, watch } = Vue;

export const DispatchChart = {
  props: {
    labels: { type: Array, required: true },
    datasets: { type: Array, required: true }, // [{label, data, kind:'line'|'bar'|'band', color}]
    height: { type: Number, default: 220 },
  },
  setup(props) {
    const canvas = ref(null);
    let chart = null;

    function draw() {
      if (!canvas.value) return;
      if (chart) chart.destroy();
      const ds = props.datasets.map((d) => {
        const base = { label: d.label, data: d.data, borderColor: d.color, backgroundColor: d.color };
        if (d.kind === "bar") return { ...base, type: "bar", borderWidth: 0 };
        if (d.kind === "band") return { ...base, type: "line", fill: "+1", backgroundColor: d.color + "33", pointRadius: 0, tension: 0.1 };
        return { ...base, type: "line", tension: 0.2, pointRadius: 0, spanGaps: true };
      });
      chart = new Chart(canvas.value.getContext("2d"), {
        data: { labels: props.labels, datasets: ds },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { labels: { color: "#c9d1d9" } } },
          scales: {
            x: { ticks: { color: "#8b98a5", maxRotation: 45 } },
            y: { ticks: { color: "#8b98a5" }, grid: { color: "#2d3844" } },
          },
        },
      });
    }
    onMounted(draw);
    watch(() => [props.labels, props.datasets], draw, { deep: true });
    onBeforeUnmount(() => chart && chart.destroy());
    return () => h("div", { class: "chart-wrap" },
      h("canvas", { ref: canvas, height: props.height }));
  },
};
```

- [ ] **Step 2: ZoneMap**

Replace `components/ZoneMap.js`:

```javascript
const { h, onMounted, onBeforeUnmount, ref, watch } = Vue;

export const ZoneMap = {
  props: {
    devices: { type: Array, required: true },   // [{device_id, zone_id, asset_lat, asset_lon, listed_capacity_kw, perf_pct}]
    pnodeCoords: { type: Object, default: () => ({}) }, // primary_pnode_id -> [lat, lon]
    minHeight: { type: String, default: "20rem" },
    id: { type: String, default: "map-leaflet" },
  },
  setup(props) {
    const mapEl = ref(null);
    let map = null;
    let markers = [];

    function colorForPerf(pct) {
      if (pct == null) return "#8b98a5";
      if (pct >= 90) return "#3fb950";
      if (pct >= 75) return "#d29922";
      return "#e5534b";
    }

    function renderMarkers() {
      if (!map) return;
      markers.forEach((m) => m.remove());
      markers = [];
      const pts = [];
      for (const d of props.devices) {
        const color = colorForPerf(d.perf_pct);
        if (d.asset_lat != null && d.asset_lon != null) {
          const m = L.circleMarker([d.asset_lat, d.asset_lon], {
            radius: 8, color, fillColor: "#98df8a", fillOpacity: 0.7, weight: 2,
          }).bindPopup(`<b>${d.device_id_external}</b><br>listed ${d.listed_capacity_kw || "—"} kW<br>perf ${d.perf_pct != null ? d.perf_pct.toFixed(0) + "%" : "—"}`)
            .addTo(map);
          markers.push(m);
          pts.push([d.asset_lat, d.asset_lon]);
        }
        const coords = props.pnodeCoords[d.primary_pnode_id];
        if (coords) {
          const m = L.circleMarker(coords, {
            radius: 6, color: "#1f77b4", fillColor: "#aec7e8", fillOpacity: 0.7, weight: 2,
          }).bindPopup(`<b>pnode ${d.primary_pnode_id}</b>`).addTo(map);
          markers.push(m);
          pts.push(coords);
        }
      }
      if (pts.length) map.fitBounds(pts, { padding: [20, 20] });
    }

    onMounted(() => {
      map = L.map(mapEl.value, { zoomControl: true }).setView([38.9, -77.35], 9);
      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
        attribution: "© OSM © CARTO", subdomains: "abcd", maxZoom: 19,
      }).addTo(map);
      renderMarkers();
    });
    watch(() => [props.devices, props.pnodeCoords], renderMarkers, { deep: true });
    onBeforeUnmount(() => map && map.remove());

    return () => h("div", {
      id: props.id,
      ref: mapEl,
      style: { minHeight: props.minHeight, width: "100%" },
    });
  },
};
```

- [ ] **Step 3: Commit**

```bash
git add app/static/dominion_admin/components/DispatchChart.js app/static/dominion_admin/components/ZoneMap.js
git commit -m "feat(admin-ui): DispatchChart + ZoneMap shared components"
```

---

## Phase F: Frontend pages

### Task F1: Dashboard page

**Files:**
- Modify: `app/static/dominion_admin/pages/Dashboard.js`

- [ ] **Step 1: Replace Dashboard.js**

```javascript
import { ZoneCard } from "../components/ZoneCard.js";
import { EventRow } from "../components/EventRow.js";
import { DispatchChart } from "../components/DispatchChart.js";
import { ZoneMap } from "../components/ZoneMap.js";

const { h, ref, onMounted } = Vue;

export const Dashboard = {
  components: { ZoneCard, EventRow, DispatchChart, ZoneMap },
  props: { api: { type: Object, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const today = ref(null);
    const zones = ref([]);
    const recent = ref([]);

    async function load() {
      try {
        const [t, z, r] = await Promise.all([
          props.api.dashboardToday(),
          props.api.zones(),
          props.api.events({ window_days: 30, limit: 6 }),
        ]);
        today.value = t;
        zones.value = z;
        recent.value = r.events;
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);

    return () => {
      if (state.value.loading) return h("div", { class: "loading" }, "Loading dashboard…");
      if (state.value.err) return h("div", { class: "panel", style: { color: "#e5534b" } }, state.value.err);

      const t = today.value;
      const labels = t.fleet_24h_signal.map((x) => new Date(x.hour_utc).toLocaleTimeString(undefined, { timeZone: "America/New_York", hour: "2-digit" }));
      const sig = t.fleet_24h_signal.map((x) => x.program_signal);

      return h("div", null, [
        h("div", { class: "panel hero-banner" }, [
          h("div", { class: "label", style: { color: "#8b98a5" } }, `Operating ${t.operating_date} · ${t.forecast_basis === "tomorrow_da" ? "PJM DA (tomorrow)" : "most recent DA"}`),
          h("div", { style: { fontSize: "1.3rem", fontWeight: 600 } },
            `${t.events_forecast} events forecast · peak ${(t.peak_program_kw / 1000).toFixed(1)} MW`),
        ]),
        h("div", { class: "grid-3" }, zones.value.map((z) => h(ZoneCard, {
          zone: z,
          slice: (t.by_zone || []).find((s) => s.zone_id === z.id) || {},
        }))),
        h("div", { class: "grid-2-1" }, [
          h(DispatchChart, {
            labels,
            datasets: [{ label: "Fleet program signal (avg)", data: sig, color: "#3fb950", kind: "line" }],
          }),
          h(ZoneMap, {
            devices: zones.value.flatMap((z) => z.device_ids.map((d) => ({ device_id_external: d, zone_id: z.id }))),
            minHeight: "18rem",
          }),
        ]),
        h("div", { class: "panel" }, [
          h("h3", { style: { marginTop: 0 } }, "Recent events"),
          h("table", null, [
            h("thead", null, h("tr", null, [
              ["Event", "Start", "Zone", "Pnode", "Tier", "Listed avg", "Realized avg", "Perf"]
                .map((t) => h("th", null, t)),
            ])),
            h("tbody", null, recent.value.map((ev) => h(EventRow, { ev }))),
          ]),
        ]),
      ]);
    };
  },
};
```

- [ ] **Step 2: Manual verification**

With the backend already deployed from Task D5, and the frontend only built locally so far, we need a local preview to exercise the Dashboard before deploying. Run the FastAPI app locally:

```bash
cd "$REPO" && DATABASE_URL="$DSN" PJM_SUBSCRIPTION_KEY=dummy \
  "$PY" -m uvicorn app.main:app --port 8001
```

(In a second terminal) open http://localhost:8001/dominion-admin/ in a browser. Confirm:
- Hero banner renders with today's operating date.
- Three zone cards appear.
- Fleet 24h chart draws.
- Leaflet map mounts and shows a gray tile base.
- Recent events table shows rows clickable to `#/events/:id` (will 404-render until F2 but the URL changes).

Stop the local server with Ctrl-C.

- [ ] **Step 3: Commit**

```bash
git add app/static/dominion_admin/pages/Dashboard.js
git commit -m "feat(admin-ui): dashboard page (hero, zones, chart, map, recent events)"
```

---

### Task F2: Event detail page

**Files:**
- Modify: `app/static/dominion_admin/pages/EventDetail.js`

- [ ] **Step 1: Replace EventDetail.js**

```javascript
import { PerfBar } from "../components/PerfBar.js";
import { DispatchChart } from "../components/DispatchChart.js";
import { ZoneMap } from "../components/ZoneMap.js";

const { h, ref, onMounted, watch } = Vue;

function fmt(v, fn, fallback = "—") {
  return v == null ? fallback : fn(v);
}

export const EventDetail = {
  components: { PerfBar, DispatchChart, ZoneMap },
  props: { api: { type: Object, required: true }, eventId: { type: String, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const ev = ref(null);

    async function load() {
      try {
        ev.value = await props.api.eventDetail(props.eventId);
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);
    watch(() => props.eventId, load);

    return () => {
      if (state.value.loading) return h("div", { class: "loading" }, "Loading event…");
      if (state.value.err) return h("div", { class: "panel", style: { color: "#e5534b" } }, state.value.err);

      const e = ev.value;
      const labels = e.hours.map((h) => {
        const d = new Date(h.interval_start_utc);
        return d.toLocaleTimeString(undefined, { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" });
      });
      const ds = [
        { label: "Program signal", data: e.hours.map((h) => h.dispatch_signal_program), color: "#3d8bfd", kind: "line" },
        { label: "Listed ask (kW)", data: e.hours.map((h) => h.listed_kw_ask), color: "#d29922", kind: "line" },
        { label: "Realized (kW)",   data: e.hours.map((h) => h.realized_kw), color: "#3fb950", kind: "bar" },
      ];

      return h("div", null, [
        h("div", { class: "crumb" }, [
          h("a", { href: "#/" }, "Dashboard"), " › ",
          h("a", { href: "#/history" }, "Events"), " › ",
          h("span", null, e.event_id),
        ]),
        h("div", { class: "panel hero-banner" }, [
          h("div", { style: { fontSize: "1.1rem", fontWeight: 600 } },
            `${e.event_id} · ${e.duration_hours}h · ${e.device_id_external}`),
          h("div", { class: "muted" },
            `Operating ${e.operating_date} · ${e.stressed_hours} stressed + ${e.extreme_hours} mandatory · zone ${e.zone_id || "—"}`),
        ]),
        h("div", { class: "grid-4" }, [
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Listed capacity (avg)"),
            h("div", { class: "val" }, fmt(e.listed_capacity_kw_avg, (v) => `${v.toFixed(0)} kW`)),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Realized capacity (avg)"),
            h("div", { class: "val" }, fmt(e.realized_capacity_kw_avg, (v) => `${v.toFixed(0)} kW`)),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Performance"),
            h("div", { class: "val" }, fmt(e.performance_pct, (v) => `${v.toFixed(1)}%`)),
            h("div", { class: "sub" }, "realized / listed"),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Mandatory performance"),
            h("div", { class: "val" }, fmt(e.mandatory_performance_pct, (v) => `${v.toFixed(1)}%`)),
            h("div", { class: "sub" }, "extreme hours only"),
          ]),
        ]),
        h("div", { class: "grid-2-1" }, [
          h(DispatchChart, { labels, datasets: ds, height: 240 }),
          h(ZoneMap, {
            id: "mini-map",
            minHeight: "14rem",
            devices: [{
              device_id_external: e.device_id_external,
              primary_pnode_id: e.primary_pnode_id,
              zone_id: e.zone_id,
              perf_pct: e.performance_pct,
            }],
          }),
        ]),
      ]);
    };
  },
};
```

- [ ] **Step 2: Manual verification**

Run the same local server as in Task F1. Navigate to `http://localhost:8001/dominion-admin/#/events/<some_event_id>` using an ID copied from `/api/v1/dominion/admin/events?limit=1`. Confirm hero, 4 KPI cards, chart with 3 series, mini-map, and breadcrumb links.

- [ ] **Step 3: Commit**

```bash
git add app/static/dominion_admin/pages/EventDetail.js
git commit -m "feat(admin-ui): event detail page"
```

---

### Task F3: Device detail page

**Files:**
- Modify: `app/static/dominion_admin/pages/DeviceDetail.js`

- [ ] **Step 1: Replace DeviceDetail.js**

```javascript
import { PerfBar } from "../components/PerfBar.js";
import { EventRow } from "../components/EventRow.js";
import { DispatchChart } from "../components/DispatchChart.js";

const { h, ref, onMounted, watch } = Vue;

export const DeviceDetail = {
  components: { PerfBar, EventRow, DispatchChart },
  props: { api: { type: Object, required: true }, deviceId: { type: String, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const data = ref(null);

    async function load() {
      try {
        data.value = await props.api.deviceSummary(props.deviceId, { window_days: 30, recent_limit: 20 });
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);
    watch(() => props.deviceId, load);

    return () => {
      if (state.value.loading) return h("div", { class: "loading" }, "Loading device…");
      if (state.value.err) return h("div", { class: "panel", style: { color: "#e5534b" } }, state.value.err);

      const d = data.value;
      const labels = d.recent_events.slice().reverse().map((e) => new Date(e.start_utc).toLocaleDateString());
      const perf = d.recent_events.slice().reverse().map((e) => e.performance_pct);

      return h("div", null, [
        h("div", { class: "crumb" }, [
          h("a", { href: "#/" }, "Dashboard"), " › ",
          h("span", null, d.device_id_external),
        ]),
        h("div", { class: "panel hero-banner" }, [
          h("div", { style: { fontSize: "1.1rem", fontWeight: 600 } },
            `${d.device_id_external} · ${d.primary_pnode_name || d.primary_pnode_id}`),
          h("div", { class: "muted" },
            `listed ${d.listed_capacity_kw || "—"} kW · zone ${d.zone_id || "—"} · window ${d.window_start} → ${d.window_end}`),
        ]),
        h("div", { class: "grid-4" }, [
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Events"),
            h("div", { class: "val" }, d.event_count),
            h("div", { class: "sub" }, `${d.total_dispatch_hours} dispatch hrs`),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Avg performance"),
            h("div", { class: "val" }, d.avg_performance_pct != null ? `${d.avg_performance_pct.toFixed(0)}%` : "—"),
            h("div", { class: "sub" }, d.rank_in_fleet != null ? `rank ${d.rank_in_fleet}` : ""),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Mandatory performance"),
            h("div", { class: "val" }, d.mandatory_performance_pct != null ? `${d.mandatory_performance_pct.toFixed(0)}%` : "—"),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Realized energy"),
            h("div", { class: "val" }, `${d.total_realized_energy_mwh.toFixed(1)} MWh`),
          ]),
        ]),
        h(DispatchChart, {
          labels,
          datasets: [{ label: "Performance % per event", data: perf, color: "#3d8bfd", kind: "line" }],
        }),
        h("div", { class: "panel" }, [
          h("h3", { style: { marginTop: 0 } }, "Recent events"),
          h("table", null, [
            h("thead", null, h("tr", null, ["Event", "Start", "Pnode", "Tier", "Listed avg", "Realized avg", "Perf"].map((t) => h("th", null, t)))),
            h("tbody", null, d.recent_events.map((ev) => h(EventRow, { ev, showZone: false }))),
          ]),
        ]),
      ]);
    };
  },
};
```

- [ ] **Step 2: Manual verification**

Local server again. Navigate to `http://localhost:8001/dominion-admin/#/devices/demo-tysons-001`. Confirm hero, 4 KPI tiles, per-event performance chart, and recent events table.

- [ ] **Step 3: Commit**

```bash
git add app/static/dominion_admin/pages/DeviceDetail.js
git commit -m "feat(admin-ui): device detail page"
```

---

### Task F4: History page

**Files:**
- Modify: `app/static/dominion_admin/pages/History.js`

- [ ] **Step 1: Replace History.js**

```javascript
import { EventRow } from "../components/EventRow.js";

const { h, ref, onMounted, watch } = Vue;

const WINDOWS = [
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
  { label: "365d", value: 365 },
];

export const History = {
  components: { EventRow },
  props: { api: { type: Object, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const zones = ref([]);
    const rows = ref([]);
    const windowDays = ref(30);
    const zoneId = ref(null);
    const hasMand = ref(null);
    const minPerf = ref(null);

    async function load() {
      state.value = { loading: true, err: null };
      try {
        if (!zones.value.length) zones.value = await props.api.zones();
        const params = { window_days: windowDays.value, limit: 200 };
        if (zoneId.value) params.zone_id = zoneId.value;
        if (hasMand.value != null) params.has_mandatory = hasMand.value;
        if (minPerf.value != null) params.min_perf = minPerf.value;
        const r = await props.api.events(params);
        rows.value = r.events;
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);
    watch([windowDays, zoneId, hasMand, minPerf], load);

    return () => {
      return h("div", null, [
        h("div", { class: "crumb" }, [h("a", { href: "#/" }, "Dashboard"), " › ", h("span", null, "History")]),
        h("div", { class: "panel" }, [
          h("div", { class: "filters" }, [
            ...WINDOWS.map((w) => h("span", {
              class: `filter ${windowDays.value === w.value ? "active" : ""}`,
              onClick: () => (windowDays.value = w.value),
            }, w.label)),
            h("span", { class: "filter muted" }, "zone:"),
            h("span", {
              class: `filter ${zoneId.value == null ? "active" : ""}`,
              onClick: () => (zoneId.value = null),
            }, "all"),
            ...zones.value.map((z) => h("span", {
              class: `filter ${zoneId.value === z.id ? "active" : ""}`,
              onClick: () => (zoneId.value = z.id),
            }, z.label)),
            h("span", {
              class: `filter ${hasMand.value === true ? "active" : ""}`,
              onClick: () => (hasMand.value = hasMand.value === true ? null : true),
            }, "mandatory-only"),
            h("span", {
              class: `filter ${minPerf.value === 85 ? "active" : ""}`,
              onClick: () => (minPerf.value = minPerf.value === 85 ? null : 85),
            }, "perf ≥ 85%"),
          ]),
          state.value.loading ? h("div", { class: "loading" }, "Loading…") :
          state.value.err ? h("div", { style: { color: "#e5534b" } }, state.value.err) :
          h("table", null, [
            h("thead", null, h("tr", null, ["Event", "Start", "Zone", "Pnode", "Tier", "Listed avg", "Realized avg", "Perf"].map((t) => h("th", null, t)))),
            h("tbody", null, rows.value.map((ev) => h(EventRow, { ev }))),
          ]),
        ]),
      ]);
    };
  },
};
```

- [ ] **Step 2: Manual verification**

Local server. Navigate to `http://localhost:8001/dominion-admin/#/history`. Confirm filters render, clicking them reloads the table, 30d shows a subset of events, and clicking a row navigates to its detail.

- [ ] **Step 3: Commit**

```bash
git add app/static/dominion_admin/pages/History.js
git commit -m "feat(admin-ui): history page with filters"
```

---

## Phase G: Deploy + verify + push

### Task G1: Deploy Cloud Run with the new UI

**Files:**
- None (deploy only)

- [ ] **Step 1: Deploy**

```bash
cd "$REPO" && gcloud run deploy dominion-api --source . --region=us-central1 --quiet | tail -5
```

Expected: revision promoted, URL echoed.

- [ ] **Step 2: Smoke-check endpoints + static UI**

```bash
# API
for p in "/health" \
         "/api/v1/dominion/admin/zones" \
         "/api/v1/dominion/admin/dashboard/today" \
         "/api/v1/dominion/admin/events?limit=3"; do
  echo "=== $p ==="
  curl -sS -o /dev/null -w "HTTP %{http_code}  %{size_download}B\n" "$BASE$p"
done

# Static UI
for f in "/dominion-admin/" "/dominion-admin/app.js" "/dominion-admin/styles.css"; do
  echo "=== $f ==="
  curl -sS -o /dev/null -w "HTTP %{http_code}  %{size_download}B\n" "$BASE$f"
done
```

Expected: every line reports `HTTP 200`.

- [ ] **Step 3: End-to-end flow in a real browser**

Open `https://dominion-api-558972293204.us-central1.run.app/dominion-admin/` in Chrome or Safari. Confirm:
- Hero banner shows today's operating date and forecast basis.
- Three zone cards render with MW totals.
- Fleet 24h signal chart draws.
- Leaflet map loads with tiles.
- Recent events table has clickable rows.
- Clicking an event row navigates to the event detail page with chart + KPIs.
- Clicking a device ID (event row) navigates to device detail.
- Clicking `History` in the header navigates to `/history` with filters.

If any of the above fails, open the browser console, note the error, fix in code, redeploy, re-verify.

- [ ] **Step 4: Push branch**

```bash
cd "$REPO" && git push github main:feature/dominion-poc | tail -5
```

Expected: commits appear on `feature/dominion-poc` at github.

- [ ] **Step 5: Final spec + plan alignment check**

Reopen `docs/superpowers/specs/2026-04-18-dominion-admin-dashboard-design.md`. Confirm:
- §3 components all exist on disk.
- §4 column exists in Cloud SQL (`SELECT listed_capacity_kw FROM dominion_devices LIMIT 1;` via the proxy).
- §5 endpoints all return 200 (see step 2).
- §7 telemetry mock is reproducible (reload a specific event twice; numbers match).
- §9 frontend mockups match what's on screen.

Any gaps: file a follow-up commit; don't silently diverge.

---

## Self-review hint

After reading through this plan, check:

1. **Every spec requirement has a task** — §1 five surfaces, §3 components, §4 data model, §5 six endpoints, §6 event materialization, §7 telemetry sim, §8 forecast rule, §9 pages, §10 seeding, §11 tests, §12 deploy. Map each onto a task above. Any gap: add a task.
2. **No placeholders** in any step. If a step says "implement X" with no code, rewrite it.
3. **Types stay consistent.** `DeviceEvent`, `DispatchHourRow`, `AdminEventSummary`, etc. are spelled identically every place they appear.
4. **Every test step shows the code**, not "similar to task N".
5. **Commands quote paths with spaces**; `$REPO` and `$DSN` are exported where needed.
