"""
Spatial Autocorrelation Router — Phase F
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import state
from app.services.autocorrelation import SpatialAutocorrelationEngine

router = APIRouter()


class AutocorrelationRequest(BaseModel):
    variable: str = Field(
        "suitability_score",
        description="Property to analyze",
    )
    k_neighbors: int = Field(5, ge=2, le=20)
    n_permutations: int = Field(999, ge=99, le=9999)
    significance_level: float = Field(0.05, ge=0.01, le=0.20)
    scenario_id: Optional[str] = None


@router.post("/autocorrelation")
async def run_autocorrelation(request: AutocorrelationRequest):
    """
    Compute Global Moran's I and Local LISA statistics
    on the suitability scores.
    """
    if request.scenario_id:
        if request.scenario_id not in state.saved_scenarios:
            raise HTTPException(
                404, f"Scenario '{request.scenario_id}' not found."
            )
        source = state.saved_scenarios[request.scenario_id]
    else:
        if not state.last_analysis:
            raise HTTPException(
                400, "No analysis result. Run an analysis first."
            )
        source = state.last_analysis

    result_geojson = source.get("result_geojson", {})
    if not result_geojson.get("features"):
        raise HTTPException(400, "No features in the result.")

    engine = SpatialAutocorrelationEngine()
    output_geojson, summary = engine.analyze(
        result_geojson=result_geojson,
        variable=request.variable,
        k_neighbors=request.k_neighbors,
        n_permutations=request.n_permutations,
        significance_level=request.significance_level,
    )

    return {
        "status": "success",
        "result_geojson": output_geojson,
        "summary": summary,
    }