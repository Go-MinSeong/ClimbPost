from __future__ import annotations

import logging
import os
import subprocess
import uuid

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import ClipInfo, PipelineContext

logger = logging.getLogger(__name__)

# Default settings (overridable via config dict)
_DEFAULTS = {
    "sample_fps": 1,
    "min_climb_sec": 8,
    "buffer_sec": 2,
    "climb_threshold": 0.55,   # y < this = person is climbing (upper part of frame)
    "rest_threshold": 0.65,    # y > this = person is resting (lower part of frame)
    "gap_sec": 5,              # seconds of rest to end a climbing segment
}

_YOLO_MODEL_PATH = os.environ.get("YOLO_MODEL", "yolov8m-pose.pt")


class ClipperStage(BaseStage):
    """Stage 1 — detect climbing segments and extract clips with FFmpeg."""

    @property
    def name(self) -> str:
        return "clipper"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("clipper", {})}

        for video in context.raw_videos:
            logger.info("Clipper: processing %s (%s)", video.raw_video_id, video.file_path)
            segments = self._detect_segments(video.file_path, cfg)
            logger.info("Clipper: found %d raw segment(s)", len(segments))

            for start, end in segments:
                # Apply buffer and clamp to video bounds
                buf = cfg["buffer_sec"]
                clip_start = max(0.0, start - buf)
                clip_end = min(video.duration_sec, end + buf)
                duration = clip_end - clip_start

                if duration < cfg["min_climb_sec"]:
                    logger.debug("Clipper: skipping short segment %.1f–%.1f (%.1fs)", clip_start, clip_end, duration)
                    continue

                clip_id = uuid.uuid4().hex[:12]
                clip_dir = os.path.join(context.storage_root, context.session_id, "clips")
                os.makedirs(clip_dir, exist_ok=True)

                clip_path = os.path.join(clip_dir, f"{clip_id}.mp4")
                thumb_path = os.path.join(clip_dir, f"{clip_id}_thumb.jpg")

                self._extract_clip(video.file_path, clip_start, duration, clip_path)
                self._extract_thumbnail(clip_path, thumb_path)

                context.clips.append(
                    ClipInfo(
                        clip_id=clip_id,
                        raw_video_id=video.raw_video_id,
                        start_time=clip_start,
                        end_time=clip_end,
                        duration_sec=duration,
                        clip_path=clip_path,
                        thumbnail_path=thumb_path,
                    )
                )
                logger.info("Clipper: clip %s — %.1f–%.1fs (%.1fs)", clip_id, clip_start, clip_end, duration)

        return context

    # ------------------------------------------------------------------
    # Segment detection using YOLOv8-pose
    # ------------------------------------------------------------------

    def _detect_segments(self, video_path: str, cfg: dict) -> list[tuple[float, float]]:
        """Return list of (start_sec, end_sec) climbing segments.

        Strategy for fixed tripod camera:
        - Person's center-y < climb_threshold → they are on the wall (climbing)
        - Person's center-y > rest_threshold → they are on the ground (resting)
        - No pose detected → resting / between attempts
        - A climbing segment starts when person goes above climb_threshold
          and ends after gap_sec of being below rest_threshold or undetected.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error("Clipper: cannot open %s", video_path)
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        climb_thresh = cfg.get("climb_threshold", 0.55)
        rest_thresh = cfg.get("rest_threshold", 0.65)
        gap_sec = cfg.get("gap_sec", 5)
        gap_frames = int(gap_sec * cfg["sample_fps"])

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = YOLO(_YOLO_MODEL_PATH)

        climbing = False
        rest_count = 0
        seg_start_time = 0.0
        segments: list[tuple[float, float]] = []

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval != 0:
                frame_idx += 1
                continue

            t = frame_idx / fps
            results = model(frame, device=device, verbose=False)
            person_y = self._get_center_y(results[0]) if results else None

            is_climbing = person_y is not None and person_y < climb_thresh
            is_resting = person_y is None or person_y > rest_thresh

            if not climbing:
                if is_climbing:
                    climbing = True
                    rest_count = 0
                    seg_start_time = t
                    logger.debug("Clipper: climb START at %.1fs (y=%.3f)", t, person_y)
            else:
                if is_resting:
                    rest_count += 1
                    if rest_count >= gap_frames:
                        seg_end_time = t - gap_sec  # end before the gap
                        segments.append((seg_start_time, seg_end_time))
                        logger.debug("Clipper: climb END at %.1fs (gap)", seg_end_time)
                        climbing = False
                        rest_count = 0
                else:
                    rest_count = 0  # reset gap counter

            frame_idx += 1

        # Close open segment
        if climbing:
            segments.append((seg_start_time, (total_frames - 1) / fps))

        cap.release()
        return segments

    @staticmethod
    def _get_center_y(result) -> float | None:
        """Extract center_y from YOLOv8 pose result for one frame."""
        if result.keypoints is None or len(result.keypoints) == 0:
            return None
        # Take the first detected person
        kpts = result.keypoints.xy[0]  # shape (17, 2), pixel coords
        conf = result.keypoints.conf[0]  # shape (17,), confidence scores

        # Use shoulders [5,6] and hips [11,12]
        indices = [5, 6, 11, 12]
        ys = []
        h = result.orig_shape[0]  # frame height for normalization
        for idx in indices:
            if conf[idx] > 0.3:
                ys.append(float(kpts[idx, 1]) / h)

        if not ys:
            return None
        return float(np.mean(ys))

    # ------------------------------------------------------------------
    # FFmpeg helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_clip(src: str, start: float, duration: float, dst: str) -> None:
        """Cut a clip from src using FFmpeg."""
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

    @staticmethod
    def _extract_thumbnail(clip_path: str, thumb_path: str) -> None:
        """Extract a single frame from the middle of a clip as a JPEG thumbnail."""
        # Get clip duration
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            clip_path,
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        dur = float(result.stdout.strip())
        mid = dur / 2.0

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{mid:.3f}",
            "-i", clip_path,
            "-frames:v", "1",
            "-q:v", "2",
            thumb_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
