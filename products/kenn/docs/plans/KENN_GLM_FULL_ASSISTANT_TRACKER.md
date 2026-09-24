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

- [x] Pick the C6 base model: `qwen3.5:4b` (clarifies 20/30, Mac p50 6.7 s) or `qwen3:4b` (clarifies 2/30, Mac p50 4.5 s; needs clarify training). See the C2 GPU evidence addendum
  > Owner chose **qwen3.5:4b** on 2026-09-23 (safer: already clarifies; the latency gap should narrow once fine-tuning shortens the prompt). Fallback if its hybrid architecture has no LoRA tooling: qwen3:4b with a clarify-heavy corpus.
- [ ] Review drafts and write independent test commands on the review page: https://claude.ai/artifact/BcWAc8j1SoPTBLGCDkxbPS (decisions and new commands are saved there; Claude reads them back)
- [ ] Review the drafted training seeds in `tooling/scripts/drafted_command_seeds.py` (C6: 21 clarify, 19 clear-command, 21 transport/rename/send/device/EQ/two-part)
- [ ] Decide C4: promote a fine-tune (candidate: run 4, 83.1% on the Mac, p50 6.5 s) from shadow to propose-with-confirm, or wait for the independent evaluation
  > 2026-09-24: owner asked to promote run 4. The promotion gate (`live_llm_promotion.py`: ≥ 500 shadow comparisons over ≥ 14 days, ≥ 98% schema acceptance, ≥ 90% agreement with the rule parser) is not met and was not bypassed. Run 4 now runs in **background shadow** on the Mac companion (`KENN_LIVE_LLM_MODE=shadow`, `KENN_LLM_ENABLED_COMMAND=1`, model `kenn-c6-run4`, compact prompt, thinking off), so every real command adds gate evidence with no added latency. Changing the gate itself would be the owner's call.
- [ ] Review the 100 drafted phrasings in `tooling/data/natural_holdout_candidates.jsonl` (labels: explicit target+amount → action, vague → clarify); approved ones move into the curated holdout
- [x] OK a `~/kenn_*` work folder on the GPU box (GPU 0, `/mnt/data`) for C6 LoRA training — text-only corpus, no audio
  > Given 2026-09-23 ("Anything we need to do that requires a GPU", no server restarts). Using `/mnt/data/kenn-bakeoff/`: user-level Ollama 0.34.2 on GPU 0, loopback port 11437, no system install.

- [ ] Demo rehearsals 2–10: owner-run, see `docs/evidence/KENN_INVESTOR_DEMO_REHEARSAL_LOG.md`

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
- [x] **A2 Known defects** (2026-09-23)
  - [x] AbletonOSC `view.py`: selecting a return or master track no longer raises; KENN reports it. Proven on real Live 2026-09-23 (382 ms, `KENN_WORLD_MODEL_REAL_LIVE_2026-09-23.md`)
  - [x] "Pan the Synth center." proposes pan 0 (5 phrasings; centre frequency excluded; verified on real Live, 2026-09-23)
  - [x] Statement-versus-request stage before retrieval: narration about KENN and typed card labels get short replies; problem statements and topics still reach chat (verified on real Live, 2026-09-23)
  - [x] Simulated voice removed: the unreachable `process_audio_features` fake is deleted and the module is documented as text-only (2026-09-23)
- [x] **A3 Remote Script deploy tool** (first real deploy + hot reload 2026-09-23, no Live restart)
  - [x] `tooling/scripts/deploy_abletonosc.py`: plan by default; `--apply` backs up, copies, stamps; `--reload` hot-reloads via `/live/api/reload` and flags files that still need a restart (2026-09-23)
  - [x] `/live/kenn/version` endpoint (reloadable `application.py`), `/api/ableton/remote-script` route, and a `remote_script` preflight check that fails on a stale or unstamped script (2026-09-23). **First real deploy + reload waits for Live to be free.**
- [ ] **A4 Demo gate 10/10** (owner-run; fix whatever it surfaces)

## Phase B — Live world model

- [ ] **B1 Read coverage** (code done 2026-09-23; real-Live proof needs the A3 deploy)
  > `core/live_world_model.py` + `/api/ableton/world-model`: one evidence-only model with per-section availability and a fingerprint that ignores meters. New hot-reloadable reads in AbletonOSC `song.py`: `/live/kenn/get/bus_mixer`, `/live/kenn/get/device_tree` (rack chains, depth 3), `/live/kenn/get/device_parameters` (display strings + automation state). The fixture recorder captures them after deploy.
  - [x] Return tracks and master (mixer, devices, selection): proven on real Live 2026-09-23
  - [x] Groups (fold state, children) and routing in and out: available on real Live 2026-09-23
  - [x] Racks and chains; all device parameters with display strings: device trees + parameter reads proven on real Live 2026-09-23 (no rack in the demo set; chains covered by fake tests)
  - [ ] Session clips (name, length, loop, warp) and arrangement clips: names/lengths/starts via understanding; loop/warp still to add
  - [x] Scenes, locators, song key, scale and time signature (in the world model, from existing reads)
  - [ ] Automation envelopes (read): per-parameter `automation_state` added; Live's API does not expose arrangement envelope points, so full envelope read is limited to clip envelopes (to do)
- [ ] **B2 Change-driven state** (versioning + invalidation done 2026-09-23; listener pushes deferred, see note)
  - [ ] AbletonOSC listeners replace polling. **Deferred:** pushes arrive on the same reply port and address as reads, so the shared socket could take a push for a pending read's reply. Needs a dedicated push port in the Remote Script first. Interim: 2 s cache plus invalidation on every KENN receipt.
  - [x] One session model with a monotonic version and fingerprint (`core/live_world_state.py`; version moves only when the fingerprint changes; invalidated on every receipt; cache keyed to the client object)
  - [x] Proposals bound to state; stale proposals refused: already enforced via `session_version` (`test_stale_state_is_rejected_before_write`, sends, undo, track creation); world answers now cite `world_model_version`
- [x] **B3 Full-model Q&A** ("what's on the vocal bus?", "which tracks send to the reverb?", "what's the drum compressor threshold?")
  > Proven on real Live 2026-09-23 (7 questions, see evidence). Code: `core/live_world_questions.py`: contents of named tracks, returns and master (with rack chains), who sends to a return, named parameter values with Live's display string, mute/solo, and Live's scale setting (labelled as a setting, not a detected key). Track-number inventory stays on the existing route. 13 unit tests + 1 Playwright spec. Real-Live proof of return/master/parameter answers waits on the A3 deploy.

## Phase C — Language brain

- [x] **C1 Constrained decoding:** the planner's JSON is valid by construction (Ollama structured outputs; xgrammar or llguidance fallback)
  > Done 2026-09-23 — every bake-off reply was schema-valid JSON (`KENN_C2_PLANNER_BAKEOFF_MAC_2026-09-23.md`). Code: `llm_plan_json_schema()` (flat, shape-only: schema const, 28 allowed actions, field types, no unknown keys) sent as Ollama `response_format: json_schema`; schema calls skip the MLX path, which silently ignored `json_mode`. Per-action `anyOf` branches were tried and made qwen2.5:1.5b pick wrong actions and overrun its token cap, so meaning stays with `validate_llm_plan`. Awaiting bake-off numbers to tick.
- [x] **C2 Model bake-off** on this Mac: `qwen2.5:1.5b`, `qwen2.5:7b-instruct`, Qwen3.5-2B/4B, Phi-4-mini (accuracy, clarification, p95 latency, memory)
  > Done 2026-09-23 (`KENN_C2_PLANNER_BAKEOFF_GPU_2026-09-23.md`). 124 cases, accuracy on GPU 0, latency on the Mac. **Winner: `qwen3.5:4b` with thinking off**: 67.7% correct, clarify 20/30, fewest wrong plans accepted; GPU p50 1.1 s; Mac (M3 16 GB, Live running) 64.5% correct, p50 10.3 s, p95 32.7 s, so not interactive on this Mac. Rule-based parser: 49.2%, clarify 30/30, instant. DeepSeek-R1 1.5B/7B: ≤4% in every thinking mode (tuned for maths reasoning; R1-7B targets the selected track). Thinking models through Ollama's /v1 route think until the token cap once a schema is set (0%); turning thinking off took qwen3.5 from 0 to 60–68%, and a 128-token budget added nothing but latency. Moving the request after the snapshot raised every model (qwen2.5:1.5b 10.5→27.4%, qwen3.5:4b 60.5→67.7%) and cut the Mac p50 from 18.6 to 10.3 s. Fixed on the way: bake-off read a persistent answer cache; cache key ignored the output contract.
  - [x] Production KENN turns thinking off for qwen3.5 (native `/api/chat` `think: false`, or the empty think-block prefill) before any promotion
    > Done 2026-09-23: schema-constrained Ollama calls to qwen3-family models go to native `/api/chat` with `think: false` (`KENN_LLM_THINK=off|on` overrides). Proven on the Mac through the real planner, no proxy: qwen3.5:4b 8/8 accepted (was 0% on the /v1 route). Warm, the native route and the prefill are the same speed (5.9 s). DeepSeek-R1 excluded: it keeps thinking even natively.
  - [x] Mac latency: qwen3.5 is a hybrid model and reuses only part of the prompt cache across commands (~3.6 s re-evaluated per command vs ~0.09 s for qwen2.5). Test standard-transformer Qwen3 (1.7B/4B) as the C6 base
    > Done 2026-09-23 (evidence addendum). Mac, same 40 cases: qwen3:4b p50 4.5 s vs qwen3.5:4b 6.7 s. Full GPU set: qwen3:4b 51.6% (clarify 2/30, 35 wrong plans accepted) vs qwen3.5:4b 66.1% (clarify 20/30, 15). qwen3:1.7b 19.4%. Owner picks the C6 base: qwen3.5:4b (safe, slower) or qwen3:4b (faster, must learn to clarify).
  - [x] Compact plan output
    > Done 2026-09-23: schema constant no longer decoded (KENN stamps it), ~12 of ~43 tokens saved; qwen3.5:4b 66.1% vs 67.7% before (within noise). Training generator shares `planner_user_prompt()` with production; corpus regenerated.
  - [ ] Grow the rule-based parser for relative dB, focus, sends, slang (volume 1/12 today)
    > Relative dB and track nicknames done 2026-09-24, from the owner's first independent test ("tuck the high hats back a couple of dbs", expected −2 dB on Hi-Hats): "up/down/back/off N dB" with one clear direction, "a couple of dB" = 2 dB, "dbs", nicknames (hats/high hats → Hi-Hats, vox → Lead Vocal, drums → Drum Bus) with a guard so "the Lead Vocal" never matches "Backing Vocal", and "some reverb" asks instead of inserting. Plain "X and Y" track controls now ask instead of proposing only X. 124 cases: **62.1%** (was 49.2%), clarify 30/30, 0 wrong plans (was 3: the earlier "0" claim was not measured). Focus, sends and slang still to do.
  - [ ] Volume mapping (code done, awaiting the Live measurement): KENN converts dB with normalized = 10^(dB/20) (1.0 = 0 dB), but Live's fader puts 0 dB at 0.85 and reaches +6 dB. Absolute and relative dB levels are therefore approximate, and "vox up 1.5 dB" at 0 dB is refused. Measure Live's fader law (as the Compressor threshold table was) and use it
    > Code done 2026-09-24: every dB → fader conversion now goes through `core/volume_law.py`: rule parser (absolute and relative), planner validator (`_volume_db_to_normalized`) and the gain-staging proposal (which used a third formula, 0.85·10^(dB/35)). Relative changes add dB to the track's current level in dB. KENN still sets at most 0 dB (raw 0.85). A new read-only AbletonOSC endpoint `/live/kenn/get/display_table` returns Live's own `str_for_value` strings, paged at ≤200 points because macOS drops UDP replies over 9,216 bytes. `tooling/scripts/measure_live_volume_law.py` reads 2,001 fader points and writes `core/live_volume_law.json`. Until that file exists KENN uses the measured Compressor Threshold table (same −inf..+6 dB range, 0.85 = 0 dB) flagged **provisional**; −6 dB is now 0.70, not 0.50. Tests: 12 new, 1,579 passed. **To finish:** open Live, `deploy_abletonosc.py --apply --reload`, run the measurement, commit the table.
    > Found while testing: the C6 corpus labelled absolute volumes as fader values under the old maths ("Bring the FX Return up to 0 dB" → 1.0, which is +6 dB in Live). Run 4 reproduces it ("set Drum Bus level to 0 dB" → 1.0) while writing dB for other levels. The corpus seeds and the unused legacy generator now label volume in dB. The next fine-tune needs this; run 4 must not be promoted for volume before then (shadow only, nothing was written).
  - [ ] Planner emits user units (dB, %) and KENN converts; stop asking the model to normalize
    > Volume in dB done 2026-09-24: `validate_llm_plan` accepts `set_volume` with `unit: "dB"`, absolute or relative, and converts with the rule parser's mapping (now Live's fader law, `core/volume_law.py`; outside −57.2..0 dB on the provisional table, or no current volume, is rejected). Found via C6 run 2, which wrote "+3 dB" plans that the old contract rejected. Pan in % still to do.
- [ ] **C3 Natural holdout** `tooling/data/natural_holdout.jsonl`
  - [ ] ≥ 100 phrasings · [ ] ≥ 250 · [ ] ≥ 500 (slang, fragments, corrections, multi-intent). Curated holdout: 24 (Codex). 100 drafted candidates in `tooling/data/natural_holdout_candidates.jsonl` await owner review before promotion.
- [ ] **C4 Staged promotion** (owner sign-off per stage)
  - [ ] shadow → propose-with-confirm
  - [ ] propose-with-confirm → active with deterministic fallback
- [ ] **C5 Planner over the world model** (bounded relevant slice only)
- [ ] **C6 LoRA refresh** with mlx-lm, evaluated on the holdout
  > Base per C2: qwen3.5:4b (owner's choice). **Run 1 done 2026-09-23** (`KENN_C6_LORA_PILOT_2026-09-23.md`). mlx-lm could not train it on the 16 GB M3, so training moved to GPU 0 on the box (17 min). Fine-tune + compact prompt: 68.5% correct vs 65.3% stock + full prompt; **clarify 30/30** (was 19/30); **wrong plans accepted 5** (was 15); but over-cautious on some clear commands (act 55/94 vs 62/94). Not ticked: run 2 and the Mac latency check are next.
  - [x] Corpus: leak guard covers all evaluation holdouts; compact targets; drafted clarify seeds (owner review pending); compact prompt
  - [x] Training pipeline: GPU box (standalone trainer, SHA-verified weights), full-checkpoint merge, GGUF, Ollama import
  - [x] Run 2: clarify share ~35%, more explicit-command and two-part variety; re-score on the 124 cases
    > Run 2 (36% clarify): 54.8%, over-asked; found the dB-volume contract gap (fixed). Run 3 (19 drafted clear-command seeds, mixer state in snapshots): **72.6%**, clarify 29/30, curated 16/24, best so far, but 13 wrong plans accepted (play/stop learned as mute). See the C6 evidence addenda.
  - [x] Run 4: drafted seeds for transport, rename, sends, device parameters, EQ, two-part requests; per-action balancing; gate on wrong plans accepted
    > **84.7%** correct (stock 65.3%), clarify 29/30, curated 19/24, wrong plans accepted 5 (gate met). EQ 0/3, device parameters 2/5, two-part 1/3 remain. Optimistic: the drafted seeds were written after seeing the evaluation's categories.
  - [ ] Fresh evaluation set written by someone other than the author of the training data (owner), for a clean score
  - [x] Run 5: EQ band/frequency and device-parameter coverage; two-part requests
    > Production-shaped evidence (single track, real Live indices). 82.3% correct; EQ 3/3 (was 0/3), same-action two-part 3/3, **2 wrong plans accepted** (safest yet); but device parameters 1/5 and inserts over-asked, curated 15/24. Run 4 stays best overall (84.7%, Mac 83.1%, p50 6.5 s).
  - [x] Latency: the gateway attaches a track's full parameter list to *every* request on that track ("mute the bass" becomes a ~5,000-token prompt because Bass has an EQ Eight). Attach evidence only for device requests, then rebuild the corpus to match.
    > Done 2026-09-24 (gateway rule + corpus). Run 6 trained to match: GPU 82.3%, Mac 79.0% (p50 6.7 s). Runs 4–6 all within 82–85%: diminishing returns; next progress needs the independent evaluation, owner-reviewed data and the C4 decision. Candidate for C4: run 4.
  - [x] Mac latency of the Q4_K_M fine-tune with the compact prompt
    > Run 1 on the M3 (Live idle): 90% on the first 40 cases vs 75% stock; median 3.6 s per command for both, since this hybrid model re-processes ~2 s of prompt per command whatever its length.

## Phase D — Control breadth

- [ ] **D1 Device qualification factory**
  > Coverage map 2026-09-24 (`KENN_DEVICE_COVERAGE_2026-09-24.md`, page https://claude.ai/artifact/XqhrDvQ8kDmzJwhpuNq2d9, `tooling/scripts/device_coverage.py`): Live 12.4.6 Suite has 78 devices. KENN knows 53 (own note) + 16 (mentioned), sees all 78, inserts 10 audio effects, sets 12 measured parameters on 9 devices. Qualify device by device (capture parameters from Live, measure units, generate per-parameter commands, run `e2e_demo_commands.py`); first wave: EQ Eight, Compressor, Utility, Limiter, Reverb/Hybrid Reverb, Delay/Echo.
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
  > Chat path done 2026-09-23 for **chords, drums, basslines** (`core/midi_generation_chat.py` on the existing generators + `MidiClipActionService`): stated key or Live's scale setting (never guessed), first MIDI track or the named one, first empty Session slot, deterministic seed so the preview is what is inserted, standard Apply/readback/Undo. Also fixed: "Create a MIDI track." (trailing full stop) was rejected by the parser. Open: arps and melody, audio preview, real-Live proof (the demo set has no MIDI track yet).
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

> Note (2026-09-23): `core/live_world_model.py` is the raw evidence layer (exactly what Live reports); the older `core/session_world_model.py` is a semantic layer (inferred roles, band ownership, deltas) that can consume it. They are complementary, not duplicates.
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
| 2026-09-23 | E2 loudness, true peak, LRA, key/tempo estimates; licence register | `a1cb848` | 6 new tests; chat gate on fake 1/1 incl. steps 12–13 |
| 2026-09-23 | F1 MIDI ideas from chat (chords/drums/bass) as confirmable clips; MIDI-track phrasing fix | `f646979` | 9 unit tests; Playwright 9/9 |
| 2026-09-23 | First real AbletonOSC deploy (hot reload); A2/B1/B3 proven on real Live; card names selected return | `2065b7f` | `KENN_WORLD_MODEL_REAL_LIVE_2026-09-23.md` |
| 2026-09-23 | C1 ticked; C2 Mac bake-off results and parser baseline | `62580f9` | `KENN_C2_PLANNER_BAKEOFF_MAC_2026-09-23.md` |
| 2026-09-23 | C2 ticked: GPU bake-off, thinking modes, prompt order fix | `e7b41af` | `KENN_C2_PLANNER_BAKEOFF_GPU_2026-09-23.md` |
| 2026-09-23 | C6 run 1: qwen3.5:4b LoRA on GPU 0; clarify 30/30, 5 wrong plans accepted | (this commit) | `KENN_C6_LORA_PILOT_2026-09-23.md` |
