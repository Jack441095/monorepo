DROP INDEX IF EXISTS idx_song_projects_reference_track;
ALTER TABLE song_projects DROP COLUMN reference_track_id;
