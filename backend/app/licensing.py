"""
Licensing endpoints -- activate/validate/deactivate.

Reuses licensing_server/server.py's crypto and contract literally (Section
17: reuse, don't replace): same Ed25519 signing via PyNaCl, same canonical
JSON signing technique (sorted keys, no incidental whitespace -- the client
verifies against the exact `token_json` string, never a re-serialization,
since JUCE's JSON writer orders/spaces differently than Python's), same
authoritative-server principle (every activate/validate call re-derives
status from this database and returns a freshly signed token).

Backed by the real `entitlements`/`activations` Postgres tables instead of
the dev server's SQLite `licenses`/`activations`, and looked up by
`entitlements.license_key` (see models.py's comment on that column).
"""
from __future__ import annotations

import base64
import functools
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from nacl.signing import SigningKey
from sqlalchemy.orm import Session

from . import models, schemas
from .config import settings
from .database import get_db
from .rate_limit import rate_limit

router = APIRouter(prefix="/v1", tags=["licensing"])


@functools.lru_cache(maxsize=1)
def _get_signing_key() -> SigningKey:
    # Production (Railway or any host without a guaranteed-persistent
    # filesystem) supplies the key via env var; local/staging keeps reading
    # the generated keypair file. See config.py's licensing key comment.
    #
    # Deliberately lazy (not at import time): a missing/malformed key used to
    # crash the whole backend on import, taking down every endpoint -- even
    # ones that never sign. Now the failure is confined to the /v1 routes
    # that actually need the key.
    if settings.licensing_private_key_base64:
        return SigningKey(base64.b64decode(settings.licensing_private_key_base64.strip()))

    private_path = Path(settings.licensing_private_key_path)
    if not private_path.exists():
        raise RuntimeError(
            f"No staging signing key at {private_path}. Run "
            "scripts/generate_staging_keypair.py first."
        )
    return SigningKey(base64.b64decode(private_path.read_text().strip()))


def _sign_payload(payload: dict) -> schemas.SignedToken:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = _get_signing_key().sign(canonical.encode("utf-8")).signature
    return schemas.SignedToken(
        token_json=canonical,
        token=payload,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def _get_entitlement(db: Session, license_key: str) -> models.Entitlement:
    entitlement = (
        db.query(models.Entitlement)
        .filter(models.Entitlement.license_key == license_key)
        .one_or_none()
    )
    if entitlement is None:
        raise HTTPException(status_code=404, detail="License not found")
    return entitlement


def _entitlement_status(entitlement: models.Entitlement, now: datetime) -> str:
    if entitlement.status in ("revoked", "suspended"):
        return entitlement.status
    if entitlement.expires_at is not None and entitlement.expires_at < now:
        return "expired"
    return "active"


def _issue_token(entitlement: models.Entitlement, device_id: str, now: datetime) -> schemas.SignedToken:
    issued_at = int(now.timestamp())
    expires_at = int(entitlement.expires_at.timestamp()) if entitlement.expires_at else None
    return _sign_payload(
        {
            "product_id": entitlement.product_id,
            "license_key": entitlement.license_key,
            "device_id": device_id,
            "tier": entitlement.license_type,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "check_again_by": issued_at + settings.offline_grace_period_seconds,
        }
    )


@router.post(
    "/activate",
    response_model=schemas.SignedToken,
    dependencies=[Depends(rate_limit("licensing:activate", max_requests=20, window_seconds=60))],
)
def activate(req: schemas.ActivateRequest, db: Session = Depends(get_db)) -> schemas.SignedToken:
    now = datetime.now(timezone.utc)
    # Phase 5.5, Section 50-51: activation-slot allocation is a
    # check-then-act sequence (count active activations, then insert if
    # under the limit) -- without a lock, two concurrent activate() calls
    # for the same entitlement can both read the count before either
    # commits, both pass the limit check, and both insert, exceeding
    # max_activations. SELECT ... FOR UPDATE on the entitlement row
    # serializes concurrent activations for the *same* entitlement (a
    # second request blocks until the first transaction commits or rolls
    # back) without affecting unrelated entitlements. Verified under real
    # concurrency in tests/test_concurrency.py.
    entitlement = (
        db.query(models.Entitlement)
        .filter(models.Entitlement.license_key == req.license_key)
        .with_for_update()
        .one_or_none()
    )
    if entitlement is None:
        raise HTTPException(status_code=404, detail="License not found")
    status = _entitlement_status(entitlement, now)
    if status != "active":
        raise HTTPException(status_code=403, detail=f"License is {status}")

    existing = (
        db.query(models.Activation)
        .filter(
            models.Activation.entitlement_id == entitlement.id,
            models.Activation.machine_id == req.device_id,
        )
        .one_or_none()
    )

    if existing is None:
        active_count = (
            db.query(models.Activation)
            .filter(
                models.Activation.entitlement_id == entitlement.id,
                models.Activation.deactivated_at.is_(None),
            )
            .count()
        )
        if active_count >= entitlement.max_activations:
            raise HTTPException(
                status_code=403,
                detail=f"Activation limit reached ({entitlement.max_activations} devices). "
                "Deactivate another device first.",
            )
        db.add(
            models.Activation(
                entitlement_id=entitlement.id,
                machine_id=req.device_id,
                machine_label=req.device_name or None,
                activated_at=now,
                last_seen_at=now,
            )
        )
    else:
        existing.deactivated_at = None
        existing.activated_at = now
        existing.last_seen_at = now
        existing.machine_label = req.device_name or existing.machine_label

    db.commit()
    return _issue_token(entitlement, req.device_id, now)


@router.post(
    "/validate",
    response_model=schemas.SignedToken,
    dependencies=[Depends(rate_limit("licensing:validate", max_requests=60, window_seconds=60))],
)
def validate(req: schemas.ValidateRequest, db: Session = Depends(get_db)) -> schemas.SignedToken:
    now = datetime.now(timezone.utc)
    entitlement = _get_entitlement(db, req.license_key)
    status = _entitlement_status(entitlement, now)
    if status != "active":
        raise HTTPException(status_code=403, detail=f"License is {status}")

    activation = (
        db.query(models.Activation)
        .filter(
            models.Activation.entitlement_id == entitlement.id,
            models.Activation.machine_id == req.device_id,
            models.Activation.deactivated_at.is_(None),
        )
        .one_or_none()
    )
    if activation is None:
        raise HTTPException(status_code=403, detail="Device is not activated for this license")

    activation.last_seen_at = now
    db.commit()
    return _issue_token(entitlement, req.device_id, now)


def _verify_activation_possession(req: schemas.DeactivateRequest) -> bool:
    """Possession proof for /v1/deactivate (SANDBOX_TO_LIVE_CHECKLIST P2).

    The caller must present the signed activation token that /v1/activate
    or /v1/validate issued for this exact license_key + device_id. Without
    this, anyone who learns only the license key (which is emailed in
    plaintext purchase confirmations) could remotely deactivate a
    customer's device. The Ed25519 signature is verified against this
    server's own key, and the embedded claims must match the request.
    Admin revoke remains the support escape hatch for lost tokens.
    """
    if not req.activation_token_json or not req.activation_signature:
        return False
    raw = req.activation_token_json.encode("utf-8")
    try:
        signature = base64.b64decode(req.activation_signature, validate=True)
        # Any failure to verify -- bad signature, malformed base64, wrong
        # key -- means "no proof", never an error surface.
        _get_signing_key().verify_key.verify(raw, signature)
    except Exception:
        return False
    try:
        claims = json.loads(req.activation_token_json)
    except ValueError:
        return False
    if not isinstance(claims, dict):
        return False
    return claims.get("license_key") == req.license_key and claims.get("device_id") == req.device_id


@router.post(
    "/deactivate",
    dependencies=[Depends(rate_limit("licensing:deactivate", max_requests=20, window_seconds=60))],
)
def deactivate(req: schemas.DeactivateRequest, db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    entitlement = _get_entitlement(db, req.license_key)

    activation = (
        db.query(models.Activation)
        .filter(
            models.Activation.entitlement_id == entitlement.id,
            models.Activation.machine_id == req.device_id,
            models.Activation.deactivated_at.is_(None),
        )
        .one_or_none()
    )
    if activation is None:
        raise HTTPException(status_code=404, detail="Active activation not found")

    if not _verify_activation_possession(req):
        raise HTTPException(
            status_code=403,
            detail="Possession proof required: present the signed activation token "
            "issued for this license and device",
        )

    activation.deactivated_at = now
    db.commit()
    return {"status": "deactivated"}
