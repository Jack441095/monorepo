# KENN rollback and recovery

This is an operational procedure. Priorities and release gates live in
[KENN_PLAN.md](../../KENN_PLAN.md). Use the receipt and exact released artifact;
never restore a producer's project from an assumption about its previous state.

## Unexpected Live change

Stop further requests and retain the execution receipt. Offer its identity-bound
Undo only after verifying that the target still has the recorded post-write value.
If another change occurred, refuse automatic restoration and inspect manually.
An incomplete batch needs a receipt identifying each applied and restored step;
do not assume the batch was atomic. If recovery is incomplete, stop the companion,
save the disposable set under a new name, and let the owner restore a known-good
Live set backup. KENN must not delete, overwrite or force-restore a project.

For repeated unexpected writes, disable `AUDIO_TOO_ALLOW_DAW_CONTROL`, stop the
companion and disable AbletonOSC in Live. Auto mode stays disabled and the legacy
KENN_Bridge route stays unselected. After confirmation-secret exposure, rotate
`KENN_CONFIRMATION_SECRET` and restart; in-memory confirmations expire. Live
inspection or further mutation follows the owner's supervised recovery schedule.

## App or code regression

Keep the previous app archive and checksum. A tester can quit KENN and replace the
app with that exact previous version; do not delete their settings or history.
Check data/schema compatibility before starting an older build and preserve a
backup if a migration occurred. Re-run the recorded smoke checks and scoped
qualification for that artifact before distributing it.

For source recovery, make a reviewed `git revert` commit for the faulty change,
run affected tests and rebuild with the existing build tooling. Do not use a hard
reset or force-push as a release recovery procedure. No old receipt automatically
qualifies the rebuilt artifact.

## Retrieval regression

Keep the current and previous index versions. The active pointer is owned by
`kenn.retrieval.index_store`; its `rollback_index()` validates the previous
manifest before moving the pointer. Use that supported path under a controlled
maintenance session, then restart/reload consumers and run the affected retrieval
fixtures. Record before/after version and digest, not just the pointer name.
Do not rebuild an index as a rollback, delete the failed candidate, or change
grounding thresholds to conceal a regression. A missing or invalid previous
version requires investigation rather than a guessed path.
