"""ISO driver registry.

Resolve a driver by `iso_id` without importing per-ISO subpackages
directly. Each driver is registered with a factory that lazily imports
its subpackage on first use, so importing `isos` stays cheap.

Example:

    >>> from isos import get_driver
    >>> driver = get_driver("CAISO")
    >>> driver.iso_id
    'CAISO'

    >>> driver = get_driver("PJM")  # reads PJM_SUBSCRIPTION_KEY from env
    >>> driver = get_driver("PJM", subscription_key="...")  # or pass explicitly

To plug in a new ISO, drop a `client.py` and `driver.py` under
`isos/<iso_id>/`, then add a factory and a `register_driver(...)` call
to the built-in section below.
"""
from __future__ import annotations

import os
from typing import Callable, Dict

from isos.base import ISODriver, NodeMeta

_FACTORIES: Dict[str, Callable[..., ISODriver]] = {}


def register_driver(iso_id: str, factory: Callable[..., ISODriver]) -> None:
    """Register a `(**kwargs) -> ISODriver` factory for an ISO id.

    Idempotent: re-registering the same iso_id replaces the prior factory,
    which is convenient for tests that swap in stubs.
    """
    _FACTORIES[iso_id.upper()] = factory


def get_driver(iso_id: str, **kwargs) -> ISODriver:
    """Instantiate the registered driver for `iso_id`. kwargs flow to the factory."""
    key = iso_id.upper()
    if key not in _FACTORIES:
        raise KeyError(
            f"No ISO driver registered for {iso_id!r}. "
            f"Registered: {sorted(_FACTORIES)}"
        )
    return _FACTORIES[key](**kwargs)


def list_isos() -> list[str]:
    """List the iso_ids that have a registered driver."""
    return sorted(_FACTORIES)


# --- Built-in registrations -------------------------------------------------
# Factories use lazy imports so that `import isos` doesn't pull in the HTTP
# clients or pandas-heavy code paths until a driver is actually requested.


def _pjm_factory(*, subscription_key: str | None = None):
    from isos.pjm.client import PJMClient
    from isos.pjm.driver import PJMDriver

    key = subscription_key or os.environ.get("PJM_SUBSCRIPTION_KEY")
    if not key:
        raise RuntimeError(
            "PJMDriver requires a `subscription_key` kwarg or PJM_SUBSCRIPTION_KEY env var"
        )
    return PJMDriver(PJMClient(key))


def _caiso_factory():
    from isos.caiso.driver import CAISODriver

    return CAISODriver()


def _nyiso_factory():
    from isos.nyiso.driver import NYISODriver

    return NYISODriver()


def _miso_factory():
    from isos.miso.driver import MISODriver

    return MISODriver()


def _isone_factory():
    from isos.isone.driver import ISONEDriver

    return ISONEDriver()


def _spp_factory():
    from isos.spp.driver import SPPDriver

    return SPPDriver()


def _wecc_factory():
    from isos.wecc.driver import WECCDriver

    return WECCDriver()


def _ercot_factory(
    *,
    username: str | None = None,
    password: str | None = None,
    subscription_key: str | None = None,
):
    from isos.ercot.client import ERCOTClient
    from isos.ercot.driver import ERCOTDriver

    user = username or os.environ.get("ERCOT_API_USERNAME")
    pw = password or os.environ.get("ERCOT_API_PASSWORD")
    key = subscription_key or os.environ.get("ERCOT_API_SUBSCRIPTION_KEY")
    missing = [
        n
        for n, v in [
            ("ERCOT_API_USERNAME", user),
            ("ERCOT_API_PASSWORD", pw),
            ("ERCOT_API_SUBSCRIPTION_KEY", key),
        ]
        if not v
    ]
    if missing:
        raise RuntimeError(
            "ERCOTDriver requires "
            + ", ".join(missing)
            + " (or matching `username`/`password`/`subscription_key` kwargs)"
        )
    return ERCOTDriver(ERCOTClient(user, pw, key))


register_driver("PJM", _pjm_factory)
register_driver("CAISO", _caiso_factory)
register_driver("NYISO", _nyiso_factory)
register_driver("MISO", _miso_factory)
register_driver("ISONE", _isone_factory)
register_driver("SPP", _spp_factory)
register_driver("WECC", _wecc_factory)
register_driver("ERCOT", _ercot_factory)


__all__ = [
    "ISODriver",
    "NodeMeta",
    "register_driver",
    "get_driver",
    "list_isos",
]
