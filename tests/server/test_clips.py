"""Tests for /clips endpoints."""
from server.db.models import UploadSession, RawVideo, Clip


def _make_clip_chain(db_session, user, **clip_kwargs):
    """Helper: create session → raw_video → clip chain."""
    session = UploadSession(user_id=user.id, status="completed")
    db_session.add(session)
    db_session.flush()

    rv = RawVideo(session_id=session.id, file_url="/fake.mp4")
    db_session.add(rv)
    db_session.flush()

    defaults = dict(
        raw_video_id=rv.id,
        difficulty="V3",
        result="success",
        is_me=True,
        start_time=0.0,
        end_time=30.0,
        duration_sec=30.0,
    )
    defaults.update(clip_kwargs)
    clip = Clip(**defaults)
    db_session.add(clip)
    db_session.commit()
    db_session.refresh(clip)
    return session, rv, clip


def test_list_clips_empty(client, auth_header):
    headers, _ = auth_header
    resp = client.get("/clips", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_clips_with_data(client, auth_header, db_session):
    headers, user = auth_header
    _make_clip_chain(db_session, user)
    _make_clip_chain(db_session, user, difficulty="V5")

    resp = client.get("/clips", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_clips_filter_difficulty(client, auth_header, db_session):
    headers, user = auth_header
    _make_clip_chain(db_session, user, difficulty="V3")
    _make_clip_chain(db_session, user, difficulty="V5")

    resp = client.get("/clips", params={"difficulty": "V3"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["difficulty"] == "V3"


def test_list_clips_filter_result(client, auth_header, db_session):
    headers, user = auth_header
    _make_clip_chain(db_session, user, result="success")
    _make_clip_chain(db_session, user, result="fail")

    resp = client.get("/clips", params={"result": "fail"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["result"] == "fail"


def test_list_clips_filter_is_me(client, auth_header, db_session):
    headers, user = auth_header
    _make_clip_chain(db_session, user, is_me=True)
    _make_clip_chain(db_session, user, is_me=False)

    resp = client.get("/clips", params={"is_me": True}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_me"] is True


def test_get_clip_detail(client, auth_header, db_session):
    headers, user = auth_header
    _, _, clip = _make_clip_chain(db_session, user, difficulty="V4")

    resp = client.get(f"/clips/{clip.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == clip.id
    assert resp.json()["difficulty"] == "V4"


def test_get_clip_not_found(client, auth_header):
    headers, _ = auth_header
    resp = client.get("/clips/nonexistent-id", headers=headers)
    assert resp.status_code == 404
