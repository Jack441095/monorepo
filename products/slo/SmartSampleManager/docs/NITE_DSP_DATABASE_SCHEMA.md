# NITE DSP — Commercial Database Schema (Design Only)

Phase 3, Sections 14-16. **Design document — no database exists yet.** Expands Phase 2's
data-model sketch (`docs/NITE_DSP_COMMERCIAL_ARCHITECTURE.md`) into an actual schema with real
column types, constraints, and indexes, per Phase 3's request for a dedicated schema document.
PostgreSQL syntax (the recommended engine — see `docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`'s
technology recommendation), but nothing here has been run against a real database.

## Governing constraint

Generic, product-aware entities throughout — never `smart_sample_manager_customers` or
`smart_sample_manager_licenses`. Every table that needs to know "which product" uses a
`product_id` foreign key to the `products` table, so adding a second NITE DSP product later is a
new row, never a schema migration.

## Schema

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    -- Auth method TBD (Section 35) -- password_hash nullable to support a
    -- passwordless-only launch without a schema change if password auth is
    -- added later.
    password_hash   TEXT,
    email_verified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_email ON users (email);

CREATE TABLE products (
    id              TEXT PRIMARY KEY,  -- stable slug, e.g. 'smart-sample-manager' -- see Section 15
    name            TEXT NOT NULL,     -- display name, e.g. 'Smart Sample Manager'
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'hidden', 'discontinued')),
    public          BOOLEAN NOT NULL DEFAULT false,   -- must be explicitly flipped true, never defaults on
    purchasable     BOOLEAN NOT NULL DEFAULT false,
    description     TEXT,
    current_version TEXT,
    platforms       TEXT[] NOT NULL DEFAULT '{}',      -- e.g. {'macos'}
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Initial production data: exactly one row.
-- INSERT INTO products (id, name, status, public, purchasable, platforms)
--   VALUES ('smart-sample-manager', 'Smart Sample Manager', 'active', true, true, '{macos}');
-- No other product row is created until that product is genuinely ready to
-- commercialise -- see docs/COMMERCIAL_SCOPE.md.

CREATE TABLE purchases (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    product_id          TEXT NOT NULL REFERENCES products(id),
    provider            TEXT NOT NULL,           -- 'paddle' | future providers
    provider_order_id   TEXT NOT NULL,
    amount_cents        INTEGER NOT NULL,
    currency            TEXT NOT NULL,            -- ISO 4217, e.g. 'GBP'
    status              TEXT NOT NULL DEFAULT 'completed'
                             CHECK (status IN ('completed', 'refunded', 'disputed')),
    purchased_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    refunded_at         TIMESTAMPTZ,
    UNIQUE (provider, provider_order_id)   -- webhook idempotency -- see docs/PAYMENT_FLOW.md
);
CREATE INDEX idx_purchases_user ON purchases (user_id);

CREATE TABLE entitlements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    product_id          TEXT NOT NULL REFERENCES products(id),
    purchase_id         UUID REFERENCES purchases(id),  -- nullable: NFR/comp/beta entitlements have no purchase
    license_type        TEXT NOT NULL
                             CHECK (license_type IN ('perpetual', 'subscription', 'trial', 'beta', 'nfr', 'educational')),
    max_activations     INTEGER NOT NULL DEFAULT 3,
    status              TEXT NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'suspended', 'revoked', 'expired')),
    expires_at          TIMESTAMPTZ,               -- null for perpetual; set for trial/beta/subscription
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at          TIMESTAMPTZ,
    revoked_reason      TEXT
);
CREATE INDEX idx_entitlements_user ON entitlements (user_id);
CREATE INDEX idx_entitlements_product ON entitlements (product_id);

CREATE TABLE activations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entitlement_id      UUID NOT NULL REFERENCES entitlements(id),
    machine_id          TEXT NOT NULL,             -- client-generated stable hardware identifier
    machine_label       TEXT,                       -- user-editable, e.g. "Jack's MacBook Pro"
    activated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deactivated_at      TIMESTAMPTZ,
    UNIQUE (entitlement_id, machine_id)
);
CREATE INDEX idx_activations_entitlement ON activations (entitlement_id);

CREATE TABLE trials (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id),   -- nullable: see docs/TRIAL_ARCHITECTURE.md's
                                                        -- anonymous-trial note
    product_id          TEXT NOT NULL REFERENCES products(id),
    machine_id          TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,
    converted_purchase_id UUID REFERENCES purchases(id),  -- set if the trial converted to a sale
    UNIQUE (product_id, machine_id)   -- one trial per machine per product -- see Trial Abuse section
);

CREATE TABLE releases (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id          TEXT NOT NULL REFERENCES products(id),
    version             TEXT NOT NULL,              -- semver, e.g. '1.0.0'
    platform            TEXT NOT NULL,               -- 'macos' | 'windows'
    architecture        TEXT NOT NULL,                -- 'universal' | 'x86_64' | 'arm64'
    channel             TEXT NOT NULL DEFAULT 'stable'
                             CHECK (channel IN ('dev', 'beta', 'stable')),
    checksum_sha256      TEXT NOT NULL,
    signature            TEXT,                          -- code-signature reference/identifier, not a secret
    storage_key           TEXT NOT NULL,                 -- object-storage path -- see docs/DOWNLOAD_ARCHITECTURE.md
    release_notes          TEXT,
    published_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, version, platform, architecture)
    -- Immutability (Phase 3 Section 80): application-layer rule, not a DB
    -- constraint -- once published_at is set and the row has been served to
    -- a customer, the release service must refuse to overwrite storage_key
    -- for that row; a new binary requires a new version row.
);
CREATE INDEX idx_releases_product_platform_channel ON releases (product_id, platform, channel);

CREATE TABLE downloads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id          UUID NOT NULL REFERENCES releases(id),
    user_id             UUID REFERENCES users(id),    -- nullable: anonymous trial downloads
    downloaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE webhook_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider            TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    provider_event_id   TEXT NOT NULL,
    payload_json         JSONB NOT NULL,
    received_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at           TIMESTAMPTZ,
    processing_error        TEXT,
    UNIQUE (provider, provider_event_id)   -- the actual duplicate-webhook-delivery guard
);
CREATE INDEX idx_webhook_events_unprocessed ON webhook_events (received_at) WHERE processed_at IS NULL;
```

## Design notes

- **`entitlements.status`** implements the refund/revocation policy from `docs/PAYMENT_FLOW.md`
  — `active`/`suspended`/`revoked`/`expired`, never a row deletion. Historical records are
  preserved per Phase 3 Section 31/32's explicit "do not silently erase" instruction.
- **`webhook_events` UNIQUE(provider, provider_event_id)`** is the actual mechanism preventing
  duplicate webhook delivery from creating duplicate entitlements — an `INSERT ... ON CONFLICT DO
  NOTHING` on this table, checked before any entitlement-creation logic runs.
- **`purchases` UNIQUE(provider, provider_order_id)`** is a second idempotency layer at the
  purchase-record level, independent of the webhook-event layer.
- **`trials` UNIQUE(product_id, machine_id)`** is the primary trial-abuse control (Section 34) —
  reasonable resistance (one trial per machine per product), not invasive fingerprinting.
- **No table stores raw payment card data** (Section 29) — `purchases` stores only
  provider-supplied metadata (amount, currency, provider's own order ID), never card details.

## What this schema does NOT include

- Admin/support-tool-specific tables (audit logs, admin user accounts) — covered separately in a
  future admin-tooling design pass (Section 68), not needed for the core commercial flow this
  schema supports.
- Anything product-specific to SmartSampleManager (library size limits, feature flags) — those
  belong in the client-side license token's `features` array (`docs/LICENSE_KEY_LIFECYCLE.md`),
  not the generic commercial schema, per Section 14's explicit instruction.

## Status

**Design only.** No PostgreSQL instance exists, this SQL has not been executed anywhere.
Deployment is gated on the production hosting account in
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`.
