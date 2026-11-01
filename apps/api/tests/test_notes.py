import httpx
import pytest

from anthropic import BadRequestError
from app.services.extract import extract
from app.services.providers import DEMO_RESULT, DEMO_TRANSCRIPT


def test_create_from_text_stores_items_and_timezone(client, alice, make_note):
    n = make_note(alice)
    assert [t["text"] for t in n["tasks"]] == ["Finish the API docs"]
    assert n["messages"][0]["to"] == "Riya" and n["messages"][0]["src"] == "email Riya"
    assert {e["tz"] for e in n["events"]} == {"Asia/Kolkata"}  # events remember where they were spoken
    assert client.get("/api/notes", headers=alice).json()[0]["id"] == n["id"]


def test_create_from_text_accepts_windows_browser_timezone(client, alice):
    r = client.post("/api/notes", headers=alice, data={"text": "Meet the team at 3", "tz": "Asia/Calcutta"})
    assert r.status_code == 200, r.text
    assert {e["tz"] for e in r.json()["events"]} == {"Asia/Calcutta"}


def test_create_from_audio_uses_the_transcript(client, alice):
    r = client.post("/api/notes", headers=alice, data={"tz": "UTC"}, files={"audio": ("note.webm", b"bytes", "audio/webm")})
    assert r.status_code == 200 and r.json()["transcript"].startswith("dictated:")


def test_demo_mode_ignores_input_and_returns_fixed_sample(client, alice, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setattr("app.services.notes.extract", extract)
    r = client.post(
        "/api/notes",
        headers=alice,
        data={"text": "private note contents must not be stored", "tz": "UTC"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["transcript"] == DEMO_TRANSCRIPT
    assert r.json()["tasks"][0]["text"] == DEMO_RESULT["tasks"][0]["text"]


def test_bad_input_is_rejected(client, alice):
    assert client.post("/api/notes", headers=alice, data={"text": "   "}).status_code == 422
    assert client.post("/api/notes", headers=alice, data={"text": "hi", "tz": "Mars/Base"}).status_code == 422


def test_oversized_audio_is_rejected(client, alice, monkeypatch):
    monkeypatch.setattr("app.routers.notes.MAX_AUDIO", 10)
    r = client.post("/api/notes", headers=alice, data={"tz": "UTC"}, files={"audio": ("n.webm", b"x" * 50, "audio/webm")})
    assert r.status_code == 413


def test_users_only_see_their_own_notes(client, alice, bob, make_note):
    make_note(alice)
    assert client.get("/api/notes", headers=bob).json() == []
    assert len(client.get("/api/notes", headers=alice).json()) == 1


def test_delete_note_only_for_the_owner(client, alice, bob, make_note):
    n = make_note(alice)
    assert client.delete(f"/api/notes/{n['id']}", headers=bob).status_code == 204
    assert len(client.get("/api/notes", headers=alice).json()) == 1  # bob's delete did nothing
    assert client.delete(f"/api/notes/{n['id']}", headers=alice).status_code == 204
    assert client.get("/api/notes", headers=alice).json() == []


def test_hourly_limit_applies_per_user(client, alice, bob, redis_cli):
    uid = client.get("/api/auth/me", headers=alice).json()["id"]
    redis_cli.set(f"rl:notes:{uid}", 60)
    assert client.post("/api/notes", headers=alice, data={"text": "hi"}).status_code == 429
    assert client.post("/api/notes", headers=bob, data={"text": "hi"}).status_code == 200


def test_a_claude_failure_is_a_clear_502_and_saves_nothing(client, alice, monkeypatch):
    async def boom(transcript, tz):
        raise RuntimeError("anthropic is down")

    monkeypatch.setattr("app.services.notes.extract", boom)
    r = client.post("/api/notes", headers=alice, data={"text": "hello there"})
    assert r.status_code == 502 and "sort" in r.json()["detail"]
    assert client.get("/api/notes", headers=alice).json() == []


def test_exhausted_claude_credits_are_reported_clearly(client, alice, monkeypatch):
    error = BadRequestError(
        "credit balance too low",
        response=httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")),
        body={"error": {"message": "Your credit balance is too low to access the Anthropic API."}},
    )

    async def no_credits(transcript, tz):
        raise error

    monkeypatch.setattr("app.services.notes.extract", no_credits)
    r = client.post("/api/notes", headers=alice, data={"text": "hello", "tz": "Asia/Calcutta"})
    assert r.status_code == 502
    assert "credits are exhausted" in r.json()["detail"]


def test_unreadable_audio_is_a_422_not_a_crash(client, alice, monkeypatch):
    async def bad(data, suffix=".webm"):
        raise ValueError("not audio")

    monkeypatch.setattr("app.routers.notes.transcribe", bad)
    r = client.post("/api/notes", headers=alice, data={"tz": "UTC"}, files={"audio": ("n.webm", b"junk", "audio/webm")})
    assert r.status_code == 422
