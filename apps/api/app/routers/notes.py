import logging
import os
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select

from ..db import Note, User
from ..deps import current_user, db, limit
from ..schemas import note_out
from ..services.notes import SortingFailed, save_note
from ..services.transcribe import transcribe

log = logging.getLogger("sift.notes")
router = APIRouter(prefix="/api/notes", tags=["notes"])
MAX_AUDIO = 25 * 1024 * 1024  # 25 MB, roughly 20+ minutes of voice


@router.post("", dependencies=[Depends(limit)])
async def create_note(audio: UploadFile | None = File(None), text: str | None = Form(None),
                      tz: str = Form("UTC"), user: User = Depends(current_user), s=Depends(db)):
    try:
        ZoneInfo(tz)
    except Exception:
        raise HTTPException(422, "Unknown timezone")
    if audio:
        data = await audio.read(MAX_AUDIO + 1)
        if len(data) > MAX_AUDIO:
            raise HTTPException(413, "Recording is too long")
        suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
        try:
            transcript = await transcribe(data, suffix)
        except Exception:
            log.exception("transcription failed")
            raise HTTPException(422, "Couldn’t read that audio. Try recording again.")
    else:
        transcript = (text or "").strip()
    if not transcript:
        raise HTTPException(422, "Send audio or text")
    try:
        return note_out(await save_note(s, user, transcript, tz))
    except SortingFailed as e:
        log.exception("sorting failed")
        raise HTTPException(502, str(e))


@router.get("")
async def list_notes(count: int = Query(20, ge=1, le=100, alias="limit"),
                     user: User = Depends(current_user), s=Depends(db)):
    rows = await s.scalars(select(Note).where(Note.user_id == user.id)
                           .order_by(Note.created_at.desc()).limit(count))
    return [note_out(n) for n in rows]


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: uuid.UUID, user: User = Depends(current_user), s=Depends(db)):
    note = await s.get(Note, note_id)
    if note and note.user_id == user.id:
        await s.delete(note)
        await s.commit()
