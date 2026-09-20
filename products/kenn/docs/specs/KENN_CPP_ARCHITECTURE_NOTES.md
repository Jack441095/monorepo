# KENN C++ and Python Architecture Notes

## Decision

KENN should use a hybrid architecture. C++ should own performance-critical,
real-time audio processing. Python should own orchestration, reasoning,
knowledge retrieval, evaluation, and product workflow.

Do not rewrite KENN entirely in C++ before beta. First profile the current
system and move only measured bottlenecks behind stable interfaces.

## Strong C++ candidates

- real-time audio analysis inside the VST3 plugin;
- peak, RMS, loudness, and crest-factor measurement;
- FFT/STFT and spectral features;
- phase, polarity, correlation, stereo-width, and transient analysis;
- low-latency ring buffers and thread-safe audio snapshots;
- audio decoding and feature extraction if offline profiling shows a bottleneck;
- ONNX or other model inference later, if it becomes a measured performance
  bottleneck.

The existing `common/AudioTooRealtimeCore.h` and `plugins/kenn-vst3-au/` are the correct
starting point for this work.

## Keep in Python

- chat and conversational reasoning;
- audio-engineering knowledge retrieval;
- source collection and knowledge-base maintenance;
- Mix Review orchestration and report generation;
- evaluation and qualification scripts;
- beta feedback and analytics;
- API and server logic;
- experimental model and prompt work.

## Target architecture

```text
VST3 plugin
    ↓
C++ real-time analysis core
    ↓
structured feature/evidence payload
    ↓
Python Mix Review and knowledge layer
    ↓
KENN explanation, citations, and recommendations
```

The C++ core should be reusable by both the VST3 plugin and offline Mix Review
where practical. Python should consume a versioned, language-neutral evidence
contract rather than reaching into C++ implementation details.

## Real-time safety rules

The plugin audio thread must not perform:

- network calls;
- Python calls;
- filesystem access;
- JSON serialization;
- logging that can block;
- unpredictable memory allocation;
- blocking mutexes or other unbounded waits;
- model or knowledge-base retrieval.

Communication with Python, the chat service, or the knowledge base must happen
on non-audio threads using bounded queues, immutable snapshots, or another
explicitly tested handoff mechanism.

## Migration order

1. Profile current plugin and Mix Review performance.
2. Define the C++ feature/evidence contract.
3. Extract or complete the real-time analysis core.
4. Add thread-safety, sanitizer, numerical, and regression tests.
5. Connect the VST3 plugin to the core.
6. Add an offline adapter for Mix Review if it improves parity and reuse.
7. Compare C++ output against the current reference implementation.
8. Measure CPU, latency, memory, numerical stability, and host behaviour.
9. Keep the Python reference path available until parity is proven.
10. Only then consider moving additional processing into C++.

## Beta rule

For beta, prioritise correctness, evidence, safe failure, and reproducibility
over maximum speed. C++ work is beta-worthy only when it has measured benefit,
clear ownership, tests, rollback, and no new dependency on the old Audio_Too
estate.
