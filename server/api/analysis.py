from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.auth.service import get_current_user
from server.db.database import get_db
from server.db.models import User, UploadSession, Job

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/{session_id}/status")
async def get_analysis_status(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the analysis status for a session."""
    session = db.query(UploadSession).filter(
        UploadSession.id == session_id,
        UploadSession.user_id == user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Calculate progress from job status
    job = db.query(Job).filter(Job.session_id == session_id).order_by(Job.created_at.desc()).first()
    progress_pct = 0
    if job:
        if job.status == "pending":
            progress_pct = 0
        elif job.status == "processing":
            progress_pct = 50
        elif job.status == "completed":
            progress_pct = 100
        elif job.status == "failed":
            progress_pct = 0

    return {
        "session_id": session_id,
        "status": session.status,
        "progress_pct": progress_pct,
    }
