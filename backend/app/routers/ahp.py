"""
AHP Router — Phase C

Endpoint for computing AHP weights from pairwise comparisons.
"""
from fastapi import APIRouter, HTTPException

from app.models.schemas import AHPRequest, AHPResponse
from app.services.ahp import AHPEngine

router = APIRouter()


@router.post("/ahp/compute", response_model=AHPResponse)
async def compute_ahp_weights(request: AHPRequest):
    """
    Compute priority weights using the Analytic Hierarchy Process.

    Accepts pairwise comparisons between criteria and returns
    mathematically derived weights with a consistency check.

    Saaty Scale Reference:
        1   — Equal importance
        3   — Moderate importance of one over the other
        5   — Strong importance
        7   — Very strong importance
        9   — Extreme importance
        2,4,6,8 — Intermediate values
        Reciprocals (1/3, 1/5, etc.) — inverse judgments
    """
    n = len(request.criteria_names)

    # Validate number of comparisons
    expected = n * (n - 1) // 2
    if len(request.comparisons) != expected:
        raise HTTPException(
            400,
            f"Expected {expected} pairwise comparisons for "
            f"{n} criteria, got {len(request.comparisons)}."
        )

    # Validate comparison indices
    for comp in request.comparisons:
        if comp.row >= n or comp.col >= n:
            raise HTTPException(
                400,
                f"Comparison index out of range: "
                f"({comp.row}, {comp.col}) for {n} criteria."
            )
        if comp.row >= comp.col:
            raise HTTPException(
                400,
                f"Comparisons must be upper-triangle: "
                f"row ({comp.row}) must be < col ({comp.col})."
            )

    # Validate unique criteria names
    if len(set(request.criteria_names)) != n:
        raise HTTPException(400, "Criteria names must be unique.")

    # Convert to tuples
    comparisons = [
        (c.row, c.col, c.value)
        for c in request.comparisons
    ]

    # Compute
    engine = AHPEngine()
    result = engine.compute_weights(
        criteria_names=request.criteria_names,
        comparisons=comparisons,
    )

    return AHPResponse(**result)