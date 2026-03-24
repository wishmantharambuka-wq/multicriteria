"""
Analytic Hierarchy Process (AHP) — Weight Derivation Engine

Reference: Saaty, T.L. (1980). The Analytic Hierarchy Process.
McGraw-Hill, New York.

This module implements two methods for computing priority
vectors from pairwise comparison matrices:

1. Eigenvector Method (primary)
   - Exact mathematical solution
   - Finds the principal eigenvector of the comparison matrix
   - Industry and academic standard

2. Geometric Mean Method (verification)
   - Simpler approximation
   - Row-wise geometric mean, then normalize
   - Gives nearly identical results for consistent matrices
   - Diverges slightly for inconsistent ones

Both methods produce weights that sum to 1.0.
"""

import logging
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# Saaty's Random Index (RI) table
# These are the average consistency indices of randomly
# generated reciprocal matrices. Used as the denominator
# in the Consistency Ratio.
#
# For n=1,2: RI=0, meaning CR is always 0 (trivially consistent)
# For n≥3:  RI increases as larger matrices have more room
#           for inconsistency.
RANDOM_INDEX = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
    11: 1.51,
    12: 1.54,
    13: 1.56,
    14: 1.57,
    15: 1.59,
}


class AHPEngine:
    """
    Analytic Hierarchy Process computation engine.

    Usage:
        engine = AHPEngine()
        result = engine.compute_weights(
            criteria_names=["roads", "flood", "amenities"],
            comparisons=[(0,1, 1/5), (0,2, 3), (1,2, 7)]
        )
    """

    def compute_weights(
        self,
        criteria_names: List[str],
        comparisons: List[Tuple[int, int, float]],
    ) -> Dict:
        """
        Compute AHP priority weights from pairwise comparisons.

        Args:
            criteria_names: Ordered list of criterion names
            comparisons: List of (row, col, value) tuples
                         representing upper-triangle comparisons.
                         value = how much more important is row
                         criterion than col criterion.

        Returns:
            Dict with weights, consistency metrics, and the
            full comparison matrix.
        """
        n = len(criteria_names)
        print(f"\n  🧮 AHP COMPUTATION")
        print(f"     Criteria: {criteria_names}")
        print(f"     n = {n}, comparisons = {len(comparisons)}")

        # ── Step 1: Build comparison matrix ──
        matrix = self._build_matrix(n, comparisons)
        print(f"     Matrix built (reciprocal, diagonal=1)")

        # ── Step 2: Compute weights via eigenvector method ──
        weights_eig, lambda_max = self._eigenvector_method(matrix)
        print(f"     Eigenvector weights: "
              f"{[f'{w:.4f}' for w in weights_eig]}")
        print(f"     λ_max = {lambda_max:.4f}")

        # ── Step 3: Compute weights via geometric mean ──
        weights_geo = self._geometric_mean_method(matrix)
        print(f"     Geometric mean weights: "
              f"{[f'{w:.4f}' for w in weights_geo]}")

        # ── Step 4: Check agreement between methods ──
        max_diff = np.max(np.abs(weights_eig - weights_geo))
        print(f"     Method agreement: max diff = {max_diff:.4f}")

        # Use eigenvector as primary (academic standard)
        weights = weights_eig

        # ── Step 5: Consistency check ──
        ci, cr, is_consistent = self._check_consistency(
            lambda_max, n
        )
        print(f"     CI = {ci:.4f}")
        print(f"     CR = {cr:.4f} "
              f"{'✅ CONSISTENT' if is_consistent else '⚠️ INCONSISTENT'}")

        # ── Step 6: Convert to percentages ──
        weights_pct = (weights * 100).round(1)

        # Adjust to sum to exactly 100
        weights_pct = self._adjust_to_100(weights_pct)

        # ── Build result ──
        weight_results = []
        for i, name in enumerate(criteria_names):
            weight_results.append({
                "name": name,
                "weight": round(float(weights[i]), 4),
                "weight_pct": float(weights_pct[i]),
            })

        message = self._build_message(cr, is_consistent, n)

        result = {
            "weights": weight_results,
            "lambda_max": round(float(lambda_max), 4),
            "consistency_index": round(float(ci), 4),
            "consistency_ratio": round(float(cr), 4),
            "is_consistent": is_consistent,
            "consistency_threshold": 0.10,
            "method": "eigenvector",
            "matrix": matrix.tolist(),
            "n_criteria": n,
            "message": message,
        }

        print(f"     Final weights: "
              f"{[f'{r['name']}={r['weight_pct']}%' for r in weight_results]}")
        print()

        return result

    # ═══════════════════════════════════════════
    #  Matrix Construction
    # ═══════════════════════════════════════════

    def _build_matrix(
        self,
        n: int,
        comparisons: List[Tuple[int, int, float]],
    ) -> np.ndarray:
        """
        Build the n×n reciprocal comparison matrix.

        Properties of a valid comparison matrix:
        - Diagonal: a_ii = 1 (criterion compared to itself)
        - Reciprocal: a_ji = 1/a_ij
        - All entries positive

        Example for n=3:
        comparisons = [(0,1, 3), (0,2, 5), (1,2, 2)]

        Produces:
        [[1,   3,   5  ],
         [1/3, 1,   2  ],
         [1/5, 1/2, 1  ]]
        """
        matrix = np.ones((n, n))

        for row, col, value in comparisons:
            if 0 <= row < n and 0 <= col < n and row != col:
                # Ensure value is positive
                value = max(value, 1 / 9)
                matrix[row, col] = value
                matrix[col, row] = 1.0 / value

        return matrix

    # ═══════════════════════════════════════════
    #  Eigenvector Method (Primary)
    # ═══════════════════════════════════════════

    def _eigenvector_method(
        self, matrix: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        Compute the priority vector using the eigenvector method.

        For a perfectly consistent matrix, the largest eigenvalue
        equals n and the corresponding eigenvector gives the
        exact priority weights.

        For an inconsistent matrix, the largest eigenvalue > n,
        and the degree of excess measures the inconsistency.

        Steps:
        1. Compute all eigenvalues and eigenvectors
        2. Find the eigenvalue with the largest real part
        3. Extract its eigenvector
        4. Take the real part (may have tiny imaginary component)
        5. Ensure all positive (eigenvectors can have arbitrary sign)
        6. Normalize to sum to 1
        """
        n = len(matrix)

        if n == 1:
            return np.array([1.0]), 1.0

        eigenvalues, eigenvectors = np.linalg.eig(matrix)

        # Find dominant eigenvalue (largest real part)
        real_parts = np.real(eigenvalues)
        max_idx = np.argmax(real_parts)
        lambda_max = float(real_parts[max_idx])

        # Extract eigenvector
        weights = np.real(eigenvectors[:, max_idx])

        # Ensure all positive
        if np.any(weights < 0):
            weights = np.abs(weights)

        # Normalize
        total = weights.sum()
        if total > 0:
            weights = weights / total
        else:
            weights = np.ones(n) / n

        return weights, lambda_max

    # ═══════════════════════════════════════════
    #  Geometric Mean Method (Verification)
    # ═══════════════════════════════════════════

    def _geometric_mean_method(
        self, matrix: np.ndarray
    ) -> np.ndarray:
        """
        Compute weights using the geometric mean of each row.

        For each criterion i:
          w_i = (∏_j a_ij)^(1/n)

        Then normalize: w_i = w_i / Σ w_i

        This method is:
        - Simpler to understand and implement
        - Preserves the reciprocal property of the matrix
        - Gives results very close to the eigenvector method
        - Recommended by Crawford and Williams (1985) for
          its superior mathematical properties
        """
        n = len(matrix)

        if n == 1:
            return np.array([1.0])

        # Row-wise geometric mean
        geo_means = np.prod(matrix, axis=1) ** (1.0 / n)

        # Normalize
        total = geo_means.sum()
        if total > 0:
            return geo_means / total
        return np.ones(n) / n

    # ═══════════════════════════════════════════
    #  Consistency Check
    # ═══════════════════════════════════════════

    def _check_consistency(
        self, lambda_max: float, n: int
    ) -> Tuple[float, float, bool]:
        """
        Compute the Consistency Ratio (CR).

        CI = (λ_max - n) / (n - 1)
            Measures how far λ_max deviates from n.
            For a perfectly consistent matrix, CI = 0.

        CR = CI / RI
            Normalizes CI against what you'd expect from
            random judgments. CR < 0.10 means your judgments
            are significantly more consistent than random.

        Interpretation:
            CR = 0.00:  Perfect consistency
            CR < 0.05:  Very good consistency
            CR < 0.10:  Acceptable consistency
            CR ≥ 0.10:  Judgments should be reviewed

        Special cases:
            n ≤ 2: CR = 0 (always consistent by definition,
                   because RI = 0 for n ≤ 2)
        """
        if n <= 2:
            return 0.0, 0.0, True

        ci = (lambda_max - n) / (n - 1)

        # Clamp CI to non-negative (numerical precision)
        ci = max(ci, 0.0)

        ri = RANDOM_INDEX.get(n, 1.49)

        if ri == 0:
            cr = 0.0
        else:
            cr = ci / ri

        is_consistent = cr < 0.10

        return ci, cr, is_consistent

    # ═══════════════════════════════════════════
    #  Utility Methods
    # ═══════════════════════════════════════════

    @staticmethod
    def _adjust_to_100(weights_pct: np.ndarray) -> np.ndarray:
        """
        Ensure percentage weights sum to exactly 100.
        Distributes rounding error to the largest weight.
        """
        diff = 100.0 - weights_pct.sum()
        if abs(diff) > 0:
            max_idx = np.argmax(weights_pct)
            weights_pct[max_idx] += diff
        return weights_pct

    @staticmethod
    def _build_message(cr: float, is_consistent: bool, n: int) -> str:
        """Build a human-readable consistency message."""
        if n <= 2:
            return (
                "With 2 criteria, weights are directly derived "
                "from your single comparison. No consistency "
                "check is needed."
            )

        if cr == 0:
            return "Perfect consistency. Your judgments are flawless."

        if cr < 0.05:
            return (
                f"Excellent consistency (CR = {cr:.1%}). "
                f"Your judgments are highly reliable."
            )

        if cr < 0.10:
            return (
                f"Acceptable consistency (CR = {cr:.1%}). "
                f"Your judgments are sufficiently consistent "
                f"for decision-making."
            )

        return (
            f"Inconsistent judgments (CR = {cr:.1%} ≥ 10%). "
            f"Your pairwise comparisons contain contradictions. "
            f"For example, if you said A > B and B > C, but then "
            f"C > A, that's a cycle. Review your comparisons and "
            f"try to resolve the contradictions."
        )