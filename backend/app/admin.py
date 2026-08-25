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
import re
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
from .storage import StorageError, StorageNotFound, get_storage

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
    product = db.get(models.Product, req.product_id)
    product_display_name = product.name if product else req.product_id
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


@router.get("/products")
def list_products(db: Session = Depends(get_db), actor: str = Depends(require_admin)) -> list[dict]:
    """No public catalog-listing endpoint exists (the website hardcodes its
    own pricing copy) -- this is the only way to see what's actually in the
    products table, which otherwise has no seed script or creation UI at
    all (found while debugging a real webhook rejecting every purchase
    as an unknown product, 2026-08-14)."""
    products = db.query(models.Product).order_by(models.Product.id).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "public": p.public,
            "purchasable": p.purchasable,
            "paddle_product_id": p.paddle_product_id,
            "platforms": p.platforms,
        }
        for p in products
    ]


class UpsertProductRequest(BaseModel):
    id: str
    name: str
    status: str = "active"
    public: bool = True
    purchasable: bool = True
    description: str | None = None
    current_version: str | None = None
    platforms: list[str] = []
    paddle_product_id: str | None = None


@router.put("/products/{product_id}")
def upsert_product(
    product_id: str,
    req: UpsertProductRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    """Create or update a Product row -- id is the path param (our stable
    internal slug), req.id must match it so the route and body can't
    silently disagree about which row is being written."""
    if req.id != product_id:
        raise HTTPException(status_code=400, detail="Path product_id and body id must match")

    product = db.get(models.Product, product_id)
    is_new = product is None
    if product is None:
        product = models.Product(id=product_id)
        db.add(product)

    product.name = req.name
    product.status = req.status
    product.public = req.public
    product.purchasable = req.purchasable
    product.description = req.description
    product.current_version = req.current_version
    product.platforms = req.platforms
    product.paddle_product_id = req.paddle_product_id

    _audit(db, actor, "product.created" if is_new else "product.updated", product_id)
    db.commit()
    return {"id": product.id, "paddle_product_id": product.paddle_product_id}


class UpsertReleaseRequest(BaseModel):
    product_id: str
    version: str
    platform: str
    architecture: str
    channel: str = "stable"
    checksum_sha256: str
    storage_key: str
    signature: str | None = None
    release_notes: str | None = None


@router.put("/releases/{product_id}/{version}/{platform}/{architecture}")
def upsert_release(
    product_id: str,
    version: str,
    platform: str,
    architecture: str,
    req: UpsertReleaseRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    """Register an already-uploaded artifact after verifying its checksum.

    This endpoint never accepts file contents or arbitrary filesystem paths;
    deployment/storage is a separate operation. The storage adapter verifies
    that the supplied checksum matches the bytes already present in the
    configured local directory or private object bucket.
    """
    if (req.product_id, req.version, req.platform, req.architecture) != (
        product_id,
        version,
        platform,
        architecture,
    ):
        raise HTTPException(status_code=400, detail="Path and body release identity must match")
    if platform not in {"macos", "windows", "linux"}:
        raise HTTPException(status_code=400, detail="Unsupported release platform")
    if req.channel not in {"dev", "beta", "private-beta", "stable"}:
        raise HTTPException(status_code=400, detail="Invalid release channel")
    if re.fullmatch(r"[0-9a-fA-F]{64}", req.checksum_sha256) is None:
        raise HTTPException(status_code=400, detail="checksum_sha256 must be a 64-character SHA-256 hex digest")

    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        storage = get_storage()
        if not storage.exists(req.storage_key):
            raise HTTPException(status_code=404, detail="Release artifact missing from storage")
        actual_checksum = storage.sha256(req.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="storage_key must remain inside configured release storage") from exc
    except StorageNotFound as exc:
        raise HTTPException(status_code=404, detail="Release artifact missing from storage") from exc
    except StorageError as exc:
        raise HTTPException(status_code=503, detail="Release storage is unavailable") from exc
    if actual_checksum != req.checksum_sha256.lower():
        raise HTTPException(status_code=409, detail="Release checksum does not match artifact bytes")

    release = (
        db.query(models.Release)
        .filter(
            models.Release.product_id == product_id,
            models.Release.version == version,
            models.Release.platform == platform,
            models.Release.architecture == architecture,
        )
        .one_or_none()
    )
    is_new = release is None
    if release is None:
        release = models.Release(
            product_id=product_id,
            version=version,
            platform=platform,
            architecture=architecture,
        )
        db.add(release)

    release.channel = req.channel
    release.checksum_sha256 = actual_checksum
    release.signature = req.signature
    release.storage_key = req.storage_key
    release.release_notes = req.release_notes
    release.published_at = datetime.now(timezone.utc)
    _audit(
        db,
        actor,
        "release.created" if is_new else "release.updated",
        f"{product_id}:{version}:{platform}:{architecture}",
    )
    db.commit()
    return {
        "product_id": release.product_id,
        "version": release.version,
        "platform": release.platform,
        "architecture": release.architecture,
        "checksum_sha256": release.checksum_sha256,
        "storage_key": release.storage_key,
    }


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


@router.get("/purchases/search")
def search_purchase(
    provider_order_id: str, db: Session = Depends(get_db), actor: str = Depends(require_admin)
) -> dict:
    """Look up a purchase by Paddle transaction ID -- e.g. after a refund
    webhook records purchase.status="refunded" (commerce.py's
    _handle_adjustment_created), an admin uses this to find the associated
    entitlement and decide whether to revoke it via the existing
    POST /admin/entitlements/{id}/revoke, per this repo's policy that
    refund-driven revocation is a manual decision, not automatic."""
    purchase = (
        db.query(models.Purchase)
        .filter(models.Purchase.provider_order_id == provider_order_id)
        .one_or_none()
    )
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    entitlements = (
        db.query(models.Entitlement).filter(models.Entitlement.purchase_id == purchase.id).all()
    )
    return {
        "purchase": {
            "id": purchase.id,
            "user_id": purchase.user_id,
            "product_id": purchase.product_id,
            "price_id": purchase.price_id,
            "provider_order_id": purchase.provider_order_id,
            "amount_cents": purchase.amount_cents,
            "currency": purchase.currency,
            "status": purchase.status,
            "purchased_at": purchase.purchased_at,
            "refunded_at": purchase.refunded_at,
        },
        "entitlements": [
            {"id": e.id, "license_key": e.license_key, "status": e.status} for e in entitlements
        ],
    }
