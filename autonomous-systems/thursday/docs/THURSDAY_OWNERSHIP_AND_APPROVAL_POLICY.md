# Thursday V2-D Ownership and Approval Policy

This document governs workspace isolation and permissions required for mutation tasks.

## 1. Repository Ownership Check
Before launching any local write task, the Orchestrator checks repository status:
- `OWNED_CLEAN`: Workspace is clean; safe for local writes.
- `OWNED_DIRTY`: Uncommitted changes present.
- `AMBIGUOUS` or `FOREIGN_BUSY`: Safety lock active; mutations deferred.

## 2. Workspace Leases
A short duration lease (default: 300 seconds) is acquired per workstream. Heartbeats must refresh active leases. Stale leases trigger escalation to `STALE_REVIEW_REQUIRED` rather than automatic override.

## 3. Approval Levels
Approval is plan-hash bound and scoped:
- **L0 — Read-Only**: No approvals required.
- **L1 — Isolated Reversible Write**: Allowed within owned staging directory.
- **L2 — Local Mutation**: Shared workspace changes; requires plan confirmation.
- **L3 — External Business Write**: Gated behind owner verification.
