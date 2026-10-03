# Correction dispatch receipt, 3 October 2026

The commit containing this receipt (parent `b2d9d799`) skips the history-free orchestrator for correction queries on
both chat surfaces. The existing history-aware router now receives the acoustic-guitar correction. Files changed:
`core/chat_answer.py`, `tests/test_correction_followups.py`, this receipt and `KENN_PLAN.md`.

From `products/kenn`, all commands used `KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling"` and
`apps/backend/.venv/bin/python -m pytest -q -p no:randomly`:

- `apps/backend/src/kenn/tests/test_correction_followups.py -o cache_dir=/private/tmp/kenn-pcache-correction-red-20261003`:
  2 failed, 10 passed before the fix; both surfaces returned `ableton_controller`.
- Same file with fresh `cache_dir=/private/tmp/kenn-pcache-correction-green-20261003`: 12 passed.
- Same file with `-k correcting_the_muddy_instrument` and fresh
  `cache_dir=/private/tmp/kenn-pcache-correction-mutation-20261003`: removing both guards reproduced 2 failures;
  the guards were restored.
- `apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-pcache-correction-suite-20261003`:
  3,575 passed, 12 skipped, 1 failed in 104.54 s. The pre-existing personal-path gate rejects the handoff note's
  machine-specific checkout path. That note was not changed. The previously reported smoke failure did not recur.

Limits: offline routing regression only, no model quality or latency result, no real Live writes. Cancel, clarification,
topic changes, UI delivery and project switching remain unqualified. C1, C2 and C3 remain unchecked.
