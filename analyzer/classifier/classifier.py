"""Stage 3 — Classifier: success / fail determination for 'me' clips only.

Uses YOLO26n-pose ONNX to extract body keypoints from the last N seconds
of each clip, then decides success/fail based on vertical position.
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
    get_center_y,
)

logger = logging.getLogger(__name__)

_MODEL_PATH = os.environ.get(
    "YOLO26N_POSE_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "yolo26n-pose.onnx"),
)

_DEFAULTS = {
    "tail_seconds": 5,           # analyse last N seconds of clip
    "sample_fps": 2,             # frames per second to sample
    "success_y_threshold": 0.40, # normalised center_y < this → reached top
    "fall_dy_threshold": 0.15,   # sudden downward jump → fail
    "conf_threshold": 0.3,       # minimum pose detection confidence
}


class ClassifierStage(BaseStage):
    """Stage 3 — classify each 'me' clip as success or fail."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._session = load_session(_MODEL_PATH)
        inp = self._session.get_inputs()[0].shape
        self._infer_h = inp[2] if isinstance(inp[2], int) else 640
        self._infer_w = inp[3] if isinstance(inp[3], int) else 640

    @property
    def name(self) -> str:
        return "classifier"

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("classifier", {})}
        for clip in context.clips:
            if not clip.is_me:
                logger.debug("Classifier: skip clip %s (is_me=False)", clip.clip_id)
                continue
            if not clip.clip_path:
                clip.result = "fail"
                continue
            clip.result = self._classify(clip.clip_path, cfg)
            logger.info("Classifier: clip %s → %s", clip.clip_id, clip.result)
        return context

    # ------------------------------------------------------------------
    # Core classification
    # ------------------------------------------------------------------

    def _classify(self, clip_path: str, cfg: dict) -> str:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            return "fail"

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        # Seek to tail section
        tail_start_frame = max(0, total_frames - int(fps * cfg["tail_seconds"]))
        cap.set(cv2.CAP_PROP_POS_FRAMES, tail_start_frame)

        y_positions: list[float] = []
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample_interval == 0:
                fh, fw = frame.shape[:2]
                blob, r, pad = preprocess(frame, self._infer_h, self._infer_w)
                raw = self._session.run(None, {self._session.get_inputs()[0].name: blob})[0]
                persons = postprocess_pose(raw, r, pad, (fh, fw), cfg["conf_threshold"])
                if len(persons) > 0:
                    cy = get_center_y(persons[0], fh)
                    if cy is not None:
                        y_positions.append(cy)
            frame_idx += 1

        cap.release()

        if not y_positions:
            logger.warning("Classifier: no pose detected in %s", clip_path)
            return "fail"

        return _decide(y_positions, cfg)


def _decide(y_positions: list[float], cfg: dict) -> str:
    fall_thresh = cfg["fall_dy_threshold"]
    success_y = cfg["success_y_threshold"]

    min_y = min(y_positions)
    last_y = y_positions[-1]
    first_y = y_positions[0]

    # Sudden fall → fail
    for i in range(1, len(y_positions)):
        if y_positions[i] - y_positions[i - 1] > fall_thresh:
            return "fail"

    # Top reached
    if min_y < success_y:
        return "success"
    # Ended higher than started (sustained upward progress)
    if last_y < first_y - 0.05:
        return "success"
    # Final position in upper half
    if last_y < 0.50:
        return "success"

    return "fail"
