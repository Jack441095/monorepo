-- Shared song-lifecycle Project entity (Phase 2 of
-- docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md). Deliberately a SEPARATE
-- entity from `projects` (the existing CRM/client engagement table) rather
-- than forced into it: a CRM project is a business engagement that can span
-- many songs; a song_project is one song's technical lifecycle (stems, mix
-- review, AutoMix runs). crm_project_id links them when relevant but is
-- optional -- most KENN chat sessions today have no CRM project at all.
--
-- Reuses whatever project_id AutoMix/stem-separation/mix-review already
-- pass around (both the real CRM `projects.id` format and the synthetic
-- `kenn-<hex>` format automix_public.py already mints) rather than minting
-- yet another id space -- song_projects.id IS that same value, so existing
-- automix_jobs.project_id / stem_uploads.project_id / stem_separation_jobs.
-- project_id columns can join against it directly, no remap needed.

CREATE TABLE IF NOT EXISTS song_projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    crm_project_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(crm_project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_song_projects_crm
    ON song_projects(crm_project_id);

-- mix_reviews never had a project_id column at all (save_review()'s
-- project_id kwarg only ever reached the artifacts/domain_events side
-- tables) -- add it so a review can be looked up by/joined to its project
-- directly, matching automix_jobs/stem_separation_jobs.
--
-- mix_reviews itself is NOT created by this migrations system -- it's
-- created by studio/audio_analysis/audio_analysis/mix_review/mix_review_config.py's
-- CREATE_REVIEWS_SQL, run via mix_review.init_reviews_table(), which
-- business/app/server.py's main() calls AFTER init_db() (this migration
-- runner). On a fresh install the table would not exist yet here, so a bare
-- ALTER TABLE would crash startup. Recreating the exact pre-existing schema
-- (IF NOT EXISTS, so a no-op wherever the table already exists) before the
-- ALTER makes this migration safe in both orderings -- exactly one ADD
-- COLUMN either way, never a duplicate.
CREATE TABLE IF NOT EXISTS mix_reviews (
    id TEXT PRIMARY KEY,
    title TEXT,
    original_name TEXT,
    stored_name TEXT,
    report_name TEXT,
    size_bytes INTEGER,
    created_at TEXT,
    status TEXT DEFAULT 'completed',
    error TEXT
);

ALTER TABLE mix_reviews ADD COLUMN project_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_mix_reviews_project
    ON mix_reviews(project_id, created_at);
