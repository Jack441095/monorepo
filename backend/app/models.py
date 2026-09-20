"""
SQLAlchemy models -- implements docs/NITE_DSP_DATABASE_SCHEMA.md exactly.
Generic, product-aware entities throughout (Section 14): no table is named
or shaped around SmartSampleManager specifically. Every product-scoped row
carries a product_id foreign key to `products`, so a second NITE DSP
product later needs a new row, never a schema migration.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Product(Base):
    __tablename__ = "products"

    # Stable slug primary key (Section 15) -- e.g. "smart-sample-manager".
    # Never mutable marketing copy. Deliberately NOT a Paddle id: Paddle's
    # own product_id is a separate, real, external reference stored below
    # (paddle_product_id) -- conflating the two meant a real webhook's
    # product_id could never match this table at all until an admin backfills
    # the mapping (found via a real sandbox purchase, 2026-08-14: Paddle sent
    # product_id="pro_01kzyq7zeefn42h5f6kewcr70k", which no query against
    # this column could ever match).
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purchasable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[str | None] = mapped_column(String)
    platforms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    # Paddle's real product_id (e.g. "pro_..."), set once a real Paddle
    # catalog exists. Nullable because this row can exist (and be edited)
    # before commerce is wired up at all -- see docs/PADDLE_INTEGRATION_AUDIT.md.
    paddle_product_id: Mapped[str | None] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active','hidden','discontinued')", name="ck_products_status"),
    )


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    # Which specific Paddle price (intro vs regular) was actually charged --
    # distinct from product_id. Nullable: purchases recorded before this
    # column existed have no value to backfill.
    price_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("provider", "provider_order_id", name="uq_purchases_provider_order"),
        CheckConstraint("status IN ('completed','refunded','disputed')", name="ck_purchases_status"),
    )


class Entitlement(Base):
    __tablename__ = "entitlements"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    purchase_id: Mapped[str | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    # Opaque customer-facing key entered into the plugin -- distinct from
    # this row's internal id. Matches Source/Licensing/LicenseTypes.h's
    # LicenseToken::licenseKey and the dev licensing_server's license_key
    # column (docs/LICENSE_KEY_LIFECYCLE.md). Format: four hyphenated
    # 8-hex-char groups, same as the dev server's generator.
    license_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    license_type: Mapped[str] = mapped_column(String, nullable=False)
    max_activations: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "license_type IN ('perpetual','subscription','trial','beta','nfr','educational')",
            name="ck_entitlements_license_type",
        ),
        CheckConstraint(
            "status IN ('active','suspended','revoked','expired')", name="ck_entitlements_status"
        ),
    )


class Activation(Base):
    __tablename__ = "activations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    entitlement_id: Mapped[str] = mapped_column(ForeignKey("entitlements.id"), nullable=False, index=True)
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    machine_label: Mapped[str | None] = mapped_column(String)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("entitlement_id", "machine_id", name="uq_activations_entitlement_machine"),
    )


class Trial(Base):
    __tablename__ = "trials"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    converted_purchase_id: Mapped[str | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("product_id", "machine_id", name="uq_trials_product_machine"),
    )


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    architecture: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False, default="stable")
    checksum_sha256: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str | None] = mapped_column(String)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    release_notes: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "product_id", "version", "platform", "architecture", name="uq_releases_product_version_platform_arch"
        ),
        CheckConstraint("channel IN ('dev','beta','private-beta','stable')", name="ck_releases_channel"),
    )


class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_webhook_events_provider_event"),
    )


class MagicLinkToken(Base):
    """Not in the Phase 3 schema doc (an implementation detail of the chosen
    auth method, not a commercial entity) -- short-lived, single-use
    passwordless login tokens. See docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md."""

    __tablename__ = "magic_link_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    use_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("email", "product_id", name="uq_waitlist_email_product"),
    )


class ContactEntry(Base):
    """Contact form submissions -- lightweight records for tracking enquiries.

    Not a user account; just a stored message that gets forwarded to the
    business owner's email.
    """

    __tablename__ = "contact_entries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class AdminAuditLogEntry(Base):
    """Section 73 -- sensitive admin actions: actor, action, target,
    timestamp. Never logs secrets."""

    __tablename__ = "admin_audit_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ParaphraseOrder(Base):
    """Anonymous pay-what-you-like purchase for the paraphrase product.

    Deliberately NOT a `users`/`purchases`/`entitlements` row: paraphrase is
    anonymous-by-design (no email, no account), and its unlock is a
    short-lived session token rather than a perpetual software licence.
    Forms the bridge between a real Paddle transaction.completed event and
    the browser that paid: the client generated a random `hint` before
    starting checkout and sent it via Paddle custom_data; the webhook
    records it here; the redemption endpoint proves it and issues the
    signed unlock token (app/paraphrase_orders.py). Idempotent via the
    unique provider_order_id -- a duplicate webhook delivery updates
    nothing.
    """

    __tablename__ = "paraphrase_orders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    hint: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    provider_order_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


