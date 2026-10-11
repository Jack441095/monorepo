# Guarded compound EQ verification — 11 October 2026

This receipt records the compound EQ slice following `4b5fa3cd`. All writes used synthetic Fake Live fixtures; there were zero writes to a running Live session. The September receipts supporting the existing taper and new native dB identity conversion do not qualify this build for real-model, independent producer or supervised Live use.

## Implemented behavior

Production compound EQ requests produce the existing recipe card with two guarded parameter children. Each child retains its addressed observation, sparse index, exact band name, metadata, readable units and before-state. A retained-reference check requires the frequency and gain observations to belong to the same device. Proposal construction does not rediscover after this check. Relative gain cannot silently rebase onto a later value. Apply, recovery and Undo delegate to the shared guarded recipe executor.

The EQ Eight gain profile is a native -15 to +15 dB identity mapping supported by the September readback receipts cited in `device_units.py`. The shared planner requires matching native bounds for every card using that profile, including single controls and recipes. The existing frequency taper remains bounded to 20 Hz..20 kHz. Legacy fake-only compound cards keep their existing format.

## Verification

From `products/kenn/apps/backend/src`, using the repository Python environment:

- Scoped command: `python -m pytest -q -p no:randomly kenn/tests/test_guarded_eq_workflows.py kenn/tests/test_guarded_recipes.py kenn/tests/test_live_action_service.py kenn/tests/test_live_command.py kenn/tests/test_device_units.py kenn/tests/test_full_stock_device_control.py`: **276 passed**, 4.43 seconds.
- After strengthening the one-time replacement regression and completing mutations: `python -m pytest -q -p no:randomly kenn/tests/test_guarded_eq_workflows.py`: **23 passed**.
- Full command with `KENN_LIVE_BACKEND=fake`: `python -m pytest -q -p no:randomly`: **4,578 passed, 137 skipped, 1 pre-existing failure, 5 warnings**, 112.73 seconds.
- The existing failure remains `kenn/tests/test_query_typo_correction.py::test_typo_query_routes_to_production_and_avoids_weak_match_early_return`: route `unknown` rather than `production`. It was reproduced at the earlier baseline and is outside this control integration slice.
- Independent spec and standards reviewers compared the final slice with `4b5fa3cd`; neither has remaining actionable findings.

## Mutation evidence

`run_eq_mutations.py` temporarily removes five boundaries and restores exact source bytes in `finally`. **5/5 caught**; results and restoration hashes are in `eq-mutations.json`: exact band pairing, shared native gain bounds, relative gain before-state, same device across observations and retained observations after validation. A one-time same-name replacement after the retained-reference check must leave a stale card rather than gain a fresh approval. Mutation runs clear the affected import cache and disable bytecode writes so equal-length edits cannot load an earlier mutation after source restoration.
- `git diff --check`: passed.

## Changed files

- `apps/backend/src/kenn/core/device_units.py`
- `apps/backend/src/kenn/core/live_action_service.py`
- `apps/backend/src/kenn/core/live_command.py`
- `apps/backend/src/kenn/core/live_control_planner.py`
- `apps/backend/src/kenn/tests/test_guarded_eq_workflows.py`
- This receipt, `run_eq_mutations.py` and `eq-mutations.json`.

Proposed progress entry for the existing `KENN_PLAN.md`: compound EQ now passes fake-backed exact duplicate targeting, native unit bounds, planning races, Apply/recovery/Undo and command gateway checks. External qualification gates remain open; the dirty main-checkout roadmap was preserved.
