import pytest


def ids(note):
    return {"task": note["tasks"][0]["id"], "dentist": note["events"][0]["id"],
            "standup": note["events"][1]["id"], "msg": note["messages"][0]["id"]}


def test_toggle_done_and_ownership(client, alice, bob, make_note):
    i = ids(make_note(alice))
    assert client.patch(f"/api/items/{i['task']}", headers=alice, json={"done": True}).json()["done"] is True
    assert client.patch(f"/api/items/{i['task']}", headers=bob, json={"done": True}).status_code == 404
    assert client.patch(f"/api/items/{i['task']}", headers=alice, json={}).status_code == 422


def test_edit_fields(client, alice, make_note):
    i = ids(make_note(alice))
    r = client.patch(f"/api/items/{i['task']}", headers=alice, json={"data": {"text": "  Ship the docs  "}})
    assert r.json()["text"] == "Ship the docs" and r.json()["src"] == "finish the API docs"
    r = client.patch(f"/api/items/{i['standup']}", headers=alice, json={"data": {"start": "2026-10-23T09:30", "durationMin": 15}})
    assert r.json()["start"] == "2026-10-23T09:30" and r.json()["durationMin"] == 15
    saved = client.get("/api/notes", headers=alice).json()[0]
    assert saved["tasks"][0]["text"] == "Ship the docs"


@pytest.mark.parametrize("payload", [
    {"data": {"title": "x"}},                 # a task has no title
    {"data": {"text": "   "}},                # text can't be blank
    {"data": {"due": "x" * 5001}},            # too long
])
def test_bad_task_edits_are_rejected(client, alice, make_note, payload):
    i = ids(make_note(alice))
    assert client.patch(f"/api/items/{i['task']}", headers=alice, json=payload).status_code == 422


@pytest.mark.parametrize("data", [{"start": "tomorrow-ish"}, {"durationMin": 2}, {"durationMin": 5000}, {"body": "x"}])
def test_bad_event_edits_are_rejected(client, alice, make_note, data):
    i = ids(make_note(alice))
    assert client.patch(f"/api/items/{i['standup']}", headers=alice, json={"data": data}).status_code == 422


def test_move_between_lists_keeps_text_and_source(client, alice, make_note):
    i = ids(make_note(alice))
    r = client.patch(f"/api/items/{i['task']}", headers=alice, json={"kind": "event"}).json()
    assert r["kind"] == "event" and r["title"] == "Finish the API docs" and r["start"] == "" and r["when"] == "2026-10-20T10:00"
    r = client.patch(f"/api/items/{i['msg']}", headers=alice, json={"kind": "task"}).json()
    assert r["kind"] == "task" and r["text"].startswith("Hi Riya")
    saved = client.get("/api/notes", headers=alice).json()[0]
    assert len(saved["tasks"]) == 1 and len(saved["events"]) == 3 and saved["messages"] == []


def test_delete_item(client, alice, bob, make_note):
    i = ids(make_note(alice))
    assert client.delete(f"/api/items/{i['task']}", headers=bob).status_code == 404
    assert client.delete(f"/api/items/{i['task']}", headers=alice).status_code == 204
    assert client.get("/api/notes", headers=alice).json()[0]["tasks"] == []
    assert client.delete(f"/api/items/{i['task']}", headers=alice).status_code == 404


def connect_google(client, engine, headers):
    from sqlalchemy import text
    uid = client.get("/api/auth/me", headers=headers).json()["id"]
    with engine.begin() as c:
        c.execute(text("INSERT INTO google_accounts(owner, email, refresh_token) VALUES (:o, 'a@gmail.com', 'enc')"), {"o": uid})


def test_calendar_sync_flow(client, engine, alice, bob, make_note, monkeypatch):
    calls = []

    async def fake_push(owner, enc, r, *, title, start, duration_min, tz):
        calls.append((title, start, duration_min, tz))
        return {"id": "g1", "htmlLink": "https://calendar.google.com/event?eid=g1"}

    monkeypatch.setattr("app.services.calendar.push_event", fake_push)
    i = ids(make_note(alice))
    url = f"/api/items/{i['dentist']}/calendar"

    assert client.post(url, headers=alice).status_code == 409          # not connected yet
    connect_google(client, engine, alice)
    assert client.post(url, headers=bob).status_code == 404            # not bob's event
    r = client.post(url, headers=alice)
    assert r.status_code == 200 and r.json()["link"].endswith("g1")
    assert calls == [("Dentist", "2026-10-22T16:00", 60, "Asia/Kolkata")]
    assert client.post(url, headers=alice).json()["already_synced"] is True and len(calls) == 1  # no duplicates

    # once it is in Google, Sift refuses edits and moves instead of silently drifting out of sync
    assert client.patch(f"/api/items/{i['dentist']}", headers=alice, json={"data": {"title": "x"}}).status_code == 409
    assert client.patch(f"/api/items/{i['dentist']}", headers=alice, json={"kind": "task"}).status_code == 409
    assert client.patch(f"/api/items/{i['dentist']}", headers=alice, json={"done": True}).status_code == 200


def test_sync_needs_a_start_time_or_an_override(client, engine, alice, make_note, monkeypatch):
    async def fake_push(owner, enc, r, *, title, start, duration_min, tz):
        return {"id": "g2", "htmlLink": "https://cal/x"}

    monkeypatch.setattr("app.services.calendar.push_event", fake_push)
    i = ids(make_note(alice))
    connect_google(client, engine, alice)
    url = f"/api/items/{i['standup']}/calendar"
    assert client.post(url, headers=alice).status_code == 422
    assert client.post(url, headers=alice, json={"start": "2026-10-24T11:00"}).status_code == 200
    assert client.post(f"/api/items/{i['task']}/calendar", headers=alice).status_code == 404  # tasks aren't events


def test_google_connect_and_callback_guards(client, alice, redis_cli):
    uid = client.get("/api/auth/me", headers=alice).json()["id"]
    url = client.get("/api/google/connect", headers=alice).json()["url"]
    state = url.split("state=")[1].split("&")[0]
    assert "client_id=test-client" in url and "access_type=offline" in url
    assert redis_cli.get(f"gstate:{state}") == uid
    assert client.get("/api/google/callback?code=x&state=forged").status_code == 400
    r = client.get("/api/google/callback?error=access_denied", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"].endswith("/settings?google=denied")
    assert client.get("/api/google/status", headers=alice).json() == {"connected": False, "email": None}
