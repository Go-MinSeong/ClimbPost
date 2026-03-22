"""Instagram Graph API publishing endpoints."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.auth.service import get_current_user
from server.config.settings import PUBLIC_BASE_URL
from server.db.database import get_db
from server.db.models import User, Clip, RawVideo, UploadSession, InstagramPublishJob, InstagramAccount
from server.services.instagram import InstagramService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instagram", tags=["instagram"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class PublishRequest(BaseModel):
    clip_ids: list[str]
    caption: str | None = None


class PublishResponse(BaseModel):
    job_id: str
    status: str


class PublishStatusResponse(BaseModel):
    job_id: str
    status: str
    error_message: str | None = None
    ig_media_id: str | None = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/publish", response_model=PublishResponse, status_code=202)
async def publish_to_instagram(
    body: PublishRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate an Instagram carousel publish. Returns job ID immediately."""
    if not body.clip_ids:
        raise HTTPException(status_code=400, detail="At least one clip_id required")
    if len(body.clip_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 clips per carousel")
    if not PUBLIC_BASE_URL:
        raise HTTPException(status_code=503, detail="PUBLIC_BASE_URL not configured — cannot serve videos to Instagram")

    # Check Instagram account is connected
    ig_account = db.query(InstagramAccount).filter(InstagramAccount.user_id == user.id).first()
    if not ig_account:
        raise HTTPException(status_code=400, detail="Instagram 계정이 연결되지 않았습니다. 먼저 Instagram을 연결하세요.")

    # Verify all clips belong to this user
    clips = (
        db.query(Clip)
        .join(RawVideo)
        .join(UploadSession)
        .filter(Clip.id.in_(body.clip_ids), UploadSession.user_id == user.id)
        .all()
    )
    found_ids = {c.id for c in clips}
    missing = set(body.clip_ids) - found_ids
    if missing:
        raise HTTPException(status_code=404, detail=f"Clips not found: {missing}")

    # Check all clips have video files
    for clip in clips:
        if not (clip.edited_url or clip.clip_url):
            raise HTTPException(status_code=400, detail=f"Clip {clip.id} has no video file")

    # Create publish job
    job = InstagramPublishJob(
        user_id=user.id,
        clip_ids=body.clip_ids,
        caption=body.caption,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Start background publish task
    asyncio.create_task(_run_publish(job.id))

    return PublishResponse(job_id=job.id, status="pending")


@router.get("/publish/{job_id}", response_model=PublishStatusResponse)
async def get_publish_status(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the status of an Instagram publish job."""
    job = db.query(InstagramPublishJob).filter(
        InstagramPublishJob.id == job_id,
        InstagramPublishJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Publish job not found")

    return PublishStatusResponse(
        job_id=job.id,
        status=job.status,
        error_message=job.error_message,
        ig_media_id=job.ig_media_id,
    )


# ------------------------------------------------------------------
# Background task
# ------------------------------------------------------------------

async def _run_publish(job_id: str) -> None:
    """Background task: publish clips to Instagram via Graph API."""
    from server.db.database import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(InstagramPublishJob).filter(InstagramPublishJob.id == job_id).first()
        if not job:
            return

        job.status = "uploading"
        db.commit()

        # Build public URLs for each clip (ordered by clip_ids)
        clips = db.query(Clip).filter(Clip.id.in_(job.clip_ids)).all()
        clip_map = {c.id: c for c in clips}

        video_urls = []
        for clip_id in job.clip_ids:
            clip = clip_map.get(clip_id)
            if not clip:
                continue
            video_path = clip.edited_url or clip.clip_url
            if not video_path:
                continue
            # Convert /storage/... to public URL
            rel_path = video_path.removeprefix("/storage/")
            public_url = f"{PUBLIC_BASE_URL}/storage/{rel_path}"
            video_urls.append(public_url)

        if not video_urls:
            job.status = "failed"
            job.error_message = "No video files available for publishing"
            db.commit()
            return

        logger.info("Publishing %d videos to Instagram for job %s", len(video_urls), job_id)

        # Get user's Instagram credentials from DB
        ig_account = db.query(InstagramAccount).filter(InstagramAccount.user_id == job.user_id).first()
        if not ig_account:
            job.status = "failed"
            job.error_message = "Instagram 계정이 연결되지 않았습니다"
            db.commit()
            return

        job.status = "processing"
        db.commit()

        # Call Instagram API with user's own credentials
        service = InstagramService(
            ig_user_id=ig_account.ig_user_id,
            access_token=ig_account.page_access_token,
        )
        result = await service.publish_carousel(
            video_urls=video_urls,
            caption=job.caption,
        )

        job.status = "published"
        job.ig_media_id = result.ig_media_id
        job.container_ids = result.container_ids
        job.carousel_container_id = result.carousel_container_id
        db.commit()

        logger.info("Job %s published → ig_media_id=%s", job_id, result.ig_media_id)

    except Exception as e:
        logger.exception("Instagram publish job %s failed: %s", job_id, e)
        job.status = "failed"
        job.error_message = str(e)[:500]
        db.commit()
    finally:
        db.close()
