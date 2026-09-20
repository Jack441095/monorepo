-- Optional AudioGen -> AutoMix chaining: a render job can request its
-- generated stems be uploaded and queued as an AutoMix job automatically.
ALTER TABLE audiogen_jobs ADD COLUMN genre TEXT NOT NULL DEFAULT '';
ALTER TABLE audiogen_jobs ADD COLUMN style_prefs TEXT NOT NULL DEFAULT '';
ALTER TABLE audiogen_jobs ADD COLUMN chain_to_automix INTEGER NOT NULL DEFAULT 0;
ALTER TABLE audiogen_jobs ADD COLUMN automix_job_id TEXT NOT NULL DEFAULT '';
