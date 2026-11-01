import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..db import Item
from ..deps import db, owned_item
from ..schemas import ItemPatch, item_out

router = APIRouter(prefix="/api/items", tags=["items"])
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "UTC")

FIELDS = {"task": {"text", "due"}, "event": {"title", "start", "durationMin", "when"}, "message": {"to", "body"}}
TEXT_KEY = {"task": "text", "event": "title", "message": "body"}
LOCKED = "This event is already in Google Calendar. Change it there."


def convert(old: str, new: str, d: dict) -> dict:
    """Move an item to another list, keeping its text and source phrase."""
    out = {TEXT_KEY[new]: d.get(TEXT_KEY[old], "")}
    if d.get("src"):
        out["src"] = d["src"]
    if old == "task" and new == "event":
        out["when"] = d.get("due", "")
    if old == "event" and new == "task":
        out["due"] = d.get("when", "")
    if new == "event":
        out |= {"start": "", "durationMin": 60, "tz": DEFAULT_TZ}
    return out


def clean(kind: str, patch: dict) -> dict:
    bad = set(patch) - FIELDS[kind]
    if bad:
        raise HTTPException(422, f"Can't edit {', '.join(sorted(bad))} on a {kind}")
    out = {}
    for k, v in patch.items():
        if k == "durationMin":
            if not isinstance(v, int) or isinstance(v, bool) or not 5 <= v <= 1440:
                raise HTTPException(422, "durationMin must be between 5 and 1440")
        elif k == "start":
            v = v or ""
            if v:
                try:
                    datetime.fromisoformat(str(v))
                except ValueError:
                    raise HTTPException(422, "start must look like 2026-10-22T16:00")
        else:
            v = str(v or "").strip()
            if len(v) > 5000:
                raise HTTPException(422, f"{k} is too long")
            if k == TEXT_KEY[kind] and not v:
                raise HTTPException(422, f"{k} can't be empty")
        out[k] = v
    return out


@router.patch("/{item_id}")
async def patch_item(body: ItemPatch, item: Item = Depends(owned_item), s=Depends(db)):
    if body.done is None and body.kind is None and body.data is None:
        raise HTTPException(422, "Nothing to change")
    synced = item.kind == "event" and bool(item.data.get("google_event_id"))
    kind, data = item.kind, dict(item.data)
    if body.kind and body.kind != kind:
        if synced:
            raise HTTPException(409, LOCKED)
        data, kind = convert(kind, body.kind, data), body.kind
    if body.data is not None:
        if synced:
            raise HTTPException(409, LOCKED)
        data = {**data, **clean(kind, body.data)}
    if body.done is not None:
        item.done = body.done
    item.kind, item.data = kind, data  # new dict object, so SQLAlchemy sees the JSONB change
    await s.commit()
    return item_out(item)


@router.delete("/{item_id}", status_code=204)
async def delete_item(item: Item = Depends(owned_item), s=Depends(db)):
    await s.delete(item)
    await s.commit()
