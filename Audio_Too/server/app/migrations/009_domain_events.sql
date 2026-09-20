-- Append-only correlated domain event stream for project timelines and replay.

CREATE TABLE IF NOT EXISTS domain_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL,
    causation_id TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    schema_version INTEGER NOT NULL DEFAULT 1,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_domain_events_project
    ON domain_events(project_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_domain_events_correlation
    ON domain_events(correlation_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_domain_events_aggregate
    ON domain_events(aggregate_type, aggregate_id, occurred_at);

CREATE TRIGGER IF NOT EXISTS domain_events_no_update
BEFORE UPDATE ON domain_events
BEGIN
    SELECT RAISE(ABORT, 'domain events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS domain_events_no_delete
BEFORE DELETE ON domain_events
BEGIN
    SELECT RAISE(ABORT, 'domain events are append-only');
END;
