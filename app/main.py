"""
Grid Constraint Classifier API

FastAPI application serving classification results, LMP data,
data center locations, and DER recommendations across all 7 US ISOs.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.limiter import limiter
from app.api.v1.routes import router as v1_router
from app.api.v1.valuation_routes import router as valuation_router
from app.api.v1.hierarchy_routes import router as hierarchy_router
from app.api.v1.wattcarbon_routes import router as wattcarbon_router
from app.api.v1.batch_routes import router as batch_router
from app.api.v1.tile_routes import router as tile_router
from app.api.v1.hosting_capacity_routes import router as hc_router
from app.api.v1.congestion_routes import router as congestion_router
from app.api.v1.monitor_routes import router as monitor_router
from app.api.v1.gpkg_routes import router as gpkg_router
from app.api.v1.review_routes import router as review_router
from app.spatial_sync import register_spatial_sync

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=(
        "API for the Grid Constraint Classifier, providing zone classifications, "
        "pnode congestion scores, data center locations, and DER recommendations "
        "across all 7 US ISOs (PJM, CAISO, MISO, SPP, ISO-NE, NYISO, ERCOT)."
    ),
)

# Attach limiter to app state (required by slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register PostGIS geometry sync (lat/lon -> geom on insert/update)
register_spatial_sync()

# Include API routes
app.include_router(v1_router)
app.include_router(valuation_router)
app.include_router(hierarchy_router)
app.include_router(wattcarbon_router)
app.include_router(batch_router)
app.include_router(tile_router)
app.include_router(hc_router)
app.include_router(congestion_router)
app.include_router(monitor_router)
app.include_router(gpkg_router)
app.include_router(review_router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": settings.API_VERSION}


# Serve Vue SPA from frontend/dist/ in production (after all API routes)
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="spa")
