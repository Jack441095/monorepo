# Thursday V2-I Architecture — Long-Horizon Autonomous Operations

Branch: `thursday/v2i-long-horizon` · Base: V2-H `4c5b700`

V2-I extends the qualified V2-H loop with exactly what long horizons
require — memory, temporal coherence and endurance — and nothing that
increases authority.

## Purpose

V2-H proved one loop closes correctly. V2-I proves loops ACCUMULATE
coherently: weeks of changing company state without forgotten history,
duplicate work, oscillating priorities, stale authority, approval
fatigue, corrupted temporal truth or useless briefs.

## New modules

| Module | Responsibility |
|---|---|
| `simulated_clock.py` | Injectable deterministic clock; forward-only; fixed-offset day boundaries; restart-persistable |
| `temporal_truth.py` | Facts with provenance: CURRENT / HISTORICAL / STALE / CONFLICTED / INVALID; authoritative reads fail closed |
| `candidate_history.py` | Persistent candidate lifecycle (13 states); deterministic identity; dedup; reopen-only-on-new-evidence; failure-escalation ladder |
| `owner_decisions.py` | Explicit scoped decision ledger (reject/defer/forbid/protect/policy); provenance required; expiry + supersession; never grants approval |
| `approval_ergonomics.py` | Owner attention economics: duplicate suppression, batching, TTL expiry (fail-closed), efficiency metrics |
| `brief_v2.py` | Long-horizon owner brief with deterministic structural quality gate |
| `state_compaction.py` | Age/count-bounded retention that can never delete critical provenance |
| `synthetic_company.py` | Persistent multi-project evolving company (branches, SHAs, tests, deps, blockers, protection) |
| `event_injection.py` | Reproducible seeded/scripted company-evolution events |
| `long_horizon_runner.py` | Daily cycle orchestrator: observe → truth → lifecycle → stable priorities → work → approvals → brief → compaction, with crash/restart continuity |

## Key semantics

* **Identity vs evidence** — a candidate's identity is its
  `(project, problem_class)`; evolving detail lives in an evidence
  digest. Same underlying work keeps one lineage across weeks;
  materially new evidence reopens it, identical evidence is suppressed.
* **Memory ≠ authority** — historical facts, past approvals and owner
  decisions inform reasoning but confer no permission. Integration
  authority remains exclusively the V2-G token chain.
* **Stable-but-responsive planning** — priority order persists unless
  evidence materially changed (digest delta or scheduled event);
  unforced reorderings are counted as integrity violations.
* **Failure intelligence** — consecutive same-class failures escalate
  retry → defer → block → abandon; different failure classes restart
  the ladder; abandonment is terminal.
* **Supersession** — when a problem class disappears (suite recovered,
  blocker cleared), pending work of the old class is superseded;
  SUPERSEDED reactivates only on materially new evidence.
* **Multi-day TOCTOU** — target SHA bound at owner-grant time;
  execution revalidates against current state pre-apply; drift fails
  closed into the failure ladder.
* **Crash continuity** — full runner state persists atomically; crash
  drills at any phase restore exactly, never duplicating side effects.

## Qualification methodology

Layered: unit → state machine → restart durability → multi-cycle
evolving-company scenarios → adversarial → 90-day soak → frozen
holdout once. See `reports/thursday/v2i/qualification.json`.
