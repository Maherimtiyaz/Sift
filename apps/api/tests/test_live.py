import asyncio

import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect

from app.services.streaming import BYTES_PER_SEC, SAMPLE_RATE, LiveTranscriber, Seg


def pcm(seconds: float, value: int = 0) -> bytes:
    return np.full(int(seconds * SAMPLE_RATE), value, dtype=np.int16).tobytes()


def scripted(*calls):
    """A fake Whisper that returns the given segments, one list per call, and records its prompts."""
    prompts, it = [], iter(calls)

    def run(audio, prompt):
        prompts.append(prompt)
        return [Seg(*s) for s in next(it)]

    run.prompts = prompts
    return run


def test_settled_segments_commit_and_the_buffer_is_trimmed():
    async def go():
        run = scripted([(0, 2, " hello"), (2, 4, " world"), (4, 6, " again")],
                       [(0, 2, " again"), (2, 3.9, " more")],
                       [(0, 1.9, " more")])
        t = LiveTranscriber(run)
        t.feed(pcm(6))
        assert await t.step() == "again" and t.text == "hello world"      # last segment is still unsettled
        assert len(t.buf) == 2 * BYTES_PER_SEC                              # 4 s committed and cut off
        t.feed(pcm(2))
        assert await t.step() == "more" and t.text == "hello world again"
        assert await t.step(final=True) == "" and t.text == "hello world again more"
        assert run.prompts[1] == "hello world"                              # context carries over the cut
    asyncio.run(go())


def test_very_short_audio_is_not_transcribed_until_final():
    async def go():
        run = scripted([(0, 0.2, " hi")])
        t = LiveTranscriber(run)
        t.feed(pcm(0.2))
        assert await t.step() == "" and run.prompts == []
        await t.step(final=True)
        assert t.text == "hi"
    asyncio.run(go())


def test_long_unbroken_speech_is_committed_past_the_window():
    async def go():
        t = LiveTranscriber(scripted([(0, 20, " a"), (20, 30, " b")]), max_window=25)
        t.feed(pcm(30))
        assert await t.step() == "" and t.text == "a b"
    asyncio.run(go())


@pytest.fixture
def fake_whisper(monkeypatch):
    """Each 'word' is a run of one repeated sample value, so trimming the buffer never changes the words."""
    def runner(audio, prompt):
        v = np.round(audio * 32768).astype(int)
        cuts = np.flatnonzero(np.diff(v)) + 1
        starts, ends = [0, *cuts], [*cuts, len(v)]
        return [Seg(a / SAMPLE_RATE, b / SAMPLE_RATE, f"w{v[a]}") for a, b in zip(starts, ends) if v[a] != 0]

    monkeypatch.setattr("app.routers.live.make_runner", lambda: runner)
    monkeypatch.setattr("app.routers.live.TICK", 0.05)


def ticket(client, headers):
    return client.post("/api/ws-ticket", headers=headers).json()["ticket"]


def finish(ws):
    seen = []
    for _ in range(500):
        m = ws.receive_json()
        seen.append(m)
        if m["type"] in ("note", "error"):
            return m, seen
    raise AssertionError("no final message")


def test_live_session_streams_captions_then_saves_the_note(client, alice, fake_whisper):
    with client.websocket_connect(f"/api/ws/notes?ticket={ticket(client, alice)}") as ws:
        ws.send_json({"type": "start", "tz": "Asia/Kolkata"})
        live = []
        for word in (1, 2, 3):
            ws.send_bytes(pcm(2, word))
            live.append(ws.receive_json())  # a caption arrives while we are still "talking"
        ws.send_json({"type": "stop"})
        final, _ = finish(ws)
    assert all(m["type"] == "caption" for m in live) and any(m["committed"] or m["tail"] for m in live)
    assert final["type"] == "note" and final["note"]["transcript"] == "w1 w2 w3"
    saved = client.get("/api/notes", headers=alice).json()
    assert [n["id"] for n in saved] == [final["note"]["id"]]
    assert {e["tz"] for e in saved[0]["events"]} == {"Asia/Kolkata"}


def test_silence_reports_no_speech(client, alice, fake_whisper):
    with client.websocket_connect(f"/api/ws/notes?ticket={ticket(client, alice)}") as ws:
        ws.send_json({"type": "start"})
        ws.send_bytes(pcm(1, 0))
        ws.send_json({"type": "stop"})
        final, _ = finish(ws)
    assert final["type"] == "error" and "speech" in final["detail"]
    assert client.get("/api/notes", headers=alice).json() == []


def test_tickets_are_single_use_and_required(client, alice, fake_whisper):
    t = ticket(client, alice)
    with client.websocket_connect(f"/api/ws/notes?ticket={t}") as ws:
        ws.send_json({"type": "stop"})
        finish(ws)
    for url in (f"/api/ws/notes?ticket={t}", "/api/ws/notes?ticket=forged", "/api/ws/notes"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(url):
                pass
    assert client.post("/api/ws-ticket").status_code == 401


def test_other_sites_cannot_use_the_socket(client, alice, fake_whisper):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/ws/notes?ticket={ticket(client, alice)}", headers={"origin": "https://evil.example"}):
            pass


def test_live_sessions_count_against_the_hourly_limit(client, alice, redis_cli, fake_whisper):
    uid = client.get("/api/auth/me", headers=alice).json()["id"]
    redis_cli.set(f"rl:notes:{uid}", 60)
    with client.websocket_connect(f"/api/ws/notes?ticket={ticket(client, alice)}") as ws:
        assert ws.receive_json() == {"type": "error", "detail": "Hourly limit reached"}


def test_session_over_the_time_limit_is_cut_off_and_still_saved(client, alice, fake_whisper, monkeypatch):
    monkeypatch.setattr("app.routers.live.MAX_SECONDS", 3)
    with client.websocket_connect(f"/api/ws/notes?ticket={ticket(client, alice)}") as ws:
        ws.send_json({"type": "start"})
        ws.send_bytes(pcm(4, 7))
        final, seen = finish(ws)
    assert any(m["type"] == "notice" for m in seen) and final["note"]["transcript"] == "w7"
