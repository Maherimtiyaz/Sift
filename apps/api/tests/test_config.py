import pytest

from app.config import allowed_origins, database_url


@pytest.mark.parametrize("given,expected", [
    ("postgres://u:p@host:5432/db", "postgresql+asyncpg://u:p@host:5432/db"),        # Render / Heroku style
    ("postgresql://u:p@host/db?ssl=require", "postgresql+asyncpg://u:p@host/db?ssl=require"),
    ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),         # already right
])
def test_database_url_is_normalised(monkeypatch, given, expected):
    monkeypatch.setenv("DATABASE_URL", given)
    assert database_url() == expected


def test_allowed_origins(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com/")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://www.example.com, https://app.example.com/ ,")
    assert allowed_origins() == ["https://app.example.com", "https://www.example.com"]
    monkeypatch.delenv("ALLOWED_ORIGINS")
    assert allowed_origins() == ["https://app.example.com"]


def test_cors_preflight(client):
    ask = {"access-control-request-method": "POST", "access-control-request-headers": "authorization,content-type"}
    ok = client.options("/api/notes", headers={"origin": "http://localhost:3000", **ask})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in ok.headers
    bad = client.options("/api/notes", headers={"origin": "https://evil.example", **ask})
    assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
