ALTER TABLE mix_references ADD COLUMN genre_key TEXT DEFAULT '';
ALTER TABLE mix_references ADD COLUMN genre_confidence REAL DEFAULT 0;
ALTER TABLE mix_references ADD COLUMN profile_json TEXT DEFAULT '[]';
ALTER TABLE mix_references ADD COLUMN crest_factor_db REAL;
ALTER TABLE mix_references ADD COLUMN integrated_lufs REAL;
ALTER TABLE mix_references ADD COLUMN loudness_range_lu REAL;
ALTER TABLE mix_references ADD COLUMN stereo_correlation REAL;
ALTER TABLE mix_references ADD COLUMN stereo_width_ratio REAL;

CREATE INDEX IF NOT EXISTS idx_mix_references_genre_key
ON mix_references(genre_key, created_at);
