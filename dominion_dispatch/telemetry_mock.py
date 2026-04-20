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
    device_id_external: str,
    pnode_id_external: str | None,
    utility_id: str | None = None,
) -> str | None:
    if pnode_id_external is None:
        return None
    idx = load_zones(utility_id)
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
    utility_id: str | None = None,
) -> float:
    """Return deterministic realized kW for one hour of a mocked event."""
    if dispatch_signal_program <= 0 or listed_kw <= 0:
        return 0.0

    baseline = DEVICE_BASELINE.get(device_id_external, DEFAULT_BASELINE)
    zone_id = _zone_id_for_device(device_id_external, pnode_id_external, utility_id)
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
