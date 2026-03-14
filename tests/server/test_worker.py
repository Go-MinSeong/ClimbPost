"""Tests for the analysis worker."""
import asyncio
from unittest.mock import patch, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.db.database import Base
from server.db.models import User, UploadSession, RawVideo, Job, Clip


def _make_worker_session():
    """Create an independent DB session for worker tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal, engine


def test_mock_analyze():
    """_mock_analyze should generate clips for each raw video."""
    SessionLocal, engine = _make_worker_session()
    db = SessionLocal()

    user = User(provider="apple")
    db.add(user)
    db.flush()

    session = UploadSession(user_id=user.id, status="analyzing")
    db.add(session)
    db.flush()

    rv1 = RawVideo(session_id=session.id, file_url="/raw/v1.mp4")
    rv2 = RawVideo(session_id=session.id, file_url="/raw/v2.mp4")
    db.add_all([rv1, rv2])
    db.flush()

    job = Job(session_id=session.id, status="processing")
    db.add(job)
    db.commit()

    from server.queue.worker import _mock_analyze

    with patch("server.queue.worker.asyncio.sleep", new_callable=AsyncMock):
        asyncio.get_event_loop().run_until_complete(_mock_analyze(job, db))

    clips = db.query(Clip).all()
    assert len(clips) >= 2
    assert len(clips) <= 6

    rv_ids = {rv1.id, rv2.id}
    for clip in clips:
        assert clip.raw_video_id in rv_ids
        assert clip.difficulty is not None
        assert clip.result in ("success", "fail")

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_process_job_completed():
    """process_job should set job and session to completed."""
    SessionLocal, engine = _make_worker_session()
    db = SessionLocal()

    user = User(provider="apple")
    db.add(user)
    db.flush()

    session = UploadSession(user_id=user.id, status="analyzing")
    db.add(session)
    db.flush()

    rv = RawVideo(session_id=session.id, file_url="/raw/v.mp4")
    db.add(rv)
    db.flush()

    job = Job(session_id=session.id, status="pending")
    db.add(job)
    db.commit()

    job_id = job.id
    session_id = session.id

    from server.queue.worker import process_job

    # Patch SessionLocal to return our test session, and prevent close()
    # from actually closing (process_job calls db.close() in finally)
    original_close = db.close

    def noop_close():
        pass

    db.close = noop_close

    with (
        patch("server.queue.worker.SessionLocal", return_value=db),
        patch("server.queue.worker.asyncio.sleep", new_callable=AsyncMock),
        patch("server.queue.worker.send_push", new_callable=AsyncMock),
        patch("server.queue.worker.MOCK_ANALYSIS", True),
    ):
        asyncio.get_event_loop().run_until_complete(process_job(job_id))

    db.close = original_close

    # Re-query objects to check final state
    job = db.query(Job).filter(Job.id == job_id).first()
    session = db.query(UploadSession).filter(UploadSession.id == session_id).first()

    assert job.status == "completed"
    assert session.status == "completed"

    clips = db.query(Clip).all()
    assert len(clips) >= 1

    db.close()
    Base.metadata.drop_all(bind=engine)
