"""Passwordless magic-link auth -- docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md.

Flow: POST /auth/request-link {email} -> creates a MagicLinkToken, "sends"
it via email.send_email (console-logged locally) as a link containing the
raw token. POST /auth/verify {token} -> looks up the hash, checks
expiry/single-use, creates the user if new, sets a signed session cookie.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from . import email_templates, models, schemas
from .config import settings
from .database import get_db
from .email import send_email
from .rate_limit import rate_limit
from .security import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_cookie,
    generate_raw_token,
    hash_token,
    read_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> models.User:
    if session_cookie is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = read_session_cookie(session_cookie)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/request-link", dependencies=[Depends(rate_limit("auth:request-link", max_requests=5, window_seconds=300))])
def request_link(req: schemas.MagicLinkRequest, db: Session = Depends(get_db)) -> dict:
    raw_token = generate_raw_token()
    now = datetime.now(timezone.utc)
    entry = models.MagicLinkToken(
        email=req.email,
        token_hash=hash_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(seconds=settings.magic_link_ttl_seconds),
    )
    db.add(entry)
    db.commit()

    subject, body = email_templates.magic_link(raw_token, settings.magic_link_ttl_seconds)
    send_email(to=req.email, subject=subject, body=body)
    return {"status": "sent"}


@router.post("/verify", dependencies=[Depends(rate_limit("auth:verify", max_requests=10, window_seconds=300))])
def verify(req: schemas.MagicLinkVerify, response: Response, db: Session = Depends(get_db)) -> dict:
    token_hash = hash_token(req.token)
    entry = (
        db.query(models.MagicLinkToken)
        .filter(models.MagicLinkToken.token_hash == token_hash)
        .one_or_none()
    )
    if entry is None:
        raise HTTPException(status_code=400, detail="Invalid token")
    now = datetime.now(timezone.utc)
    if entry.used_at is not None:
        raise HTTPException(status_code=400, detail="Token already used")
    if entry.expires_at < now:
        raise HTTPException(status_code=400, detail="Token expired")

    entry.used_at = now

    user = db.query(models.User).filter(models.User.email == entry.email).one_or_none()
    if user is None:
        user = models.User(email=entry.email, email_verified_at=now)
        db.add(user)
        db.flush()

    db.commit()

    cookie_value = create_session_cookie(user.id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
    )
    return {"status": "ok", "user": schemas.UserOut.model_validate(user).model_dump(mode="json")}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me", response_model=schemas.UserOut)
def me(request_user: models.User = Depends(get_current_user)) -> models.User:
    return request_user


@router.get("/entitlements", response_model=list[schemas.EntitlementOut])
def my_entitlements(
    request_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[models.Entitlement]:
    return db.query(models.Entitlement).filter(models.Entitlement.user_id == request_user.id).all()
