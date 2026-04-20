"""
Grid Constraint Classifier API

FastAPI application serving classification results, LMP data,
data center locations, and DER recommendations across all 7 US ISOs.

Dominion DER demo UI: ``/dominion-demo/`` (static) calling ``/api/v1/dominion/*``.
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
_DOMINION_EXEC_DIR = _STATIC_DIR / "dominion_executive"

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

if _DOMINION_EXEC_DIR.is_dir():
    app.mount(
        "/dominion",
        StaticFiles(directory=str(_DOMINION_EXEC_DIR), html=True),
        name="dominion_executive",
    )


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": settings.API_VERSION}
