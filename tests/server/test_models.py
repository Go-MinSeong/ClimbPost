"""Tests for DB model creation."""
from server.db.models import User, Gym, UploadSession, RawVideo, Clip, Job


def test_create_user(db_session):
    user = User(provider="apple", email="u@test.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert len(user.id) == 36  # UUID format
    assert user.created_at is not None
    assert user.provider == "apple"
    assert user.email == "u@test.com"


def test_create_gym(db_session):
    gym = Gym(name="Boulder Lab", latitude=37.5, longitude=127.0, color_map={"red": "V3"})
    db_session.add(gym)
    db_session.commit()
    db_session.refresh(gym)

    assert gym.id is not None
    assert gym.name == "Boulder Lab"
    assert gym.color_map == {"red": "V3"}


def test_create_upload_session_with_relationships(db_session):
    user = User(provider="google", email="g@test.com")
    gym = Gym(name="G", latitude=0.0, longitude=0.0)
    db_session.add_all([user, gym])
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(gym)

    session = UploadSession(user_id=user.id, gym_id=gym.id, status="uploading")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assert session.id is not None
    assert session.user_id == user.id
    assert session.gym_id == gym.id
    assert session.status == "uploading"
    assert session.user.email == "g@test.com"
    assert session.gym.name == "G"


def test_create_raw_video(db_session):
    user = User(provider="apple")
    db_session.add(user)
    db_session.flush()

    session = UploadSession(user_id=user.id, status="uploading")
    db_session.add(session)
    db_session.flush()

    rv = RawVideo(session_id=session.id, file_url="/raw/test.mp4", duration_sec=120.5)
    db_session.add(rv)
    db_session.commit()
    db_session.refresh(rv)

    assert rv.id is not None
    assert rv.session_id == session.id
    assert rv.duration_sec == 120.5
    assert rv.session.user_id == user.id


def test_create_clip(db_session):
    user = User(provider="apple")
    db_session.add(user)
    db_session.flush()

    session = UploadSession(user_id=user.id)
    db_session.add(session)
    db_session.flush()

    rv = RawVideo(session_id=session.id)
    db_session.add(rv)
    db_session.flush()

    clip = Clip(
        raw_video_id=rv.id,
        difficulty="V5",
        tape_color="blue",
        result="success",
        is_me=True,
        start_time=10.0,
        end_time=45.0,
        duration_sec=35.0,
    )
    db_session.add(clip)
    db_session.commit()
    db_session.refresh(clip)

    assert clip.id is not None
    assert clip.difficulty == "V5"
    assert clip.result == "success"
    assert clip.is_me is True
    assert clip.raw_video.session_id == session.id


def test_create_job(db_session):
    user = User(provider="apple")
    db_session.add(user)
    db_session.flush()

    session = UploadSession(user_id=user.id)
    db_session.add(session)
    db_session.flush()

    job = Job(session_id=session.id, status="pending")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.id is not None
    assert job.status == "pending"
    assert job.created_at is not None
    assert job.updated_at is not None
    assert job.session.user_id == user.id
