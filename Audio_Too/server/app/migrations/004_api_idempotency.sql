-- Idempotency records for retryable API mutations

CREATE TABLE IF NOT EXISTS api_idempotency (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (operation, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_api_idempotency_created_at
ON api_idempotency(created_at);
