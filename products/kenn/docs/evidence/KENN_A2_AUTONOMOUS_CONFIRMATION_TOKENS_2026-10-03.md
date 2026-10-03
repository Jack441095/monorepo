# Autonomous producer confirmation tokens, 3 October 2026

Code commit: `91bdb78` on `fix/review-critical-2026-10-02`; baseline `b00c262` (rebased onto `255c6cd`, a docs-only commit).

`react_deliberate` built its own `react_<hash>` token and a recipe-shaped dictionary.
The shared confirmation service never issued that token, so Apply could not consume
it and Dismiss (`revoke_confirmation`) returned false. Reproduced on fake Live before
the change: the demo dispatch returned seven steps (a recipe holds three), the owner
had **0** pending confirmations, and revoking the token returned **False**. The same
Kick fader step also appeared three times, which would have failed its own stale-value
check on the second pass.

## What changed

Files, relative to `products/kenn/apps/backend/src/kenn`:

- `autonomous_agent.py` — the proposal now comes from `LiveRecipeService.propose_recipe`,
  so the token is a signed `v1.` token bound to the exact typed child steps and the
  owner chat. New `_split_recipe_steps` picks what a recipe can carry and returns the
  rest with a reason each: an action a recipe does not support (insert device, EQ band,
  automation), a step with no exact Live target (the master Limiter ceiling step has
  no track, device or parameter index), a second step on a target an earlier step
  already changes, and anything past the three-step limit. The answer text lists these
  under "Not included", and the result carries `left_out` and `suggested_step_count`.
  If nothing is carryable, or the recipe service rejects the plan against live state,
  the result is `status: failed` with no token. Safety clamps and the master-fader
  lock are unchanged and run first; no limit was widened.
- `tests/test_orchestrator_autonomous.py` — eight new cases (below).
- `tests/conftest.py` — shared `fake_live` fixture (fake client plus isolated
  confirmation state).
- `tests/test_react_deliberation.py`, `test_react_dual_glm.py`,
  `test_autonomous_guardian_integration.py` — moved from invented tracks to the fake
  Live session. A recipe is checked against live state, so a snapshot naming tracks
  Live does not have now fails honestly instead of receiving a made-up token. The
  telemetry test now expects the Limiter ceiling step in `left_out`, not in the proposal.

New regression cases: the token is `v1.` and registered (one pending for the owner);
preparing writes nothing to fake Live; dismiss stops a held copy from applying; another
chat can neither dismiss nor apply; an edited step is refused; apply verifies, a replay
is refused, and Undo restores the original faders; omitted steps are reported and the
counts add up; unusable suggestions get no token; duplicate targets are collapsed.

## Verification

Environment: Claude Cloud container, Python 3.11, fake Live only. The container had no
pytest, fastapi or numpy; with Jack's approval a throwaway venv outside the repo was
built from `apps/backend/requirements.txt` without `librosa` and `onnxruntime`, plus
`soundfile`. No repo, CI or dependency file changed.

Before the fix, the new file: **7 failed, 6 passed**.

Scoped command (the handoff's five files plus the four other files that call
`react_deliberate`), run from `products/kenn` with a fresh cache:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_orchestrator_autonomous.py apps/backend/src/kenn/tests/test_react_deliberation.py apps/backend/src/kenn/tests/test_orchestrator_session_ownership.py apps/backend/src/kenn/tests/test_confirmation_cancellation_routes.py apps/backend/src/kenn/tests/test_session_clear_revokes_pending_confirmations.py apps/backend/src/kenn/tests/test_react_dual_glm.py apps/backend/src/kenn/tests/test_autonomous_guardian_integration.py apps/backend/src/kenn/tests/test_reference_tool_evidence.py apps/backend/src/kenn/tests/test_answer_audit.py -o cache_dir="$(mktemp -d /tmp/kenn-cloud-scoped-XXXXXX)"
```

Result: **136 passed, 1 warning**. The handoff's five files alone gave 107 passed on the
untouched checkout (the Mac's 134 covered a wider file set).

Full backend, same environment: **4008 passed, 137 skipped, 10 failed**. The same ten
fail identically on a clean checkout of `b00c262` with the change stashed, so none comes
from this change. Nine are cloud-environment gaps (local-only index/corpus inputs and
the optional audio packages left out of the venv): `test_answer_upgrade_context`,
`test_loudness_analysis`, `test_note_section_boost`, `test_sample_library`,
`test_stream_request_delivery`, and four in `test_streamed_generation_prefix_guard`.
The tenth is the known `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`;
its trace is not copied here. These figures are not comparable to the Mac's 4133 passed.

## Limits

- Fake Live only. No real Live write, real-model run or Live-open measurement; C1, C2
  and C3 stay open.
- A recipe carries at most three steps, so most autonomous suggestions are reported as
  not included. Raising that limit, or splitting a large plan into several confirmable
  recipes, is a product decision for Jack and was not attempted.
- Master Limiter ceiling, EQ band, device insertion and automation suggestions still
  cannot be applied through a recipe. They are now reported, not faked.
- `react_deliberate` now needs a snapshot that matches Live. Callers that pass a
  stale or foreign snapshot get `failed`, not a proposal.
