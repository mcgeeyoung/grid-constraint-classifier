"""Registry of available PUC scrapers."""

from typing import Optional

from .base import PUCScraper
from .cpuc import CPUCScraper
from .vascc import VASCCScraper
from .ncuc import NCUCScraper
from .nypsc import NYPSCScraper


_SCRAPER_MAP: dict[str, type[PUCScraper]] = {
    "CA": CPUCScraper,
    "VA": VASCCScraper,
    "NC": NCUCScraper,
    "NY": NYPSCScraper,
}


def get_scraper(state: str, **kwargs) -> PUCScraper:
    """Get a PUC scraper for a state."""
    state = state.upper()
    if state not in _SCRAPER_MAP:
        available = ", ".join(sorted(_SCRAPER_MAP.keys()))
        raise ValueError(f"No scraper for state '{state}'. Available: {available}")
    return _SCRAPER_MAP[state](**kwargs)


def list_scrapers() -> list[str]:
    """List available scraper state codes."""
    return sorted(_SCRAPER_MAP.keys())


def get_all_scrapers(**kwargs) -> dict[str, PUCScraper]:
    """Get all available scrapers."""
    return {state: cls(**kwargs) for state, cls in _SCRAPER_MAP.items()}
