from __future__ import annotations

import logging
import os
import subprocess
import uuid

import cv2
import mediapipe as mp
import numpy as np

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import ClipInfo, PipelineContext

logger = logging.getLogger(__name__)

# Default settings (overridable via config dict)
_DEFAULTS = {
    "sample_fps": 2,
    "min_climb_sec": 5,
    "buffer_sec": 3,
    "motion_threshold": 0.02,
    "still_frames": 4,
}


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
    # Segment detection using MediaPipe Pose
    # ------------------------------------------------------------------

    def _detect_segments(self, video_path: str, cfg: dict) -> list[tuple[float, float]]:
        """Return list of (start_sec, end_sec) climbing segments."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error("Clipper: cannot open %s", video_path)
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = max(1, int(fps / cfg["sample_fps"]))

        pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        prev_y: float | None = None
        climbing = False
        still_count = 0
        seg_start_frame = 0
        segments: list[tuple[float, float]] = []

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval != 0:
                frame_idx += 1
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)

            person_y = self._get_center_y(results)

            if person_y is not None and prev_y is not None:
                dy = abs(person_y - prev_y)
                moving = dy > cfg["motion_threshold"]

                if not climbing and moving:
                    climbing = True
                    still_count = 0
                    seg_start_frame = frame_idx
                elif climbing:
                    if moving:
                        still_count = 0
                    else:
                        still_count += 1
                        if still_count >= cfg["still_frames"]:
                            segments.append(
                                (seg_start_frame / fps, frame_idx / fps)
                            )
                            climbing = False
                            still_count = 0

            prev_y = person_y
            frame_idx += 1

        # Close open segment at end of video
        if climbing:
            segments.append((seg_start_frame / fps, (total_frames - 1) / fps))

        pose.close()
        cap.release()
        return segments

    @staticmethod
    def _get_center_y(results) -> float | None:
        """Return normalized y-center of detected pose landmarks, or None."""
        if not results.pose_landmarks:
            return None
        ys = [lm.y for lm in results.pose_landmarks.landmark if lm.visibility > 0.5]
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
