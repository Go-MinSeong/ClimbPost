STORAGE_ROOT = "./data/storage"
DB_PATH = "./server/climbpost.db"

PIPELINE_STAGES = [
    "analyzer.clipper.clipper.ClipperStage",
]

# Clipper settings
CLIPPER_SAMPLE_FPS = 2            # frames per second to sample for pose detection
CLIPPER_MIN_CLIMB_SEC = 5         # minimum climb duration to keep
CLIPPER_BUFFER_SEC = 3            # seconds of padding before/after detected climb
CLIPPER_MOTION_THRESHOLD = 0.02   # normalized y-displacement to count as movement
CLIPPER_STILL_FRAMES = 4          # consecutive still frames to end a climb segment
