# MiniMax Music 3 — KENN research note

**Date:** 2026-09-06
**Status:** Research only; no model weights downloaded and no runtime integration added.

## Summary

MiniMax Music 3 is a Chinese-origin, open-weight music-generation model from
MiniMax. It generates complete songs from lyrics plus a detailed music
description. It is a plausible future backend for KENN's existing AudioGen
workflow, but it should remain an optional external generation service rather
than being embedded in KENN's VST3 plug-in, real-time audio path, or core
analysis engine.

Primary references:

- [MiniMax-Music3 official repository](https://github.com/MiniMax-AI/MiniMax-Music3)
- [MiniMax-Music3 official Hugging Face model card](https://huggingface.co/MiniMaxAI/MiniMax-Music3)
- [MiniMax-Music3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-Music3/blob/main/LICENSE)
- [SGLang-Omni MiniMax Music 3 deployment guide](https://github.com/sgl-project/sglang-omni/blob/main/docs/cookbook/minimax_music3.md)
- [MiniMax structured caption rewriter](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/skills/music-caption-rewriter/SKILL.md)

## Model architecture

The official model description identifies these major stages:

- An 8B Qwen3-based Global LLM models long-range musical structure and
  predicts the first semantic RVQ codebook.
- A 0.6B Local LLM/depth decoder predicts the remaining acoustic codebooks.
- The audio representation uses eight RVQ codebooks: one semantic codebook
  with 16,384 entries and seven acoustic codebooks with 1,024 entries each.
- Fused hidden states condition a roughly 2.4B Flow Matching synthesis stage.
- A Flow-VAE/DAC-derived decoder produces 32 kHz, 16-bit stereo WAV output.
- The intended generation range is complete songs up to approximately five
  minutes, with a maximum of 9,000 acoustic frames in the published serving
  contract.

This is a coupled text-to-music generation pipeline. The RVQ, hidden-state,
Flow Matching, and decoder components are not independently useful KENN
features without the surrounding model and checkpoint conventions. The model
card also states that generation is non-streaming and does not provide
reference-audio conditioning, so it is not currently a drop-in solution for
mix matching, cover/remix control, or live audio transformation.

## Hardware and deployment fit

The current KENN development machine is an Apple M3 MacBook Air with 16 GB
unified memory. PyTorch reports MPS availability but no CUDA device.

MiniMax's official serving path is CUDA-oriented and describes a two-GPU split:
the autoregressive stage on one GPU and Flow Matching/waveform decoding on the
other. SGLang-Omni documents both single-GPU colocation and dual-GPU serving,
but both paths still require CUDA. A community MLX/Apple-Silicon port may be
useful for experimentation, but it is not the official KENN deployment target
and should not be treated as a production dependency without parity and
quality testing.

Recommended deployment shape:

```text
KENN on Mac
  -> typed, asynchronous MiniMax provider request
  -> separate CUDA service (local Linux/NVIDIA host or remote worker)
  -> WAV + generation metadata
  -> KENN hashing, audition, analysis, and confirmation-gated Live import
```

## License and product constraints

The published MiniMax-Music3 Community License permits use, copying,
modification, merging, publication, distribution, sublicensing, and provision
of copies, subject to its conditions. Important product obligations include:

- Commercial products or services using the software must prominently display
  `MiniMax-Music3` in their user interface.
- Separate prior written authorization is required when aggregate yearly
  revenue from the relevant products/services and affiliates exceeds US$20M.
- A product or hosted service that lets third parties generate outputs must
  maintain reasonable, proportionate safeguards against infringing or otherwise
  prohibited uses and outputs.
- The license requires compliance with applicable law and third-party
  intellectual-property rights; it does not grant rights to the training data
  or to user-requested copyrighted material.

The license notes that the model was fine-tuned from Qwen3-8B (Apache 2.0),
that the DiT was modified from Stable Audio Tools (MIT), and that the VAE was
modified from DAC (MIT). Those upstream notices should remain part of any
distributed integration.

## What KENN should reuse

### 1. Provider adapter — recommended first implementation

Add MiniMax as an optional backend behind the existing AudioGen abstraction.
The adapter should call the model's OpenAI-compatible audio endpoint with:

- original lyrics in `input`;
- a structured caption in `instructions`;
- an explicit seed;
- an explicit frame/duration limit;
- non-streaming WAV output.

The adapter should not expose raw model paths, arbitrary remote URLs, or model
internals to the LLM-facing context.

### 2. Structured music-caption contract

MiniMax's recommended caption format maps well to KENN's creative brief:

- `Global Metadata`: genre, subgenre, tempo, key/scale when known, emotional
  progression, and production profile;
- `Vocal Details`: vocal presence, timbre, register, delivery, harmony, and
  effects;
- `Arrangement`: section-by-section instrument entrances, exits, groove,
  energy, transitions, and spatial treatment.

KENN should adapt this contract into its own typed request rather than making
the model-specific prose format a privileged command path. Explicit user
constraints must be preserved, while unspecified BPM, key, vocal identity, or
instrumentation must remain unknown rather than being invented.

### 3. Existing KENN artifact and safety pipeline

Generated WAV output should pass through the existing KENN pattern:

1. asynchronous job record;
2. allowlisted artifact metadata;
3. content hash and provider/model version;
4. explicit `generated` provenance, separate from measured user audio;
5. local audition and KENN audio analysis;
6. optional comparison against another generated candidate;
7. confirmation-only proposal before any Ableton import;
8. readback, receipt, and undo if imported into Live.

Relevant KENN surfaces:

- [server.py](<LOCAL_VOLUME>/Shenrendao/KENN/apps/backend/src/kenn/server.py)
- [audiogen_artifacts.py](<LOCAL_VOLUME>/Shenrendao/KENN/apps/backend/src/kenn/core/audiogen_artifacts.py)
- [mcp_facade.py](<LOCAL_VOLUME>/Shenrendao/KENN/apps/backend/src/kenn/core/mcp_facade.py)
- [integrated audio architecture](<LOCAL_VOLUME>/Shenrendao/KENN/docs/KENN_INTEGRATED_AUDIO_INTELLIGENCE_ARCHITECTURE.md)

## What KENN should not reuse yet

- Do not place MiniMax inference in the VST3 audio callback.
- Do not bundle the full checkpoint into the KENN repository or plug-in.
- Do not transplant isolated RVQ/Flow-VAE/DiT code without the matching
  checkpoint, tensor layouts, scheduler, and decoder contracts.
- Do not treat generated audio as measured evidence about the user's mix.
- Do not assume that requested BPM, key, lyrics, instruments, or arrangement
  sections are guaranteed; the official model card explicitly describes these
  as generative controls rather than strict symbolic guarantees.
- Do not add reference-audio or streaming options to KENN's public contract
  until the selected backend actually supports and verifies them.

## Proposed implementation phases

### Phase A — dry-run adapter

- Define a provider-neutral `audio_generation_request.v1` and
  `audio_generation_result.v1`.
- Add a `MiniMaxMusic3Backend` using an injected HTTP client.
- Add mocked tests for request validation, timeout/failure handling, response
  format, hashing, and provenance.
- Keep the backend disabled unless explicitly configured.

### Phase B — external inference qualification

- Run the official or pinned SGLang/Diffusers path on a CUDA host.
- Generate short fixed-seed fixtures first, then longer songs.
- Measure latency, VRAM, output sample rate/channels, clipping, silence,
  stitching artefacts, and reproducibility.
- Record the exact model revision and serving runtime in each artifact.

### Phase C — KENN creative workflow

- Add structured-caption generation from KENN creative briefs.
- Expose generated candidates through existing audition/comparison routes.
- Add explicit user approval before any Live import.
- Add licensing attribution and generated-content disclosure to the UI.

## Current recommendation

Proceed with a thin, provider-agnostic MiniMax adapter and structured-caption
support. Keep the model weights and heavy inference runtime outside KENN until
there is a CUDA host, a pinned runtime, a licensing review for the intended
commercial distribution, and an audio-quality qualification set.

## Phase A implementation status (2026-09-07)

The dry-run boundary is now implemented in
`apps/backend/src/kenn/core/audio_generation.py`. It defines provider-neutral v1 request,
result, and structured-caption schemas; keeps missing BPM, key, scale, genre,
and vocal identity explicitly unknown; and enforces bounded duration,
non-streaming WAV output, timeout, artifact size, valid mono/stereo WAV
structure, SHA-256 identity, pinned-revision agreement, and generated/model
provenance. The `MiniMaxMusic3Backend` accepts only an injected transport and
is disabled by default, so this change adds no network call, checkpoint,
startup dependency, or Live mutation route. Ten focused tests use only mocked
responses.

Phase B remains intentionally unstarted: real inference still requires a
pinned CUDA service, license and attribution review, content safeguards, and a
listening qualification set. This boundary is infrastructure for that later
decision, not evidence that MiniMax improves KENN's current advice or that its
audio is ready for testers.
