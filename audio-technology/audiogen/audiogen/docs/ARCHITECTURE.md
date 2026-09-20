# Architecture

This repository is a realtime generative music system with two main domains:

- **Composition (symbolic)**: generates a section plan and produces MIDI-like events (bass, chords, melody, arp, drone, counter).
- **Audio (render/mix/playback)**: renders those events via a sampler engine into audio, mixes with DAW-style sends/returns, and streams in realtime.

The core design is “DAW-like”: **instrument lanes → mixer strips (with sends) → return tracks → master bus**.

If you’re trying to understand “where harmony comes from” vs “what gets learned”, start with `docs/HARMONY_SOURCES.md`.

---

## Entry points and runtime modes

- **Realtime listen / interactive**: `main.py` (primary) creates config, audio graph, composition generator, and starts RT playback.
- **Alternate realtime entry**: `main_llm_chorus_only.py` (specialized run mode).
- **Offline multi-section songs**: `composition/song_generator.py` (`SongGenerator`) builds multiple sections by repeatedly calling the same section pipeline and offsetting events onto a global timeline.

---

## Top-level realtime flow

The main entrypoint is `main.py`.

### Startup (realtime mode)

1. Load and layer `CONFIG` (conversation preset / style profile / meta preset / CLI overrides).
2. `CONFIG.rebuild_samplers()` (best-effort) prepares sampler configs.
3. `AudioContainer.create_from_config(CONFIG)` wires the audio graph:
   - `audio/engine/mixer.py` → `AudioMixer` (strip gain/pan/EQ + send accumulators)
   - `audio/engine/reverb.py` → `RoomReverb` (shared reverb return)
   - `audio/engine/master_bus.py` → `MasterBus` (returns + master chain)
4. `composition/engine.py` → `CompositionGenerator` is created (planners + Markov + policies).
5. `audio/RT_player/player.py` → `PolyphonicPlayer` starts the realtime loop and schedules section/bar generation.

### Emotion = song identity (important)

In the current runtime, **emotions are song identities**, not just parameter presets.

- **Switching emotion** recalls that emotion’s cached arranged song (no regeneration).
- **Generating a new song for the current emotion** is an explicit action: `fresh` (alias `r`).
  - `fresh` **always** rolls a new random seed, even if the app was launched with `--seed`.

This behavior is implemented across:

- `main.py`: caches arranged songs per `(emotion, form, root, seed_base)` and returns cache hits.
- `realtime_cli.py`: emotion switches do **not** reseed when per-emotion identity is enabled; `fresh` forces a new random seed.
- `core/composition_config.py`: configuration surface for per-emotion identity (`per_emotion_song_identity_enabled`, form pool/map, seed salting).

### Per-bar realtime loop (conceptual)

For each bar:

1. **Generate**: create new symbolic events (usually section-aware) via `CompositionGenerator`.
2. **Render**: `audio/RT_player/renderer.py` → `AudioRenderer` renders events into per-channel buffers.
3. **Mix + FX**:
   - `AudioMixer.mix_audio(...)` → `(dry, reverb_send, delay_send, distortion_send)`
   - `MasterBus.process(...)` mixes returns and applies master processing
4. **Output**: final stereo bar audio to the device stream.

---

## Composition architecture (symbolic generation)

Primary orchestrator:

- `composition/engine.py` → `CompositionGenerator.generate_section(...)`

The generator delegates section construction to:

- `composition/section_planner/planner.py` → `SectionPlanner.build_section(...)`

`SectionPlanner.build_section` wraps:

- **Best-of-K sampling** / retries: `composition/section_planner/section_sampling.py`
- **Section scoring** (including optional “hook” scoring for chorus-like roles): `composition/section_scoring.py`
- **Timeline targets** (optional pop-style role contrast nudges): `composition/section_planner/timeline.py`

For a detailed, up-to-date, ordered walkthrough of the section pipeline, use:

- `COMPOSITION_GENERATION_PIPELINE.md`

### Emotion-driven composition vs “one song under different knobs”

The system supports an **emotion-driven** mode intended to make each emotion feel like an individual performance:

- `CONFIG.composition.emotion_driven_harmony_enabled`
  - disables role-based cadence rewrites and phrase-level function scaffolding (`T/PD/D`) when enabled
  - disables chord “guided start” priming from the chosen template (avoids shared openings)
- `composition/melody_runtime.py` in emotion-driven mode:
  - emotion+role dependent seed contour (not always `"static"`)
  - makes learned contour planning dominate (high strength) and applies deterministic contour rotations

Together with pool-only chord picking (see below) these remove the biggest “same phrases / same song” convergence mechanisms.

### High-level ordered stages (one section)

1. **Timeline + arrangement context** (role, per-bar targets, phrase spans)
2. **Harmony symbols + roots**: chord progression planning (`composition/chord_planner.py` via `composition/harmony_manager.py`)
3. **Voicing / voice-leading**: choose per-bar anchors (`composition/voice_leading_engine.py`, `composition/voice_leading_engine.py`)
4. **Harmonic snapshots**: `composition/harmonic_plan.py` (`refresh_harmonic_plan`, `refresh_harmonic_plan_comping`)
5. **Arp → melody → counter → bass → chord comping MIDI** (important ordering: chord comping is generated after melody so it can react to lead density)
6. **Finalize + QA**: merge, humanize/microtiming, range limiting, validations (`composition/event_pipeline.py`, `finalize_section_events` in the planner)

### Event format and channels

The common event tuple is:

- `(channel, midi, velocity, start_beats, duration_beats, notes)`

Typed equivalent:

- `composition/event.py` → `Event`

Default channel meanings:

- `0`: bass
- `1`: chords (poly events)
- `2`: lead melody
- `3`: arp
- `4`: drone
- `5`: counter melody / extra mono lane

---

## Markov melody subsystem

Melody generation uses a **two-chain** Markov approach (rhythm + interval) plus post-passes and coupling/rerank options.

- **Doc**: `MARKOV_MELODY_ARCHITECTURE.md`
- **Code**: `ai/markov/melody/` (note generator and phrase logic), integrated via `composition/melody_manager.py`

---

## Audio: sampling, rendering, mixing, mastering

### Sampling

Realtime rendering is sample playback (no time-stretching):

- `sampler/sampler.py` → `Sampler` (ADSR, velocity layers, optional looping/filters, pad “shimmer” option)
- `sampler/engine.py` → `SamplerEngine` (caching/loading + poly helpers)

### Renderer

- `audio/RT_player/renderer.py` → `AudioRenderer`
  - buckets mono vs poly (`audio/RT_player/render_pipeline.py`)
  - renders per-channel audio
  - calls mixer + master bus

### Mixer, sends/returns, master bus

- `audio/engine/mixer.py` → `AudioMixer` (dry mix + send buffers; supports pre/post-fader staging)
- `audio/engine/reverb.py` → `RoomReverb` (shared reverb return)
- `audio/engine/master_bus.py` → `MasterBus`
  - mixes returns (reverb/delay/distortion wet)
  - applies master chain (EQ, optional multiband via `audio/engine/multiband_adapter.py`, limiter/clip options)

### Wiring / container

- `audio/audio_container.py` → `AudioContainer` builds and wires the graph from `CONFIG` and translates strip configs into runtime mixer values.

---

## Configuration, presets, and live control

- **Config root**: `core/config.py` → `CONFIG`
  - composition knobs: `core/composition_config.py`
  - mixer defaults: `core/mixer_config.py`
  - post/fx presets: `core/post_processing_config.py`

Preset layers (overview in `COMMANDS.md`):

- **Conversation presets**: `data/conversation_presets.py` (+ `data/user_conversation_presets.json`)
- **Style profiles**: `data/sample_style_profiles.py`
- **Sample packs**: `data/sample_packs.py`
- **Meta presets**: `.audiogen/presets/*.json` (combine pack/style/convo/fx/macros)

Live tweaking uses the shared event bus:

- `audio/engine/__init__.py` exports `EVENT_BUS` (mixer/master subscribe to events).

---

## Realtime performance architecture (stability under load)

This repo is a realtime system, so it contains multiple **guardrails** to prevent runaway CPU spikes.

### Stress tiers (“normal / balanced / safe / emergency”)

- Implemented in `audio/RT_player/player.py` (`_runtime_generation_mode`).
- **Watchdog**: `rt_render_watchdog_*` triggers forced `safe` for a hold window when bar render time exceeds a ratio threshold.
- **Actions bundle**: the player logs a compact line when realtime actions change:
  - `RT actions: mode=... ratio=... watchdog=... culprit=... fast_master=... bypass_inserts=... reverb=... drop_ch=...`

### Targeted chord protection

When chord rendering is the dominant culprit and over-budget, the player can:

- **simplify chord voicings** (fewer tones) before dropping chords
- **cap chord sustain durations** (especially on long bars / slow tempos)
- **optionally drop the chord channel** as a last resort

These guardrails live in `audio/RT_player/player.py` and are configured via `core/config.py` (audio config).

### Sampler prefetch (warm cache, but never steal CPU)

- Background worker lives in `audio/RT_player/player.py`.
- Prefetch is **budgeted** (`prefetch_budget_ms`, `prefetch_max_items`, `prefetch_max_duration_sec`).
- If prefetch becomes harmful (single call too slow), it is temporarily disabled.
- Chord prefetch is off by default (can be expensive).

### Observability

- Runtime log: `logs/runtime.log`
- Summarizer: `tools/rt_log_health.py`
  - parses watchdog, slow bars (with culprit), RT action transitions, arranged preview usage, and prefetch stats.

## Training / retraining (current shape)

At runtime, harmony is **generated from curated pools and in-memory Markov fits**, not from scanning an external dataset.

- `composition/engine.py` has stubs for training hooks (e.g. `train_for_emotion(...)` is a no-op in the stock runtime path).
- For “what’s curated vs retrained”, see `docs/HARMONY_SOURCES.md`.

---

## Testing

The test suite includes end-to-end “generate → render” coverage:

- `tests/test_audio_pipeline.py` exercises `CompositionGenerator.generate_section(...)` + `AudioRenderer.render_bar(...)` and regressions around mixer/master bus behavior.

Run:

```bash
pytest
```

---

## Key files (index)

- **Entrypoint**: `main.py`
- **Realtime playback**: `audio/RT_player/player.py`, `audio/RT_player/renderer.py`
- **Composition**: `composition/engine.py`, `composition/section_planner/planner.py`
- **Harmony + voicing**: `composition/harmony_manager.py`, `composition/chord_planner.py`, `composition/voice_leading_engine.py`
- **Arp + melody**: `composition/arpeggiator_engine.py`, `composition/melody_manager.py`, `ai/markov/melody/`
- **Audio engine**: `sampler/engine.py`, `audio/engine/mixer.py`, `audio/engine/master_bus.py`, `audio/engine/reverb.py`
- **Config/presets**: `core/config.py`, `data/conversation_presets.py`, `data/sample_style_profiles.py`, `.audiogen/presets/`
