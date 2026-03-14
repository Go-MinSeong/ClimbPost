"""End-to-end integration tests for ClimbPost server."""

import asyncio
import io
import tempfile
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.db.database import Base, get_db
from server.db.models import User, Gym, DeviceToken
from server.auth.service import create_jwt
from server.main import app


# ---------------------------------------------------------------------------
# Fixtures: file-based temp SQLite DB shared by app + worker
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_setup():
    """Create a file-based temp SQLite DB so the worker's SessionLocal works."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield engine, TestingSessionLocal

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def db_session(db_setup):
    """Direct DB session for test setup/assertions."""
    _, TestingSessionLocal = db_setup
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture()
def client(db_setup):
    """FastAPI TestClient with overridden DB."""
    with TestClient(app) as c:
        yield c


def _make_user(db, email="test@example.com", provider="apple"):
    user = User(email=email, provider=provider)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_gym(db, name="Test Gym"):
    gym = Gym(
        name=name,
        latitude=37.5665,
        longitude=126.9780,
        color_map={"red": "V3", "blue": "V5"},
    )
    db.add(gym)
    db.commit()
    db.refresh(gym)
    return gym


def _auth_header(user_id: str) -> dict:
    token = create_jwt(user_id)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Test 1-4: Full Server Upload → Mock Analysis → Clips Flow
# ===========================================================================


class TestFullUploadAnalysisClipsFlow:
    """End-to-end: upload → analysis → clip retrieval."""

    def test_create_session(self, client, db_session):
        user = _make_user(db_session)
        gym = _make_gym(db_session)
        headers = _auth_header(user.id)

        resp = client.post(
            "/videos/sessions",
            json={"gym_id": gym.id},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["gym_id"] == gym.id
        assert data["status"] == "uploading"

    def test_upload_video(self, client, db_session):
        user = _make_user(db_session)
        gym = _make_gym(db_session)
        headers = _auth_header(user.id)

        session_resp = client.post(
            "/videos/sessions", json={"gym_id": gym.id}, headers=headers
        )
        session_id = session_resp.json()["id"]

        fake_file = io.BytesIO(b"fake video content")
        resp = client.post(
            f"/videos/upload/{session_id}",
            files={"file": ("test.mov", fake_file, "video/quicktime")},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["session_id"] == session_id

    def test_start_analysis(self, client, db_session):
        user = _make_user(db_session)
        gym = _make_gym(db_session)
        headers = _auth_header(user.id)

        session_id = client.post(
            "/videos/sessions", json={"gym_id": gym.id}, headers=headers
        ).json()["id"]

        client.post(
            f"/videos/upload/{session_id}",
            files={"file": ("v.mov", io.BytesIO(b"data"), "video/quicktime")},
            headers=headers,
        )

        resp = client.post(
            f"/videos/sessions/{session_id}/start-analysis", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["session_id"] == session_id

    def test_full_flow_with_mock_analysis(self, client, db_session, db_setup):
        """Upload → start analysis → process_job (mock) → verify clips."""
        engine, TestingSessionLocal = db_setup
        user = _make_user(db_session)
        gym = _make_gym(db_session)
        headers = _auth_header(user.id)

        # 1. Create session
        session_id = client.post(
            "/videos/sessions", json={"gym_id": gym.id}, headers=headers
        ).json()["id"]

        # 2. Upload a file
        client.post(
            f"/videos/upload/{session_id}",
            files={"file": ("v.mov", io.BytesIO(b"fake"), "video/quicktime")},
            headers=headers,
        )

        # 3. Start analysis
        job_resp = client.post(
            f"/videos/sessions/{session_id}/start-analysis", headers=headers
        )
        job_id = job_resp.json()["id"]

        # 4. Check status is analyzing
        status_resp = client.get(
            f"/analysis/{session_id}/status", headers=headers
        )
        assert status_resp.json()["status"] == "analyzing"

        # 5. Run the worker's process_job with MOCK_ANALYSIS=True
        with (
            patch("server.queue.worker.MOCK_ANALYSIS", True),
            patch("server.queue.worker.SessionLocal", TestingSessionLocal),
            patch("server.queue.worker.asyncio.sleep", new_callable=AsyncMock),
            patch("server.queue.worker.send_push", new_callable=AsyncMock),
        ):
            asyncio.get_event_loop().run_until_complete(
                __import__("server.queue.worker", fromlist=["process_job"]).process_job(job_id)
            )

        # 6. Check completed status
        status_resp = client.get(
            f"/analysis/{session_id}/status", headers=headers
        )
        assert status_resp.json()["status"] == "completed"
        assert status_resp.json()["progress_pct"] == 100

        # 7. Get clips
        clips_resp = client.get(
            f"/clips?session_id={session_id}", headers=headers
        )
        assert clips_resp.status_code == 200
        clips = clips_resp.json()
        assert len(clips) >= 1

        # 8. Verify clip fields
        clip = clips[0]
        assert "id" in clip
        assert "difficulty" in clip
        assert "tape_color" in clip
        assert "result" in clip
        assert clip["result"] in ("success", "fail")

        # 9. Get single clip detail
        clip_detail_resp = client.get(
            f"/clips/{clip['id']}", headers=headers
        )
        assert clip_detail_resp.status_code == 200
        assert clip_detail_resp.json()["id"] == clip["id"]


# ===========================================================================
# Test 5-7: Auth Flow End-to-End
# ===========================================================================


class TestAuthFlow:
    """Auth: JWT creation, /me, /refresh."""

    def test_get_me(self, client, db_session):
        user = _make_user(db_session, email="me@test.com")
        headers = _auth_header(user.id)

        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user.id
        assert data["email"] == "me@test.com"
        assert data["provider"] == "apple"

    def test_refresh_token(self, client, db_session):
        user = _make_user(db_session)
        headers = _auth_header(user.id)

        resp = client.post("/auth/refresh", headers=headers)
        assert resp.status_code == 200
        new_token = resp.json()["access_token"]
        assert new_token  # non-empty

        # Use the new token
        new_headers = {"Authorization": f"Bearer {new_token}"}
        resp2 = client.get("/auth/me", headers=new_headers)
        assert resp2.status_code == 200
        assert resp2.json()["user_id"] == user.id

    def test_invalid_token_rejected(self, client):
        headers = {"Authorization": "Bearer invalid-token"}
        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 401


# ===========================================================================
# Test 8-10: Upload Authorization (user isolation)
# ===========================================================================


class TestUploadAuthorization:
    """Verify user A can't access user B's resources."""

    def test_user_b_cannot_upload_to_user_a_session(self, client, db_session):
        user_a = _make_user(db_session, email="a@test.com")
        user_b = _make_user(db_session, email="b@test.com")
        gym = _make_gym(db_session)

        headers_a = _auth_header(user_a.id)
        headers_b = _auth_header(user_b.id)

        # User A creates session
        session_id = client.post(
            "/videos/sessions", json={"gym_id": gym.id}, headers=headers_a
        ).json()["id"]

        # User B tries to upload to A's session → 404
        resp = client.post(
            f"/videos/upload/{session_id}",
            files={"file": ("v.mov", io.BytesIO(b"data"), "video/quicktime")},
            headers=headers_b,
        )
        assert resp.status_code == 404

    def test_user_b_cannot_start_analysis_on_user_a_session(self, client, db_session):
        user_a = _make_user(db_session, email="a@test.com")
        user_b = _make_user(db_session, email="b@test.com")
        gym = _make_gym(db_session)

        headers_a = _auth_header(user_a.id)
        headers_b = _auth_header(user_b.id)

        session_id = client.post(
            "/videos/sessions", json={"gym_id": gym.id}, headers=headers_a
        ).json()["id"]
        client.post(
            f"/videos/upload/{session_id}",
            files={"file": ("v.mov", io.BytesIO(b"data"), "video/quicktime")},
            headers=headers_a,
        )

        # User B tries to start analysis on A's session → 404
        resp = client.post(
            f"/videos/sessions/{session_id}/start-analysis", headers=headers_b
        )
        assert resp.status_code == 404

    def test_user_b_cannot_see_user_a_clips(self, client, db_session, db_setup):
        """User B gets empty list when querying User A's session clips."""
        engine, TestingSessionLocal = db_setup
        user_a = _make_user(db_session, email="a@test.com")
        user_b = _make_user(db_session, email="b@test.com")
        gym = _make_gym(db_session)

        headers_a = _auth_header(user_a.id)
        headers_b = _auth_header(user_b.id)

        # User A: full flow
        session_id = client.post(
            "/videos/sessions", json={"gym_id": gym.id}, headers=headers_a
        ).json()["id"]
        client.post(
            f"/videos/upload/{session_id}",
            files={"file": ("v.mov", io.BytesIO(b"data"), "video/quicktime")},
            headers=headers_a,
        )
        job_id = client.post(
            f"/videos/sessions/{session_id}/start-analysis", headers=headers_a
        ).json()["id"]

        with (
            patch("server.queue.worker.MOCK_ANALYSIS", True),
            patch("server.queue.worker.SessionLocal", TestingSessionLocal),
            patch("server.queue.worker.asyncio.sleep", new_callable=AsyncMock),
            patch("server.queue.worker.send_push", new_callable=AsyncMock),
        ):
            asyncio.get_event_loop().run_until_complete(
                __import__("server.queue.worker", fromlist=["process_job"]).process_job(job_id)
            )

        # User A sees clips
        clips_a = client.get(
            f"/clips?session_id={session_id}", headers=headers_a
        ).json()
        assert len(clips_a) >= 1

        # User B sees empty list
        clips_b = client.get(
            f"/clips?session_id={session_id}", headers=headers_b
        ).json()
        assert len(clips_b) == 0


# ===========================================================================
# Test 11-12: Push Registration Flow
# ===========================================================================


class TestPushRegistration:
    """Push notification device token registration."""

    def test_register_device_token(self, client, db_session):
        user = _make_user(db_session)
        headers = _auth_header(user.id)

        resp = client.post(
            "/push/register",
            json={"device_token": "abc123token"},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "registered"

        # Verify in DB
        dt = db_session.query(DeviceToken).filter(
            DeviceToken.user_id == user.id
        ).first()
        assert dt is not None
        assert dt.token == "abc123token"

    def test_register_same_token_twice(self, client, db_session):
        user = _make_user(db_session)
        headers = _auth_header(user.id)

        client.post(
            "/push/register",
            json={"device_token": "dup-token"},
            headers=headers,
        )

        resp = client.post(
            "/push/register",
            json={"device_token": "dup-token"},
            headers=headers,
        )
        # Second registration returns already_registered (still 201 status code)
        assert resp.json()["status"] == "already_registered"
