# C3 history boundaries, 3 October 2026

Implementation commit: `16bf7279fa4f4ffeee791580b7d2a790d53ee9c2`.

This closes the three deterministic routing gaps named in handoff step 2. C3 remains open: these tests do not qualify model answers, five-turn UI delivery or the Live-open 15-second gate. C1 and C2 also remain unticked.

## Files and behavior

- `apps/backend/src/kenn/core/chat_answer.py`: "Cancel that, I will do it myself." and bounded variants use the existing cancellation path before retrieval. Pending confirmations are revoked only within the bound session. Delivery is marked discarded; this does not abort running inference or undo a completed action.
- `apps/backend/src/kenn/core/chat_routing.py`: clarification can name the earlier request instead of reopening the generic intake menu. "What would you try first?" retains the snare and its subsequent volume constraint. Explicit returns to a topic select a matching earlier turn; standalone export and streaming-loudness questions drop unrelated drum-reverb context. Elliptical parameter questions and session-only context retain history.
- `apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py`: adds the natural cancellation phrase to the session-isolation test.
- `apps/backend/src/kenn/tests/test_history_boundaries.py`: named regressions cover both stream and payload boundaries, constraint retention, topic changes, return to an earlier topic, session-only context and cancellation questions that are not withdrawals. No-history clarification still asks for a subject.

Grounding thresholds, model prompts, production output limits and Live permissions are unchanged. The missing-analysis guard remains in force; clarification does not invent an analysis result.

## Verification

Commands ran sequentially from `products/kenn`, with Fake Live and fresh pytest cache directories. No index rebuild or model run was needed.

Initial regression command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py -o cache_dir=/private/tmp/kenn-pcache-history-boundaries-red-20261003
```

Result before the routing fix: **11 failed, 2 passed**. Subsequent boundary tests were added while checking parameter and session-context behavior.

Final scoped command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q -p no:randomly apps/backend/src/kenn/tests/test_history_boundaries.py apps/backend/src/kenn/tests/test_correction_followups.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_missing_analysis_guard.py -o cache_dir=/private/tmp/kenn-pcache-history-boundaries-final2-20261003
```

Result: **94 passed, 2 warnings in 1.84 seconds**, exit 0.

Final full-suite command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-pcache-history-boundaries-suite-final-20261003
```

Result: **3605 passed, 12 skipped, 1 failed, 7 warnings in 103.59 seconds**, exit 1. The sole failure is pre-existing: `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host` finds a machine-specific checkout path in `docs/evidence/KENN_CODEX_HANDOFF_2026-10-03.md`. That handoff is unchanged. The known ordering-dependent `test_server_smoke.py::test_main_chat_can_combine_explicit_mix_review_and_plugin_evidence` passed.

An earlier full run, using `/private/tmp/kenn-pcache-history-boundaries-suite-20261003`, reported **3604 passed, 12 skipped, 1 failed in 93.21 seconds**, then aborted during teardown with `recursive_mutex lock failed: Invalid argument` (exit 134). The final run includes one additional session-context regression and exited normally. The native teardown failure has no established cause; the rerun does not diagnose it.

## Limits

The new chat-surface tests disable the model and isolate retrieval with an empty corpus and a search spy; agent dispatch is stubbed. Existing correction tests separately exercise the actual classifier boundary. These are routing examples, not real-model usefulness or timing results.

Topic selection uses existing topic tags and bounded wording. It does not establish arbitrary dialogue understanding, cross-project isolation, two-track choice quality, failed-job handling or UI qualification. No new five-turn real-model conversation run was performed. Real Live memory pressure and audio dropouts remain for Jack's scheduled soak. No plan tick is earned.
