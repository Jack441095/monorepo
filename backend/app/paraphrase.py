"""Free Para-phase router for the hosted rewrite engine.

The browser talks to this backend (POST /v1/paraphrase) which proxies a
Server-Sent-Events stream from the engine service
(products/nite-paraphrase/engine/server.py). The backend never touches
Ollama directly and never stores the pasted text: events are streamed
through and dropped, matching the "rewrites are not stored" privacy
promise of the product.

The free tier allows `paraphrase_free_daily_limit` rewrites per client IP,
using the in-process limiter from rate_limit.py. Existing paid unlocks remain
redeemable while their records and short-lived tokens are still valid; this
router no longer creates new Para-phase charges.
"""
from __future__ import annotations

import hmac
from collections.abc import AsyncIterator

import anyio
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from . import paraphrase_orders
from .config import settings
from .database import get_db
from .rate_limit import rate_limit
from .schemas import ParaphraseRedemptionRequest, ParaphraseRequest

router = APIRouter(prefix="/v1/paraphrase", tags=["paraphrase"])

# Injectable for tests (httpx.MockTransport); production uses the real client.
_client_factory = httpx.AsyncClient

# Engine dial budget: fail fast when the engine is down, but allow long
# streams once connected (rewrites stream token-by-token). Read has no
# timeout by design; output size is bounded in _forward instead.
_ENGINE_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0)

# Output budget: input is capped at 8000 chars (schemas.py), so a 256 KiB
# SSE cap is generous for any legitimate rewrite and bounds a runaway or
# malicious engine from holding a worker indefinitely.
_MAX_STREAM_BYTES = 256 * 1024


def _gate() -> None:
    """404 when the product is config-gated off (estate norm)."""
    if not settings.paraphrase_enabled:
        raise HTTPException(status_code=404, detail="not found")


def _unlocked(request: Request) -> bool:
    bearer = request.headers.get("X-Paraphrase-Token", "")
    if not bearer:
        return False
    if settings.paraphrase_unlock_token and hmac.compare_digest(
        bearer, settings.paraphrase_unlock_token
    ):
        return True
    return paraphrase_orders.verify_unlock_token(bearer)


def _limit(request: Request) -> None:
    if _unlocked(request):
        return
    rate_limit("paraphrase", settings.paraphrase_free_daily_limit, 24 * 60 * 60.0)(request)


async def _forward(client: httpx.AsyncClient, resp: httpx.Response) -> AsyncIterator[bytes]:
    """Re-emit the engine's SSE stream verbatim, closing everything on exit.

    Bounded at _MAX_STREAM_BYTES: a runaway engine is cut off instead of
    holding the worker connection open indefinitely.
    """
    emitted = 0
    try:
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                chunk = f"data:{line[len('data:'):]}\n\n".encode("utf-8")
                emitted += len(chunk)
                if emitted > _MAX_STREAM_BYTES:
                    break
                yield chunk
    finally:
        # StreamingResponse cancels its task when the browser disconnects.
        # Shield both closes so cancellation cannot interrupt cleanup.
        with anyio.CancelScope(shield=True):
            try:
                await resp.aclose()
            finally:
                await client.aclose()


@router.post("", response_class=StreamingResponse)
async def paraphrase(
    body: ParaphraseRequest,
    _: None = Depends(_gate),
    __: None = Depends(_limit),
) -> StreamingResponse:
    headers = {}
    if settings.paraphrase_service_token:
        headers["Authorization"] = f"Bearer {settings.paraphrase_service_token}"
    url = f"{settings.paraphrase_engine_url.rstrip('/')}/v1/paraphrase"

    client = None
    try:
        client = _client_factory(timeout=_ENGINE_TIMEOUT, headers=headers)
        request = client.build_request("POST", url, json=body.model_dump())
        resp = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        if client is not None:
            await client.aclose()
        raise HTTPException(status_code=503, detail="paraphrase engine unavailable") from exc

    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=resp.status_code, detail="paraphrase engine error")

    return StreamingResponse(
        _forward(client, resp),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/redemption")
async def paraphrase_redemption(
    body: ParaphraseRedemptionRequest,
    _: None = Depends(_gate),
    db: Session = Depends(get_db),
) -> dict:
    """Exchange a completed payment's hint for a signed session-unlock token.

    No authentication. The Stripe redirect back to the page includes the
    hint in the URL; the client polls this endpoint until it returns 200
    or a 30-second timeout expires.  Idempotent: redeeming the same hint
    twice returns a fresh token (the server tracks redeemed_at for audit
    only, never for access control).
    """
    result = paraphrase_orders.redeem(db, body.hint)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown or unpaid hint")
    token, expires_at = result
    db.commit()
    return {"unlock_token": token, "expires": expires_at.isoformat()}
