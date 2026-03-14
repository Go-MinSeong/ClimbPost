"""Tests for /push endpoints."""


def test_register_device_token(client, auth_header):
    headers, _ = auth_header
    resp = client.post(
        "/push/register",
        json={"device_token": "abc123device"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "registered"


def test_register_duplicate_token(client, auth_header):
    headers, _ = auth_header
    client.post(
        "/push/register",
        json={"device_token": "abc123device"},
        headers=headers,
    )
    resp = client.post(
        "/push/register",
        json={"device_token": "abc123device"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "already_registered"


def test_register_no_auth(client):
    resp = client.post("/push/register", json={"device_token": "abc123device"})
    assert resp.status_code in (401, 403)
