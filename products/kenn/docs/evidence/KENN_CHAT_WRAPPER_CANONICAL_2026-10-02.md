# One chat wrapper, one Dockerfile that does not need Audio_Too — 2 October 2026

A3 slice. It supports [KENN_PLAN.md](../../KENN_PLAN.md) and closes the wrapper and container-path findings left
open in [the LaunchAgent receipt](KENN_LAUNCHAGENT_AND_DOC_POINTERS_2026-10-02.md). Jack chose to use the copy
in `products/kenn` rather than rebuild on Audio_Too.

## What changed

- `products/kenn/chat` (13 tracked files) is removed. `packages/chat` is the wrapper: `start_server.sh`,
  `run_tests_on_box.py`, `qualify_internal_beta.py`, the eval scripts and three backend tests already pointed at
  it, and nothing live pointed at `chat/` (a repo-wide `git grep` for the old paths found only dated docs).
  `chat/` held two tests that `packages/chat` lacked, `test_build_runtime_index.py` and
  `test_import_isolation.py`. Both moved to `packages/chat/tests` with their paths fixed (the default-engine
  assertion used `SERVICE_ROOT.parent`, right for `chat/` and wrong one level down; the isolation test no longer
  runs over two wrappers).
- `packages/chat/Dockerfile` is rewritten. It copied `Audio_Too/studio/kenn`, whose `kenn/requirements.txt` does
  not exist because the symlink lands on `products/kenn`, and it copied the old `products/kenn/chat`. It now keeps
  the product layout under `/app/products/kenn` so the wrapper's own default engine path (`../../apps/backend/src`)
  and its requirements include (`../../apps/backend/requirements.txt`) both resolve. `KENN_ENGINE_ROOT` is no
  longer set.
- New `packages/chat/Dockerfile.dockerignore`. The repo-root `.dockerignore` drops `products/` for the backend
  image, so no image could have been built from `products/kenn` at all. The per-Dockerfile file allows only the
  backend requirements, backend source and wrapper, and leaves out `artifacts/models/*` except `minilm` (8 GB of
  fine-tuned weights down to 87 MB), `chats/` (saved user chats and the memory database), the backend tests and the
  wrapper's `.runtime`. The root `.dockerignore` is untouched.
- Stale Audio_Too wording is gone from `packages/chat/app.py`, `.env.example`, `index_runtime.py` and the README
  ("Run the service from `packages/chat/`").

## Verification

- `packages/chat`: `../../apps/backend/.venv/bin/python -m pytest -q -p no:randomly tests`, 83 passed and 2 failed.
  The two failures are the known `test_full_evaluation_receipt_passes` and `test_full_chat_coverage_receipt_passes`
  (see [the echo receipt](KENN_EVAL_ROWS_RELATED_QUESTION_ECHO_2026-10-02.md)). The two moved test files pass,
  11 cases.
- Backend: 3,544 passed, 12 skipped, unchanged (129.57 s).

## Limits

- The image was not built. There is no Docker on this Mac, so the Dockerfile and its ignore file are untested.
  The pip include path and the allowlist-with-exceptions ignore pattern are the two things most worth watching on
  the first real build.
- The index build needs `Training_Data_Notes`, `Training_Data_Sources`, `Training_Data_PDF` and the MiniLM model,
  all git-ignored data. The image therefore builds only from a checkout that has them on disk, never from a clean
  git clone, and no CI or Railway config builds it. The build script was not run against the real notes (the plan
  says not to rebuild the index on this Mac).
- `chat/` still holds git-ignored leftovers on disk (`.runtime/kenn.db`, caches). They were left in place.
- Dated docs (`CHANGELOG.md`, `KNOWN_ISSUES.md`, `ABLETON_ASSISTANT_CURRENT_STATE.md`) still say `chat/app.py`;
  they are records and were not rewritten.

## Exact changed files

Paths are relative to `products/kenn`.

- Removed: the 11 remaining tracked files under `chat/` (two tests moved).
- Moved: `chat/tests/test_build_runtime_index.py`, `chat/tests/test_import_isolation.py` to `packages/chat/tests/`.
- `packages/chat/Dockerfile`, `packages/chat/Dockerfile.dockerignore` (new), `app.py`, `.env.example`,
  `index_runtime.py`, `README.md`.
- `docs/evidence/KENN_CHAT_WRAPPER_CANONICAL_2026-10-02.md` and `KENN_PLAN.md`.
