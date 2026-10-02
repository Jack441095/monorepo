# Unused private helpers and imports — 2 October 2026

This records another bounded cleanup under A3 in
[KENN_PLAN.md](../../KENN_PLAN.md). No feature or module was removed.

## Reachability evidence and exact changes

Repository symbol searches found only definitions for `_contains_all` and
`_bool_value`. AST checks found zero loads, exports, direct or star imports for
the candidates, and no dynamic name lookup in the owning modules. The Live
parser exports only `parse_request`; its rule chain and proposal registry do not
name the removed helper. Packaging includes the module, not that helper.

Paths are relative to `products/kenn/apps/backend/src/kenn/core`.

- `diagnostic_framework.py`: remove unused `_contains_all`.
- `live_intent.py`: remove unused `_bool_value`.
- `assistant_recovery_qualification.py`: remove unused `deepcopy` import.
- `psychoacoustics.py`: remove unused `dataclass` and `field` imports.
- `arrangement_doctor.py`: remove unused `asdict` import; keep used dataclass imports.

The code diff contains five files, 11 deleted lines and one added line. Diagnostic
planning, parser rules, recovery qualification, psychoacoustic calculations and
arrangement analysis retain their existing public behavior.

## Verification

The same scoped command passed 139 tests before deletion in 0.65 s and after
deletion in 0.66 s. The post-edit log was retained locally. The combined 3,413-case
backend run immediately preceded this cleanup and is not presented as a run of
the subsequent deletions. `git diff --check` passed. No model, network or Live
calls were used.

From `products/kenn/apps/backend/src`:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_diagnostic_loop.py kenn/tests/test_diagnostic_loop_store.py kenn/tests/test_assistant_recovery_qualification.py kenn/tests/test_psychoacoustics.py kenn/tests/test_arrangement_doctor.py kenn/tests/test_live_intent_rule_order.py kenn/tests/test_triage_unparsed_requests.py
```

This receipt and the bounded checked item in `KENN_PLAN.md` are the only
documentation changes for the deletion.
