# Thursday Runtime State

Thursday stores mutable user state outside the source checkout. This prevents
ordinary requests, feedback, profile learning, alerts, and SQLite WAL files
from dirtying Git or entering a release archive.

## Default locations

| Platform | State root |
| --- | --- |
| macOS | `~/Library/Application Support/Audio_Too/thursday/` |
| Linux | `${XDG_STATE_HOME:-~/.local/state}/audio-too/thursday/` |
| Windows | `%LOCALAPPDATA%\Audio_Too\thursday\` |

The tree contains `user_data/`, `profiles/`, `analytics/`, `sessions/`,
`alerts/`, `calendar_data/`, `logs/`, the active-session pointer, and the
daily-briefing stamp.

## Migration behavior

On normal CLI or Thursday server startup, legacy state under the repository's
`thursday/` directory is copied into the external state root. Migration:

- never deletes the legacy source;
- never overwrites an existing destination file;
- skips symbolic links;
- is safe to repeat.

After verifying the external copy and taking a backup, legacy files may be
removed manually. The application does not automatically delete user data.

## Overrides

Set `THURSDAY_STATE_DIR` to relocate the complete Thursday tree:

```bash
export THURSDAY_STATE_DIR="/secure/path/thursday"
```

`AUDIO_TOO_STATE_DIR` provides a shared Audio_Too parent; Thursday uses its
`thursday/` child. Existing subsystem overrides remain supported:

- `THURSDAY_DATA_DIR`
- `THURSDAY_PROFILE_DIR`
- `THURSDAY_ANALYTICS_DIR`
- `THURSDAY_SESSION_DIR` and `THURSDAY_SESSION_FILE`
- `THURSDAY_ALERTS_DIR`
- `THURSDAY_CALENDAR_DIR`
- `THURSDAY_LOG_DIR`
- `THURSDAY_ACTION_RECEIPTS_DB`
- `THURSDAY_PLAN_MEMORY_DB` and `THURSDAY_PLAN_MEMORY_ARCHIVE`

Subsystem overrides take precedence over the state root for that subsystem.

## Backup and restore

Stop Thursday before copying state so SQLite databases and WAL files remain
consistent. Back up the entire state root, including hidden files. Restore it
to the same location before starting Thursday, or point `THURSDAY_STATE_DIR`
at the restored tree.

Do not merge SQLite files from two live installations. Restore one coherent
snapshot instead.

## Uninstall and reset

Removing the application code does not remove this state. To uninstall while
preserving data, archive the state root and then remove the code. To perform a
full reset, stop every Thursday process and delete or rename the state root.
Thursday creates a fresh tree on its next start.

The repository's `thursday/profiles/benchmark.json` is a static test fixture,
not runtime user state.

## Setup precondition: `nite_ai`

`thursday/company_state.py` lazily imports `nite_ai` (the
`autonomous-systems/platform-support` submodule's package) for company-state
snapshots, the daily brief, and company Q&A. Without it installed,
`tests/thursday/test_thursday_company_state.py`,
`test_thursday_company_qa.py`, `test_thursday_daily_brief.py`, and the
morning-brief benchmark fail with `CompanyStateUnavailable` /
`ModuleNotFoundError: No module named 'nite_ai'` (48 of 819 tests, verified
2026-09-02). Before running Thursday's tests or server:

```bash
pip install -e autonomous-systems/platform-support
```

**Install it into whichever interpreter actually runs Thursday.** `./audio-too`
prefers `Audio_Too/.venv/bin/python` over system Python when a `.venv`
exists — installing `nite_ai` only into system Python leaves the live CLI
(and any server process launched the same way) silently degraded: company
state renders `_unavailable_` and the daily brief logs
`CompanyStateUnavailable` instead of erroring loudly. Verified 2026-09-02
by running `./audio-too thursday "pipeline summary"` live: it degraded
silently until `nite_ai` was also installed into `.venv`. If both a
system-Python and a `.venv` interpreter are in play, install into both.
