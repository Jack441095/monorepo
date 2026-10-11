# Guarded recipe verification — 11 October 2026

This receipt records the recipe slice following `281ee3c8`. All writes in these tests used synthetic Fake Live fixtures. There were zero writes to a running Live session. This does not qualify the new build against a real model, producer review or supervised Live soak.

## Implemented behavior

Recipe parameter children retain their observed object, topology, sparse parameter index, metadata, bounds and readable units through the parent confirmation. Apply delegates to the existing guarded parameter executor. Recovery and Undo use the original receipt observation and require the verified post-state; an identical replacement or a later manual edit cannot inherit the write. Unknown outcomes remain partial recovery requiring inspection. Mixer and transport recovery also refuse to overwrite later producer changes. Recipe receipts bind Undo to their project/session.

The existing command gateway and recipe card schema carry these changes. Legacy production cards still refuse before a write. Four existing command-test session strings now keep Apply and Undo in the same project.

## Verification

From `products/kenn/apps/backend/src`, with the repository Python environment and `KENN_LIVE_BACKEND=fake`:

- `python -m pytest -q -p no:randomly kenn/tests/test_guarded_recipes.py`: **28 passed**.
- `python -m pytest -q -p no:randomly`: **4,555 passed, 137 skipped, 1 pre-existing failure, 5 warnings**, 117.82 seconds.
- The failure is `test_typo_query_routes_to_production_and_avoids_weak_match_early_return` in `test_query_typo_correction.py`: the route is `unknown` rather than `production`. It was reproduced at the preceding baseline and is outside this parameter execution slice.
- `git diff --check`: passed.

Independent spec and standards reviews compared the slice with `281ee3c8`. A spec finding about mixed recipe recovery overwriting a later mixer edit was fixed and re-reviewed. A standards finding about the malformed-card fallback comment was fixed. Neither review has remaining actionable findings.

## Mutation evidence

`run_recipe_mutations.py` temporarily removes six guards, runs the relevant regression, and restores exact source bytes in `finally`. **6/6 caught**, with restoration hashes in `recipe-mutations.json`: parent target/semantics binding, original object identity, retained Undo observation after validation, mixer-only project isolation, mixer post-state recovery and transport post-state recovery.

The retained-observation mutation validates the receipt and then deliberately rediscovers by position. A one-time identical replacement between those operations must not gain Undo authority. The project mutation uses a mixer-only recipe so a device child's separate guard cannot mask loss of the parent boundary.

## Changed files

- `apps/backend/src/kenn/core/live_recipe.py`
- `apps/backend/src/kenn/tests/test_guarded_recipes.py`
- `apps/backend/src/kenn/tests/test_live_command.py`
- This receipt, `run_recipe_mutations.py` and `recipe-mutations.json`.

Proposed progress entry for the existing `KENN_PLAN.md`: guarded recipe integration now passes fake-backed Apply, recovery, Undo, project isolation and gateway regressions; real-model, independent producer and owner-supervised Live qualification remain open. The dirty roadmap in the main checkout was preserved.
