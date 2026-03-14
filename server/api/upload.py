import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from server.auth.service import get_current_user
from server.config.settings import STORAGE_ROOT
from server.db.database import get_db
from server.db.models import User, UploadSession, RawVideo, Job
from server.db.schemas import UploadSessionCreate, UploadSessionResponse, RawVideoResponse, JobResponse

router = APIRouter(prefix="/videos", tags=["upload"])


@router.post("/sessions", response_model=UploadSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: UploadSessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new upload session."""
    session = UploadSession(
        user_id=user.id,
        gym_id=body.gym_id,
        recorded_date=body.recorded_date,
        status="uploading",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/upload/{session_id}", response_model=RawVideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    session_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a video file to an existing session."""
    session = db.query(UploadSession).filter(
        UploadSession.id == session_id,
        UploadSession.user_id == user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Save file to disk
    save_dir = Path(STORAGE_ROOT) / "raw" / session_id
    save_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_dir / file.filename
    contents = await file.read()
    file_path.write_bytes(contents)

    file_url = f"/storage/raw/{session_id}/{file.filename}"

    raw_video = RawVideo(
        session_id=session_id,
        file_url=file_url,
    )
    db.add(raw_video)
    db.commit()
    db.refresh(raw_video)
    return raw_video


@router.post("/sessions/{session_id}/start-analysis", response_model=JobResponse)
async def start_analysis(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start analysis for all videos in a session."""
    session = db.query(UploadSession).filter(
        UploadSession.id == session_id,
        UploadSession.user_id == user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.status != "uploading":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not in uploading state")

    session.status = "analyzing"
    job = Job(session_id=session_id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
