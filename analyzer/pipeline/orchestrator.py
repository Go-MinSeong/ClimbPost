from __future__ import annotations

import importlib
import logging
import time

from .base_stage import BaseStage
from .context import PipelineContext

logger = logging.getLogger(__name__)


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

    def __init__(self, stage_paths: list[str], config: dict | None = None):
        self.config = config or {}
        self.stages: list[BaseStage] = []
        for path in stage_paths:
            cls = _load_stage_class(path)
            self.stages.append(cls(self.config))

    def run(self, context: PipelineContext) -> PipelineContext:
        logger.info("Pipeline started — session %s, %d stage(s)", context.session_id, len(self.stages))
        for stage in self.stages:
            logger.info("Stage [%s] starting", stage.name)
            t0 = time.perf_counter()
            context = stage.process(context)
            elapsed = time.perf_counter() - t0
            logger.info("Stage [%s] completed in %.2fs", stage.name, elapsed)
        logger.info("Pipeline finished — session %s, %d clip(s)", context.session_id, len(context.clips))
        return context
