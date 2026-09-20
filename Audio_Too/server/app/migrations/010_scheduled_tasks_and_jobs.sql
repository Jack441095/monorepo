-- Migration 010: Scheduled Tasks and Podcast Repair Jobs
-- Run this to enable agent automation infrastructure

-- Scheduled task logging for audit trail
CREATE TABLE IF NOT EXISTS scheduled_task_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    agent TEXT NOT NULL,
    method TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    result_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_scheduled_task_name ON scheduled_task_log(task_name);
CREATE INDEX IF NOT EXISTS idx_scheduled_task_ran_at ON scheduled_task_log(ran_at);

-- Podcast repair service jobs
CREATE TABLE IF NOT EXISTS podcast_repair_jobs (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    tier TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    estimated_seconds INTEGER,
    callback_url TEXT,
    output_path TEXT,
    metrics TEXT
);

CREATE INDEX IF NOT EXISTS idx_podcast_job_status ON podcast_repair_jobs(status);
CREATE INDEX IF NOT EXISTS idx_podcast_job_created ON podcast_repair_jobs(created_at);

-- Invoice follow-up triggers
CREATE TABLE IF NOT EXISTS invoice_followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    result TEXT
);

CREATE INDEX IF NOT EXISTS idx_followup_invoice ON invoice_followups(invoice_id);
CREATE INDEX IF NOT EXISTS idx_followup_status ON invoice_followups(status);

-- Lead scoring and engagement tracking
CREATE TABLE IF NOT EXISTS lead_scores (
    lead_id TEXT PRIMARY KEY,
    score INTEGER DEFAULT 0,
    last_scored TEXT NOT NULL,
    nurturing_status TEXT DEFAULT 'not_contacted',
    last_contact TEXT,
    engagement_events TEXT
);

CREATE INDEX IF NOT EXISTS idx_lead_score ON lead_scores(score DESC);
CREATE INDEX IF NOT EXISTS idx_lead_nurturing ON lead_scores(nurturing_status);