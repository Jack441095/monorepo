from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


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
