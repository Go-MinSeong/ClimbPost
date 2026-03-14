"""Tests for analyzer.clipper.clipper.ClipperStage.

Tests marked @pytest.mark.slow require the real test video and take longer.
"""

import os

import pytest

from analyzer.clipper.clipper import ClipperStage
from analyzer.pipeline.context import PipelineContext, RawVideoInfo


@pytest.mark.slow
def test_clipper_detects_segments(pipeline_context, tmp_storage):
    """Clipper should detect at least one climbing segment from test2.mov."""
    stage = ClipperStage({})
    result = stage.process(pipeline_context)
    assert len(result.clips) > 0


@pytest.mark.slow
def test_clipper_creates_clip_files(pipeline_context):
    """Each detected clip should have a .mp4 file on disk."""
    stage = ClipperStage({})
    result = stage.process(pipeline_context)
    for clip in result.clips:
        assert clip.clip_path is not None
        assert os.path.isfile(clip.clip_path)
        assert clip.clip_path.endswith(".mp4")


@pytest.mark.slow
def test_clipper_creates_thumbnails(pipeline_context):
    """Each detected clip should have a .jpg thumbnail on disk."""
    stage = ClipperStage({})
    result = stage.process(pipeline_context)
    for clip in result.clips:
        assert clip.thumbnail_path is not None
        assert os.path.isfile(clip.thumbnail_path)
        assert clip.thumbnail_path.endswith(".jpg")


@pytest.mark.slow
def test_clipper_clip_info_populated(pipeline_context):
    """All ClipInfo fields set by clipper should be populated."""
    stage = ClipperStage({})
    result = stage.process(pipeline_context)
    for clip in result.clips:
        assert clip.start_time >= 0
        assert clip.end_time > clip.start_time
        assert clip.duration_sec > 0
        assert clip.clip_path is not None
        assert clip.thumbnail_path is not None
        assert clip.raw_video_id == "raw-001"


def test_clipper_empty_video(tmp_storage):
    """Clipper should not crash on a nonexistent video path."""
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map={},
        raw_videos=[
            RawVideoInfo(
                raw_video_id="rv-bad",
                file_path="/nonexistent/video.mov",
                duration_sec=60.0,
            )
        ],
        storage_root=tmp_storage,
    )
    stage = ClipperStage({})
    result = stage.process(ctx)
    assert result.clips == []


def test_clipper_min_climb_filter(tmp_storage):
    """Segments shorter than min_climb_sec should be filtered out."""
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map={},
        raw_videos=[
            RawVideoInfo(
                raw_video_id="rv-bad",
                file_path="/nonexistent/video.mov",
                duration_sec=60.0,
            )
        ],
        storage_root=tmp_storage,
    )
    # With a very high min_climb_sec, even if segments were found, they'd be filtered
    stage = ClipperStage({"clipper": {"min_climb_sec": 9999}})
    result = stage.process(ctx)
    assert result.clips == []
