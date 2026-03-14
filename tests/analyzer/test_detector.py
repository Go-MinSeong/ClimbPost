"""Tests for analyzer.detector.detector.DetectorStage.

Unit tests create synthetic numpy arrays with known HSV values.
"""

import numpy as np
import pytest

from analyzer.detector.detector import DetectorStage, _DEFAULTS, _HSV_COLOR_TABLE
from analyzer.pipeline.context import ClipInfo, PipelineContext


CFG = {**_DEFAULTS}


def _make_bgr_from_hsv(h, s, v, size=50):
    """Create a uniform BGR image from a single HSV colour."""
    import cv2
    hsv_img = np.full((size, size, 3), [h, s, v], dtype=np.uint8)
    bgr = cv2.cvtColor(hsv_img, cv2.COLOR_HSV2BGR)
    return bgr


def test_detector_dominant_color_yellow():
    """HSV hue ~25 (within 20-35) with good saturation → '노랑'."""
    roi = _make_bgr_from_hsv(h=25, s=200, v=200)
    result = DetectorStage._dominant_color_in_roi(roi, CFG)
    assert result == "노랑"


def test_detector_dominant_color_blue():
    """HSV hue ~100 (within 86-130) with good saturation → '파랑'."""
    roi = _make_bgr_from_hsv(h=100, s=200, v=200)
    result = DetectorStage._dominant_color_in_roi(roi, CFG)
    assert result == "파랑"


def test_detector_dominant_color_black():
    """Low V (brightness) regardless of hue → '검정'."""
    roi = _make_bgr_from_hsv(h=0, s=0, v=20)
    result = DetectorStage._dominant_color_in_roi(roi, CFG)
    assert result == "검정"


def test_detector_dominant_color_green():
    """HSV hue ~60 (within 36-85) → '초록'."""
    roi = _make_bgr_from_hsv(h=60, s=200, v=200)
    result = DetectorStage._dominant_color_in_roi(roi, CFG)
    assert result == "초록"


def test_detector_dominant_color_red():
    """HSV hue ~5 (within 0-10) → '빨강'."""
    roi = _make_bgr_from_hsv(h=5, s=200, v=200)
    result = DetectorStage._dominant_color_in_roi(roi, CFG)
    assert result == "빨강"


def test_detector_color_mapping(sample_color_map):
    """tape_color maps to difficulty via color_map."""
    mapping = sample_color_map["mapping"]
    assert mapping["노랑"] == "V0-V1"
    assert mapping["초록"] == "V2-V3"
    assert mapping["파랑"] == "V4-V5"
    assert mapping["빨강"] == "V6-V7"
    assert mapping["검정"] == "V8+"


def test_detector_no_clip_path(sample_color_map):
    """Clip with no clip_path should be skipped gracefully."""
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

    stage = DetectorStage({})
    result = stage.process(ctx)
    assert result.clips[0].tape_color is None
    assert result.clips[0].difficulty is None


def test_detector_hsv_table_coverage():
    """All 5 Korean colour names should have HSV ranges in the table."""
    expected_colors = {"노랑", "초록", "파랑", "빨강", "검정"}
    table_colors = {entry[2] for entry in _HSV_COLOR_TABLE}
    assert expected_colors == table_colors
