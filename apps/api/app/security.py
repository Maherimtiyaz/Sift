import datetime as dt
import os
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

SECRET = os.environ["JWT_SECRET"]
assert len(SECRET) >= 32, "JWT_SECRET must be at least 32 characters"
DAYS = int(os.getenv("JWT_DAYS", "7"))

_ph = PasswordHasher()
DUMMY_HASH = _ph.hash("not-a-real-password")  # lets login take equal time for unknown emails


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def make_token(user_id: uuid.UUID) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + dt.timedelta(days=DAYS)},
                      SECRET, algorithm="HS256")


def read_token(token: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(jwt.decode(token, SECRET, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
