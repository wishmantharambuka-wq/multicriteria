"""
FastAPI Application — Phase F
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    analysis, scenarios, ahp, sensitivity, hexgrid, autocorrelation
)

app = FastAPI(
    title="Site Suitability Engine",
    description="Dynamic multi-criteria site suitability analysis API",
    version="0.7.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(scenarios.router, prefix="/api/v1", tags=["scenarios"])
app.include_router(ahp.router, prefix="/api/v1", tags=["ahp"])
app.include_router(sensitivity.router, prefix="/api/v1", tags=["sensitivity"])
app.include_router(hexgrid.router, prefix="/api/v1", tags=["hexgrid"])
app.include_router(autocorrelation.router, prefix="/api/v1", tags=["autocorrelation"])


@app.get("/", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": "Site Suitability Engine", "version": "0.7.0"}


@app.get("/api/v1/health", tags=["health"])
async def api_health():
    try:
        import geopandas, shapely
        return {"status": "healthy", "geopandas_version": geopandas.__version__, "shapely_version": shapely.__version__}
    except ImportError as e:
        return {"status": "degraded", "error": str(e)}