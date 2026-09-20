-- Add optimistic locking version columns and worker fields for Automix jobs

-- Add optimistic_version to CRM tables
ALTER TABLE enquiries ADD COLUMN optimistic_version INTEGER DEFAULT 1;
ALTER TABLE projects ADD COLUMN optimistic_version INTEGER DEFAULT 1;
ALTER TABLE clients ADD COLUMN optimistic_version INTEGER DEFAULT 1;
ALTER TABLE leads ADD COLUMN optimistic_version INTEGER DEFAULT 1;
ALTER TABLE invoices ADD COLUMN optimistic_version INTEGER DEFAULT 1;
ALTER TABLE drafts ADD COLUMN optimistic_version INTEGER DEFAULT 1;

-- Add worker columns to automix_jobs
ALTER TABLE automix_jobs ADD COLUMN worker_id TEXT;
ALTER TABLE automix_jobs ADD COLUMN claimed_at TEXT;
ALTER TABLE automix_jobs ADD COLUMN heartbeat_at TEXT;
ALTER TABLE automix_jobs ADD COLUMN lease_expiry_at TEXT;
ALTER TABLE automix_jobs ADD COLUMN progress INTEGER DEFAULT 0;
ALTER TABLE automix_jobs ADD COLUMN cancellation_requested INTEGER DEFAULT 0;
