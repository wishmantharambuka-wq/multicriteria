"""
Shared Application State

In-memory stores for the current session.
In production, replace with:
  - uploaded_layers → PostgreSQL + file storage (S3)
  - last_analysis   → Redis cache (TTL 1 hour)
  - saved_scenarios → PostgreSQL + PostGIS

For now, everything lives in memory. Restarting the
server clears all state.
"""

# layer_id → {file_path, name, metadata}
uploaded_layers: dict = {}

# Most recent analysis result — used by "Save Scenario"
# Stored automatically after each analysis completes
last_analysis: dict = {}

# scenario_id → full scenario data
saved_scenarios: dict = {}
