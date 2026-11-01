import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..db import User
from ..deps import current_user, db, r
from ..security import DUMMY_HASH, hash_password, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
ALLOW_SIGNUP = os.getenv("ALLOW_SIGNUP", "true").lower() == "true"


class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class Register(Login):
    password: str = Field(min_length=10, max_length=128)


def token_for(user: User) -> dict:
    return {"access_token": make_token(user.id), "token_type": "bearer"}


@router.post("/register", status_code=201)
async def register(c: Register, s=Depends(db)):
    if not ALLOW_SIGNUP:
        raise HTTPException(403, "Sign-ups are closed")
    user = User(email=c.email.lower(), password_hash=hash_password(c.password))
    s.add(user)
    try:
        await s.commit()
    except IntegrityError:
        raise HTTPException(409, "That email is already registered")
    return token_for(user)


@router.post("/login")
async def login(c: Login, s=Depends(db)):
    email = c.email.lower()
    key = f"rl:login:{email}"  # brute-force guard: 10 tries per 15 minutes per email
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, 900)
    if n > 10:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    user = await s.scalar(select(User).where(User.email == email))
    ok = verify_password(user.password_hash if user else DUMMY_HASH, c.password)
    if not (user and ok):
        raise HTTPException(401, "Wrong email or password")
    return token_for(user)


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {"id": str(user.id), "email": user.email}
