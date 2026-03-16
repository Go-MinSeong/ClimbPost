from __future__ import annotations

import logging
import os

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)

_YOLO_MODEL_PATH = os.environ.get("YOLO_MODEL", "yolov8m-pose.pt")

# Default settings (overridable via config dict)
_DEFAULTS = {
    "tail_seconds": 3,          # analyse last N seconds of each clip
    "sample_fps": 2,            # frames per second to sample
    "top_zone_ratio": 0.20,     # upper 20% of frame counts as "top"
    "hold_frames": 2,           # consecutive top-zone frames to confirm success
    "fall_dy_threshold": 0.15,  # normalised y-jump that counts as a fall
}


class ClassifierStage(BaseStage):
    """Stage 2 — classify each clip as success or fail.

    Strategy (minimum-viable version):
      1. Read the last *tail_seconds* of the clip.
      2. Run YOLOv8-pose on sampled frames.
      3. If the climber's centre-y sits in the top 20 % of the frame for
         *hold_frames* consecutive samples → success.
      4. If a sudden downward jump (> fall_dy_threshold) is detected → fail.
      5. Otherwise fall back to checking the final detected y-position:
         top 30 % → success, else fail.
    """

    @property
    def name(self) -> str:
        return "classifier"

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("classifier", {})}

        for clip in context.clips:
            if not clip.clip_path:
                logger.warning("Classifier: clip %s has no file path, skipping", clip.clip_id)
                clip.result = "fail"
                continue

            result = self._classify_clip(clip.clip_path, cfg)
            clip.result = result
            logger.info("Classifier: clip %s → %s", clip.clip_id, result)

        return context

    # ------------------------------------------------------------------
    # Core classification logic
    # ------------------------------------------------------------------

    def _classify_clip(self, clip_path: str, cfg: dict) -> str:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            logger.error("Classifier: cannot open %s", clip_path)
            return "fail"

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = YOLO(_YOLO_MODEL_PATH)

        y_positions: list[float] = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval != 0:
                frame_idx += 1
                continue

            results = model(frame, device=device, verbose=False)
            center_y = self._get_center_y(results[0]) if results else None
            if center_y is not None:
                y_positions.append(center_y)

            frame_idx += 1

        cap.release()

        if not y_positions:
            logger.warning("Classifier: no pose detected in frames")
            return "fail"

        return self._decide(y_positions, cfg)

    @staticmethod
    def _decide(y_positions: list[float], cfg: dict) -> str:
        """Determine success/fail from the sequence of y positions.

        For fixed tripod camera, success = climber reached high on the wall.
        Uses absolute y position rather than relative movement.
        """
        if not y_positions:
            return "fail"

        fall_threshold = cfg.get("fall_dy_threshold", 0.15)
        success_y = cfg.get("success_y_threshold", 0.40)

        min_y = min(y_positions)  # highest point reached (lower y = higher)
        last_y = y_positions[-1]
        first_y = y_positions[0] if y_positions else 0.5

        # Check for sudden fall (large downward jump in y)
        for i in range(1, len(y_positions)):
            dy = y_positions[i] - y_positions[i - 1]
            if dy > fall_threshold:
                return "fail"

        # Success: climber reached high enough on the wall
        if min_y < success_y:
            return "success"

        # Success: ended higher than started (climbed up and stayed)
        if last_y < first_y - 0.05:
            return "success"

        # Success: final position is in upper half
        if last_y < 0.50:
            return "success"

        return "fail"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_center_y(result) -> float | None:
        """Return normalised y-centre of detected pose, or None."""
        if result.keypoints is None or len(result.keypoints) == 0:
            return None
        kpts = result.keypoints.xy[0]   # shape (17, 2), pixel coords
        conf = result.keypoints.conf[0]  # shape (17,), confidence scores
        h = result.orig_shape[0]

        # Use shoulders [5,6] and hips [11,12]
        indices = [5, 6, 11, 12]
        ys = []
        for idx in indices:
            if conf[idx] > 0.3:
                ys.append(float(kpts[idx, 1]) / h)

        if not ys:
            return None
        return float(np.mean(ys))
