"""
Minimal admin operations -- Section 73.

Fail-closed by design: `require_admin` rejects every request unless
`settings.admin_api_key` is non-empty AND the caller's `X-Admin-Key` header
matches it via constant-time comparison. An empty admin_api_key (the
default, since no production secrets store exists yet -- see config.py's
comment) means these endpoints are entirely unreachable, not "reachable
with no auth" -- the exact gap found in the dev licensing_server's
POST /v1/admin/licenses, which this deliberately does not repeat.

Every mutating action writes an AdminAuditLogEntry (actor/action/target/
reason) -- never logs secrets.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import email_templates, models
from .config import settings
from .database import get_db
from .email import send_email
from .rate_limit import rate_limit

# Phase 5, Section 23: a beta tester must not be unexpectedly disabled
# mid-testing-cycle. 90 days is long enough to span a typical private-beta
# cycle (feedback rounds, a couple of point releases) without needing
# manual renewal, while still being a bounded grant rather than a
# perpetual one. Applies only when the admin doesn't specify an explicit
# expires_in_days -- an explicit value always wins.
DEFAULT_BETA_EXPIRY_DAYS = 90

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_key_rate_limit = rate_limit("admin:auth", max_requests=10, window_seconds=60)


def require_admin(request: Request, x_admin_key: str | None = Header(default=None)) -> str:
    # Applied here rather than per-route so every admin endpoint is covered
    # uniformly -- this is the login-sensitive operation (an admin-key
    # guess), not any individual admin action.
    _admin_key_rate_limit(request)
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin API is not configured")
    if x_admin_key is None or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return "admin"


def _audit(db: Session, actor: str, action: str, target: str, reason: str | None = None) -> None:
    db.add(models.AdminAuditLogEntry(actor=actor, action=action, target=target, reason=reason))


@router.get("/users/search")
def search_user(email: str, db: Session = Depends(get_db), actor: str = Depends(require_admin)) -> dict:
    user = db.query(models.User).filter(models.User.email == email).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    entitlements = db.query(models.Entitlement).filter(models.Entitlement.user_id == user.id).all()
    return {
        "user": {"id": user.id, "email": user.email, "created_at": user.created_at},
        "entitlements": [
            {
                "id": e.id,
                "product_id": e.product_id,
                "license_key": e.license_key,
                "license_type": e.license_type,
                "status": e.status,
                "max_activations": e.max_activations,
            }
            for e in entitlements
        ],
    }


@router.get("/entitlements/{entitlement_id}/activations")
def list_activations(
    entitlement_id: str, db: Session = Depends(get_db), actor: str = Depends(require_admin)
) -> list[dict]:
    activations = (
        db.query(models.Activation).filter(models.Activation.entitlement_id == entitlement_id).all()
    )
    return [
        {
            "id": a.id,
            "machine_id": a.machine_id,
            "machine_label": a.machine_label,
            "activated_at": a.activated_at,
            "last_seen_at": a.last_seen_at,
            "deactivated_at": a.deactivated_at,
        }
        for a in activations
    ]


class IssueEntitlementRequest(BaseModel):
    email: str
    product_id: str
    license_type: str = "beta"
    max_activations: int = 3
    expires_in_days: int | None = None


@router.post("/entitlements/issue")
def issue_entitlement(
    req: IssueEntitlementRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    if req.license_type not in ("perpetual", "subscription", "trial", "beta", "nfr", "educational"):
        raise HTTPException(status_code=400, detail="Invalid license_type")

    user = db.query(models.User).filter(models.User.email == req.email).one_or_none()
    if user is None:
        user = models.User(email=req.email, email_verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()

    expires_in_days = req.expires_in_days
    if expires_in_days is None and req.license_type == "beta":
        expires_in_days = DEFAULT_BETA_EXPIRY_DAYS
    expires_at = None
    if expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    license_key = "-".join(secrets.token_hex(4).upper() for _ in range(4))
    entitlement = models.Entitlement(
        user_id=user.id,
        product_id=req.product_id,
        license_key=license_key,
        license_type=req.license_type,
        max_activations=req.max_activations,
        status="active",
        expires_at=expires_at,
    )
    db.add(entitlement)
    db.flush()
    _audit(db, actor, "issue_entitlement", entitlement.id, f"{req.license_type} for {req.email}")
    db.commit()

    expires_at_iso = expires_at.date().isoformat() if expires_at else None
    product_display_name = "Smart Sample Manager"  # only commercial product -- Section 14
    if req.license_type == "beta":
        subject, body = email_templates.beta_invite(license_key, product_display_name, expires_at_iso)
    else:
        subject, body = email_templates.license_ready(product_display_name, license_key)
    send_email(to=req.email, subject=subject, body=body)
    return {"entitlement_id": entitlement.id, "license_key": license_key, "expires_at": expires_at}


class RevokeRequest(BaseModel):
    reason: str


@router.post("/entitlements/{entitlement_id}/revoke")
def revoke_entitlement(
    entitlement_id: str,
    req: RevokeRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    entitlement = db.get(models.Entitlement, entitlement_id)
    if entitlement is None:
        raise HTTPException(status_code=404, detail="Entitlement not found")
    entitlement.status = "revoked"
    entitlement.revoked_at = datetime.now(timezone.utc)
    entitlement.revoked_reason = req.reason
    _audit(db, actor, "revoke_entitlement", entitlement_id, req.reason)
    db.commit()
    return {"status": "revoked"}


@router.post("/activations/{activation_id}/reset")
def reset_activation(
    activation_id: str, db: Session = Depends(get_db), actor: str = Depends(require_admin)
) -> dict:
    activation = db.get(models.Activation, activation_id)
    if activation is None:
        raise HTTPException(status_code=404, detail="Activation not found")
    activation.deactivated_at = datetime.now(timezone.utc)
    _audit(db, actor, "reset_activation", activation_id)
    db.commit()
    return {"status": "reset"}


@router.get("/webhooks/failed")
def failed_webhooks(db: Session = Depends(get_db), actor: str = Depends(require_admin)) -> list[dict]:
    events = (
        db.query(models.WebhookEvent)
        .filter(models.WebhookEvent.processing_error.is_not(None))
        .order_by(models.WebhookEvent.received_at.desc())
        .all()
    )
    return [
        {
            "id": e.id,
            "provider": e.provider,
            "event_type": e.event_type,
            "provider_event_id": e.provider_event_id,
            "received_at": e.received_at,
            "processing_error": e.processing_error,
        }
        for e in events
    ]
