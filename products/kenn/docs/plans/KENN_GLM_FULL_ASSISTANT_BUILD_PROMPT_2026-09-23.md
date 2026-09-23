# KENN — Full GLM Ableton Audio Assistant: Build Prompt

**Written:** 2026-09-23, from the state at commit `5d7089c` (monorepo `main`).
**Use:** paste the whole "Prompt" section into a fresh coding-agent session started in
`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/products/kenn`. It is designed to run
across many sessions: every session starts by reading the tracker, continues the
first unticked item, and ticks items off as they land.

---

## Prompt

You are the lead engineer turning **KENN** into a fully functioning, language-model-driven
("GLM") AI audio assistant for **Ableton Live 12**. A producer should be able to talk to
KENN in plain language and have it understand the session, answer questions about it,
listen to and critique the audio, make exact, safe changes, build multi-step workflows,
generate musical ideas, explain Live, and remember how this producer works. Every change
must stay inside KENN's proven safety envelope.

This is a long programme, not one task. Work one sub-item at a time, prove each one
against real Live through the real UI path, commit it, and tick it off in the tracker.

### 0. Read first (every session)

1. `/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/monorepo/CLAUDE.md`: repo rules. **Never add
   an AI attribution trailer to commits in this repo.**
2. `docs/plans/KENN_GLM_FULL_ASSISTANT_TRACKER.md`: the live checklist for this
   programme. **Create it on your first session** from section 6 below if it does not exist.
3. `docs/plans/KENN_GLM_ABLETON_ASSISTANT_PLAN_2026-09-22.md`: the investor-demo plan
   and its progress tracker (demo polish items still open live there).
4. `docs/runbooks/KENN_INVESTOR_DEMO.md` and
   `docs/evidence/KENN_INVESTOR_DEMO_REHEARSAL_LOG.md`: the qualified demo path. **Do not
   regress it.** Every change must keep the 20-step demo passing.
5. `git log --oneline -30` to see what landed since this prompt was written.

Then run the baseline and record the numbers at the top of the tracker:

```bash
PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests
cd apps/frontend && PATH="/opt/homebrew/bin:$PATH" npx vitest run && PATH="/opt/homebrew/bin:$PATH" npm run build
```

(The Intel `node`/`npm` in `/usr/local/bin` cannot run on this Mac and there is no
Rosetta. Always put `/opt/homebrew/bin` first.)

### 1. Non-negotiables

1. **Safety envelope.** Every Live mutation goes proposal → confirmation token → execute
   → independent readback → durable receipt → exact, identity-bound undo. No path may
   bypass it: not the language model, MCP, voice, recipes, or "autonomous" modes.
   Destructive operations (delete, overwrite, replace, bounce-over, master-level
   extremes) stay refused unless a phase below explicitly designs a classified, confirmed
   and reversible path for them.
2. **Evidence over claims.** A capability counts only when it works against real Live
   through the **same route the UI uses** (`/kenn/api/ask` → proposal card → Apply →
   `/kenn/api/ableton/command`). On 2026-09-23 a 10/10 automated gate passed while the
   UI's Apply button was broken for every numeric proposal. The gate called the command
   endpoint directly, and the browser's `JSON.stringify` drops a float's trailing `.0`.
   Test the real path.
3. **No simulations presented as real.** `kenn/speech/voice_copilot.py` currently fakes
   voice input: a hard-coded sentence and an invented "+120 ms" latency. Anything like
   this must be removed or clearly labelled, and must never be demoed. Stubs belong in
   tests only.
4. **Licences.** KENN is a closed commercial product. Do not add GPL, AGPL, BSL, PolyForm
   or non-commercial code or weights. Known **avoid** list: Essentia, aubio, libkeyfinder,
   pedalboard, atomacos, madmom *models*, MusicGen/audiocraft weights, xLAM/Hammer
   models, Qwen2.5-**3B**, Producer Pal, LivePilot, talkback-mcp, phantom, OBSIDIAN-Neural,
   suno-to-ableton, and dawtool's GPL file. BlackHole (virtual audio) is GPL-3.0: never
   bundle it. Verify every new dependency's licence and record it in
   `docs/research/THIRD_PARTY_LICENCES.md`.
5. **Owner audio stays out of git.** Corpora, stems and captures live under `.runtime/`
   or outside the repo.
6. **Commits.** One sub-item per commit, message explains *why*, no AI trailer. Tick the
   tracker in the same commit. Do not push; the owner pushes, because `main` mirrors to a
   public repo and Vercel.
7. **Stop and ask** when a decision is the owner's: licensing, anything that needs Live's
   GUI, a model promotion stage, a destructive-operation design, or any spend.

### 2. Verified current state (2026-09-23)

**Architecture:**

```
Vue 3 UI (apps/frontend, served by the companion at http://127.0.0.1:8090/)
  → /kenn/api/ask (server.py)
      → live inspection (live_session_questions.py: count, selection, overview, tempo,
        duplicates, change history scoped to session, mix advice)
      → imperative Live phrasing → live_command.handle_command()
          → session_context.py (10-exchange anaphora: "undo that", "again")
          → live_intent.parse_request() (~1.5k-line deterministic parser)
          → [LLM planner, shadow mode only: validate_llm_plan, contract gate]
          → typed proposal + HMAC token (confirmation.py; numbers canonicalised)
      → otherwise orchestrator → knowledge chat (BM25 retrieval; embeddings missing)
  → Apply → /kenn/api/ableton/command → live_action_service.apply()
      → live_executor → AbletonOSC (UDP 11000/11001) → readback → receipt journal
        (kenn/data/ableton_receipts.jsonl) → undo via /kenn/api/ableton/osc/undo
```

- **Start the full companion,** not `run_ux_backend.py` (which skips the Mixing Doctor
  status loop):
  `KENN_ALLOW_DAW_CONTROL=1 KENN_LIVE_AUDIO_CAPTURE_PATH=… KENN_LIVE_VOCAL_CAPTURE_PATH=…
  PYTHONPATH=apps/backend/src:tooling python3 apps/backend/src/kenn/server.py`
- **Remote Script:** the vendored fork is `integrations/ableton-osc/`. Live loads the copy in
  `/Volumes/Jack_Gandy_1TB_SSD/User Library/Remote Scripts/AbletonOSC/` and only reloads
  it when Live restarts. The repo copy is the source of truth; deploy by copying and
  back up the old copy under `.runtime/`.
- **Works end to end through the UI (live-verified):**
  - session Q&A;
  - volume, pan, mute, solo;
  - track and device focus;
  - exact device-parameter sets on qualified profiles, e.g. Compressor Output and EQ
    Eight band gain;
  - atomic EQ insert-and-tune;
  - bounded two-step recipes;
  - chat "Undo that.";
  - receipt Undo;
  - session-scoped change history;
  - refusals for delete and master extremes;
  - low-end and vocal-clipping advice from hash-bound rendered captures;
  - Arrangement audio import through the Places allowlist
    (`/live/track/import_arrangement_audio`).
- **Device coverage:** 11 evidence-backed unit profiles across 8 devices
  (`core/device_units.py`). Qualification tooling: `tooling/scripts/qualify_ableton_live_*.py`.
- **Language layer:** the deterministic parser is authoritative. The LLM planner
  (`live_command.py`: `LLM_COMMAND_SYSTEM_PROMPT`, `_llm_planner_snapshot`,
  `validate_llm_plan`) runs in **shadow** only, with durable promotion thresholds and
  state, and a LoRA pipeline for Qwen2.5-1.5B (`tooling/scripts/*kenn_command*`). Local
  models available in Ollama: `qwen2.5:1.5b` and `qwen2.5:7b-instruct` (both Apache-2.0).
  `mlx`, `mlx-lm`, `librosa` and `pyloudnorm` are installed.
- **Tests:** 1,414 backend (5 skipped), 21 frontend, and a production build, all green.
- **Demo:** 1 of 10 required consecutive 20-step rehearsals passed.

**Known gaps and defects (carry these into the tracker):**

- Plain statements typed into chat get confident but unrelated knowledge answers:
  retrieval rates them "high". Needs a statement-versus-request stage.
- The chat parser cannot return a pan to centre ("Pan the Synth center.").
- AbletonOSC `view.py` `get_selected_track` raises when a return or master track is
  selected, causing a 1.2 s timeout in KENN.
- Voice input is simulated (see non-negotiable 3). The frontend has no microphone code.
- Live has no save API. The operator must press Cmd-S, and Live saves a loose `.als`
  into a new Project folder.
- Live's Browser hides Places inside hidden folders (`.runtime`), so imports need a
  visible, hash-verified Place.
- Kick and Synth are **MIDI** tracks in the reset fixture; audio cannot be placed on them.
- Track creation has no undo; delete is refused outright.
- The semantic retrieval index is missing (the MiniLM ONNX model is not fetched), so
  retrieval is BM25-only.
- Audio analysis only sees pre-rendered captures. There is no live capture path from
  Live yet.
- Rate limits are crude (60 per 60 s), and there is no nightly real-Live regression.

### 3. Definition of "fully functioning"

KENN is done with this programme when all of these hold, each with an evidence receipt
under `docs/evidence/`:

| Capability | Bar |
|---|---|
| Understands open phrasing | ≥ 95% correct typed intent (or correct clarification) on a **natural-language holdout of ≥ 500 producer phrasings** that is not paraphrased from training seeds, scored end to end through `/kenn/api/ask` |
| Knows the session | Answers about tracks, returns, master, groups, devices, parameter values, clips, scenes, arrangement, routing, tempo, key and selection, grounded in a fresh snapshot with zero invented facts |
| Controls Live | ≥ 60 evidence-backed parameter profiles across ≥ 25 native devices. Tracks, returns, sends, groups, clips, scenes, locators, tempo, MIDI notes and automation writes, all with readback and exact undo |
| Multi-step workflows | ≥ 15 qualified recipes (e.g. "set up a vocal chain", "parallel-compress the drums", "sidechain the bass to the kick"), each one token for the whole plan, per-step readback, compensating rollback |
| Listens | Captures real session audio (master or per-track) without manual renders; reports LUFS-I, true peak, LRA, spectral balance, masking, mono compatibility, key and tempo, all with evidence and confidence |
| Advises → acts | Every finding can become a confirmable proposal ("fix it" → exact plan → Apply → verified) |
| Creates | Generates MIDI ideas (drums, bass, chords, melody) in key and tempo; preview → approve → insert with undo. Audio-to-MIDI. |
| Explains | Answers Ableton "how do I" questions with cited, owned knowledge, grounded in the user's actual devices and values |
| Remembers | Per-project memory and opt-in producer preferences, citable and deletable |
| Converses | Multi-turn anaphora and corrections; stays silent or asks when a message is not a request |
| Voice | Real push-to-talk speech → the same command path (local speech recognition), with the same confirmations |
| Reliable | Nightly real-Live regression and CI fake-Live replay. SLOs: p95 command → proposal ≤ 500 ms, verified-execution ≥ 99%, undo 100%, zero unconfirmed mutations |

### 4. Workstreams

Do them in order. Within a phase, sub-items may be reordered if the tracker says why.

#### Phase A — Harden the foundation (do first, keeps the demo safe)

- **A1 UI-path test harness.** Playwright (Apache-2.0) end-to-end tests that type into the
  real chat, click Apply, Undo and Dismiss, and assert card states. Add a **fake-Live
  record/replay layer** at the OSC boundary (the pattern from Loophole's FakeLiveBridge,
  MIT: copy the idea, not the code) so CI runs without Live. Every future capability
  lands with a UI-path test.
- **A2 Fix the known defects** listed in section 2: `view.py` return/master selection;
  pan-to-centre phrasing; a statement-versus-request classifier before retrieval (reply
  briefly and do not lecture when the message is not a request); remove or label the
  simulated voice module.
- **A3 Remote Script deployment tool.** `tooling/scripts/deploy_abletonosc.py`: diff the
  repo against the installed copy, back up, copy, write a version stamp, and add a
  `/live/kenn/version` endpoint so preflight fails when Live runs a stale script.
- **A4 Finish the demo gate** (ten consecutive rehearsals). This is owner-run; support it
  and fix whatever it surfaces.

#### Phase B — A complete Live world model

- **B1 Read coverage.** Return tracks, master, groups (fold state and children), routing
  in and out, device chains including racks and chains, **all** device parameters with
  display strings, clip slots and clips (names, lengths, warp, loop), arrangement clips,
  scenes, locators, automation envelopes (read), song key and scale, time signature,
  and selection including return and master.
- **B2 Change-driven state.** Subscribe to AbletonOSC listeners instead of polling. Keep one
  in-memory session model with a monotonic version and fingerprint, used by proposals,
  the UI card and advice. Proposals stay bound to the version they were made against.
- **B3 Session Q&A over the full model.** Examples: "what's on the vocal bus?", "which
  tracks send to the reverb?", "what's the threshold on the drum compressor?", "where
  does the drop start?". Every answer is grounded and cites the snapshot version.

#### Phase C — The language brain

- **C1 Constrained decoding.** Force the planner's JSON with a schema: Ollama structured
  outputs first, then xgrammar (Apache-2.0) or llguidance (MIT) if needed. Schema
  validity must reach 100% by construction.
- **C2 Model bake-off,** on the natural holdout, latency-aware, on this Mac:
  `qwen2.5:1.5b` (current), `qwen2.5:7b-instruct`, Qwen3.5-2B/4B (Apache-2.0) and
  Phi-4-mini (MIT). Report accuracy, clarification quality, p95 latency and memory.
  Keep a hosted-model option behind the same contract gate, but the local model is the
  default.
- **C3 Natural-language corpus.** Build `tooling/data/natural_holdout.jsonl` (≥ 500) from
  shadow-mode logs, rehearsal transcripts and owner-written phrasings. Include slang,
  fragments, corrections and multi-intent sentences. Never train on the holdout.
- **C4 Staged promotion.** Use the existing gate stages: shadow → propose-with-confirm →
  active-with-deterministic-fallback. Each stage needs the thresholds already recorded
  in the gate plus **owner sign-off**. The deterministic parser stays authoritative for
  refusals and safety classification at every stage.
- **C5 Planner over the full world model.** The LLM sees a bounded, relevant slice of the
  B2 model (the tracks and devices named or implied), never the whole session.
- **C6 LoRA refresh.** Retrain on corpus data with mlx-lm (MIT), and evaluate with
  `evaluate_kenn_command_lora.py` against the holdout.

#### Phase D — Control breadth

- **D1 Device qualification factory.** Turn `qualify_ableton_live_device.py` into a batch
  pipeline. It sweeps each parameter on a disposable set, fits a linear, log, table or
  discrete mapping, drafts a `DeviceUnitProfile` with its evidence transcript, and
  queues it for owner sign-off. Target ≥ 25 native devices and ≥ 60 parameters,
  prioritised by producer demand: Utility, EQ Eight (frequency and Q for all bands),
  Compressor (attack, release, ratio, knee, makeup), Glue, Limiter, Saturator, Auto
  Filter, Reverb, Hybrid Reverb, Delay, Echo, Chorus-Ensemble, Phaser-Flanger, Drum
  Buss, Roar, Gate, Multiband Dynamics, Channel EQ, Pedal, Amp, Redux, Erosion, Corpus,
  and Spectral Resonator.
- **D2 Borrow proven Live-side handlers.** Take them from `ahujasid/ableton-mcp` (MIT;
  exclude its default-on telemetry) and use `leolabs/ableton-js` (MIT) as an API
  reference, for browser device loading, rack chains, routing and arrangement. Record
  attribution in the licence file.
- **D3 New action families,** each with readback and exact undo:
  - sends and returns;
  - group and ungroup;
  - routing;
  - tempo and signature;
  - clips: create, launch, loop, warp, gain, transpose;
  - MIDI note edit;
  - scenes;
  - locators;
  - automation **write** (envelope points with an exact inverse);
  - track create (design an undo: a confirmed delete limited to tracks KENN created in
    this session that are still empty).
- **D4 Save.** An opt-in macOS Accessibility automation for Cmd-S with a before-and-after
  file hash check. The owner grants the permission. Handle Live's Project-folder
  save-as behaviour.
- **D5 Recipes.** ≥ 15 qualified multi-step recipes as single-token plans with per-step
  readback and compensating rollback (the atomic-EQ pattern generalised).

#### Phase E — Listening and analysis

- **E1 Live capture path.** Design and prove how KENN gets audio from Live without manual
  renders. Options to evaluate:
  - a KENN-created resampling track recorded for N bars, then read the recorded clip file;
  - per-track solo plus master capture;
  - a Max for Live capture device;
  - a system loopback device (licence-check it; do not bundle GPL drivers).

  Every capture is hash-bound and deleted after analysis unless the user keeps it.
- **E2 Measurement upgrades.** pyloudnorm (MIT) for LUFS-I, S and M plus LRA;
  pyebur128/libebur128 (MIT) for true peak; librosa (ISC) for key, tempo, chroma and
  onset. Keep the stdlib FFT and native kernels as the fast path.
- **E3 Per-track and masking analysis.** Solo-capture key tracks, build a frequency-band
  collision map, and rank masking candidates with confidence. Never claim masking the
  measurement cannot prove.
- **E4 Stem separation** for reference tracks: evaluate Demucs (MIT code; verify the
  weight licence before use).
- **E5 Advice → action.** Each finding carries a suggested fix plan that becomes a normal
  confirmable proposal or recipe, plus an A/B "before and after" re-measure after Apply.

#### Phase F — Creation

- **F1 MIDI generation** in key, scale, tempo and section length: drums, bass, chords,
  arps, melody. Start rule- and probability-based (mido and pretty_midi, MIT). Preview by
  rendering through the track's instrument or a preview clip, then approve → insert as a
  clip with undo.
- **F2 Audio-to-MIDI** with basic-pitch (Apache-2.0): "turn this vocal hum into MIDI".
- **F3 Generative audio (evaluate only).** Magenta RealTime (code Apache-2.0, weights
  CC-BY-4.0 with attribution) and ACE-Step 1.5 (verify the code licence). Stable Audio
  Open is free only under $1M revenue; record it as a future cost. Everything goes
  through preview → approve → insert.

#### Phase G — Knowledge, memory and conversation

- **G1 Owned knowledge base.** Write KENN's own device and workflow notes. Do **not**
  ingest Ableton's copyrighted manual wholesale. Fetch the MiniLM ONNX model
  (`python scripts/fetch_embedding_model.py`) so retrieval is hybrid, not BM25-only.
  Answers cite their notes and, when relevant, the user's actual device values.
- **G2 Project memory.** Per-set memory (what was changed and why, open issues) keyed by
  the set's identity, viewable and deletable in the UI.
- **G3 Preferences** (opt-in): "I like my vocals bright", "I always parallel-compress
  drums". Stored locally, cited when used, never silently applied.
- **G4 Conversation policy.** Covers the statement classifier, clarify-don't-guess,
  corrections ("no, the other vocal"), and concise studio tone.

#### Phase H — Surfaces

- **H1 Real voice.** Push-to-talk in the UI → local speech recognition (Whisper-class on
  MLX; verify the model licence) → the same `/kenn/api/ask` path. Confirmation stays a
  click or an explicit spoken confirm of the exact proposal. Optionally add spoken
  replies through the existing TTS route once it is tested.
- **H2 MCP server.** Expose KENN's safe tools (read, propose, confirm and undo, never raw
  OSC) through `core/mcp_facade.py` so other agents drive Live only through KENN's
  envelope.
- **H3 UI.**
  - A session map panel: tracks, devices and sends, live from the B2 model.
  - Receipt timeline.
  - Advice → "Fix it" buttons.
  - Proposal cards for recipes, with a per-step preview.

#### Phase I — Reliability and evaluation

- **I1 Nightly real-Live regression.** Open a fixture set, run the top 50 commands and all
  recipes through the UI route, verify readback and undo, reset, and publish an SLO
  report.
- **I2 End-to-end benchmark.** The natural holdout scored through `/kenn/api/ask`, with
  per-category accuracy, clarification rate, latency and a regression diff per commit.
- **I3 Chaos.** Kill Live mid-write, drop UDP, restart the companion, send a stale token or
  replay a token. Expect a correct refusal or recovery every time.
- **I4 Rate limiting.** Replace the crude 60/60 s with per-route budgets that keep the UI
  responsive.

### 5. Working method for every sub-item

1. Write a 3–6 line plan in the tracker under the item: approach, files, how you will
   prove it.
2. Implement it with tests at unit level **and** through the real UI path (A1 harness).
3. For anything that touches Live: prove it on a **disposable** set (never the tracked
   reset fixture), confirm Live's document path from Live's log before any confirmed
   write, and record evidence under `docs/evidence/` (what ran, readback values, undo
   result, timings).
4. Run the full backend and frontend suites and the build. Re-run the 13-prompt demo
   script gate and one manual demo pass if the change touches the chat, Apply or Undo
   path.
5. Commit (no AI trailer), tick the tracker in the same commit, and report in 3–5 lines:
   what changed, the evidence, and what's next.
6. If blocked on the owner (GUI action, licence call, promotion sign-off, spend), write
   the exact ask in the tracker's "Waiting on owner" section and move to the next
   unblocked item.

### 6. Tracker skeleton (create `docs/plans/KENN_GLM_FULL_ASSISTANT_TRACKER.md`)

```markdown
# KENN GLM Full Assistant — Tracker
Baseline: <commit> · backend <n> passed · frontend <n> passed · build ok · demo <n>/10

## Waiting on owner
- (none)

## Phase A — Foundation
- [ ] A1 UI-path harness (Playwright + fake-Live replay)
- [ ] A2 Known defects (view.py selection, pan centre, statement classifier, voice stub)
- [ ] A3 Remote Script deploy tool + version endpoint
- [ ] A4 Demo gate 10/10 (owner-run)
## Phase B — World model
- [ ] B1 Read coverage · [ ] B2 Change-driven state · [ ] B3 Full-model Q&A
## Phase C — Language brain
- [ ] C1 Constrained decoding · [ ] C2 Model bake-off · [ ] C3 Natural holdout ≥500
- [ ] C4 Staged promotion (owner sign-off per stage) · [ ] C5 Planner over world model · [ ] C6 LoRA refresh
## Phase D — Control breadth
- [ ] D1 Qualification factory (≥25 devices / ≥60 params) · [ ] D2 Borrowed handlers
- [ ] D3 New action families · [ ] D4 Save automation · [ ] D5 ≥15 recipes
## Phase E — Listening
- [ ] E1 Live capture path · [ ] E2 LUFS/true-peak/key/tempo · [ ] E3 Masking map
- [ ] E4 Stem separation (eval) · [ ] E5 Advice → action + re-measure
## Phase F — Creation
- [ ] F1 MIDI generation · [ ] F2 Audio-to-MIDI · [ ] F3 Generative audio (eval)
## Phase G — Knowledge & memory
- [ ] G1 Owned KB + embeddings · [ ] G2 Project memory · [ ] G3 Preferences · [ ] G4 Conversation policy
## Phase H — Surfaces
- [ ] H1 Real voice · [ ] H2 MCP server · [ ] H3 UI upgrades
## Phase I — Reliability
- [ ] I1 Nightly real-Live · [ ] I2 End-to-end benchmark · [ ] I3 Chaos · [ ] I4 Rate limits
## Scorecard (section 3 of the prompt)
| Capability | Bar | Current | Evidence |
```

### 7. Start now

Read section 0, run the baseline, create the tracker, then begin **A1**. Report the
baseline numbers and your A1 plan before writing A1 code.

---

## Owner notes (not part of the prompt)

- Expect this to take many sessions. The tracker is the hand-off between them, so any
  agent (Claude, Codex) can resume from the first unticked item.
- Phases C4 (model promotion), D1 (profile sign-off), D4 (Accessibility permission) and
  E1 (capture design) need you in the loop by design.
- Keep rehearsing the demo in parallel. Phase A protects it; later phases must never
  merge while they break the 20-step script.
