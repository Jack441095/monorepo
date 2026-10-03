"""Verified Stripe events fulfil paid sessions and record refund status."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import email_templates, models, paraphrase_orders
from .config import settings
from .database import get_db
from .email import send_email

router = APIRouter(prefix="/webhooks", tags=["stripe"])
logger = logging.getLogger("nitedsp.stripe_commerce")
WEBHOOK_MAX_AGE_SECONDS = 5 * 60


class StripeWebhookVerificationError(Exception):
    pass


def _verify_stripe_signature(raw_body: bytes, signature_header: str) -> None:
    if not settings.stripe_webhook_secret:
        raise StripeWebhookVerificationError("No stripe_webhook_secret configured")
    timestamps, signatures = [], []
    for item in signature_header.replace(";", ",").split(","):
        key, _, value = item.partition("=")
        if key.strip() == "t":
            timestamps.append(value.strip())
        elif key.strip() == "v1":
            signatures.append(value.strip())
    if len(timestamps) != 1 or not signatures:
        raise StripeWebhookVerificationError("Malformed Stripe-Signature header")
    timestamp = timestamps[0]
    if not re.fullmatch(r"[0-9]{1,12}", timestamp):
        raise StripeWebhookVerificationError("Invalid Stripe timestamp")
    signatures = [value for value in signatures if re.fullmatch(r"[0-9a-fA-F]{64}", value)]
    if not signatures:
        raise StripeWebhookVerificationError("Invalid Stripe signature")
    try:
        timestamp_int = int(timestamp)
        raw_body.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise StripeWebhookVerificationError("Invalid timestamp or body encoding") from exc
    if abs(time.time() - timestamp_int) > WEBHOOK_MAX_AGE_SECONDS:
        raise StripeWebhookVerificationError("Stripe webhook timestamp outside acceptable window")
    expected = hmac.new(
        settings.stripe_webhook_secret.encode(),
        timestamp.encode() + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    # Stripe supplies multiple v1 signatures during signing-secret rotation.
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise StripeWebhookVerificationError("Stripe webhook signature mismatch")


def _generate_license_key() -> str:
    return "-".join(secrets.token_hex(4).upper() for _ in range(4))


def _handle_checkout_session_completed(db: Session, payload: dict) -> str:
    session = payload["data"]["object"]
    # Delayed payment methods complete checkout before funds are confirmed.
    # The later async_payment_succeeded event re-enters this same fulfilment path.
    if session.get("payment_status") not in ("paid", "no_payment_required"):
        return "awaiting_payment"
    if not isinstance(session.get("id"), str) or not session["id"]:
        raise ValueError("Missing Checkout session id")
    amount_total = session.get("amount_total")
    currency = session.get("currency")
    if type(amount_total) is not int or amount_total < 0 or not isinstance(currency, str) or not currency:
        raise ValueError("Invalid Checkout amount or currency")
    metadata = session.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Invalid Checkout metadata")
    if paraphrase_orders.handle_checkout_completed(db, session):
        return "processed"
    product_id = metadata.get("product_id")
    if not product_id:
        return "skipped"
    product = (
        db.query(models.Product).filter(models.Product.id == product_id)
        .with_for_update().one_or_none()
    )
    if product is None or not product.purchasable:
        return "rejected_unknown_catalog_item"
    # Different Stripe event IDs can refer to the same paid session. The
    # product lock serialises that check and insert across worker processes.
    existing = db.query(models.Purchase).filter(
        models.Purchase.provider == "stripe",
        models.Purchase.provider_order_id == session["id"],
    ).one_or_none()
    if existing is not None:
        return "already_processed"
    email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
    if not isinstance(email, str) or not email:
        raise ValueError("Missing Checkout customer email")
    user = db.query(models.User).filter(models.User.email == email).one_or_none()
    if user is None:
        user = models.User(email=email, email_verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
    payment_intent = session.get("payment_intent")
    if isinstance(payment_intent, dict):
        payment_intent = payment_intent.get("id")
    purchase = models.Purchase(
        user_id=user.id, product_id=product.id, price_id=metadata.get("price_id"),
        provider="stripe", provider_order_id=session["id"],
        provider_payment_id=payment_intent, amount_cents=amount_total,
        currency=currency.upper(), status="completed",
    )
    db.add(purchase)
    db.flush()
    license_key = _generate_license_key()
    db.add(models.Entitlement(
        user_id=user.id, product_id=product.id, purchase_id=purchase.id,
        license_key=license_key, license_type="perpetual",
        max_activations=settings.default_max_activations, status="active",
    ))
    subject, body = email_templates.purchase_confirmation(
        product.name, f"{currency.upper()} {amount_total / 100:.2f}", license_key,
    )
    send_email(to=email, subject=subject, body=body)
    return "processed"


def _handle_refund_or_dispute(db: Session, payload: dict) -> None:
    data = payload["data"]["object"]
    payment_intent = data.get("payment_intent")
    if isinstance(payment_intent, dict):
        payment_intent = payment_intent.get("id")
    if not payment_intent:
        return
    purchase = db.query(models.Purchase).filter(
        models.Purchase.provider == "stripe",
        models.Purchase.provider_payment_id == payment_intent,
    ).with_for_update().one_or_none()
    if purchase is None:
        return
    if payload["type"] == "charge.refunded":
        # Partial refunds keep the purchase completed; licence revocation
        # remains an explicit admin decision, as before the provider change.
        if data.get("refunded") and purchase.status != "refunded":
            purchase.status = "refunded"
            purchase.refunded_at = datetime.now(timezone.utc)
    elif purchase.status == "completed":
        purchase.status = "disputed"


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw_body = await request.body()
    try:
        _verify_stripe_signature(raw_body, request.headers.get("Stripe-Signature", ""))
    except StripeWebhookVerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("Invalid event body")
        event_type, provider_event_id = payload.get("type"), payload.get("id")
        if not isinstance(provider_event_id, str) or not provider_event_id or not isinstance(event_type, str):
            raise ValueError("Missing event id or type")
        if not isinstance(payload.get("data"), dict) or not isinstance(payload["data"].get("object"), dict):
            raise ValueError("Missing event object")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe event body") from exc

    event = models.WebhookEvent(
        provider="stripe", event_type=event_type, provider_event_id=provider_event_id,
        payload_json=payload, received_at=datetime.now(timezone.utc),
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    event = db.query(models.WebhookEvent).filter(
        models.WebhookEvent.provider == "stripe",
        models.WebhookEvent.provider_event_id == provider_event_id,
    ).with_for_update().populate_existing().one()
    if event.processed_at is not None:
        return {"status": "already_processed"}
    try:
        if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            result = _handle_checkout_session_completed(db, payload)
        elif event_type in ("charge.refunded", "charge.dispute.created"):
            _handle_refund_or_dispute(db, payload)
            result = "processed"
        else:
            result = "ignored"
        event.processed_at = datetime.now(timezone.utc)
        event.processing_error = "unknown product_id in metadata" if result == "rejected_unknown_catalog_item" else None
        db.commit()
    except Exception as exc:
        # A failed flush leaves the SQLAlchemy session unusable until rollback.
        # Retain only the receipt and error so the same event can retry safely.
        db.rollback()
        event = db.query(models.WebhookEvent).filter(
            models.WebhookEvent.provider == "stripe",
            models.WebhookEvent.provider_event_id == provider_event_id,
        ).with_for_update().populate_existing().one()
        if event.processed_at is None:
            event.processing_error = str(exc)
        db.commit()
        logger.exception("Stripe event processing failed: %s", provider_event_id)
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc
    return {"status": result}
