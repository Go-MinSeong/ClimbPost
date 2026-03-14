from __future__ import annotations

import logging

import cv2
import mediapipe as mp
import numpy as np

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)

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
      2. Run MediaPipe Pose on sampled frames.
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
        duration = total_frames / fps

        # Analyze the full clip (not just the tail) for better accuracy
        start_frame = 0
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        y_positions: list[float] = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx < start_frame or frame_idx % sample_interval != 0:
                frame_idx += 1
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)
            center_y = self._get_center_y(results)
            if center_y is not None:
                y_positions.append(center_y)

            frame_idx += 1

        pose.close()
        cap.release()

        if not y_positions:
            logger.warning("Classifier: no pose detected in tail frames")
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
    def _get_center_y(results) -> float | None:
        """Return normalised y-centre of detected pose, or None."""
        if not results.pose_landmarks:
            return None
        ys = [lm.y for lm in results.pose_landmarks.landmark if lm.visibility > 0.5]
        if not ys:
            return None
        return float(np.mean(ys))
