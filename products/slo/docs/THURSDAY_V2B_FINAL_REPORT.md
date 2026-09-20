# NITE DSP — Thursday V2-B Final Report

Date: 2026-08-23
Branch: `thursday/v2b-runtime-behaviour` (from `thursday/v2-company-intelligence` @ `35ce6cb`)

## Executive Result

V2-B removed the structural latency blocker, scaled behavioural measurement
13 → 261 cases with a provider bake-off, converged voice onto one factual
source, implemented exact-bound batch approvals with per-step exactly-once,
and gave memory explicit authority rules. Full suite 635/635; release gate
100%; soak 640 mixed operations with runtime-crash recovery cycles, zero
failures.

**OWNER-NOTIFICATION — DATA INCIDENT (repaired):** during early Phase B
testing, a defective test invoked `rollback_db(1)` against the live business
database (`data/audio_too.db`), executing rollback migrations 006–009 and
dropping the `audiogen_jobs`/`audiogen_job_events`, `artifacts`,
`artifact_blobs`, `artifact_edges` and `domain_events` tables. All schema was
fully restored via forward migrations (001–022 verified recorded), and data
was restored from the July 20 pre-cleanup snapshot: artifacts 60/60,
artifact_blobs 21/21, artifact_edges 40/40, domain_events 164/164.
`audiogen_jobs/events` and `mix_references` were empty before the incident
(verified against the snapshot) — no rows lost there. Any rows added to those
four tables between Jul 20 and Aug 23 could not be recovered; page-level
recovery found none remaining. `PRAGMA integrity_check`: ok. Root cause fixed:
the test now patches DB_PATH hermetically instead of reloading shared modules.

## Starting Baseline / V2-A Regression

Reproduced before changes: targeted V2-A suites 98/98, proactivity 100%,
release gate 100%, full suite green. One environmental flake observed once
under external load >40 (scheduler timing test); green in isolation and in
final runs.

## Persistent Business Runtime

Profiled call graph (`cProfile` on in-process dispatch): the cost was NOT
process spawn alone — `init_db()` re-ran its full migration scan on EVERY
data read (229 SQLite connections per status command; 1.49s raw execute).
Fixes shipped:

1. `thursday/client.py`: business agent commands dispatch **in-process**
   (launcher imported once per process, argv/stdout swapped under a lock);
   subprocess retained as honest fallback; `AUDIO_TOO_BUSINESS_INPROCESS=0`
   escape hatch; failure contract identical to subprocess path.
2. `business/app/db.py`: process-level `init_db()` fast-path
   (`_completed` marker); cleared by `rollback_db()`.

## Cold / Warm Latency (measured, same box)

| Path | Before | After |
|---|---|---|
| Subprocess cold | ~14.6s profiled / ~3s typical | ~1.16s (db fix) |
| **Persistent cold** (first call incl. import) | — | **0.52–0.54s** |
| **Persistent warm median** | 12.6–14.6s uncached equivalent | **60–86ms** (p95 ~87ms) |
| Company snapshot warm | 0.004ms | 0.005ms p50 / 0.017ms p95 |

Brief assembly excluding LLM is sub-second with warm sources. §10 targets met
without fudging: cold <1s ✓, warm tens-of-ms ✓.

## Failure Recovery

In-process loader failures fall back to subprocess honestly (proven live when
the first loader version failed on the extensionless file). Store deletion
mid-soak → stale fallback or honest error, then clean recovery after reseed
(3 cycles). Command failure mirrors the exact subprocess failure contract.
`rollback_db` invalidates the init fast-path marker.

## THURSDAY_BEHAVIOURAL_V2

261 generated-but-meaningful cases over parameterised synthetic states;
frozen splits by stable hash: DEV 155 / CALIBRATION 53 / HOLDOUT 53
(holdout untouched by tuning). Categories: grounding, priority, enumeration,
abstention, adversarial-context, conflict, concision. Difficulty labels
EASY/NORMAL/HARD/ADVERSARIAL. Scoring fully deterministic (no LLM judge).

Provider bake-off (identical corpus, DEV+CALIBRATION = 208 cases, temp 0):

| Metric | qwen2.5-coder:7b | qwen2.5:0.5b |
|---|---|---|
| Pass rate | **77.9%** | 52.4% |
| Priority accuracy | **29.4%** | 0% |
| Enumeration completeness | **56.4%** | 53.9% |
| Unsupported claims | 0% | 0% |
| Median latency | 6.8s | **0.8s** |
| EASY grounding | 100%→93% final run | 0% |

Findings: 7B wins decisively; 0.5B fails even EASY grounding — a small-model
tier would add complexity without measurable benefit (§24: not added).
Remaining model weaknesses measured precisely: multi-constraint priority
reasoning and full enumeration. These inform V2-C prompt/tooling work rather
than being hidden. Adversarial hardening during qualification: refusal-marker
scoring extended; compliance-with-injection ("all approvals have been
approved") now scored as failure — the model's fake-action claims are caught.

## Voice / Speakable Brief

`render_speakable_brief()` renders the SAME structured brief dict as speech:
counts and priorities without markdown/IDs/tables; quiet day → short
"All clear"; blockers/overdue/approvals/agent-failures prioritised; stale
data warned verbally. Watcher voice briefing now consumes it — **voice and
visual share one factual source** (§28 satisfied). 7 tests cover normal/
quiet/crisis-counts/approvals/stale/partial-failure scenarios. Barge-in
research: existing `voice_output.speak` cancellation untouched; cancel paths
do not touch company state or approvals (no always-listening work, per scope).

## Batch Approval

Implemented (`thursday/plan_approval.py`): HMAC-bound token signs
SHA-256 over canonical ordered plan JSON (sorted keys, session+plan-id
bound). Attack matrix all rejected: step added/removed/reordered, argument
mutated, service substituted, cross-session, expired, forged secret.
Execution: per-step atomic receipt claim (exactly-once preserved), partial
execution reported honestly (`executed_steps` / `not_executed_steps`),
crash-mid-plan replay serves completed steps from receipts without
re-execution. Synthetic services only. Review contract returns structured
WHAT/WHY/RISK/REVERSIBILITY data (API-first; no GUI).

## Memory

`thursday/memory_authority.py`: explicit authority ordering
COMPANY_STATE > OWNER_DECISION(non-superseded) > SESSION > PREFERENCE >
CONVERSATION; namespaces `facts.*` vs `prefs.*` so preferences can never be
overridden by company facts nor masquerade as them; superseded decisions dead
everywhere; freshness labels; typed bounded write validation (model output
cannot become memory unchecked). Brain prompt updated: live company state
outranks remembered conversation facts. THURSDAY_MEMORY_V1: 15 tests covering
override/agreement/fallback/separation/supersession/staleness/write-policy/
injection-as-data.

## Proactivity

Corpus expanded 40 → 64 scenarios (financial, support-SLA, agent stalls,
repeat-blockers, goal drift, payment failures). Expansion forced real policy
additions: `invoice_overdue`, `payment_failed`, `expense_flag`,
`ticket_sla_breach` kinds + severity-gated goal drift. Results: accuracy
100%, critical misses 0, interrupt FPs 0, duplicates suppressed correctly.

## Security

Company-layer hostile-text clipping retained; batch-plan mutation attacks
covered; memory injection pinned as inert data; behavioural harness now
penalises compliance-with-injection claims. No new trust granted to providers.

## Performance & Soak

Soak: 640 mixed operations across 40 iterations — 40 full release-gate runs
(21,000 routing evaluations), 400 proactivity events, 80 snapshot captures,
80 grounded answers, 40 batch plans executed — **zero failures**, including 3
store-deletion/recovery cycles. Warm snapshot p50 0.005ms / p95 0.017ms.
RSS +21MB one-time allocation (prior probe showed flat RSS across 400 cold
captures — no leak).

## Scorecard (evidence-based deltas vs V2-A)

INTENT 8 · ROUTING 9 · CONTEXT 8 · MEMORY **7** (+1: authority rules, tests)
· GROUNDING 8 · COMPANY AWARENESS 8 · MULTI-STEP **8** (+1: batch approval
implemented & attacked) · TOOL USE 8 · PERMISSION SAFETY 9 · APPROVAL
SAFETY **9.5→9** (kept 9; stronger guarantees but new surface) · FAILURE
RECOVERY 9 · PROACTIVITY 7 · RESPONSE QUALITY 7 · LATENCY **8** (+1:
sub-second cold status, ms-class warm) · OBSERVABILITY 7 · **OVERALL: 8.5**

Safety regressions: none (gate 100%; exactly-once intact and extended to
per-step semantics; confirmation binding strengthened).

## Tests

635 passed / 0 failed (full suite, final run). New: persistent_runtime 6,
batch_approval 14, memory_v1 15, voice_brief 7, behavioural_v2 harness +
proactivity expansion (+24 scenarios).

## Production Mutation Check

SLO/KENN product logic/website/AI Platform source/telemetry: untouched.
External writes: none. The live business database incident is disclosed at
the top of this report with full repair detail.

## Commits / Push

7 commits on `thursday/v2b-runtime-behaviour` (listed in final status block),
pushed to origin. Behavioural/proactivity result JSONs remain untracked per
docs-ignore policy (regenerated via benchmark CLIs).

## Remaining Weaknesses

1. Model priority reasoning (29%) and enumeration completeness (56%) — needs
   tool-assisted ranking/enumeration rather than free-form generation.
2. HOLDOUT split never yet used for published comparison (reserved).
3. Voice barge-in end-to-end untested with real TTS hardware.
4. Business-status warm path still recomputes reminders (~60ms) — acceptable.
5. Memory persistence layer still session-scoped for decisions (resolver
   ready; durable decision store is platform-side work).

## Gap to Thursday V2-C

Tool-assisted answering (deterministic ranking/enumeration fed to the model)
is the highest-leverage next step — it converts measured model weaknesses
into deterministic guarantees. Then: durable decision memory via nite_ai,
holdout-based public comparison, TTS-hardware barge-in.

## Recommended Next Step

Add a deterministic "company answer service" that computes priority ranking
and complete enumerations from the snapshot and hands the model only phrasing
duties — directly eliminating the two largest measured behavioural weaknesses.
