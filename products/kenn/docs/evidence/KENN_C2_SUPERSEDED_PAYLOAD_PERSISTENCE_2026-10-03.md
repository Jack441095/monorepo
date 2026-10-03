# C2 superseded payload persistence receipt — 3 October 2026

Code commit: `249db324` on `fix/review-critical-2026-10-02`.

The foreground payload path could persist a completed answer after its chat had cancelled or moved to another turn. It now uses the same request owner as the HTTP foreground/background path, checks each knowledge-answer save under the existing ownership lock, and discards stale text before delivery. Read-only/background calls preserve the foreground owner. Anonymous requests remain unbound. Padded or overlong session IDs remain unbound too: normalizing them would grant access to another session's pending confirmation.

## Exact files and behavior

- `apps/backend/src/kenn/core/chat_answer.py`: thread the request owner through payload generation; guard knowledge session memory, citation counts, reasoning traces and semantic-cache saves/turn records; discard superseded payloads. Critique and generation stay outside the ownership lock.
- `apps/backend/src/kenn/server.py`: pass the HTTP owner to foreground/background payload calls; guard feedback and checkpoint saves; recheck delivery after augmentation.
- `apps/backend/src/kenn/core/response_contract.py`: encode an empty cancelled answer as a cancelled result envelope rather than constructing a text-required assistant response.
- `apps/backend/src/kenn/tests/test_stream_request_delivery.py`: template/model cancellation, replacement and other-chat persistence cases, plus HTTP discard/checkpoint/feedback checks.
- `apps/backend/src/kenn/tests/test_semantic_cache_turn_record.py`: a cancelled/replaced cache hit cannot record a new turn; another chat retains its own cache-hit behavior.
- `apps/backend/src/kenn/tests/test_answer_upgrade_context.py`: HTTP/background owner reuse, read-only isolation and anonymous requests.

## Commands and results

All pytest commands ran from `products/kenn`, serially, with existing dependencies, Fake Live and fresh cache directories. Providers and retrieval use fixtures; there was no real-model run.

Qualifying regression before the fix: **6 failed, 59 deselected in 0.61 s**, exit 1. Earlier fixture setup attempts were corrected before this run.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py -k superseded_payload -o cache_dir=/private/tmp/kenn-payload-owner-red3-20261003
```

Final scoped verification: **149 passed, 2 warnings in 4.17 s**, exit 0.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_stream_request_delivery.py apps/backend/src/kenn/tests/test_semantic_cache_turn_record.py apps/backend/src/kenn/tests/test_answer_upgrade_context.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py -o cache_dir=/private/tmp/kenn-payload-owner-scoped-final-20261003
```

The first full run exposed two new padded-session binding regressions (3695 passed, 12 skipped, 3 failed). The binding was corrected and the scoped/full checks rerun. Final full backend verification: **3697 passed, 12 skipped, 1 failed, 7 warnings in 91.76 s**, exit 1.

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH="apps/backend/src:tooling" apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-payload-owner-full-final-20261003 > /private/tmp/kenn-payload-owner-full-final-20261003.log 2>&1
```

The remaining failure is pre-existing: `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`. Its legacy findings are not reproduced here. The previously ordering-sensitive server smoke test passed. Scoped `git diff --check` passed.

## Limits and research

This is a persistence/delivery correction, not a speed measurement or inference abort. Each save checks ownership independently; a save already holding the lock completes before cancellation obtains it. Knowledge-answer persistence is covered; action/fast-path side effects and the provider response cache remain outside this regression. Cancellation during HTTP delivery cannot retract bytes already sent.

The [speed shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) remains a list of hardware-specific experiment leads. Local phase measurements still identify decode and answer length as the main latency costs. Cap/style trials remain disabled for Jack's decision; residency and thinking-off settings are unchanged. No grounding change, model prose, private audio, dependency, model download, runtime switch or index rebuild is included. Real Live memory pressure and audio dropouts remain open for an owner-scheduled soak. **C1, C2 and C3 remain unticked.**
