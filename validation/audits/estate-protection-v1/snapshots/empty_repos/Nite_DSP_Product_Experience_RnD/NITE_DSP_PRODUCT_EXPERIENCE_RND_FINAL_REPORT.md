# NITE DSP - Product Experience & Workflow R&D Final Report

## Executive Result

**PASS WITH LIMITATIONS.** The programme completed eight read-only R&D tracks, nine experiments, five executable probe families, and 135 synthetic workflow scenarios. It produced evidence for five near-term experience promotions and several features that should be parked. It did not integrate any result into production.

The strongest result is a coherent common path: intent -> measured evidence -> focused result -> preview -> user decision -> reversible action. SLO should own sample discovery, KENN should own audio engineering interpretation, and Thursday should orchestrate company state without absorbing either product's semantics.

## Programme Scope

The programme evaluated SLO workflows, KENN workflow trust, Ableton/DAW context, cross-product contracts, onboarding, accessibility, localisation, performance, Thursday's company interface, and synthetic user friction. Evidence is labelled OBSERVED, MEASURED, INFERRED, HYPOTHESISED, or RECOMMENDED in the track reports and registry.

All implementation work was confined to the isolated local home `Nite_DSP_Product_Experience_RnD/`. Production repositories were audited read-only.

## Parallel Agent Utilisation

Four local read-only audit/benchmark streams ran in parallel at peak. The intended W1-W8 roles are recorded in [WORKER_MATRIX.md](controller/WORKER_MATRIX.md). One attempted external research worker was rate-limited by the model service; the same audit continued directly against the workspace. No claim is made that eight independent model workers completed work.

## Repository Ownership

| Repository | Branch | Starting/current SHA | Classification | Programme action |
|---|---|---|---|---|
| SLO `Nite_DSP/Nite_DSP_01` | `engineering/slo-classification-analysis-v4` | `dd60ddb31c66d8ee43f318764c0ac1f9eb972eef` | ACTIVE_WRITER | Read only |
| SLO UX | `ux/slo-v3-premium-product` | `a347bf5e6929a15bd6078aaa6a8bd49771f91691` | Historical/read only | Read only |
| Website | `web/nitedsp-world-class-v3` | `ed2664ed341ca15ee7886f56f6430d2ed3ae272d` | ACTIVE_WRITER, modified | Read only |
| Thursday/KENN `Audio_Too` | `thursday/daily-brief-mvp` | `6810283b67d24c1e8bbcc65ac3a4969330d1e8af` | ACTIVE_WRITER, working | Read only |
| AI Platform | `platform/phase4-company-capabilities` | `5287273b84b6747868739a68eb1d078ab2d7b85d` | ACTIVE_WRITER, untracked evals | Read only |
| EMBER design system | local design-system checkout | `c4802a24964b9d22c8083081f75f5c8fc7e71f77` | Frozen foundation | Read only |
| PX R&D home | local only, no remote | created during programme | Isolated | Writable |

The owner-audio paths and production databases were not opened for modification. The isolated home has no remote and no commits were made.

## Experiments

The machine-readable [experiment registry](controller/EXPERIMENT_REGISTRY.json) contains nine entries with method, metric, result, status, artifact, and conclusion.

| Track | Experiment | Result | Status |
|---|---|---|---|
| PX-A SLO | Search index | 25,000-record worst-query median 241.9812 ms linear vs 6.4816 ms exact-token; one numeric match-count parity gap | PASS |
| PX-A SLO | MAP culling | 25,000-point proxy 11.9241 ms full scan vs 0.3452 ms cell cull, identical visible count | PASS |
| PX-B KENN | Proposal state | Provisional -> apply/reject, undo retained, healthy no-action state | PASS |
| PX-C DAW | Context inventory | Portable and Ableton-specific boundaries classified; no live SLO handoff found | PASS |
| PX-D Cross-product | Evidence-only contracts | Safe KENN/SLO payloads accepted; raw audio rejected | PASS |
| PX-E UX | Accessibility/l10n stress | Structural invariants passed; 9 width overflows detected | PASS |
| PX-F Performance | Budgets and IPC | IPC median 0.5481 ms, P95 16.3472 ms, max 131.4537 ms | PASS |
| PX-G Thursday | Company interface | Platform approval boundary passes; active daily-brief test has 2 failures | INCONCLUSIVE |
| PX-H Journeys | Synthetic corpus | 135 scenarios; complement search largest modelled reduction; chatbot-first negative | PASS |

## User Journey Corpus

The corpus contains 135 scenarios from nine synthetic archetypes across 15 tasks. It measures modelled steps, clicks, keystrokes, context switches, decision points, wait, and error recovery for current and proposed workflows. It is not human research.

- 81 scenarios were marked candidate promotion.
- 45 were marked continue R&D.
- 9 chatbot-first scenarios were marked drop/park.
- Largest modelled step reduction: `find_complementary_clap`, approximately 9 to 5 steps.
- Worst proposed feature: `chatbot_first_plugin`, approximately 8 to 11 steps.

See [PX_USER_JOURNEY_REPORT.md](reports/PX_USER_JOURNEY_REPORT.md) and the complete [synthetic corpus](user_journeys/synthetic_corpus.json).

## SLO

### SLO WORKFLOW STATUS

**PASS WITH LIMITATIONS.** SLO's core sample intelligence is strong. Search, filters, HNSW similarity, cached MAP rendering, favourites, preview history, and native drag exist. The common path still needs a semantics-preserving ranked search index, complete MAP keyboard access, and better audition/drag continuity.

### TIME-TO-SAMPLE

A human time-to-useful-sample was not measured. The measurable search proxy at 25,000 synthetic samples was 241.9812 ms for the observed linear path versus 6.4816 ms for an exact-token candidate. The token candidate missed one numeric substring match, so it is a research direction rather than a shippable result.

### FIND SIMILAR

**Exists.** SLO uses a 512-dimensional PANNs embedding and HNSW retrieval, with weighted, refined, reference, and duplicate variants. The UI has a Find Similar action, results panel, MAP emphasis, and a model-unavailable state. Measure the complete selected sample -> audition -> decision -> drag path before adding more retrieval modes.

### FIND COMPLEMENT

**Not present as a production SLO capability.** The KENN/AutoMix relationship and masking evidence make it worth a constrained pilot, but the mode adds complexity. Require human usefulness and false-positive evidence before promotion.

### MAP

**Exists and is well-directed.** Cached layers, viewport culling, reusable scratch storage, semantic zoom, and a spatial index are present. The main gap is keyboard selection and focus traversal. Preserve the renderer while instrumenting real P95/P99 frames.

### DRAG-TO-DAW

**Exists for original files and waveform slices.** Browser/canvas drag the original path; waveform slice drag creates a temporary render. XMP support is separate and not part of native drag metadata. Make original versus preview explicit and test disposable Ableton workflows.

### TOP 5 SLO WORKFLOW IMPROVEMENTS

1. Semantics-preserving indexed and ranked search.
2. One selected-sample state shared by list, MAP, audition, and drag.
3. Complete keyboard MAP navigation and commands.
4. Faster, optional looped and normalised audition without misrepresenting source audio.
5. Evidence-backed Find Complement pilot.

## KENN

### KENN WORKFLOW STATUS

**PASS WITH LIMITATIONS.** KENN and AutoMix already measure more than the current presentation makes easy to act on. The next gain is prioritised, evidence-first, reversible proposals.

### ISSUE PRESENTATION

Use a compact ranked queue: Top issue, Next issue, Optional improvement, and No action needed. Include severity text, scope, evidence, cause hypothesis, and one next action. Avoid decorative confidence percentages.

### EVIDENCE UX

**Strong foundation observed.** The existing manifest handoff includes decisions, quality receipts, technical metrics, safety diagnostics, reference comparison, and bounded priority actions. Operational telemetry is explicitly distinguished from mix-quality evidence.

### PRIORITISATION

The prototype showed that three visible findings are enough for a testable default, but production prioritisation and cognitive load are not yet proven. Compare all findings, top three, and no-action states with engineers.

### AUTOMIX PROPOSAL UX

AutoMix corrections and reference movements are opt-in, and an automation preview exists. Keep every result provisional until the user decides. Show before/after diff, Apply, Reject, Modify, and Undo with durable receipts. A quality gate is not user authority.

### REFERENCE WORKFLOW

Show measured deviation and bounded direction in the user's artistic context. Do not optimise toward spectrum identity. Existing source history supports listening-gated, boost-biased decisions over aggressive cut-heavy matching.

### TOP 5 KENN WORKFLOW IMPROVEMENTS

1. Ranked issue queue with a first-class no-action state.
2. Evidence and affected scope beside each issue.
3. Explicit preview, Apply, Reject, Modify, and Undo.
4. Separate audio evidence from render telemetry and reference targets.
5. Human cognitive-load test for issue prioritisation.

## Ableton / DAW

### ABLETON INTEGRATION

**PASS WITH LIMITATIONS.** Portable SLO host context supports BPM, playing state, and PPQ position for quantised audition. The optional Ableton OSC bridge supplies richer track, device, clip, scene, transport, tempo, and selected write operations. These are separate permission and availability states.

### PORTABLE DAW CONTEXT

BPM, transport playing state, PPQ/playhead position, plugin audio format context, and small plugin project preferences. Portable SLO does not expose a complete project model.

### ABLETON-SPECIFIC CONTEXT

Track data, volume/pan/mute/solo/arm, device parameters, device creation, clip load/launch, scene launch, transport play/stop, tempo setting, sidechain command, optional Remote Script, and XMP sidecar support.

### UNAVAILABLE/UNRELIABLE CONTEXT

Selected track identity in portable SLO, full routing/device topology, project key/scale, project MIDI notes, full track/master capture, arrangement semantics, and project ownership. Never present these as automatically available across DAWs.

### PLUGIN/COMPANION BOUNDARY

Plugin: immediate UI, transport-aware audition, selection, keyboard state, native file drag. Companion/local runtime: models, embeddings, library index, background analysis, shared coordination, and capability routing. Ableton bridge: explicitly enabled host-specific actions and receipts.

### BEST DAW INTEGRATION OPPORTUNITY

Transport-aware audition-to-native-drag, with original versus rendered preview clearly named and no browser/file-search detour.

## Cross-Product Intelligence

### KENN -> SLO

A measured kick issue can pass frequency occupancy, transient profile, pitch class, BPM, and a context reference to a candidate SLO complement search. SLO returns ranked samples and owns audition. This is the best cross-product hypothesis.

### SLO -> KENN

SLO can pass a sample reference and feature summary for KENN fit evaluation against a mix context. Raw audio stays local.

### THURSDAY -> PRODUCTS

Thursday should call typed product capabilities, summarise their evidence, and route the user to the owning product. It should not absorb DSP semantics.

### SHARED CONTRACTS

Reuse `nite_ai.AgentRequest`, `AgentResult`, `CapabilityDefinition`, privacy classes, evidence packets, trace IDs, and artifact references. Candidate audio IDs are not live in the current registry.

### PRIVACY

Cross metrics, features, references, evidence, and artifact IDs. Reject raw audio, full projects, project paths, credentials, and private data in ordinary inter-product payloads. The synthetic probe enforced this.

### BEST CROSS-PRODUCT WORKFLOW

KENN measured issue -> SLO complement candidates -> user audition and choice -> KENN fit evidence -> user decision.

## Onboarding

### ONBOARDING

The first-run path is install -> open -> select library -> scan -> understand classification -> search -> audition -> drag. Every failure state must name the next action. Required states include no library, scanning, no results, no favourites/history, no similar samples, unknown/OOD, offline model, analysis failure, and permission denied.

### ACCESSIBILITY

Structural checks passed for named controls, keyboard reachability, unique focus order, redundant semantic encoding, and reduced motion. The current SLO MAP keyboard gap remains the largest concrete failure.

### LOCALISATION

The pseudo-locale stress detected nine width overflows across English, German-like, Spanish, French, CJK-like, and RTL-like fixtures. CJK-like expansion produced four; 150% text scale flagged Reject and empty-state copy. Use adaptive layout and wrapping, not truncation. Technical notation remains Hz, kHz, dB, LUFS, ms, and BPM.

## Performance

### PERFORMANCE BUDGET

**Created.** See [performance_budget_manifest.json](performance/performance_budget_manifest.json). Headline targets are search response 50 ms, MAP P95 frame 16.7 ms, warm audition start 100 ms, IPC P95 5 ms, and zero UI blocking from background analysis. Stretch and fail thresholds are recorded in the manifest.

### MEASURED PROXY RESULTS

- Search at 25,000 synthetic records: linear worst-query median 241.9812 ms; exact-token candidate 6.4816 ms.
- MAP at 25,000 synthetic points: full scan 11.9241 ms; cell cull 0.3452 ms.
- Existing local runtime: 100 requests, median 0.5481 ms, P95 16.3472 ms, max 131.4537 ms.

### AUDIO THREAD

SLO prepares files off the audio callback. Follow up on non-atomic shared BPM/playing state and pending reader/trigger publication. Do not place model inference, filesystem, network, or blocking IPC on the audio thread.

### MULTI-INSTANCE

Not measured. Run 1, 3, and 10 instance tests for model duplication, DB contention, workers, memory, and shutdown.

### BIGGEST PERFORMANCE RISK

Tail latency and cold-start behavior hidden by good medians, especially if future cross-product calls reach a UI-critical or real-time path.

## Thursday Company Interface

### COMPANY INTERFACE

Thursday has a daily brief composer, scheduling, receipts, intent/registry, confirmation, menu-bar/HUD, voice modules, and typed company capabilities. It should be a concise company interface, not a second product semantics layer.

### MORNING BRIEF

The existing brief gathers business status, agenda, week ahead, agent receipts, and scheduler status with per-section degradation. The typed platform brief is the better long-term source of truth. Prioritise changes, obligations, blockers, decisions, approvals, and risks over metric dumps.

### PROACTIVITY

Use immediate, next-brief, weekly-review, and do-not-surface classes. No real alert-fatigue study was run.

### APPROVAL UX

The platform separates approval recording from execution. Thursday has signed expiring confirmations and idempotent receipts. Approval surfaces need action, why, effect, risk, reversibility, evidence, Approve, and Reject.

### VOICE

Voice modules exist for optional STT/TTS. Use push-to-talk for brief capture and hand off visual evidence/approval. Do not build always-listening behavior from this programme.

### RECOMMENDED APPLICATION FORM

Menu-bar entry point plus command palette plus visual brief/detail and approval surface. Dashboard is secondary; chat is not the approval surface.

### BIGGEST GAP TO JARVIS-LIKE EXPERIENCE

Reliable prioritised company state connected to decisions, approvals, evidence, and deadlines. Voice is not the primary gap.

The active daily-brief test run was **8 passed, 2 failed**: calendar routing did not return the composed brief, and the expected patch target was not exposed. Those production-branch failures were not modified.

## Synthetic User Evaluation

The synthetic corpus confirms the strongest shared workflow is measured issue -> focused candidate -> audition/preview -> user decision. It also rejects chatbot-first plugin UX, broad forced ecosystem dashboards, automatic destructive changes, and confidence-number clutter.

## Top 10 Workflows

| Rank | User intent | Product | Current friction | Target experience | Evidence | Promotion status |
|---:|---|---|---|---|---|---|
| 1 | Find something that complements this kick | KENN + SLO | Requires a new mode and cross-product handoff | Measured issue -> ranked complement candidates -> audition -> fit evidence | Synthetic contract + journey corpus; feature not live | CONTINUE R&D |
| 2 | Find a similar sample quickly | SLO | Similarity exists but selection/audition/drag path needs measurement | One selected object, Find Similar, instant audition, native drag | OBSERVED production source | PROMOTE DISCOVERY |
| 3 | Search a 20k-25k sample library | SLO | Linear substring scan scales poorly | Ranked semantics-preserving index with parity tests | MEASURED synthetic proxy | PROMOTE DISCOVERY |
| 4 | Understand the biggest mix problem | KENN | Findings and evidence can be scattered | Top issue card with scope, evidence, and next action | OBSERVED payloads + prototype | PROMOTE HUMAN TEST |
| 5 | Preview a mix improvement safely | KENN | Opt-in correction flags exist but end-to-end proposal parity needs proof | Before/after preview, explicit decision, receipt, undo | OBSERVED AutoMix + prototype | PROMOTE HUMAN TEST |
| 6 | Audition and place a sample in Ableton | SLO / DAW | Original drag works; preview and metadata handoff are split | Transport-aware audition to native drag | OBSERVED source audit | PROMOTE FIXTURE |
| 7 | Know that no important mix fix is needed | KENN | Healthy state can be overlooked by optimisation UX | Clear measured no-action state | MEASURED synthetic prototype | PROMOTE HUMAN TEST |
| 8 | Recover a failed library scan | SLO | Failure/recovery path needs a unified state model | Preserve selection, explain failure, resume/retry safely | Synthetic journey + source state inventory | CONTINUE R&D |
| 9 | Ask what matters this morning | Thursday | Brief exists; active handler wiring is not green | Prioritised typed brief with evidence and approval links | OBSERVED source + 8/10 test result | CONTINUE R&D |
| 10 | Discover samples without a mouse | SLO | Editor shortcuts exist; MAP keyboard path is absent | Complete focusable MAP state machine | OBSERVED source + structural probe | PROMOTE ACCESSIBILITY |

## Top Friction Points

1. Intent-to-useful-result spans too many product surfaces without a shared selected object.
2. SLO's MAP is visually capable but not keyboard-equivalent.
3. SLO text search has no relevance ranking and scales as a linear scan.
4. KENN has rich evidence but needs a prioritised decision surface and explicit no-action state.
5. Portable plugin APIs cannot supply the project context users may assume.
6. Thursday's daily brief has an active branch integration gap.
7. IPC and model cold starts need tail-latency measurement, not median-only claims.
8. Localisation and 150% text scale can overflow compact controls.

## Anti-Features / Things Not To Build

- Chatbot-first plugin UI.
- Constant numeric confidence on every KENN card.
- Forced ecosystem dashboards that duplicate product surfaces.
- Silent or destructive automatic mix changes.
- A new MAP mode before keyboard and performance acceptance exist.
- Automatic full-project interpretation based on unavailable host context.
- Always-listening production voice behavior.

## Performance Budgets

The complete target/stretch/fail matrix is in [performance_budget_manifest.json](performance/performance_budget_manifest.json). Every future qualification should report median, P95, P99, and worst meaningful spike, plus conditions and hardware.

## Cross-Product Opportunities

The only opportunity strong enough to carry forward is evidence-only KENN -> SLO complement search with optional SLO -> KENN fit evaluation. It needs candidate capability registration, adapter ownership, privacy review, ranking evaluation, and human validation. Shared infrastructure should remain invisible to users.

## Real Human Testing Required

No real users were recruited or contacted. The next moderated study should include a beginner producer, professional producer, mix engineer, Ableton power user, large-library user, and keyboard-accessibility user. Tasks: find kick, Find Similar, Find Complement, diagnose harshness, compare reference, recover scan, navigate MAP, reject proposal, approve Thursday action, switch locale, and use three instances.

Measure completion, time to useful result, decision reversals, trust, confusion, error recovery, context switches, and observed shortcut/focus behavior. Compare all-findings versus top-three KENN cards and include a no-action control.

## Promotion Candidates

1. Semantics-preserving SLO search index with substring/fuzzy parity tests.
2. Shared selected-sample focus state plus keyboard-complete MAP workflow.
3. KENN evidence-first ranked issue cards with preview, decision, receipt, and undo.
4. Transport-aware SLO audition and native Ableton drag fixture.
5. Evidence-only KENN/SLO adapter spike using existing `nite_ai` contracts, without raw audio or production registration.

## Experience Roadmap

### NOW

Instrument SLO search, audition, drag, and MAP frames. Define the shared selected-sample state. Specify KENN issue-card and no-action human tests. Repair the active Thursday daily-brief integration in its owning branch.

### NEXT

Run production-shaped fixture benchmarks, keyboard/focus prototype tests, KENN prioritisation studies, and disposable Ableton Live 12 workflows. Resolve IPC tail and audio-thread publication findings.

### LATER

Register reviewed audio capabilities, add companion/runtime coordination, and run a bounded KENN/SLO complement workflow if human evidence supports it.

### RESEARCH

Find Complement ranking, processed-preview drag, real localisation/font metrics, screen-reader behavior, multi-instance memory, cold-start, reference presentation, alert fatigue, and cross-DAW portability.

### DROP

Chatbot-first plugin UI, forced dashboards, always-on voice, confidence-number clutter, and automatic destructive mix changes.

## Repository / Production Mutation Check

No SLO production files, KENN production files, Thursday production files, website files, installed plugins, sample libraries, reference tracks, customer data, credentials, signing assets, or production databases were modified. The isolated R&D home was the only writable target.

## Commits / Pushes

No commits, pushes, branches, merges, rebases, force pushes, or history rewrites were performed. The existing human Git identity was not changed. No AI attribution was added anywhere.

## Recommended Next Sprint

Run one instrumented, production-shaped SLO validation sprint covering 25,000-sample search, keyboard MAP discovery, audition start, and disposable Ableton native drag; use its measured and moderated results as the gate for the search-index and focus-state engineering work before registering any cross-product audio capability.

NITE DSP PRODUCT EXPERIENCE R&D:
PASS WITH LIMITATIONS

TRACKS COMPLETED:
8 / 8

EXPERIMENTS:
9

WORKFLOW SCENARIOS:
135

PARALLEL WORKERS PEAK:
4

PRODUCTION REPOSITORIES MODIFIED:
NONE

SLO PRODUCTION MODIFIED:
NO

KENN PRODUCTION MODIFIED:
NO

THURSDAY PRODUCTION MODIFIED:
NO

WEBSITE MODIFIED:
NO

INSTALLED PLUGINS MODIFIED:
NO

OWNER DATA MODIFIED:
NO

EXTERNAL BUSINESS WRITES:
NONE

AI ATTRIBUTION IN COMMITS:
NONE

SLO WORKFLOW:
PASS WITH LIMITATIONS - strong existing core; ranked search and keyboard MAP are the first engineering gates.

KENN WORKFLOW:
PASS WITH LIMITATIONS - evidence-first reversible proposals are ready for human validation.

ABLETON / DAW:
PASS WITH LIMITATIONS - transport-aware audition is portable; rich context is opt-in Ableton-specific.

CROSS-PRODUCT:
PASS WITH LIMITATIONS - evidence-only KENN/SLO complement workflow is promising but not registered live.

ACCESSIBILITY / ONBOARDING:
PASS WITH LIMITATIONS - structural invariants pass; MAP keyboard parity and adaptive localisation remain.

PERFORMANCE:
PASS WITH LIMITATIONS - budgets and proxies exist; tail, cold-start, JUCE, and multi-instance evidence remain.

THURSDAY INTERFACE:
PASS WITH LIMITATIONS - typed company boundary is sound; active daily-brief wiring is inconclusive.

USER JOURNEY LAB:
PASS WITH LIMITATIONS - 135 synthetic scenarios rank opportunities; human validation remains required.

BEST SLO OPPORTUNITY:
Semantics-preserving ranked search joined to one selected-sample audition and drag state.

BEST KENN OPPORTUNITY:
Evidence-first Top issue / Next issue / No action cards with preview, explicit decision, and undo.

BEST DAW OPPORTUNITY:
Transport-aware audition to native Ableton drag.

BEST CROSS-PRODUCT OPPORTUNITY:
KENN measured issue to SLO complement candidates to KENN fit evidence, with the user deciding.

BIGGEST UX FAILURE:
SLO MAP has no complete keyboard-equivalent discovery path, while KENN's evidence still needs prioritised presentation.

BIGGEST PERFORMANCE RISK:
Tail latency and cold-start behavior hidden by medians, especially around future shared runtime calls.

TOP 5 EXPERIENCE PROMOTIONS:
1. Semantics-preserving SLO search index.
2. Shared selected-sample focus and keyboard MAP state machine.
3. KENN evidence-first reversible proposal cards.
4. Transport-aware audition and native Ableton drag fixture.
5. Evidence-only KENN/SLO adapter spike using existing platform contracts.

TOP 3 CONTINUED EXPERIMENTS:
1. Find Complement ranking and human usefulness.
2. IPC cold-start, tail, and multi-instance behavior.
3. Real Ableton, screen-reader, localisation, and moderated workflow validation.

TOP 3 FEATURES TO DROP/PARK:
1. Chatbot-first plugin UI.
2. Forced ecosystem dashboard and duplicate product semantics.
3. Silent destructive automation or always-listening voice.

RECOMMENDED NEXT STEP:
Run the instrumented 25,000-sample SLO search-to-drag and keyboard-MAP validation sprint before production engineering or cross-product capability registration.
