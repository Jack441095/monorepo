#pragma once

#include <JuceHeader.h>
#include <string>
#include <vector>
#include <queue>
#include <deque>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <functional>
#include <memory>
#include <thread>
#include "AbletonXmpWriter.h"
#include "PhysicalAcoustics.h"

// Forward declarations for ONNX Runtime to avoid including full headers in this header file
namespace Ort {
    class Env;
    class Session;
}

// DSP feature bundle computed by analyzeAudioBuffer() (SampleManagerEngine.cpp)
// and used internally by prepareFile()/AbletonTaxonomy::classify(). Declared
// here (moved from file-local scope in the .cpp) solely so
// analyzeFileForDiagnostics() below can expose it for offline calibration
// tooling -- see Fine-Grained Subcategorization V1's attribute-layer work.
// Not persisted per-sample in the cache; this is a diagnostic-only exposure,
// not a schema change.
struct AudioFeatures {
    float zcr = 0.0f;
    float lowEnergyRatio = 0.0f;
    float highEnergyRatio = 0.0f;
    float decayTimeSeconds = 0.0f;
    float pitchSweep = 0.0f;
    // Final-third / first-third energy. Feeds the loop-vs-one-shot decision;
    // see AbletonTaxonomy::detectLoopVsOneShot. 1.0 = sustained (safe default).
    float energyDecayRatio = 1.0f;
};

// Embedding pipeline outcome for one sample -- see docs/ONNX_FAILURE_HANDLING.md.
// Deliberately no "fake but plausible" state: a sample either has a real,
// model-produced embedding (Valid) or it doesn't (everything else), and
// nothing downstream (findSimilarSamples, duplicate detection) should ever
// treat a non-Valid embedding as meaningful.
enum class EmbeddingStatus {
    NotAnalysed,      // never attempted yet
    Valid,             // real ONNX-produced embedding present
    FailedRetryable,   // inference failed; will be retried on next scan
    FailedPermanent    // failed repeatedly (see kMaxEmbeddingFailuresBeforePermanent);
                        // stops retrying every launch, surfaced to the user instead
};

// RECOVERY PHASE R2 -- Audio Feature Analysis contract (see
// docs/SLO_AUDIO_FEATURE_RECOVERY.md for evidence sources, equations, and
// units). Type name `AudioAnalysisResult`, member name `audioFeatures`,
// column name `feature_version`, and function name `analyzeAudioProperties`
// are all restored verbatim from surviving evidence: the type/column/
// version-constant names from docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md
// (a pre-incident design doc, dated 2026-08-14, describing the storage/
// versioning contract in detail but NOT the DSP equations themselves), the
// field set/units from the surviving Source/test_audio_features_main.cpp.
// No historical DSP implementation source survived, so
// analyzeAudioProperties() in SampleManagerEngine.cpp is a from-scratch
// REIMPLEMENTATION of a verified behavioural contract, not the exact
// historical DSP. Deliberately a distinct type from the pre-existing
// (unrelated, taxonomy-only) `AudioFeatures` struct local to
// SampleManagerEngine.cpp -- that one backs instrument-type/Ableton-taxonomy
// heuristics and is not part of this contract.
struct AudioAnalysisResult {
    float peakAmplitude = 0.0f;       // linear amplitude, max(|x[n]|), range (0, 1]
    float rmsAmplitude = 0.0f;        // linear amplitude, sqrt(mean(x[n]^2)), range (0, peakAmplitude]
    float spectralCentroid = 0.0f;    // Hz, magnitude-weighted mean frequency, averaged across analysis frames
    float spectralRolloff = 0.0f;     // Hz, frequency below which 85% of frame spectral energy lies, frame-averaged
    float zeroCrossingRate = 0.0f;    // crossings / (numSamples - 1), range [0, 1]
    float crestFactor = 1.0f;         // linear ratio peakAmplitude / rmsAmplitude, always >= 1.0
    int onsetCount = 0;               // UNKNOWN HISTORICAL SEMANTICS -- reimplemented as a spectral-flux
                                       // peak-picking proxy (Bello-style adaptive threshold); see recovery doc.
    double originalSampleRate = 0.0;  // Hz, from the source file's own header (not the analysis/embedding rate)
    int originalChannels = 0;         // channel count from the source file's own header
    int originalBitDepth = 0;         // bits per sample from the source file's own header
    // Added post-recovery, not part of the restored R2 contract: seconds
    // from the amplitude envelope's peak to where it drops below 10% of
    // that peak. Computed by the same shared helper (see
    // computeEnvelopeDecayTimeSeconds() in SampleManagerEngine.cpp) as the
    // taxonomy-only AudioFeatures::decayTimeSeconds above -- numerically
    // identical for the same file, just exposed here for the predicted-tags
    // system too. See docs/classification/DECAY_TIME_ENVELOPE_FIX_V1_REPORT.md
    // and docs/classification/DECAY_ATTRIBUTE_TAG_V1_REPORT.md.
    float decayTimeSeconds = 0.0f;
    // Energy in the final third / first third of the file. A one-shot decays
    // toward silence (crash ~0.00); a loop sustains (~0.87). Feeds
    // AbletonTaxonomy::detectLoopVsOneShot, which measures 96.4% held-out with
    // it versus 90.8% on duration alone. Default 1.0 ("sustained") so a legacy
    // row without a stored value is not spuriously demoted to one-shot.
    float energyDecayRatio = 1.0f;
    
    // Pearson correlation between L and R channels, range [-1, 1]. 1.0 =
    // identical channels (mono-compatible, whether genuinely mono-summed
    // or literally mono content stored in a stereo container); lower/
    // negative values indicate a decorrelated, wide stereo image. Defaults
    // to 1.0 (mono-compatible) since that's the correct value for a
    // genuinely mono source file (originalChannels == 1), not just a safe
    // placeholder. See docs/classification/WIDE_MONO_ATTRIBUTE_TAG_V1_REPORT.md.
    float stereoCorrelation = 1.0f;

    // Versioned FFT evidence used by conditional taxonomy/attribute layers.
    // Kept outside the frozen 520-D acoustic head until a retrained head
    // proves a repeatable grouped-CV gain. Ratios are frame-averaged
    // magnitude-energy bands; flux values are gain-normalised.
    float lowBandEnergyRatio = 0.0f;    // <150 Hz
    float midBandEnergyRatio = 0.0f;    // 150 Hz .. 2 kHz
    float highBandEnergyRatio = 0.0f;   // >2 kHz
    float spectralFluxMean = 0.0f;      // mean positive spectral change/frame
    float spectralFluxStd = 0.0f;       // standard deviation of normalised flux
    float spectralFluxPeakRate = 0.0f;  // adaptive flux peaks per second
    PhysicalAcoustics::Analysis physics;
};

// Bump when DSP extraction or the metadata-evidence contract changes in a way
// that makes previously-persisted analysis rows semantically stale. The
// selective cache refresh uses this version to reread format-aware metadata
// as well as recompute native DSP features.
// 4: decayTimeSeconds is now persisted (decay_time_seconds column) because it
// feeds DSP dim 5 of the 520-D acoustic classifier input. Rows written at
// version 3 have no stored decay, so they must be re-analysed rather than
// classified with the duration fallback.
// 5: physical-acoustics class/material measurements are persisted for
// smart-collection filtering and cold-start hydration.
// Bumped when deterministic DSP-derived metadata changes. Version 6 adds the
// conservative chroma major/minor key-mode pass, and version 7 persists the
// gain-invariant FFT evidence sidecar used by conditional classification and
// predicted-tag layers. The frozen acoustic head remains 520-D.
static constexpr int kFeatureAnalysisVersion = 8;

// RECOVERY PHASE R3 -- Cache Version Enforcement (brief section 57-64; see
// docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §3, a pre-incident design
// doc that documented this exact version-domain split -- restored verbatim
// from that surviving evidence, not invented for R3). Bump only when the
// embedding model itself changes (e.g. swapping panns_cnn10_embedding.onnx
// for a different model/checkpoint) in a way that makes previously-persisted
// 512D embeddings incomparable to freshly-computed ones.
static constexpr int kEmbeddingModelVersion = 1;

// Semantic filename analysis helpers
juce::StringArray extractSemanticFilenameTokens(const juce::String& filename);
std::string parseKeyFromFilename(const std::string& filename);
float parseBpmFromFilename(const std::string& filename);
float estimateBpmFromAudio(const float* data, int numSamples, double sampleRate,
                           float trueContentDurationSeconds);

// Naming-only presentation rule: a tonal one-shot is a single note, not a
// scale/mode claim.  Thus "B Major" is rendered as "B" for one-shots while
// loops retain the full key/mode.  The stored key remains unchanged.
juce::String formatKeyForSampleName(const juce::String& key, bool oneShot);

juce::String getFormattedFilename(const juce::String& originalName,
                                  const juce::String& category,
                                  const juce::String& subcategory,
                                  const juce::String& key,
                                  float bpm,
                                  int namingStyle,
                                  int wwiseVariationNumber = 0);

struct SampleItem {
    std::string filePath;
    std::string name;
    float bpm = 0.0f;
    std::string key = "Unknown";
    std::string instrumentType = "Unknown";
    std::vector<float> embedding; // 512D; ONLY meaningful when embeddingStatus == Valid
    EmbeddingStatus embeddingStatus = EmbeddingStatus::NotAnalysed;
    int embeddingFailureCount = 0;
    // FNV-1a 64-bit hash (hex string) of the fully-decoded, mono-downmixed
    // PCM audio content -- independent of file path, filename, and metadata
    // tags, so a re-tagged or renamed copy of the same audio still matches.
    // Used for exact-duplicate detection (see findDuplicateGroups()). Empty
    // if the file failed to decode.
    std::string contentHash;

    // Ableton-oriented taxonomy classification (see AbletonTaxonomy.h) --
    // deliberately separate fields from instrumentType above (the
    // pre-existing single-string coarse classifier), not a replacement for
    // it, so nothing already reading instrumentType breaks.
    std::string category;                    // e.g. "Drums", "Bass", "Vocals" -- empty until classified
    std::string subcategory;                 // e.g. "Kick", "Bass One-Shot", "Vocal Phrase"
    std::vector<std::string> secondaryTags;   // e.g. {"Loop"}, {"One-Shot", "Electronic"}
    float durationSeconds = 0.0f;             // true original file duration -- NOT the fixed embedding window, which is padded/truncated to 5s
    float tagConfidence = 0.0f;               // 0..1, signal-agreement based -- see classifySampleTaxonomy()
    std::string tagSource = "unclassified";   // "unclassified" | "heuristic" | "ml_v3" | "ml_ood" | "user"
    bool tagUserOverridden = false;           // true once a user has manually edited the tags; classification must never overwrite these again
    std::string winningEvidence = "UNKNOWN";  // persisted provenance: "USER_OVERRIDE" | "EMBEDDED_METADATA" | "FILENAME" | "FOLDER" | "DSP" | "UNKNOWN"
    int taxonomyVersion = 0;                  // classifier version this row was produced under; 0 = not yet classified under this taxonomy system
    // Version of AcousticClassifierWeights.h that produced the persisted ML
    // decision. Separate from embeddingModelVersion so a changed linear head
    // can reclassify cached embeddings without another ONNX pass.
    int classificationModelVersion = 0;

    // V4-F QUALIFICATION DIAGNOSTICS ONLY -- populated alongside the existing
    // V4-D ML-override decision purely for benchmark instrumentation (see
    // ClassificationBenchmark). Never read by production classification
    // logic and never influences category/subcategory/winningEvidence --
    // recording these values does not change any decision the engine makes.
    std::string diagHeuristicCategoryPreML;    // category/subcategory/evidence/confidence as they
    std::string diagHeuristicSubcategoryPreML; // stood immediately before the V4-D ML-override check
    std::string diagHeuristicEvidencePreML;    // ran (i.e. the pre-V4-D-equivalent heuristic result).
    float diagHeuristicConfidencePreML = 0.0f;
    std::string diagMlSubcategory;             // AcousticClassifier::Result::subcategory, always recorded
    float diagMlConfidence = -1.0f;            // when an embedding was available (-1 = ML not evaluated)
    bool diagMlIsOod = false;
    bool diagMlEvaluated = false;
    bool diagMlOverrideApplied = false;        // true iff the ML result actually replaced the heuristic result
    // V4-G OOD-HARNESS DIAGNOSTICS ONLY -- same non-production-decision
    // contract as the V4-F fields above. AcousticClassifier::Result::margin/
    // entropy, recorded so the offline OOD evaluation harness (see
    // docs/SLO_CLASSIFICATION_V4G_OOD_REPORT.md) can compute AUROC/AUPR/
    // FPR@95TPR/coverage/selective-accuracy for multiple candidate OOD
    // scores without needing to re-run the ONNX model.
    float diagMlMargin = -1.0f;
    float diagMlEntropy = -1.0f;
    float diagMlLogitEnergy = 0.0f;            // research-only -logsumexp(logits)
    float diagMlCentroidCos = -2.0f;           // AcousticClassifier::Result::centroidCosineSimilarity;
                                                 // this now drives isOod (see AcousticClassifier.h)
    int diagMlNearestCentroid = -1;              // AcousticClassifier::Result::nearestCentroidIndex
                                                 // (which per-class threshold row applied); -1 = ML
                                                 // not evaluated. Same non-production contract.

    float x = 0.0f;
    float y = 0.0f;
    bool isProcessed = false;
    // True only when x/y were loaded from a persisted, still-valid UMAP
    // layout in the SQLite cache (see openCacheDb()'s umap_x/umap_y columns) --
    // distinguishes "genuinely projected at (0,0)" from "not yet projected",
    // since 0.0f/0.0f is itself a valid coordinate. Used to decide whether a
    // full UMAP recompute can be skipped entirely on app launch.
    bool umapPositionFromCache = false;

    // RECOVERY PHASE R2 -- see AudioAnalysisResult above. featureVersion==0
    // means "not yet analysed under the current contract" (fresh struct,
    // or a cache row written before this column existed / under an older
    // algorithm version -- see docs/SLO_AUDIO_FEATURE_RECOVERY.md's Cache
    // section for the known gap around forcing re-extraction on version
    // mismatch, deferred to R3).
    AudioAnalysisResult audioFeatures;
    int featureVersion = 0;

    // RECOVERY PHASE R3 -- Cache Version Enforcement. Which
    // kEmbeddingModelVersion produced `embedding`. 0 means "not yet set"
    // (fresh struct); a cache row from before this column existed is read
    // back as the *current* version, not 0 -- see tryLoadFromCache() and
    // docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §3's "legacy-row
    // handling differs by field" note for why that asymmetry with
    // featureVersion/taxonomyVersion is deliberate.
    int embeddingModelVersion = 0;
};

// Free function backing SampleManagerEngine::getPredictedTags() (see that
// method's comment) -- declared here, not just file-local to
// SampleManagerEngine.cpp, so tests can exercise it directly against
// synthetic SampleItem values without a full engine/decode pipeline.
std::vector<std::string> generatePredictedTags(const SampleItem& item);

// Samples that can actually participate in a UMAP projection: isProcessed with
// a Valid, numerically-safe embedding (see hasSafeEmbeddingBuffer()). Returns
// pointers into `samples` in stable order so every UMAP code path sizes its
// fixed-length buffers and writes coordinates back for the exact same set --
// a failed/retryable attempt is isProcessed==true with the embedding cleared
// (see docs/ONNX_FAILURE_HANDLING.md), so !isProcessed-based loops would
// write coordinates to the wrong items and read out of bounds. Declared here
// so tests can exercise the predicate directly against synthetic SampleItem
// values without running UMAP itself.
std::vector<SampleItem*> collectUmapEligibleSamples(std::vector<SampleItem>& samples);

// Writes row r of `embedding2d` (interleaved [x_r, y_r]) into
// samples[snapshotIndices[r]], but only after re-deriving the eligible set and
// confirming it is byte-for-byte the same as `snapshotIndices`. runFullUMAP()
// snapshots the eligible set under dbLock, releases the lock for the expensive
// umappp projection, then calls this to publish the result. If a scan/prune
// changed the eligible set while the projection ran lock-free, the snapshot's
// row->sample mapping is no longer valid, so this writes nothing and returns
// false. Callers must hold dbLock. Declared here so tests can drive the
// snapshot/guard contract with synthetic SampleItem values and a fake
// embedding2d, without running UMAP.
bool writeBackUmapCoordinates(std::vector<SampleItem>& samples,
                              const std::vector<size_t>& snapshotIndices,
                              const std::vector<double>& embedding2d);

// A set of two or more samples sharing the same contentHash -- i.e. the same
// underlying audio content, regardless of filename/path/metadata.
struct DuplicateGroup {
    std::string contentHash;
    std::vector<SampleItem> items;
};

// One preview-playback event, newest-first from getRecentPreviews(). Restored
// R1 -- see docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md (History).
struct PreviewHistoryEntry {
    std::string filePath;
    juce::int64 previewedAtMs = 0; // ms since epoch, juce::Time::getCurrentTime().toMilliseconds()
};

// Coarse engine lifecycle state, polled by the editor (see
// docs/ASYNC_STARTUP.md) instead of scattered booleans. Uninitialized only
// exists momentarily before initAsync() is called; Failed is reserved for a
// future case where even basic engine setup can't proceed (not currently
// reachable -- a missing/corrupt ONNX model degrades to Degraded, not
// Failed, since browsing/metadata search stay fully functional).
enum class EngineInitState { Uninitialized, Initializing, Ready, Degraded, Failed };

class SampleManagerEngine : public juce::Thread {
public:
    SampleManagerEngine();
    ~SampleManagerEngine() override;

    // Synchronous model+session load -- does the actual work. Prefer
    // initAsync() (below) for real use; this is kept public mainly because
    // the test suite calls it directly and doesn't need to poll async state.
    bool init(const std::string& customModelPath = "");

    // Starts init() on a background thread and returns immediately -- see
    // docs/ASYNC_STARTUP.md. Safe to call from PluginProcessor's constructor:
    // scanning/decoding/metadata work queued before this completes is not
    // blocked (only embedding generation needs the model), and every engine
    // entry point already tolerates the model not being ready yet.
    void initAsync(const std::string& customModelPath = "");

    EngineInitState getEngineState() const { return engineState.load(std::memory_order_acquire); }

    // True only once the model has finished loading successfully -- see
    // docs/ONNX_FAILURE_HANDLING.md. When false, no sample will ever get a
    // Valid embedding; callers (the editor) should surface this clearly
    // rather than let similarity features look silently broken/empty.
    bool isEmbeddingModelAvailable() const { return getEngineState() == EngineInitState::Ready; }

    // Add audio file or directory path to the import queue
    void addPathToQueue(const std::string& path);

    // Removes samples whose underlying file no longer exists on available
    // storage (moved or deleted outside the app since the last scan) -- "detect deleted
    // samples", scoped to what's safely, synchronously checkable: this does
    // NOT watch folders live, it's a manual/periodic "clean up now" pass.
    // Records on a disconnected external volume are preserved.
    // Never touches anything on disk itself, only the in-memory/cached
    // sample list. Returns how many were removed.
    int pruneMissingFiles();
    int getLastPruneUnavailableStorageCount() const
    {
        return lastPruneUnavailableStorageCount.load(std::memory_order_relaxed);
    }

    // "Sounds like this" -- returns up to k samples whose embeddings are
    // acoustically closest (L2 distance in the 512D PANNs embedding space)
    // to the sample at filePath, nearest first, excluding the query sample
    // itself. Reuses the same HNSW index already maintained for incremental
    // UMAP placement (see rebuildHnswIndexFull/placeNewSamplesIncrementally)
    // rather than building a second one. Returns an empty vector if the
    // query sample isn't found/processed, or if the index isn't ready yet
    // (e.g. called before any scan has completed).
    std::vector<SampleItem> findSimilarSamples(const std::string& filePath, size_t k = 20);

    // O(1) path->index helpers backing pathToIndex. Callers must already hold
    // dbLock (they touch `samples` and `pathToIndex` together). findSampleIndex
    // returns SIZE_MAX when the path is absent.
    static constexpr size_t kSampleIndexNotFound = static_cast<size_t>(-1);
    size_t findSampleIndex(const std::string& filePath) const;
    void rebuildPathIndex();

    // RECOVERY PHASE R3-A -- Weighted Find Similar (brief section 14-24; see
    // docs/SMART_SAMPLE_MANAGER_FEATURE_ROADMAP.md's V1.1 "Find Similar 2.0"
    // entry -- surviving evidence: "Expose weights to combine ML embeddings
    // with deterministic DSP features. Let users filter search results by
    // brightness (spectral centroid), punchiness (crest factor), or
    // transient count (onsets)"). Per-field weight knobs the caller sets to
    // bias which restored R2 AudioAnalysisResult fields matter for a given
    // query -- ONLY the three fields the roadmap doc names are exposed here
    // (brief section 16: do not include Rolloff just because R2 now exposes
    // it, without evidence it participated historically). All default to
    // 0 (no DSP contribution beyond whatever dspWeight itself is set to in
    // findSimilarWeighted -- see there for how these combine).
    struct FeatureWeights {
        float spectralCentroidWeight = 0.0f; // brightness
        float crestFactorWeight = 0.0f;      // punchiness
        float onsetCountWeight = 0.0f;       // transient density
    };

    // "Sounds like this, but weighted" -- same HNSW embedding-candidate
    // pipeline as findSimilarSamples(), reranked by a hybrid distance that
    // blends normalized embedding distance with a normalized, per-field
    // weighted DSP feature distance. See findSimilarWeighted()'s .cpp doc
    // comment for the exact hybrid formula and normalization ranges.
    // dspWeight in [0, 1]: 0 = pure embedding similarity (identical to
    // findSimilarSamples' ordering), 1 = pure weighted-DSP similarity.
    // Excludes the query sample itself; deterministic tie-breaking by path.
    std::vector<SampleItem> findSimilarWeighted(const std::string& filePath, const FeatureWeights& weights,
                                                 float dspWeight = 0.5f, size_t k = 20);

    // RECOVERY PHASE R3-B -- Timbre Refinement (brief section 25-30; see
    // docs/SMART_SAMPLE_MANAGER_FEATURE_ROADMAP.md's V1.5 "Timbre Refinement
    // Sliders" entry: "'More Like This' / 'Less Like This' buttons that
    // update search queries based on the selected sample's timbre"). Bipolar
    // controls in [-1, +1]; 0 (neutral) must reproduce findSimilarWeighted's
    // baseline ordering with all FeatureWeights at a fixed neutral setting
    // (brief section 27). Semantic->DSP mapping (documented in the .cpp):
    // brightnessShift -> spectralCentroid weight direction, punchShift ->
    // crestFactor weight direction, noiseShift -> zeroCrossingRate weight
    // direction (a DSP field findSimilarWeighted itself doesn't expose,
    // since the roadmap doc's Find Similar 2.0 entry doesn't name it, but
    // ZCR is the direct, evidence-consistent proxy for "noisiness" among the
    // R2 contract's restored fields -- see .cpp for the full reasoning).
    struct TimbreRefinement {
        float brightnessShift = 0.0f; // -1 darker .. 0 neutral .. +1 brighter
        float punchShift = 0.0f;      // -1 softer .. 0 neutral .. +1 punchier
        float noiseShift = 0.0f;      // -1 cleaner .. 0 neutral .. +1 noisier
    };
    std::vector<SampleItem> findSimilarRefined(const std::string& filePath, const TimbreRefinement& refinement, size_t k = 20);

    // RECOVERY PHASE R3-C -- Reference Search (brief section 31-35; see
    // docs/SMART_SAMPLE_MANAGER_FEATURE_ARCHITECTURE.md §4, a pre-incident
    // doc naming this exact function signature and pipeline: decode+resample
    // the reference file, run one-off ONNX inference to get its 512D
    // embedding, query the existing HNSW index, exclude nothing extra since
    // the reference itself was never added, return top K). The reference
    // file is NEVER added to the library/cache/UMAP -- its embedding lives
    // only in a local variable for the duration of this call. Returns an
    // empty vector if the model isn't ready, the file fails to decode, or
    // inference fails -- never a fake/partial result.
    std::vector<SampleItem> findSimilarToReference(const std::string& referencePath, size_t k = 20);

    // COMBINED QUERY -- similarity + taxonomy/attribute hard filters
    // (SLO_SIMILARITY_SEARCH_REPORT_V1 open item: "darker 808s, shorter" needs
    // HNSW candidates intersected with attribute filters, not either alone).
    // Additive-only: post-filters findSimilarSamples() output, so Beta-1
    // PANNs+DSP ranking is untouched when no filter is set. Implementation is
    // header-inline to avoid touching the .cpp translation unit.
    struct CombinedQueryFilter {
        std::string category;            // exact match when non-empty
        std::string subcategory;         // exact match when non-empty
        float minDurationSeconds = -1.0f; // inclusive lower bound; <0 = unused
        float maxDurationSeconds = -1.0f; // inclusive upper bound; <0 = unused
        float maxSpectralCentroidHz = -1.0f; // "darker than"; <0 = unused
        float minSpectralCentroidHz = -1.0f; // "brighter than"; <0 = unused
        size_t overfetchMultiplier = 5;   // HNSW over-fetch factor before filtering
    };

    inline bool matchesCombinedFilter(const SampleItem& item, const CombinedQueryFilter& f) const {
        if (!f.category.empty() && item.category != f.category) return false;
        if (!f.subcategory.empty() && item.subcategory != f.subcategory) return false;
        if (f.minDurationSeconds >= 0.0f && item.durationSeconds < f.minDurationSeconds) return false;
        if (f.maxDurationSeconds >= 0.0f && item.durationSeconds > f.maxDurationSeconds) return false;
        if (f.maxSpectralCentroidHz >= 0.0f && item.audioFeatures.spectralCentroid > f.maxSpectralCentroidHz) return false;
        if (f.minSpectralCentroidHz >= 0.0f && item.audioFeatures.spectralCentroid < f.minSpectralCentroidHz) return false;
        return true;
    }

    inline std::vector<SampleItem> findSimilarFiltered(const std::string& filePath,
                                                       const CombinedQueryFilter& filter,
                                                       size_t k = 20) {
        const size_t fetch = k * (filter.overfetchMultiplier > 0 ? filter.overfetchMultiplier : 1);
        std::vector<SampleItem> candidates = findSimilarSamples(filePath, fetch);
        std::vector<SampleItem> out;
        out.reserve(k);
        for (const auto& item : candidates) {
            if (!matchesCombinedFilter(item, filter)) continue;
            out.push_back(item);
            if (out.size() >= k) break;
        }
        return out;
    }

    // RECOVERY PHASE R3-D -- Near-Duplicate Detection (brief section 36-43;
    // see docs/SMART_SAMPLE_MANAGER_FEATURE_ROADMAP.md's V1.1 entry: "Group
    // files with high embedding cosine similarity (e.g. > 0.98) to flag
    // near-identical or transcode variants" -- and Source/test_near_duplicates_main.cpp,
    // which calls this with threshold 0.98f). Distinct from the existing
    // exact-match-only findDuplicateGroups() (contentHash equality): this
    // compares 512D embeddings pairwise via cosine similarity, so it also
    // catches near-identical-but-not-byte-identical audio (e.g. a
    // gain-adjusted or format-converted copy) that contentHash would miss.
    // O(N^2) over processed-with-Valid-embedding samples (brief section 41:
    // restore correctness first, optimize later). Purely read-only --
    // returns groups, never deletes or moves anything (brief section 38).
    std::vector<DuplicateGroup> findNearDuplicates(float cosineThreshold = 0.98f);

    // RECOVERY PHASE R3-E -- Auto-Tagging (brief section 44-51). Deterministic,
    // profile-based (NOT generative/LLM -- brief section 45): a pure function
    // of the sample's already-computed category/subcategory/secondaryTags
    // (AbletonTaxonomy) and AudioAnalysisResult fields (R2 contract). See
    // docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §3's note that
    // predictedTags "is not independently versioned -- it's a pure function
    // ... regenerated whenever either of its two upstream inputs is
    // recomputed" -- computed on demand here rather than cached separately,
    // consistent with that. Returns an empty vector if the sample isn't
    // found/processed. Stable, deterministic ordering for identical inputs.
    std::vector<std::string> getPredictedTags(const std::string& filePath);

    // RECOVERY PHASE R3-F -- Map Clusters (brief section 52-56). NOT genuine
    // spatial clustering -- restored honestly as CATEGORY CENTROIDS: for
    // each distinct AbletonTaxonomy category among processed samples with a
    // valid UMAP position, the mean (x, y) of its members' coordinates, with
    // a minimum group size below which a category is omitted (too few points
    // for a meaningful label). Samples with no category (not yet classified)
    // are excluded. Deterministic for a given sample set.
    struct MapClusterLabel {
        std::string category;
        float x = 0.0f;
        float y = 0.0f;
        int sampleCount = 0;
    };
    std::vector<MapClusterLabel> computeMapClusters(int minGroupSize = 2);

    // Where the on-disk sample cache lives -- exposed so UI code (Preferences'
    // "Clear Cache") doesn't need to duplicate this path logic. Honors the
    // test-only directory override set via setCacheDbDirectoryOverrideForTesting()
    // below, if one is active.
    static juce::File getCacheDbFile();

    // RECOVERY PHASE R1 -- restored test/production cache isolation (see
    // docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md). Every automated test binary
    // must call this (via ScopedIsolatedCacheDb, Source/TestCacheDbIsolation.h)
    // BEFORE constructing the first SampleManagerEngine in the process --
    // openCacheDb() runs from the constructor's member initializer, so there
    // is no way to redirect it after the fact. Passing juce::File() clears
    // the override (restores production resolution).
    //
    // This alone is necessary but not sufficient for isolation: it only
    // protects binaries that remember to call it. See
    // isKnownProductionCacheDbPath() / SSM_TEST_BINARY below for the
    // fail-closed backstop that does not depend on that.
    static void setCacheDbDirectoryOverrideForTesting(const juce::File& dir);

    // Decodes `file` to mono and runs the same analyzeAudioBuffer() DSP
    // feature extraction prepareFile() uses internally, returning the raw
    // features directly. Diagnostic-only: exists so offline calibration
    // tooling (see tools/classification_benchmark/) can get real feature
    // distributions from real audio to justify attribute-tag thresholds
    // with evidence, without persisting these floats per-sample in the
    // production cache (a schema change this doesn't need). Returns a
    // default-constructed AudioFeatures{} on any decode failure.
    static AudioFeatures analyzeFileForDiagnostics(const juce::File& file);

    // True if `candidate` is (or would resolve to) the real, single,
    // machine-wide production cache DB file -- i.e. what getCacheDbFile()
    // returns when no test override is active. Pure/static so it's directly
    // unit-testable (see TestSafetyRegression) without needing to actually
    // open or touch the file. Used by the SSM_TEST_BINARY fail-closed guard
    // in openCacheDb().
    static bool isKnownProductionCacheDbPath(const juce::File& candidate);

    // P1-A cache-root divergence: test-only override for the LEGACY cache
    // location (mirrors setCacheDbDirectoryOverrideForTesting). Exists only so
    // migrateLegacyCacheIfNeeded() can be exercised against disposable fixtures
    // rather than the owner's real ~/Library/SmartSampleManager.
    static void setLegacyCacheDbDirectoryOverrideForTesting(const juce::File& dir);

    // P1-A: one-time, copy-based adoption of a cache left at the legacy
    // ~/Library/SmartSampleManager location by pre-migration builds. Safe to
    // call; no-ops when there is nothing to migrate or when it would be
    // unsafe (isolated test / env-var path).
    static void migrateLegacyCacheIfNeeded();

    // Runs SQLite's own integrity check against the cache DB. Never touches
    // sample audio files -- only the derived cache -- so callers may freely
    // quarantine/rebuild on failure. Exposed mainly for tests; openCacheDb()
    // already calls this automatically on startup.
    bool checkCacheIntegrity();

    // Closes the cache DB connection, deletes it (and its WAL/SHM sidecar
    // files) from disk, and reopens an empty one -- safe to call while the
    // engine is otherwise idle. Does NOT touch in-memory `samples` or
    // source files; a subsequent rescan will just reprocess everything
    // instead of hitting the cache.
    void clearCache();

    // Main background thread loop
    void run() override;

    // Thread-safe getter for processed samples
    std::vector<SampleItem> getSamples();

    // O(1) count (no full-vector copy) — lets a poll loop cheaply check whether
    // it's already caught up via drainNewSampleEvents() before paying for a full
    // getSamples() copy.
    size_t getSampleCount();

    // Per-field BPM lookup for one catalogued file, without the full-library
    // getSamples() deep copy. Returns 0.0 when the path isn't catalogued (or
    // carries no BPM), which callers treat as "play at the file's natural
    // sample rate". Deliberately a no-copy linear scan (not pathToIndex):
    // reorganizeSamples() rewrites filePath in place without updating the
    // index, so a map lookup would miss every post-sort path while the linear
    // scan keeps working exactly like the getSamples() loop it replaces.
    double getSampleBpm(const std::string& filePath);

    // Read-only audio-model view for one catalogued file (F-02 split display).
    // Re-runs the frozen acoustic head over the persisted 512-D embedding plus
    // stored DSP features WITHOUT the filename/folder MlOverrideGate fusion,
    // so the UI can show "audio model says X" next to the fused "shown: Y".
    // Pure recompute: never mutates the item, cache, or taxonomy. Returns
    // available=false when no usable embedding is stored (heuristic-only or
    // failed rows). staleHead=true when the row was classified under an older
    // head (classificationModelVersion mismatch) -- the view still recomputes
    // with the current head, so compare with the shown label accordingly.
    // unmapped=true when the head's raw class has no taxonomy mapping.
    struct AudioOnlyView {
        bool available = false;
        bool staleHead = false;
        bool unmapped = false;
        std::string category;
        std::string subcategory;
        float confidence = 0.0f;
        bool isOod = false;
    };
    AudioOnlyView getAudioOnlyView(const std::string& filePath) const;

    // Groups currently-processed samples by identical audio-content hash,
    // returning only groups with 2+ members (i.e. actual duplicates).
    // Exact-match only by design -- no similarity threshold to mistune, see
    // SampleItem::contentHash for what "identical" means here.
    std::vector<DuplicateGroup> findDuplicateGroups();

    // --- Favorites (RECOVERY PHASE R1 restoration -- see
    // docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md). Backed by the user_favorites
    // table (path TEXT PRIMARY KEY, added_at INTEGER), whose schema survived
    // the incident inside the live production DB even though the engine code
    // that wrote it was lost -- restored here to match that schema exactly.
    // User data (favorites/history/collections), unlike the derived
    // sample_cache table, deliberately survives clearCache().
    void setFavorite(const std::string& filePath, bool isFavorite);
    bool isFavorite(const std::string& filePath);
    std::vector<std::string> getFavorites();

    // --- Preview History (RECOVERY PHASE R1 restoration). Backed by
    // preview_history (id INTEGER PK AUTOINCREMENT, path TEXT, previewed_at
    // INTEGER). Trimmed to the 200 most recent entries after each write so
    // the table can't grow unbounded. getRecentPreviews returns newest-first.
    void recordPreview(const std::string& filePath);
    std::vector<PreviewHistoryEntry> getRecentPreviews(int limit = 50);

    // --- Smart Collections (RECOVERY PHASE R1 restoration). Backed by
    // smart_collections (name TEXT PRIMARY KEY, query_rules TEXT). query_rules
    // is a flat JSON object of optional filters, ANDed together --
    // {"favorite":bool, "bpm_min":n, "bpm_max":n, "key":"...",
    // "category":"...", "centroid_min":n, "centroid_max":n}. No nested rules,
    // no OR logic -- this exact, narrower-than-designed contract is preserved
    // deliberately; see Source/SmartCollectionsPanel.h, which was already
    // built against it.
    void createSmartCollection(const std::string& name, const std::string& queryRulesJson);
    void deleteSmartCollection(const std::string& name);
    std::vector<std::string> getSmartCollectionNames();
    std::vector<SampleItem> getSmartCollectionSamples(const std::string& name);

    // Pops up to `maxItems` newly-committed samples that haven't been drained yet
    // (in commit order) into `outItems`, returning how many were popped. Backed by
    // a lock-free juce::AbstractFifo, so this is cheap to call every frame from a
    // UI timer instead of re-copying the whole (potentially 100k+ item) sample
    // list just to find out what's new. Only covers brand-new samples — it does
    // NOT reflect existing samples whose position/fields changed (UMAP re-anchor,
    // metadata edit); callers should still watch getSamplesVersion() for those.
    int drainNewSampleEvents(std::vector<SampleItem>& outItems, int maxItems);

    // Sets callback to run when samples are updated or UMAP finishes
    void setUpdateCallback(std::function<void()> callback);

    // Update metadata directly in WAV file (non-blocking)
    void updateMetadataAsync(const std::string& filePath, float bpm, const std::string& key, const std::string& instrumentType);

    // User-corrected Ableton taxonomy tags (see AbletonTaxonomy.h). Unlike
    // updateMetadataAsync above, this never touches the WAV file (Tier 3
    // XMP-writing is a deferred follow-up) -- it updates the in-memory item
    // and persists to the sample cache immediately, and marks the sample as
    // user-overridden so future re-scans never silently reclassify over it.
    void updateTaxonomyAsync(const std::string& filePath, const std::string& category,
                              const std::string& subcategory, const std::vector<std::string>& secondaryTags,
                              const std::string& userNote = {});

    // Clears a user override and all derived taxonomy fields, resets
    // taxonomyVersion to 0, and persists that reset so the sample is picked
    // back up by heuristic classification the next time it's (re)scanned.
    // Does not reclassify synchronously -- see PluginEditor's "Reset to Auto"
    // button for the user-facing explanation of that.
    void resetTaxonomyToAuto(const std::string& filePath);

    // EXPERIMENTAL / unofficial: writes this sample's category, subcategory,
    // and secondary tags into its folder's Ableton "Places" XMP sidecar (see
    // AbletonXmpWriter.h) so Live 12+'s Browser can filter on them directly.
    // This is the ONLY tagging mechanism that actually reaches Ableton's own
    // UI -- everything else in this file is this app's own internal
    // metadata. Reverse-engineered format, no official API; always backs up
    // an existing sidecar before touching it, never touches the audio file.
    // Synchronous (direct small-file I/O, not queued) -- meant to be called
    // from an explicit, opt-in user action, not automatically during scans.
    AbletonXmpWriter::WriteResult writeAbletonXmpTags(const std::string& filePath);

    // Reorganize samples on disk by moving or copying them into subfolders based on classification and style.
    // Synchronous -- blocks the calling thread for the whole operation (per-file
    // disk move/copy under dbLock). Kept for the test suite and any caller that
    // genuinely wants synchronous semantics; UI code should use
    // reorganizeSamplesAsync() below instead -- see docs/SORT_LIBRARY_BACKGROUND.md.
    void reorganizeSamples(int namingStyle, bool copyInsteadOfMove = false, juce::File customTargetDir = {});

    // Runs reorganizeSamples() on a background thread and reports progress via
    // getSortLibraryProgress() (poll from a UI timer) plus onComplete (delivered
    // on the message thread) when done. See docs/SORT_LIBRARY_BACKGROUND.md.
    void reorganizeSamplesAsync(int namingStyle, bool copyInsteadOfMove,
                                 std::function<void(int moved, int failed, bool cancelled)> onComplete);

    // Requests the in-progress reorganizeSamplesAsync() operation stop before
    // its next file -- already-moved files stay moved (this is a "stop before
    // more changes happen", not a rollback; each individual file move/copy is
    // already atomic via juce::File's own move/copy).
    void cancelSortLibrary() { sortCancelRequested.store(true, std::memory_order_relaxed); }

    struct SortLibraryProgress {
        bool inProgress = false;
        int done = 0;
        int total = 0;
        int failed = 0;
        int skippedByPolicy = 0;   // declined by the beta decision policy
    };

    // Read-only scan progress for the editor. Counts include files admitted by
    // the queue (including cache hits), and `done` advances only once each file
    // has either committed or been rejected, so the denominator is honest.
    struct ScanProgress {
        bool inProgress = false;
        int done = 0;
        int total = 0;
        int failed = 0;
    };

    ScanProgress getScanProgress() const {
        return {
            busyFlag.load(std::memory_order_relaxed),
            scanDone.load(std::memory_order_relaxed),
            scanTotal.load(std::memory_order_relaxed),
            scanFailed.load(std::memory_order_relaxed)
        };
    }

    // F-03 rescan-diff receipt: what the last scan run actually did. added =
    // brand-new library rows; changed = re-analysed existing rows (mtime
    // touch, head/taxonomy refresh); failed = decode/analysis failures
    // (== ScanProgress::failed); skippedNonAudio = enumerated files refused
    // admission (unsupported extension, symlink). Lock-free snapshot; stable
    // once the scan completes (busyFlag false).
    struct ScanReceipt {
        int added = 0;
        int changed = 0;
        int failed = 0;
        int skippedNonAudio = 0;
    };
    ScanReceipt getLastScanReceipt() const {
        return {
            scanAdded.load(std::memory_order_relaxed),
            scanChanged.load(std::memory_order_relaxed),
            scanFailed.load(std::memory_order_relaxed),
            scanSkippedNonAudio.load(std::memory_order_relaxed)
        };
    }

    // Credits UI-side pre-filtered drops (files the UI refused before calling
    // addPathToQueue) to the running scan's skip count, or to the pending
    // pure-skip accumulation when idle. Call AFTER the scan-starting
    // addPathToQueue calls so a fresh-scan reset cannot erase the credit.
    void noteSkippedDrops(int count) {
        if (count > 0)
            scanSkippedNonAudio.fetch_add(count, std::memory_order_relaxed);
    }

    // F-04 diagnostics bundle: one JSON string with app/model versions, OOD
    // thresholds, library + last-scan receipt, evidence-split counts, and a
    // best-effort log tail for support. Read-only snapshot; never touches the
    // cache, taxonomy, or user files. record_type is deliberately distinct
    // from the label-free evidence packet so its import parser never collides.
    std::string buildDiagnosticsBundle(size_t maxLogLines = 200) const;
    // Beta safety gate. ON by default: a sort must never relocate files on a
    // weak classification. Turning it off is a deliberate, explicit act.
    void setBetaPolicyGateEnabled(bool on) { betaPolicyGateEnabled.store(on); }
    bool isBetaPolicyGateEnabled() const { return betaPolicyGateEnabled.load(); }
    void setBetaPolicyGate(float g) {
        betaPolicyGate.store(std::clamp(g, 0.0f, 1.0f), std::memory_order_relaxed);
    }

    struct BetaSortPreview {
        int autoRenameEligible = 0;
        int suggest = 0;
        int review = 0;
        int neverAct = 0;
        int total = 0;
    };

    // PREVIEW ONLY -- inspects state and touches no file. This is what the beta
    // UI shows before the user decides anything.
    BetaSortPreview previewBetaSort() const;

    struct SortPreviewItem {
        int sampleIndex = -1;
        std::string sourcePath;
        std::string sourceFilename;
        std::string destinationPath;
        std::string destinationFilename;
        std::string category;
        std::string subcategory;
        std::string key;
        float bpm = 0.0f;
        bool eligible = true;
        std::string policyReason;
        bool willCollide = false;
    };

    struct SortPreviewResult {
        std::vector<SortPreviewItem> items;
        int totalCount = 0;
        int eligibleCount = 0;
        int skippedCount = 0;
        int collisionCount = 0;
        std::string rootDirectory;
    };

    // Interactive rename preview -- computes exact proposed file paths and
    // safety-gate eligibility for all samples without modifying the filesystem.
    SortPreviewResult previewSortLibrary(int namingStyle, bool copyInsteadOfMove = true, juce::File customTargetDir = {}) const;

    struct UndoSortResult {
        bool success = false;
        int revertedCount = 0;
        int failedCount = 0;
        std::string journalPath;
        std::string errorMessage;
    };

    // Checks whether a valid, non-undone sort journal exists
    bool canUndoSort() const;

    // Locates the most recent sort journal file on disk
    juce::File getMostRecentSortJournal() const;

    // Synchronously undoes the last sort operation recorded in the journal
    UndoSortResult undoLastSort();

    // Asynchronously undoes the last sort on the background sort thread
    void undoLastSortAsync(std::function<void(UndoSortResult)> onComplete);

    SortLibraryProgress getSortLibraryProgress() const {
        return {
            sortInProgress.load(std::memory_order_relaxed),
            sortDone.load(std::memory_order_relaxed),
            sortTotal.load(std::memory_order_relaxed),
            sortFailed.load(std::memory_order_relaxed),
            sortSkippedByPolicy.load(std::memory_order_relaxed)
        };
    }

    // Absolute path of the most recent sort journal.  The journal is written
    // before any filesystem mutation and records every planned and committed
    // source -> destination mapping, so an explicit undo tool can verify and
    // reverse a move without guessing.
    std::string getLastSortJournalPath() const {
        const juce::ScopedLock sl(dbLock);
        return lastSortJournalPath;
    }

    // Forces a UMAP projection run on current embeddings. `forceFullRecompute`
    // (the default, matching this method's documented "forces a run" contract for
    // external callers) always re-projects every sample from scratch. Passing
    // false allows the cheaper incremental out-of-sample placement path once the
    // engine has already bootstrapped a full projection at least once — used
    // internally by the scan coordinator so a long scan doesn't pay for a full
    // O(N) UMAP recompute after every batch.
    void triggerUMAP(bool forceFullRecompute = true);

    // Check if the background thread is currently processing or running UMAP
    bool isBusy() const { return busyFlag.load(); }

    // Wall-clock duration of the most recent UMAP layout pass, in milliseconds
    // (0 before any layout has run). The scan coordinator performs layout
    // inline and only then clears busyFlag, so `isBusy()` -- and therefore any
    // elapsed-time measurement built on it -- covers decode + embed + HNSW +
    // layout together. This accessor lets benchmark/qualification tooling
    // report scan cost and canvas-layout cost separately instead of silently
    // attributing layout time to per-file scan cost. Measurement only; nothing
    // in the product reads it.
    double getLastLayoutDurationMs() const
    {
        return lastLayoutDurationMs.load(std::memory_order_relaxed);
    }

    // Startup cache restoration is independent of the scan coordinator. This
    // becomes true only after the background hydration pass has either rebuilt
    // the runtime library/index or established that there is nothing usable to
    // restore. It lets callers avoid treating a partially built HNSW index as
    // a ready library.
    bool isPersistedCacheHydrationComplete() const { return hydrationComplete.load(); }

    // Monotonically increasing counter, bumped whenever `samples` changes.
    // Callers (e.g. the editor's poll timer) can cheaply skip re-fetching/re-rendering
    // when this hasn't advanced since their last check, instead of unconditionally
    // copying and re-processing the full sample list on every tick.
    uint64_t getSamplesVersion() const { return samplesVersion.load(std::memory_order_relaxed); }

    juce::AudioFormatManager& getFormatManager() { return formatManager; }

private:
    // A file that's been read/resampled/heuristically-classified but not yet run
    // through ONNX inference. Produced in parallel by scanPool workers, consumed
    // in batches by the InferenceWorker thread.
    struct PendingInference {
        SampleItem item;
        std::vector<float> waveform; // 160000 floats @ 32kHz, fed to ONNX in batches
        // True if `item.embedding` was hydrated from the on-disk cache (see
        // tryLoadFromCache) and doesn't need to go through ONNX at all — it still
        // flows through the same batch/commit/FIFO pipeline as freshly-inferred
        // items (so UMAP placement and canvas pickup work identically), it's just
        // excluded from the batch's inference tensor and from the cache re-write.
        bool embeddingAlreadyKnown = false;

        // RECOVERY PHASE R3-G -- Cache Version Enforcement. True when this
        // item came from lightReanalyzeFile() (embedding reused, but DSP
        // features and/or taxonomy were selectively recomputed because their
        // version was stale). Without this, runInferenceBatch()'s
        // cache-rewrite index (built from `needsInference`, i.e.
        // !embeddingAlreadyKnown) would silently discard the selective
        // refresh the moment it's not re-persisted -- see
        // docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §4.
        bool derivedDataChanged = false;

        // True when a cached, still-valid embedding belongs to a row whose
        // taxonomy was stale and whose prior result came from the acoustic
        // classifier. Cache hydration skips ONNX by design, but the frozen
        // classifier head still needs to be reapplied after the heuristic
        // taxonomy baseline has been rebuilt; otherwise a stale-taxonomy
        // refresh can silently downgrade an ml_v3/ml_ood result to heuristic.
        bool reclassifyKnownEmbedding = false;
    };

    // Decodes `filePath` once and selectively recomputes only the stale
    // derived-data field(s) of `cached` (DSP features and/or taxonomy),
    // leaving its already-current embedding and any current field
    // untouched. Called from prepareFile() when tryLoadFromCache() returns a
    // hit whose embedding is current but whose featureVersion and/or
    // taxonomyVersion is stale -- see
    // docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §4 for the full
    // decision table this implements. Never recomputes taxonomy if
    // cached.tagUserOverridden is set (a user correction is frozen until an
    // explicit "Reset to Auto").
    SampleItem lightReanalyzeFile(const std::string& filePath, SampleItem cached);

    // Drains pendingFiles until empty: does file I/O + resample + feature
    // extraction/classification (everything except ONNX inference), then hands the
    // result off to the inference queue. Runs on scanPool worker jobs, in parallel
    // across CPU cores.
    void drainQueueWorker();
    void releaseQueuedPath(const std::string& filePath);
    // Returns true when the path was handed to the inference queue. A decode
    // failure returns false so admission can be released immediately;
    // successful work remains guarded until runInferenceBatch() commits it.
    bool prepareFile(const std::string& filePath);

    void runUMAPInternal(bool forceFullRecompute);

    // Full UMAP recompute over every processed sample (the original, expensive
    // O(N) path) — used to bootstrap the very first projection and for explicit
    // user-forced re-anchors.
    //
    // Locking contract (engineering/SLO dbLock-scope): takes dbLock internally
    // only to snapshot the eligible embeddings and to write coordinates back;
    // the umappp projection itself runs with dbLock RELEASED so the message
    // thread stays responsive during a multi-second bootstrap/rebuild. Returns
    // true when the projection was committed (or there was nothing to project),
    // false when the eligible set changed mid-projection and the layout was
    // discarded — in that case the caller must NOT record the samples as
    // projected. Must be called WITHOUT holding dbLock.
    bool runFullUMAP();

    // Places samples[umapProjectedCount .. samples.size()) using the hnsw index
    // built from already-projected points: each new point is positioned at the
    // distance-weighted centroid of its k-nearest already-embedded neighbors'
    // existing 2D coordinates (a standard UMAP out-of-sample extension), then
    // added to the index itself so later new points in the same batch can use it
    // as a neighbor too. O(log N) per point instead of a full O(N) recompute.
    void placeNewSamplesIncrementally();

    // (Re)builds the hnsw index from scratch over every processed sample's
    // 512D embedding. Called after a full UMAP recompute, since that's the only
    // time every point's neighbor set may have shifted.
    void rebuildHnswIndexFull();

    // Coalesces update notifications across many concurrent worker threads so we
    // fire the UI callback at most a few times per second, not once per file.
    void maybeNotifyUpdate();

    // Batches PendingInference entries (up to kMaxInferenceBatch, or whatever's
    // available after a short wait once kMinInferenceBatch can't be reached) and
    // runs a single Ort::Session::Run() call per batch instead of one per file.
    // Runs continuously for the engine's lifetime on its own dedicated thread.
    class InferenceWorker : public juce::Thread {
    public:
        explicit InferenceWorker(SampleManagerEngine& e) : juce::Thread("SampleManagerEngine-Inference"), engine(e) {}
        void run() override;
    private:
        SampleManagerEngine& engine;
    };
    friend class InferenceWorker;

    void runInferenceBatch(std::vector<PendingInference>& batch);

    // Coalesced async TagLib write queue: a single persistent worker thread
    // drains pending metadata writes, keyed by path so repeated edits to the same
    // file before the previous write finishes just replace the pending entry
    // instead of queuing up separate writes (matters for bulk retagging —
    // otherwise the old per-call juce::Thread::launch() approach could spawn
    // thousands of OS threads).
    struct PendingMetadataWrite {
        float bpm;
        std::string key;
        std::string instrumentType;
    };
    class MetadataWriteWorker : public juce::Thread {
    public:
        explicit MetadataWriteWorker(SampleManagerEngine& e) : juce::Thread("SampleManagerEngine-MetadataWrite"), engine(e) {}
        void run() override;
    private:
        SampleManagerEngine& engine;
    };
    friend class MetadataWriteWorker;

    // On-disk SQLite (WAL mode) cache of already-processed files, keyed by
    // absolute path + mtime + size, so relaunching/rescanning a library skips
    // Audio decode + mel-spec + ONNX inference entirely for files that haven't
    // changed since they were last cached. Kept as an opaque pimpl so sqlite3.h
    // doesn't need to be dragged into every translation unit that includes this
    // header.
    struct CacheDb;
    std::unique_ptr<CacheDb> cacheDb;
    juce::CriticalSection cacheDbLock;

    // isRetryAfterQuarantine: true only on the recursive re-open performed
    // after a corrupt cache DB was quarantined, to prevent looping if the
    // freshly-created DB were somehow flagged again.
    void openCacheDb(bool isRetryAfterQuarantine = false);
    // Restores previously indexed, currently available files from the cache
    // after opening it. This is deliberately separate from addPathToQueue():
    // startup must not walk the library or invoke inference merely to rebuild
    // the in-memory model used by the browser and map.
    void hydratePersistedSamples();
    // Looks up `filePath` in the cache; on a hit where the cached mtime/size
    // still match the file on disk, hydrates `outItem` and returns true.
    bool tryLoadFromCache(const std::string& filePath, SampleItem& outItem);
    // Upserts cache rows for batch[indices] (the freshly-inferred subset of a
    // batch — cache-hit items don't need to be re-written) in a single transaction.
    void upsertCacheEntries(const std::vector<PendingInference>& batch, const std::vector<size_t>& indices);
    // Persists the current x/y for every processed sample in samples[startIdx..end)
    // back to the umap_x/umap_y cache columns, so a future launch can skip
    // recomputing their projection entirely. See docs/UMAP_PERSISTENCE.md.
    void persistUmapPositions(size_t startIdx);

    // DSP / Feature Extraction
    // outContentHash, if non-null, is set to the FNV-1a hash of the full
    // decoded mono PCM buffer (before resampling/padding to targetNumSamples)
    // -- computed here rather than via a second decode pass, since this
    // function already has the complete audio in memory.
    std::vector<float> loadAndResampleWaveform(const std::string& filePath, double targetSampleRate, int targetNumSamples, std::string* outContentHash = nullptr, float* outDurationSeconds = nullptr);
    std::vector<float> computeMelSpectrogram(const std::vector<float>& audioData, double sampleRate, int& outFrames, int& outMelBins);
    std::string detectKeyFromAudio(const float* data, int numSamples, double sampleRate);

    // TagLib Metadata helpers
    bool readAudioMetadata(const std::string& filePath, float& bpm, std::string& key, std::string& instrumentType);
    void writeWavMetadata(const std::string& filePath, float bpm, const std::string& key, const std::string& instrumentType);

    std::atomic<bool> busyFlag{false};
    std::atomic<int> scanDone{0};
    std::atomic<int> scanTotal{0};
    std::atomic<int> scanFailed{0};
    // F-03 rescan-diff counters. Reset whenever a fresh scan starts (!wasBusy
    // in addPathToQueue); overlapping rescans accumulate, matching scanTotal
    // semantics. Pure-skip admissions (no scan started) accumulate until the
    // next scan resets them, so the count is never silently dropped.
    std::atomic<int> scanAdded{0};
    std::atomic<int> scanChanged{0};
    std::atomic<int> scanSkippedNonAudio{0};
    std::atomic<int> lastPruneUnavailableStorageCount{0};

    // Sort Library background-operation state -- see reorganizeSamplesAsync()
    // and docs/SORT_LIBRARY_BACKGROUND.md. Polled by the UI, not locked, since
    // these are just progress counters (not correctness-critical shared state).
    std::atomic<bool> sortInProgress{false};
    std::atomic<bool> sortCancelRequested{false};
    std::atomic<int> sortDone{0};
    std::atomic<int> sortTotal{0};
    std::atomic<bool> betaPolicyGateEnabled{true};
    std::atomic<float> betaPolicyGate{0.93f};
    std::atomic<int> sortFailed{0};
    std::string lastSortJournalPath;
    // Files the beta decision policy declined to touch. Reported to the user so
    // "SLO sorted fewer files than I have" is explained rather than mysterious.
    std::atomic<int> sortSkippedByPolicy{0};
    // Owns the background thread reorganizeSamplesAsync() starts -- joined
    // in ~SampleManagerEngine() before samples/dbLock/etc. are torn down,
    // same reasoning and pattern as initThread above.
    std::thread sortThread;

    // Internal data structures
    std::queue<std::string> pendingFiles;
    std::vector<SampleItem> samples;
    // filePath -> positional index into `samples`. Maintained under dbLock by
    // the same sites that mutate `samples` (inference-batch commit, prune,
    // hydration bulk assignment). Gives findSimilarSamples() and the batch
    // commit O(1) path lookup instead of an O(N) linear scan while holding
    // dbLock (Phase 3, engineering/slo-perf-scale-v1). Rebuilt wholesale
    // after index-shifting bulk mutations (prune erase, hydration); updated
    // incrementally on push_back in the batch commit.
    std::unordered_map<std::string, size_t> pathToIndex;
    std::function<void()> onUpdate;

    mutable juce::CriticalSection dbLock;
    juce::CriticalSection queueLock;
    // A path remains in this set from admission until its scan worker has
    // finished. This prevents overlapping UI rescans from processing the same
    // path twice while still allowing a later, deliberate rescan to detect a
    // changed file through the normal cache identity check.
    std::unordered_set<std::string> queuedOrProcessingPaths;

    // Parallel file-processing pool (I/O + DSP + ONNX inference), sized to the
    // number of CPU cores by default. The `run()` thread itself no longer processes
    // files directly; it only submits worker jobs and coordinates the debounced
    // UMAP re-projection once the pool has fully drained.
    juce::ThreadPool scanPool;

    std::atomic<uint64_t> samplesVersion{0};
    std::atomic<uint32_t> lastNotifyMs{0};

    std::string modelPath;

    // Gates all access to env/session below -- written once (release) at the
    // end of init() on the background thread initAsync() launches, read
    // (acquire) by isEmbeddingModelAvailable() and runInferenceBatch() from
    // whichever thread calls them. This is the standard "publish a pointer
    // via an atomic flag" pattern: the acquire-load on engineState==Ready
    // synchronizes-with the release-store, making env/session's construction
    // visible to the reading thread without a separate lock. See
    // docs/ASYNC_STARTUP.md.
    std::atomic<EngineInitState> engineState { EngineInitState::Uninitialized };

    // Owns the background thread initAsync() starts -- joined in
    // ~SampleManagerEngine() before env/session/etc. are torn down, so a
    // fast destroy-after-construct can never race a still-running init().
    // See docs/ASYNC_STARTUP.md.
    std::thread initThread;

    // ONNX Runtime members
    std::unique_ptr<Ort::Env> env;
    std::unique_ptr<Ort::Session> session;
    bool coreMLEnabled = false;

    // Batched inference pipeline
    std::unique_ptr<InferenceWorker> inferenceWorker;
    juce::CriticalSection inferenceQueueLock;
    std::deque<PendingInference> inferenceQueue;
    // Counts items that have been queued for inference but not yet committed to
    // `samples`. The scan coordinator waits for this to reach 0 (in addition to
    // scanPool draining) before it considers a scan finished and runs UMAP —
    // otherwise embeddings still in flight on the inference thread would be
    // silently dropped from that projection.
    std::atomic<int> pendingInferenceCount{0};

    // Lock-free ring buffer of newly-committed samples, for cheap low-latency
    // pickup by the UI (see drainNewSampleEvents). Single-producer (the
    // InferenceWorker thread is the only thing that ever commits new samples)
    // single-consumer (whichever thread calls drainNewSampleEvents — intended to
    // always be the same UI timer). Slots are pre-constructed real SampleItem
    // objects; the AbstractFifo index protocol guarantees the writer and reader
    // never touch the same slot concurrently, so writing/reading the non-POD
    // SampleItem (string/vector members) through it is safe despite not using a
    // lock for the actual data transfer.
    static constexpr int kCanvasFifoCapacity = 4096;
    juce::AbstractFifo canvasUpdateFifo{ kCanvasFifoCapacity };
    std::vector<SampleItem> canvasUpdateSlots{ static_cast<size_t>(kCanvasFifoCapacity) };

    // Incremental UMAP spatial index. Kept as an opaque pimpl so hnswlib's headers
    // (templated on our own EmbeddingDim etc.) don't need to be dragged into every
    // translation unit that includes this header.
    struct HnswIndexImpl;
    std::unique_ptr<HnswIndexImpl> hnswIndex;

    // True once a full UMAP projection has run at least once. Before that,
    // incremental placement has nothing to anchor to and a full recompute is
    // always required.
    bool umapBootstrapped = false;

    // Written by triggerUMAP() on the scan coordinator thread; read by
    // getLastLayoutDurationMs(). See that accessor for why this is exposed.
    std::atomic<double> lastLayoutDurationMs { 0.0 };

    // Set by pruneMissingFiles() when it has removed entries from `samples`
    // after hnswIndex was already built. hnswlib labels are the sample's
    // index-at-build-time; removing entries shifts every later index, so the
    // index must be fully rebuilt (not incrementally patched) before the next
    // findSimilarSamples() call, or it can silently resolve a hit to the wrong
    // sample. Consumed (and cleared) by run()'s next quiescence pass.
    std::atomic<bool> forcedUmapRecomputePending { false };

    // Number of leading entries in `samples` that already have valid UMAP
    // coordinates and are present in hnswIndex. New entries are always appended
    // (see prepareFile/runInferenceBatch), so [umapProjectedCount, samples.size())
    // is exactly the set of not-yet-placed points.
    size_t umapProjectedCount = 0;

    // Coalesced async TagLib write queue (see MetadataWriteWorker above)
    std::unique_ptr<MetadataWriteWorker> metadataWriteWorker;
    juce::CriticalSection metadataWriteLock;
    std::map<std::string, PendingMetadataWrite> pendingMetadataWrites;

    // Cache hydration can involve thousands of rows, so it never runs on the
    // JUCE message thread or the audio thread. Joined during destruction before
    // cacheDb/samples are torn down.
    std::thread hydrationThread;
    std::atomic<bool> hydrationComplete { false };

    juce::AudioFormatManager formatManager;

    // Safely notifies `onUpdate` via MessageManager::callAsync -- see
    // docs/ASYNC_STARTUP.md's "second bug" note. A plain `[this]` capture in
    // an async callback is unsafe if the engine is destroyed before the
    // message loop processes it (a real risk: onUpdate fires from multiple
    // worker threads throughout a scan, and a host can destroy the plugin
    // at any time). Uses a juce::WeakReference so a since-destroyed engine
    // is detected and the callback becomes a safe no-op instead of touching
    // freed memory. Centralizes what were 7 duplicated call sites.
    void notifyUpdateNow();

    JUCE_DECLARE_WEAK_REFERENCEABLE(SampleManagerEngine)
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(SampleManagerEngine)
};
