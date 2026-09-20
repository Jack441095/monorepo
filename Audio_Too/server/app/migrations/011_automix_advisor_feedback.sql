CREATE TABLE IF NOT EXISTS automix_advisor_feedback (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    shadow_artifact_id TEXT NOT NULL,
    source_plan_revision TEXT NOT NULL,
    operation_index INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected', 'needs_work')),
    usefulness_rating INTEGER NOT NULL CHECK (usefulness_rating BETWEEN 1 AND 5),
    explanation_quality_rating INTEGER NOT NULL CHECK (explanation_quality_rating BETWEEN 1 AND 5),
    audible_improvement_rating INTEGER CHECK (audible_improvement_rating BETWEEN 1 AND 5),
    preview_artifact_id TEXT,
    reason TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(shadow_artifact_id, operation_index)
);

CREATE INDEX IF NOT EXISTS idx_automix_advisor_feedback_job
    ON automix_advisor_feedback(job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_automix_advisor_feedback_decision
    ON automix_advisor_feedback(decision, created_at);
