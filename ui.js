/**
 * ui.js — Complete UI Controller (Phases A through F)
 */

const UI = (() => {
    const uploadedLayers = new Map();
    const layerColors = new Map();
    const criteria = new Map();
    let selectedTargetId = null;
    let lastAnalysisResult = null;
    let isComparisonMode = false;

    const COLORS = [
        "#e94560", "#0abde3", "#feca57", "#ff9ff3",
        "#54a0ff", "#5f27cd", "#01a3a4", "#f368e0",
    ];
    let colorIdx = 0;
    const API = "http://localhost:8000/api/v1";

    // ══════════════════════════════════════
    //  INIT
    // ══════════════════════════════════════

    function init() {
        console.log("🔧 UI initializing...");
        _setupDropZone();
        _setupFileInput();
        _setupTargetSelector();
        _setupAnalysisButton();
        _setupScenarioControls();
        if (typeof AHP !== "undefined") AHP.init();
        console.log("✅ UI initialized");
    }

    // ══════════════════════════════════════
    //  DRAG & DROP
    // ══════════════════════════════════════

    function _setupDropZone() {
        const zone = document.getElementById("drop-zone");
        if (!zone) { console.error("❌ drop-zone not found"); return; }

        zone.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add("drag-over");
        });

        zone.addEventListener("dragleave", (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove("drag-over");
        });

        zone.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove("drag-over");
            console.log("📂 Files dropped:", e.dataTransfer.files.length);
            Array.from(e.dataTransfer.files).forEach(_uploadFile);
        });

        console.log("  ✓ Drop zone ready");
    }

    function _setupFileInput() {
        const input = document.getElementById("file-input");
        if (!input) { console.error("❌ file-input not found"); return; }

        input.addEventListener("change", (e) => {
            console.log("📂 Files selected:", e.target.files.length);
            Array.from(e.target.files).forEach(_uploadFile);
            e.target.value = "";
        });

        console.log("  ✓ File input ready");
    }

    // ══════════════════════════════════════
    //  TARGET SELECTOR
    // ══════════════════════════════════════

    function _setupTargetSelector() {
        const sel = document.getElementById("target-layer-select");
        if (!sel) return;
        sel.addEventListener("change", (e) => {
            selectedTargetId = e.target.value || null;
            _rebuildCriteriaCards();
        });
    }

    function _setupAnalysisButton() {
        const btn = document.getElementById("run-analysis-btn");
        if (btn) btn.addEventListener("click", _runAnalysis);
    }

    // ══════════════════════════════════════
    //  FILE UPLOAD
    // ══════════════════════════════════════

    async function _uploadFile(file) {
        console.log(`📤 Uploading: ${file.name}`);
        const fd = new FormData();
        fd.append("file", file);
        fd.append("layer_name", file.name.replace(/\.(geojson|json)$/i, ""));

        try {
            const res = await fetch(`${API}/upload`, { method: "POST", body: fd });
            if (!res.ok) {
                let errMsg = `Server error (HTTP ${res.status})`;
                try { const err = await res.json(); errMsg = err.detail || errMsg; } catch {}
                alert(`Upload failed: ${errMsg}`);
                return;
            }
            const meta = await res.json();
            uploadedLayers.set(meta.layer_id, meta);

            const color = COLORS[colorIdx++ % COLORS.length];
            layerColors.set(meta.layer_id, color);

            const geoRes = await fetch(`${API}/layers/${meta.layer_id}/geojson`);
            MapEngine.addLayer(meta.layer_id, await geoRes.json(), color);

            _addLayerListItem(meta, color);
            _updateTargetDropdown();
            _rebuildCriteriaCards();

            console.log(`✅ Uploaded: ${meta.name} (${meta.feature_count} features)`);
        } catch (err) {
            console.error("Upload error:", err);
            alert("Backend connection failed. Is it running on :8000?");
        }
    }

    // ══════════════════════════════════════
    //  LAYER LIST
    // ══════════════════════════════════════

    function _addLayerListItem(meta, color) {
        const list = document.getElementById("layers-list");
        if (!list) return;

        const g = meta.geometry_type.toLowerCase();
        let badge = "polygon";
        if (g.includes("line")) badge = "line";
        if (g.includes("point")) badge = "point";

        const item = document.createElement("div");
        item.className = "layer-item";
        item.id = `layer-item-${meta.layer_id}`;
        item.innerHTML = `
            <div>
                <span style="color:${color}">●</span>
                <span class="layer-name">${meta.name}</span>
                <span class="type-badge ${badge}">${meta.geometry_type}</span>
                <div class="layer-meta">${meta.feature_count} features</div>
            </div>
            <button class="remove-btn" data-id="${meta.layer_id}">✕</button>`;

        item.querySelector(".remove-btn")
            .addEventListener("click", () => _removeLayer(meta.layer_id));
        list.appendChild(item);
    }

    function _updateTargetDropdown() {
        const sel = document.getElementById("target-layer-select");
        if (!sel) return;

        sel.innerHTML = '<option value="">— Select the layer to score —</option>';
        uploadedLayers.forEach((m, lid) => {
            const o = document.createElement("option");
            o.value = lid;
            o.textContent = `${m.name} (${m.feature_count} ${m.geometry_type}s)`;
            sel.appendChild(o);
        });
        if (selectedTargetId) sel.value = selectedTargetId;

        document.getElementById("target-selector").style.display =
            uploadedLayers.size >= 2 ? "block" : "none";
    }

    async function _removeLayer(lid) {
        try { await fetch(`${API}/layers/${lid}`, { method: "DELETE" }); } catch (_) {}
        MapEngine.removeLayer(lid);
        uploadedLayers.delete(lid);
        layerColors.delete(lid);
        criteria.delete(lid);
        if (selectedTargetId === lid) selectedTargetId = null;
        const el = document.getElementById(`layer-item-${lid}`);
        if (el) el.remove();
        _updateTargetDropdown();
        _rebuildCriteriaCards();
    }

    // ══════════════════════════════════════
    //  CRITERIA CARDS
    // ══════════════════════════════════════

    function _rebuildCriteriaCards() {
        const container = document.getElementById("criteria-controls");
        const help = document.getElementById("criteria-help");
        const wSum = document.getElementById("weight-summary");
        if (!container) return;
        container.innerHTML = "";

        const layers = [];
        uploadedLayers.forEach((m, lid) => {
            if (lid !== selectedTargetId) layers.push({ id: lid, meta: m });
        });

        if (!layers.length) {
            if (help) help.style.display = "none";
            if (wSum) wSum.style.display = "none";
            _updateValidation();
            return;
        }
        if (help) help.style.display = "block";
        if (wSum) wSum.style.display = "flex";

        layers.forEach(({ id, meta }) => {
            if (!criteria.has(id)) {
                const s = _suggestType(meta);
                criteria.set(id, {
                    weight: 0, type: s.type, isConstraint: s.isConstraint,
                    params: {
                        buffer_distance_m: 500, decay_function: "linear",
                        graduated: false, bandwidth_m: 1000, network_layer_id: "",
                    },
                });
            }
            _createCard(id, meta, criteria.get(id), container);
        });

        criteria.forEach((_, lid) => {
            if (!uploadedLayers.has(lid) || lid === selectedTargetId)
                criteria.delete(lid);
        });

        _updateValidation();
        if (typeof AHP !== "undefined") AHP.rebuild();
    }

    function _suggestType(meta) {
        const n = meta.name.toLowerCase();
        if (n.includes("flood") || n.includes("hazard") || n.includes("protected"))
            return { type: "exclusion", isConstraint: true };
        if (n.includes("amenity") || n.includes("amenities"))
            return { type: "density", isConstraint: false };
        if (meta.geometry_type.toLowerCase().includes("line") ||
            meta.geometry_type.toLowerCase().includes("point"))
            return { type: "proximity", isConstraint: false };
        return { type: "inclusion", isConstraint: false };
    }

    function _createCard(layerId, meta, state, container) {
        const color = layerColors.get(layerId) || "#888";
        const isCon = state.isConstraint;
        const t = state.type;
        const showBuffer = ["proximity", "avoidance", "network_proximity"].includes(t);
        const showDecay = showBuffer && !isCon;
        const showGrad = ["inclusion", "exclusion"].includes(t);
        const showBW = t === "density" && !isCon;
        const showNet = t === "network_proximity" && !isCon;

        let netOpts = '<option value="">Auto-detect</option>';
        uploadedLayers.forEach((m, lid) => {
            if (m.geometry_type.includes("Line") && lid !== selectedTargetId)
                netOpts += `<option value="${lid}" ${state.params.network_layer_id === lid ? "selected" : ""}>${m.name}</option>`;
        });

        const card = document.createElement("div");
        card.className = `criterion-card ${isCon ? "constraint-mode" : "factor-mode"}`;
        card.id = `criterion-${layerId}`;
        card.innerHTML = `
            <div class="criterion-header">
                <span class="criterion-name"><span style="color:${color}">●</span> ${meta.name}</span>
                <span class="mode-badge ${isCon ? "constraint-badge" : "factor-badge"}">${isCon ? "🔒 CONSTRAINT" : "📊 FACTOR"}</span>
            </div>
            <div class="mode-toggle">
                <button class="toggle-btn ${!isCon ? "active" : ""}" data-mode="factor" data-id="${layerId}">📊 Factor</button>
                <button class="toggle-btn ${isCon ? "active" : ""}" data-mode="constraint" data-id="${layerId}">🔒 Constraint</button>
            </div>
            <label>Criteria Type</label>
            <select class="ct-type" data-id="${layerId}">
                <option value="proximity" ${t==="proximity"?"selected":""}>📍 Proximity</option>
                <option value="avoidance" ${t==="avoidance"?"selected":""}>🚫 Avoidance</option>
                <option value="inclusion" ${t==="inclusion"?"selected":""}>✅ Inclusion</option>
                <option value="exclusion" ${t==="exclusion"?"selected":""}>❌ Exclusion</option>
                <option value="density" ${t==="density"?"selected":""} ${isCon?"disabled":""}>🔥 Density</option>
                <option value="network_proximity" ${t==="network_proximity"?"selected":""} ${isCon?"disabled":""}>🛣️ Network</option>
            </select>
            <div class="constraint-info" style="display:${isCon?"block":"none"}"><div class="constraint-desc">${_getConstraintDesc(t)}</div></div>
            <div class="param-group pg-buffer" style="display:${showBuffer?"block":"none"}"><label>${isCon?"Threshold (m)":"Buffer (m)"}</label><input type="number" class="ct-buffer" data-id="${layerId}" value="${state.params.buffer_distance_m}" min="50" step="50" /></div>
            <div class="param-group pg-decay" style="display:${showDecay?"block":"none"}"><label>Decay Function</label><select class="ct-decay" data-id="${layerId}"><option value="linear" ${state.params.decay_function==="linear"?"selected":""}>Linear</option><option value="gaussian" ${state.params.decay_function==="gaussian"?"selected":""}>Gaussian</option><option value="exponential" ${state.params.decay_function==="exponential"?"selected":""}>Exponential</option><option value="inverse_power" ${state.params.decay_function==="inverse_power"?"selected":""}>Inverse Power</option><option value="step" ${state.params.decay_function==="step"?"selected":""}>Step</option></select></div>
            <div class="param-group pg-grad" style="display:${showGrad?"block":"none"}"><label class="checkbox-label"><input type="checkbox" class="ct-grad" data-id="${layerId}" ${state.params.graduated?"checked":""} /> Graduated</label></div>
            <div class="param-group pg-bw" style="display:${showBW?"block":"none"}"><label>Bandwidth (m): <span class="bw-display">${state.params.bandwidth_m}</span></label><input type="range" class="ct-bandwidth" data-id="${layerId}" min="100" max="5000" step="100" value="${state.params.bandwidth_m}" /></div>
            <div class="param-group pg-net" style="display:${showNet?"block":"none"}"><label>Network Layer</label><select class="ct-network" data-id="${layerId}">${netOpts}</select></div>
            <div class="weight-section" style="display:${isCon?"none":"block"}"><label>Weight</label><div class="weight-slider-group"><input type="range" class="ct-weight" data-id="${layerId}" min="0" max="100" step="5" value="${state.weight}" /><span class="weight-value" id="weight-val-${layerId}">${state.weight}%</span></div></div>`;

        // Events
        card.querySelectorAll(".toggle-btn").forEach((b) => {
            b.addEventListener("click", (e) => {
                const c = criteria.get(e.target.dataset.id);
                c.isConstraint = e.target.dataset.mode === "constraint";
                if (c.isConstraint) c.weight = 0;
                _rebuildCriteriaCards();
            });
        });
        card.querySelector(".ct-type").addEventListener("change", (e) => { criteria.get(layerId).type = e.target.value; _rebuildCriteriaCards(); });
        card.querySelector(".ct-buffer").addEventListener("input", (e) => { criteria.get(layerId).params.buffer_distance_m = parseInt(e.target.value) || 500; });
        card.querySelector(".ct-decay").addEventListener("change", (e) => { criteria.get(layerId).params.decay_function = e.target.value; });
        card.querySelector(".ct-grad").addEventListener("change", (e) => { criteria.get(layerId).params.graduated = e.target.checked; });
        card.querySelector(".ct-bandwidth").addEventListener("input", (e) => { const v = parseInt(e.target.value); criteria.get(layerId).params.bandwidth_m = v; card.querySelector(".bw-display").textContent = v; });
        card.querySelector(".ct-network").addEventListener("change", (e) => { criteria.get(layerId).params.network_layer_id = e.target.value; });
        card.querySelector(".ct-weight").addEventListener("input", (e) => { const v = parseInt(e.target.value); criteria.get(layerId).weight = v; document.getElementById(`weight-val-${layerId}`).textContent = `${v}%`; _updateValidation(); });

        container.appendChild(card);
    }

    function _getConstraintDesc(type) {
        return {
            exclusion: "Parcels that intersect will be <b>eliminated</b>.",
            inclusion: "Parcels that do NOT intersect will be <b>eliminated</b>.",
            proximity: "Parcels beyond threshold will be <b>eliminated</b>.",
            avoidance: "Parcels within threshold will be <b>eliminated</b>.",
            density: "Parcels with low density will be <b>eliminated</b>.",
            network_proximity: "Parcels beyond network threshold will be <b>eliminated</b>.",
        }[type] || "";
    }

    // ══════════════════════════════════════
    //  VALIDATION
    // ══════════════════════════════════════

    function _updateValidation() {
        let factorTotal = 0, hasConstraints = false, hasFactors = false;
        criteria.forEach((c) => {
            if (c.isConstraint) hasConstraints = true;
            else if (c.weight > 0) { hasFactors = true; factorTotal += c.weight; }
        });

        const display = document.getElementById("weight-total");
        if (!display) return;

        if (hasFactors) display.textContent = `${factorTotal}% (factors)`;
        else if (hasConstraints) display.textContent = "Constraints only";
        else display.textContent = "0%";

        const isValid = hasFactors ? (factorTotal >= 95 && factorTotal <= 105) : hasConstraints;
        display.className = `weight-total ${isValid ? "valid" : "invalid"}`;

        const btn = document.getElementById("run-analysis-btn");
        if (btn) btn.disabled = !(isValid && selectedTargetId && (hasConstraints || hasFactors));
    }

    // ══════════════════════════════════════
    //  RUN ANALYSIS
    // ══════════════════════════════════════

    async function _runAnalysis() {
        if (isComparisonMode) _closeComparison();

        const criteriaList = [];
        criteria.forEach((c, lid) => {
            if (c.isConstraint || c.weight > 0) {
                criteriaList.push({
                    layer_id: lid, weight: c.isConstraint ? 0 : c.weight,
                    criteria_type: c.type, parameters: c.params, is_constraint: c.isConstraint,
                });
            }
        });
        if (!criteriaList.length) { alert("Configure at least one criterion."); return; }

        document.getElementById("map-loading").style.display = "flex";
        document.getElementById("run-analysis-btn").disabled = true;

        try {
            const res = await fetch(`${API}/analyze`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ criteria: criteriaList, target_layer_id: selectedTargetId }),
            });
            if (!res.ok) { alert(`Failed: ${(await res.json()).detail}`); return; }

            const result = await res.json();
            lastAnalysisResult = result;
            MapEngine.renderResult(result.result_geojson);
            _displayResults(result);
            _showScenariosPanel();

            if (typeof Sensitivity !== "undefined") Sensitivity.showTrigger();
            if (typeof Autocorrelation !== "undefined") Autocorrelation.showTrigger();
            await _refreshScenarioList();

        } catch (err) { console.error(err); alert("Analysis failed."); }
        finally {
            document.getElementById("map-loading").style.display = "none";
            document.getElementById("run-analysis-btn").disabled = false;
        }
    }

    // ══════════════════════════════════════
    //  RESULTS DISPLAY
    // ══════════════════════════════════════

    function _displayResults(result) {
        const panel = document.getElementById("results-panel");
        const summary = document.getElementById("results-summary");
        if (!panel || !summary) return;
        panel.style.display = "block";

        const s = result.summary;
        const dist = s.class_distribution || {};
        const details = result.criteria_details || [];
        const conSummary = result.constraint_summary || [];

        const classColors = { "Very Low":"#ff4757","Low":"#ff6348","Moderate":"#ffa502","High":"#7bed9f","Very High":"#2ed573","Infeasible":"#444466","Feasible":"#2ed573" };
        const classOrder = ["Infeasible","Very Low","Low","Moderate","High","Very High","Feasible"];
        const total = s.total_features || 1;

        let conHTML = "";
        if (conSummary.length > 0) {
            conHTML = '<div class="result-section"><div class="result-section-title">🔒 Constraints</div>';
            conSummary.forEach((c) => {
                const pc = c.pass_rate > 0.8 ? "#2ed573" : c.pass_rate > 0.5 ? "#ffa502" : "#ff4757";
                conHTML += `<div class="constraint-result-card"><div style="display:flex;justify-content:space-between"><span><b>${c.name}</b></span><span style="color:${pc};font-weight:700">${(c.pass_rate*100).toFixed(0)}% pass</span></div><div style="background:var(--bg-dark);height:6px;border-radius:3px;overflow:hidden;margin-top:6px"><div style="width:${c.pass_rate*100}%;height:100%;background:${pc};border-radius:3px"></div></div></div>`;
            });
            conHTML += "</div>";
        }

        let barHTML = '<div class="class-bar">';
        classOrder.forEach((cls) => { const cnt = dist[cls]||0; const pct = cnt/total*100; if (pct>0) barHTML += `<div class="class-segment" style="width:${pct}%;background:${classColors[cls]}"></div>`; });
        barHTML += "</div>";

        let factHTML = "";
        if (details.length > 0) {
            const icons = {proximity:"📍",avoidance:"🚫",inclusion:"✅",exclusion:"❌",density:"🔥",network_proximity:"🛣️"};
            factHTML = '<div class="result-section"><div class="result-section-title">📊 Factors</div>';
            details.forEach((d) => { const mp = (d.mean_score*100).toFixed(1); factHTML += `<div style="background:var(--bg-input);padding:8px 10px;border-radius:5px;margin-bottom:6px;font-size:0.75rem"><div style="display:flex;justify-content:space-between"><span>${icons[d.criteria_type]||"📊"} <b>${d.name}</b></span><span style="color:var(--accent);font-weight:700">${d.weight_pct}%</span></div><div style="background:var(--bg-dark);height:6px;border-radius:3px;overflow:hidden;margin-top:4px"><div style="width:${mp}%;height:100%;background:var(--accent);border-radius:3px"></div></div></div>`; });
            factHTML += "</div>";
        }

        summary.innerHTML = `
            <div class="stat-grid">
                <div class="stat-card"><div class="stat-value">${s.total_features}</div><div class="stat-label">Total</div></div>
                <div class="stat-card"><div class="stat-value">${s.feasible_count}</div><div class="stat-label">Feasible</div></div>
                <div class="stat-card"><div class="stat-value">${s.mean_score!=null?(s.mean_score*100).toFixed(1)+"%":"—"}</div><div class="stat-label">Mean</div></div>
                <div class="stat-card"><div class="stat-value">${s.max_score!=null?(s.max_score*100).toFixed(1)+"%":"—"}</div><div class="stat-label">Best</div></div>
            </div>${conHTML}${barHTML}${factHTML}`;

        document.getElementById("export-btn").onclick = () => {
            const blob = new Blob([JSON.stringify(result.result_geojson, null, 2)], { type: "application/json" });
            const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "suitability_result.geojson"; a.click();
        };
    }

    // ══════════════════════════════════════
    //  SCENARIOS
    // ══════════════════════════════════════

    function _setupScenarioControls() {
        const saveBtn = document.getElementById("save-scenario-btn");
        if (saveBtn) saveBtn.addEventListener("click", _saveScenario);

        const compareBtn = document.getElementById("compare-btn");
        if (compareBtn) compareBtn.addEventListener("click", _runComparison);

        const closeBtn = document.getElementById("close-comparison-btn");
        if (closeBtn) closeBtn.addEventListener("click", _closeComparison);

        ["compare-select-a", "compare-select-b"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener("change", () => {
                const a = document.getElementById("compare-select-a").value;
                const b = document.getElementById("compare-select-b").value;
                const btn = document.getElementById("compare-btn");
                if (btn) btn.disabled = !(a && b && a !== b);
            });
        });
    }

    function _showScenariosPanel() {
        const panel = document.getElementById("scenarios-panel");
        if (panel) panel.style.display = "block";
    }

    async function _saveScenario() {
        const input = document.getElementById("scenario-name-input");
        const name = input ? input.value.trim() : "";
        if (!name) { alert("Enter a scenario name."); return; }
        try {
            const res = await fetch(`${API}/scenarios/save`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
            if (!res.ok) { alert(`Save failed: ${(await res.json()).detail}`); return; }
            if (input) input.value = "";
            await _refreshScenarioList();
            console.log(`💾 Scenario saved: ${name}`);
        } catch (err) { console.error(err); }
    }

    async function _refreshScenarioList() {
        try {
            const res = await fetch(`${API}/scenarios`);
            if (!res.ok) return;
            const scenarios = await res.json();
            _renderScenarioList(scenarios);
            _updateCompareDropdowns(scenarios);
        } catch (err) { console.error(err); }
    }

    function _renderScenarioList(scenarios) {
        const list = document.getElementById("scenario-list");
        if (!list) return;
        list.innerHTML = "";
        if (!scenarios.length) { list.innerHTML = '<div style="text-align:center;color:var(--text-secondary);font-size:0.8rem;padding:12px">No saved scenarios</div>'; return; }

        scenarios.forEach((s) => {
            const meanPct = s.mean_score != null ? `${(s.mean_score * 100).toFixed(0)}%` : "—";
            const card = document.createElement("div");
            card.className = "scenario-card";
            card.innerHTML = `
                <div class="scenario-card-header"><span class="scenario-name">${s.name}</span><button class="scenario-delete-btn" data-id="${s.id}">🗑️</button></div>
                <div class="scenario-card-stats"><span>📊 ${s.feature_count}</span><span>✅ ${s.feasible_count}</span><span>📈 ${meanPct}</span></div>
                <div class="scenario-card-actions"><button class="scenario-load-btn" data-id="${s.id}">🗺️ Load on Map</button></div>`;
            card.querySelector(".scenario-load-btn").addEventListener("click", () => _loadScenario(s.id, s.name));
            card.querySelector(".scenario-delete-btn").addEventListener("click", () => _deleteScenario(s.id));
            list.appendChild(card);
        });

        const compareSection = document.getElementById("compare-section");
        if (compareSection) compareSection.style.display = scenarios.length >= 2 ? "block" : "none";
    }

    function _updateCompareDropdowns(scenarios) {
        ["compare-select-a", "compare-select-b"].forEach((id) => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const cur = sel.value;
            sel.innerHTML = '<option value="">— Select —</option>';
            scenarios.forEach((s) => { const o = document.createElement("option"); o.value = s.id; o.textContent = s.name; sel.appendChild(o); });
            if (cur) sel.value = cur;
        });
    }

    async function _loadScenario(id, name) {
        if (isComparisonMode) _closeComparison();
        try {
            const res = await fetch(`${API}/scenarios/${id}/geojson`);
            if (!res.ok) return;
            MapEngine.renderResult(await res.json());
            const panel = document.getElementById("results-panel");
            if (panel) { panel.style.display = "block"; document.getElementById("results-summary").innerHTML = `<div style="text-align:center;padding:12px"><div style="font-size:1.1rem;font-weight:700">📋 ${name}</div></div>`; }
        } catch (err) { console.error(err); }
    }

    async function _deleteScenario(id) {
        if (!confirm("Delete this scenario?")) return;
        try { await fetch(`${API}/scenarios/${id}`, { method: "DELETE" }); await _refreshScenarioList(); } catch (err) { console.error(err); }
    }

    async function _runComparison() {
        const idA = document.getElementById("compare-select-a").value;
        const idB = document.getElementById("compare-select-b").value;
        if (!idA || !idB || idA === idB) return;
        document.getElementById("map-loading").style.display = "flex";

        try {
            const res = await fetch(`${API}/scenarios/compare`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_a_id: idA, scenario_b_id: idB }) });
            if (!res.ok) { alert(`Comparison failed: ${(await res.json()).detail}`); return; }
            const result = await res.json();
            isComparisonMode = true;
            MapEngine.renderDiff(result.diff_geojson, result.scenario_a.name, result.scenario_b.name);
            document.getElementById("results-panel").style.display = "none";
            document.getElementById("comparison-panel").style.display = "block";
            document.getElementById("comparison-results").innerHTML = `<div style="text-align:center;font-weight:700;margin:12px 0">🔵 ${result.scenario_a.name} vs 🔴 ${result.scenario_b.name}</div><div class="stat-grid"><div class="stat-card"><div class="stat-value">${result.summary.features_compared}</div><div class="stat-label">Compared</div></div><div class="stat-card"><div class="stat-value">${(result.summary.correlation*100).toFixed(0)}%</div><div class="stat-label">Correlation</div></div></div>`;
        } catch (err) { console.error(err); }
        finally { document.getElementById("map-loading").style.display = "none"; }
    }

    function _closeComparison() {
        isComparisonMode = false;
        MapEngine.clearDiff();
        document.getElementById("comparison-panel").style.display = "none";
        if (lastAnalysisResult) {
            MapEngine.renderResult(lastAnalysisResult.result_geojson);
            document.getElementById("results-panel").style.display = "block";
        }
    }

    // ══════════════════════════════════════
    //  PUBLIC: AHP + HexGrid integration
    // ══════════════════════════════════════

    function getFactorLayers() {
        const factors = [];
        criteria.forEach((c, lid) => {
            if (!c.isConstraint && lid !== selectedTargetId) {
                const meta = uploadedLayers.get(lid);
                if (meta) factors.push({ id: lid, name: meta.name });
            }
        });
        return factors;
    }

    function applyAHPWeights(weightMap) {
        Object.entries(weightMap).forEach(([lid, pct]) => {
            const c = criteria.get(lid);
            if (!c) return;
            const rounded = Math.round(pct / 5) * 5;
            c.weight = rounded;
            const slider = document.querySelector(`#criterion-${lid} .ct-weight`);
            if (slider) slider.value = rounded;
            const display = document.getElementById(`weight-val-${lid}`);
            if (display) display.textContent = `${rounded}%`;
        });
        _updateValidation();
    }

    function addGeneratedLayer(layerId, metadata, color) {
        uploadedLayers.set(metadata.layer_id || layerId, metadata);
        layerColors.set(metadata.layer_id || layerId, color);
        _addLayerListItem(metadata, color);
        _updateTargetDropdown();
        if (metadata.geometry_type === "Polygon" || metadata.geometry_type === "MultiPolygon") {
            const sel = document.getElementById("target-layer-select");
            if (sel) { sel.value = metadata.layer_id || layerId; selectedTargetId = metadata.layer_id || layerId; }
        }
        _rebuildCriteriaCards();
    }

    return { init, getFactorLayers, applyAHPWeights, addGeneratedLayer };
})();