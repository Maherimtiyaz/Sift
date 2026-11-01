from conftest import register


def test_register_login_me(client):
    h = register(client, "a@example.com")
    assert client.get("/api/auth/me", headers=h).json()["email"] == "a@example.com"
    r = client.post("/api/auth/login", json={"email": "A@Example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"  # email is case-insensitive


def test_duplicate_email_conflicts(client):
    register(client, "a@example.com")
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "another-long-password"})
    assert r.status_code == 409


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client, "a@example.com")
    bad = client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope-nope-nope"})
    unknown = client.post("/api/auth/login", json={"email": "who@example.com", "password": "nope-nope-nope"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()


def test_register_validation(client):
    assert client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "nope", "password": "long-enough-password"}).status_code == 422


def test_signups_can_be_closed(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.ALLOW_SIGNUP", False)
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "long-enough-password"})
    assert r.status_code == 403


def test_login_is_throttled(client):
    register(client, "a@example.com")
    codes = [client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-wrong"}).status_code
             for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_protected_routes_need_a_valid_token(client):
    for headers in ({}, {"authorization": "Bearer garbage"}, {"authorization": "Basic abc"}):
        for method, path in [("get", "/api/notes"), ("post", "/api/notes"), ("patch", "/api/items/1"),
                             ("delete", "/api/items/1"), ("get", "/api/google/status"), ("get", "/api/auth/me")]:
            assert getattr(client, method)(path, headers=headers).status_code == 401, (method, path)
    health = client.get("/api/health").json()
    assert health["ok"] is True and isinstance(health["demo_mode"], bool)


def test_health_reports_demo_mode(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert client.get("/api/health").json() == {"ok": True, "demo_mode": True}
