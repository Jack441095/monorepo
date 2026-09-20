# Rename-plan dry run — current safety result

Date: 2026-09-11

The existing testing-library plan was validated in read-only mode with the
386 suggestion rows selected and the current duplicate guard attached.

| result | count |
| --- | ---: |
| plan rows inspected | 7,315 |
| suggestions selected | 386 |
| duplicate-flagged suggestions | 30 |
| suggestions without duplicate flags | 356 |

Duplicate flags among the selected rows were:

- 13 exact duplicate canonicals
- 16 exact duplicate aliases
- 11 acoustic near-duplicate candidates

The 356 rows without duplicate flags are not approved or safe to apply: they
still require explicit human approval and the normal confidence, collision,
and qualification gates. The dry run performed no filesystem mutation and
left every plan row unchanged.

Receipt: `results_rename_plan_dry_run_current_v1.json`.
