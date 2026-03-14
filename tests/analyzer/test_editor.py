"""Tests for analyzer.editor.editor.EditorStage.

Tests that use ffmpeg on real clips are marked @pytest.mark.slow.
"""

import os
import subprocess

import pytest

from analyzer.editor.editor import EditorStage
from analyzer.pipeline.context import ClipInfo, PipelineContext


@pytest.mark.slow
def test_editor_crops_to_3x4(pipeline_context):
    """Edited output should have dimensions 1080x1440."""
    # First run clipper to get real clips
    from analyzer.clipper.clipper import ClipperStage

    clipper = ClipperStage({})
    ctx = clipper.process(pipeline_context)
    assert len(ctx.clips) > 0, "Clipper must produce at least one clip"

    editor = EditorStage({})
    ctx = editor.process(ctx)

    for clip in ctx.clips:
        if not clip.edited_path:
            continue
        w, h, _ = EditorStage._probe(clip.edited_path)
        assert w == 1080
        assert h == 1440


@pytest.mark.slow
def test_editor_trims_to_60s(pipeline_context):
    """Edited output duration should be ≤ 60s."""
    from analyzer.clipper.clipper import ClipperStage

    clipper = ClipperStage({})
    ctx = clipper.process(pipeline_context)

    editor = EditorStage({})
    ctx = editor.process(ctx)

    for clip in ctx.clips:
        if not clip.edited_path:
            continue
        _, _, dur = EditorStage._probe(clip.edited_path)
        assert dur <= 60.0 + 0.5  # small tolerance for codec frame rounding


@pytest.mark.slow
def test_editor_creates_output_file(pipeline_context):
    """Edited file should exist on disk."""
    from analyzer.clipper.clipper import ClipperStage

    clipper = ClipperStage({})
    ctx = clipper.process(pipeline_context)

    editor = EditorStage({})
    ctx = editor.process(ctx)

    for clip in ctx.clips:
        if clip.edited_path:
            assert os.path.isfile(clip.edited_path)


def test_editor_no_clip_path(tmp_storage, sample_color_map):
    """Clip with no clip_path should be skipped gracefully."""
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map=sample_color_map,
        raw_videos=[],
        storage_root=tmp_storage,
    )
    clip = ClipInfo(
        clip_id="c1",
        raw_video_id="rv-1",
        start_time=0.0,
        end_time=10.0,
        duration_sec=10.0,
        clip_path=None,
    )
    ctx.clips.append(clip)

    stage = EditorStage({})
    result = stage.process(ctx)
    assert result.clips[0].edited_path is None


@pytest.mark.slow
def test_editor_probe(pipeline_context):
    """Probe of edited clip returns correct dimensions."""
    from analyzer.clipper.clipper import ClipperStage

    clipper = ClipperStage({})
    ctx = clipper.process(pipeline_context)
    assert len(ctx.clips) > 0

    editor = EditorStage({})
    ctx = editor.process(ctx)

    for clip in ctx.clips:
        if not clip.edited_path:
            continue
        w, h, dur = EditorStage._probe(clip.edited_path)
        assert w == 1080
        assert h == 1440
        assert dur > 0
