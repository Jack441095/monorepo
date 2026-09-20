ALTER TABLE automix_jobs ADD COLUMN correlation_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_automix_jobs_correlation
    ON automix_jobs(correlation_id);
