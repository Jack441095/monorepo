# KENN GLM Full Assistant — Tracker

The live checklist for the programme in
[`KENN_GLM_FULL_ASSISTANT_BUILD_PROMPT_2026-09-23.md`](../../../../KENN_GLM_FULL_ASSISTANT_BUILD_PROMPT_2026-09-23.md)
(monorepo root). Tick items in the same commit as the work that completes them, and add
the date and a pointer to the evidence (`docs/evidence/…`) or commit.

**Baseline (2026-09-23, `5d7089c`):**
- Tests: backend 1,414 passed (5 skipped), frontend 21 passed, production build ok.
- Demo gate: 1/10 rehearsals.
- Devices: 11 profiles across 8 devices.
- LLM stage: `shadow`.
- Retrieval: BM25-only.

## Waiting on owner

- [ ] Review the 100 drafted phrasings in `tooling/data/natural_holdout_candidates.jsonl` (labels: explicit target+amount → action, vague → clarify); approved ones move into the curated holdout
- [ ] OK a `~/kenn_*` work folder on the GPU box (GPU 0, `/mnt/data`) for C6 LoRA training — text-only corpus, no audio

- [ ] Demo rehearsals 2–10: owner-run, see `docs/evidence/KENN_INVESTOR_DEMO_REHEARSAL_LOG.md`
- [ ] Say when Live is free, so I can run `deploy_abletonosc.py --apply --reload` (hot reload, no restart needed) and prove A2's selection fix and A3 on real Live

## Phase A — Harden the foundation

- [x] **A1 UI-path test harness** (2026-09-23, evidence `docs/evidence/KENN_A1_UI_PATH_HARNESS_2026-09-23.md`)
  > **Plan (2026-09-23):**
  > 1. Record the real demo set once (`tooling/scripts/record_fake_live_fixture.py`) into a JSON fixture of tracks, returns, devices and parameters with display strings.
  > 2. Add a `KENN_LIVE_BACKEND=fake` backend (`core/fake_live.py`) that replays the fixture statefully, with writes and readback.
  > 3. Put the 13-prompt demo gate through `/kenn/api/ask`.
  > 4. Add Playwright (system Chrome via `channel: 'chrome'`, no browser download) specs that drive the real UI against a companion started with the fake backend.
  >
  > Proof: specs pass locally without Live, and the gate passes against both real and fake Live.
  - [x] Playwright set up with Homebrew Node; one smoke test that types in chat and reads the reply
  - [x] Tests for Apply, Undo, Dismiss and chat "Undo that." card states (5/5 green)
  - [x] Fake-Live record/replay at the OSC boundary; CI runs without Live
  - [x] The 13-prompt demo script gate also runs through `/kenn/api/ask`: 10/10 on real Live, slowest 597.6 ms
- [ ] **A2 Known defects**
  - [ ] AbletonOSC `view.py`: selecting a return or master track no longer raises; KENN reports it. **Code and tests done (2026-09-23); real-Live proof waits on A3 deploy + Live restart.**
  - [x] "Pan the Synth center." proposes pan 0 (5 phrasings; centre frequency excluded; verified on real Live, 2026-09-23)
  - [x] Statement-versus-request stage before retrieval: narration about KENN and typed card labels get short replies; problem statements and topics still reach chat (verified on real Live, 2026-09-23)
  - [x] Simulated voice removed: the unreachable `process_audio_features` fake is deleted and the module is documented as text-only (2026-09-23)
- [ ] **A3 Remote Script deploy tool** (code done; first real deploy pending)
  - [x] `tooling/scripts/deploy_abletonosc.py`: plan by default; `--apply` backs up, copies, stamps; `--reload` hot-reloads via `/live/api/reload` and flags files that still need a restart (2026-09-23)
  - [x] `/live/kenn/version` endpoint (reloadable `application.py`), `/api/ableton/remote-script` route, and a `remote_script` preflight check that fails on a stale or unstamped script (2026-09-23). **First real deploy + reload waits for Live to be free.**
- [ ] **A4 Demo gate 10/10** (owner-run; fix whatever it surfaces)

## Phase B — Live world model

- [ ] **B1 Read coverage** (code done 2026-09-23; real-Live proof needs the A3 deploy)
  > `core/live_world_model.py` + `/api/ableton/world-model`: one evidence-only model with per-section availability and a fingerprint that ignores meters. New hot-reloadable reads in AbletonOSC `song.py`: `/live/kenn/get/bus_mixer`, `/live/kenn/get/device_tree` (rack chains, depth 3), `/live/kenn/get/device_parameters` (display strings + automation state). The fixture recorder captures them after deploy.
  - [ ] Return tracks and master (mixer, devices, selection): code + fake tests done; real-Live proof pending
  - [ ] Groups (fold state, children) and routing in and out: already read by `query_session_understanding`; now surfaced in the world model; real-Live proof pending
  - [ ] Racks and chains; all device parameters with display strings: code done; real-Live proof pending
  - [ ] Session clips (name, length, loop, warp) and arrangement clips: names/lengths/starts via understanding; loop/warp still to add
  - [x] Scenes, locators, song key, scale and time signature (in the world model, from existing reads)
  - [ ] Automation envelopes (read): per-parameter `automation_state` added; Live's API does not expose arrangement envelope points, so full envelope read is limited to clip envelopes (to do)
- [ ] **B2 Change-driven state** (versioning + invalidation done 2026-09-23; listener pushes deferred, see note)
  - [ ] AbletonOSC listeners replace polling. **Deferred:** pushes arrive on the same reply port and address as reads, so the shared socket could take a push for a pending read's reply. Needs a dedicated push port in the Remote Script first. Interim: 2 s cache plus invalidation on every KENN receipt.
  - [x] One session model with a monotonic version and fingerprint (`core/live_world_state.py`; version moves only when the fingerprint changes; invalidated on every receipt; cache keyed to the client object)
  - [x] Proposals bound to state; stale proposals refused: already enforced via `session_version` (`test_stale_state_is_rejected_before_write`, sends, undo, track creation); world answers now cite `world_model_version`
- [ ] **B3 Full-model Q&A** ("what's on the vocal bus?", "which tracks send to the reverb?", "what's the drum compressor threshold?")
  > Code done 2026-09-23 (`core/live_world_questions.py`): contents of named tracks, returns and master (with rack chains), who sends to a return, named parameter values with Live's display string, mute/solo, and Live's scale setting (labelled as a setting, not a detected key). Track-number inventory stays on the existing route. 13 unit tests + 1 Playwright spec. Real-Live proof of return/master/parameter answers waits on the A3 deploy.

## Phase C — Language brain

- [ ] **C1 Constrained decoding:** the planner's JSON is valid by construction (Ollama structured outputs; xgrammar or llguidance fallback)
  > Code done 2026-09-23: `llm_plan_json_schema()` (flat, shape-only: schema const, 28 allowed actions, field types, no unknown keys) sent as Ollama `response_format: json_schema`; schema calls skip the MLX path, which silently ignored `json_mode`. Per-action `anyOf` branches were tried and made qwen2.5:1.5b pick wrong actions and overrun its token cap, so meaning stays with `validate_llm_plan`. Awaiting bake-off numbers to tick.
- [ ] **C2 Model bake-off** on this Mac: `qwen2.5:1.5b`, `qwen2.5:7b-instruct`, Qwen3.5-2B/4B, Phi-4-mini (accuracy, clarification, p95 latency, memory)
- [ ] **C3 Natural holdout** `tooling/data/natural_holdout.jsonl`
  - [ ] ≥ 100 phrasings · [ ] ≥ 250 · [ ] ≥ 500 (slang, fragments, corrections, multi-intent). Curated holdout: 24 (Codex). 100 drafted candidates in `tooling/data/natural_holdout_candidates.jsonl` await owner review before promotion.
- [ ] **C4 Staged promotion** (owner sign-off per stage)
  - [ ] shadow → propose-with-confirm
  - [ ] propose-with-confirm → active with deterministic fallback
- [ ] **C5 Planner over the world model** (bounded relevant slice only)
- [ ] **C6 LoRA refresh** with mlx-lm, evaluated on the holdout

## Phase D — Control breadth

- [ ] **D1 Device qualification factory**
  - [ ] Batch sweep → mapping fit → draft `DeviceUnitProfile` + evidence transcript
  - [ ] Owner sign-off queue
  - [ ] 20 profiles · [ ] 40 profiles · [ ] 60 profiles
  - [ ] 15 devices · [ ] 25 devices
- [ ] **D2 Borrowed Live-side handlers** (ableton-mcp, MIT, telemetry excluded; ableton-js as reference); attribution recorded
- [ ] **D3 New action families** (each with readback and exact undo)
  - [ ] Sends and returns · [ ] Group and ungroup · [ ] Routing
  - [ ] Tempo and signature · [ ] Scenes · [ ] Locators
  - [ ] Clips: create, launch, loop, warp, gain, transpose
  - [ ] MIDI note edit · [ ] Automation write
  - [ ] Track create with a scoped undo design
- [ ] **D4 Save automation** (opt-in Accessibility Cmd-S, hash-checked; Project-folder save-as handled)
- [ ] **D5 Recipes**, single token, per-step readback, rollback
  - [ ] 5 · [ ] 10 · [ ] 15

## Phase E — Listening and analysis

- [ ] **E1 Live capture path:** design chosen and proven (resample track, Max for Live device, or loopback; licence-checked)
- [x] **E2 Measurements:** LUFS-I/S/M and LRA (pyloudnorm); true peak; key and tempo (librosa) — 2026-09-23
  > `core/loudness_analysis.py`: BS.1770 loudness, EBU 3342 LRA (approximate), 4x-oversampled true peak via scipy (pyebur128 not installed), key via chroma + Krumhansl-Kessler with the relative key always reported, librosa tempo. Mix advice now ends with a loudness line and flags true peak above −1 dBTP; results cached by content hash with the core analysis (preflight warms it). Demo mix: −11.7 LUFS-I, −0.06 dBTP, LRA 6.5 LU, 119.7 BPM, key F major / relative D minor (composed in D minor). Key/tempo are not yet surfaced in chat. Licences recorded in `docs/research/THIRD_PARTY_LICENCES.md`.
- [ ] **E3 Per-track capture and masking collision map** with confidence
- [ ] **E4 Stem separation evaluation** (Demucs; weight licence verified first)
- [ ] **E5 Advice → action:** every finding has a "Fix it" plan, plus a before-and-after re-measure

## Phase F — Creation

- [ ] **F1 MIDI generation** (drums, bass, chords, arps, melody) in key and tempo; preview → approve → insert with undo
- [ ] **F2 Audio-to-MIDI** (basic-pitch)
- [ ] **F3 Generative audio evaluation** (Magenta RealTime, ACE-Step; licences recorded)

## Phase G — Knowledge, memory and conversation

- [ ] **G1 Owned knowledge base:** KENN-written device and workflow notes; MiniLM ONNX fetched; hybrid retrieval
- [ ] **G2 Project memory** (viewable and deletable in the UI)
- [ ] **G3 Opt-in producer preferences** (cited, never silently applied)
- [ ] **G4 Conversation policy:** clarify rather than guess, corrections, studio tone

## Phase H — Surfaces

- [ ] **H1 Real voice:** push-to-talk → local speech recognition → `/kenn/api/ask`; confirmations unchanged
- [ ] **H2 MCP server** exposing KENN's safe tools only
- [ ] **H3 UI upgrades:** session map, receipt timeline, "Fix it" buttons, recipe step previews

## Phase I — Reliability and evaluation

> Note (2026-09-23): one backend suite run showed 8 intermittent failures while the real-Live gate was running at the same time; two re-runs passed 1,448/1,448. Investigate under I3/I4.

- [ ] **I1 Nightly real-Live regression** (top 50 commands + all recipes via the UI route; SLO report)
- [ ] **I2 End-to-end benchmark** on the natural holdout, with a per-commit diff
- [ ] **I3 Chaos suite:** Live killed mid-write, UDP drops, companion restart, stale or replayed tokens
- [ ] **I4 Per-route rate limits**

## Scorecard

| Capability | Bar | Current (2026-09-23) | Evidence |
|---|---|---|---|
| Understands open phrasing | ≥ 95% on ≥ 500 natural phrasings via `/kenn/api/ask` | Not measured; deterministic parser only | — |
| Knows the session | Full-model Q&A, zero invented facts | 7 question kinds + change history + advice | `test_live_session_questions.py` |
| Controls Live | ≥ 60 params / ≥ 25 devices, full action families | 11 profiles / 8 devices; mixer, focus, EQ, sends | `core/device_units.py` |
| Multi-step workflows | ≥ 15 qualified recipes | Atomic EQ + bounded two-step recipe | `KENN_INVESTOR_DEMO_LIVE_QUALIFICATION_2026-09-23.md` |
| Listens | Live capture + LUFS, true peak, key, tempo, masking | Pre-rendered captures only | `live_session_advice.py` |
| Advises → acts | Every finding → confirmable fix + re-measure | Advice only | — |
| Creates | MIDI ideas → preview → insert; audio-to-MIDI | None | — |
| Explains | Cited, owned knowledge, grounded in the user's devices | BM25 over existing notes | — |
| Remembers | Project memory + opt-in preferences | Session-scoped receipts only | — |
| Converses | Anaphora, corrections, statement handling | 10-exchange anaphora; statements mis-handled | `session_context.py` |
| Voice | Real push-to-talk → same command path | Simulated only (do not demo) | `speech/voice_copilot.py` |
| Reliable | Nightly real-Live; p95 ≤ 500 ms; verified ≥ 99%; undo 100% | Preflight 11/11; script gate 10/10; no nightly | Rehearsal log |

## Log

| Date | Item | Commit | Evidence |
|---|---|---|---|
| 2026-09-23 | Tracker created from the build prompt | — | — |
| 2026-09-23 | A1 UI-path harness: fake Live backend, chat-route gate, Playwright E2E | `683bb39` | `KENN_A1_UI_PATH_HARNESS_2026-09-23.md` |
| 2026-09-23 | A2 defects: selection fix (code), pan centre, statement classifier, voice fake removed | `241abff` | tests + real-Live chat probes; 7/7 Playwright |
| 2026-09-23 | A3 deploy tool, version endpoint, stale-script preflight check | `0d6da61` | 11 new tests; plan shows only view.py + application.py differ (both hot-reloadable) |
| 2026-09-23 | B1 world model (code): returns/master/racks/automation-state reads, world-model route | `e5d4b21` | 4 new tests; fake-backed route smoke |
| 2026-09-23 | B3 world-model questions (code) | `df88e4f` | 13 unit tests; Playwright 8/8 |
| 2026-09-23 | B2 versioned world state + receipt invalidation | `030593f` | 4 new tests; backend 1,479 |
| 2026-09-23 | C1 schema-constrained planner decoding; bake-off harness; 100 candidate phrasings | `1e99d99` | 4 new tests; bake-off running |
| 2026-09-23 | E2 loudness, true peak, LRA, key/tempo estimates; licence register | (this commit) | 6 new tests; chat gate on fake 1/1 incl. steps 12–13 |
