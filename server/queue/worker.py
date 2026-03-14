import asyncio
import logging
import random
import uuid

from sqlalchemy.orm import Session

from server.config.settings import MOCK_ANALYSIS
from server.db.database import SessionLocal
from server.db.models import Job, UploadSession, RawVideo, Clip
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


async def _real_analyze(job: Job, db: Session) -> None:
    """Run the actual analyzer pipeline (subprocess or import)."""
    # TODO: integrate with analyzer pipeline when available
    raise NotImplementedError("Real analysis pipeline not yet integrated")


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
