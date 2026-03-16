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

from server.config.settings import MOCK_ANALYSIS, STORAGE_ROOT, ANALYZER_URL
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
    """Run the actual analyzer pipeline via the analyzer microservice."""
    import httpx

    # 1. Query raw videos and session info
    raw_video_records = db.query(RawVideo).filter(RawVideo.session_id == job.session_id).all()
    session = db.query(UploadSession).filter(UploadSession.id == job.session_id).first()
    if not session:
        raise ValueError(f"No upload session found for job {job.id}")

    gym_id = session.gym_id or ""

    # 2. Load color map
    gym = db.query(Gym).filter(Gym.id == gym_id).first() if gym_id else None
    color_map = _load_color_map(gym, gym_id)

    # 3. Build raw video list with file path conversion and duration
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
        raw_videos.append({"raw_video_id": rv.id, "file_path": file_path, "duration_sec": duration})

    # 4. Call analyzer microservice
    payload = {
        "session_id": job.session_id,
        "gym_id": gym_id,
        "color_map": color_map,
        "raw_videos": raw_videos,
        "storage_root": STORAGE_ROOT,
        "pipeline_config": {
            "clipper": {"motion_threshold": 0.04, "still_frames": 6, "min_climb_sec": 10},
            "classifier": {"top_zone_ratio": 0.30, "hold_frames": 1, "fall_dy_threshold": 0.20},
            "detector": {"min_saturation": 30, "max_samples": 20},
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Submit job
        response = await client.post(f"{ANALYZER_URL}/jobs", json=payload)
        response.raise_for_status()
        job_id = response.json()["job_id"]
        logger.info("Analyzer job submitted: %s for session %s", job_id, job.session_id)

        # Step 2: Poll until completed or failed (5s interval, max 30 min = 360 attempts)
        for attempt in range(360):
            await asyncio.sleep(5)
            status_resp = await client.get(f"{ANALYZER_URL}/jobs/{job_id}")
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data["status"]
            progress = status_data.get("progress_pct", 0)
            logger.debug("Job %s: status=%s progress=%d%%", job_id, status, progress)

            if status == "completed":
                break
            elif status == "failed":
                error = status_data.get("error", "unknown error")
                raise RuntimeError(f"Analyzer job {job_id} failed: {error}")
            elif status == "cancelled":
                raise RuntimeError(f"Analyzer job {job_id} was cancelled")
        else:
            raise TimeoutError(f"Analyzer job {job_id} timed out after 30 minutes")

        # Step 3: Fetch result
        result_resp = await client.get(f"{ANALYZER_URL}/jobs/{job_id}/result")
        result_resp.raise_for_status()
        data = result_resp.json()

    # 5. Save clips to DB (convert absolute paths to relative /storage/ URLs)
    def _to_url(abs_path: str | None) -> str | None:
        if not abs_path:
            return None
        try:
            rel = os.path.relpath(abs_path, STORAGE_ROOT)
            return f"/storage/{rel}"
        except ValueError:
            return abs_path

    for clip in data["clips"]:
        clip_record = Clip(
            raw_video_id=clip["raw_video_id"],
            gym_id=gym_id,
            start_time=clip["start_time"],
            end_time=clip["end_time"],
            duration_sec=clip["duration_sec"],
            difficulty=clip.get("difficulty"),
            tape_color=clip.get("tape_color"),
            result=clip.get("result"),
            is_me=clip.get("is_me"),
            thumbnail_url=_to_url(clip.get("thumbnail_path")),
            clip_url=_to_url(clip.get("clip_path")),
            edited_url=_to_url(clip.get("edited_path")),
        )
        db.add(clip_record)

    db.commit()
    logger.info("Real analysis complete for session %s: %d clip(s) saved", job.session_id, len(data["clips"]))


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
