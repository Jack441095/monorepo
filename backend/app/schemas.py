from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class ParaphraseRequest(BaseModel):
    """Body for the paraphrase rewrite endpoint (products/nite-paraphrase).

    Field is `voice` (the three registers) because `register` shadows a
    pydantic BaseModel internals attribute and emits a model warning.
    """

    voice: Literal["essay", "email", "report", "casual"]
    text: str = Field(min_length=1, max_length=8000)


class ParaphraseCheckoutRequest(BaseModel):
    """Start an anonymous pay-what-you-like purchase."""

    tier: Literal["gbp-1", "gbp-3", "gbp-10"]


class ParaphraseRedemptionRequest(BaseModel):
    """Exchange a completed transaction hint for a session unlock token."""

    hint: str = Field(min_length=1, max_length=100)


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkVerify(BaseModel):
    token: str


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: str
    name: str
    status: str
    public: bool
    purchasable: bool
    description: str | None
    current_version: str | None
    platforms: list[str]

    model_config = {"from_attributes": True}


class EntitlementOut(BaseModel):
    id: str
    product_id: str
    license_key: str
    license_type: str
    max_activations: int
    status: str
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SignedToken(BaseModel):
    """Matches licensing_server/server.py's _sign_payload() shape exactly --
    token_json is the literal canonical string the client verifies the
    signature against; token is the same payload pre-parsed for convenience."""

    token_json: str
    token: dict
    signature: str


class ActivateRequest(BaseModel):
    license_key: str
    device_id: str
    device_name: str = ""


class ValidateRequest(BaseModel):
    license_key: str
    device_id: str


class DeactivateRequest(BaseModel):
    license_key: str
    device_id: str
    # Possession proof (SANDBOX_TO_LIVE_CHECKLIST P2): the signed activation
    # token + signature exactly as returned by /v1/activate or /v1/validate
    # for this license_key + device_id. Without it, anyone who learns only
    # the license key could deactivate a customer's device.
    activation_token_json: str
    activation_signature: str
