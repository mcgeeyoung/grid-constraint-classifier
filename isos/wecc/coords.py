"""WECC DGAP centroids -- one coordinate per BAA control area.

Coordinates are the BAA control center / largest load center; they
anchor the DGAPs on a regional map. No HIFLD matching applies because
DGAPs are aggregates, not substations.
"""
from __future__ import annotations


WECC_DGAP_CENTROIDS: dict[str, tuple[float, float]] = {
    "DGAP_CISO-APND":   (35.3733, -119.0187),  # CAISO / California (Bakersfield)
    "DGAP_BANC-APND":   (38.5816, -121.4944),  # SMUD / Sacramento
    "DGAP_TIDC-APND":   (37.4946, -120.8466),  # Turlock CA
    "DGAP_LADWP-APND":  (34.0522, -118.2437),  # LADWP / LA
    "DGAP_PACE-APND":   (40.7608, -111.8910),  # PacifiCorp East / Salt Lake City
    "DGAP_PACW-APND":   (45.5152, -122.6784),  # PacifiCorp West / Portland
    "DGAP_PGE-APND":    (45.5152, -122.6784),  # Portland General Electric
    "DGAP_AVA-APND":    (47.6588, -117.4260),  # Avista / Spokane
    "DGAP_PSEI-APND":   (47.6062, -122.3321),  # Puget Sound Energy / Seattle area
    "DGAP_SCL-APND":    (47.6062, -122.3321),  # Seattle City Light
    "DGAP_TPWR-APND":   (47.2529, -122.4443),  # Tacoma Power
    "DGAP_BPAT-APND":   (45.6428, -121.9019),  # Bonneville / The Dalles area
    "DGAP_BCHA-APND":   (49.2827, -123.1207),  # BC Hydro / Vancouver BC
    "DGAP_IPCO-APND":   (43.6150, -116.2023),  # Idaho Power / Boise
    "DGAP_NWMT-APND":   (45.7833, -108.5007),  # NorthWestern Energy / Billings MT
    "DGAP_NEVP-APND":   (36.1699, -115.1398),  # NV Energy / Las Vegas
    "DGAP_AZPS-APND":   (33.4484, -112.0740),  # APS / Phoenix
    "DGAP_SRP-APND":    (33.4484, -112.0740),  # Salt River Project / Phoenix
    "DGAP_TEPC-APND":   (32.2226, -110.9747),  # Tucson Electric Power
    "DGAP_PNM-APND":    (35.0844, -106.6504),  # Public Service of NM / Albuquerque
    "DGAP_EPE-APND":    (31.7619, -106.4850),  # El Paso Electric
    "DGAP_WALC-APND":   (35.1983, -114.4869),  # WAPA Lower Colorado / Bullhead City AZ
    "DGAP_AVRN-APND":   (45.5152, -122.6784),  # Avangrid Renewables (rough Pacific NW)
}


def aggregate_centroids() -> dict[str, tuple[float, float]]:
    return dict(WECC_DGAP_CENTROIDS)


def normalize_pnode_name(pname: str) -> list[str]:
    return []
