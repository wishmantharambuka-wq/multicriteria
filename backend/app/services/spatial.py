"""
Spatial Analysis Engine — Phase A: Constraints vs Factors

Architecture change:
    OLD: All criteria → weighted scores → composite
    NEW: Constraints → mask → Factors → weighted scores
         → composite × mask → final scores

The formula is now:
    S = (Π Cⱼ) × (Σ wᵢ · Fᵢ)

    Where:
      Cⱼ = constraint j result (0 or 1)
      Π Cⱼ = product of all constraints (AND logic)
      wᵢ = normalized weight of factor i
      Fᵢ = factor i score (0.0 to 1.0)

    If ANY constraint fails → Π Cⱼ = 0 → final score = 0
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point

from app.config import DEFAULT_CRS
from app.models.schemas import (
    Criterion, CriterionResult, ConstraintResult, LayerMetadata,
)

logger = logging.getLogger(__name__)


class SpatialAnalysisEngine:

    # ═══════════════════════════════════════════
    #  CRS UTILITIES
    # ═══════════════════════════════════════════

    @staticmethod
    def _detect_utm_crs(gdf: gpd.GeoDataFrame) -> str:
        bounds = gdf.total_bounds
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        zone = int((center_lon + 180) / 6) + 1
        epsg = (32600 + zone) if center_lat >= 0 else (32700 + zone)
        return f"EPSG:{epsg}"

    # ═══════════════════════════════════════════
    #  FILE I/O
    # ═══════════════════════════════════════════

    def extract_metadata(
        self, file_path: Path, layer_id: str, layer_name: str,
    ) -> LayerMetadata:
        gdf = gpd.read_file(file_path)
        if gdf.crs is None:
            gdf = gdf.set_crs(DEFAULT_CRS)
        geom_type = "Unknown"
        if not gdf.geometry.is_empty.all():
            geom_type = gdf.geometry.geom_type.mode().iloc[0]
        bounds = [round(b, 6) for b in gdf.total_bounds.tolist()]
        props = [c for c in gdf.columns if c != "geometry"]
        return LayerMetadata(
            layer_id=layer_id, name=layer_name,
            feature_count=len(gdf), geometry_type=geom_type,
            bounds=bounds, crs=str(gdf.crs), properties=props,
        )

    def load_layer(self, file_path: str) -> gpd.GeoDataFrame:
        gdf = gpd.read_file(file_path)
        if gdf.crs is None:
            gdf = gdf.set_crs(DEFAULT_CRS)
        return gdf

    # ═══════════════════════════════════════════
    #  DISTANCE DECAY
    # ═══════════════════════════════════════════

    @staticmethod
    def _apply_decay(
        distances: pd.Series, buffer_m: float,
        decay_type: str = "linear", invert: bool = False,
    ) -> pd.Series:
        if buffer_m <= 0:
            buffer_m = 1.0
        if decay_type == "linear":
            scores = 1.0 - (distances / buffer_m)
        elif decay_type == "gaussian":
            sigma = buffer_m / 3.0
            scores = np.exp(-(distances ** 2) / (2.0 * sigma ** 2))
        elif decay_type == "exponential":
            lam = 3.0 / buffer_m
            scores = np.exp(-lam * distances)
        elif decay_type == "inverse_power":
            d0 = buffer_m / 3.0
            scores = 1.0 / (1.0 + (distances / d0) ** 2)
        elif decay_type == "step":
            scores = (distances <= buffer_m).astype(float)
        else:
            scores = 1.0 - (distances / buffer_m)
        scores = scores.clip(lower=0.0, upper=1.0)
        if invert:
            scores = 1.0 - scores
        return scores

    # ═══════════════════════════════════════════
    #  DISTANCE COMPUTATION
    # ═══════════════════════════════════════════

    def _compute_distances(
        self, target_gdf: gpd.GeoDataFrame,
        criterion_gdf: gpd.GeoDataFrame, projected_crs: str,
    ) -> pd.Series:
        target_proj = target_gdf.to_crs(projected_crs)
        criterion_proj = criterion_gdf.to_crs(projected_crs)
        centroids = target_proj.geometry.centroid
        dissolved = criterion_proj.geometry.unary_union
        return centroids.distance(dissolved)

    # ═══════════════════════════════════════════
    #  CONSTRAINT EVALUATION
    # ═══════════════════════════════════════════
    #
    # Constraints return a boolean Series:
    #   True  = parcel PASSES (feasible)
    #   False = parcel FAILS  (eliminated)
    #
    # This is different from factor scoring which
    # returns a continuous 0-1 score.
    # ═══════════════════════════════════════════

    def _evaluate_constraint(
        self,
        target_gdf: gpd.GeoDataFrame,
        criterion_gdf: gpd.GeoDataFrame,
        criteria_type: str,
        parameters: Dict[str, Any],
        projected_crs: str,
    ) -> pd.Series:
        """
        Evaluate a hard constraint. Returns boolean Series.
        True = passes, False = eliminated.

        Constraint logic by type:
          exclusion:  PASS if parcel does NOT intersect criterion
          inclusion:  PASS if parcel DOES intersect criterion
          proximity:  PASS if parcel is WITHIN buffer_distance_m
          avoidance:  PASS if parcel is BEYOND buffer_distance_m
          density:    PASS if density score > threshold (default 0.1)
        """
        buffer_m = parameters.get("buffer_distance_m", 500)
        graduated = parameters.get("graduated", False)

        if criteria_type == "exclusion":
            if graduated:
                # Graduated constraint: fail if overlap > threshold
                threshold = parameters.get("max_overlap_pct", 0.0)
                target_proj = target_gdf.to_crs(projected_crs)
                criterion_proj = criterion_gdf.to_crs(projected_crs)
                dissolved = criterion_proj.geometry.unary_union
                parcel_areas = target_proj.geometry.area
                overlap_areas = target_proj.geometry.intersection(
                    dissolved
                ).area
                safe_areas = parcel_areas.replace(0, np.nan)
                overlap_pct = (overlap_areas / safe_areas).fillna(0.0)
                passes = overlap_pct <= threshold
            else:
                dissolved = criterion_gdf.geometry.unary_union
                passes = ~target_gdf.geometry.intersects(dissolved)

        elif criteria_type == "inclusion":
            if graduated:
                threshold = parameters.get("min_overlap_pct", 0.5)
                target_proj = target_gdf.to_crs(projected_crs)
                criterion_proj = criterion_gdf.to_crs(projected_crs)
                dissolved = criterion_proj.geometry.unary_union
                parcel_areas = target_proj.geometry.area
                overlap_areas = target_proj.geometry.intersection(
                    dissolved
                ).area
                safe_areas = parcel_areas.replace(0, np.nan)
                overlap_pct = (overlap_areas / safe_areas).fillna(0.0)
                passes = overlap_pct >= threshold
            else:
                dissolved = criterion_gdf.geometry.unary_union
                passes = target_gdf.geometry.intersects(dissolved)

        elif criteria_type == "proximity":
            # Must be WITHIN buffer distance
            distances = self._compute_distances(
                target_gdf, criterion_gdf, projected_crs
            )
            passes = distances <= buffer_m

        elif criteria_type == "avoidance":
            # Must be BEYOND buffer distance
            distances = self._compute_distances(
                target_gdf, criterion_gdf, projected_crs
            )
            passes = distances >= buffer_m

        elif criteria_type == "density":
            # Must have minimum density score
            threshold = parameters.get("min_density_score", 0.1)
            bandwidth_m = parameters.get("bandwidth_m", 1000)
            density_scores = self._score_density(
                target_gdf, criterion_gdf, bandwidth_m, projected_crs
            )
            normalized = self._normalize_min_max(density_scores)
            passes = normalized >= threshold

        else:
            logger.warning(
                f"Unknown constraint type: {criteria_type}. "
                f"All parcels pass."
            )
            passes = pd.Series(True, index=target_gdf.index)

        return passes.astype(bool)

    # ═══════════════════════════════════════════
    #  FACTOR SCORING (from Phase 5b, unchanged)
    # ═══════════════════════════════════════════

    def _score_proximity(
        self, target_gdf, criterion_gdf, buffer_m, decay, projected_crs,
    ) -> pd.Series:
        distances = self._compute_distances(
            target_gdf, criterion_gdf, projected_crs
        )
        scores = self._apply_decay(distances, buffer_m, decay, invert=False)
        logger.info(
            f"  Proximity [{decay}] — dist: "
            f"[{distances.min():.0f}m, {distances.max():.0f}m], "
            f"mean: {scores.mean():.3f}"
        )
        return scores

    def _score_avoidance(
        self, target_gdf, criterion_gdf, buffer_m, decay, projected_crs,
    ) -> pd.Series:
        distances = self._compute_distances(
            target_gdf, criterion_gdf, projected_crs
        )
        scores = self._apply_decay(distances, buffer_m, decay, invert=True)
        logger.info(
            f"  Avoidance [{decay}] — dist: "
            f"[{distances.min():.0f}m, {distances.max():.0f}m], "
            f"mean: {scores.mean():.3f}"
        )
        return scores

    def _score_inclusion(
        self, target_gdf, criterion_gdf, graduated, projected_crs,
    ) -> pd.Series:
        if not graduated:
            dissolved = criterion_gdf.geometry.unary_union
            return target_gdf.geometry.intersects(dissolved).astype(float)
        target_proj = target_gdf.to_crs(projected_crs)
        criterion_proj = criterion_gdf.to_crs(projected_crs)
        dissolved = criterion_proj.geometry.unary_union
        parcel_areas = target_proj.geometry.area
        overlap = target_proj.geometry.intersection(dissolved).area
        safe = parcel_areas.replace(0, np.nan)
        return (overlap / safe).fillna(0.0).clip(0.0, 1.0)

    def _score_exclusion(
        self, target_gdf, criterion_gdf, graduated, projected_crs,
    ) -> pd.Series:
        inclusion = self._score_inclusion(
            target_gdf, criterion_gdf, graduated, projected_crs
        )
        return 1.0 - inclusion

    def _score_density(
        self, target_gdf, criterion_gdf, bandwidth_m, projected_crs,
    ) -> pd.Series:
        target_proj = target_gdf.to_crs(projected_crs)
        criterion_proj = criterion_gdf.to_crs(projected_crs)
        geom_type = criterion_proj.geometry.geom_type.iloc[0]
        if geom_type in ("Polygon", "MultiPolygon",
                         "LineString", "MultiLineString"):
            source_geom = criterion_proj.geometry.centroid
        else:
            source_geom = criterion_proj.geometry
        target_centroids = target_proj.geometry.centroid
        source_xy = np.column_stack([
            source_geom.x.values, source_geom.y.values
        ])
        target_xy = np.column_stack([
            target_centroids.x.values, target_centroids.y.values
        ])
        h = max(bandwidth_m, 1.0)
        density = np.zeros(len(target_xy))
        for i in range(len(source_xy)):
            dx = target_xy[:, 0] - source_xy[i, 0]
            dy = target_xy[:, 1] - source_xy[i, 1]
            density += np.exp(-(dx**2 + dy**2) / (2.0 * h**2))
        return pd.Series(density, index=target_gdf.index)

    def _build_network_graph(
        self, roads_gdf, projected_crs, snap_tolerance_m=5.0,
    ) -> Tuple[nx.Graph, np.ndarray]:
        roads_proj = roads_gdf.to_crs(projected_crs)
        G = nx.Graph()
        all_lines = []
        for _, row in roads_proj.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            if geom.geom_type == "MultiLineString":
                all_lines.extend(geom.geoms)
            elif geom.geom_type == "LineString":
                all_lines.append(geom)
        if not all_lines:
            return G, np.array([])
        snap = max(snap_tolerance_m, 1.0)
        for line in all_lines:
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                x0 = round(coords[i][0] / snap) * snap
                y0 = round(coords[i][1] / snap) * snap
                x1 = round(coords[i+1][0] / snap) * snap
                y1 = round(coords[i+1][1] / snap) * snap
                start, end = (x0, y0), (x1, y1)
                if start == end:
                    continue
                dist = ((coords[i][0]-coords[i+1][0])**2 +
                        (coords[i][1]-coords[i+1][1])**2)**0.5
                if G.has_edge(start, end):
                    if G[start][end]["weight"] > dist:
                        G[start][end]["weight"] = dist
                else:
                    G.add_edge(start, end, weight=dist)
        nodes = list(G.nodes())
        node_array = np.array(nodes) if nodes else np.array([])
        return G, node_array

    def _snap_points_to_network(self, points, node_array):
        if len(node_array) == 0:
            return [None] * len(points)
        snapped = []
        for point in points:
            if point is None or point.is_empty:
                snapped.append(None)
                continue
            dists = np.sqrt(
                (node_array[:, 0] - point.x)**2 +
                (node_array[:, 1] - point.y)**2
            )
            snapped.append(tuple(node_array[np.argmin(dists)]))
        return snapped

    def _score_network_proximity(
        self, target_gdf, criterion_gdf, network_gdf,
        buffer_m, decay, projected_crs,
    ) -> pd.Series:
        G, node_array = self._build_network_graph(
            network_gdf, projected_crs
        )
        if G.number_of_nodes() == 0:
            return self._score_proximity(
                target_gdf, criterion_gdf,
                buffer_m, decay, projected_crs
            )
        target_proj = target_gdf.to_crs(projected_crs)
        criterion_proj = criterion_gdf.to_crs(projected_crs)
        criterion_nodes = self._snap_points_to_network(
            criterion_proj.geometry.centroid, node_array
        )
        valid = [n for n in criterion_nodes if n is not None]
        if not valid:
            return self._score_proximity(
                target_gdf, criterion_gdf,
                buffer_m, decay, projected_crs
            )
        SUPER = "__super__"
        G.add_node(SUPER)
        for cn in valid:
            if cn in G:
                G.add_edge(SUPER, cn, weight=0.0)
        try:
            net_dists = nx.single_source_dijkstra_path_length(
                G, SUPER, weight="weight"
            )
        except nx.NetworkXError:
            G.remove_node(SUPER)
            return self._score_proximity(
                target_gdf, criterion_gdf,
                buffer_m, decay, projected_crs
            )
        G.remove_node(SUPER)
        target_centroids = target_proj.geometry.centroid
        target_nodes = self._snap_points_to_network(
            target_centroids, node_array
        )
        distances = []
        for i, tn in enumerate(target_nodes):
            if tn is None or tn not in net_dists:
                distances.append(buffer_m * 2)
                continue
            c = target_centroids.iloc[i]
            snap_d = ((c.x - tn[0])**2 + (c.y - tn[1])**2)**0.5
            distances.append(net_dists[tn] + snap_d)
        return self._apply_decay(
            pd.Series(distances, index=target_gdf.index),
            buffer_m, decay
        )

    # ═══════════════════════════════════════════
    #  NORMALIZATION
    # ═══════════════════════════════════════════

    @staticmethod
    def _normalize_min_max(scores: pd.Series) -> pd.Series:
        smin, smax = scores.min(), scores.max()
        if smin == smax:
            return pd.Series(
                0.5 if smax > 0 else 0.0, index=scores.index
            )
        return (scores - smin) / (smax - smin)

    # ═══════════════════════════════════════════
    #  HELPER: Clean layer name from file path
    # ═══════════════════════════════════════════

    @staticmethod
    def _clean_layer_name(file_path: str) -> str:
        stem = Path(file_path).stem
        parts = stem.split("_", 1)
        return parts[1] if len(parts) > 1 else stem

    # ═══════════════════════════════════════════
    #  HELPER: Resolve target / network layers
    # ═══════════════════════════════════════════

    def _resolve_target_layer(
        self, layer_paths, target_id,
    ) -> Optional[gpd.GeoDataFrame]:
        if target_id and target_id in layer_paths:
            return self.load_layer(layer_paths[target_id])
        for lid, path in layer_paths.items():
            gdf = self.load_layer(path)
            if len(gdf) > 0:
                if gdf.geometry.geom_type.iloc[0] in (
                    "Polygon", "MultiPolygon"
                ):
                    return gdf
        if layer_paths:
            return self.load_layer(next(iter(layer_paths.values())))
        return None

    def _resolve_network_layer(
        self, layer_paths, network_layer_id,
    ) -> Optional[gpd.GeoDataFrame]:
        if network_layer_id and network_layer_id in layer_paths:
            gdf = self.load_layer(layer_paths[network_layer_id])
            if "Line" in gdf.geometry.geom_type.iloc[0]:
                return gdf
        for lid, path in layer_paths.items():
            gdf = self.load_layer(path)
            if len(gdf) > 0 and "Line" in gdf.geometry.geom_type.iloc[0]:
                return gdf
        return None

    # ═══════════════════════════════════════════
    #  ROUTE A CRITERION TO ITS SCORING FUNCTION
    # ═══════════════════════════════════════════

    def _score_factor(
        self,
        target_gdf: gpd.GeoDataFrame,
        criterion_gdf: gpd.GeoDataFrame,
        criteria_type: str,
        parameters: Dict[str, Any],
        projected_crs: str,
        layer_paths: Dict[str, str],
    ) -> pd.Series:
        """
        Score a single soft factor. Routes to the appropriate
        scoring function based on criteria_type.
        Returns raw (un-normalized) scores.
        """
        buffer_m = parameters.get("buffer_distance_m", 500)
        decay = parameters.get("decay_function", "linear")
        graduated = parameters.get("graduated", False)
        bandwidth_m = parameters.get("bandwidth_m", 1000)
        network_lid = parameters.get("network_layer_id", None)

        if criteria_type == "proximity":
            return self._score_proximity(
                target_gdf, criterion_gdf,
                buffer_m, decay, projected_crs,
            )

        elif criteria_type == "avoidance":
            return self._score_avoidance(
                target_gdf, criterion_gdf,
                buffer_m, decay, projected_crs,
            )

        elif criteria_type == "inclusion":
            return self._score_inclusion(
                target_gdf, criterion_gdf,
                graduated, projected_crs,
            )

        elif criteria_type == "exclusion":
            return self._score_exclusion(
                target_gdf, criterion_gdf,
                graduated, projected_crs,
            )

        elif criteria_type == "density":
            return self._score_density(
                target_gdf, criterion_gdf,
                bandwidth_m, projected_crs,
            )

        elif criteria_type == "network_proximity":
            net_gdf = self._resolve_network_layer(
                layer_paths, network_lid
            )
            if net_gdf is not None:
                return self._score_network_proximity(
                    target_gdf, criterion_gdf, net_gdf,
                    buffer_m, decay, projected_crs,
                )
            else:
                return self._score_proximity(
                    target_gdf, criterion_gdf,
                    buffer_m, decay, projected_crs,
                )

        else:
            logger.warning(f"Unknown factor type: {criteria_type}")
            return pd.Series(0.5, index=target_gdf.index)

    # ═══════════════════════════════════════════════════
    #  MAIN PIPELINE — CONSTRAINTS THEN FACTORS
    # ═══════════════════════════════════════════════════

    def run_suitability_analysis(
        self,
        layer_paths: Dict[str, str],
        criteria: List[Criterion],
        target_layer_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[CriterionResult], List[ConstraintResult]]:
        """
        Two-stage suitability analysis:
            Stage 1: Evaluate hard constraints → feasibility mask
            Stage 2: Score soft factors → weighted combination
            Combine: final = mask × weighted_score

        Returns:
            (result_geojson, criterion_details, constraint_summary)
        """
        print("\n" + "=" * 60)
        print("  SUITABILITY ANALYSIS — PHASE A")
        print("  Constraints + Factors Pipeline")
        print("=" * 60)

        # ── Load target ──
        target_gdf = self._resolve_target_layer(
            layer_paths, target_layer_id
        )
        if target_gdf is None or len(target_gdf) == 0:
            return (
                {"type": "FeatureCollection", "features": []},
                [], [],
            )

        target_gdf = target_gdf.reset_index(drop=True)
        projected_crs = self._detect_utm_crs(target_gdf)
        n_parcels = len(target_gdf)
        print(f"  Target: {n_parcels} features")
        print(f"  CRS: {projected_crs}")

        # ── Separate constraints from factors ──
        constraints = [
            c for c in criteria
            if c.is_constraint
            and c.layer_id in layer_paths
            and c.layer_id != target_layer_id
        ]
        factors = [
            c for c in criteria
            if not c.is_constraint
            and c.weight > 0
            and c.layer_id in layer_paths
            and c.layer_id != target_layer_id
        ]

        print(f"  Hard constraints: {len(constraints)}")
        print(f"  Soft factors: {len(factors)}")

        # ════════════════════════════════════════
        #  STAGE 1: EVALUATE HARD CONSTRAINTS
        # ════════════════════════════════════════

        print(f"\n  ── STAGE 1: CONSTRAINTS ──")

        # Combined mask — starts as all True (all feasible)
        feasibility_mask = pd.Series(True, index=target_gdf.index)
        constraint_summary = []

        # Track which constraints each parcel failed
        # This will be a list of constraint names per parcel
        failed_reasons = [[] for _ in range(n_parcels)]

        for i, con in enumerate(constraints, 1):
            con_gdf = self.load_layer(layer_paths[con.layer_id])
            name = self._clean_layer_name(layer_paths[con.layer_id])

            print(f"\n  [{i}/{len(constraints)}] CONSTRAINT: {name}")
            print(f"     Type: {con.criteria_type}")

            # Evaluate: True = passes, False = eliminated
            passes = self._evaluate_constraint(
                target_gdf, con_gdf,
                con.criteria_type, con.parameters, projected_crs,
            )

            n_pass = int(passes.sum())
            n_fail = n_parcels - n_pass
            pass_rate = n_pass / n_parcels if n_parcels > 0 else 0

            print(f"     PASSED: {n_pass}/{n_parcels} "
                  f"({pass_rate:.1%})")
            print(f"     FAILED: {n_fail}/{n_parcels}")

            # Store pass/fail in the target GDF as a property
            col_name = f"constraint_{name}"
            target_gdf[col_name] = passes.map(
                {True: "PASS", False: "FAIL"}
            )

            # Track failure reasons per parcel
            for idx in range(n_parcels):
                if not passes.iloc[idx]:
                    failed_reasons[idx].append(name)

            # AND logic: if any constraint fails, parcel is out
            feasibility_mask &= passes

            constraint_summary.append(ConstraintResult(
                name=name,
                criteria_type=con.criteria_type,
                passed=n_pass,
                failed=n_fail,
                pass_rate=round(pass_rate, 4),
            ))

        # Store feasibility
        n_feasible = int(feasibility_mask.sum())
        n_infeasible = n_parcels - n_feasible
        target_gdf["is_feasible"] = feasibility_mask
        target_gdf["failed_constraints"] = [
            ", ".join(reasons) if reasons else ""
            for reasons in failed_reasons
        ]

        print(f"\n  ── CONSTRAINT RESULT ──")
        print(f"     Feasible: {n_feasible}/{n_parcels}")
        print(f"     Eliminated: {n_infeasible}/{n_parcels}")

        if n_feasible == 0 and len(factors) > 0:
            print("  ⚠ ALL parcels eliminated by constraints!")
            print("     Factor scores will be computed but final "
                  "scores will all be 0.")

        # ════════════════════════════════════════
        #  STAGE 2: SCORE SOFT FACTORS
        # ════════════════════════════════════════

        print(f"\n  ── STAGE 2: FACTORS ──")

        score_columns = []
        weight_map = {}
        criterion_details = []

        if not factors:
            print("  No soft factors configured.")
            # If only constraints, feasible parcels get score 1.0
            if constraints:
                target_gdf["suitability_score"] = (
                    feasibility_mask.astype(float)
                )
        else:
            total_weight = sum(f.weight for f in factors)
            print(f"  Factor weight sum: {total_weight}%")

            for i, fac in enumerate(factors, 1):
                fac_gdf = self.load_layer(layer_paths[fac.layer_id])
                name = self._clean_layer_name(
                    layer_paths[fac.layer_id]
                )
                score_col = f"score_{name}"

                print(f"\n  [{i}/{len(factors)}] FACTOR: {name}")
                print(f"     Type: {fac.criteria_type}")
                print(f"     Weight: {fac.weight}%")

                try:
                    raw = self._score_factor(
                        target_gdf, fac_gdf,
                        fac.criteria_type, fac.parameters,
                        projected_crs, layer_paths,
                    )
                except Exception as e:
                    print(f"     ✗ Error: {e}")
                    raw = pd.Series(0.5, index=target_gdf.index)

                normalized = self._normalize_min_max(raw)
                target_gdf[score_col] = normalized.round(4)
                score_columns.append(score_col)
                weight_map[score_col] = fac.weight / total_weight

                criterion_details.append(CriterionResult(
                    name=name,
                    criteria_type=fac.criteria_type,
                    is_constraint=False,
                    weight_pct=fac.weight,
                    normalized_weight=round(
                        weight_map[score_col], 4
                    ),
                    mean_score=round(float(normalized.mean()), 4),
                    min_score=round(float(normalized.min()), 4),
                    max_score=round(float(normalized.max()), 4),
                ))

                print(f"     Range: [{normalized.min():.3f}, "
                      f"{normalized.max():.3f}]")

            # ── Weighted combination ──
            print(f"\n  ── Weighted Combination ──")
            composite = pd.Series(0.0, index=target_gdf.index)
            for col in score_columns:
                contribution = target_gdf[col] * weight_map[col]
                composite += contribution
                print(f"     {col} × {weight_map[col]:.3f} → "
                      f"mean: {contribution.mean():.4f}")

            # Store the UNCONSTRAINED factor score
            # (useful for popups: "would have scored X")
            target_gdf["factor_score"] = composite.round(4)

            # ════════════════════════════════════════
            #  STAGE 3: COMBINE
            #    final = constraint_mask × factor_score
            # ════════════════════════════════════════

            print(f"\n  ── STAGE 3: COMBINE ──")
            print(f"     Formula: final = mask × factor_score")

            target_gdf["suitability_score"] = (
                feasibility_mask.astype(float) * composite
            ).round(4)

        # ── Classify ──
        # Infeasible parcels get their own class
        target_gdf["suitability_class"] = "Infeasible"

        if n_feasible > 0:
            feasible_idx = target_gdf[feasibility_mask].index
            feasible_scores = target_gdf.loc[
                feasible_idx, "suitability_score"
            ]

            if len(factors) > 0:
                # Classify feasible parcels by score
                classes = pd.cut(
                    feasible_scores,
                    bins=[-0.001, 0.2, 0.4, 0.6, 0.8, 1.001],
                    labels=[
                        "Very Low", "Low", "Moderate",
                        "High", "Very High",
                    ],
                ).astype(str)
                target_gdf.loc[feasible_idx, "suitability_class"] = (
                    classes
                )
            else:
                # No factors — feasible parcels all get "Feasible"
                target_gdf.loc[
                    feasible_idx, "suitability_class"
                ] = "Feasible"

        # ── Rank (only feasible parcels) ──
        target_gdf["rank"] = 0
        if n_feasible > 0:
            feasible_df = target_gdf[feasibility_mask]
            ranks = (
                feasible_df["suitability_score"]
                .rank(ascending=False, method="min")
                .astype(int)
            )
            target_gdf.loc[feasibility_mask, "rank"] = ranks

        # ── Summary ──
        scores = target_gdf["suitability_score"]
        print(f"\n  ── FINAL RESULTS ──")
        print(f"     Total parcels: {n_parcels}")
        print(f"     Feasible: {n_feasible}")
        print(f"     Infeasible: {n_infeasible}")
        if n_feasible > 0:
            feasible_scores = scores[feasibility_mask]
            print(f"     Score range (feasible): "
                  f"[{feasible_scores.min():.4f}, "
                  f"{feasible_scores.max():.4f}]")
            print(f"     Mean (feasible): "
                  f"{feasible_scores.mean():.4f}")
        for cls, cnt in (
            target_gdf["suitability_class"].value_counts().items()
        ):
            print(f"     {cls}: {cnt}")
        print("=" * 60 + "\n")

        # ── Export ──
        output = target_gdf.to_crs(DEFAULT_CRS)
        result = json.loads(output.to_json())
        return result, criterion_details, constraint_summary