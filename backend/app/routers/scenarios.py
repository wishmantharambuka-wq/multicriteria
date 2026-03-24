"""
Scenarios Router — Phase B

Endpoints:
  POST   /scenarios/save       — save the last analysis as a named scenario
  GET    /scenarios             — list all saved scenarios
  GET    /scenarios/{id}        — get full scenario detail
  GET    /scenarios/{id}/geojson — get just the result GeoJSON
  DELETE /scenarios/{id}        — delete a scenario
  POST   /scenarios/compare     — compare two scenarios, return diff
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException

from app import state
from app.models.schemas import (
    ScenarioSaveRequest,
    ScenarioMeta,
    ScenarioDetail,
    CompareRequest,
    CompareResponse,
    CriterionResult,
    ConstraintResult,
)

router = APIRouter()


# ═══════════════════════════════════════════
#  SAVE
# ═══════════════════════════════════════════

@router.post("/scenarios/save", response_model=ScenarioMeta)
async def save_scenario(request: ScenarioSaveRequest):
    """
    Save the most recent analysis result as a named scenario.

    The analysis router stores each result in state.last_analysis.
    This endpoint copies that data into the persistent scenario store
    with a user-provided name.
    """
    if not state.last_analysis:
        raise HTTPException(
            400, "No analysis result to save. Run an analysis first."
        )

    scenario_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()

    summary = state.last_analysis.get("summary", {})

    scenario = {
        "id": scenario_id,
        "name": request.name,
        "created_at": now,
        "target_layer_id": state.last_analysis.get("target_layer_id"),
        "criteria": state.last_analysis.get("criteria", []),
        "result_geojson": state.last_analysis.get("result_geojson", {}),
        "summary": summary,
        "criteria_details": state.last_analysis.get(
            "criteria_details", []
        ),
        "constraint_summary": state.last_analysis.get(
            "constraint_summary", []
        ),
    }

    state.saved_scenarios[scenario_id] = scenario

    print(f"  💾 Scenario saved: '{request.name}' (id: {scenario_id})")

    return ScenarioMeta(
        id=scenario_id,
        name=request.name,
        created_at=now,
        feature_count=summary.get("total_features", 0),
        feasible_count=summary.get("feasible_count", 0),
        constraint_count=summary.get("constraint_count", 0),
        factor_count=summary.get("factor_count", 0),
        mean_score=summary.get("mean_score"),
    )


# ═══════════════════════════════════════════
#  LIST
# ═══════════════════════════════════════════

@router.get("/scenarios", response_model=List[ScenarioMeta])
async def list_scenarios():
    """List all saved scenarios (lightweight, no GeoJSON)."""
    result = []
    for sid, s in state.saved_scenarios.items():
        summary = s.get("summary", {})
        result.append(ScenarioMeta(
            id=sid,
            name=s["name"],
            created_at=s["created_at"],
            feature_count=summary.get("total_features", 0),
            feasible_count=summary.get("feasible_count", 0),
            constraint_count=summary.get("constraint_count", 0),
            factor_count=summary.get("factor_count", 0),
            mean_score=summary.get("mean_score"),
        ))
    # Sort by creation time, newest first
    result.sort(key=lambda x: x.created_at, reverse=True)
    return result


# ═══════════════════════════════════════════
#  GET DETAIL
# ═══════════════════════════════════════════

@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    """Get full scenario detail including criteria config and summary."""
    if scenario_id not in state.saved_scenarios:
        raise HTTPException(404, "Scenario not found.")

    s = state.saved_scenarios[scenario_id]
    return {
        "id": s["id"],
        "name": s["name"],
        "created_at": s["created_at"],
        "target_layer_id": s.get("target_layer_id"),
        "criteria": s.get("criteria", []),
        "summary": s.get("summary", {}),
        "criteria_details": s.get("criteria_details", []),
        "constraint_summary": s.get("constraint_summary", []),
    }


# ═══════════════════════════════════════════
#  GET GEOJSON (for map rendering)
# ═══════════════════════════════════════════

@router.get("/scenarios/{scenario_id}/geojson")
async def get_scenario_geojson(scenario_id: str):
    """Return just the result GeoJSON for rendering on the map."""
    if scenario_id not in state.saved_scenarios:
        raise HTTPException(404, "Scenario not found.")
    return state.saved_scenarios[scenario_id]["result_geojson"]


# ═══════════════════════════════════════════
#  DELETE
# ═══════════════════════════════════════════

@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str):
    if scenario_id not in state.saved_scenarios:
        raise HTTPException(404, "Scenario not found.")
    name = state.saved_scenarios[scenario_id]["name"]
    del state.saved_scenarios[scenario_id]
    print(f"  🗑️ Scenario deleted: '{name}'")
    return {"status": "deleted", "scenario_id": scenario_id}


# ═══════════════════════════════════════════
#  COMPARE
# ═══════════════════════════════════════════

@router.post("/scenarios/compare", response_model=CompareResponse)
async def compare_scenarios(request: CompareRequest):
    """
    Compare two saved scenarios and return a diff GeoJSON.

    Algorithm:
    ──────────
    1. Load both scenario result GeoJSONs
    2. Match features by common ID field or by index
    3. For each matched feature, compute:
       - score_delta = score_a - score_b
       - rank_delta  = rank_b - rank_a (positive = A has better rank)
       - class transition
       - feasibility change
    4. Build summary statistics:
       - Mean/max/min delta
       - Pearson correlation between scores
       - Biggest rank movers
       - Class transition counts
       - Feasibility change counts
    5. Return diff GeoJSON + summary
    """
    if request.scenario_a_id not in state.saved_scenarios:
        raise HTTPException(
            404, f"Scenario A '{request.scenario_a_id}' not found."
        )
    if request.scenario_b_id not in state.saved_scenarios:
        raise HTTPException(
            404, f"Scenario B '{request.scenario_b_id}' not found."
        )
    if request.scenario_a_id == request.scenario_b_id:
        raise HTTPException(
            400, "Cannot compare a scenario with itself."
        )

    sa = state.saved_scenarios[request.scenario_a_id]
    sb = state.saved_scenarios[request.scenario_b_id]

    features_a = sa["result_geojson"].get("features", [])
    features_b = sb["result_geojson"].get("features", [])

    if not features_a or not features_b:
        raise HTTPException(
            400, "One or both scenarios have no features."
        )

    # ── Match features ──
    matched = _match_features(features_a, features_b)

    if not matched:
        raise HTTPException(
            400,
            "Could not match features between scenarios. "
            "Were they run on the same target layer?"
        )

    # ── Build diff features ──
    diff_features = []
    scores_a = []
    scores_b = []
    deltas = []
    rank_changes = []
    class_transitions = {}
    feasibility_changes = {
        "both_feasible": 0,
        "both_infeasible": 0,
        "gained_in_b": 0,
        "lost_in_b": 0,
    }
    biggest_movers = []

    for fa, fb in matched:
        pa = fa["properties"]
        pb = fb["properties"]

        score_a = pa.get("suitability_score", 0)
        score_b = pb.get("suitability_score", 0)
        rank_a = pa.get("rank", 0)
        rank_b = pb.get("rank", 0)
        class_a = pa.get("suitability_class", "Unknown")
        class_b = pb.get("suitability_class", "Unknown")
        feas_a = pa.get("is_feasible", True)
        feas_b = pb.get("is_feasible", True)

        delta = round(score_a - score_b, 4)
        # Positive rank_delta means A has a BETTER (lower number) rank
        rank_d = rank_b - rank_a if (rank_a > 0 and rank_b > 0) else 0
        abs_delta = abs(delta)

        # Classify change magnitude
        if abs_delta >= 0.3:
            magnitude = "large"
        elif abs_delta >= 0.1:
            magnitude = "medium"
        else:
            magnitude = "small"

        # Determine winner
        if delta > 0.02:
            winner = "A"
        elif delta < -0.02:
            winner = "B"
        else:
            winner = "tie"

        scores_a.append(score_a)
        scores_b.append(score_b)
        deltas.append(delta)

        if rank_a > 0 and rank_b > 0:
            rank_changes.append(rank_d)

        # Class transition
        if class_a != class_b:
            transition_key = f"{class_a} → {class_b}"
            class_transitions[transition_key] = (
                class_transitions.get(transition_key, 0) + 1
            )

        # Feasibility changes
        if feas_a and feas_b:
            feasibility_changes["both_feasible"] += 1
        elif not feas_a and not feas_b:
            feasibility_changes["both_infeasible"] += 1
        elif not feas_a and feas_b:
            feasibility_changes["gained_in_b"] += 1
        else:
            feasibility_changes["lost_in_b"] += 1

        # Track for biggest movers
        # Find a display ID for this feature
        display_id = _get_feature_id(pa)
        biggest_movers.append({
            "id": display_id,
            "score_a": score_a,
            "score_b": score_b,
            "score_delta": delta,
            "rank_a": rank_a,
            "rank_b": rank_b,
            "rank_delta": rank_d,
        })

        # ── Build combined properties ──
        # Start with original properties (exclude analysis fields)
        skip_keys = {
            "suitability_score", "suitability_class", "rank",
            "is_feasible", "failed_constraints", "factor_score",
        }
        base_props = {
            k: v for k, v in pa.items()
            if k not in skip_keys and not k.startswith("score_")
            and not k.startswith("constraint_")
        }

        diff_props = {
            **base_props,
            "score_a": score_a,
            "score_b": score_b,
            "score_delta": delta,
            "abs_score_delta": abs_delta,
            "rank_a": rank_a,
            "rank_b": rank_b,
            "rank_delta": rank_d,
            "class_a": class_a,
            "class_b": class_b,
            "feasible_a": feas_a,
            "feasible_b": feas_b,
            "winner": winner,
            "change_magnitude": magnitude,
        }

        diff_features.append({
            "type": "Feature",
            "geometry": fa["geometry"],
            "properties": diff_props,
        })

    # ── Summary statistics ──
    scores_a_arr = np.array(scores_a)
    scores_b_arr = np.array(scores_b)
    deltas_arr = np.array(deltas)

    # Pearson correlation
    correlation = 0.0
    if len(scores_a_arr) > 1:
        std_a = scores_a_arr.std()
        std_b = scores_b_arr.std()
        if std_a > 0 and std_b > 0:
            correlation = float(np.corrcoef(
                scores_a_arr, scores_b_arr
            )[0, 1])

    # Sort biggest movers by absolute score delta
    biggest_movers.sort(key=lambda x: abs(x["score_delta"]), reverse=True)
    top_movers = biggest_movers[:10]

    # Count direction of changes
    a_better = sum(1 for d in deltas if d > 0.02)
    b_better = sum(1 for d in deltas if d < -0.02)
    similar = len(deltas) - a_better - b_better

    summary = {
        "features_compared": len(matched),
        "mean_score_a": round(float(scores_a_arr.mean()), 4),
        "mean_score_b": round(float(scores_b_arr.mean()), 4),
        "mean_delta": round(float(deltas_arr.mean()), 4),
        "mean_abs_delta": round(float(np.abs(deltas_arr).mean()), 4),
        "max_delta": round(float(deltas_arr.max()), 4),
        "min_delta": round(float(deltas_arr.min()), 4),
        "correlation": round(correlation, 4),
        "a_better_count": a_better,
        "b_better_count": b_better,
        "similar_count": similar,
        "rank_agreement_pct": round(
            sum(1 for r in rank_changes if abs(r) <= 3)
            / max(len(rank_changes), 1) * 100, 1
        ),
        "class_transitions": class_transitions,
        "feasibility_changes": feasibility_changes,
        "biggest_movers": top_movers,
    }

    diff_geojson = {
        "type": "FeatureCollection",
        "features": diff_features,
    }

    print(f"\n  ⚖️ Comparison: '{sa['name']}' vs '{sb['name']}'")
    print(f"     Features matched: {len(matched)}")
    print(f"     Mean delta: {summary['mean_delta']:+.4f}")
    print(f"     Correlation: {summary['correlation']:.4f}")
    print(f"     A better: {a_better}, B better: {b_better}, "
          f"Similar: {similar}")

    return CompareResponse(
        status="success",
        scenario_a={"id": sa["id"], "name": sa["name"]},
        scenario_b={"id": sb["id"], "name": sb["name"]},
        diff_geojson=diff_geojson,
        summary=summary,
    )


# ═══════════════════════════════════════════
#  Feature Matching Helpers
# ═══════════════════════════════════════════

def _match_features(
    features_a: List[Dict],
    features_b: List[Dict],
) -> List[tuple]:
    """
    Match features between two scenario results.

    Strategy:
    1. Try matching by common ID property
       (parcel_id, id, fid, OBJECTID, etc.)
    2. Fall back to index-based matching

    Returns list of (feature_a, feature_b) tuples.
    """
    # Identify common ID field
    id_fields = [
        "parcel_id", "id", "fid", "gid", "OBJECTID",
        "FID", "ID", "NAME", "name",
    ]

    props_a = features_a[0].get("properties", {}) if features_a else {}
    common_id = None
    for field in id_fields:
        if field in props_a:
            common_id = field
            break

    if common_id:
        # Build lookup from B
        b_lookup = {}
        for fb in features_b:
            fid = fb.get("properties", {}).get(common_id)
            if fid is not None:
                b_lookup[fid] = fb

        matched = []
        for fa in features_a:
            fid = fa.get("properties", {}).get(common_id)
            if fid in b_lookup:
                matched.append((fa, b_lookup[fid]))

        if matched:
            print(f"     Matched {len(matched)} features by '{common_id}'")
            return matched

    # Fall back to index matching
    n = min(len(features_a), len(features_b))
    if n > 0:
        print(f"     Matched {n} features by index")
        return [(features_a[i], features_b[i]) for i in range(n)]

    return []


def _get_feature_id(properties: Dict) -> str:
    """Extract a display-friendly ID from feature properties."""
    id_fields = [
        "parcel_id", "id", "fid", "gid", "name",
        "NAME", "OBJECTID",
    ]
    for field in id_fields:
        if field in properties:
            return str(properties[field])
    return "unknown"