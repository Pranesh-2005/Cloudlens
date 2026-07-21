import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-bytes-long-for-hs256")
os.environ.setdefault("ENCRYPTION_KEY", "ocGnzbPk86LtfQOpdehFobVvNAHQTt8oa0gYb1XEZy0=")
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = ""
os.environ["FRONTEND_ORIGIN"] = "http://localhost:3000"


@pytest.fixture(autouse=True)
def _isolated_sqlite_db(tmp_path, monkeypatch):
    """Fresh sqlite file per test so tests don't leak state, fresh cache/engine too."""
    from app import db as db_module
    from app.cache import cache
    from app.ratelimit import limiter

    db_path = tmp_path / f"{uuid.uuid4().hex}.db"
    monkeypatch.chdir(tmp_path)
    db_module.reset_engine()
    cache.clear()
    limiter.reset()
    yield
    db_module.reset_engine()


@pytest_asyncio.fixture
async def app():
    from app.main import create_app

    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def registered_user(client):
    resp = await client.post("/api/v1/auth/register", json={"email": "demo@cloudlens.dev", "password": "hunter2pass"})
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}}
