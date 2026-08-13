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
independent of having a live Paddle account -- see tests/test_e2e.py and
tests/test_concurrency.py (there is no separate tests/test_commerce.py).

Refund/dispute events only ever *record* the refund on the Purchase row
(status, refunded_at). They never touch the Entitlement -- entitlement
revocation on refund stays the existing manual admin action
(`POST /admin/entitlements/{id}/revoke`, see tests/test_e2e.py step 7)
rather than an automatic webhook-driven policy, since that policy choice
belongs to the business, not this code (docs/PADDLE_INTEGRATION_AUDIT.md).

An adjustment (refund/chargeback) is NOT final at `adjustment.created` --
Paddle Billing's real lifecycle is created with status=pending_approval,
then a later `adjustment.updated` flips status to approved/rejected
(sandbox auto-approves after ~10 minutes; live requires manual approval
for high-value refunds). Both event types are handled by the same
function and a Purchase is only ever marked refunded once status is
actually "approved" -- never on the initial pending event. Idempotent by
construction (only acts once per purchase, regardless of how many
created/updated deliveries arrive or in what order) rather than needing
separate duplicate/out-of-order handling.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import email_templates, models
from .auth import get_current_user
from .config import settings
from .database import get_db
from .email import send_email

router = APIRouter(prefix="/webhooks", tags=["commerce"])
checkout_router = APIRouter(prefix="/commerce", tags=["commerce"])
logger = logging.getLogger("nitedsp.commerce")


class WebhookVerificationError(Exception):
    pass


class UnknownCatalogItemError(Exception):
    """Raised when a webhook references a product_id/price_id combination
    that isn't in our configured mapping. Deliberately distinct from a
    generic processing failure: Paddle should NOT retry-deliver an event
    that will never map to anything we recognise, so the webhook handler
    responds 200 (not 500) for this specific case -- see paddle_webhook."""


class CommerceProvider(ABC):
    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool: ...

    @abstractmethod
    def create_checkout_url(self, price_id: str, customer_email: str) -> str: ...


class PaddleProvider(CommerceProvider):
    """Sandbox-only until a human explicitly points paddle_api_base_url at
    api.paddle.com for a real production deploy. `configured` is False
    whenever no Paddle account exists yet (paddle_api_key empty) -- callers
    must check this before attempting anything that would need a real API
    round-trip; webhook *verification* still works without it, since that
    only needs the shared webhook secret, not the API key."""

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

    def create_checkout_url(self, price_id: str, customer_email: str) -> str:
        if not self.configured:
            raise RuntimeError(
                "Paddle is not configured (no sandbox account yet -- "
                "docs/HUMAN_COMMERCIAL_REQUIREMENTS.md). Cannot create a real checkout."
            )
        # Paddle Billing's Transactions API: creating a transaction with
        # collection_mode=automatic and no existing payment returns a
        # checkout.url the client can redirect to -- this is the real
        # server-prepared-checkout shape, not a mocked URL. See
        # https://developer.paddle.com/api-reference/transactions/create-transaction
        # (verify the exact response shape against current docs before
        # relying on this in a real sandbox test -- untested against a live
        # account as of writing, no account exists yet).
        try:
            response = httpx.post(
                f"{settings.paddle_api_base_url}/transactions",
                headers={
                    "Authorization": f"Bearer {settings.paddle_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "items": [{"price_id": price_id, "quantity": 1}],
                    "customer": {"email": customer_email},
                    "collection_mode": "automatic",
                },
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Paddle checkout creation failed: %s", exc)
            raise RuntimeError("Could not create Paddle checkout") from exc

        data = response.json()
        checkout_url = data.get("data", {}).get("checkout", {}).get("url")
        if not checkout_url:
            raise RuntimeError("Paddle response did not include a checkout URL")
        return checkout_url


def get_provider() -> CommerceProvider:
    return PaddleProvider()


def _price_to_product() -> dict[str, str]:
    """Fail-closed catalog mapping (docs/PADDLE_INTEGRATION_AUDIT.md Section
    12): built fresh from settings each call rather than cached at import
    time, so tests can override config per-case. Empty entries are dropped,
    not mapped to "" -- an unconfigured price_id must never match anything."""
    mapping: dict[str, str] = {}
    if settings.paddle_intro_price_id and settings.paddle_product_id:
        mapping[settings.paddle_intro_price_id] = settings.paddle_product_id
    if settings.paddle_regular_price_id and settings.paddle_product_id:
        mapping[settings.paddle_regular_price_id] = settings.paddle_product_id
    return mapping


def _generate_license_key() -> str:
    import secrets

    return "-".join(secrets.token_hex(4).upper() for _ in range(4))


def _handle_transaction_completed(db: Session, payload: dict) -> None:
    """Simulated-payload shape, matching Paddle Billing's documented
    transaction.completed event: {data: {customer: {email}, items: [{price: {product_id, id}}], id}}"""
    data = payload["data"]
    email = data["customer"]["email"]
    provider_order_id = data["id"]
    amount_cents = int(data.get("details", {}).get("totals", {}).get("total", "0"))
    currency = data.get("currency_code", "GBP")
    price = data["items"][0]["price"]
    product_id = price["product_id"]
    price_id = price.get("id")

    product = db.get(models.Product, product_id)
    if product is None or not product.purchasable:
        raise UnknownCatalogItemError(f"Unknown or non-purchasable product_id {product_id!r}")

    # price_id is only present once real Paddle price IDs exist in the
    # payload; a configured mapping (paddle_intro/regular_price_id set)
    # makes checking it mandatory, so a real event with an unrecognised
    # price can never slip through once the catalog is actually wired up.
    mapping = _price_to_product()
    if price_id is not None and mapping:
        if mapping.get(price_id) != product_id:
            raise UnknownCatalogItemError(
                f"price_id {price_id!r} does not map to product_id {product_id!r}"
            )

    user = db.query(models.User).filter(models.User.email == email).one_or_none()
    if user is None:
        user = models.User(email=email, email_verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()

    purchase = models.Purchase(
        user_id=user.id,
        product_id=product_id,
        price_id=price_id,
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


def _handle_adjustment_event(db: Session, payload: dict) -> None:
    """Paddle Billing's real refund/chargeback lifecycle -- handles both
    adjustment.created and adjustment.updated with the same logic.
    Simulated-payload shape (verify against a real sandbox event once
    reachable): {data: {action: "refund"|"chargeback"|"credit",
    status: "pending_approval"|"approved"|"rejected"|"reversed",
    transaction_id: str}}.

    Only status=="approved" is authoritative -- created always arrives
    pending_approval; approval (sandbox: automatic after ~10 min; live:
    manual for high-value refunds) arrives later as a separate
    adjustment.updated delivery. A "rejected" adjustment must never mark
    the purchase refunded.

    Idempotent and order-tolerant by construction: only acts when the
    purchase isn't already refunded/disputed, so a duplicate approved
    delivery, or a stale pending/rejected delivery arriving after an
    approved one, is always a no-op rather than needing separate
    duplicate/ordering logic.

    Deliberately does NOT touch the Entitlement -- see this module's
    docstring. Records the refund on Purchase only, so an admin can see it
    via GET /admin/purchases/search and act via the existing manual revoke
    endpoint. If no matching Purchase exists locally, this is logged and
    left alone rather than raised as an error: Paddle is the source of
    truth for the adjustment either way, and there is nothing local to
    update."""
    data = payload["data"]
    action = data.get("action")
    if action not in ("refund", "chargeback"):
        return  # credits/other adjustment types: no local purchase-status change

    if data.get("status") != "approved":
        return  # not yet authoritative -- wait for the approving adjustment.updated

    transaction_id = data.get("transaction_id")
    purchase = (
        db.query(models.Purchase)
        .filter(models.Purchase.provider == "paddle", models.Purchase.provider_order_id == transaction_id)
        .one_or_none()
    )
    if purchase is None:
        logger.warning("approved adjustment (%s) for unknown transaction_id=%r", action, transaction_id)
        return

    if purchase.status in ("refunded", "disputed"):
        return  # already recorded -- duplicate/out-of-order delivery

    purchase.status = "refunded" if action == "refund" else "disputed"
    purchase.refunded_at = datetime.now(timezone.utc)


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
        elif event_type in ("adjustment.created", "adjustment.updated"):
            _handle_adjustment_event(db, payload)
        event.processed_at = datetime.now(timezone.utc)
    except UnknownCatalogItemError as exc:
        # Fail safely without issuing an entitlement, but don't ask Paddle
        # to keep retrying an event that will never map to anything real --
        # that's a permanent rejection, not a transient failure.
        event.processing_error = str(exc)
        db.commit()
        return {"status": "rejected_unknown_catalog_item"}
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


class CheckoutRequest(BaseModel):
    # Logical name, not a raw price ID -- callers ask for "intro" or
    # "regular" and the server resolves it from settings.paddle_active_price_id
    # / the specific price fields, never accepting an arbitrary price_id from
    # the client (that would let a caller checkout against any price at all).
    price: str = "active"


@checkout_router.post("/checkout")
def create_checkout(
    req: CheckoutRequest,
    user: models.User = Depends(get_current_user),
    provider: CommerceProvider = Depends(get_provider),
) -> dict:
    if not provider.configured:
        raise HTTPException(status_code=503, detail="Checkout is not available yet")

    price_map = {
        "active": settings.paddle_active_price_id,
        "intro": settings.paddle_intro_price_id,
        "regular": settings.paddle_regular_price_id,
    }
    price_id = price_map.get(req.price)
    if not price_id:
        raise HTTPException(status_code=400, detail="Unknown or unconfigured price")

    try:
        checkout_url = provider.create_checkout_url(price_id, user.email)
    except RuntimeError as exc:
        logger.error("Checkout creation failed for user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Could not create checkout") from exc

    return {"checkout_url": checkout_url}
