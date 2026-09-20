-- Durable external-delivery outbox with explicit claim and receipt states

CREATE TABLE IF NOT EXISTS delivery_outbox (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT,
    claimed_at TEXT,
    lease_expiry_at TEXT,
    sending_at TEXT,
    sent_at TEXT,
    provider_receipt TEXT,
    followup_id TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (kind, aggregate_type, aggregate_id)
);

CREATE INDEX IF NOT EXISTS idx_delivery_outbox_status_created
ON delivery_outbox(status, created_at);

CREATE INDEX IF NOT EXISTS idx_delivery_outbox_lease
ON delivery_outbox(status, lease_expiry_at);
