# Recipe dispatch ownership, 3 October 2026

Code commit: `8c0d7ac2` on `fix/review-critical-2026-10-02`; baseline `06d4772e`.

Rack, MIDI and surgical masking dispatch now require a nonempty string owner,
strip surrounding whitespace and reject owners longer than 128 characters.
Validation happens before reading the Live snapshot or telemetry and before
preparing a proposal. These routes previously invented shared owners or coerced
invalid values. Rack catalogue requests remain available without a session owner.

Exact runtime/test files:

- `apps/backend/src/kenn/orchestrator.py`
- `apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py`

## Verification receipt

Commands ran from `products/kenn` on 3 October 2026 with fake Live and fresh caches.
The public-dispatch regression first failed on the original implementation:
**24 failed, 19 passed in 0.53 s**. The seven invalid-owner forms reached proposal
work in all three routes; padded owners were not normalized. Since each failure
traced directly to an explicit fallback assignment, no broader hypothesis search
or temporary instrumentation was needed.

Red command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py -o cache_dir=/private/tmp/kenn-recipe-owners-red-20261003-01
```

Scoped final command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py apps/backend/src/kenn/tests/test_orchestrator_autonomous.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py apps/backend/src/kenn/tests/test_rack_builder.py apps/backend/src/kenn/tests/test_rack_builder_pro.py apps/backend/src/kenn/tests/test_generative_midi.py apps/backend/src/kenn/tests/test_masking_doctor_closed_loop.py apps/backend/src/kenn/tests/test_session_doctor.py apps/backend/src/kenn/tests/test_midi_generation_chat.py -o cache_dir=/private/tmp/kenn-recipe-owners-green-20261003-01
```

Result: **134 passed, 2 existing deprecation warnings in 2.00 s**. Invalid-owner
tests use proposal call traps and snapshot/telemetry recorders. Valid-owner tests
exercise the actual deterministic recipe generators on a fake snapshot, including
distinct tokens for two chats, whitespace normalization and the 128-character
boundary. None of the dispatch tests modifies fake Live state. Anonymous catalogue
dispatch reads no Live snapshot and produces no confirmation token.

Full backend command, with output retained outside git:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-recipe-owners-full-20261003-01 > /private/tmp/kenn-recipe-owners-full-20261003-01.log 2>&1
```

Result: **4133 passed, 12 skipped, 5 warnings, 1 pre-existing failure in 86.57 s**.
The failure remains
`test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`.
Its detailed trace is not copied here. The scoped warnings concern Starlette/httpx
and AnyIO's `BlockingPortal` alias; no dependencies changed.

## Limits and next step

This closes three recipe dispatch owner fallbacks, not the full A2/A3 audit.
Distinct generated tokens do not establish registration, cancellation or execution
qualification. Next inspect KENN's autonomous `react_` token issuance with isolated
fixtures. Thursday is a separate product and remains excluded from this work queue.

No real model, GPU job, real Live interaction, index rebuild, grounding or answer-style
change occurred. This is not a latency result. The deep-research shortlist remains
advice for measured experiments on the target Mac. The Live-open useful-answer
15 s gate is still failed; C1, C2 and C3 remain unticked. No new checkbox is ticked.
