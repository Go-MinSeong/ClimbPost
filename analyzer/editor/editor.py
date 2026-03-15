from __future__ import annotations

import logging
import os
import subprocess

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)

# Default settings (overridable via config dict)
_DEFAULTS = {
    "output_width": 1080,
    "output_height": 1440,       # 3:4 aspect ratio
    "max_duration_sec": 60,
    "video_codec": "libx264",
    "crf": 18,                   # quality (lower = better, 18 is visually lossless)
    "preset": "medium",
}


class EditorStage(BaseStage):
    """Stage 5 — crop clips to 3:4 vertical and trim to max 60 seconds.

    Processing steps:
      1. Probe the source clip for dimensions and duration.
      2. Compute a centre crop to achieve 3:4 aspect ratio.
      3. Scale to 1080×1440.
      4. Trim to at most 60 seconds.
      5. Write the edited file to storage_root/edited/{session_id}/{clip_id}_edited.mp4.
    """

    @property
    def name(self) -> str:
        return "editor"

    def process(self, context: PipelineContext) -> PipelineContext:
        cfg = {**_DEFAULTS, **self.config.get("editor", {})}

        out_dir = os.path.join(context.storage_root, "edited", context.session_id)
        os.makedirs(out_dir, exist_ok=True)

        for clip in context.clips:
            if not clip.clip_path:
                logger.warning("Editor: clip %s has no file path, skipping", clip.clip_id)
                continue

            out_path = os.path.join(out_dir, f"{clip.clip_id}_edited.mp4")

            try:
                self._edit_clip(clip.clip_path, out_path, cfg)
                clip.edited_path = out_path
                logger.info("Editor: clip %s → %s", clip.clip_id, out_path)
            except subprocess.CalledProcessError:
                logger.error("Editor: FFmpeg failed for clip %s", clip.clip_id)
            except Exception:
                logger.exception("Editor: unexpected error for clip %s", clip.clip_id)

        return context

    # ------------------------------------------------------------------
    # Core editing logic
    # ------------------------------------------------------------------

    def _edit_clip(self, src: str, dst: str, cfg: dict) -> None:
        """Crop, scale, and trim a single clip using FFmpeg."""
        src_w, src_h, src_dur = self._probe(src)

        out_w = cfg["output_width"]
        out_h = cfg["output_height"]
        max_dur = cfg["max_duration_sec"]
        target_ratio = out_w / out_h  # 0.75 for 3:4

        # Compute crop dimensions to achieve target aspect ratio
        src_ratio = src_w / src_h if src_h > 0 else 1.0

        if src_ratio > target_ratio:
            # Source is wider than target — crop width (left/right)
            crop_h = src_h
            crop_w = int(src_h * target_ratio)
        else:
            # Source is taller than target — crop height (top/bottom)
            crop_w = src_w
            crop_h = int(src_w / target_ratio)

        # Centre crop offsets
        crop_x = (src_w - crop_w) // 2
        crop_y = (src_h - crop_h) // 2

        # Build FFmpeg filter: crop → scale
        vf = (
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
            f"scale={out_w}:{out_h},format=yuv420p"
        )

        # Duration limit
        duration = min(src_dur, max_dur)

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-t", f"{duration:.3f}",
            "-vf", vf,
            "-c:v", cfg["video_codec"],
            "-pix_fmt", "yuv420p",       # 8-bit for iOS compatibility
            "-color_primaries", "bt709",  # SDR color metadata (iPhone HDR → SDR)
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            "-crf", str(cfg["crf"]),
            "-preset", cfg["preset"],
            "-an",  # strip audio
            "-movflags", "+faststart",
            dst,
        ]

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    # ------------------------------------------------------------------
    # FFmpeg probe helper
    # ------------------------------------------------------------------

    @staticmethod
    def _probe(path: str) -> tuple[int, int, float]:
        """Return (width, height, duration_sec) for a video file."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-show_entries", "format=duration",
            "-of", "csv=p=0:s=,",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # ffprobe may output multiple lines; first line has stream info
        lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]

        width = 0
        height = 0
        duration = 0.0

        if lines:
            parts = lines[0].split(",")
            # Stream line: width,height[,duration]
            if len(parts) >= 2:
                width = int(parts[0])
                height = int(parts[1])
            if len(parts) >= 3 and parts[2] != "N/A":
                duration = float(parts[2])

        # If stream duration was N/A, try format duration (second line)
        if duration == 0.0 and len(lines) > 1:
            try:
                duration = float(lines[1].strip(","))
            except (ValueError, IndexError):
                pass

        return width, height, duration
