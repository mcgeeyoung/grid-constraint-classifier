"""
Grid Constraint Classifier API

FastAPI application serving classification results, LMP data,
data center locations, and DER recommendations across all 7 US ISOs.

Executive SPAs: ``/dominion/`` and ``/pge/`` (shared static, tenant-aware via
URL) calling ``/api/v1/{utility_id}/admin/*``. Dominion demo at
``/dominion-demo/``; Dominion ops at ``/dominion-admin/``.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api.v1.routes import router as v1_router

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_DOMINION_DEMO_DIR = _STATIC_DIR / "dominion_demo"
_DOMINION_ADMIN_DIR = _STATIC_DIR / "dominion_admin"
_UTILITY_EXEC_DIR = _STATIC_DIR / "utility_executive"

# Executive SPA tenants. Each mounts the same static dir; the SPA parses the
# utility_id from its own URL and fetches /api/v1/{utility_id}/admin/ui-config
# for tenant-specific copy, zones, scenarios, and pilot pnodes. To add a new
# tenant, create utilities/<id>/{config.yaml,zones.yaml,scenarios.json,
# pilot_pnodes.json} and add the id to _EXEC_TENANTS below.
_EXEC_TENANTS = ("dominion", "pge")

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=(
        "API for the Grid Constraint Classifier, providing zone classifications, "
        "pnode congestion scores, data center locations, and DER recommendations "
        "across all 7 US ISOs (PJM, CAISO, MISO, SPP, ISO-NE, NYISO, ERCOT)."
    ),
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(v1_router)

if _STATIC_DIR.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="static",
    )

if _DOMINION_DEMO_DIR.is_dir():
    app.mount(
        "/dominion-demo",
        StaticFiles(directory=str(_DOMINION_DEMO_DIR), html=True),
        name="dominion_demo",
    )

if _DOMINION_ADMIN_DIR.is_dir():
    app.mount(
        "/dominion-admin",
        StaticFiles(directory=str(_DOMINION_ADMIN_DIR), html=True),
        name="dominion_admin",
    )

if _UTILITY_EXEC_DIR.is_dir():
    for _utility_id in _EXEC_TENANTS:
        app.mount(
            f"/{_utility_id}",
            StaticFiles(directory=str(_UTILITY_EXEC_DIR), html=True),
            name=f"{_utility_id}_executive",
        )


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": settings.API_VERSION}
