"""
Sensitivity Analysis Router — Phase D
"""
from fastapi import APIRouter, HTTPException

from app import state
from app.models.schemas import SensitivityRequest, SensitivityResponse
from app.services.sensitivity import SensitivityEngine

router = APIRouter()


@router.post("/sensitivity", response_model=SensitivityResponse)
async def run_sensitivity(request: SensitivityRequest):
    """
    Run Monte Carlo sensitivity analysis on the last analysis
    or a saved scenario.

    Returns stability metrics per parcel, tornado chart data,
    and overall reliability assessment.
    """
    # ── Resolve data source ──
    if request.scenario_id:
        if request.scenario_id not in state.saved_scenarios:
            raise HTTPException(
                404, f"Scenario '{request.scenario_id}' not found."
            )
        source = state.saved_scenarios[request.scenario_id]
        source_name = source["name"]
    else:
        if not state.last_analysis:
            raise HTTPException(
                400, "No analysis result available. Run an analysis "
                     "or specify a scenario_id."
            )
        source = state.last_analysis
        source_name = "Last Analysis"

    # ── Extract required data ──
    result_geojson = source.get("result_geojson", {})
    criteria_details = source.get("criteria_details", [])

    if not result_geojson.get("features"):
        raise HTTPException(400, "No features in the analysis result.")

    if not criteria_details:
        raise HTTPException(
            400, "No criteria details found. The analysis must "
                 "include at least one scored factor."
        )

    print(f"\n  🎲 Sensitivity analysis on: {source_name}")

    # ── Run analysis ──
    engine = SensitivityEngine()
    sensitivity_geojson, tornado_data, summary = engine.run_sensitivity(
        result_geojson=result_geojson,
        criteria_details=criteria_details,
        n_simulations=request.n_simulations,
        perturbation_pct=request.perturbation_pct,
        top_k=request.top_k,
    )

    return SensitivityResponse(
        status="success",
        result_geojson=sensitivity_geojson,
        tornado=tornado_data,
        summary=summary,
        simulation_params={
            "n_simulations": request.n_simulations,
            "perturbation_pct": request.perturbation_pct,
            "top_k": request.top_k,
            "source": source_name,
        },
    )