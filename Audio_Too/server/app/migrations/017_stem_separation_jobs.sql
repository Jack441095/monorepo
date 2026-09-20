-- Durable stem-separation (Demucs v4) job queue with leases, recovery, and
-- immutable events. Mirrors 007_audiogen_jobs.sql's shape.

CREATE TABLE IF NOT EXISTS stem_separation_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    source_filename TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'htdemucs',
    project_id TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    error TEXT NOT NULL DEFAULT '',
    worker_id TEXT,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    heartbeat_at TEXT,
    lease_expiry_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stem_separation_jobs_queue
    ON stem_separation_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_stem_separation_jobs_lease
    ON stem_separation_jobs(status, lease_expiry_at);
CREATE INDEX IF NOT EXISTS idx_stem_separation_jobs_project
    ON stem_separation_jobs(project_id, created_at);

CREATE TABLE IF NOT EXISTS stem_separation_job_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES stem_separation_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_stem_separation_job_events_job
    ON stem_separation_job_events(job_id, created_at);
