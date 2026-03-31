"""Stage 1 — Clipper: per-person climbing segment detection and clip extraction.

Uses YOLO26n-ONNX for person detection and ByteTrack for tracking.
Segments are detected by monitoring each tracked person's vertical position.

Performance notes
-----------------
- sample_fps=5: process every 6th frame at 30fps → half the YOLO calls vs 10fps
- cap.grab() for skipped frames: avoids full BGR decode on non-sample frames
- Batch YOLO inference (_INFER_BATCH frames per session.run call): amortises
  CUDA kernel-launch overhead across a mini-batch
"""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path

import cv2
import numpy as np
from boxmot import ByteTrack

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import ClipInfo, PipelineContext
from analyzer.pipeline.onnx_infer import load_session, preprocess_batch, postprocess_det

logger = logging.getLogger(__name__)

_INFER_BATCH = 8   # frames per YOLO session.run call

_DEFAULTS = {
    "sample_fps": 5,             # inference FPS — halved from 10; 0.2s resolution is fine
    "climb_threshold": 0.65,     # center_y < this → person is climbing
    "gap_tolerance_sec": 3.0,    # non-climbing gap allowed within a segment
    "padding_before_sec": 5.0,   # seconds prepended before detected segment start
    "padding_after_sec": 2.0,    # seconds appended after detected segment end
    "min_clip_sec": 10.0,        # discard clips shorter than this
    "max_clip_sec": 180.0,       # discard clips longer than this
    "conf_threshold": 0.3,       # minimum detection confidence
    "nms_threshold": 0.45,       # NMS IoU threshold (kept for API compat)
}

_MODEL_PATH = os.environ.get(
    "YOLO26N_ONNX",
    str(Path(__file__).resolve().parent.parent / "models" / "yolo26n.onnx"),
)


class ClipperStage(BaseStage):
    """Stage 1 — per-person climbing segment detection via YOLO26n-ONNX + ByteTrack."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._session = load_session(_MODEL_PATH)
        inp = self._session.get_inputs()[0].shape
        self._infer_h = inp[2] if isinstance(inp[2], int) else 640
        self._infer_w = inp[3] if isinstance(inp[3], int) else 640

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
    # Segment detection — grab()-based skip + batch YOLO
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

        climbing_times: dict[int, list[float]] = {}

        # Accumulator for batch inference
        batch: list[tuple[float, np.ndarray, tuple[int, int]]] = []  # (t, frame, shape)
        frame_idx = 0

        while True:
            is_sample = (frame_idx % sample_interval == 0)
            if is_sample:
                ret, frame = cap.read()
                if not ret:
                    break
                t = frame_idx / fps
                batch.append((t, frame, frame.shape[:2]))

                if len(batch) >= _INFER_BATCH:
                    _run_batch(self._session, self._infer_h, self._infer_w,
                               batch, tracker, climbing_times, cfg)
                    batch = []
            else:
                if not cap.grab():
                    break
            frame_idx += 1

        # Flush remaining frames
        if batch:
            _run_batch(self._session, self._infer_h, self._infer_w,
                       batch, tracker, climbing_times, cfg)

        cap.release()
        return _build_segments(climbing_times, duration_sec, cfg)

    # ------------------------------------------------------------------
    # FFmpeg clip extraction
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
# Module-level helpers
# ------------------------------------------------------------------

def _run_batch(
    session,
    infer_h: int,
    infer_w: int,
    batch: list[tuple[float, np.ndarray, tuple[int, int]]],
    tracker: ByteTrack,
    climbing_times: dict[int, list[float]],
    cfg: dict,
) -> None:
    """Run YOLO on a mini-batch, then feed results to ByteTrack sequentially."""
    frames = [f for _, f, _ in batch]
    shapes = [s for _, _, s in batch]

    blob, r_list, pad_list = preprocess_batch(frames, infer_h, infer_w)
    raw = session.run(None, {session.get_inputs()[0].name: blob})[0]  # [N, 300, 6]

    for i, (t, frame, shape) in enumerate(batch):
        fh = shape[0]
        dets = postprocess_det(raw[i:i+1], r_list[i], pad_list[i], shape, cfg["conf_threshold"])
        tracks = tracker.update(dets, frame)
        for track in tracks:
            tid = int(track[4])
            center_y = ((track[1] + track[3]) / 2) / fh
            if center_y < cfg["climb_threshold"]:
                climbing_times.setdefault(tid, []).append(t)


def _build_segments(
    climbing_times: dict[int, list[float]],
    duration_sec: float,
    cfg: dict,
) -> list[tuple[int, float, float]]:
    """Merge per-track climbing timestamps into (track_id, start, end) segments."""
    gap = cfg["gap_tolerance_sec"]
    pad_before = cfg["padding_before_sec"]
    pad_after = cfg["padding_after_sec"]
    min_dur = cfg["min_clip_sec"]
    max_dur = cfg["max_clip_sec"]

    raw: list[tuple[int, float, float]] = []
    for tid, times in climbing_times.items():
        times.sort()
        seg_start = seg_end = times[0]
        for t in times[1:]:
            if t - seg_end <= gap:
                seg_end = t
            else:
                raw.append((tid, seg_start, seg_end))
                seg_start = seg_end = t
        raw.append((tid, seg_start, seg_end))

    valid: list[tuple[int, float, float]] = []
    for tid, start, end in raw:
        start = max(0.0, start - pad_before)
        end = min(duration_sec, end + pad_after)
        dur = end - start
        if min_dur <= dur <= max_dur:
            valid.append((tid, start, end))
        else:
            logger.debug(
                "Clipper: track %d segment %.1f–%.1fs (%.1fs) filtered", tid, start, end, dur
            )
    return valid
