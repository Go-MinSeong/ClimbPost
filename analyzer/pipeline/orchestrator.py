from __future__ import annotations

import importlib
import logging
import time
from typing import Callable

from .base_stage import BaseStage
from .context import PipelineContext

logger = logging.getLogger(__name__)

_DEFAULT_STAGE_WEIGHTS = {
    "clipper": 40,
    "classifier": 10,
    "detector": 15,
    "identifier": 5,
    "editor": 30,
}


def _load_stage_class(dotted_path: str) -> type[BaseStage]:
    """Import a stage class from a dotted module path like 'analyzer.clipper.clipper.ClipperStage'."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not (isinstance(cls, type) and issubclass(cls, BaseStage)):
        raise TypeError(f"{dotted_path} is not a BaseStage subclass")
    return cls


class Pipeline:
    """Runs a sequence of stages against a PipelineContext."""

    def __init__(
        self,
        stage_paths: list[str],
        config: dict | None = None,
        stage_weights: dict[str, int] | None = None,
    ):
        self.config = config or {}
        self.stage_weights = stage_weights if stage_weights is not None else _DEFAULT_STAGE_WEIGHTS
        self.stages: list[BaseStage] = []
        for path in stage_paths:
            cls = _load_stage_class(path)
            self.stages.append(cls(self.config))

    def run(
        self,
        context: PipelineContext,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> PipelineContext:
        logger.info("Pipeline started — session %s, %d stage(s)", context.session_id, len(self.stages))
        cumulative_pct = 0
        for stage in self.stages:
            logger.info("Stage [%s] starting", stage.name)
            t0 = time.perf_counter()
            context = stage.process(context)
            elapsed = time.perf_counter() - t0
            logger.info("Stage [%s] completed in %.2fs", stage.name, elapsed)
            cumulative_pct += self.stage_weights.get(stage.name, 0)
            if progress_callback is not None:
                progress_callback(stage.name, cumulative_pct)
        logger.info("Pipeline finished — session %s, %d clip(s)", context.session_id, len(context.clips))
        return context
