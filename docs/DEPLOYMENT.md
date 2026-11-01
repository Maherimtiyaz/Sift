# Deployment

## Can the backend and frontend be deployed separately?

**Yes.** They are two independent programs that only talk over the network:

- `apps/api` is a FastAPI server (plus Postgres and Redis).
- `apps/web` is a Next.js server. It is the frontend; there is no separate static landing page.

Deploy each wherever you like, on different hosts and domains, and connect them with a handful of settings. The web app never needs the API's code, and the API never needs the web app's.

### The four connection points

| # | Connection | Setting | Where |
|---|---|---|---|
| 1 | Web server → API (all normal requests: login, notes, history, calendar) | `API_URL` | **web** |
| 2 | Browser → API (live captions WebSocket only) | `WS_URL` | **web** (read at runtime) |
| 3 | API → browser (redirect after Google sign-in) | `FRONTEND_URL` | **API** |
| 4 | API checks who may open the WebSocket / call it directly | `FRONTEND_URL`, `ALLOWED_ORIGINS` | **API** |

Plus one setting for Google: `GOOGLE_REDIRECT_URI` on the API and the same URI in Google Cloud.

### Why there is no cross-site cookie or CORS puzzle

- **Normal requests go server to server.** The browser only talks to the web app's own domain. The Next.js server forwards `/api/*` to the API, adding the login token. A browser never calls the API directly for these, so **CORS does not apply**.
- **The login cookie belongs to the web domain only** (`httpOnly`, `SameSite=Lax`, `Secure` over HTTPS). The API never sees cookies; it receives the token in an `Authorization` header. So the two can sit on completely different domains.
- **Live captions** open a WebSocket straight from the browser to the API. Browsers cannot attach login headers to a WebSocket, so the page first asks the web app for a **30-second, single-use ticket**, then connects with it. The API also refuses WebSocket connections whose `Origin` is not in the allow-list.
- **CORS is still configured** on the API for anyone who calls it directly from a browser (another web app, a mobile web view). It allows only `FRONTEND_URL` plus `ALLOWED_ORIGINS`, allows no cookies, and answers any other origin with a 400.

### Recommended domain layout

```
https://app.example.com   → web  (Next.js)
https://api.example.com   → API  (FastAPI)
```

Different subdomains, or entirely different domains, both work.

| Setting | Value |
|---|---|
| API `FRONTEND_URL` | `https://app.example.com` (exact, no trailing slash) |
| API `ALLOWED_ORIGINS` | empty, or extra origins such as `https://www.example.com` |
| API `GOOGLE_REDIRECT_URI` | `https://api.example.com/api/google/callback` |
| Web `API_URL` | `https://api.example.com` (or the host's private network address) |
| Web `WS_URL` | `wss://api.example.com` (`wss`, not `ws`) |

The origin must match **exactly** what the browser shows: `https://app.example.com` and `https://www.app.example.com` are different origins. List extras in `ALLOWED_ORIGINS`.

`WS_URL` is read when the web server runs, not when it is built, so you can build once and point it at any backend.

### AI provider configuration

Set `LLM_PROVIDER` and `TRANSCRIPTION_PROVIDER` on the **API service**, not in Vercel's web environment:

- Hosted Groq: `LLM_PROVIDER=groq`, `TRANSCRIPTION_PROVIDER=groq`, and `GROQ_API_KEY`.
- Anthropic note sorting: `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`; choose `groq` or `local` separately for transcription.
- Local services: `LLM_PROVIDER=ollama` with `OLLAMA_BASE_URL`/`OLLAMA_MODEL`, and `TRANSCRIPTION_PROVIDER=local`. Live captions use local faster-whisper even when uploaded audio uses Groq.
- Key-free fixed demo: set both providers to `mock`. The app shows a **DEMO MODE** label, ignores submitted note contents, and returns a fixed sample without calling AI services. Live captions are disabled.

Keep provider keys server-side and out of the web deployment. Provider limits, model availability, and data handling are controlled by each provider; check its current account documentation and use sample or non-sensitive data for public demos.

## Option A: Render (API and web as two services)

Render labels change over time; the settings below are what matters.

**1. Postgres and Redis** (same region as the services, so private addresses work)
- New → **PostgreSQL**. Copy the **Internal** connection URL.
- New → **Key Value** (Redis-compatible). Copy the **Internal** URL.

**2. API** (New → Web Service → connect your repo)
- Runtime: **Docker**. Root directory: `apps/api`.
- Health check path: `/api/health`.
- Instance: at least **2 GB RAM** (Whisper). The free 512 MB tier will run out of memory.
- Environment variables:

```
DATABASE_URL=<Postgres internal URL, postgres:// form is fine>
REDIS_URL=<Key Value internal URL>
LLM_PROVIDER=groq
TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=...
GROQ_LLM_MODEL=llama-3.3-70b-versatile
GROQ_WHISPER_MODEL=whisper-large-v3
# Optional alternative for note sorting: LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY=...
JWT_SECRET=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
TOKEN_ENCRYPTION_KEY=<python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
FRONTEND_URL=https://app.example.com
GOOGLE_CLIENT_ID=...            (optional)
GOOGLE_CLIENT_SECRET=...        (optional)
GOOGLE_REDIRECT_URI=https://api.example.com/api/google/callback
ALLOW_SIGNUP=true               (set to false after you register)
WHISPER_PRELOAD=true
DEFAULT_TZ=Asia/Kolkata
```

The container runs `alembic upgrade head` on every start, then the server on Render's `$PORT`. Add the custom domain `api.example.com` under Settings → Custom Domains and create the DNS record Render shows.

**3. Web** (New → Web Service, same repo)
- Runtime: **Docker**. Root directory: `apps/web`.
- Environment variables:

```
API_URL=https://api.example.com
WS_URL=wss://api.example.com
```

Add the custom domain `app.example.com`.

**4. Finish**
- Google Cloud → add `https://api.example.com/api/google/callback` as an authorised redirect URI.
- Open `https://app.example.com`, create your account, then set `ALLOW_SIGNUP=false` on the API service.

## Option B: Frontend on Vercel, API elsewhere

The API cannot run on Vercel (it needs a long-lived server for WebSockets, Postgres and Whisper). Put the API on Render, Fly.io, a VPS or any Docker host (Option A step 2, or Option C), then:

1. Vercel → Add New Project → import the repo → **Root Directory: `apps/web`** (framework: Next.js).
2. Environment variables: `API_URL=https://api.example.com`, `WS_URL=wss://api.example.com`.
3. Add the domain `app.example.com`, and set the API's `FRONTEND_URL` to it.

Limits to know:
- Vercel functions accept request bodies up to **4.5 MB**. Live captions are unaffected (audio goes over the WebSocket, not through Vercel). Only the fallback "record, then upload" path, and typed notes, go through it, so a very long fallback recording could be rejected. Function time limits depend on your plan; sorting a note takes a few seconds, so check yours. If either bites, host the web app as a container (Option A or C).

## Option C: One server with Docker and Caddy

For a VPS (Ubuntu 22.04 or later, at least 4 GB RAM) with DNS A records for `app.example.com` and `api.example.com` pointing at it. This path is not tested end to end by the author; the Caddy and compose files are small, but expect to read the logs once.

```bash
curl -fsSL https://get.docker.com | sh
git clone <your-repo-url> sift && cd sift
cp .env.example .env
nano .env
```

In `.env` set your AI providers and keys (the hosted Groq setup is shown above), `JWT_SECRET`, `TOKEN_ENCRYPTION_KEY`, and

```
FRONTEND_URL=https://app.example.com
WS_URL=wss://api.example.com
GOOGLE_REDIRECT_URI=https://api.example.com/api/google/callback
APP_DOMAIN=app.example.com
API_DOMAIN=api.example.com
```

Then:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose logs -f api web caddy
```

Caddy obtains HTTPS certificates by itself (ports 80 and 443 must be open). The app ports are bound to `127.0.0.1`, and Postgres and Redis are not published at all. After registering, set `ALLOW_SIGNUP=false` and run the same `up -d` command again.

To update: `git pull`, then the same `up -d --build` command. Migrations run automatically.

## Check that it works

```bash
curl https://api.example.com/api/health          # includes "ok" and "demo_mode"
curl https://app.example.com/api/live-config     # includes "wsUrl" and "demoMode"
```

Then in the browser: create an account, tap the orb and speak. In DevTools → Network → WS you should see a connection to `wss://api.example.com/api/ws/notes` and captions arriving. If you only see "Recording. Tap Stop when you're done", the WebSocket is not reachable; check `WS_URL`, and that `FRONTEND_URL` exactly equals the address in the browser bar.

## Sizing and operations

- **Whisper is CPU-heavy.** Live captions run the `base` model on the API's CPU while you speak. This has **not been benchmarked**: start with 2 vCPU and 4 GB RAM and watch caption lag. If captions fall behind, use `WHISPER_LIVE_MODEL=tiny`, or leave `WS_URL` empty to turn live captions off (recording then uploads when you stop).
- **Model download.** Models download from Hugging Face on first use and are lost when a container is replaced unless you keep a volume (the compose file does). `WHISPER_PRELOAD=true` moves the download to startup.
- **Backups.** Everything important is in Postgres. Schedule `pg_dump` (Render offers backups for paid databases).
- **Scaling.** Run one API instance at first. A live session lives on the instance that accepted it; tickets and rate limits live in Redis, so more instances are possible later. Transcription runs one job at a time per instance.
- **Migrations.** Applied at container start. Create new ones with `alembic revision --autogenerate -m "describe change"` in `apps/api`; a test fails if models and migrations disagree.

## Google Calendar in production

- Authorised redirect URI in Google Cloud: `https://api.example.com/api/google/callback`, identical to `GOOGLE_REDIRECT_URI`.
- Consent screen in **Testing** status: refresh tokens expire after 7 days (reconnect in Settings). Publish the app to avoid this.
- Keep `TOKEN_ENCRYPTION_KEY` safe and unchanged; changing it makes stored Google connections unreadable (users reconnect).

## The standalone demo page

`apps/demo/sift-demo.html` is a single file with no backend: the original animated demo. It can be hosted on any static host (Netlify, GitHub Pages, S3) as a marketing page. Outside its original artifact viewer its sorting uses a simple built-in rule-based fallback instead of a hosted LLM, and live captions depend on the visitor's browser speech recognition (Chrome and Safari). Treat it as a visual demo, not the product.

## Manual steps and open items

You must do yourself:
- Configure an AI provider and its key if required, create a JWT secret and encryption key, and fill `.env`.
- Create the Google Cloud project and OAuth client (optional feature).
- DNS records and domains; HTTPS (Render, Vercel and Caddy do it for you).
- Set `ALLOW_SIGNUP=false` after creating your account.
- Backups.

Not built: the WhatsApp/Telegram bot, the weekly digest, password reset, email verification, server-side session revocation. Not verified by the author: Docker image builds, real AI-provider/Google calls, and the browser UI. The CI workflow builds both Docker images on every push, which will surface Dockerfile problems.
