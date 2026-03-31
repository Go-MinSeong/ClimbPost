"""Stage 4 — Detector: tape colour and difficulty detection for 'me' clips only.

Uses YOLO26n-pose ONNX to locate wrist keypoints, then analyses HSV colour
of the surrounding region (where the climber's hands touch the holds/tape).
Clips with is_me=False are skipped.

Performance notes
-----------------
- cap.grab() for non-sample frames: avoids full BGR decode
- Batch pose inference: collect all sample frames, single session.run call
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
    preprocess_batch,
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
    (20,  35,  "노랑"),
    (36,  85,  "초록"),
    (86, 130,  "파랑"),
    (0,   10,  "빨강"),
    (170, 180, "빨강"),
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
    # Batch pose inference + colour voting
    # ------------------------------------------------------------------

    def _detect_color(self, clip_path: str, cfg: dict) -> str | None:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))
        max_samples = cfg["max_samples"]

        # Collect up to max_samples frames
        frames: list[np.ndarray] = []
        shapes: list[tuple[int, int]] = []
        frame_pos = 0

        while frame_pos < total_frames and len(frames) < max_samples:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
            shapes.append(frame.shape[:2])

            next_pos = frame_pos + sample_interval
            if next_pos >= total_frames or len(frames) >= max_samples:
                break

            # Skip non-sample frames without decoding
            for _ in range(next_pos - (frame_pos + 1)):
                if not cap.grab():
                    break

            frame_pos = next_pos

        cap.release()

        if not frames:
            return None

        # Single batch pose inference
        batch_blob, r_list, pad_list = preprocess_batch(frames, self._infer_h, self._infer_w)
        raw_batch = self._session.run(
            None, {self._session.get_inputs()[0].name: batch_blob}
        )[0]  # [N, 300, 57]

        color_votes: dict[str, float] = {}
        for i, (frame, shape, r, pad) in enumerate(zip(frames, shapes, r_list, pad_list)):
            fh, fw = shape
            persons = postprocess_pose(raw_batch[i:i+1], r, pad, shape, cfg["conf_threshold"])
            if len(persons) > 0:
                for cx_px, cy_px, vis in get_wrist_points(persons[0], fh, fw):
                    roi = _extract_roi(frame, cx_px, cy_px, fh, fw, cfg["roi_pad_ratio"])
                    if roi is not None:
                        color = _dominant_color(roi, cfg)
                        if color:
                            color_votes[color] = color_votes.get(color, 0.0) + vis

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

    black_ratio = np.count_nonzero(v_c < cfg["min_value"]) / max(h_c.size, 1)
    if black_ratio > 0.4:
        return "검정"

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
