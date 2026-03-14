from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawVideoInfo:
    raw_video_id: str
    file_path: str
    duration_sec: float


@dataclass
class ClipInfo:
    clip_id: str
    raw_video_id: str
    start_time: float
    end_time: float
    duration_sec: float
    clip_path: str | None = None
    difficulty: str | None = None
    tape_color: str | None = None
    result: str | None = None       # "success" | "fail"
    is_me: bool | None = None
    thumbnail_path: str | None = None
    edited_path: str | None = None


@dataclass
class PipelineContext:
    session_id: str
    gym_id: str
    color_map: dict
    raw_videos: list[RawVideoInfo]
    clips: list[ClipInfo] = field(default_factory=list)
    storage_root: str = "./data/storage"
