-- Recreate mix_references without added columns
PRAGMA foreign_keys=OFF;

CREATE TABLE IF NOT EXISTS mix_references_old (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    style TEXT,
    original_name TEXT,
    stored_name TEXT,
    metrics_json TEXT,
    size_bytes INTEGER,
    created_at TEXT
);
INSERT OR IGNORE INTO mix_references_old (id, name, style, original_name, stored_name, metrics_json, size_bytes, created_at)
SELECT id, name, style, original_name, stored_name, metrics_json, size_bytes, created_at FROM mix_references;
DROP TABLE IF EXISTS mix_references;
ALTER TABLE mix_references_old RENAME TO mix_references;

PRAGMA foreign_keys=ON;
