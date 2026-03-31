"""Stage 3 — Classifier: success / fail determination for 'me' clips only.

Uses YOLO26n-pose ONNX to extract body keypoints from the last N seconds
of each clip, then decides success/fail based on vertical position.
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
    # Batch pose inference over tail section
    # ------------------------------------------------------------------

    def _classify(self, clip_path: str, cfg: dict) -> str:
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            return "fail"

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        tail_start = max(0, total_frames - int(fps * cfg["tail_seconds"]))
        cap.set(cv2.CAP_PROP_POS_FRAMES, tail_start)

        # Collect all sample frames from the tail section
        frames: list[np.ndarray] = []
        shapes: list[tuple[int, int]] = []
        frame_pos = tail_start

        while frame_pos < total_frames:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
            shapes.append(frame.shape[:2])

            next_pos = frame_pos + sample_interval
            if next_pos >= total_frames:
                break

            # Skip non-sample frames without decoding
            for _ in range(next_pos - (frame_pos + 1)):
                if not cap.grab():
                    break

            frame_pos = next_pos

        cap.release()

        if not frames:
            logger.warning("Classifier: no frames collected from %s", clip_path)
            return "fail"

        # Single batch pose inference
        batch_blob, r_list, pad_list = preprocess_batch(frames, self._infer_h, self._infer_w)
        raw_batch = self._session.run(
            None, {self._session.get_inputs()[0].name: batch_blob}
        )[0]  # [N, 300, 57]

        y_positions: list[float] = []
        for i, (shape, r, pad) in enumerate(zip(shapes, r_list, pad_list)):
            persons = postprocess_pose(raw_batch[i:i+1], r, pad, shape, cfg["conf_threshold"])
            if len(persons) > 0:
                cy = get_center_y(persons[0], shape[0])
                if cy is not None:
                    y_positions.append(cy)

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

    for i in range(1, len(y_positions)):
        if y_positions[i] - y_positions[i - 1] > fall_thresh:
            return "fail"

    if min_y < success_y:
        return "success"
    if last_y < first_y - 0.05:
        return "success"
    if last_y < 0.50:
        return "success"

    return "fail"
