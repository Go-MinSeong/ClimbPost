"""Tests for analyzer.pipeline.context data classes."""

from analyzer.pipeline.context import ClipInfo, PipelineContext, RawVideoInfo


def test_raw_video_info_creation():
    rv = RawVideoInfo(raw_video_id="rv-1", file_path="/tmp/v.mov", duration_sec=120.5)
    assert rv.raw_video_id == "rv-1"
    assert rv.file_path == "/tmp/v.mov"
    assert rv.duration_sec == 120.5


def test_clip_info_defaults():
    clip = ClipInfo(
        clip_id="c1",
        raw_video_id="rv-1",
        start_time=0.0,
        end_time=10.0,
        duration_sec=10.0,
    )
    assert clip.clip_path is None
    assert clip.difficulty is None
    assert clip.tape_color is None
    assert clip.result is None
    assert clip.is_me is None
    assert clip.thumbnail_path is None
    assert clip.edited_path is None


def test_pipeline_context_empty_clips():
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map={},
        raw_videos=[],
    )
    assert ctx.clips == []
    assert ctx.storage_root == "./data/storage"
