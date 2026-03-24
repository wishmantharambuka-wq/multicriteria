/**
 * sensitivity.js — Phase D (Bulletproof version)
 */

const Sensitivity = (() => {
    const API = "http://localhost:8000/api/v1";
    let lastResult = null;

    function getStabilityColor(cls) {
        switch (cls) {
            case "Very Stable":   return "#2ed573";
            case "Stable":        return "#7bed9f";
            case "Moderate":      return "#ffa502";
            case "Volatile":      return "#ff6348";
            case "Very Volatile": return "#ff4757";
            case "Infeasible":    return "#2a2a3e";
            default:              return "#888888";
        }
    }

    function init() {
        // Attach trigger FIRST — no dependencies
        const triggerBtn = document.getElementById("sensitivity-trigger-btn");
        if (triggerBtn) {
            triggerBtn.addEventListener("click", () => {
                console.log("🎲 Button clicked");
                const panel = document.getElementById("sensitivity-panel");
                if (!panel) {
                    console.error("❌ sensitivity-panel not found");
                    alert("Sensitivity panel HTML is missing from index.html");
                    return;
                }

                const isHidden = panel.style.display === "none" || panel.style.display === "";

                if (isHidden) {
                    panel.style.display = "block";
                    triggerBtn.textContent = "🎲 Hide Sensitivity";
                    // Scroll sidebar to show panel
                    setTimeout(() => panel.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
                } else {
                    panel.style.display = "none";
                    triggerBtn.textContent = "🎲 Sensitivity Analysis";
                }
            });
            console.log("✅ Sensitivity trigger listener attached");
        } else {
            console.error("❌ sensitivity-trigger-btn not found");
        }

        // Attach run button
        const runBtn = document.getElementById("sensitivity-run-btn");
        if (runBtn) {
            runBtn.addEventListener("click", _runSensitivity);
            console.log("✅ Sensitivity run listener attached");
        } else {
            console.warn("⚠ sensitivity-run-btn not found yet (OK if panel hidden)");
        }

        // Attach close button
        const closeBtn = document.getElementById("sensitivity-close-btn");
        if (closeBtn) {
            closeBtn.addEventListener("click", _closeSensitivity);
        }

        // Slider display updates
        _attachSlider("sens-simulations", "sens-sim-display", (v) => v);
        _attachSlider("sens-perturbation", "sens-pert-display", (v) => `±${(v * 100).toFixed(0)}%`);
        _attachSlider("sens-topk", "sens-topk-display", (v) => v);
    }

    function _attachSlider(sliderId, displayId, formatter) {
        const slider = document.getElementById(sliderId);
        const display = document.getElementById(displayId);
        if (slider && display) {
            slider.addEventListener("input", (e) => {
                display.textContent = formatter(parseFloat(e.target.value));
            });
        }
    }

    function showTrigger() {
        const btn = document.getElementById("sensitivity-trigger-btn");
        if (btn) btn.style.display = "block";
    }

    function hideTrigger() {
        const btn = document.getElementById("sensitivity-trigger-btn");
        if (btn) btn.style.display = "none";
        _closeSensitivity();
    }

    async function _runSensitivity() {
        console.log("🎲 Running sensitivity...");

        const simEl = document.getElementById("sens-simulations");
        const pertEl = document.getElementById("sens-perturbation");
        const topkEl = document.getElementById("sens-topk");

        const nSim = simEl ? parseInt(simEl.value) : 1000;
        const pertPct = pertEl ? parseFloat(pertEl.value) : 0.15;
        const topK = topkEl ? parseInt(topkEl.value) : 5;

        const btn = document.getElementById("sensitivity-run-btn");
        if (btn) { btn.disabled = true; btn.textContent = "Running..."; }

        const loading = document.getElementById("map-loading");
        if (loading) loading.style.display = "flex";

        try {
            const res = await fetch(`${API}/sensitivity`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    n_simulations: nSim,
                    perturbation_pct: pertPct,
                    top_k: topK,
                }),
            });

            if (!res.ok) {
                const err = await res.json();
                alert(`Sensitivity failed: ${err.detail}`);
                return;
            }

            lastResult = await res.json();

            // Render on map
            if (MapEngine.renderSensitivity) {
                MapEngine.renderSensitivity(lastResult.result_geojson, {
                    getColor: (p) => getStabilityColor(p.stability_class),
                    getPopup: (p) => _buildPopup(p),
                    getLegendItems: () => ({
                        title: "Rank Stability",
                        classes: [
                            { label: "Very Stable", color: "#2ed573" },
                            { label: "Stable", color: "#7bed9f" },
                            { label: "Moderate", color: "#ffa502" },
                            { label: "Volatile", color: "#ff6348" },
                            { label: "Very Volatile", color: "#ff4757" },
                            { label: "Infeasible", color: "#2a2a3e" },
                        ],
                    }),
                });
            } else {
                // Fallback if renderSensitivity doesn't exist
                MapEngine.renderResult(lastResult.result_geojson);
            }

            _displayResults(lastResult);
            console.log("✅ Sensitivity complete");
        } catch (err) {
            console.error("Sensitivity error:", err);
            alert("Sensitivity failed. Check console for details.");
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = "🎲 Run Sensitivity Analysis"; }
            if (loading) loading.style.display = "none";
        }
    }

    function _buildPopup(props) {
        if (props.is_feasible === false) {
            return `<div style="font-family:Inter,sans-serif">
                <div style="font-size:1.5rem;font-weight:700;color:#ff4757">✗ INFEASIBLE</div>
            </div>`;
        }

        const stable = props.stability_class || "Unknown";
        const color = getStabilityColor(stable);
        const meanRank = props.rank_mean != null ? props.rank_mean.toFixed(1) : "—";
        const rankStd = props.rank_std != null ? props.rank_std.toFixed(1) : "—";
        const origScore = props.original_score != null ? (props.original_score * 100).toFixed(1) : "—";
        const origRank = props.original_rank || "—";
        const ciLow = props.rank_ci_lower || "—";
        const ciHigh = props.rank_ci_upper || "—";
        const probTopK = props.prob_top_k != null ? (props.prob_top_k * 100).toFixed(0) : "—";
        const topK = lastResult?.summary?.top_k || 5;

        let fid = "";
        for (const key of ["parcel_id", "id", "fid", "name"]) {
            if (props[key] != null) { fid = `<div style="font-size:0.7rem;color:#999">${key}: ${props[key]}</div>`; break; }
        }

        return `
            <div style="font-family:Inter,sans-serif;min-width:220px">
                ${fid}
                <div style="display:flex;align-items:center;gap:10px;margin:6px 0">
                    <div style="font-size:1.6rem;font-weight:700;color:${color}">#${meanRank}</div>
                    <div>
                        <div style="font-weight:600;color:${color}">${stable}</div>
                        <div style="font-size:0.7rem;color:#999">Mean rank ± ${rankStd}</div>
                    </div>
                </div>
                <table style="width:100%;font-size:0.75rem;border-collapse:collapse">
                    <tr style="border-bottom:1px solid #eee">
                        <td style="padding:3px 0;color:#888">Original</td>
                        <td style="text-align:right;font-weight:600">${origScore}% (#${origRank})</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee">
                        <td style="padding:3px 0;color:#888">95% CI</td>
                        <td style="text-align:right;font-weight:600">#${ciLow} – #${ciHigh}</td>
                    </tr>
                    <tr>
                        <td style="padding:3px 0;color:#888">Prob Top-${topK}</td>
                        <td style="text-align:right;font-weight:700;color:${
                            probTopK >= 80 ? "#2ed573" : probTopK >= 50 ? "#ffa502" : "#ff4757"
                        }">${probTopK}%</td>
                    </tr>
                </table>
            </div>`;
    }

    function _displayResults(result) {
        const container = document.getElementById("sensitivity-results");
        if (!container) return;
        container.style.display = "block";

        const s = result.summary;
        const tornado = result.tornado || [];
        const params = result.simulation_params;

        const assessColors = {
            "Highly Reliable": "#2ed573",
            "Moderately Reliable": "#7bed9f",
            "Somewhat Uncertain": "#ffa502",
            "Highly Uncertain": "#ff4757",
        };
        const assessColor = assessColors[s.overall_assessment] || "#888";

        // Stability bar
        const stabDist = s.stability_distribution || {};
        const total = s.n_feasible || 1;
        const stabClasses = [
            { key: "Very Stable", color: "#2ed573" },
            { key: "Stable", color: "#7bed9f" },
            { key: "Moderate", color: "#ffa502" },
            { key: "Volatile", color: "#ff6348" },
            { key: "Very Volatile", color: "#ff4757" },
        ];

        let stabBar = '<div class="sens-stab-bar">';
        let stabLeg = '<div class="sens-stab-legend">';
        stabClasses.forEach((c) => {
            const cnt = stabDist[c.key] || 0;
            const pct = (cnt / total * 100).toFixed(0);
            if (cnt > 0) {
                stabBar += `<div class="sens-stab-seg" style="width:${pct}%;background:${c.color}" title="${c.key}: ${cnt}"></div>`;
                stabLeg += `<span style="color:${c.color}">●</span> ${c.key}: <b>${cnt}</b>&emsp;`;
            }
        });
        stabBar += "</div>";
        stabLeg += "</div>";

        // Tornado
        let tornadoHTML = "";
        if (tornado.length > 0) {
            const maxSwing = Math.max(...tornado.map((t) => t.score_swing));
            tornadoHTML = '<div class="sens-section"><div class="sens-section-title">🌪️ Criterion Influence</div>';
            tornado.forEach((t) => {
                const barPct = maxSwing > 0 ? (t.score_swing / maxSwing * 100).toFixed(0) : 0;
                tornadoHTML += `
                    <div style="margin-bottom:8px">
                        <div style="display:flex;justify-content:space-between;font-size:0.8rem">
                            <b>${t.criterion_name}</b>
                            <span style="color:var(--text-secondary);font-size:0.7rem">
                                ${(t.weight_low*100).toFixed(0)}%–${(t.weight_high*100).toFixed(0)}%
                            </span>
                        </div>
                        <div style="background:var(--bg-dark);height:12px;border-radius:6px;overflow:hidden;margin:4px 0">
                            <div style="width:${barPct}%;height:100%;background:linear-gradient(90deg,#e17055,#d63031);border-radius:6px"></div>
                        </div>
                        <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--text-secondary)">
                            <span>${(t.mean_score_at_low*100).toFixed(1)}%</span>
                            <span style="color:#e17055;font-weight:600">Δ${(t.score_swing*100).toFixed(1)}%</span>
                            <span>${(t.mean_score_at_high*100).toFixed(1)}%</span>
                        </div>
                    </div>`;
            });
            tornadoHTML += "</div>";
        }

        // Top parcels
        let topHTML = "";
        const topP = s.top_parcels || [];
        if (topP.length > 0) {
            topHTML = `<div class="sens-section"><div class="sens-section-title">🏆 Top ${s.top_k} Stability</div>`;
            topP.forEach((p) => {
                const pc = p.prob_top_k >= 0.8 ? "#2ed573" : p.prob_top_k >= 0.5 ? "#ffa502" : "#ff4757";
                topHTML += `
                    <div style="display:flex;justify-content:space-between;align-items:center;
                                font-size:0.75rem;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05)">
                        <span style="color:var(--text-secondary)">${p.id}</span>
                        <span>#${p.mean_rank} ±${p.rank_std}</span>
                        <span>CI: ${p.ci[0]}–${p.ci[1]}</span>
                        <span style="color:${pc};font-weight:700">${(p.prob_top_k*100).toFixed(0)}%</span>
                    </div>`;
            });
            topHTML += "</div>";
        }

        container.innerHTML = `
            <div class="sens-assessment" style="border-color:${assessColor}">
                <div class="sens-assess-label">Overall Reliability</div>
                <div class="sens-assess-value" style="color:${assessColor}">${s.overall_assessment}</div>
                <div class="sens-assess-detail">
                    ${s.stable_pct}% stable across ${params.n_simulations.toLocaleString()} simulations
                </div>
            </div>
            <div class="stat-grid">
                <div class="stat-card"><div class="stat-value">${params.n_simulations.toLocaleString()}</div><div class="stat-label">Simulations</div></div>
                <div class="stat-card"><div class="stat-value">${s.n_feasible}</div><div class="stat-label">Parcels</div></div>
                <div class="stat-card"><div class="stat-value">${s.mean_rank_std}</div><div class="stat-label">Mean σ</div></div>
                <div class="stat-card"><div class="stat-value">${s.stable_pct}%</div><div class="stat-label">Stable</div></div>
            </div>
            ${stabBar}${stabLeg}
            ${tornadoHTML}
            ${topHTML}
            <button id="sensitivity-restore-btn" class="btn btn-secondary" style="margin-top:10px">
                🗺️ Restore Suitability Map
            </button>`;

        document.getElementById("sensitivity-restore-btn")
            .addEventListener("click", _closeSensitivity);

        container.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function _closeSensitivity() {
        if (MapEngine.clearSensitivity) MapEngine.clearSensitivity();
        const r = document.getElementById("sensitivity-results");
        if (r) r.style.display = "none";
    }

    return { init, showTrigger, hideTrigger };
})();