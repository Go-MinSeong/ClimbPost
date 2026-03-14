from __future__ import annotations

from abc import ABC, abstractmethod

from .context import PipelineContext


class BaseStage(ABC):
    """Base class for all pipeline stages."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def process(self, context: PipelineContext) -> PipelineContext:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
