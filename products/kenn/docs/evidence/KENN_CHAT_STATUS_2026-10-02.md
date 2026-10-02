# Observed chat status — 2 October 2026

This records the nonstream chat-status slice of A4 in
[KENN_PLAN.md](../../KENN_PLAN.md). It does not qualify provider health or an
Ableton connection.

## Reproduced behavior

The public `answer_payload` status shortcut always claimed operational Apple
Silicon MLX and an OSC bridge on ports 11000/11001. That text was independent of
the selected provider, model enablement, loaded weights or an observed reply
from Live.

## Changed behavior

The shortcut reports the configured provider/model and whether rewriting is
enabled. A selected MLX path describes runtime availability and an already-loaded
model, including a mismatch with its configured model. It does not construct the
engine, load weights or run inference. Configured provider fallback remains
distinct from observed residency or health.

For the currently bound OSC backend, status reads the cached state and age of the
last successful heartbeat. It explicitly leaves current health unchecked. The
MCP backend reports only its cached properties because its getter would start a
provider request. A fake backend is identified as a test fixture; other or
unavailable observations are described without an operational claim.

## Verification

Twenty-one new cases exercise the actual public nonstream shortcut, including
five aliases, provider enablement/key/model boundaries, selected and unselected
MLX residency, recent and stale OSC replies, cached MCP state and fake/unavailable
backends. Forbidden model and Live operations are instrumented to fail the test.

The scoped command below passed 51 cases in 3.42 s. A temporary compiled copy
restoring the unconditional status reply failed the public-alias regression.
These checks precede the combined streaming/cancellation/index verification;
the streaming binding was separately found to skip the shortcut and remains a
separate repair at this point.

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_chat_status_observations.py kenn/tests/test_llm_public_status.py kenn/tests/test_confirmation_gate_status.py kenn/tests/test_knowledge_request_context.py
```

## Exact changed files

Paths are relative to `products/kenn`.

- `apps/backend/src/kenn/core/chat_answer.py`: status branch of
  `_short_circuit_evaluator` only.
- `apps/backend/src/kenn/tests/test_chat_status_observations.py`: observed-status
  and forbidden-I/O regressions.
- `docs/evidence/KENN_CHAT_STATUS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: checks only the nonstream observed-status slice.
