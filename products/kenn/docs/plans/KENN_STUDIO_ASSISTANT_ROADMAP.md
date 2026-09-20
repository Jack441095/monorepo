# KENN Studio Assistant — End-to-End Roadmap

**Status:** Stages 1 and 2 complete. Stage 4, item 1 (knowledge Q&A exposed via MCP) complete. Stage 3, items 1-2 complete (item 3, Live import, confirmed blocked -- same class of gap as send/return control). Stage 5: scene launch and clip-slot stop real-Live qualified, two real bugs found and fixed in the process.
**Date:** 2026-09-05

## Context

KENN started as (and already is, to a remarkable degree) a safety-first Ableton
Live control system: deterministic natural-language parsing, exact
track/device/parameter identity resolution, confirmation-gated proposals,
readback verification, receipts, and identity-bound undo — qualified against
real Live for track/transport control, EQ Eight, Glue Compressor, Saturator,
Auto Filter, Drum Buss, and supervised MIDI clip creation, with an MCP facade
exposing ~27 tools to external LLM clients. A parallel C++ native layer
mirrors part of this (hardened this session: an `NDEBUG`/`assert()` testing
gap was found and fixed, along with two real parser bugs and a real
reliability gap in the direct OSC read layer — see
`docs/ABLETON_ASSISTANT_CURRENT_STATE.md`'s 2026-09-05 entries).

The goal is to grow this into a full studio assistant: more Ableton control,
mixing feedback like an audio engineer would give, sample-selection help, and
general audio-engineering knowledge — "like Claude, but specializing in
Ableton" (with SLO, a separate audio-classifier project at NITE_DSP,
referenced as a design inspiration for evidence-gated classification, not as
code to reuse).

Two research passes found the real starting point for each pillar:

- **Ableton control**: existing-device parameter control is *already*
  device-name-agnostic (it matches any device name present in the live
  snapshot, not a hardcoded list) — no work needed there. The real gaps were:
  scene launching and clip-slot stop were wired at the raw OSC-client level
  (`launch_scene`, `create_scene` in `apps/backend/src/kenn/ableton_osc_bridge.py`) but
  **completely unused** by the intent parser, action service, or MCP facade;
  device *insertion* is capped at a 5-device allowlist that only grows after
  real-Live reversible-parameter qualification (by design); the C++ local
  parser's device-name table only recognized 7 phrases; and track-send
  (return) control is blocked because the vendored AbletonOSC Remote Script
  has no return-track enumeration endpoint.
- **Mix suggestions**: *not* greenfield. `mix-review/core/local_engine.py`
  already produces qualified findings (clipping, headroom,
  silence/truncation, channel imbalance, phase/mono-compatibility, DC offset,
  loudness estimate) each with `explanation`, `suggested_next_step`,
  `severity`, `confidence`, and a derived `action_plan`.
  `apps/backend/src/kenn/project_analysis.py` already has a `Recommendation` dataclass
  and `recommendations_from_mix_review()`, exposed via the MCP tool
  `mix_review_recommendations`. What's missing is prioritization/dedup across
  families, genre-aware context (via the existing `genre_profiles.py`), a
  more conversational tone, and an explicit (never-auto-inferred) handoff to
  a real Live proposal.
- **Sample selection**: genuinely greenfield — zero existing sample
  database/indexer/search code anywhere in the repo. Only reusable pieces are
  `genre_profiles.py` (genre detection + audio targets) and
  `track_classifier.py` (instrument-role classification from track names).
  KENN will be pointed at a local sample folder with mostly meaningful
  filenames/folder structure (metadata comes from that, not embedded tags,
  for now).
- **General audio-engineering knowledge**: already real and working. The
  `chat/` app wraps `apps/backend/src/kenn/core/chat_answer.py` /
  `apps/backend/src/kenn/retrieval/` — a deterministic hybrid BM25+embedding retrieval
  engine (ONNX embedder, no LLM required) over 244 curated markdown notes in
  `apps/backend/src/kenn/Training_Data_Notes/`, with a real abstention mechanism
  (`chat_retrieval.py::query_is_out_of_scope`) that refuses out-of-scope or
  weakly-matched questions instead of guessing. It is **not** exposed via
  MCP today — only through two separate HTTP surfaces (public `chat/app.py`,
  local companion `apps/backend/src/kenn/server.py`).

Every stage below must keep KENN's existing design laws intact: one mutation
boundary (`LiveActionService`), exact identity before any write, no silent
inference of a Live target from measured/generated/library evidence, real
confirmation + readback + receipt for every new mutating action, and no new
work on the real-time audio callback.

## System architecture (attached from `KENN_INTEGRATED_AUDIO_INTELLIGENCE_ARCHITECTURE.md`)

### Design laws

1. **Facts before interpretation.** Every useful context item has a source,
   timestamp, version, and confidence.
2. **Unknown is a valid result.** Missing, ambiguous, unsupported, stale, and
   out-of-distribution states are reported explicitly.
3. **The LLM is a planner, not a privileged executor.** It may select typed
   tools and compose recipes; it cannot emit raw OSC, arbitrary Python, or
   unreviewed filesystem operations.
4. **One mutation boundary.** All Live writes go through the existing
   proposal/confirmation/stale-state/readback/receipt/undo service
   (`LiveActionService`).
5. **Creative output is not evidence.** AudioGen output is generated
   material; Mix Review output is measured material; a sample-library
   suggestion (once Stage 3 exists) is neither — three distinct evidence
   categories that must never be conflated.
6. **Offline renderers stay offline.** AutoMix may create candidates and
   reports, but does not silently alter the Live set.
7. **Classification is evidence-gated.** Measure separability on real
   held-out data before shipping a new label, and stay silent when
   confidence is not earned (the methodology SLO's classifier design
   inspires, not its code).
8. **Every meaningful change is reversible** — or, when it genuinely isn't
   (scene launch, clip stop), the system says so explicitly instead of
   inventing an undo.
9. **Real-time audio stays deterministic.** The C++ plug-in audio callback
   does meters and bounded feature extraction only. Python, the LLM, disk
   I/O, and network calls stay off the callback.

### High-level architecture

```text
                         User
                           |
                UI / KENN plug-in / MCP client
                           |
                           v
              +-----------------------------+
              | KENN intent + recipe layer  |
              | deterministic parser first  |
              | optional LLM planner        |
              +-------------+---------------+
                            |
                            v
              +-----------------------------+
              | Versioned SessionContext    |
              | facts + evidence + jobs     |
              +--+-----------+-----------+--+
                 |           |           |
                 v           v           v
       Ableton/MCP      Mix Review    SLO classifier
       Live snapshot    measurements  roles/subtypes
                 |           |           |
                 +-----------+-----------+
                             |
                             v
                  typed tool/recipe planner
                             |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
   LiveActionService     AudioGen jobs        AutoMix jobs
   OSC + readback        WAV + MIDI           offline candidates
        |                    |                    |
        v                    v                    v
   Ableton Live        generated assets      render/report store
        |                    |                    |
        +--------------------+--------------------+
                             v
                 receipts, memory, evaluation
```

### Current state vs. target integration (selected rows)

| Surface | Current verified state | Target integration |
|---|---|---|
| AbletonOSC | Working local transport and fresh Live snapshots | Remain the default backend behind KENN's safety service |
| KENN MCP facade | Read tools, confirmation-only proposals, guarded apply/undo | Expose the shared context and typed recipes |
| Live control | Track/device/parameter, scene launch, clip-slot stop, supervised MIDI clip creation qualified/wired | Send/return control once the Remote Script gap closes; broader device families after real-Live qualification |
| Mix Review | KENN-owned deterministic WAV boundary with seven qualified fault families | Feed measured findings into prioritized explanations and proposal generation (Stage 2) |
| LLM command planning | Optional shadow/active code exists; capability identity, unit, and range gates reject unsafe plans; deterministic parser remains authoritative | Activate only after complete shadow agreement, latency, and human-review gates |

Full architecture detail (SessionContext schema, AudioGen/AutoMix
integration, safety/failure-state vocabulary, implementation roadmap
Phases 0-6) lives in `KENN_INTEGRATED_AUDIO_INTELLIGENCE_ARCHITECTURE.md`;
this section is a condensed attachment, not a replacement.

## Open-source landscape (informs, doesn't replace, the plan above)

A web research pass turned up existing open-source projects relevant to each
pillar. None of these should be pulled in wholesale — KENN's core safety
property (typed tools only, no raw OSC/arbitrary code execution reaching an
LLM) is stricter than most of them — but several are worth learning from or
directly reusing as offline/library dependencies:

- **Ableton control / MCP**: several open-source "Ableton MCP" projects
  already exist —
  [ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp) (the most
  widely used; Remote Script + socket server + MCP server for track/clip/
  MIDI composition),
  [Simon-Kansara/ableton-live-mcp-server](https://github.com/Simon-Kansara/ableton-live-mcp-server)
  (exhaustively maps AbletonOSC's own OSC address space to MCP tools — worth
  diffing against KENN's vendored AbletonOSC fork to see if they've solved
  the return-track/send enumeration gap),
  [xiaolaa2/ableton-copilot-mcp](https://github.com/xiaolaa2/ableton-copilot-mcp)
  (built on `ableton-js`, covers Arrangement View / MIDI editing / audio
  recording — a useful reference for scope beyond Session View if KENN grows
  that direction later), and
  [bschoepke/ableton-live-mcp](https://github.com/bschoepke) (explicitly
  exposes Ableton's full object model via arbitrary Python `eval` — this is
  the anti-pattern KENN's typed-proposal boundary exists to avoid; useful
  only as a "what not to do" reference, not as code to adopt).
- **Sample BPM/key tagging**: [Audet](https://github.com/makalin/Audet)
  (librosa + Essentia, Camelot key notation, batch analysis, drag-and-drop
  GUI) and [libraz/bpm-detector](https://github.com/libraz/bpm-detector)
  (Python, BPM + musical key) are realistic references for a later
  enhancement to Stage 3 once filename-based indexing is in place —
  extracting real BPM/key from audio content instead of relying only on
  filenames. This is offline/batch analysis, so heavier dependencies
  (librosa/Essentia) are acceptable here in a way they are not for the
  real-time plug-in path.
- **Mix analysis / mastering**:
  [sergree/matchering](https://github.com/sergree/matchering) (reference-
  matching mastering: RMS/frequency response/peak/stereo width matching) and
  [Essentia](https://essentia.upf.edu/) (C++ MIR library with EBU R128
  loudness meters and audio-quality-problem detection) are directly relevant
  to Stage 2: KENN's own docs already list calibrated LUFS/LRA and true-peak
  as explicit gaps the current repo-owned analyzer abstains on
  (`docs/ABLETON_ASSISTANT_CURRENT_STATE.md`, "Not verified here" /
  `NOT_EVALUATED_FAULT_FAMILIES`). Essentia's R128 implementation is a
  credible, offline (non-realtime) path to closing that specific gap rather
  than building calibrated loudness measurement from scratch — this should
  be evaluated as an explicit sub-task inside Stage 2, not assumed.
- **Local reference material already on disk**: the user's
  `<LOCAL_VOLUME>/testing-for-NITE-DSP/` volume already has a
  `sample_pack_testing/` folder (~36 named sample packs — drum kits,
  percussion, synths, vocal packs, cinematic/organic/lo-fi categories) and a
  `testing_track_stems/` folder (per-song stem folders plus `_automix_out`
  and `_zips`). These look like a ready-made fixture set for Stage 3's
  indexer tests.

## Stage 1 — Ableton control expansion (build first; no live Ableton required)

1. **Wire scene launching end-to-end.** ✅ Done. `SUPPORTED_SCENE_ACTIONS` /
   `propose_scene_action` + an `execute()` branch in
   `apps/backend/src/kenn/core/live_action_service.py`, natural-language parsing
   ("play/launch/fire/trigger scene N") in `live_intent.py`, dispatch in
   `live_command.py`. Scene firing has no natural inverse value, so
   `propose_undo` explicitly refuses rather than inventing one. Full test
   coverage: parser, ambiguity, refusal, identity, fake-Live lifecycle,
   replay rejection.
2. **Wire clip-slot stop.** ✅ Done. Same shape as scene launching; requires
   an explicit clip-slot number rather than guessing which clip is playing.
3. **Expand the C++ local parser's device-name table.** ✅ Done, and
   updated again 2026-09-06: the *insertion* regex (`add`/`append`/`insert`/
   `put`/`load`) was still missing `Compressor`, `Hybrid Reverb`, and `Echo`
   even after they were promoted into `DEVICE_INSERTION_ALLOWLIST` -- added
   all three, confirmed `"glue compressor"` still resolves to the distinct
   device rather than being shadowed by the new bare `"compressor"`
   alternative. Compiles and runs standalone (zero JUCE dependency); 10/10
   contract cases pass. See `docs/ABLETON_ASSISTANT_CURRENT_STATE.md`'s
   2026-09-06 entry.
4. **Candidate device list for insertion.** ✅ Done, and fully promoted
   since. `CANDIDATE_DEVICE_INSERTION_ALLOWLIST` originally listed Reverb,
   Delay, Compressor, and Limiter as candidates pending real-Live
   qualification. Reverb/Delay/Limiter were dropped after real-Live testing
   found their plain names resolve to the wrong stock device via
   AbletonOSC's browser search (`"Reverb"` → `"Convolution Reverb"`, etc.);
   the correctly-resolving names (`Hybrid Reverb`, `Echo`) plus `Compressor`
   all passed a real reversible-parameter qualification and moved into the
   active `DEVICE_INSERTION_ALLOWLIST`. `CANDIDATE_DEVICE_INSERTION_ALLOWLIST`
   is now empty -- there is currently no pending candidate.
5. **Document send/return-track control as explicitly blocked.** ✅ Done,
   then fully closed 2026-09-06 (both halves) — see
   `docs/ABLETONOSC_ROUTE.md`'s "Track-send (return) control: fully closed,
   natural-language control shipped" section. Ableton's own bundled Python
   model stubs confirmed `Song.return_tracks` is real and readable; the
   vendored AbletonOSC fork gained three new read-only endpoints mirroring
   the existing regular-track enumeration pattern, and
   `kenn.ableton_osc_bridge.get_return_tracks()` /
   `GET /api/ableton/osc/return-tracks` expose it. Verified live: the
   disposable set's two real return tracks (`A-Reverb`, `B-Delay`) came
   back correctly through the running companion. The natural-language half
   (wiring a return track's name into `live_intent.py`/`live_command.py`/
   `LiveActionService.propose_send_action`) shipped the same day: exact
   case-insensitive name match wins, an unambiguous substring match is a
   safe fallback, real-Live verified end to end including a stale-undo
   fix found and closed in the same pass. 3 + 11 new tests across both
   halves; full regression **539/539** at the time.
6. **Root-cause the device-insertion name-mismatch at the browser-search
   layer.** ✅ Code done, real-Live reload pending (2026-09-05). The earlier
   Stage 5 auto-revert fix cleaned up *after* the wrong device was inserted;
   this closes the actual cause inside the vendored AbletonOSC fork. The bug
   was breadth-first substring matching winning over an exact match found
   later in the tree — exactly reproducing the real "Reverb" →
   "Convolution Reverb" finding. Fixed via a new, Live-independent
   `abletonosc/browser_search.py` (unit-testable without a running Live
   instance, unlike the rest of this vendored fork) with two-pass logic:
   exact match anywhere always wins over any substring match. 6 new unit
   tests reproduce the exact real bug plus the substring fallback,
   category/leaf name collisions, and cycle safety. Deployed to the active
   Remote Scripts directory with an automatic rollback backup via
   `scripts/install_abletonosc.py --replace`. Real-Live re-verification
   needs a Live restart (to reload the Remote Script) — deliberately not
   done autonomously to avoid disrupting the user's running session; this
   is the next Stage 5 qualification step, re-running the exact
   `"Reverb"`/`"Delay"`/`"Limiter"` cases that surfaced the bug. **Re-verified
   against real Ableton 2026-09-06**: Live was restarted (with the user's
   approval) to reload the fixed Remote Script; all three cases now resolve
   exactly (previously "Convolution Reverb"/"Align Delay"/"Color Limiter").
   Final Live state matched the pre-restart snapshot exactly; full
   regression re-passed **469/469**. See
   `docs/ABLETON_ASSISTANT_CURRENT_STATE.md`'s 2026-09-05/06 entries.
6. **Broader phrasing pass.** Ongoing alongside items 1-2 (scene/clip
   synonyms already added); further passes as gaps are found.

**Verification**: focused pytest for each new action (parser/ambiguity/
refusal/range/identity/fake-Live lifecycle/replay), full repo-wide
regression (**412/412** as of this update), and native CTest (**9/9**,
stress-verified) after the C++ table change.

## Stage 2 — Mix-suggestion assistant

Builds directly on `Recommendation`/`action_plan`, which already exist.

1. ✅ Done. `prioritize_recommendations()` ranks by severity then confidence
   and merges exact-duplicate findings. An optional, explicitly-supplied
   (never audio-inferred) `genre` appends one advisory reference note from
   `genre_profiles.py`'s targets — it never changes a finding's severity or
   claims a pass/fail verdict against the (uncalibrated) measured loudness.
2. ✅ Done. `summarize_recommendations()` groups the ranked list into
   deterministic "fix first / worth addressing / for reference" plain
   language, still evidence-cited per finding.
3. ✅ Already done from prior work — `create_mix_review_recipe_proposal`
   already sends the review id to KENN, which fetches/sanitises the review
   and binds it as evidence into the recipe confirmation and receipt,
   without inferring the Live target from the audio.
4. ✅ Done (stretch item, 2026-09-05). Calibrated ITU-R BS.1770-4 integrated
   LUFS/LRA and 4x-oversampled true-peak, closing the gap this plan flagged
   above under "Open-source landscape". Used `pyloudnorm` (MIT) instead of
   Essentia (LGPL/AGPL dual license, worse fit here) plus
   `scipy.signal.resample_poly` for the oversampling. Honest optional-
   dependency abstention (never a fabricated value) when `pyloudnorm`/
   `scipy`/numpy acceleration is unavailable or the input is shorter than
   BS.1770's 400 ms gating block. Validated against the known -3.01 LUFS
   mono full-scale-sine reference. Flows through to
   `mix_review_recommendations` automatically via the existing generic
   `_safe_flag()` conversion in `local_mix_review_service.py` — no adapter
   changes needed. Five new tests; full regression **447/447**. See
   `docs/ABLETON_ASSISTANT_CURRENT_STATE.md`'s 2026-09-05 entry for detail.

**Verification**: unit tests on the new ranking/synthesis functions against
fixed finding sets; MCP smoke test for the recommendation → recipe handoff
using a fake Live snapshot.

## Stage 3 — Sample selection help (greenfield)

Starts once an explicit local folder path is given to index (filenames/
folder structure are the metadata source, not embedded tags, for a first
pass).

1. ✅ Done. `apps/backend/src/kenn/core/sample_library.py` scans one explicitly
   approved folder (`KENN_SAMPLE_LIBRARY_ROOT`), reading only filenames/
   folder structure — no audio content opened, analyzed, or hashed. Each
   entry addressed by an opaque id; no raw filesystem path is ever returned.
2. ✅ Done. `search_samples()` ranks by filename/folder tag and token
   overlap — advisory only, clearly labelled as a library reference, never
   "measured" or "generated" (a fourth evidence category). Exposed
   read-only as the MCP tool `search_sample_library`. Real smoke test
   against the actual `sample_pack_testing` library indexed **28,330** WAV
   files in **1.44 s** with genuinely relevant results for `"dark 808 kick"`.
3. ✅ Done (2026-09-06) -- implemented end to end, real-Live verified, one
   known scale limitation honestly documented. Builds on the research above:
   `integrations/ableton-osc/abletonosc/browser_sample_search.py` (new,
   Live-independent, 8 unit tests) reconstructs a real absolute path from a
   browser item's `userfolder:<root>#<relative>` URI (format learned live)
   and does a **depth-first** bounded search of `browser.user_folders` for
   an exact match -- depth-first mattered for more than style: an initial
   breadth-first version visited 9000+ items without reaching a real file 5
   folders deep in a large personal library, since breadth-first exhausts
   every sibling at each level before going deeper. The new
   `/live/track/import_sample` OSC endpoint refuses an occupied clip slot,
   re-fetches `Track`/`ClipSlot` references fresh after `load_item()` (they
   go stale otherwise), and reports the real created clip's name back.
   `apps/backend/src/kenn/core/sample_import_service.py` (new) follows the exact
   propose/execute/undo shape already established for MIDI clips; the
   proposal never carries a raw path -- only the sample's opaque id, with
   the absolute path re-resolved fresh at execute time. Exposed as
   `POST /api/ableton/sample-import/proposal` and the MCP tool
   `import_sample_to_live`. Real end-to-end verification: the full propose
   -> confirm -> execute -> receipt pipeline was run against the real
   companion and real Ableton; the honest AbletonOSC-side failure (sample
   not found in a bounded search) correctly produced a `status: "failed"`
   receipt rather than a false success, with the path never appearing in
   any client-visible payload and the target clip slot confirmed unchanged.
   **Known, honestly-documented limitation, not resolved in this pass**:
   search completeness/speed against a real, large, deeply-nested personal
   library isn't fully characterized -- the same real file was found
   near-instantly in one attempt and not found (bounded search exhausted)
   in another, depending on which registered folder's subtree got explored
   first. See `docs/ABLETON_ASSISTANT_CURRENT_STATE.md`'s 2026-09-06 entry
   for the full trail. 15 new tests; full regression **494/494**.
4. ✅ Done (stretch item, 2026-09-05). Real, on-demand BPM/pitch-class
   estimation via `librosa` (optional dependency), following the
   `makalin/Audet` reference noted in Open-source landscape. Deliberately
   separate from the filename-only bulk scan/search — a regression test
   guards that boundary so the 28k-file scan stays fast. BPM and key are
   estimated independently and abstain honestly (missing dependency,
   unreadable/too-short file, no stable tempo/pitch) rather than guessing;
   key detection reports a pitch class only, never major/minor. Exposed as
   the MCP tool `analyze_sample_library_entry`. Validated against known
   synthetic references (120 BPM click track, A4/440 Hz tone) and a real
   smoke test against 5 random files from the actual sample library — one
   estimated key matched its own filename's stated pitch. 9 new tests; full
   regression **456/456**.

5. ✅ Done (stretch item, 2026-09-05). Real, bounded sample-similarity
   search via a reused PANNs Cnn10 512D embedding (MIT code / CC BY 4.0
   training data), following the "PANNs-embedding-based sample similarity
   search" candidate. The exact model file was reused from the sibling SLO
   project, where only the embedding output was already exported and
   validated -- SLO's classifier heads and taxonomy labels are not reused
   at all, consistent with `SLO_TO_KENN_REUSE_PLAN.md`'s conclusion. A
   caller must supply a keyword-filtered candidate pool (capped at 25) --
   this never scans the whole library, since embedding inference is real
   per-file neural-network work. Exposed as the MCP tool
   `find_similar_samples`. Real smoke test against the actual library
   returned acoustically sensible top matches (0.96+ cosine similarity)
   for a kick-sample query. `onnxruntime` was already a KENN dependency;
   no new one was added. 10 new tests; full regression **469/469**.

**Verification**: 10 indexer/ranking unit tests against a small fixture
folder, 2 MCP tests (configured/unconfigured root), 9 tests for the
BPM/key estimator, 10 tests for the similarity search; full regression
**469/469** passed.

## Stage 4 — General audio-engineering knowledge Q&A

Already works; mainly needs exposing and growing.

1. ✅ Done. Added the MCP tool `ask_audio_engineering_question` and
   `POST /api/knowledge/ask`, both backed by a new `grounded_knowledge_answer()`
   that reuses the existing retrieval engine with the same specialist-dispatch
   sealing `chat/app.py`'s public boundary already uses (null orchestrator,
   `allow_llm=False`) — a knowledge question can never be misrouted into an
   Ableton/Mix Review/AudioGen side effect. Verified real grounded answers and
   honest out-of-scope abstention.
2. ✅ Done (2026-09-06). Manually probing plausible producer questions (not
   in the curated eval corpus, which is 100% passing and so surfaces no
   gaps on its own) found a real one: "How do I use Max for Live devices?"
   incorrectly routed to a generic clarification prompt instead of
   `"ableton"`. Root cause: `route_query`'s topic classification
   (`TOPIC_SYNONYMS` in `kenn/retrieval/retrieval.py`) had no entry
   recognizing "max for live" / "m4l" / "amxd" phrasing at all -- a pure
   routing gap upstream of retrieval, not a missing note by itself. Added
   both: the missing topic terms (to the existing `"automation"` topic,
   which already routes to Ableton) and a new
   `ableton-max-for-live-overview.md` note (the existing
   `ableton-max-modulation-devices.md` only covered the bundled LFO/Shaper/
   Expression-Control utilities, not Max for Live as a workflow concept).
   Measured before/after: `found=False` (clarify prompt) before, `found=True,
   confidence=high`, grounded in the new note, after -- verified through the
   full engine directly and through the running companion's real
   `/api/knowledge/ask` endpoint. The public "mix advice only"
   `chat/eval_runner.py`/`chat/app.py` surface applies its own separate,
   intentionally stricter scope gate (`MIX_ADVICE_TERMS`) unrelated to this
   fix -- this query is correctly out of scope there by design, so no case
   was added to that harness; a focused regression test was added instead
   at `apps/backend/src/kenn/tests/test_chat_max_for_live_routing.py`, which exercises
   the full internal engine. Full regression **471/471**; public eval
   harness unaffected, still 100% passing.
3. ✅ Done (2026-09-06). `ask_audio_engineering_question` / `POST
   /api/knowledge/ask` now accept an optional `session_id`. When a question
   names exactly one instrument role (e.g. "why is my vocal getting
   masked") and a live Ableton snapshot is available, the new
   `track_classifier.find_tracks_by_question_role()` reuses the existing
   name-based track-role classifier's own regex patterns against the
   question text, matches it against each track's real classified role, and
   appends a clearly-labeled "Live session evidence" section citing the
   actual track name/index/device list -- never a guess, never inferred
   audio characteristics beyond what's genuinely observed. With no
   session_id, an ambiguous/unnamed role, or no Live connection, behavior is
   identical to before (purely additive). Verified real end-to-end via the
   running companion: a fake two-track snapshot with a "Vocal" track
   correctly surfaced its exact devices; the actual disposable set (no
   vocal-named track) correctly returned no evidence rather than fabricating
   any. 9 new tests (pure role-matcher, HTTP-level with/without session_id,
   MCP passthrough). Full regression **480/480**.

**Verification**: existing `chat/tests` and `chat/evals` harness; add a
focused MCP-tool test.

## Stage 5 — Real-Live qualification pass

Once Ableton + the KENN companion are running again, qualify everything
built fixtures-first in Stage 1 against the real disposable set (scene
launch, clip-slot stop, each new candidate device's one reversible
parameter), following the existing qualification-runner pattern
(`scripts/qualify_ableton_live_*.py`). Nothing from Stage 1 gets treated as
trustworthy/qualified before this pass, matching the existing discipline for
Glue/Saturator/Auto Filter/Drum Buss.

**Scene launch and clip-slot stop: ✅ qualified (2026-09-05).** Started
Ableton + the companion for the first time this session on the same
disposable four-track set. Qualifying found and fixed two real bugs that no
fixture test had caught (the fixture test doubles were more permissive than
the real bridge):
- Scenes were silently invisible to command parsing, because the fast
  topology-only snapshot command parsing uses had scene-name fetching
  bundled into the same conditional batch as mixer/transport values. Fixed
  with a new `get_scene_names()` and a targeted enrichment step that only
  runs when a command mentions "scene".
- `is_triggered` can transition (to actually playing) faster than one
  network round-trip can observe it — a real scene fire that genuinely
  started playback still read back `is_triggered=false`. Fixed by recording
  whether transport was already playing before the proposal, and accepting
  "transport now playing" as corroborating evidence only when it's known
  transport was stopped beforehand (no false-positive risk). The
  pre-existing, separately-qualified `clip_audition_service.py` was observed
  to have the identical race live during this session — noted as a known
  gap in that service, not fixed here (out of scope for this pass).

Both fixes are covered by new regression tests using a fake-Live double that
reproduces the exact race. After the fixes: real confirmed apply with
genuinely verified readback, exact replay rejection, and the deliberate "no
bespoke undo" refusal for both actions, all passed cleanly. A temporary test
clip was removed via its identity-bound undo; final Live state matches the
original disposable set exactly. Full regression: **440/440**.

**Candidate devices: qualified, with a significant finding (2026-09-05).**
Tested all four originally-listed candidates (`Reverb`, `Delay`, `Compressor`,
`Limiter`) directly against AbletonOSC's browser-search insertion:

- **Three of four candidate names silently resolved to the wrong device.**
  `"Reverb"` → `"Convolution Reverb"`, `"Delay"` → `"Align Delay"`,
  `"Limiter"` → `"Color Limiter"` — none the plain stock device a user
  would expect. Only `"Compressor"` resolved correctly.
- The existing, already-shipped `execute_device_insertion()` correctly
  reports `verified=False` on this mismatch (never a false success) — but
  had **no automatic cleanup**. ✅ **Fixed and re-verified against real
  Ableton.** `_revert_mismatched_insertion()` now auto-removes the wrongly
  inserted device, deliberately narrow (only acts on exactly one new device
  in the expected position with everything else unchanged), reports an
  explicit `auto_revert` field on the receipt, and re-ran the exact
  `"Reverb"` → `"Convolution Reverb"` case live: the wrong device was
  removed and `4-Audio` ended empty, same as it started. 2 new regression
  tests. Full regression **442/442**.
- `CANDIDATE_DEVICE_INSERTION_ALLOWLIST` updated to the names that actually
  resolve correctly: `"Hybrid Reverb"` and `"Echo"` (still unqualified —
  insertion for them remains blocked).
- `"Compressor"` passed a full real-Live reversible-parameter qualification
  (`Threshold` 0.85 → 0.5 → 0.85, verified readback, exact replay rejected,
  device removed) and is now promoted into the active
  `DEVICE_INSERTION_ALLOWLIST`.

Final Live state after every test this session: all four tracks, zero
devices, transport stopped — exactly the original disposable set. Full
regression: **440/440**.

## Sequencing

1 → 4a (cheap, reuses everything, can slot in anywhere) → 2 → 3 → 5,
revisiting Stage 5 qualification for each stage's new Live-facing pieces as
Ableton becomes available.
