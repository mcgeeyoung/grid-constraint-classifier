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
