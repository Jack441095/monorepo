# Local agent data

**Primary store:** `data/audio_too.db` (SQLite).

JSON files in this folder are **export snapshots only** — they are not updated on every change. To refresh them from the database:

```bash
./agent export-json
```

Backups also include a JSON snapshot under `agents/Shared/backups/.../agent_data/`.

On a fresh clone with no database, legacy JSON in this folder is imported once into SQLite on first `init_db()`. Empty templates are in `seed/`.

```bash
cp seed/*.json .
```

Back up regularly with `./agent backup` or the dashboard **Run backup** action.
