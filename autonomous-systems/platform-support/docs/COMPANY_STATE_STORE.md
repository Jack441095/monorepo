# Company State Store

`nite_ai.company_store` — smallest local persistence for Thursday's company-AI
role. SQLite (stdlib), parameterised SQL, foreign keys ON.

## Schema
Versioned (`SCHEMA_VERSION = 1`, migration 1, atomic apply + rollback on
failure; newer-than-supported databases are refused). Tables: `goals`,
`projects`, `tasks`, `decisions`, `risks`, `agent_runs`. CSV-encoded id lists
for depends_on/blocked_by; timestamps as epoch floats.

## API (explicit, no ORM)
`open_store(path)` → (conn, CompanyStore). Operations: create_goal /
update_goal_status / list_goals · create_project / list_projects ·
create_task / update_task_status / list_tasks (priority DESC, due ASC) ·
record_decision / resolve_decision / list_open_decisions · record_risk /
retire_risk / list_active_risks · record_agent_run / recent_agent_runs.

## Safety
- Tests use temp isolated DBs only; no production DB is touched.
- Foreign keys enforced (orphan tasks rejected — tested).
- Reopening persists data (tested).
- Future schema versions refuse to open with older code (tested).
- No secrets, no audio, no conversation dumps.

## Location policy
The store path is always caller-supplied. Production default belongs to
Thursday's app-data directory (never source dirs, repo dirs, or caches).
