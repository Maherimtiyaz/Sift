import os
import pathlib

from cryptography.fernet import Fernet

# Must be set before the app is imported.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sift:sift@localhost:5432/sift_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "t" * 48)
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/google/callback")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
import redis as redis_sync  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SORTED = {
    "tasks": [{"text": "Finish the API docs", "due": "2026-10-20T10:00", "src": "finish the API docs"}],
    "events": [
        {"title": "Dentist", "start": "2026-10-22T16:00", "durationMin": 60, "when": "Thursday 4pm", "src": "dentist Thursday"},
        {"title": "Standup", "start": "", "durationMin": 30, "when": "", "src": "standup"},
    ],
    "messages": [{"to": "Riya", "body": "Hi Riya, the invoice will be with you by Friday.", "src": "email Riya"}],
}


def sync_url(url: str | None = None) -> str:
    return (url or os.environ["DATABASE_URL"]).replace("+asyncpg", "+psycopg2")


def alembic_cfg() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(sync_url())
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_cfg(), "head")  # tests run on the real migrations, not create_all
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def client(engine):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def redis_cli():
    return redis_sync.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


@pytest.fixture(autouse=True)
def _clean(engine, redis_cli):
    redis_cli.flushdb()
    with engine.begin() as c:
        c.execute(text("TRUNCATE users, notes, items, google_accounts RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def fake_ai(client, monkeypatch):
    async def fake_extract(transcript, tz):
        return {k: [dict(x) for x in v] for k, v in SORTED.items()}

    async def fake_transcribe(data, suffix=".webm"):
        return "dictated: email Riya about the invoice"

    monkeypatch.setattr("app.services.notes.extract", fake_extract)
    monkeypatch.setattr("app.routers.notes.transcribe", fake_transcribe)


def register(client, email="alice@example.com", password="correct-horse-battery") -> dict:
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture
def alice(client):
    return register(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return register(client, "bob@example.com")


@pytest.fixture
def make_note(client):
    def _make(headers, text="email Riya about the invoice"):
        r = client.post("/api/notes", headers=headers, data={"text": text, "tz": "Asia/Kolkata"})
        assert r.status_code == 200, r.text
        return r.json()

    return _make
