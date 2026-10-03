# Anonymous dispatch ownership, 3 October 2026

Code commit: `ce4f1eeb` on `fix/review-critical-2026-10-02`; baseline `0f4373f5`.

`orchestrator.py::_dispatch_ableton` and `_dispatch_autonomous_producer` no longer
invent shared owners for callers without session identity. Both require a nonempty
string, strip surrounding whitespace and reject owners longer than 128 characters,
matching the public chat boundary. Rejection happens before command preparation or
producer deliberation, so these requests create neither proposals nor Live conversation
state. Explicit owners remain distinct; anonymous read-only session inspection works.

Exact runtime/test files:

- `apps/backend/src/kenn/orchestrator.py`
- `apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py`

## Verification receipt

All commands ran from `products/kenn` on 3 October 2026 with fake Live and fresh caches.
The regression first failed on the original implementation: **10 failed, 4 passed
in 0.37 s**. Missing owners generated confirmations under the shared name; blank
owners recorded conversation state; producer requests began deliberation.

Scoped final command:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py apps/backend/src/kenn/tests/test_orchestrator_autonomous.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py -o cache_dir=/private/tmp/kenn-owner-scoped-final-20261003
```

Result: **77 passed, 2 existing deprecation warnings in 1.23 s**. The new tests cover
two rejected requests per invalid owner, existing named-chat state and pending-token
isolation, explicit producer ownership, and anonymous read-only inspection. Producer
deliberation is replaced with a call recorder for the rejection tests; the existing
named-owner test still exercises actual deterministic deliberation on a fake snapshot.

Full backend command, with output kept outside git:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests -o cache_dir=/private/tmp/kenn-owner-full-20261003 > /private/tmp/kenn-owner-full-20261003.log 2>&1
```

Result: **4105 passed, 12 skipped, 5 warnings, 1 pre-existing failure in 87.31 s**.
The failure remains
`test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`.
Its detailed trace is not copied into this receipt. Existing warnings concern the
Starlette/httpx integration and AnyIO alias; no dependencies changed.

Mutation check: temporarily restored both shared-owner fallback blocks and ran:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py -o cache_dir=/private/tmp/kenn-owner-mutation-20261003
```

Result: **10 failed, 5 passed in 0.14 s**. Both mutations were detected. The committed
source was restored byte-for-byte and checked with `git diff --exit-code`.

After restoring the source, the scoped command above was repeated with
`-o cache_dir=/private/tmp/kenn-owner-restored-20261003`: **77 passed, 2 existing
warnings in 1.53 s**.

## Limits

This closes the two anonymous dispatch fallbacks, not the whole A2/A3 audit.
Thursday's compatibility fallback, other specialist recipe owners and autonomous
`react_` token issuance still require their own fixtures and source traces. Named
producer proposals are not newly qualified for cancellation or execution by this fix.
No real model, GPU work, index rebuild, grounding or answer-style change occurred.
The Live-open useful-answer 15 s gate remains failed; C1, C2 and C3 stay unticked.
