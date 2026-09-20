# Phase 4 — Thursday Company AI Report

Date: 2026-08-22 · Platform v0.3.0 · Audio_Too canonical integrated.

## Executive Result

Thursday Company AI foundation is operational end-to-end:

```
CompanyStore (SQLite) ─► company.* capabilities ─► LocalRuntime (Unix socket)
                                                        ▲
                                        RuntimeClient / CLI / Thursday
```

## Gate Results

| Gate | Result |
|---|---|
| Audio_Too adapter integration | COMPLETE — fast-forward `6b35f5e → 9a10ccf`, pushed, 24 tests re-run from canonical tree |
| Company capability registry | PROVEN — 9 capabilities registered and dispatched |
| Approval inbox | PROVEN — pending list + owner decision (internal state only) |
| Local runtime POC | PROVEN — lifecycle/IPC/security/failure tests |
| CLI | PROVEN — human + JSON output, unavailable/mismatch handling |
| Grounding honesty | PROVEN — empty state reports "no company state recorded yet" |

## Company capabilities (v0.1.0 each, provider `nite_ai.company_store`)

Read-only (LOW risk): `company.brief.daily`, `company.review.weekly`,
`company.goals.list`, `company.tasks.list`, `company.risks.list`,
`company.decisions.pending`, `company.agents.status`, `company.approvals.pending`.
Write-level: `company.approvals.decide` (HIGH risk, READ+WRITE permission) —
changes internal approval state only; executing an approved external action
does not exist and is a separate future capability.

## Local runtime

Unix domain socket, length-prefixed JSON envelope, protocol version 1.0.
Lifecycle: start → stale-socket probe/cleanup → serve → graceful shutdown;
second instance refused; restart verified. Limits: 1 MB max message,
30 s receive timeout. Security: socket chmod 0600 = V1 auth boundary
(single-user macOS threat model); structured errors for malformed JSON /
oversized / protocol mismatch / unknown operation / permission denial.
One bad request can never kill the serve thread.

## Grounding guarantees

Handlers report real persisted state only. Empty store ⇒ explicit
"no company state recorded yet" notes. No synthetic data outside tests.
LLM interpretation layers must treat DailyBriefData as the sole source of
truth; confidence vocabulary stays measured/observed/derived/reasoned.

## Engineering status

Generic `EngineeringStatus` snapshot contract added to the domain model
(product/repo/branch/sha/test/build/qualification/release/blockers/source/
timestamp) — ready for read-only Git adapters in Phase 5.

## Version decision

0.2.0 → **0.3.0**: new public surface (runtime + client protocol, company
capability registry, approvals schema migration v2). Additive; no breaking
changes to live Thursday/KENN adapters.

## Test totals this phase

Platform suite: 105 tests, all PASS (84 prior + 21 new).

## Next phase (recommended)

Phase 5: real company-state bootstrap tooling for the owner, read-only local
Git engineering adapter feeding `EngineeringStatus`, then Gmail/Calendar read
connectors behind approval-gated design.
