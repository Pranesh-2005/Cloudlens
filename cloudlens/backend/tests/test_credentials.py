import pytest

pytestmark = pytest.mark.asyncio


async def test_credentials_encryption_roundtrip(client, registered_user):
    resp = await client.put(
        "/api/v1/credentials",
        json={"access_key_id": "AKIAABCDEFGH1234", "secret_access_key": "supersecretvalue", "region": "us-west-2"},
        headers=registered_user["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["last4"] == "1234"
    assert "supersecretvalue" not in resp.text
    assert "AKIAABCDEFGH1234" not in resp.text

    me = await client.get("/api/v1/me", headers=registered_user["headers"])
    assert me.json()["has_aws_credentials"] is True
    assert me.json()["demo_mode"] is False

    # roundtrip actually decrypts to the original values
    from app.credentials import decrypt
    from app.db import get_sessionmaker
    from app.auth import get_user_by_email

    sm = get_sessionmaker()
    async with sm() as session:
        user = await get_user_by_email(session, "demo@cloudlens.dev")
        access_key_id, secret_access_key = decrypt(user.credential)
        assert access_key_id == "AKIAABCDEFGH1234"
        assert secret_access_key == "supersecretvalue"


async def test_delete_credentials(client, registered_user):
    await client.put(
        "/api/v1/credentials",
        json={"access_key_id": "AKIAABCDEFGH1234", "secret_access_key": "supersecretvalue"},
        headers=registered_user["headers"],
    )
    resp = await client.delete("/api/v1/credentials", headers=registered_user["headers"])
    assert resp.status_code == 200
    me = await client.get("/api/v1/me", headers=registered_user["headers"])
    assert me.json()["has_aws_credentials"] is False
