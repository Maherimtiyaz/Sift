import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
CAL_SCOPE = "https://www.googleapis.com/auth/calendar.events"  # create/edit events only, not full calendar access
SCOPES = f"openid email {CAL_SCOPE}"

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REDIRECT_URI = os.environ["GOOGLE_REDIRECT_URI"]
fernet = Fernet(os.environ["TOKEN_ENCRYPTION_KEY"])


class GoogleRevoked(Exception):
    """The refresh token no longer works. The user must reconnect."""


def encrypt(token: str) -> str:
    return fernet.encrypt(token.encode()).decode()


def auth_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true", "state": state,
    })


async def _post(url: str, **kw) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15) as c:
        return await c.post(url, **kw)


async def exchange_code(code: str) -> dict:
    resp = await _post(TOKEN_URL, data={
        "code": code, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"})
    if resp.status_code != 200:
        raise HTTPException(400, "Google rejected the sign-in code")
    return resp.json()


async def user_email(access: str) -> str | None:
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.get(USERINFO_URL, headers={"Authorization": f"Bearer {access}"})
    return resp.json().get("email") if resp.status_code == 200 else None


async def revoke(enc_refresh: str) -> None:
    try:
        await _post(REVOKE_URL, data={"token": fernet.decrypt(enc_refresh.encode()).decode()})
    except Exception:
        pass  # best effort: we delete our copy either way


async def access_token(owner: str, enc_refresh: str, r) -> str:
    if cached := await r.get(f"gaccess:{owner}"):
        return cached
    resp = await _post(TOKEN_URL, data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "refresh_token",
        "refresh_token": fernet.decrypt(enc_refresh.encode()).decode()})
    if resp.status_code != 200:
        if resp.json().get("error") == "invalid_grant":
            raise GoogleRevoked()
        raise HTTPException(502, "Could not reach Google")
    j = resp.json()
    await r.set(f"gaccess:{owner}", j["access_token"], ex=max(60, j.get("expires_in", 3600) - 120))
    return j["access_token"]


async def push_event(owner: str, enc_refresh: str, r, *, title: str, start: str,
                     duration_min: int, tz: str) -> dict:
    try:
        s = datetime.fromisoformat(start)
    except ValueError:
        raise HTTPException(422, "start must look like 2026-10-22T16:00")
    body = {
        "summary": title,
        "description": "Created by Sift from a voice note.",
        "start": {"dateTime": s.isoformat(), "timeZone": tz},
        "end": {"dateTime": (s + timedelta(minutes=duration_min)).isoformat(), "timeZone": tz},
        "reminders": {"useDefault": True},
    }
    for attempt in (1, 2):
        token = await access_token(owner, enc_refresh, r)
        resp = await _post(EVENTS_URL, json=body, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401 and attempt == 1:  # cached token went stale, refresh once
            await r.delete(f"gaccess:{owner}")
            continue
        break
    if resp.status_code == 401:
        raise GoogleRevoked()
    if resp.status_code != 200:
        raise HTTPException(502, f"Google Calendar error {resp.status_code}")
    return resp.json()
