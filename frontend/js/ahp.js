/**
 * ahp.js — Analytic Hierarchy Process UI
 *
 * This module handles:
 *   - Generating pairwise comparison sliders for all factor pairs
 *   - Sending comparisons to the backend
 *   - Displaying derived weights and consistency check
 *   - Applying weights to the main UI sliders
 *
 * Communication with ui.js:
 *   - Reads:  UI.getFactorLayers()  → [{id, name}, ...]
 *   - Writes: UI.applyAHPWeights({layerId: pct, ...})
 */

const AHP = (() => {
    const API = "http://localhost:8000/api/v1";

    // Saaty scale: slider position → comparison value
    // Position range: -8 to +8 (17 steps)
    // Negative = criterion B is more important
    // Positive = criterion A is more important
    // Zero = equal

    function posToValue(pos) {
        if (pos >= 0) return pos + 1;        // 0→1, 1→2, ..., 8→9
        return 1.0 / (-pos + 1);             // -1→0.5, -2→0.333, ..., -8→0.111
    }

    function valueToPos(val) {
        if (val >= 1) return Math.round(val - 1);
        return Math.round(-(1.0 / val) + 1);
    }

    const INTENSITY_LABELS = {
        0: "Equal importance",
        1: "Slightly more",
        2: "Somewhat more",
        3: "Moderately more",
        4: "Moderate–strong",
        5: "Strongly more",
        6: "Strong–very strong",
        7: "Very strongly more",
        8: "Extremely more",
    };

    // ── State ──
    let factorLayers = [];       // [{id, name}, ...] — from UI module
    let comparisonValues = {};   // "row-col" → slider position
    let lastResult = null;

    // ══════════════════════════════════════
    //  PUBLIC: Rebuild when criteria change
    // ══════════════════════════════════════

    function rebuild() {
        factorLayers = UI.getFactorLayers();
        lastResult = null;

        const section = document.getElementById("ahp-section");
        const triggerBtn = document.getElementById("ahp-trigger-btn");
        const container = document.getElementById("ahp-comparisons");
        const resultsDiv = document.getElementById("ahp-results");

        // Need 2+ factors for AHP
        if (factorLayers.length < 2) {
            section.style.display = "none";
            triggerBtn.style.display = "none";
            return;
        }

        triggerBtn.style.display = "block";

        // If section is currently open, rebuild comparisons
        if (section.style.display !== "none") {
            _renderComparisons(container);
        }

        // Clear old results
        resultsDiv.style.display = "none";
        resultsDiv.innerHTML = "";
    }

    // ══════════════════════════════════════
    //  PUBLIC: Initialize event listeners
    // ══════════════════════════════════════

    function init() {
        // Trigger button toggles AHP section
        document.getElementById("ahp-trigger-btn")
            .addEventListener("click", _toggleSection);

        // Compute button
        document.getElementById("ahp-compute-btn")
            .addEventListener("click", _computeWeights);
    }

    // ══════════════════════════════════════
    //  Toggle AHP Section
    // ══════════════════════════════════════

    function _toggleSection() {
        const section = document.getElementById("ahp-section");
        const btn = document.getElementById("ahp-trigger-btn");

        if (section.style.display === "none") {
            section.style.display = "block";
            btn.textContent = "🧮 Hide AHP";
            btn.classList.add("active");

            factorLayers = UI.getFactorLayers();
            _renderComparisons(
                document.getElementById("ahp-comparisons")
            );
        } else {
            section.style.display = "none";
            btn.textContent = "🧮 Derive Weights (AHP)";
            btn.classList.remove("active");
        }
    }

    // ══════════════════════════════════════
    //  Render Pairwise Comparison Sliders
    // ══════════════════════════════════════

    function _renderComparisons(container) {
        container.innerHTML = "";
        const n = factorLayers.length;

        if (n < 2) {
            container.innerHTML =
                '<div class="ahp-empty">Need 2+ factor layers for AHP.</div>';
            return;
        }

        // Header
        const header = document.createElement("div");
        header.className = "ahp-instructions";
        header.innerHTML = `
            <p>For each pair, indicate which criterion is more
            important and by how much.</p>
            <p class="ahp-pair-count">
                ${n} criteria → ${n * (n - 1) / 2} comparisons
            </p>
        `;
        container.appendChild(header);

        // Generate one slider for each unique pair
        let pairNum = 1;
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const key = `${i}-${j}`;
                const nameA = factorLayers[i].name;
                const nameB = factorLayers[j].name;

                // Restore previous value or default to 0 (equal)
                const savedPos = comparisonValues[key] ?? 0;

                const card = document.createElement("div");
                card.className = "ahp-comparison-card";

                card.innerHTML = `
                    <div class="ahp-pair-label">
                        Comparison ${pairNum}
                    </div>

                    <div class="ahp-comparison-names">
                        <span class="ahp-name ahp-name-a">${nameA}</span>
                        <span class="ahp-vs">vs</span>
                        <span class="ahp-name ahp-name-b">${nameB}</span>
                    </div>

                    <div class="ahp-slider-container">
                        <div class="ahp-slider-labels">
                            <span class="ahp-end-label">◄ ${nameA}</span>
                            <span class="ahp-center-label">Equal</span>
                            <span class="ahp-end-label">${nameB} ►</span>
                        </div>
                        <input
                            type="range"
                            class="ahp-slider"
                            data-key="${key}"
                            min="-8"
                            max="8"
                            step="1"
                            value="${savedPos}"
                        />
                        <div class="ahp-value-display"
                             id="ahp-display-${key}">
                            ${_getDisplayText(savedPos, nameA, nameB)}
                        </div>
                    </div>
                `;

                // Slider event
                const slider = card.querySelector(".ahp-slider");
                slider.addEventListener("input", (e) => {
                    const pos = parseInt(e.target.value);
                    comparisonValues[key] = pos;

                    document.getElementById(`ahp-display-${key}`)
                        .innerHTML = _getDisplayText(pos, nameA, nameB);

                    // Clear old results when comparisons change
                    const res = document.getElementById("ahp-results");
                    if (res.style.display !== "none") {
                        res.style.display = "none";
                    }
                });

                comparisonValues[key] = savedPos;
                container.appendChild(card);
                pairNum++;
            }
        }
    }

    function _getDisplayText(pos, nameA, nameB) {
        const absPos = Math.abs(pos);
        const label = INTENSITY_LABELS[absPos] || "";

        if (pos === 0) {
            return `<span class="ahp-equal">Equal importance</span>`;
        }

        const value = posToValue(pos);
        const displayVal = pos > 0
            ? value.toFixed(0)
            : `1/${(1 / value).toFixed(0)}`;

        if (pos > 0) {
            return `<span class="ahp-favors-a">
                <b>${nameA}</b> is ${label.toLowerCase()}
                <span class="ahp-scale-val">(${displayVal}×)</span>
            </span>`;
        } else {
            return `<span class="ahp-favors-b">
                <b>${nameB}</b> is ${label.toLowerCase()}
                <span class="ahp-scale-val">(${displayVal})</span>
            </span>`;
        }
    }

    // ══════════════════════════════════════
    //  Compute Weights (API Call)
    // ══════════════════════════════════════

    async function _computeWeights() {
        const n = factorLayers.length;
        if (n < 2) return;

        // Build comparisons array
        const comparisons = [];
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const key = `${i}-${j}`;
                const pos = comparisonValues[key] ?? 0;
                comparisons.push({
                    row: i,
                    col: j,
                    value: posToValue(pos),
                });
            }
        }

        const criteriaNames = factorLayers.map((l) => l.name);

        // Show loading
        const btn = document.getElementById("ahp-compute-btn");
        btn.disabled = true;
        btn.textContent = "Computing...";

        try {
            const res = await fetch(`${API}/ahp/compute`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    criteria_names: criteriaNames,
                    comparisons: comparisons,
                }),
            });

            if (!res.ok) {
                const err = await res.json();
                alert(`AHP failed: ${err.detail}`);
                return;
            }

            lastResult = await res.json();
            _displayResults(lastResult);
        } catch (err) {
            console.error("AHP error:", err);
            alert("AHP computation failed.");
        } finally {
            btn.disabled = false;
            btn.textContent = "🧮 Compute Weights";
        }
    }

    // ══════════════════════════════════════
    //  Display Results
    // ══════════════════════════════════════

    function _displayResults(result) {
        const container = document.getElementById("ahp-results");
        container.style.display = "block";

        const cr = result.consistency_ratio;
        const isConsistent = result.is_consistent;

        // Consistency badge
        let consistencyHTML;
        if (result.n_criteria <= 2) {
            consistencyHTML = `
                <div class="ahp-consistency ahp-consistent">
                    <span class="ahp-cr-badge">✅ N/A</span>
                    <span class="ahp-cr-text">
                        Only ${result.n_criteria} criteria — 
                        consistency check not applicable.
                    </span>
                </div>
            `;
        } else if (isConsistent) {
            let quality;
            if (cr === 0) quality = "Perfect";
            else if (cr < 0.05) quality = "Excellent";
            else quality = "Acceptable";

            consistencyHTML = `
                <div class="ahp-consistency ahp-consistent">
                    <span class="ahp-cr-badge">
                        ✅ CR = ${(cr * 100).toFixed(1)}%
                    </span>
                    <span class="ahp-cr-text">
                        ${quality} consistency.
                        ${result.message}
                    </span>
                </div>
            `;
        } else {
            consistencyHTML = `
                <div class="ahp-consistency ahp-inconsistent">
                    <span class="ahp-cr-badge">
                        ⚠️ CR = ${(cr * 100).toFixed(1)}%
                    </span>
                    <span class="ahp-cr-text">
                        ${result.message}
                    </span>
                </div>
            `;
        }

        // Weight bars
        let weightsHTML = '<div class="ahp-weights-list">';
        result.weights.forEach((w) => {
            const pct = w.weight_pct;
            const barColor = pct >= 30 ? "var(--accent)"
                : pct >= 15 ? "#ffa502" : "var(--text-secondary)";
            weightsHTML += `
                <div class="ahp-weight-row">
                    <div class="ahp-weight-name">${w.name}</div>
                    <div class="ahp-weight-bar-container">
                        <div class="ahp-weight-bar"
                             style="width:${pct}%;
                                    background:${barColor}">
                        </div>
                    </div>
                    <div class="ahp-weight-pct">${pct}%</div>
                </div>
            `;
        });
        weightsHTML += "</div>";

        // Matrix display
        let matrixHTML = '<div class="ahp-matrix-section">';
        matrixHTML += '<div class="ahp-matrix-title">Comparison Matrix</div>';
        matrixHTML += '<div class="ahp-matrix-scroll"><table class="ahp-matrix">';

        // Header row
        matrixHTML += "<tr><th></th>";
        result.weights.forEach((w) => {
            const short = w.name.length > 6
                ? w.name.substring(0, 6) + "…" : w.name;
            matrixHTML += `<th>${short}</th>`;
        });
        matrixHTML += "</tr>";

        // Data rows
        result.matrix.forEach((row, i) => {
            const short = result.weights[i].name.length > 6
                ? result.weights[i].name.substring(0, 6) + "…"
                : result.weights[i].name;
            matrixHTML += `<tr><th>${short}</th>`;
            row.forEach((val, j) => {
                let display;
                if (i === j) {
                    display = "1";
                } else if (val >= 1) {
                    display = val.toFixed(val % 1 === 0 ? 0 : 2);
                } else {
                    display = `1/${(1/val).toFixed(0)}`;
                }
                const cellClass = i === j ? "ahp-diag" :
                    val > 1 ? "ahp-above" : val < 1 ? "ahp-below" : "";
                matrixHTML += `<td class="${cellClass}">${display}</td>`;
            });
            matrixHTML += "</tr>";
        });
        matrixHTML += "</table></div></div>";

        // Technical details
        const techHTML = `
            <div class="ahp-tech-details">
                <span>λ_max = ${result.lambda_max.toFixed(4)}</span>
                <span>CI = ${result.consistency_index.toFixed(4)}</span>
                <span>Method: ${result.method}</span>
            </div>
        `;

        // Apply button
        const applyHTML = `
            <button id="ahp-apply-btn" class="btn btn-primary ahp-apply-btn"
                    ${!isConsistent && result.n_criteria > 2 ? "" : ""}>
                ✅ Apply Weights to Sliders
            </button>
            ${!isConsistent && result.n_criteria > 2 ? `
                <div class="ahp-apply-warning">
                    ⚠️ Weights may be unreliable due to
                    inconsistent judgments. Consider revising.
                </div>
            ` : ""}
        `;

        container.innerHTML = `
            <div class="ahp-results-header">Derived Weights</div>
            ${consistencyHTML}
            ${weightsHTML}
            ${matrixHTML}
            ${techHTML}
            ${applyHTML}
        `;

        // Wire up apply button
        document.getElementById("ahp-apply-btn")
            .addEventListener("click", _applyWeights);

        // Scroll to results
        container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // ══════════════════════════════════════
    //  Apply Weights to UI Sliders
    // ══════════════════════════════════════

    function _applyWeights() {
        if (!lastResult) return;

        const weightMap = {};
        lastResult.weights.forEach((w, i) => {
            if (i < factorLayers.length) {
                weightMap[factorLayers[i].id] = w.weight_pct;
            }
        });

        UI.applyAHPWeights(weightMap);

        // Visual feedback
        const btn = document.getElementById("ahp-apply-btn");
        btn.textContent = "✅ Applied!";
        btn.disabled = true;
        setTimeout(() => {
            btn.textContent = "✅ Apply Weights to Sliders";
            btn.disabled = false;
        }, 2000);

        console.log("🧮 AHP weights applied to sliders");
    }

    // ── Public API ──
    return { init, rebuild };
})();