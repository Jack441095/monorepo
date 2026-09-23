# KENN GLM Audit & Completion Plan — 2026-09-23

**Date:** 2026-09-23 · **Commit:** `62580f9` (12 commits ahead of `origin/main`)  
**Baseline tests:** backend 1,503 passed / 5 skipped · frontend 21 passed · production build ok  
**Demo gate:** 1/10 rehearsals · **Devices:** 11 profiles across 8 devices · **LLM stage:** `shadow` · **Retrieval:** BM25-only

---

## 1. What KENN IS (as of 2026-09-23)

### Architecture at a Glance

```
┌──────────────┐   POST /kenn/api/ask    ┌─────────────────┐
│   Frontend   │ ───────────────────────► │   server.py     │ ──► Knowledge chat
│   (Vue 3)    │   POST /kenn/api/command │  (http.server)   │ ──► Live commands
└──────────────┘                          └─────────────────┘
                                                │
                        ┌───────────────────────┴────────────────────────┐
                        ▼                                                                    ▼
               core/live_command.py                          core/chat.py (knowledge)
               handle_command()                             answer_payload()
               ┌────────────────────────────────┐          ┌──────────────────┐
               │ 1. Answer session questions     │          │ BM25 retrieval   │
               │ (read-only, grounded)           │          │ over Training    │
               │ 2. Preprocess context           │          │ Data Notes       │
               │ 3. Deterministic parse           │          │ + LLM rewrite    │
               │ 4. LLM shadow (if enabled)      │          │ (Ollama/OpenAI)  │
               │ 5. Create proposal              │          └──────────────────┘
               │ 6. Apply on confirm             │
               └────────────────────────────────┘
                        │
                        ▼
        core/live_action_service.py  (single safety boundary)
        ┌─────────────────────────────────────────────────────┐
        │ proposal → confirmation token → execute             │
        │ → fresh-read verification → durable receipt         │
        │ → exact, identity-bound undo                        │
        └─────────────────────────────────────────────────────┘
                        │
                        ▼
            AbletonOSC (UDP) → Ableton Live 12
```

### Key Environment Variables

```bash
# DAW control — MUST be set for any mutation
KENN_ALLOW_DAW_CONTROL=1

# LLM for command planning (shadow mode by default)
KENN_LIVE_LLM_ENABLED=1          # Enable LLM planner (disabled by default)
KENN_LIVE_LLM_MODE=shadow         # shadow | propose | active (shadow only)

# Chat LLM
AUDIO_TOO_LLM_ENABLED=1
AUDIO_TOO_LLM_PROVIDER=ollama    # or "openai"
AUDIO_TOO_LLM_MODEL=gpt-4o-mini
```

### Proven Safety Envelope

Every Live mutation follows this exact path:

1. **Proposal** — `LiveActionService.propose_*` creates a proposal with a unique confirmation token
2. **Confirmation** — User clicks "Apply" in UI or calls `/api/ableton/command` with the token
3. **Execute** — `consume_confirmation(token)` validates the token hasn't been used
4. **Readback verification** — Fresh snapshot compared against expected values
5. **Durable receipt** — `record_receipt()` writes to journal (SQLite + JSON)
6. **Exact undo** — `propose_undo(receipt)` creates an inverse proposal with identity matching

### What's Already Working End-to-End

#### Session Q&A (B3)
7 question kinds through the real chat path: connection status, track count, track identity, tempo/time signature, selected track, duplicate names, session overview.

#### Receipt-backed change history
"What did you change?" answered from the journal with proposal IDs and exact undo capability.

#### LLM shadow mode (C1, C4)
The planner's JSON is constrained by `llm_plan_json_schema()` (28 allowed actions, field types, no unknown keys). The LLM plan is compared to the deterministic parser's intent via `compare_llm_plan()`. Shadow results are logged to JSONL. Promotion thresholds are wired (shadow → propose → active) but stage remains `shadow`. Each model gets one bounded structural-repair attempt if the first reply is schema-invalid.

#### Mix advice (E2, partially E5)
LUFS-I, LRA, true peak (4×-oversampled via scipy), key and tempo (librosa). Flags vocal clipping and low-end issues from hash-bound pre-rendered captures. Results cached by content hash.

#### MIDI generation (F1)
"Write a 4-bar D minor chord progression on the Pads track" → chord progression / drum pattern / bassline → proposal with deterministic seed → readback → undo. Key resolved from message or Live's scale setting (never guessed).

#### Device control (11 profiles / 8 devices)
EQ Eight (frequency-log + gain), Auto Filter (Resonance, Frequency-log), Compressor (Threshold with 20-point measured table), Saturator (Drive), Drum Buss (Drive), Hybrid Reverb (Dry/Wet), Echo (Dry/Wet), Utility (Gain), mixer (volume, pan, mute, solo, arm), sends/returns, EQ band gain, device insertion, clip duplication/rename/stop, locators, group tracks, gain staging, focus track/device, transport play/stop.

#### Demo fixture, preflight, test harness, latency, multi-turn context, Remote Script deployment, statement classifier — all done (see Section 5 for file references).

### 12 Commits of Progress Since the Build Prompt

| Commit | Work Completed |
|---|---|
| `683bb39` | A1: UI-path test harness — fake Live backend, chat-route gate, Playwright E2E |
| `241abff` | A2: Defects — return/master selection fix, pan center, statement classifier, fake voice removed |
| `0d6da61` | A3: Deploy tool, version endpoint, stale-script preflight check |
| `e5d4b21` | B1: World model (code) — returns/master/racks/device parameters |
| `df88e4f` | B3: Session questions from full world model |
| `030593f` | B2: Versioned world state, invalidated by every KENN write |
| `1e99d99` | C1: Constrained planner decoding, bake-off harness, 100 candidate phrasings |
| `a1cb848` | E2: Loudness, true peak, LRA, key/tempo estimates; licence register |
| `f646979` | F1: MIDI ideas from chat as confirmable clips; MIDI-track phrasing fix |
| `2065b7f` | Real AbletonOSC deploy (hot reload); A2/B1/B3 proven on real Live |
| `62580f9` | C1/C2: Record Mac planner bake-off and parser baseline (current HEAD) |

---

## 2. What KENN CANNOT Yet Do (Gap Analysis)

### Phase A — Foundation
- **[A4]** Ten consecutive complete 20-step investor demo rehearsals — **1 of 10 done** (owner-run)
- **[Defect]** `JSON.stringify` drops float trailing `.0` in frontend Apply button (known fix: explicit decimal handling)

### Phase B — World Model (Code done; real-Live proof mostly complete)
- **[B1]** Session clips (loop/warp states still to add); automation envelopes (limited to clip envelopes, no full envelope points)
- **[B2]** Live listener pushes (deferred — needs dedicated push port in Remote Script; interim: 2s cache + invalidation on every KENN receipt)

### Phase C — Language Brain (Largest gap for GLM transformation)
- **[C1]** ✅ Schema-constrained decoding — done, but bake-off results pending finalization
- **[C2]** Model bake-off — in progress (qwen2.5:1.5b 12%, qwen2.5:7b 56% on 100 phrasings on Mac; GPU run needed)
- **[C3]** Natural-language holdout of ≥500 phrasings — 100 candidates drafted, **waiting on owner review**
- **[C4]** Staged promotion — infrastructure done, but stage remains `shadow` (needs owner sign-off)
- **[C5]** Planner over the world model — **not started** (LLM sees full snapshot, not bounded relevant slice)
- **[C6]** LoRA refresh — **not started** (needs GPU box access, owner-gated)

### Phase D — Control Breadth (Critical gap)

| Action Family | Status | Notes |
|---|---|---|
| Mixer (volume, pan, mute, solo, arm) | ✅ Done | Live-verified |
| EQ (band gain, tuning gain) | ✅ Done | EQ Eight only |
| Sends/returns | ✅ Done | set_send wired and tested |
| Track creation | ⚠️ Partial | create_midi/audio/return_track — **no undo** |
| Track rename | ✅ Done | Live-verified |
| Device insert | ✅ Done | EQ Eight, Compressor, Auto Filter, Saturator, Hybrid Reverb, Echo |
| Device parameter | ✅ Done | 11 profiles / 8 devices |
| Device remove | ✅ Done | remove_device wired |
| Focus track/device | ✅ Done | focus_track, focus_device |
| Transport (play/stop) | ✅ Done | Live-verified |
| Group/ungroup | ⚠️ Partial | gain_stage_tracks, group_tracks implemented |
| Tempo/signature | ❌ Not done | Parsed but not executable |
| Scenes | ❌ Not done | Scene names read for parsing only; launch_scene declared but not wired |
| Clips: create/launch/loop/warp/gain/transpose | ❌ Not done | stop_clip and duplicate_clip/rename_clip done |
| MIDI note edit | ❌ Not done | Not implemented |
| Automation write | ❌ Not done | Read only (automation_state); no envelope point writes |
| Track delete | ❌ Refused | Destructive — correctly refused |
| Clip delete | ❌ Refused | Destructive — correctly refused |
| Locators | ✅ Done | add_locator, remove_locator wired and tested |

**Device profiles: 11 / 25 target** (need Utility, Glue Compressor, Limiter, Roar, Chorus-Ensemble, Phaser-Flanger, Gate, Multiband Dynamics, Channel EQ, Pedal, Amp, Redux, Erosion, Corpus, Spectral Resonator)
**Recipes: 1-2 / 15 target**

### Phase E — Listening
- **[E1]** Live capture path — **not started** (needs owner design decision)
- **[E2]** ✅ Measurements — done (LUFS, true peak, LRA, key, tempo)
- **[E3]** Per-track masking collision map — **not started**
- **[E4]** Stem separation evaluation — **not started**
- **[E5]** Advice → "Fix it" → re-measure — **not started** (advice is read-only)

### Phase F — Creation
- **[F1]** ✅ MIDI generation (chords, drums, bass) — done in chat path, real-Live proof pending
- **[F2]** Audio-to-MIDI (basic-pitch) — **not started**
- **[F3]** Generative audio (Magenta RealTime, ACE-Step) — **not started**

### Phase G — Knowledge & Memory
- **[G1]** Owned KB + embeddings — **not started** (BM25-only; MiniLM ONNX not fetched)
- **[G2]** Project memory — **not started**
- **[G3]** Preferences — **not started**
- **[G4]** ✅ Conversation policy — partially done (statement classifier, 10-exchange context, anaphora)

### Phase H — Surfaces
- **[H1]** Real voice — **not started** (no microphone code in frontend)
- **[H2]** MCP server — **not started**
- **[H3]** UI upgrades — partially done (session map, receipt timeline, "Fix it" buttons not done)

### Phase I — Reliability
- **[I1]** Nightly real-Live regression — **not started**
- **[I2]** End-to-end benchmark on holdout — **not started**
- **[I3]** Chaos suite — **not started**
- **[I4]** Per-route rate limits — **not started** (crude 60/60s)

### Owner-Gated Items
1. **[C3]** Review 100 drafted natural phrasings in `tooling/data/natural_holdout_candidates.jsonl`
2. **[C4]** Sign off on LLM promotion from `shadow` → `propose` stage
3. **[C6]** OK `~/kenn_*` work folder on GPU box for LoRA training
4. **[E1]** Choose live capture design (resample track / Max for Live / loopback)
5. **[D4]** Grant Accessibility permission for Cmd-S automation
6. **[A4]** Run demo rehearsals 2–10

---

## 3. Completion Plan — "Fully Functioning GLM AI Assistant"

The definition of "fully functioning" is in the build prompt's Section 3 (lines 155–173). Here's the ordered plan:

### Phase A — Foundation Hardening (3-5 days)
1. **[A4]** Complete 10 consecutive 20-step demo rehearsals (owner-run)
2. Fix the `JSON.stringify` float issue in frontend Apply button
3. Add explicit decimal formatting for floating-point values in `KennActionProposal`

### Phase B → C — World Model + Language Brain (8-12 days, partially owner-gated)
4. **[B1]** Add session clip loop/warp reads to the world model
5. **[C3]** Owner reviews 100 natural phrasings → curate 500+ holdout `tooling/data/natural_holdout.jsonl`
6. **[C5]** Wire the LLM planner to see a bounded, relevant slice of the B2 world model
7. **[C2]** Complete the model bake-off on GPU (qwen2.5:7b, Qwen3.5-2B/4B, Phi-4-mini)
8. **[C4]** Owner signs off on promotion to `propose` stage → LLM can now propose (with human confirmation)
9. **[C6]** (Owner-gated) LoRA refresh on GPU box with mlx-lm, evaluated on holdout
10. **I2** End-to-end benchmark on the natural holdout, per-commit diff

### Phase D — Control Breadth (10-15 days)
11. **[D1]** Run `qualify_ableton_live_device.py` batch sweep → target 25+ devices, 60+ params
12. **[D2]** Integrate borrowed handlers from `ableton-mcp` (MIT) and `ableton-js` (MIT)
13. **[D3]** Implement new action families: tempo/signature, scene launch, clip create/launch/loop/warp/gain/transpose, MIDI note edit, automation write, track creation with scoped undo
14. **[D4]** (Owner-gated) Implement Cmd-S Accessibility automation with hash check
15. **[D5]** Build 15 qualified recipes (vocal chain, parallel compress drums, sidechain bass to kick, etc.)

### Phase E — Listening & Analysis (5-8 days)
16. **[E1]** (Owner-gated) Implement chosen live capture path
17. **[E3]** Implement per-track capturing and masking collision map with confidence
18. **[E4]** Evaluate Demucs for stem separation (verify weight licence)
19. **[E5]** Wire advice → "Fix it" → confirmable proposal → re-measure loop

### Phase F — Creation (3-5 days)
20. **[F1]** Complete arps and melody MIDI generation; prove on real Live
21. **[F2]** Implement audio-to-MIDI with basic-pitch (verify licence)
22. **[F3]** Evaluate Magenta RealTime and ACE-Step for generative audio

### Phase G — Knowledge & Memory (3-5 days)
23. **[G1]** Write KENN-owned device/workflow notes; fetch MiniLM ONNX for hybrid retrieval
24. **[G2]** Implement project memory (per-set, viewable/deletable in UI)
25. **[G3]** Implement opt-in preferences store
26. **[G4]** Strengthen conversation policy (corrections, studio tone)

### Phase H — Surfaces (3-5 days)
27. **[H1]** Implement real push-to-talk in frontend → Whisper-class MLX speech recognition → `/kenn/api/ask`
28. **[H2]** Implement MCP server (`core/mcp_facade.py`) exposing only KENN-safe tools
29. **[H3]** UI upgrades: session map, receipt timeline, "Fix it" buttons, recipe step previews

### Phase I — Reliability (3-5 days)
30. **[I1]** Nightly real-Live regression script + SLO report
31. **[I3]** Chaos suite (Live killed mid-write, UDP drops, companion restart, stale/replayed tokens)
32. **[I4]** Per-route rate limits replacing crude 60/60s
33. **[I2]** End-to-end benchmark on natural holdout (if not done in Phase B)

### Final — Demo & Promotion
34. Complete 10 consecutive full 20-step demo rehearsals with projector layout and timing
35. Final 11-check preflight on the stem-loaded disposable set
36. Owner promotes LLM from `propose` → `active` (owner sign-off)

---

## 4. Critical Path Summary (Owner-Gated Milestones)

| Owner Decision | Blocks What | When Needed |
|---|---|---|
| **[C3]** Review 100 natural phrasings | C3 holdout curation, C4 promotion data | Before C4 promotion |
| **[C4]** Sign off on `propose` stage | LLM can propose (with confirm) for real | After C3 holdout + C2 bake-off |
| **[C6]** OK GPU box `~/kenn_*` folder | LoRA training | After C6 corpus is ready |
| **[E1]** Choose capture design | Live audio capture (E1, E3, E5) | Before E1 implementation |
| **[D4]** Grant Accessibility permission | Cmd-S automation | Before D4 |
| **[A4]** Run demo rehearsals 2–10 | Final demo qualification | After all demo-path features |

---

## 5. Test Baseline & Verification Strategy

**Current baseline:**
```bash
cd products/kenn
PYTHONPATH="apps/backend/src:tooling" python3 -m pytest -q apps/backend/src/kenn/tests
# Result: 1,503 passed, 5 skipped in 71.34s

cd apps/frontend
PATH="/opt/homebrew/bin:$PATH" npx vitest run
# Result: 21 passed
```

**Every change must pass:**
1. Backend test suite (1,503+ tests)
2. Frontend test suite (21 tests)
3. Frontend production build
4. 13-prompt demo script gate (`tooling/scripts/demo_script_gate.py --runs 10`)
5. One manual demo pass if the change touches the chat, Apply or Undo path

**Verification method for Live changes:**
- Prove on a **disposable** Live set (never the tracked reset fixture)
- Confirm Live's document path from Live's log before any confirmed write
- Record evidence under `docs/evidence/` (what ran, readback values, undo result, timings)
- No AI attribution trailers in commits

---

## 6. Key Files & Directories Reference

| Concern | Path |
|---|---|
| Command gateway | `apps/backend/src/kenn/core/live_command.py` |
| Deterministic parser | `apps/backend/src/kenn/core/live_intent.py` |
| Safety boundary / proposals | `apps/backend/src/kenn/core/live_action_service.py` |
| Tier-2/Tier-3 actions | `apps/backend/src/kenn/core/actions/tier2_tier3_actions.py` |
| World model | `apps/backend/src/kenn/core/live_world_model.py` |
| Session Q&A | `apps/backend/src/kenn/core/live_session_questions.py` |
| Receipt journal | `apps/backend/src/kenn/core/live_receipt_journal.py` |
| LLM shadow/promotion | `core/live_shadow_log.py`, `core/live_llm_promotion.py` |
| LLM wrapper | `apps/backend/src/kenn/llm/llm_rewrite.py` |
| Session context | `apps/backend/src/kenn/core/session_context.py` |
| Device units | `apps/backend/src/kenn/core/device_units.py` |
| MIDI generation | `apps/backend/src/kenn/core/midi_generation_chat.py` |
| Frontend API client | `apps/frontend/src/api/kenn.ts` |
| Frontend composable | `apps/frontend/src/composables/useKenn.ts` |
| API paths | `apps/frontend/src/api/paths.ts` |
| HTTP server | `apps/backend/src/kenn/server.py` |
| Command handler route | `apps/backend/src/kenn/routes/daw_command_handler.py` |
| Chat handler route | `apps/backend/src/kenn/routes/chat_routes.py` |
| Device qualification | `tooling/scripts/qualify_ableton_live_*.py` |
| Deploy Remote Script | `tooling/scripts/deploy_abletonosc.py` |
| Demo script gate | `tooling/scripts/demo_script_gate.py` |
| Preflight | `tooling/scripts/demo_preflight.py` |
| Shadow bake-off | `tooling/scripts/analyze_shadow_logs.py` |
| Tracker | `docs/plans/KENN_GLM_FULL_ASSISTANT_TRACKER.md` |
| Build prompt | `KENN_GLM_FULL_ASSISTANT_BUILD_PROMPT_2026-09-23.md` (monorepo root) |
| Runbook | `docs/runbooks/KENN_INVESTOR_DEMO.md` |

---

## 7. Assessment: Where the Project Stands

KENN is at a **critical inflection point**. The foundation is remarkably solid — the safety envelope is proven against real Ableton Live, the deterministic parser handles the core command vocabulary, the world model is comprehensive, and the test infrastructure is robust. The 12 commits since the build prompt represent rapid, disciplined progress.

The remaining work falls into three buckets:

1. **Owner-gated decisions** (6 items) — These block C4, E1, D4, A4, and require the owner's sign-off or hardware access.
2. **Engineering breadth** (30+ items across D3, D1, D5, E3-E5, F2-F3, G1-G4, H1-H3, I1-I4) — These are well-defined, individually testable, and follow established patterns. The safety envelope already covers them.
3. **LLM promotion journey** (C3 → C4 → C6) — Collect natural-language data, get the model promoted from shadow to propose (with mandatory human confirmation), then eventually to active. This is the core "GLM" transformation.

**The path is clear but long** — approximately 40-60 days of focused engineering work plus owner decisions, assuming real Live hardware access for qualification. The biggest risks are: (a) the owner-gated items that block C4/E1/D4, (b) the 500-phrase natural holdout not yet curated, and (c) the device qualification sweep to 25+ devices.

The tracker at `docs/plans/KENN_GLM_FULL_ASSISTANT_TRACKER.md` is the authoritative hand-off between sessions and should be updated in the same commit as each completed item.