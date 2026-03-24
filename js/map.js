/**
 * map.js — Phase B: Diff Map Rendering
 *
 * Additions:
 *   - renderDiff() for scenario comparison visualization
 *   - Diverging blue–gray–red color scheme for deltas
 *   - Comparison popup with side-by-side scores
 */

const MapEngine = (() => {
    let map = null;
    const layerGroups = {};
    let resultLayer = null;
    let diffLayer = null;
    let legendControl = null;

    // ── Score colors (same as before) ──
    function getScoreColor(score) {
        if (score >= 0.8) return "#2ed573";
        if (score >= 0.6) return "#7bed9f";
        if (score >= 0.4) return "#ffa502";
        if (score >= 0.2) return "#ff6348";
        return "#ff4757";
    }

    // ── Diff colors (diverging blue–red) ──
    function getDiffColor(delta) {
        if (delta >= 0.3)  return "#1565c0";   // strong blue (A much better)
        if (delta >= 0.15) return "#42a5f5";   // blue
        if (delta >= 0.05) return "#90caf9";   // light blue
        if (delta > -0.05) return "#9e9e9e";   // gray (similar)
        if (delta > -0.15) return "#ef9a9a";   // light red
        if (delta > -0.3)  return "#e53935";   // red
        return "#b71c1c";                       // strong red (B much better)
    }

    function init() {
        map = L.map("map", {
            center: [35.78, -78.64],
            zoom: 12,
        });
        L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
            {
                attribution: "&copy; OpenStreetMap &copy; CARTO",
                subdomains: "abcd",
                maxZoom: 19,
            }
        ).addTo(map);
        console.log("🗺️ Map initialized");
    }

    function addLayer(layerId, geojsonData, color = "#e94560") {
        if (layerGroups[layerId]) map.removeLayer(layerGroups[layerId]);
        const layer = L.geoJSON(geojsonData, {
            style: () => ({
                color, weight: 2, opacity: 0.8,
                fillColor: color, fillOpacity: 0.15,
            }),
            pointToLayer: (f, ll) => L.circleMarker(ll, {
                radius: 6, fillColor: color, color: "#fff",
                weight: 1, opacity: 1, fillOpacity: 0.8,
            }),
            onEachFeature: (f, l) => {
                if (f.properties) {
                    const rows = Object.entries(f.properties)
                        .map(([k, v]) =>
                            `<tr><td style="padding:2px 8px 2px 0;color:#999">${k}</td>
                             <td style="padding:2px 0">${v}</td></tr>`)
                        .join("");
                    l.bindPopup(
                        `<div style="font-family:Inter,sans-serif;font-size:0.8rem">
                         <table>${rows}</table></div>`
                    );
                }
            },
        }).addTo(map);
        layerGroups[layerId] = layer;
        const b = layer.getBounds();
        if (b.isValid()) map.fitBounds(b, { padding: [50, 50] });
    }

    function removeLayer(layerId) {
        if (layerGroups[layerId]) {
            map.removeLayer(layerGroups[layerId]);
            delete layerGroups[layerId];
        }
    }

    // ── Render suitability result (Phase A, unchanged) ──

    function renderResult(geojsonData) {
        clearDiff();
        if (resultLayer) map.removeLayer(resultLayer);

        resultLayer = L.geoJSON(geojsonData, {
            style: (feature) => {
                const p = feature.properties;
                const feasible = p.is_feasible !== false;
                const score = p.suitability_score || 0;
                if (!feasible) {
                    return {
                        fillColor: "#2a2a3e", weight: 2,
                        opacity: 0.9, color: "#ff4757",
                        fillOpacity: 0.6, dashArray: "4 4",
                    };
                }
                return {
                    fillColor: getScoreColor(score), weight: 2,
                    opacity: 0.9, color: "#ffffff", fillOpacity: 0.75,
                };
            },
            onEachFeature: (feature, layer) => {
                layer.bindPopup(() => _buildResultPopup(feature.properties));
            },
        }).addTo(map);

        const b = resultLayer.getBounds();
        if (b.isValid()) map.fitBounds(b, { padding: [50, 50] });
        _addResultLegend(geojsonData);
    }

    // ── Render diff layer (NEW in Phase B) ──

    function renderDiff(diffGeojson, nameA, nameB) {
        clearResult();
        clearDiff();

        diffLayer = L.geoJSON(diffGeojson, {
            style: (feature) => {
                const p = feature.properties;
                const delta = p.score_delta || 0;
                return {
                    fillColor: getDiffColor(delta),
                    weight: 2,
                    opacity: 0.9,
                    color: "#ffffff",
                    fillOpacity: 0.75,
                };
            },
            onEachFeature: (feature, layer) => {
                layer.bindPopup(() =>
                    _buildDiffPopup(feature.properties, nameA, nameB)
                );
            },
        }).addTo(map);

        const b = diffLayer.getBounds();
        if (b.isValid()) map.fitBounds(b, { padding: [50, 50] });
        _addDiffLegend(diffGeojson, nameA, nameB);
        console.log("⚖️ Diff layer rendered");
    }

    // ── Diff popup ──

    function _buildDiffPopup(props, nameA, nameB) {
        const delta = props.score_delta || 0;
        const absDelta = Math.abs(delta);
        const pctA = (props.score_a * 100).toFixed(1);
        const pctB = (props.score_b * 100).toFixed(1);
        const pctDelta = (delta * 100).toFixed(1);
        const diffColor = getDiffColor(delta);
        const winner = props.winner;
        const fid = _getDisplayId(props);

        let directionText, directionIcon;
        if (winner === "A") {
            directionText = `${nameA} scores higher`;
            directionIcon = "🔵";
        } else if (winner === "B") {
            directionText = `${nameB} scores higher`;
            directionIcon = "🔴";
        } else {
            directionText = "Scores are similar";
            directionIcon = "⚪";
        }

        // Rank change
        const rankA = props.rank_a || "—";
        const rankB = props.rank_b || "—";
        const rankD = props.rank_delta || 0;
        let rankText = "";
        if (rankD > 0) {
            rankText = `<span style="color:#42a5f5">↑${rankD} in ${nameA}</span>`;
        } else if (rankD < 0) {
            rankText = `<span style="color:#e53935">↓${Math.abs(rankD)} in ${nameA}</span>`;
        } else {
            rankText = `<span style="color:#9e9e9e">Same rank</span>`;
        }

        // Feasibility changes
        let feasHTML = "";
        if (props.feasible_a !== props.feasible_b) {
            if (props.feasible_a && !props.feasible_b) {
                feasHTML = `<div style="background:#ff475720;border-radius:4px;
                    padding:4px 8px;margin-top:6px;font-size:0.7rem;color:#ff6b6b">
                    ⚠️ Became <b>infeasible</b> in ${nameB}</div>`;
            } else {
                feasHTML = `<div style="background:#2ed57320;border-radius:4px;
                    padding:4px 8px;margin-top:6px;font-size:0.7rem;color:#2ed573">
                    ✅ Became <b>feasible</b> in ${nameB}</div>`;
            }
        }

        // Other properties
        const skipKeys = new Set([
            "score_a", "score_b", "score_delta", "abs_score_delta",
            "rank_a", "rank_b", "rank_delta", "class_a", "class_b",
            "feasible_a", "feasible_b", "winner", "change_magnitude",
        ]);
        const others = Object.entries(props)
            .filter(([k]) => !skipKeys.has(k));
        let othersHTML = "";
        if (others.length > 0) {
            othersHTML = `<div style="margin-top:8px;border-top:1px solid #eee;
                padding-top:6px;font-size:0.7rem;color:#777">
                ${others.map(([k,v]) => `<b>${k}:</b> ${v}`).join(" · ")}
            </div>`;
        }

        return `
            <div style="font-family:Inter,sans-serif;min-width:260px">
                ${fid !== "unknown" ? `<div style="font-size:0.7rem;color:#999;margin-bottom:4px">${fid}</div>` : ""}

                <div style="text-align:center;margin-bottom:8px">
                    <div style="font-size:1.8rem;font-weight:700;color:${diffColor}">
                        ${delta >= 0 ? "+" : ""}${pctDelta}%
                    </div>
                    <div style="font-size:0.75rem;color:#666">
                        ${directionIcon} ${directionText}
                    </div>
                </div>

                <table style="width:100%;font-size:0.8rem;border-collapse:collapse">
                    <thead>
                        <tr style="border-bottom:2px solid #eee">
                            <th style="text-align:left;padding:4px 0"></th>
                            <th style="text-align:center;padding:4px 8px;
                                color:#42a5f5;font-size:0.7rem">${nameA}</th>
                            <th style="text-align:center;padding:4px 8px;
                                color:#e53935;font-size:0.7rem">${nameB}</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom:1px solid #f0f0f0">
                            <td style="padding:4px 0;color:#888">Score</td>
                            <td style="text-align:center;font-weight:700;
                                color:${getScoreColor(props.score_a)}">${pctA}%</td>
                            <td style="text-align:center;font-weight:700;
                                color:${getScoreColor(props.score_b)}">${pctB}%</td>
                        </tr>
                        <tr style="border-bottom:1px solid #f0f0f0">
                            <td style="padding:4px 0;color:#888">Class</td>
                            <td style="text-align:center">${props.class_a}</td>
                            <td style="text-align:center">${props.class_b}</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 0;color:#888">Rank</td>
                            <td style="text-align:center">#${rankA}</td>
                            <td style="text-align:center">#${rankB}</td>
                        </tr>
                    </tbody>
                </table>

                <div style="text-align:center;margin-top:6px;font-size:0.75rem">
                    ${rankText}
                </div>
                ${feasHTML}
                ${othersHTML}
            </div>
        `;
    }

    function _getDisplayId(props) {
        const fields = ["parcel_id", "id", "fid", "name", "NAME"];
        for (const f of fields) {
            if (props[f] !== undefined) return `${f}: ${props[f]}`;
        }
        return "unknown";
    }

    // ── Result popup (from Phase A, unchanged) ──

    function _buildResultPopup(props) {
        const feasible = props.is_feasible !== false;
        const score = props.suitability_score || 0;
        const pct = (score * 100).toFixed(1);
        const cls = props.suitability_class || "N/A";
        const rank = props.rank || "—";

        const constraintCols = Object.entries(props)
            .filter(([k]) => k.startsWith("constraint_"));
        let constraintHTML = "";
        if (constraintCols.length > 0) {
            constraintHTML = '<div style="margin-top:10px;border-top:1px solid #eee;padding-top:8px"><div style="font-weight:600;font-size:0.75rem;color:#666;margin-bottom:4px">Constraints</div>';
            constraintCols.forEach(([k, v]) => {
                const name = k.replace("constraint_", "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                const passed = v === "PASS";
                constraintHTML += `<div style="display:flex;justify-content:space-between;font-size:0.75rem;margin-bottom:2px"><span>${name}</span><span style="font-weight:700;color:${passed ? "#2ed573" : "#ff4757"}">${passed ? "✅ PASS" : "❌ FAIL"}</span></div>`;
            });
            constraintHTML += "</div>";
        }

        let failHTML = "";
        if (!feasible && props.failed_constraints) {
            failHTML = `<div style="background:#ff475720;border:1px solid #ff475750;border-radius:4px;padding:6px 8px;margin-top:8px;font-size:0.75rem;color:#ff6b6b"><b>Eliminated by:</b> ${props.failed_constraints}</div>`;
        }

        let factorHint = "";
        if (!feasible && props.factor_score !== undefined) {
            factorHint = `<div style="font-size:0.7rem;color:#888;margin-top:6px;font-style:italic">Factor score would have been: ${(props.factor_score*100).toFixed(1)}%</div>`;
        }

        const scoreCols = Object.entries(props).filter(([k]) => k.startsWith("score_")).sort((a, b) => b[1] - a[1]);
        let breakdownHTML = "";
        if (scoreCols.length > 0 && feasible) {
            breakdownHTML = '<div style="margin-top:10px;border-top:1px solid #eee;padding-top:8px"><div style="font-weight:600;font-size:0.75rem;color:#666;margin-bottom:6px">Score Breakdown</div>';
            scoreCols.forEach(([k, v]) => {
                const label = k.replace("score_", "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                const bp = (v * 100).toFixed(0);
                breakdownHTML += `<div style="margin-bottom:4px"><div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#555"><span>${label}</span><span style="font-weight:600">${bp}%</span></div><div style="background:#eee;height:6px;border-radius:3px;overflow:hidden"><div style="width:${bp}%;height:100%;background:${getScoreColor(v)};border-radius:3px"></div></div></div>`;
            });
            breakdownHTML += "</div>";
        }

        const skipKeys = new Set(["suitability_score", "suitability_class", "rank", "is_feasible", "failed_constraints", "factor_score", ...scoreCols.map(([k]) => k), ...constraintCols.map(([k]) => k)]);
        const others = Object.entries(props).filter(([k]) => !skipKeys.has(k));
        let othersHTML = "";
        if (others.length > 0) {
            othersHTML = `<div style="margin-top:8px;border-top:1px solid #eee;padding-top:6px;font-size:0.7rem;color:#777">${others.map(([k,v]) => `<b>${k}:</b> ${v}`).join(" · ")}</div>`;
        }

        if (!feasible) {
            return `<div style="font-family:Inter,sans-serif;min-width:220px"><div style="display:flex;align-items:center;gap:12px"><div style="font-size:2rem;font-weight:700;color:#ff4757">✗</div><div><div style="font-weight:700;font-size:1rem;color:#ff4757">INFEASIBLE</div><div style="font-size:0.75rem;color:#999">Eliminated by constraints</div></div></div>${failHTML}${constraintHTML}${factorHint}${othersHTML}</div>`;
        }

        const color = getScoreColor(score);
        return `<div style="font-family:Inter,sans-serif;min-width:220px"><div style="display:flex;align-items:center;gap:12px;margin-bottom:4px"><div style="font-size:2rem;font-weight:700;color:${color}">${pct}%</div><div><div style="font-weight:600;font-size:0.9rem">${cls}</div><div style="font-size:0.7rem;color:#999">Rank #${rank}</div></div></div><div style="background:#eee;height:8px;border-radius:4px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${color};border-radius:4px"></div></div>${constraintHTML}${breakdownHTML}${othersHTML}</div>`;
    }

    // ── Legends ──

    function _addResultLegend(geojsonData) {
        if (legendControl) map.removeControl(legendControl);
        const classCounts = {};
        geojsonData.features.forEach((f) => {
            const cls = f.properties.suitability_class || "Unknown";
            classCounts[cls] = (classCounts[cls] || 0) + 1;
        });
        legendControl = L.control({ position: "bottomright" });
        legendControl.onAdd = () => {
            const div = L.DomUtil.create("div", "legend");
            div.style.cssText = "background:rgba(26,26,46,0.92);padding:14px 18px;border-radius:8px;color:#f1f1f1;font-family:Inter,sans-serif;font-size:0.75rem;line-height:1.9;backdrop-filter:blur(4px)";
            const classes = [
                { label: "Very High", color: "#2ed573" },
                { label: "High", color: "#7bed9f" },
                { label: "Moderate", color: "#ffa502" },
                { label: "Low", color: "#ff6348" },
                { label: "Very Low", color: "#ff4757" },
                { label: "Infeasible", color: "#2a2a3e" },
            ];
            div.innerHTML = "<b style='font-size:0.85rem'>Suitability</b><br>";
            classes.forEach((c) => {
                const cnt = classCounts[c.label] || 0;
                if (cnt > 0 || c.label !== "Infeasible") {
                    const border = c.label === "Infeasible" ? "border:1px solid #ff4757;" : "";
                    div.innerHTML += `<span style="display:inline-block;width:14px;height:14px;background:${c.color};margin-right:8px;border-radius:3px;vertical-align:middle;${border}"></span>${c.label} <span style="color:#888">(${cnt})</span><br>`;
                }
            });
            return div;
        };
        legendControl.addTo(map);
    }

    function _addDiffLegend(diffGeojson, nameA, nameB) {
        if (legendControl) map.removeControl(legendControl);

        const counts = { aStrong: 0, aMed: 0, aLight: 0, similar: 0, bLight: 0, bMed: 0, bStrong: 0 };
        diffGeojson.features.forEach((f) => {
            const d = f.properties.score_delta || 0;
            if (d >= 0.3) counts.aStrong++;
            else if (d >= 0.15) counts.aMed++;
            else if (d >= 0.05) counts.aLight++;
            else if (d > -0.05) counts.similar++;
            else if (d > -0.15) counts.bLight++;
            else if (d > -0.3) counts.bMed++;
            else counts.bStrong++;
        });

        legendControl = L.control({ position: "bottomright" });
        legendControl.onAdd = () => {
            const div = L.DomUtil.create("div", "legend");
            div.style.cssText = "background:rgba(26,26,46,0.92);padding:14px 18px;border-radius:8px;color:#f1f1f1;font-family:Inter,sans-serif;font-size:0.75rem;line-height:1.9;backdrop-filter:blur(4px)";
            div.innerHTML = `<b style="font-size:0.85rem">Scenario Diff</b><br>`;

            const rows = [
                { color: "#1565c0", label: `${nameA} ≫`, count: counts.aStrong },
                { color: "#42a5f5", label: `${nameA} >`, count: counts.aMed },
                { color: "#90caf9", label: `${nameA} ≥`, count: counts.aLight },
                { color: "#9e9e9e", label: "Similar", count: counts.similar },
                { color: "#ef9a9a", label: `${nameB} ≥`, count: counts.bLight },
                { color: "#e53935", label: `${nameB} >`, count: counts.bMed },
                { color: "#b71c1c", label: `${nameB} ≫`, count: counts.bStrong },
            ];
            rows.forEach((r) => {
                div.innerHTML += `<span style="display:inline-block;width:14px;height:14px;background:${r.color};margin-right:8px;border-radius:3px;vertical-align:middle"></span>${r.label} <span style="color:#888">(${r.count})</span><br>`;
            });
            return div;
        };
        legendControl.addTo(map);
    }

    // ── Clear methods ──

    function clearResult() {
        if (resultLayer) { map.removeLayer(resultLayer); resultLayer = null; }
        if (legendControl && !diffLayer) { map.removeControl(legendControl); legendControl = null; }
    }

    function clearDiff() {
        if (diffLayer) { map.removeLayer(diffLayer); diffLayer = null; }
        if (legendControl) { map.removeControl(legendControl); legendControl = null; }
    }

    function clearAll() {
        clearResult();
        clearDiff();
        clearSensitivity();
    }

        // ── Sensitivity layer (Phase D) ──
    let sensitivityLayer = null;
    let sensitivityLegend = null;

    function renderSensitivity(geojsonData, options) {
        clearSensitivity();
        clearResult();

        sensitivityLayer = L.geoJSON(geojsonData, {
            style: (feature) => {
                const p = feature.properties;
                const color = options.getColor(p);
                const feasible = p.is_feasible !== false;

                if (!feasible) {
                    return {
                        fillColor: "#2a2a3e",
                        weight: 2,
                        opacity: 0.9,
                        color: "#ff4757",
                        fillOpacity: 0.5,
                        dashArray: "4 4",
                    };
                }

                return {
                    fillColor: color,
                    weight: 2,
                    opacity: 0.9,
                    color: "#ffffff",
                    fillOpacity: 0.75,
                };
            },
            onEachFeature: (feature, layer) => {
                layer.bindPopup(() =>
                    options.getPopup(feature.properties)
                );
            },
        }).addTo(map);

        const b = sensitivityLayer.getBounds();
        if (b.isValid()) map.fitBounds(b, { padding: [50, 50] });

        // Legend
        const legendItems = options.getLegendItems();
        _addSensitivityLegend(legendItems, geojsonData);
    }

    function _addSensitivityLegend(legendItems, geojsonData) {
        if (sensitivityLegend) map.removeControl(sensitivityLegend);

        const classCounts = {};
        geojsonData.features.forEach((f) => {
            const cls = f.properties.stability_class || "Unknown";
            classCounts[cls] = (classCounts[cls] || 0) + 1;
        });

        sensitivityLegend = L.control({ position: "bottomright" });
        sensitivityLegend.onAdd = () => {
            const div = L.DomUtil.create("div", "legend");
            div.style.cssText =
                "background:rgba(26,26,46,0.92);padding:14px 18px;" +
                "border-radius:8px;color:#f1f1f1;" +
                "font-family:Inter,sans-serif;font-size:0.75rem;" +
                "line-height:1.9;backdrop-filter:blur(4px)";

            div.innerHTML =
                `<b style="font-size:0.85rem">${legendItems.title}</b><br>`;

            legendItems.classes.forEach((c) => {
                const cnt = classCounts[c.label] || 0;
                const border = c.label === "Infeasible"
                    ? "border:1px solid #ff4757;" : "";
                div.innerHTML +=
                    `<span style="display:inline-block;width:14px;` +
                    `height:14px;background:${c.color};` +
                    `margin-right:8px;border-radius:3px;` +
                    `vertical-align:middle;${border}"></span>` +
                    `${c.label} <span style="color:#888">(${cnt})` +
                    `</span><br>`;
            });
            return div;
        };
        sensitivityLegend.addTo(map);
    }

    function clearSensitivity() {
        if (sensitivityLayer) {
            map.removeLayer(sensitivityLayer);
            sensitivityLayer = null;
        }
        if (sensitivityLegend) {
            map.removeControl(sensitivityLegend);
            sensitivityLegend = null;
        }
    }

    return {
        init, addLayer, removeLayer,
        renderResult, renderDiff, renderSensitivity,
        clearResult, clearDiff, clearSensitivity, clearAll,
    };
})();