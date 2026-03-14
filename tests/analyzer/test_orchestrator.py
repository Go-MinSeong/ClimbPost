"""Tests for analyzer.pipeline.orchestrator."""

import pytest

from analyzer.pipeline.base_stage import BaseStage
from analyzer.pipeline.context import PipelineContext
from analyzer.pipeline.orchestrator import Pipeline


def test_pipeline_loads_stages():
    """Loading a known stage path should not raise."""
    pipeline = Pipeline(["analyzer.clipper.clipper.ClipperStage"], {})
    assert len(pipeline.stages) == 1


def test_pipeline_invalid_stage_path():
    """An invalid dotted path should raise ImportError or AttributeError."""
    with pytest.raises((ImportError, AttributeError)):
        Pipeline(["analyzer.nonexistent.BadStage"], {})


def test_pipeline_invalid_stage_not_base():
    """A valid class that isn't a BaseStage subclass should raise TypeError."""
    with pytest.raises(TypeError):
        Pipeline(["analyzer.config.settings.PIPELINE_STAGES"], {})


def test_pipeline_run_empty_stages():
    """Running with no stages returns context unchanged."""
    ctx = PipelineContext(
        session_id="s1",
        gym_id="g1",
        color_map={},
        raw_videos=[],
    )
    pipeline = Pipeline([], {})
    result = pipeline.run(ctx)
    assert result is ctx
    assert result.clips == []


def test_pipeline_custom_stage():
    """A custom dummy stage gets called and can modify context."""

    class DummyStage(BaseStage):
        @property
        def name(self) -> str:
            return "dummy"

        def process(self, context: PipelineContext) -> PipelineContext:
            context.session_id = "modified"
            return context

    ctx = PipelineContext(
        session_id="original",
        gym_id="g1",
        color_map={},
        raw_videos=[],
    )

    pipeline = Pipeline([], {})
    pipeline.stages = [DummyStage({})]
    result = pipeline.run(ctx)
    assert result.session_id == "modified"
