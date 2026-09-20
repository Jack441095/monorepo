# KENN private beta sprint plan

**Date:** 2026-09-06
**Target:** a restricted, private beta of KENN as a supervised Ableton audio assistant
**Suggested duration:** 10 working days, with a release gate at the end

**Next phase:** This sprint has reached supervised-pilot readiness. Continue
with `KENN_BETA_PLUS_PLAN_2026-09-07.md` for the current 15-day qualification,
real-material evaluation, reliability, capability, and optional MiniMax plan.

## Progress update — 2026-09-07

- Fixed a P0 startup reliability defect: `/api/health` no longer blocks on a
  synchronous AbletonOSC probe while the Mixing Doctor polling thread owns the
  shared exchange lock. Focused startup and server tests pass.
- Closed the known Chain Selector defect. The exact Ableton question now routes
  to Ableton and ranks `ableton-racks-and-chain-selectors.md` first instead of
  unrelated Wwise Switch notes; explicit Wwise Switch questions remain green.
- Added an approved, focused Ableton Link note based on Ableton's Live 12
  Reference Manual and corrected the older Wi-Fi-only/transport wording.
- Added a Link intent lock so direct Link and Link Audio questions are not
  drowned out by generic mixer-send, reverb, routing, or delivery vocabulary.
- Versioned semantic-cache entries by retrieval logic and active index, so a
  stale high-confidence response cannot conceal a deployed ranking or corpus
  fix until the one-hour TTL expires.
- Rebuilt the hybrid index successfully: 1,116 chunks from 234 approved notes
  and one PDF.
- Made the optional AudioGen boundary quiet and explicit: ordinary knowledge
  questions no longer attempt to import a missing provider, while real
  generation requests report that generation is unavailable and confirm that
  no audio was created or changed.
- Current local full regression: **590 passed, 5 dependency deprecation
  warnings**. A fresh clone and Python
  3.13 virtual environment passed the complete core suite with **574 passed,
  7 expected optional-training skips, and 4 warnings**; see
  `KENN_CLEAN_INSTALL_VERIFICATION_2026-09-07.md`.
- Host-format qualification advanced: Apple's `auval` passed the installed AU,
  and pluginval passed the installed VST3 at strictness levels 5 and 10 across
  44.1–192 kHz, multiple block sizes, state/automation/thread-safety checks,
  and parameter fuzzing. Ableton Live 12.4.5 then discovered, instantiated, and
  cleanly removed both VST3 and AUv2 builds in an unsaved disposable set on
  macOS 26.6.2. See `KENN_PLUGIN_HOST_VALIDATION_2026-09-07.md`.
- Packaging found one real blocker: both local bundles are ad-hoc signed and
  Gatekeeper rejects them. Added a fail-closed Developer ID signing,
  notarization, stapling, Gatekeeper, and checksum script; release credentials
  are still required before a distributable archive can be produced.
- Hardened optional semantic-model provisioning: the MiniLM downloader no
  longer disables TLS verification, is pinned to an exact upstream revision,
  verifies both artifact SHA-256 digests, and stages the pair before replacing
  local files.
- Bounded two beta-facing registries that still grew for the lifetime of the
  companion: the Live planner now retains at most 1,000 unexpired pending
  proposals, while Mix Review retains at most 500 metadata-only receipts and
  writes them atomically with owner-only permissions.
- Refreshed the 100-case independent-review packet against the current hybrid
  index and bound it to source, generator, fixture, index, and model digests.
  Adjudication decisions are now bound to that packet and both exact reviewer
  files, preventing a stale or copied approval from satisfying the gate.
- Fresh release decision: **ready for a supervised disposable-set internal
  beta** (`ABLETON_INTERNAL_BETA_0.1_GATE_2026-09-07.json`, 4/4 required pilot
  gates). A fresh `--check-live` run is still required immediately before an
  actual session.
- Qualified-beta blockers remain: two independent human review score files and
  adjudication, plus Developer ID signing and notarization. The real Ableton
  host-load check is complete. The colleague-owned UX folder remains untouched
  and is outside this sprint's engineering scope.

## Beta objective

Make KENN feel reliable and useful for a small group of real producers without
claiming that it is an autonomous DAW agent or a finished audio-generation
platform.

The beta promise is:

1. KENN can inspect a current Ableton Live session and return what it knows,
   what it does not know, and how fresh the state is.
2. KENN can answer in-scope audio-engineering questions with grounded,
   cited knowledge and honest abstention.
3. KENN can propose a bounded change to a qualified Live target, wait for
   explicit confirmation, apply it, read it back, and provide an undoable
   receipt.
4. KENN can analyse supplied/rendered audio and keep measured findings
   separate from generated material and Live state.
5. The companion and backend produce enough structured health, timing, and
   recovery evidence that a tester or developer can diagnose failures without
   needing the development team beside them.

The companion UI is being developed separately by a colleague. This sprint
owns the backend contracts, state transitions, diagnostics, and receipts that
the UI consumes, but not visual design or interaction polish.

## Deliberate beta boundaries

These are not beta blockers and should remain disabled or explicitly marked
experimental during this sprint:

- autonomous LLM-controlled Live writes;
- arbitrary plug-in/device parameter control;
- silent project saves or overwrites;
- destructive replacement of clips or files;
- AutoMix rendering as a product promise;
- full local MiniMax Music 3 inference;
- reference-audio remixing, streaming generation, or vocal identity claims;
- send/return-track mutation until independently qualified;
- general-purpose filesystem operations from model output.

MiniMax Music 3 remains an optional future provider. Its useful contribution
to this sprint is limited to shaping a provider-neutral creative brief and
caption contract; its weights and CUDA serving stack should not enter the beta
critical path. See [MiniMax research](MINIMAX_MUSIC3_KENN_RESEARCH.md).

## Current starting point

The repository already has substantial foundations:

- supervised AbletonOSC control for a bounded device/action set;
- confirmation, stale-state, readback, replay-rejection, receipt, and undo
  patterns;
- KENN-owned Mix Review and an indexed knowledge base;
- VST3/AU builds and compiled plug-in/server integration tests;
- typed MIDI/audio artifact and audition paths;
- explicit offline, unsupported, and evidence-limited behavior.

The working tree is currently dirty. The sprint begins by preserving and
reviewing those changes, not by resetting them or assuming they are complete.

## Priority order

### P0 — must ship for beta

#### 1. Backend state, observability, and failure contracts

Define every request and response to move through:

```text
offline -> inspecting -> proposal_ready -> awaiting_confirmation
         -> applying -> verified
```

Represent `stale`, `timeout`, `readback_failed`, `transport_uncertain`, and
`rolled_back` as distinct machine-readable states. A timeout must never be
treated as a failed write that is safe to retry automatically.

Acceptance criteria:

- every request and proposal carries connection state, target identity,
  snapshot age, operation stage, readback status, and failure reason;
- health and support diagnostics expose stage-specific latency and timeout
  information;
- receipts distinguish verified success, verified rollback, failed
  verification, and ambiguous transport;
- every error records whether retrying is safe, unsafe, or requires inspection;
- backend state transitions are covered independently of any UI implementation.

Add a small reliability/observability slice alongside this work:

- bounded request and generation queues with explicit capacity and expiry;
- correlation IDs across request, proposal, apply, readback, and receipt;
- stage timings for Live snapshot, proposal construction, OSC write,
  readback, and response serialization;
- redacted support diagnostics that never expose raw paths, credentials, or
  unbounded producer metadata;
- deterministic health checks for KENN, AbletonOSC, and optional subsystems.

#### 2. Finish the qualified Live action matrix

Keep the default matrix intentionally small and excellent:

- track selection/inspection;
- transport reads and the already-qualified bounded transport actions;
- EQ Eight;
- one or two clearly qualified parameters each for Glue Compressor,
  Saturator, Auto Filter, and Drum Buss;
- exact device insertion where the device family is allowlisted;
- identity-bound undo.

For every exposed parameter, record:

- exact Live device and parameter identity;
- type, raw range, display unit, and quantization;
- proposal-only behavior;
- successful write and readback;
- stale-target rejection;
- replay/duplicate rejection;
- inverse restoration;
- behavior when Live disappears at each stage.

Do not expose a parameter merely because Ableton reports a name. A parameter
needs a tested profile or must remain clarification-gated.

#### 3. Recovery and interruption qualification

Test the failure cases that matter in a real beta:

- Live closes during inspection;
- Live closes after proposal creation;
- Live closes during or immediately after a write;
- OSC acknowledgement is lost after a write;
- the companion restarts with a pending proposal;
- the target track/device changes before confirmation;
- the same confirmation is submitted twice;
- an undo is requested after the target has changed.

Acceptance criteria:

- no automatic retry after ambiguous transport;
- ambiguous outcomes become explicit `transport_uncertain` records;
- recovery is inspect-first and never blind;
- no successful receipt is issued without readback evidence.

#### 4. Grounded assistant qualification

Create a small held-out beta evaluation pack covering:

- common mix questions;
- Ableton workflow questions;
- unsupported or ambiguous requests;
- questions requiring measured audio evidence;
- prompt injection through filenames, track names, device names, and metadata;
- follow-up questions after a Live snapshot or Mix Review result.

Acceptance criteria:

- existing regression evaluations remain green;
- every answer cites or clearly identifies its evidence source;
- unsupported questions abstain instead of improvising;
- generated audio, filenames, and user claims are not treated as measured
  evidence;
- optional LLM rewriting cannot invent measurements, citations, or actions.

### P1 — should ship for a strong beta

#### 5. Mix Review human qualification

Run the current Mix Review engine against a small, rights-cleared real-mix
corpus plus synthetic edge cases. Use at least two independent listeners or
reviewers for the user-facing findings.

Record:

- useful findings;
- false flags;
- missed problems;
- confusing wording;
- cases where the engine must say “not evaluated.”

Keep the measured scope honest. Do not promote masking, tonal balance,
arrangement, or genre claims until each has its own evidence and evaluation.

#### 6. Artifact and audition workflow

Finish the generated/imported asset experience for the capabilities that are
actually enabled:

- clear generated-versus-measured provenance;
- safe artifact metadata and content hashes;
- local audition without automatic Live mutation;
- bounded candidate comparison;
- confirmation-gated import;
- readback and undo after import.

An artifact path or producer-specific metadata must never become an arbitrary
filesystem or Live command path.

#### 7. Installation and support path

Produce one repeatable private-beta setup path:

- clean checkout or packaged companion;
- AbletonOSC installation/check;
- plug-in install and DAW restart instructions;
- health check;
- disposable Live test set;
- rollback/uninstall instructions;
- support bundle with versions, route health, and redacted receipts.

The backend should provide machine-readable health and capability responses so
the separately developed UI can clearly represent offline, connected,
confirmation-pending, and readback-pending states.

### P2 — only if P0/P1 are green

- broader device parameter profiles;
- richer track-role and project-context explanations;
- sample-library recommendations and supervised sample import;
- optional AudioGen/MiniMax provider adapter in dry-run mode;
- improved caption/creative-brief support;
- additional MIDI generation and audition polish.

## Ten-day execution schedule

### Days 1–2: baseline and product contract

- preserve the dirty working tree and inventory each change;
- run the full current test suite and record the baseline;
- freeze the beta scope and supported device/action matrix;
- write the machine-readable state-machine contract;
- identify and fix any P0 crash, import, or startup issue.

### Days 3–4: Backend state and Live qualification

- finish machine-readable inspection/proposal/apply/readback states;
- add correlation IDs, stage timings, bounded queue behavior, and redacted
  support diagnostics;
- complete parameter profiles for the small beta matrix;
- test display-unit versus raw-value boundaries;
- add missing proposal, stale, replay, and undo fixtures;
- run the first controlled real-Live qualification pass.

### Days 5–6: interruption and recovery

- execute the Live-loss and acknowledgement-loss scenarios;
- verify no blind retries or false success receipts;
- test companion restart and pending-proposal behavior;
- fix recovery state transitions and support diagnostics;
- repeat the real-Live matrix after fixes.

### Days 7–8: assistant and audio evidence

- build and run the held-out knowledge/command evaluation pack;
- complete the human Mix Review review packet;
- fix overclaiming, citation, and abstention failures;
- qualify the enabled artifact/audition/import path;
- keep generation clearly separate from measurement.

### Day 9: packaging and beta rehearsal

- test the clean installation path;
- load the plug-in in a disposable Ableton set;
- perform the scripted smoke test from the tester guide;
- verify support bundle and rollback instructions;
- run all automated tests and release checks from a clean environment.

### Day 10: release gate

- triage every open issue as ship, defer, or block;
- repeat the critical Live scenarios from a clean state;
- freeze the beta matrix and known-limitations document;
- prepare tester guide, feedback form, and rollback procedure;
- only then distribute the private beta build.

## Release gates

The beta ships only if all of these are true:

- full automated test suite is green;
- no known P0/P1 safety, data-loss, or false-success issue remains;
- every exposed Live mutation is confirmation-gated, identity-bound,
  readback-verified, receipt-backed, and undoable;
- ambiguous transport never triggers automatic retry;
- at least one complete clean-install and rollback rehearsal passes;
- the held-out assistant evaluation has no fabricated citations, measurements,
  or unsupported Live actions;
- human review has documented the actual Mix Review strengths and failures;
- the tester guide lists every enabled capability and every important
  limitation;
- MiniMax, AutoMix, and autonomous LLM writes are either disabled or clearly
  labelled experimental and excluded from the beta promise.

## What success looks like

A beta tester should be able to ask KENN:

> “Show me what is on track 4, explain the likely issue in this supplied mix,
> and propose reducing EQ Eight band 2A by 3 dB.”

KENN should inspect current state, distinguish measured evidence from
interpretation, show the exact target and before/after values, wait for
confirmation, apply once, verify the result, and offer a receipt-backed undo.

That coherent supervised loop is more valuable for beta than adding another
large generative model before the core interaction is dependable.

## Post-beta backlog

- MiniMax Music 3 external-provider adapter and structured-caption workflow;
- local/remote GPU worker management;
- autonomous LLM planning after a successful shadow and human-review gate;
- more device families and display-unit mappings;
- richer project/session memory;
- qualified AutoMix and offline candidate comparison;
- broader real-mix analysis, including masking and tonal-balance evidence;
- public release licensing, telemetry, privacy, and support review.
