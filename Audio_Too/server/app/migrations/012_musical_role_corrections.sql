CREATE TABLE IF NOT EXISTS automix_musical_role_corrections (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    source_plan_revision TEXT NOT NULL,
    stem_name TEXT NOT NULL,
    inferred_role TEXT NOT NULL,
    inferred_priority TEXT NOT NULL,
    inferred_confidence REAL NOT NULL CHECK (inferred_confidence BETWEEN 0.0 AND 1.0),
    inferred_ambiguous INTEGER NOT NULL CHECK (inferred_ambiguous IN (0, 1)),
    corrected_role TEXT NOT NULL,
    corrected_priority TEXT NOT NULL,
    correction_hash TEXT NOT NULL,
    actor_id TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_id, stem_name)
);

CREATE INDEX IF NOT EXISTS idx_automix_role_corrections_project
    ON automix_musical_role_corrections(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_automix_role_corrections_revision
    ON automix_musical_role_corrections(source_plan_revision);
