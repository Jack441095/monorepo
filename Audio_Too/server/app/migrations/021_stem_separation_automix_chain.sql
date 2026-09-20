-- D3.3 (docs/KENN_FUTURE_PLAN.md Phase 3): optional stem-separation ->
-- AutoMix chaining, mirroring migration 014's audiogen_jobs columns --
-- a separation job can request its own completed stems be uploaded and
-- queued as an AutoMix job automatically once Demucs finishes.
ALTER TABLE stem_separation_jobs ADD COLUMN genre TEXT NOT NULL DEFAULT '';
ALTER TABLE stem_separation_jobs ADD COLUMN style_prefs TEXT NOT NULL DEFAULT '';
ALTER TABLE stem_separation_jobs ADD COLUMN chain_to_automix INTEGER NOT NULL DEFAULT 0;
ALTER TABLE stem_separation_jobs ADD COLUMN automix_job_id TEXT NOT NULL DEFAULT '';
