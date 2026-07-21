import pytest

pytestmark = pytest.mark.asyncio


async def test_register_login_me_flow(client):
    reg = await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "correcthorse"})
    assert reg.status_code == 200
    token = reg.json()["token"]

    login = await client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "correcthorse"})
    assert login.status_code == 200
    assert login.json()["token"]

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "a@b.com"
    assert body["demo_mode"] is True
    assert body["has_aws_credentials"] is False


async def test_duplicate_register_rejected(client):
    await client.post("/api/v1/auth/register", json={"email": "dup@b.com", "password": "correcthorse"})
    dup = await client.post("/api/v1/auth/register", json={"email": "dup@b.com", "password": "correcthorse"})
    assert dup.status_code == 409


async def test_wrong_password_rejected(client):
    await client.post("/api/v1/auth/register", json={"email": "c@b.com", "password": "correcthorse"})
    bad = await client.post("/api/v1/auth/login", json={"email": "c@b.com", "password": "wrong"})
    assert bad.status_code == 401


async def test_protected_route_requires_auth(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_healthz_no_auth(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
