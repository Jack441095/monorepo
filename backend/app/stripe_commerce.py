"""
Stripe webhook handling and purchase fulfilment.

Mirrors the Paddle implementation in commerce.py. The webhook endpoint is
`/webhooks/stripe`; it receives `checkout.session.completed` events and
issues a Purchase + Entitlement + confirmation email.

Product routing uses `session.metadata["product_id"]` (our internal slug,
e.g. "smart-sample-manager"), set at payment-link creation time. Events
without a recognised product_id are skipped without error -- this covers
Paraphrase tip-jar payments, which carry no product_id and need no fulfilment.

Signature verification matches Stripe's documented scheme:
  HMAC-SHA256(secret, f"{timestamp}.{raw_body}")
  header format: "t=<unix>;v1=<hex>" (or comma-separated -- both accepted).

Replay protection: events older than WEBHOOK_MAX_AGE_SECONDS are rejected.
Idempotency: claimed via WebhookEvent's unique (provider, provider_event_id)
constraint, same as commerce.py.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import email_templates, models
from .config import settings
from .database import get_db
from .email import send_email

router = APIRouter(prefix="/webhooks", tags=["stripe"])
logger = logging.getLogger("nitedsp.stripe_commerce")

WEBHOOK_MAX_AGE_SECONDS = 5 * 60  # Stripe recommends 5-minute tolerance


class StripeWebhookVerificationError(Exception):
    pass


def _verify_stripe_signature(raw_body: bytes, signature_header: str) -> None:
    """Raise StripeWebhookVerificationError if the signature is invalid."""
    if not settings.stripe_webhook_secret:
        raise StripeWebhookVerificationError("No stripe_webhook_secret configured")

    # Header may use "," or ";" as separator; normalise to ";"
    header = signature_header.replace(",", ";")
    parts = {}
    for item in header.split(";"):
        if "=" in item:
            k, _, v = item.partition("=")
            parts[k.strip()] = v.strip()

    ts_str = parts.get("t")
    v1 = parts.get("v1")
    if not ts_str or not v1:
        raise StripeWebhookVerificationError("Malformed Stripe-Signature header")

    try:
        ts_int = int(ts_str)
    except ValueError:
        raise StripeWebhookVerificationError("Malformed timestamp in Stripe-Signature") from None

    if abs(time.time() - ts_int) > WEBHOOK_MAX_AGE_SECONDS:
        raise StripeWebhookVerificationError("Stripe webhook timestamp outside acceptable window")

    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StripeWebhookVerificationError("Webhook body is not valid UTF-8") from exc

    signed_payload = f"{ts_str}.{body_text}"
    expected = hmac.new(
        settings.stripe_webhook_secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, v1):
        raise StripeWebhookVerificationError("Stripe webhook signature mismatch")


def _generate_license_key() -> str:
    return "-".join(secrets.token_hex(4).upper() for _ in range(4))


def _handle_checkout_session_completed(db: Session, payload: dict) -> str | None:
    """Process a checkout.session.completed event.

    Returns "skipped" when the session has no product_id in its metadata
    (covers Paraphrase tip-jar payments which need no fulfilment), or
    "processed" after a Purchase + Entitlement are created and the
    confirmation email is sent.

    Raises HTTPException(400/500) for unrecoverable errors so the webhook
    handler can tell Stripe to retry only real transient failures.
    """
    session = payload.get("data", {}).get("object", {})

    product_id = (session.get("metadata") or {}).get("product_id")
    if not product_id:
        logger.info("stripe checkout.session.completed: no product_id in metadata -- skipping fulfilment")
        return "skipped"

    product = db.query(models.Product).filter(models.Product.id == product_id).one_or_none()
    if product is None or not product.purchasable:
        logger.error("stripe checkout.session.completed: unknown/non-purchasable product_id=%r", product_id)
        return "rejected_unknown_catalog_item"

    email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
    if not email:
        logger.error("stripe checkout.session.completed: no customer email in session id=%s", session.get("id"))
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    stripe_session_id = session.get("id", "")
    amount_total = session.get("amount_total") or 0
    currency = (session.get("currency") or "gbp").upper()

    user = db.query(models.User).filter(models.User.email == email).one_or_none()
    if user is None:
        user = models.User(email=email, email_verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()

    purchase = models.Purchase(
        user_id=user.id,
        product_id=product.id,
        price_id=None,
        provider="stripe",
        provider_order_id=stripe_session_id,
        amount_cents=int(amount_total),
        currency=currency,
        status="completed",
    )
    db.add(purchase)
    db.flush()

    license_key = _generate_license_key()
    entitlement = models.Entitlement(
        user_id=user.id,
        product_id=product.id,
        purchase_id=purchase.id,
        license_key=license_key,
        license_type="perpetual",
        max_activations=settings.default_max_activations,
        status="active",
    )
    db.add(entitlement)

    amount_display = f"{currency} {int(amount_total) / 100:.2f}"
    subject, body = email_templates.purchase_confirmation(product.name, amount_display, license_key)
    send_email(to=email, subject=subject, body=body)

    return "processed"


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        _verify_stripe_signature(raw_body, sig_header)
    except StripeWebhookVerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    import json

    payload = json.loads(raw_body)
    event_type = payload.get("type", "unknown")
    provider_event_id = payload.get("id")
    if not provider_event_id:
        raise HTTPException(status_code=400, detail="Missing event id")

    event = models.WebhookEvent(
        provider="stripe",
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
        event = (
            db.query(models.WebhookEvent)
            .filter(
                models.WebhookEvent.provider == "stripe",
                models.WebhookEvent.provider_event_id == provider_event_id,
            )
            .with_for_update()
            .populate_existing()
            .one()
        )
        if event.processed_at is not None:
            return {"status": "already_processed"}
    else:
        event = (
            db.query(models.WebhookEvent)
            .filter(models.WebhookEvent.id == event.id)
            .with_for_update()
            .populate_existing()
            .one()
        )
        if event.processed_at is not None:
            return {"status": "already_processed"}

    try:
        if event_type == "checkout.session.completed":
            result = _handle_checkout_session_completed(db, payload)
            if result == "rejected_unknown_catalog_item":
                event.processing_error = f"unknown product_id in metadata"
                db.commit()
                return {"status": "rejected_unknown_catalog_item"}
        else:
            result = "ignored"

        event.processed_at = datetime.now(timezone.utc)
        event.processing_error = None
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        event.processing_error = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc

    db.commit()
    return {"status": result or "processed"}
