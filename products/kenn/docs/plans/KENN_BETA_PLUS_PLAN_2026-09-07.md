# KENN Beta+ plan of action

**Date:** 2026-09-07

**Starting point:** supervised pilot ready; current live preflight 5/5; 590 tests passing

**Target:** a dependable, genuinely useful private beta that can survive repeated producer sessions and generate evidence strong enough for a qualified-beta decision

**Suggested duration:** 15 working days, followed by a seven-day soak/pilot window

## Progress

- **Slice 1 complete (2026-09-07):** the companion now takes a per-user,
  OS-held instance lock before index warmup, Mixing Doctor startup, or HTTP
  binding. A second launch exits with status 2 and allow-listed PID/start-time
  diagnostics without killing the owner. Kernel lock ownership recovers after
  crashes/termination, and stale metadata is safely overwritten. Six focused
  ownership/launcher tests and the 38-test server/diagnostics set pass. The
  complete repository suite passes **595 tests** with five dependency
  deprecation warnings.
- **Slice 2 harness complete (2026-09-07):** `scripts/soak_companion.py`
  now produces a bounded machine-readable health/latency/RSS/thread report for
  an already-running companion and fails closed on unhealthy samples or more
  than 128 MiB RSS growth. Deterministic pass/fail tests pass. A four-sample
  real smoke against Ableton-connected KENN passed with five threads, zero RSS
  growth, and 22.008 ms median health-sample latency. The required 24-hour run
  remains pending and must not be inferred from this short smoke.
- **Slice 3 framework complete (2026-09-07):** real-mix intake, packet
  generation, independent reviewer templates, and fail-closed aggregation now
  exist in `scripts/evaluate_real_mix_corpus.py`. Intake verifies consent,
  rights basis, path containment, and audio hashes while emitted packets omit
  audio and filesystem paths. Qualification requires 12+ cases, two distinct
  reviewers, 90% evidence correctness, 85% useful ratings, and at most 10%
  recorded false positives. Five focused boundary/threshold tests pass; the
  complete repository suite passes **602 tests** with five dependency
  deprecation warnings. Actual qualification remains pending consented audio
  and genuine human scores.
- **Slice 4 diagnostics complete (2026-09-07):**
  `scripts/build_support_bundle.py` creates an owner-only ZIP containing a
  second allow-listed projection of support health, up to 100 lifecycle-event
  statuses, source revision, and per-file hashes. It copies no raw logs and
  excludes audio, prompts, session IDs, names, targets, error text, paths, and
  confirmation material. Three bundle tests plus the existing diagnostic tests
  pass. A real Ableton-connected smoke produced a three-file mode-0600 archive;
  inspection found only the documented lifecycle keys. The complete repository
  suite passes **605 tests** with five dependency deprecation warnings.
- **Slice 5 reconnect-safe device undo complete (2026-09-07):** device-
  parameter undo now proves that the current device identity, parameter
  identity, and value still match the original verified readback before it
  creates an inverse proposal. A journal-restored receipt can issue a fresh
  process-bound confirmation and complete a verified undo after restart when
  Live is unchanged; a later edit made while KENN is disconnected is refused
  without sending a write. The focused recovery set passes 41 tests and the
  complete repository suite passes **607 tests** with five dependency
  deprecation warnings.
- **Slice 6 interrupted-write reconciliation complete (2026-09-07):** the
  shared track, transport, scene, clip, and send execution boundary no longer
  treats a thrown or missing transport acknowledgement as proof of failure.
  It performs authoritative readback, accepts the action only when the exact
  requested state is observed, labels it `unacknowledged_write_reconciled`,
  and consumes the confirmation/idempotency key. If readback cannot prove the
  state, the receipt is non-success and `requires_inspection`; blind replay is
  still refused. Bounded journal rows retain only the acknowledgement class
  and retry classification, not raw transport errors. The focused service,
  command, HTTP, and journal integration set passes 128 tests; the complete
  repository suite passes **609 tests** with five dependency deprecation
  warnings.
- **Slice 7 recipe disconnect and recovery complete (2026-09-07):** every
  attempted recipe step now retains enough exact state to reconcile a lost
  acknowledgement or participate in compensating rollback after a readback
  disconnect. Verified readback permits an applied-but-unacknowledged step to
  continue; unavailable or mismatched readback aborts the recipe and restores
  all attempted steps in reverse order. Failed recipes now emit a typed
  receipt distinguishing `failed_rolled_back` from `partial_recovery`, with
  the latter explicitly requiring inspection when any compensating write
  cannot be verified. Deterministic tests prove successful reconciliation,
  reverse-order restoration after a transient disconnect, and honest partial-
  recovery reporting when rollback itself fails. The focused command, HTTP,
  MCP, and journal set passes 128 tests; the complete repository suite passes
  **611 tests** with five dependency deprecation warnings.
- **Slice 8 reconnect-aware soak gate complete (2026-09-07):** the companion
  soak report now counts observed Ableton disconnect and reconnect transitions,
  measures the longest sampled outage, and records whether Live is connected
  at the final sample. Qualification can require a minimum reconnect count, a
  maximum outage duration, and a connected final state. The documented 24-hour
  procedure requires one operator-induced Live close/open cycle while the
  harness remains observation-only and performs no unattended mutations. Four
  deterministic harness tests pass; the complete repository suite passes
  **613 tests** with five dependency deprecation warnings. The actual 24-hour
  run remains pending.
- **Slice 9 honest chat benchmark foundation complete (2026-09-07):** the
  128-case public chat evaluator now enforces corpus assertions that were
  previously present but silently skipped: any-of answer terms, expected
  topics and routes, minimum source quality, and weak-match behavior. Failures
  are separated into behavior, retrieval, and answer dimensions so ranking
  misses are no longer conflated with response-content misses. Engine-only
  grounding and answer-quality assertions are explicitly counted as
  unobserved at the reduced public boundary instead of being implied as tested.
  All 128 real-index cases pass the stricter evaluator, and an adversarial
  evaluator test proves every dimension fails independently when corrupted.
  The complete repository suite passes **614 tests** with five dependency
  deprecation warnings.
- **Slice 10 engine hard-case benchmark complete (2026-09-07):**
  `scripts/evaluate_chat_hard_cases.py` now qualifies the existing corpus cases
  that carry internal grounding or answer-quality requirements. It enforces
  grounding mode, minimum grounding score, minimum answer-quality score, and
  the engine self-check while leaving public abstention cases to the public
  boundary suite. Receipts are tied to the corpus SHA-256 and retain IDs,
  scores, latency, and failures but no question, answer, or source text. The
  current real-index run passes **15/15** cases at 506.817 ms median and
  862.655 ms maximum latency, bound to corpus hash
  `8f219e2215bdd9376483237105931307a48dd3631dd55fe270eef6414d449a5f`.
  The complete repository suite passes **616 tests** with five dependency
  deprecation warnings.
- **Slice 11 retrieval baseline and mode gate complete (2026-09-07):**
  `scripts/evaluate_retrieval_modes.py` now measures retrieval independently
  from generated answer quality on 58 corpus cases with explicit expected
  sources. Results are bound to corpus hash and active index version while
  excluding question and source text; personal feedback boosts are disabled
  for reproducibility. On index `v-0af833f62d00`, current hybrid retrieval
  improves over BM25: top-1 **72.41% vs 68.97%**, recall@4 **89.66% vs
  87.93%**, and MRR **0.7960 vs 0.7716**. Median latency is 48.799 ms versus
  39.969 ms (8.830 ms cost). The learned reranker remains disabled and is not
  deployable because its model artifact is absent; no improvement is inferred.
  The complete repository suite passes **617 tests** with five dependency
  deprecation warnings.
- **Slice 12 retrieval hard-case improvement complete (2026-09-07):** the
  benchmark now measures unique source rank rather than allowing repeated
  chunks from one document to crowd the expected-source metric, and correctly
  requires every source in multi-source fixtures. Production reranking adds a
  bounded boost only when at least two exact query tokens match a source's
  title identity, plus explicit canonicalization for the observed
  `sidechane`/`bas`/`kik` typo case. On all 58 fixed fixtures, hybrid recall@4
  improves from **94.83% to 100%**, top-1 from **72.41% to 75.86%**, and MRR
  from **0.8366 to 0.8736**, with no remaining hybrid misses. The stricter
  128-case public benchmark and 15-case engine hard-case benchmark remain
  green, and focused regression coverage proves the typo/title behavior. The
  complete repository suite passes **619 tests** with five dependency
  deprecation warnings.
- **Slice 13 qualified-release evidence enforcement complete (2026-09-07):**
  the qualified profile now requires the engine hard-case and retrieval-mode
  benchmarks to run successfully against the same corpus hash, a qualifying
  24-hour companion receipt containing at least one observed Ableton reconnect
  and a connected final state, and a qualifying consented real-mix receipt
  proving at least 12 cases and two independent reviewers. These requirements
  were previously documented but not executable release gates. Seven focused
  gate tests cover explicit execution, corpus mismatch, short/reconnect-free
  soaks, and valid/insufficient real-mix receipts. The qualified profile now
  had **10 required gates** at this slice; missing external evidence remained visibly pending.
  The complete repository suite passes **626 tests** with five dependency
  deprecation warnings.
- **Slice 14 bounded-state soak telemetry complete (2026-09-07):** the health
  endpoint now exposes counts and hard limits only—not content—for pending Live
  proposals, action receipts, and local Mix Review records. The soak harness
  records start, end, growth, maximum, and limit for each state family on every
  run, and fails closed if telemetry disappears or a bound is exceeded. The
  action-service proposal cache now enforces its previously implied 10,000-row
  cap, while the planner retains its separate 1,000-row cap. Focused soak,
  server, Live-action, command, and planner coverage passes **140 tests**. A real runtime
  sample was unavailable because no companion was listening on port 8090; no
  live evidence is inferred from unit coverage. The complete repository suite
  passes **628 tests** with five dependency deprecation warnings.
- **Slice 15 real-mix qualification integrity complete (2026-09-07):** intake
  now rejects empty or malformed human ground truth and records whether the
  corpus spans vocals, drums, bass, dense electronic, and sparse acoustic
  material. Scoring recomputes that coverage from packet cases, requires every
  engine analysis to complete, and requires reviewers to score evidence,
  usefulness, severity ordering, and abstention. Qualification thresholds now
  include at least 85% correct severity ordering and abstention in addition to
  the existing evidence/usefulness/false-positive thresholds. The preparation
  command can emit two separately labelled, packet-bound reviewer forms in one
  operation. The qualified release gate checks the expanded receipt contract.
  Focused evaluation/release coverage passes **36 tests**; the complete
  repository suite passes **633 tests** with five dependency warnings. Real
  qualification remains pending consented audio and genuine independent human
  scores; none are fabricated by this framework.
- **Slice 16 session-grounded advice benchmark complete (2026-09-07):**
  `scripts/evaluate_session_grounded_advice.py` now exercises the real
  retrieval answer path against six fixed synthetic Live snapshots. Four
  single-role cases require exact observed track name/index/device evidence
  plus the expected approved knowledge source; offline and multi-role cases
  require KENN to omit session evidence rather than guess. Every attached Live
  fact must appear under the explicit “observed just now, not inferred” label.
  Receipts retain case IDs and counts but no questions, answers, or Live names.
  A corrupted answerer fails all six fixtures. The qualified intelligence gate
  now runs this benchmark alongside the 15 engine hard cases and 58-case
  retrieval comparison; the actual combined gate passes **15/15**, **100%
  hybrid recall@4**, and **6/6** respectively. The complete repository suite
  passes **635 tests** with five dependency warnings. Synthetic snapshots test
  evidence separation, not current Live connectivity or musical usefulness.
- **Slice 17 exact release provenance gate complete (2026-09-07):** the
  qualified report now contains a structured `kenn.release_provenance.v1`
  envelope and an explicit eleventh gate. It binds the exact Git commit,
  validated active index version/content/chunk count, MiniLM model and tokenizer
  hashes, plug-in archive checksum, and every qualified Live/OS/architecture/
  bridge configuration. Every active index artifact is rehashed. Qualification
  fails if an artifact or model is tampered with, or if the unqualified LLM
  rewrite is enabled; it remains pending when an identity is unavailable. On
  the current repository, source/index/model/Live identities verify and the gate
  is pending only for the absent signed plug-in archive. Two focused tests prove
  complete binding and hard-failure behavior. The qualified profile now has
  **11 required gates**; the supervised pilot profile remains unchanged. The
  complete repository suite passes **638 tests** with five dependency warnings.
- **Slice 18 supervised-pilot evidence gate complete (2026-09-07):** the
  ten-session/three-project Beta+ criterion is now machine-enforced rather than
  represented only by a Markdown checklist. A privacy-safe JSON log records a
  unique run ID, hashed project pseudonym, exact candidate commit and support
  configuration, complete preflight, operation/readback/undo accounting, five
  zero-tolerance safety counters, and tester sign-off. The aggregator rejects
  stale revisions, unsupported configurations, duplicate runs, incomplete
  readback or undo, any unauthorized mutation/false success/lost undo/crash/
  unrecoverable state, and fewer than ten sessions or three projects. Its
  receipt is bound to the exact support-matrix hash. The qualified profile now
  has **12 required gates**; actual pilot evidence remains pending real signed-
  off sessions and is not inferred from tests. Five focused tests cover the
  passing aggregate, safety incidents, revision/undo mismatches, zero-activity
  rejection, and release-gate binding. The complete repository suite passes
  **643 tests** with five dependency warnings.
- **Slice 19 optional MiniMax Phase A boundary complete (2026-09-07):** KENN
  now has provider-neutral v1 request/result contracts, an honest structured-
  caption builder that preserves unknown musical attributes, and a disabled-
  by-default `MiniMaxMusic3Backend` with an injected transport. The adapter
  accepts only bounded non-streaming WAV results, verifies WAV metadata and
  requested duration, hashes the bytes, and labels provider/model/generated
  provenance. It rejects a provider/configuration revision mismatch and adds
  no network client, model weights, startup dependency, or Live mutation surface.
  Ten mocked tests cover bounds, forged requests, disabled operation, valid
  output, malformed responses, revision mismatch, and timeout failure. Real
  inference and tester enablement remain blocked on the Phase B external
  qualification. The complete repository suite passes **653 tests** with five
  dependency warnings.
- **Slice 20 packet-bound human-review thresholds complete (2026-09-07):** the
  qualified gate no longer permits a validly bound adjudicator approval to
  override poor reviewer scores. The 100-case packet now binds an 85% overall
  combined-score floor, 90% floors for technical correctness, evidence use,
  safety, and overclaiming control, and a 75% floor for every represented
  category. The adjudicator reports each threshold result, and the release
  gate requires all of them in addition to complete independent scoring and an
  explicit approval. Threshold changes alter the packet hash and invalidate
  stale forms. Two focused tests cover quantitative pass/fail reporting and
  the formerly possible all-zero-scores-plus-approval bypass. The complete
  repository suite passes **655 tests** with five dependency warnings.
- **Slice 21 real-mix receipt hardening complete (2026-09-07):** real-mix
  packets and results now carry the exact Mix Review engine SHA-256, and the
  qualified gate requires it to match the current engine. The gate explicitly
  requires evidence correctness, usefulness, severity ordering, abstention,
  and false-positive threshold flags and independently checks their metrics;
  a forged top-level `qualified: true` can no longer bypass a failed core
  quality criterion. One new adversarial release-gate test plus strengthened
  evaluator assertions cover the boundary.
  The complete repository suite passes **656 tests** with five dependency
  warnings.
- **Slice 22 soak receipt hardening complete (2026-09-07):** the 24-hour soak
  receipt now records the exact Git revision, and the qualified gate requires
  it to match HEAD. The gate independently validates all sampled timestamps
  and their cadence, every sample's health/error/runtime-state
  fields, zero summarized errors, bounded RSS and runtime registries, the
  required reconnect and maximum-outage policy, and connected final Live state.
  A new adversarial test proves that a forged `qualified: true` receipt with an
  unhealthy middle sample fails. The complete repository suite passes **657
  tests** with five dependency warnings.
- **Slice 23 human-review packet freshness gate complete (2026-09-07):** the
  qualified gate now validates packet generator and question-corpus hashes,
  exact active index/model identity, source ancestry, and the absence of any
  post-generation change to answer-engine inputs before it asks for reviewer
  files. The stale packet was rebuilt from `9122b65`: all 100 case IDs remained
  stable, while 40 answer payloads legitimately changed from the superseded
  `87eae23` engine snapshot. Review fields are blank and old forms are invalid
  by packet hash. One adversarial test proves stale provenance fails before
  reviewers spend time on it. The complete repository suite passes **658
  tests** with five dependency warnings.
- **Slice 24 exact-archive clean-host evidence complete (2026-09-07):** the
  existing distribution gate now requires a machine-readable host-validation
  receipt after local Developer ID, notarization, stapling, and Gatekeeper
  checks pass. The receipt binds the exact archive SHA-256 and Git revision and
  requires a clean local account or second Mac, AU and VST3 validator success,
  Ableton discovery for both formats, rollback verification, a non-future
  timestamp, and tester sign-off. A privacy-safe template is included. Local
  cryptographic checks alone now remain pending rather than overstating
  clean-host compatibility; one new focused test covers that state. The
  complete repository suite passes **659 tests** with five dependency warnings.
- **Slice 25 receipt-bound supervised-pilot sessions complete (2026-09-07):**
  every qualifying session now requires a hashed tester pseudonym and a unique
  sibling privacy-safe support bundle. The evaluator verifies the bundle hash,
  exact allow-listed file set, support-bundle schema, lifecycle-event integrity
  hash, and enough events for all declared mutations and undos. Aggregate
  metrics expose tester and bound-receipt counts without identities or paths;
  revision-scoped opaque grouping commitments permit independent count checks
  without retaining raw project/tester hashes. The release gate cross-checks
  one distinct evidence bundle and one passing row per counted session. The support-bundle command can now filter
  receipts by local session ID without persisting that ID. Two new focused
  tests cover missing/reused evidence and safe session-filter URL construction.
  The complete repository suite passes **661 tests** with five dependency
  warnings.
- **Slice 26 pilot-evidence replay resistance complete (2026-09-08):** pilot
  qualification now counts uniquely identified, verified lifecycle receipts,
  rather than merely counting differently packaged support ZIP files. Reusing
  the same event payload, duplicating receipt IDs across sessions, or supplying
  unverified events fails qualification. The aggregate receipt is also bound
  to the exact pilot evaluator source, and the release gate recomputes that
  identity. The current release-scoped suite passes **900 tests** with five
  skipped and four dependency warnings.
- **Slice 27 real-mix review provenance complete (2026-09-08):** real-mix
  scoring now requires distinct reviewer slots, validates false-positive and
  missed-family lists, retains anonymous SHA-256 identities for both exact
  reviewer files, and binds the aggregate to the evaluator implementation.
  The release gate recomputes the evaluator hash and rejects missing,
  malformed, or duplicate reviewer evidence. The current release-scoped suite
  passes **901 tests** with five skipped and four dependency warnings.
- **Slice 28 independent-review role binding complete (2026-09-08):** the
  human-review adjudicator now requires the exported form schema and exact
  `a`/`b` reviewer slots, preventing copied or swapped forms from passing under
  renamed identities. Final approval must name an adjudicator and explicitly
  confirm that disagreements were reviewed, in addition to the existing exact
  packet/reviewer hashes and quantitative thresholds.
- **Slice 29 plug-in archive extraction and identity boundary complete
  (2026-09-08):** the distribution gate now bounds compressed size,
  uncompressed size, and member count before extraction; rejects duplicate,
  encrypted, traversal, and symbolic-link members; proves AU and VST3 bundles
  share one Developer Team; and requires the clean-host receipt to name that
  same team. The release-scoped suite passes **902 tests** with five skipped
  and four dependency warnings.
- **Slice 30 real-Live lifecycle evidence completeness complete
  (2026-09-08):** the qualified gate now requires non-empty session and task
  identities, a real plan and proposal, unique write/undo receipt IDs, valid
  SHA-256 snapshot fingerprints, and one complete ordered lifecycle from
  initial context through verified undo and final context. Initial and final
  event records must independently bind the same connected Live session and
  exact fingerprints as the top-level receipt. Missing, duplicated, reordered,
  or unbound evidence can no longer qualify through empty-value equality or
  generic success flags. The release-scoped suite passes **903 tests** with
  five skipped and four dependency warnings.
- **Slice 31 action-bound real-Live receipts complete (2026-09-08):** the
  qualification runner now accepts verified write and undo receipts only when
  each receipt identifies the exact forward or inverse proposal that produced
  it. The release gate independently reconstructs and validates the recorded
  model plan, proposal, applied result, task completion, replay rejection,
  inverse proposal, and undo result; event receipts must equal the top-level
  receipts and retain the correct action identities. Two adversarial runner
  cases prove that unrelated verified receipts fail without preventing exact
  restoration. The release-scoped suite passes **905 tests** with five skipped
  and four dependency warnings.
- **Slice 32 source-attested real-Live lifecycle complete (2026-09-08):** the
  real-Live runner now records the exact Git revision and its own SHA-256 in
  every proposal-ready or completed lifecycle receipt. The qualified gate
  requires both identities to match the current release candidate and current
  runner, preventing an otherwise valid old Live session from being replayed
  after behavior or verification code changes. Adversarial checks cover stale
  commits and modified runner identity. The release-scoped suite remains green
  at **905 tests** with five skipped and four dependency warnings.
- **Slice 33 source-bound real-mix review complete (2026-09-08):** real-mix
  packet preparation now records the exact KENN Git revision before human
  scoring begins. Scoring rejects a packet from any other revision and carries
  the same identity into the privacy-safe aggregate receipt; the qualified gate
  independently requires that revision plus a valid packet hash to match the
  current candidate. This keeps expensive reviewer evidence attached to the
  exact analysis implementation and dependencies that produced it. The
  release-scoped suite passes **906 tests** with five skipped and four
  dependency warnings.
- **Slice 34 independently verified soak receipts complete (2026-09-08):**
  both partial checkpoints and final soak receipts now attest the exact harness
  SHA-256. Qualification requires the current source and harness, a complete
  expected sample set with sequential indices, local companion endpoint and
  valid process identity, and real per-sample latency/RSS/thread/Live-state
  telemetry. It independently recomputes memory growth, maximum threads,
  disconnects, reconnects, outage duration, and final connectivity instead of
  trusting summary claims; legacy summary-only receipts no longer pass. The
  release-scoped suite remains at **906 tests** with five skipped and four
  dependency warnings.
- **Slice 35 cold/steady Mix Review latency separation complete
  (2026-09-08):** the synthetic qualification benchmark now measures the
  one-time numerical/audio-stack cold start explicitly and includes it in the
  unchanged 500 ms maximum ceiling. The unchanged 100 ms mean ceiling applies
  to the full repeated case set after initialization, preventing test order
  and SciPy startup from being conflated with steady analysis latency. The
  report exposes cold, steady mean, and cold-inclusive maximum values; neither
  release threshold was relaxed.
- **Slice 36 transient memory-spike soak gate complete (2026-09-08):** the
  soak harness now records peak RSS and peak growth in addition to start/end
  growth. Both the harness and release gate fail when any sampled transient
  spike exceeds the unchanged 128 MiB allowance, even if memory returns to its
  starting level before the run ends. The gate recomputes both peak values from
  raw samples, preventing summary-field substitution. The release-scoped suite
  passes **907 tests** with five skipped and four dependency warnings.
- **Slice 37 transient thread-leak soak gate complete (2026-09-08):** the
  harness now records starting, ending, maximum, and peak-growth thread counts
  and fails above the explicit eight-thread growth allowance. The release gate
  recomputes each value from raw samples, so a temporary thread leak cannot be
  hidden by returning to baseline before the final sample. Operator docs now
  state that only complete current-source/current-harness receipts qualify;
  older diagnostic soaks remain informative but cannot be promoted. The
  release-scoped suite passes **908 tests** with five skipped and four
  dependency warnings.
- **Slice 38 independently recomputed pilot aggregates complete
  (2026-09-08):** supervised-pilot rows now carry revision-scoped opaque
  project, tester, and receipt buckets. They cannot be correlated across
  release revisions and do not expose original pseudonym hashes or evidence
  paths, but allow the qualified gate to independently recompute unique
  sessions, projects, testers, bound receipts, and passing-session totals. The
  gate also enforces the complete privacy declaration, preventing forged
  aggregate counts or silently weakened privacy claims from qualifying. The
  release-scoped suite remains at **908 tests** with five skipped and four
  dependency warnings.
- **Slice 39 realtime review reasoning surface complete (2026-09-09):** the
  existing read-only `/api/plugin-live-review` receipt is now exposed to MCP
  reasoning clients as `live_plugin_review`. The tool preserves the validated
  plug-in-bus scope, bounded trend, freshness/expiry, advisory-only status,
  and `capture_requested: false` boundary; missing or expired context is not
  converted into a measurement. It opens no OSC socket and requests no new
  capture. Focused MCP/server/plugin-handoff coverage passes **108/108**; the
  active companion and 8-hour soak were not restarted.
- **Slice 40 opt-in realtime context integration complete (2026-09-09):**
  `kenn_context` and `kenn_session_intelligence` now accept an explicit
  `plugin_session_id` and carry the already-validated plug-in bus frame,
  pink-noise-style evidence, bounded trend, and freshness receipt into the
  read-only planning/intelligence output. The fetch is opt-in, adds no OSC
  socket or capture request, and missing context remains an explicit
  limitation. Focused MCP/context/intelligence/plugin-handoff coverage passes
  **128/128**; the active companion and 8-hour soak were not restarted.
- **Slice 41 exact device comparison complete (2026-09-09):** MCP now exposes
  `compare_live_devices` as a read-only diagnostic. It binds both devices to
  one fresh topology snapshot, verifies parameter identities, matches exact
  parameter names with duplicate-name handling, and reports raw-value deltas
  while keeping unmatched controls explicit. It makes no sonic-quality claim
  and never authorizes a Live write. Focused MCP/context coverage passes
  **89/89**; the active companion and 8-hour soak were not restarted.
- **Slice 42 planner unit-conversion parity complete (2026-09-09):** the
  lower-level `LiveControlPlanner.parse_and_propose()` path now applies the
  same evidence-backed display-to-raw conversion as the main command resolver
  for qualified percentage, millisecond, and ratio controls. Natural-language
  planning therefore remains consistent for requests such as Hybrid Reverb
  Dry/Wet at 25%, while unverified discrete display values still fail closed
  before proposal creation. Focused planner/unit/stress coverage passes
  **16/16**; no Live process was restarted or mutated.
- **Slice 43 retrieval source selection complete (2026-09-09):** narrow
  questions now receive a bounded exact-term contribution from note bodies,
  retain a materially relevant note from a distinct source before generic
  manual context, and surface a near-ranked authoritative measurement note
  when present. Four held-out source-selection misses now pass, including
  reamping, converter-input clipping, arrangement masking, and ITU true-peak
  grounding. Focused retrieval/knowledge evaluation coverage passes **4/4**;
  no external data or runtime state was changed.
- **Slice 44 one-call realtime mix advice complete (2026-09-09):** the
  read-only MCP knowledge question and HTTP endpoint now accept an explicit
  `plugin_session_id`, fetch only the latest validated plug-in bus receipt,
  and carry its pink-noise-style measurement into the deterministic answer
  path. KENN can therefore explain a measured band/deviation and suggest a
  listening check in one reasoning call, while preserving the no-capture,
  no-track-attribution, and no-automatic-EQ boundaries. New MCP forwarding and
  standalone handoff-to-answer coverage passes **5/5**; no Live state or
  external data was changed.

## Product thesis for this phase

KENN should become excellent at four things before its surface area grows:

1. understanding the current Ableton session;
2. giving grounded, musically useful production advice;
3. proposing and safely applying a bounded set of reversible changes;
4. learning from structured evaluation without training on private user audio.

The companion UI is owned by a colleague and is explicitly outside this plan.
This phase owns backend contracts, intelligence, reliability, evaluation,
packaging, diagnostics, and evidence supplied to the UI.

## Definition of Beta+

Beta+ is reached only when all of the following are true:

- The qualified gate passes 14/14, including supervised-pilot evidence, exact release provenance,
  intelligence benchmarks, a
  reconnect-aware 24-hour soak, consented real-mix evaluation, independent
  human review, and a
  Developer ID-signed, notarized, stapled, Gatekeeper-accepted plug-in archive.
- Ten supervised sessions across at least three real projects complete without
  an unauthorized mutation, false success receipt, lost undo, or companion
  crash.
- KENN's advice meets the human-review thresholds on the bound 100-case packet
  and a smaller consented real-mix listening set.
- A 24-hour companion soak shows bounded memory/state growth and clean recovery
  from Live restarts, network loss, and a second-instance launch.
- Every beta claim is tied to machine-readable evidence and an exact source,
  model, index, plug-in, Live, and OS version.

## Workstream 1 — close release qualification

**Priority:** P0

**Window:** days 1–5, with external inputs scheduled immediately

### Actions

1. Recruit two independent reviewers who did not write the answers or the
   evaluation tooling.
2. Give each reviewer one separately exported, packet-bound score file and the
   rubric; prevent access to the other reviewer's scores until submission.
3. Run the existing adjudication tool, inspect every disagreement, and bind the
   final decision to the exact packet and both reviewer hashes.
4. Obtain/install a Developer ID Application certificate and configure an
   `xcrun notarytool` keychain profile outside the repository.
5. Run the fail-closed package pipeline, then test the archive from a clean
   macOS user account or second Mac rather than only the build machine.
6. Rerun the qualified profile from a clean commit with current Live attached.

### Exit gate

- Human-review gate passes with no missing scores and explicit adjudication.
- Archive checksum, signing chain, notarization ticket, stapling, Gatekeeper,
  AU validation, VST3 validation, and clean-machine Ableton discovery all pass.
- `qualify_internal_beta.py --profile qualified` returns 14/14 with no pending or
  failed required gate.

## Workstream 2 — prove musical usefulness on real material

**Priority:** P0

**Window:** days 1–10

Synthetic correctness is strong; the largest product risk is now advice that
is technically grounded but not useful in an actual mix.

### Actions

1. Build a consented evaluation set of 12–20 short mix excerpts or stems,
   covering at least vocals, drums, bass, dense electronic material, and sparse
   acoustic material. Keep source audio out of Git.
2. Create privacy-safe ground truth: engineer observations, confidence,
   acceptable alternatives, intentionally unscored subjective choices, and
   before/after references where rights permit.
3. Evaluate Mix Review for false positives, missed issues, severity ordering,
   evidence correctness, usefulness, and abstention—not just detector accuracy.
4. Add session-aware question cases that require KENN to combine Live state
   with retrieved knowledge while clearly separating observed facts from
   general advice.
5. Turn every reproducible miss into a fixture before changing heuristics,
   retrieval, prompts, or thresholds.

### Exit gate

- Zero fabricated measurements or Live-state claims.
- At least 90% evidence correctness and 85% reviewer-rated usefulness on the
  agreed objective/diagnostic subset.
- False-positive rate at or below 10% for qualified fault families.
- Subjective or unsupported questions abstain or present options rather than a
  false single answer.

## Workstream 3 — production reliability and observability

**Priority:** P0

**Window:** days 3–10

### Actions

1. Add a single-instance companion lock or explicit startup refusal before UDP
   11001 is contested. Include the owning PID/start time in local diagnostics
   when safely available; never terminate another process automatically.
2. Add a 24-hour soak harness that samples resident memory, thread count,
   proposal count, review-registry size, request latency, and OSC reconnects.
3. Exercise Live closed/open/restart, companion restart, stale confirmation,
   duplicate confirmation, interrupted write, failed readback, and undo after
   reconnect.
4. Add structured local event IDs for proposal, confirmation, execution,
   readback, undo, and recovery so a support log can reconstruct one operation
   without retaining user audio or full prompt content.
5. Add a one-command privacy-safe diagnostic bundle with secrets, absolute user
   paths, lyrics, filenames, and project names redacted by default.

### Exit gate

- Second companion launch fails clearly before serving a misleading partial
  state.
- No unbounded growth or material memory leak during the 24-hour soak.
- All injected failures yield non-success receipts and no unverified mutation
  is reported as successful.
- Diagnostic bundle is sufficient to identify the failing subsystem without
  exposing project content.

## Workstream 4 — deepen the safe Ableton capability set

**Priority:** P1

**Window:** days 6–12

### Actions

1. Analyse pilot requests and select only the five most valuable unsupported
   operations; do not expand from an arbitrary feature list.
2. Prefer operations that compose existing typed primitives, such as gain
   staging across selected tracks, comparing two device settings, or applying
   a bounded multi-step recipe.
3. Require target identity, before values, session version, confirmation,
   ordered execution, per-step readback, compensating rollback, and one receipt
   for every recipe.
4. Test ambiguity around duplicate track/device names, racks, groups, disabled
   devices, automation, parameter units, and changed state between proposal and
   confirmation.
5. Keep clip deletion, file overwrite, project save, flatten/freeze, and broad
   autonomous mixing outside the beta boundary.

### Exit gate

- Each promoted operation has unit, adversarial, integration, and real-Live
  evidence on the supported configuration.
- A failed step cannot leave an unexplained partially applied recipe.
- No new operation bypasses the shared proposal/confirmation/readback/undo
  contract.

## Workstream 5 — improve KENN's reasoning and retrieval

**Priority:** P1

**Window:** days 6–13

### Actions

1. Use human-review disagreements and real-session misses to create a compact
   hard-case benchmark for routing, retrieval, citation, and abstention.
2. Add evidence-class and confidence metadata to approved notes, prioritising
   notes used by the hard-case benchmark instead of mechanically backfilling
   the whole corpus first.
3. Introduce answer-level support checks: every technical recommendation must
   map to retrieved text or an explicitly measured/session-observed fact.
4. Measure retrieval quality separately from answer quality so ranking failures
   are not confused with generation failures.
5. Compare the current hybrid retriever with candidate rerankers under fixed
   fixtures; deploy only a measurable improvement with bounded latency and a
   deterministic fallback.

### Exit gate

- No regression on the existing bound packet or abstention suite.
- Hard-case retrieval improves against a recorded baseline.
- Citation-support checks reject intentionally fabricated and weakly supported
  answers.
- Median local answer latency remains inside the agreed pilot budget.

## Workstream 6 — optional MiniMax Music 3 experiment

**Priority:** P2; start only after P0 gates are stable

**Window:** days 11–15

MiniMax should accelerate a future creative workflow, not distract from KENN's
core reliability or become a plug-in dependency.

### Actions

1. Implement provider-neutral `audio_generation_request.v1` and
   `audio_generation_result.v1` contracts with strict duration, format,
   provenance, timeout, and artifact-size bounds.
2. Build a disabled-by-default MiniMax backend using an injected HTTP client
   and mocked responses; do not download weights into this repository.
3. Implement KENN's typed structured-caption builder while preserving unknown
   BPM, key, instrumentation, and vocal identity instead of inventing them.
4. Hash and analyse returned WAVs, label them as generated, and keep them
   separate from user-source and measured-evidence artifacts.
5. Allow Live import only through a new confirmation-gated proposal with exact
   destination, readback, receipt, and undo.
6. Do not enable the provider for testers until a pinned CUDA service, license
   review, attribution requirement, content safeguards, and listening test are
   complete.

### Exit gate

- Mocked adapter and artifact-boundary tests pass with the provider disabled by
  default.
- Provider failure cannot alter Live, block core KENN startup, or corrupt a
  user artifact.
- A separate go/no-go record decides whether real inference is worth operating.

## Execution order

```text
Days 1–5    Human review + signing inputs + real-material corpus setup
Days 3–10   Reliability, singleton startup, soak and failure injection
Days 1–10   Real-mix/session usefulness evaluation and regression fixtures
Days 6–12   Five evidence-driven Ableton capability promotions
Days 6–13   Retrieval/reasoning improvements from measured failures
Days 11–15  Optional MiniMax dry-run adapter
Days 16–22  Supervised pilot/soak window and final qualified gate
```

Workstreams may overlap, but their release gates do not. A new feature cannot
compensate for a failed safety, evaluation, signing, or human-review gate.

## Slice 45 — repeat sample-import lookup latency

The vendored AbletonOSC browser search now keeps a bounded, process-local cache
of exact path-to-item matches. A cached match is accepted only when its current
URI still reconstructs to the requested path and the item remains a loadable
non-folder; otherwise the cache is discarded and the existing bounded
depth-first browser walk is used. This is a performance improvement for repeat
lookups in large libraries, not a completeness claim: the containing folder
still must be an Ableton Place, and the normal KENN confirmation, empty-slot
guard, readback, receipt, and undo boundaries remain unchanged.

Exit evidence: **10/10** vendored browser-search tests pass, including cache
reuse and invalid-cache fallback. Real-Live requalification is intentionally
deferred until the active companion soak completes, because the Remote Script
must be reloaded to exercise the new code.

## Slice 46 — natural-language command coverage

The deterministic intent layer now covers the measured misses in the synthetic
command corpus: bounded spoken numeric values, ordinal track references, named
track focus, short EQ-band phrasing, and a trailing device-setup clause. These
forms resolve to the same typed, confirmation-gated plans as their existing
digit/numbered equivalents. The change does not infer a target from an absent
snapshot, widen the mutation allowlist, or bypass proposal/readback safety.

Exit evidence: the corpus audit reaches **30/30 (100%)** parser-contract
matches, with holdout protection and label validation passed; focused intent,
command, and prompt-boundary coverage passes **187/187**. The corpus remains
synthetic training material and is not a real-session quality claim.

## Slice 47 — GPU planner comparison and non-promotion

The existing shared-host Qwen3-4B inference service was reused for a complete
three-repeat comparison across both sealed planner suites. The result is
recorded as a model-selection finding, not a release receipt: the model scored
4/10 on every normal repeat and 6/12 on every adversarial repeat, with mean
pass-rate/score 0.45, minimum contract validity 0.40, and minimum safety rate
0.60. It is not eligible for promotion. Because this run used the older
Ollama-shaped runner, it does not replace the prior input-bound V6 evidence;
the release artifact was restored after inspection. No shared GPU service was
started, stopped, or restarted.

## Slice 48 — combined Mix Review and realtime bus guidance

The MCP `mix_review_recommendations` tool now accepts an optional explicit
`plugin_session_id`. It can include the latest already-captured and validated
plug-in bus observation as a separately labelled advisory recommendation,
while preserving uploaded/rendered findings as a distinct evidence class. A
realtime recommendation is emitted only when the bounded pink-noise-style
comparison has a sufficiently large measured deviation; it never infers a
responsible track/device, requests a new capture, or creates a master-EQ
mutation.

Exit evidence: focused MCP, plug-in handoff, session-intelligence, and
evidence coverage passes **95/95**, including the no-OSC/no-mutation boundary.

## Slice 49 — typed realtime evidence for knowledge answers

The one-call `ask_audio_engineering_question` path now returns the bounded
`kenn.evidence.v1` packet used to ground a realtime plug-in answer whenever an
explicit `plugin_session_id` is supplied. This keeps measured bus facts,
freshness, provenance, and limitations machine-readable alongside the prose,
without retaining raw audio or inferring a track/device cause. The path still
does not request a capture, open an OSC socket, or authorize a Live mutation.

Exit evidence: focused realtime MCP/server handoff coverage passes **8/8**.

## Slice 50 — retrieval evidence baseline refresh

The current local knowledge index was re-evaluated without downloading or
modifying external data. Official-manual grounding selects the authoritative
manual class for **16/16** cases across nine categories. On the fixed 58-case
retrieval comparison, hybrid search retains recall@4 at **98.28%**, improves
MRR from **0.8573** to **0.877**, and improves top-1 from **74.14%** to
**77.59%**; the median latency is **80.388 ms** versus **67.179 ms** for
BM25. The result is a retrieval baseline, not a human usefulness claim.

Exit evidence: `evaluate_ableton_manual_grounding.py` passes **16/16** and
`evaluate_retrieval_modes.py` records `no_quality_regression: true` and
`deploy_candidate: true`.

## Slice 51 — current-source intelligence receipt refresh

The intelligence qualification receipt was rerun after the realtime evidence
integration and rebound to the current source hash. It passes hard cases
**15/15**, hybrid retrieval recall@4 **98.28%**, session-grounded advice
**6/6**, assistant recovery **8/8** with **7/7** safety cases, and arrangement
intelligence **4/4**. This confirms no deterministic intelligence regression;
it does not substitute for human review or real-session qualification.

## Slice 52 — explicit realtime evidence freshness

The shared `kenn.evidence.v1` packet now marks plug-in bus observations as
`current_for_diagnosis` only when they are no more than **15 seconds** old.
Older validated observations remain visible as `stale_or_unknown` historical
context, matching the existing diagnosis filter and preventing the longer
handoff retention window from being mistaken for current meter truth.

Exit evidence: focused evidence, plug-in handoff, and knowledge-path coverage
passes **19/19**.

## Slice 53 — latest SLO handoff audit

The sibling SLO checkout was rechecked read-only after its newer v4 hybrid
checkpoint appeared. The checkpoint hash is recorded in
`docs/SLO_HANDOFF_AUDIT_2026-09-09.md`, but there is still no immutable
`kenn.slo_artifact_manifest.v1` export. The current evidence is mixed: strong
closed-set/fusion metrics (**96.54% accuracy**, **96.45% macro F1**, **88.29%
fusion-adversarial accuracy**) sit alongside a failing OOD result (**168/168
false-known**) and unsuitable cold-scan/RSS measurements (**25.0 s** / **2.44
GB**). The classifier therefore remains disabled in KENN. No SLO files,
models, training data, or generated folders were copied.

Exit evidence: read-only artifact, hash, manifest, OOD, and performance checks
completed; integration remains correctly blocked pending a portable,
identity-bound KENN evaluation package.

## First implementation slice

The first engineering slice should be companion single-instance enforcement
for the HTTP server and AbletonOSC reply socket. The 2026-09-07 host preflight
showed that a stale KENN process can leave a new companion serving HTTP while
its OSC subsystem is offline. The current behavior is fail-safe, but it is not
clear enough for beta operators. This slice is local, testable, high leverage,
and independent of the two external release inputs.

Acceptance criteria:

- one companion starts normally and reports connected/offline truthfully;
- a second companion exits non-zero before advertising itself as ready;
- the error identifies a probable existing KENN instance without killing it;
- a stale lock with no live owner is safely recoverable;
- OS lock ownership releases on normal shutdown and common termination paths;
- tests cover concurrent starts and stale-lock recovery;
- the support runbook documents the behavior.

## Final decision rule

The post-beta programme for moving from a qualified private beta to a polished,
broadly dependable assistant is defined in
`docs/KENN_POLISHED_ABLETON_ASSISTANT_PLAN_2026-09-08.md`.

At the end of the phase, choose one of three evidence-backed outcomes:

- **Qualified private beta:** all 14 gates and Beta+ criteria pass.
- **Continue supervised pilot:** safety remains sound but quality, soak,
  signing, or review evidence is incomplete.
- **Hold:** any unauthorized mutation, false success, unrecoverable state,
  distribution failure, or serious privacy issue is observed.

## Slice 54 — realtime API freshness boundary

The direct plug-in live-context response now exposes the same explicit
freshness decision as the shared evidence packet: `current_for_diagnosis` is
true only through 15 seconds, after which the retained snapshot is labelled
`stale_or_unknown` while remaining available until the 30-minute context TTL.
This makes direct API, MCP, and operator reads consistent before real-session
qualification.

Exit evidence: focused plug-in handoff, evidence, and MCP coverage passes
**24/24**.

## Slice 55 — stale realtime recommendation abstention

The Mix Review recommendation bridge now refuses to emit current-sounding
realtime guidance when the retained plug-in bus context is past its
15-second diagnostic freshness boundary. The snapshot remains available for
explicit inspection and history, while the recommendation path abstains until
a new validated frame arrives.

Exit evidence: focused realtime/MCP/server coverage passes **31/31**.

## Slice 56 — current-source planner bake-off refresh

The Python 3.10-compatible Transformers runner was executed against the
already-present `Qwen3-4B-input-bound-v6` checkpoint on GPUs 1–4. After fixing
two model-prompt classification misses and aligning the Ollama runner's sketch
hydration, all six required runs passed: holdout **10/10** and adversarial
**12/12** across three repeats, with 100% contract and safety rates and model
recovery passing. Mean latency was **3,812.679 ms** and maximum suite p95 was
**11,408.809 ms**, both within the planner gate. The canonical receipt was
replaced only after all eight input hashes matched the current checkout.

The failed compatibility-endpoint comparison was retained outside the
repository as non-qualifying diagnostic evidence and was not promoted.

Exit evidence: `evaluation/results/KENN_DELIBERATIVE_MODEL_BAKEOFF.json` is
complete, input-bound, and planner-gate passing again.

## Slice 57 — current-source qualification refresh and low-CPU evidence tooling

The human-review packet was regenerated against the committed answer-engine
source and active hybrid index. Packet generation now bounds its local ONNX
embedding session to one intra-op and inter-op thread, and disables tokenizer
parallelism for this offline evidence job; KENN's normal service defaults are
unchanged. The packet is now provenance-valid and ready for two independent
reviewers.

The full current-source regression suite passes **1,070 tests** with four
warnings. The five intelligence qualification benchmarks also pass: hard
cases **15/15**, hybrid recall@4 **98.28%**, session-grounded advice **6/6**,
assistant recovery **8/8** including **7/7** safety cases, and arrangement
intelligence **4/4**.

Exit evidence: the supervised-pilot profile is now ready when a disposable
Live session is available. Qualified-beta work remains gated by independent
human scoring, signed distribution, current model-planned real-Live
qualification, a qualifying reconnect soak, real-mix review, and supervised
pilot evidence. The previous real-Live receipt is from an older source commit
and is correctly rejected until rerun against the current source.

## Slice 58 — qualification evidence is source-stable

The readiness hash now covers KENN runtime/evaluation inputs—source packages,
tests, scripts, the vendored bridge, and project configuration—rather than
every tracked narrative document. This prevents a status-note edit from
invalidating a test receipt while preserving source-bound invalidation for
code, fixtures, indexes, models, and qualification tooling.

After the change, the current receipts remain valid: the full regression suite
passes **1,070/1,070**, and intelligence qualification passes **15/15** hard
cases, hybrid recall@4 **98.28%**, session-grounded advice **6/6**, assistant
recovery **8/8** including **7/7** safety cases, and arrangement intelligence
**4/4**. The qualified profile is now **7 passed, 6 pending, 1 failed**; the
single failure is the source-stale real-Live assistant receipt, not an
automated code regression.

No deadline or feature count overrides this decision rule.

## Slice 59 — specific grounded advice and natural Live phrasing

The retrieval and answer layers now preserve user-specific intent for three
common assistant questions: hi-hat harshness selects the dedicated hat
workflow instead of vocal de-essing, explicit reverb Dry/Wet requests
distinguish an insert value from a 100%-wet return, and stated pink-noise
frequency deviations are interpreted as bounded user-reported evidence rather
than an automatic EQ instruction. Explicit Ableton questions retain the
`ableton_steps` answer shape, and the advice-only surface remains unable to
execute Live changes.

The private deterministic Live parser now also accepts spoken track numbers
such as “track four,” resolving them to the exact current snapshot identity
with confirmation still required. Existing MIDI-track creation and hi-hat
reverb setup paths remain typed and confirmation-gated.

Exit evidence: the focused advice/retrieval checks pass **57/57**, the focused
Live intent/command/action checks pass **233/233**, and the source-bound
qualification suite passes **1,077** tests with four warnings. Real-Live
execution evidence remains pending because the current Ableton runtime is
offline; no runtime restart or evidence relaxation was performed.

## Slice 60 — native parser parity for spoken track references

The plug-in's standalone C++ command parser now accepts spoken cardinal and
ordinal track references after the track/channel word, matching the Python
Live-intent parser for phrases such as “track four.” Numeric track references
remain unchanged, and the parser still only emits a local intent; it never
touches Live, OSC, audio, or the network.

Exit evidence: the native contract executable passes **12/12** cases and its
10,000-parse bounded performance probe completes successfully. Real-Live
qualification remains separate and was not attempted while Ableton was
offline.

## Slice 61 — native structural-command handoff parity

The plug-in's C++ parser now recognizes the already-qualified companion
commands `create/add/make MIDI track` and `create/add/make audio track`,
including an optional requested track name. This is intent and observability
parity only: `LocalLivePlan` continues to keep structural actions
companion-owned, so the native fallback cannot create a track or bypass the
Python service's fresh-topology binding, confirmation, type/name readback,
receipt, and no-automatic-undo contract.

Exit evidence: the native contract executable passes **15/15** cases plus the
10,000-parse bounded performance probe. No native mutation path or runtime
restart was added; real-Live qualification remains pending.

## Slice 62 — editor-independent realtime context publishing

The opt-in plugin context feed is now processor-owned rather than editor-owned.
A low-priority JUCE worker waits for the existing 8-second cadence, checks the
persisted `live_context_enabled` parameter, and sends only the existing
feature-only `kenn.plugin_handoff.v1` payload. It never runs from
`processBlock()`, and processor destruction signals and joins the worker so a
closing editor cannot silently stop the realtime review feed or leave a
publisher thread using a destroyed processor.

Exit evidence: the full `KENNMixAssistant` target builds successfully with one
low-priority job. No Ableton/companion/GPU restart or new Live mutation path
was introduced.

The compiled command-client integration check was also aligned with its
offline contract: a reachable companion with AbletonOSC unavailable now skips
only Live-bound proposal assertions and reports that qualification is deferred,
while malformed HTTP responses or unexpected client failures still fail the
test.

Both current macOS plugin bundles were then rebuilt from this source and
passed strict deep ad-hoc signature verification as universal arm64/x86_64
artifacts. Ad-hoc signing is suitable for local development only; it does not
advance the Developer ID, notarization, clean-host, or Ableton-discovery gates.

The compiled plugin boundary suite then passed **3/3** (native language,
native read/plan safety, and companion command-client integration). The client
integration check correctly defers only Live-bound proposal assertions while
AbletonOSC is offline.

## Slice 63 — identity-safe send-recipe compensation

Compensating rollback for a `set_send` recipe step now revalidates both sides
of the routing relationship: the source track must still have the exact bound
index/name, and the return track must still have the exact bound
index/name. A stale or replaced source therefore produces an
inspection-required recovery rather than risking an undo write to a different
track at the same index. Stale return identity is also rejected before any
recipe write.

Exit evidence: focused send/recipe safety coverage passes **5/5** and the full
repository regression suite passes **1,120/1,120** with four warnings. Ableton
remains offline, so real-Live execution evidence remains pending.

## Slice 64 — MIDI clip undo identity safety

MIDI clip creation receipts now revalidate the exact source track index and
name both when an undo proposal is prepared and immediately before the
deletion write. A renamed or replaced track at the same index therefore
cannot receive a deletion from an old receipt; the service returns a typed
failure without sending the delete request.

Exit evidence: focused MIDI clip service coverage passes **6/6**. The full
source-bound regression and intelligence receipts now pass **1,124/1,124** and
**15/15** against the committed source; Ableton remains offline and no Live or
runtime state was changed.

## Slice 65 — reversible clip-action identity audit

The same exact-track identity rule is now applied consistently to all
reversible clip actions: duplication undo, clip rename undo, sample-import
undo, and MIDI clip undo each revalidate the target track when the inverse is
prepared and again immediately before its write. This prevents an old receipt
from deleting a clip or renaming a clip on a replacement track at the same
index.

Exit evidence: focused cross-service identity coverage passes **14/14**; the
full source-bound regression suite passes **1,124/1,124** with four warnings,
and intelligence qualification remains **15/15**. Ableton remains offline, so
real-Live execution evidence remains pending.

## Slice 66 — MIDI creation interruption reconciliation

MIDI clip creation now performs one authoritative clip/notes read after a
negative or lost create/note acknowledgement. If the exact requested clip is
present, KENN records a verified `unacknowledged_write_reconciled` result and
keeps its identity-bound undo. If the state is partial or ambiguous, the
receipt is marked `requires_inspection` and its idempotency key is consumed,
so callers cannot blindly retry into a duplicate or overwrite.

Exit evidence: focused MIDI creation/recovery coverage passes **9/9**. The
refreshed release-scoped source-bound regression and intelligence receipts pass
**1,129/1,129** and **15/15** against the committed source; Ableton remains
offline and no Live or runtime state was changed.

## Slice 67 — read-only per-track meter evidence

The standard AbletonOSC bridge now requests the documented read-only
`output_meter_level` and `output_meter_right` properties only for the rich
session-understanding path and the background Mixing Doctor poll. This lets
KENN name a track for an instantaneous headroom check while preserving the
fast topology/control snapshot for ordinary planning. The values are clearly
bounded as post-fader meter observations: they cannot establish audio-rate
peak, LUFS, true peak, spectrum, or masking, and they do not authorize a
mutation. The live low-end heuristic was narrowed at the same time to an
unmuted name/fader `low_end_overlap_candidate` with no arbitrary volume-fix
action; measured masking remains in the multi-stem Mix Review path.

Exit evidence: bridge/Mixing Doctor coverage passes **35/35**, the full local
regression passes **1,136/1,136** with four warnings, and no Ableton,
companion, GPU, or UX process/state was changed. Real-Live qualification of
the new meter handoff remains pending because AbletonOSC is currently offline.

## Slice 68 — meter evidence reaches the reasoning layer

The optional per-track meter readings are now preserved when the live
snapshot is composed into `kenn.session_context.v1`. Kenn's compact
`kenn.session_intelligence.v1` briefing carries the readings alongside the
inferred track role and exposes a bounded `track_meter_observations` list for
advice clients. Each observation declares `instantaneous_post_fader` scope
and remains advisory-only, so a reasoning model cannot mistake the handoff for
audio-rate peak, LUFS, true-peak, spectrum, or masking evidence.

Exit evidence: session-context/intelligence coverage passes **23/23**, and the
full local regression passes **1,136/1,136** with four warnings. No Ableton,
companion, GPU, or UX process/state was changed; real-Live meter qualification
remains pending because AbletonOSC is currently offline.

## Slice 69 — fail-closed live-analysis language

The Mixing Doctor dispatch contract now distinguishes an unavailable Live
connection from a connected session with no active advisories. Offline or
unknown state returns `unavailable` with no alerts and does not imply that
clipping, masking, phase, or headroom were checked. Connected healthy state
is phrased as the absence of observed structural or instantaneous-meter
advisories, with the audio-rate limits stated explicitly. Project-health
normalization similarly reports instantaneous meter capability only when a
valid bounded reading exists; malformed values cannot create a headroom
finding.

Exit evidence: focused Mixing Doctor/project-analysis coverage passes
**17/17**, and the full local regression passes **1,139/1,139** with four
warnings. No Ableton, companion, GPU, or UX process/state was changed.

## Slice 70 — unified realtime session review

Added a single read-only `realtime_session_review` MCP capability and
`GET /api/realtime-session-review` handoff. It composes the latest cached
Ableton session, track observations, Mixing Doctor alerts, project-health
recommendations, and optional validated plug-in bus recommendations. The
response keeps `ableton_session_snapshot`, `cached_session_audits`, and
`plugin_bus` scopes separate, preserves advisory-only/no-capture/no-mutation
limits, and returns a structured `unavailable` result when the Live cache is
not current. This gives reasoning clients one coherent current-session scan
without adding an OSC socket or asking the plug-in for a capture.

Exit evidence: composed-review/MCP/server coverage passes **126/126**. No
Ableton, companion, GPU, or UX process/state was changed.

## Slice 71 — natural-language realtime session scan

The unified realtime session review is now reachable from ordinary KENN chat
requests such as “scan the current Ableton session for advice.” The
orchestrator routes these requests to a dedicated read-only reviewer, which
returns the same scope-labelled report used by MCP/HTTP clients. It preserves
the distinction between cached Live observations, structural Mixing Doctor
advisories, and optional plug-in-bus evidence, and refuses to infer audio
problems when the Live snapshot is unavailable.

Exit evidence: focused orchestrator/realtime/MCP/server coverage passes
**134/134**. No Ableton, companion, GPU, or UX process/state was changed.

## Slice 72 — realtime evidence propagation through chat

The explicit `plugin_session_id` accepted by `/api/ask` is now forwarded
through both streaming and non-streaming answer paths into the natural-language
realtime reviewer. A chat session scan can therefore include the latest
validated plug-in-bus snapshot when an integration supplies its identifier,
without requesting a capture or weakening the scope boundary.

Exit evidence: focused chat/orchestrator/server coverage passes **140/140**.
No Ableton, companion, GPU, or UX process/state was changed.

## Slice 73 — actionable realtime chat summary

Natural-language realtime scans now surface up to three bounded findings per
evidence scope directly in the chat response: cached Live/Mixing Doctor
advisories, project-health recommendations, and validated plug-in-bus advice.
Each line is labelled by scope and carries the existing inspection guidance;
the underlying report remains available as structured metadata and no line
authorises an automatic Live change.

Exit evidence: realtime/server coverage passes **50/50**. No Ableton,
companion, GPU, or UX process/state was changed.

## Slice 74 — knowledge-grounded realtime next checks

The natural-language session reviewer now retrieves a small, bounded set of
relevant sources from KENN's indexed knowledge base after composing the live
findings. Each `knowledge_guidance` item carries its evidence class and label
(`official_ableton_manual`, `youtube_transcript`, or curated KENN guidance), a
short excerpt, and an advisory-only marker. The excerpts are surfaced as
“Knowledge-grounded next checks” in chat; they never become measurements,
track attribution, or Live mutation authority.

Exit evidence: realtime/MCP/server/orchestrator coverage passes **137/137**.
No Ableton, companion, GPU, or UX process/state was changed.

## Slice 75 — source-diverse realtime guidance

Realtime guidance now supplements hybrid practical-note retrieval with one
source-specific BM25 candidate from the official Ableton manual and one from
reviewed producer transcripts when substantive matches exist. Optional
fallback failures no longer discard valid hybrid results. Excerpts are
cleaned of catalogue metadata before rendering, while source class and
advisory-only status remain explicit in the structured report.

Exit evidence: the real local index returned official-manual,
reviewed-transcript, and curated-note candidates for a headroom scan; focused
realtime coverage passes **138/138**. No Ableton, companion, GPU, or UX
process/state was changed.

## Slice 76 — focused guidance for all realtime clients

The shared `realtime_session_review` HTTP and MCP surfaces now accept an
optional `focus` string such as `headroom and gain staging`. When supplied,
the response includes the same bounded `knowledge_guidance` contract used by
normal chat, with source-diverse manual/transcript/practical references and
explicit advisory-only provenance. Without a focus, clients retain the fast
session composition with no unnecessary retrieval work.

Exit evidence: MCP/HTTP and realtime integration coverage passes **139/139**.
No Ableton, companion, GPU, or UX process/state was changed.

## Slice 77 — standard chat source citations

Realtime-session scans now promote their bounded `knowledge_guidance` records
into the normal chat `sources` field for both streaming and non-streaming
responses. The colleague-owned UX and downstream clients can therefore render
manual/transcript provenance through the established citation contract rather
than parsing specialist metadata. Unavailable scans return no sources.

Exit evidence: realtime/MCP/server/chat coverage passes **144/144**. No
Ableton, companion, GPU, or UX process/state was changed.

## Slice 78 — refresh human-review provenance

Regenerated the 100-case human-review packet against the current committed
answer engine and active hybrid index, then rebound both blank independent
reviewer forms to the new packet SHA-256. No reviewer scores or release
decision were invented. The qualified gate now reports human review as
`pending` rather than failing on stale packet provenance.

Exit evidence: packet builder created 100 cases; qualified-gate validation
accepts the packet provenance. No Ableton, companion, GPU, or UX process/state
was changed.

## Slice 79 — preserve realtime spectral evidence

The unified realtime session-review contract now carries the validated,
bounded pink-noise-style reference summary and recent trend, including the
nearest band and measured dB deviation. This lets downstream chat and review
clients render concrete observations such as a band near 315 Hz being above
the measured baseline without parsing prose or treating the result as a
track-level diagnosis or automatic EQ instruction. Raw audio and untrusted
fields remain excluded.

Exit evidence: focused realtime/plugin coverage passes **135/135**. No
Ableton, companion, GPU, or UX process/state was changed.

## Slice 80 — refresh current-source planner evidence

The existing `Qwen3-4B-input-bound-v6` checkpoint was rerun through the
Python 3.10-compatible Transformers runner using the already-installed GPU
environment and GPUs 1–4. All six required runs passed: holdout **10/10** and
adversarial **12/12** across three repeats, with 100% contract/safety rates,
model recovery passing, weighted mean latency **3,948.237 ms**, and maximum
suite p95 **11,989.39 ms**. The receipt is bound to the current eight input
hashes and the planner gate now passes again. No GPU service, driver,
container, host, Ableton, companion, or UX process was restarted or changed.

## Slice 81 — shared versioned evidence packet across native and offline analysis

Added the canonical `common/kenn_evidence_v1.schema.json` contract and emit a
`kenn.evidence.v1` packet from both the native plug-in handoff and the
offline Mix Review analyser. The packet carries only bounded scalar facts,
units, source provenance, and explicit limitations; legacy handoff/report
fields remain for compatibility. Live context summaries now expose the same
packet, with current/stale diagnosis freshness still computed by the host.

Exit evidence: focused Python coverage passes **44/44**; the native
`KENNMixAssistant` and numerical-parity targets build successfully; the
native command/live-plan/integration/numerical/thread-safety set passes
**5/5**. No Ableton, companion, GPU, or UX process/state was changed.

## Slice 82 — validate shared evidence at the handoff boundary

The optional `kenn.evidence.v1` envelope is now validated when a native
plug-in handoff enters KENN: source identity, bounded scalar facts, finite
numbers, units, confidence labels, timestamps, and limitations are checked.
Malformed or source-mismatched evidence is rejected, while legacy handoffs
without the envelope remain compatible. Focused handoff/evidence/service
coverage passes **22/22**. No Ableton, companion, GPU, or UX process/state was
changed.

## Slice 84 — type stem-masking evidence without overclaiming

The standalone time-aligned stem-masking analysis now emits the shared
`kenn.evidence.v1` packet and KENN can convert it into typed evidence history.
The packet records bounded overlap/stem/candidate facts and marks competition
findings as `measured_proxy`; it preserves the explicit limitation that this
is not psychoacoustic masking or proof of an EQ move. Focused masking,
evidence, chat-tool, and service coverage passes **29/29**. No Ableton,
companion, GPU, or UX process/state was changed.

## Slice 83 — measure the realtime and offline performance envelope

Executed the existing native micro-benchmark and the actual offline Mix
Review engine under low-priority, single-threaded numerical-library settings.
The realtime core measured **0.111–0.124%** of the 48 kHz budget across 64–
1024-sample buffers (**23.05–25.75 ns/sample**) with **8.25 MB** peak process
RSS. The Mix Review engine measured **31.983 ms mean / 34.325 ms max** for a
5-second 48 kHz mono WAV, with **127.94 MB** process RSS including startup.
These are bounded synthetic performance measurements, not perceptual or
whole-DAW quality claims.

Exit evidence: all native performance buffer sizes passed; the offline
benchmark returned `qualified: true`; no Ableton, companion, GPU, or UX
process/state was changed.

## Slice 85 — preserve stem-masking evidence across chat follow-ups

The `/api/ask` contract now accepts an explicit prior
`kenn.mix_review_masking_analysis.v1` result as `stem_masking_context`. KENN
validates the nested shared evidence packet before adding it to answer
history, and returns a metadata-only `stem_masking_evidence` packet so a
client can preserve the context for the next turn without retaining audio or
granting mutation authority. Invalid or untrusted result shapes are ignored.

Exit evidence: focused server evidence coverage passes **2/2**. No Ableton,
companion, GPU, or UX process/state was changed.

## Slice 86 — render standalone stem-masking evidence into advice

The evidence renderer now recognises the standalone
`stem_masking_analysis` source for masking and low-end follow-ups. It reports
the bounded candidate count, strongest competing pair/band, and overlapping
frame fraction when present, while retaining the measured-proxy limitation:
these results prioritise listening checks but do not prove audibility,
causation, or an EQ move.

Exit evidence: focused evidence coverage passes **16/16**. No Ableton,
companion, GPU, or UX process/state was changed.

## Slice 87 — harden stem-masking evidence provenance

The standalone masking follow-up adapter now requires the nested evidence
packet to declare the exact `stem_masking_analysis` source and a bounded list
of limitations. Forged source identity and malformed limitations are rejected
before evidence can enter chat history or response metadata.

Exit evidence: focused masking/evidence/server coverage passes **17/17**. No
Ableton, companion, GPU, or UX process/state was changed.

## Slice 88 — carry advisory classifier evidence into ordinary chat

The `/api/ask` contract now accepts an explicit completed
`kenn.audio_classification.v1` result as `audio_classification_context`.
KENN validates the result before adding typed specialist-inference evidence to
answer history and returns metadata-only classification evidence for the
caller. Audio-only and metadata-assisted predictions stay separate, while
Unknown/OOD output remains unresolved. The bridge does not load SLO weights,
enable inference by itself, or grant Live mutation authority.

Exit evidence: focused classification/evidence/server coverage passes
**30/30**. No Ableton, companion, GPU, or UX process/state was changed.

## Slice 89 — revalidate classifier context after construction

`kenn.session_context.v1` now revalidates each audio-classification entry
after the context is built, and normalized entries carry an explicit
`completed` status. Mutating a selected label or OOD state in-place is
rejected before the context can reach advice or planning.

Exit evidence: focused session-context/classification/intelligence/evidence/
server coverage passes **40/40**. No SLO artifact was loaded or copied, and
no Ableton, companion, GPU, or UX process/state was changed.

## Slice 90 — surface specialist evidence in ordinary answers

Normal deterministic answer templates now render relevant typed evidence from
`audio_classification` and `stem_masking_analysis` history. This closes the
gap where explicit sample-identification or masking follow-ups could receive
the evidence in metadata but not in the answer body. Unknown/OOD and advisory
language remain intact.

Exit evidence: focused answer/evidence coverage passes **42/42**. No SLO
weights were loaded and no Ableton, companion, GPU, or UX process/state was
changed.

## Slice 91 — ground generated answers with specialist evidence

Generated-answer validation now accepts the same bounded specialist
observations that deterministic templates render from typed history. This
keeps classifier and stem-energy measurements in the grounding boundary for
local, rewritten, and streaming answers, without treating the specialist
result as retrieval text or weakening the Unknown/OOD and measured-proxy
limitations.

Exit evidence: focused grounding/answer/evidence/server coverage passes
**9/9**. No SLO weights were loaded and no Ableton, companion, GPU, or UX
process/state was changed.
