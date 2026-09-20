-- §13.6.2 (docs/KENN_FUTURE_PLAN.md): "Applied revisions log -- track
-- what KENN applied + whether you kept it." Migration 020 already
-- tracks what was requested; this adds whether the user kept it,
-- fed by D2.4's listening-checkpoint accept/reject reply. Empty string
-- means "no checkpoint reply recorded yet" (most rows, since not every
-- revision request gets a checkpoint, and not every checkpoint gets a
-- yes/no reply) -- not the same as a deliberate "neither kept nor
-- reverted" state, there isn't one.
ALTER TABLE project_revision_history ADD COLUMN outcome TEXT NOT NULL DEFAULT '';
