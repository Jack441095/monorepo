# KENN Open-Source Capability Landscape — 15 October 2026

Research only. Nothing in this document is an approval, a commitment, or an instruction to install anything. It merges the four lane notes of the 2026-10-15 KENN landscape research pass:

- `kenn-landscape-notes-2026-10-15/01-ableton-integration.md` — Ableton Live integration surfaces.
- `kenn-landscape-notes-2026-10-15/02-local-brain-voice.md` — local models, retrieval and voice.
- `kenn-landscape-notes-2026-10-15/03-audio-understanding.md` — licence-clean audio ML.
- `kenn-landscape-notes-2026-10-15/04-teaching-patterns.md` — teaching, grading and practice patterns.

The licence rule applied throughout is `THIRD_PARTY_LICENCES.md`: KENN ships closed-source, so MIT, BSD, ISC, Apache-2.0 and Unlicense code and weights are shippable; MPL-2.0 is test-only; GPL, AGPL, LGPL, BSL, PolyForm, non-commercial terms and unclear code or weights are blocked. CC-BY-4.0 is not on the allow-list. Items under it are marked gated here and need an owner decision plus an attribution line before they could ship.

Evidence legend: **[V]** verified against a named primary source on 2026-10-15; **[I]** inferred by the lane and stated as such; **[U]** or **[?]** unverified, unreproducible or contradictory. Where a lane corrected its own earlier finding, the corrected value is used here and the change is listed in section 7. Item codes (C1–C5, L1–L5, B1–B4, E1–E11, S4/S6, D2–D6) refer to `KENN_PLAN.md`. Recommendations in section 6 are proposals for the owner, not approvals.

## Executive summary

Fifteen conclusions for the owner, each expanded in its section with sources and dates.

1. **Live stable is 12.4.6 (2026-09-15); Extensions remain beta-channel only.** Every Extensions-related build rides the 12.4.5 → 12.4.15 beta branch (today 12.4.15b7, 2026-10-15), Suite-only, and no public Live 13 pages exist (three ableton.com URLs return 404). [V]

2. **The OSC spine stays.** AbletonOSC (MIT, 827★) is the deepest free control surface KENN rides today, but it is stalled: last push 2025-11-19, zero releases, 39 open issues plus 34 open PRs, and a live callback bug (#212) sitting untriaged. KENN vendors and patches it, so continuity is KENN's to own.

3. **AbletonOSC's structural gaps are where ableton-js is strong** (MIT, 532★, npm 5.0.4 dated 2026-10-12): browser `load_item`/`preview_item`, rack and chain traversal, grouped undo steps and automation envelopes. The costs are a second Remote Script, an unencrypted loopback WebSocket, and a TypeScript runtime.

4. **The Extensions SDK is not the path to transport, real-time audio or MIDI, browser scanning, or stable identity** — all four are absent or officially disallowed today. Its `.ablx` install story is attractive, but the SDK licence text is not publicly readable (Centercode-gated). Owner/legal must read it before any closed-source commercial distribution.

5. **Ollama changed engines under KENN's feet.** Stable is v0.40.4 (2026-10-12); since v0.40.0 (2026-09-25), MLX is the default runner on Apple Silicon for supported models. Any latency conclusion measured on Ollama 0.34.4 with llama.cpp b11081 needs re-measuring on 0.40.x.

6. **Digest pinning alone no longer identifies the engine.** v0.40.2 (2026-10-08) introduced background model re-downloads (runner `ggml` → `llamacpp`, old copy kept), so one tag can map to two digests. Record the runner name alongside the digest.

7. **Small-model refresh:** Qwen3.5-4B (Apache-2.0, HF created 26–28 Feb 2026; 2.47 GiB Ollama blob; thinking off for the planner) and Gemma 4 E4B (Apache-2.0, 5.12 GiB blob) are the new challengers to the Qwen3-4B-2507 baseline. Qwen3.6 and Qwen3.8 shipped no sub-14B models.

8. **Reranker shortlist corrected.** Every Jina reranker from v2 onward is CC-BY-NC-4.0 and excluded. The clean trio: FlashRank (Apache-2.0, ~4 MB tiny ONNX — the only one that fits the C5 ≤250 MB and ≤150 ms p95 budget), bge-reranker-v2-m3 and Qwen3-Reranker-0.6B (both Apache-2.0; both about 0.57–0.6 GB int8, likely over the 250 MB line).

9. **Embeddings:** EmbeddingGemma-2 (Apache-2.0, created 2026-09-14; 740M multimodal; 768-d; 8k context; Ollama blob 0.28 GiB) is new. Qwen3-Embedding-0.6B stays the text pick; bge-m3 (MIT) is the hybrid fallback.

10. **Voice:** whisper.cpp remains the push-to-talk baseline (MIT, Metal; large-v3-turbo weights MIT). Parakeet TDT 0.6B v3 (CC-BY-4.0 weights — gated) and Moonshine (MIT code and models) are challengers. Kokoro-82M (Apache-2.0) is the TTS default; Chatterbox (MIT) needs a PerTh watermark decision first. Wake word stays out of scope: openWakeWord's pre-trained models are CC-BY-NC-SA-4.0.

11. **Audio understanding:** the only shippable SOTA source separation today is MSST (MIT) plus two ZFTurbo checkpoints with explicit first-party MIT statements plus KimberleyJSN mel-band vocals (MIT). Demucs v4 weights are "not covered by the MIT license ... provided only for scientific purposes" — blocked.

12. **Basic Pitch stays the clean AMT pick** (Apache-2.0; `nmp.onnx` exactly 230,444 bytes; no TensorFlow needed). beat_this is clean on both code and weights (MIT; 8.1 MB small model) but pulls LGPL `soxr`, which policy excludes unless it is isolated or replaced.

13. **LAION-CLAP is the only licence-clean audio-text embedder** (CC0 code and checkpoints; the HF mirror is Apache-2.0), but MAEB puts CLAP-class retrieval at only 8–14%. Frame it as a ranking aid, not semantic search.

14. **Generation:** exactly two families are Apache-2.0 on both code and weights — ACE-Step v1 and DiffRhythm — and both are background-render workloads (M2 Max: 26.43 s per minute of audio at 27 steps). Keep behind B4's explicit opt-in gate. Stable Audio Open Small is gated; MusicGen, MAGNeT, AudioLDM2 and Tango2 are CC-BY-NC.

15. **Teaching and grading:** only loudness and peak claims have open citable standards (EBU R128 family / Tech 3343, AES TD1006, TD1008). Headroom, mono-compat thresholds and gain-staging baselines are house rules and must stay labelled as such. No comparable product found ships a numeric grade out of 100 with reasoning. MixAssist (COLM 2025) is the phrasing reference, with CC-BY-4.0 raw data on two Zenodo records.

**Single most important recommendation.** Re-baseline the runtime before any other latency work: one same-prompt A/B of Ollama 0.34.4 against 0.40.4 on this M3, recording the model digest, the runner name, `eval_count`, `prompt_eval_count`, cached tokens and time-to-first-token per call (C2, effort S). Every other performance conclusion — KV quantization, speculative decoding, model swaps, the 15 s gate arithmetic — is currently unanchored because the engine changed. Until this runs, prior numbers describe a runtime combination that no longer exists on a fresh install.

## 1. Ableton integration surfaces

Merged from lane 01. All repo and release facts checked against primary sources on 2026-10-15 unless marked otherwise.

### 1.1 Live release status, October 2026

Stable Live is **12.4.6** (bugfix, 2026-09-15). The last feature release **12.4** (2026-05-05) brought Link Audio, stem-separation commands and the Learn View. Release-note dates: 12.4.1 (2026-05-28), 12.4.2 (2026-06-11), 12.4.3 (2026-07-14 — "Max for Live can now open or close plug-in editor windows via the LOM"), 12.4.5 (2026-08-26 — Max 9.1.5), 12.4.6 (2026-09-15). No "12.4.4" section appears on the public notes page; if it shipped, its notes are not public [V / I]. The beta channel is **12.4.15b7** (2026-10-15). Extensions-related work rides the 12.4.5 → 12.4.15 beta branch and is absent from stable release notes. Three Live 13 URLs return 404; there is no official Live 13 anything [V]. A prior note that "a community extension dev references Live 13 Beta" could not be reproduced and is treated as dead [U].

What this means for KENN [I]:

- Do not build generic stem-separation UX. Live 12.4 separates stems for a time selection and merges 2–3 stems natively; KENN's value sits above it (judgement, grading, context) and in the JUCE analyser.
- Link Audio is a Live-to-Live transport. On 16 GB M3, assume stems stay files on disk for analysis, not a live audio stream.
- Learn View is now Live's own in-app teaching surface. KENN's education story must be critique and measurement, not lesson replay.
- Any KENN `.ablx` is a Suite-beta-only story until Ableton ships Extensions to stable.

### 1.2 The four-way capability matrix

Status legend: **Y** available and used by real projects; **P** partial or needs qualification; **N** absent; **X** available but verified broken (field reports). "Remote Script direct" is the private Python LiveAPI that all bridges ride.

| Capability | AbletonOSC (MIT) | ableton-js / Remote Script direct (MIT) | Extensions SDK 12.4.15b7 (beta, licence U) | Max for Live (licence U) | Caveats |
|---|---|---|---|---|---|
| Play/stop/continue, transport | Y | Y | **N** | Y | Extensions FAQ: no real-time transport interaction |
| Set/read song time, jump, loop, punch | Y | Y | N (no `current_song_time`) | Y | — |
| Record into Arrangement / overdub / session record | Y (`record_mode`, `punch_in/out`, `session_record`, `trigger_session_record`) | Y | N | Y | Recording while KENN drives = high-risk automation |
| Locators (cue points) create/delete/jump | Y | Y | Y (`createCuePoint`) | Y | — |
| Tracks create/duplicate/delete/group/colour | Y (group not verified upstream) | Y | Y (no grouping call in public API doc) | Y | — |
| Scenes create/delete/duplicate | Y | Y | Y | Y | — |
| Clip CRUD session view | Y (fire/stop/duplicate_loop/notes) | Y | Y | Y | — |
| MIDI notes read/write | Y (arrays, `remove_notes_by_id`) | Y | Y (whole-array get/set) | Y | Extensions has no per-note API |
| Audio clip create from file | Y | Y | Y (import copies into project) | Y | — |
| Arrangement clip enumerate | **P** (only `length/start_time/name`) | Y (`arrangement_clips`) | Y (`arrangementClips[]`) | Y | AbletonOSC arrangement is nearly blind |
| Duplicate clip to Arrangement | N | Y (`duplicate_clip_to_arrangement`) | Y (beyond holes) | Y | — |
| Move/split/resize arrangement clips | N | P (holding-area workarounds; resize impossible for warped looped clips) | P | P | producer-pal field notes, verified Live 12.4.3 |
| Take lanes | N | Y (`create_take_lane`) | Y | Y (12.2+ API) | — |
| Devices insert/delete/duplicate/reorder | P (`delete_device`; insert not exposed as an OSC address) | Y (`insert_device`, `find_device_position`, `move_device`) | Y (`insertDevice`, `duplicateDevice`, `deleteDevice`) | Y | Device name resolution differs (class vs display name) |
| Device parameter read/write | Y (value, min/max, is_quantized, value_string, listeners) | Y | Y (`getValue`/`setValue`; no display strings in public doc) | Y | Only automatable parameters (LOM) |
| Parameter value strings/units | Y (`str_for_value` via `get parameter/value_string`) | Y (`display_value`, `str_for_value`) | P (quantized `valueItems` only) | Y | KENN readback layer should adopt this |
| Nested rack / chain traversal | **N** (0 `chain` mentions in device.py) | Y (`RackDevice`, `Chain`, `DrumChain`) | Y (`chains[]`, `Chain.devices[]`) | Y | Biggest AbletonOSC coverage gap |
| Browser search/load/preview | N | Y (`application.browser`, `load_item`, `preview_item`; undocumented publicly) | **N** (cannot scan folders) | Y | Undocumented, so version fragility is unknown |
| Groove pool read + assign | P (`has_groove` read; `groove` commented out with OSC type error) | Y (`Groove`, `GroovePool`) | N in public doc | Y | Remote Script paths only |
| Automation read/write | N in track/song/device handlers | Y (`Envelope`, `automation_state`) | N in public doc | Y | KENN marks automation partial already |
| Sends/return routing | Y | Y (`MixerDevice`) | Y (returnTracks) | Y | — |
| Meters (track level L/R) | Y (`output_meter_level/left/right` getters) | Y | N | Y | Real-time-ish polling only |
| Live audio observation | N | N (only meters) | N; `renderPreFxAudio` offline pre-FX render | Y (M4L device) | LivePilot ships an M4L Analyzer for this |
| Undo | Y atomic (`undo`/`redo`) | Y atomic + **grouped steps** (`begin_undo_step`/`end_undo_step`) | Y (`withinTransaction`, nested calls collapse) | Y | Grouped steps are undocumented in public LOM |
| Stable object identity across moves | N (index-based) | N | N (handles invalidate on move) | N | KENN fingerprints remain the answer |
| Warp markers write | N (OSC type error) | **X** (add/move report success, change nothing — Live 12.4.3) | N | Y | Never promise this |
| Third-party plug-in params | Y if automatable (`PluginDevice`) | Y | Y | Y | Resolve by name, never index-persist |
| Bundle as one-file install | N (Remote Scripts folder copy) | N (Remote Scripts folder copy) | Y (`.ablx` via Settings → Extensions) | N (`.amxd` + Max needed) | Extensions beta-only, Suite-only |
| Closed-source commercial redistribution | Y (MIT) | Y (MIT) | **U** (read SDK licence from the zip first) | U (Max terms to read) | Owner/legal gate |

Supporting detail from the lane:

- **Extensions SDK surface** (1.0.0-beta.0, community reference doc cross-checked against beta notes): `Song`/`Track`/`Clip` objects, whole-array MIDI-note get/set, `withinTransaction` grouped undo, `ui.showModalDialog` WebViews, `ui.registerContextMenuAction`, `resources.importIntoProject`, `resources.renderPreFxAudio` (pre-FX only), ephemeral bigint handles. Entry is `activate(activation)` → `initialize(activation, "1.0.0")`. NodeJS v24.16.0+; SDK under 5 MB disk; `npm start` opens Live against a local build.
- **Extensions cannot**: no real-time audio or MIDI processing, no in-chain devices, no background processing during playback, no sample-accurate timing, no transport interaction, no browser access, no MIDI-instrument or post-FX render (no freeze/flatten/bounce), no escape hatch beyond the curated property set, no move-stable identity. Ableton's FAQ steers real-time work to Max for Live.
- **Producer-pal's decision** (ADR-0007, accepted 2026-06-28) records these limits and stays on Max for Live + V8, with a stated revisit trigger: "Revisit if the SDK gains either MIDI-instrument/post-FX render (or freeze/flatten) or a move-stable identity primitive."
- **ableton-js specifics**: WebSocket on 127.0.0.1:39031, optional password auth (salt + HMAC-SHA256; socket stays `ws://`); namespaces mirror the LOM including Browser, BrowserItem, Chain, Envelope, Groove, GroovePool, TakeLane, TuningSystem; `beginUndoStep()`/`endUndoStep()` map to the Remote Script's `begin_undo_step`/`end_undo_step` (used by Live's own Push framework, not on the public LOM page).
- **AbletonOSC specifics**: handler modules are application, clip, clip_slot, device, midimap, scene, song, track, view, handler, introspection, osc_server — no browser, groove, take-lane or automation module. Device parameter value listeners and `output_meter_*` exist; #212 (2026-06-20) reports the clip_slot callback raising `RemoteScriptError` on every message. Groove and `warp_markers` are commented out upstream with the recorded error "Infered arg_value type is not supported" — that is upstream master's comment, not KENN's invention.
- **Field notes worth keeping** (producer-pal, verified against Live 12.4.3): warp-marker add/move silently no-op; warped looped arrangement clip length "cannot be changed after creation by any means"; mid-clip splitting discards the tail instead of splitting; `end_marker` is unclamped (`99999` sticks); `loop_end` reverts on warped clips and has different units per clip type.

### 1.3 Ecosystem refresh (what moved since 14 October)

Transferable patterns, not repo adoption, are the value here [I]:

1. Split the SDK-free core from the Live adapter — Loophole's `core`/`mcp`/`extension` packages (MIT, 22★, pushed 2026-10-11) exist so logic is testable without Live; they even name a `FakeLiveBridge`. KENN already does this with `FakeLiveBackend`.
2. Capability-honest verification gates — Loophole marks unverified E2E gates NOT_RUN rather than implying CI coverage; `next-live-mcp` brands itself "capability-honest". This matches KENN's "offline verified only" matrix column.
3. Context economy — LivePilot advertises 28 entry points while keeping 474 callable tools searchable on demand. On a 16 GB M3, a small advertised surface plus on-demand discovery is the sane pattern.
4. Evidence labelling — LivePilot separates measured audio, setup-derived heuristics and artistic judgement in every report. KENN's grading needs exactly this honesty taxonomy.
5. Undo-boundary discipline — LivePilot states in-set changes ride Ableton's undo stack while downloads/memory/library scans do not; producer-pal keeps a stable-id contract so a model can name objects across a session. Both map onto KENN's proposal/readback/undo plus fingerprints.
6. Set-scoped memory — LivePilot ties learned taste to the Live Set, not the chat. `Song.name`/`Song.file_path` are readable via LOM.
7. Localhost HTTP + OpenAPI between agent and extension — Protocol0's contract (`@protocol0/extension-sdk`, MIT, npm 0.1.2, 2026-06-11) exposes extension actions to an external agent on :9010 with `/openapi.json`.
8. Telemetry is optional and off by default in the serious tools — ahujasid (anonymous telemetry, disable-able) is the contrast; KENN stays local-first and explicit about never phoning home.

Repo refresh: ahujasid/ableton-mcp (3,190★, MIT, pushed 2026-09-22) is the field's most-starred Remote Script socket + MCP bridge. dreamrec/LivePilot (82★, BSL-1.1, pushed 2026-10-15) is the closest full competitor: 474 tools / 57 domains, M4L Analyzer, evidence labels, project memory. producer-pal (329★, GPL-3.0-or-later) publishes the best Live-API field notes. Extension-native MCP servers now exist (loophole MIT; jasper-zheng no licence; ulm0, idx3d, t1merickson MIT; pnomolos live-wire GPL-3.0). dormancy: freekmurze/ableton-ai, peterkolbe/ableton-for-ai, F-Fischer/ableton-copilot, josefigueredo/ableton-mcp and RiotTheMan/ableton-mentor-mcp are all small MIT repos, stale since 2026-08 or earlier; madisonrickert/ableton-tools (16★, MIT, pushed 2026-10-09) ships Claude Code skills.

### 1.4 Ranked adopt list (effort S/M/L)

1. **Adopt the evidence-labelling taxonomy in outputs (S).** LivePilot separates measured audio, setup-derived heuristics and artistic judgement per report; KENN's grade and proposal receipts should carry the same three labels. Wording and schema, not architecture.
2. **Use `display_value` / `str_for_value` / `value_items` in the readback layer (S).** LOM exposes GUI strings and enum names; the vendored AbletonOSC already has `get parameter/value_string` upstream. Typed proposals get more explainable with zero new transport.
3. **Key project memory to the Live Set identity (S).** Bind memory to live-set identity (`Song.name`, `Song.file_path`) so renamed-copy workflows do not leak state between sets.
4. **Adopt context economy for MCP tool exposure (M).** Advertise a small named core; keep the long tail discoverable on demand. Fits a 16 GB machine serving a local model.
5. **Keep producer-pal-style field notes per bridge surface (S).** A document per surface recording which writes silently no-op. Most of KENN's worst bugs will be Live-version behaviours, not KENN code.
6. **Qualify a browser path via the Remote Script surface (M).** `application.browser` + `load_item`/`preview_item` exist (ableton-js proves them); undocumented publicly, so gate behind a feature handshake and real-Live qualification. Unlocks "load the right instrument or sample" flows OSC cannot do.
7. **Watch the Extensions SDK for a companion `.ablx` (M now, L later).** Decision gate: the producer-pal revisit triggers (MIDI-instrument or post-FX render/freeze/flatten, plus move-stable identity) and stable-channel availability. Until both, it cannot be the sole path.
8. **Watch the extension-native MCP cluster (S to monitor).** If one ships a polished `.ablx` with broad coverage it becomes the UX benchmark for KENN's install story. Their "SDK never enters the source tree" packaging rule is also the right licence hygiene.
9. **Consider the Loophole test-split shape (M).** A `FakeLiveBridge`-style port formalises what `FakeLiveBackend` already does and keeps any future extension path Live-free for CI.
10. **Track LivePilot's confidence gates and three-way exploration (M).** "Quick path for simple asks, full critic pass for ambiguity" is a workflow design KENN can copy without touching Live APIs.

### 1.5 Avoid list

- **No copyleft or source-available code into the product:** producer-pal (GPL-3.0-or-later), LivePilot (BSL-1.1), live-wire (GPL-3.0), Paulstretch for Live (GPL-2.0), Noise Canvas (AGPL-3.0), jasper-zheng/ableton-sdk-mcp (no licence). Ideas are fine; code is not. (xiaolaa2/ableton-copilot-mcp is MIT but is a competing bridge, not a dependency candidate.)
- **No SDK tarball redistribution or dependency:** `extensions-sdk-*.zip`, `vendor/*.tgz`; the `@ableton-extensions/{sdk,cli,create-extension}` scoped npm names are not publicly installable. Read the licence inside the zip before any `.ablx` distribution decision.
- **Do not promise verified-broken writes:** warp-marker add/move (no-ops on Live 12.4.3), arrangement resize of warped looped clips, mid-clip "split" semantics. Do not advertise groove assignment over OSC until the object-serialisation seam is engineered.
- **Do not treat the Extensions SDK as the path to transport, real-time audio or MIDI, browser or library scanning, or stable identity** — none exist there today, officially.
- **Do not rebuild what Live 12.4 does natively:** stem separation (per-selection plus stem merge), Link Audio streaming, Learn View lessons.
- **Do not build against the public LOM docs alone** for Browser, groove or take-lane paths; they are absent there. Qualify on a real session or keep behind feature handshakes.
- **Do not assume AbletonOSC will be maintained.** Last push Nov 2025, 34 open PRs, no releases. Own any fix through the vendored copy; consider a thin superset bridge only if browser/rack gaps block roadmap items.
- **Do not telephone home by default.** ahujasid's disable-able anonymous telemetry is a contrast example, not a norm for a local-first product.

### 1.6 Owner and legal flags

- **Extensions SDK licence text is not publicly readable** (Centercode-gated; not fetched under the no-install rule). The FAQ confirms the SDK is free and third-party developers "may choose to charge for their products", but redistribution terms for closed-source commercial `.ablx` are undocumented. Read the licence from the SDK zip before any decision. [U]
- **Max for Live commercial redistribution terms were not verified** in this pass. Many paid M4L devices exist, but the Max/MSP licensing terms for embedding and redistribution need reading before any M4L dependency. [U]
- **"12.4.4"** has no public release-notes section; existence unknown. [U]
- **LivePilot's "474 tools / 57 domains"** is vendor-stated, not independently counted. [U]
- **"Ableton has said today's permission model will harden into a stricter sandbox"** is producer-pal's report; the official statement was not located. [U]

### 1.7 What stays (the OSC spine) vs what could be added

**What stays.** AbletonOSC remains KENN's primary control transport and the OSC spine of the product: MIT-clean, already vendored and patched, tested against `FakeLiveBackend`, and the only path KENN currently ships to session control, meters, clip notes, device parameters with value strings, atomic undo, and record/transport state. Nothing in this research justifies replacing it. The Extensions SDK cannot replace it (no transport, no observers, beta-only, Suite-only) and ableton-js would replace one Remote Script dependency with a second plus a TypeScript runtime.

**What could be added, in gap order:**

1. **Readback enrichment from the existing Remote Script path** — display strings, enum labels, undo-granularity knowledge. No new transport; the addresses already exist upstream.
2. **A qualified browser path** (`application.browser`, `load_item`, `preview_item`) behind a feature handshake, for instrument and sample loading.
3. **A thin superset bridge** — ableton-js-style coverage over the OSC transport, i.e. adding Browser, Chain and Envelope coverage to KENN's own vendored bridge — only if items 1–2 prove insufficient and the roadmap needs rack traversal or automation writes.
4. **An Extensions `.ablx` companion** — one-file install, typed API, grouped undo, pre-FX render — held behind the producer-pal gate (post-FX/MIDI render or stable identity) and stable-channel availability, and behind the SDK licence review.
5. **Max for Live remains the only real-time audio/MIDI observation path** (LivePilot's M4L Analyzer is the precedent), but it is a separate runtime and a licence review of its own; nothing in the current plan needs it.

## 2. Local brain and voice

Merged from lane 02. Target: KENN closed-source, local-first, Apple M3 with 16 GB, alongside Ableton Live. Baseline recorded in the plan: Qwen3 4B chat plus Qwen3 4B planner via Ollama, text-only. All facts verified against primary sources on 2026-10-15 unless marked.

### 2.1 Chat and planner models

**Qwen line.** Qwen3.6 (created 2026-04-15/21) shipped only a 35B-A3B and a 27B; Qwen3.8 (created 2026-08-05/24) shipped a 27B, a 2.4T-A95B and the Flash-Next variant. **No sub-14B model in either generation.** The small-model ceiling in the Qwen line is still the Qwen3.5 0.8B/2B/4B/9B refresh, HF-created **26–28 Feb 2026**, every model Apache-2.0. Qwen3.5-4B: hybrid 24 linear + 8 attention layers, 262,144-token native context, vision encoder, **thinking on by default** (disable with `chat_template_kwargs {"enable_thinking": false}`); published scores MMLU-Pro **79.1**, IFEval **89.8**, BFCL-V4 **50.3**, TAU2-Bench **79.9**. Qwen3.5-9B: MMLU-Pro 82.5, IFEval 91.5, BFCL-V4 66.1 — materially better at tool calling. Ollama blob sizes: **0.8B 0.76 GiB, 2B 1.87 GiB, 4B 2.47 GiB, 9B 5.24 GiB** (`qwen3.5` is a first-class Ollama library model, named in the v0.40.0 notes). MLX conversions exist (`mlx-community/Qwen3.5-4B-MLX-8bit`). [V]

**Gemma 4.** Apache-2.0 on code and weights for all five sizes (E2B, E4B, 12B Unified, 26B-A4B, 31B). E4B: 42 layers, 512-token sliding window with interleaved global attention, 128K context, text + image + **audio** input (ASR/translation, capped at 30 s per clip), native function calling, configurable thinking. Published scores: E4B MMLU-Pro **69.4**, Tau2 **42.2**; 12B Unified 77.2/69.0. Ollama blob sizes: **e2b 3.26 GiB, e4b 5.12 GiB (8B total including embeddings), 12b 6.87 GiB**. Pre-Gemma-4 Gemma families remain on the custom Gemma licence — do not mix them up. [V]

**Everything else.** Ministral 3 (3B/8B/14B, Apache-2.0) is Nov 2025, not refreshed in 2026; Mistral's 2026 releases are all 100B-plus. No Llama newer than Llama 4 (Apr 2025; `license:other`, off-list). No Phi in 2026. IBM Granite 4.2 3B (Apache-2.0, created 2026-08-07) has IBM-published MLX q4/q8/bf16 conversions but no quality evidence was gathered. SmolLM's newest text models are SmolLM3-3B derivatives. [V]

| Candidate | Size / quant | Licence (code / weights) | 16 GB fit with Live | Evidence |
|---|---|---|---|---|
| **Qwen3.5-4B** | 2.47 GiB Ollama blob; hybrid 24 linear + 8 attention layers | Apache-2.0 / Apache-2.0 | Best fit among new entrants | [Qwen3.5-4B card](https://huggingface.co/Qwen/Qwen3.5-4B), registry manifest |
| Qwen3.5-9B | 5.24 GiB blob | Apache-2.0 / Apache-2.0 | Tight; only if 4B quality fails | same |
| Gemma 4 E2B-it | 3.26 GiB blob | Apache-2.0 / Apache-2.0 | Fits; weak tool scores (Tau2 24.5) | [Gemma 4 card](https://huggingface.co/google/gemma-4-E4B-it) |
| Gemma 4 E4B-it | 5.12 GiB blob | Apache-2.0 / Apache-2.0 | Tight; strongest same-class audio+text option | same |
| Granite 4.2 3B (IBM MLX q4) | MLX q4 conversion | Apache-2.0 / Apache-2.0 | Fits; quality unproven here | [granite-4.2-3b-q4-mlx](https://huggingface.co/ibm-granite/granite-4.2-3b-q4-mlx) |
| Ministral 3 3B / 8B | Nov 2025 family | Apache-2.0 / Apache-2.0 | 3B fits; 8B tight | [HF API: mistralai](https://huggingface.co/api/models?author=mistralai) |
| Qwen3-4B-2507 *(incumbent)* | KENN-measured baseline; MMLU-Pro 69.6 / IFEval 83.4 | Apache-2.0 / Apache-2.0 | Known good on 0.34.4 | KENN docs |

Inference: the lowest-risk C2/S4 experiment is a same-harness A/B of Qwen3-4B-2507 against Qwen3.5-4B with thinking off, at pinned context. Qwen3.5-4B's hybrid layout means only 8 of 32 layers carry a per-token KV cache — roughly **32 KiB/token at f16** versus **144 KiB/token** for the dense Qwen3-4B (36 layers × 8 KV heads × 128 dim × K+V × 2 bytes). That arithmetic is inferred from card geometry, not measured. No independent evaluation of either new model on KENN-shaped tasks exists yet. [I]

### 2.2 Structured output

Typed tool-call planning has first-class local support on every runtime KENN might use. Ollama takes a `format` field (JSON schema) or `response_format` on `/v1/chat/completions`; v0.34.4 changed structured outputs on thinking models to apply in a single pass and updated "llama.cpp, MLX, and XGrammar" together, i.e. schema enforcement is XGrammar-based locally. Documented tips: schema also in the prompt, temperature 0 for determinism, validate with Pydantic or Zod. Cloud models do not support structured outputs — a local-only feature, irrelevant for KENN. `tool_choice` is not supported on Ollama's OpenAI-compatible surface; the native `/api/chat` can simply omit `tools`. llama.cpp takes `-j/--json-schema`, `--grammar`, per-request `json_schema` and `response_format` (`json_object` and `json_schema`); llama.cpp ships built-in Gemma and Granite chat templates. MLX has no grammar layer in mlx-lm's own CLI surface; constrained generation on MLX goes through Outlines' `MLXLM` adapter (Apache-2.0). Qwen3.5 templates control thinking via `enable_thinking`, not the Qwen3 `/think` soft switch. [V]

Safest 2026 stack [I]: Ollama 0.40.x `format` schema + `enable_thinking=false` + temperature 0, schema embedded in the system prompt. llama.cpp `--json-schema` is the equivalent when slot-level control is needed. Measurement gap: no published schema-adherence rates for these small models under XGrammar or llama.cpp on Apple Silicon; whether Ollama's MLX runner applies `format` identically to the llama.cpp runner is unverified and worth one C2 test.

### 2.3 Latency levers and the engine swap

- **Context default is small.** Ollama defaults to **4k context below 24 GiB VRAM** (KENN's prior measured runner was 4096), 32k at 24–48 GiB, 256k above. Set `OLLAMA_CONTEXT_LENGTH` or `num_ctx`; the docs advise ≥64k for agent-style workloads. [V]
- **KV-cache quantization.** `OLLAMA_KV_CACHE_TYPE` (global) with `f16` default; `q8_0` ≈ half the memory with "very small" quality loss, `q4_0` ≈ quarter with "small-medium" loss. It requires Flash Attention, which Ollama enables automatically when supported. Docs warn high-GQA models can lose more precision — relevant to Qwen3.5-4B's 16 Q / 4 KV heads. [V]
- **llama.cpp server surface** (master, 2026-10-15): `--cache-prompt` default **enabled**; `--cache-reuse N` (default 0); `--slot-save-path`; per-slot context; `-ctk`/`-ctv` per-K and per-V cache types; speculative decoding with `--spec-draft-n-max` default **3** plus a full draft-model flag family; `--ctx-checkpoints` default 32. [V]
- **llama.cpp v0.6.0** (2026-10-05): `llama_batch_ext` API, **MTP speculative decoding for Qwen4Exp**, a **Metal tensor-API flash-attention kernel for F16 KV**, sparse flash attention for quantized K/V (Vulkan). [V]
- **Ollama's MLX runner contains its own speculative-decoding subsystem** — `mlxrunner/speculate.go` describes "a persistent speculative-decoding subsystem of a Runner — one per loaded model", with draft sessions that "learn the conversation" from committed-stream reports. v0.40.4 (2026-10-12) "improved speculative decoding reliability in the MLX runner, including recurrent state handling after rollback" and improved reuse of "verified manifests and already loaded models". [V]
- **mlx-lm** carries `--draft-model` (default 3 draft tokens), KV quantization (`kv_bits`) and a rotating KV cache (`--max-kv-size`); last tagged release **v0.31.3 (2026-04-22)**, repo active; MLX core is v0.32.4 (2026-10-14). [V]

Inferences for C2 [I]: prefer `q8_0` KV over forcing a large `num_ctx` on 16 GB (roughly 0.5–1 GiB of KV at 32k for the hybrid Qwen3.5-4B at f16, by arithmetic, not measurement); prompt-cache reuse across KENN's stable system prefix already worked at 0.34.4 (one live request: 1434 prompt tokens = 666 cached + 512 processed) and remains the cheapest prefill win; whether the MLX runner fires speculation for `qwen3.5`/`gemma4` in practice is unverified and should be instrumented, not tuned.

### 2.4 Rerankers

The clean trio, all Apache-2.0 or MIT:

| Candidate | Size | Licence (code / weights) | C5 budget note (≤250 MB, ≤150 ms p95) |
|---|---|---|---|
| **FlashRank** (ONNX) | tiny `ms-marco-TinyBERT-L-2-v2` ~**4 MB** | Apache-2.0 / Apache-2.0 | **Only reranker that clearly fits the budget**; weakest quality; `onnxruntime` already in `apps/backend/requirements.txt` |
| bge-reranker-v2-m3 | ~568M params → ~0.57 GB int8, ~1.1 GB fp16 (arithmetic) | Apache-2.0 / Apache-2.0 | Quality favourite; likely busts 250 MB unless the budget is revisited |
| Qwen3-Reranker-0.6B | ~0.6B params → ~0.6 GB int8 (arithmetic) | Apache-2.0 / Apache-2.0 | Instruction-aware, 32k context; same budget problem |

Excluded: every Jina reranker from v2 onward — `jina-reranker-v2-base-multilingual`, `jina-reranker-v3` (2025-09-18) and `jina-reranker-v3.5` (2026-07-14) are all CC-BY-NC-4.0. Only the English-only v1-turbo/tiny rerankers are Apache-2.0. Any secondary claim that bge-reranker-v2-m3 is MIT is wrong; the HF frontmatter is `license: apache-2.0`. `Qwen3-VL-Reranker-2B` exists (Apache-2.0) if image-query reranking is ever needed. llama.cpp gained RANK pooling batch splitting "for causal LLM rerankers" (aggregator-sourced build note, Sep 27) and reranker GGUF conversions exist. [V for licences; aggregator flag on the llama.cpp note]

### 2.5 Embeddings

- **EmbeddingGemma-2** (created 2026-09-14, Apache-2.0): 740M total = 270M text backbone + 170M vision + 300M audio encoders, **selectively loadable**; one 768-d space across text/images/video/audio; Matryoshka truncation to 128/256/512; **8k-token context**; 100+ languages. Packaged for every runtime KENN uses: GGUF (ggml-org, unsloth), MLX (bf16/8bit/6bit), ONNX, LiteRT, and **Ollama `embeddinggemma-2` (blob 0.28 GiB)**, named as the MLX-supported embedding model in Ollama v0.40.0. EmbeddingGemma-1 (`google/embeddinggemma-300m`) is on the custom Gemma licence — not the same thing. [V]
- **Qwen3-Embedding-0.6B** (Apache-2.0): 28 layers, 32k context, up to 1024-d output (MRL 32–1024), instruction-aware, 100+ languages; Ollama blob 0.60 GiB. The 8B sibling held MTEB-Multilingual #1 (70.58) in June 2025. [V]
- **bge-m3** (MIT): dense + sparse + multi-vector hybrid, 8k context, 32.3M downloads, Ollama blob 1.08 GiB. [V]
- Excluded: jina-embeddings-v3 (CC-BY-NC-4.0). Available later if multimodal retrieval is wanted: Qwen3-VL-Embedding-2B/8B (Apache-2.0, created 2026-01-07). [V]

Inference [I]: for text-only retrieval today, the drop-in experiment is Qwen3-Embedding-0.6B at 1024-d (or truncated 512-d to cut index size) with the index rebuilt; EmbeddingGemma-2 is the strategic pick if stem or audio metadata should live in the same vector space later. An embedding swap invalidates the index; measure "retrieval quality per ms of query latency" before trusting any MTEB rank.

### 2.6 Speech-to-text (the whisper stack)

- **whisper.cpp** (MIT, repo pushed 2026-10-12) is the zero-dependency default: Apple Silicon is first-class (NEON, Accelerate, Metal, Core ML), inference runs on the GPU via Metal, integer quantization (`q5_0`) is built in, VAD and an XCFramework exist. README memory table: tiny 75 MiB disk / ~273 MB memory, base 142 MiB / ~388 MB, small 466 MiB / ~852 MB, medium 1.5 GiB / ~2.1 GB, large 2.9 GiB / ~3.9 GB. `large-v3-turbo` is a first-class build target. The Core ML encoder is "more than x3 faster compared with CPU-only"; ANEForge is "about 2x faster than the Core ML encoder from tiny to medium". The `stream` example transcribes continuously in half-second steps — a bonus path; PTT wants record-while-held then batch transcribe on release. [V]
- **Whisper weights are clean**: `openai/whisper-large-v3-turbo` MIT (809M params), `large-v3` Apache-2.0 (1550M), `distil-large-v3` MIT. Runtimes: whisper.cpp MIT, faster-whisper MIT (not re-verified this pass; on macOS it runs CPU-only because CTranslate2 has no Metal backend, so it drops out of a Metal-first comparison). [V / U for faster-whisper]
- **Challengers.** Parakeet TDT 0.6B v3: weights CC-BY-4.0, 25 European languages; the MLX port `senstella/parakeet-mlx` is Apache-2.0 (pushed 2026-10-01). Moonshine: code MIT and "the models are MIT by default too, in every language and at every size", with one carve-out — legacy non-streaming non-English models stay under the non-commercial Moonshine Community Licence; streaming-first design, micro models down to 1 MB. Voxtral Mini 4B Realtime (Apache-2.0): "sub-500 ms" streaming delay, 13 languages — but at 4B it competes with the chat model for RAM. Qwen3-ASR 0.6B/1.7B (Apache-2.0, 30 languages) exists but was not evaluated. [V]
- Recommendation: keep whisper.cpp as the pinned PTT baseline (`small` or `large-v3-turbo`, Metal on); treat Parakeet and Moonshine as second-trial challengers justified by accuracy-per-byte; `transcribe.cpp` is third-party glue worth one look only if every STT candidate should sit behind one small runtime. [I]

### 2.7 Text-to-speech

- **Kokoro-82M** (Apache-2.0 code and weights, 10.5M downloads) is the safest pick for short spoken confirmations: 82M parameters, an order of magnitude smaller than the chat model it runs beside, Apple-Silicon instructions in the README (`PYTORCH_ENABLE_MPS_FALLBACK=1` for GPU acceleration). [V]
- **Chatterbox** (MIT weights on both the base and Nano HF repos): Turbo 350M (speech-token-to-mel decoder distilled "from 10 steps to just one"), Nano 110M ("3x realtime on 8 cores"), Multilingual V3 0.5B (23+ languages). **Every output carries Resemble's PerTh watermark, on by default** — a product decision before it is a technical one: leaving it on is consistent with disclosure framing; stripping it needs legal review. Chatterbox-Nano has ~0 HF downloads, so it is unproven in the wild. [V]
- **mlx-audio** (`Blaizzy/mlx-audio`, MIT, 8.0k★, pushed 2026-10-14) is the one actively maintained Apple-native STT/TTS toolkit; worth one spike to see whether one dependency can serve voice for the whole stack, with a fallback to per-model PyTorch paths. [V / I]
- Excluded: F5-TTS weights (CC-BY-NC-4.0; code is MIT), Piper (original repo archived; successor `piper1-gpl` is GPL-3.0), StyleTTS2 weights (no licence tag). Orpheus, Dia-1.6B and CSM-1B are licence-clean Apache-2.0 but 2025-era with no 2026 refresh — research-only until re-verified. [V]

### 2.8 Wake word

**Out of scope for now** — B4 commits to push-to-talk, which sidesteps the problem. Groundwork if a product requirement ever forces it: openWakeWord is Apache-2.0 **code**, but its shipped pre-trained models are **CC-BY-NC-SA-4.0** (README: "due to the inclusion of datasets with unknown or restrictive licensing as part of the training data"). The clean route is to train a KENN wake-word model with the Apache-2.0 pipeline on synthetic speech (<1 hour in the provided Colab notebook; English only today) and check the model in as a first-party asset. microWakeWord (Apache-2.0, pushed 2026-07-09) is the actively developed lineage to audit next, but its shipped model licences were not audited. Porcupine's repo is Apache-2.0 but the runtime needs a Picovoice AccessKey and its additional-language terms are "commercial customers case-by-case" — a terms review, not a drop-in local dependency. [V]

### 2.9 Ollama, llama.cpp and MLX releases

| Release | Date | What changed (relevant to KENN) |
|---|---|---|
| Ollama v0.40.0 | 2026-09-25 | "On Apple Silicon devices, model architectures supported by the MLX runtime will automatically run on MLX" — names `gemma4`, `qwen3.6`, `qwen3.5`, decision models, `embeddinggemma-2` |
| Ollama v0.40.1 | 2026-10-07 | Patch release on the 0.40 line |
| Ollama v0.40.2 | 2026-10-08 | Background model upgrades (runner `ggml` → `llamacpp`, old copy kept) — one tag can map to two digests |
| Ollama v0.40.3 | 2026-10-11 | Paused part of the background upgrade for request performance |
| Ollama v0.40.4 (stable) | 2026-10-12 | MLX speculative-decoding reliability (recurrent state after rollback); reusing verified manifests and loaded models |
| Ollama v0.40.5-rc0 | 2026-10-14 | GitHub pre-release (`prerelease=true`) |
| llama.cpp v0.5.0 | 2026-09-23 | First semver tag on the new release schedule |
| llama.cpp v0.6.0 | 2026-10-05 | `llama_batch_ext`; MTP spec decoding for Qwen4Exp; Metal tensor-API FA kernel for F16 KV; sparse FA for quantized K/V (Vulkan); ggml 0.26.0 |
| llama.cpp b11643 | 2026-10-15 | Current nightly (all daily builds are prereleases) |
| MLX core v0.32.4 | 2026-10-14 | Active core releases through the window |
| mlx-lm v0.31.3 | 2026-04-22 | Last tagged release; repo remains active |

**Digest-pinning finding.** Because v0.40.2 can silently re-download a different runner for the same tag, KENN's "verify the digest" step is necessary but no longer sufficient: a digest check plus a **runner check** (MLX vs llamacpp) is the honest version. An Ollama tag alone does not identify the engine on Apple Silicon as of 0.40.x. KENN's recorded baseline ran Ollama 0.34.4 with llama.cpp b11081 and prefix caching worked (1434 prompt tokens = 666 cached + 512 processed on one live request); under 0.40.x the runner package is renamed and MLX is the default for supported models, so "same model" comparisons must state the runner, not just the tag. [V for releases; I for the pinning consequence]

### 2.10 Ranked shortlists: C2, C5, B4

Effort scale: **S** ≈ one sitting under a day; **M** ≈ multi-day with a held-out evaluation attached; **L** ≈ needs its own plan slice.

**C2 — remove measured wasted work:**

1. **Runtime A/B first: Ollama 0.34.4 vs 0.40.4**, same prompt set, pinned model, reported runner; capture `eval_count`, `prompt_eval_count`, cached tokens, TTFT and runner name per call. Cheapest measurement that decides whether any prior latency conclusion survives. **Effort S.**
2. **Qwen3.5-4B (thinking off) vs Qwen3-4B-2507 A/B** at pinned context, same checkpoint lineage rule as C2 states. **Effort M.**
3. **Prompt-cache alignment check** — stable system prefix first, observe cached-token counts on the terminal response. **Effort S.**
4. **q8_0 KV trial** (`OLLAMA_KV_CACHE_TYPE`), one model, one context, quality spot-check — only after 1–2 define the engine. **Effort S.**
5. **Speculative-decoding observation on 0.40.4** — does the MLX runner fire for qwen3.5/gemma4, at what acceptance rate? Instrument, do not tune. **Effort S/M.**

**C5 — abstentions and the reranker trial (off by default; the 13 Oct decision gates it):**

1. **FlashRank, ONNX tiny model first.** Only shortlisted reranker that fits the written budget as-is; `onnxruntime` is already a dependency, so the model file is the only new asset. Its job: prove the harness (held-out set excluding the 2 Oct spike rows, recall@4, retrieval-caused-failure accounting, 150 ms p95). Weak quality is expected — the harness must be able to reject it. **Effort S.**
2. **bge-reranker-v2-m3 second, with the 250 MB line explicitly revisited** in the trial request. **Effort M.**
3. **Qwen3-Reranker-0.6B third** if instruction-aware scoring and 32k context matter more than size. **Effort M.**
4. Adjacent, not C5: one embedding-swap measurement (Qwen3-Embedding-0.6B against the current embedder on KENN's retrieval set), reporting retrieval quality per ms of query latency. **Effort S/M.**

**B4 — push-to-talk and voice (plan names "local whisper.cpp push-to-talk", one provider at a time):**

1. **whisper.cpp PTT baseline** per the plan: record-while-held, batch transcribe on release; `small` and `large-v3-turbo`; Metal on. Measure release-to-text latency and WER on Ableton vocabulary. **Effort S.**
2. **Parakeet TDT 0.6B v3 via parakeet-mlx** as the accuracy challenger, only after (1) establishes the harness. CC-BY-4.0 requires an attribution line in the product. **Effort M.**
3. **Kokoro-82M spoken feedback** for short confirmations, MPS fallback set; measure first-audio latency and whether feedback helps or annoys in a real session. **Effort S/M.**
4. **Chatterbox-Nano/Turbo voice trial** only after the PerTh watermark decision is recorded. **Effort M.**
5. **Wake word: out of scope.** If forced later, train an openWakeWord model with KENN's own pipeline rather than shipping CC-BY-NC-SA pretrained assets. **Effort M.**
6. Optional groundwork: mlx-audio spike, one dependency for STT + TTS. **Effort S (survey only).**

## 3. Audio understanding

Merged from lane 03. Scope: what KENN can do with audio beyond the 2026-10-14 engineering-candidates doc (loudness, spectral, stereo, Demucs, the GPL/AGPL trap list), covering plan B3–B4. Every claim was verified against the primary repo, HF page or issue where reachable on 2026-10-15. The lane also re-verified its predecessor's ten headline claims; the changes are in section 7.

### 3.1 Source separation

**The only shippable SOTA separation today is the ZFTurbo MSST ecosystem.** [V]

- **Demucs v4 / htdemucs: blocked on weights.** Code is MIT, but the author (adefossez, issue #327 comment, 2022-05-23) states: "The model weights are not covered by the MIT license, and are provided only for scientific purposes." A corroborating comment ties it to MUSDB training terms. Third-party mirrors contradict each other (Intel `demucs-openvino` labelled MIT; MrCitron CC-BY-NC, not re-checked this run). `demucs-mlx` inherits the same weight problem.
- **MSST (Music-Source-Separation-Training)**: MIT framework, but the author's MIT statement covers **two specific checkpoints, not his checkpoint collection**: the 53-stem MVSep Mega model (issue #245, 2026-09-25: "I have released the model weights for 53-stem model under the MIT License ... I do not hold the copyright to all audio data used to train this model") and `model_bs_roformer_ep_17_sdr_9.6568` (issue #254, 2026-09-30: "I released this checkpoint under the MIT license ... the model was trained on the MUSDB18-HQ dataset. I do not know if the dataset's license imposes any restrictions on the commercial use of models trained on it, so you will need to verify that on your end."). The live `docs/pretrained_models.md` has **no licence column**, and ZFTurbo explicitly disclaims authorship of the other entries. A follow-up question about SCNet XL IHF is unanswered as of 2026-10-15.
- **KimberleyJSN/melbandroformer**: HF licence tag **mit** (card modified 2026-04-22); SDR vocals **10.98** on Multisong — the best single-stem vocals entry in the MSST table. The separate KimberleyJensen repo carries no licence file.
- **Unstated licences everywhere else**: all viperx/aufr33/TRvlvr/jarredou checkpoints in the MSST docs (MelBand viperx, DrumSep, denoise/dereverb) have no licence statement. `kuielab/mdx23c` (MDX23C first-party) returns 404 today. `jarredou/BS-RoFormer-SW` HF page returns 401, so its "licence unknown" status is inherited, not directly observed.
- **Architecture code**: `lucidrains/BS-RoFormer` MIT; a `lucidrains/mel-band-roformer` repo could not be found (404) — Mel-Band implementations live in downstream repos. A ggml port exists (`chenmozhijin/BSRoformer.cpp`, MIT).
- **SOTA numbers in one place** ("Multisong" unless noted): MelBand Kimberley vocals SDR 10.98; BS-RoFormer (ZFTurbo) MUSDB avg 9.65; SCNet XL IHF MUSDB avg 10.08 / Multisong 9.92 (licence pending); HTDemucs4 MVSep avg 9.16; a 6-stem HTDemucs4 exists in the MSST list but its weights are the Demucs `.th` files — not shippable.
- **Conversion precedent** (third-party plans, no released tool): CoreML fp16 conversion described in-thread for iOS; TorchScript planned for a macOS plug-in.

**KENN-safe separation statement** [I]: MSST (MIT) + KimberleyJSN mel-band vocals (MIT) + the ZFTurbo BS-RoFormer bass/drums checkpoint (MIT), with the MUSDB18-HQ chain-of-title caveat quoted verbatim in NOTICE.md. The workflow matches issue #245's own example ("instrumental by subtracting a Mel-Band RoFormer vocal estimate from the mix"). These are few-hundred-MB transformer models; one track at a time on M3 is plausible but **no measured M3 number exists** — expect seconds to minutes per 3–4 min track. Until the MUSDB18-HQ dataset terms are read, even the MIT checkpoints carry a documented chain-of-title caveat. Fine-tuning on user-authorized stems is the clean long-term fix and out of this lane's scope.

### 3.2 Note and MIDI transcription

**Basic Pitch is the single clean, small, production-mature option** and KENN_PLAN B4 already names it. [V]

- Apache-2.0 (Spotify, ICASSP 2022, still maintained); official exports in the git tree: `nmp.onnx` **230,444 bytes**, `nmp.tflite` 204,448 bytes, CoreML plus TF SavedModel; default runtime order TF → CoreML → TFLite → ONNX and TF is not installed by default; instrument-agnostic polyphonic, "works best on one instrument at a time"; mono, resampled to 22,050 Hz. **No sentence grants a separate weights licence** — the model files ship inside the repo, so the Apache-2.0 grant is expected to cover them, but that is a reading, not an author statement. A one-line confirmation from Spotify would close it.
- Blocked or unstated: MT3 (code Apache-2.0, checkpoint licence unstated; heavyweight T5X/JAX chain — research-only until terms exist); `piano_transcription_inference` (archived 2023, no licence at all); RMVPE (`Dream-High/RMVPE`, code Apache-2.0, pretrained `rmvpe.pt` weight **unstated**, widely used inside the so-vits-svc AGPL ecosystem).
- Clean small extras: `torchcrepe` (now `maxrmorrison/torchcrepe`) MIT, weight bundled with the package (inferred MIT); `swift-f0` MIT (pushed 2026-09-25), lightweight f0 tracker. No licence-clean melody extractor was found (classic Melodia is a GPL Vamp plug-in).
- Practical stack [I]: Basic Pitch ONNX on bounded instrument clips, one at a time; torchcrepe or swift-f0 if a monophonic pitch curve is wanted for vocal tuning analysis. None of these need TensorFlow on macOS in production. No clean, shippable guitar-transcription model exists — guitar-specific AMT is research code.

### 3.3 Audio embeddings and sound search

**LAION-CLAP is the only licence-clean audio-text embedder.** [V]

- LAION-AI/CLAP repo **CC0-1.0**; PyPI `laion-clap` CC0 1.0; the primary checkpoint host `lukewys/laion_clap` is tagged **cc0-1.0**; the HF Transformers mirror `laion/clap-htsat-unfused` is **apache-2.0** (1.07M downloads). Embedding dims: 512-d joint space / 768-d HTSAT audio tower [I]. (The prior "apache-2.0 weights" phrasing was corrected this run: apache only covers the mirror.)
- Blocked or unresolved: MS-CLAP (code MIT under `microsoft/CLAP`, but `microsoft/clap-ms-2023` weights return HTTP 401; the earlier "ms-pl" claim could not be reproduced); MuQ (code MIT, weights `OpenMuQ/MuQ-large-msd-iter` CC-BY-NC-4.0); MERT (code Apache-2.0, weights `m-a-p/MERT-v1-95M` CC-BY-NC-4.0); musicnn (code ISC, weights unstated, Million Song Dataset research terms).
- Off-list but non-NC: **OpenL3** — code MIT; README states "The model weights are made available under a Creative Commons Attribution 4.0 International (CC BY 4.0) License" — gated, not blocked; dated and needs TF2.
- **Expect weak absolute retrieval.** MAEB (arXiv 2602.16008, 2026-02-17) evaluates 53 encoders: "most models show weak retrieval performance (CLAP variants around 8–14%)", best clustering 22.7% V-measure, multilingual retrieval below 3% for most language pairs. The ACL 2026 Main paper Omni-Embed-Audio (arXiv 2604.18360) argues caption-style benchmarks flatter models vs real user-intent queries. A 2026 DAFx paper (arXiv 2607.03806) shows LUFS/RT60/spectral-centroid are recoverable from CLAP embeddings — evidence CLAP carries low-level mix attributes, not only semantics. [V]
- Product implication [I]: CLAP is fine as a ranking and embedded-suggestion aid; do not promise semantic search accuracy. ONNX/CoreML export is routine but no official export exists.

### 3.4 Drum and rhythm

**beat_this is the one clean drum-adjacent win**, with a dependency caveat. [V]

- `CPJKU/beat_this` (ISMIR 2024) licence section verbatim: "The code and the published model weights are released under the MIT license. Note that some of the training files are fully copyrighted or under limited Creative Commons licenses, and it is up to the user to assess whether this may impact their use case." Sizes: main `final*` ≈ 78 MB; `small*` ≈ **8.1 MB** per model. Its inference requirement list includes `soxr` → PyPI licence **LGPL-2.1-or-later** (blocked by policy unless replaced or isolated). The optional DBN needs madmom (GPL) and is not required; the paper's point is no DBN post-processing.
- ADTOF: LICENSE file is **CC BY-NC-SA 4.0** — blocked. No drum-transcription alternative with a first-party permissive statement was found. Drum-separation checkpoints (jarredou/aufr33) have unstated licences. No shippable groove model exists; groove/pattern analysis is better served by KENN's own DSP (onset/tempo from existing C++ meters).
- If beat_this ships: replace `soxr` with a permissive resampler (torchaudio or vDSP-based) or document LGPL as isolated; the licence argument applies to both code and the weights chain.

### 3.5 Music generation (future, opt-in)

**Exactly two families are Apache-2.0 end-to-end:** ACE-Step and DiffRhythm. [V]

- **ACE-Step v1**: repo and HF weights `Apache-2.0`; 3.5B params; first-party Mac timing: **MacBook M2 Max, RTF 2.27 at 27 steps = 26.43 s per minute of audio** (58.25 s/min at 60 steps); max VRAM reduced to 8 GB with `--torch_compile true --cpu_offload true --overlapped_decode true`; macOS requires `--bf16 false`. v1.5 (announced 2026-01-28) exists and its licence is **not verified**. LoRA variants (Lyric2Vocal, Text2Samples) exist.
- **DiffRhythm**: "DiffRhythm (code and DiT weights) is released under the Apache License 2.0"; 1.2B base; "requires a minimum of 8G of VRAM ... use the `--chunked` argument"; full-length 285 s generation; macOS supported since 2025-03-11. Caveats: the HF checkpoint repos carry no licence tag (`ASLP-lab/DiffRhythm-1_2B` 401s), the separate `DiffRhythm-vae` licence is unstated, and the runtime needs `espeak-ng` (**GPL-3.0** — must be isolated or avoided).
- **YuE**: Apache-2.0 code and weights, but a 7B + 1B stack — weight memory alone exceeds comfortable 16 GB f16 use.
- **Blocked (verified HF tags)**: `facebook/musicgen-small` CC-BY-NC-4.0; `facebook/magnet-small-10secs` CC-BY-NC-4.0; `cvssp/audioldm2` CC-BY-NC-SA-4.0; `declare-lab/tango2` **CC-BY-NC-SA-4.0** (prior note said ND — corrected); `StabilityAI/stable-audio-open-small` gated `stability-ai-community` licence with revenue terms. Mustango not checked; treat as blocked by family.
- If generation ever ships [I]: ACE-Step v1 is the pick on licence plus Mac evidence; DiffRhythm second (smaller, VAE and espeak caveats). Both are background-render workloads, never interactive, behind B4's explicit opt-in and licence review. Both READMEs themselves ask users to verify originality of generated audio.

### 3.6 Sample-library retrieval infrastructure

- **Freesound API**: the free tier is non-commercial — "You can use the Freesound API for free only for non-commercial purposes" — and the licence is "temporary and may be withdrawn by Freesound at any time"; keys "may be revoked"; commercial terms are "negotiated on a case by case basis". Per-sound CC licences still apply, and NC sounds must be filtered even under a deal. Treat as a contracted vendor behind explicit opt-in, never a default path. [V]
- **Local fingerprinting**: chromaprint is LGPL-2.1 **as a whole** ("Chromaprint's own source code is licensed under the MIT license, but we include some parts of the FFmpeg library ..."), so do not bundle it; **audfprint** (`dpwe/audfprint`, MIT) is the clean substitute, frozen since 2019 but pure NumPy and simple to vendor. [V]
- Local index plan [I]: file-hash dedupe → audfprint fingerprints for near-duplicate detection → CLAP embeddings for text/similarity search. All against the user's own files, so no distribution licence arises; only code licences matter. No Freesound commercial price/volume terms are published.

### 3.7 Mix-scoring models

- **NISQA**: code MIT, weights **CC BY-NC-SA 4.0**, and the domain is transmitted or synthesized **speech** only — blocked twice over. [V]
- **AudioBox-Aesthetics** (Meta): repo and HF weights both **CC-BY-4.0** (permissive with attribution, but off the strict allow-list — gated). Predicts labelled aesthetic/quality dimensions (CE/CU/PC/PQ per the model card); exact head semantics should be verified before product use. 508K HF downloads. [V]
- SQUIM / speech quality metrics in torchaudio are speech-only, not music-relevant (licence not re-verified). **No licence-clean music-mix quality model exists in the open.** KENN's own C++ meters remain the only fully owned mix-scoring layer; CLAP-embedding probes and AudioBox-Aesthetics are opt-in research aids, not shipped grading, because no model is validated on club or pop mixes. [V / I]

### 3.8 Ranked shortlist and 16 GB caveats

| Rank | Feature | Stack | Licence state | Effort | Notes |
|---|---|---|---|---|---|
| 1 | Audio-to-MIDI on bounded clips (B4) | Basic Pitch ONNX (CoreML on macOS) | Clean both sides | S | 230,444-byte model; no TF; B4 names it |
| 2 | Push-to-talk voice (B4) | whisper.cpp or faster-whisper + large-v3-turbo | Clean both sides | S–M | MIT runtimes and MIT turbo weights; do not use whisper-timestamped (AGPL) |
| 3 | MIDI artifact pipeline (B3) | Existing artifact provider + Basic Pitch output | Clean | S | Bounded, hashed, labelled artifacts already engineered |
| 4 | Reference/material suggestions (B4, E6 adjacent) | LAION-CLAP embeddings + local index (audfprint for dedupe) | CC0 both sides | M | Frame as ranking aid; MAEB 8–14% sets expectations |
| 5 | Separation / target extraction (B4 helpers) | MSST + KimberleyJSN mel-band (vocals) + ZFTurbo BS-RoFormer (bass/drums) | MIT per author statements; MUSDB18-HQ caveat documented | M–L | Conversion precedent third-party only; measure M3 |
| 6 | Beat/downbeat timeline (B4 support) | beat_this `small` | MIT both sides | S | Replace or isolate `soxr` (LGPL-2.1) |
| 7 | Library dedupe/detection (B4) | audfprint | MIT | S | Avoid chromaprint (LGPL as a whole) |
| 8 | AudioGen, opt-in only (B4) | ACE-Step v1 (primary) / DiffRhythm (alternate) | Apache both sides | L | M2 Max 26.43 s per minute; gate behind opt-in + licence review; verify ACE-Step v1.5 terms first |
| — | Mix scoring (E2/E9 research) | KENN DSP meters (shipped) + optional AudioBox-Aesthetics research | CC-BY-4.0 (gated) | M/L | No clean music-MOS model; keep out of shipped claims |

**16 GB feasibility caveats.** The only first-party Mac timing found anywhere in this sweep is ACE-Step's M2 Max figure; there is no published M3-16 GB number for Demucs, BS-RoFormer, CLAP, Whisper, beat_this or any embedder. Every separation, embedding and generation model must be run one at a time beside Live, and each needs an on-machine measurement of peak memory and wall time before any product promise. The plan's own B4 rule applies: pin code and weight licences separately, qualify offline operation and resource use. [I]

## 4. Teaching, grading and practice patterns

Merged from lane 04. Context: KENN is a closed-source, local-first assistant for Ableton Live; this lane covers the education and grading layer (`KENN_PLAN.md` E1–E11): datasets and papers for mix critique, citable grading conventions, teaching-tooling OSS, spaced repetition, and comparable-product UX patterns.

### 4.1 Research findings: datasets and papers

**MixAssist — the phrasing reference.** "MixAssist: An Audio-Language Dataset for Co-Creative AI Assistance in Music Mixing" (Clemens & Marasović, arXiv 2507.06329, COLM 2025, CC BY 4.0). Shape: 431 audio-grounded expert responses from 7 one-hour sessions with 12 producers (two swapped roles, so 14 pairings); splits 241 train / 34 dev / 156 test, with two complete sessions held out. Result: fine-tuned Qwen-Audio-Instruct-7B achieved top rank in **50.4%** of LLM-as-judge evaluations against fine-tuned LTU and MU-LLaMA. Human check: 10 producers, 100 comparisons — generated Qwen preferred 40% of the time, the original expert 33% (paper calls this preliminary). Real-time study (10 producers, ~5 min each): 70% rated the interaction "Somewhat/Very natural", 70% got ideas they had not considered, and users rated their own creative contribution higher than the agent's; named limits are audio-analysis depth and suggestion creativity. The paper's own design lessons: producers want an "explainable teacher and assistant", feedback shown visually inside the DAW, and guidance that stays on the right side of creative control; attribution and consent around training data came up unprompted. That is the E4 brief in external words. Code: `github.com/mclemcrew/MixAssist` MIT, 19★, pushed 2026-07-24; the repo carries a reconstructed fine-tuning pipeline (weights not bit-identical to the original). LoRA adapter: `mclemcrew/Qwen2-Audio-MixAssist-LoRA` (base Qwen2-Audio-7B-Instruct, QLoRA 4-bit nf4, r=8, α=32; ~11 minutes on one GB10; decode with sampling plus `repetition_penalty=1.1` — greedy decoding loops). The HF datasets (`mclemcrew/MixAssist`, `mclemcrew/MixParams`) declare **no licence** — reading material only. Raw audio/transcripts live on **two Zenodo records, both cc-by-4.0**: 15571750 (the record the paper cites; 47 files; 3,841,882,881 bytes ≈ 3.84 GB) and 15848443 (the record the model card cites; 8 files; 2,461,168,869 bytes ≈ 2.46 GB). [V]

**MED — Mix Evaluation Dataset.** Not on Zenodo. The live copy is HuggingFace `sparrowreivun/Mix-Evaluation-Dataset-2.0` (created 2026-09-24, 907 downloads, **no licence declared**, recorded size 187.5 GB). The DAFx-17 paper (De Man & Reiss, 2017) says verbatim: "Six of the ten songs are made available in their entirety under a Creative Commons BY 4.0 license"; the other four are copyrighted and not online. Listening interface: rd-conx.github.io/med-web (MUSHRA-style). KENN use: offline calibration and listening-test material restricted to the six CC BY tracks; **never redistribute from the Hub mirror**. [V]

**Adjacent papers.** SPHERE (arXiv 2608.30559, EMNLP 2026) encodes "music mixing conventions" as six deterministic perceptual sub-rewards for upmixing — transferable claim: expert domain knowledge can be encoded as verifiable rewards. MEGAMI (arXiv 2511.08040, ICASSP 2026 submission) frames mixing as "characterized by subjectivity where multiple valid solutions exist for the same input" — one-line support for KENN's ranges-and-reasons stance. Sequential Stem Blending (arXiv 2608.05506) models mixing the way engineers work — blending one stem into a growing submix. AI TrackMate (arXiv 2412.06617, NeurIPS 2024 Creative AI) is the measure-then-phrase pipeline precedent: Music Analysis → LLM-Readable Music Report → Production-Oriented Feedback (pilot study n=1). PardonMix (CHI EA '26, doi 10.1145/3772363.3798647) argues expert disagreement "is not random noise but a structured" signal — abstract only, full text paywalled. Still referenceable: the adoption survey (arXiv 2304.03407), reference-song communication (arXiv 2304.03404), and "Semantic Music Production" (JAES 2022). [V]

Net: no public dataset pairs acceptable ranges with explanations. MixAssist is the phrasing set, MED the listening set, SPHERE the reward-design precedent. Nothing here changes E2's structure; all of it supports "measure first, phrase second". [I]

### 4.2 Citable standards vs house rules

Rule for the whole grading layer: **every number KENN prints in a grade or a lever either cites a public document or is labelled a house rule.** This subsection is that audit. [V, re-read from the primary PDFs 2026-10-15]

| Claim | Source | Verified wording / value |
|---|---|---|
| True-peak ceiling | EBU Tech 3343 (2023) | "The Maximum True-Peak Level in production shall not exceed −1 dBTP"; use −2 dBTP where data-reduction codecs follow |
| Loudness target + tolerance | EBU R128 rev 3 (2020), quoted via Tech 3343 | Target −23 LUFS; production tolerance ±0.2 LU |
| Digital alignment level | EBU R68 | 1 kHz alignment = −18 dBFS; the old peak-meter level −9 dBFS (ITU-R BS.645) is obsolete |
| Downmix convention | EBU R128 family | Lo/Ro is the default downmix |
| Programme loudness (broadcast) | AES TD1006.1.17-10 | −16 ±1 LKFS; maximum true peak −1 dBTP |
| Music targets (streaming era) | AES TD1008.1.21-9 (published 24 Sep 2021, supersedes TD1004) | track-normalized music −16 LUFS; album −14 LUFS; speech −18 LUFS |
| Spotify platform target | Spotify's own loudness page | −14 LUFS; −1 dBTP (−2 dBTP if louder) |

- AES77-2023 exists (aes2.org listing) but the PDF is paywalled/403 — **cite the title only, never values we have not read**.
- The EBU R128 PDF itself was not opened this run; Tech 3343 carries the quotable R128 values. ITU-R BS.1770 remains the underlying measurement standard; we rely on the EBU/AES restatements.

**House rules (no open citable source — must be labelled as ours):** headroom targets (mix bus, stems); mono-compatibility and correlation thresholds (only the sign of correlation has a published basis; the E2 work records 3 of 16 deductions as published, 13 as house rules); gain-staging baselines (the name/fader-derived ones were already converted to advice-only on 14 Oct). [V]

Copy implications for E2–E4 [I]: keep the `source` field on every deduction as the logic moves into E3; each E3 lever either names its standard ("EBU R128 −23 LUFS") or says "our measured range"; E4 explanations cite the standard by name where one exists, otherwise use "we measured" phrasing. Never dress a house rule as a standard.

### 4.3 Comparable-product patterns

Quotes read from the live pages on 2026-10-15; licences from raw LICENSE files where noted.

| Pattern | Who | Verified anchor | Maps to |
|---|---|---|---|
| Free instant mix report, no account; per-category verdicts (tone/EQ, dynamics, loudness, stereo) with suggested fixes | RoEx Mix Check Studio | Genre-adapted feedback; "1.1M+ tracks analyzed"; reports savable/shareable | E2 surface; E3 category-shaped levers |
| "Starting point, not verdict" — assistant proposes, producer keeps or rejects; do-no-harm framing | iZotope Neutron 5 Mix Assistant | Copy: "starting point", "tweak to taste, or reject", "do no harm"; Target Library compares against a reference | E3 (reversible levers), E5 (Apply/Undo), E4 (tone) |
| Genre mix profiles plus custom profiles built from the user's own reference track; multi-track group view (10 tracks) | sonible smart:EQ 4 | "custom reference profiles" (correction: "reference zone" was not found in the live copy) | E2 (declared target, reference match), E6 |
| Create-tools that deliberately do not grade | Output Co-Producer | "listens, curates & lets you decide"; "AI should power your workflow, but not make choices for you"; Re-imagine 2.0 shipped 16 Sep 2026 | E4 (division-of-labour copy); contrast for our grade |
| Massive tool-count DAW agent | dreamrec/LivePilot | 82★, BSL-1.1 (raw LICENSE verified: "Business Source License 1.1"), pushed 2026-10-15; "474 tools across 57 domains" | pattern-only; the tool-sprawl trap |
| Automated mixing/mastering agent plus skills | fadelabs/phantom | 39★, AGPL-3.0 (raw LICENSE verified); "MCP server + Claude Code skills for automated mixing/mastering" | avoid as dependency; agents want to do, KENN teaches |

### 4.4 Relevance to E1–E11

Plan-item definitions read from `KENN_PLAN.md` lines 2375–2450. Lane 03 assumed the E-family meant the four capability probes inside B4 because it could not locate E1–E4; the plan defines E1–E11 explicitly, so that assumption is discarded (see section 7). [I]

| Item | What it is | Finding from this lane |
|---|---|---|
| E1 Real-time analysis | 100 ms windows with positions, age, drops | Not covered by this lane; B1's conformance vectors (LUFS/LRA/true peak) remain the measurement anchor |
| E2 Grade out of 100 | 30 technical health / 30 declared target / 40 reference match | Carry the citable-vs-house split and the `source` field into the grade text; targets list matches AES TD1008 + Spotify + the −1 dBTP ceiling |
| E3 Specific, actionable help | Short lever list, bound to Live targets or marked informational | Each lever names its standard or says "our measured range"; Neutron's "starting point" register is the right tone |
| E4 Explain and teach | Explain why and what to listen for | Build the style sheet from MixAssist dialogues (CC BY 4.0, attribution); cite standards by name where they exist |
| E5 Gate the whole flow | Full path with Apply/Undo and human grading | Neutron's reversible-lever pattern is the closest shipped analogue |
| E6 Reference library and mix archive | Named mixes re-graded after each change | sonible's custom reference profiles are the shipped precedent |
| E7 Remembering the session | Context across turns and sessions | Not covered here; lane 01's set-scoped memory pattern (E7/B2) applies |
| E8 Learning path vs one-off help | Formal curriculum separate from ad-hoc questions | fsrs (PyPI, MIT) as scheduler; music21 (BSD-3; corpus caveat), partitura (Apache-2.0), tonal (MIT), VexFlow (MIT per file) as utilities; no open mixing curriculum exists, author content in-house (E11 is its natural source of record) |
| E9 Is the grade reliable? | Check the grade, do not assume | MED six CC BY songs for A/B calibration of tolerances; the 3-of-16 published basis is the precedent to keep |
| E10 Before/after comparison | Keep analysis, re-grade against the original | Output Co-Producer's "lets you decide" is the division-of-labour contrast |
| E11 Expert network | Engineers contribute notes, lessons, benchmarks | The curriculum content gap is E11's supply problem, not a tooling problem |

Teaching-tooling details [V]: music21 BSD-3-Clause, 2,600★, pushed 2026-10-13 — corpus caveat verbatim: "Some encodings included in the corpus may not be used for commercial uses or have other restrictions"; partitura Apache-2.0, 377★; tonal MIT via the npm registry (the GitHub API field reads null — cite npm); VexFlow MIT per LICENSE text (4,397★, last push 2025-03-05; the GitHub API reports NOASSERTION because the copyright preamble defeats the detector); audiate Apache-2.0 but 11★ and last touched 2021 (patterns only). The FSRS stack is uniformly MIT: fsrs (PyPI) 6.3.2 uploaded 2026-08-09, py-fsrs (512★), fsrs4anki (4,108★, pushed 2026-08-14) as the reference for parameter fitting and desired-retention behaviour. SuperMemo2 (Python) is MIT but archived 2024 — do not depend on it.

### 4.5 The /100 grading differentiator

**No product found ships a numeric grade out of 100 with reasoning, and none ships a curriculum.** The closest are RoEx (categorical verdicts, no number) and Neutron (suggestions, no number). KENN's E2 proposal — 30 technical health / 30 declared target / 40 reference match, with the reasoning shown and "42 of 60, no reference supplied" instead of rescaling — is not matched by anything checked. The differentiator holds: numbered, reasoned, teach instead of do. [V for the product check; I for market-completeness — true of the products checked, not an exhaustive survey]

## 5. Cross-cutting licence table

Every dependency, data source and deliberately-avoided item named in this document, one row each. Families that share a licence and a source are one row, marked as a family. Verdict vocabulary: **shippable** = licence-compatible with a closed-source product under `THIRD_PARTY_LICENCES.md` (not an adoption approval); **gated** = off the allow-list or requiring an owner/legal decision (CC-BY-4.0 attribution, commercial deal, unread licence); **blocked** = GPL/AGPL/LGPL/BSL/non-commercial/unclear; **test-only** = MPL-2.0-class tooling, none of which appears in these lanes. "Recorded (not re-checked)" marks a dependency already in use whose licence was outside this pass's scope. A dash in the source column marks an item the lane notes name without a recorded URL; the link is not asserted here. The "recorded (not re-checked)" rows cite the file that records them instead, in the last column. Dates in section headers are the verification dates.

### 5.1 Ableton integration surfaces

| Name | Licence (code / weights) | Primary source | Verdict | Where it would apply |
|---|---|---|---|---|
| AbletonOSC | MIT | [GH](https://github.com/ideoforms/AbletonOSC) | shippable | OSC spine; already vendored |
| ableton-js | MIT | [GH](https://github.com/leolabs/ableton-js) | shippable | candidate coverage superset (browser, chain, grouped undo) |
| Extensions SDK (`@ableton-extensions/*`, `.ablx`) | unknown; Centercode-gated | [FAQ](https://help.ableton.com/hc/en-us/articles/27303428331420-Ableton-Extensions-FAQ) | gated | future `.ablx` companion; owner/legal must read the zip licence |
| Max for Live | unverified terms | [Extensions FAQ cross-ref](https://help.ableton.com/hc/en-us/articles/27303428331420-Ableton-Extensions-FAQ) | gated | only real-time audio/MIDI path; not needed today |
| ahujasid/ableton-mcp | MIT | — | shippable | comparable bridge; telemetry contrast |
| dreamrec/LivePilot | BSL-1.1 (→ MIT 2030-04-13) | [GH](https://github.com/dreamrec/LivePilot) | blocked | pattern reference only |
| adamjmurray/producer-pal | GPL-3.0-or-later | [GH](https://github.com/adamjmurray/producer-pal) | blocked | field notes and ADR only |
| OthmanAdi/loophole | MIT | [GH](https://github.com/OthmanAdi/loophole) | shippable | test-split pattern, `FakeLiveBridge` |
| jasper-zheng/ableton-sdk-mcp | none | — | blocked | — |
| t1merickson/next-live-mcp | MIT | — | shippable | capability-honest pattern |
| ulm0/ableton-live-mcp | MIT | — | shippable | extension-native MCP watch list |
| idx3d/ableton-mcp-extension | MIT | — | shippable | extension-native MCP watch list |
| pnomolos/live-wire | GPL-3.0 | — | blocked | — |
| Paulstretch for Live | GPL-2.0 | [GH](https://github.com/olilarkin/paulstretch-for-live) | blocked | — |
| Noise Canvas | AGPL-3.0 | — | blocked | — |
| @protocol0/extension-sdk | MIT | [npm](https://www.npmjs.com/package/@protocol0/extension-sdk) | shippable | localhost HTTP + OpenAPI pattern |
| xiaolaa2/ableton-copilot-mcp | MIT | — | shippable | competing bridge, not a dependency |
| CanArslanDev/ableton-live-mcp | MIT | — | shippable | watch list |
| cmdiego/ableton_live_mcp | Apache-2.0 | — | shippable | watch list |
| madisonrickert/ableton-tools | MIT | — | shippable | skills pattern |
| freekmurze/ableton-ai | MIT | — | shippable | dormant |
| peterkolbe/ableton-for-ai | MIT | — | shippable | dormant; self-describing JSON pattern |
| F-Fischer/ableton-copilot | MIT | — | shippable | dormant |
| josefigueredo/ableton-mcp | MIT | — | shippable | dormant |
| RiotTheMan/ableton-mentor-mcp | MIT | — | shippable | dormant |
| alpacaaa/max4node | none | — | blocked | dead since 2020 |
| 2bbb/node-abletonlink | MIT | — | shippable | irrelevant (Link tempo sync) |
| amitbaz/music-production-ai-mentor | MIT | — | shippable | education framing, first week only |
| rremedio-web/composing-sidekick | MIT | — | shippable | composer-identity idea |

### 5.2 Brain, retrieval and runtimes

| Name | Licence (code / weights) | Primary source | Verdict | Where it would apply |
|---|---|---|---|---|
| Qwen3.5 small family (0.8B/2B/4B/9B) | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/Qwen/Qwen3.5-4B) | shippable | chat/planner challenger (C2/S4) |
| Qwen3-4B-2507 (incumbent) | Apache-2.0 / Apache-2.0 | [HF API](https://huggingface.co/api/models?author=Qwen&sort=createdAt&direction=-1) | shippable | production control |
| Qwen3.6 and Qwen3.8 | Apache-2.0 | [HF API](https://huggingface.co/api/models?author=Qwen&sort=createdAt&direction=-1) | shippable (no sub-14B fit) | none on 16 GB |
| Gemma 4 family (E2B/E4B/12B/26B/31B) | Apache-2.0 / Apache-2.0 | [licence page](https://ai.google.dev/gemma/apache_2), [HF](https://huggingface.co/google/gemma-4-E4B-it) | shippable | E4B challenger |
| Pre-Gemma-4 Gemma family (incl. `embeddinggemma-300m`) | custom Gemma licence | [HF](https://huggingface.co/api/models/google/embeddinggemma-300m) | blocked | — |
| Granite 4.2 3B + IBM MLX conversions | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/ibm-granite/granite-4.2-3b) | shippable | shadow trial |
| Ministral 3 (3B/8B/14B) | Apache-2.0 | [HF API](https://huggingface.co/api/models?author=mistralai&sort=createdAt&direction=-1) | shippable | 3B fits, 8B tight |
| Llama 4 family | `license:other` (Llama Community Licence) | [HF API](https://huggingface.co/api/models?author=meta-llama&sort=createdAt&direction=-1) | blocked | — |
| Ollama | MIT | [GH](https://github.com/ollama/ollama) | shippable | local runtime |
| llama.cpp | MIT | [GH](https://github.com/ggml-org/llama.cpp) | shippable | local runtime |
| mlx / mlx-lm | MIT | [GH](https://github.com/ml-explore/mlx-lm) | shippable | LoRA training and eval |
| Outlines (MLX adapter) | Apache-2.0 | [GH](https://github.com/dottxt-ai/outlines) | shippable | constrained generation on MLX |
| XGrammar (Ollama's schema layer) | not read this pass | [Ollama v0.34.4 notes](https://github.com/ollama/ollama/releases/tag/v0.34.4) | gated (unread) | local schema enforcement |
| bge-reranker-v2-m3 | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/BAAI/bge-reranker-v2-m3) | shippable | C5 trial 2 |
| Qwen3-Reranker-0.6B | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | shippable | C5 trial 3 |
| Qwen3-VL-Reranker-2B | Apache-2.0 | — | shippable | image-query reranking later |
| FlashRank | Apache-2.0 | [GH](https://github.com/PrithivirajDamodaran/FlashRank) | shippable | C5 trial 1 |
| Jina rerankers v2 onward (v2, v3, v3.5) | CC-BY-NC-4.0 | [HF search](https://huggingface.co/api/models?search=jina-reranker) | blocked | — |
| Qwen3-Embedding-0.6B | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | shippable | retrieval embedder |
| EmbeddingGemma-2 | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/google/embeddinggemma-2) | shippable | multimodal embeddings |
| bge-m3 | MIT / MIT | [HF](https://huggingface.co/BAAI/bge-m3) | shippable | hybrid retrieval fallback |
| jina-embeddings-v3 | CC-BY-NC-4.0 | [HF](https://huggingface.co/api/models/jinaai/jina-embeddings-v3) | blocked | — |
| Qwen3-VL-Embedding-2B/8B | Apache-2.0 | [HF](https://huggingface.co/api/models/Qwen/Qwen3-VL-Embedding-2B) | shippable | image/scene embeddings later |
| Ollama tag manifests (model blobs) | n/a | [registry](https://registry.ollama.ai/v2/library/qwen3.5/manifests/4b) | recorded (not re-checked) | size evidence only |

### 5.3 Voice

| Name | Licence (code / weights) | Primary source | Verdict | Where it would apply |
|---|---|---|---|---|
| whisper.cpp | MIT | [GH](https://github.com/ggml-org/whisper.cpp) | shippable | PTT baseline (B4) |
| OpenAI Whisper weights (turbo MIT; v3 Apache-2.0; distil MIT) | permissive, mixed | [HF API](https://huggingface.co/api/models/openai/whisper-large-v3-turbo) | shippable | STT weights |
| Parakeet TDT 0.6B v3 weights | CC-BY-4.0 | [HF](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | gated (attribution) | STT challenger (B4) |
| senstella/parakeet-mlx | Apache-2.0 | [GH](https://github.com/senstella/parakeet-mlx) | shippable | Parakeet runtime on MLX |
| Moonshine | MIT code and models (non-English legacy non-streaming: Community Licence) | [GH](https://github.com/moonshine-ai/moonshine) | shippable (English/streaming; carve-out) | streaming STT challenger |
| Voxtral Mini 4B Realtime | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602) | shippable | streaming STT, RAM-heavy |
| Qwen3-ASR 0.6B / 1.7B | Apache-2.0 | — | shippable | STT, unevaluated |
| faster-whisper | MIT | — | shippable | STT runtime (macOS CPU-only) |
| transcribe.cpp | not verified this pass | — | gated (unread) | optional single-runtime glue |
| Kokoro-82M | Apache-2.0 / Apache-2.0 | [HF](https://huggingface.co/hexgrad/Kokoro-82M) | shippable | TTS default (B4) |
| Chatterbox (Turbo/Nano/V3) | MIT / MIT | [GH](https://github.com/resemble-ai/chatterbox), [HF](https://huggingface.co/api/models/ResembleAI/chatterbox-nano) | shippable (PerTh decision first) | TTS personality trial |
| mlx-audio | MIT | [GH](https://github.com/Blaizzy/mlx-audio) | shippable | Apple-native STT/TTS toolkit |
| F5-TTS | MIT code / CC-BY-NC-4.0 weights | [HF](https://huggingface.co/SWivid/F5-TTS) | blocked | — |
| Piper / piper1-gpl | GPL-3.0 (successor; original archived) | [GH](https://github.com/OHF-Voice/piper1-gpl) | blocked | — |
| StyleTTS2 weights | none on checkpoint | [HF search](https://huggingface.co/api/models?search=StyleTTS2) | blocked | — |
| Orpheus | Apache-2.0 | [HF](https://huggingface.co/api/models/canopylabs/orpheus-3b-0.1-ft) | shippable (frozen 2025) | research only |
| Dia-1.6B | Apache-2.0 | [HF API](https://huggingface.co/api/models/nari-labs/Dia-1.6B) | shippable (frozen) | research only |
| CSM-1B | Apache-2.0 | — | shippable (frozen) | research only |
| openWakeWord (code) | Apache-2.0 | [GH](https://github.com/dscripka/openWakeWord) | shippable | wake-word pipeline (train own model) |
| openWakeWord (pre-trained models) | CC-BY-NC-SA-4.0 | [GH §License](https://github.com/dscripka/openWakeWord) | blocked | do not ship |
| microWakeWord | Apache-2.0 code; model licences unaudited | [GH](https://github.com/kahrendt/microWakeWord) | gated (models unread) | wake-word lineage to audit |
| Porcupine (Picovoice) | Apache-2.0 bindings; runtime needs AccessKey, commercial terms case-by-case | [GH](https://github.com/Picovoice/porcupine) | gated | terms review first |

### 5.4 Audio ML

| Name | Licence (code / weights) | Primary source | Verdict | Where it would apply |
|---|---|---|---|---|
| MSST (ZFTurbo) framework | MIT | [GH](https://github.com/ZFTurbo/Music-Source-Separation-Training) | shippable | separation engine |
| ZFTurbo 53-stem MVSep Mega checkpoint | MIT (author statement #245) | [issue](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245) | shippable | >6-stem separation |
| ZFTurbo BS-RoFormer `ep_17_sdr_9.6568` | MIT (author statement #254; MUSDB18-HQ caveat) | [issue](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/254) | shippable (notice required) | bass/drums stems |
| KimberleyJSN mel-band RoFormer | MIT (HF tag) | — | shippable | vocals separation |
| Demucs v4 / htdemucs | MIT code / weights "not covered ... only for scientific purposes" | [issue](https://github.com/facebookresearch/demucs/issues/327) | blocked | — |
| demucs-mlx | MIT code; inherits Demucs weights | — | blocked (weights) | — |
| Open-Unmix | MIT code / `umxl` CC-BY-NC-SA, `umxhq` unstated | [GH](https://github.com/sigsep/open-unmix-pytorch) | blocked (weights) | — |
| Spleeter | MIT code / weights unstated | [GH](https://github.com/deezer/spleeter) | blocked (weights) | — |
| lucidrains/BS-RoFormer | MIT | — | shippable | architecture code |
| chenmozhijin/BSRoformer.cpp | MIT | — | shippable | C++ inference precedent |
| MDX23C first-party (kuielab) | repo 404 / checkpoints unstated | — | blocked | — |
| viperx / aufr33 / TRvlvr / jarredou checkpoint families | no licence statement | [MSST docs](https://raw.githubusercontent.com/ZFTurbo/Music-Source-Separation-Training/main/docs/pretrained_models.md) | blocked | — |
| jarredou/BS-RoFormer-SW | unresolved (HF 401) | — | blocked | — |
| Basic Pitch | Apache-2.0; no separate weights grant (repo-distributed) | [GH](https://github.com/spotify/basic-pitch) | shippable (confirmation advised) | audio-to-MIDI (B4) |
| MT3 | Apache-2.0 code / checkpoint unstated | — | blocked (weights) | — |
| piano_transcription_inference | none (archived) | — | blocked | — |
| torchcrepe | MIT (weight bundled, inferred) | — | shippable | f0 tracking |
| RMVPE | Apache-2.0 code / weight unstated | — | blocked (weights) | — |
| swift-f0 | MIT (bundled model detail unverified) | — | shippable | lightweight f0 |
| Melodia | GPL Vamp plug-in | — | blocked | — |
| LAION-CLAP | CC0-1.0 code and checkpoints; HF mirror Apache-2.0 | [GH](https://github.com/LAION-AI/CLAP), [HF](https://huggingface.co/lukewys/laion_clap) | shippable | audio-text embeddings |
| MS-CLAP | MIT code / weights unresolved (HF 401) | — | blocked (unresolved) | — |
| MuQ | MIT code / CC-BY-NC-4.0 weights | — | blocked (weights) | — |
| MERT | Apache-2.0 code / CC-BY-NC-4.0 weights | — | blocked (weights) | — |
| OpenL3 | MIT code / CC-BY-4.0 weights | — | gated (attribution) | embeddings, dated |
| musicnn | ISC code / weights unstated (MSD terms) | — | blocked (weights) | — |
| YAMNet | Apache-2.0 [R] | — | shippable (not re-verified) | tagging |
| beat_this | MIT code and published weights | [GH](https://github.com/CPJKU/beat_this) | shippable | beat/downbeat (B4) |
| soxr | LGPL-2.1-or-later | — | blocked | pulled by beat_this; replace or isolate |
| ADTOF | CC-BY-NC-SA-4.0 | [LICENSE](https://raw.githubusercontent.com/MZehren/ADTOF/master/LICENSE) | blocked | — |
| ACE-Step v1 | Apache-2.0 / Apache-2.0 (v1.5 unverified) | [GH](https://github.com/ace-step/ACE-Step) | shippable | opt-in generation (B4) |
| DiffRhythm | Apache-2.0 code and DiT weights; VAE unstated; espeak-ng GPL-3.0 dep | [GH](https://github.com/ASLP-lab/DiffRhythm) | gated | alternate generation |
| espeak-ng | GPL-3.0 | — | blocked | must not be bundled |
| YuE | Apache-2.0 code and weights | — | shippable (too big for 16 GB) | — |
| MusicGen | CC-BY-NC-4.0 weights | — | blocked | — |
| MAGNeT | CC-BY-NC-4.0 weights | — | blocked | — |
| AudioLDM2 | CC-BY-NC-SA-4.0 weights | — | blocked | — |
| Tango2 | CC-BY-NC-SA-4.0 weights | — | blocked | — |
| Stable Audio Open Small | `stability-ai-community`, gated | — | gated (revenue terms) | — |
| Mustango | unverified; Tango-family assumption | — | blocked (assumed) | — |
| Freesound API | vendor ToS; free tier non-commercial, revocable | [ToS](https://freesound.org/docs/api/terms_of_use.html) | gated (commercial deal) | opt-in sample source only |
| chromaprint | LGPL-2.1 as a whole | [LICENSE](https://raw.githubusercontent.com/acoustid/chromaprint/master/LICENSE.md) | blocked | use audfprint instead |
| audfprint | MIT | — | shippable | local fingerprinting |
| NISQA | MIT code / CC-BY-NC-SA-4.0 weights, speech-only | [README](https://raw.githubusercontent.com/gabrielmittag/NISQA/master/README.md) | blocked | — |
| AudioBox-Aesthetics | CC-BY-4.0 code and weights | — | gated (attribution) | opt-in mix-quality research |
| SQUIM (torchaudio) | not re-verified this pass | — | gated (unread), speech-only | — |
| whisper-timestamped | AGPL-3.0 (plus GPL `dtw-python` dep) | — | blocked | do not use for timestamps |

### 5.5 Teaching, data and recorded dependencies

| Name | Licence | Primary source | Verdict | Where it would apply |
|---|---|---|---|---|
| music21 | BSD-3-Clause (bundled corpora need per-file checks) | — | shippable (library) | E8 theory utilities |
| partitura | Apache-2.0 | — | shippable | E8 score alignment |
| tonal | MIT (npm) | — | shippable | E8 theory primitives (TS) |
| VexFlow | MIT per LICENSE text | — | shippable | E8 notation rendering |
| audiate | Apache-2.0 (stale since 2021) | — | shippable (patterns only) | ear-training interaction ideas |
| birdears | AGPL-3.0 | — | blocked | — |
| nootka | GPL-3.0 | — | blocked | — |
| fsrs (PyPI) | MIT | — | shippable | E8 spaced repetition |
| py-fsrs | MIT | — | shippable | E8 reference |
| fsrs4anki | MIT | — | shippable | parameter-fitting reference |
| SuperMemo2 (Python) | MIT but archived 2024 | — | shippable licence; do not depend | dead code |
| mclemcrew/MixAssist (code) | MIT | [GH](https://github.com/mclemcrew/MixAssist) | shippable (reference) | E4 phrasing patterns |
| MixAssist Zenodo 15571750 / 15848443 | CC-BY-4.0 | [Zenodo](https://doi.org/10.5281/zenodo.15571750) | gated (attribution) | E4 style sheet source data |
| MixAssist HF datasets (`mclemcrew/MixAssist`, `MixParams`) | none declared | — | blocked | reading only, never shipped |
| MED Hub mirror (`sparrowreivun/Mix-Evaluation-Dataset-2.0`) | none declared | — | blocked | do not use |
| MED DAFx-17 six-song subset | CC BY 4.0 | — | gated (attribution) | E9 listening calibration |
| CoMix (~640 conversations) | unverifiable; dropped | — | blocked (do not cite) | — |
| librosa | ISC headline; pulls `soxr` (LGPL-2.1-or-later) | — | recorded (not re-checked); soxr question open | already in `THIRD_PARTY_LICENCES.md` |
| soxr | LGPL-2.1-or-later | — | blocked unless isolated or replaced | pulled by librosa and beat_this |
| onnxruntime | not re-checked this pass | — | recorded (not re-checked) | already in `apps/backend/requirements.txt` |

## 6. Recommendations mapped to KENN_PLAN.md item codes

These are proposals for the owner. None is an approval, and nothing here edits `KENN_PLAN.md`. Item codes refer to the plan's own definitions, read for this merge: **C2** remove measured wasted work; **C3** five-turn conversation qualification; **C5** reach the quality and timing targets (home of the reranker decision); **S4** compare alternative model sizes as separate experiments; **S6** qualify useful answers per inference cost; **L1** device capability coverage (incl. display-unit parity); **L2** retrieval and knowledge; **L3** qualify existing recipes; **L5** transport reliability across surfaces; **B1** listening usefulness; **B2** memory usability; **B3** MIDI creation; **B4** optional integrations (typed artifact providers, one at a time); **E1–E11** as defined at `KENN_PLAN.md` lines 2375–2450; **D4** demo answers and narrative.

Evidence tier: **V** = the underlying capability or licence was verified against a primary source in this pass; **V/I** = verified facts plus an inferred benefit; **I** = judgement from the lane. Effort as the lanes gave it: S under a day, M multi-day with evaluation, L needs its own plan slice.

| # | Recommendation (proposal) | Plan item(s) | Tier | Effort | Lane |
|---|---|---|---|---|---|
| 1 | Runtime A/B: Ollama 0.34.4 vs 0.40.4, same prompts, digest + runner recorded; capture `eval_count`, `prompt_eval_count`, cached tokens, TTFT | C2 | V | S | 2 |
| 2 | Qwen3.5-4B (thinking off) vs Qwen3-4B-2507 at pinned context, held-out comparison | C2, S4 | V/I | M | 2 |
| 3 | Prompt-cache alignment check — stable system prefix first, watch cached-token counts | C2 | V/I | S | 2 |
| 4 | q8_0 KV trial (`OLLAMA_KV_CACHE_TYPE`), one model, one context, quality spot-check | C2 | V/I | S | 2 |
| 5 | Speculative-decoding observation on 0.40.4 (does MLX fire for qwen3.5/gemma4?) — instrument only | C2 | I | S/M | 2 |
| 6 | FlashRank ONNX tiny reranker trial against the existing harness; expected weak, must be rejectable | C5 | V | S | 2 |
| 7 | bge-reranker-v2-m3 second, with the 250 MB C5 memory line explicitly revisited in the trial request | C5 | V | M | 2 |
| 8 | Qwen3-Reranker-0.6B third, if instruction-aware scoring matters | C5 | V | M | 2 |
| 9 | Embedding-swap measurement (Qwen3-Embedding-0.6B vs current embedder; quality per ms) | L2 | V/I | S/M | 2 |
| 10 | Evidence-labelling taxonomy in grade and proposal receipts (measured / heuristic / artistic) | E2, E4, D4 | V | S | 1 |
| 11 | `display_value` / `str_for_value` / `value_items` in the readback layer | L1 | V | S | 1 |
| 12 | Key project memory to Live Set identity (`Song.name` / `file_path`) | E7, B2 | V/I | S | 1 |
| 13 | Context economy for MCP exposure — small advertised core, discoverable long tail | C2, S6 | V/I | M | 1 |
| 14 | Field-notes document per bridge surface for silently-broken writes | L5 | V | S | 1 |
| 15 | Qualify the browser path (`application.browser`, `load_item`, `preview_item`) behind a feature handshake | L1, L3 | V/U | M | 1 |
| 16 | Watch the Extensions SDK for a `.ablx` companion (producer-pal gate + stable channel + SDK licence read) | none (watch) | V | M/L | 1 |
| 17 | Watch the extension-native MCP cluster for install-UX benchmark | none (watch) | V | S | 1 |
| 18 | `FakeLiveBridge`-style port of the Loophole test split for any future extension path | D2 support | V | M | 1 |
| 19 | Copy LivePilot's confidence gates — quick path vs full critic pass for ambiguous asks | C5 | V | M | 1 |
| 20 | whisper.cpp PTT baseline (`small`, `large-v3-turbo`), release-to-text latency and Ableton-vocabulary WER | B4 | V | S | 2, 3 |
| 21 | Parakeet TDT 0.6B v3 via parakeet-mlx as accuracy challenger (CC-BY-4.0 attribution line) | B4 | V | M | 2, 3 |
| 22 | Kokoro-82M spoken feedback for short confirmations, MPS fallback set; judge annoyance in a real session | B4 | V/I | S/M | 2 |
| 23 | Chatterbox voice trial only after the PerTh watermark decision is recorded | B4 | V/I | M | 2 |
| 24 | Wake word out of scope; if forced, train an openWakeWord model with KENN's own pipeline | B4 | V | M | 2 |
| 25 | Basic Pitch ONNX audio-to-MIDI on bounded instrument clips | B4, B3 | V | S | 3 |
| 26 | CLAP + audfprint local library index (dedupe, embeddings), framed as ranking aid | B4, E6 adjacent | V/I | M | 3 |
| 27 | MSST + KimberleyJSN + ZFTurbo separation trial, MUSDB18-HQ caveat in NOTICE.md, measure M3 memory and time | B4 | V | M/L | 3 |
| 28 | beat_this `small` beat/downbeat timeline, `soxr` replaced or isolated | B4 | V | S | 3 |
| 29 | ACE-Step v1 opt-in AudioGen trial (background render class; B4 opt-in + licence review first) | B4 | V | L | 3 |
| 30 | mlx-audio spike — one MIT dependency for STT + TTS | B4 groundwork | V | S | 2 |
| 31 | Carry the `source` tag from E2 into E3 levers and E4 explanations | E2, E3, E4 | V | S | 4 |
| 32 | Adopt fsrs (PyPI, MIT) as the E8 scheduler; fixed desired-retention first | E8 | V | S | 4 |
| 33 | Build the E4 style sheet from MixAssist dialogues (CC BY 4.0, attribution; Zenodo copies) | E4 | V | M | 4 |
| 34 | Author the E8 curriculum skeleton (measurement literacy, reference discipline, stage conventions) | E8, E11 | V | M | 4 |
| 35 | "Why this number" affordance on every displayed E2/E4 value, linked to the source table | E2, E4 (E3) | V | M | 4 |
| 36 | MED-based A/B calibration for E9 tolerances, six CC BY songs only | E9 | V | L | 4 |
| 37 | Theory modules (music21 / partitura / VexFlow) only if the E8 outline pulls them in | E8 | V | L | 4 |
| 38 | AudioBox-Aesthetics as opt-in research only, never shipped grading | E2/E9 research | V/I | M/L | 3 |

Notes on the mapping. Items 1–5 assume C2 stays the home for runtime and residency work; the lane's evidence base is release notes, not measurement. Item 13 also serves S6's cost accounting. Items 16–17 have no plan item; they are watch items with a decision gate, recorded here so they are not lost. Items 20–29 are all "one provider at a time" trials under B4's own rule. Item 38 lands in E2/E9 as research because CC-BY-4.0 is off the allow-list. Lane 03's assumed E1–E4 mapping (its four B4 probes) is replaced by the plan's actual definitions; the corrected mapping is shown above (audio-to-MIDI is B4/B3, PTT is B4, mix scoring is E2/E9).

## 7. Corrections and confirmations vs the 2026-10-02 and 2026-10-14 documents

What this pass changed, what it confirmed, and where the lane notes disagree with the shipping licence policy. Every correction below is the value this document uses; the superseded value is named so it can be retired from older docs.

### 7.1 Ableton lane

Changed:

- **"~73 open issues/PRs" on AbletonOSC** (14 Oct phrasing): the accurate split is **39 open issues + 34 open PRs** (2026-10-15). The stalls, the missing releases and the no-browser/no-rack/no-automation gaps are all confirmed.
- **"A community extension dev references Live 13 Beta"** could not be reproduced in any re-check. Treat as dead unless the original source is re-found. [U]
- **The "12.3 LOM dump" artefact** behind several 14 Oct claims was not located, but each claim was re-verified independently: grouped undo via ableton-js source plus Live's Push framework (not on the public LOM page), `str_for_value`/`display_value` via the DeviceParameter LOM, `Browser.load_item` via ableton-js's Browser.py (public LOM `/browser/` 404s), `duplicate_clip_to_arrangement` and take lanes via the Track LOM.
- **The comment-outs** (groove, `warp_markers`) that the 13 Oct research attributed to the bundled KENN copy are also present in **upstream master** — they are upstream's, with the recorded OSC error text.
- New this pass, not in the 14 Oct conclusions: the Extensions-SDK-native MCP cluster (loophole and peers), Protocol0's localhost-HTTP/OpenAPI extension contract, producer-pal's ADR-0007 and Live-12.4.3 field notes, Ableton-owned npm placeholders, ableton-js Browser/Chain namespaces, and `xiaolaa2/ableton-copilot-mcp` (93★, MIT).

Confirmed exactly: Live stable 12.4.6 / 12.4 dated 2026-05-05 / beta 12.4.15b7; Extensions as a public beta (announced 2026-06-02), Suite-only, no observers/transport/real-time; SDK free but third-party devs may charge (FAQ, verbatim); no Ableton store; SDK not on public npm; AbletonOSC MIT; ableton-js MIT, npm 5.0.4 (2026-10-12); ahujasid 3,190★ MIT; producer-pal GPL-3.0-or-later (LICENSE file); LivePilot BSL-1.1 with change date 2030-04-13.

### 7.2 Brain and voice lane

Changed:

- **"All three shortlisted rerankers are clean" is wrong.** Every Jina reranker from v2 onward (including `jina-reranker-v3.5`, 2026-07) and `jina-embeddings-v3` are CC-BY-NC-4.0. The clean shortlist is bge-reranker-v2-m3, Qwen3-Reranker-0.6B and FlashRank.
- **Qwen3.5 small-model dates**: HF `createdAt` is **26–28 Feb 2026**, not "2 Mar 2026".
- **openWakeWord**: the project is not simply "Apache-2.0" — code is Apache-2.0 but the shipped pre-trained models are CC-BY-NC-SA-4.0. Earlier shorthand without the qualifier is incomplete for shipping.
- **The Ollama engine swap** (MLX default on Apple Silicon since v0.40.0, 2026-09-25) invalidates latency baselines that pinned only the Ollama version or model digest. Runner identity must be recorded from now on.

Confirmed as stated previously: Gemma 4 is Apache-2.0 across all five sizes; bge-reranker-v2-m3 is Apache-2.0 (secondary "MIT" claims are wrong); Qwen3.6/Qwen3.8 never shipped a small model; Ollama stable is v0.40.4 with v0.40.5-rc0 as a GitHub prerelease.

### 7.3 Audio understanding lane

Changed:

- **LAION-CLAP licence phrasing corrected**: code CC0-1.0 (repo and PyPI) and the primary checkpoints (`lukewys/laion_clap`) are **cc0-1.0**; apache-2.0 applies only to the HF-transformers mirror `laion/clap-htsat-unfused`. Both are clean; the earlier "apache-2.0 weights" shorthand was the mirror, not the host.
- **ZFTurbo's MIT statement narrowed**: it covers **two specific checkpoints** (53-stem MVSep Mega; `model_bs_roformer_ep_17_sdr_9.6568`), not "his checkpoints" as a class; `docs/pretrained_models.md` has no licence column and the author disclaims the rest.
- **Tango2 is CC-BY-NC-SA-4.0**, not ND (previous note).
- **MS-CLAP weights**: the earlier "ms-pl" claim could not be reproduced — `microsoft/clap-ms-2023` returns HTTP 401. Status is unresolved, not known.
- **Basic Pitch**: exact ONNX size is **230,444 bytes**; no separate sentence grants a weights licence (repo-level Apache-2.0 expected to cover, flagged for confirmation).
- **Freesound**: strengthened — the API licence is "temporary and may be withdrawn by Freesound at any time" and keys "may be revoked".
- **16 GB timings**: one new first-party anchor — ACE-Step M2 Max 26.43 s per minute of audio at 27 steps. Everything else still unmeasured.
- **Demucs**: the 14 Oct doc said "no separate licence statement found"; this pass found the author's direct statement (issue #327, 2022-05-23) that the weights are **not** MIT and are for scientific purposes only. Stronger than "not found".

Confirmed: whisper large-v3-turbo MIT / v3 Apache-2.0; the whisper-timestamped (AGPL), NISQA (NC weights + speech-only), ADTOF (NC-SA) and chromaprint (LGPL as a whole) traps; MAEB's CLAP 8–14% retrieval figure and the ACL 2026 caption critique (arXiv IDs verified); ACE-Step and DiffRhythm Apache-2.0 code and weights.

### 7.4 Teaching lane

Changed:

- **MixAssist has two Zenodo records, not one**: 15571750 (cited by the paper; ~3.84 GB) and 15848443 (cited by the model card; ~2.46 GB). Both cc-by-4.0. The earlier notes recorded only 15848443.
- **fsrs 6.3.2** was uploaded 2026-08-09, not "fresh 14 Oct".
- **"OpenEar = MIT" and "fet/pure-ear = MIT"** could not be reproduced in any re-check and are dropped.
- **VexFlow** star count corrected from 247 to **4,397**; the MIT conclusion survives from the raw LICENSE text (GitHub API reports NOASSERTION).
- **sonible** "reference zone" was not found in the live copy; replaced with "custom reference profiles".
- **CoMix (~640 conversations)** could not be located in any re-check; dropped as unverifiable.
- **dawcraft**: "no licence" was inaccurate — a licence file is present but unrecognised (NOASSERTION). Accurate wording: "licence file present, not recognised — treat as unclear terms".
- **LivePilot and phantom licences** were re-verified from raw LICENSE files (BSL-1.1 / AGPL-3.0); the GitHub API reports NOASSERTION for both, so API-only checks would have misreported them.
- Cadence warning: five tiny Ableton-agent repos appeared in about one day around 14–15 Oct. Any comparable-products table older than a week is candidate staleness; re-check licence and last push before citing.

Confirmed: producer-pal at 329★ (328 → 329); MED on HuggingFace with no licence declared and only the DAFx-17 six-song subset citable; the mid-size product quirk set (RoEx, Neutron, sonible, Output) at the pages cited.

### 7.5 Cross-cutting reconciliation with the shipping licence policy

Where the lane notes and `THIRD_PARTY_LICENCES.md` disagree, the policy wins and the discrepancy is flagged here:

1. **CC-BY-4.0 is gated, not shippable.** Lanes 2 and 3 describe CC-BY-4.0 items as "off-list (attribution)" or "clean-ish". The policy allow-list is MIT/BSD/ISC/Apache-2.0/Unlicense plus MPL-2.0 for test-only tooling, so every CC-BY-4.0 item in section 5 (Parakeet weights, OpenL3 weights, AudioBox-Aesthetics, MixAssist/MED data) is marked **gated** and needs an owner decision plus an attribution line before shipping.
2. **soxr is LGPL and the recorded dependency table does not say so.** `THIRD_PARTY_LICENCES.md` records librosa under its ISC headline licence. Lane 03 verified `soxr` — a hard dependency of librosa and of beat_this — is **LGPL-2.1-or-later**, which the policy excludes. The 14 Oct engineering-candidates doc also flagged this and left "whether KENN packaging bundles soxr" unchecked. Resolve that check before any work that depends on librosa or beat_this proceeds.
3. **The notes' verdict shorthand otherwise matches the policy**: MIT/BSD/ISC/Apache-2.0 clean, MPL-2.0 test-only, GPL/AGPL/LGPL/BSL/PolyForm/non-commercial/unclear blocked. No other conflicts were found.
4. **Lane 3's "M3 16 GB fit: Yes" column is inference**, not measurement — it is a model-size judgement from blob sizes and geometry. Section 3.8's caveats govern.

## 8. Open questions / review queue for Jack

Decisions only the owner can make, items that could not be verified, and measurements that require the M3/16 GB machine. Nothing here is approved work.

### 8.1 Owner decisions

1. **Extensions SDK licence.** Read the licence from the SDK zip (Centercode-gated) and decide whether a KENN `.ablx` is worth maintaining while it remains beta-channel, Suite-only, and short of transport, real-time audio, browser and stable identity.
2. **Max for Live terms.** Only if a real-time audio or MIDI path is ever wanted; the Max/MSP embedding and redistribution terms were not verified in this pass.
3. **The C5 reranker memory line.** Hold the written ≤250 MB budget (FlashRank only) or revisit it for bge-reranker-v2-m3 / Qwen3-Reranker-0.6B, quote the 0.57–0.6 GB int8 arithmetic in the decision.
4. **PerTh watermark** (Chatterbox). Keep it on, strip it, or do not ship Chatterbox — decide before any voice trial, not after.
5. **CC-BY-4.0 allow-list question.** Parakeet TTS weights, OpenL3, AudioBox-Aesthetics and the MixAssist/MED data are attribution-licensed, which is off the current allow-list. Decide: allow with an attribution line, or keep the list strict and skip them.
6. **Freesound.** Negotiate commercial terms only if online sample search is a product goal; otherwise stay local-library-only.
7. **Wake word.** Confirm push-to-talk stays the only voice-input mode for the planning horizon (it avoids both the CC-BY-NC-SA model problem and an always-on mic story).
8. **Embedding swap.** Approve or defer an index-rebuild measurement (Qwen3-Embedding-0.6B or EmbeddingGemma-2 against the current embedder).
9. **soxr packaging check.** Establish what the shipped tree actually bundles. Lane 03 verified soxr is LGPL-2.1-or-later; if it ships through librosa, plan the replacement or isolation before more librosa-dependent work. (beat_this has the same pull.)
10. **E8 curriculum authorship.** No open mixing curriculum exists to import; confirm in-house authoring with E11 as the sourcing path.

### 8.2 Unverifiable or unreproducible — do not repeat as fact

- The "community extension dev references Live 13 Beta" claim (dead unless the original source is re-found). [U]
- Existence or nature of Live "12.4.4". [U]
- "Ableton has said today's permission model will harden into a stricter sandbox" (producer-pal's report; statement not located). [U]
- LivePilot's "474 tools / 57 domains" (vendor-stated). [U]
- Unread licence texts: Extensions SDK, Max for Live, Porcupine commercial terms, microWakeWord models, XGrammar, transcribe.cpp. [U]
- MUSDB18-HQ dataset terms (chains to every MUSDB-trained checkpoint); Basic Pitch's separate weights grant (one-line confirmation advised); bge-reranker-v2-m3's ~568M parameter count (not read from the card). [U]
- MS-CLAP weights (HF 401), jarredou/BS-RoFormer-SW (401), `lucidrains/mel-band-roformer` (404), `kuielab/mdx23c` (404), Mustango (not checked). [U]
- ACE-Step v1.5 licence; DiffRhythm VAE and espeak-ng resolution; Moonshine's full model matrix; faster-whisper's macOS status (CPU-only assumed); Orpheus repo identity; Granite 4.2 quality; Chatterbox-Nano real-world quality. [U]
- Aggregator-sourced only: llama.cpp RANK-pooling batch splitting (b11222), the JSON-schema refactor (b10947), and parts of the Ollama MLX speculative-decoding behaviour. [U]
- EBU R128 PDF values (used Tech 3343 instead); AES77-2023 (paywalled; cite the title only); PardonMix full text (abstract only); CoMix (dropped). [U]
- Lane 1 methodology note: the session's websearch returned no results that day; discovery used curl to DuckDuckGo plus direct fetches and APIs. A very recent news item could have been missed. [U]

### 8.3 Measurements that need the M3 with 16 GB, on mains power (ranked)

1. **Ollama 0.34.4 vs 0.40.4 A/B**, same prompts, digest and runner recorded, `eval_count` / `prompt_eval_count` / cached tokens / TTFT per call. The single most important measurement in this document.
2. **Qwen3.5-4B (thinking off) vs Qwen3-4B-2507** alongside Live: peak memory, memory pressure, p50/p95 first-visible and complete answers, token cap hits.
3. **q8_0 KV trial**: quality spot-check on KENN's answer set plus memory delta.
4. **Speculative decoding on 0.40.4**: does it fire for qwen3.5/gemma4; acceptance rate.
5. **Reranker latency and memory**: FlashRank p95 ≤150 ms first; bge-reranker only if the budget moves.
6. **Embedding swap**: retrieval quality per ms of query latency; index size.
7. **whisper.cpp PTT**: release-to-text latency and WER on Ableton vocabulary; large-v3-turbo memory beside the chat model.
8. **Kokoro first-audio latency**; Chatterbox if the watermark decision goes ahead.
9. **Separation (MSST stack)**: wall time and peak memory per 3–4 min track; an artefact confidence gate.
10. **beat_this with soxr replaced**; beat/downbeat latency.
11. **ACE-Step / DiffRhythm generation time and memory** on M3 (M2 Max is the closest published anchor, and it is not this machine).
12. **Schema adherence rates** for Qwen3.5-4B and Gemma 4 E4B under Ollama/llama.cpp with the planner schema.
13. **CLAP retrieval on a real user library** (all published evidence is benchmark datasets).
14. **Whole-stack coexistence**: chat + embedding + STT resident with Live open, measured against the plan's 15 s / 70% acceptance gate and the S6 cost accounting.

Re-verify cadence: the Ableton extension ecosystem and the Ollama/llama.cpp line both move weekly (five tiny Ableton-agent repos appeared in about one day around 14–15 Oct; Ollama shipped 0.40.0 → 0.40.4 in eighteen days). Licence and push dates in section 5 expire fast; re-check before citing or acting on them. This document describes the state on 2026-10-15.
