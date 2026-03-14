"""Tests for /videos endpoints."""
import io

from server.db.models import UploadSession, Job


def test_create_session(client, auth_header):
    headers, user = auth_header
    resp = client.post("/videos/sessions", json={}, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "uploading"
    assert data["user_id"] == user.id


def test_create_session_with_gym(client, auth_header, db_session):
    headers, user = auth_header
    from server.db.models import Gym

    gym = Gym(name="Test Gym", latitude=37.5, longitude=127.0)
    db_session.add(gym)
    db_session.commit()
    db_session.refresh(gym)

    resp = client.post(
        "/videos/sessions",
        json={"gym_id": gym.id},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["gym_id"] == gym.id


def test_upload_video(client, auth_header, db_session, tmp_path):
    headers, user = auth_header
    # Create session first
    session = UploadSession(user_id=user.id, status="uploading")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    # Monkey-patch STORAGE_ROOT to use tmp_path
    import server.api.upload as upload_mod

    original_root = upload_mod.STORAGE_ROOT
    upload_mod.STORAGE_ROOT = str(tmp_path)
    try:
        fake_file = io.BytesIO(b"fake video content")
        resp = client.post(
            f"/videos/upload/{session.id}",
            files={"file": ("test.mp4", fake_file, "video/mp4")},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_id"] == session.id
        assert "test.mp4" in data["file_url"]
    finally:
        upload_mod.STORAGE_ROOT = original_root


def test_upload_to_nonexistent_session(client, auth_header):
    headers, _ = auth_header
    fake_file = io.BytesIO(b"data")
    resp = client.post(
        "/videos/upload/nonexistent-id",
        files={"file": ("test.mp4", fake_file, "video/mp4")},
        headers=headers,
    )
    assert resp.status_code == 404


def test_start_analysis(client, auth_header, db_session):
    headers, user = auth_header
    session = UploadSession(user_id=user.id, status="uploading")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    resp = client.post(f"/videos/sessions/{session.id}/start-analysis", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session.id
    assert data["status"] == "pending"

    # Verify session status changed
    db_session.refresh(session)
    assert session.status == "analyzing"

    # Verify job was created
    job = db_session.query(Job).filter(Job.session_id == session.id).first()
    assert job is not None
    assert job.status == "pending"


def test_start_analysis_already_analyzing(client, auth_header, db_session):
    headers, user = auth_header
    session = UploadSession(user_id=user.id, status="analyzing")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    resp = client.post(f"/videos/sessions/{session.id}/start-analysis", headers=headers)
    assert resp.status_code == 400
    assert "not in uploading state" in resp.json()["detail"]
