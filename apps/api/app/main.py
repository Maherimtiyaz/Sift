import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import allowed_origins
from .routers import auth, google, items, live, notes
from .services.providers import is_demo_mode, llm_provider, transcription_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    llm_provider()
    transcription_provider()
    if not is_demo_mode() and os.getenv("WHISPER_PRELOAD", "").lower() == "true":
        # Live captions use local Whisper even when uploaded audio uses Groq.
        from .services.streaming import preload

        app.state.preload = asyncio.create_task(asyncio.to_thread(preload))
    yield


# Schema changes are applied by Alembic (`alembic upgrade head`), not at startup.
app = FastAPI(title="Sift", lifespan=lifespan)
# The bundled web app calls the API through its own server, so it never needs CORS. This is for browsers or
# apps that call the API directly. Tokens travel in the Authorization header, so cookies are not allowed.
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["authorization", "content-type"], max_age=600)
for r in (auth.router, notes.router, items.router, google.router, live.router):
    app.include_router(r)


@app.get("/api/health")
async def health():
    return {"ok": True, "demo_mode": is_demo_mode()}
