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
    assert events[0].event_id == "E-2026-04-15-d1-10"
