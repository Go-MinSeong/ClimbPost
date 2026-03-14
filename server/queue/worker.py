from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import subprocess
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from server.config.settings import MOCK_ANALYSIS, STORAGE_ROOT
from server.db.database import SessionLocal
from server.db.models import Job, UploadSession, RawVideo, Clip, Gym
from server.push.service import send_push

logger = logging.getLogger(__name__)

TAPE_COLORS = ["red", "blue", "green", "yellow", "orange", "pink", "purple", "white", "black"]
DIFFICULTIES = ["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8+"]
RESULTS = ["success", "fail"]


async def _mock_analyze(job: Job, db: Session) -> None:
    """Generate fake clip results after a short delay."""
    await asyncio.sleep(5)

    raw_videos = db.query(RawVideo).filter(RawVideo.session_id == job.session_id).all()
    session = db.query(UploadSession).filter(UploadSession.id == job.session_id).first()

    for rv in raw_videos:
        num_clips = random.randint(1, 3)
        for i in range(num_clips):
            start = random.uniform(0, 30)
            duration = random.uniform(15, 60)
            color_idx = random.randint(0, len(TAPE_COLORS) - 1)
            clip = Clip(
                raw_video_id=rv.id,
                gym_id=session.gym_id,
                start_time=start,
                end_time=start + duration,
                duration_sec=duration,
                difficulty=DIFFICULTIES[color_idx % len(DIFFICULTIES)],
                tape_color=TAPE_COLORS[color_idx],
                result=random.choice(RESULTS),
                is_me=random.random() > 0.3,
                thumbnail_url=f"/storage/thumbnails/{job.session_id}/{uuid.uuid4()}.jpg",
                clip_url=f"/storage/clips/{job.session_id}/{uuid.uuid4()}.mp4",
                edited_url=f"/storage/edited/{job.session_id}/{uuid.uuid4()}.mp4",
            )
            db.add(clip)

    db.commit()


def _get_video_duration(file_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _resolve_file_path(file_url: str) -> str:
    """Convert a storage URL like '/storage/raw/{sid}/file.mov' to an absolute file path."""
    relative = file_url.replace("/storage/", "/")
    return str(Path(STORAGE_ROOT) / relative.lstrip("/"))


def _load_color_map(gym: Gym | None, gym_id: str) -> dict:
    """Load color map from DB gym record, falling back to data/color_maps/ file."""
    if gym and gym.color_map:
        cm = gym.color_map
        if isinstance(cm, str):
            cm = json.loads(cm)
        # Ensure it has the 'mapping' key
        if "mapping" in cm:
            return cm
        # If the whole dict is the mapping itself, wrap it
        return {"mapping": cm}

    # Fallback: load from file
    color_map_path = Path(__file__).resolve().parent.parent.parent / "data" / "color_maps" / f"{gym_id}.json"
    if color_map_path.exists():
        with open(color_map_path) as f:
            return json.load(f)

    # Last resort: empty mapping
    logger.warning("No color map found for gym %s", gym_id)
    return {"mapping": {}}


async def _real_analyze(job: Job, db: Session) -> None:
    """Run the actual analyzer pipeline on uploaded videos."""
    from analyzer.pipeline.context import PipelineContext, RawVideoInfo
    from analyzer.pipeline.orchestrator import Pipeline
    from analyzer.config.settings import PIPELINE_STAGES

    # 1. Query raw videos and session info
    raw_video_records = db.query(RawVideo).filter(RawVideo.session_id == job.session_id).all()
    session = db.query(UploadSession).filter(UploadSession.id == job.session_id).first()
    if not session:
        raise ValueError(f"No upload session found for job {job.id}")

    gym_id = session.gym_id or ""

    # 2. Load color map
    gym = db.query(Gym).filter(Gym.id == gym_id).first() if gym_id else None
    color_map = _load_color_map(gym, gym_id)

    # 3. Build RawVideoInfo list with file path conversion and duration
    raw_videos = []
    for rv in raw_video_records:
        file_path = _resolve_file_path(rv.file_url)
        duration = rv.duration_sec
        if duration is None:
            try:
                duration = _get_video_duration(file_path)
            except (ValueError, FileNotFoundError):
                logger.warning("Could not get duration for %s, defaulting to 0", file_path)
                duration = 0.0
        raw_videos.append(
            RawVideoInfo(
                raw_video_id=rv.id,
                file_path=file_path,
                duration_sec=duration,
            )
        )

    # 4. Build pipeline context
    context = PipelineContext(
        session_id=job.session_id,
        gym_id=gym_id,
        color_map=color_map,
        raw_videos=raw_videos,
        storage_root=STORAGE_ROOT,
    )

    # 5. Run pipeline (CPU/GPU-bound, run in executor to avoid blocking event loop)
    config = {
        "clipper": {
            "motion_threshold": 0.04,   # less sensitive (was 0.02)
            "still_frames": 6,          # longer pause to end clip (was 4)
            "min_climb_sec": 10,        # min 10s clips (was 5)
        },
        "classifier": {
            "top_zone_ratio": 0.30,     # top 30% = success zone (was 0.20)
            "hold_frames": 1,           # 1 frame in top = success (was 2)
            "fall_dy_threshold": 0.20,  # bigger fall needed for fail (was 0.15)
        },
        "detector": {
            "min_saturation": 30,       # detect less saturated colors (was 50)
            "max_samples": 20,          # more frames to sample (was 10)
        },
    }
    pipeline = Pipeline(PIPELINE_STAGES, config)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, pipeline.run, context)

    # 6. Save clips to DB (convert absolute paths to relative /storage/ URLs)
    def _to_url(abs_path: str | None) -> str | None:
        if not abs_path:
            return None
        try:
            rel = os.path.relpath(abs_path, STORAGE_ROOT)
            return f"/storage/{rel}"
        except ValueError:
            return abs_path

    for clip in result.clips:
        clip_record = Clip(
            raw_video_id=clip.raw_video_id,
            gym_id=context.gym_id,
            start_time=clip.start_time,
            end_time=clip.end_time,
            duration_sec=clip.duration_sec,
            difficulty=clip.difficulty,
            tape_color=clip.tape_color,
            result=clip.result,
            is_me=clip.is_me,
            thumbnail_url=_to_url(clip.thumbnail_path),
            clip_url=_to_url(clip.clip_path),
            edited_url=_to_url(clip.edited_path),
        )
        db.add(clip_record)

    db.commit()
    logger.info("Real analysis complete for session %s: %d clip(s) saved", job.session_id, len(result.clips))


async def process_job(job_id: str) -> None:
    """Process a single analysis job."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job or job.status != "pending":
            return

        job.status = "processing"
        db.commit()

        try:
            if MOCK_ANALYSIS:
                await _mock_analyze(job, db)
            else:
                await _real_analyze(job, db)

            job.status = "completed"
            session = db.query(UploadSession).filter(UploadSession.id == job.session_id).first()
            if session:
                session.status = "completed"
            db.commit()

            # Send push notification
            if session:
                await send_push(
                    session.user_id,
                    "Analysis Complete",
                    "Your climbing video analysis is ready!",
                    db,
                )

        except Exception:
            logger.exception("Job %s failed", job_id)
            job.status = "failed"
            session = db.query(UploadSession).filter(UploadSession.id == job.session_id).first()
            if session:
                session.status = "failed"
            db.commit()
    finally:
        db.close()


async def poll_jobs() -> None:
    """Poll for pending jobs and process them. Intended to run as a background task."""
    while True:
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.status == "pending").order_by(Job.created_at).first()
            if job:
                logger.info("Processing job %s for session %s", job.id, job.session_id)
                db.close()
                await process_job(job.id)
            else:
                db.close()
                await asyncio.sleep(2)
        except Exception:
            logger.exception("Error polling jobs")
            db.close()
            await asyncio.sleep(5)
