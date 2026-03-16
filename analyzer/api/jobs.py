from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ColorMap(BaseModel):
    mapping: dict[str, str]


class RawVideoRequest(BaseModel):
    raw_video_id: str
    file_path: str
    duration_sec: float


class PipelineConfig(BaseModel):
    clipper: dict = {}
    classifier: dict = {}
    detector: dict = {}


class AnalyzeRequest(BaseModel):
    session_id: str
    gym_id: str
    color_map: dict
    raw_videos: list[RawVideoRequest]
    storage_root: str = "/data/storage"
    pipeline_config: PipelineConfig | None = None


class ClipResult(BaseModel):
    clip_id: str
    raw_video_id: str
    start_time: float
    end_time: float
    duration_sec: float
    clip_path: str | None
    thumbnail_path: str | None
    difficulty: str | None
    tape_color: str | None
    result: str | None
    is_me: bool | None
    edited_path: str | None


class AnalyzeResponse(BaseModel):
    session_id: str
    clips: list[ClipResult]
    elapsed_sec: float


# ---------------------------------------------------------------------------
# Job state dataclass
# ---------------------------------------------------------------------------

@dataclass
class JobState:
    job_id: str
    session_id: str
    request: AnalyzeRequest
    status: str = "queued"   # queued|processing|completed|failed|cancelled
    progress_pct: int = 0
    current_stage: str = ""
    stages_completed: list[str] = field(default_factory=list)
    result: AnalyzeResponse | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    started_at: datetime | None = None


# ---------------------------------------------------------------------------
# Job queue
# ---------------------------------------------------------------------------

class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._jobs: dict[str, JobState] = {}
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background worker. Call once on app startup."""
        self._worker_task = asyncio.create_task(self._worker())

    async def submit(self, request: AnalyzeRequest) -> JobState:
        """Enqueue a new job. Returns the JobState with status='queued'."""
        job_id = "job_" + uuid.uuid4().hex[:12]
        state = JobState(job_id=job_id, session_id=request.session_id, request=request)
        self._jobs[job_id] = state
        await self._queue.put(job_id)
        return state

    def get_status(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> bool:
        """Cancel a queued job. Returns False if job is already processing/completed."""
        state = self._jobs.get(job_id)
        if not state or state.status not in ("queued",):
            return False
        state.status = "cancelled"
        return True

    async def _worker(self) -> None:
        """Single worker: processes jobs one at a time from the queue."""
        while True:
            job_id = await self._queue.get()
            state = self._jobs.get(job_id)
            if not state or state.status == "cancelled":
                self._queue.task_done()
                continue
            await self._run_job(state)
            self._queue.task_done()

    async def _run_job(self, state: JobState) -> None:
        """Execute the pipeline for a job, updating state as stages complete."""
        import time
        from analyzer.pipeline.context import PipelineContext, RawVideoInfo
        from analyzer.pipeline.orchestrator import Pipeline
        from analyzer.config.settings import PIPELINE_STAGES

        state.status = "processing"
        state.started_at = datetime.utcnow()

        stage_weights = {
            "clipper": 40,
            "classifier": 10,
            "detector": 15,
            "identifier": 5,
            "editor": 30,
        }

        def progress_callback(stage_name: str, pct: int) -> None:
            state.current_stage = stage_name
            state.progress_pct = pct
            if stage_name not in state.stages_completed:
                state.stages_completed.append(stage_name)

        req = state.request
        raw_videos = [
            RawVideoInfo(
                raw_video_id=rv.raw_video_id,
                file_path=rv.file_path,
                duration_sec=rv.duration_sec,
            )
            for rv in req.raw_videos
        ]
        config = {}
        if req.pipeline_config:
            config = {
                "clipper": req.pipeline_config.clipper,
                "classifier": req.pipeline_config.classifier,
                "detector": req.pipeline_config.detector,
            }
        context = PipelineContext(
            session_id=req.session_id,
            gym_id=req.gym_id,
            color_map=req.color_map,
            raw_videos=raw_videos,
            storage_root=req.storage_root,
        )

        started = time.monotonic()
        try:
            pipeline = Pipeline(PIPELINE_STAGES, config, stage_weights=stage_weights)
            loop = asyncio.get_event_loop()
            result_context = await loop.run_in_executor(
                None, lambda: pipeline.run(context, progress_callback=progress_callback)
            )
            clips = [
                ClipResult(
                    clip_id=clip.clip_id,
                    raw_video_id=clip.raw_video_id,
                    start_time=clip.start_time,
                    end_time=clip.end_time,
                    duration_sec=clip.duration_sec,
                    clip_path=clip.clip_path,
                    thumbnail_path=clip.thumbnail_path,
                    difficulty=clip.difficulty,
                    tape_color=clip.tape_color,
                    result=clip.result,
                    is_me=clip.is_me,
                    edited_path=clip.edited_path,
                )
                for clip in result_context.clips
            ]
            state.result = AnalyzeResponse(
                session_id=req.session_id,
                clips=clips,
                elapsed_sec=time.monotonic() - started,
            )
            state.status = "completed"
            state.progress_pct = 100
        except Exception as exc:
            logger.exception("Job %s failed: %s", state.job_id, exc)
            state.status = "failed"
            state.error = str(exc)


# ---------------------------------------------------------------------------
# Module-level singleton — imported by router and main
# ---------------------------------------------------------------------------

job_queue = JobQueue()
