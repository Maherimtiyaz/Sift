import os


def database_url() -> str:
    """DATABASE_URL, also accepting the plain postgres:// form that hosts like Render and Heroku hand out."""
    url = os.environ["DATABASE_URL"]
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")


def allowed_origins() -> list[str]:
    """The frontend plus any extra comma-separated ALLOWED_ORIGINS. Used for CORS and the WebSocket origin check."""
    extra = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return list(dict.fromkeys([frontend_url(), *extra]))
