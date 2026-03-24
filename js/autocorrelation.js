/**
 * autocorrelation.js — Phase F: Spatial Autocorrelation
 */

const Autocorrelation = (() => {
    const API = "http://localhost:8000/api/v1";
    let lastResult = null;

    const LISA_COLORS = {
        "High-High":        "#e74c3c",
        "Low-Low":          "#3498db",
        "High-Low":         "#e67e22",
        "Low-High":         "#9b59b6",
        "Not Significant":  "#95a5a6",
        "Infeasible":       "#2a2a3e",
    };

    function init() {
        const triggerBtn = document.getElementById("autocorr-trigger-btn");
        if (triggerBtn) {
            triggerBtn.addEventListener("click", _togglePanel);
            console.log("✅ Autocorrelation trigger attached");
        }

        const runBtn = document.getElementById("autocorr-run-btn");
        if (runBtn) runBtn.addEventListener("click", _runAnalysis);

        const closeBtn = document.getElementById("autocorr-close-btn");
        if (closeBtn) closeBtn.addEventListener("click", _close);

        _attachSlider("autocorr-k", "autocorr-k-display", (v) => v);
        _attachSlider("autocorr-perms", "autocorr-perms-display", (v) => v);
        _attachSlider("autocorr-sig", "autocorr-sig-display", (v) => `${(v * 100).toFixed(0)}%`);
    }

    function _attachSlider(id, displayId, fmt) {
        const s = document.getElementById(id);
        const d = document.getElementById(displayId);
        if (s && d) s.addEventListener("input", (e) => { d.textContent = fmt(parseFloat(e.target.value)); });
    }

    function showTrigger() {
        const btn = document.getElementById("autocorr-trigger-btn");
        if (btn) btn.style.display = "block";
    }

    function hideTrigger() {
        const btn = document.getElementById("autocorr-trigger-btn");
        if (btn) btn.style.display = "none";
        _close();
    }

    function _togglePanel() {
        const panel = document.getElementById("autocorr-panel");
        const btn = document.getElementById("autocorr-trigger-btn");
        if (!panel) return;

        const hidden = panel.style.display === "none" || panel.style.display === "";
        if (hidden) {
            panel.style.display = "block";
            btn.textContent = "📈 Hide Autocorrelation";
            btn.classList.add("active");
            setTimeout(() => panel.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
        } else {
            panel.style.display = "none";
            btn.textContent = "📈 Spatial Autocorrelation";
            btn.classList.remove("active");
        }
    }

    async function _runAnalysis() {
        const kEl = document.getElementById("autocorr-k");
        const permEl = document.getElementById("autocorr-perms");
        const sigEl = document.getElementById("autocorr-sig");

        const k = kEl ? parseInt(kEl.value) : 5;
        const perms = permEl ? parseInt(permEl.value) : 999;
        const sig = sigEl ? parseFloat(sigEl.value) : 0.05;

        const btn = document.getElementById("autocorr-run-btn");
        if (btn) { btn.disabled = true; btn.textContent = "Computing..."; }

        const loading = document.getElementById("map-loading");
        if (loading) loading.style.display = "flex";

        try {
            const res = await fetch(`${API}/autocorrelation`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    k_neighbors: k,
                    n_permutations: perms,
                    significance_level: sig,
                }),
            });

            if (!res.ok) {
                const err = await res.json();
                alert(`Autocorrelation failed: ${err.detail}`);
                return;
            }

            lastResult = await res.json();
            _renderOnMap(lastResult.result_geojson);
            _displayResults(lastResult);
            console.log("✅ Autocorrelation complete");
        } catch (err) {
            console.error(err);
            alert("Autocorrelation failed.");
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = "📈 Run Autocorrelation"; }
            if (loading) loading.style.display = "none";
        }
    }

    function _renderOnMap(geojsonData) {
        if (MapEngine.renderSensitivity) {
            MapEngine.renderSensitivity(geojsonData, {
                getColor: (p) => LISA_COLORS[p.lisa_class] || "#888",
                getPopup: (p) => _buildPopup(p),
                getLegendItems: () => ({
                    title: "LISA Clusters",
                    classes: [
                        { label: "High-High", color: "#e74c3c" },
                        { label: "Low-Low", color: "#3498db" },
                        { label: "High-Low", color: "#e67e22" },
                        { label: "Low-High", color: "#9b59b6" },
                        { label: "Not Significant", color: "#95a5a6" },
                        { label: "Infeasible", color: "#2a2a3e" },
                    ],
                }),
            });
        } else {
            MapEngine.renderResult(geojsonData);
        }
    }

    function _buildPopup(props) {
        if (props.is_feasible === false) {
            return `<div style="font-family:Inter,sans-serif"><div style="font-size:1.5rem;font-weight:700;color:#ff4757">✗ INFEASIBLE</div></div>`;
        }

        const cls = props.lisa_class || "Unknown";
        const color = LISA_COLORS[cls] || "#888";
        const localI = props.local_morans_i != null ? props.local_morans_i.toFixed(4) : "—";
        const pVal = props.lisa_p_value != null ? props.lisa_p_value.toFixed(4) : "—";
        const sig = props.lisa_significant ? "✅ Yes" : "❌ No";
        const zScore = props.z_score != null ? props.z_score.toFixed(2) : "—";
        const lag = props.spatial_lag != null ? props.spatial_lag.toFixed(2) : "—";
        const score = props.suitability_score != null ? (props.suitability_score * 100).toFixed(1) : "—";

        const descriptions = {
            "High-High": "🔴 Hot Spot — High score surrounded by high scores. Prime development zone.",
            "Low-Low": "🔵 Cold Spot — Low score surrounded by low scores. Consistently unsuitable area.",
            "High-Low": "🟠 Outlier — High score surrounded by low scores. Isolated opportunity.",
            "Low-High": "🟣 Outlier — Low score surrounded by high scores. Gap in a good area.",
            "Not Significant": "⚪ No significant spatial pattern at this location.",
        };

        let fid = "";
        for (const key of ["parcel_id", "cell_id", "id", "fid", "name"]) {
            if (props[key] != null) { fid = `<div style="font-size:0.7rem;color:#999">${key}: ${props[key]}</div>`; break; }
        }

        return `
            <div style="font-family:Inter,sans-serif;min-width:240px">
                ${fid}
                <div style="display:flex;align-items:center;gap:10px;margin:6px 0">
                    <div style="width:20px;height:20px;border-radius:4px;background:${color}"></div>
                    <div>
                        <div style="font-weight:700;font-size:0.9rem;color:${color}">${cls}</div>
                        <div style="font-size:0.7rem;color:#999">Suitability: ${score}%</div>
                    </div>
                </div>
                <div style="font-size:0.75rem;color:#666;margin:6px 0;line-height:1.4;padding:6px 8px;background:#f5f5f5;border-radius:4px">
                    ${descriptions[cls] || ""}
                </div>
                <table style="width:100%;font-size:0.75rem;border-collapse:collapse;margin-top:6px">
                    <tr style="border-bottom:1px solid #eee">
                        <td style="padding:3px 0;color:#888">Local Moran's I</td>
                        <td style="text-align:right;font-weight:600">${localI}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee">
                        <td style="padding:3px 0;color:#888">p-value</td>
                        <td style="text-align:right;font-weight:600">${pVal}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee">
                        <td style="padding:3px 0;color:#888">Significant</td>
                        <td style="text-align:right;font-weight:600">${sig}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #eee">
                        <td style="padding:3px 0;color:#888">Z-score</td>
                        <td style="text-align:right;font-weight:600">${zScore}</td>
                    </tr>
                    <tr>
                        <td style="padding:3px 0;color:#888">Spatial Lag</td>
                        <td style="text-align:right;font-weight:600">${lag}</td>
                    </tr>
                </table>
            </div>`;
    }

    function _displayResults(result) {
        const container = document.getElementById("autocorr-results");
        if (!container) return;
        container.style.display = "block";

        const s = result.summary;
        const counts = s.lisa_class_counts || {};

        // Pattern badge
        const patternColors = { Clustered: "#e74c3c", Dispersed: "#3498db", Random: "#95a5a6" };
        const patternColor = patternColors[s.pattern] || "#888";
        const patternIcons = { Clustered: "🔴", Dispersed: "🔵", Random: "⚪" };

        // LISA distribution bar
        const total = s.n_features || 1;
        const lisaClasses = [
            { key: "High-High", color: "#e74c3c", label: "HH" },
            { key: "Low-Low", color: "#3498db", label: "LL" },
            { key: "High-Low", color: "#e67e22", label: "HL" },
            { key: "Low-High", color: "#9b59b6", label: "LH" },
            { key: "Not Significant", color: "#95a5a6", label: "NS" },
        ];

        let lisaBar = '<div class="sens-stab-bar">';
        let lisaLeg = '<div class="sens-stab-legend">';
        lisaClasses.forEach((c) => {
            const cnt = counts[c.key] || 0;
            const pct = (cnt / total * 100).toFixed(0);
            if (cnt > 0) {
                lisaBar += `<div class="sens-stab-seg" style="width:${pct}%;background:${c.color}" title="${c.key}: ${cnt}"></div>`;
                lisaLeg += `<span style="color:${c.color}">●</span> ${c.label}: <b>${cnt}</b>&emsp;`;
            }
        });
        lisaBar += "</div>";
        lisaLeg += "</div>";

        // Moran scatter plot (simple ASCII-style with HTML)
        let scatterHTML = "";
        if (s.moran_scatter) {
            const zVals = s.moran_scatter.z_values;
            const lagVals = s.moran_scatter.spatial_lag;
            const classes = s.moran_scatter.classes;

            scatterHTML = `
                <div class="sens-section">
                    <div class="sens-section-title">📊 Moran Scatter Plot</div>
                    <div class="moran-scatter-container">
                        <svg viewBox="-3.5 -3.5 7 7" width="100%" height="200"
                             style="background:var(--bg-dark);border-radius:6px">
                            <!-- Axes -->
                            <line x1="-3.2" y1="0" x2="3.2" y2="0"
                                  stroke="#555" stroke-width="0.03"/>
                            <line x1="0" y1="-3.2" x2="0" y2="3.2"
                                  stroke="#555" stroke-width="0.03"/>

                            <!-- Quadrant labels -->
                            <text x="1.5" y="-2.5" fill="#e74c3c" font-size="0.3"
                                  text-anchor="middle">HH</text>
                            <text x="-1.5" y="2.8" fill="#3498db" font-size="0.3"
                                  text-anchor="middle">LL</text>
                            <text x="1.5" y="2.8" fill="#e67e22" font-size="0.3"
                                  text-anchor="middle">HL</text>
                            <text x="-1.5" y="-2.5" fill="#9b59b6" font-size="0.3"
                                  text-anchor="middle">LH</text>

                            <!-- Axis labels -->
                            <text x="2.8" y="0.4" fill="#888" font-size="0.25"
                                  text-anchor="end">z</text>
                            <text x="0.4" y="-2.8" fill="#888" font-size="0.25">Wz</text>

                            <!-- Regression line (slope = Moran's I) -->
                            <line x1="-3" y1="${(-3 * s.global_morans_i).toFixed(2)}"
                                  x2="3" y2="${(3 * s.global_morans_i).toFixed(2)}"
                                  stroke="#ffa502" stroke-width="0.04"
                                  stroke-dasharray="0.1,0.1"/>

                            <!-- Points -->
                            ${zVals.map((z, i) => {
                                const lag = lagVals[i];
                                const cls = classes[i];
                                const color = LISA_COLORS[cls] || "#888";
                                const cx = Math.max(-3, Math.min(3, z));
                                const cy = Math.max(-3, Math.min(3, -lag));
                                return `<circle cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}"
                                         r="0.12" fill="${color}" opacity="0.8"/>`;
                            }).join("")}
                        </svg>
                        <div style="font-size:0.65rem;color:var(--text-secondary);text-align:center;margin-top:4px">
                            Slope = Moran's I (${s.global_morans_i.toFixed(3)})
                            &nbsp;|&nbsp; Yellow dashed = regression line
                        </div>
                    </div>
                </div>`;
        }

        container.innerHTML = `
            <!-- Global Moran's I Result -->
            <div class="sens-assessment" style="border-color:${patternColor}">
                <div class="sens-assess-label">Global Moran's I</div>
                <div style="display:flex;justify-content:center;align-items:center;gap:12px;margin:6px 0">
                    <div style="font-size:1.8rem;font-weight:700;color:${patternColor}">
                        ${s.global_morans_i.toFixed(3)}
                    </div>
                    <div style="text-align:left">
                        <div style="font-size:1rem;font-weight:700;color:${patternColor}">
                            ${patternIcons[s.pattern] || ""} ${s.pattern}
                        </div>
                        <div style="font-size:0.7rem;color:var(--text-secondary)">
                            p = ${s.p_value.toFixed(4)}
                            ${s.significant ? "✅ Significant" : "❌ Not significant"}
                        </div>
                    </div>
                </div>
                <div class="sens-assess-detail">${s.interpretation}</div>
            </div>

            <!-- Stats -->
            <div class="stat-grid">
                <div class="stat-card">
                    <div class="stat-value">${s.global_morans_i.toFixed(3)}</div>
                    <div class="stat-label">Moran's I</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${s.z_score.toFixed(2)}</div>
                    <div class="stat-label">Z-score</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${s.p_value.toFixed(4)}</div>
                    <div class="stat-label">p-value</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${s.n_features}</div>
                    <div class="stat-label">Features</div>
                </div>
            </div>

            <!-- LISA Distribution -->
            <div class="sens-section">
                <div class="sens-section-title">🗺️ LISA Cluster Types</div>
                ${lisaBar}
                ${lisaLeg}
            </div>

            <!-- Moran Scatter Plot -->
            ${scatterHTML}

            <button id="autocorr-restore-btn" class="btn btn-secondary" style="margin-top:10px">
                🗺️ Restore Suitability Map
            </button>`;

        document.getElementById("autocorr-restore-btn")
            .addEventListener("click", _close);

        container.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function _close() {
        if (MapEngine.clearSensitivity) MapEngine.clearSensitivity();
        const r = document.getElementById("autocorr-results");
        if (r) r.style.display = "none";
    }

    return { init, showTrigger, hideTrigger };
})();