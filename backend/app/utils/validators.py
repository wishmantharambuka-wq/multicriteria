"""
GeoJSON Validation Utilities

Validates uploaded GeoJSON before we spend resources
processing it with GeoPandas.
"""
from typing import Any, Dict, Tuple


def validate_geojson(data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate that a parsed JSON object is a valid GeoJSON
    FeatureCollection.

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check top-level type
    if "type" not in data:
        return False, "Missing 'type' field in GeoJSON."

    valid_types = {
        "FeatureCollection",
        "Feature",
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }

    if data["type"] not in valid_types:
        return False, (
            f"Invalid GeoJSON type: '{data['type']}'. "
            f"Expected one of: {valid_types}"
        )

    # If it's a FeatureCollection, check for features array
    if data["type"] == "FeatureCollection":
        if "features" not in data:
            return False, (
                "FeatureCollection must contain a 'features' array."
            )
        if not isinstance(data["features"], list):
            return False, "'features' must be an array."
        if len(data["features"]) == 0:
            return False, "FeatureCollection contains no features."

        # Spot-check the first feature
        first = data["features"][0]
        if "geometry" not in first:
            return False, (
                "First feature is missing a 'geometry' field."
            )

    return True, ""