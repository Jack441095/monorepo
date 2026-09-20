-- Persists podcast-check reports so they can be revisited/shared via a
-- signed-token link, the same "like Mix Doctor" treatment plan.md's own
-- NEXT section calls for. Unlike mix_reviews, analysis here is synchronous
-- (no background thread), so the full computed report is stored in one
-- insert -- no "pending" status/report_name-on-disk indirection needed.
CREATE TABLE IF NOT EXISTS podcast_reports (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL,
    score INTEGER,
    report_json TEXT NOT NULL,
    html_report TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_podcast_reports_created_at ON podcast_reports(created_at);
