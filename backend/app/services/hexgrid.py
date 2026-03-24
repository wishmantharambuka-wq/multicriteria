"""
Hex Grid Generator — Phase E

Generates flat-top hexagonal grids covering a given bounding box.
No external dependencies beyond NumPy, Shapely, and GeoPandas.

Hexagon geometry (flat-top orientation):
       ___
      /   \       width  = 2 × size
     /     \      height = √3 × size
     \     /
      \___/

  Flat-top layout:
    - Columns offset vertically by height/2
    - Horizontal spacing = width × 3/4
    - Vertical spacing   = height

Why flat-top (not pointy-top)?
  Convention in GIS and planning. Either works mathematically,
  but flat-top tiles a rectangular bounding box more naturally.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon

from app.config import DEFAULT_CRS

logger = logging.getLogger(__name__)


class HexGridGenerator:
    """
    Generate hexagonal grids for spatial analysis.

    Usage:
        gen = HexGridGenerator()
        gdf = gen.generate(
            bounds=[-78.70, 35.74, -78.58, 35.82],
            cell_size_m=200,
            crs="EPSG:4326",
        )
    """

    def generate(
        self,
        bounds: List[float],
        cell_size_m: float = 200,
        crs: str = DEFAULT_CRS,
    ) -> gpd.GeoDataFrame:
        """
        Generate a hex grid covering the bounding box.

        Args:
            bounds: [minx, miny, maxx, maxy] in the given CRS
            cell_size_m: Hex cell edge length in meters
            crs: Coordinate reference system of the bounds

        Returns:
            GeoDataFrame with hex polygons and cell IDs
        """
        print(f"\n  🔷 HEX GRID GENERATION")
        print(f"     Cell size: {cell_size_m}m")
        print(f"     Bounds: {[round(b, 4) for b in bounds]}")
        print(f"     Input CRS: {crs}")

        # ── Convert bounds to projected CRS for metric math ──
        minx, miny, maxx, maxy = bounds

        # Detect UTM zone from center of bounds
        center_lon = (minx + maxx) / 2
        center_lat = (miny + maxy) / 2
        utm_zone = int((center_lon + 180) / 6) + 1
        utm_epsg = (32600 + utm_zone) if center_lat >= 0 else (32700 + utm_zone)
        projected_crs = f"EPSG:{utm_epsg}"

        print(f"     Projected CRS: {projected_crs}")

        # Create a small GDF from the bbox corners to reproject
        from shapely.geometry import box
        bbox_gdf = gpd.GeoDataFrame(
            geometry=[box(minx, miny, maxx, maxy)],
            crs=crs,
        )
        bbox_proj = bbox_gdf.to_crs(projected_crs)
        proj_bounds = bbox_proj.total_bounds
        px_min, py_min, px_max, py_max = proj_bounds

        print(f"     Projected bounds: "
              f"[{px_min:.0f}, {py_min:.0f}, "
              f"{px_max:.0f}, {py_max:.0f}]")

        # ── Generate hex centers ──
        size = max(cell_size_m, 10)  # Edge length (meters)
        hex_width = 2.0 * size
        hex_height = np.sqrt(3.0) * size

        # Spacing between hex centers
        col_spacing = hex_width * 0.75
        row_spacing = hex_height

        # Add buffer so edge hexes cover the full extent
        buffer = size * 2
        x_start = px_min - buffer
        x_end = px_max + buffer
        y_start = py_min - buffer
        y_end = py_max + buffer

        # Count expected cells (for warning)
        n_cols = int(np.ceil((x_end - x_start) / col_spacing)) + 1
        n_rows = int(np.ceil((y_end - y_start) / row_spacing)) + 1
        est_cells = n_cols * n_rows

        print(f"     Estimated cells: ~{est_cells}")

        if est_cells > 10000:
            print(f"     ⚠ Large grid! Consider increasing cell size.")

        # ── Build hex polygons ──
        hexagons = []
        cell_ids = []
        cell_num = 0

        col = 0
        x = x_start
        while x <= x_end:
            row = 0
            # Odd columns are offset by half the row spacing
            y_offset = (row_spacing / 2.0) if (col % 2 == 1) else 0.0
            y = y_start + y_offset

            while y <= y_end:
                hex_poly = self._create_hex(x, y, size)
                hexagons.append(hex_poly)
                cell_ids.append(f"H-{cell_num:05d}")
                cell_num += 1
                y += row_spacing
                row += 1

            x += col_spacing
            col += 1

        print(f"     Generated: {len(hexagons)} hexagons")

        if len(hexagons) == 0:
            print("     ⚠ No hexagons generated!")
            return gpd.GeoDataFrame(
                columns=["cell_id", "geometry"],
                geometry="geometry",
                crs=crs,
            )

        # ── Create GeoDataFrame ──
        gdf = gpd.GeoDataFrame(
            {"cell_id": cell_ids},
            geometry=hexagons,
            crs=projected_crs,
        )

        # ── Clip to original bounding box ──
        # (remove hexes that fall entirely outside)
        bbox_geom = bbox_proj.geometry.iloc[0]
        gdf = gdf[gdf.geometry.intersects(bbox_geom)].copy()
        gdf = gdf.reset_index(drop=True)

        # Re-assign IDs after clipping
        gdf["cell_id"] = [f"H-{i:05d}" for i in range(len(gdf))]

        # Compute cell area (in m²)
        gdf["area_sqm"] = gdf.geometry.area.round(1)

        print(f"     After clipping: {len(gdf)} hexagons")
        print(f"     Cell area: ~{gdf['area_sqm'].mean():.0f} m²")

        # ── Reproject back to original CRS ──
        gdf = gdf.to_crs(crs)

        print(f"     ✅ Hex grid ready\n")

        return gdf

    @staticmethod
    def _create_hex(cx: float, cy: float, size: float) -> Polygon:
        """
        Create a flat-top regular hexagon centered at (cx, cy).

        Flat-top vertex angles: 0°, 60°, 120°, 180°, 240°, 300°

        Vertex i at angle (60° × i):
            x = cx + size × cos(angle)
            y = cy + size × sin(angle)
        """
        angles = np.arange(0, 360, 60) * (np.pi / 180.0)
        vertices = [
            (cx + size * np.cos(a), cy + size * np.sin(a))
            for a in angles
        ]
        return Polygon(vertices)

    def estimate_cell_count(
        self,
        bounds: List[float],
        cell_size_m: float,
        crs: str = DEFAULT_CRS,
    ) -> Dict[str, Any]:
        """
        Estimate how many hex cells would be generated
        without actually creating them. Used by the frontend
        to warn the user about large grids.
        """
        minx, miny, maxx, maxy = bounds
        center_lon = (minx + maxx) / 2
        center_lat = (miny + maxy) / 2

        # Approximate conversion from degrees to meters
        # at this latitude
        lat_m = 111320.0
        lon_m = 111320.0 * np.cos(np.radians(center_lat))

        width_m = (maxx - minx) * lon_m
        height_m = (maxy - miny) * lat_m
        area_km2 = (width_m * height_m) / 1e6

        size = max(cell_size_m, 10)
        hex_area = (3.0 * np.sqrt(3.0) / 2.0) * size ** 2
        est_cells = int((width_m * height_m) / hex_area * 1.15)

        return {
            "estimated_cells": est_cells,
            "study_area_km2": round(area_km2, 2),
            "cell_area_m2": round(hex_area, 1),
            "cell_size_m": cell_size_m,
            "warning": est_cells > 5000,
            "message": (
                f"~{est_cells} cells for {area_km2:.1f} km² "
                f"at {cell_size_m}m resolution"
            ),
        }