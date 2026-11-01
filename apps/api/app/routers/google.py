import os
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..config import frontend_url
from ..db import GoogleAccount, Item, Note, User
from ..deps import current_user, db, owned_item, r
from ..services import calendar as cal

router = APIRouter(prefix="/api", tags=["google"])
FRONTEND_URL = frontend_url()
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "UTC")


@router.get("/google/connect")
async def connect(user: User = Depends(current_user)):
    state = secrets.token_urlsafe(24)
    await r.set(f"gstate:{state}", str(user.id), ex=600)  # the state remembers who is connecting
    return {"url": cal.auth_url(state)}


@router.get("/google/callback")  # public on purpose: Google redirects the browser here
async def callback(code: str | None = None, state: str = "", error: str | None = None, s=Depends(db)):
    back = f"{FRONTEND_URL}/settings"
    if error or not code:
        return RedirectResponse(f"{back}?google=denied")
    owner = await r.getdel(f"gstate:{state}")  # one-time use
    if not owner:
        raise HTTPException(400, "Invalid or expired state")
    tokens = await cal.exchange_code(code)
    if cal.CAL_SCOPE not in tokens.get("scope", ""):
        return RedirectResponse(f"{back}?google=missing_scope")
    if not tokens.get("refresh_token"):
        return RedirectResponse(f"{back}?google=no_refresh")
    enc = cal.encrypt(tokens["refresh_token"])
    email = await cal.user_email(tokens["access_token"])
    acct = await s.get(GoogleAccount, owner)
    if acct:
        acct.refresh_token, acct.email = enc, email
    else:
        s.add(GoogleAccount(owner=owner, email=email, refresh_token=enc))
    await s.commit()
    await r.set(f"gaccess:{owner}", tokens["access_token"], ex=max(60, tokens.get("expires_in", 3600) - 120))
    return RedirectResponse(f"{back}?google=connected")


@router.get("/google/status")
async def status(user: User = Depends(current_user), s=Depends(db)):
    acct = await s.get(GoogleAccount, str(user.id))
    return {"connected": bool(acct), "email": acct.email if acct else None}


@router.delete("/google", status_code=204)
async def disconnect(user: User = Depends(current_user), s=Depends(db)):
    owner = str(user.id)
    acct = await s.get(GoogleAccount, owner)
    if acct:
        await cal.revoke(acct.refresh_token)
        await s.delete(acct)
        await s.commit()
    await r.delete(f"gaccess:{owner}")


class Override(BaseModel):
    start: str | None = None  # fix a missing or wrong time: "2026-10-22T16:00"
    duration_min: int | None = Field(None, ge=5, le=1440)


async def _sync(item: Item, body: Override, s, owner: str) -> dict:
    d = item.data
    if d.get("google_event_id"):
        return {"id": item.id, "already_synced": True, "link": d.get("google_link")}
    start = body.start or d.get("start")
    if not start:
        raise HTTPException(422, 'This event has no start time. Send {"start": "YYYY-MM-DDTHH:MM"}.')
    acct = await s.get(GoogleAccount, owner)
    if not acct:
        raise HTTPException(409, "Google Calendar isn't connected")
    lock = f"lock:item:{item.id}"
    if not await r.set(lock, "1", nx=True, ex=30):  # blocks double-clicks creating duplicates
        raise HTTPException(409, "Sync already in progress")
    try:
        ev = await cal.push_event(
            owner, acct.refresh_token, r, title=d.get("title") or "Untitled", start=start,
            duration_min=body.duration_min or d.get("durationMin") or 60, tz=d.get("tz", DEFAULT_TZ))
        item.data = {**d, "start": start, "google_event_id": ev["id"], "google_link": ev.get("htmlLink")}
        await s.commit()
    except cal.GoogleRevoked:
        await s.delete(acct)
        await s.commit()
        raise HTTPException(401, "Google access expired or was revoked. Reconnect your calendar.")
    finally:
        await r.delete(lock)
    return {"id": item.id, "synced": True, "link": item.data["google_link"]}


@router.post("/items/{item_id}/calendar")
async def sync_item(body: Override | None = None, item: Item = Depends(owned_item),
                    user: User = Depends(current_user), s=Depends(db)):
    if item.kind != "event":
        raise HTTPException(404, "Event not found")
    return await _sync(item, body or Override(), s, str(user.id))


@router.post("/notes/{note_id}/calendar")
async def sync_note(note_id: uuid.UUID, user: User = Depends(current_user), s=Depends(db)):
    note = await s.get(Note, note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(404, "Note not found")
    results = []
    for it in (i for i in note.items if i.kind == "event"):
        try:
            results.append(await _sync(it, Override(), s, str(user.id)))
        except HTTPException as e:
            results.append({"id": it.id, "error": e.detail})
    return {"results": results}
