from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from server.auth.service import get_current_user
from server.config.settings import STORAGE_ROOT
from server.db.database import get_db
from server.db.models import User, Clip, UploadSession, RawVideo
from server.db.schemas import ClipResponse

router = APIRouter(prefix="/clips", tags=["clips"])


@router.get("", response_model=list[ClipResponse])
async def list_clips(
    session_id: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    is_me: Optional[bool] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List clips with optional filters."""
    query = db.query(Clip).join(RawVideo).join(UploadSession).filter(
        UploadSession.user_id == user.id,
    )

    if session_id:
        query = query.filter(RawVideo.session_id == session_id)
    if difficulty:
        query = query.filter(Clip.difficulty == difficulty)
    if result:
        query = query.filter(Clip.result == result)
    if is_me is not None:
        query = query.filter(Clip.is_me == is_me)

    clips = query.order_by(Clip.created_at.desc()).all()
    return clips


@router.get("/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get clip details."""
    clip = db.query(Clip).join(RawVideo).join(UploadSession).filter(
        Clip.id == clip_id,
        UploadSession.user_id == user.id,
    ).first()
    if not clip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    return clip


@router.get("/{clip_id}/video")
async def stream_clip_video(
    clip_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream clip video file."""
    clip = db.query(Clip).join(RawVideo).join(UploadSession).filter(
        Clip.id == clip_id,
        UploadSession.user_id == user.id,
    ).first()
    if not clip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    url = clip.edited_url or clip.clip_url
    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not available")

    # Convert URL path to filesystem path
    rel = url.removeprefix("/storage/") if url.startswith("/storage/") else url
    file_path = Path(STORAGE_ROOT) / rel
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found on disk")

    return FileResponse(file_path, media_type="video/mp4")
