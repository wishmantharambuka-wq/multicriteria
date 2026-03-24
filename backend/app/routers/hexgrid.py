"""
Hex Grid Router — Phase E

Endpoints:
  POST /hexgrid/generate   — generate a hex grid from bounds
  POST /hexgrid/estimate    — estimate cell count before generating
"""
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import DEFAULT_CRS, UPLOAD_DIR
from app import state
from app.services.hexgrid import HexGridGenerator
from app.services.spatial import SpatialAnalysisEngine

router = APIRouter()


class HexGridRequest(BaseModel):
    """Request to generate a hex grid."""
    cell_size_m: float = Field(
        200, ge=10, le=5000,
        description="Hex cell edge length in meters",
    )
    bounds: Optional[List[float]] = Field(
        None,
        description="[minx, miny, maxx, maxy] in WGS84. "
                    "If None, computed from all uploaded layers.",
    )


class HexEstimateRequest(BaseModel):
    cell_size_m: float = Field(200, ge=10, le=5000)
    bounds: Optional[List[float]] = None


@router.post("/hexgrid/estimate")
async def estimate_hexgrid(request: HexEstimateRequest):
    """
    Estimate how many cells a hex grid would produce.
    Call this before generating to warn about large grids.
    """
    bounds = request.bounds or _compute_bounds()
    if not bounds:
        raise HTTPException(
            400, "No bounds provided and no layers uploaded."
        )

    gen = HexGridGenerator()
    return gen.estimate_cell_count(
        bounds=bounds,
        cell_size_m=request.cell_size_m,
    )


@router.post("/hexgrid/generate")
async def generate_hexgrid(request: HexGridRequest):
    """
    Generate a hex grid and register it as an uploaded layer.
    The grid can then be used as the target layer for analysis.
    """
    bounds = request.bounds or _compute_bounds()
    if not bounds:
        raise HTTPException(
            400, "No bounds provided and no layers uploaded."
        )

    # ── Estimate first ──
    gen = HexGridGenerator()
    estimate = gen.estimate_cell_count(
        bounds=bounds,
        cell_size_m=request.cell_size_m,
    )

    if estimate["estimated_cells"] > 10000:
        raise HTTPException(
            400,
            f"Grid too large (~{estimate['estimated_cells']} cells). "
            f"Increase cell size or reduce study area. "
            f"Max recommended: 10,000 cells.",
        )

    # ── Generate grid ──
    gdf = gen.generate(
        bounds=bounds,
        cell_size_m=request.cell_size_m,
    )

    if len(gdf) == 0:
        raise HTTPException(400, "Generated grid has no cells.")

    # ── Save as GeoJSON and register as a layer ──
    import uuid
    layer_id = str(uuid.uuid4())[:8]
    layer_name = f"hexgrid_{int(request.cell_size_m)}m"
    file_path = UPLOAD_DIR / f"{layer_id}_{layer_name}.geojson"

    gdf.to_file(file_path, driver="GeoJSON")

    # Extract metadata
    engine = SpatialAnalysisEngine()
    metadata = engine.extract_metadata(file_path, layer_id, layer_name)

    # Register in state
    state.uploaded_layers[layer_id] = {
        "file_path": str(file_path),
        "name": layer_name,
        "metadata": metadata,
    }

    # Return GeoJSON + metadata
    result_geojson = json.loads(gdf.to_json())

    return {
        "status": "success",
        "layer_id": layer_id,
        "layer_name": layer_name,
        "metadata": metadata,
        "cell_count": len(gdf),
        "cell_size_m": request.cell_size_m,
        "study_area_km2": estimate["study_area_km2"],
        "geojson": result_geojson,
    }


def _compute_bounds() -> Optional[List[float]]:
    """
    Compute the combined bounding box of all uploaded layers.
    Used when the user doesn't specify explicit bounds.
    """
    if not state.uploaded_layers:
        return None

    import geopandas as gpd

    all_bounds = []
    for lid, info in state.uploaded_layers.items():
        try:
            gdf = gpd.read_file(info["file_path"])
            if len(gdf) > 0:
                all_bounds.append(gdf.total_bounds)
        except Exception:
            continue

    if not all_bounds:
        return None

    import numpy as np
    bounds_array = np.array(all_bounds)
    combined = [
        float(bounds_array[:, 0].min()),  # minx
        float(bounds_array[:, 1].min()),  # miny
        float(bounds_array[:, 2].max()),  # maxx
        float(bounds_array[:, 3].max()),  # maxy
    ]

    return combined