"""Tests for analyzer.identifier.identifier.IdentifierStage."""

import pytest

from analyzer.identifier.identifier import IdentifierStage
from analyzer.pipeline.context import ClipInfo, PipelineContext


def _make_context_with_clips(n_clips, tmp_storage, sample_color_map, clip_path=None):
    """Helper to create a context with n ClipInfo entries."""
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map=sample_color_map,
        raw_videos=[],
        storage_root=tmp_storage,
    )
    for i in range(n_clips):
        ctx.clips.append(
            ClipInfo(
                clip_id=f"clip-{i:03d}",
                raw_video_id="rv-1",
                start_time=float(i * 10),
                end_time=float(i * 10 + 10),
                duration_sec=10.0,
                clip_path=clip_path,
            )
        )
    return ctx


def test_identifier_single_clip(tmp_storage, sample_color_map):
    """A single clip should be marked as is_me=True (≤1 valid clips fallback)."""
    ctx = _make_context_with_clips(1, tmp_storage, sample_color_map)
    stage = IdentifierStage({})
    result = stage.process(ctx)
    assert result.clips[0].is_me is True


def test_identifier_no_clips(tmp_storage, sample_color_map):
    """No clips should return context unchanged."""
    ctx = _make_context_with_clips(0, tmp_storage, sample_color_map)
    stage = IdentifierStage({})
    result = stage.process(ctx)
    assert result.clips == []


def test_identifier_all_noise(tmp_storage, sample_color_map):
    """Clips without clip_path (no features extractable) → fallback marks all as is_me=True."""
    ctx = _make_context_with_clips(3, tmp_storage, sample_color_map, clip_path=None)
    stage = IdentifierStage({})
    result = stage.process(ctx)
    for clip in result.clips:
        assert clip.is_me is True


def test_identifier_process_sets_is_me(tmp_storage, sample_color_map):
    """Clips with nonexistent paths produce no features → fallback to all is_me=True."""
    ctx = _make_context_with_clips(
        3, tmp_storage, sample_color_map, clip_path="/nonexistent/clip.mp4"
    )
    stage = IdentifierStage({})
    result = stage.process(ctx)
    for clip in result.clips:
        assert clip.is_me is True
