DROP INDEX IF EXISTS idx_automix_jobs_correlation;
ALTER TABLE automix_jobs DROP COLUMN correlation_id;
