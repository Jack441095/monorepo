"""
Commerce -- Paddle sandbox integration + webhook handling.

docs/COMMERCE_PROVIDER_DECISION.md picked Paddle (Merchant of Record).
Section 95: sandbox/mock only, never live payments -- there is no code path
here that can charge a real card; `paddle_api_key` is only ever read from
environment/secrets and a blank key (the default, since no Paddle account
exists yet -- docs/HUMAN_COMMERCIAL_REQUIREMENTS.md) puts PaddleProvider
into a documented mock mode instead of attempting a real API call.

Webhook signature verification implements Paddle Billing's actual documented
scheme (HMAC-SHA256 over "{timestamp}:{raw_body}", header format
"ts=<unix>;h1=<hex>") so the verification logic itself is real and testable
independent of having a live Paddle account -- see tests/test_commerce.py.
"""
from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import email_templates, models
from .config import settings
from .database import get_db
from .email import send_email

router = APIRouter(prefix="/webhooks", tags=["commerce"])


class WebhookVerificationError(Exception):
    pass


class CommerceProvider(ABC):
    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool: ...

    @abstractmethod
    def create_checkout_url(self, product_id: str, customer_email: str) -> str: ...


class PaddleProvider(CommerceProvider):
    """Sandbox-only. `configured` is False whenever no Paddle account exists
    yet (paddle_api_key empty) -- callers must check this before attempting
    anything that would need a real API round-trip; webhook *verification*
    still works without it, since that only needs the shared webhook
    secret, not the API key."""

    def __init__(self) -> None:
        self.configured = bool(settings.paddle_api_key)

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        if not settings.paddle_webhook_secret:
            raise WebhookVerificationError("No paddle_webhook_secret configured")
        parts = dict(
            item.split("=", 1) for item in signature_header.split(";") if "=" in item
        )
        ts = parts.get("ts")
        h1 = parts.get("h1")
        if ts is None or h1 is None:
            raise WebhookVerificationError("Malformed signature header")

        signed_payload = f"{ts}:{raw_body.decode('utf-8')}"
        expected = hmac.new(
            settings.paddle_webhook_secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, h1)

    def create_checkout_url(self, product_id: str, customer_email: str) -> str:
        if not self.configured:
            raise RuntimeError(
                "Paddle is not configured (no sandbox account yet -- "
                "docs/HUMAN_COMMERCIAL_REQUIREMENTS.md). Cannot create a real checkout."
            )
        raise NotImplementedError(
            "Real Paddle API checkout creation needs a live sandbox account to test against"
        )


def get_provider() -> CommerceProvider:
    return PaddleProvider()


def _generate_license_key() -> str:
    import secrets

    return "-".join(secrets.token_hex(4).upper() for _ in range(4))


def _handle_transaction_completed(db: Session, payload: dict) -> None:
    """Simulated-payload shape, matching Paddle Billing's documented
    transaction.completed event: {data: {customer: {email}, items: [{price: {product_id}}], id}}"""
    data = payload["data"]
    email = data["customer"]["email"]
    provider_order_id = data["id"]
    amount_cents = int(data.get("details", {}).get("totals", {}).get("total", "0"))
    currency = data.get("currency_code", "GBP")
    product_id = data["items"][0]["price"]["product_id"]

    user = db.query(models.User).filter(models.User.email == email).one_or_none()
    if user is None:
        user = models.User(email=email, email_verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()

    purchase = models.Purchase(
        user_id=user.id,
        product_id=product_id,
        provider="paddle",
        provider_order_id=provider_order_id,
        amount_cents=amount_cents,
        currency=currency,
        status="completed",
    )
    db.add(purchase)
    db.flush()

    license_key = _generate_license_key()
    entitlement = models.Entitlement(
        user_id=user.id,
        product_id=product_id,
        purchase_id=purchase.id,
        license_key=license_key,
        license_type="perpetual",
        max_activations=settings.default_max_activations,
        status="active",
    )
    db.add(entitlement)

    amount_display = f"{currency} {amount_cents / 100:.2f}"
    subject, body = email_templates.purchase_confirmation("Smart Sample Manager", amount_display, license_key)
    send_email(to=email, subject=subject, body=body)


@router.post("/paddle")
async def paddle_webhook(
    request: Request,
    db: Session = Depends(get_db),
    provider: CommerceProvider = Depends(get_provider),
) -> dict:
    raw_body = await request.body()
    signature_header = request.headers.get("Paddle-Signature", "")

    try:
        valid = provider.verify_webhook_signature(raw_body, signature_header)
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    import json

    payload = json.loads(raw_body)
    event_type = payload.get("event_type", "unknown")
    provider_event_id = payload.get("event_id")
    if not provider_event_id:
        raise HTTPException(status_code=400, detail="Missing event_id")

    # Phase 5.5, Section 50-51: a SELECT-then-INSERT idempotency check has
    # the same race as licensing.py's activation-limit bug -- two
    # concurrent deliveries of the *same* event_id can both pass the "not
    # yet seen" check before either commits. Claim the event_id via the
    # database's own UNIQUE (provider, provider_event_id) constraint
    # instead: insert-and-commit immediately, and let a concurrent loser
    # fail on the constraint rather than on racing app-level logic.
    # Verified under real concurrency in tests/test_concurrency.py.
    event = models.WebhookEvent(
        provider="paddle",
        event_type=event_type,
        provider_event_id=provider_event_id,
        payload_json=payload,
        received_at=datetime.now(timezone.utc),
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "already_processed"}

    try:
        if event_type == "transaction.completed":
            _handle_transaction_completed(db, payload)
        event.processed_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001 -- persist the error, don't lose the event
        # Full detail persisted server-side (admin/webhooks/failed) for real
        # debugging -- never returned in the HTTP response itself, which
        # only needs to tell the caller (Paddle) to retry. Section 103:
        # exception text, SQL errors, and stack details never reach an
        # external caller.
        event.processing_error = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc

    db.commit()
    return {"status": "processed"}
