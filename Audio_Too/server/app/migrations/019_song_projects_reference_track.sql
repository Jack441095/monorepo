-- D1.7 (docs/KENN_FUTURE_PLAN.md Phase 1): project continuity for the
-- reference track a song_project is being mixed against. Nullable and
-- optional -- most reviews still have no reference at all, and this only
-- ever gets set the first time a review for a given project explicitly
-- selects a saved reference (studio/audio_analysis/audio_analysis/mix_review/
-- review_workflow.py::save_review()), then auto-applied to every
-- subsequent review for that same project that doesn't specify one.
--
-- References mix_references(id), NOT a foreign key constraint enforced at
-- the SQLite level -- mix_references lives in the same physical database
-- but is created by mix_review_config.py's own CREATE_REVIEWS_SQL (run via
-- init_reviews_table()), not by this migrations system, so a FK here could
-- reference a table that doesn't exist yet on a fresh install depending on
-- init ordering (same ordering hazard migration 018 already documented and
-- worked around for mix_reviews.project_id).
ALTER TABLE song_projects ADD COLUMN reference_track_id TEXT;

CREATE INDEX IF NOT EXISTS idx_song_projects_reference_track
    ON song_projects(reference_track_id);
