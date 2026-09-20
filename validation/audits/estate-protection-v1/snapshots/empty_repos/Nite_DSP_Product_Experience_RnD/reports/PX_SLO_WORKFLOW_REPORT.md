# PX-A - SLO Workflow Report

## Status

**PASS WITH LIMITATIONS**

SLO has a strong existing sample-intelligence core. The main measured opportunity is the common text-search path, not a wholesale MAP rewrite. No production SLO files were modified.

## Evidence

### OBSERVED

- `Nite_DSP/Nite_DSP_01/SmartSampleManager/Source/PrecisionBrowser.cpp` and `SampleCanvas.cpp` perform case-insensitive substring matching over concatenated metadata. The path is an O(N) scan with no text relevance ranking.
- Structured category filters and Smart Collection rules exist in `SampleManagerEngine`.
- `SampleManagerEngine::findSimilarSamples` uses a runtime HNSW index over 512-dimensional PANNs embeddings. Weighted and refined similarity variants also exist.
- The MAP uses cached static rendering, QuadTree viewport queries, semantic label thresholds, and reusable scratch vectors. A source comment reports approximately 85 ms for an uncached 5,000-point repaint and approximately 1 ms for a cached blit; this is source evidence, not an independently repeated measurement.
- Favourites, preview history, saved collections, and user tag overrides persist in the SQLite cache.
- Audition is prepared on the message thread, supports quantised beat starts and BPM-based playback-rate matching, and has no looping or loudness normalisation in the audited path.
- Browser and canvas drag the original file. Waveform slice drag exports a temporary slice file. Metadata sidecar support exists separately through `AbletonXmpWriter`; it is not attached to the native drag operation.
- Editor-level shortcuts exist for search, audition, favourite, similar, and browser movement. Canvas keyboard selection and MAP focus traversal were not found.

### MEASURED PROXY

The isolated benchmark in [search_and_map_results.json](../benchmarks/search_and_map_results.json) used deterministic fixtures at 500, 2,000, 5,000, 10,000, and 25,000 samples.

At 25,000 samples:

- Worst-query linear substring median: **241.9812 ms**.
- Exact-token candidate median for the same query: **6.4816 ms**.
- Full point-scan MAP proxy: **11.9241 ms**.
- Cell-cull MAP proxy: **0.3452 ms**.

The candidate token path did not preserve exact substring semantics: the numeric `120` query produced a different match count. This is a parity gap, not a reason to ship the candidate unchanged.

## Required Closeout

### TIME-TO-SAMPLE

A full human intent-to-useful-sample time was not measured. The search-response proxy moved from 241.9812 ms to 6.4816 ms at 25,000 synthetic records, but that is not a human time-to-sample result. The next real measure must include audition start, decision time, and drag initiation.

### FIND SIMILAR

**EXISTS and is technically mature.** HNSW retrieval, reference-file search, weighted/refined variants, results-panel presentation, MAP emphasis, and an honest unavailable state are present. The remaining workflow work is to reduce the path from selected sample to audition to native drag and to measure acceptance, not to add another similarity mode immediately.

### FIND COMPLEMENT

**ABSENT as a production SLO capability.** It is a credible hypothesis because KENN/AutoMix already produces relationship and masking evidence, but it would add a new semantic mode. Keep it as a typed, evidence-backed experiment. Promotion requires candidate usefulness, false-positive review, and human time-to-useful-sample evidence.

### MAP

**EXISTS and should be preserved.** Existing culling and cached layers are the right direction. The proxy supports bounded work, but it does not exercise JUCE, the production QuadTree, text labels, or 60 Hz interaction on representative hardware. Add frame-time telemetry with median, P95, P99, and meaningful worst spikes before changing the renderer.

### DRAG-TO-DAW

**EXISTS for original files and waveform slices.** The shortest safe path today is search, audition, select, native external drag. Processed-preview drag and metadata transfer are not a single coherent workflow. A future experiment should make the source/preview choice explicit and preserve a recoverable temporary artifact without changing production filesystem behavior.

## Top 5 SLO Workflow Improvements

1. Add a production-shaped, semantics-preserving search index with substring/fuzzy parity tests and relevance ranking.
2. Make the selected result the shared object across list, MAP, audition, and drag, including clear focus and keyboard state.
3. Add a keyboard-complete MAP path: focus entry, pan/zoom, point navigation, selection, audition, and drag command.
4. Measure and improve audition start, including optional loop and gain-normalised preview modes that never obscure original-source identity.
5. Run a narrow Find Complement pilot using measured issue evidence and sample features; do not expose it as a generic second search mode until it proves value.

## Promotion Decision

Promote search-index and keyboard/focus spikes to engineering discovery. Continue R&D on Find Complement, processed-preview drag, and MAP interaction. Do not promote a broad new dashboard or additional search modes from this audit alone.

## Artifacts

- [search_and_map_benchmark.py](../benchmarks/search_and_map_benchmark.py)
- [search_and_map_results.json](../benchmarks/search_and_map_results.json)
- [EXPERIMENT_REGISTRY.json](../controller/EXPERIMENT_REGISTRY.json)
