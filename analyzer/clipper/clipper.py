"""Stage 1 — Clipper: per-person climbing segment detection and clip extraction.

Uses YOLO26n-ONNX for person detection and ByteTrack for tracking.
Segments are detected by monitoring each tracked person's vertical position.
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
from analyzer.pipeline.onnx_infer import load_session, preprocess, postprocess_det

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "sample_fps": 10,            # inference FPS (10 or 15 recommended)
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

        climbing_times: dict[int, list[float]] = {}
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample_interval == 0:
                t = frame_idx / fps
                fh = frame.shape[0]
                blob, r, pad = preprocess(frame, self._infer_h, self._infer_w)
                raw = self._session.run(None, {self._session.get_inputs()[0].name: blob})[0]
                dets = postprocess_det(raw, r, pad, (fh, frame.shape[1]), cfg["conf_threshold"])
                tracks = tracker.update(dets, frame)
                for track in tracks:
                    tid = int(track[4])
                    center_y = ((track[1] + track[3]) / 2) / fh
                    if center_y < cfg["climb_threshold"]:
                        climbing_times.setdefault(tid, []).append(t)
            frame_idx += 1

        cap.release()
        return _build_segments(climbing_times, duration_sec, cfg)

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
# Module-level helper
# ------------------------------------------------------------------

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
