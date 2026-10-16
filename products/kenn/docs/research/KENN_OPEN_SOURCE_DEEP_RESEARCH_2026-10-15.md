# KENN open-source deep research — synthesis, 15 October 2026

**Provenance.** Synthesis of the six-lane open-source capability pass run on 15 October 2026. Canonical inputs: the six lane notes in `kenn-landscape-notes-2026-10-15/` (`01-ableton-integration.md`, `02-local-brain-voice.md`, `03-audio-understanding.md`, `04-teaching-patterns.md`, `05-mix-analysis-and-grading.md`, `06-conversation-agent-architecture.md`), each re-verified against primary sources on 15 Oct; lanes 01 and 04 were finished in place after the ~12:28 session-runtime loss and both lane 01 and lane 04 carry takeover-review sections. This document re-read those notes; it ran no new web research and made no measurements. No installs, no source edits, no Live writes. After oracle review, the §8 plan edits were applied to `KENN_PLAN.md` additive-only and quote-anchored (see §8 status).

**Supersedes.** Where this document conflicts with `KENN_OPEN_SOURCE_CAPABILITY_LANDSCAPE_2026-10-15.md` (785 lines), this document wins. That landscape doc predates the lane takeover reviews; the corrections it needs are consolidated in §4.

**Markers.** `[V]` verified against the cited URL/API on 15 Oct 2026; `[R]` carried from a previous run's log, not re-fetched; `[I]` inferred (judgement or arithmetic, not measured); `[?]` unverified / not reproducible. The spec's `[U]` marker was superseded by `[?]` in the lanes; see §9.

**Status.** Research only. Every candidate below is a proposal for owner approval. Nothing is an adoption decision and no dependency is added; the §8 plan edits were applied additively after oracle review (§8 status). Hard constraints assumed throughout: Apple M3 16 GB with Live open; local-first; Qwen3 4B via Ollama today (model choice open, memory constraint fixed); Python owns dialogue/retrieval/policy, all DSP is C++ (nanobind); AbletonOSC is the sole Live write authority with typed policy and Apply/Undo; closed-source commercial product, so code **and** weights need permissive licences — MIT/BSD/ISC/Apache-2.0 clean, MPL-2.0 test-only, anything NC/ND/RAIL/gated/research-only/unstated is off the table or gated.

**Verdict vocabulary.** **ADOPT** = shippable inside the current allow-list (still subject to the standing reuse check and owner approval); **WATCH** = gated on an owner decision, an unread licence, or an allow-list question; **AVOID** = blocked (copyleft, non-commercial, unstated). Effort S/M/L: S < 2 days, M ≤ 1 week, L > 1 week.

---

## 1. Executive summary

1. **Nothing in this pass is approved.** The six lanes produced candidates, licence readings and first steps; every adoption still runs through the standing open-source reuse check (`KENN_PLAN.md` L59–77) and the owner.
2. **The meter, not the grade logic, is the weakest qualified link.** The 15 Oct research pinned the official conformance material the plan calls "download URL unverified": EBU Tech 3341-2023 names its 48 kHz signal set at `http://tech.ebu.ch/loudness` (page returned 403 during the pass, file terms unstated), and ITU Report BS.2217-2 is a free 29-file expected-value table at ±0.1 LKFS (lane 05 §1.2).
3. **Every latency number KENN owns is stale.** Ollama v0.40.0 (2026-09-25) made the MLX runner the default on Apple Silicon for supported models; the recorded baseline (0.34.4, llama.cpp b11081) no longer describes a fresh install. Pin the runner, not only the digest; re-measure before quoting (lane 02 H5, KQ3).
4. **Speculative decoding was reachable longer than believed** — the MLX runner has automatic MTP speculation since v0.32.6 (2026-08-04), memory growth fixed in v0.34.2; v0.40.0's change was routing. The 13 Oct parked decision stands; runtime changes compare separately from model changes (lane 02 KQ3; `KENN_PLAN.md` L1176–1180).
5. **The cleanest adopts are small and boring:** Basic Pitch ONNX for bounded audio-to-MIDI (Apache-2.0, 230,444-byte file), whisper.cpp + large-v3-turbo weights for push-to-talk (MIT), LAION-CLAP for audio-text embeddings (CC0 both sides), beat_this small for beats (MIT, with a soxr call to replace or isolate), audfprint for dedupe (MIT), fsrs for curriculum scheduling (MIT), and the two named ZFTurbo checkpoints for separation (MIT per author statements, with a documented MUSDB chain-of-title caveat).
6. **The avoid list is unchanged at its core:** Demucs v4 weights ("not covered by the MIT license … only for scientific purposes", adefossez 2022-05-23), matchering (GPL-3.0 as a whole), openWakeWord's pretrained models (CC-BY-NC-SA-4.0), chromaprint (LGPL-2.1 as a whole), whisper-timestamped (AGPL), NISQA weights (NC + speech-only), the MusicGen/MAGNeT/AudioLDM2/Tango2 family (NC weights), Freesound's free tier (non-commercial, revocable), and MUSDB18/-HQ (`other-nc` verbatim).
7. **Three findings change previous beliefs.** (a) ACE-Step v1.5's licence resolved to MIT (lane 03 KQ5). (b) The claim "no product ships a 0–100 grade with reasoning" is falsified — Rate My Song AI and TrackScore.AI ship exactly that, TrackScore with conversation grounded in the user's measurement history (lane 04 §5). (c) MS-CLAP's weights resolved to MS-PL, off-list → WATCH, not blocked (lane 03 KQ3).
8. **The differentiator narrows to in-session, source-labelled, teaching-first grading.** No competitor found grades a live DAW session, publishes a standard-vs-house-rule taxonomy per number, or ships a curriculum; that is where E2–E4 and E8 now sit (lane 04 §5 net).
9. **The C5 reranker budget does not fit the quality favourites.** FlashRank (Apache-2.0, ~4 MB tiny ONNX) is the only shortlisted model inside 150 ms p95 / 250 MB as written; bge-reranker-v2-m3 (~0.56 GB int8 arithmetic) and Qwen3-Reranker-0.6B (~0.6 GB) likely bust the cap — owner call, not an engineering answer (lane 02 KQ4, C5 shortlist).
10. **The additive retrieval technique is query rewriting, not reranking.** Hybrid BM25+dense RRF already shipped with a measured receipt (24 Sep 2026: recall@4 0.966→0.983; 0.616→0.736 on device-purpose questions). Pre-retrieval rewriting (Rewrite-Retrieve-Read, arXiv 2305.14283) is the untried delta (lane 06 KQ5).
11. **Promptfoo is the best-fit eval harness for a 16 GB machine.** It is the only one whose docs name the model-residency failure mode and give `keep_alive: 0` to fix it; DeepEval is the pytest-native second, Inspect AI the audit-grade third, Ragas is dormant and out (lane 06 KQ1).
12. **The Live surface is broader than the public LOM.** Browser load/preview, rack-chain traversal, take lanes and grouped undo exist in the private Remote Script API; qualify them through KENN's vendored bridge as a capability probe, never by adding a second bridge. Warp-marker writes and warped-looped arrangement resizes are verified broken — do not promise them (lane 01 Q5).
13. **The Extensions SDK remains a gate, not a path.** Beta-only, Suite-only, no transport/observers, and the SDK licence text is still unreadable publicly (Centercode-gated; a downstream project calls the package "non-redistributable"). Owner/legal must read the licence inside the SDK zip before any `.ablx` decision (lane 01 Q2).
14. **No M3 measurements were made in any lane.** Every fit/cost claim is `[I]` from vendor numbers; the only first-party Mac figure found is ACE-Step's M2 Max 26.43 s/min of audio at 27 steps `[V]`. The standing rule holds: library claims do not qualify KENN.
15. **This pass drafted 13 additive KENN_PLAN.md edits (E-01…E-13) instead of applying them** — the spec asked for actual edits; that deviation is flagged in §9 and the drafts are ready for oracle review in §8.

---

## 2. Consolidated capability map

Per-subsystem map below: capability → best available options → licence (code / weights) → M3 16 GB fit → effort → verdict → KENN_PLAN mapping. Licence cells give the verified value; `[?]` where public text is missing (unstated = unusable until stated).

### 2.1 Ableton Live integration and control (lane 01)

| Capability | Candidate | Licence (code / weights) | Fit / state | Effort | Verdict |
|---|---|---|---|---|---|
| Live control transport (incumbent) | AbletonOSC, vendored pin `88b08476…` | MIT / n/a | 827★, last push 2025-11-19, zero releases; KENN owns fixes | — | **KEEP** (sole write authority) |
| Breadth KENN lacks: browser, chains, take lanes, grouped undo | ableton-js (Remote Script) | MIT / n/a | 532★, npm 5.0.4 (2026-10-12); exposes Browser/Chain/TakeLane/Groove/Envelope namespaces | M | **Qualify via vendored bridge**; do not ship a second runtime |
| First-party extension surface | Extensions SDK 12.4.15b7 | **[?]** (no public text; downstream: "non-redistributable") / n/a | Beta-only, Live 12 Suite only, no transport/observers/real-time; `withinTransaction` grouped undo; pre-FX render | M–L | **WATCH** (gate: licence read; stable channel; producer-pal triggers) |
| Real-time observation | Max for Live | **[?]** (terms unread) / n/a | The only real-time audio/MIDI path; LivePilot ships an M4L Analyzer | M | **WATCH** (owner/legal read) |
| MCP-in-extension pattern | OthmanAdi/loophole | MIT / n/a | 22★; SDK-free core + `FakeLiveBridge`; "NOT_RUN" honesty gates; `.ablx` packaging discipline | S (monitor) | **Pattern** |
| Field notes on broken writes | producer-pal (`dev/live-api/arrangement-operations.md`) | GPL-3.0-or-later (repo) / n/a | Verified against Live 12.4.3; documents silently no-oping writes | S | **Ideas only** (copyleft) |
| Context economy + evidence labelling + set-scoped memory | LivePilot (dreamrec) | BSL-1.1 (not open source; → MIT 2030-04-13) / n/a | 28 entry points over 474 tools; measured/heuristic/artistic labels; memory follows the Live set | S–M | **Patterns only** (licence) |
| Localhost HTTP + OpenAPI between agent and extension | Protocol0 extension-sdk | MIT / n/a | npm 0.1.2; `POST localhost:9010 → /openapi.json` contract | S (pattern) | **Pattern** |
| Competing bridges | ahujasid/ableton-mcp (MIT, 3,190★, telemetry disable-able); xiaolaa2/ableton-copilot-mcp (MIT, 93★) | MIT / n/a | Field's biggest MCP; not dependency candidates | — | **Reference** |
| Measurement-first coaching precedent | happysasha18/track-coach | MIT / **Demucs weights caveat** | 1★; closest published artefact to KENN's framing — but the Demucs dependency fails licence | — | **Idea; do not vendor models** |

Ranked next adoption steps (all lane-01): evidence-labelling taxonomy into grade/proposal receipts (S); `display_value`/`str_for_value`/`value_items` in the readback layer (S); project memory keyed to Live Set identity (`Song.name`/`file_path`) (S); MCP context economy — small advertised core, long tail behind discovery (M); a per-bridge quirks field-notes doc seeded with groove/warp comment-outs and issue #212 (S); browser capability probe through the vendored handler with an explicit refusal path (M); `.ablx` watch (M now, L later). Plan mapping: L1, L1a, L2, L5, §2 route audit, B4.

### 2.2 Local model and runtime (lane 02)

| Candidate | Size (Ollama manifest total) | Licence (code / weights) | Fit for 16 GB with Live | Effort | Verdict |
|---|---|---|---|---|---|
| **Qwen3.5-4B** | 3.10 GiB (2.47 GiB layer + 0.63 GiB projector) | Apache-2.0 / Apache-2.0 | Best fit among new entrants; direct successor to incumbent; thinking off via `enable_thinking:false` | M | **A/B candidate** vs Qwen3-4B-2507, same harness, pinned context |
| Gemma 4 E4B-it | 6.13 GiB (8B total incl. embeddings) | Apache-2.0 / Apache-2.0 | Tight; native function calling; audio input ≤30 s clips | M | WATCH (memory) |
| Qwen3.5-9B | 6.10 GiB | Apache-2.0 / Apache-2.0 | Tight; materially better tool scores (BFCL-V4 66.1 vs 50.3) | M | WATCH (memory) |
| Granite 4.2 3B (MLX q4) | MLX conversion | Apache-2.0 / Apache-2.0 | Fits; no quality evidence gathered | M | WATCH |
| Qwen3-4B-2507 (incumbent) | measured baseline | Apache-2.0 / Apache-2.0 | Known good on 0.34.4 | — | **KEEP until the A/B** |

Runtime facts: Ollama stable **v0.40.4** (2026-10-12); MLX runner default on Apple Silicon since v0.40.0 for supported models (names `qwen3.5`, `gemma4`); v0.40.2 can silently re-download a tag under a different runner package (`ggml`→`llamacpp`) — digest check plus runner check is the honest verification. llama.cpp moved to semver: v0.6.0 (2026-10-05) adds a Metal tensor-API flash-attention kernel for F16 KV and MTP speculation for Qwen4Exp; nightlies land several times a day (b11645 on 15 Oct). KV: `OLLAMA_KV_CACHE_TYPE q8_0` is the memory play at 16 GB; Ollama's default context below 24 GiB is 4k tokens. Techniques on the table: prompt-cache alignment (worked at 0.34.4, 666/1434 cached), q8_0 KV trial, instrument-only spec-decode observation on 0.40.4. Plan mapping: C1, C2 (L1286–1292), parked MLX decision (L1176–1180).

### 2.3 Retrieval: embeddings, rerankers, fusion (lanes 02/06)

| Candidate | Licence (code / weights) | C5 budget note (≤150 ms p95, ≤250 MB) | Effort | Verdict |
|---|---|---|---|---|
| Qwen3-Embedding-0.6B | Apache-2.0 / Apache-2.0 | 0.60 GiB blob; 1024-d, 32k ctx; swap invalidates the index | S–M | **Measure-first swap candidate** |
| EmbeddingGemma-2 | Apache-2.0 / Apache-2.0 | 1.20 GiB pull total (0.91 GiB projector); multimodal incl. audio; 768-d unified space | M | WATCH (strategic if audio vectors matter) |
| bge-m3 | MIT / MIT | 1.08 GiB; dense+sparse hybrid | M | Fallback |
| **FlashRank** | Apache-2.0 / Apache-2.0 | tiny model ~4 MB — **only one inside the written budget**; weakest quality | S | **C5 trial #1** (off by default, 13 Oct gate) |
| bge-reranker-v2-m3 | Apache-2.0 / Apache-2.0 | ~560M params → ~0.56 GB int8 (arithmetic) — likely busts 250 MB | M | Trial #2 with the budget line revisited |
| Qwen3-Reranker-0.6B | Apache-2.0 / Apache-2.0 | ~0.6 GB int8 — same problem | M | Trial #3 |
| Jina rerankers/embeddings v2+ | CC-BY-NC-4.0 / same | — | — | **AVOID** |
| Hybrid RRF (shipped) | in-repo | measured 24 Sep 2026: 0.966→0.983 overall; 0.616→0.736 device-purpose | — | **KEEP — nothing to add** |
| Query rewriting (pre-retrieval) | technique (arXiv 2305.14283) | one extra local call per follow-up | S/M | **TRIAL** (C3/L2), routing unchanged |

Note: every secondary claim that bge-reranker-v2-m3 is MIT is wrong — HF frontmatter is `license: apache-2.0`; the model remains clean, the citation does not.

### 2.4 Voice: STT, TTS, wake word (lane 02)

| Candidate | Licence (code / weights) | Fit / notes | Effort | Verdict |
|---|---|---|---|---|
| **whisper.cpp** + large-v3-turbo | MIT / MIT (turbo; v3 Apache-2.0) | PTT baseline per B4; Metal first-class; tiny 273 MB → large ~3.9 GB memory table; `stream` mode exists but PTT wants record-held → batch on release | S | **ADOPT candidate** (B4) |
| faster-whisper | MIT / MIT | **macOS is CPU-only** (CTranslate2 GPU = CUDA/ROCm only) — drops out of a Metal-first comparison | — | Reference |
| Parakeet TDT 0.6B v3 | Apache-2.0 port / **CC-BY-4.0 weights** | 25 European languages; needs attribution line; off-list | M | WATCH (allow-list decision) |
| Moonshine | MIT / MIT by default | Streaming-first; micro 1 MB models; legacy non-English carve-out under Community Licence — read LICENSE before non-English use | M | WATCH (details) |
| VibeVoice-ASR-Streaming 1.5B/7B | MIT / MIT | Speaker-aware streaming; new, unmeasured | M | WATCH |
| Voxtral Mini 4B Realtime | Apache-2.0 / Apache-2.0 | <500 ms delay; at 4B it competes with the chat model for RAM | M | WATCH (memory) |
| **Kokoro-82M** | Apache-2.0 / Apache-2.0 | TTS default for short spoken confirmations; MPS fallback env noted | S–M | **ADOPT candidate** (B4) |
| Chatterbox Turbo/Nano/V3 | MIT / MIT | 350M/110M/500M; every output carries Resemble's **PerTh watermark** — product decision before technical one | M | WATCH (PerTh + unproven) |
| F5-TTS | MIT code / **CC-BY-NC-4.0 weights** | — | — | **AVOID** |
| Piper line | archived MIT → successor GPL-3.0 | — | — | **AVOID** |
| openWakeWord | Apache-2.0 code / **pretrained models CC-BY-NC-SA-4.0** | Clean route = KENN-trained model via the Apache pipeline (<1 h, synthetic data) | M | Split — see §5 |
| microWakeWord | Apache-2.0 / **Apache-2.0 incl. shipped `.tflite` weights** | The only fully clean pretrained wake-word package found | M | WATCH (phrase availability) |
| Porcupine | Apache-2.0 repo / runtime needs AccessKey | Language terms "case-by-case"; hosted dependency, not local-first | M | WATCH (terms review) |

Voice-cloning scope: every clean candidate supports a reference clip; that is a product question (consent/storage) the plan should name before a trial — default recommendation: no (D-27).

### 2.5 Audio understanding: separation, transcription, embeddings, rhythm (lane 03)

| Candidate | Licence (code / weights) | Verified size | Effort | Verdict |
|---|---|---|---|---|
| **Basic Pitch** | Apache-2.0 / Apache-2.0 (repo-distributed; no separate grant sentence `[I]`) | `nmp.onnx` 230,444 B; TFLite/CoreML/pb exports in tree | S | **ADOPT candidate** (B4 names it) |
| **LAION-CLAP** | CC0-1.0 / CC0-1.0 (HF mirror Apache-2.0) | checkpoints 1.86–2.35 GB each | M | **ADOPT candidate** (ranking aid; no accuracy promises) |
| MSST + KimberleyJSN mel-band vocals | MIT / **MIT** (HF tag; card mod 2026-04-22) | `MelBandRoformer.ckpt` 913,106,900 B; vocals SDR 10.98 | M | **ADOPT (caveat)** — MUSDB18-HQ chain-of-title |
| ZFTurbo BS-RoFormer 4-stem | MIT / **MIT** (#254; author: "verify on your end") | `model_bs_roformer_ep_17_sdr_9.6568.ckpt` | M | **ADOPT (caveat)** — quote author statement in NOTICE |
| beat_this | MIT / **MIT** (explicit) | small 8.1 MB; final 78 MB | S | **ADOPT (condition)** — replace/isolate inference-time `soxr` call (`inference.py` L274–275, LGPL-2.1-or-later) |
| torchcrepe | MIT / MIT (bundled, inferred) | small | S | ADOPT |
| swift-f0 | MIT / bundled (detail unverified) | small | S | WATCH (re-check weight file) |
| audfprint | MIT / n/a | small (frozen 2019) | S | ADOPT (dedupe; chromaprint substitute) |
| MS-CLAP | MIT / **MS-PL** (`microsoft/msclap`) | 2.33 GB/690 MB/1.71 GB | M | WATCH (off-list licence) |
| OpenL3 | MIT / CC-BY-4.0 (explicit) | small; TF2 dep | M | WATCH (allow-list) |
| AudioBox-Aesthetics | CC-BY-4.0 (majority; unilm MIT) / CC-BY-4.0 | CE/CU/PC/PQ verified | M | WATCH (allow-list; research aid only) |
| M2D-CLAP (MAEB T2A leader 47.9%) | unchecked `[?]` | — | — | WATCH (licence unread) |
| MT3 | Apache-2.0 (`magenta/mt3`) / **unstated** | T5-class | — | **AVOID** |
| piano_transcription_inference | no LICENSE file (README claims Apache 2.0) / Zenodo terms unstated | — | — | **AVOID** |
| RMVPE | Apache-2.0 / **unstated** | small | — | **AVOID** (weights) |
| musicnn | ISC / unstated + MSD terms | small | — | **AVOID** |
| Demucs v4 | MIT / **not covered** | ~300 MB class | — | **AVOID** |
| Open-Unmix | MIT / `umxl` NC-SA; `umxhq` unstated | — | — | **AVOID** (weights) |
| Spleeter | MIT / unstated (code-only statement) | — | — | **AVOID** (weights) |
| BS PolarFormer (vocals table top, SDR 11.00); MDX23C; viperx/aufr33/TRvlvr/jarredou/anvuew/Sucial families | n/a / **no statement anywhere** | — | — | **AVOID** (unstated) |
| ADTOF | CC-BY-NC-SA-4.0 | small | — | **AVOID** |
| MuQ / MERT | MIT / Apache-2.0 code but **CC-BY-NC-4.0 weights** | — | — | **AVOID** (weights) |
| chromaprint | MIT parts / n/a | tiny | — | **AVOID** (LGPL-2.1 as a whole) |
| Freesound API | vendor ToS / per-sound CC (filter NC) | — | — | WATCH (commercial deal only) |

Retrieval-quality caveat: the earlier "CLAP 8–14%" figures could not be re-located → `[?]`, not quotable. What survived verification: MAEB's best clustering result 22.7% V-measure (clap-htsat-fused) and M2D-CLAP's 47.9% text-to-audio. A 2026 DAFx paper (arXiv 2607.03806) shows CLAP embeddings carry low-level mix attributes (LUFS/RT60/spectral centroid) — evidence for feature probes, not search promises. Plan mapping: B3, B4, E2/E9 research rows.

### 2.6 Music generation (lane 03) — opt-in only per B4

| Candidate | Licence (code / weights) | Evidence | Effort | Verdict |
|---|---|---|---|---|
| ACE-Step v1 | Apache-2.0 / Apache-2.0 | M2 Max: RTF 2.27 @27 steps = **26.43 s per minute of audio** `[V]`; macOS needs `--bf16 false` | L | ADOPT (opt-in) |
| ACE-Step v1.5 | **MIT / MIT** (resolved this pass) | Card asserts licensed training data (vendor claim) | L | ADOPT (opt-in; measure on M3 first) |
| DiffRhythm | Apache-2.0 / Apache-2.0 (DiT weights quote) | HF checkpoints untagged; 1_2B 401s; VAE unstated; espeak-ng GPL-3.0 program to isolate | L | WATCH (unresolved parts) |
| YuE | Apache-2.0 / Apache-2.0 (s1) | 7B+1B — no 16 GB fit | L | Licence-clean, unfit |
| MusicGen / MAGNeT / AudioLDM2 / Tango2 | permissive family / **CC-BY-NC(-SA)-4.0** | Tango2 corrected to NC-SA (prior note said ND) | — | **AVOID** |
| Stable Audio Open (Small) | community licence / gated `stability-ai-community` + revenue terms | — | — | WATCH (gated) |
| Mustango | apache-2.0 tag only `[?]` | Tango lineage | — | AVOID (default) |

### 2.7 Measurement, standards and mix grading (lane 05; conventions from lane 04)

| Candidate | Licence | Role | Effort | Verdict |
|---|---|---|---|---|
| EBU Tech 3341-2023 signals + ITU BS.2217-2 table | EBU/ITU publications; file terms unstated `[?]` | Conformance audio (48 kHz) + 29-file oracle at ±0.1 LKFS | S | **Use for tests** (terms check first; never redistribute) |
| libebur128 | MIT | Test-side comparator only (~5.53 MB/state @96 kHz — too heavy for 64 inserts) | S | Comparator |
| **sz_meters** | MIT (LICENSE read) | C++ BS.1770-4 gating + inter-sample true peak + AES17 metrics; second comparator to benchmark | S–M | **Benchmark candidate** |
| r8brain-free-src | MIT | Standby resampler if the JUCE 8x gate needs it | M | Standby |
| metermaid | MIT | Human spot-check desktop meter | S | Tool only |
| alleato-llc/dr | MIT | DR definition reference (Pleasurize algorithm) | S | Reference |
| matchering | **GPL-3.0** | Reference-mastering capability list only | — | **AVOID** |
| ViSQOL | Apache-2.0 | Full-reference perceptual metric; codec domain, 48 kHz — research only | L | WATCH (research) |
| AutoEq | MIT | Math reference for FR→EQ derivation | S | Reference |
| FFTBalance | MIT wrapper, FFTW GPL + libsndfile LGPL-2.1 | — | — | **AVOID bundling** |
| Diff-MST; jhtonyKoo style-transfer weights | CC-BY-NC-SA-4.0; unlicensed + MUSDB18 | — | — | **AVOID** |
| timbral_models | Apache-2.0 | Eight interpretable timbre attributes; offline E4 pilot, out of grade | M | **Pilot candidate** |
| automix-toolkit | Apache-2.0 / apache-2.0 (HF) | Drum auto-mix pattern only (KENN has own kernels) | — | Pattern |
| wavesurfer.js | BSD-3-Clause | Only if interactive playback-linked figures are wanted; otherwise extend existing Vue canvas components | S–M | Optional |
| peaks.js; matplotlib | LGPL-3.0; PSF-style but off allow-list | — | — | **AVOID**; owner decision |
| MixAssist dialogues (Zenodo 15571750/15848443) | cc-by-4.0 both | Phrasing structure: name the measurement → give the range → say what to listen for; HF copies unlicensed — never ship | M | **Use with attribution** |
| MED (six CC BY songs) | CC BY 4.0 (6/10 songs) | E9 listening material; Hub mirror unlicensed | M–L | **Use for E9 only** |
| MUSDB18 / -HQ | `other-nc` verbatim | Cannot ship/train commercially; quotable caveat | — | Do not ship |

Standards state: EBU R128-2023 (V5, Nov 2023) is current — ±1.0 LU live tolerance, ±0.2 LU QC tolerance (the prior "rev 3 (2020)" was stale); Tech 3342-2023 V4 is the LRA document; BS.1770-5 (11/2023) adds Annexes 3–4 beyond the stereo algorithm KENN implements. House rules (keep labelled): PLR/DR thresholds, correlation/mono-compat thresholds, headroom targets — and the 0–100 grade itself has no open standard. Meter choice: recommendation to keep 4x true peak for the live meter (meets the EBU minimum; 8x costs 31–47% of a core for KENN's own stricter margin). Plan mapping: E2, E3, E4, E9, E10, B1.

### 2.8 Teaching and education layer (lane 04)

| Candidate | Licence | Role | Effort | Verdict |
|---|---|---|---|---|
| fsrs (PyPI) | MIT | E8 scheduler; wrap Card/Scheduler over the existing progress store; fixed desired-retention first | S | **ADOPT candidate** |
| music21 | BSD-3-Clause | Theory/analysis; bundled corpus caveat — keep corpus files out unless checked | M | Reuse |
| partitura | Apache-2.0 | Score/performance alignment if a module needs scores | M | Reuse |
| tonal | MIT (npm) | Theory primitives if curriculum UI is TS/JS | S | Reuse |
| VexFlow | MIT (per LICENSE text; API detector NOASSERTION) | Notation rendering | S–M | Reuse |
| audiate | Apache-2.0 | Ear-training interaction patterns; stale since 2021 | — | Reference only |
| birdears; nootka; phantom; live-maestro | AGPL-3.0; GPL-3.0; AGPL-3.0; AGPL-3.0 | — | — | **AVOID** |
| SuperMemo2 (Python) | MIT but archived 2024 | — | — | Dead |

Product patterns to study (not depend on): Rate My Song AI (0–100 + 3 fixes + V2 comparison; "bring the vocal forward 2 dB in the chorus"-grade specificity) and TrackScore.AI ("Every answer cites your numbers … names the target it was scored against"; conversational memory of previous tracks) — the two shipped 0–100-with-reasoning competitors. RoEx Mix Check Studio (free per-category report), iZotope Neutron ("starting point, not verdict", do-no-harm framing), sonible smart:EQ 4 (reference-derived custom profiles, 10-track group unmasking). None grade a live session, publish a standard/house-rule taxonomy, or ship a curriculum. Curriculum content: no open mixing curriculum exists — author in-house; the "why this number" affordance (every displayed E2/E4 value links to its source) remains the unshipped teach-first feature. Plan mapping: E2–E4, E8, E9, E11.

### 2.9 Conversation and agent architecture (lane 06)

| Candidate | Licence | Role / key fact | Effort | Verdict |
|---|---|---|---|---|
| **promptfoo** | MIT | Eval runner + Web UI + `ollama:chat:*` targets and Ollama-as-judge; **`keep_alive: 0`** unloads each model after the call; assertion concurrency down to 1 | S | **ADOPT #1** (C1/C4) |
| DeepEval | Apache-2.0 | pytest-native; `deepeval set-ollama`; G-Eval metrics | S | ADOPT #2 (if pytest-first) |
| Inspect AI | MIT | Audit-grade: `inspect view` (127.0.0.1:7575), Scores filter, static `inspect view bundle` for sealed runs | M | Shortlist #3 (C4 evidence) |
| Ragas | Apache-2.0 | Dormant: last push 2026-02-24, 637 open issues | — | AVOID as gating harness |
| Langfuse self-host | MIT outside `ee/`, enterprise inside | Five services incl. ClickHouse — competes with Live for RAM; annotation queues outside `ee/` | L | WATCH (volume doesn't exist) |
| mem0 | Apache-2.0 | ADD-only accumulate pattern validates KENN's supersede model; published scores are managed-platform numbers | M | WATCH (patterns > dependency) |
| Graphiti | Apache-2.0 | Validity-window facts ("invalidated — not deleted"); needs graph DB + warns small models break extraction schemas | L | AVOID for now (infra + model class) |
| Letta V1 | Apache-2.0 | Retired in place ("Historical source"); successor is a coding agent, not a memory library | — | AVOID |
| KENN profile/task memory (in place) | in-repo | Bounded rows, active/inactive supersede, keep/revise/reject, no hidden reasoning/tool payloads | — | **KEEP** |
| XGrammar via Ollama `format` | Apache-2.0 | Constraint layer already inside Ollama's MLX runner (`mlxrunner/xgrammar/`) — schema support on the MLX path is real; runner parity unmeasured | S (verify) | ADOPT — no new dep |
| Outlines / llguidance | Apache-2.0 (open-core) / MIT | Python-side schema composition; second engine | S/M | WATCH |
| PEFT / TRL | Apache-2.0 / Apache-2.0 | SEAL stack already pinned in `requirements-training.txt` | — | **KEEP** |
| Unsloth | **Apache-2.0 core + AGPL-3.0 Studio UI** (dual) | Same-hardware A/B only if the packet grows; core wheel only, never Studio | M | WATCH (licence split) |
| Axolotl | Apache-2.0 | Publishes NVIDIA Ampere+/AMD requirement; telemetry defaults on (`AXOLOTL_DO_NOT_TRACK=1`) | M | WATCH (not for SEAL as-is) |

`tool_choice` remains unsupported on Ollama's OpenAI-compatible surface — do not design around forced function calling; a single-schema `format` is the available mechanism. L4 next step: one required-schema request per runner (llamacpp vs MLX) before the next shadow comparison, recording the runner per trace.

---

## 3. Consolidated licence tables

Verdict column is this pass's reading against the KENN allow-list. Source lane in the last column. "Clean" = code and weights both MIT/BSD/ISC/Apache-2.0.

### 3.1 Brain, runtime, retrieval, evaluation, training tooling (lanes 02/06)

| Component | Code | Weights | Verdict | Lane |
|---|---|---|---|---|
| Qwen3.5-4B / 0.8B / 2B / 9B | Apache-2.0 | Apache-2.0 | ADOPT-eligible | 02 |
| Gemma 4 (E2B/E4B/12B/26B/31B) | Apache-2.0 | Apache-2.0 | ADOPT-eligible | 02 |
| Granite 4.2 3B; Ministral 3; Qwen3-4B-2507 | Apache-2.0 | Apache-2.0 | ADOPT-eligible | 02 |
| Pre-Gemma-4 Gemma family (e.g. embeddinggemma-300m) | custom Gemma licence | same | AVOID (non-Apache) | 02 |
| Llama family | `other` | Llama Community Licence | AVOID | 02 |
| Ollama; llama.cpp; MLX | MIT | n/a | Tooling | 02 |
| XGrammar; Ollama `format`; Outlines; llguidance | Apache-2.0; MIT runner; Apache-2.0; MIT | n/a | Tooling | 06 |
| Qwen3-Embedding-0.6B; EmbeddingGemma-2; bge-m3 | Apache-2.0; Apache-2.0; MIT | Apache-2.0; Apache-2.0; MIT | Clean | 02 |
| bge-reranker-v2-m3; Qwen3-Reranker-0.6B; FlashRank | Apache-2.0 all | Apache-2.0 all | Clean | 02 |
| Jina rerankers v2+/embeddings-v3 | CC-BY-NC-4.0 | same | AVOID | 02 |
| promptfoo; DeepEval; Inspect AI | MIT; Apache-2.0; MIT | n/a | Clean | 06 |
| Ragas | Apache-2.0 | n/a | Dormant | 06 |
| Langfuse | MIT outside `ee/`; enterprise inside | n/a | Composite — read boundaries | 06 |
| mem0; Graphiti | Apache-2.0 | n/a | Patterns only | 06 |
| PEFT; TRL | Apache-2.0 | n/a | KEEP | 06 |
| Unsloth | Apache-2.0 core + AGPL-3.0 Studio | n/a | Dual — cite the split | 06 |
| Axolotl | Apache-2.0 | n/a | WATCH | 06 |
| mlx-audio | MIT | n/a | Survey only | 02 |

### 3.2 Voice (lane 02)

| Component | Code | Weights | Verdict | Lane |
|---|---|---|---|---|
| whisper.cpp; faster-whisper | MIT | MIT (turbo) / Apache-2.0 (v3) | Clean | 02 |
| Parakeet TDT 0.6B v3 | Apache-2.0 port | **CC-BY-4.0** | WATCH (allow-list) | 02 |
| Moonshine (streaming) | MIT | MIT by default (legacy non-English carve-out) | WATCH (read LICENSE) | 02 |
| VibeVoice-ASR-Streaming | MIT | MIT | Clean (unmeasured) | 02 |
| Voxtral Mini 4B Realtime | Apache-2.0 | Apache-2.0 | Clean (memory) | 02 |
| Qwen3-ASR 0.6B/1.7B | Apache-2.0 | Apache-2.0 | Clean | 02 |
| Kokoro-82M | Apache-2.0 | Apache-2.0 | Clean | 02 |
| Chatterbox family | MIT | MIT | WATCH (PerTh watermark) | 02 |
| F5-TTS | MIT | **CC-BY-NC-4.0** | AVOID | 02 |
| Piper line | archived; successor GPL-3.0 | — | AVOID | 02 |
| StyleTTS2 | MIT | no licence tag `[?]` | Unclear | 02 |
| Orpheus/Dia/CSM | Apache-2.0 tags | gated/stale | Research only | 02 |
| openWakeWord | Apache-2.0 | pretrained **CC-BY-NC-SA-4.0** | Split — train own model | 02 |
| microWakeWord | Apache-2.0 | **Apache-2.0 incl. shipped weights** | Clean | 02 |
| Porcupine | Apache-2.0 repo | runtime AccessKey, per-language terms | WATCH (terms) | 02 |

### 3.3 Audio understanding (lane 03)

| Component | Code | Weights | Verdict | Lane |
|---|---|---|---|---|
| Basic Pitch | Apache-2.0 | Apache-2.0 (repo-distributed `[I]`) | ADOPT-eligible | 03 |
| LAION-CLAP | CC0-1.0 | CC0-1.0 (HF mirror Apache-2.0) | Clean | 03 |
| MSST; KimberleyJSN mel-band; ZFTurbo BS-RoFormer | MIT | MIT per first-party statements | ADOPT w/ MUSDB caveat | 03 |
| beat_this | MIT | MIT | ADOPT w/ soxr condition | 03 |
| torchcrepe; swift-f0; audfprint | MIT | MIT / bundled / n/a | Clean | 03 |
| OpenL3; AudioBox-Aesthetics | MIT; CC-BY-4.0 | CC-BY-4.0; CC-BY-4.0 | WATCH (allow-list) | 03 |
| MS-CLAP | MIT | **MS-PL** | WATCH (off-list) | 03 |
| M2D-CLAP | unread `[?]` | unread | WATCH | 03 |
| MuQ; MERT | MIT; Apache-2.0 | **CC-BY-NC-4.0** | AVOID | 03 |
| Demucs v4 | MIT | **not covered** | AVOID | 03 |
| Open-Unmix; Spleeter | MIT | NC-SA; unstated | AVOID | 03 |
| BS PolarFormer; MDX23C; viperx family etc. | n/a | **no statement** | AVOID | 03 |
| MT3; RMVPE; musicnn; piano_transcription_inference | Apache/MIT/ISC/no file | **unstated** | AVOID | 03 |
| ADTOF | CC-BY-NC-SA-4.0 | same | AVOID | 03 |
| chromaprint | MIT parts | n/a | AVOID (LGPL as a whole) | 03 |
| Freesound API | ToS | per-sound CC | WATCH (deal) | 03 |

### 3.4 Generation (lane 03)

| Component | Code | Weights | Verdict | Lane |
|---|---|---|---|---|
| ACE-Step v1; v1.5 | Apache-2.0; **MIT** | Apache-2.0; MIT | ADOPT (opt-in) | 03 |
| DiffRhythm | Apache-2.0 | Apache-2.0 (DiT); VAE unstated | WATCH | 03 |
| YuE | Apache-2.0 | Apache-2.0 | Clean, unfit | 03 |
| MusicGen; MAGNeT; AudioLDM2; Tango2 | permissive family | **CC-BY-NC(-SA)-4.0** | AVOID | 03 |
| Stable Audio Open Small | community | gated + revenue terms | WATCH | 03 |
| Mustango | tag only `[?]` | unread | AVOID default | 03 |

### 3.5 Measurement and standards (lanes 04/05)

| Component | Licence | Verdict | Lane |
|---|---|---|---|
| libebur128; r8brain; metermaid; alleato-llc/dr | MIT | Test-side / reference only | 05 |
| sz_meters | MIT | Benchmark candidate | 05 |
| matchering | **GPL-3.0** | AVOID | 05 |
| ViSQOL | Apache-2.0 | Research only | 05 |
| AutoEq | MIT | Math reference | 05 |
| FFTBalance | FFTW GPL + libsndfile LGPL | AVOID bundling | 05 |
| Diff-MST; jhtonyKoo weights | NC-SA; unlicensed | AVOID | 05 |
| timbral_models | Apache-2.0 | Pilot | 05 |
| wavesurfer.js | BSD-3-Clause | Optional | 05 |
| peaks.js; matplotlib | LGPL-3.0; off-list | AVOID; owner call | 05 |
| EBU/ITU conformance signals | publication; file terms `[?]` | Test material only | 05 |
| R128-2023 / Tech 3342-2023 / Tech 3343-2023 / BS.1770-5 | public documents | Citable | 04/05 |
| AES TD1006 / TD1008; Spotify target | public/PDF | Citable | 04 |

### 3.6 Live integration, teaching and ecosystem tooling (lanes 01/04/06)

| Component | Licence | Verdict | Lane |
|---|---|---|---|
| AbletonOSC (vendored) | MIT | KEEP (sole write authority) | 01 |
| ableton-js | MIT | Qualify via vendored bridge; no second runtime | 01 |
| Extensions SDK | **`[?]`** ("non-redistributable" downstream) | WATCH (Legal read required) | 01 |
| Max for Live | **`[?]`** (terms unread) | WATCH (Legal read) | 01 |
| producer-pal; live-wire; Paulstretch; Noise Canvas | GPL-3.0-or-later; GPL-3.0; GPL-2.0; AGPL-3.0 | Ideas only | 01 |
| LivePilot | BSL-1.1 (→MIT 2030-04-13) | Patterns only | 01/04 |
| Loophole; Protocol0 extension-sdk; ableton-js | MIT | Patterns | 01 |
| track-coach | MIT (Demucs weights caveat) | Idea; no model vendor | 01 |
| fsrs / py-fsrs / fsrs4anki | MIT | Clean | 04 |
| music21; partitura; tonal; VexFlow | BSD-3; Apache-2.0; MIT; MIT | Clean (corpus caveat) | 04 |
| birdears; nootka; phantom; live-maestro | AGPL/GPL | AVOID | 04 |
| SuperMemo2 Python | MIT but archived | Dead | 04 |
| promptfoo/DeepEval/Inspect | MIT/Apache/MIT | Clean | 06 |
| mem0/Graphiti | Apache-2.0 | Patterns only | 06 |

### 3.7 Data, content and test material (lanes 03/04/05)

| Item | Licence | Verdict | Lane |
|---|---|---|---|
| MixAssist Zenodo 15571750 / 15848443 | cc-by-4.0 both | Use with attribution (phrasing) | 04/05 |
| MixAssist HF copies + `Qwen-Audio-Mix-Instruct` repo | **none declared** | Never ship | 04 |
| MED Hub mirror | **none declared** | Never ship | 04 |
| MED DAFx-17 six-song subset | CC BY 4.0 | E9 listening only | 04/05 |
| MUSDB18 / MUSDB18-HQ | `other-nc` verbatim | Do not ship/train commercially | 03/05 |
| MAEB / Omni-Embed-Audio figures | paper; percentages `[?]` | Quote task-level caution only | 03 |
| EBU Tech 3341 signals; BS.2217-2 `.wav` hosting | terms unstated `[?]` | Test-only; confirm terms | 05 |
| Freesound free tier | non-commercial, revocable | WATCH (deal) | 03 |

---

## 4. Integrated corrections vs prior docs and beliefs

Each row changes a claim that appears in `KENN_OPEN_SOURCE_CAPABILITY_LANDSCAPE_2026-10-15.md`, the 14 Oct docs, or earlier project beliefs.

| # | Prior claim | Correction | Source |
|---|---|---|---|
| 1 | Ollama model sizes as model-layer figures | Manifest totals (what a pull downloads): qwen3.5 4b **3.10 GiB**, gemma4 e4b **6.13 GiB**, embeddinggemma-2 **1.20 GiB**, qwen3.5 0.8b **1.23 GiB** incl. 302 MB draft | lane 02 takeover |
| 2 | Latency baseline Ollama 0.34.4 valid | Ollama 0.40.x runs supported models on the **MLX runner by default** since v0.40.0; stale until re-measured; pin runner + digest | lane 02 H5/KQ3 |
| 3 | Spec decode unreachable / only on 0.40 | MLX MTP speculation since **v0.32.6** (2026-08-04), memory fix v0.34.2; v0.40.0 = routing. Parked decision stands | lane 02 takeover |
| 4 | openWakeWord "Apache-2.0" | Split: code Apache-2.0, **pretrained models CC-BY-NC-SA-4.0**; microWakeWord is the clean alternative | lane 02 |
| 5 | faster-whisper unclear on macOS | **CPU-only on macOS** — CTranslate2's only GPU targets are CUDA/ROCm | lane 02 |
| 6 | ACE-Step v1.5 licence unresolved | **MIT** (LICENSE + README + HF tags) | lane 03 KQ5 |
| 7 | MS-CLAP weights unresolved/401 | **MS-PL** on `microsoft/msclap`; `clap-ms-2023` still 401 | lane 03 KQ3 |
| 8 | LAION-CLAP weights apache-2.0 | Checkpoints are **cc0-1.0** (`lukewys/laion_clap`); Apache-2.0 is only the HF-transformers mirror | lane 03 KQ0 |
| 9 | "CLAP 8–14%" retrieval figures | Not re-locatable → `[?]`; only 22.7% best clustering / 47.9% M2D T2A are quotable | lane 03 KQ0.9 |
| 10 | "EBU R128 rev 3 (2020)" | **R 128-2023 V5 (Nov 2023)**; ±1.0 LU live / ±0.2 LU QC; Tech 3342-2023 V4; BS.1770-5 current | lane 04 §2 / lane 05 |
| 11 | "No product ships 0–100 with reasoning" | **Falsified** — ratemysong.ai and trackscore.ai ship it; TrackScore adds measurement-grounded conversation | lane 04 §5 |
| 12 | 12.4.6 carries the M4L "unstored" fix | 12.4.6 = one bugfix (render hang); the unstored fix is the last item of **12.4.5** | lane 01 Q1 |
| 13 | AbletonOSC "4 rack mentions are type checks" | **Zero rack code**; three raw `rack` substrings sit inside `track_index` | lane 01 Q3 |
| 14 | Extensions install path "Preferences → Extensions" | Official FAQ: **Settings → Extensions** | lane 01 Q2 |
| 15 | MUSDB dataset terms unread | Read: access by request, "academic purposes only"; `other-nc` on Zenodo — chain-of-title caveat now quotable | lane 05 §3.3 |
| 16 | Basic Pitch has clean weights | No separate weights sentence exists; repo-distribution reading `[I]` — confirm if it ships | lane 03 KQ2 |
| 17 | Tango2 NC-ND | **NC-SA** (prior note wrong) | lane 03 KQ5 |
| 18 | KimberleyJSN tops the vocals table | **BS PolarFormer SDR 11.00** tops it, unlicensed → AVOID | lane 03 takeover |
| 19 | "E1–E4 not located" (lane 03 early note) | E1–E11 are defined at `KENN_PLAN.md` ~2375–2447; mapping corrected and retracted | lane 03 takeover |
| 20 | Unsloth Apache-2.0 | **Dual-licensed**: Apache-2.0 core + AGPL-3.0 Studio UI | lane 06 |
| 21 | Ragas as default RAG-eval harness; Letta active | Ragas dormant since 2026-02-24; Letta V1 retired ("Historical source") | lane 06 |
| 22 | "Add hybrid retrieval" | Shipped: RRF fusion with a 24 Sep 2026 measured receipt; only query rewriting remains | lane 06 |
| 23 | bge-reranker-v2-m3 MIT (secondary) | HF frontmatter **apache-2.0**; the MIT citation was wrong | lane 02 |
| 24 | soxr role in beat_this "not inspected" | Confirmed inference-time call: `beat_this/inference.py` L274–275 (`soxr.resample`) | lane 03 KQ4 |
| 25 | MLX-runner schema support open question | Answered: XGrammar layer exists (`mlxrunner/xgrammar/`); behavioural parity still unmeasured | lane 06 KQ3 |
| 26 | 14 Oct comparable-products table complete | Missing ahujasid/ableton-mcp (3,190★ MIT), Rate My Song AI, TrackScore.AI; producer-pal licence is GPL-3.0-**or-later**; dawcraft = MIT + non-distributed GPL test fixtures | lane 04 §6 |

---

## 5. Traps and avoid list, with exact triggering licence text

### 5.1 Blocked by licence (do not vendor, copy, link or ship)

- **Demucs v4 weights** — "The model weights are not covered by the MIT license, and are provided only for scientific purposes." (adefossez, facebookresearch/demucs#327, 2022-05-23). Mirrors disagree (Intel MIT vs NC) — never rely on mirrors.
- **openWakeWord pretrained models** — "All of the included pre-trained models are licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license". Code and pipeline are Apache-2.0; the shipped model files are not.
- **Open-Unmix `umxl`** — "Note, that the weights are only licensed for non-commercial use (CC BY-NC-SA 4.0)." `umxhq`/`umx` unstated + MUSDB terms.
- **NISQA weights** — "The model weights (nisqa.tar, nisqa_mos_only.tar, nisqa_tts.tar) are provided under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) License." Speech-only besides.
- **matchering** — LICENSE first lines: "GNU GENERAL PUBLIC LICENSE / Version 3, 29 June 2007". Forks are derivative works; no adoption including the CLI/Docker images.
- **chromaprint** — "As a whole, Chromaprint should be therefore considered to be licensed under the LGPL 2.1 license." (audfprint, MIT, is the substitute.)
- **MUSDB18 / MUSDB18-HQ** — "MUSDB18 is provided for educational purposes only and the material contained in them should not be used for any commercial purpose without the express permission of the copyright holders." Every MUSDB-trained "MIT" checkpoint carries this caveat; ZFTurbo's own line: "you will need to verify that on your end."
- **Freesound API free tier** — "You can use the Freesound API for free only for non-commercial purposes." Plus: "the license is temporary and may be withdrawn by Freesound at any time"; keys "may be revoked".
- **LivePilot** — BSL 1.1 ("Business Source License 1.1", Licensor Pilot Studio, change → MIT 2030-04-13): "You may make production use of the Licensed Work, provided your use does not include offering it as a commercial hosted service to third parties." Source-available, not open source.
- **MuseCritic code/weights; jasper-zheng/ableton-sdk-mcp; audiojs/loudness; producer-player** — licence `None` / `NOASSERTION`; unstated = unusable.
- **jhtonyKoo style-transfer weights** — Google Drive files, no licence, "Trained with MUSDB18".
- **Diff-MST** — "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International" (LICENSE first line).
- **whisper-timestamped** — AGPL-3.0 repo; README also names `dtw-python` (GPL v3) as a dependency.
- **ADTOF** — LICENSE first line: "Attribution-NonCommercial-ShareAlike 4.0 International".
- **MusicGen / MAGNeT / AudioLDM2 / Tango2 weights** — CC-BY-NC(-SA)-4.0; the family's code licences cannot rescue the weights.
- **MuQ / MERT weights** — CC-BY-NC-4.0.
- **Spleeter models** — licence statement covers code only; pretrained weights unstated.
- **MT3 / RMVPE / musicnn / piano_transcription_inference / BS PolarFormer / MDX23C / viperx-aufr33-TRvlvr-jarredou-anvuew-Sucial families** — weights or the project carry no statement; "pin code and weight licences separately" (B4) makes these unusable until stated.
- **DiffRhythm `espeak-ng`; beat_this optional DBN/madmom; FFTBalance (FFTW GPL + libsndfile LGPL); ffmpeg-based loudness tools** — GPL/LGPL programs to isolate or avoid bundling, never ship inside KENN.
- **Grisey, dr14.t.meter, audiometer, pedalboard, peaks.js, LivePilot, producer-pal, live-wire, Paulstretch for Live, Noise Canvas, birdears, nootka, phantom, live-maestro** — GPL/AGPL/LGPL/BSL copyleft; ideas are fine, code is not.

### 5.2 Gated (WATCH) — decision needed before any work

- **CC-BY-4.0 allow-list group** — Parakeet weights, OpenL3 weights, AudioBox-Aesthetics, MixAssist/MED data: permissive-with-attribution but off today's MIT/Apache list. Each needs the owner's allow-list decision plus the attribution line; none is shippable until then.
- **MS-CLAP (MS-PL)** — permissive but off-list; recommended no (D-09).
- **Extensions SDK licence text** — Centercode-gated; "non-redistributable" is the strongest public evidence (Loophole CONTRIBUTING). Read the licence inside the zip before any `.ablx` decision.
- **Max for Live terms** — embedding/redistribution terms not read; owner/legal question before any M4L path.
- **Stable Audio Open Small / Freesound commercial** — gated community licence, revenue terms; contact-only commercial deal.
- **Porcupine** — runtime AccessKey + per-language commercial terms; not local-first as-is.
- **Orpheus/Dia/CSM TTS** — Apache-2.0 tags but 2025-era, gated or stale; research-only until re-verified.

### 5.3 Verified-broken writes and technical traps (not licence)

- **Warp-marker writes** (`Clip.add_warp_marker`/`move_warp_marker`): "both report success and change nothing" (Live 12.4.3, producer-pal field notes). Never promise.
- **Warped looped arrangement clips cannot be resized** by any property; **mid-clip "split"** truncates and discards the tail. Only edge trims work.
- **AbletonOSC `groove` property** is commented out upstream with a recorded OSC serialisation error; `warp_markers` blocked for the same net effect.
- **Extensions SDK is not a path to** transport, real-time audio/MIDI, browser/library scanning, or stable identity — officially absent.
- **AbletonOSC is effectively unmaintained** (last code push Nov 2025, 34 open PRs, zero releases); KENN owns fixes through its vendored pin (already riding unmerged PR #173).
- **Do not build against public LOM docs alone** for browser/groove/take-lane paths — they are absent there; qualify via a feature handshake or keep out.

---

## 6. Decision register — owner questions and research recommendations

Each entry: decision, source lane, recommendation. "Owner" where licence, money or positioning needs a human call; "Defer" where the research answers itself.

| ID | Decision | Lane | Recommendation |
|---|---|---|---|
| D-01 | Read the Extensions SDK licence inside the zip (Centercode) | 01 | Owner downloads and captures the licence; it unblocks or kills any `.ablx` distribution decision |
| D-02 | Approve the browser/rack-chain/take-lane capability probe through the vendored bridge (feature handshake + refusal path) | 01 | Yes — read-verified capabilities only, one write authority unchanged |
| D-03 | C2 re-measure on Ollama 0.40.x with runner pinned and reported | 02 | Yes — cheapest measurement that decides whether prior latency conclusions survive |
| D-04 | PerTh watermark on Chatterbox voice output | 02 | Decide before shipping voice, not after; keeping it is the defensible default |
| D-05 | Widen the allow-list for CC-BY-4.0 (Parakeet, OpenL3, AudioBox-Aesthetics) | 02/03 | Owner call; attribution obligations documented; research-only until answered |
| D-06 | Commission the MUSDB chain-of-title legal read | 03/05 | Owner/legal; blocks "MIT" separation checkpoints from shipping clean |
| D-07 | soxr substitution/packaging for beat_this (and the librosa/soxr question in the meter path) | 03/05 | Replace the one inference call site first; isolated LGPL is the fallback |
| D-08 | One-line Basic Pitch weights confirmation from Spotify if it ships | 03 | Yes — repo-distribution reading `[I]` is not an author statement |
| D-09 | Pursue MS-CLAP as a CLAP alternative (MS-PL) | 03 | No — LAION-CLAP covers the need with CC0 both sides |
| D-10 | Accept the corrected E-mapping of lane-03 rows (B4 / B4+E6 / B4 support / E2-E9 research) | 03 | Accept; the early "E1–E4 not located" note is retracted |
| D-11 | Update the 14 Oct comparable-products doc: ahujasid/ableton-mcp, producer-pal `-or-later`, dawcraft, both grade products | 04 | Yes — one table edit |
| D-12 | Competitive-reframe wording in the E2 note (differentiator = in-session, source-labelled, teaching-first) | 04 | Yes — gated on orchestrator review |
| D-13 | Author E8 curriculum in-house | 04 | Yes — no open curriculum exists; utilities only |
| D-14 | Benchmark sz_meters as second comparator vs the 8x reference | 05 | Yes — S–M, test-side only, no dependency |
| D-15 | timbral_models pilot (Apache-2.0), offline, out of grade | 05 | Yes — validate on music before any descriptor ships |
| D-16 | Adopt EBU/ITU test material once file terms are checked | 05 | Yes — closes "download URL unverified"; never redistribute |
| D-17 | PLR readout as a labelled house rule | 05 | Yes — one subtraction over owned meters with its formula named |
| D-18 | MixAssist Zenodo reuse under cc-by-4.0 for phrasing | 04/05 | Yes — Zenodo copies only; HF copies never ship |
| D-19 | Eval harness pick | 06 | promptfoo first (keep_alive: 0), DeepEval if pytest-first, Inspect AI for sealed C4 |
| D-20 | Query-rewriting trial on the follow-up path | 06 | Yes — M; measure on device-purpose fixtures; routing unchanged |
| D-21 | Trace store (Langfuse self-host) | 06 | No for now — five services compete with Live; volume doesn't exist |
| D-22 | C5 reranker choice under the written budget | 02 | FlashRank only fit; bge/Qwen3 need the 250 MB line revisited as an explicit owner call |
| D-23 | Embedding swap | 02 | Measure-first: Qwen3-Embedding-0.6B vs incumbent, retrieval quality per ms; swap invalidates the index |
| D-24 | Freesound commercial deal | 03 | No — contact-only terms; local library indexing has no such problem |
| D-25 | Wake word scope | 02 | Out for now — B4 chose PTT; microWakeWord clean if forced later |
| D-26 | Max for Live terms legal read | 01 | Owner/legal before any M4L path |
| D-27 | Voice cloning scope | 02 | Default no; name consent/storage questions before any trial |
| D-28 | mix_doctor house rules: keep or drop before E9 | 04/05 | Keep until E9 listening; every one stays tagged as house rule |
| D-29 | 4x vs 8x true-peak for the live meter | 05 | Keep 4x (meets EBU minimum); 8x buys only our stricter margin at 31–47% of a core |
| D-30 | ViSQOL evaluation | 05 | Defer — wrong domain (codec degradation), L effort |
| D-31 | New figure dependencies (matplotlib, wavesurfer.js) | 05 | No new deps now; extend existing canvas components; owner call if server-side PNGs wanted |
| D-32 | Unsloth A/B against PEFT | 06 | Gated — only if the SEAL packet grows; core wheel only, never Studio; same-hardware A/B |
| D-33 | MED six CC BY songs for E9 listening | 04/05 | Yes — E9 listening only with attribution; the unlicensed Hub mirror never ships |

---

## 7. Facts not verified `[?]` — gating ship decisions

1. **Extensions SDK licence text** — not readable publicly; strongest evidence "non-redistributable". Gates every `.ablx` commercial decision.
2. **Max for Live commercial redistribution terms** — unread. Gates any M4L path.
3. **MUSDB-trained-weights legal reading** — dataset NC; whether weights are derivative is a legal call. Gates the separation "ADOPT (caveat)" rows.
4. **EBU test-signal file terms and hosting** — `http://tech.ebu.ch/loudness` returned Cloudflare 403; the BS.2217 `.wav` hosting is unstated; whether any newer compliance set covers BS.1770-5 Annexes 3–4 is unknown.
5. **sz_meters true-peak accuracy** — MIT licence read; no conformance vectors or claims seen.
6. **timbral_models' training-data chain** (Freesound sample terms) and behavioural validity on full mixes.
7. **Unresolved licence lookups**: M2D-CLAP; MT3 checkpoint; BS PolarFormer; 53-stem first-party host; `jarredou/BS-RoFormer-SW` (401); `microsoft/clap-ms-2023` (401); Mustango card; RMVPE/swift-f0 weight terms; YAMNet re-check; DiffRhythm VAE and successors.
8. **MAEB percentages** — "8–14%" and "<3% FLEURS" not re-locatable; do not quote. 22.7% clustering / 47.9% M2D T2A stand.
9. **No M3 16 GB measurement of any kind** — no STT/TTS latency, no reranker latency, no 0.34.4-vs-0.40.4 A/B, no WER on Ableton vocabulary, no separation wall time, no generation s/min. Every fit cell is `[I]`.
10. **MLX vs llama.cpp runner parity** for `format` acceptance — existence of the XGrammar layer verified; equivalence untested.
11. **Whether speculation fires in practice** for qwen3.5/gemma4 on 0.40.4 and at what acceptance rate; whether image `draft` layers affect loaded-model memory.
12. **`OLLAMA_KV_CACHE_TYPE` on the MLX runner** — docs describe the llama.cpp path; unverified on MLX.
13. **Unsloth wheel boundary** — whether the PyPI wheel can ever contain AGPL-3.0 Studio components.
14. **Basic Pitch weights grant** — reading, not statement (D-08).
15. **ANEForge for large-v3-turbo** — published benchmarks cover tiny→medium encoders only.
16. **Freesound commercial pricing/limits** — contact-only.
17. **promptfoo `--filter-metadata` and grouping serialisation** under all assertion types — doc-read, not run.
18. **Whether KENN needs a trace store at all** — product decision, not research finding.
19. **12.4.4** — no public release-notes section; existence unknown. **Live 13 Beta community reference** — not reproducible; treat as dead.
20. **LivePilot "474 tools / 57 domains"** — vendor-stated, not counted.

---

## 8. Proposed KENN_PLAN.md additive edits (DRAFT — for oracle review)

**Status:** applied to `KENN_PLAN.md` on 15 Oct 2026 after oracle review — 13 additive, quote-anchored inserts; no owner wording was reworded, removed or reordered. The plan drifts as the owner edits it; the line numbers below are the review-time frame — re-match by quote before reuse. Items touching new runtime dependencies are marked. Each edit states its anchor quote, the current line, the exact insert, its rationale, and the source lane.

### E-01 — research pointer after the standing reuse check

**Anchor (L77):** "It is a source review; comparative benchmarks and any adoption remain open." — last line of the reuse-check pointer paragraph.

**Insert after L77:**
```
The [15 October open-source deep research](docs/research/KENN_OPEN_SOURCE_DEEP_RESEARCH_2026-10-15.md)
extends this check across the brain, voice, retrieval, Live-integration, teaching and grading
surfaces with per-candidate licences (code and weights), M3 fit estimates and first steps. Like
the 14 October screen, it is a source review: it approves nothing, adds no dependency, and every
candidate stays behind this check and owner approval.
```

**Rationale:** records the pass without widening the reuse check's authority. **Source:** all lanes; spec output 3 ("update the research references").

### E-02 — runtime baseline note

**Anchor (L1163):** "Needs the route/context audit; fixes may land in small slices while that audit continues." — §2 opener.

**Insert after L1163:**
```
Runtime baseline note (15 Oct research): the recorded latency baseline ran Ollama 0.34.4 on the
llama.cpp runner; since v0.40.0 supported models run on the MLX runner by default on Apple
Silicon, and a tag can resolve to two runner packages. Until a same-prompt re-measure on the
current stable line exists, earlier latency figures describe a runtime combination no longer
installed. Pin the runner name alongside the digest in C2 receipts.
```

**Rationale:** keeps C2 honest without touching the parked decision. **Source:** lane 02 KQ3/KQ9, H5.

### E-03 — speculative-decoding history correction

**Anchor (L1180):** "...with held-out quality unchanged. Compare a change of model separately from a change of runtime." — parked MLX decision tail.

**Insert after L1180 (new bullet in the 13 Oct decision list):**
```
- **Speculative-decoding history (15 Oct research note):** the MLX engine has used Qwen3.5's MTP
  head automatically since v0.32.6 (2026-08-04), with a memory-growth fix in v0.34.2; v0.40.0
  changed routing, not availability. The parked decision above is unchanged: runtime changes
  compare separately from model changes, on the same explicitly pinned checkpoint.
```

**Rationale:** corrects the record without reopening the park. **Source:** lane 02 KQ3, takeover.

### E-04 — runner verification and eval residency discipline (C2)

**Anchor (L1291–1292):** "...Require unchanged safety and a held-out quality comparison for each latency change." — C2 main bullet tail.

**Insert after L1292 (new sub-bullet under C2):**
```
  - [ ] Record the runner, not only the digest, in every C2 receipt, and unload eval models after
    each call: evals run beside a KENN session must set `keep_alive: 0` on the Ollama provider and
    be checked with `ollama ps`. Serial eval runs alone do not prevent two models staying
    resident for their keep-alive window. (Research: KENN_OPEN_SOURCE_DEEP_RESEARCH_2026-10-15.md
    §2.2, §2.9; lane 02 KQ3, lane 06 KQ1.)
```

**Rationale:** implements C2's "verify digest and response path" rule in the 0.40.x world; no new dependency. **Source:** lanes 02/06.

### E-05 — Remote Script breadth via the vendored bridge (L1)

**Anchor (L2187):** "...recording unsupported or manual-only controls explicitly." — L1 bullet tail.

**Insert after L2187 (new sub-bullet under L1):**
```
  - [ ] Qualify the Remote Script surfaces AbletonOSC does not expose — browser load/preview,
    rack-chain traversal, take lanes, grouped undo steps — through the vendored bridge as a
    capability probe with an explicit refusal path; one write authority stays. Read-verified only
    today; Live 12.4.3 field reports show warp-marker writes and warped-looped arrangement
    resizes no-op, so do not promise them. (Research: lane 01 Q5.)
```

**Rationale:** biggest coverage gap, ranked #6 in lane 01, kept read-only-safe. **Source:** lane 01.

### E-06 — licence-verified provider candidates (B4)

**Anchor (L2380):** "...Pin code and weight licences separately and qualify offline operation and resource use." — B4 tail.

**Insert after L2380 (new bullet after B4):**
```
- Research pointer, 15 Oct (licence-first): Basic Pitch ONNX (Apache-2.0, 230,444-byte file),
  whisper.cpp with large-v3-turbo weights (MIT), beat_this small (MIT; replace or isolate its
  inference-time `soxr` call, LGPL-2.1-or-later), MSST + KimberleyJSN mel-band + ZFTurbo
  BS-RoFormer separation checkpoints (MIT per first-party statements, MUSDB18-HQ chain-of-title
  to clear), ACE-Step v1/v1.5 generation (Apache-2.0 / MIT, opt-in only). Each remains a
  candidate: this check and owner approval still gate any addition.
```

**Rationale:** gives B4 its vetted shortlist without approving it. **Source:** lane 03; spec's §1.4 findings honoured. *(New-dependency candidates — needs approval.)*

### E-07 — conformance material pinned (E2/B1)

**Anchor (L2398):** "Later 15 Oct timing correction: ... [Timing evidence](docs/evidence/KENN_STREAMING_MOMENTARY_TIMING_2026-10-15.md)." — last E2 meter bullet.

**Insert after L2398:**
```
  - [ ] Conformance material, 15 Oct: the "download URL unverified" note is resolved — EBU Tech
    3341-2023 names its minimum-requirement test signals at http://tech.ebu.ch/loudness,
    synthesised at 48 kHz; ITU Report BS.2217-2 (10/2016) is a free 29-file expected-value table
    at ±0.1 LKFS; EBU Tech 3342-2023 V4 is the current LRA document. Confirm the EBU file terms
    before downloading or redistributing; the page returned HTTP 403 during the research pass.
```

**Rationale:** closes a standing plan gap with citable pointers; test material only. **Source:** lane 05 §1.2.

### E-08 — second comparator note (E2)

**Anchor:** immediately after E-07's insert (both after L2398).

**Insert after E-07's block (new sub-bullet):**
```
  - [ ] Comparator, 15 Oct: libebur128 (MIT, quiet since v1.2.6) stays test-side only.
    sz_meters (MIT, C++, BS.1770-4 gating + inter-sample true peak + AES17 metrics) is the
    second comparator to benchmark against the existing 8x accuracy reference before any
    live-path consideration. No dependency is added by this note.
```

**Rationale:** second independent oracle strengthens the meter proof; memory cost stays out of the insert path. **Source:** lane 05 §1.4.

### E-09 — E4 explanation aids

**Anchor (L2434):** "Test that every number in an explanation comes from the grade's own measurements or a cited source, so the grounding gate has nothing to reject and the model never guesses a figure." — E4 bullet 2.

**Insert after L2434 (new sub-bullet under E4):**
```
  - [ ] Two E4 aids from the 15 Oct research: MixAssist dialogues (Zenodo 15571750 / 15848443,
    both cc-by-4.0) for phrasing structure — name the measurement, give the range, say what to
    listen for — using the Zenodo copies only, never the unlicensed HuggingFace copies; and
    AudioCommons timbral_models (Apache-2.0) as an offline descriptor pilot, kept out of the
    grade until an E9 listening check passes.
```

**Rationale:** gives E4 a citation-backed phrasing pattern and a bounded descriptor experiment. **Source:** lanes 04 §1, 05 §3.3. *(timbral_models — new dependency, needs approval.)*

### E-10 — E8 curriculum sourcing

**Anchor (L2451):** "Check that one-off questions don't corrupt curriculum state, and that curriculum state never blocks a one-off question." — E8 bullet 3.

**Insert after L2451 (new sub-bullet under E8):**
```
  - [ ] Curriculum material, 15 Oct: no open mixing curriculum exists to reuse — author lesson
    content in-house. Utilities are clean: fsrs (MIT) scheduler; music21 (BSD-3, keep bundled
    corpus files out unless checked); partitura (Apache-2.0); tonal (MIT); VexFlow (MIT). The six
    MED CC BY songs are the only clean external listening set. Competitive note: 0–100-with-
    reasoning grades now ship elsewhere; the differentiator is in-session, source-labelled,
    teaching-first grading. (Research: lane 04 §3, §5, §8; lane 05 §3.)
```

**Rationale:** records the content gap and the narrowed positioning in the plan's own education section. **Source:** lane 04. *(fsrs, music21, partitura, tonal, VexFlow — new dependencies, needs approval.)*

### E-11 — new acceptance row (meter conformance material)

**Anchor:** acceptance table, between the "Real-time analysis" row (L2868) and "Suggestion validity" row (L2869).

**Insert between L2868 and L2869 (one new table row):**
```
| Meter conformance material | Generated Tech 3341/3342 cases remain the gate; the EBU 48 kHz signal set (http://tech.ebu.ch/loudness) and the ITU BS.2217-2 expected-value table (±0.1 LKFS) are the external oracles once file terms are checked. Test-only; never redistributed. |
```

**Rationale:** the acceptance table records the oracle without changing any owner target. **Source:** lane 05 §1.2.

### E-12 — query-rewriting trial (C3)

**Anchor (L1463):** "...only explicit Apply produces an execution receipt. Include the UI delivery path." — C3 bullet tail.

**Insert after L1463 (new sub-bullet under C3):**
```
  - [ ] Query-rewriting trial (15 Oct research): resolve the follow-up against session context,
    rewrite the retrieval query before the existing hybrid search (Rewrite-Retrieve-Read,
    arXiv 2305.14283), and measure recall on the device-purpose fixtures the RRF receipt showed
    weakest (0.616 pre-fusion). Routing stays unchanged; one local call per follow-up.
    (Research: lane 06 KQ5.)
```

**Rationale:** the only additive retrieval technique after RRF shipped; measurable on existing fixtures. **Source:** lane 06.

### E-13 — runner parity check before the next L4 comparison

**Anchor (L2232–2233):** "...include ambiguity, missing ranges, wrong units and stale identities. A large synthetic corpus or high schema validity alone does not qualify action accuracy." — L4 bullet tail.

**Insert after L2233 (new sub-bullet under L4):**
```
  - [ ] Before the next shadow comparison, send one required-schema planner-shaped request
    through both Ollama runners (llamacpp and MLX) on the installed line and compare `format`
    acceptance; record the runner per shadow trace. Keep `tool_choice` out of the design —
    it is unsupported on the OpenAI-compatible surface. (Research: lane 06 KQ3.)
```

**Rationale:** protects the shadow comparison's comparability across the engine swap. **Source:** lane 06.

### README proposal (`docs/research/README.md`)

Current file is 48 lines ending with the `CPP_DSP_RELEASE_QUALIFICATION.md` bullet. Proposed addition after line 48:

```
---

## 4. Open-source capability and licence research (October 2026)

- **[KENN_OPEN_SOURCE_DEEP_RESEARCH_2026-10-15.md](KENN_OPEN_SOURCE_DEEP_RESEARCH_2026-10-15.md)**
  *Synthesis of the six-lane open-source pass: ADOPT/WATCH/AVOID capability map, licence tables with verbatim triggers, corrections against the 14–15 October docs, and 13 draft additive plan edits for review.*
```

---

## 9. Spec-compliance flags

1. **Spec location.** The deliverable spec was found at repo root `kenn-evaluation-data/prompts/kenn-open-source-deep-research-prompt.md` (87 lines), not under a BASE path as earlier task context stated. Flagged for the record; no action.
2. **Marker drift.** Spec §4 defines `[V]/[I]/[U]`; the executed lanes use `[V]/[R]/[I]/[?]` — `[U]` was superseded by `[?]` and `[R]` (carried, not re-fetched) was added mid-pass. This synthesis follows the lane convention.
3. **Lane numbering differs from the spec.** Spec §3: 02=audio understanding, 03=mix, 04=teaching, 05=conversation, 06=synthesis. Executed: 02=local brain+voice, 03=audio understanding, 04=teaching, 05=mix, 06=conversation. Citations in §2/§3 use executed numbering plus the lane filenames.
4. **Plan edits: drafted, reviewed, then applied.** Spec §5.3 asked for minimal additive KENN_PLAN.md edits. This pass itself wrote none (drafts pending oracle review); after review the drafts were applied additive-only on 15 Oct 2026 (E-01…E-13; see §8 status).
5. **Line-number drift.** All 13 anchors plus the E-11 table position were re-verified against the 3,733-line plan on 15 Oct 2026. Several seed numbers were off by one (E-04 spans L1291–1292; E-07→L2398; E-09→L2434; E-10→L2451; E-11 between L2868/L2869); §8 carries the verified numbers. At application the owner had edited the plan again (3,737 lines pre-insert; 3,799 after): every insert anchored by quote, so these numbers are reading aids only.
6. **Definition-of-done audit vs spec §6.** Lanes 01 and 04 skeletons are filled (no "skel"/"(expand)" markers remain; lane 04 records the audit, md5 `ca3c79025d3c24b7c30bbbf13d7f4951`); every candidate in §2/§3 carries licence (code + weights), M3 fit basis, effort and first step either in its lane or in this synthesis; `[V]` claims carry URLs and dates in the lane notes; owner questions are collected in §6; nothing was installed, no source touched, no Live writes.
7. **Supersession note.** `KENN_OPEN_SOURCE_CAPABILITY_LANDSCAPE_2026-10-15.md` (785 lines) predates the lane takeover reviews; where they conflict this document and the lane notes win. The landscape doc's four-lane provenance (01/02/03/04 at write time) did not include the finished 05 and 06 lanes.
