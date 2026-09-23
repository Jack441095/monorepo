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

- [ ] Demo rehearsals 2–10: owner-run, see `docs/evidence/KENN_INVESTOR_DEMO_REHEARSAL_LOG.md`
- [ ] Restart Live once A3 deploys the updated AbletonOSC, so A2's return/master selection fix can be proven

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
- [ ] **A3 Remote Script deploy tool**
  - [ ] `tooling/scripts/deploy_abletonosc.py`: diff, back up, copy, version stamp
  - [ ] `/live/kenn/version` endpoint; preflight fails on a stale script
- [ ] **A4 Demo gate 10/10** (owner-run; fix whatever it surfaces)

## Phase B — Live world model

- [ ] **B1 Read coverage**
  - [ ] Return tracks and master (mixer, devices, selection)
  - [ ] Groups (fold state, children) and routing in and out
  - [ ] Racks and chains; all device parameters with display strings
  - [ ] Session clips (name, length, loop, warp) and arrangement clips
  - [ ] Scenes, locators, song key, scale and time signature
  - [ ] Automation envelopes (read)
- [ ] **B2 Change-driven state**
  - [ ] AbletonOSC listeners replace polling
  - [ ] One session model with a monotonic version and fingerprint
  - [ ] Proposals bound to the model version; stale proposals refused
- [ ] **B3 Full-model Q&A** ("what's on the vocal bus?", "which tracks send to the reverb?", "what's the drum compressor threshold?")

## Phase C — Language brain

- [ ] **C1 Constrained decoding:** the planner's JSON is valid by construction (Ollama structured outputs; xgrammar or llguidance fallback)
- [ ] **C2 Model bake-off** on this Mac: `qwen2.5:1.5b`, `qwen2.5:7b-instruct`, Qwen3.5-2B/4B, Phi-4-mini (accuracy, clarification, p95 latency, memory)
- [ ] **C3 Natural holdout** `tooling/data/natural_holdout.jsonl`
  - [ ] ≥ 100 phrasings · [ ] ≥ 250 · [ ] ≥ 500 (slang, fragments, corrections, multi-intent)
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
- [ ] **E2 Measurements:** LUFS-I/S/M and LRA (pyloudnorm); true peak (pyebur128); key and tempo (librosa)
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
| 2026-09-23 | A2 defects: selection fix (code), pan centre, statement classifier, voice fake removed | (this commit) | tests + real-Live chat probes; 7/7 Playwright |
