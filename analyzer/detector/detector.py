"""Stage 4 — Detector: tape colour and difficulty detection for 'me' clips only.

Uses YOLO26n-pose ONNX to locate wrist keypoints, then analyses HSV colour
of the surrounding region (where the climber's hands touch the holds/tape).
Clips with is_me=False are skipped.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import cv2
import numpy as np

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext
from analyzer.pipeline.onnx_infer import (
    load_session,
    preprocess,
    postprocess_pose,
    get_wrist_points,
)

logger = logging.getLogger(__name__)

_MODEL_PATH = os.environ.get(
    "YOLO26N_POSE_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "yolo26n-pose.onnx"),
)

_DEFAULTS = {
    "sample_fps": 1,          # frames per second to sample
    "max_samples": 10,        # cap sampled frames per clip
    "roi_pad_ratio": 0.20,    # expand hand region by this ratio
    "min_saturation": 50,     # minimum S in HSV
    "min_value": 50,          # minimum V in HSV
    "conf_threshold": 0.3,    # minimum pose detection confidence
}

# HSV tape colour table (OpenCV H: 0-180)
_COLOR_TABLE: list[tuple[int, int, str]] = [
    (20,  35,  "노랑"),   # yellow
    (36,  85,  "초록"),   # green
    (86, 130,  "파랑"),   # blue
    (0,   10,  "빨강"),   # red low
    (170, 180, "빨강"),   # red high
]


class DetectorStage(BaseStage):
    """Stage 4 — detect tape colour and map to difficulty for 'me' clips."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._session = load_session(_MODEL_PATH)
        inp = self._session.get_inputs()[0].shape
        self._infer_h = inp[2] if isinstance(inp[2], int) else 640
        self._infer_w = inp[3] if isinstance(inp[3], int) else 640

    @property
    def name(self) -> str:
        return "detector"

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("detector", {})}
        color_mapping = context.color_map.get("mapping", {})

        for clip in context.clips:
            if not clip.is_me:
                logger.debug("Detector: skip clip %s (is_me=False)", clip.clip_id)
                continue
            if not clip.clip_path:
                continue

            color = self._detect_color(clip.clip_path, cfg)
            clip.tape_color = color
            if color and color in color_mapping:
                clip.difficulty = color_mapping[color]
                logger.info(
                    "Detector: clip %s → tape=%s difficulty=%s",
                    clip.clip_id, color, clip.difficulty,
                )
            else:
                logger.info("Detector: clip %s → tape=%s (no mapping)", clip.clip_id, color)

        return context

    # ------------------------------------------------------------------
    # Tape colour detection
    # ------------------------------------------------------------------

    def _detect_color(self, clip_path: str, cfg: dict) -> str | None:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        color_votes: dict[str, float] = {}
        samples = 0
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample_interval == 0 and samples < cfg["max_samples"]:
                fh, fw = frame.shape[:2]
                blob, r, pad = preprocess(frame, self._infer_h, self._infer_w)
                raw = self._session.run(None, {self._session.get_inputs()[0].name: blob})[0]
                persons = postprocess_pose(raw, r, pad, (fh, fw), cfg["conf_threshold"])

                if len(persons) > 0:
                    for cx_px, cy_px, vis in get_wrist_points(persons[0], fh, fw):
                        roi = _extract_roi(frame, cx_px, cy_px, fh, fw, cfg["roi_pad_ratio"])
                        if roi is not None:
                            color = _dominant_color(roi, cfg)
                            if color:
                                color_votes[color] = color_votes.get(color, 0.0) + vis
                samples += 1
            frame_idx += 1

        cap.release()
        if not color_votes:
            return None
        return max(color_votes, key=color_votes.get)  # type: ignore[arg-type]


# ------------------------------------------------------------------
# ROI + colour helpers
# ------------------------------------------------------------------

def _extract_roi(
    frame: np.ndarray,
    cx: int,
    cy: int,
    fh: int,
    fw: int,
    pad_ratio: float,
) -> np.ndarray | None:
    pad = int(max(fh, fw) * pad_ratio)
    x1, y1 = max(0, cx - pad), max(0, cy - pad)
    x2, y2 = min(fw, cx + pad), min(fh, cy + pad)
    roi = frame[y1:y2, x1:x2]
    return roi if roi.size > 0 else None


def _dominant_color(roi: np.ndarray, cfg: dict) -> str | None:
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    h_c = hsv[:, :, 0]
    s_c = hsv[:, :, 1]
    v_c = hsv[:, :, 2]

    # Black: low brightness
    black_ratio = np.count_nonzero(v_c < cfg["min_value"]) / max(h_c.size, 1)
    if black_ratio > 0.4:
        return "검정"

    # Exclude skin tones
    skin = (h_c <= 20) & (s_c >= 30) & (s_c <= 170) & (v_c >= 80)
    valid = (s_c >= cfg["min_saturation"]) & (v_c >= cfg["min_value"]) & ~skin
    valid_h = h_c[valid]

    if valid_h.size == 0:
        return None

    votes: dict[str, int] = {}
    for lo, hi, name in _COLOR_TABLE:
        cnt = int(np.count_nonzero((valid_h >= lo) & (valid_h <= hi)))
        if cnt > 0:
            votes[name] = votes.get(name, 0) + cnt

    return max(votes, key=votes.get) if votes else None  # type: ignore[arg-type]
