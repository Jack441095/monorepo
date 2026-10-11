# Guarded device setup verification — 11 October 2026

This receipt records the setup slice following `d030a479`. Every write used synthetic Fake Live fixtures; there were zero writes to a running Live session. This build still requires the finished model build, independent human review and an owner-supervised Live soak before external qualification gates can close.

## Implemented behavior

Production setup uses the existing insertion owner for its first confirmation. That Apply inserts and verifies one allowed device. It then reads the new device's exact controls and returns a fresh recipe card with actual before-values. Configuration requires a second explicit Apply. The first confirmation binds the requested follow-up control names, units and values, so those intents cannot be substituted in transit.

The second card retains addressed observations and sparse parameter indices. Multiple controls must belong to the same observed device. Duplicate or unindexed inventory, unqualified native bounds, protected controls and unknown enable semantics withhold configuration authority. EQ's Filter On control requires exposed quantized 0/1 endpoints. Parameter Apply, recovery and Undo use the shared guarded recipe executor. Insertion and configuration have separate receipts and separate Undo actions. Legacy fake setup examples keep their existing combined format; legacy production setup cards continue to refuse before writing.

If inspection fails after verified insertion, the insertion receipt stays applied and no controls are written. There is no automatic reinsertion or removal. If dispatch occurs but acknowledgement/readback cannot establish the outcome, the receipt is `unknown`, requires inspection and has no follow-up card. The command gateway reports `changed=null` and preserves the uncertain receipt even if subsequent logging fails. HTTP returns 409 for the unknown outcome. A consumed token cannot send the insertion twice.

Read-only MCP adapters now declare their disabled write boundary so insertion and parameter owners refuse before dispatch with `write_attempted=False`. These definite refusals stay distinct from uncertain writes. Insertion also selects its result API or legacy writer before dispatch; an internal `AttributeError` after a possible insertion cannot invoke the other writer and append a second device.

HTTP registers the returned configuration card for token-only confirmation. The frontend keeps the insertion receipt on its original card and displays a separate pending configuration card. It never applies that second card automatically.

Example from the synthetic fixture: an empty Bus receives EQ Eight on the first Apply. Fresh inspection observes band 2A off, 250 Hz and 0 dB at sparse indices 4, 12 and 21. The second card requests on, 5 kHz and +3 dB. Only the second Apply writes those controls; configuration Undo restores the observed values, and insertion Undo removes the inserted device. The template track is untouched.

## Verification

Backend commands ran from `products/kenn/apps/backend/src`, using the repository Python environment with `KENN_LIVE_BACKEND=fake`:

- Scoped: `python -m pytest -q -p no:randomly kenn/tests/test_guarded_device_setup.py kenn/tests/test_daw_command_handler.py kenn/tests/test_guarded_eq_workflows.py kenn/tests/test_guarded_recipes.py kenn/tests/test_live_action_service.py kenn/tests/test_live_command.py kenn/tests/test_live_backend.py kenn/tests/test_device_units.py kenn/tests/test_full_stock_device_control.py kenn/tests/test_fastapi_live_command_owner.py kenn/tests/test_live_setup.py kenn/tests/test_setup_routes.py`: **345 passed**, 3.41 seconds. The new setup file contains **36 passing cases**.
- Full suite: `python -m pytest -q -p no:randomly`: **4,614 passed, 137 skipped, 1 failed**, 5 warnings, 115.64 seconds. The failure is the pre-existing `kenn/tests/test_query_typo_correction.py::test_typo_query_routes_to_production_and_avoids_weak_match_early_return`: the typo query routes to `unknown` instead of `production`. It was reproduced at the integration baseline and remains outside this control slice's ownership.
- An earlier full run caught a read-only refusal incorrectly reported as an unknown write. The final build refuses before dispatch, and both the existing read-only MCP test and the new insertion/configuration regressions pass.
- Both independent reviewers compared the final setup slice with `d030a479`. Standards: no remaining actionable findings. Spec: unknown insertion reporting and token-only registration findings were fixed and re-reviewed; no remaining actionable findings.

Frontend commands ran from `products/kenn/apps/frontend` with the app's existing ARM Node runtime:

- `node node_modules/vitest/vitest.mjs run --maxWorkers=1`: **80 passed in 9 files**, 2.20 seconds.
- `node node_modules/vue-tsc/bin/vue-tsc.js -b`: passed.
- `node node_modules/vite/bin/vite.js build`: passed, 1.27 seconds.
- The system's x64 Node could not load the installed ARM native bindings. Using the bundled ARM runtime required no dependency or lockfile changes.

## Mutation evidence

`run_setup_mutations.py` temporarily breaks sixteen boundaries and restores exact source bytes in `finally`. **16/16 caught**, with restoration hashes in `setup-mutations.json`: deferred intent binding, same device across configuration reads, retained single-control observations, unique indexed inventory, binary enable semantics, separate configuration Apply, frontend API payload preservation, separate chat card display, unknown insertion receipts, unknown gateway outcomes, unknown receipts surviving log failure, token-only follow-up registration, no retry after an internal attribute error, read-only insertion refusal, read-only parameter refusal and the read-only backend declaration.

The duplicate-inventory regression supplies an ambiguous positional list while leaving addressed metadata unique; another planner guard cannot mask loss of the inventory check. The single-control replacement regression likewise avoids a second stale child masking rediscovery. Python mutations clear the affected bytecode cache and disable bytecode writes so restored source is actually tested.

`git diff --check`: passed.

## Changed files

- `apps/backend/src/kenn/core/live_action_service.py`
- `apps/backend/src/kenn/core/live_backend.py`
- `apps/backend/src/kenn/core/live_command.py`
- `apps/backend/src/kenn/routes/daw_command_handler.py`
- `apps/backend/src/kenn/tests/test_guarded_device_setup.py`
- `apps/backend/src/kenn/tests/test_live_backend.py`
- `apps/frontend/src/api/kenn.ts`
- `apps/frontend/src/api/kenn.test.ts`
- `apps/frontend/src/composables/useKenn.ts`
- `apps/frontend/src/composables/useKenn.test.ts`
- This receipt, `run_setup_mutations.py` and `setup-mutations.json`.

## Proposed roadmap progress entries

For the existing `KENN_PLAN.md`, whose dirty main-checkout changes were preserved:

- C3/C5: setup exposes the actual inserted device's before-values, a separate confirmation and honest applied/unknown outcomes; HTTP and frontend journeys pass with fake fixtures.
- L1: setup retains observed identities and sparse indices through configuration, and refuses ambiguous inventory, protected controls and unqualified semantics. These results add fake-backed evidence, not new measured coverage.
- L3/L5: setup reuses insertion and recipe owners, with separately confirmed stages, guarded recovery/Undo, no duplicate insertion after lost acknowledgement and inspection-required unknown outcomes.
- C1/C2/C4 and L2/L4: this slice adds no inference tuning, model promotion, retrieval changes or new qualification claims. Prepared model runs await Claude's exact finished build and an available machine. Independent answer review still needs at least 150 cases; natural-request qualification still needs 500 fresh blind phrases from at least three authors and two reviewers. The supervised Live requirement for at least 15 recipes remains open.

No new inference-side hook is required from Claude for this setup slice. All control authority stays with the existing deterministic owners.
