-- Durable AudioGen render queue with leases, recovery, and immutable events.

CREATE TABLE IF NOT EXISTS audiogen_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL DEFAULT 'full_song',
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    emotion TEXT NOT NULL,
    bars INTEGER NOT NULL,
    candidate_count INTEGER NOT NULL,
    publish INTEGER NOT NULL DEFAULT 1,
    project_id TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    error TEXT NOT NULL DEFAULT '',
    cancellation_requested INTEGER NOT NULL DEFAULT 0,
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

CREATE INDEX IF NOT EXISTS idx_audiogen_jobs_queue
    ON audiogen_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_audiogen_jobs_lease
    ON audiogen_jobs(status, lease_expiry_at);
CREATE INDEX IF NOT EXISTS idx_audiogen_jobs_project
    ON audiogen_jobs(project_id, created_at);

CREATE TABLE IF NOT EXISTS audiogen_job_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES audiogen_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audiogen_job_events_job
    ON audiogen_job_events(job_id, created_at);
