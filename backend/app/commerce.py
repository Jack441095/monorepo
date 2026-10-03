"""Stripe hosted checkout with server-controlled product and price metadata."""
from __future__ import annotations

import logging
from typing import Protocol
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models
from .auth import get_current_user
from .config import settings
from .database import get_db

checkout_router = APIRouter(prefix="/commerce", tags=["commerce"])
logger = logging.getLogger("nitedsp.commerce")


class CommerceProvider(Protocol):
    configured: bool

    def create_checkout_url(
        self, price_id: str, *, metadata: dict[str, str],
        success_url: str | None = None, customer_email: str | None = None,
    ) -> str: ...


class StripeProvider:
    def __init__(self) -> None:
        self.configured = bool(settings.stripe_secret_key)

    def create_checkout_url(
        self, price_id: str, *, metadata: dict[str, str],
        success_url: str | None = None, customer_email: str | None = None,
    ) -> str:
        if not self.configured:
            raise RuntimeError("Stripe is not configured")
        public_url = settings.nite_dsp_public_url.rstrip("/")
        data = {
            "mode": "payment",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": success_url or f"{public_url}/account?purchase=pending",
            "cancel_url": f"{public_url}/pricing",
        }
        data.update({f"metadata[{key}]": value for key, value in metadata.items()})
        if customer_email:
            data["customer_email"] = customer_email
        try:
            response = httpx.post(
                "https://api.stripe.com/v1/checkout/sessions",
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
                data=data,
                timeout=20,
            )
            response.raise_for_status()
            checkout_url = response.json().get("url")
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("Could not create Stripe checkout") from exc
        if not isinstance(checkout_url, str):
            raise RuntimeError("Stripe response did not include a checkout URL")
        parsed = urlparse(checkout_url)
        if parsed.scheme != "https" or parsed.hostname != "checkout.stripe.com":
            raise RuntimeError("Stripe response contained an invalid checkout URL")
        return checkout_url


def get_provider() -> CommerceProvider:
    return StripeProvider()


class CheckoutRequest(BaseModel):
    # Clients select a tier; only the server can supply chargeable price IDs.
    price: str = "active"


@checkout_router.post("/checkout")
def create_checkout(
    req: CheckoutRequest,
    user: models.User = Depends(get_current_user),
    provider: CommerceProvider = Depends(get_provider),
    db: Session = Depends(get_db),
) -> dict:
    if not settings.stripe_checkout_enabled or not provider.configured:
        raise HTTPException(status_code=503, detail="Checkout is not available yet")
    price_id = {
        "active": settings.stripe_active_price_id,
        "intro": settings.stripe_intro_price_id,
        "regular": settings.stripe_regular_price_id,
    }.get(req.price)
    if not price_id or not settings.stripe_product_id:
        raise HTTPException(status_code=400, detail="Unknown or unconfigured price")
    product = db.get(models.Product, settings.stripe_product_id)
    if product is None or not product.purchasable:
        raise HTTPException(status_code=503, detail="Checkout product is not available")
    try:
        checkout_url = provider.create_checkout_url(
            price_id,
            metadata={"product_id": settings.stripe_product_id, "price_id": price_id},
            customer_email=user.email,
        )
    except RuntimeError as exc:
        logger.error("Checkout creation failed for user=%s", user.id)
        raise HTTPException(status_code=502, detail="Could not create checkout") from exc
    return {"checkout_url": checkout_url}
