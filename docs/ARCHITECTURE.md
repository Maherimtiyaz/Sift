# Architecture

## Request flows

**Typed note or upload:** browser → `POST /api/notes` on the web server → proxied to the API with the user's session token → (audio: selected transcription provider) → selected LLM provider sorts the transcript into validated JSON → stored → returned.

**Live note:** browser opens the mic → `POST /api/ws-ticket` (through the web proxy) → browser connects to `WS_URL/api/ws/notes?ticket=…` → an audio worklet streams 16 kHz mono PCM every ~250 ms → every 1.5 s the API transcribes only the not-yet-settled audio and sends `caption` messages (settled text + changing tail). Segments that ended more than a second before the end of the buffer are committed and cut off, so work per step stays small however long you talk → on stop the API transcribes the rest, sorts and saves the note, and sends it back on the same socket.

**Google Calendar:** Settings → `GET /api/google/connect` returns Google's consent URL (with a one-time `state`) → Google redirects to `/api/google/callback` on the API → refresh token stored Fernet-encrypted → the API then redirects the browser to `FRONTEND_URL/settings`. Syncing an event calls the Calendar API once; Redis locks stop double clicks creating duplicates.

AI providers are selected independently with `LLM_PROVIDER` and `TRANSCRIPTION_PROVIDER`. Uploaded recordings use the selected transcription provider; live WebSocket captions use local faster-whisper. When either provider is `mock`, the API health response enables a fixed-output demo, and the web app labels it and disables live captions.

## API

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /api/health` | no | liveness and demo-mode status |
| `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` | no / no / yes | accounts (login is rate-limited per email) |
| `POST /api/notes` | yes | multipart `audio` or form `text`, plus `tz` |
| `GET /api/notes?limit=` · `DELETE /api/notes/{id}` | yes | history |
| `PATCH /api/items/{id}` · `DELETE /api/items/{id}` | yes | body `{done?, kind?, data?}`: tick, move to another list, edit; delete |
| `POST /api/items/{id}/calendar` · `POST /api/notes/{id}/calendar` | yes | add one event / all events to Google Calendar |
| `GET /api/google/connect` · `GET /api/google/callback` · `GET /api/google/status` · `DELETE /api/google` | yes (callback: one-time state) | Google connection |
| `POST /api/ws-ticket` · `WS /api/ws/notes?ticket=` | yes / ticket | live captions |

Web app routes: `/` (record), `/history`, `/settings`, `/login`; route handlers `/api/auth/{login,register,logout}` (set or clear the cookie), `/api/live-config` (returns `WS_URL` and demo status), and a catch-all `/api/*` proxy.

## Data model (Postgres, managed by Alembic)

`users` (id, email, password hash) → `notes` (id, user, transcript, created) → `items` (id, note, `kind` task | event | message, `data` JSONB, `done`). `google_accounts` (owner = user id, email, encrypted refresh token). Redis holds rate-limit counters, OAuth `state`, WebSocket tickets, cached Google access tokens and sync locks.

## Security model

- Passwords: Argon2. Logins: HS256 JWT, 7 days, in an `httpOnly` `SameSite=Lax` cookie on the web domain. The API sees only the bearer token.
- Every note, item and Google connection is scoped to its owner; another user's item answers 404.
- Per-user limit of 60 note calls per hour (REST and live share it); uploads capped at 25 MB; live sessions capped at 5 minutes.
- WebSocket: single-use 30-second ticket plus an `Origin` allow-list.
- CORS: only `FRONTEND_URL` and `ALLOWED_ORIGINS`, no credentials.
- Events already in Google Calendar cannot be edited or moved in Sift, so the two never silently disagree.
- Demo mode ignores submitted note contents and returns fixed sample data without calling an AI provider.
