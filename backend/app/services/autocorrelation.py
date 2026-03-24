"""
Spatial Autocorrelation Engine — Phase F

Implements Global and Local Moran's I using pure NumPy.
No PySAL dependency required.

Global Moran's I:
    Measures overall spatial clustering of a variable.
    Reference: Moran, P.A.P. (1950). Notes on continuous
    stochastic phenomena. Biometrika, 37, 17-23.

Local Moran's I (LISA):
    Identifies local clusters and spatial outliers.
    Reference: Anselin, L. (1995). Local Indicators of
    Spatial Association — LISA. Geographical Analysis, 27, 93-115.

Spatial Weights:
    K-Nearest Neighbors (KNN) with row standardization.
    More robust than contiguity for irregular geometries.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import geopandas as gpd

logger = logging.getLogger(__name__)


class SpatialAutocorrelationEngine:
    """
    Compute spatial autocorrelation statistics on
    suitability analysis results.
    """

    def analyze(
        self,
        result_geojson: Dict[str, Any],
        variable: str = "suitability_score",
        k_neighbors: int = 5,
        n_permutations: int = 999,
        significance_level: float = 0.05,
        seed: int = 42,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Run spatial autocorrelation analysis.

        Args:
            result_geojson: Scored GeoJSON from analysis
            variable: Property name to analyze
            k_neighbors: Number of nearest neighbors for weights
            n_permutations: Permutations for significance testing
            significance_level: p-value threshold
            seed: Random seed

        Returns:
            (output_geojson, summary)
        """
        print("\n" + "=" * 60)
        print("  SPATIAL AUTOCORRELATION ANALYSIS")
        print(f"  Variable: {variable}")
        print(f"  K neighbors: {k_neighbors}")
        print(f"  Permutations: {n_permutations}")
        print(f"  Significance: {significance_level}")
        print("=" * 60)

        np.random.seed(seed)

        features = result_geojson.get("features", [])
        if not features:
            return result_geojson, {"error": "No features"}

        # ── Extract feasible features ──
        feasible_idx = []
        feasible_features = []
        values = []

        for i, f in enumerate(features):
            props = f.get("properties", {})
            if props.get("is_feasible", True):
                val = props.get(variable)
                if val is not None and not np.isnan(float(val)):
                    feasible_idx.append(i)
                    feasible_features.append(f)
                    values.append(float(val))

        n = len(values)
        print(f"  Feasible features with valid scores: {n}")

        if n < 5:
            print("  ⚠ Too few features for spatial autocorrelation")
            return result_geojson, {
                "error": "Need at least 5 feasible features",
                "n_features": n,
            }

        values = np.array(values)

        # ── Compute centroids ──
        centroids = self._extract_centroids(feasible_features)
        print(f"  Centroids extracted: {len(centroids)}")

        # ── Build spatial weights (KNN) ──
        k = min(k_neighbors, n - 1)
        W = self._build_knn_weights(centroids, k)
        print(f"  Spatial weights: KNN k={k}, "
              f"row-standardized")

        # ── Global Moran's I ──
        global_I, global_EI, global_p, global_z = (
            self._global_morans_i(values, W, n_permutations)
        )

        print(f"\n  ── GLOBAL MORAN'S I ──")
        print(f"     I = {global_I:.4f}")
        print(f"     E[I] = {global_EI:.4f}")
        print(f"     Z-score = {global_z:.4f}")
        print(f"     p-value = {global_p:.4f}")

        if global_p < significance_level:
            if global_I > 0:
                pattern = "Clustered"
                interpretation = (
                    "High-suitability areas tend to be near other "
                    "high-suitability areas, and low near low. "
                    "There are distinct geographic zones of "
                    "suitability."
                )
            else:
                pattern = "Dispersed"
                interpretation = (
                    "High and low suitability scores alternate "
                    "spatially (checkerboard pattern). Adjacent "
                    "parcels tend to have contrasting scores."
                )
        else:
            pattern = "Random"
            interpretation = (
                "No statistically significant spatial pattern. "
                "Suitability scores are distributed randomly "
                "across the study area."
            )

        print(f"     Pattern: {pattern}")

        # ── Local Moran's I (LISA) ──
        local_I, local_p, lisa_classes = (
            self._local_morans_i(
                values, W, n_permutations, significance_level
            )
        )

        # Count classes
        class_counts = {}
        for cls in lisa_classes:
            class_counts[cls] = class_counts.get(cls, 0) + 1

        print(f"\n  ── LOCAL MORAN'S I (LISA) ──")
        for cls, cnt in sorted(class_counts.items()):
            print(f"     {cls}: {cnt}")

        # ── Spatial lag values (for Moran scatter plot) ──
        z_values = (values - values.mean()) / max(values.std(), 1e-10)
        spatial_lag = W @ z_values

        # ── Build output GeoJSON ──
        output_features = []
        feasible_counter = 0

        for i, f in enumerate(features):
            new_props = dict(f.get("properties", {}))

            if i in feasible_idx:
                fi = feasible_idx.index(i)

                new_props["lisa_class"] = lisa_classes[fi]
                new_props["local_morans_i"] = round(
                    float(local_I[fi]), 4
                )
                new_props["lisa_p_value"] = round(
                    float(local_p[fi]), 4
                )
                new_props["z_score"] = round(
                    float(z_values[fi]), 4
                )
                new_props["spatial_lag"] = round(
                    float(spatial_lag[fi]), 4
                )
                new_props["lisa_significant"] = bool(
                    local_p[fi] < significance_level
                )
            else:
                new_props["lisa_class"] = "Infeasible"
                new_props["local_morans_i"] = 0
                new_props["lisa_p_value"] = 1.0
                new_props["lisa_significant"] = False

            output_features.append({
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": new_props,
            })

        output_geojson = {
            "type": "FeatureCollection",
            "features": output_features,
        }

        # ── Summary ──
        summary = {
            "global_morans_i": round(float(global_I), 4),
            "expected_i": round(float(global_EI), 4),
            "z_score": round(float(global_z), 4),
            "p_value": round(float(global_p), 4),
            "significant": bool(global_p < significance_level),
            "pattern": pattern,
            "interpretation": interpretation,
            "n_features": n,
            "k_neighbors": k,
            "n_permutations": n_permutations,
            "significance_level": significance_level,
            "lisa_class_counts": class_counts,
            "variable": variable,
            "moran_scatter": {
                "z_values": z_values.round(4).tolist(),
                "spatial_lag": spatial_lag.round(4).tolist(),
                "classes": lisa_classes,
            },
        }

        print(f"\n  ✅ Autocorrelation analysis complete")
        print("=" * 60 + "\n")

        return output_geojson, summary

    # ═══════════════════════════════════════════
    #  Centroid Extraction
    # ═══════════════════════════════════════════

    def _extract_centroids(
        self, features: List[Dict]
    ) -> np.ndarray:
        """
        Extract centroids from GeoJSON features.
        Returns Nx2 array of [x, y] coordinates.
        """
        from shapely.geometry import shape

        centroids = []
        for f in features:
            geom = shape(f["geometry"])
            c = geom.centroid
            centroids.append([c.x, c.y])

        return np.array(centroids)

    # ═══════════════════════════════════════════
    #  Spatial Weights (KNN)
    # ═══════════════════════════════════════════

    def _build_knn_weights(
        self, centroids: np.ndarray, k: int
    ) -> np.ndarray:
        """
        Build K-Nearest Neighbors spatial weight matrix.

        For each feature, find the K closest features
        by Euclidean distance between centroids.
        Row-standardize so each row sums to 1.

        Returns:
            NxN row-standardized weight matrix.
        """
        n = len(centroids)
        W = np.zeros((n, n))

        # Compute pairwise distances
        for i in range(n):
            dists = np.sqrt(
                (centroids[:, 0] - centroids[i, 0]) ** 2 +
                (centroids[:, 1] - centroids[i, 1]) ** 2
            )
            # Set self-distance to infinity
            dists[i] = np.inf
            # Find k nearest
            neighbors = np.argsort(dists)[:k]
            W[i, neighbors] = 1.0

        # Row standardize
        row_sums = W.sum(axis=1)
        row_sums[row_sums == 0] = 1  # Avoid division by zero
        W = W / row_sums[:, np.newaxis]

        return W

    # ═══════════════════════════════════════════
    #  Global Moran's I
    # ═══════════════════════════════════════════

    def _global_morans_i(
        self,
        values: np.ndarray,
        W: np.ndarray,
        n_permutations: int,
    ) -> Tuple[float, float, float, float]:
        """
        Compute Global Moran's I with permutation test.

        I = (N/S0) × (z'Wz / z'z)

        Where:
            z = x - mean(x)  (deviations from mean)
            S0 = sum of all weights
            N = number of observations

        Significance via permutation:
            Shuffle z values n_permutations times,
            recompute I each time, count how many
            simulated I values are as extreme as observed.
        """
        n = len(values)
        z = values - values.mean()
        S0 = W.sum()

        # Compute observed I
        numerator = float(z @ W @ z)
        denominator = float(z @ z)

        if denominator == 0 or S0 == 0:
            return 0.0, 0.0, 0.0, 1.0

        I_observed = (n / S0) * (numerator / denominator)

        # Expected I under null hypothesis
        E_I = -1.0 / (n - 1)

        # Permutation test
        I_simulated = np.zeros(n_permutations)
        for perm in range(n_permutations):
            z_perm = np.random.permutation(z)
            num_perm = float(z_perm @ W @ z_perm)
            I_simulated[perm] = (n / S0) * (num_perm / denominator)

        # Two-tailed p-value
        more_extreme = np.sum(np.abs(I_simulated) >= abs(I_observed))
        p_value = (more_extreme + 1) / (n_permutations + 1)

        # Z-score
        std_sim = I_simulated.std()
        if std_sim > 0:
            z_score = (I_observed - E_I) / std_sim
        else:
            z_score = 0.0

        return I_observed, E_I, p_value, z_score

    # ═══════════════════════════════════════════
    #  Local Moran's I (LISA)
    # ═══════════════════════════════════════════

    def _local_morans_i(
        self,
        values: np.ndarray,
        W: np.ndarray,
        n_permutations: int,
        significance_level: float,
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Compute Local Moran's I for each feature.

        Iᵢ = zᵢ × Σⱼ wᵢⱼ × zⱼ

        Where zᵢ = (xᵢ - x̄) / σ (standardized)

        Classification:
            HH: zᵢ > 0 AND lag > 0 AND significant → Hot Spot
            LL: zᵢ < 0 AND lag < 0 AND significant → Cold Spot
            HL: zᵢ > 0 AND lag < 0 AND significant → High Outlier
            LH: zᵢ < 0 AND lag > 0 AND significant → Low Outlier
            NS: not significant
        """
        n = len(values)
        mean_val = values.mean()
        std_val = values.std()

        if std_val == 0:
            return (
                np.zeros(n),
                np.ones(n),
                ["Not Significant"] * n,
            )

        z = (values - mean_val) / std_val
        spatial_lag = W @ z

        # Compute local I
        local_I = z * spatial_lag

        # Permutation test for each location
        local_p = np.ones(n)

        for i in range(n):
            # Get neighbors
            neighbors = np.where(W[i] > 0)[0]
            if len(neighbors) == 0:
                continue

            # Conditional permutation
            sim_I = np.zeros(n_permutations)
            other_indices = np.arange(n)
            other_indices = other_indices[other_indices != i]

            for perm in range(n_permutations):
                # Randomly pick len(neighbors) values from others
                perm_indices = np.random.choice(
                    other_indices, size=len(neighbors), replace=False
                )
                perm_lag = np.mean(z[perm_indices])
                sim_I[perm] = z[i] * perm_lag

            # Pseudo p-value (two-tailed)
            more_extreme = np.sum(np.abs(sim_I) >= abs(local_I[i]))
            local_p[i] = (more_extreme + 1) / (n_permutations + 1)

        # ── Classify ──
        classes = []
        for i in range(n):
            if local_p[i] >= significance_level:
                classes.append("Not Significant")
            elif z[i] > 0 and spatial_lag[i] > 0:
                classes.append("High-High")
            elif z[i] < 0 and spatial_lag[i] < 0:
                classes.append("Low-Low")
            elif z[i] > 0 and spatial_lag[i] < 0:
                classes.append("High-Low")
            elif z[i] < 0 and spatial_lag[i] > 0:
                classes.append("Low-High")
            else:
                classes.append("Not Significant")

        return local_I, local_p, classes