"""
Paraphrase PWYW commerce (products/nite-paraphrase Phase 4).

Anonymous pay-what-you-like unlock flow that stays completely decoupled
from the main product's users/purchases/entitlements tables: the server
generates a random `hint` before checkout, the Stripe Checkout session carries
it via metadata, the webhook records it, and the redemption endpoint
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


def _tier_to_price_id(tier: str) -> str | None:
    return {
        "gbp-1": settings.paraphrase_price_gbp_1,
        "gbp-3": settings.paraphrase_price_gbp_3,
        "gbp-10": settings.paraphrase_price_gbp_10,
    }.get(tier)


def create_checkout(
    provider: CommerceProvider,
    tier: str,
) -> tuple[str, str]:
    """Create a server-side Stripe checkout transaction.

    Returns (checkout_url, hint).  The caller must redirect the browser
    to checkout_url; Stripe redirects back to success_url with the hint
    preserved in the query string, so the client can poll redemption
    afterwards.

    Raises:
        ValueError: for an unknown/unconfigured tier.
        RuntimeError: for a Stripe API failure.
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
        metadata={"product_id": settings.paraphrase_product_id, "paraphrase_hint": hint},
        success_url=success_url,
    )
    return checkout_url, hint


def handle_checkout_completed(db: Session, session: dict) -> bool:
    metadata = session.get("metadata") or {}
    if metadata.get("product_id") != settings.paraphrase_product_id:
        return False
    hint = metadata.get("paraphrase_hint")
    if not hint:
        # Payment links used as tip jars have no browser hint to redeem.
        return True
    from sqlalchemy.dialects.postgresql import insert

    db.execute(
        insert(models.ParaphraseOrder).values(
            hint=hint,
            provider_order_id=session["id"],
            amount_cents=session["amount_total"],
            currency=session["currency"].upper(),
        ).on_conflict_do_nothing(index_elements=["provider_order_id"])
    )
    return True


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
