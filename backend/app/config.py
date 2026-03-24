"""
Application configuration and constants.
"""
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"

# Create upload directory if it doesn't exist
UPLOAD_DIR.mkdir(exist_ok=True)

# Analysis defaults
DEFAULT_CRS = "EPSG:4326"       # WGS84 for GeoJSON input
PROJECTED_CRS = "EPSG:3857"     # Web Mercator for distance calculations

# File constraints
MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = {".geojson", ".json"}