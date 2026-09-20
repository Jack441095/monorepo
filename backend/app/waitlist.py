from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .rate_limit import rate_limit

logger = logging.getLogger("nitedsp.waitlist")

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

CAPACITY = {
    "smart-sample-manager": 50,
}


class WaitlistJoinRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    product_id: str
    use_case: str | None = None


class WaitlistJoinResponse(BaseModel):
    ok: bool
    count: int
    capacity: int


class WaitlistCountResponse(BaseModel):
    count: int
    capacity: int


@router.post("/join", response_model=WaitlistJoinResponse)
async def join_waitlist(
    body: WaitlistJoinRequest,
    db: Session = Depends(get_db),
    _rl: None = Depends(rate_limit("waitlist:join", max_requests=5, window_seconds=300)),
):
    product = db.get(models.Product, body.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    capacity = CAPACITY.get(body.product_id, 50)

    existing = (
        db.query(models.WaitlistEntry)
        .filter_by(email=body.email, product_id=body.product_id)
        .first()
    )
    if existing:
        count = (
            db.query(func.count(models.WaitlistEntry.id))
            .filter_by(product_id=body.product_id)
            .scalar()
        )
        return WaitlistJoinResponse(ok=True, count=count, capacity=capacity)

    entry = models.WaitlistEntry(
        email=body.email,
        name=body.name,
        product_id=body.product_id,
        use_case=body.use_case,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        # SELECT-then-INSERT race: a concurrent join for the same
        # (email, product_id) won the unique constraint. Roll back and
        # return the current count idempotently instead of 500.
        db.rollback()
        count = (
            db.query(func.count(models.WaitlistEntry.id))
            .filter_by(product_id=body.product_id)
            .scalar()
            or 0
        )
        return WaitlistJoinResponse(ok=True, count=count, capacity=capacity)

    count = (
        db.query(func.count(models.WaitlistEntry.id))
        .filter_by(product_id=body.product_id)
        .scalar()
    )

    logger.info("waitlist_join product=%s count=%d", body.product_id, count)
    return WaitlistJoinResponse(ok=True, count=count, capacity=capacity)


@router.get("/count/{product_id}", response_model=WaitlistCountResponse)
async def waitlist_count(
    product_id: str,
    db: Session = Depends(get_db),
):
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    capacity = CAPACITY.get(product_id, 50)
    count = (
        db.query(func.count(models.WaitlistEntry.id))
        .filter_by(product_id=product_id)
        .scalar()
    )
    return WaitlistCountResponse(count=count, capacity=capacity)
