import os
from pathlib import Path


# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'climbpost.db'}")

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "climbpost-dev-secret-change-in-prod!")  # 36 bytes
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

# APNs
APNS_KEY_PATH = os.getenv("APNS_KEY_PATH", "")
APNS_KEY_ID = os.getenv("APNS_KEY_ID", "")
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", "")

# Apple Sign-In
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "com.climbpost.app")

# Google Sign-In
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

# Storage paths
STORAGE_ROOT = os.getenv("STORAGE_ROOT", str(PROJECT_ROOT / "data" / "storage"))
RAW_DIR = f"{STORAGE_ROOT}/raw/{{session_id}}/"
CLIPS_DIR = f"{STORAGE_ROOT}/clips/{{session_id}}/"
EDITED_DIR = f"{STORAGE_ROOT}/edited/{{session_id}}/"
THUMBNAILS_DIR = f"{STORAGE_ROOT}/thumbnails/{{session_id}}/"

# Analyzer microservice URL
ANALYZER_URL = os.getenv("ANALYZER_URL", "http://localhost:8001")

# Mock analysis mode (skip GPU pipeline, generate fake results)
MOCK_ANALYSIS = os.getenv("MOCK_ANALYSIS", "false").lower() in ("true", "1", "yes")

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
