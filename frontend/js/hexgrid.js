/**
 * hexgrid.js — Phase E: Hex Grid Generation UI
 *
 * Provides a "Generate Hex Grid" button in the target
 * selector area. When clicked, generates a hex grid
 * covering all uploaded layers and adds it as a new
 * target layer option.
 */

const HexGrid = (() => {
    const API = "http://localhost:8000/api/v1";

    function init() {
        const btn = document.getElementById("hexgrid-generate-btn");
        if (btn) {
            btn.addEventListener("click", _showControls);
            console.log("✅ HexGrid module ready");
        }

        const runBtn = document.getElementById("hexgrid-run-btn");
        if (runBtn) {
            runBtn.addEventListener("click", _generate);
        }

        const slider = document.getElementById("hexgrid-size-slider");
        if (slider) {
            slider.addEventListener("input", _onSizeChange);
        }
    }

    function _showControls() {
        const controls = document.getElementById("hexgrid-controls");
        if (!controls) return;

        const isHidden = controls.style.display === "none" || controls.style.display === "";
        controls.style.display = isHidden ? "block" : "none";

        // Get estimate immediately
        if (isHidden) _updateEstimate();
    }

    async function _onSizeChange(e) {
        const size = parseInt(e.target.value);
        const display = document.getElementById("hexgrid-size-display");
        if (display) display.textContent = `${size}m`;
        _updateEstimate();
    }

    async function _updateEstimate() {
        const slider = document.getElementById("hexgrid-size-slider");
        const estimateDiv = document.getElementById("hexgrid-estimate");
        if (!slider || !estimateDiv) return;

        const size = parseInt(slider.value);

        try {
            const res = await fetch(`${API}/hexgrid/estimate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cell_size_m: size }),
            });

            if (!res.ok) {
                estimateDiv.innerHTML = `<span style="color:var(--text-secondary)">Upload layers first to estimate</span>`;
                return;
            }

            const data = await res.json();
            const color = data.warning ? "#ffa502" : "#2ed573";

            estimateDiv.innerHTML = `
                <span style="color:${color}">
                    ~${data.estimated_cells.toLocaleString()} cells
                </span>
                <span style="color:var(--text-secondary)">
                    (${data.study_area_km2} km²)
                </span>
                ${data.warning ? '<div style="color:#ffa502;font-size:0.65rem;margin-top:2px">⚠ Large grid — may be slow</div>' : ''}
            `;
        } catch (err) {
            estimateDiv.innerHTML = `<span style="color:var(--text-secondary)">Could not estimate</span>`;
        }
    }

    async function _generate() {
        const slider = document.getElementById("hexgrid-size-slider");
        const size = slider ? parseInt(slider.value) : 200;

        const btn = document.getElementById("hexgrid-run-btn");
        if (btn) { btn.disabled = true; btn.textContent = "Generating..."; }

        const loading = document.getElementById("map-loading");
        if (loading) loading.style.display = "flex";

        try {
            const res = await fetch(`${API}/hexgrid/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cell_size_m: size }),
            });

            if (!res.ok) {
                const err = await res.json();
                alert(`Grid generation failed: ${err.detail}`);
                return;
            }

            const data = await res.json();

            // Render on map
            MapEngine.addLayer(data.layer_id, data.geojson, "#00b894");

            // Notify UI module to refresh target dropdown
            if (typeof UI !== "undefined" && UI.addGeneratedLayer) {
                UI.addGeneratedLayer(data.layer_id, data.metadata, "#00b894");
            }

            // Hide controls, show success
            const controls = document.getElementById("hexgrid-controls");
            if (controls) controls.style.display = "none";

            console.log(`🔷 Hex grid generated: ${data.cell_count} cells at ${size}m`);

        } catch (err) {
            console.error("HexGrid error:", err);
            alert("Grid generation failed. Check console.");
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = "🔷 Generate Grid"; }
            if (loading) loading.style.display = "none";
        }
    }

    return { init };
})();