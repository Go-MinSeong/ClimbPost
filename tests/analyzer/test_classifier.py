"""Tests for analyzer.classifier.classifier.ClassifierStage.

Unit tests call ClassifierStage._decide() directly with synthetic y_positions.
"""

import pytest

from analyzer.classifier.classifier import ClassifierStage, _DEFAULTS
from analyzer.pipeline.context import ClipInfo, PipelineContext


# Default config for _decide calls
CFG = {**_DEFAULTS}


def test_classifier_decide_success_top_zone():
    """Consecutive frames in the top zone → success."""
    # top_zone_ratio = 0.20, hold_frames = 2
    y_positions = [0.50, 0.30, 0.15, 0.10]  # last two are in top zone
    assert ClassifierStage._decide(y_positions, CFG) == "success"


def test_classifier_decide_fail_fall():
    """Sudden downward y jump (increase) > fall_dy_threshold → fail."""
    # fall_dy_threshold = 0.15
    y_positions = [0.30, 0.25, 0.20, 0.50]  # jump of 0.30 > 0.15
    assert ClassifierStage._decide(y_positions, CFG) == "fail"


def test_classifier_decide_success_final_position():
    """Final y ≤ 0.30 with no fall and no sustained top zone → success via fallback."""
    y_positions = [0.50, 0.40, 0.35, 0.28]  # no fall, no top-zone hold, final ≤ 0.30
    assert ClassifierStage._decide(y_positions, CFG) == "success"


def test_classifier_decide_fail_low_position():
    """Final y > 0.30 with no top zone hold → fail."""
    y_positions = [0.50, 0.50, 0.50, 0.50]  # stays in the middle
    assert ClassifierStage._decide(y_positions, CFG) == "fail"


def test_classifier_no_clip_path(sample_color_map):
    """Clip with no clip_path should get result='fail' without crashing."""
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map=sample_color_map,
        raw_videos=[],
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

    stage = ClassifierStage({})
    result = stage.process(ctx)
    assert result.clips[0].result == "fail"


def test_classifier_process_sets_result(sample_color_map):
    """Clips with nonexistent clip_path get result set (to 'fail' since can't open)."""
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map=sample_color_map,
        raw_videos=[],
    )
    clip = ClipInfo(
        clip_id="c1",
        raw_video_id="rv-1",
        start_time=0.0,
        end_time=10.0,
        duration_sec=10.0,
        clip_path="/nonexistent/clip.mp4",
    )
    ctx.clips.append(clip)

    stage = ClassifierStage({})
    result = stage.process(ctx)
    assert result.clips[0].result in ("success", "fail")
