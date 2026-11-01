# Sift

Ramble for a minute, get your day sorted. You talk (or type), and Sift turns it into **tasks**, **calendar items** and **draft messages**, with live captions while you speak and one-tap adding to Google Calendar.

## What works, and what does not

| Area | Status |
|---|---|
| Record or type a note, sorted by a configurable AI provider into tasks / events / messages | Built |
| Live captions over WebSocket (words appear as you speak) | Built. Falls back to record-then-upload if the socket is unavailable |
| Edit text, move items between lists, delete with undo, tick tasks, set event times | Built |
| Source highlighting (tap an item to see the words it came from) | Built |
| Accounts: register, login (JWT in an httpOnly cookie), per-user data | Built |
| Google Calendar sync (OAuth, refresh token stored encrypted) | Built. Needs your own Google Cloud setup |
| History of past notes | Built |
| Database migrations (Alembic), 46 API tests on real Postgres + Redis, CI | Built |
| **WhatsApp / Telegram bot** | **Not built** |
| **Weekly digest email/worker** | **Not built** |
| Password reset, email verification | Not built |
| Editing an event after it is in Google Calendar | Not supported on purpose (Sift locks it; edit it in Google) |

**Not verified by the author** (could not be done in the build environment): building the Docker images, real local Whisper transcription (model download was blocked), real Groq, Anthropic and Google OAuth calls, and clicking through the UI in a browser. Everything else was run: API tests, a production build of the web app, and an end-to-end run of the API plus the built web server (login, proxy, migrations, WebSocket origin and ticket checks, CORS).

There is no separate marketing "landing page". The **web app** (`apps/web`) is the frontend. `apps/demo/sift-demo.html` is a standalone, backend-free demo page (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#the-standalone-demo-page)).

## How it fits together

```
 Browser ──HTTPS──▶  apps/web  (Next.js)  ──server-to-server──▶  apps/api (FastAPI) ──▶ Postgres
    │                  logs you in, keeps the JWT                      │    └──────────▶ Redis
    │                  in an httpOnly cookie, proxies /api/*           └─▶ Groq / Anthropic / Ollama, Whisper, Google Calendar
    └──WebSocket (live captions, one-time ticket)──────────────────────▶ apps/api
```

```
sift/
├── apps/
│   ├── api/                 FastAPI backend
│   │   ├── app/             main.py, config.py, db.py, deps.py, security.py, schemas.py
│   │   │   ├── routers/     auth, notes, items, live (WebSocket), google
│   │   │   └── services/    extract (Groq / Anthropic / Ollama / demo), transcribe + streaming (Whisper)
│   │   ├── alembic/         database migrations
│   │   ├── tests/           pytest suite
│   │   └── Dockerfile, requirements*.txt
│   ├── web/                 Next.js frontend (TypeScript)
│   │   ├── src/app/         pages (/, /history, /settings, /login) and route handlers (/api/*)
│   │   ├── src/components/  Orb (animated), Results
│   │   ├── src/lib/         api client, recorder, live-caption hook
│   │   ├── public/          pcm-worklet.js (audio capture)
│   │   └── Dockerfile
│   └── demo/sift-demo.html  standalone demo page
├── docs/                    DEPLOYMENT.md, ARCHITECTURE.md
├── docker-compose.yml       db, redis, api, web
├── docker-compose.override.yml   dev only: publishes db and redis on localhost
├── .env.example             every setting, documented
├── Makefile                 shortcuts
└── .github/workflows/ci.yml tests, typecheck, Docker builds
```

## Prerequisites

You need **one** of these setups:

- **Docker path (simplest):** Docker Desktop or Docker Engine with Compose v2 (`docker compose version` works).
- **Without Docker for the app:** Python 3.12, Node.js 22 (`nvm use` reads `apps/web/.nvmrc`), and Docker only for Postgres and Redis (or your own Postgres 16 and Redis 7).

You also need:
- A **Groq API key** (https://console.groq.com/keys) for the recommended hosted setup, or an Anthropic key / local Ollama install. Demo mode needs no AI keys.
- Internet access on first run if you use local Whisper; it downloads a speech model.
- A browser on `http://localhost` or HTTPS. Browsers block the microphone on plain `http://` for any other host.
- Optional: a Google Cloud project, for calendar sync (see below).

## Quick start with Docker

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"    # paste into JWT_SECRET
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # paste into TOKEN_ENCRYPTION_KEY
# edit .env: set GROQ_API_KEY, JWT_SECRET, TOKEN_ENCRYPTION_KEY
# for the key-free fixed-output demo, set LLM_PROVIDER=mock and TRANSCRIPTION_PROVIDER=mock

docker compose up --build
```

Open http://localhost:3000, choose **New here? Create an account**, then tap the orb. The API runs its database migrations on every start.

Then, so nobody else can sign up and use your AI provider account, set `ALLOW_SIGNUP=false` in `.env` and run `docker compose up -d`.

First live session: Whisper downloads its model (the `whisper` volume keeps it afterwards). With `WHISPER_PRELOAD=true` this happens at startup instead of during your first note.

## Run without Docker for the app (development)

Terminal 1, database and Redis (the override file publishes them on localhost):

```bash
docker compose up -d db redis
```

Terminal 2, API:

```bash
cd apps/api
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
set -a; source ../../.env; set +a
export DATABASE_URL=postgresql+asyncpg://sift:sift@localhost:5432/sift REDIS_URL=redis://localhost:6379/0
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Terminal 3, web:

```bash
cd apps/web
cp .env.example .env.local      # API_URL and WS_URL already point at localhost:8000
npm ci
npm run dev                      # http://localhost:3000
```

## Tests

```bash
make test          # starts db + redis, creates the sift_test database, runs the API tests
make typecheck     # typechecks the web app
```

The tests wipe only the `sift_test` database and Redis database 1, never your dev data. They mock AI providers and Google, so they need no provider keys. To run them by hand: start Postgres and Redis (superuser `sift`/`sift` on localhost, database `sift_test`), then `cd apps/api && pytest -q`.

## Settings

All API settings live in the root `.env` (full list with comments in [.env.example](.env.example)). The important ones:

| Variable | Needed | What it does |
|---|---|---|
| `LLM_PROVIDER` | yes | `groq`, `anthropic`, `ollama`, or `mock`; selects note sorting |
| `TRANSCRIPTION_PROVIDER` | yes | `groq`, `local`, or `mock`; selects uploaded-audio transcription |
| `GROQ_API_KEY` | for Groq | Groq key used for Llama sorting and/or uploaded-audio transcription |
| `GROQ_LLM_MODEL`, `GROQ_WHISPER_MODEL` | optional | Override the Groq chat and speech models |
| `ANTHROPIC_API_KEY` | for Anthropic | Optional Claude key; `CLAUDE_MODEL` selects the model |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | for Ollama | Local OpenAI-compatible Ollama endpoint and model |
| `JWT_SECRET` | yes | Signs logins. 32+ characters, keep secret |
| `DATABASE_URL`, `REDIS_URL` | yes | Postgres and Redis. `postgres://` style URLs are accepted |
| `FRONTEND_URL` | yes | Exact address of the web app. Used for the Google redirect, WebSocket origin check and CORS |
| `ALLOW_SIGNUP` | | `false` closes registration |
| `ALLOWED_ORIGINS` | | Extra origins for CORS and the WebSocket, comma separated |
| `TOKEN_ENCRYPTION_KEY`, `GOOGLE_*` | for calendar | Google Calendar sync |
| `WHISPER_MODEL`, `WHISPER_LIVE_MODEL`, `WHISPER_LANGUAGE`, `WHISPER_PRELOAD`, `LIVE_*` | | Local Whisper tuning; live captions always use local Whisper |

The web app (`apps/web/.env.local`, or container environment) reads two settings **at runtime**:

| Variable | What it does |
|---|---|
| `API_URL` | Where the Next.js **server** reaches the API (server to server) |
| `WS_URL` | Where the **browser** reaches the API for live captions. `ws://` locally, `wss://` in production. Empty disables live captions (uploads still work) |

### AI providers and demo mode

- **Groq (recommended):** set `LLM_PROVIDER=groq`, `TRANSCRIPTION_PROVIDER=groq`, and `GROQ_API_KEY`. Uploaded audio uses Groq Whisper; note sorting uses the configured Groq Llama model. Live captions use local Whisper and fall back to uploaded-audio transcription if the socket is unavailable. Groq account limits and model availability can change; check your account’s limits page. For public demos, use sample audio and non-sensitive notes rather than personal data.
- **Anthropic:** set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. Audio transcription remains independently selectable with `TRANSCRIPTION_PROVIDER`.
- **Local:** install Ollama and pull a model (for example, `ollama pull llama3.2`), set `LLM_PROVIDER=ollama`, and set `TRANSCRIPTION_PROVIDER=local` for faster-whisper. Local speech models and LLMs need disk space and memory; they can be slow on a laptop. In Docker, set `OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` to reach Ollama on your host.
- **Demo:** set both `LLM_PROVIDER=mock` and `TRANSCRIPTION_PROVIDER=mock`. Sift labels the screen **DEMO MODE**, ignores submitted note contents, and returns a fixed sample result without making any AI-provider calls or requiring AI keys. Live captions are disabled in this mode.

The Groq and Anthropic credentials belong **only on the API server**. Keep keys in `.env` or your host’s server-side environment settings; never put them in the web app’s environment or commit them to Git. If a key has ever been exposed, revoke it with its provider. The committed `.env.example` contains placeholders, not credentials.

## Google Calendar setup (optional)

1. https://console.cloud.google.com → create a project → **APIs & Services → Library** → enable **Google Calendar API**.
2. **OAuth consent screen** → External → add your own Google account as a **test user**.
3. **Credentials → Create credentials → OAuth client ID → Web application**. Add the authorised redirect URI `http://localhost:8000/api/google/callback` (in production: `https://YOUR-API-DOMAIN/api/google/callback`).
4. Put the client ID and secret in `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`), generate `TOKEN_ENCRYPTION_KEY`, restart the API.
5. In Sift, open **Settings → Connect Google Calendar**.

While the Google app is in **Testing** status, Google expires the refresh token after 7 days and you must reconnect. Publishing the app removes this; an unverified published app shows a warning screen, which is fine for personal use.

## Production

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**: deploying the API and the web app together or on separate hosts and domains, with Render, Vercel and a single-server (Docker + Caddy) walkthrough, plus CORS, domains and environment variables.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Couldn't sort your note right now" | Check `LLM_PROVIDER`, its corresponding key or local service, and the selected model; `docker compose logs api` shows the real error |
| Recording says "Recording. Tap Stop when you're done" instead of showing captions | Live captions are off or unreachable: check `WS_URL`, that the browser can open it, and that `FRONTEND_URL` exactly matches the address in the browser bar |
| Redirected back to /login | Session expired (7 days), or `JWT_SECRET` changed. Sign in again |
| Microphone blocked | Allow it in the browser, and use `http://localhost` or HTTPS |
| Google says `redirect_uri_mismatch` | `GOOGLE_REDIRECT_URI` must match the authorised URI in Google Cloud exactly |
| Google connection stops working after about a week | Consent screen is in Testing status (see above) |
| `relation "users" already exists` when migrating | Your database predates Alembic. Run `alembic stamp head` once, or reset with `make reset` (deletes data) |
| Port 5432 or 6379 already in use | Stop your local Postgres/Redis, or edit `docker-compose.override.yml` |
| First live session is slow | The Whisper model is downloading. Keep `WHISPER_PRELOAD=true` |

## Security notes

- Never commit `.env`. The repository ignores it.
- Set `ALLOW_SIGNUP=false` after creating your account. Hosted AI providers can incur usage costs or enforce rate limits.
- Logins last 7 days and cannot be revoked server-side before then (logging out only deletes the cookie). Rotate `JWT_SECRET` to sign everyone out.
- Do not expose Postgres or Redis to the internet. The production compose file does not publish them.
- Use HTTPS in production. The login cookie is marked `Secure` whenever the site is served over HTTPS.
