# Dead code removed from Audio_Too — 2 October 2026

A3 slice, done at Jack's request. It supports [KENN_PLAN.md](../../KENN_PLAN.md). Audio_Too is the frozen legacy
tree, so only code with no caller anywhere in the monorepo was removed, and everything doubtful was left in place
and is listed below.

## Removed

17 tracked files (2,020 lines), commit "Delete 17 Audio_Too scripts and one agent module that nothing references":

- `scripts/eval/`: `apply_body_boost_diagnostic`, `apply_combined_reference_match_diagnostic`,
  `apply_low_shelf_diagnostic`, `apply_low_shelf_generalize`, `apply_low_shelf_v2_diagnostic`,
  `apply_reference_eq_diagnostic`, `automix_render_cprofile`, `kenn_diagnostic_eval`, `kenn_model_blind_eval`,
  `kenn_thursday_conversation_audit`, `native_kernel_bench`, `resonance_calibration`.
- `scripts/`: `generate_training_from_notes`, `paraphrase_notes`, `kenn_chromium_smoke_test`, `pdf_simple`.
- `server/agents/Shared/agent_lora.py`.

Evidence per file: a whole-word `git grep` over the entire monorepo (not just Audio_Too) for the module name finds
no other file, docs and CI included. A second grep for name prefixes and for dynamic loading (`import_module`,
`__import__`, `pkgutil`, directory globs over `scripts/`) found nothing that could reach them. Two of the agent's
candidates failed that second check and were kept (below).

`main.py`: `cmd_package` and its two dispatch entries (`package`, `release-package`) and usage lines are removed.
It ran `scripts/build_release_package.py`, which does not exist in the tree (it appears only in an archived plan), so
the command could only fail.

## Verification

- `pytest --collect-only -q tests` from `Audio_Too` with the KENN backend venv: 2,673 collected and 214 collection
  errors both before and after, with the same list of erroring files. The errors come from this venv lacking
  Audio_Too's dependencies and from the missing `studio/kenn/kenn` path, not from this change.
- `tests/test_main_cli.py`, `test_main_cmd_stop_worker.py`, `test_main_status_health.py`, `test_audio_too_wrapper.py`:
  44 passed and 11 failed with the `main.py` edit and the same 44 and 11 without it (the wrapper tests need an
  Audio_Too Python environment).
- No test or script enumerates `scripts/` by directory.

## Second pass: eight single functions

Each name appeared once in the monorepo (its own definition) before removal, and again nowhere afterwards,
including tests and strings. Two more became caller-less once their only caller went.

- `server/agents/Shared/agent_llm.py`: `generate_llm_simple`, then `_ollama_generate` (its only caller).
- `server/app/automix_worker.py`: `stop_automix_worker`.
- `server/agents/Shared/data_store.py`: `save_records`, `export_xlsx`.
- `server/app/db.py`: `replace_records` (only `save_records` called it).
- `server/agents/Shared/reports.py`: `str_date`.
- `scripts/serve.py`: `start_ableton_web`.

Kept from the earlier candidate list: `process_podcast_repair`, `validate_rating`, `cohens_kappa_binary`
(benchmark and podcast routes exist) and `write_text_pdf` (its file went in the first pass).
`export_multi_sheet_xlsx` and `upsert_record` still have callers.

Checked from `Audio_Too` with the KENN backend venv, which lacks Audio_Too's own dependencies:

- All six files parse; `grep` for the eight names over tracked files is empty.
- `pytest --collect-only -q tests`: 2,864 collected, 188 errors, same as before.
- The 19 test files that import these modules: 35 passed, 11 failed, 11 collection errors, with and without
  the change (the failures and errors are missing dependencies).

## Left in place on purpose

- `server/services/knowledge_flywheel_agent.py`: `thursday/scheduler.py` names `KnowledgeFlywheelAgent` and its
  `run_knowledge_flywheel` method in a weekly task, and the Audio_Too scheduler reports "not yet implemented"
  for it. It is unfinished, not dead.
- `server/services/podcast_repair_api.py`: unreferenced, but `010_scheduled_tasks_and_jobs.sql` creates a
  `podcast_repair_jobs` table for it. A half-built feature, so it is Jack's call.
- `scripts/listening_benchmark_{assignment,loudness_match,replay,scorecard}.py`: no importer, but
  `reference_track_comparison.py` tells users to use them and the benchmark routes, page and migration exist.
- Likely-dead single functions found by the same search (name appears once in the repo; `getattr` dispatch not
  ruled out): `process_podcast_repair`, `validate_rating`, `cohens_kappa_binary`, `generate_llm_simple`,
  `start_ableton_web`, `write_text_pdf`, `stop_automix_worker`, `save_records`, `export_xlsx`, `str_date`.
- Broken, not dead (the `studio/kenn` symlink lands on `products/kenn`, so `studio/kenn/kenn` is missing):
  `main.py` `cmd_ableton`, `cmd_lint`, `cmd_export_training`, `server/app/ableton_bridge.py` and about 45 tests and
  25 scripts. These need repointing, and the target is a decision: the importable package is
  `products/kenn/apps/backend/src/kenn`.
- `audio-too-ci.yml` lines 139-141 deselect two test files that do not exist; Jack approved removing them on 2 October; the three `tests/kenn/...` deselects are gone from the workflow (`tests/kenn` holds only `__pycache__`), and the YAML still parses. The workflow itself was not run. The Makefile `lint` target listed a `business/` directory that does not exist; that entry is removed (`ruff` was not run, the directory was simply absent).
- `scripts/kenn_demo_doctor.py` checks four files that no longer exist.
- `Audio_Too/thursday` is a declared duplicate (`DEPRECATED_THURSDAY.txt`, canonical copy under
  `autonomous-systems/thursday`) but live server code, CI and about 115 test files import it, so removing it is a
  migration. It also holds the uncommitted `redaction.py` edits that are not mine.

## Limits

- Orphan status is by text search. A caller that builds a script path from pieces at run time would not show up;
  none was found, but absence of evidence is all there is.
- The Audio_Too suite does not run cleanly in any environment I have here, so this is checked by collection parity
  rather than by a green run.

## Exact changed files

Paths are relative to the monorepo root.

- Deleted: the 17 files above, under `Audio_Too/`.
- `Audio_Too/main.py`: `cmd_package`, its two dispatch entries and its usage lines.
- The six files in the second pass above.
- `products/kenn/docs/evidence/KENN_AUDIO_TOO_DEAD_CODE_2026-10-02.md` and `products/kenn/KENN_PLAN.md`.
