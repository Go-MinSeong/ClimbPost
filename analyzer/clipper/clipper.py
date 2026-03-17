from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from boxmot import ByteTrack

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import ClipInfo, PipelineContext

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "sample_fps": 10,            # inference FPS (10 or 15 recommended)
    "climb_threshold": 0.65,     # center_y < this → person is climbing
    "gap_tolerance_sec": 3.0,    # non-climbing gap allowed within a segment
    "padding_sec": 2.0,          # seconds added before/after segment
    "min_clip_sec": 10.0,        # discard clips shorter than this
    "max_clip_sec": 180.0,       # discard clips longer than this
    "conf_threshold": 0.3,       # minimum detection confidence
    "nms_threshold": 0.45,       # NMS IoU threshold
}

_MODEL_PATH = os.environ.get(
    "YOLO26N_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "yolo26n.onnx"),
)
_INFER_SIZE = 640


class ClipperStage(BaseStage):
    """Stage 1 — per-person climbing segment detection via YOLO26n-ONNX + ByteTrack."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self._session = ort.InferenceSession(_MODEL_PATH, providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        inp_shape = self._session.get_inputs()[0].shape
        self._infer_h = inp_shape[2] if isinstance(inp_shape[2], int) else _INFER_SIZE
        self._infer_w = inp_shape[3] if isinstance(inp_shape[3], int) else _INFER_SIZE

    @property
    def name(self) -> str:
        return "clipper"

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("clipper", {})}
        for video in context.raw_videos:
            logger.info("Clipper: processing %s (%s)", video.raw_video_id, video.file_path)
            segments = self._detect_segments(video.file_path, video.duration_sec, cfg)
            logger.info("Clipper: %d valid segment(s) found", len(segments))
            for track_id, start, end in segments:
                clip_id = uuid.uuid4().hex[:12]
                clip_dir = os.path.join(context.storage_root, context.session_id, "clips")
                os.makedirs(clip_dir, exist_ok=True)
                clip_path = os.path.join(clip_dir, f"{clip_id}.mp4")
                self._extract_clip(video.file_path, start, end - start, clip_path)
                context.clips.append(
                    ClipInfo(
                        clip_id=clip_id,
                        raw_video_id=video.raw_video_id,
                        start_time=start,
                        end_time=end,
                        duration_sec=end - start,
                        clip_path=clip_path,
                    )
                )
                logger.info(
                    "Clipper: clip %s  track=%d  %.1f–%.1fs (%.1fs)",
                    clip_id, track_id, start, end, end - start,
                )
        return context

    # ------------------------------------------------------------------
    # Segment detection
    # ------------------------------------------------------------------

    def _detect_segments(
        self, video_path: str, duration_sec: float, cfg: dict
    ) -> list[tuple[int, float, float]]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error("Clipper: cannot open %s", video_path)
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        tracker = ByteTrack(
            track_thresh=cfg["conf_threshold"],
            track_buffer=int(cfg["gap_tolerance_sec"] * cfg["sample_fps"]),
            match_thresh=0.8,
            frame_rate=int(cfg["sample_fps"]),
        )

        # track_id → sorted list of timestamps where person was in climbing zone
        climbing_times: dict[int, list[float]] = {}

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                t = frame_idx / fps
                frame_h = frame.shape[0]
                dets = self._infer_person(frame, cfg)
                tracks = tracker.update(dets, frame)

                for track in tracks:
                    x1, y1, x2, y2 = track[0], track[1], track[2], track[3]
                    tid = int(track[4])
                    center_y = ((y1 + y2) / 2) / frame_h
                    if center_y < cfg["climb_threshold"]:
                        climbing_times.setdefault(tid, []).append(t)

            frame_idx += 1

        cap.release()
        return _build_segments(climbing_times, duration_sec, cfg)

    # ------------------------------------------------------------------
    # ONNX inference
    # ------------------------------------------------------------------

    def _infer_person(self, frame: np.ndarray, cfg: dict) -> np.ndarray:
        """Run YOLO26n on frame, return person detections [N, 6] (x1,y1,x2,y2,conf,cls)."""
        h, w = frame.shape[:2]
        blob, r, pad = _preprocess(frame, self._infer_h, self._infer_w)
        raw = self._session.run(None, {self._input_name: blob})[0]
        return _postprocess(raw, r, pad, (h, w), cfg)

    # ------------------------------------------------------------------
    # FFmpeg helper
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_clip(src: str, start: float, duration: float, dst: str) -> None:
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", src,
            "-t", f"{duration:.3f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            dst,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


# ------------------------------------------------------------------
# Module-level helpers (pure functions, easier to test)
# ------------------------------------------------------------------

def _preprocess(
    frame: np.ndarray, target_h: int, target_w: int
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Letterbox resize → [1, 3, H, W] float32 normalized to [0, 1]."""
    h, w = frame.shape[:2]
    r = min(target_h / h, target_w / w)
    new_h, new_w = int(h * r), int(w * r)
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_h = target_h - new_h
    pad_w = target_w - new_w
    top, left = pad_h // 2, pad_w // 2
    bottom, right = pad_h - top, pad_w - left
    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )

    blob = padded[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    return np.expand_dims(blob, 0), r, (left, top)


def _postprocess(
    output: np.ndarray,
    r: float,
    pad: tuple[int, int],
    orig_shape: tuple[int, int],
    cfg: dict,
) -> np.ndarray:
    """Decode YOLO26n ONNX output → person detections [M, 6].

    Supports two common ultralytics ONNX output layouts:
      • [1, 84, N] — raw anchor predictions (cx, cy, w, h + 80 class scores)
      • [1, N, 6]  — post-NMS predictions   (x1, y1, x2, y2, conf, cls)
    """
    conf_thresh = cfg["conf_threshold"]
    nms_thresh = cfg["nms_threshold"]
    orig_h, orig_w = orig_shape
    pad_x, pad_y = pad

    # Detect layout: [1, N, 6] post-NMS  vs  [1, 84, N] raw anchors
    if output.ndim == 3 and output.shape[2] == 6:
        # Post-NMS layout [1, N, 6]: filter person class (cls == 0)
        preds = output[0]  # [N, 6]
        person_mask = (preds[:, 5] == 0) & (preds[:, 4] >= conf_thresh)
        preds = preds[person_mask]
        if len(preds) == 0:
            return np.empty((0, 6), dtype=np.float32)
        x1 = np.clip((preds[:, 0] - pad_x) / r, 0, orig_w)
        y1 = np.clip((preds[:, 1] - pad_y) / r, 0, orig_h)
        x2 = np.clip((preds[:, 2] - pad_x) / r, 0, orig_w)
        y2 = np.clip((preds[:, 3] - pad_y) / r, 0, orig_h)
        return np.stack([x1, y1, x2, y2, preds[:, 4], preds[:, 5]], axis=1).astype(np.float32)

    # Raw layout [1, 84, N]
    preds = output[0].T  # [N, 84]
    person_conf = preds[:, 4]  # class index 0 score (cx,cy,w,h at 0:4)
    mask = person_conf >= conf_thresh
    if not mask.any():
        return np.empty((0, 6), dtype=np.float32)

    preds = preds[mask]
    scores = person_conf[mask]
    cx, cy, bw, bh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    x1 = np.clip((cx - bw / 2 - pad_x) / r, 0, orig_w)
    y1 = np.clip((cy - bh / 2 - pad_y) / r, 0, orig_h)
    x2 = np.clip((cx + bw / 2 - pad_x) / r, 0, orig_w)
    y2 = np.clip((cy + bh / 2 - pad_y) / r, 0, orig_h)

    boxes_xywh = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
    indices = cv2.dnn.NMSBoxes(boxes_xywh, scores.tolist(), conf_thresh, nms_thresh)
    if len(indices) == 0:
        return np.empty((0, 6), dtype=np.float32)

    idx = indices.flatten()
    return np.stack(
        [x1[idx], y1[idx], x2[idx], y2[idx], scores[idx], np.zeros(len(idx), dtype=np.float32)],
        axis=1,
    ).astype(np.float32)


def _build_segments(
    climbing_times: dict[int, list[float]],
    duration_sec: float,
    cfg: dict,
) -> list[tuple[int, float, float]]:
    """Merge per-track climbing timestamps into (track_id, start, end) segments."""
    gap = cfg["gap_tolerance_sec"]
    pad = cfg["padding_sec"]
    min_dur = cfg["min_clip_sec"]
    max_dur = cfg["max_clip_sec"]

    raw_segments: list[tuple[int, float, float]] = []
    for tid, times in climbing_times.items():
        if not times:
            continue
        times.sort()
        seg_start = seg_end = times[0]
        for t in times[1:]:
            if t - seg_end <= gap:
                seg_end = t
            else:
                raw_segments.append((tid, seg_start, seg_end))
                seg_start = seg_end = t
        raw_segments.append((tid, seg_start, seg_end))

    valid: list[tuple[int, float, float]] = []
    for tid, start, end in raw_segments:
        start = max(0.0, start - pad)
        end = min(duration_sec, end + pad)
        dur = end - start
        if min_dur <= dur <= max_dur:
            valid.append((tid, start, end))
        else:
            logger.debug(
                "Clipper: track %d segment %.1f–%.1fs (%.1fs) filtered", tid, start, end, dur
            )
    return valid
