# Thursday V2-H Crash Recovery Report

## Transaction state machine

Shared mutation is governed by `IntegrationTransaction` — a directed acyclic
state machine:

```
PREPARED → APPROVED → APPLYING → VALIDATING → COMPLETED
                     ↘ ROLLING_BACK → FAILED_SAFE
PREPARED/APPROVED → ABORTED
```

Forbidden transitions raise; terminal states accept no further transitions.

## Recovery semantics

* **Pre-apply abort** — token mismatch, TOCTOU drift, or lease loss aborts
  before any mutation (`ABORTED`, no-op on the worktree).
* **Deterministic rollback** — post-QA failure or apply error drives
  `ROLLING_BACK` and lands in `FAILED_SAFE`; rollback is a deterministic
  `git reset --hard <pre_sha>` recorded before mutations begin.
* **Atomic checkpoints** — controller loop state (plans, pending approvals,
  cycle results) persists via temp-file + fsync + rename, so a crashed process
  resumes from durable state.
* **Lineage survives crashes** — candidate lineage is append-only; closing is
  idempotent (Z-26), so replayed recovery cannot corrupt history.
* **Reconciliation** — `StateReconciler` re-derives Thursday-owned views after
  integration; rejected/integrated proposals keep their audit trail
  (crash-recovery category R: 5/5 PASS).

## Soak evidence

Every QA-passing soak cycle drilled the full rollback path:
1,707 rollbacks executed · rollback failures **0** · invalid state transitions
accepted **0** (1,707 correctly blocked) · orphan tasks after reconciliation **0**.
