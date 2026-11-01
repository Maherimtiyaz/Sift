import os

import redis.asyncio as redis
from fastapi import Depends, Header, HTTPException

from .db import Item, Note, Session, User
from .security import read_token

r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)


async def db():
    async with Session() as s:
        yield s


async def current_user(authorization: str = Header(default=""), s=Depends(db)) -> User:
    scheme, _, token = authorization.partition(" ")
    uid = read_token(token) if scheme.lower() == "bearer" else None
    user = await s.get(User, uid) if uid else None
    if not user:
        raise HTTPException(401, "Not signed in", headers={"WWW-Authenticate": "Bearer"})
    return user


async def spend(user_id) -> bool:
    """Count one expensive call (Whisper + Claude) against the user's hourly allowance of 60."""
    key = f"rl:notes:{user_id}"
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, 3600)
    return n <= 60


async def limit(user: User = Depends(current_user)):
    if not await spend(user.id):
        raise HTTPException(429, "Hourly limit reached")


async def owned_item(item_id: int, user: User = Depends(current_user), s=Depends(db)) -> Item:
    item = await s.get(Item, item_id)
    note = await s.get(Note, item.note_id) if item else None
    if not note or note.user_id != user.id:  # 404, not 403: don't reveal that the id exists
        raise HTTPException(404, "Not found")
    return item
