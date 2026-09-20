"""
Paraphrase PWYW commerce (products/nite-paraphrase Phase 4).

Anonymous pay-what-you-like unlock flow that stays completely decoupled
from the main product's users/purchases/entitlements tables: the browser
generates a random `hint` before checkout, the Paddle transaction carries
it via custom_data, the webhook records it, and the redemption endpoint
proves it and issues a short-lived signed session token.  No email, no
account, no perpetual licence.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .commerce import CommerceProvider

logger = logging.getLogger("nitedsp.paraphrase_orders")

# itsdangerous is a direct dependency already present in requirements.txt
# (used by starlette/itsdangerous for sessions); the serializer is
# stateless and needs only the same session_secret the auth path uses.
_SCOPE = "paraphrase_unlock"


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="nitedsp-paraphrase-unlock")


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------

def _tier_to_price_id(tier: str) -> str | None:
    return {
        "gbp-1": settings.paraphrase_price_gbp_1,
        "gbp-3": settings.paraphrase_price_gbp_3,
        "gbp-10": settings.paraphrase_price_gbp_10,
    }.get(tier)


def is_paraphrase_product(paddle_product_id: str) -> bool:
    """Webhook fast-path: does this Paddle product belong to paraphrase?"""
    return bool(settings.paraphrase_product_id and paddle_product_id == settings.paraphrase_product_id)


# ---------------------------------------------------------------------------
# Checkout (called from the paraphrase router)
# ---------------------------------------------------------------------------

def create_checkout(
    provider: CommerceProvider,
    tier: str,
) -> tuple[str, str]:
    """Create a server-side Paddle checkout transaction.

    Returns (checkout_url, hint).  The caller must redirect the browser
    to checkout_url; Paddle redirects back to success_url with the hint
    preserved in the query string, so the client can poll redemption
    afterwards.

    Raises:
        ValueError: for an unknown/unconfigured tier.
        RuntimeError: for a Paddle API failure.
    """
    price_id = _tier_to_price_id(tier)
    if not price_id:
        available = [k for k in ("gbp-1", "gbp-3", "gbp-10") if _tier_to_price_id(k)]
        raise ValueError(f"unknown or unconfigured tier {tier!r}; configured: {available}")

    hint = secrets.token_urlsafe(20)
    success_url = (
        f"{settings.nite_dsp_public_url.rstrip('/')}/paraphrase"
        f"?paraphrase_hint={hint}"
    )

    checkout_url = provider.create_checkout_url(
        price_id,
        custom_data={"paraphrase_hint": hint},
        success_url=success_url,
    )
    return checkout_url, hint


# ---------------------------------------------------------------------------
# Webhook handler (called from commerce.py paddle_webhook)
# ---------------------------------------------------------------------------

def handle_transaction_completed(db: Session, payload: dict) -> bool:
    """Inspect and potentially consume a transaction.completed event.

    Returns True if this event was a paraphrase purchase (even if it
    failed to record for some reason -- a bad hint should not fall
    through to the licence path which would reject the product anyway).
    Returns False if this is not a paraphrase transaction, so the caller
    should continue with the normal licence flow.
    """
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return False
    # Find the paraphrase product_id among the transaction items.
    items = data.get("items", [])
    if not isinstance(items, list):
        return False
    paddle_product_id: str | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        price = item.get("price", {})
        if not isinstance(price, dict):
            continue
        if price.get("product_id") == settings.paraphrase_product_id:
            paddle_product_id = price["product_id"]
            break
    if paddle_product_id is None:
        return False  # not our product

    custom_data = data.get("custom_data") or {}
    if not isinstance(custom_data, dict):
        custom_data = {}
    hint = custom_data.get("paraphrase_hint")
    if not hint:
        # A real transaction with our product_id but no hint -- there is
        # no client that could redeem it (ParaphraseOrder.hint is NOT NULL
        # UNIQUE), so intentionally do not insert a row. Log identifiers
        # for reconciliation instead. This is a permanent rejection:
        # Paddle should not retry this.
        logger.warning(
            "paraphrase purchase without hint provider_order_id=%r paddle_product_id=%r",
            data.get("id"),
            paddle_product_id,
        )
        return True

    from decimal import Decimal, InvalidOperation

    try:
        raw_total = data.get("details", {}).get("totals", {}).get("total", "0")
        amount_cents = int(Decimal(str(raw_total)) * 100)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        amount_cents = 0
    currency = data.get("currency_code", "GBP")
    if not isinstance(currency, str) or not currency:
        currency = "GBP"
    provider_order_id = data.get("id")
    if not isinstance(provider_order_id, str) or not provider_order_id:
        return True

    # Idempotent upsert: unique(provider_order_id) means a duplicate
    # webhook delivery is always a safe no-op; unique(hint) means one
    # hint can never fan out into two paid rows.
    existing = (
        db.query(models.ParaphraseOrder)
        .filter(models.ParaphraseOrder.provider_order_id == provider_order_id)
        .one_or_none()
    )
    if existing is not None:
        return True

    db.add(
        models.ParaphraseOrder(
            hint=hint,
            provider_order_id=provider_order_id,
            amount_cents=amount_cents,
            currency=currency,
        )
    )
    return True


# ---------------------------------------------------------------------------
# Redemption (called from the paraphrase router)
# ---------------------------------------------------------------------------

def redeem(db: Session, hint: str) -> tuple[str, datetime] | None:
    """Prove payment and issue a signed session-unlock token.

    Returns (token, expires_at) on success, None if no matching paid
    order exists.  Idempotent: re-redeeming the same hint returns a
    fresh token (the row's redeemed_at is set only once, preserving
    the audit trail of when it was first used).
    """
    row = (
        db.query(models.ParaphraseOrder)
        .filter(models.ParaphraseOrder.hint == hint)
        .one_or_none()
    )
    if row is None:
        return None

    if row.redeemed_at is None:
        row.redeemed_at = datetime.now(timezone.utc)

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.paraphrase_unlock_days)
    token = _signer().dumps(
        {"hint": hint, "scope": _SCOPE, "exp": expires_at.isoformat()}
    )
    return token, expires_at


def verify_unlock_token(token: str) -> bool:
    """Verify a paraphrase unlock token (signature + TTL, not database).

    Enforces both the serializer max_age backstop and the embedded `exp`
    claim, so changing `paraphrase_unlock_days` cannot retroactively extend
    an already-issued token past its stated expiry.
    """
    try:
        data = _signer().loads(token, max_age=settings.paraphrase_unlock_days * 86400)
        if data.get("scope") != _SCOPE:
            return False
        exp_raw = data.get("exp")
        if not exp_raw:
            return False
        try:
            exp = datetime.fromisoformat(exp_raw)
        except ValueError:
            return False
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)
    except (BadSignature, SignatureExpired, ValueError):
        return False