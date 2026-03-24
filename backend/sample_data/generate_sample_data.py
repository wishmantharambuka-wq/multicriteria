"""
Generate sample GeoJSON files — Phase 5b

Key change: roads now form a CONNECTED GRID NETWORK with
shared intersection nodes, required for network distance analysis.
"""
import json
import random
import math

CENTER_LAT = 35.78
CENTER_LNG = -78.64
SPREAD = 0.04

random.seed(42)


def generate_parcels(n=30):
    features = []
    rows = int(math.sqrt(n))
    cols = n // rows
    for i in range(rows):
        for j in range(cols):
            lat = CENTER_LAT - SPREAD + (2 * SPREAD / rows) * i
            lng = CENTER_LNG - SPREAD + (2 * SPREAD / cols) * j
            lat += random.uniform(-0.002, 0.002)
            lng += random.uniform(-0.002, 0.002)
            size = random.uniform(0.003, 0.006)
            h = size / 2
            features.append({
                "type": "Feature",
                "properties": {
                    "parcel_id": f"P-{i * cols + j + 1:03d}",
                    "area_sqm": round(random.uniform(2000, 15000), 1),
                    "zoning": random.choice([
                        "Residential", "Commercial",
                        "Mixed-Use", "Industrial"
                    ]),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lng - h, lat - h], [lng + h, lat - h],
                        [lng + h, lat + h], [lng - h, lat + h],
                        [lng - h, lat - h],
                    ]],
                },
            })
    return {"type": "FeatureCollection", "features": features}


def generate_roads_network():
    """
    Generate a connected road grid.

    WHY A GRID:
    Network analysis requires a CONNECTED graph. Random
    independent line segments create disconnected components,
    making Dijkstra fail. A grid ensures every intersection
    connects to its neighbors.

    The intersection coordinates are computed ONCE and shared
    by both horizontal and vertical roads, so the NetworkX
    graph builder will merge them into shared nodes.
    """
    rows, cols = 5, 5
    features = []
    rid = 1

    # Pre-compute intersection coordinates (shared by H and V roads)
    intersections = {}
    for i in range(rows):
        for j in range(cols):
            lat = CENTER_LAT - SPREAD + (2 * SPREAD / (rows - 1)) * i
            lng = CENTER_LNG - SPREAD + (2 * SPREAD / (cols - 1)) * j
            intersections[(i, j)] = [lng, lat]

    road_names_h = [
        "Main St", "Oak Ave", "Park Blvd", "Elm Dr", "Lake Rd"
    ]
    road_names_v = [
        "1st St", "2nd St", "3rd St", "4th St", "5th St"
    ]

    # Horizontal roads (connect columns within each row)
    for i in range(rows):
        coords = [intersections[(i, j)] for j in range(cols)]
        features.append({
            "type": "Feature",
            "properties": {
                "road_id": f"R-{rid:03d}",
                "name": road_names_h[i % len(road_names_h)],
                "type": random.choice(["Arterial", "Collector"]),
                "speed_limit": random.choice([25, 35, 45]),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })
        rid += 1

    # Vertical roads (connect rows within each column)
    for j in range(cols):
        coords = [intersections[(i, j)] for i in range(rows)]
        features.append({
            "type": "Feature",
            "properties": {
                "road_id": f"R-{rid:03d}",
                "name": road_names_v[j % len(road_names_v)],
                "type": random.choice(["Arterial", "Local"]),
                "speed_limit": random.choice([25, 35]),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })
        rid += 1

    return {"type": "FeatureCollection", "features": features}


def generate_flood_zones(n=5):
    features = []
    zone_types = ["AE", "A", "X500", "VE"]
    for i in range(n):
        lat = CENTER_LAT + random.uniform(-SPREAD, SPREAD)
        lng = CENTER_LNG + random.uniform(-SPREAD, SPREAD)
        size = random.uniform(0.008, 0.016)
        h = size / 2
        features.append({
            "type": "Feature",
            "properties": {
                "zone_id": f"FZ-{i + 1:03d}",
                "flood_zone": random.choice(zone_types),
                "risk_level": random.choice(["High", "Moderate", "Low"]),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lng - h, lat - h], [lng + h, lat - h],
                    [lng + h, lat + h], [lng - h, lat + h],
                    [lng - h, lat - h],
                ]],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def generate_amenities(n=20):
    features = []
    types = [
        "School", "Hospital", "Park", "Fire Station",
        "Library", "Shopping Center", "Transit Stop",
    ]
    for i in range(n):
        # Cluster some amenities together to make KDE interesting
        if i < 8:
            # Dense cluster in NE quadrant
            lat = CENTER_LAT + random.uniform(0.005, 0.025)
            lng = CENTER_LNG + random.uniform(0.005, 0.025)
        elif i < 13:
            # Small cluster in SW
            lat = CENTER_LAT + random.uniform(-0.025, -0.010)
            lng = CENTER_LNG + random.uniform(-0.025, -0.010)
        else:
            # Scattered
            lat = CENTER_LAT + random.uniform(-SPREAD, SPREAD)
            lng = CENTER_LNG + random.uniform(-SPREAD, SPREAD)

        features.append({
            "type": "Feature",
            "properties": {
                "amenity_id": f"A-{i + 1:03d}",
                "name": f"{random.choice(types)} {i + 1}",
                "type": random.choice(types),
                "rating": round(random.uniform(2.0, 5.0), 1),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lng, lat],
            },
        })
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    datasets = {
        "parcels.geojson": generate_parcels(30),
        "roads.geojson": generate_roads_network(),
        "flood_zones.geojson": generate_flood_zones(5),
        "amenities.geojson": generate_amenities(20),
    }

    for filename, data in datasets.items():
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        count = len(data["features"])
        print(f"✅ {filename} ({count} features)")

    print("\n🎉 Sample data generated (Phase 5b)")
    print("Roads now form a connected grid for network analysis.")