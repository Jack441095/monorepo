# Ableton Assistant Rollback Plan

If a mutation is unexpected, stop further requests, save the execution receipt, and use its undo payload after verifying the target still has the expected post-write value. If the value has changed independently, do not overwrite it; inspect manually and create a new proposal.

For a failed batch, require an atomic rollback receipt and verify every restored value. If rollback is incomplete, stop the companion, save the disposable set under a new name, and restore from the user's known-good Live set backup. KENN never deletes, overwrites, or force-restores a project.

Disable `AUDIO_TOO_ALLOW_DAW_CONTROL`, stop the companion, and remove/disable `AbletonOSC` in Live if repeated unexpected writes occur. Auto mode remains disabled. Rotate `KENN_CONFIRMATION_SECRET` after token exposure and restart the process; in-memory tokens are then invalid. Keep the legacy `KENN_Bridge` route unselected.
