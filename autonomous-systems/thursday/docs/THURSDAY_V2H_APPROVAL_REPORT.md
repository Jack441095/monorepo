# Thursday V2-H Approval Report

## Model

Owner approval is a capability, not a conversation. Approval is expressed as an
`ApprovalToken` bound to exactly one sealed `IntegrationPlan` at exactly one
target SHA.

## Binding properties

* **Plan digest binding** — token carries the SHA-256 of the canonical plan
  bytes; any post-seal plan change invalidates the token (Z-25).
* **Target SHA binding** — TOCTOU drift between approval and apply is detected
  and aborted before mutation (category O).
* **Single use** — `consume()` marks the token; replayed verification fails
  structurally (`consumed=True` → verify fails). Double-consume raises.
  Benchmark categories M/N: 15/15 PASS.
* **Expiry** — tokens carry TTLs; expired tokens fail closed.
* **Forbidden targets** — `main`, `master`, `production`, `release` are
  structurally rejected as integration targets in `IntegrationPlan.__post_init__`.

## WAITING_FOR_APPROVAL durability

`WAITING_FOR_APPROVAL` is a first-class durable loop state
(`autonomous_controller.py:96`). Each waiting candidate is persisted as a
`PendingApproval` record (proposal, plan hash, token id, target SHA/branch,
candidate SHA, expiry) via atomic write (temp file + fsync + rename).

Restarting Thursday therefore cannot:

* auto-approve or auto-integrate a waiting candidate,
* lose lineage (record carries proposal + plan + token identity),
* reuse an expired or consumed token (verify fails closed on both).

## Soak evidence

Across the 5,000-cycle soak, every opportunity cycle exercised fresh
token issue → verify → consume → replay-attempt:

* duplicate side effects blocked: 3,414 · accepted: **0**
