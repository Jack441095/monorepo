# SLO File and Data Safety Audit V1

## Positive controls

- Default cache is under `~/Library/SmartSampleManager`; legacy migration is explicit.
- `SSM_CACHE_DB_DIR` and test overrides support isolation.
- Corrupt databases are detected, quarantined, rebuilt, and user state is salvaged/restored.
- Production-cache guard tests passed in the existing tree and production DB size/mtime were unchanged.
- Destination path components are sanitized; the path-traversal regression exists.
- Duplicate reporting does not automatically delete files.
- Automatic plugin installation is opt-in and defaults OFF.

## Material risk

Sort Library is move/rename by default after user confirmation. A failed or interrupted move, an unexpected category, or a user misunderstanding can change the user’s library. This is a destructive surface even though the UI asks for confirmation.

## Beta policy

Default beta mode should be read-only classification and review. If sorting is enabled, require explicit per-operation confirmation, show source/destination mappings, provide a reversible journal/undo or export, and never delete automatically. Audit owner/customer audio was not accessed or modified.
