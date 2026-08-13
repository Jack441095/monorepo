from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import admin, auth, commerce, downloads, licensing
from .config import settings
from .database import engine

# uvicorn attaches handlers to its own "uvicorn" logger tree, not the root
# logger, so INFO messages from our "nitedsp" logger would otherwise never
# reach any handler even with propagate=True (no handler == no output,
# regardless of level). Attach our own handler directly.
_nitedsp_logger = logging.getLogger("nitedsp")
_nitedsp_logger.setLevel(logging.INFO)
if not _nitedsp_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    _nitedsp_logger.addHandler(_handler)
    _nitedsp_logger.propagate = False

def _allowed_cors_origins() -> list[str]:
    """The website is a separate origin from the API (Section 6) --
    credentialed cross-origin requests need an explicit allow-list, never
    a wildcard, since we allow_credentials. Phase 5.6, Section 16: also
    allow the "www." variant of an apex domain automatically, since a real
    site commonly gets visited both ways, without needing a second setting
    -- "do not allow wildcard authenticated CORS" is satisfied by this
    still being a short, explicit, derived list, not a pattern match.
    """
    origins = [settings.nite_dsp_public_url]
    parsed = urlparse(settings.nite_dsp_public_url)
    if parsed.hostname and not parsed.hostname.startswith("www."):
        www_netloc = f"www.{parsed.netloc}"
        origins.append(f"{parsed.scheme}://{www_netloc}")
    return origins


app = FastAPI(title="NITE DSP Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(licensing.router)
app.include_router(commerce.router)
app.include_router(downloads.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict:
    """Liveness only -- confirms the process is up and serving requests.
    Never checks dependencies (that's /ready's job) so a slow/degraded
    database doesn't make an otherwise-healthy process look dead."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready(response: Response) -> dict:
    """Readiness -- confirms critical dependencies (currently: the
    database) are actually reachable, not just that the process started.
    Returns 503 rather than raising, so a load balancer's readiness probe
    gets a clean signal instead of a stack trace. Never includes secrets or
    connection strings in the response."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if not db_ok:
        response.status_code = 503
    return {"status": "ok" if db_ok else "unavailable", "database": db_ok}
