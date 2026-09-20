-- Real storage for POST /api/benchmark/rate. Previously this route created
-- its own ad-hoc table via a raw sqlite3 connection, using the name
-- "automix_advisor_feedback" -- which collided with the real, differently
-- shaped automix_advisor_feedback table from migration 011. Every insert
-- silently failed against the real schema's NOT NULL/CHECK constraints and
-- missing columns, swallowed by a bare except, while the route still
-- reported success. This table has its own name and its own real schema.
CREATE TABLE IF NOT EXISTS listening_benchmark_ratings (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    package_id TEXT NOT NULL,
    active_mix_evaluated INTEGER NOT NULL DEFAULT 1,
    preference TEXT NOT NULL DEFAULT 'equal',
    producer_name TEXT NOT NULL DEFAULT '',
    score_clarity INTEGER,
    score_bass INTEGER,
    score_width INTEGER,
    score_punch INTEGER,
    feedback_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listening_benchmark_ratings_package
    ON listening_benchmark_ratings(package_id, created_at);
