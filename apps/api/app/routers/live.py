import asyncio
import json
import logging
import os
import secrets
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, WebSocket
from fastapi.encoders import jsonable_encoder

from ..config import allowed_origins
from ..db import User
from ..deps import current_user, db, r, spend
from ..schemas import note_out
from ..services.notes import SortingFailed, save_note
from ..services.streaming import BYTES_PER_SEC, LiveTranscriber, make_runner

log = logging.getLogger("sift.live")
router = APIRouter(prefix="/api", tags=["live"])
TICK = float(os.getenv("LIVE_TICK_SECONDS", "1.5"))
MAX_SECONDS = int(os.getenv("LIVE_MAX_SECONDS", "300"))
ALLOWED = allowed_origins()


@router.post("/ws-ticket")
async def ws_ticket(user: User = Depends(current_user)):
    """Browsers can't set headers on a WebSocket, so trade the login for a 30-second, single-use ticket."""
    ticket = secrets.token_urlsafe(24)
    await r.set(f"wsticket:{ticket}", str(user.id), ex=30)
    return {"ticket": ticket}


@router.websocket("/ws/notes")
async def live_note(ws: WebSocket, ticket: str = "", s=Depends(db)):
    origin = ws.headers.get("origin")
    if origin and origin.rstrip("/") not in ALLOWED:  # blocks pages on other sites from using this socket
        return await ws.close(code=1008)
    uid = await r.getdel(f"wsticket:{ticket}") if ticket else None
    user = await s.get(User, uuid.UUID(uid)) if uid else None
    if not user:
        return await ws.close(code=1008)
    await ws.accept()
    if not await spend(user.id):
        await ws.send_json({"type": "error", "detail": "Hourly limit reached"})
        return await ws.close()

    tr, tz, total = LiveTranscriber(make_runner()), "UTC", 0

    async def ticker():
        try:
            while True:
                await asyncio.sleep(TICK)
                if not tr.lock.locked():
                    tail = await tr.step()
                    await ws.send_json({"type": "caption", "committed": tr.text, "tail": tail})
        except Exception:  # socket closed or the model failed: the final pass below reports real problems
            log.debug("caption ticker stopped", exc_info=True)

    task = asyncio.create_task(ticker())
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes") is not None:
                total += len(msg["bytes"])
                tr.feed(msg["bytes"])
                if total > MAX_SECONDS * BYTES_PER_SEC:
                    await ws.send_json({"type": "notice", "text": f"Reached the {MAX_SECONDS // 60}-minute limit"})
                    break
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except ValueError:
                    continue
                if data.get("type") == "start":
                    try:
                        ZoneInfo(str(data.get("tz")))
                        tz = str(data["tz"])
                    except Exception:
                        pass  # keep UTC
                elif data.get("type") == "stop":
                    break
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    try:
        await tr.step(final=True)
        if not tr.text:
            await ws.send_json({"type": "error", "detail": "I didn’t catch any speech. Try again."})
        else:
            note = await save_note(s, user, tr.text, tz)
            await ws.send_json({"type": "note", "note": jsonable_encoder(note_out(note))})
    except SortingFailed as e:
        log.exception("live note sorting failed")
        await ws.send_json({"type": "error", "detail": str(e)})
    except Exception:
        log.exception("live note failed")
        await ws.send_json({"type": "error", "detail": "Couldn’t sort your note. Try again."})
    await ws.close()
