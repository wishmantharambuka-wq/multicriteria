document.addEventListener("DOMContentLoaded", () => {
    console.log("🚀 Site Suitability Engine starting...");
    MapEngine.init();
    UI.init();
    if (typeof AHP !== "undefined") AHP.init();
    if (typeof Sensitivity !== "undefined") Sensitivity.init();
    if (typeof HexGrid !== "undefined") HexGrid.init();
    if (typeof Autocorrelation !== "undefined") Autocorrelation.init();
    console.log("✅ Application ready");
});