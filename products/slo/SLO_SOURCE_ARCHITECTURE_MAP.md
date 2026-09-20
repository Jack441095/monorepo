# SLO Source Architecture Map

## Audit qualification note

The shared engine-core object-library build optimization is source-visible and preserves the intended compile-time dependency graph, but the current clean Release link is not qualified: helper-based engine tests duplicate JUCE module objects and report 13,044 duplicate symbols. This is a P0 build blocker to resolve before relying on the full qualification groups.

Audit: SLO Full Product, Classification & Beta-Readiness Audit V1  
Canonical product path: `/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo`  
Current source checkout: `products/slo/SmartSampleManager`  
Current HEAD: `dd60ddb31c66d8ee43f318764c0ac1f9eb972eef`

## Product identity

SLO is the single product formerly named Smart Sample Manager. The current JUCE
bundle/product identifiers retain `Smart Sample Manager`, `com.nitedsp.smartsamplemanager`,
manufacturer `NDSP`, plugin code `AtSm`, and version `1.0.0`. Historical source and
artifact names are provenance, not a separate product.

## Runtime/data flow

```text
WAV path / drag-and-drop
        |
        v
SampleManagerEngine -- TagLib metadata + dr_wav decode + DSP features
        |                         |
        |                         +--> AbletonTaxonomy category/subcategory/tags
        |                         +--> filename/folder/embedded metadata evidence
        v
PANNs CNN10 ONNX embedding (512-D, background inference worker)
        |
        v
AcousticClassifier frozen 16-class linear head + centroid OOD gate
        |
        v
SQLite cache + HNSW/UMAP search state + JUCE editor/UI
        |
        +--> optional confirmed Sort Library move/rename operation
        +--> audition playback prepared off the audio thread
```

## Components

| Area | Canonical implementation | Role |
|---|---|---|
| JUCE app/plugin | `SmartSampleManager/Source/PluginProcessor.*`, `PluginEditor.*` | AU/VST3/Standalone wrapper, UI, state, host integration |
| Audio processor | `PluginProcessor.cpp::processBlock` | Clears input, synchronises playhead, mixes prepared audition playback |
| Library engine | `SampleManagerEngine.*` | Scan queue, metadata, classification, cache, search, sort, recovery |
| Taxonomy | `AbletonTaxonomy.*` | Canonical category/subcategory/loop-vs-one-shot mapping; taxonomy version 2 |
| Acoustic head | `AcousticClassifier.h`, `AcousticClassifierWeights.h` | 16-class softmax head over 512-D embeddings; temperature `0.686393678188324` |
| OOD gate | `AcousticClassifierCentroids.h`, `MlOverrideGate.h` | Nearest-centroid cosine score and shrunk per-class thresholds; OOD clears weak labels |
| Audio features | `SampleManagerEngine.cpp`, `VectorMath.*` | WAV decode/resampling, energy, pitch/key, BPM, decay, ZCR and related heuristics |
| Model runtime | ONNX Runtime 1.29.0; bundled `panns_cnn10_embedding.onnx` + `.data` | Local embedding inference; CoreML may service supported graph partitions |
| File metadata | TagLib 2.3.1 | Read/write metadata and XMP/Ableton sidecar support |
| Database/cache | SQLite system library, WAL mode | Sample rows, embeddings, metadata, favorites/history/collections/overrides |
| Search/index | HNSW plus UMAP/knncolle/umappp | Similarity search and 2-D map placement |
| File operations | `reorganizeSamples*`, `sanitizePathComponent` | Confirmed move/rename or copy path; traversal guards and cancellation |
| Model bundle | `Models/panns_cnn10_embedding.onnx[.data]` | Production model only; CLAP/foundation probe is research evidence, not shipped |
| Packaging | CMake, `bundle_apple_deps.py`, release manifest/architecture guards | AU/VST3/Standalone bundles, transitive dylib bundling, no auto-install by default |
| Tests | 31 CMake test/benchmark executables, direct runners, Python benchmark tooling | Unit, integration, cache/safety, classifier parity, benchmark and research evidence |
| Research lineage | V4-F/G/H reports, V5 research docs, foundation-probe worktree | Evidence only; not production runtime and not used as a replacement classifier |

## Build targets

`CMakeLists.txt` defines one JUCE plugin target with AU, VST3 and Standalone
formats, plus 31 test/benchmark executables. The current build graph uses shared
test/prod engine object cores and explicit dependencies on the generated
`JuceHeader.h`. The audit’s clean build root is outside the checkout at
`workspace/builds/slo-audit-v1` with plugin auto-install disabled.

## Cache identity and safety

The runtime cache defaults to JUCE’s user application data location resolved on
this machine as `~/Library/SmartSampleManager/sample_cache.sqlite3`. Tests can
override the cache directory, and the test binaries are compile-time guarded
against opening the production cache. Model-version and taxonomy-version fields
are persisted and checked. Corruption is quarantined and user state is salvaged
and restored by the recovery path.

## Research/superseded systems

V5, CLAP, foundation-probe, fusion and active-learning material is present in
reports/tools/worktrees, but no production C++ path references those approaches.
The production classifier is the V4-H frozen hybrid path described above. AL-001
and AL-002 remain evidence-policy-controlled; this audit does not expose protected
labels or rerun one-shot holdouts.

## Evidence limitations

The repository contains many historical reports from different branches and
dirty states. They are cited as prior evidence only when their split and status
are explicit. Current audit execution is isolated, read-mostly, and does not use
owner audio or production cache state.
