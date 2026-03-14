"""Tests for /analysis endpoints."""
from server.db.models import UploadSession, Job


def test_get_status_pending(client, auth_header, db_session):
    headers, user = auth_header
    session = UploadSession(user_id=user.id, status="analyzing")
    db_session.add(session)
    db_session.flush()
    job = Job(session_id=session.id, status="pending")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(session)

    resp = client.get(f"/analysis/{session.id}/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["progress_pct"] == 0
    assert data["status"] == "analyzing"


def test_get_status_processing(client, auth_header, db_session):
    headers, user = auth_header
    session = UploadSession(user_id=user.id, status="analyzing")
    db_session.add(session)
    db_session.flush()
    job = Job(session_id=session.id, status="processing")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(session)

    resp = client.get(f"/analysis/{session.id}/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["progress_pct"] == 50


def test_get_status_completed(client, auth_header, db_session):
    headers, user = auth_header
    session = UploadSession(user_id=user.id, status="completed")
    db_session.add(session)
    db_session.flush()
    job = Job(session_id=session.id, status="completed")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(session)

    resp = client.get(f"/analysis/{session.id}/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["progress_pct"] == 100


def test_get_status_not_found(client, auth_header):
    headers, _ = auth_header
    resp = client.get("/analysis/nonexistent-id/status", headers=headers)
    assert resp.status_code == 404
