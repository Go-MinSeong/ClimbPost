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
    "sample_fps": 1,            # frames per second to sample
    "max_samples": 10,          # cap sampled frames per clip
    "roi_pad_ratio": 0.20,      # expand detected hand region by this ratio
    "min_saturation": 50,       # minimum S in HSV to count as coloured
    "min_value": 50,            # minimum V in HSV to avoid near-black
}

# HSV ranges for Korean colour names used in color_maps.
# Hue is [0..180] in OpenCV.  Each entry: (hue_low, hue_high, name).
_HSV_COLOR_TABLE: list[tuple[int, int, str]] = [
    (20, 35, "노랑"),     # yellow
    (36, 85, "초록"),     # green
    (86, 130, "파랑"),    # blue
    (0, 10, "빨강"),      # red (low hue wrap)
    (170, 180, "빨강"),   # red (high hue wrap)
    (0, 180, "검정"),     # black — matched by low V, handled separately
]


class DetectorStage(BaseStage):
    """Stage 3 — detect tape colour and map to difficulty.

    Strategy:
      1. Sample frames from the clip.
      2. Use YOLOv8-pose to locate the climber's hands.
      3. Extract a region around each hand (where hold tape is visible).
      4. Analyse HSV histogram of those regions to find dominant tape colour.
      5. Map the colour name via context.color_map → difficulty string.
    """

    @property
    def name(self) -> str:
        return "detector"

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("detector", {})}
        color_mapping = context.color_map.get("mapping", {})

        for clip in context.clips:
            if not clip.clip_path:
                logger.warning("Detector: clip %s has no file path, skipping", clip.clip_id)
                continue

            color_name = self._detect_tape_color(clip.clip_path, cfg)
            clip.tape_color = color_name

            if color_name and color_name in color_mapping:
                clip.difficulty = color_mapping[color_name]
                logger.info("Detector: clip %s → tape=%s, difficulty=%s", clip.clip_id, color_name, clip.difficulty)
            else:
                logger.warning("Detector: clip %s → tape=%s (no difficulty mapping)", clip.clip_id, color_name)

        return context

    # ------------------------------------------------------------------
    # Tape colour detection
    # ------------------------------------------------------------------

    def _detect_tape_color(self, clip_path: str, cfg: dict) -> str | None:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            logger.error("Detector: cannot open %s", clip_path)
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = YOLO(_YOLO_MODEL_PATH)

        # Accumulate confidence-weighted colour votes across sampled frames
        color_votes: dict[str, float] = {}
        samples = 0
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval != 0:
                frame_idx += 1
                continue
            if samples >= cfg["max_samples"]:
                break

            results = model(frame, device=device, verbose=False)
            rois_with_conf = self._get_hand_rois(results[0] if results else None, frame, cfg["roi_pad_ratio"])

            for roi, confidence in rois_with_conf:
                color = self._dominant_color_in_roi(roi, cfg)
                if color:
                    color_votes[color] = color_votes.get(color, 0.0) + confidence

            samples += 1
            frame_idx += 1

        cap.release()

        if not color_votes:
            return None

        return max(color_votes, key=color_votes.get)

    # ------------------------------------------------------------------
    # Hand ROI extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _get_hand_rois(
        result, frame: np.ndarray, pad_ratio: float
    ) -> list[tuple[np.ndarray, float]]:
        """Extract image patches around detected wrists with their keypoint confidence."""
        if result is None or result.keypoints is None or len(result.keypoints) == 0:
            return []

        h, w = frame.shape[:2]
        kpts = result.keypoints.xy[0]   # shape (17, 2)
        conf = result.keypoints.conf[0]  # shape (17,)

        rois: list[tuple[np.ndarray, float]] = []
        # YOLOv8 COCO keypoints: 9=left_wrist, 10=right_wrist
        for idx in (9, 10):
            kp_conf = float(conf[idx])
            if kp_conf < 0.3:
                continue

            cx, cy = int(kpts[idx, 0]), int(kpts[idx, 1])
            pad = int(max(h, w) * pad_ratio)

            x1 = max(0, cx - pad)
            y1 = max(0, cy - pad)
            x2 = min(w, cx + pad)
            y2 = min(h, cy + pad)

            roi = frame[y1:y2, x1:x2]
            if roi.size > 0:
                rois.append((roi, kp_conf))

        return rois

    # ------------------------------------------------------------------
    # HSV colour analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _dominant_color_in_roi(roi: np.ndarray, cfg: dict) -> str | None:
        """Determine the dominant tape colour name in a BGR image patch."""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        h_chan = hsv[:, :, 0]
        s_chan = hsv[:, :, 1]
        v_chan = hsv[:, :, 2]

        # Check for 검정 (black) first: low brightness, regardless of hue
        black_mask = v_chan < cfg["min_value"]
        total_pixels = hsv.shape[0] * hsv.shape[1]
        if total_pixels > 0 and np.count_nonzero(black_mask) / total_pixels > 0.4:
            return "검정"

        # Filter out unsaturated/dark pixels and skin tones
        # Skin: Hue 0~20, Sat 30~170, Val > 80 — exclude from tape detection
        skin_mask = (h_chan <= 20) & (s_chan >= 30) & (s_chan <= 170) & (v_chan >= 80)
        valid = (s_chan >= cfg["min_saturation"]) & (v_chan >= cfg["min_value"]) & ~skin_mask
        valid_hues = h_chan[valid]

        if valid_hues.size == 0:
            return None

        # Count votes per named colour
        votes: dict[str, int] = {}
        for hue_low, hue_high, name in _HSV_COLOR_TABLE:
            if name == "검정":
                continue  # handled above
            count = int(np.count_nonzero((valid_hues >= hue_low) & (valid_hues <= hue_high)))
            if count > 0:
                votes[name] = votes.get(name, 0) + count

        if not votes:
            return None

        return max(votes, key=votes.get)  # type: ignore[arg-type]
