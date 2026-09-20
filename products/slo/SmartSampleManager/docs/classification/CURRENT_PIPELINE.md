# NITE DSP SLO — Current Pipeline Cartography

This document traces the exact end-to-end pipeline of the Sample Library Optimiser (SLO) from file discovery to cache storage, search, and visualization.

```mermaid
graph TD
    A[File Queue / Directory Discovery] --> B{Cache Hit Check}
    B -- Yes (Hit) --> C{Check Versions Current?}
    C -- Yes --> D[Skip Decode & Inference]
    C -- No --> E[lightReanalyzeFile: Selective Re-Analysis]
    B -- No (Miss) --> F[Read format-aware metadata when available]
    F --> G[Load & Resample Waveform 32kHz mono]
    G --> H[analyzeAudioProperties: DSP Features]
    H --> I[Detect Key / BPM]
    I --> J{instrumentType == "Unknown"?}
    J -- Yes --> K[Filename / Folder Heuristic Classifier]
    K --> L{Heuristic Match?}
    L -- No --> M[classifyAudioFeatures: DSP Fallback]
    L -- Yes --> N[AbletonTaxonomy::classify]
    J -- No --> N
    M --> N
    E --> O[Queue to InferenceWorker]
    D --> O
    N --> O
    O --> P[ONNX embedding + acoustic head/OOD gate]
    P --> Q[SQLite Batch Upsert]
    Q --> R[Coordinate UMAP Projection & HNSW Indexing]
    R --> S[Canvas UI / Similarity Search]
```

---

## 1. File Discovery
* **Class/Function**: `SampleManagerEngine::addPathToQueue(const std::string& path)`
* **Thread**: Message Thread / UI Thread.
* **Input**: An absolute file path or directory path.
* **Output**: Files whose extensions are registered by the engine's `juce::AudioFormatManager` are added to `pendingFiles`, and parallel background jobs are scheduled. The directory wildcard is derived from the registered formats rather than a hard-coded WAV list.
* **Failure Path**: Non-existent paths, unregistered extensions, symlink paths, and files that later fail decoding are skipped without entering the library. Symlinked audio discovered inside a scanned directory is also excluded, preventing a library scan from widening into another filesystem location.
* **Admission Idempotency**: A path is coalesced from admission through inference commit, so overlapping UI rescans cannot schedule duplicate work or create duplicate in-memory rows. Once the prior work commits, a later rescan remains allowed and uses the normal path/mtime/size cache identity check to detect changes.
* **Fallback**: The engine admits only formats it can decode through the registered JUCE reader path.
* **Cache Interaction**: None.
* **Tests**: `test_path_traversal_main.cpp`, `test_prune_missing_main.cpp`, and the mixed-format admission regression in `test_format_aware_scan_main.cpp` (duplicate admission, symlink rejection, unsupported extension, malformed FLAC, and WAV/AIFF/FLAC coverage).

---

## 2. Validation & Cache Check
* **Class/Function**: `SampleManagerEngine::prepareFile(const std::string& filePath)` calling `tryLoadFromCache()`
* **Thread**: Parallel worker threads of `scanPool`.
* **Input**: File path.
* **Output**: A hydrated `SampleItem` if cached, or execution continues to decoding.
* **Cache Interaction**: Fast read from SQLite `sample_cache` using file path, modification time (`mtime`), and `size` as the composite key.
* **Selective Update (Version Enforcement)**: If a cache hit is found, it validates that `featureVersion == kFeatureAnalysisVersion` and `taxonomyVersion == AbletonTaxonomy::kTaxonomyVersion`. If either is stale, `lightReanalyzeFile` rereads format-aware metadata, selectively updates stale DSP/taxonomy fields, and preserves the existing 512D embedding. User overrides remain frozen.

---

## 3. Audio Decoding & Preprocessing
* **Class/Function**: `SampleManagerEngine::loadAndResampleWaveform()` using the engine's registered JUCE audio readers
* **Thread**: `scanPool` worker thread.
* **Input**: File path, target sample rate (32000.0 Hz), target sample count (160000 samples for 5 seconds).
* **Output**: Monophonic `std::vector<float>` waveform, `contentHash` (64-bit FNV-1a hash of mono PCM before resampling), and `durationSeconds`.
* **Failure Path**: Corrupt headers or zero-byte files cause decoding to fail, returning an empty vector. It logs a warning via `AppLogger::getInstance().logWarning()` and exits gracefully without crashing the scan.
* **Mono Conversion**: Left/right channels are averaged. The same registered-format reader boundary is used for WAV, AIFF, FLAC, and any other format explicitly enabled by the build.

---

## 4. DSP Feature Extraction
* **Class/Function**: `analyzeAudioProperties(const std::string& filePath)`
* **Thread**: `scanPool` worker thread.
* **Input**: File path.
* **Output**: `AudioAnalysisResult` containing peak/RMS amplitudes, spectral centroid, spectral rolloff, zero-crossing rate, crest factor, onset count (via Bello-style spectral flux peak-picking proxy), sample rate, channels, and bit depth.
* **Note**: This performs a *second* full decode of the same file to extract native-resolution properties (rather than resampled 32kHz clip properties).

---

## 5. Metadata, Key, and BPM Detection
* **Class/Function**: `readAudioMetadata()` using TagLib's RIFF/WAV ID3 path or format-neutral `PropertyMap`, then `parseKeyFromFilename()`, `parseBpmFromFilename()`, and `detectKeyFromAudio()`
* **Thread**: `scanPool` worker thread.
* **Input**: File path and the resampled waveform.
* **Output**: BPM and Key. BPM is only retained for loop-like material; one-shots,
  FX, atmospheres, and other non-loop samples remain tempo-unknown. A user tag
  override is the intentional exception and remains authoritative.
  Key output uses an autocorrelation pitch prior plus a conservative chroma
  profile comparison for major/minor mode; an isolated single-note hit remains
  a note name (mode is only meaningful when the evidence supports it).
* **Priority**:
  1. Reads existing embedded metadata via TagLib. WAV retains the project-specific ID3 `InstrumentType` frame; non-WAV formats use recognized `PropertyMap` keys such as `BPM`, `TEMPO`, `KEY`, `INITIALKEY`, `INSTRUMENTTYPE`, and `INSTRUMENT`.
  2. If missing, attempts to parse from the filename via regex tokenization.
  3. If key is still missing, runs `detectKeyFromAudio()`. If BPM is still missing,
  the acoustic estimator uses the true decoded duration capped at the model's
  5-second window and, for longer files, a second view capped at 20 seconds;
  an estimate is retained only when the views agree within 2 BPM. Otherwise
  BPM remains unknown (`0.0f`). The fixed model-padding silence is excluded
  from the short tempo view.
  An ML-OOD taxonomy abstention does not erase a measured BPM when an explicit
  loop token still provides structural loop evidence; OOD only withholds the
  semantic class.
* **Format limitation**: Metadata availability remains container-dependent. Non-WAV files with unrecognized or malformed properties fall through safely to filename/DSP/ML evidence; the reader does not infer metadata from arbitrary unsupported fields.

---

## 6. Classification Systems
* **Class/Function**: `SampleManagerEngine::prepareFile`, `AbletonTaxonomy::classify`, `AcousticClassifier::classify`, and `MlOverrideGate::evaluate`
* **Thread**: `scanPool` worker thread.
* **Input**: `loadedSample.name`, `parentFolder`, `AudioFeatures` (ZCR, low/high energy ratios, decay time, pitch sweep).
* **Output**: `category`, `subcategory`, `secondaryTags`, `tagConfidence`, `tagSource`, `winningEvidence`, and `taxonomyVersion`.
* **Evidence cascade**: User overrides are frozen. Otherwise embedded metadata is preferred, then filename/folder tokens, then the DSP fallback. `AbletonTaxonomy::classify` maps the resolved legacy instrument value to the product taxonomy and adds loop/one-shot evidence.
* **Acoustic ML path**: A valid 512D PANNs embedding is evaluated by the frozen 16-class `AcousticClassifier` head. A sufficiently confident, non-OOD result can override DSP/folder evidence; strong filename/metadata evidence is preserved. The centroid OOD gate can instead clear the derived taxonomy and expose an explicit review/unknown state.
* **Taxonomy boundary**: The product taxonomy contains 17 subcategories, while the current acoustic head contains 16 trained classes. `Atmosphere` is intentionally not emitted by the head and remains an evidence-bounded heuristic taxonomy result. This is a qualification limitation, not evidence that the head covers all 17 classes.
* **Fine-grained tags**: 808/Reese, kick length, bass timbre, and hi-hat type are additive only where their separate evidence reports support them; they do not expand the primary taxonomy claim.

---

## 7. Inference Pipeline, Embeddings & ML Classification
* **Class/Function**: `InferenceWorker::run()`, `SampleManagerEngine::runInferenceBatch()`
* **Thread**: Dedicated `SampleManagerEngine-Inference` background thread.
* **Input**: Batches of `PendingInference` containing resampled waveforms.
* **Output**: 512D float embeddings from the `fc1` layer of the ONNX `panns_cnn10_embedding` model, followed by deterministic acoustic-head classification and centroid OOD evaluation. Margin, entropy, centroid similarity, and logit energy are recorded as research diagnostics; only the centroid gate currently affects production decisions.
* **Safety**: Null, zero-norm, non-finite, and arithmetic-overflow-scale embeddings are rejected before classification, cache persistence, similarity indexing, or UMAP.
* **Note**: Skips the ONNX runtime call for files with `embeddingAlreadyKnown == true`, but a stale cached ML taxonomy is re-evaluated from the persisted valid embedding.

---

## 8. Cache Persistence
* **Class/Function**: `SampleManagerEngine::upsertCacheEntries()`
* **Thread**: `InferenceWorker` thread.
* **Input**: Batches of processed sample items.
* **Output**: Inserted/updated rows in SQLite `sample_cache` table under `cacheDbLock`.

---

## 9. Spatial Indexing & Visualization (UMAP & HNSW)
* **Class/Function**: `SampleManagerEngine::run()` coordinator thread loop, calling `placeNewSamplesIncrementally()` or `runFullUMAP()` and `rebuildHnswIndexFull()`
* **Thread**: Coordinator Thread (`SampleManagerEngine` thread).
* **Input**: All processed sample embeddings.
* **Output**: 2D coordinate projections (`umap_x`, `umap_y`) and updated HNSW index for similarity queries.
