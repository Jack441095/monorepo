# Thursday Autonomous Recovery & Qualification Report

Date: 2026-08-22 (Thursday programme, recovery session)
Repository: `Audio_Too` — branch `thursday/daily-brief-mvp`

## Executive Result

The interrupted agent died mid-way through wiring the composed Daily Brief
into Thursday's handler routing: composer built and pushed, integration tests
written but red (implementation missing), one pre-existing test failure
(missing codebase map) left behind. This session recovered that work to green,
then converted the compute window into measured improvements:

- **Recovered**: handler→composer routing completed; orphaned tests green.
- **Fixed a real safety gap**: confirmed consequential actions no longer sit
  inside the retry loop (exactly-once execution).
- **Hardened injection surface**: untrusted session summaries are now
  quarantined as labelled data in brain prompts; new adversarial suite pins
  this plus brain-output validation.
- **New owned suites**: prompt-injection (17 cases), receipt integrity (14),
  morning-brief benchmark (5).
- **Routing**: release gate raised from 99.41% → **100%** (525/525) by fixing
  corpus mislabels and adding weather coverage + a guarded rain pattern.
- **Performance**: daily brief sources now compose concurrently — measured
  live at ~11.8s total against a single 12.6s source (previously additive).

Full Thursday suite: **518 passed** at last complete run. Final re-validation
was interrupted by an external system-load event (load average >200 from other
programmes); see "Production Mutation Check".

## Interrupted Session Recovery

| Item | State found |
|---|---|
| Branch | `thursday/daily-brief-mvp` @ `6810283` (pushed) |
| Worktree | Dirty: `.env.example`, `tests/thursday/test_thursday_daily_brief.py` (+57 lines) |
| Committed by predecessor | `feat(thursday): daily brief composer…` (6810283) |
| Uncommitted WIP | 3 handler-integration tests calling `handlers.daily_brief` (attribute did not exist yet) |
| Implementation status | `_handle_calendar` still routed briefing phrases to legacy `daily_briefing` |
| Pre-existing failure | `test_load_codebase_map_reads_the_real_file` — `docs/CODEBASE_MAP.md` deleted in `ae7ca5b` while brain still loads it |
| Background processes | None surviving (Ollama serve was already running since 00:02, owner-level) |
| Stale artifacts | `.pytest_cache/lastfailed` stale/unrelated (audio suites); documented, untouched |

**Recovery verdict**: the interrupted agent did NOT fail completely — its
committed layer was sound (7/7 composer tests passing on arrival). It stopped
between writing the integration tests and implementing the routing.

## Repository / Ownership State

- Ownership of Audio_Too: **FREE** (no git locks, index mtime = last commit
  time 17:23, no writes for ~85 min while sibling programmes were active).
- Other programmes active in workspace (`Nite_DSP_RnD`, `Nite_DSP_Product_
  Experience_Rnd`) — not entered, not modified.
- Single worktree; remotes unchanged (`origin`, `nitedsp_prod`,
  `velvet_thunder`); no force-push; identity untouched.

## Starting SHA / Ending SHA

- Starting SHA: `6810283b67d24c1e8bbcc65ac3a4969330d1e8af`
- Ending SHA: see Commits section (branch advanced by 6 commits).

## Recovered Work

1. `.env.example`: TokenRa OpenAI-compatible provider documentation
   (committed as-is after secret-safety review; placeholder key only).
2. Handler-integration tests: implemented missing routing in
   `_handle_calendar` (`thursday/registry/handlers.py`) so briefing phrases
   return the composed brief; added module-level `daily_brief` import the
   tests' patch target requires.

## Rejected / Incomplete Work

- Legacy `daily_briefing()` remains authoritative for orchestrator/watcher
  proactive surfaces — deliberately NOT replaced this session (separate
  product decision; recorded as V2 work).
- `docs/CODEBASE_MAP.md` regenerated but left **untracked**: `docs/` is
  deliberately gitignored ("internal docs — not part of the public repo").
  Force-adding would violate stated repo policy. Owner decision required if
  fresh clones should carry functional ground-truth files.

## Current Architecture (verified from source)

USER INPUT → deterministic intent classification (`intent.py` regex/weights)
→ registry routing (`registry/system.py` → `handlers.py`) → service action
→ response formatting (`orchestrator.handle`) with:

- LLM escalation only for unknown/contextual intents (`brain.decide`),
  services trimmed per-message (`_select_relevant_services`, ≤15),
- codebase map injected into brain prompts (`brain.load_codebase_map`),
- consequential actions: signed expiring confirmation (`confirmation.py`,
  HMAC-bound token) → atomic receipt claim (`action_receipts.py`, SQLite WAL)
   → execute → receipt completion appended to reply,
- macros/steps re-validated through the same gateway; brain plan steps are
  re-mapped against the real service registry before anything executes,
- bounded retries (2 attempts, transient-only taxonomy) — now excluding
  receipt-backed consequential actions,
- memory: session store + plan memory + user profile; receipts DB separate.

Unnecessary complexity noted: two parallel "briefing" implementations
(legacy `scheduling.daily_briefing` vs composed `daily_brief.py`) — V2 should
converge them.

## Qualification Benchmark

Name: **THURSDAY_QUALIFICATION_V1** (this session's frozen reference):
- Deterministic release gate: 525 cases (`thursday.evals.benchmark`)
- Development corpus: 708 held-out cases
- Injection/adversarial suite: 17 cases
- Receipt integrity: 14 cases
- Exactly-once dispatch: 2 cases
- Morning brief benchmark: 5 cases
- Full `tests/thursday/` regression: 518 tests

## Baseline Results (measured at session start)

- Release gate (as found): 510 cases, overall 99.41%, critical 100%,
  target 100%, 3 failures — all one root cause family (below).
- Full suite: 480 passed / 1 failed (codebase map missing).
- Gate latency: median ≈12.6 ms/case; RSS drift over 2,625 executions: +0.0 MB.

## Failure Taxonomy

| # | Failure | Root cause class | Severity | Disposition |
|---|---|---|---|---|
| 1 | Briefing phrase returned legacy agenda, not composed brief | Interrupted implementation | P1 | Fixed |
| 2 | `docs/CODEBASE_MAP.md` missing → brain silently context-free + test red | Deletion during docs consolidation; functional file treated as doc | P1 | Fixed (regenerated; tracked-status = owner decision) |
| 3 | Weather question labelled `unknown` in corpus | Corpus mislabel (weather IS registered) | P2 | Fixed labels + added weather family |
| 4 | "will it rain" fell to contextual | Router pattern gap | P3 | Fixed with subordinator-guarded pattern |
| 5 | Consequential actions inside retry loop → duplicate side-effect risk | Retry policy applied uniformly | **P0** | Fixed (exactly-once) |
| 6 | Hostile session summary injected as bare system-role text | Prompt construction trusted memory | P1 | Fixed (quarantined as labelled untrusted data) |

## Changes Implemented (commits, in order)

1. `chore(config): document TokenRa OpenAI-compatible LLM provider option`
2. `feat(thursday): route morning briefing requests through the composed daily brief`
3. `docs(thursday): restore codebase map with current architecture ground truth` *(untracked by policy)*
4. `fix(thursday): route direct rain queries to weather and cover weather in the release corpus`
5. `test(thursday): pin injection resistance and receipt integrity; quarantine untrusted session summaries in brain prompts`
6. `fix(orchestrator): execute confirmed consequential actions exactly once without retry re-execution`
7. `perf(thursday): compose daily brief sources concurrently so latency tracks the slowest source`

## Before / After Results

| Metric | Before | After |
|---|---|---|
| Release gate accuracy | 99.41% (3 fails / 510) | **100%** (0 fails / 525) |
| Full Thursday suite | 479 pass / 1 fail | **518 pass / 0 fail** |
| Adversarial injection coverage | incidental only | 17 pinned cases, all pass |
| Receipt guarantees under test | indirect | 14 dedicated cases incl. concurrency |
| Duplicate-execution exposure on confirmed timeout | present | eliminated (test-pinned) |
| Brief composition vs slowest source | additive (sequential) | concurrent (live-measured 11.8s vs 12.6s source) |
| Brain context (codebase map) | silently empty | restored (94 lines) |

## Routing

Confusion-matrix style verification via the 708-case dev corpus + 525-case
release gate across 17 intent families. Weather family added (was absent).
Adversarial probes verified compound sentences ("even if it will rain…, show
overdue invoices") keep their real intent — guarded pattern blocks
subordinate-clause hijacks (10/10 probe cases pass).

## Permissions / Approvals / Action Receipts

- Fail-closed confirmed: unsafe dispatch without exact token is blocked;
  wrong-text/wrong-service/wrong-session tokens rejected; forged-token from
  foreign HMAC secret rejected (new tests).
- Receipts: claim idempotency, conflict rejection (text/service/session),
  session-scoped reads, single-completion with preserved first outcome,
  newest-first reporting, inclusive since-filter, 8-thread race → exactly one
  winner, concurrent completion → single shared outcome.

## Failure Recovery / Retries

Transient-only retry taxonomy preserved for read paths; consequential path
now executes once and reports honest failure; replayed confirmation after
failed attempt returns "already being processed" without re-execution
(test-pinned). No retry storms possible (max_attempts=2).

## Prompt Injection / Hallucination Resistance

- 7 payload families routed away from consequential intents by the
  deterministic layer.
- Brain output validation pinned: invented service IDs, kind misuse,
  non-dict steps, unknown agents → dropped before execution.
- Session-summary quarantine added (defence-in-depth; downstream validation
  remains the hard boundary).
- Hallucination posture: abstain-vs-answer split retained in chat_only mode;
  general-knowledge answered directly, unknown facts must say so (prompt
  contract verified textually; behavioural LLM eval deferred — needs provider).

## Morning Brief

Benchmark pins: full structure when healthy, per-section degradation shell
when every source dies, receipts surfaced with status, bounded 20-item agent
window (summary-not-dump property), interactive latency budget with stubbed
sources, concurrency property (slow source doesn't stack).

## Latency

- Deterministic routing: median 12.6 ms/case (release gate).
- Brief composition (real sources, loaded machine): business_status 12.6 s
  dominates; compose now ≈ max(sources) instead of Σ(sources).
- Known cost centre: `business_status` subprocess (~60 s worst case budget) —
  V2 candidate: persistent business-layer API call or cached status.

## Soak

5 × 525 read-only gate executions (2,625 total): zero failures, zero RSS
drift, stable latencies. A longer mixed-soak was planned but the machine hit
external load >200 (other programmes); deferred rather than measured under
invalid conditions.

## Regression Tests Added

`tests/thursday/test_thursday_prompt_injection.py` (17),
`tests/thursday/test_thursday_action_receipts.py` (14),
`tests/thursday/test_thursday_exactly_once.py` (2),
`tests/thursday/test_thursday_morning_brief_benchmark.py` (5),
+3 recovered handler-integration tests, +18 release-gate weather cases.

## Remaining Weaknesses

1. Two briefing implementations (legacy vs composed) — convergence debt.
2. `business_status` subprocess latency dominates every brief.
3. Behavioural LLM evaluation (grounding, concision, proactivity quality)
   requires a live provider — deterministic proxies only this session.
4. CODEBASE_MAP freshness relies on manual updates; untracked by policy.
5. Proactivity classification (interrupt/brief/weekly/log/ignore) exists as
   alerts pipeline but has no measurable false-positive benchmark yet.

## Gap to Thursday V2 / Jarvis-Like Target (Top 10)

| # | Gap | Current | Target | Severity | Effort |
|---|---|---|---|---|---|
| 1 | Company-state reasoning over structured goals/projects | brief reads status CLI only | retrieval over AI Platform state | high | L |
| 2 | Behavioural eval harness w/ live provider | none | grounded-response scoring | high | M |
| 3 | Briefing convergence (legacy vs composed) | two paths | one composer everywhere | med | S |
| 4 | Proactivity policy benchmarks | alerts only | interrupt/surface/log classes + FP rate | med | M |
| 5 | Business-status latency | subprocess 12–60 s | <1 s cached/API | med | M |
| 6 | Approval UX for multi-step plans | per-step pauses | batch approval with binding | med | M |
| 7 | Evidence typing (measured/retrieved/inferred) | implicit | tagged evidence in responses | med | M |
| 8 | Agent delegation observability | receipts basic | per-step traces + durations | low | S |
| 9 | Voice interruption architecture | workers exist | barge-in tested end-to-end | low | M |
| 10 | Context budget telemetry | ad-hoc trims | measured tokens/call | low | S |

## Scorecard (evidence-based)

INTENT 8 · ROUTING 9 · CONTEXT 7 · MEMORY 6 · GROUNDING 6 · COMPANY AWARENESS 5 ·
MULTI-STEP 7 · TOOL USE 8 · PERMISSION SAFETY 9 · APPROVAL SAFETY 9 ·
FAILURE RECOVERY 8 · PROACTIVITY 5 · RESPONSE QUALITY 6 · LATENCY 6 ·
OBSERVABILITY 7 · **OVERALL 7/10**

(Company awareness/proactivity/response-quality scored on deterministic
proxies only; behavioural LLM eval pending — hence not higher.)

## Recommended Engineering Priorities

1. Company-state retrieval layer feeding brief + Q&A (AI Platform contracts).
2. Behavioural qualification harness against a real provider (TokenRa/Ollama).
3. Briefing convergence + business-status caching.
4. Proactivity policy + false-positive benchmark.
5. Batch approvals for multi-step plans with exact-binding semantics.

## Commits / Pushes

Branch: `thursday/daily-brief-mvp` (tracks `origin/thursday/daily-brief-mvp`,
already authorised by prior pushes). Local commits listed above; push status
recorded in final status block.

## Production Mutation Check

SLO/KENN-product/website: untouched. Owner data: untouched. External writes:
none. Only Audio_Too mutated. Final full-suite re-run was blocked mid-flight
by external machine load (>200) — last complete full-suite result before the
load event: **518/518 green**; targeted suites re-verified green afterwards.
