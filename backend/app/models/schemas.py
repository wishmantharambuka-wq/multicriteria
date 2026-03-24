"""
Pydantic Models — Phase B: Scenarios

Additions:
  - ScenarioSaveRequest / ScenarioMeta / ScenarioDetail
  - CompareRequest / CompareResponse
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Layer & Criterion models (unchanged from Phase A) ──

class LayerMetadata(BaseModel):
    layer_id: str
    name: str
    feature_count: int
    geometry_type: str
    bounds: List[float]
    crs: str
    properties: List[str]


class Criterion(BaseModel):
    layer_id: str
    weight: float = Field(0, ge=0, le=100)
    criteria_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    is_constraint: bool = False


class AnalysisRequest(BaseModel):
    criteria: List[Criterion]
    target_layer_id: Optional[str] = None


class CriterionResult(BaseModel):
    name: str
    criteria_type: str
    is_constraint: bool = False
    weight_pct: float
    normalized_weight: float
    mean_score: float
    min_score: float
    max_score: float


class ConstraintResult(BaseModel):
    name: str
    criteria_type: str
    passed: int
    failed: int
    pass_rate: float


class AnalysisResponse(BaseModel):
    status: str
    message: str
    result_geojson: Dict[str, Any]
    summary: Dict[str, Any]
    criteria_details: List[CriterionResult] = Field(default_factory=list)
    constraint_summary: List[ConstraintResult] = Field(default_factory=list)


# ── Scenario models (new in Phase B) ──

class ScenarioSaveRequest(BaseModel):
    """Request body for saving the last analysis as a named scenario."""
    name: str = Field(
        ..., min_length=1, max_length=100,
        description="Human-readable scenario name",
    )


class ScenarioMeta(BaseModel):
    """Lightweight scenario info for list views."""
    id: str
    name: str
    created_at: str
    feature_count: int
    feasible_count: int
    constraint_count: int
    factor_count: int
    mean_score: Optional[float] = None


class ScenarioDetail(BaseModel):
    """Full scenario data including criteria config."""
    id: str
    name: str
    created_at: str
    target_layer_id: Optional[str]
    criteria: List[Dict[str, Any]]
    result_geojson: Dict[str, Any]
    summary: Dict[str, Any]
    criteria_details: List[CriterionResult] = Field(default_factory=list)
    constraint_summary: List[ConstraintResult] = Field(default_factory=list)


class CompareRequest(BaseModel):
    """Request to compare two saved scenarios."""
    scenario_a_id: str
    scenario_b_id: str


class CompareResponse(BaseModel):
    """Result of comparing two scenarios."""
    status: str
    scenario_a: Dict[str, str]
    scenario_b: Dict[str, str]
    diff_geojson: Dict[str, Any]
    summary: Dict[str, Any]

# ── AHP Models (Phase C) ──

class AHPPairwiseComparison(BaseModel):
    """A single pairwise comparison between two criteria."""
    row: int = Field(..., ge=0, description="Index of criterion A")
    col: int = Field(..., ge=0, description="Index of criterion B")
    value: float = Field(
        ..., gt=0,
        description="How much more important is A than B? "
                    "Use Saaty scale: 1 (equal) to 9 (extreme). "
                    "Use reciprocals (1/3, 1/5, etc.) if B is more "
                    "important than A."
    )


class AHPRequest(BaseModel):
    """Request body for AHP weight computation."""
    criteria_names: List[str] = Field(
        ..., min_length=2,
        description="Ordered list of criterion names",
    )
    comparisons: List[AHPPairwiseComparison] = Field(
        ...,
        description="Upper triangle pairwise comparisons. "
                    "For n criteria, provide n(n-1)/2 comparisons.",
    )


class AHPWeightResult(BaseModel):
    """Result of AHP weight computation for one criterion."""
    name: str
    weight: float
    weight_pct: float


class AHPResponse(BaseModel):
    """Full AHP computation result."""
    weights: List[AHPWeightResult]
    lambda_max: float
    consistency_index: float
    consistency_ratio: float
    is_consistent: bool
    consistency_threshold: float = 0.10
    method: str
    matrix: List[List[float]]
    n_criteria: int
    message: str

    # ── Sensitivity Analysis Models (Phase D) ──

class SensitivityRequest(BaseModel):
    """Parameters for Monte Carlo sensitivity analysis."""
    n_simulations: int = Field(
        1000, ge=100, le=10000,
        description="Number of weight perturbation simulations",
    )
    perturbation_pct: float = Field(
        0.15, ge=0.01, le=0.50,
        description="Maximum fractional perturbation per weight "
                    "(0.15 = ±15%)",
    )
    top_k: int = Field(
        5, ge=1, le=50,
        description="K for 'probability of being in top K'",
    )
    scenario_id: Optional[str] = Field(
        None,
        description="If set, run sensitivity on a saved scenario "
                    "instead of the last analysis.",
    )


class TornadoItem(BaseModel):
    """One criterion's influence in the tornado chart."""
    criterion_name: str
    original_weight: float
    weight_low: float
    weight_high: float
    mean_score_at_low: float
    mean_score_at_high: float
    score_swing: float
    influence_rank: int


class SensitivityResponse(BaseModel):
    """Full sensitivity analysis result."""
    status: str
    result_geojson: Dict[str, Any]
    tornado: List[TornadoItem]
    summary: Dict[str, Any]
    simulation_params: Dict[str, Any]