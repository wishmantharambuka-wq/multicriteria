"""
Analysis Router — Phase B

Changes:
  - Uses shared state module instead of local dict
  - Stores last analysis result in state.last_analysis
    so the scenarios router can save it
"""
import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, HTTPException

from app.config import UPLOAD_DIR
from app.models.schemas import (
    LayerMetadata, AnalysisRequest, AnalysisResponse,
)
from app.services.spatial import SpatialAnalysisEngine
from app.utils.validators import validate_geojson
from app import state

router = APIRouter()


@router.post("/upload", response_model=LayerMetadata)
async def upload_layer(
    file: UploadFile = File(...),
    layer_name: Optional[str] = Form(None),
):
    if not file.filename.endswith((".geojson", ".json")):
        raise HTTPException(400, "Only .geojson/.json accepted.")
    content = await file.read()
    try:
        geojson_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(400, "Not valid JSON.")
    is_valid, err = validate_geojson(geojson_data)
    if not is_valid:
        raise HTTPException(400, err)
    layer_id = str(uuid.uuid4())[:8]
    safe_name = layer_name or file.filename.replace(".geojson", "")
    file_path = UPLOAD_DIR / f"{layer_id}_{safe_name}.geojson"
    with open(file_path, "w") as f:
        json.dump(geojson_data, f)
    engine = SpatialAnalysisEngine()
    metadata = engine.extract_metadata(file_path, layer_id, safe_name)
    state.uploaded_layers[layer_id] = {
        "file_path": str(file_path),
        "name": safe_name,
        "metadata": metadata,
    }
    return metadata


@router.get("/layers")
async def list_layers():
    return {
        "layers": {
            lid: {"name": info["name"], "metadata": info["metadata"]}
            for lid, info in state.uploaded_layers.items()
        }
    }


@router.get("/layers/{layer_id}/geojson")
async def get_layer_geojson(layer_id: str):
    if layer_id not in state.uploaded_layers:
        raise HTTPException(404, "Layer not found.")
    with open(state.uploaded_layers[layer_id]["file_path"]) as f:
        return json.load(f)


@router.delete("/layers/{layer_id}")
async def delete_layer(layer_id: str):
    if layer_id not in state.uploaded_layers:
        raise HTTPException(404, "Layer not found.")
    p = Path(state.uploaded_layers[layer_id]["file_path"])
    if p.exists():
        p.unlink()
    del state.uploaded_layers[layer_id]
    return {"status": "deleted", "layer_id": layer_id}


@router.post("/analyze", response_model=AnalysisResponse)
async def run_analysis(request: AnalysisRequest):
    for c in request.criteria:
        if c.layer_id not in state.uploaded_layers:
            raise HTTPException(404, f"Layer '{c.layer_id}' not found.")
    if (request.target_layer_id
            and request.target_layer_id not in state.uploaded_layers):
        raise HTTPException(
            404, f"Target layer '{request.target_layer_id}' not found."
        )

    constraints = [c for c in request.criteria if c.is_constraint]
    factors = [c for c in request.criteria
               if not c.is_constraint and c.weight > 0]

    if not constraints and not factors:
        raise HTTPException(
            400, "Configure at least one constraint or factor."
        )

    if factors:
        total = sum(f.weight for f in factors)
        if not (90 <= total <= 110):
            raise HTTPException(
                400,
                f"Factor weights must sum to ~100%. Current: {total}%"
            )

    layer_paths = {
        lid: info["file_path"]
        for lid, info in state.uploaded_layers.items()
    }

    engine = SpatialAnalysisEngine()
    result_geojson, criterion_details, constraint_summary = (
        engine.run_suitability_analysis(
            layer_paths=layer_paths,
            criteria=request.criteria,
            target_layer_id=request.target_layer_id,
        )
    )

    features = result_geojson.get("features", [])
    scores = [
        f["properties"].get("suitability_score", 0) for f in features
    ]
    feasible = [
        f for f in features
        if f["properties"].get("is_feasible", True)
    ]
    feasible_scores = [
        f["properties"].get("suitability_score", 0) for f in feasible
    ]

    summary = {
        "total_features": len(features),
        "feasible_count": len(feasible),
        "infeasible_count": len(features) - len(feasible),
        "constraint_count": len(constraints),
        "factor_count": len(factors),
    }
    if feasible_scores:
        summary.update({
            "min_score": round(min(feasible_scores), 4),
            "max_score": round(max(feasible_scores), 4),
            "mean_score": round(
                sum(feasible_scores) / len(feasible_scores), 4
            ),
        })
    class_dist = {}
    for f in features:
        cls = f["properties"].get("suitability_class", "Unknown")
        class_dist[cls] = class_dist.get(cls, 0) + 1
    summary["class_distribution"] = class_dist

    # ── Store for scenario saving ──
    state.last_analysis = {
        "target_layer_id": request.target_layer_id,
        "criteria": [c.model_dump() for c in request.criteria],
        "result_geojson": result_geojson,
        "summary": summary,
        "criteria_details": [d.model_dump() for d in criterion_details],
        "constraint_summary": [c.model_dump() for c in constraint_summary],
    }

    return AnalysisResponse(
        status="success",
        message="Suitability analysis complete",
        result_geojson=result_geojson,
        summary=summary,
        criteria_details=criterion_details,
        constraint_summary=constraint_summary,
    )
