"""Tests for /auth endpoints."""


def test_login_unsupported_provider(client):
    resp = client.post("/auth/login", json={"provider": "facebook", "id_token": "tok"})
    assert resp.status_code == 400
    assert "Unsupported provider" in resp.json()["detail"]


def test_refresh_token_success(client, auth_header):
    headers, user = auth_header
    resp = client.post("/auth/refresh", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_refresh_token_no_auth(client):
    resp = client.post("/auth/refresh")
    assert resp.status_code in (401, 403)


def test_me_success(client, auth_header):
    headers, user = auth_header
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user.id
    assert data["email"] == "test@test.com"
    assert data["provider"] == "apple"


def test_me_invalid_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert resp.status_code == 401
