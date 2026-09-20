-- Content-addressed blobs and logical artifact lineage.

CREATE TABLE IF NOT EXISTS artifact_blobs (
    content_hash TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    storage_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    producer TEXT NOT NULL,
    producer_version TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    external_key TEXT UNIQUE,
    source_uri TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted')),
    created_at TEXT NOT NULL,
    FOREIGN KEY(content_hash) REFERENCES artifact_blobs(content_hash)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_project
    ON artifacts(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_hash
    ON artifacts(content_hash);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind
    ON artifacts(kind, created_at);

CREATE TABLE IF NOT EXISTS artifact_edges (
    artifact_id TEXT NOT NULL,
    parent_artifact_id TEXT NOT NULL,
    relationship TEXT NOT NULL DEFAULT 'derived_from',
    created_at TEXT NOT NULL,
    PRIMARY KEY (artifact_id, parent_artifact_id, relationship),
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
    FOREIGN KEY(parent_artifact_id) REFERENCES artifacts(id)
);

CREATE INDEX IF NOT EXISTS idx_artifact_edges_parent
    ON artifact_edges(parent_artifact_id);
