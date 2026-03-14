STORAGE_ROOT = "./data/storage"
DB_PATH = "./server/climbpost.db"

PIPELINE_STAGES = [
    "analyzer.clipper.clipper.ClipperStage",
    "analyzer.classifier.classifier.ClassifierStage",
    "analyzer.detector.detector.DetectorStage",
    "analyzer.identifier.identifier.IdentifierStage",
    "analyzer.editor.editor.EditorStage",
]

# Clipper settings
CLIPPER_SAMPLE_FPS = 2            # frames per second to sample for pose detection
CLIPPER_MIN_CLIMB_SEC = 5         # minimum climb duration to keep
CLIPPER_BUFFER_SEC = 3            # seconds of padding before/after detected climb
CLIPPER_MOTION_THRESHOLD = 0.02   # normalized y-displacement to count as movement
CLIPPER_STILL_FRAMES = 4          # consecutive still frames to end a climb segment

# Classifier settings
CLASSIFIER_TAIL_SECONDS = 3      # analyse last N seconds of each clip
CLASSIFIER_SAMPLE_FPS = 2        # frames per second to sample
CLASSIFIER_TOP_ZONE_RATIO = 0.20 # upper 20% of frame = "top zone"
CLASSIFIER_HOLD_FRAMES = 2       # consecutive top-zone frames to confirm success
CLASSIFIER_FALL_DY_THRESHOLD = 0.15  # normalised y-jump that counts as a fall

# Detector settings
DETECTOR_SAMPLE_FPS = 1          # frames per second to sample
DETECTOR_MAX_SAMPLES = 10        # cap sampled frames per clip
DETECTOR_ROI_PAD_RATIO = 0.15   # expand hand region by this ratio
DETECTOR_MIN_SATURATION = 50    # minimum S in HSV to count as coloured
DETECTOR_MIN_VALUE = 50         # minimum V in HSV to avoid near-black
