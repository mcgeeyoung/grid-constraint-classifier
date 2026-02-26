"""
Grid Constraint Classifier API

FastAPI application serving classification results, LMP data,
data center locations, and DER recommendations across all 7 US ISOs.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.routes import router as v1_router
from app.api.v1.valuation_routes import router as valuation_router
from app.api.v1.hierarchy_routes import router as hierarchy_router
from app.api.v1.wattcarbon_routes import router as wattcarbon_router

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
app.include_router(valuation_router)
app.include_router(hierarchy_router)
app.include_router(wattcarbon_router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": settings.API_VERSION}
