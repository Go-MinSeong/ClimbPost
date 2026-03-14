import os
import subprocess

import pytest

from analyzer.pipeline.context import ClipInfo, PipelineContext, RawVideoInfo

TEST_VIDEO = "/Users/song/Desktop/geun1/climbPost/test2.mov"


@pytest.fixture
def test_video_path():
    return TEST_VIDEO


@pytest.fixture
def tmp_storage(tmp_path):
    return str(tmp_path)


@pytest.fixture
def sample_color_map():
    return {
        "gym_id": "gym_001",
        "mapping": {
            "노랑": "V0-V1",
            "초록": "V2-V3",
            "파랑": "V4-V5",
            "빨강": "V6-V7",
            "검정": "V8+",
        },
    }


@pytest.fixture
def pipeline_context(test_video_path, tmp_storage, sample_color_map):
    """Full PipelineContext pointing at the real test video."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            test_video_path,
        ],
        capture_output=True,
        text=True,
    )
    duration = float(result.stdout.strip())

    return PipelineContext(
        session_id="test-session-001",
        gym_id="gym_001",
        color_map=sample_color_map,
        raw_videos=[
            RawVideoInfo(
                raw_video_id="raw-001",
                file_path=test_video_path,
                duration_sec=duration,
            )
        ],
        storage_root=tmp_storage,
    )


@pytest.fixture
def make_clip_info():
    """Factory fixture that creates a ClipInfo with sensible defaults."""
    def _make(**overrides):
        defaults = dict(
            clip_id="clip-001",
            raw_video_id="raw-001",
            start_time=0.0,
            end_time=10.0,
            duration_sec=10.0,
        )
        defaults.update(overrides)
        return ClipInfo(**defaults)
    return _make
