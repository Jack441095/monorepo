DROP INDEX IF EXISTS idx_mix_reviews_project;
ALTER TABLE mix_reviews DROP COLUMN project_id;
DROP INDEX IF EXISTS idx_song_projects_crm;
DROP TABLE IF EXISTS song_projects;
