-- D2.2 (docs/KENN_FUTURE_PLAN.md Phase 2): "Mix Memory" storage half --
-- remembers the revision requests a producer has made against a
-- song_project, so KENN can later answer "what did I ask for last time?"
-- across restarts. Deliberately just the request text + timestamp, not a
-- structured diff of what changed -- the structured "applied changes" list
-- already exists per-request (mix_decision_engine.apply_revision_feedback's
-- return value) but is transient, never persisted; wiring that through is
-- separate follow-up work, not needed for basic history recall.
--
-- No foreign key constraint on project_id, same reasoning as migration 019:
-- song_projects and this table are not guaranteed to be created in a fixed
-- order on a fresh install.
CREATE TABLE IF NOT EXISTS project_revision_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    feedback_text TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_revision_history_project
    ON project_revision_history(project_id, created_at);
