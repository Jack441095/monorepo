"""
Download service -- signed URLs against local mock storage + release API.

GET /downloads/latest requires the caller to be authenticated (session
cookie) and to hold an active entitlement for the requested product --
Section 52's "no download without entitlement" requirement. It returns a
short-lived signed download token (15 min, security.py's
DOWNLOAD_URL_MAX_AGE_SECONDS) rather than a permanent public URL, matching
docs/DOWNLOAD_ARCHITECTURE.md.

`mock_storage/` stands in for real object storage during local staging --
see config.py's mock_storage_dir comment. It never contains real
SmartSampleManager build artifacts under the NITE DSP name, since that
identity has not been approved (docs/NITE_DSP_PRODUCT_IDENTITY.md); test
release rows point at placeholder files created only to exercise the
download mechanics.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import models, schemas
from .auth import get_current_user
from .config import settings
from .database import get_db
from .rate_limit import rate_limit
from .security import create_download_token, read_download_token

router = APIRouter(prefix="/downloads", tags=["downloads"])


def _require_entitlement(db: Session, user: models.User, product_id: str) -> models.Entitlement:
    entitlement = (
        db.query(models.Entitlement)
        .filter(
            models.Entitlement.user_id == user.id,
            models.Entitlement.product_id == product_id,
            models.Entitlement.status == "active",
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

    release = db.get(models.Release, claims["release_id"])
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    file_path = Path(settings.mock_storage_dir) / release.storage_key
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Release artifact missing from storage")

    db.add(models.Download(release_id=release.id, user_id=claims["user_id"]))
    db.commit()

    return FileResponse(file_path, filename=file_path.name, media_type="application/octet-stream")
