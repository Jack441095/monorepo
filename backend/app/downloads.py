"""
Download service -- entitlement-gated release URLs + storage adapters.

GET /downloads/latest requires the caller to be authenticated (session
cookie) and to hold an active entitlement for the requested product --
Section 52's "no download without entitlement" requirement. It returns a
short-lived signed download token (15 min, security.py's
DOWNLOAD_URL_MAX_AGE_SECONDS) rather than a permanent public URL, matching
docs/DOWNLOAD_ARCHITECTURE.md.

Local `mock_storage/` is used for development/tests. S3-compatible mode
returns a short-lived presigned object URL after this API validates the signed
token and records the download. Release artifacts only; customer documents are
never written here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from . import models
from .auth import get_current_user
from .config import settings
from .database import get_db
from .rate_limit import rate_limit
from .security import DOWNLOAD_URL_MAX_AGE_SECONDS, create_download_token, read_download_token
from .storage import StorageError, StorageNotFound, get_storage

router = APIRouter(prefix="/downloads", tags=["downloads"])

# Platform names are part of the customer-facing download contract. Keep the
# release table extensible, but fail clearly for accidental/unsupported
# requests instead of returning the same generic "release missing" response
# for a platform NITE DSP does not ship.
SUPPORTED_PLATFORMS = frozenset({"macos", "windows", "linux"})


def _require_entitlement(db: Session, user: models.User, product_id: str) -> models.Entitlement:
    now = datetime.now(timezone.utc)
    entitlement = (
        db.query(models.Entitlement)
        .filter(
            models.Entitlement.user_id == user.id,
            models.Entitlement.product_id == product_id,
            models.Entitlement.status == "active",
            (models.Entitlement.expires_at.is_(None) | (models.Entitlement.expires_at > now)),
        )
        .one_or_none()
    )
    if entitlement is None:
        raise HTTPException(status_code=403, detail="No active entitlement for this product")
    return entitlement


@router.get("/latest", dependencies=[Depends(rate_limit("downloads:latest", max_requests=30, window_seconds=60))])
def latest(
    product_id: str,
    platform: str,
    architecture: str,
    channel: str = "stable",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> dict:
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform: {platform}. Supported platforms: macos, windows, linux",
        )

    _require_entitlement(db, user, product_id)

    release = (
        db.query(models.Release)
        .filter(
            models.Release.product_id == product_id,
            models.Release.platform == platform,
            models.Release.architecture == architecture,
            models.Release.channel == channel,
        )
        .order_by(models.Release.published_at.desc())
        .first()
    )
    if release is None:
        raise HTTPException(status_code=404, detail="No matching release found")

    token = create_download_token(release.id, user.id)
    return {
        "version": release.version,
        "checksum_sha256": release.checksum_sha256,
        "release_notes": release.release_notes,
        "download_url": f"{settings.nite_dsp_api_url}/downloads/fetch?token={token}",
    }


@router.get("/fetch", dependencies=[Depends(rate_limit("downloads:fetch", max_requests=30, window_seconds=60))])
def fetch(token: str, db: Session = Depends(get_db)):
    claims = read_download_token(token)
    if claims is None:
        raise HTTPException(status_code=400, detail="Download link expired or invalid")
    if not isinstance(claims, dict):
        raise HTTPException(status_code=400, detail="Download link expired or invalid")
    release_id = claims.get("release_id")
    user_id = claims.get("user_id")
    if not isinstance(release_id, str) or not release_id:
        raise HTTPException(status_code=400, detail="Download link expired or invalid")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=400, detail="Download link expired or invalid")

    release = db.get(models.Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=403, detail="No active entitlement for this product")
    _require_entitlement(db, user, release.product_id)

    try:
        storage = get_storage()
        if not storage.exists(release.storage_key):
            raise HTTPException(status_code=404, detail="Release artifact missing from storage")
        file_path = storage.local_path(release.storage_key)
        if file_path is None:
            signed_url = storage.presigned_get_url(
                release.storage_key,
                expires_in=DOWNLOAD_URL_MAX_AGE_SECONDS,
                filename=release.storage_key.rsplit("/", 1)[-1],
            )
            if not signed_url:
                raise HTTPException(status_code=503, detail="Release storage is unavailable")
            db.add(models.Download(release_id=release.id, user_id=user_id))
            db.commit()
            return RedirectResponse(signed_url, status_code=307)
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Release artifact missing from storage")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Release artifact missing from storage") from exc
    except StorageNotFound as exc:
        raise HTTPException(status_code=404, detail="Release artifact missing from storage") from exc
    except StorageError as exc:
        raise HTTPException(status_code=503, detail="Release storage is unavailable") from exc

    db.add(models.Download(release_id=release.id, user_id=user_id))
    db.commit()

    return FileResponse(file_path, filename=file_path.name, media_type="application/octet-stream")
