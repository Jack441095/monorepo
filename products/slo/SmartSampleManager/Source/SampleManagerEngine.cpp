#include "SampleManagerEngine.h"
#include "MissingFilePolicy.h"
#include "BetaDecisionPolicy.h"
#include "CorrectionLog.h"
#include <array>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <onnxruntime_cxx_api.h>
#include <coreml_provider_factory.h>
#include <taglib/wavfile.h>
#include <taglib/fileref.h>
#include <taglib/tpropertymap.h>
#include <taglib/id3v2tag.h>
#include <taglib/textidentificationframe.h>

// Include UMAP headers
#include "umappp/umappp.hpp"
#include "knncolle/knncolle.hpp"

// Approximate nearest-neighbor index used for incremental UMAP out-of-sample placement
#include "hnswlib/hnswlib.h"

#define DR_WAV_IMPLEMENTATION
#include "dr_wav.h"

#include "VectorMath.h"
#include "AppLogger.h"
#include "AbletonTaxonomy.h"
#include "AcousticClassifier.h"
#include "MlOverrideGate.h"
#include "BassTimbreClassifier.h"
#include "HiHatTypeClassifier.h"

#include <sqlite3.h>

#include <cmath>
#include <algorithm>
#include <iostream>
#include <cctype>
#include <initializer_list>
#include <unordered_map>
#include <unordered_set>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <limits>
#include <mutex>
#include <stdexcept>

#if JUCE_MAC
 #include <dlfcn.h>
#endif

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Definition lives with the engine's filename-token helpers below.
std::vector<std::string> rawUnderscoreSplitLowercase(const juce::String& str);

namespace
{
// Statement writes that discard their step() result silently swallowed
// sqlite failures (disk full, I/O errors, constraint/contention -- anything
// the WAL write path can hit). Route every write through this so a failure is
// at least surfaced in the log instead of just lost; success returns
// SQLITE_DONE exactly as before, keeping the call sites' semantics unchanged.
int logWriteStep(sqlite3* db, sqlite3_stmt* stmt, const char* what)
{
    const int rc = sqlite3_step(stmt);
    if (rc != SQLITE_DONE) {
        const char* msg = sqlite3_errmsg(db);
        AppLogger::getInstance().logError(
            "SQLite write failed [" + juce::String(what) + "]: rc=" + juce::String(rc)
            + (msg != nullptr ? " msg=" + juce::String(msg) : juce::String()));
    }
    return rc;
}

// Definition lives with the engine's filename-token helpers below.
std::vector<std::string> tokenizeString(const juce::String& str);

bool isLoopTaxonomyLabel(const std::string& subcategory)
{
    return subcategory.find("Loop") != std::string::npos
        || subcategory.find("loop") != std::string::npos;
}

bool hasLoopToken(const SampleItem& item)
{
    const auto tokens = tokenizeString(juce::String(item.name));
    for (const auto& token : tokens)
        if (token == "loop" || token == "loops" || token.find("loop") != std::string::npos)
            return true;
    return false;
}

// A BPM value has meaning for repeatable musical material.  Applying this at
// the taxonomy boundary prevents legacy/default 120 BPM values from leaking
// into one-shot/FX names while preserving explicit and estimated tempo for
// loop classes.  User tag overrides remain untouched by callers.
void normalizeTempoForTaxonomy(SampleItem& item)
{
    const bool loopEvidence = isLoopTaxonomyLabel(item.subcategory) || hasLoopToken(item);
    if (!item.tagUserOverridden
        && ((!item.subcategory.empty() && !isLoopTaxonomyLabel(item.subcategory))
            || (item.tagSource == "ml_ood" && !loopEvidence)))
        item.bpm = 0.0f;
}

// A plug-in executes inside its DAW process, so JUCE's
// currentExecutableFile identifies the host (for example Ableton Live), not
// necessarily this AU/VST3 module. dladdr identifies the loaded image that
// contains this code, which is the bundle whose Resources directory carries
// the embedding model.
juce::File getThisModuleFile()
{
#if JUCE_MAC
    Dl_info info{};
    if (dladdr(reinterpret_cast<const void*>(&getThisModuleFile), &info) != 0
        && info.dli_fname != nullptr)
        return juce::File(juce::String::fromUTF8(info.dli_fname));
#endif
    return {};
}

// The model contract is a concrete float tensor [batch, 512].  Validate the
// runtime output before taking a typed pointer: GetTensorMutableData<float>()
// does not make an incorrectly shaped/type-ed output safe, and the batch
// consumer otherwise trusts the expected element count while walking it.
bool hasExpectedEmbeddingOutput(const Ort::Value& output, int64_t batchSize)
{
    if (batchSize <= 0 || !output.IsTensor()) return false;

    const auto info = output.GetTensorTypeAndShapeInfo();
    const auto shape = info.GetShape();
    bool match = (info.GetElementType() == ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT
        && shape.size() == 2
        && shape[0] == batchSize
        && shape[1] == AcousticClassifier::pannsDim
        && info.GetElementCount() == static_cast<size_t>(batchSize) * static_cast<size_t>(AcousticClassifier::pannsDim));
    if (!match) {
        juce::String shapeStr = "[";
        for (size_t i = 0; i < shape.size(); ++i) {
            if (i > 0) shapeStr += ", ";
            shapeStr += juce::String(shape[i]);
        }
        shapeStr += "]";
        AppLogger::getInstance().logError("Embedding output mismatch: type=" + juce::String(info.GetElementType())
            + " shape=" + shapeStr + " count=" + juce::String(info.GetElementCount())
            + " expected batch=" + juce::String(batchSize) + " dim=" + juce::String(AcousticClassifier::pannsDim));
    }
    return match;
}

// A rename/sort operation must never destroy an unrelated file merely because
// two source files produce the same canonical name.  The old path chose the
// requested destination and deleted it before moving, which made a collision
// destructive.  Reserve a deterministic sibling instead; the caller can then
// journal the exact source -> destination mapping and the original remains
// recoverable in both copy and move modes.
juce::File chooseNonDestructiveDestination(const juce::File& desired,
                                           const juce::File& source)
{
    const auto desiredPath = desired.getFullPathName();
    if (desiredPath == source.getFullPathName()
        || (!desired.existsAsFile() && !desired.isDirectory()))
        return desired;

    const auto stem = desired.getFileNameWithoutExtension();
    const auto extension = desired.getFileExtension();
    for (int suffix = 1; suffix <= 99999; ++suffix)
    {
        const auto candidate = desired.getSiblingFile(
            stem + "_" + juce::String(suffix).paddedLeft('0', 2) + extension);
        if (candidate.getFullPathName() != source.getFullPathName()
            && !candidate.existsAsFile() && !candidate.isDirectory())
            return candidate;
    }

    // An empty path is an explicit failure signal.  The caller must count the
    // file as failed and leave the source untouched rather than guessing.
    return {};
}

bool isInsideDirectory(const juce::File& child, const juce::File& parent)
{
    const auto childPath = child.getFullPathName();
    const auto parentPath = parent.getFullPathName();
    return childPath == parentPath
        || childPath.startsWith(parentPath + juce::File::getSeparatorString());
}

juce::String journalCsvField(const juce::String& value)
{
    return "\"" + value.replace("\"", "\"\"") + "\"";
}

bool appendSortJournalRow(juce::FileOutputStream& stream,
                          const juce::String& operation,
                          const juce::String& status,
                          const juce::File& source,
                          const juce::File& destination)
{
    const auto timestamp = juce::Time::getCurrentTime().toISO8601(true);
    const auto row = journalCsvField("1")
        + "," + journalCsvField(operation)
        + "," + journalCsvField(status)
        + "," + journalCsvField(source.getFullPathName())
        + "," + journalCsvField(destination.getFullPathName())
        + "," + journalCsvField(timestamp) + "\n";
    stream.writeText(row, false, false, nullptr);
    stream.flush();
    return true;
}

juce::StringArray parseJournalCsvLine(const juce::String& line)
{
    juce::StringArray tokens;
    juce::String currentToken;
    bool inQuotes = false;
    for (int i = 0; i < line.length(); ++i) {
        juce::juce_wchar c = line[i];
        if (c == '"') {
            if (inQuotes && i + 1 < line.length() && line[i + 1] == '"') {
                currentToken += '"';
                ++i;
            } else {
                inQuotes = !inQuotes;
            }
        } else if (c == ',' && !inQuotes) {
            tokens.add(currentToken);
            currentToken.clear();
        } else {
            currentToken += c;
        }
    }
    tokens.add(currentToken);
    return tokens;
}

// One predicate for every consumer of persisted/in-memory embeddings.  A
// length check alone is not enough: legacy rows or future callers could carry
// a 512-float buffer containing zero, non-finite, or arithmetic-overflow-scale
// values.  Keep the status bit and the numerical contract aligned before any
// cache write, classifier call, similarity query, HNSW insertion, or UMAP run.
bool hasSafeEmbeddingBuffer(const std::vector<float>& embedding)
{
    // The persisted/in-memory vector is the 512-D PANNs embedding. The
    // classifier's 520-D input is assembled separately by
    // buildAcousticClassifierInput() and never stored on the item, so this
    // predicate must check pannsDim -- checking embeddingDim (520) here
    // rejects every cache-hydrated row, which restores exactly the silent
    // "hydrated rows are never classified" defect this split removes.
    return embedding.size() == static_cast<size_t>(AcousticClassifier::pannsDim)
        && AcousticClassifier::isValidEmbedding(embedding.data());
}

// Assemble the 520-D classifier input: the 512-D PANNs embedding followed by
// the 8 normalised DSP features.
//
// SINGLE SOURCE OF TRUTH. Both the fresh-inference path (runInferenceBatch)
// and the cache-hydration path reach the classifier through here, so the two
// cannot drift apart and produce different tags for the same file depending
// on whether its row came from the cache.
//
// The normalisation constants below are matched byte-for-byte by
// tools/classification_benchmark/build_hybrid_v4_dataset.py, which builds the
// training set. Changing one without the other silently reintroduces
// train/serve skew -- see docs/classification/SLO_V4_DSP_FEATURE_PARITY_SPEC.md
// and validate_dsp_parity.py.
std::array<float, AcousticWeights::embeddingDim>
buildAcousticClassifierInput(const std::vector<float>& embedding,
                             const AudioAnalysisResult& f,
                             double durationSeconds)
{
    std::array<float, AcousticWeights::embeddingDim> input{};
    std::copy(embedding.begin(),
              embedding.begin() + AcousticClassifier::pannsDim,
              input.begin());

    const float normDur = std::min(static_cast<float>(durationSeconds) / 10.0f, 1.0f);
    float normDecay = std::min(f.decayTimeSeconds / 3.0f, 1.0f);
    // decayTimeSeconds is persisted (feature_version >= 4). A legacy row
    // predating that column reads back 0 and falls through to duration here,
    // exactly as a genuinely undetectable decay would.
    if (normDecay <= 0.001f) normDecay = normDur;

    const float rolloffRatio = std::min(f.spectralRolloff / 20000.0f, 1.0f);

    float* dsp = input.data() + AcousticClassifier::pannsDim;
    dsp[0] = normDur;
    dsp[1] = std::min(f.spectralCentroid / 16000.0f, 1.0f);
    dsp[2] = 1.0f - std::min(f.crestFactor / 20.0f, 1.0f);
    dsp[3] = std::min(std::max(f.zeroCrossingRate, 0.0f), 1.0f);
    dsp[4] = std::min(f.rmsAmplitude * 5.0f, 1.0f);
    dsp[5] = normDecay;
    dsp[6] = 1.0f - rolloffRatio;
    dsp[7] = rolloffRatio;

    // The DSP block is derived from cached doubles that could be NaN/Inf on a
    // corrupt row. isValidEmbedding() only covers the PANNs half, so guard
    // these here rather than let a non-finite value reach the matmul.
    for (int d = 0; d < AcousticClassifier::dspFeatureDim; ++d)
        if (!std::isfinite(dsp[d])) dsp[d] = 0.0f;

    return input;
}

bool hasUsableEmbedding(const SampleItem& sample)
{
    return sample.isProcessed
        && sample.embeddingStatus == EmbeddingStatus::Valid
        && hasSafeEmbeddingBuffer(sample.embedding);
}

// Apply the frozen acoustic head and its evidence/OOD gate to an embedding
// that is already available. Fresh rows and cache-hit rows must use the same
// path: cache hydration intentionally skips ONNX, but it must not skip the
// deterministic classifier over a valid persisted embedding when a stale
// taxonomy baseline has just been rebuilt.
void applyAcousticClassification(SampleItem& item)
{
    if (item.tagUserOverridden || !hasSafeEmbeddingBuffer(item.embedding)) return;

    // V4-F QUALIFICATION DIAGNOSTICS ONLY: snapshot the heuristic result
    // exactly as it stood before the ML gate can touch it.
    item.diagHeuristicCategoryPreML = item.category;
    item.diagHeuristicSubcategoryPreML = item.subcategory;
    item.diagHeuristicEvidencePreML = item.winningEvidence;
    item.diagHeuristicConfidencePreML = item.tagConfidence;

    const auto classifierInput = buildAcousticClassifierInput(
        item.embedding, item.audioFeatures, item.durationSeconds);
    AcousticClassifier::Result acRes = AcousticClassifier::classify520(classifierInput.data());
    item.diagMlEvaluated = true;
    item.diagMlSubcategory = acRes.subcategory;
    item.diagMlConfidence = acRes.confidence;
    item.diagMlIsOod = acRes.isOod;
    item.diagMlMargin = acRes.margin;
    item.diagMlEntropy = acRes.entropy;
    item.diagMlLogitEnergy = acRes.logitEnergy;
    item.diagMlCentroidCos = acRes.centroidCosineSimilarity;
    item.diagMlNearestCentroid = acRes.nearestCentroidIndex;
    item.classificationModelVersion = AcousticWeights::modelVersion;

    // V4-H: keep the ML-override/OOD decision in the pure gate so fresh and
    // cached embeddings cannot drift into different evidence semantics.
    MlOverrideGate::Input gateInput;
    gateInput.isOod = acRes.isOod;
    gateInput.mlConfidence = acRes.confidence;
    gateInput.winningEvidence = item.winningEvidence;
    gateInput.preMlCategory = item.category;
    gateInput.preMlSubcategory = item.subcategory;
    gateInput.preMlConfidence = item.tagConfidence;
    gateInput.mlSubcategory = acRes.subcategory;
    gateInput.durationSeconds = static_cast<double>(item.durationSeconds);
    if (item.category == "Vocals" && item.subcategory == "Vocal Loop") {
        const juce::String parentFolder = juce::File(item.filePath).getParentDirectory().getFileName();
        const auto vocalLoopEvidence = AbletonTaxonomy::detectFilenameSubcategoryEvidence(
            tokenizeString(juce::String(item.name)), tokenizeString(parentFolder),
            rawUnderscoreSplitLowercase(juce::String(item.name)));
        gateInput.preserveVocalLoopEvidence = vocalLoopEvidence.hasLoopToken
            || vocalLoopEvidence.hasTempoKeySuffix
            || vocalLoopEvidence.hasTempoMarker;
    }

    MlOverrideGate::Decision gateDecision = MlOverrideGate::evaluate(gateInput);
    item.category = gateDecision.category;
    item.subcategory = gateDecision.subcategory;
    item.tagConfidence = gateDecision.tagConfidence;
    item.tagSource = gateDecision.tagSource;
    item.winningEvidence = gateDecision.winningEvidence;
    item.diagMlOverrideApplied = gateDecision.overrideApplied;

    // Secondary tags are derived taxonomy state, not independent user data.
    // An OOD abstention must not remain searchable through stale Loop/
    // One-Shot/Atonal/fine-grained tags, and an ML override must not retain
    // tags produced for the superseded heuristic subcategory during a cache
    // refresh. Rebuild only the conservative tag implied by the final ML
    // subcategory; fine-grained labels are appended below.
    const auto addUniqueSecondaryTag = [&item](const std::string& tag) {
        if (tag.empty()) return;
        if (std::find(item.secondaryTags.begin(), item.secondaryTags.end(), tag)
                == item.secondaryTags.end())
            item.secondaryTags.push_back(tag);
    };
    if (gateDecision.tagSource == "ml_ood") {
        item.secondaryTags.clear();
    } else if (gateDecision.overrideApplied) {
        item.secondaryTags.clear();
        const bool isLoop = item.subcategory == "Bass Loop"
            || item.subcategory == "Synth Loop"
            || item.subcategory == "Music Loop"
            || item.subcategory == "Vocal Loop";
        if (!item.subcategory.empty())
            addUniqueSecondaryTag(isLoop ? "Loop" : "One-Shot");

        // Kick length is a separately documented, duration-only attribute;
        // preserve it when the primary Kick label is supplied by the acoustic
        // head rather than the heuristic classifier.
        if (item.subcategory == "Kick" && item.durationSeconds > 0.0f)
            addUniqueSecondaryTag(item.durationSeconds >= 0.7f ? "Long" : "Short");
    }

    // Fine-Grained Subcategorization V1, Phase 9: additive bass-timbre tag.
    if (item.subcategory == "Bass One-Shot" || item.subcategory == "Bass Loop") {
        auto bassTimbre = BassTimbreClassifier::classify(item.embedding.data());
        addUniqueSecondaryTag(bassTimbre.label);
    }

    // Fine-Grained Subcategorization V1, Phase 11: additive hi-hat type tag.
    if (item.subcategory == "Hi-Hat") {
        auto hihatType = HiHatTypeClassifier::classify(item.embedding.data());
        addUniqueSecondaryTag(hihatType.label);
    }

    // The acoustic gate may replace the heuristic subcategory (or abstain to
    // OOD), so enforce the tempo contract again against the final label. This
    // closes the path where a legacy/estimated BPM survived an ML override
    // that changed a loop into a one-shot.
    normalizeTempoForTaxonomy(item);
}
}

SampleManagerEngine::SampleManagerEngine()
    : Thread("SampleManagerEngine")
{
    formatManager.registerBasicFormats();
    openCacheDb();

    // The persisted cache is the library's startup source of truth. Loading it
    // asynchronously avoids blocking editor construction; notifyUpdateNow()
    // publishes the completed model to the UI once it is safe to render.
    hydrationThread = std::thread([this] { hydratePersistedSamples(); });

    // The batched-inference consumer runs continuously for the engine's lifetime
    // (not spun up per-scan) so it can coalesce work across back-to-back
    // addPathToQueue calls, not just within a single one.
    inferenceWorker = std::make_unique<InferenceWorker>(*this);
    inferenceWorker->startThread(juce::Thread::Priority::normal);

    // Persistent async metadata-write worker (see MetadataWriteWorker).
    metadataWriteWorker = std::make_unique<MetadataWriteWorker>(*this);
    metadataWriteWorker->startThread(juce::Thread::Priority::normal);
}

SampleManagerEngine::~SampleManagerEngine()
{
    if (hydrationThread.joinable())
        hydrationThread.join();

    // initAsync() (see docs/ASYNC_STARTUP.md) runs init() on a background
    // thread that touches env/session/engineState/modelPath -- all members
    // of this object. If the engine is destroyed while that thread is still
    // in flight (a fast construct-then-destroy, e.g. a host briefly
    // instantiating the plugin, or the crash reproduced this session inside
    // JUCE's VST3 moduleinfo-generation tooling), the thread would go on
    // touching a partially/fully destroyed object -- a real use-after-free,
    // not just a build-tool artifact. Joining here blocks destruction until
    // any in-flight init genuinely finishes, matching the same "wait for
    // background work before tearing down what it touches" pattern already
    // used below for scanPool/inferenceWorker/metadataWriteWorker.
    if (initThread.joinable())
        initThread.join();

    // Same reasoning as initThread above, for reorganizeSamplesAsync()'s
    // background thread (see docs/SORT_LIBRARY_BACKGROUND.md) -- it touches
    // samples/dbLock/sortDone/sortFailed/sortInProgress, all members of this
    // object. Request cancellation first (checked once per file in
    // reorganizeSamples()'s loop) so a fast destroy during a large in-progress
    // sort doesn't block until every remaining file has been moved -- then
    // join to guarantee the thread has genuinely stopped touching `this`
    // before anything below starts tearing it down.
    sortCancelRequested.store(true, std::memory_order_relaxed);
    if (sortThread.joinable())
        sortThread.join();

    signalThreadShouldExit();

    // Drop any not-yet-started work so drainQueueWorker jobs currently in flight
    // find the queue empty and return promptly, rather than churning through
    // everything still pending.
    {
        const juce::ScopedLock sl(queueLock);
        while (!pendingFiles.empty()) pendingFiles.pop();
    }

    // Worker jobs capture `this` — make sure they've all actually finished before
    // any members they touch (samples, dbLock, session, etc.) start being destroyed.
    scanPool.removeAllJobs(true, 5000);

    // Stop the inference thread before tearing down `session`/`samples`, which it
    // may still be touching mid-batch.
    if (inferenceWorker != nullptr) {
        inferenceWorker->signalThreadShouldExit();
        inferenceWorker->notify();
        inferenceWorker->waitForThreadToExit(5000);
    }

    // Stop the metadata-write worker before tearing down cacheDb, which it may
    // still be touching.
    if (metadataWriteWorker != nullptr) {
        metadataWriteWorker->signalThreadShouldExit();
        metadataWriteWorker->notify();
        metadataWriteWorker->waitForThreadToExit(5000);
    }

    // Wake up the coordinator thread if it's waiting
    notify();
    waitForThreadToExit(5000);
}

struct SampleManagerEngine::CacheDb {
    sqlite3* db = nullptr;
    sqlite3_stmt* selectStmt = nullptr;
    sqlite3_stmt* upsertStmt = nullptr;
    sqlite3_stmt* updateUmapStmt = nullptr;

    ~CacheDb() {
        if (selectStmt) sqlite3_finalize(selectStmt);
        if (upsertStmt) sqlite3_finalize(upsertStmt);
        if (updateUmapStmt) sqlite3_finalize(updateUmapStmt);
        if (db) sqlite3_close(db);
    }
};

// RECOVERY PHASE R1 -- test/production cache isolation (see
// docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md). File-scope (not a class static
// member) so it stays a plain global with ordinary static-init semantics;
// juce::File's default constructor is cheap/side-effect-free so there's no
// static-init-order hazard here.
static juce::File g_cacheDbDirectoryOverrideForTesting;

// P1-A (cache-root divergence) -- test-only override for the LEGACY cache
// location (see migrateLegacyCacheIfNeeded below), mirroring the current-location
// override. Lets the migration be exercised against disposable fixture copies
// rather than the owner's real ~/Library/SmartSampleManager directory.
static juce::File g_legacyCacheDbDirectoryOverrideForTesting;

void SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(const juce::File& dir)
{
    g_cacheDbDirectoryOverrideForTesting = dir;
}

juce::File SampleManagerEngine::getCacheDbFile()
{
    // Priority order (see docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §1,
    // recovered from the surviving doc after the incident):
    //  1. In-process test override (ScopedIsolatedCacheDb).
    //  2. SSM_CACHE_DB_DIR env var -- defense-in-depth for external tooling
    //     that drives the real Standalone binary and can't call the
    //     in-process API. No shipped code path sets this itself.
    //  3. Production default.
    juce::File cacheDir;
    if (g_cacheDbDirectoryOverrideForTesting != juce::File()) {
        cacheDir = g_cacheDbDirectoryOverrideForTesting;
    } else {
        juce::String envOverride = juce::SystemStats::getEnvironmentVariable("SSM_CACHE_DB_DIR", juce::String());
        cacheDir = envOverride.isNotEmpty()
            ? juce::File(envOverride)
            : juce::File::getSpecialLocation(juce::File::userApplicationDataDirectory)
                  .getChildFile("SmartSampleManager");
    }
    cacheDir.createDirectory();
    return cacheDir.getChildFile("sample_cache.sqlite3");
}

bool SampleManagerEngine::isKnownProductionCacheDbPath(const juce::File& candidate)
{
    juce::File productionCacheDir = juce::File::getSpecialLocation(juce::File::userApplicationDataDirectory)
                                         .getChildFile("SmartSampleManager");
    juce::File productionCacheFile = productionCacheDir.getChildFile("sample_cache.sqlite3");
    return candidate.getFullPathName() == productionCacheFile.getFullPathName();
}

void SampleManagerEngine::setLegacyCacheDbDirectoryOverrideForTesting(const juce::File& dir)
{
    g_legacyCacheDbDirectoryOverrideForTesting = dir;
}

namespace {
// Legacy cache root used by builds that predate the move to
// juce::File::userApplicationDataDirectory. Those builds stored the whole
// product data directory (cache + device_id.txt) directly under ~/Library/
// rather than ~/Library/Application Support/. See the P1-A finding in the
// hardening report.
juce::File getLegacyCacheDbFile()
{
    if (g_legacyCacheDbDirectoryOverrideForTesting != juce::File())
        return g_legacyCacheDbDirectoryOverrideForTesting.getChildFile("sample_cache.sqlite3");
    return juce::File::getSpecialLocation(juce::File::userHomeDirectory)
        .getChildFile("Library")
        .getChildFile("SmartSampleManager")
        .getChildFile("sample_cache.sqlite3");
}
}

// P1-A -- one-time, copy-based adoption of a cache left at the legacy
// ~/Library/SmartSampleManager location. This closes the cache-root divergence
// that stranded a user's real cache (and its favorites/history/collections/tag
// overrides/embeddings) at the old path while the new code looked at an empty
// ~/Library/Application Support/SmartSampleManager, silently forcing a full
// rescan and hiding user-created state.
//
// Safety:
//  * Copy, never move/delete -- the legacy file remains as a non-destructive
//    backup and the owner's originals are never renamed.
//  * Runs only for the production path, or when BOTH the current and legacy
//    test overrides are set (an explicit migration test). A plain test with
//    only the current override -- or any SSM_CACHE_DB_DIR env-var path --
//    never triggers it, so tests can never read/copy the owner's real cache.
//  * One-shot via a sibling marker file, so it can't loop, and clearCache()
//    (which deletes sample_cache.sqlite3* but not the marker) can't resurrect
//    the stale legacy snapshot.
void SampleManagerEngine::migrateLegacyCacheIfNeeded()
{
    const juce::File currentCacheFile = getCacheDbFile();

    const bool currentOverridden = (g_cacheDbDirectoryOverrideForTesting != juce::File());
    const bool legacyOverridden  = (g_legacyCacheDbDirectoryOverrideForTesting != juce::File());

    if (currentOverridden != legacyOverridden)
        return;  // isolated (current-only) test or partial override -- never migrate

    if (!currentOverridden && !isKnownProductionCacheDbPath(currentCacheFile))
        return;  // SSM_CACHE_DB_DIR env-var path -- never migrate

    const juce::File marker = currentCacheFile.getSiblingFile(".migrated-from-legacy");
    if (marker.existsAsFile())
        return;  // already migrated (idempotent, survives clearCache())

    if (currentCacheFile.existsAsFile() && currentCacheFile.getSize() > 0)
        return;  // a populated cache already exists at the current location

    const juce::File legacyCacheFile = getLegacyCacheDbFile();
    if (legacyCacheFile.getFullPathName() == currentCacheFile.getFullPathName())
        return;  // legacy == current, nothing to do

    if (!legacyCacheFile.existsAsFile() || legacyCacheFile.getSize() <= 0)
        return;  // no legacy data to adopt

    AppLogger::getInstance().logInfo(
        "Migrating legacy sample cache " + legacyCacheFile.getFullPathName()
        + " -> " + currentCacheFile.getFullPathName());

    const juce::File currentDir = currentCacheFile.getParentDirectory();
    currentDir.createDirectory();

    if (!legacyCacheFile.copyFileTo(currentCacheFile)) {
        AppLogger::getInstance().logWarning("Legacy cache migration failed (main DB copy); will rescan instead.");
        return;
    }

    // Preserve any uncheckpointed WAL/SHM sidecars so a hot legacy cache isn't
    // adopted without its in-flight transaction state.
    const juce::File legacyWal = legacyCacheFile.getSiblingFile(legacyCacheFile.getFileName() + "-wal");
    if (legacyWal.existsAsFile())
        legacyWal.copyFileTo(currentDir.getChildFile(currentCacheFile.getFileName() + "-wal"));
    const juce::File legacyShm = legacyCacheFile.getSiblingFile(legacyCacheFile.getFileName() + "-shm");
    if (legacyShm.existsAsFile())
        legacyShm.copyFileTo(currentDir.getChildFile(currentCacheFile.getFileName() + "-shm"));

    marker.create();
}

// Bump whenever the embedding model or the UMAP algorithm/parameters change
// in a way that makes previously-computed 2D coordinates meaningless against
// newly-computed ones (different embedding space entirely). Checked against
// cache_meta's stored value in openCacheDb() -- a mismatch wipes all
// persisted umap_x/umap_y values so stale and fresh layouts never mix.
static constexpr int kUmapLayoutVersion = 1;

// Below this many processed samples, umappp's SVD step can fail outright
// (observed: "requested number of singular values cannot be greater than
// the smaller matrix dimension" at nobs=2 -- see docs/SEARCH_QUALITY_AUDIT.md).
// Short-circuit to a deterministic placement instead of hitting that error.
static constexpr int kMinSamplesForUmapProjection = 5;

// After this many consecutive inference failures for the same file, stop
// retrying it on every single future scan -- see docs/ONNX_FAILURE_HANDLING.md.
// Still user-recoverable (a fresh scan after fixing the underlying file, or
// clearCache(), resets the counter), just not silently retried forever.
static constexpr int kMaxEmbeddingFailuresBeforePermanent = 3;

namespace {
// ---------------------------------------------------------------------------
// Cache integrity classification + user-state salvage/restore.
//
// The cache DB is a single physical SQLite file that holds BOTH regenerable
// derived data (sample_cache, cache_meta) AND irreplaceable user data
// (user_favorites, preview_history, smart_collections, and the user tag
// overrides embedded in sample_cache rows where tag_user_overridden=1).
//
// A database must only be quarantined (file renamed + rebuilt) when there is
// strong evidence of persistent physical corruption. SQLITE_BUSY / LOCKED /
// transient IO errors must NEVER trigger quarantine -- the original
// quickCheckPassed() collapsed all of these into a single "false", which
// meant a healthy cache could be quarantined simply because a concurrent
// plugin instance held a lock during open. That is the most likely root cause
// of the dozens of .corrupt-* artifacts observed in the field.
// ---------------------------------------------------------------------------

enum class CacheIntegrity
{
    Healthy,       // quick_check returned "ok"
    Busy,          // SQLITE_BUSY -- another connection holds a lock
    Locked,        // SQLITE_LOCKED -- a lock is held within this process
    IoError,       // SQLITE_IOERR -- transient disk/IO problem
    Corrupt,       // genuine database corruption (or quick_check reported errors)
    NotADb,        // SQLITE_NOTADB -- the file is not a SQLite database
    Unknown        // any other unexpected condition
};

struct IntegrityResult
{
    CacheIntegrity status = CacheIntegrity::Unknown;
    std::string reason;
};

IntegrityResult classifyCacheIntegrity(sqlite3* rawDb)
{
    IntegrityResult out;

    sqlite3_stmt* stmt = nullptr;
    int prepRc = sqlite3_prepare_v2(rawDb, "PRAGMA quick_check;", -1, &stmt, nullptr);
    if (prepRc != SQLITE_OK)
    {
        const char* msg = sqlite3_errmsg(rawDb);
        out.reason = (msg != nullptr) ? msg : "";
        switch (sqlite3_extended_errcode(rawDb))
        {
            case SQLITE_BUSY:   out.status = CacheIntegrity::Busy;    break;
            case SQLITE_LOCKED: out.status = CacheIntegrity::Locked;  break;
            case SQLITE_IOERR:  out.status = CacheIntegrity::IoError; break;
            case SQLITE_CORRUPT: out.status = CacheIntegrity::Corrupt; break;
            case SQLITE_NOTADB: out.status = CacheIntegrity::NotADb;  break;
            default:            out.status = CacheIntegrity::Unknown; break;
        }
        return out;
    }

    int stepRc = sqlite3_step(stmt);
    if (stepRc == SQLITE_ROW)
    {
        const unsigned char* text = sqlite3_column_text(stmt, 0);
        const char* ctext = (text != nullptr) ? reinterpret_cast<const char*>(text) : "";
        out.reason = ctext;
        out.status = (juce::String(ctext) == "ok") ? CacheIntegrity::Healthy : CacheIntegrity::Corrupt;
    }
    else if (stepRc == SQLITE_BUSY)
    {
        out.status = CacheIntegrity::Busy;
        out.reason = "quick_check returned SQLITE_BUSY";
    }
    else if (stepRc == SQLITE_LOCKED)
    {
        out.status = CacheIntegrity::Locked;
        out.reason = "quick_check returned SQLITE_LOCKED";
    }
    else
    {
        const char* msg = sqlite3_errmsg(rawDb);
        out.reason = (msg != nullptr) ? msg : "";
        int err = sqlite3_extended_errcode(rawDb);
        out.status = (err == SQLITE_CORRUPT || err == SQLITE_NOTADB)
            ? CacheIntegrity::Corrupt
            : CacheIntegrity::Unknown;
    }
    sqlite3_finalize(stmt);
    return out;
}

// Thin compatibility wrapper kept for checkCacheIntegrity()'s boolean API.
// Returns true only for a genuinely healthy database.
bool quickCheckPassed(sqlite3* rawDb)
{
    return classifyCacheIntegrity(rawDb).status == CacheIntegrity::Healthy;
}

// Irreplaceable user state salvaged out of a corrupt cache before the file is
// quarantined, then re-inserted into the freshly rebuilt cache so a rebuild
// never silently destroys user intent (favorites/history/collections/tag
// overrides). See the hardening brief sections 9 and 36.
struct SalvagedUserState
{
    struct Favorite    { std::string path; long long addedAt = 0; };
    struct HistoryRow  { std::string path; long long previewedAt = 0; };
    struct Collection  { std::string name; std::string queryRules; };
    struct TagOverride { std::string path; std::string category; std::string subcategory;
                         std::string secondaryTags; double confidence = 0.0; std::string source; };

    std::vector<Favorite>    favorites;
    std::vector<HistoryRow>  history;
    std::vector<Collection>  collections;
    std::vector<TagOverride> overrides;
};

void salvageUserState(sqlite3* db, SalvagedUserState& out)
{
    if (db == nullptr) return;

    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db, "SELECT path, added_at FROM user_favorites ORDER BY added_at ASC;", -1, &stmt, nullptr) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                SalvagedUserState::Favorite f;
                const unsigned char* p = sqlite3_column_text(stmt, 0);
                if (p) f.path = reinterpret_cast<const char*>(p);
                f.addedAt = sqlite3_column_int64(stmt, 1);
                out.favorites.push_back(std::move(f));
            }
            sqlite3_finalize(stmt);
        }
    }

    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db, "SELECT path, previewed_at FROM preview_history ORDER BY id ASC;", -1, &stmt, nullptr) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                SalvagedUserState::HistoryRow h;
                const unsigned char* p = sqlite3_column_text(stmt, 0);
                if (p) h.path = reinterpret_cast<const char*>(p);
                h.previewedAt = sqlite3_column_int64(stmt, 1);
                out.history.push_back(std::move(h));
            }
            sqlite3_finalize(stmt);
        }
    }

    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db, "SELECT name, query_rules FROM smart_collections ORDER BY name ASC;", -1, &stmt, nullptr) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                SalvagedUserState::Collection c;
                const unsigned char* n = sqlite3_column_text(stmt, 0);
                if (n) c.name = reinterpret_cast<const char*>(n);
                const unsigned char* r = sqlite3_column_text(stmt, 1);
                if (r) c.queryRules = reinterpret_cast<const char*>(r);
                out.collections.push_back(std::move(c));
            }
            sqlite3_finalize(stmt);
        }
    }

    // Best-effort: salvage user tag overrides from sample_cache (legacy
    // location). These rows may be unreadable if sample_cache itself is the
    // corrupt table; the durable recovery path going forward is the dedicated
    // user_tag_overrides table.
    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db,
                "SELECT path, category, subcategory, secondary_tags, tag_confidence, tag_source "
                "FROM sample_cache WHERE tag_user_overridden = 1;", -1, &stmt, nullptr) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                SalvagedUserState::TagOverride o;
                auto copyText = [&](int col, std::string& dest) {
                    const unsigned char* t = sqlite3_column_text(stmt, col);
                    if (t) dest = reinterpret_cast<const char*>(t);
                };
                copyText(0, o.path);
                copyText(1, o.category);
                copyText(2, o.subcategory);
                copyText(3, o.secondaryTags);
                o.confidence = sqlite3_column_double(stmt, 4);
                copyText(5, o.source);
                out.overrides.push_back(std::move(o));
            }
            sqlite3_finalize(stmt);
        }
    }

    // Salvage from the durable user_tag_overrides table too (the current
    // home of manual corrections). Appended after the legacy sample_cache
    // overrides so restoreUserState()'s INSERT OR REPLACE gives this table
    // the final word for any path present in both.
    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db,
                "SELECT path, category, subcategory, secondary_tags, tag_confidence, tag_source "
                "FROM user_tag_overrides ORDER BY path ASC;", -1, &stmt, nullptr) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                SalvagedUserState::TagOverride o;
                auto copyText = [&](int col, std::string& dest) {
                    const unsigned char* t = sqlite3_column_text(stmt, col);
                    if (t) dest = reinterpret_cast<const char*>(t);
                };
                copyText(0, o.path);
                copyText(1, o.category);
                copyText(2, o.subcategory);
                copyText(3, o.secondaryTags);
                o.confidence = sqlite3_column_double(stmt, 4);
                copyText(5, o.source);
                out.overrides.push_back(std::move(o));
            }
            sqlite3_finalize(stmt);
        }
    }
}

void restoreUserState(sqlite3* db, const SalvagedUserState& state)
{
    if (db == nullptr) return;

    sqlite3_exec(db, "BEGIN TRANSACTION;", nullptr, nullptr, nullptr);
    int writeFailures = 0;

    for (const auto& f : state.favorites)
    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db, "INSERT OR REPLACE INTO user_favorites (path, added_at) VALUES (?, ?);", -1, &stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(stmt, 1, f.path.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_int64(stmt, 2, f.addedAt);
            if (logWriteStep(db, stmt, "restore favorites") != SQLITE_DONE) writeFailures++;
            sqlite3_finalize(stmt);
        }
    }

    for (const auto& h : state.history)
    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db, "INSERT INTO preview_history (path, previewed_at) VALUES (?, ?);", -1, &stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(stmt, 1, h.path.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_int64(stmt, 2, h.previewedAt);
            if (logWriteStep(db, stmt, "restore history") != SQLITE_DONE) writeFailures++;
            sqlite3_finalize(stmt);
        }
    }

    for (const auto& c : state.collections)
    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db, "INSERT OR REPLACE INTO smart_collections (name, query_rules) VALUES (?, ?);", -1, &stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(stmt, 1, c.name.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 2, c.queryRules.c_str(), -1, SQLITE_TRANSIENT);
            if (logWriteStep(db, stmt, "restore collections") != SQLITE_DONE) writeFailures++;
            sqlite3_finalize(stmt);
        }
    }

    for (const auto& o : state.overrides)
    {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db,
                "INSERT OR REPLACE INTO user_tag_overrides "
                "(path, category, subcategory, secondary_tags, tag_confidence, tag_source) "
                "VALUES (?, ?, ?, ?, ?, ?);", -1, &stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(stmt, 1, o.path.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 2, o.category.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 3, o.subcategory.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 4, o.secondaryTags.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_double(stmt, 5, o.confidence);
            sqlite3_bind_text(stmt, 6, o.source.c_str(), -1, SQLITE_TRANSIENT);
            if (logWriteStep(db, stmt, "restore tag overrides") != SQLITE_DONE) writeFailures++;
            sqlite3_finalize(stmt);
        }
    }

    if (writeFailures > 0) {
        // Never keep a half-restored state: a user who just weathered a cache
        // rebuild would have their favorites/history half-restored and missing
        // the rest, with nothing logged to explain it.
        sqlite3_exec(db, "ROLLBACK;", nullptr, nullptr, nullptr);
        AppLogger::getInstance().logError(
            "SQLite: restoreUserState rolled back " + juce::String(writeFailures)
            + " failed write(s) -- the rebuilt cache will start with no salvaged state");
    } else {
        sqlite3_exec(db, "COMMIT;", nullptr, nullptr, nullptr);
    }
}

std::string canonicalizeTaxonomyString(const std::string& input)
{
    if (input == "Hat" || input == "HiHat" || input == "Hi Hat" || input == "Hihat")
    {
        return "Hi-Hat";
    }
    return input;
}

std::vector<std::string> tokenizeString(const juce::String& str)
{
    std::vector<std::string> tokens;
    juce::String currentToken = "";
    
    for (int i = 0; i < str.length(); ++i)
    {
        juce::juce_wchar c = str[i];
        
        // Split by separators
        bool isSeparator = (c == '_' || c == '-' || c == ' ' || c == '.' || 
                            c == '(' || c == ')' || c == '[' || c == ']' || 
                            c == '{' || c == '}' || (c >= '0' && c <= '9'));
        
        // Handle CamelCase transition
        bool isCamelTransition = false;
        if (i > 0 && !isSeparator)
        {
            juce::juce_wchar prev = str[i - 1];
            if (juce::CharacterFunctions::isLowerCase(prev) && juce::CharacterFunctions::isUpperCase(c))
            {
                isCamelTransition = true;
            }
        }
        
        if (isSeparator || isCamelTransition)
        {
            if (currentToken.isNotEmpty())
            {
                tokens.push_back(currentToken.toLowerCase().toStdString());
                currentToken = "";
            }
            if (!isSeparator)
            {
                currentToken += c;
            }
        }
        else
        {
            currentToken += c;
        }
    }
    
    if (currentToken.isNotEmpty())
    {
        tokens.push_back(currentToken.toLowerCase().toStdString());
    }
    
    return tokens;
}

bool containsAnyToken(const std::vector<std::string>& tokens, const std::vector<std::string>& searchList)
{
    for (const auto& token : tokens)
    {
        for (const auto& searchItem : searchList)
        {
            if (token == searchItem)
                return true;
        }
    }
    return false;
}
} // end anonymous namespace

juce::StringArray extractSemanticFilenameTokens(const juce::String& filename)
{
    juce::StringArray result;
    juce::StringArray baseTokens;
    baseTokens.addTokens(filename, "_ -", "\"");

    for (const auto& token : baseTokens)
    {
        juce::String t = token.trim();
        if (t.isEmpty()) continue;
        result.add(t);

        // Split CamelCase and letter/digit transitions
        juce::String currentSub = "";
        for (int i = 0; i < t.length(); ++i)
        {
            juce::juce_wchar c = t[i];
            juce::juce_wchar prev = (i > 0) ? t[i - 1] : 0;

            bool isUpper = juce::CharacterFunctions::isUpperCase(c);
            bool prevLower = (i > 0) && juce::CharacterFunctions::isLowerCase(prev);
            bool isDigit = juce::CharacterFunctions::isDigit(c);
            bool prevDigit = (i > 0) && juce::CharacterFunctions::isDigit(prev);
            bool isLetter = juce::CharacterFunctions::isLetter(c);
            bool prevLetter = (i > 0) && juce::CharacterFunctions::isLetter(prev);

            // Boundary 1: lower -> UPPER (e.g. reeseBass)
            // Boundary 2: letter -> DIGIT (e.g. lead128)
            // Boundary 3: digit -> LETTER (e.g. 128bpm)
            bool boundary = (isUpper && prevLower) ||
                            (isDigit && prevLetter) ||
                            (isLetter && prevDigit);

            if (boundary && currentSub.isNotEmpty())
            {
                result.add(currentSub);
                currentSub = "";
            }
            currentSub += juce::String::charToString(c);
        }
        if (currentSub.isNotEmpty())
            result.add(currentSub);
    }

    return result;
}

// Semantic, digit-preserving split for filename analysis (CamelCase-aware,
// digit/letter boundary-aware, and "_ -"-delimited).
// Used to feed AbletonTaxonomy::detectFilenameSubcategoryEvidence's
// BPM+key filename-suffix evidence (see AbletonTaxonomy.h/.cpp).
std::vector<std::string> rawUnderscoreSplitLowercase(const juce::String& str)
{
    juce::StringArray parts = extractSemanticFilenameTokens(str);
    std::vector<std::string> out;
    out.reserve(static_cast<size_t>(parts.size()));
    for (auto& p : parts) {
        juce::String trimmed = p.trim().toLowerCase();
        if (trimmed.isNotEmpty())
            out.push_back(trimmed.toStdString());
    }
    return out;
}

// Applies a persisted user tag override (if any) on top of a freshly-loaded
// sample_cache row. Called from tryLoadFromCache() while the cache lock is
// held, so a user's manual classification correction survives even when the
// underlying sample_cache row was regenerated (e.g. after a quarantine).
void applyUserTagOverride(sqlite3* db, SampleItem& item)
{
    if (db == nullptr) return;
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db,
            "SELECT category, subcategory, secondary_tags, tag_confidence, tag_source "
            "FROM user_tag_overrides WHERE path = ?;", -1, &stmt, nullptr) != SQLITE_OK)
        return;
    sqlite3_bind_text(stmt, 1, item.filePath.c_str(), -1, SQLITE_TRANSIENT);
    if (sqlite3_step(stmt) == SQLITE_ROW)
    {
        const unsigned char* cat = sqlite3_column_text(stmt, 0);
        const unsigned char* sub = sqlite3_column_text(stmt, 1);
        const unsigned char* tags = sqlite3_column_text(stmt, 2);
        item.category = cat ? canonicalizeTaxonomyString(reinterpret_cast<const char*>(cat)) : "";
        item.subcategory = sub ? canonicalizeTaxonomyString(reinterpret_cast<const char*>(sub)) : "";
        item.secondaryTags.clear();
        if (tags != nullptr)
        {
            juce::StringArray parts = juce::StringArray::fromTokens(
                reinterpret_cast<const char*>(tags), "|", "");
            for (const auto& part : parts)
                if (part.isNotEmpty())
                    item.secondaryTags.push_back(canonicalizeTaxonomyString(part.toStdString()));
        }
        item.tagConfidence = static_cast<float>(sqlite3_column_double(stmt, 3));
        const unsigned char* src = sqlite3_column_text(stmt, 4);
        item.tagSource = src ? reinterpret_cast<const char*>(src) : "user";
        item.tagUserOverridden = true;
        item.winningEvidence = "USER_OVERRIDE";
    }
    sqlite3_finalize(stmt);
}

void SampleManagerEngine::openCacheDb(bool isRetryAfterQuarantine)
{
    juce::File cacheFile = getCacheDbFile();

#if defined(SSM_TEST_BINARY)
    // RECOVERY PHASE R1 P0 fail-closed backstop (see
    // docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md / AGENT_SAFETY.md). Every
    // Test*/Benchmark* CMake target defines SSM_TEST_BINARY. If such a
    // binary resolves to the real production cache path -- i.e. no
    // ScopedIsolatedCacheDb (setCacheDbDirectoryOverrideForTesting) is
    // active -- refuse before ever calling sqlite3_open, rather than
    // silently reading/writing/clearing the user's real cache. This is what
    // makes the incident (a test run observed shrinking the real 4,743,168
    // byte production DB to 1,363,968 bytes) mechanically difficult to
    // reintroduce, independent of any individual test remembering isolation.
    if (isKnownProductionCacheDbPath(cacheFile)) {
        AppLogger::getInstance().logError(
            "Refusing to execute test against production SLO cache: " + cacheFile.getFullPathName());
        std::cerr << "FATAL: Refusing to execute test against production SLO cache." << std::endl;
        std::abort();
    }
#endif

    // P1-A cache-root divergence: one-time adoption of a legacy-location cache
    // (production / explicit-test-override only -- see the function).
    migrateLegacyCacheIfNeeded();

    sqlite3* rawDb = nullptr;
    if (sqlite3_open(cacheFile.getFullPathName().toRawUTF8(), &rawDb) != SQLITE_OK) {
        AppLogger::getInstance().logError("Failed to open sample cache DB at " + cacheFile.getFullPathName());
        if (rawDb) sqlite3_close(rawDb);
        return;
    }

    // WAL mode: readers (a future "browse cache without a full rescan" feature)
    // never block writers and vice versa.
    sqlite3_exec(rawDb, "PRAGMA journal_mode=WAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "PRAGMA synchronous=NORMAL;", nullptr, nullptr, nullptr);
    // Concurrent multi-instance access (two plugin instances scanning
    // simultaneously) can otherwise surface as an immediate SQLITE_BUSY on
    // whichever instance loses a write race, rather than a bounded wait --
    // see docs/REALTIME_SAFETY_AUDIT.md P3 finding. 5s covers a full
    // upsert-batch write under normal load without risking an unbounded
    // stall if something is actually wedged.
    sqlite3_busy_timeout(rawDb, 5000);

    // Cache DB corruption must never be mistaken for "no cache" (which would
    // silently force a full rescan/re-embed with no explanation) or crash --
    // detect it explicitly and rebuild a fresh cache in place. Only the
    // derived cache is ever touched here; original sample audio is never at
    // risk. Skip on the recursive re-open after a quarantine to avoid looping.
    //
    // IMPORTANT: only genuine corruption (or a file that is not a database)
    // quarantines. SQLITE_BUSY / SQLITE_LOCKED / transient IO errors are NOT
    // corruption and must never destroy a healthy cache -- previously any
    // failed quick_check (including a concurrent-writer lock) was treated as
    // corruption, which is the most likely cause of the repeated quarantine
    // events observed in the field. User state (favorites/history/collections/
    // tag overrides) is salvaged before the file is renamed and restored after
    // the rebuild so a rebuild never destroys user intent.
    if (!isRetryAfterQuarantine) {
        IntegrityResult integrity = classifyCacheIntegrity(rawDb);
        if (integrity.status == CacheIntegrity::Corrupt || integrity.status == CacheIntegrity::NotADb) {
            AppLogger::getInstance().logError(
                "Sample cache DB failed integrity check (" + juce::String(integrity.reason.c_str())
                + ") -- salvaging user state, then quarantining and rebuilding. "
                + "Source audio files are not affected; only cached metadata/embeddings will be re-scanned.");

            SalvagedUserState salvaged;
            salvageUserState(rawDb, salvaged);
            sqlite3_close(rawDb);

            juce::String quarantineSuffix = ".corrupt-" + juce::String(juce::Time::getCurrentTime().toMilliseconds());
            cacheFile.moveFileTo(cacheFile.getSiblingFile(cacheFile.getFileName() + quarantineSuffix));
            cacheFile.getSiblingFile(cacheFile.getFileName() + "-wal")
                .moveFileTo(cacheFile.getSiblingFile(cacheFile.getFileName() + "-wal" + quarantineSuffix));
            cacheFile.getSiblingFile(cacheFile.getFileName() + "-shm")
                .moveFileTo(cacheFile.getSiblingFile(cacheFile.getFileName() + "-shm" + quarantineSuffix));

            openCacheDb(true);
            restoreUserState(cacheDb ? cacheDb->db : nullptr, salvaged);
            return;
        }

        if (integrity.status != CacheIntegrity::Healthy) {
            AppLogger::getInstance().logError(
                "Sample cache integrity check inconclusive ("
                + juce::String(integrity.reason.c_str())
                + ") -- continuing WITHOUT quarantine; the cache is treated as healthy.");
        }
    }

    const char* createTableSql =
        "CREATE TABLE IF NOT EXISTS sample_cache ("
        "  path TEXT PRIMARY KEY,"
        "  mtime INTEGER NOT NULL,"
        "  size INTEGER NOT NULL,"
        "  bpm REAL,"
        "  key TEXT,"
        "  instrument_type TEXT,"
        "  embedding BLOB"
        ");";
    char* errMsg = nullptr;
    if (sqlite3_exec(rawDb, createTableSql, nullptr, nullptr, &errMsg) != SQLITE_OK) {
        AppLogger::getInstance().logError(juce::String("Failed to create sample_cache table: ") + (errMsg ? errMsg : "unknown error"));
        sqlite3_free(errMsg);
        sqlite3_close(rawDb);
        return;
    }

    // Additive migration for pre-existing cache DBs from before content_hash
    // existed. Errors (e.g. "duplicate column name" on a DB that already has
    // it) are expected and harmless -- intentionally not checked.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN content_hash TEXT;", nullptr, nullptr, nullptr);

    // Additive migration for the Ableton taxonomy fields. Same pattern:
    // each ALTER TABLE either succeeds once (fresh column) or fails
    // harmlessly forever after ("duplicate column name") -- not checked.
    // secondary_tags is stored "|"-joined (matching the separator Ableton's
    // own XMP tag format uses, so it reads naturally if ever surfaced
    // there) rather than as a second table, since a sample only ever has a
    // handful of secondary tags.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN category TEXT;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN subcategory TEXT;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN secondary_tags TEXT;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN tag_confidence REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN tag_source TEXT;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN tag_user_overridden INTEGER;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN taxonomy_version INTEGER;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN duration_seconds REAL;", nullptr, nullptr, nullptr);

    // Persisted UMAP 2D layout -- see docs/UMAP_PERSISTENCE.md. NULL until a
    // projection has actually been computed and written back for this row.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN umap_x REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN umap_y REAL;", nullptr, nullptr, nullptr);

    // Embedding pipeline outcome -- see docs/ONNX_FAILURE_HANDLING.md.
    // NULL (pre-existing rows from before this migration) is treated the
    // same as Valid provided the embedding blob itself is present and the
    // right size, for backward compatibility with caches written before
    // this column existed.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN embedding_status INTEGER;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN embedding_failure_count INTEGER;", nullptr, nullptr, nullptr);

    // RECOVERY PHASE R2 -- Audio Feature Analysis persistence (brief section
    // 34/36), CORRECTED during R3 (brief section 86): originally implemented
    // as one version column plus a single pipe-delimited packed TEXT column
    // (see the now-removed serializeAudioFeatures/deserializeAudioFeatures),
    // an R2-invented shortcut with no direct evidence behind the packing
    // format itself. R3-G's forensics surfaced a genuine contradiction: TWO
    // independent pre-incident sources -- docs/SMART_SAMPLE_MANAGER_FEATURE_ARCHITECTURE.md
    // §5 ("Added 11 new columns to sample_cache via additive migrations",
    // naming all ten fields as individual snake_case columns:
    // peak_amplitude/rms_amplitude/crest_factor/zero_crossing_rate/
    // onset_count/spectral_centroid/spectral_rolloff/original_sample_rate/
    // original_channels/original_bit_depth, i.e. 10 + feature_version = 11)
    // and Source/test_cache_version_enforcement_main.cpp (a surviving
    // pre-incident test that directly `UPDATE sample_cache SET
    // peak_amplitude = ...` against a real column) -- both independently
    // show the real historical schema used individual named columns, not a
    // packed blob. Corrected here per brief section 86 rather than editing
    // the test, since the test is the harder-to-fake evidence (a schema a
    // test binary actually executed SQL against, not a doc's prose).
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN feature_version INTEGER;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN peak_amplitude REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN rms_amplitude REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN crest_factor REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN zero_crossing_rate REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN onset_count INTEGER;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN spectral_centroid REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN spectral_rolloff REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN original_sample_rate REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN original_channels INTEGER;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN original_bit_depth INTEGER;", nullptr, nullptr, nullptr);
    // feature_version 4: decayTimeSeconds became a classifier input (DSP dim 5
    // of the 520-D acoustic head). Before this column existed it was recomputed
    // per scan and never persisted, so a cache-hydrated row classified with the
    // duration fallback while a freshly-analysed row used the real decay -- the
    // same file tagged differently depending on cache state. Persist it.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN decay_time_seconds REAL;", nullptr, nullptr, nullptr);
    // Physical-acoustics advisory fields. Nullable so legacy rows remain
    // explicitly Unknown until a real reanalysis populates them.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN physical_class TEXT;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN physical_material INTEGER;", nullptr, nullptr, nullptr);
    // FFT evidence sidecar (feature version 7). Individual nullable columns
    // keep migrations additive and make the values inspectable for audits.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN low_band_energy_ratio REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN mid_band_energy_ratio REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN high_band_energy_ratio REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN spectral_flux_mean REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN spectral_flux_std REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN spectral_flux_peak_rate REAL;", nullptr, nullptr, nullptr);

    // RECOVERY PHASE R3-G -- Cache Version Enforcement (brief section 57-64;
    // see docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §3, a pre-incident
    // doc documenting this exact column). NULL (a row from before this
    // migration) is deliberately read back as *current*, not stale -- see
    // tryLoadFromCache() below and the doc's "legacy-row handling differs by
    // field" note: those rows already have a real, valid embedding blob,
    // just no version bookkeeping for it, so treating NULL as stale would
    // force every existing user's whole library through an unnecessary
    // one-time mass re-embed the moment this migration ships.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN embedding_model_version INTEGER;", nullptr, nullptr, nullptr);
    // Taxonomy provenance was historically held only in SampleItem. Persist
    // it beside the taxonomy fields so restart/hydration cannot silently turn
    // a known filename/DSP/user decision into UNKNOWN.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN winning_evidence TEXT;", nullptr, nullptr, nullptr);
    // Keep the acoustic head's version separate from the embedding model and
    // Ableton taxonomy versions. A head change must invalidate cached ML
    // decisions while retaining a compatible embedding for cheap reclassify.
    sqlite3_exec(rawDb, "ALTER TABLE sample_cache ADD COLUMN classification_model_version INTEGER;", nullptr, nullptr, nullptr);
    const std::string stampLegacyClassificationVersion =
        "UPDATE sample_cache SET classification_model_version = "
        + std::to_string(AcousticWeights::modelVersion)
        + " WHERE classification_model_version IS NULL AND embedding IS NOT NULL;";
    sqlite3_exec(rawDb, stampLegacyClassificationVersion.c_str(), nullptr, nullptr, nullptr);

    // Small key/value table for cache-wide metadata not tied to any one
    // sample row -- currently just the UMAP layout's invalidation version.
    sqlite3_exec(rawDb,
        "CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT);",
        nullptr, nullptr, nullptr);

    // RECOVERY PHASE R1 -- Favorites / History / Smart Collections tables.
    // Schema recovered verbatim from the live production DB (these tables
    // and their exact columns survived the incident inside the DB file even
    // though the engine code that read/wrote them was lost -- see
    // docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md). User data, not derived
    // cache -- deliberately NOT touched by clearCache().
    sqlite3_exec(rawDb,
        "CREATE TABLE IF NOT EXISTS user_favorites ("
        "  path TEXT PRIMARY KEY,"
        "  added_at INTEGER NOT NULL"
        ");",
        nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb,
        "CREATE TABLE IF NOT EXISTS preview_history ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  path TEXT NOT NULL,"
        "  previewed_at INTEGER NOT NULL"
        ");",
        nullptr, nullptr, nullptr);
    sqlite3_exec(rawDb,
        "CREATE TABLE IF NOT EXISTS smart_collections ("
        "  name TEXT PRIMARY KEY,"
        "  query_rules TEXT NOT NULL"
        ");",
        nullptr, nullptr, nullptr);

    // User tag overrides live in their own table so that a cache rebuild
    // (quarantine) never loses the user's manually-corrected classifications,
    // which are irreplaceable product data. Previously these were stored only
    // as tag_user_overridden=1 rows inside the regenerable sample_cache table,
    // so a quarantine wiped them. See the hardening brief sections 9 and 36.
    sqlite3_exec(rawDb,
        "CREATE TABLE IF NOT EXISTS user_tag_overrides ("
        "  path TEXT PRIMARY KEY,"
        "  category TEXT,"
        "  subcategory TEXT,"
        "  secondary_tags TEXT,"
        "  tag_confidence REAL,"
        "  tag_source TEXT"
        ");",
        nullptr, nullptr, nullptr);

    // If the embedding model or UMAP algorithm/parameters ever change,
    // bump kUmapLayoutVersion (SampleManagerEngine.cpp) -- any persisted
    // layout computed under an older version is no longer meaningful
    // (different embedding space entirely), so wipe it here rather than let
    // stale coordinates silently mix with freshly-computed ones.
    {
        sqlite3_stmt* metaStmt = nullptr;
        int storedVersion = -1;
        if (sqlite3_prepare_v2(rawDb, "SELECT value FROM cache_meta WHERE key = 'umap_layout_version';",
                                -1, &metaStmt, nullptr) == SQLITE_OK) {
            if (sqlite3_step(metaStmt) == SQLITE_ROW) {
                const unsigned char* text = sqlite3_column_text(metaStmt, 0);
                if (text) storedVersion = juce::String(reinterpret_cast<const char*>(text)).getIntValue();
            }
            sqlite3_finalize(metaStmt);
        }

        if (storedVersion != kUmapLayoutVersion) {
            sqlite3_exec(rawDb, "UPDATE sample_cache SET umap_x = NULL, umap_y = NULL;", nullptr, nullptr, nullptr);
            sqlite3_stmt* upsertMetaStmt = nullptr;
            if (sqlite3_prepare_v2(rawDb,
                    "INSERT INTO cache_meta (key, value) VALUES ('umap_layout_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
                    -1, &upsertMetaStmt, nullptr) == SQLITE_OK) {
                juce::String versionStr(kUmapLayoutVersion);
                sqlite3_bind_text(upsertMetaStmt, 1, versionStr.toRawUTF8(), -1, SQLITE_TRANSIENT);
                sqlite3_step(upsertMetaStmt);
                sqlite3_finalize(upsertMetaStmt);
            }
        }
    }

    auto db = std::make_unique<CacheDb>();
    db->db = rawDb;

    sqlite3_prepare_v2(rawDb,
        "SELECT mtime, size, bpm, key, instrument_type, embedding, content_hash, "
        "category, subcategory, secondary_tags, tag_confidence, tag_source, tag_user_overridden, "
        "taxonomy_version, duration_seconds, umap_x, umap_y, embedding_status, embedding_failure_count, "
        "feature_version, peak_amplitude, rms_amplitude, crest_factor, zero_crossing_rate, onset_count, "
        "spectral_centroid, spectral_rolloff, original_sample_rate, original_channels, original_bit_depth, "
        "embedding_model_version, winning_evidence, classification_model_version, "
        "decay_time_seconds, physical_class, physical_material, "
        "low_band_energy_ratio, mid_band_energy_ratio, high_band_energy_ratio, "
        "spectral_flux_mean, spectral_flux_std, spectral_flux_peak_rate "
        "FROM sample_cache WHERE path = ?;",
        -1, &db->selectStmt, nullptr);
    sqlite3_prepare_v2(rawDb,
        "UPDATE sample_cache SET umap_x = ?, umap_y = ? WHERE path = ?;",
        -1, &db->updateUmapStmt, nullptr);
    sqlite3_prepare_v2(rawDb,
        "INSERT INTO sample_cache (path, mtime, size, bpm, key, instrument_type, embedding, content_hash, "
        "category, subcategory, secondary_tags, tag_confidence, tag_source, tag_user_overridden, "
        "taxonomy_version, duration_seconds, embedding_status, embedding_failure_count, "
        "feature_version, peak_amplitude, rms_amplitude, crest_factor, zero_crossing_rate, onset_count, "
        "spectral_centroid, spectral_rolloff, original_sample_rate, original_channels, original_bit_depth, "
        "embedding_model_version, winning_evidence, classification_model_version, decay_time_seconds, physical_class, physical_material, "
        "low_band_energy_ratio, mid_band_energy_ratio, high_band_energy_ratio, spectral_flux_mean, spectral_flux_std, spectral_flux_peak_rate) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
        " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, size=excluded.size, bpm=excluded.bpm, "
        "key=excluded.key, instrument_type=excluded.instrument_type, embedding=excluded.embedding, "
        "content_hash=excluded.content_hash, category=excluded.category, subcategory=excluded.subcategory, "
        "secondary_tags=excluded.secondary_tags, tag_confidence=excluded.tag_confidence, "
        "tag_source=excluded.tag_source, tag_user_overridden=excluded.tag_user_overridden, "
        "taxonomy_version=excluded.taxonomy_version, duration_seconds=excluded.duration_seconds, "
        "embedding_status=excluded.embedding_status, embedding_failure_count=excluded.embedding_failure_count, "
        "feature_version=excluded.feature_version, peak_amplitude=excluded.peak_amplitude, "
        "rms_amplitude=excluded.rms_amplitude, crest_factor=excluded.crest_factor, "
        "zero_crossing_rate=excluded.zero_crossing_rate, onset_count=excluded.onset_count, "
        "spectral_centroid=excluded.spectral_centroid, spectral_rolloff=excluded.spectral_rolloff, "
        "original_sample_rate=excluded.original_sample_rate, original_channels=excluded.original_channels, "
        "original_bit_depth=excluded.original_bit_depth, "
        "embedding_model_version=excluded.embedding_model_version, "
        "winning_evidence=excluded.winning_evidence, "
        "classification_model_version=excluded.classification_model_version, "
        "decay_time_seconds=excluded.decay_time_seconds, "
        "physical_class=excluded.physical_class, physical_material=excluded.physical_material, "
        "low_band_energy_ratio=excluded.low_band_energy_ratio, mid_band_energy_ratio=excluded.mid_band_energy_ratio, "
        "high_band_energy_ratio=excluded.high_band_energy_ratio, spectral_flux_mean=excluded.spectral_flux_mean, "
        "spectral_flux_std=excluded.spectral_flux_std, spectral_flux_peak_rate=excluded.spectral_flux_peak_rate;",
        -1, &db->upsertStmt, nullptr);

    cacheDb = std::move(db);
}

bool SampleManagerEngine::checkCacheIntegrity()
{
    const juce::ScopedLock sl(cacheDbLock);
    if (cacheDb == nullptr || cacheDb->db == nullptr) return false;
    return quickCheckPassed(cacheDb->db);
}

void SampleManagerEngine::clearCache()
{
    const juce::ScopedLock sl(cacheDbLock);

    // RECOVERY PHASE R1 -- clearCache() now clears only the derived
    // per-sample analysis cache (sample_cache + cache_meta), not the whole
    // DB file. user_favorites/preview_history/smart_collections are user
    // data living in the same physical file and must survive a cache clear
    // (restored/verified by TestFavorites and TestHistory -- see
    // docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md). Falls back to the old
    // whole-file reset only if there's no live connection to run SQL
    // against (e.g. mid corrupt-quarantine).
    if (cacheDb != nullptr && cacheDb->db != nullptr) {
        sqlite3_exec(cacheDb->db, "DELETE FROM sample_cache;", nullptr, nullptr, nullptr);
        sqlite3_exec(cacheDb->db, "DELETE FROM cache_meta;", nullptr, nullptr, nullptr);
        return;
    }

    // Destructing CacheDb finalizes the prepared statements and closes the
    // sqlite3 connection cleanly before we touch the files on disk.
    cacheDb.reset();

    juce::File cacheFile = getCacheDbFile();
    cacheFile.deleteFile();
    cacheFile.getSiblingFile(cacheFile.getFileName() + "-wal").deleteFile();
    cacheFile.getSiblingFile(cacheFile.getFileName() + "-shm").deleteFile();

    openCacheDb();
}

bool SampleManagerEngine::tryLoadFromCache(const std::string& filePath, SampleItem& outItem)
{
    if (cacheDb == nullptr || cacheDb->selectStmt == nullptr) return false;

    juce::File file(filePath);
    const bool fileIsAvailable = file.existsAsFile();
    const bool storageIsUnavailable = !fileIsAvailable
        && shouldPreserveMissingFileForUnavailableStorage(file);
    if (!fileIsAvailable && !storageIsUnavailable) return false;

    int64_t mtime = fileIsAvailable ? file.getLastModificationTime().toMilliseconds() : 0;
    int64_t size = fileIsAvailable ? file.getSize() : 0;

    bool hit = false;
    {
        const juce::ScopedLock sl(cacheDbLock);
        sqlite3_stmt* stmt = cacheDb->selectStmt;
        sqlite3_reset(stmt);
        sqlite3_bind_text(stmt, 1, filePath.c_str(), -1, SQLITE_TRANSIENT);

        if (sqlite3_step(stmt) == SQLITE_ROW) {
            int64_t cachedMtime = sqlite3_column_int64(stmt, 0);
            int64_t cachedSize = sqlite3_column_int64(stmt, 1);

            // When an external volume is absent we cannot stat the file, but
            // the persisted row remains the authoritative catalogue record.
            // Revalidate mtime/size normally as soon as the drive is mounted.
            if (storageIsUnavailable || (cachedMtime == mtime && cachedSize == size)) {
                // NULL (pre-migration row) is treated as legacy-Valid, gated on
                // the blob check below for backward compatibility.
                bool statusIsNull = sqlite3_column_type(stmt, 17) == SQLITE_NULL;
                int statusInt = statusIsNull ? -1 : sqlite3_column_int(stmt, 17);
                auto cachedStatus = static_cast<EmbeddingStatus>(statusInt);

                const void* blob = sqlite3_column_blob(stmt, 5);
                int blobBytes = sqlite3_column_bytes(stmt, 5);
                bool hasValidBlob = (blob != nullptr
                    && blobBytes == static_cast<int>(AcousticClassifier::pannsDim * sizeof(float))
                    && AcousticClassifier::isValidEmbedding(static_cast<const float*>(blob)));

                // A retryable failure is deliberately NOT a cache hit -- the
                // file goes through the normal decode+inference path again
                // this scan, giving it another chance rather than being
                // silently skipped. A permanent failure (or a real Valid
                // embedding) short-circuits reprocessing either way -- see
                // docs/ONNX_FAILURE_HANDLING.md.
                bool isPermanentFailure = (!statusIsNull && cachedStatus == EmbeddingStatus::FailedPermanent);
                bool isLegacyOrValid = (statusIsNull || cachedStatus == EmbeddingStatus::Valid);
                bool wellFormedValid = isLegacyOrValid && hasValidBlob;

                // RECOVERY PHASE R3-G -- Cache Version Enforcement. NULL
                // (legacy row, before this column existed) reads as current
                // -- see the ALTER TABLE comment in openCacheDb() for why
                // that's deliberate. A stale, non-NULL value means the
                // embedding itself is no longer trustworthy (a different
                // model produced it): nothing selective is worth preserving,
                // so this falls all the way through to the ordinary
                // full-miss path (docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §4).
                bool embeddingModelVersionIsNull = sqlite3_column_type(stmt, 30) == SQLITE_NULL;
                int cachedEmbeddingModelVersion = embeddingModelVersionIsNull ? kEmbeddingModelVersion : sqlite3_column_int(stmt, 30);
                bool embeddingModelVersionCurrent = (cachedEmbeddingModelVersion == kEmbeddingModelVersion);

                // Anything that isn't a permanent failure and isn't a real,
                // well-formed, current-model-version Valid embedding is
                // treated as a cache miss -- covers retryable failures
                // (explicitly, so they get another attempt), a stale
                // embedding model version, and any unexpected/corrupt status
                // value (fails safe: reprocess rather than trust ambiguous
                // cached state).
                if (!isPermanentFailure && !(wellFormedValid && embeddingModelVersionCurrent)) {
                    sqlite3_reset(stmt);
                    return false;
                }

                outItem.filePath = filePath;
                outItem.name = file.getFileNameWithoutExtension().toStdString();
                outItem.bpm = static_cast<float>(sqlite3_column_double(stmt, 2));

                const unsigned char* keyText = sqlite3_column_text(stmt, 3);
                outItem.key = keyText ? reinterpret_cast<const char*>(keyText) : "Unknown";

                const unsigned char* typeText = sqlite3_column_text(stmt, 4);
                outItem.instrumentType = typeText ? reinterpret_cast<const char*>(typeText) : "Unknown";

                outItem.embeddingFailureCount = sqlite3_column_type(stmt, 18) == SQLITE_NULL
                    ? 0 : sqlite3_column_int(stmt, 18);

                if (isPermanentFailure) {
                    outItem.embeddingStatus = EmbeddingStatus::FailedPermanent;
                    outItem.embedding.clear();
                    hit = true;
                } else {
                    // isLegacyOrValid && hasValidBlob, guaranteed by the guard above.
                    outItem.embedding.assign(static_cast<const float*>(blob),
                                             static_cast<const float*>(blob) + AcousticClassifier::pannsDim);
                    outItem.embeddingStatus = EmbeddingStatus::Valid;
                    outItem.embeddingFailureCount = 0;
                    outItem.embeddingModelVersion = kEmbeddingModelVersion; // gated current above

                    const unsigned char* hashText = sqlite3_column_text(stmt, 6);
                    outItem.contentHash = hashText ? reinterpret_cast<const char*>(hashText) : "";

                    const unsigned char* categoryText = sqlite3_column_text(stmt, 7);
                    outItem.category = categoryText ? canonicalizeTaxonomyString(reinterpret_cast<const char*>(categoryText)) : "";

                    const unsigned char* subcategoryText = sqlite3_column_text(stmt, 8);
                    outItem.subcategory = subcategoryText ? canonicalizeTaxonomyString(reinterpret_cast<const char*>(subcategoryText)) : "";

                    const unsigned char* secondaryTagsText = sqlite3_column_text(stmt, 9);
                    outItem.secondaryTags.clear();
                    if (secondaryTagsText != nullptr) {
                        juce::StringArray parts = juce::StringArray::fromTokens(
                            reinterpret_cast<const char*>(secondaryTagsText), "|", "");
                        for (const auto& part : parts)
                            if (part.isNotEmpty())
                                outItem.secondaryTags.push_back(canonicalizeTaxonomyString(part.toStdString()));
                    }

                    outItem.tagConfidence = static_cast<float>(sqlite3_column_double(stmt, 10));

                    const unsigned char* tagSourceText = sqlite3_column_text(stmt, 11);
                    outItem.tagSource = tagSourceText ? reinterpret_cast<const char*>(tagSourceText) : "unclassified";

                    outItem.tagUserOverridden = sqlite3_column_int(stmt, 12) != 0;
                    outItem.taxonomyVersion = sqlite3_column_int(stmt, 13);
                    outItem.durationSeconds = static_cast<float>(sqlite3_column_double(stmt, 14));

                    if (sqlite3_column_type(stmt, 15) != SQLITE_NULL && sqlite3_column_type(stmt, 16) != SQLITE_NULL) {
                        outItem.x = static_cast<float>(sqlite3_column_double(stmt, 15));
                        outItem.y = static_cast<float>(sqlite3_column_double(stmt, 16));
                        outItem.umapPositionFromCache = true;
                    }

                    // RECOVERY PHASE R2 -- Audio Features. A cache row from
                    // before this column existed, or written under an older
                    // feature_version, keeps featureVersion == 0 (its
                    // SampleItem default) rather than being force-reanalysed
                    // here -- full version-mismatch handling is deferred to
                    // R3's Cache Version Enforcement (brief section 36; see
                    // docs/SLO_AUDIO_FEATURE_RECOVERY.md's Cache section,
                    // flagged there as an explicit P1).
                    int cachedFeatureVersion = sqlite3_column_type(stmt, 19) == SQLITE_NULL
                        ? 0 : sqlite3_column_int(stmt, 19);
                    if (cachedFeatureVersion == kFeatureAnalysisVersion) {
                        // RECOVERY PHASE R3-G schema correction (brief section 86 -- see
                        // the ALTER TABLE block in openCacheDb() for the evidence): read
                        // directly from the individual named columns rather than a packed
                        // TEXT blob. NULL-checked defensively even though a current
                        // featureVersion should mean these were all written together.
                        if (sqlite3_column_type(stmt, 20) != SQLITE_NULL) {
                            AudioAnalysisResult parsed;
                            parsed.peakAmplitude = static_cast<float>(sqlite3_column_double(stmt, 20));
                            parsed.rmsAmplitude = static_cast<float>(sqlite3_column_double(stmt, 21));
                            parsed.crestFactor = static_cast<float>(sqlite3_column_double(stmt, 22));
                            parsed.zeroCrossingRate = static_cast<float>(sqlite3_column_double(stmt, 23));
                            parsed.onsetCount = sqlite3_column_int(stmt, 24);
                            parsed.spectralCentroid = static_cast<float>(sqlite3_column_double(stmt, 25));
                            parsed.spectralRolloff = static_cast<float>(sqlite3_column_double(stmt, 26));
                            parsed.originalSampleRate = sqlite3_column_double(stmt, 27);
                            parsed.originalChannels = sqlite3_column_int(stmt, 28);
                            parsed.originalBitDepth = sqlite3_column_int(stmt, 29);
                            // feature_version 4. A legacy row predating the
                            // column reads NULL -> 0.0, which the classifier
                            // input builder treats as "no measurable decay"
                            // and falls back to duration. The version gate
                            // above means such rows are re-analysed anyway.
                            parsed.decayTimeSeconds =
                                static_cast<float>(sqlite3_column_double(stmt, 33));
                            const unsigned char* physicalClassText = sqlite3_column_text(stmt, 34);
                            parsed.physics.physicalClass = physicalClassText
                                ? reinterpret_cast<const char*>(physicalClassText) : "";
                            if (sqlite3_column_type(stmt, 35) != SQLITE_NULL) {
                                const int material = sqlite3_column_int(stmt, 35);
                                if (material >= static_cast<int>(PhysicalAcoustics::PhysicalMaterial::Wood)
                                    && material <= static_cast<int>(PhysicalAcoustics::PhysicalMaterial::Unknown))
                                    parsed.physics.material = static_cast<PhysicalAcoustics::PhysicalMaterial>(material);
                            }
                            parsed.lowBandEnergyRatio = static_cast<float>(sqlite3_column_double(stmt, 36));
                            parsed.midBandEnergyRatio = static_cast<float>(sqlite3_column_double(stmt, 37));
                            parsed.highBandEnergyRatio = static_cast<float>(sqlite3_column_double(stmt, 38));
                            parsed.spectralFluxMean = static_cast<float>(sqlite3_column_double(stmt, 39));
                            parsed.spectralFluxStd = static_cast<float>(sqlite3_column_double(stmt, 40));
                            parsed.spectralFluxPeakRate = static_cast<float>(sqlite3_column_double(stmt, 41));
                            outItem.audioFeatures = parsed;
                            outItem.featureVersion = cachedFeatureVersion;
                        }
                    }

                    const unsigned char* evidenceText = sqlite3_column_text(stmt, 31);
                    outItem.winningEvidence = evidenceText
                        ? reinterpret_cast<const char*>(evidenceText)
                        : "UNKNOWN";
                    // openCacheDb() stamps normal legacy rows. Keep the NULL
                    // fallback defensive for a row created during an older
                    // migration; non-current values trigger cheap head-only
                    // reclassification in prepareFile().
                    outItem.classificationModelVersion = sqlite3_column_type(stmt, 32) == SQLITE_NULL
                        ? AcousticWeights::modelVersion
                        : sqlite3_column_int(stmt, 32);

                    // Apply any persisted user tag override on top of the cached
                    // row so manual corrections survive cache regeneration
                    // (e.g. after a quarantine-and-rebuild).
                    applyUserTagOverride(cacheDb->db, outItem);
                    // Older cache rows commonly contain the historical
                    // 120-BPM fallback even for one-shots.  Normalize the
                    // in-memory value immediately; a subsequent scan will
                    // persist the corrected row without touching source audio.
                    normalizeTempoForTaxonomy(outItem);
                    hit = true;
                }
            }
        }
        sqlite3_reset(stmt);
    }

    return hit;
}

void SampleManagerEngine::hydratePersistedSamples()
{
    const auto finish = [this] {
        hydrationComplete.store(true, std::memory_order_release);
        notifyUpdateNow();
    };

    std::vector<std::string> paths;
    {
        const juce::ScopedLock sl(cacheDbLock);
        if (cacheDb == nullptr || cacheDb->db == nullptr) {
            finish();
            return;
        }

        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(cacheDb->db, "SELECT path FROM sample_cache ORDER BY path;", -1, &stmt, nullptr) != SQLITE_OK) {
            finish();
            return;
        }

        while (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* path = sqlite3_column_text(stmt, 0);
            if (path != nullptr)
                paths.emplace_back(reinterpret_cast<const char*>(path));
        }
        sqlite3_finalize(stmt);
    }

    std::vector<SampleItem> hydrated;
    hydrated.reserve(paths.size());
    for (const auto& path : paths) {
        SampleItem item;
        if (tryLoadFromCache(path, item)) {
            if (item.taxonomyVersion < AbletonTaxonomy::kTaxonomyVersion && !item.tagUserOverridden) {
                // Hydration is read-only and must not promote stale semantic
                // labels. Leave the row stale in SQLite so an explicit scan
                // can run the normal selective-reclassification path; expose
                // it as unknown in memory until that happens. This also keeps
                // reset-to-Auto rows (taxonomyVersion == 0) unknown after a
                // restart instead of silently re-tagging them.
                item.category.clear();
                item.subcategory.clear();
                item.secondaryTags.clear();
                item.tagConfidence = 0.0f;
                item.tagSource = "unclassified";
                item.winningEvidence = "UNKNOWN";
            }

            item.isProcessed = true;
            hydrated.push_back(std::move(item));
        }
    }

    if (!hydrated.empty()) {
        const juce::ScopedLock sl(dbLock);
        // Startup runs before scans normally add entries. Guard nevertheless
        // makes the operation idempotent if a host creates an editor late.
        if (samples.empty()) {
            samples = std::move(hydrated);
            rebuildPathIndex();
            // Hydration replaces the runtime model rather than flowing
            // through the scan FIFO. Editors poll samplesVersion to know when
            // a full resync is required, so publish this bulk replacement or
            // a freshly opened process can retain its initial empty canvas.
            samplesVersion.fetch_add(1, std::memory_order_relaxed);
            // HNSW is intentionally runtime-only. Reconstruct it directly
            // from the valid persisted embeddings so cold-start Find Similar
            // has the same retrieval state as a completed scan, without raw
            // audio I/O or ONNX inference.
            rebuildHnswIndexFull();
        }
    }

    finish();
}

void SampleManagerEngine::upsertCacheEntries(const std::vector<PendingInference>& batch, const std::vector<size_t>& indices)
{
    if (cacheDb == nullptr || cacheDb->upsertStmt == nullptr || indices.empty()) return;

    const juce::ScopedLock sl(cacheDbLock);
    sqlite3_stmt* stmt = cacheDb->upsertStmt;

    sqlite3_exec(cacheDb->db, "BEGIN TRANSACTION;", nullptr, nullptr, nullptr);
    int writeFailures = 0;

    for (size_t idx : indices) {
        const auto& item = batch[idx].item;

        // A retryable failure is deliberately NOT written to the cache at
        // all -- leaving no row (or leaving whatever row already existed)
        // means the next scan's tryLoadFromCache() naturally misses and
        // retries it, with no separate "clear the failure" step needed. Only
        // Valid and FailedPermanent are persisted -- see
        // docs/ONNX_FAILURE_HANDLING.md.
        if (item.embeddingStatus == EmbeddingStatus::FailedRetryable) continue;
        bool isValid = (item.embeddingStatus == EmbeddingStatus::Valid);
        if (isValid && !hasSafeEmbeddingBuffer(item.embedding)) continue; // defensive, shouldn't happen

        juce::File file(item.filePath);
        int64_t mtime = file.getLastModificationTime().toMilliseconds();
        int64_t size = file.getSize();

        sqlite3_reset(stmt);
        sqlite3_bind_text(stmt, 1, item.filePath.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int64(stmt, 2, mtime);
        sqlite3_bind_int64(stmt, 3, size);
        sqlite3_bind_double(stmt, 4, static_cast<double>(item.bpm));
        sqlite3_bind_text(stmt, 5, item.key.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 6, item.instrumentType.c_str(), -1, SQLITE_TRANSIENT);
        if (isValid) {
            sqlite3_bind_blob(stmt, 7, item.embedding.data(), static_cast<int>(item.embedding.size() * sizeof(float)), SQLITE_TRANSIENT);
        } else {
            // FailedPermanent: never store a placeholder/fake vector -- NULL
            // is the honest representation of "no real embedding exists".
            sqlite3_bind_null(stmt, 7);
        }
        sqlite3_bind_text(stmt, 8, item.contentHash.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 9, item.category.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 10, item.subcategory.c_str(), -1, SQLITE_TRANSIENT);

        std::string joinedSecondaryTags;
        for (size_t i = 0; i < item.secondaryTags.size(); ++i) {
            if (i > 0) joinedSecondaryTags += "|";
            joinedSecondaryTags += item.secondaryTags[i];
        }
        sqlite3_bind_text(stmt, 11, joinedSecondaryTags.c_str(), -1, SQLITE_TRANSIENT);

        sqlite3_bind_double(stmt, 12, static_cast<double>(item.tagConfidence));
        sqlite3_bind_text(stmt, 13, item.tagSource.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int(stmt, 14, item.tagUserOverridden ? 1 : 0);
        sqlite3_bind_int(stmt, 15, item.taxonomyVersion);
        sqlite3_bind_double(stmt, 16, static_cast<double>(item.durationSeconds));
        sqlite3_bind_int(stmt, 17, static_cast<int>(item.embeddingStatus));
        sqlite3_bind_int(stmt, 18, item.embeddingFailureCount);

        // RECOVERY PHASE R2 -- Audio Features, schema CORRECTED during R3-G
        // (brief section 86; see the ALTER TABLE block in openCacheDb() for
        // the evidence): individual named columns, not a packed TEXT blob.
        // featureVersion == 0 means extraction didn't run (or hasn't yet)
        // for this item; persist NULL rather than a misleading
        // empty-but-versioned row.
        if (item.featureVersion > 0) {
            const auto& f = item.audioFeatures;
            sqlite3_bind_int(stmt, 19, item.featureVersion);
            sqlite3_bind_double(stmt, 20, static_cast<double>(f.peakAmplitude));
            sqlite3_bind_double(stmt, 21, static_cast<double>(f.rmsAmplitude));
            sqlite3_bind_double(stmt, 22, static_cast<double>(f.crestFactor));
            sqlite3_bind_double(stmt, 23, static_cast<double>(f.zeroCrossingRate));
            sqlite3_bind_int(stmt, 24, f.onsetCount);
            sqlite3_bind_double(stmt, 25, static_cast<double>(f.spectralCentroid));
            sqlite3_bind_double(stmt, 26, static_cast<double>(f.spectralRolloff));
            sqlite3_bind_double(stmt, 27, f.originalSampleRate);
            sqlite3_bind_int(stmt, 28, f.originalChannels);
            sqlite3_bind_int(stmt, 29, f.originalBitDepth);
        } else {
            sqlite3_bind_null(stmt, 19);
            for (int col = 20; col <= 29; ++col) sqlite3_bind_null(stmt, col);
        }

        // RECOVERY PHASE R3-G -- only meaningful alongside a real embedding;
        // NULL for a FailedPermanent row (no embedding exists to version).
        if (isValid) {
            sqlite3_bind_int(stmt, 30, item.embeddingModelVersion > 0 ? item.embeddingModelVersion : kEmbeddingModelVersion);
        } else {
            sqlite3_bind_null(stmt, 30);
        }

        sqlite3_bind_text(stmt, 31, item.winningEvidence.c_str(), -1, SQLITE_TRANSIENT);
        if (isValid && item.classificationModelVersion > 0) {
            sqlite3_bind_int(stmt, 32, item.classificationModelVersion);
        } else {
            sqlite3_bind_null(stmt, 32);
        }

        // feature_version 4: persist decay so DSP dim 5 survives a cache
        // round-trip. Without this a hydrated row silently classifies with
        // the duration fallback instead of the measured decay.
        sqlite3_bind_double(stmt, 33, static_cast<double>(item.audioFeatures.decayTimeSeconds));
        if (item.featureVersion > 0 && !item.audioFeatures.physics.physicalClass.empty())
            sqlite3_bind_text(stmt, 34, item.audioFeatures.physics.physicalClass.c_str(), -1, SQLITE_TRANSIENT);
        else
            sqlite3_bind_null(stmt, 34);
        if (item.featureVersion > 0)
            sqlite3_bind_int(stmt, 35, static_cast<int>(item.audioFeatures.physics.material));
        else
            sqlite3_bind_null(stmt, 35);

        if (item.featureVersion > 0) {
            const auto& f = item.audioFeatures;
            sqlite3_bind_double(stmt, 36, static_cast<double>(f.lowBandEnergyRatio));
            sqlite3_bind_double(stmt, 37, static_cast<double>(f.midBandEnergyRatio));
            sqlite3_bind_double(stmt, 38, static_cast<double>(f.highBandEnergyRatio));
            sqlite3_bind_double(stmt, 39, static_cast<double>(f.spectralFluxMean));
            sqlite3_bind_double(stmt, 40, static_cast<double>(f.spectralFluxStd));
            sqlite3_bind_double(stmt, 41, static_cast<double>(f.spectralFluxPeakRate));
        } else {
            for (int col = 36; col <= 41; ++col) sqlite3_bind_null(stmt, col);
        }

        if (logWriteStep(cacheDb->db, stmt, "upsertCacheEntries") != SQLITE_DONE) writeFailures++;
    }

    if (writeFailures > 0) {
        // A partial batch would leave the cache looking complete to the next
        // scan; roll the whole write back instead so nothing silently sticks.
        sqlite3_exec(cacheDb->db, "ROLLBACK;", nullptr, nullptr, nullptr);
        AppLogger::getInstance().logError(
            "SQLite: upsertCacheEntries rolled back " + juce::String(writeFailures)
            + " failed write(s); stale cache rows for this batch are left untouched");
    } else {
        sqlite3_exec(cacheDb->db, "COMMIT;", nullptr, nullptr, nullptr);
    }
}

void SampleManagerEngine::persistUmapPositions(size_t startIdx)
{
    if (cacheDb == nullptr || cacheDb->updateUmapStmt == nullptr) return;
    if (startIdx >= samples.size()) return;

    const juce::ScopedLock sl(cacheDbLock);
    sqlite3_stmt* stmt = cacheDb->updateUmapStmt;

    sqlite3_exec(cacheDb->db, "BEGIN TRANSACTION;", nullptr, nullptr, nullptr);
    int writeFailures = 0;
    for (size_t i = startIdx; i < samples.size(); ++i) {
        const auto& s = samples[i];
        if (!s.isProcessed) continue;

        sqlite3_reset(stmt);
        sqlite3_bind_double(stmt, 1, static_cast<double>(s.x));
        sqlite3_bind_double(stmt, 2, static_cast<double>(s.y));
        sqlite3_bind_text(stmt, 3, s.filePath.c_str(), -1, SQLITE_TRANSIENT);
        if (logWriteStep(cacheDb->db, stmt, "persistUmapPositions") != SQLITE_DONE) writeFailures++;
    }
    if (writeFailures > 0) {
        sqlite3_exec(cacheDb->db, "ROLLBACK;", nullptr, nullptr, nullptr);
        AppLogger::getInstance().logError(
            "SQLite: persistUmapPositions rolled back " + juce::String(writeFailures)
            + " failed write(s)");
    } else {
        sqlite3_exec(cacheDb->db, "COMMIT;", nullptr, nullptr, nullptr);
    }
}

bool SampleManagerEngine::init(const std::string& customModelPath)
{
    try {
        if (!customModelPath.empty()) {
            modelPath = customModelPath;
        } else {
            constexpr const char* kModelFileName = "panns_cnn10_embedding.onnx";
            juce::File currentExe = juce::File::getSpecialLocation(juce::File::currentExecutableFile);
            juce::File moduleFile = getThisModuleFile();

            // VST3/AU/Standalone are all macOS bundles with the same layout
            // (Contents/MacOS/<exe>, Contents/Resources/) -- one relative
            // path covers all three formats. See CMakeLists.txt's POST_BUILD
            // copy step, which puts the model there.
            juce::File bundleResourceModel = currentExe.getParentDirectory().getParentDirectory()
                                                  .getChildFile("Resources").getChildFile(kModelFileName);
            juce::File moduleResourceModel = moduleFile.getParentDirectory().getParentDirectory()
                                                  .getChildFile("Resources").getChildFile(kModelFileName);
            // Plain "next to the executable" for non-bundled deployments
            // (e.g. a future Windows build with no Contents/Resources/ layout).
            juce::File siblingModel = currentExe.getParentDirectory().getChildFile(kModelFileName);

            if (moduleResourceModel.existsAsFile()) {
                modelPath = moduleResourceModel.getFullPathName().toStdString();
            } else if (bundleResourceModel.existsAsFile()) {
                modelPath = bundleResourceModel.getFullPathName().toStdString();
            } else if (siblingModel.existsAsFile()) {
                modelPath = siblingModel.getFullPathName().toStdString();
            } else {
                // No hardcoded dev-machine fallback here (a prior version of
                // this code had one, which meant model loading only ever
                // actually worked on the machine that path happened to
                // exist on). Leaving modelPath empty lets the
                // Ort::Session construction below fail loudly into the
                // catch block instead of silently "succeeding" against a
                // path nothing else on the system has.
                AppLogger::getInstance().logWarning(
                    juce::String("Could not locate ") + kModelFileName + " next to the executable or in "
                    "its bundle's Resources/ folder -- embedding generation will be unavailable, "
                    "everything else still works.");
            }
        }

        // CoreML execution-provider setup below makes direct Objective-C/
        // CoreML framework calls. Those calls create autoreleased Cocoa
        // objects; on a plain juce::Thread (no autorelease pool is created
        // implicitly by JUCE's thread entry point -- confirmed by reading
        // juce_Thread.cpp), those objects are never drained, which can
        // corrupt the heap in a way that crashes later, in unrelated code --
        // exactly the symptom reproduced this session (a SIGSEGV inside
        // ONNX's own static operator-schema hash table, on the initAsync()
        // background thread, during JUCE's VST3 moduleinfo-generation step).
        // This is the first code path in this engine that makes direct
        // ObjC/CoreML calls from a background thread (existing worker
        // threads -- InferenceWorker, MetadataWriteWorker -- only call
        // ONNX Runtime's plain C API after Env/Session already exist, no
        // ObjC involved), so nothing else needed this.
        JUCE_AUTORELEASEPOOL

        // Serializes ONNX Runtime Env/Session construction across every
        // SampleManagerEngine instance in this process. ONNX Runtime
        // registers its operator schemas into process-wide static state
        // (onnx::OpSchema's global registry) the first time an Env/Session
        // is constructed; that registration is not safe to run concurrently
        // from multiple threads. Since initAsync() (see docs/ASYNC_STARTUP.md)
        // runs this on a background thread per engine instance, a host that
        // creates multiple plugin instances at once during project load --
        // or a VST3 introspection tool instantiating the plugin more than
        // once -- can trigger two of these constructions racing against each
        // other. That race is exactly what caused a real SIGSEGV reproduced
        // this session (crash inside libonnx.dylib's OpSchema hash table,
        // on a background "anonymous" thread, during JUCE's VST3
        // moduleinfo-generation step, which instantiates the plugin more
        // than once). This mutex only serializes the one-time Env/Session
        // *construction* -- normal inference afterward is already confined
        // to a single dedicated InferenceWorker thread per instance and is
        // unaffected.
        static std::mutex onnxInitMutex;
        std::lock_guard<std::mutex> onnxInitLock(onnxInitMutex);

        // Initialize ONNX Runtime Env and Session
        env = std::make_unique<Ort::Env>(ORT_LOGGING_LEVEL_WARNING, "SmartSampleManagerEnv");
        Ort::SessionOptions sessionOptions;
        // Inference now runs on a single dedicated batching thread (see
        // InferenceWorker) rather than being called concurrently from every scan
        // worker, so it's worth letting ORT parallelize each batch's CPU-EP work
        // across cores instead of pinning it to one thread.
        sessionOptions.SetIntraOpNumThreads(juce::jmax(1, juce::SystemStats::getNumCpus()));
        sessionOptions.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

        // Try to enable the CoreML execution provider (Apple Silicon GPU/ANE).
        // Falls back to the CPU EP silently if unavailable — e.g. this ORT build
        // wasn't compiled with CoreML support, or we're not running on Apple
        // hardware that supports it.
        try {
            std::unordered_map<std::string, std::string> coreMLOptions;
            // Valid values for this option are "CPUOnly", "CPUAndGPU", and
            // "CPUAndNeuralEngine" (not the "MLComputeUnits..." enum-case names
            // the coreml_provider_factory.h header comment suggests). ANE+CPU is
            // the best perf/power tradeoff for a small embedding conv-net like this.
            coreMLOptions[kCoremlProviderOption_MLComputeUnits] = "CPUAndNeuralEngine";

            // Cache compiled CoreML subgraphs across sessions so subsequent startups
            // avoid re-converting and re-specializing the model from scratch.
            auto coremlCacheDir = juce::File::getSpecialLocation(juce::File::userApplicationDataDirectory)
                                    .getChildFile("Application Support")
                                    .getChildFile("SmartSampleManager")
                                    .getChildFile("coreml_cache");
            coremlCacheDir.createDirectory();
            coreMLOptions[kCoremlProviderOption_ModelCacheDirectory] = coremlCacheDir.getFullPathName().toStdString();

            sessionOptions.AppendExecutionProvider("CoreML", coreMLOptions);
            coreMLEnabled = true;
            AppLogger::getInstance().logInfo("CoreML execution provider enabled with model cache at: " + coremlCacheDir.getFullPathName());
        }
        catch (const std::exception& e) {
            coreMLEnabled = false;
            AppLogger::getInstance().logWarning(juce::String("CoreML execution provider unavailable, falling back to CPU EP: ") + e.what());
        }

        session = std::make_unique<Ort::Session>(*env, modelPath.c_str(), sessionOptions);
        AppLogger::getInstance().logInfo("Successfully loaded ONNX model from: " + juce::String(modelPath));
        // engineState is set here (not only in initAsync()'s wrapper) so
        // direct synchronous callers of init() -- every Test* binary calls
        // it this way -- also get a correct Ready/Degraded state. See
        // docs/ASYNC_STARTUP.md.
        engineState.store(EngineInitState::Ready, std::memory_order_release);
        return true;
    }
    catch (const std::exception& e) {
        AppLogger::getInstance().logError(juce::String("Failed to initialize ONNX Runtime session: ") + e.what());
        engineState.store(EngineInitState::Degraded, std::memory_order_release);
        return false;
    }
}

void SampleManagerEngine::initAsync(const std::string& customModelPath)
{
    engineState.store(EngineInitState::Initializing, std::memory_order_release);

    // A plain, engine-owned std::thread (joined in ~SampleManagerEngine(),
    // not a fire-and-forget juce::Thread::launch()) -- this thread touches
    // `this` (env/session/engineState/modelPath), so the engine must be able
    // to guarantee it has actually finished before any of those members
    // start being destroyed. A prior version of this code used
    // juce::Thread::launch(), which is unmanaged/unjoinable; that caused a
    // real, reproduced use-after-free (SIGSEGV inside ONNX Runtime's static
    // state) when the engine was destroyed while init() was still in
    // flight. See docs/ASYNC_STARTUP.md. init() itself sets the final
    // Ready/Degraded state, so nothing further is needed here.
    initThread = std::thread([this, customModelPath]() {
        init(customModelPath);
    });
}

void SampleManagerEngine::addPathToQueue(const std::string& path)
{
    juce::File file(path);
    if (!file.exists() || file.isSymbolicLink()) return;

    std::vector<std::string> newFiles;
    int skippedHere = 0;

    if (file.isDirectory()) {
        // Enumerate every file (not just audio-pattern matches) so skipped
        // non-audio files can be counted honestly (F-03) instead of silently
        // vanishing. Only admitted paths are stored; skips are a counter.
        // Directory traversal cost is unchanged -- findChildFiles walks the
        // tree either way; the pattern only filtered the result list.
        // Counted into skippedHere and published AFTER the fresh-scan reset
        // below, so this call's own skips are never erased by it.
        juce::Array<juce::File> allFiles;
        file.findChildFiles(allFiles, juce::File::TypesOfFileToFind::findFiles, true, "*");
        newFiles.reserve(static_cast<size_t>(allFiles.size()));
        for (const auto& f : allFiles) {
            if (f.isSymbolicLink()
                || formatManager.findFormatForFileExtension(f.getFileExtension()) == nullptr) {
                ++skippedHere;
                continue;
            }
            newFiles.push_back(f.getFullPathName().toStdString());
        }
    } else if (file.existsAsFile()
               && formatManager.findFormatForFileExtension(file.getFileExtension()) != nullptr) {
        newFiles.push_back(file.getFullPathName().toStdString());
    } else if (file.existsAsFile()) {
        // Single unsupported file (e.g. a dropped .txt): no scan will start,
        // so count the skip immediately -- no fresh-scan reset can follow to
        // report it, and leaving it uncounted keeps the silent-drop behavior.
        // (Drops pre-filtered by the UI use noteSkippedDrops() instead.)
        scanSkippedNonAudio.fetch_add(1, std::memory_order_relaxed);
        return;
    }

    if (newFiles.empty()) return;

    int queuedCount = 0;
    {
        const juce::ScopedLock sl(queueLock);
        for (auto& f : newFiles) {
            if (queuedOrProcessingPaths.insert(f).second) {
                pendingFiles.push(std::move(f));
                ++queuedCount;
            }
        }
    }

    // Publish this call's admission skips even when every file was already
    // queued (queuedCount == 0): the user still dropped/scanned them, and a
    // scan may already be running whose receipt should include them.
    if (skippedHere > 0 && queuedCount == 0 && !busyFlag.load(std::memory_order_relaxed)) {
        // No scan running and none starting: same pure-skip situation as the
        // single-file path above -- count now, the next fresh scan resets.
        scanSkippedNonAudio.fetch_add(skippedHere, std::memory_order_relaxed);
        return;
    }

    if (queuedCount == 0) {
        // A scan is already running (busyFlag true): fold the skips into its
        // receipt, matching scanTotal's overlapping-scan accumulation.
        if (skippedHere > 0)
            scanSkippedNonAudio.fetch_add(skippedHere, std::memory_order_relaxed);
        return;
    }

    const bool wasBusy = busyFlag.exchange(true, std::memory_order_acq_rel);
    if (!wasBusy)
    {
        scanDone.store(0, std::memory_order_relaxed);
        scanFailed.store(0, std::memory_order_relaxed);
        scanTotal.store(queuedCount, std::memory_order_relaxed);
        scanAdded.store(0, std::memory_order_relaxed);
        scanChanged.store(0, std::memory_order_relaxed);
        scanSkippedNonAudio.store(0, std::memory_order_relaxed);
    }
    else
    {
        scanTotal.fetch_add(queuedCount, std::memory_order_relaxed);
    }
    // Publish this call's skips AFTER the reset above, so a fresh scan never
    // erases its own admission skips. (Pure-skip calls returned earlier and
    // are unaffected by any reset.)
    if (skippedHere > 0)
        scanSkippedNonAudio.fetch_add(skippedHere, std::memory_order_relaxed);

    // Fan out worker jobs across the pool to drain the queue in parallel. Each job
    // just loops popping the next pending file until the queue is empty, so we only
    // ever need up to `numThreads` live jobs regardless of how many files were added.
    int numWorkers = juce::jmin(queuedCount, scanPool.getNumThreads());
    for (int i = 0; i < numWorkers; ++i) {
        scanPool.addJob([this]() { drainQueueWorker(); });
    }

    if (!isThreadRunning()) {
        startThread(juce::Thread::Priority::normal);
    }
    // Always notify (not just in an "already running" branch): the pool jobs we
    // just submitted can finish before the freshly-started coordinator thread
    // reaches its first wait(-1) call. juce::Thread's notify/wait is backed by a
    // WaitableEvent, so a notify() sent before wait() is called is still observed
    // (not lost) — without this, a fast scan on a fresh engine would leave the
    // coordinator parked on wait(-1) forever and busyFlag stuck true.
    notify();
}

void SampleManagerEngine::drainQueueWorker()
{
    for (;;) {
        std::string fileToProcess;
        {
            const juce::ScopedLock sl(queueLock);
            if (pendingFiles.empty()) return;
            fileToProcess = std::move(pendingFiles.front());
            pendingFiles.pop();
        }

        // I/O + resample + heuristic classification only — ONNX inference now
        // happens separately, batched, on the InferenceWorker thread.
        bool submitted = false;
        try {
            submitted = prepareFile(fileToProcess);
        } catch (const std::exception& error) {
            AppLogger::getInstance().logError(
                "Unhandled scan failure for " + juce::String(fileToProcess) + ": " + error.what());
        } catch (...) {
            AppLogger::getInstance().logError(
                "Unhandled scan failure for " + juce::String(fileToProcess));
        }
        if (!submitted)
        {
            scanFailed.fetch_add(1, std::memory_order_relaxed);
            scanDone.fetch_add(1, std::memory_order_relaxed);
            releaseQueuedPath(fileToProcess);
        }
    }
}

void SampleManagerEngine::releaseQueuedPath(const std::string& filePath)
{
    const juce::ScopedLock sl(queueLock);
    queuedOrProcessingPaths.erase(filePath);
}

void SampleManagerEngine::maybeNotifyUpdate()
{
    if (!onUpdate) return;

    // Coalesce notifications from many concurrent worker threads: at most one
    // MessageManager::callAsync every 250ms, instead of one per processed file.
    const uint32_t now = juce::Time::getMillisecondCounter();
    uint32_t last = lastNotifyMs.load(std::memory_order_relaxed);
    if (now - last < 250) return;
    if (!lastNotifyMs.compare_exchange_strong(last, now, std::memory_order_relaxed)) return;

    notifyUpdateNow();
}

void SampleManagerEngine::notifyUpdateNow()
{
    if (!onUpdate) return;

    // See the member declaration in SampleManagerEngine.h -- a bare [this]
    // capture here would be unsafe if the engine is destroyed before the
    // message loop processes this callback. The WeakReference detects that
    // and turns the callback into a safe no-op instead.
    juce::WeakReference<SampleManagerEngine> safeThis(this);
    juce::MessageManager::callAsync([safeThis]() {
        if (auto* self = safeThis.get())
            if (self->onUpdate) self->onUpdate();
    });
}

void SampleManagerEngine::run()
{
    // This thread no longer processes files itself (that now happens in parallel
    // on scanPool worker jobs — see addPathToQueue/drainQueueWorker). It only
    // coordinates: wait for the pool to fully drain, debounce briefly to avoid
    // re-running UMAP on every drain race during a fast scan, then re-project.
    while (!threadShouldExit()) {
        wait(-1);
        if (threadShouldExit()) break;

        while (!threadShouldExit()) {
            // A scan is only truly finished once every file has both been read
            // (scanPool drained) AND had its embedding computed and committed to
            // `samples` (pendingInferenceCount back to 0) — otherwise UMAP would
            // run while embeddings are still in flight on the inference thread.
            bool scanPoolIdle = scanPool.getNumJobs() == 0;
            bool inferenceIdle = pendingInferenceCount.load(std::memory_order_relaxed) == 0;

            if (scanPoolIdle && inferenceIdle) {
                // Quiescence check: wait a short cooldown and re-check, in case more
                // work was queued (or another job hasn't been dispatched yet) while
                // we were about to declare the scan finished.
                wait(300);
                if (scanPool.getNumJobs() == 0 && pendingInferenceCount.load(std::memory_order_relaxed) == 0) break;
            } else {
                wait(100);
            }
        }

        if (threadShouldExit()) break;

        // Bootstrap (first-ever projection) still runs a full UMAP; every scan
        // after that just incrementally places the newly-added samples against
        // the existing projection instead of recomputing everything from scratch.
        // A pending prune forces a full rebuild instead, since hnswIndex labels
        // would otherwise be stale relative to the just-shrunk `samples` vector.
        bool forceFull = forcedUmapRecomputePending.exchange(false, std::memory_order_relaxed);
        triggerUMAP(forceFull);
        busyFlag = false;
    }
}

std::vector<SampleItem> SampleManagerEngine::getSamples()
{
    const juce::ScopedLock sl(dbLock);
    return samples;
}

size_t SampleManagerEngine::findSampleIndex(const std::string& filePath) const
{
    // Caller must hold dbLock (see header). O(1) map lookup replaces the
    // previous O(N) linear scan; kept as a method so every lookup site
    // benefits and the invariant has a single implementation.
    auto it = pathToIndex.find(filePath);
    return it != pathToIndex.end() ? it->second : kSampleIndexNotFound;
}

void SampleManagerEngine::rebuildPathIndex()
{
    // Caller must hold dbLock. O(N) wholesale rebuild, used after index-
    // shifting bulk mutations (prune erase, hydration assignment). Prune and
    // hydration are rare, heavy operations that already pay O(N) work, so
    // this does not change their complexity.
    pathToIndex.clear();
    pathToIndex.reserve(samples.size());
    for (size_t i = 0; i < samples.size(); ++i)
        pathToIndex.emplace(samples[i].filePath, i);
}

size_t SampleManagerEngine::getSampleCount()
{
    const juce::ScopedLock sl(dbLock);
    return samples.size();
}

double SampleManagerEngine::getSampleBpm(const std::string& filePath)
{
    // No-copy lookup: same lock scope and result as the previous
    // `for (const auto& s : getSamples())` loop, but without deep-copying
    // every SampleItem (each 512-float embedding vector) just to read one
    // numeric field on an audition click.
    const juce::ScopedLock sl(dbLock);
    for (const auto& s : samples) {
        if (s.filePath == filePath) return s.bpm;
    }
    return 0.0;
}

std::string SampleManagerEngine::buildDiagnosticsBundle(size_t maxLogLines) const
{
    // One getSamples() snapshot serves the counts below; the receipt atomics,
    // constexpr versions, and ONNX version string need no lock.
    const std::vector<SampleItem> snapshot = [&] {
        const juce::ScopedLock sl(dbLock);
        return samples;
    }();
    const ScanReceipt receipt = getLastScanReceipt();

    auto* root = new juce::DynamicObject();
    juce::var body(root);
    root->setProperty("record_type", "slo_diagnostics_bundle");
    root->setProperty("schema_version", 1);

    auto* app = new juce::DynamicObject();
    app->setProperty("name", "SLO");
    app->setProperty("version", "1.0.0");
    app->setProperty("juce_version", juce::String(juce::SystemStats::getJUCEVersion()));
    root->setProperty("app", juce::var(app));

    auto* models = new juce::DynamicObject();
    models->setProperty("embedding", kEmbeddingModelVersion);
    models->setProperty("classification_head", AcousticWeights::modelVersion);
    models->setProperty("taxonomy", AbletonTaxonomy::kTaxonomyVersion);
    models->setProperty("dsp_features", kFeatureAnalysisVersion);
    models->setProperty("onnxruntime", juce::String(Ort::GetVersionString()));
    root->setProperty("models", juce::var(models));

    auto* ood = new juce::DynamicObject();
    ood->setProperty("global_cosine_threshold",
                     static_cast<double>(AcousticOodCentroids::oodCosineSimilarityThreshold));
    juce::Array<juce::var> perClass;
    for (int c = 0; c < AcousticOodCentroids::numClasses; ++c) {
        auto* entry = new juce::DynamicObject();
        entry->setProperty("class", AcousticOodCentroids::classNames[c]);
        entry->setProperty("threshold",
                           static_cast<double>(AcousticOodCentroids::perClassOodThreshold[c]));
        perClass.add(juce::var(entry));
    }
    ood->setProperty("per_class", perClass);
    root->setProperty("ood_gate", juce::var(ood));

    auto* library = new juce::DynamicObject();
    library->setProperty("samples", static_cast<int>(snapshot.size()));
    library->setProperty("samples_version",
                         static_cast<juce::int64>(samplesVersion.load(std::memory_order_relaxed)));
    auto* receiptObj = new juce::DynamicObject();
    receiptObj->setProperty("added", receipt.added);
    receiptObj->setProperty("changed", receipt.changed);
    receiptObj->setProperty("failed", receipt.failed);
    receiptObj->setProperty("skipped_non_audio", receipt.skippedNonAudio);
    library->setProperty("last_scan_receipt", juce::var(receiptObj));
    root->setProperty("library", juce::var(library));

    auto* tagSources = new juce::DynamicObject();
    auto* evidences = new juce::DynamicObject();
    int userOverridden = 0, staleTaxonomy = 0, staleHead = 0;
    for (const auto& s : snapshot) {
        const std::string sourceKey = s.tagSource.empty() ? "unclassified" : s.tagSource;
        tagSources->setProperty(juce::String(sourceKey),
                                static_cast<int>(tagSources->getProperty(juce::String(sourceKey))) + 1);
        const std::string evidenceKey = s.winningEvidence.empty() ? "UNKNOWN" : s.winningEvidence;
        evidences->setProperty(juce::String(evidenceKey),
                               static_cast<int>(evidences->getProperty(juce::String(evidenceKey))) + 1);
        if (s.tagUserOverridden) ++userOverridden;
        if (s.taxonomyVersion != 0 && s.taxonomyVersion != AbletonTaxonomy::kTaxonomyVersion)
            ++staleTaxonomy;
        if (s.classificationModelVersion != 0
            && s.classificationModelVersion != AcousticWeights::modelVersion)
            ++staleHead;
    }
    auto* splits = new juce::DynamicObject();
    splits->setProperty("tag_source", juce::var(tagSources));
    splits->setProperty("winning_evidence", juce::var(evidences));
    splits->setProperty("user_overridden", userOverridden);
    splits->setProperty("stale_taxonomy", staleTaxonomy);
    splits->setProperty("stale_head", staleHead);
    root->setProperty("evidence_splits", juce::var(splits));

    // Best-effort log tail: the logger owns the file and its write buffering,
    // so a missing/rotated file simply yields an empty tail, never an error.
    // Cap 64KB from the end; logs carry status lines, never credentials.
    auto* logObj = new juce::DynamicObject();
    const juce::File logFile = AppLogger::getInstance().getLogFile();
    logObj->setProperty("path", juce::String(logFile.getFullPathName()));
    juce::Array<juce::var> tailLines;
    if (logFile.existsAsFile()) {
        constexpr juce::int64 kMaxTailBytes = 65536;
        juce::FileInputStream stream(logFile);
        if (stream.openedOk()) {
            const juce::int64 size = stream.getTotalLength();
            stream.setPosition(size > kMaxTailBytes ? size - kMaxTailBytes : 0);
            juce::StringArray lines;
            lines.addLines(stream.readEntireStreamAsString());
            const int keep = static_cast<int>(std::min<size_t>(
                static_cast<size_t>(std::max<int>(0, lines.size())),
                maxLogLines == 0 ? 0 : maxLogLines));
            for (int i = lines.size() - keep; i < lines.size(); ++i)
                tailLines.add(lines[i]);
        }
    }
    logObj->setProperty("lines", tailLines);
    root->setProperty("log_tail", juce::var(logObj));

    return juce::JSON::toString(body, true).toStdString();
}

SampleManagerEngine::AudioOnlyView
SampleManagerEngine::getAudioOnlyView(const std::string& filePath) const
{
    // Snapshot under dbLock, classify after release: classify520() is a pure
    // frozen-head forward pass over static weights, so it must not run while
    // holding the lock that the inference worker's write-back needs.
    // Deliberately a linear scan (not pathToIndex): reorganizeSamples()
    // rewrites filePath in place without updating the index -- see
    // getSampleBpm() above for the same reason.
    struct Snapshot {
        bool found = false;
        std::vector<float> embedding;
        AudioAnalysisResult features{};
        double durationSeconds = 0.0;
        int modelVersion = 0;
    };
    Snapshot snap;
    {
        const juce::ScopedLock sl(dbLock);
        for (const auto& s : samples) {
            if (s.filePath != filePath) continue;
            snap.found = true;
            snap.embedding = s.embedding;
            snap.features = s.audioFeatures;
            snap.durationSeconds = static_cast<double>(s.durationSeconds);
            snap.modelVersion = s.classificationModelVersion;
            break;
        }
    }
    AudioOnlyView view;
    if (!snap.found || !hasSafeEmbeddingBuffer(snap.embedding)) return view;

    const auto classifierInput =
        buildAcousticClassifierInput(snap.embedding, snap.features, snap.durationSeconds);
    const AcousticClassifier::Result acRes =
        AcousticClassifier::classify520(classifierInput.data());

    view.available = true;
    view.staleHead = (snap.modelVersion != AcousticWeights::modelVersion);
    view.confidence = acRes.confidence;
    view.isOod = acRes.isOod;
    if (acRes.isOod) return view;
    std::string mappedCategory, mappedSubcategory;
    if (!AbletonTaxonomy::mapAcousticClassToTaxonomy(
            acRes.subcategory, mappedCategory, mappedSubcategory)) {
        view.unmapped = true;
        view.subcategory = acRes.subcategory;
        return view;
    }
    view.category = mappedCategory;
    view.subcategory = mappedSubcategory;
    return view;
}

int SampleManagerEngine::pruneMissingFiles()
{
    int removedCount = 0;
    int unavailableStorageCount = 0;
    {
        const juce::ScopedLock sl(dbLock);
        auto it = std::remove_if(samples.begin(), samples.end(), [&unavailableStorageCount](const SampleItem& s) {
            const juce::File file(s.filePath);
            if (file.existsAsFile())
                return false;
            if (shouldPreserveMissingFileForUnavailableStorage(file)) {
                ++unavailableStorageCount;
                return false;
            }
            return true;
        });
        removedCount = static_cast<int>(std::distance(it, samples.end()));
        samples.erase(it, samples.end());
        // Erase shifts every later positional index, so the path->index map
        // is stale for all entries after the first removed one. Same staleness
        // reason the HNSW index is force-rebuilt below -- rebuild the map
        // wholesale here (prune is rare and already O(N)).
        rebuildPathIndex();
    }
    lastPruneUnavailableStorageCount.store(unavailableStorageCount, std::memory_order_relaxed);

    if (removedCount > 0) {
        // Removal (not a plain append) -- the FIFO fast path only covers new
        // arrivals, so bump the version to force callers' next poll to do a
        // full getSamples() resync instead of trusting a stale FIFO delta.
        samplesVersion.fetch_add(1, std::memory_order_relaxed);

        // hnswIndex labels are positional indices into `samples` as of the
        // last (re)build. Erasing entries shifts every later index, so the
        // index is now stale -- findSimilarSamples() could resolve a hit to
        // the wrong sample entirely, not just fail to exclude a removed one.
        // Force a full rebuild on the coordinator thread before the next
        // similarity query is trusted.
        if (umapBootstrapped) {
            forcedUmapRecomputePending.store(true, std::memory_order_relaxed);
            busyFlag = true;
            if (!isThreadRunning()) {
                startThread(juce::Thread::Priority::normal);
            }
            notify();
        }

        notifyUpdateNow();

        AppLogger::getInstance().logInfo("Pruned " + juce::String(removedCount)
            + " sample(s) whose files no longer exist on disk.");
    }

    if (unavailableStorageCount > 0) {
        AppLogger::getInstance().logInfo("Preserved " + juce::String(unavailableStorageCount)
            + " sample(s) because their external storage is unavailable.");
    }

    return removedCount;
}

std::vector<DuplicateGroup> SampleManagerEngine::findDuplicateGroups()
{
    std::unordered_map<std::string, std::vector<SampleItem>> byHash;
    {
        const juce::ScopedLock sl(dbLock);
        for (const auto& s : samples) {
            if (!s.isProcessed || s.contentHash.empty()) continue;
            byHash[s.contentHash].push_back(s);
        }
    }

    std::vector<DuplicateGroup> groups;
    for (auto& [hash, items] : byHash) {
        if (items.size() < 2) continue;
        groups.push_back(DuplicateGroup{ hash, std::move(items) });
    }

    // Largest groups first -- the biggest wins for a user cleaning up a library.
    std::sort(groups.begin(), groups.end(), [](const DuplicateGroup& a, const DuplicateGroup& b) {
        return a.items.size() > b.items.size();
    });

    return groups;
}

// --- Favorites (RECOVERY PHASE R1 restoration) --------------------------

void SampleManagerEngine::setFavorite(const std::string& filePath, bool isFav)
{
    const juce::ScopedLock sl(cacheDbLock);
    if (cacheDb == nullptr || cacheDb->db == nullptr) return;

    if (isFav) {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(cacheDb->db,
                "INSERT INTO user_favorites (path, added_at) VALUES (?, ?) "
                "ON CONFLICT(path) DO NOTHING;",
                -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_text(stmt, 1, filePath.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_int64(stmt, 2, juce::Time::getCurrentTime().toMilliseconds());
            logWriteStep(cacheDb->db, stmt, "setFavorite add");
            sqlite3_finalize(stmt);
        }
    } else {
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(cacheDb->db, "DELETE FROM user_favorites WHERE path = ?;",
                -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_text(stmt, 1, filePath.c_str(), -1, SQLITE_TRANSIENT);
            logWriteStep(cacheDb->db, stmt, "setFavorite remove");
            sqlite3_finalize(stmt);
        }
    }
}

bool SampleManagerEngine::isFavorite(const std::string& filePath)
{
    const juce::ScopedLock sl(cacheDbLock);
    if (cacheDb == nullptr || cacheDb->db == nullptr) return false;

    bool result = false;
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(cacheDb->db, "SELECT 1 FROM user_favorites WHERE path = ?;",
            -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, filePath.c_str(), -1, SQLITE_TRANSIENT);
        result = (sqlite3_step(stmt) == SQLITE_ROW);
        sqlite3_finalize(stmt);
    }
    return result;
}

std::vector<std::string> SampleManagerEngine::getFavorites()
{
    const juce::ScopedLock sl(cacheDbLock);
    std::vector<std::string> result;
    if (cacheDb == nullptr || cacheDb->db == nullptr) return result;

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(cacheDb->db, "SELECT path FROM user_favorites ORDER BY added_at ASC;",
            -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* text = sqlite3_column_text(stmt, 0);
            if (text) result.push_back(reinterpret_cast<const char*>(text));
        }
        sqlite3_finalize(stmt);
    }
    return result;
}

// --- Preview History (RECOVERY PHASE R1 restoration) ---------------------

// Bounded growth -- restored/verified by TestHistory: after each write, trim
// to the 200 most recent rows so the table can't grow unbounded over a long
// session. Kept small/simple (DELETE by id cutoff) rather than a rolling
// ring-buffer table since history writes aren't hot-path/real-time.
static constexpr int kMaxPreviewHistoryRows = 200;

void SampleManagerEngine::recordPreview(const std::string& filePath)
{
    const juce::ScopedLock sl(cacheDbLock);
    if (cacheDb == nullptr || cacheDb->db == nullptr) return;

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(cacheDb->db,
            "INSERT INTO preview_history (path, previewed_at) VALUES (?, ?);",
            -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, filePath.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int64(stmt, 2, juce::Time::getCurrentTime().toMilliseconds());
        logWriteStep(cacheDb->db, stmt, "recordPreview");
        sqlite3_finalize(stmt);
    }

    std::string trimSql = "DELETE FROM preview_history WHERE id NOT IN "
        "(SELECT id FROM preview_history ORDER BY id DESC LIMIT " + std::to_string(kMaxPreviewHistoryRows) + ");";
    if (sqlite3_exec(cacheDb->db, trimSql.c_str(), nullptr, nullptr, nullptr) != SQLITE_OK) {
        AppLogger::getInstance().logError(
            "SQLite: preview-history trim failed: " + juce::String(sqlite3_errmsg(cacheDb->db)));
    }
}

std::vector<PreviewHistoryEntry> SampleManagerEngine::getRecentPreviews(int limit)
{
    const juce::ScopedLock sl(cacheDbLock);
    std::vector<PreviewHistoryEntry> result;
    if (cacheDb == nullptr || cacheDb->db == nullptr) return result;

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(cacheDb->db,
            "SELECT path, previewed_at FROM preview_history ORDER BY id DESC LIMIT ?;",
            -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_int(stmt, 1, limit);
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            PreviewHistoryEntry entry;
            const unsigned char* text = sqlite3_column_text(stmt, 0);
            entry.filePath = text ? reinterpret_cast<const char*>(text) : std::string();
            entry.previewedAtMs = sqlite3_column_int64(stmt, 1);
            result.push_back(std::move(entry));
        }
        sqlite3_finalize(stmt);
    }
    return result;
}

// --- Smart Collections (RECOVERY PHASE R1 restoration) -------------------

void SampleManagerEngine::createSmartCollection(const std::string& name, const std::string& queryRulesJson)
{
    const juce::ScopedLock sl(cacheDbLock);
    if (cacheDb == nullptr || cacheDb->db == nullptr) return;

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(cacheDb->db,
            "INSERT INTO smart_collections (name, query_rules) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET query_rules = excluded.query_rules;",
            -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, queryRulesJson.c_str(), -1, SQLITE_TRANSIENT);
        logWriteStep(cacheDb->db, stmt, "createSmartCollection");
        sqlite3_finalize(stmt);
    }
}

void SampleManagerEngine::deleteSmartCollection(const std::string& name)
{
    const juce::ScopedLock sl(cacheDbLock);
    if (cacheDb == nullptr || cacheDb->db == nullptr) return;

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(cacheDb->db, "DELETE FROM smart_collections WHERE name = ?;",
            -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_TRANSIENT);
        logWriteStep(cacheDb->db, stmt, "deleteSmartCollection");
        sqlite3_finalize(stmt);
    }
}

std::vector<std::string> SampleManagerEngine::getSmartCollectionNames()
{
    const juce::ScopedLock sl(cacheDbLock);
    std::vector<std::string> result;
    if (cacheDb == nullptr || cacheDb->db == nullptr) return result;

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(cacheDb->db, "SELECT name FROM smart_collections ORDER BY name ASC;",
            -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* text = sqlite3_column_text(stmt, 0);
            if (text) result.push_back(reinterpret_cast<const char*>(text));
        }
        sqlite3_finalize(stmt);
    }
    return result;
}

// Flat AND-only rule schema -- see SmartCollectionsPanel.h/.cpp, which
// documents this exact contract (verified against this function before that
// panel was built): {"favorite":bool, "bpm_min":n, "bpm_max":n, "key":"...",
// "category":"...", "physical_class":"...", "material":"...",
// "centroid_min":n, "centroid_max":n}. Unknown measurements never satisfy
// a numeric filter.
std::vector<SampleItem> SampleManagerEngine::getSmartCollectionSamples(const std::string& name)
{
    std::string rulesJson;
    {
        const juce::ScopedLock sl(cacheDbLock);
        if (cacheDb == nullptr || cacheDb->db == nullptr) return {};

        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(cacheDb->db, "SELECT query_rules FROM smart_collections WHERE name = ?;",
                -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_TRANSIENT);
            if (sqlite3_step(stmt) == SQLITE_ROW) {
                const unsigned char* text = sqlite3_column_text(stmt, 0);
                if (text) rulesJson = reinterpret_cast<const char*>(text);
            }
            sqlite3_finalize(stmt);
        }
    }
    if (rulesJson.empty()) return {};

    juce::var parsed = juce::JSON::parse(juce::String(rulesJson));
    auto* rules = parsed.getDynamicObject();
    if (rules == nullptr) return {};

    bool wantFavoriteOnly = rules->hasProperty("favorite") && (bool)rules->getProperty("favorite");
    bool hasBpmMin = rules->hasProperty("bpm_min");
    float bpmMin = hasBpmMin ? (float)(double)rules->getProperty("bpm_min") : 0.0f;
    bool hasBpmMax = rules->hasProperty("bpm_max");
    float bpmMax = hasBpmMax ? (float)(double)rules->getProperty("bpm_max") : 0.0f;
    bool hasKey = rules->hasProperty("key");
    juce::String wantKey = hasKey ? rules->getProperty("key").toString() : juce::String();
    bool hasCategory = rules->hasProperty("category");
    juce::String wantCategory = hasCategory ? rules->getProperty("category").toString() : juce::String();
    bool hasPhysicalClass = rules->hasProperty("physical_class");
    juce::String wantPhysicalClass = hasPhysicalClass ? rules->getProperty("physical_class").toString() : juce::String();
    bool hasMaterial = rules->hasProperty("material");
    juce::String wantMaterial = hasMaterial ? rules->getProperty("material").toString() : juce::String();
    bool hasCentroidMin = rules->hasProperty("centroid_min");
    float centroidMin = hasCentroidMin ? (float)(double)rules->getProperty("centroid_min") : 0.0f;
    bool hasCentroidMax = rules->hasProperty("centroid_max");
    float centroidMax = hasCentroidMax ? (float)(double)rules->getProperty("centroid_max") : 0.0f;
    bool hasCentroidFilter = rules->hasProperty("centroid_min") || rules->hasProperty("centroid_max");

    std::vector<std::string> favs;
    if (wantFavoriteOnly) favs = getFavorites();

    std::vector<SampleItem> result;

    const juce::ScopedLock sl(dbLock);
    const auto matchesPhysicalClass = [&wantPhysicalClass](const std::string& actual) {
        if (wantPhysicalClass.isEmpty()) return true;
        const juce::String a(actual);
        if (a.equalsIgnoreCase(wantPhysicalClass)) return true;
        if (wantPhysicalClass.equalsIgnoreCase("Crash / Cymbal"))
            return a.equalsIgnoreCase("Crash") || a.equalsIgnoreCase("Cymbal");
        if (wantPhysicalClass.equalsIgnoreCase("Piano / Plucked String"))
            return a.equalsIgnoreCase("Piano") || a.equalsIgnoreCase("Plucked String");
        return false;
    };
    const auto matchesMaterial = [&wantMaterial](PhysicalAcoustics::PhysicalMaterial actual) {
        if (wantMaterial.isEmpty()) return true;
        const auto actualName = juce::String(PhysicalAcoustics::materialToString(actual));
        if (actualName.equalsIgnoreCase(wantMaterial)) return true;
        if (wantMaterial.equalsIgnoreCase("Skin / Mylar")) return actualName.equalsIgnoreCase("Skin") || actualName.equalsIgnoreCase("Mylar");
        if (wantMaterial.equalsIgnoreCase("Glass / Ceramic")) return actualName.equalsIgnoreCase("Glass") || actualName.equalsIgnoreCase("Ceramic");
        return false;
    };
    for (const auto& s : samples) {
        if (!s.isProcessed) continue;
        if (hasBpmMin && s.bpm < bpmMin) continue;
        if (hasBpmMax && s.bpm > bpmMax) continue;
        if (hasKey && !wantKey.isEmpty() && juce::String(s.key) != wantKey) continue;
        if (hasCategory && !wantCategory.isEmpty() && juce::String(s.category) != wantCategory) continue;
        if (hasCentroidFilter) {
            const float centroid = s.audioFeatures.spectralCentroid;
            if (!std::isfinite(centroid) || centroid <= 0.0f) continue;
            if (hasCentroidMin && centroid < centroidMin) continue;
            if (hasCentroidMax && centroid > centroidMax) continue;
        }
        if (hasPhysicalClass && !matchesPhysicalClass(s.audioFeatures.physics.physicalClass)) continue;
        if (hasMaterial && !matchesMaterial(s.audioFeatures.physics.material)) continue;
        if (wantFavoriteOnly && std::find(favs.begin(), favs.end(), s.filePath) == favs.end()) continue;
        result.push_back(s);
    }
    return result;
}

int SampleManagerEngine::drainNewSampleEvents(std::vector<SampleItem>& outItems, int maxItems)
{
    int start1, size1, start2, size2;
    canvasUpdateFifo.prepareToRead(maxItems, start1, size1, start2, size2);

    outItems.reserve(outItems.size() + static_cast<size_t>(size1 + size2));
    for (int i = 0; i < size1; ++i) {
        outItems.push_back(std::move(canvasUpdateSlots[static_cast<size_t>(start1 + i)]));
    }
    for (int i = 0; i < size2; ++i) {
        outItems.push_back(std::move(canvasUpdateSlots[static_cast<size_t>(start2 + i)]));
    }

    canvasUpdateFifo.finishedRead(size1 + size2);
    return size1 + size2;
}

void SampleManagerEngine::setUpdateCallback(std::function<void()> callback)
{
    onUpdate = callback;
    // Hydration may complete before an editor installs its callback. Publish
    // the already-hydrated model in that case instead of leaving the editor
    // permanently displaying its initial empty state.
    if (onUpdate && getSampleCount() > 0)
        notifyUpdateNow();
}

void SampleManagerEngine::updateMetadataAsync(const std::string& filePath, float bpm, const std::string& key, const std::string& instrumentType)
{
    // Update the in-memory database immediately, so the UI reflects the edit
    // right away rather than waiting on the disk write.
    {
        const juce::ScopedLock sl(dbLock);
        for (auto& item : samples) {
            if (item.filePath == filePath) {
                item.bpm = bpm;
                item.key = key;
                item.instrumentType = instrumentType;
                break;
            }
        }
    }

    // This changes an *existing* item's fields in place (no new sample, so the
    // FIFO fast path doesn't cover it) — bump the version so pollers like the
    // editor's timer know a full resync is needed to pick up e.g. a changed
    // category/dot-color.
    samplesVersion.fetch_add(1, std::memory_order_relaxed);

    notifyUpdateNow();

    // Queue the actual disk write on the persistent metadata-write worker
    // instead of spawning a new OS thread per call (juce::Thread::launch()) —
    // multiple edits to the same file before the worker gets to it just replace
    // the pending entry, so bulk retagging can't spawn unbounded threads.
    {
        const juce::ScopedLock sl(metadataWriteLock);
        pendingMetadataWrites[filePath] = PendingMetadataWrite{ bpm, key, instrumentType };
    }
    metadataWriteWorker->notify();
}

void SampleManagerEngine::updateTaxonomyAsync(const std::string& filePath, const std::string& category,
                                               const std::string& subcategory, const std::vector<std::string>& secondaryTags,
                                               const std::string& userNote)
{
    SampleItem snapshot;
    bool found = false;
    {
        const juce::ScopedLock sl(dbLock);
        for (auto& item : samples) {
            if (item.filePath == filePath) {
                // Capture what the MODEL said before the user's edit overwrites
                // it. This is the whole value of the record: a correction that
                // does not say what was corrected teaches nothing. Logging is
                // best-effort and deliberately cannot affect the edit -- a
                // failed write must never change what the user sees.
                slo::CorrectionRecord corr;
                corr.filePath = item.filePath;
                corr.contentHash = item.contentHash;
                corr.originalCategory = item.category;
                corr.originalSubcategory = item.subcategory;
                corr.originalEvidence = item.winningEvidence;
                corr.originalConfidence = item.tagConfidence;
                corr.correctedCategory = category;
                corr.correctedSubcategory = subcategory;
                corr.userNote = userNote;
                corr.taxonomyVersion = item.taxonomyVersion;
                corr.classifierVersion = item.classificationModelVersion;
                (void) slo::appendCorrection(corr);

                item.category = category;
                item.subcategory = subcategory;
                item.secondaryTags = secondaryTags;
                item.tagConfidence = 1.0f; // a direct user edit is ground truth, not a heuristic guess
                item.tagSource = "user";
                item.tagUserOverridden = true;
                item.winningEvidence = "USER_OVERRIDE";
                item.taxonomyVersion = AbletonTaxonomy::kTaxonomyVersion;
                snapshot = item;
                found = true;
                break;
            }
        }
    }
    if (!found) return;

    samplesVersion.fetch_add(1, std::memory_order_relaxed);
    notifyUpdateNow();

    // Persisted synchronously (not queued like the WAV-metadata worker
    // above) since this is a cheap SQLite upsert, not a file I/O operation
    // with retry/coalescing needs -- and a user correction should survive
    // an immediate restart, not wait behind an unrelated pending write.
    // upsertCacheEntries takes cacheDbLock itself below.
    if (cacheDb != nullptr && cacheDb->upsertStmt != nullptr
        && snapshot.embeddingStatus == EmbeddingStatus::Valid
        && hasSafeEmbeddingBuffer(snapshot.embedding)) {
        std::vector<PendingInference> batch(1);
        batch[0].item = snapshot;
        upsertCacheEntries(batch, { 0 });
    }

    // Persist the manual correction to the dedicated user_tag_overrides table
    // so it survives a cache quarantine/rebuild (which regenerates
    // sample_cache). Joined "|"-separated, matching sample_cache's own format.
    {
        const juce::ScopedLock sl(cacheDbLock);
        if (cacheDb != nullptr && cacheDb->db != nullptr) {
            std::string joined;
            for (size_t i = 0; i < snapshot.secondaryTags.size(); ++i) {
                if (i > 0) joined += "|";
                joined += snapshot.secondaryTags[i];
            }
            sqlite3_stmt* stmt = nullptr;
            if (sqlite3_prepare_v2(cacheDb->db,
                    "INSERT OR REPLACE INTO user_tag_overrides "
                    "(path, category, subcategory, secondary_tags, tag_confidence, tag_source) "
                    "VALUES (?, ?, ?, ?, ?, ?);", -1, &stmt, nullptr) == SQLITE_OK) {
                sqlite3_bind_text(stmt, 1, snapshot.filePath.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_text(stmt, 2, snapshot.category.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_text(stmt, 3, snapshot.subcategory.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_text(stmt, 4, joined.c_str(), -1, SQLITE_TRANSIENT);
                sqlite3_bind_double(stmt, 5, static_cast<double>(snapshot.tagConfidence));
                sqlite3_bind_text(stmt, 6, snapshot.tagSource.c_str(), -1, SQLITE_TRANSIENT);
                logWriteStep(cacheDb->db, stmt, "applyUserTagOverride");
                sqlite3_finalize(stmt);
            }
        }
    }
}

void SampleManagerEngine::resetTaxonomyToAuto(const std::string& filePath)
{
    bool found = false;
    {
        const juce::ScopedLock sl(dbLock);
        for (auto& item : samples) {
            if (item.filePath == filePath) {
                item.category.clear();
                item.subcategory.clear();
                item.secondaryTags.clear();
                item.tagConfidence = 0.0f;
                item.tagSource = "unclassified";
                item.tagUserOverridden = false;
                item.winningEvidence = "UNKNOWN";
                item.taxonomyVersion = 0;
                found = true;
                break;
            }
        }
    }
    if (!found) return;

    samplesVersion.fetch_add(1, std::memory_order_relaxed);
    notifyUpdateNow();

    // Clear both persistence layers together. Removing only the dedicated
    // override row left the regenerable sample_cache row marked as a user
    // override, so a restart could resurrect the old tags.
    {
        const juce::ScopedLock sl(cacheDbLock);
        if (cacheDb != nullptr && cacheDb->db != nullptr) {
            sqlite3_exec(cacheDb->db, "BEGIN TRANSACTION;", nullptr, nullptr, nullptr);
            int writeFailures = 0;

            sqlite3_stmt* resetStmt = nullptr;
            if (sqlite3_prepare_v2(cacheDb->db,
                    "UPDATE sample_cache SET category = '', subcategory = '', secondary_tags = '', "
                    "tag_confidence = 0.0, tag_source = 'unclassified', tag_user_overridden = 0, "
                    "taxonomy_version = 0, winning_evidence = 'UNKNOWN' WHERE path = ?;",
                    -1, &resetStmt, nullptr) == SQLITE_OK) {
                sqlite3_bind_text(resetStmt, 1, filePath.c_str(), -1, SQLITE_TRANSIENT);
                if (logWriteStep(cacheDb->db, resetStmt, "resetTaxonomyToAuto sample_cache") != SQLITE_DONE) writeFailures++;
                sqlite3_finalize(resetStmt);
            }

            sqlite3_stmt* stmt = nullptr;
            if (sqlite3_prepare_v2(cacheDb->db, "DELETE FROM user_tag_overrides WHERE path = ?;",
                    -1, &stmt, nullptr) == SQLITE_OK) {
                sqlite3_bind_text(stmt, 1, filePath.c_str(), -1, SQLITE_TRANSIENT);
                if (logWriteStep(cacheDb->db, stmt, "resetTaxonomyToAuto overrides") != SQLITE_DONE) writeFailures++;
                sqlite3_finalize(stmt);
            }

            if (writeFailures > 0) {
                // A half-reset would resurrect the user's tags from whichever
                // layer failed to clear -- roll back so both stay consistent.
                sqlite3_exec(cacheDb->db, "ROLLBACK;", nullptr, nullptr, nullptr);
                AppLogger::getInstance().logError(
                    "SQLite: resetTaxonomyToAuto rolled back " + juce::String(writeFailures)
                    + " failed write(s) -- tags re-classified on next scan");
            } else {
                sqlite3_exec(cacheDb->db, "COMMIT;", nullptr, nullptr, nullptr);
            }
        }
    }
}

AbletonXmpWriter::WriteResult SampleManagerEngine::writeAbletonXmpTags(const std::string& filePath)
{
    SampleItem snapshot;
    bool found = false;
    {
        const juce::ScopedLock sl(dbLock);
        for (const auto& item : samples) {
            if (item.filePath == filePath) {
                snapshot = item;
                found = true;
                break;
            }
        }
    }
    if (!found) {
        AbletonXmpWriter::WriteResult result;
        result.errorMessage = "Sample not found in the library.";
        return result;
    }

    std::vector<std::string> keywords;
    if (!snapshot.category.empty() && !snapshot.subcategory.empty()) {
        keywords.push_back(snapshot.category + "|" + snapshot.subcategory);
    } else if (!snapshot.category.empty()) {
        keywords.push_back(snapshot.category);
    }
    for (const auto& tag : snapshot.secondaryTags) {
        keywords.push_back(tag);
    }

    return AbletonXmpWriter::writeTagsForFile(filePath, keywords);
}

void SampleManagerEngine::MetadataWriteWorker::run()
{
    while (!threadShouldExit()) {
        std::string path;
        PendingMetadataWrite write{};
        bool found = false;

        {
            const juce::ScopedLock sl(engine.metadataWriteLock);
            if (!engine.pendingMetadataWrites.empty()) {
                auto it = engine.pendingMetadataWrites.begin();
                path = it->first;
                write = it->second;
                engine.pendingMetadataWrites.erase(it);
                found = true;
            }
        }

        if (found) {
            engine.writeWavMetadata(path, write.bpm, write.key, write.instrumentType);
        } else {
            wait(-1);
        }
    }
}

void SampleManagerEngine::triggerUMAP(bool forceFullRecompute)
{
    // Timed so benchmark/qualification tooling can report layout cost
    // separately from scan cost -- the coordinator clears busyFlag only after
    // this returns, so any isBusy()-based elapsed measurement would otherwise
    // fold layout into per-file scan time. See getLastLayoutDurationMs().
    const auto layoutStart = std::chrono::steady_clock::now();
    runUMAPInternal(forceFullRecompute);
    const auto layoutEnd = std::chrono::steady_clock::now();
    lastLayoutDurationMs.store(
        std::chrono::duration<double, std::milli>(layoutEnd - layoutStart).count(),
        std::memory_order_relaxed);
    notifyUpdateNow();
}

std::string parseKeyFromFilename(const std::string& filename)
{
    juce::String s(filename);
    juce::StringArray tokens = extractSemanticFilenameTokens(s);
    
    for (int i = tokens.size() - 1; i >= 0; --i) {
        juce::String t = tokens[i].trim().toLowerCase();
        if (t.isEmpty()) continue;
        
        if (t == "c#" || t == "db") return "C# Minor";
        if (t == "d#" || t == "eb") return "D# Minor";
        if (t == "f#" || t == "gb") return "F# Minor";
        if (t == "g#" || t == "ab") return "G# Minor";
        if (t == "a#" || t == "bb") return "A# Minor";
        if (t == "c") return "C Major";
        if (t == "d") return "D Major";
        if (t == "e") return "E Major";
        if (t == "f") return "F Major";
        if (t == "g") return "G Major";
        if (t == "a") return "A Major";
        if (t == "b") return "B Major";
        
        if (t == "cm" || t == "cmin" || t == "c_minor") return "C Minor";
        if (t == "dm" || t == "dmin" || t == "d_minor") return "D Minor";
        if (t == "em" || t == "emin" || t == "e_minor") return "E Minor";
        if (t == "fm" || t == "fmin" || t == "f_minor") return "F Minor";
        if (t == "gm" || t == "gmin" || t == "g_minor") return "G Minor";
        if (t == "am" || t == "amin" || t == "a_minor") return "A Minor";
        if (t == "bm" || t == "bmin" || t == "b_minor") return "B Minor";

        if (t == "c#m" || t == "dbm") return "C# Minor";
        if (t == "d#m" || t == "ebm") return "D# Minor";
        if (t == "f#m" || t == "gbm") return "F# Minor";
        if (t == "g#m" || t == "abm") return "G# Minor";
        if (t == "a#m" || t == "bbm") return "A# Minor";
        
        if (t == "cmaj" || t == "c_major") return "C Major";
        if (t == "dmaj" || t == "d_major") return "D Major";
        if (t == "emaj" || t == "e_major") return "E Major";
        if (t == "fmaj" || t == "f_major") return "F Major";
        if (t == "gmaj" || t == "g_major") return "G Major";
        if (t == "amaj" || t == "a_major") return "A Major";
        if (t == "bmaj" || t == "b_major") return "B Major";
    }
    
    return "";
}

float parseBpmFromFilename(const std::string& filename)
{
    juce::String s(filename);
    juce::StringArray tokens = extractSemanticFilenameTokens(s);
    
    for (int i = 0; i < tokens.size(); ++i) {
        juce::String t = tokens[i].trim().toLowerCase();
        if (t.endsWith("bpm")) {
            float val = t.dropLastCharacters(3).getFloatValue();
            if (val >= 40.0f && val <= 300.0f) {
                return val;
            }
        }
        float val = t.getFloatValue();
        if (val >= 60.0f && val <= 220.0f && t.containsOnly("0123456789.")) {
            if (s.containsIgnoreCase("bpm") || (i + 1 < tokens.size() && tokens[i + 1].equalsIgnoreCase("bpm"))) {
                return val;
            }
        }
    }

    // A common producer-pack convention omits the literal "BPM" marker and
    // writes a loop as e.g. `Loop_110_Fm` or `Loop_01_160_C#`.  Treat only a
    // plausible numeric token that is close to a musical-key token *and* is
    // in an explicitly loop-marked filename as tempo evidence.  This avoids
    // promoting ordinary variation/index numbers (Loop_01, Loop_10) to BPM.
    bool hasLoopToken = false;
    for (const auto& token : tokens) {
        const juce::String t = token.trim().toLowerCase();
        if (t == "loop" || t == "loops" || t == "drumloop" || t == "toploop") {
            hasLoopToken = true;
            break;
        }
    }
    if (hasLoopToken) {
        for (int i = 0; i < tokens.size(); ++i) {
            const juce::String numericToken = tokens[i].trim();
            if (!numericToken.containsOnly("0123456789.")) continue;
            const float candidate = numericToken.getFloatValue();
            if (candidate < 40.0f || candidate > 220.0f) continue;

            bool hasNearbyKey = false;
            for (int j = std::max(0, i - 2); j <= std::min(tokens.size() - 1, i + 2); ++j) {
                if (j == i) continue;
                const juce::String keyToken = tokens[j].upToFirstOccurrenceOf(".", false, false);
                if (!parseKeyFromFilename(keyToken.toStdString()).empty()) {
                    hasNearbyKey = true;
                    break;
                }
            }
            if (hasNearbyKey) return candidate;
        }
    }
    
    return 0.0f;
}

// AudioFeatures struct now declared in SampleManagerEngine.h (see that
// file's comment) so analyzeFileForDiagnostics() can expose it externally.

// Shared envelope-follower decay-time measurement (~15ms time constant --
// see docs/classification/DECAY_TIME_ENVELOPE_FIX_V1_REPORT.md). Extracted
// so analyzeAudioBuffer() (taxonomy-only AudioFeatures) and
// analyzeAudioProperties() (predicted-tags-facing AudioAnalysisResult) both
// call the exact same computation rather than risking two independently-
// maintained decay measurements silently drifting apart.
float computeEnvelopeDecayTimeSeconds(const float* data, int numSamples, double sampleRate)
{
    if (numSamples <= 0 || sampleRate <= 0.0) return 0.0f;

    std::vector<float> envelope(static_cast<size_t>(numSamples));
    const double timeConstantSeconds = 0.015;
    const float alpha = static_cast<float>(1.0 - std::exp(-1.0 / (sampleRate * timeConstantSeconds)));
    float env = 0.0f;
    for (int i = 0; i < numSamples; ++i) {
        env += alpha * (std::abs(data[i]) - env);
        envelope[static_cast<size_t>(i)] = env;
    }

    int envelopePeakIndex = 0;
    float envelopePeakVal = 0.0f;
    for (int i = 0; i < numSamples; ++i) {
        if (envelope[static_cast<size_t>(i)] > envelopePeakVal) {
            envelopePeakVal = envelope[static_cast<size_t>(i)];
            envelopePeakIndex = i;
        }
    }

    int decayIndex = numSamples - 1;
    float threshold = envelopePeakVal * 0.1f;
    for (int i = envelopePeakIndex; i < numSamples; ++i) {
        if (envelope[static_cast<size_t>(i)] < threshold) {
            decayIndex = i;
            break;
        }
    }
    return static_cast<float>(decayIndex - envelopePeakIndex) / static_cast<float>(sampleRate);
}

AudioFeatures analyzeAudioBuffer(const float* data, int numSamples, double sampleRate)
{
    AudioFeatures f;
    if (numSamples <= 0) return f;

    // 1. Zero Crossing Rate (ZCR)
    int crossings = 0;
    float peak = 0.0f;
    for (int i = 1; i < numSamples; ++i)
    {
        if ((data[i - 1] >= 0.0f && data[i] < 0.0f) || (data[i - 1] < 0.0f && data[i] >= 0.0f)) {
            crossings++;
        }
        peak = std::max(peak, std::abs(data[i]));
    }
    f.zcr = static_cast<float>(crossings) / static_cast<float>(numSamples);

    // 2. Temporal Envelope & Decay Time
    int peakIndex = 0;
    float maxVal = 0.0f;
    for (int i = 0; i < numSamples; ++i)
    {
        if (std::abs(data[i]) > maxVal) {
            maxVal = std::abs(data[i]);
            peakIndex = i;
        }
    }
    
    // Find how long it takes to decay to 10% of peak -- via a SMOOTHED
    // amplitude envelope, not raw instantaneous sample magnitude. BUG FIX
    // (see docs/classification/DECAY_TIME_ENVELOPE_FIX_V1_REPORT.md): real
    // audio oscillates, so searching raw |data[i]| for the first sample
    // below 10% of peak finds the very next zero-crossing after the peak --
    // typically a fraction of a millisecond, regardless of the sound's true
    // decay. Verified on real audio: sustained 9-16s pad/atmosphere content
    // measured ~0.05-0.15ms "decay time" under the old method. A one-pole
    // envelope follower (~15ms time constant -- fast enough to track real
    // percussive decay, slow enough to average over several cycles even at
    // low audible frequencies) fixes this without needing a full FFT/STFT.
    // Deliberately computed separately from peakIndex/maxVal above rather
    // than replacing them -- pitchSweep below still uses the raw sample
    // peak, unaffected by this fix. See computeEnvelopeDecayTimeSeconds()
    // above (shared with AudioAnalysisResult::decayTimeSeconds).
    f.decayTimeSeconds = computeEnvelopeDecayTimeSeconds(data, numSamples, sampleRate);

    // Sustained-energy ratio: final third over first third. Distinguishes a
    // loop (energy persists, ~0.87) from a long one-shot with a natural tail
    // such as a crash (~0.00). See AbletonTaxonomy::detectLoopVsOneShot.
    if (numSamples >= 30) {
        const int third = numSamples / 3;
        double head = 0.0, tail = 0.0;
        for (int i = 0; i < third; ++i) {
            const double a = data[i];
            const double b = data[numSamples - 1 - i];
            head += a * a;
            tail += b * b;
        }
        head /= third; tail /= third;
        f.energyDecayRatio = (head > 1.0e-12)
            ? static_cast<float>(std::min(tail / head, 2.0))
            : 1.0f;
    }

    // 3. Basic frequency band analysis (simplified differentiator)
    double lowSum = 0.0;
    double highSum = 0.0;
    for (int i = 1; i < numSamples; ++i)
    {
        float diff = data[i] - data[i - 1];
        float smooth = (data[i] + data[i - 1]) * 0.5f;
        lowSum += std::abs(smooth);
        highSum += std::abs(diff);
    }
    
    double total = lowSum + highSum + 1e-5;
    f.lowEnergyRatio = static_cast<float>(lowSum / total);
    f.highEnergyRatio = static_cast<float>(highSum / total);

    // 4. Pitch Sweep Detector (for Laser SFX)
    int halfSamples = numSamples / 2;
    auto estimatePitch = [&](const float* subData, int len) -> float {
        if (len < 128) return 0.0f;
        int maxLag = std::min(len, static_cast<int>(sampleRate / 80.0)); // min 80Hz
        int minLag = static_cast<int>(sampleRate / 1000.0); // max 1000Hz
        if (minLag >= maxLag) return 0.0f;
        int bestLag = minLag;
        float bestCorr = -1e9f;
        for (int lag = minLag; lag < maxLag; ++lag)
        {
            float corr = 0.0f;
            for (int j = 0; j < len - lag; ++j) {
                corr += subData[j] * subData[j + lag];
            }
            if (corr > bestCorr) {
                bestCorr = corr;
                bestLag = lag;
            }
        }
        return static_cast<float>(sampleRate / bestLag);
    };

    if (numSamples >= 2048) {
        float startPitch = estimatePitch(data + peakIndex, std::min(halfSamples, 2048));
        float endPitch = estimatePitch(data + (numSamples - std::min(halfSamples, 2048)), std::min(halfSamples, 2048));
        f.pitchSweep = startPitch - endPitch; // Descending sweep has positive value
    }

    return f;
}

// Fine-Grained Subcategorization V1, attribute-layer calibration tooling.
// Self-contained JUCE decode (own AudioFormatManager, not
// SampleManagerEngine::loadAndResampleWaveform) deliberately -- that
// function is an instance method whose owning engine's constructor touches
// the cache DB, which this diagnostic-only, no-side-effects path has no
// reason to do. Decodes at the file's OWN sample rate rather than
// resampling to the 32kHz the ONNX embedding model requires -- irrelevant
// here since analyzeAudioBuffer()'s time-based features (decay time) just
// need *a* consistent, correct sample rate, not specifically 32kHz.
AudioFeatures SampleManagerEngine::analyzeFileForDiagnostics(const juce::File& file)
{
    juce::AudioFormatManager fm;
    fm.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader(fm.createReaderFor(file));
    if (reader == nullptr || reader->lengthInSamples <= 0) {
        return AudioFeatures{};
    }

    juce::AudioBuffer<float> buffer(static_cast<int>(reader->numChannels), static_cast<int>(reader->lengthInSamples));
    reader->read(&buffer, 0, static_cast<int>(reader->lengthInSamples), 0, true, true);

    // Mono-mixdown policy matches loadAndResampleWaveform's elsewhere in
    // this file: average channels rather than picking just the left.
    std::vector<float> mono(static_cast<size_t>(buffer.getNumSamples()), 0.0f);
    for (int ch = 0; ch < buffer.getNumChannels(); ++ch) {
        const float* chData = buffer.getReadPointer(ch);
        for (int i = 0; i < buffer.getNumSamples(); ++i) {
            mono[static_cast<size_t>(i)] += chData[i] / static_cast<float>(buffer.getNumChannels());
        }
    }

    return analyzeAudioBuffer(mono.data(), static_cast<int>(mono.size()), reader->sampleRate);
}

// RECOVERY PHASE R2 -- reconstructs the AudioAnalysisResult contract (see
// SampleManagerEngine.h and docs/SLO_AUDIO_FEATURE_RECOVERY.md). Decodes
// directly from filePath (independent of the 32kHz/5s embedding-window
// waveform used elsewhere in prepareFile) so originalSampleRate/Channels/
// BitDepth reflect the true source file, and so RMS/peak/centroid/etc. are
// computed over the file's full native-resolution audio rather than a
// resampled, duration-clipped copy. This is a second decode of the same
// file within prepareFile() -- a known, documented inefficiency (not a
// correctness issue); see the recovery doc's Performance section.
AudioAnalysisResult analyzeAudioProperties(const std::string& filePath)
{
    AudioAnalysisResult out;

    drwav wav;
    if (!drwav_init_file(&wav, filePath.c_str(), nullptr)) {
        // Malformed/unsupported file (brief section 30): return safe,
        // all-zero/default features rather than crash or leak NaN/Inf.
        return out;
    }

    const unsigned int channels = wav.channels;
    const double sampleRate = static_cast<double>(wav.sampleRate);
    const drwav_uint64 totalFrames = wav.totalPCMFrameCount;

    out.originalSampleRate = sampleRate;
    out.originalChannels = static_cast<int>(channels);
    out.originalBitDepth = static_cast<int>(wav.bitsPerSample);

    if (channels == 0 || totalFrames == 0 || sampleRate <= 0.0) {
        drwav_uninit(&wav);
        return out; // e.g. zero-length file -- brief section 22/23
    }

    const int numFrames = static_cast<int>(totalFrames);
    std::vector<float> interleaved(static_cast<size_t>(numFrames) * channels);
    drwav_uint64 framesRead = drwav_read_pcm_frames_f32(&wav, totalFrames, interleaved.data());
    drwav_uninit(&wav);
    if (framesRead == 0) return out;

    // Mono downmix policy: average all channels -- matches
    // loadAndResampleWaveform's existing mono policy elsewhere in this file
    // (brief section 20), so left/right asymmetry can't produce
    // inconsistent results between the two analysis paths.
    std::vector<float> mono(static_cast<size_t>(numFrames), 0.0f);
    if (channels == 1) {
        std::copy(interleaved.begin(), interleaved.begin() + numFrames, mono.begin());
    } else {
        for (int i = 0; i < numFrames; ++i) {
            float sum = 0.0f;
            const float* frame = interleaved.data() + static_cast<size_t>(i) * channels;
            for (unsigned int c = 0; c < channels; ++c) sum += frame[c];
            mono[static_cast<size_t>(i)] = sum / static_cast<float>(channels);
        }
    }

    // --- Peak / RMS / Crest Factor (brief sections 13-15) ---------------
    double sumSquares = 0.0;
    float peak = 0.0f;
    for (int i = 0; i < numFrames; ++i) {
        float v = mono[static_cast<size_t>(i)];
        peak = std::max(peak, std::abs(v));
        sumSquares += static_cast<double>(v) * static_cast<double>(v);
    }
    float rms = static_cast<float>(std::sqrt(sumSquares / static_cast<double>(numFrames)));

    out.peakAmplitude = peak;
    out.rmsAmplitude = rms;
    // Linear ratio (not dB) -- RMS <= peak always holds mathematically, so
    // crestFactor >= 1.0 for any non-silent signal. Near-silence (rms below
    // an epsilon) is defined as unity rather than dividing toward Inf.
    out.crestFactor = (rms > 1.0e-9f) ? (peak / rms) : 1.0f;

    // --- Zero-Crossing Rate (brief section 16) ---------------------------
    // Normalized crossings / (numSamples - 1); sign test uses >= 0 vs < 0
    // (matches the existing analyzeAudioBuffer() convention above) so an
    // exact-zero sample doesn't get double-counted or dropped.
    int crossings = 0;
    for (int i = 1; i < numFrames; ++i) {
        bool prevNonNeg = mono[static_cast<size_t>(i - 1)] >= 0.0f;
        bool curNonNeg = mono[static_cast<size_t>(i)] >= 0.0f;
        if (prevNonNeg != curNonNeg) crossings++;
    }
    out.zeroCrossingRate = (numFrames > 1)
        ? static_cast<float>(crossings) / static_cast<float>(numFrames - 1)
        : 0.0f;

    // --- Decay time (added post-recovery; see AudioAnalysisResult's
    // decayTimeSeconds comment in the header) -------------------------------
    out.decayTimeSeconds = computeEnvelopeDecayTimeSeconds(mono.data(), numFrames, sampleRate);

    // --- Sustained-energy ratio (loop vs one-shot) ------------------------
    // Mean square of the final third over the first third. A one-shot's energy
    // is front-loaded and decays away; a loop's persists. This is what lets a
    // crash (rings >2.5s, ratio ~0.00) be told apart from a genuine loop
    // (~0.87) -- the case the old duration/decay heuristic could not handle.
    if (numFrames >= 30) {
        const int third = numFrames / 3;
        double head = 0.0, tail = 0.0;
        for (int i = 0; i < third; ++i) {
            const double a = mono[static_cast<size_t>(i)];
            const double b = mono[static_cast<size_t>(numFrames - 1 - i)];
            head += a * a;
            tail += b * b;
        }
        head /= third; tail /= third;
        out.energyDecayRatio = (head > 1.0e-12)
            ? static_cast<float>(std::min(tail / head, 2.0))
            : 1.0f;
    }

    // --- Stereo correlation (added post-recovery; see AudioAnalysisResult's
    // stereoCorrelation comment in the header) -- computed from the
    // pre-downmix interleaved buffer above, using channels 0/1 as L/R.
    // Real corpus evidence (see docs/classification/
    // WIDE_MONO_ATTRIBUTE_TAG_V1_REPORT.md) found this a real, separating
    // signal matching known mixing conventions (bass/kick/vocals kept
    // mono/centered; risers/pads/foley often stereo-widened).
    if (channels >= 2) {
        double meanL = 0.0, meanR = 0.0;
        for (int i = 0; i < numFrames; ++i) {
            const float* frame = interleaved.data() + static_cast<size_t>(i) * channels;
            meanL += frame[0];
            meanR += frame[1];
        }
        meanL /= numFrames;
        meanR /= numFrames;

        double num = 0.0, denL = 0.0, denR = 0.0;
        for (int i = 0; i < numFrames; ++i) {
            const float* frame = interleaved.data() + static_cast<size_t>(i) * channels;
            double dl = frame[0] - meanL;
            double dr = frame[1] - meanR;
            num += dl * dr;
            denL += dl * dl;
            denR += dr * dr;
        }
        out.stereoCorrelation = (denL > 1e-12 && denR > 1e-12)
            ? static_cast<float>(num / std::sqrt(denL * denR))
            : 1.0f; // silence/DC in a channel: not a meaningful wide signal, treat as mono-compatible
    }
    // else: genuinely mono source file -- struct default (1.0) is already correct.

    // --- Spectral Centroid / Rolloff / Onset proxy (brief sections 17-19) -
    // 2048-point FFT / Hann window / 512-sample hop -- matches the FFT size
    // already used by computeMelSpectrogram() elsewhere in this file, so no
    // new arbitrary DSP constant is introduced. Frame results are averaged
    // across the whole file (brief section 17's "averaging policy").
    const int fftOrder = 11;
    const int fftSize = 1 << fftOrder;
    const int hopSize = fftSize / 4;
    const int numMagBins = fftSize / 2 + 1;

    if (numFrames >= fftSize) {
        juce::dsp::FFT fft(fftOrder);
        std::vector<float> hann(static_cast<size_t>(fftSize));
        for (int i = 0; i < fftSize; ++i)
            hann[static_cast<size_t>(i)] = static_cast<float>(
                0.5 * (1.0 - std::cos(2.0 * juce::MathConstants<double>::pi * i / (fftSize - 1))));

        std::vector<float> fftData(static_cast<size_t>(fftSize) * 2, 0.0f);
        std::vector<float> magnitude(static_cast<size_t>(numMagBins), 0.0f);
        std::vector<float> prevMagnitude(static_cast<size_t>(numMagBins), 0.0f);
        std::vector<double> spectralFlux;
        std::vector<double> normalisedSpectralFlux;

        double centroidSum = 0.0;
        double rolloffSum = 0.0;
        double lowBandRatioSum = 0.0;
        double midBandRatioSum = 0.0;
        double highBandRatioSum = 0.0;
        int frameCount = 0;
        double previousMagnitudeSum = 0.0;

        for (int offset = 0; offset + fftSize <= numFrames; offset += hopSize) {
            for (int i = 0; i < fftSize; ++i)
                fftData[static_cast<size_t>(i)] = mono[static_cast<size_t>(offset + i)] * hann[static_cast<size_t>(i)];
            std::fill(fftData.begin() + fftSize, fftData.end(), 0.0f);

            fft.performRealOnlyForwardTransform(fftData.data());

            double weightedSum = 0.0;
            double magSum = 0.0;
            double flux = 0.0;
            double lowBandEnergy = 0.0;
            double midBandEnergy = 0.0;
            double highBandEnergy = 0.0;
            for (int k = 0; k < numMagBins; ++k) {
                float real = fftData[static_cast<size_t>(2 * k)];
                float imag = fftData[static_cast<size_t>(2 * k + 1)];
                float mag = std::sqrt(real * real + imag * imag);
                magnitude[static_cast<size_t>(k)] = mag;

                double freqHz = (static_cast<double>(k) * sampleRate) / fftSize;
                weightedSum += freqHz * static_cast<double>(mag);
                magSum += static_cast<double>(mag);

                const double energy = static_cast<double>(mag) * static_cast<double>(mag);
                if (freqHz < 150.0) lowBandEnergy += energy;
                else if (freqHz < 2000.0) midBandEnergy += energy;
                else highBandEnergy += energy;

                if (frameCount > 0) {
                    double d = static_cast<double>(mag) - static_cast<double>(prevMagnitude[static_cast<size_t>(k)]);
                    if (d > 0.0) flux += d; // half-wave rectified spectral flux (standard onset-detection input)
                }
            }

            if (magSum > 1.0e-9) {
                centroidSum += weightedSum / magSum;

                const double totalBandEnergy = lowBandEnergy + midBandEnergy + highBandEnergy;
                if (totalBandEnergy > 1.0e-12) {
                    lowBandRatioSum += lowBandEnergy / totalBandEnergy;
                    midBandRatioSum += midBandEnergy / totalBandEnergy;
                    highBandRatioSum += highBandEnergy / totalBandEnergy;
                }

                // Rolloff: lowest frequency bin below which 85% of this
                // frame's magnitude-spectrum energy lies.
                double target = 0.85 * magSum;
                double running = 0.0;
                int rolloffBin = numMagBins - 1;
                for (int k = 0; k < numMagBins; ++k) {
                    running += static_cast<double>(magnitude[static_cast<size_t>(k)]);
                    if (running >= target) { rolloffBin = k; break; }
                }
                rolloffSum += (static_cast<double>(rolloffBin) * sampleRate) / fftSize;
                frameCount++;
            }

            if (frameCount > 0) {
                spectralFlux.push_back(flux);
            }
            // A normalized flux sample is meaningful only when a preceding
            // non-silent frame exists.  Skipping the first valid frame (and
            // any frame after silence) prevents division by a zero baseline
            // from producing giant, non-finite-looking evidence values.
            if (frameCount > 1 && previousMagnitudeSum > 1.0e-9) {
                // Divide by the preceding frame's magnitude sum to make the
                // sidecar gain-invariant. Keep the historical raw-flux vector
                // above untouched because onsetCount is a compatibility field.
                // Bound pathological ratios from a nearly silent preceding
                // frame. This keeps the evidence numerically stable while
                // retaining the useful range of onset-strength variation.
                normalisedSpectralFlux.push_back(std::min(
                    flux / std::max(previousMagnitudeSum, 1.0e-9), 100.0));
            }
            if (magSum > 1.0e-9) previousMagnitudeSum = magSum;
            prevMagnitude = magnitude;
        }

        if (frameCount > 0) {
            out.spectralCentroid = static_cast<float>(centroidSum / frameCount);
            out.spectralRolloff = static_cast<float>(rolloffSum / frameCount);
            out.lowBandEnergyRatio = static_cast<float>(lowBandRatioSum / frameCount);
            out.midBandEnergyRatio = static_cast<float>(midBandRatioSum / frameCount);
            out.highBandEnergyRatio = static_cast<float>(highBandRatioSum / frameCount);
        }

        if (!normalisedSpectralFlux.empty()) {
            double mean = 0.0;
            for (double value : normalisedSpectralFlux) mean += value;
            mean /= static_cast<double>(normalisedSpectralFlux.size());
            double variance = 0.0;
            for (double value : normalisedSpectralFlux)
                variance += (value - mean) * (value - mean);
            variance /= static_cast<double>(normalisedSpectralFlux.size());
            out.spectralFluxMean = static_cast<float>(mean);
            out.spectralFluxStd = static_cast<float>(std::sqrt(variance));

            const double threshold = mean + std::sqrt(variance);
            int peaks = 0;
            for (size_t i = 1; i + 1 < normalisedSpectralFlux.size(); ++i) {
                if (normalisedSpectralFlux[i] > threshold
                    && normalisedSpectralFlux[i] >= normalisedSpectralFlux[i - 1]
                    && normalisedSpectralFlux[i] >= normalisedSpectralFlux[i + 1])
                    ++peaks;
            }
            const double analysedSeconds = static_cast<double>(numFrames) / sampleRate;
            out.spectralFluxPeakRate = analysedSeconds > 0.0
                ? static_cast<float>(peaks / analysedSeconds) : 0.0f;
        }

        // Onset proxy: count of spectral-flux local maxima above an
        // adaptive threshold (mean + 1 stddev) -- a standard, well
        // established onset-detection heuristic (spectral-flux peak
        // picking). No surviving evidence establishes the exact historical
        // onset semantics (brief section 19), so this is explicitly a
        // REIMPLEMENTATION of a plausible proxy, not a recovered value --
        // see docs/SLO_AUDIO_FEATURE_RECOVERY.md.
        if (spectralFlux.size() >= 3) {
            double mean = 0.0;
            for (double v : spectralFlux) mean += v;
            mean /= static_cast<double>(spectralFlux.size());
            double variance = 0.0;
            for (double v : spectralFlux) variance += (v - mean) * (v - mean);
            variance /= static_cast<double>(spectralFlux.size());
            double stddev = std::sqrt(variance);
            double threshold = mean + stddev;

            int onsets = 0;
            for (size_t i = 1; i + 1 < spectralFlux.size(); ++i) {
                if (spectralFlux[i] > threshold &&
                    spectralFlux[i] >= spectralFlux[i - 1] &&
                    spectralFlux[i] >= spectralFlux[i + 1]) {
                    onsets++;
                }
            }
            out.onsetCount = onsets;
        }
    }
    // else: file shorter than one FFT frame -- spectralCentroid/Rolloff/
    // onsetCount stay at their safe zero defaults (brief section 22, short
    // files). No out-of-bounds access, no uninitialised FFT input.

    // Populate the physical-acoustics analysis on the same native-resolution
    // mono buffer. This is advisory metadata only; it does not alter semantic
    // taxonomy or rename policy. The compact physical class/material fields
    // are persisted with the rest of the versioned audio analysis cache.
    out.physics = PhysicalAcoustics::analyzeFromAudioBuffer(
        mono.data(), numFrames, sampleRate,
        out.zeroCrossingRate, out.crestFactor,
        out.decayTimeSeconds, out.energyDecayRatio);

    // --- Numerical sanity guard (brief section 28) -----------------------
    auto sanitize = [](float v) { return std::isfinite(v) ? v : 0.0f; };
    out.peakAmplitude = sanitize(out.peakAmplitude);
    out.rmsAmplitude = sanitize(out.rmsAmplitude);
    out.spectralCentroid = sanitize(out.spectralCentroid);
    out.spectralRolloff = sanitize(out.spectralRolloff);
    out.zeroCrossingRate = sanitize(out.zeroCrossingRate);
    out.crestFactor = std::isfinite(out.crestFactor) ? std::max(out.crestFactor, 1.0f) : 1.0f;
    out.decayTimeSeconds = sanitize(out.decayTimeSeconds);
    out.energyDecayRatio = std::isfinite(out.energyDecayRatio) ? out.energyDecayRatio : 1.0f;
    out.stereoCorrelation = std::isfinite(out.stereoCorrelation) ? out.stereoCorrelation : 1.0f;
    out.lowBandEnergyRatio = sanitize(out.lowBandEnergyRatio);
    out.midBandEnergyRatio = sanitize(out.midBandEnergyRatio);
    out.highBandEnergyRatio = sanitize(out.highBandEnergyRatio);
    out.spectralFluxMean = sanitize(out.spectralFluxMean);
    out.spectralFluxStd = sanitize(out.spectralFluxStd);
    out.spectralFluxPeakRate = sanitize(out.spectralFluxPeakRate);

    return out;
}

std::string classifyAudioFeatures(const AudioFeatures& f, const std::string& filename)
{
    juce::String name(filename);
    
    // UI clicks/blips: very short duration, high frequency
    if (f.decayTimeSeconds < 0.06f && f.highEnergyRatio > 0.6f) {
        return "UI";
    }
    // Laser: has a clear pitch sweep downwards
    if (f.pitchSweep > 150.0f && f.decayTimeSeconds > 0.1f && f.decayTimeSeconds < 0.8f) {
        return "Laser";
    }
    // Vocal / Speech (DSP Heuristic):
    // Voiced/unvoiced vocal chops & phrases have moderate decay (0.12s to 1.5s),
    // moderate ZCR (0.06 to 0.32), and balanced energy distribution (neither purely low-sub nor purely high-noise).
    if (f.decayTimeSeconds >= 0.12f && f.decayTimeSeconds < 1.5f &&
        f.zcr >= 0.06f && f.zcr <= 0.32f &&
        f.lowEnergyRatio >= 0.20f && f.lowEnergyRatio <= 0.75f &&
        f.highEnergyRatio < 0.65f) {
        // If it also matches any vocal keyword substring in the filename:
        juce::String lowerName = name.toLowerCase();
        if (lowerName.contains("vox") || lowerName.contains("vocal") || lowerName.contains("acap") ||
            lowerName.contains("adlib") || lowerName.contains("phrase") || lowerName.contains("chant") ||
            lowerName.contains("sing") || lowerName.contains("choir")) {
            return "Vocal";
        }
        // Pure DSP vocal chop heuristic: moderate decay and balanced spectral energy
        if (f.decayTimeSeconds >= 0.15f && f.zcr >= 0.08f && f.zcr <= 0.28f &&
            f.lowEnergyRatio > 0.25f && f.lowEnergyRatio < 0.70f) {
            return "Vocal";
        }
    }
    // Kick: Low frequency energy dominates, fast decay, very low zero crossing rate
    if (f.lowEnergyRatio > 0.85f && f.decayTimeSeconds < 0.28f && f.zcr < 0.10f) {
        return "Kick";
    }
    // Hi-Hat / Cymbals: High frequency energy dominates, high zero crossing rate
    if (f.highEnergyRatio > 0.7f && f.zcr > 0.3f && f.decayTimeSeconds < 0.32f) {
        return "Hi-Hat";
    }
    // Snare / Clap: Mid/high frequency mix, moderate decay, high ZCR
    if (f.zcr > 0.18f && f.decayTimeSeconds >= 0.05f && f.decayTimeSeconds < 0.42f) {
        // Exclude balanced vocal-like energy distribution from snare trap
        if (f.decayTimeSeconds >= 0.15f && f.lowEnergyRatio > 0.30f && f.highEnergyRatio < 0.50f) {
            return "Vocal";
        }
        return "Snare";
    }
    // Explosion: Very loud, long noisy decay
    if (f.decayTimeSeconds > 0.55f && f.lowEnergyRatio > 0.55f && f.zcr > 0.12f) {
        return "Explosion";
    }
    // Bass: Sustained low frequency
    if (f.lowEnergyRatio > 0.78f && f.decayTimeSeconds > 0.38f) {
        return "Bass";
    }
    // Synth / Vocal / Loop: Sustained complex signals
    if (f.decayTimeSeconds > 0.5f) {
        return "Loop";
    }
    
    return "Other";
}

// RECOVERY PHASE R3-G -- Cache Version Enforcement selective-recompute path.
// Decodes `filePath` once (needed regardless of which sub-field is stale),
// then conditionally recomputes DSP features (analyzeAudioProperties) and/or
// taxonomy (AbletonTaxonomy::classify, skipped entirely if tagUserOverridden
// -- a user correction is frozen until an explicit "Reset to Auto"), leaving
// `cached`'s already-current embedding untouched. If a stale taxonomy cannot
// be decoded, the taxonomy is cleared and left at version zero so the cache
// cannot serve a false-known label. See
// docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §4 for the evidence this
// implements verbatim.
SampleItem SampleManagerEngine::lightReanalyzeFile(const std::string& filePath, SampleItem cached)
{
    bool featuresCurrent = (cached.featureVersion == kFeatureAnalysisVersion);
    bool metadataChanged = false;

    // The analysis-version bump also covers the format-aware metadata reader.
    // Refresh metadata before deciding whether the derived taxonomy is still
    // current, otherwise a newly supported embedded label would remain hidden
    // behind a valid cache row forever. User overrides remain authoritative and
    // are never replaced by a file-side metadata refresh.
    if (!featuresCurrent && !cached.tagUserOverridden) {
        float metadataBpm = 0.0f;
        std::string metadataKey;
        std::string metadataInstrumentType = "Unknown";

        // Version 3 also repairs values that were admitted by the previous
        // metadata contract. Preserve a legitimate fallback BPM, but never
        // carry a non-finite/out-of-range value forward merely because the
        // newly reread tag was rejected.
        if (!std::isfinite(cached.bpm) || cached.bpm < 0.0f || cached.bpm > 1000.0f) {
            cached.bpm = 0.0f;
            metadataChanged = true;
        }
        if (cached.instrumentType.empty()) {
            cached.instrumentType = "Unknown";
            metadataChanged = true;
        }

        if (readAudioMetadata(filePath, metadataBpm, metadataKey, metadataInstrumentType)) {
            if (metadataBpm > 0.0f && cached.bpm != metadataBpm) {
                cached.bpm = metadataBpm;
                metadataChanged = true;
            }
            if (!metadataKey.empty() && cached.key != metadataKey) {
                cached.key = metadataKey;
                metadataChanged = true;
            }
            if (metadataInstrumentType != "Unknown"
                && !metadataInstrumentType.empty()
                && cached.instrumentType != metadataInstrumentType) {
                cached.instrumentType = metadataInstrumentType;
                cached.winningEvidence = "EMBEDDED_METADATA";
                metadataChanged = true;
            }
        }
    }

    bool taxonomyCurrent = cached.tagUserOverridden
        || (!metadataChanged && cached.taxonomyVersion == AbletonTaxonomy::kTaxonomyVersion);

    if (featuresCurrent && taxonomyCurrent)
        return cached; // shouldn't normally be reached, but nothing to do

    if (!featuresCurrent) {
        cached.audioFeatures = analyzeAudioProperties(filePath);
        cached.featureVersion = kFeatureAnalysisVersion;
    }

    if (!taxonomyCurrent) {
        double targetRate = 32000.0;
        int targetSamplesCount = 160000;
        std::vector<float> waveform = loadAndResampleWaveform(filePath, targetRate, targetSamplesCount, nullptr, nullptr);
        if (!waveform.empty()) {
            AudioFeatures dspFeatures = analyzeAudioBuffer(waveform.data(), static_cast<int>(waveform.size()), targetRate);

            juce::String cachedParentFolder = juce::File(filePath).getParentDirectory().getFileName();
            AbletonTaxonomy::ClassificationInput taxInput;
            taxInput.existingInstrumentType = cached.instrumentType;
            taxInput.durationSeconds = cached.durationSeconds;
            taxInput.decayTimeSeconds = dspFeatures.decayTimeSeconds;
            taxInput.energyDecayRatio = dspFeatures.energyDecayRatio;
            taxInput.fileName = juce::File(filePath).getFileName().toStdString();
            taxInput.zcr = dspFeatures.zcr;
            taxInput.lowEnergyRatio = dspFeatures.lowEnergyRatio;
            taxInput.highEnergyRatio = dspFeatures.highEnergyRatio;
            taxInput.winningEvidence = cached.winningEvidence;
            taxInput.filenameEvidence = AbletonTaxonomy::detectFilenameSubcategoryEvidence(
                tokenizeString(juce::String(cached.name)), tokenizeString(cachedParentFolder),
                rawUnderscoreSplitLowercase(juce::String(cached.name)));

            AbletonTaxonomy::Classification tax = AbletonTaxonomy::classify(taxInput);
            cached.category = tax.category;
            cached.subcategory = tax.subcategory;
            cached.secondaryTags = tax.secondaryTags;
            cached.tagConfidence = tax.confidence;
            cached.tagSource = "heuristic";
            cached.winningEvidence = tax.winningEvidence;

            cached.taxonomyVersion = AbletonTaxonomy::kTaxonomyVersion;
            normalizeTempoForTaxonomy(cached);
        } else {
            // A stale row whose source can no longer be decoded must not be
            // promoted to the current taxonomy while retaining an old label.
            // Keep the legacy evidence tier for diagnostics/retry context,
            // but clear the derived taxonomy and leave version at zero so the
            // next scan will retry instead of serving false-known metadata.
            cached.category.clear();
            cached.subcategory.clear();
            cached.secondaryTags.clear();
            cached.tagConfidence = 0.0f;
            cached.tagSource = "unclassified";
            cached.taxonomyVersion = 0;
        }
    }

    return cached;
}

float estimateBpmFromAudio(const float* data, int numSamples, double sampleRate, float trueContentDurationSeconds)
{
    // V4-F QUALIFICATION FIX: the analysis buffer passed in here is always
    // zero-padded/truncated to a fixed 5s window (see prepareFile() below --
    // targetSamplesCount == 160000 @ 32kHz), regardless of how long the
    // source file actually is. Gating on numSamples/sampleRate therefore
    // always measures ~5.0s and NEVER rejects short one-shots, defeating the
    // "minimum 2s of real audio" one-shot safety net entirely -- V4-F
    // benchmarking against a real 1607-file commercial one-shot/loop corpus
    // (SmartSampleManager/docs/SLO_CLASSIFICATION_V4F_QUALIFICATION_REPORT.md)
    // measured 87.5% of true one-shots (Kick, Snare, Clap, Hi-Hat, Percussion,
    // Bass One-Shot, Synth, Vocal Phrase, etc. -- median real duration ~0.5s)
    // acquiring a plausible-looking fake tempo from this padded-silence
    // buffer. Gate on the caller-supplied TRUE original file duration
    // instead so sub-2s one-shots correctly short-circuit to UNKNOWN (0.0f)
    // regardless of window padding.
    if (trueContentDurationSeconds < 2.0f) {
        return 0.0f; // Insufficient real duration (<2s) for reliable loop tempo estimation
    }
    if (numSamples < static_cast<int>(sampleRate * 2.0)) {
        return 0.0f; // Insufficient duration (<2s) for reliable loop tempo estimation
    }

    const int hopSize = 256;
    const int frameSize = 1024;
    const int numFrames = (numSamples - frameSize) / hopSize;
    if (numFrames < 64) return 0.0f;

    const float frameRate = static_cast<float>(sampleRate / hopSize);

    // 1. Compute a multi-band onset detection function (ODF).  A single
    // broadband RMS envelope is easily hijacked by a regular hi-hat/16th-note
    // subdivision, which is exactly the failure mode seen on real hip-hop and
    // bass loops.  Keep the broadband signal, but add a low-frequency band so
    // kick/bass pulses contribute a beat-level cue and an air band so a sparse
    // percussion loop does not disappear when its low end is quiet.
    std::vector<float> lowPassed(static_cast<size_t>(numSamples), 0.0f);
    const float lowPassAlpha = static_cast<float>(
        1.0 - std::exp(-2.0 * M_PI * 180.0 / sampleRate));
    float lowPassState = 0.0f;
    for (int i = 0; i < numSamples; ++i) {
        lowPassState += lowPassAlpha * (data[i] - lowPassState);
        lowPassed[static_cast<size_t>(i)] = lowPassState;
    }

    std::vector<float> fullEnergy(static_cast<size_t>(numFrames), 0.0f);
    std::vector<float> lowEnergy(static_cast<size_t>(numFrames), 0.0f);
    std::vector<float> airEnergy(static_cast<size_t>(numFrames), 0.0f);
    for (int n = 0; n < numFrames; ++n) {
        const int offset = n * hopSize;
        float fullSum = 0.0f;
        float lowSum = 0.0f;
        float airSum = 0.0f;
        for (int i = 0; i < frameSize; ++i) {
            const float s = data[offset + i];
            const float low = lowPassed[static_cast<size_t>(offset + i)];
            const float air = s - low;
            fullSum += s * s;
            lowSum += low * low;
            airSum += air * air;
        }
        fullEnergy[static_cast<size_t>(n)] = std::sqrt(fullSum / static_cast<float>(frameSize));
        lowEnergy[static_cast<size_t>(n)] = std::sqrt(lowSum / static_cast<float>(frameSize));
        airEnergy[static_cast<size_t>(n)] = std::sqrt(airSum / static_cast<float>(frameSize));
    }

    std::vector<float> fullOnsets(static_cast<size_t>(numFrames), 0.0f);
    std::vector<float> lowOnsets(static_cast<size_t>(numFrames), 0.0f);
    std::vector<float> airOnsets(static_cast<size_t>(numFrames), 0.0f);
    float fullOnsetMean = 0.0f;
    float lowOnsetMean = 0.0f;
    float airOnsetMean = 0.0f;
    for (int n = 0; n < numFrames; ++n) {
        const float previousFull = n > 0 ? fullEnergy[static_cast<size_t>(n - 1)] : 0.0f;
        const float previousLow = n > 0 ? lowEnergy[static_cast<size_t>(n - 1)] : 0.0f;
        const float previousAir = n > 0 ? airEnergy[static_cast<size_t>(n - 1)] : 0.0f;
        const float full = std::max(0.0f, fullEnergy[static_cast<size_t>(n)] - previousFull);
        const float low = std::max(0.0f, lowEnergy[static_cast<size_t>(n)] - previousLow);
        const float air = std::max(0.0f, airEnergy[static_cast<size_t>(n)] - previousAir);
        fullOnsets[static_cast<size_t>(n)] = full;
        lowOnsets[static_cast<size_t>(n)] = low;
        airOnsets[static_cast<size_t>(n)] = air;
        fullOnsetMean += full;
        lowOnsetMean += low;
        airOnsetMean += air;
    }
    fullOnsetMean /= static_cast<float>(numFrames);
    lowOnsetMean /= static_cast<float>(numFrames);
    airOnsetMean /= static_cast<float>(numFrames);

    const float fullScale = fullOnsetMean > 1.0e-9f ? 1.0f / fullOnsetMean : 0.0f;
    const float lowScale = lowOnsetMean > 1.0e-9f ? 1.0f / lowOnsetMean : 0.0f;
    const float airScale = airOnsetMean > 1.0e-9f ? 1.0f / airOnsetMean : 0.0f;
    std::vector<float> odf(static_cast<size_t>(numFrames), 0.0f);
    for (int n = 0; n < numFrames; ++n) {
        // Broadband remains dominant; low/air are complementary cues, not
        // independent votes.  Normalising each positive-difference stream
        // keeps quiet bass loops from being numerically drowned by hats.
        odf[static_cast<size_t>(n)] =
            0.55f * fullOnsets[static_cast<size_t>(n)] * fullScale
            + 0.35f * lowOnsets[static_cast<size_t>(n)] * lowScale
            + 0.10f * airOnsets[static_cast<size_t>(n)] * airScale;
    }

    // Estimate a beat-period prior from stable onset spacing.  Raw
    // autocorrelation often has equally strong half/double-time harmonics;
    // without this prior a simple click train at 120 BPM can legitimately
    // return 60 BPM.  Keep the prior conservative: require several isolated,
    // regularly spaced peaks and fold only by powers of two into the admitted
    // musical range.  If the pattern is irregular, the autocorrelation path
    // below remains the sole signal.
    float maxOdf = 0.0f;
    float meanOdf = 0.0f;
    for (float value : odf) {
        maxOdf = std::max(maxOdf, value);
        meanOdf += value;
    }
    meanOdf /= static_cast<float>(odf.size());
    std::vector<int> onsetFrames;
    if (maxOdf > 0.0f) {
        const float onsetThreshold = std::max(maxOdf * 0.25f, meanOdf * 3.0f);
        const int minOnsetSpacing = std::max(1, static_cast<int>(frameRate * 0.05f));
        int lastOnset = -minOnsetSpacing;
        for (int n = 1; n + 1 < numFrames; ++n) {
            if (odf[static_cast<size_t>(n)] < onsetThreshold
                || odf[static_cast<size_t>(n)] < odf[static_cast<size_t>(n - 1)]
                || odf[static_cast<size_t>(n)] < odf[static_cast<size_t>(n + 1)]
                || n - lastOnset < minOnsetSpacing)
                continue;
            onsetFrames.push_back(n);
            lastOnset = n;
        }
    }

    float onsetPriorBpm = 0.0f;
    if (onsetFrames.size() >= 4) {
        std::vector<float> intervals;
        intervals.reserve(onsetFrames.size() - 1);
        for (size_t i = 1; i < onsetFrames.size(); ++i)
            intervals.push_back(static_cast<float>(onsetFrames[i] - onsetFrames[i - 1]));
        std::sort(intervals.begin(), intervals.end());
        const float medianInterval = intervals[intervals.size() / 2];
        if (medianInterval > 0.0f) {
            float intervalBpm = 60.0f * frameRate / medianInterval;
            while (intervalBpm < 55.0f) intervalBpm *= 2.0f;
            while (intervalBpm > 185.0f) intervalBpm *= 0.5f;
            const float medianAbsDeviation = [&]() {
                std::vector<float> deviations;
                deviations.reserve(intervals.size());
                for (float interval : intervals)
                    deviations.push_back(std::abs(interval - medianInterval));
                std::sort(deviations.begin(), deviations.end());
                return deviations[deviations.size() / 2];
            }();
            // Reject unstable onset trains; a low-CV pattern is the useful
            // discriminator between a real pulse and transient texture.
            if (medianAbsDeviation / medianInterval <= 0.20f)
                onsetPriorBpm = intervalBpm;
        }
    }

    // 2. Autocorrelation of ODF across 50 - 200 BPM range
    int minLag = static_cast<int>(frameRate * 60.0f / 200.0f); // 200 BPM
    int maxLag = static_cast<int>(frameRate * 60.0f / 50.0f);  // 50 BPM

    if (maxLag >= numFrames / 2) {
        maxLag = numFrames / 2 - 1;
    }
    if (minLag >= maxLag || minLag <= 0) return 0.0f;

    int bestLag = 0;
    float bestCorr = -1.0f;
    float totalCorr = 0.0f;
    int countCorr = 0;

    for (int lag = minLag; lag <= maxLag; ++lag) {
        float corr = 0.0f;
        for (int i = 0; i < numFrames - lag; ++i) {
            corr += odf[i] * odf[i + lag];
        }
        totalCorr += corr;
        countCorr++;

        if (corr > bestCorr) {
            bestCorr = corr;
            bestLag = lag;
        }
    }

    if (bestLag == 0 || countCorr == 0) return 0.0f;

    float avgCorr = totalCorr / static_cast<float>(countCorr);
    if (avgCorr <= 0.0f) return 0.0f;

    // V4-G BLOCKER-B FIX: the old code took the single largest autocorrelation
    // lag and blindly folded it into [70,170] BPM by repeated doubling/halving,
    // regardless of whether the *true* periodicity actually lived at a
    // neighbouring octave. That assumption is false whenever the strongest ODF
    // peak corresponds to a rhythmic subdivision (e.g. hi-hats/16ths) rather
    // than the beat itself -- V4-F measured ~52 BPM mean absolute error on real
    // loops, including catastrophic non-octave errors (true 60-66 BPM Psy-Bass
    // loops estimated ~101 BPM), which a pure re-fold cannot fix because 101
    // is not an octave multiple of 60-66 at all -- the wrong LAG was chosen,
    // not just the wrong octave of the right lag.
    //
    // Fix: recompute the full lag->correlation curve once (already have it via
    // repeated corr() calls above is wasteful; store it), find ALL locally-
    // salient peaks (not just the global max), fold each candidate's BPM into
    // an extended musical range, and pick whichever *actual measured*
    // candidate has the strongest prominence (peak / local-mean), instead of
    // assuming prominence carries over unchanged across an octave fold.
    std::vector<float> corrCurve(static_cast<size_t>(maxLag) + 1, 0.0f);
    for (int lag = minLag; lag <= maxLag; ++lag) {
        float corr = 0.0f;
        for (int i = 0; i < numFrames - lag; ++i) {
            corr += odf[i] * odf[i + lag];
        }
        corrCurve[static_cast<size_t>(lag)] = corr;
    }

    struct Peak { int lag; float corr; };
    std::vector<Peak> peaks;
    for (int lag = minLag + 1; lag < maxLag; ++lag) {
        float c = corrCurve[static_cast<size_t>(lag)];
        if (c >= corrCurve[static_cast<size_t>(lag - 1)] &&
            c >= corrCurve[static_cast<size_t>(lag + 1)] &&
            c > avgCorr * 1.3f) {
            peaks.push_back({ lag, c });
        }
    }
    // Always keep the global best lag as a candidate even if the strict local-
    // maxima scan above missed it at a range boundary.
    peaks.push_back({ bestLag, bestCorr });

    if (peaks.empty()) return 0.0f;

    // Keep at most the 6 strongest peaks to bound cost -- runtime is already
    // small relative to ONNX embedding inference (see V4-G BPM report).
    std::sort(peaks.begin(), peaks.end(), [](const Peak& a, const Peak& b) { return a.corr > b.corr; });
    if (peaks.size() > 6) peaks.resize(6);

    struct Candidate { float bpm; float prominence; };
    std::vector<Candidate> candidates;
    const float kMinBpm = 55.0f, kMaxBpm = 185.0f; // extended musical range (was a hard [70,170] fold)
    for (const auto& pk : peaks) {
        float bpm = (60.0f * frameRate) / static_cast<float>(pk.lag);
        float prominence = pk.corr / avgCorr;
        for (float mult : { 0.25f, 0.5f, 1.0f, 2.0f, 4.0f }) {
            float b = bpm * mult;
            if (b >= kMinBpm && b <= kMaxBpm) {
                candidates.push_back({ b, prominence });
            }
        }
    }

    // Derive an independent beat prior from the low-frequency onset stream.
    // This is intentionally separate from the broadband prior: hats and
    // shakers can be the most regular events in a loop, while kick/bass events
    // usually carry the producer's intended beat.  Only accept it when the
    // low-band train itself is stable, so a noisy low end cannot override the
    // broader evidence.
    float lowBandPriorBpm = 0.0f;
    {
        float maxLowOnset = 0.0f;
        float meanLowOnset = 0.0f;
        for (float value : lowOnsets) {
            maxLowOnset = std::max(maxLowOnset, value);
            meanLowOnset += value;
        }
        meanLowOnset /= static_cast<float>(lowOnsets.size());
        if (maxLowOnset > 0.0f) {
            const float threshold = std::max(maxLowOnset * 0.25f, meanLowOnset * 3.0f);
            const int minSpacing = std::max(1, static_cast<int>(frameRate * 0.05f));
            int last = -minSpacing;
            std::vector<int> lowFrames;
            for (int n = 1; n + 1 < numFrames; ++n) {
                const float value = lowOnsets[static_cast<size_t>(n)];
                if (value < threshold
                    || value < lowOnsets[static_cast<size_t>(n - 1)]
                    || value < lowOnsets[static_cast<size_t>(n + 1)]
                    || n - last < minSpacing)
                    continue;
                lowFrames.push_back(n);
                last = n;
            }
            if (lowFrames.size() >= 4) {
                std::vector<float> intervals;
                intervals.reserve(lowFrames.size() - 1);
                for (size_t i = 1; i < lowFrames.size(); ++i)
                    intervals.push_back(static_cast<float>(lowFrames[i] - lowFrames[i - 1]));
                std::sort(intervals.begin(), intervals.end());
                const float median = intervals[intervals.size() / 2];
                std::vector<float> deviations;
                deviations.reserve(intervals.size());
                for (float interval : intervals)
                    deviations.push_back(std::abs(interval - median));
                std::sort(deviations.begin(), deviations.end());
                const float medianDeviation = deviations[deviations.size() / 2];
                if (median > 0.0f && medianDeviation / median <= 0.25f) {
                    lowBandPriorBpm = 60.0f * frameRate / median;
                    while (lowBandPriorBpm < 55.0f) lowBandPriorBpm *= 2.0f;
                    while (lowBandPriorBpm > 185.0f) lowBandPriorBpm *= 0.5f;
                }
            }
        }
    }
    if (candidates.empty()) return 0.0f; // no candidate falls in a plausible musical range at all

    const Candidate* winner = &candidates.front();
    for (const auto& c : candidates) {
        float candidateScore = c.prominence;
        float winnerScore = winner->prominence;
        if (onsetPriorBpm > 0.0f) {
            // Log-distance treats half and double time symmetrically.  A
            // stable onset prior is intentionally strong enough to break an
            // otherwise near-tied autocorrelation harmonic, but it cannot
            // rescue a candidate outside the prior's octave neighborhood.
            const float candidateDistance = std::abs(std::log2(c.bpm / onsetPriorBpm));
            const float winnerDistance = std::abs(std::log2(winner->bpm / onsetPriorBpm));
            candidateScore += 2.0f * std::exp(-4.0f * candidateDistance);
            winnerScore += 2.0f * std::exp(-4.0f * winnerDistance);
        }
        if (lowBandPriorBpm > 0.0f) {
            const float candidateDistance = std::abs(std::log2(c.bpm / lowBandPriorBpm));
            const float winnerDistance = std::abs(std::log2(winner->bpm / lowBandPriorBpm));
            // Low-band evidence is a tie-breaker, not a hard override.  The
            // smaller weight keeps melodic/bass loops with a deliberately
            // syncopated low end from being forced onto a false quarter-note.
            candidateScore += 1.5f * std::exp(-4.0f * candidateDistance);
            winnerScore += 1.5f * std::exp(-4.0f * winnerDistance);
        }
        if (candidateScore > winnerScore) winner = &c;
    }

    // Same honesty gate as before (peak-to-mean prominence), now applied to
    // the candidate actually selected rather than only the raw global peak.
    if (winner->prominence < 1.8f) {
        return 0.0f; // Low confidence, unclassifiable rhythm
    }

    return std::round(winner->bpm * 10.0f) / 10.0f;
}

bool SampleManagerEngine::prepareFile(const std::string& filePath)
{
    // Cache check first: if this exact file (by path + mtime + size) was already
    // processed in a previous scan, skip audio decode + mel-spec + ONNX entirely —
    // just feed its cached data through the same commit/UMAP-placement/canvas-FIFO
    // pipeline as a freshly-processed file.
    SampleItem cachedItem;
    if (tryLoadFromCache(filePath, cachedItem)) {
        // RECOVERY PHASE R3-G -- Cache Version Enforcement. tryLoadFromCache()
        // only returning true at all already proved embeddingModelVersion is
        // current (see there) -- but featureVersion and/or taxonomyVersion
        // may still be stale (an algorithm/taxonomy bump since this row was
        // written). Selectively recompute just those, reusing the embedding
        // -- see docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §4.
        bool featuresCurrent = (cachedItem.featureVersion == kFeatureAnalysisVersion);
        bool taxonomyCurrent = cachedItem.tagUserOverridden
            || (cachedItem.taxonomyVersion == AbletonTaxonomy::kTaxonomyVersion);
        bool classificationCurrent = cachedItem.tagUserOverridden
            || (cachedItem.classificationModelVersion == AcousticWeights::modelVersion);
        bool derivedDataStale = !featuresCurrent || !taxonomyCurrent;
        bool classifierStale = !classificationCurrent;

        PendingInference pending;
        if (derivedDataStale || classifierStale) {
            const bool priorMlResult = cachedItem.tagSource == "ml_v3"
                || cachedItem.tagSource == "ml_ood";
            if (derivedDataStale)
                pending.item = lightReanalyzeFile(filePath, std::move(cachedItem));
            else
                pending.item = std::move(cachedItem);
            pending.embeddingAlreadyKnown = true;
            pending.derivedDataChanged = derivedDataStale;
            pending.reclassifyKnownEmbedding = !pending.item.tagUserOverridden
                && (classifierStale || (!taxonomyCurrent && priorMlResult));
        } else {
            pending.item = std::move(cachedItem);
            pending.embeddingAlreadyKnown = true;
        }

        pendingInferenceCount.fetch_add(1, std::memory_order_relaxed);
        {
            const juce::ScopedLock sl(inferenceQueueLock);
            inferenceQueue.push_back(std::move(pending));
        }
        inferenceWorker->notify();
        return true;
    }

    juce::File f(filePath);
    SampleItem loadedSample;
    loadedSample.filePath = filePath;
    loadedSample.name = f.getFileNameWithoutExtension().toStdString();

    // 1. Read format-aware metadata using TagLib
    readAudioMetadata(filePath, loadedSample.bpm, loadedSample.key, loadedSample.instrumentType);

    // 2. Load audio and resample to 32kHz (160000 samples = 5 seconds) --
    // 32kHz because that's what the PANNs Cnn10 embedding model was trained
    // on (see model_export/export_cnn10.py); still comfortably covers the
    // full range of musically-relevant fundamentals for key detection below.
    double targetRate = 32000.0;
    int targetSamplesCount = 160000;
    std::vector<float> audioWaveform = loadAndResampleWaveform(filePath, targetRate, targetSamplesCount, &loadedSample.contentHash, &loadedSample.durationSeconds);

    if (audioWaveform.empty()) {
        AppLogger::getInstance().logWarning("Failed to load audio for: " + juce::String(filePath));
        return false;
    }

    // RECOVERY PHASE R2 -- Audio Feature Analysis (see SampleManagerEngine.h
    // and docs/SLO_AUDIO_FEATURE_RECOVERY.md). Background-thread only: this
    // runs on the same scan/inference worker path as embedding extraction
    // and TagLib metadata reads above, never on the audio callback (brief
    // sections 32/33).
    loadedSample.audioFeatures = analyzeAudioProperties(filePath);
    loadedSample.featureVersion = kFeatureAnalysisVersion;

    // Auto-key detection if missing
    if (loadedSample.key.empty()) {
        std::string parsedKey = parseKeyFromFilename(loadedSample.name);
        if (!parsedKey.empty()) {
            loadedSample.key = parsedKey;
        } else {
            loadedSample.key = detectKeyFromAudio(audioWaveform.data(), static_cast<int>(audioWaveform.size()), targetRate);
        }
    }
    

    // Acoustic BPM if trusted metadata/filename evidence is missing.  The
    // estimator is intentionally conservative: form gating and the paired
    // short/long-view agreement check below can leave BPM unknown (0.0f).
    if (loadedSample.bpm <= 0.0f) {
        float parsedBpm = parseBpmFromFilename(loadedSample.name);
        if (parsedBpm > 0.0f) {
            loadedSample.bpm = parsedBpm;
        } else {
            // The embedding view is intentionally bounded to 5 seconds, but
            // tempo needs enough bars to distinguish a beat from a sparse
            // subdivision.  For longer files, make a separate bounded tempo
            // view (up to 20 seconds) while leaving the model input and cache
            // shape unchanged.  The extra decode is paid only when no trusted
            // BPM metadata/filename token exists.
            // The PANNs waveform is fixed at five seconds and may contain
            // trailing zero padding for a shorter source.  Tempo analysis is
            // independent of the model input: bound the short view to the
            // true decoded duration so padded silence cannot distort beat
            // spacing or manufacture a plausible correlation peak.
            const int shortTempoSamples = juce::jlimit(
                0, static_cast<int>(audioWaveform.size()),
                static_cast<int>(std::ceil(loadedSample.durationSeconds * targetRate)));
            const float shortTempo = estimateBpmFromAudio(
                audioWaveform.data(), shortTempoSamples, targetRate,
                loadedSample.durationSeconds);
            float longTempo = 0.0f;
            const float tempoWindowSeconds = std::min(20.0f, loadedSample.durationSeconds);
            if (tempoWindowSeconds > 5.0f) {
                const int tempoSamples = static_cast<int>(std::ceil(tempoWindowSeconds * targetRate));
                const std::vector<float> tempoWaveform = loadAndResampleWaveform(
                    filePath, targetRate, tempoSamples, nullptr, nullptr);
                longTempo = estimateBpmFromAudio(
                    tempoWaveform.data(), static_cast<int>(tempoWaveform.size()),
                    targetRate, loadedSample.durationSeconds);
            }

            // Multi-view agreement is the acoustic confidence gate.  A single
            // short view can lock onto a local subdivision; a single long view
            // can be diluted by arrangement changes.  Accept their mean only
            // when they agree, otherwise preserve the honest unknown state.
            if (shortTempo > 0.0f && longTempo > 0.0f) {
                loadedSample.bpm = std::abs(shortTempo - longTempo) <= 2.0f
                    ? std::round(((shortTempo + longTempo) * 0.5f) * 10.0f) / 10.0f
                    : 0.0f;
            } else {
                loadedSample.bpm = shortTempo > 0.0f ? shortTempo : longTempo;
            }
        }
    }

    // Computed lazily, at most once, and shared between the DSP-fallback
    // classifier below and the Ableton taxonomy classifier further down --
    // both need the same zcr/decay/energy features, and analyzeAudioBuffer
    // is redundant work worth avoiding when both run for the same file.
    bool haveSharedDspFeatures = false;
    AudioFeatures sharedDspFeatures;
    auto getSharedDspFeatures = [&]() -> const AudioFeatures& {
        if (!haveSharedDspFeatures) {
            sharedDspFeatures = analyzeAudioBuffer(audioWaveform.data(), static_cast<int>(audioWaveform.size()), targetRate);
            haveSharedDspFeatures = true;
        }
        return sharedDspFeatures;
    };

    // Default classification based on filename and parent folder matching if instrumentType is Unknown
    if (loadedSample.instrumentType == "Unknown") {
        juce::String name(loadedSample.name);
        juce::String parentFolder = f.getParentDirectory().getFileName();
        
        std::vector<std::string> nameTokens = tokenizeString(name);
        std::vector<std::string> folderTokens = tokenizeString(parentFolder);
        
        auto matchType = [&](const std::vector<std::string>& tokens, std::string& outType) -> bool {
            if (containsAnyToken(tokens, {"explosion", "explosions", "blast", "bomb", "boom"})) { outType = "Explosion"; return true; }
            if (containsAnyToken(tokens, {"laser", "lasers", "zap", "pew", "blaster", "beam"})) { outType = "Laser"; return true; }
            if (containsAnyToken(tokens, {"powerup", "buff", "level"})) { outType = "Powerup"; return true; }
            if (containsAnyToken(tokens, {"jump", "hop", "bounce"})) { outType = "Jump"; return true; }
            if (containsAnyToken(tokens, {"coin", "coins", "pickup", "gem", "chime"})) { outType = "Coin"; return true; }
            if (containsAnyToken(tokens, {"ui", "ui_", "click", "button", "menu", "select"})) { outType = "UI"; return true; }
            if (containsAnyToken(tokens, {"footstep", "footsteps", "step", "walk"})) { outType = "Footstep"; return true; }
            if (containsAnyToken(tokens, {"impact", "hit", "smash"})) { outType = "Impact"; return true; }
            if (containsAnyToken(tokens, {"kick", "kicks", "bd", "bassdrum", "kck"})) { outType = "Kick"; return true; }
            // Token->type mappings below are validated against 649 by-ear
            // labels. Corrections applied (measured agreement in brackets):
            //   crash/cymbal      Hi-Hat -> Crash      [6/6, 10/12]
            //   shaker/tambourine Hi-Hat -> Percussion [11/12, 3/5]
            //   rim/rimshot       Snare  -> Rimshot    [8/11, 2/4]
            //   snap              removed from Snare   [5/6 were Foley, not Snare]
            //   ride              removed from Hi-Hat  [ambiguous: 3/8 Misc, 2/8 Hi-Hat]
            // Crash and Rimshot were already in AbletonTaxonomy's table but
            // unreachable, because nothing ever emitted them.
            if (containsAnyToken(tokens, {"rimshot", "rim", "rimshots", "xstick", "crossstick"})) { outType = "Rimshot"; return true; }
            if (containsAnyToken(tokens, {"snare", "snares", "sd", "snr"})) { outType = "Snare"; return true; }
            if (containsAnyToken(tokens, {"crash", "crashes", "cymbal", "cymbals", "splash", "china"})) { outType = "Crash"; return true; }
            if (containsAnyToken(tokens, {"hihat", "hi-hat", "hat", "hats", "hh", "ch", "oh", "openhat", "closedhat"})) { outType = "Hi-Hat"; return true; }
            if (containsAnyToken(tokens, {"clap", "claps", "cp", "handclap"})) { outType = "Clap"; return true; }
            if (containsAnyToken(tokens, {"perc", "percussion", "tom", "toms", "conga", "bongo", "fill", "cabasa", "cowbell", "triangle", "woodblock", "clave", "shaker", "shakers", "tambourine", "tamb", "djembe", "cajon", "timbale", "guiro", "agogo"})) { outType = "Percussion"; return true; }
            if (containsAnyToken(tokens, {"bass", "sub", "808", "subbass", "synthbass", "reab"})) { outType = "Bass"; return true; }
            if (containsAnyToken(tokens, {"voc", "vocal", "vocals", "sing", "singing", "singer", "chant", "vox", "adlib", "ad-lib", "acapella", "acap", "choir", "speech", "spoken", "phrase", "bv", "bvs"})) { outType = "Vocal"; return true; }
            if (containsAnyToken(tokens, {"synth", "synthesizer", "lead", "chord", "pluck", "pad", "keys", "key", "string", "strings", "piano", "organ", "arp", "arpeggio", "stab"})) { outType = "Synth"; return true; }
            if (containsAnyToken(tokens, {"loop", "loops", "stem", "stems", "drumloop", "toploop"})) { outType = "Loop"; return true; }
            return false;
        };
        
        bool hasHeuristicsMatch = true;
        std::string detectedType = "";
        
        std::string folderDetectedType;
        const bool hasFolderMatch = matchType(folderTokens, folderDetectedType);

        if (matchType(nameTokens, detectedType)) {
            // A generic UI word such as "click" can occur in a vocal phrase
            // title (e.g. Loaded Samples' "With the Click [72 BPM]"). When a
            // clearly domain-specific Vocal folder agrees, prefer the folder
            // rather than misclassifying the sample as a UI sound. Keep the
            // normal filename-first precedence for every other conflict.
            if (detectedType == "UI" && hasFolderMatch && folderDetectedType == "Vocal") {
                loadedSample.instrumentType = folderDetectedType;
                loadedSample.winningEvidence = "FOLDER";
            } else {
                loadedSample.instrumentType = detectedType;
                loadedSample.winningEvidence = "FILENAME";
            }
        } else if (hasFolderMatch) {
            loadedSample.instrumentType = folderDetectedType;
            loadedSample.winningEvidence = "FOLDER";
        } else {
            hasHeuristicsMatch = false;
        }

        // Run C++ DSP feature analysis if filename + parent folder matching is generic/absent
        if (!hasHeuristicsMatch) {
            loadedSample.instrumentType = classifyAudioFeatures(getSharedDspFeatures(), loadedSample.name);
            loadedSample.winningEvidence = "DSP";
        }
    } else {
        loadedSample.winningEvidence = "EMBEDDED_METADATA";
    }

    // Ableton-oriented taxonomy classification (Category/Subcategory/tags) --
    // additive, does not touch instrumentType above. Gated on taxonomyVersion
    // rather than nested inside the "instrumentType == Unknown" block above,
    // so pre-existing cache rows (instrumentType already set from a prior
    // scan, taxonomyVersion still 0) get classified too, not just freshly
    // scanned files. Never runs if the user has corrected these tags --
    // a re-scan (e.g. after a file's mtime changes) must not silently
    // clobber a manual edit.
    if (!loadedSample.tagUserOverridden && loadedSample.taxonomyVersion < AbletonTaxonomy::kTaxonomyVersion) {
        const AudioFeatures& taxonomyFeatures = getSharedDspFeatures();

        // Filename/folder loop-vs-one-shot(/phrase) evidence -- independent
        // of how existingInstrumentType (category) was determined, so
        // computed unconditionally here rather than only inside the
        // "instrumentType == Unknown" branch above. See
        // AbletonTaxonomy::FilenameSubcategoryEvidence's doc comment.
        juce::String taxonomyParentFolder = f.getParentDirectory().getFileName();
        AbletonTaxonomy::ClassificationInput taxInput;
        taxInput.existingInstrumentType = loadedSample.instrumentType;
        taxInput.durationSeconds = loadedSample.durationSeconds;
        taxInput.decayTimeSeconds = taxonomyFeatures.decayTimeSeconds;
        taxInput.energyDecayRatio = taxonomyFeatures.energyDecayRatio;
        taxInput.fileName = loadedSample.name;
        taxInput.zcr = taxonomyFeatures.zcr;
        taxInput.lowEnergyRatio = taxonomyFeatures.lowEnergyRatio;
        taxInput.highEnergyRatio = taxonomyFeatures.highEnergyRatio;
        taxInput.winningEvidence = loadedSample.winningEvidence;
        taxInput.filenameEvidence = AbletonTaxonomy::detectFilenameSubcategoryEvidence(
            tokenizeString(juce::String(loadedSample.name)), tokenizeString(taxonomyParentFolder),
            rawUnderscoreSplitLowercase(juce::String(loadedSample.name)));

        AbletonTaxonomy::Classification tax = AbletonTaxonomy::classify(taxInput);
        loadedSample.category = tax.category;
        loadedSample.subcategory = tax.subcategory;
        loadedSample.secondaryTags = tax.secondaryTags;
        loadedSample.tagConfidence = tax.confidence;
        loadedSample.tagSource = "heuristic";
        loadedSample.winningEvidence = tax.winningEvidence;
        loadedSample.taxonomyVersion = AbletonTaxonomy::kTaxonomyVersion;
        normalizeTempoForTaxonomy(loadedSample);

        // Fine-Grained Subcategorization V1, Phase 10: kick length secondary
        // tag (Short/Long). Additive, duration-only -- no embedding
        // dependency, so this runs synchronously here rather than waiting
        // for the async inference batch (unlike the Bass timbre tag, which
        // needs the embedding). Real kick durations in this codebase's own
        // cross-vendor corpus are continuous (0.07-2.09s, no natural
        // cluster boundary) -- 0.7s is a median-based, stated threshold,
        // not a discovered category. See
        // docs/classification/BASS_TIMBRE_TAG_V1_REPORT.md's sibling
        // report for the kick-length methodology and
        // SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md for why this is
        // presented as an honest threshold, not false precision.
        if (loadedSample.subcategory == "Kick") {
            loadedSample.secondaryTags.push_back(loadedSample.durationSeconds >= 0.7 ? "Long" : "Short");
        }
    }

    // 3. Compute Mel Spectrogram (Optional features demonstration) - Disabled: QW-01 dead weight
    // int frames = 0;
    // int melBins = 0;
    // std::vector<float> melSpec = computeMelSpectrogram(audioWaveform, targetRate, frames, melBins);

    // Note: embedding/isProcessed are intentionally left unset here — ONNX
    // inference happens on the InferenceWorker thread, batched across many
    // files. Hand this file off to that queue instead of running inference now.
    PendingInference pending;
    pending.item = std::move(loadedSample);
    pending.waveform = std::move(audioWaveform);

    pendingInferenceCount.fetch_add(1, std::memory_order_relaxed);
    {
        const juce::ScopedLock sl(inferenceQueueLock);
        inferenceQueue.push_back(std::move(pending));
    }
    inferenceWorker->notify();
    return true;
}

void SampleManagerEngine::runInferenceBatch(std::vector<PendingInference>& batch)
{
    if (batch.empty()) return;

    // Cache-hit items already have their embedding — only the rest need to go
    // through ONNX at all. This is what lets a rescan of an already-cached
    // library skip inference entirely for unchanged files while still sharing
    // the same batch/commit/UMAP-placement/FIFO pipeline as freshly-processed ones.
    std::vector<size_t> needsInference;
    needsInference.reserve(batch.size());
    for (size_t i = 0; i < batch.size(); ++i) {
        if (!batch[i].embeddingAlreadyKnown) needsInference.push_back(i);
    }

    // RECOVERY PHASE R3-G -- Cache Version Enforcement. Items that skipped
    // ONNX inference (embeddingAlreadyKnown) but had stale DSP features/
    // taxonomy selectively recomputed by lightReanalyzeFile() still need
    // their row rewritten, or the refresh is silently lost the moment
    // `samples` is discarded (e.g. app relaunch) -- see
    // docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §4.
    std::vector<size_t> cacheRewriteIndices = needsInference;
    for (size_t i = 0; i < batch.size(); ++i) {
        if (batch[i].embeddingAlreadyKnown
            && (batch[i].derivedDataChanged || batch[i].reclassifyKnownEmbedding))
            cacheRewriteIndices.push_back(i);
    }

    const int64_t batchSize = static_cast<int64_t>(needsInference.size());
    const int64_t sampleLen = 160000; // must match targetSamplesCount used in prepareFile

    if (batchSize > 0) {
        // Acquire-load synchronizes-with initAsync()'s release-store, so a
        // Ready read here guarantees session/env are fully constructed and
        // safe to dereference from this (inference worker) thread even
        // though they were built on a different (init) thread -- see the
        // engineState member comment in SampleManagerEngine.h.
        if (engineState.load(std::memory_order_acquire) == EngineInitState::Ready) {
            try {
                // Pack every waveform needing inference into one contiguous
                // [batchSize, sampleLen] tensor so a single Ort::Session::Run()
                // call covers the whole batch, instead of one Run() per file.
                std::vector<float> batchInput(static_cast<size_t>(batchSize) * static_cast<size_t>(sampleLen));
                for (int64_t b = 0; b < batchSize; ++b) {
                    const auto& wf = batch[needsInference[static_cast<size_t>(b)]].waveform;
                    std::copy(wf.begin(), wf.end(), batchInput.begin() + static_cast<size_t>(b) * static_cast<size_t>(sampleLen));
                }

                std::vector<int64_t> input_shape = { batchSize, sampleLen };

                auto memory_info = Ort::MemoryInfo::CreateCpu(OrtDeviceAllocator, OrtMemTypeCPU);
                Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
                    memory_info,
                    batchInput.data(),
                    batchInput.size(),
                    input_shape.data(),
                    input_shape.size()
                );

                const char* input_names[] = { "input" };
                const char* output_names[] = { "output" };

                auto output_tensors = session->Run(
                    Ort::RunOptions{ nullptr },
                    input_names,
                    &input_tensor,
                    1,
                    output_names,
                    1
                );

                if (output_tensors.size() != 1
                    || !hasExpectedEmbeddingOutput(output_tensors.front(), batchSize))
                {
                    throw std::runtime_error("ONNX embedding output must be one float tensor shaped [batch, 512]");
                }

                // Output is [batchSize, 512]
                float* output_data = output_tensors.front().GetTensorMutableData<float>();
                for (int64_t b = 0; b < batchSize; ++b) {
                    auto& item = batch[needsInference[static_cast<size_t>(b)]].item;
                    float* row = output_data + b * 512;
                    item.embedding.assign(row, row + AcousticClassifier::pannsDim);

                    // item.embedding stays the 512-D PANNs vector: it is what
                    // gets persisted, indexed and similarity-searched. The 8 DSP
                    // dims are appended only into the transient classifier input
                    // built by buildAcousticClassifierInput().

                    // Shape is not enough to establish a usable model result:
                    // reject zero/non-finite embeddings before they can be
                    // classified, cached, or indexed.  Treat this exactly
                    // like another retryable inference failure; no fabricated
                    // fallback class or vector is allowed.
                    if (!AcousticClassifier::isValidEmbedding(item.embedding.data()))
                    {
                        item.embedding.clear();
                        item.embeddingFailureCount++;
                        item.embeddingStatus = (item.embeddingFailureCount >= kMaxEmbeddingFailuresBeforePermanent)
                            ? EmbeddingStatus::FailedPermanent
                            : EmbeddingStatus::FailedRetryable;
                        item.embeddingModelVersion = 0;
                        continue;
                    }

                    item.embeddingStatus = EmbeddingStatus::Valid;
                    item.embeddingFailureCount = 0;
                    item.embeddingModelVersion = kEmbeddingModelVersion; // RECOVERY PHASE R3-G

                    // PHASE V4-D: Evaluate Classification V3 linear head on
                    // the 512D PANNs embedding. The same helper is also used
                    // for a valid cache-hit embedding when taxonomy refresh
                    // explicitly marked its prior ML result stale.
                    applyAcousticClassification(item);
                }
            }
            catch (const std::exception& e) {
                // A batched Run() failure doesn't tell us which file in the
                // batch was the problem, so every file in this batch is
                // marked failed-and-retryable rather than caching a fake
                // "zero embedding" that would silently poison similarity
                // search results forever with no automatic retry -- see
                // docs/ONNX_FAILURE_HANDLING.md. NOT_ANALYSED-style: no
                // meaningful vector, never treated as real data downstream.
                AppLogger::getInstance().logError("ONNX batched inference error (batch of " + juce::String(batchSize) + "): " + e.what());
                for (size_t idx : needsInference) {
                    auto& item = batch[idx].item;
                    item.embedding.clear();
                    item.embeddingFailureCount++;
                    item.embeddingStatus = (item.embeddingFailureCount >= kMaxEmbeddingFailuresBeforePermanent)
                        ? EmbeddingStatus::FailedPermanent
                        : EmbeddingStatus::FailedRetryable;
                }
            }
        } else {
            // Model failed to load -- no real embedding can be produced.
            // Per Phase 2 Section 18 ("no fake intelligence"): never
            // manufacture a plausible-looking pseudo-embedding (e.g. from a
            // filename hash) to paper over this. Mark honestly as failed
            // instead so downstream similarity/duplicate features clearly
            // have nothing to work with rather than silently misleading
            // results driven by meaningless vectors.
            for (size_t idx : needsInference) {
                auto& item = batch[idx].item;
                item.embedding.clear();
                item.embeddingFailureCount++;
                item.embeddingStatus = (item.embeddingFailureCount >= kMaxEmbeddingFailuresBeforePermanent)
                    ? EmbeddingStatus::FailedPermanent
                    : EmbeddingStatus::FailedRetryable;
            }
        }
    }

    // Cache hydration skips ONNX because the embedding is already persisted,
    // but a stale taxonomy or classifier-head version still needs the
    // deterministic acoustic head/gate reapplied. Do this after fresh
    // inference so both paths share exactly the same helper.
    for (size_t i = 0; i < batch.size(); ++i) {
        if (batch[i].embeddingAlreadyKnown && batch[i].reclassifyKnownEmbedding) {
            applyAcousticClassification(batch[i].item);
            // A valid persisted embedding was evaluated by the current
            // classifier even when waveform decode failed, so this row has a
            // current taxonomy result (including an explicit abstention).
            if (hasSafeEmbeddingBuffer(batch[i].item.embedding))
                batch[i].item.taxonomyVersion = AbletonTaxonomy::kTaxonomyVersion;
        }
    }

    // Cache the freshly-computed entries (cache-hit items don't need re-writing —
    // they came from the cache unchanged). Failed-but-retryable items are
    // deliberately excluded from indices passed to upsertCacheEntries below
    // via its own status check, so a transient failure doesn't get "stuck"
    // in the cache and skip retry on the next scan.
    upsertCacheEntries(batch, cacheRewriteIndices);

    // Commit the whole batch to the shared database under a single lock
    // acquisition, rather than one lock/unlock per file.
    int addedInCommit = 0;
    {
        const juce::ScopedLock sl(dbLock);
        for (auto& p : batch) {
            p.item.isProcessed = true;
            // O(1) map lookup instead of an O(N) find_if per item -- with a
            // 64-item batch this was O(64*N) string comparisons under the
            // lock on every batch (Phase 3, engineering/slo-perf-scale-v1).
            const size_t existingIndex = findSampleIndex(p.item.filePath);
            const bool isNewSample = (existingIndex == kSampleIndexNotFound);

            if (isNewSample) {
                // Push a copy into the lock-free FIFO before moving the original
                // into `samples`, so the UI can pick up brand-new points cheaply
                // (see drainNewSampleEvents) without waiting for/paying for a full
                // getSamples() copy of the whole (potentially 100k+ item) vector.
                // If the FIFO is momentarily full, this is a harmless no-op — the
                // UI's version-gated full-pull fallback still catches it eventually.
                int start1, size1, start2, size2;
                canvasUpdateFifo.prepareToWrite(1, start1, size1, start2, size2);
                if (size1 > 0) {
                    canvasUpdateSlots[static_cast<size_t>(start1)] = p.item;
                } else if (size2 > 0) {
                    canvasUpdateSlots[static_cast<size_t>(start2)] = p.item;
                }
                canvasUpdateFifo.finishedWrite(size1 + size2);

                samples.push_back(std::move(p.item));
                pathToIndex.emplace(samples.back().filePath, samples.size() - 1);
                ++addedInCommit;
            } else {
                samples[existingIndex] = std::move(p.item);
            }
        }
    }
    if (addedInCommit > 0)
        scanAdded.fetch_add(addedInCommit, std::memory_order_relaxed);
    scanChanged.fetch_add(static_cast<int>(batch.size()) - addedInCommit, std::memory_order_relaxed);

    // Keep admission coalesced until the complete path has committed, not
    // merely until decode/DSP preparation has finished. Otherwise a second
    // scan can arrive while the first item is waiting in the inference batch
    // and schedule duplicate model work for the same file.
    for (const auto& item : batch)
        releaseQueuedPath(item.item.filePath);

    int failedInBatch = 0;
    for (const auto& item : batch)
    {
        if (item.item.embeddingStatus == EmbeddingStatus::FailedRetryable
            || item.item.embeddingStatus == EmbeddingStatus::FailedPermanent)
            ++failedInBatch;
    }
    if (failedInBatch > 0)
        scanFailed.fetch_add(failedInBatch, std::memory_order_relaxed);
    scanDone.fetch_add(static_cast<int>(batch.size()), std::memory_order_relaxed);

    pendingInferenceCount.fetch_sub(static_cast<int>(batch.size()), std::memory_order_relaxed);
    samplesVersion.fetch_add(1, std::memory_order_relaxed);
    maybeNotifyUpdate();
}

void SampleManagerEngine::InferenceWorker::run()
{
    constexpr int kFlushWaitMs = 150;

    // Phase 2 batch-size sweep hook: benchmark tooling can override the batch
    // bounds via environment variables to measure CoreML/ANE behavior at
    // different batch sizes without rebuilding. Dev-only: not read from any
    // settings file, and not documented as a user knob (see
    // docs/BATCH_SIZE_SWEEP_REPORT.md).
    // Batch bounds. Defaults adopted from the Phase 2 measured sweep
    // (docs/BATCH_SIZE_SWEEP_REPORT.md): max 32 matched or beat 64/128 on
    // cold-scan throughput in Release and reduced post-scan RSS by roughly
    // 1 GB (smaller ONX/CoreML working set per Run()). SLO_INFERENCE_MIN_BATCH
    // / SLO_INFERENCE_MAX_BATCH remain available as a dev-only override hook
    // for future re-tuning; not a user-facing knob.
    size_t kMinBatch = 16;
    size_t kMaxBatch = 32;
    if (const char* envMin = std::getenv("SLO_INFERENCE_MIN_BATCH")) {
        const long v = std::strtol(envMin, nullptr, 10);
        if (v > 0 && v <= 1024) kMinBatch = static_cast<size_t>(v);
    }
    if (const char* envMax = std::getenv("SLO_INFERENCE_MAX_BATCH")) {
        const long v = std::strtol(envMax, nullptr, 10);
        if (v > 0 && v <= 1024 && static_cast<size_t>(v) >= kMinBatch) kMaxBatch = static_cast<size_t>(v);
    }


    auto collectBatch = [this, kMaxBatch](std::vector<SampleManagerEngine::PendingInference>& out) {
        const juce::ScopedLock sl(engine.inferenceQueueLock);
        while (!engine.inferenceQueue.empty() && out.size() < kMaxBatch) {
            out.push_back(std::move(engine.inferenceQueue.front()));
            engine.inferenceQueue.pop_front();
        }
    };

    while (!threadShouldExit()) {
        std::vector<SampleManagerEngine::PendingInference> batch;
        collectBatch(batch);

        if (batch.empty()) {
            wait(kFlushWaitMs);
            continue;
        }

        if (batch.size() < kMinBatch) {
            // Give a little more time for the batch to fill up before running
            // inference, so a fast-arriving scan gets real batching instead of
            // lots of tiny Run() calls. But only while scan workers are still
            // producing: prepareFile() (both the cache-hit and fresh-decode
            // enqueue paths) is the ONLY producer of inferenceQueue, and it
            // always runs on a scanPool job. Once the pool has fully drained,
            // nothing else will ever arrive, so waiting out the full grace
            // period here would stall the tail batch of a finished scan by
            // kFlushWaitMs for no benefit. (Enqueue sites already call
            // inferenceWorker->notify(), which wakes the wait() below early,
            // so this grace wait never delays a batch that fills up.)
            if (engine.scanPool.getNumJobs() != 0) {
                wait(kFlushWaitMs);
                collectBatch(batch);
            }
        }

        engine.runInferenceBatch(batch);
    }
}

struct SampleManagerEngine::HnswIndexImpl {
    static constexpr size_t kDim = 512;
    std::unique_ptr<hnswlib::L2Space> space;
    std::unique_ptr<hnswlib::HierarchicalNSW<float>> index;
    size_t capacity = 0;

    void ensureCapacity(size_t needed) {
        if (index == nullptr || needed <= capacity) return;
        size_t newCap = std::max(needed, capacity * 2);
        index->resizeIndex(newCap);
        capacity = newCap;
    }
};

void SampleManagerEngine::rebuildHnswIndexFull()
{
    size_t n = samples.size();

    hnswIndex = std::make_unique<HnswIndexImpl>();
    hnswIndex->space = std::make_unique<hnswlib::L2Space>(HnswIndexImpl::kDim);
    size_t initialCap = std::max<size_t>(n, 64);
    hnswIndex->index = std::make_unique<hnswlib::HierarchicalNSW<float>>(hnswIndex->space.get(), initialCap, 16, 200);
    hnswIndex->capacity = initialCap;
    hnswIndex->index->setEf(50);

    for (size_t i = 0; i < n; ++i) {
        // A sample can be isProcessed==true with no Valid embedding (a
        // failed/retryable/permanent embedding attempt -- see
        // docs/ONNX_FAILURE_HANDLING.md, embedding is cleared in that case).
        // hnswlib::addPoint reads exactly kDim floats from whatever pointer
        // it's given with no bounds checking, so passing an empty vector's
        // data() would read out of bounds. Skipping still leaves `i` as the
        // correct positional label for every point actually added, since
        // label is passed explicitly rather than relying on insertion order.
        if (!hasUsableEmbedding(samples[i])) continue;
        hnswIndex->index->addPoint(samples[i].embedding.data(), i);
    }
}

void SampleManagerEngine::placeNewSamplesIncrementally()
{
    if (hnswIndex == nullptr || hnswIndex->index == nullptr) {
        // Shouldn't normally happen once bootstrapped, but recover gracefully.
        rebuildHnswIndexFull();
        return;
    }

    constexpr size_t k = 10;
    hnswIndex->ensureCapacity(samples.size());

    for (size_t i = umapProjectedCount; i < samples.size(); ++i) {
        auto& target = samples[i];

        // No Valid embedding (failed/retryable/permanent) -- nothing to
        // query or add to the index with. Leave at the default (0,0); it'll
        // get a real position once/if a future rescan produces a Valid
        // embedding for it (isProcessed alone no longer implies a usable
        // embedding -- see docs/ONNX_FAILURE_HANDLING.md).
        if (!hasUsableEmbedding(target)) continue;

        if (hnswIndex->index->cur_element_count == 0) {
            // No existing points to anchor to — place at the origin.
            target.x = 0.0f;
            target.y = 0.0f;
        } else {
            size_t kk = std::min(k, static_cast<size_t>(hnswIndex->index->cur_element_count));
            auto result = hnswIndex->index->searchKnn(target.embedding.data(), kk);

            // Distance-weighted centroid of the neighbors' already-known 2D
            // positions — a standard UMAP out-of-sample extension approximation.
            float sumWeight = 0.0f;
            float sumX = 0.0f;
            float sumY = 0.0f;
            while (!result.empty()) {
                float dist = result.top().first;
                size_t label = static_cast<size_t>(result.top().second);
                result.pop();

                float weight = 1.0f / (dist + 1e-4f);
                const auto& neighbor = samples[label];
                sumX += weight * neighbor.x;
                sumY += weight * neighbor.y;
                sumWeight += weight;
            }

            if (sumWeight > 0.0f) {
                target.x = sumX / sumWeight;
                target.y = sumY / sumWeight;
            } else {
                target.x = 0.0f;
                target.y = 0.0f;
            }
        }

        // Add to the index so later new points in this same batch (e.g. many
        // similar samples added together) can use it as a neighbor too.
        hnswIndex->index->addPoint(target.embedding.data(), i);
    }
}

std::vector<SampleItem> SampleManagerEngine::findSimilarSamples(const std::string& filePath, size_t k)
{
    const juce::ScopedLock sl(dbLock);

    if (hnswIndex == nullptr || hnswIndex->index == nullptr || hnswIndex->index->cur_element_count == 0) {
        return {};
    }

    const SampleItem* queryItem = nullptr;
    {
        // O(1) map lookup instead of the previous O(N) linear scan under the
        // lock (Phase 3, engineering/slo-perf-scale-v1). The HNSW search
        // below deliberately stays inside dbLock: rebuildHnswIndexFull() can
        // replace the index on another thread, and unlike `samples` its
        // replacement isn't proven safe against a concurrent query.
        const size_t queryIndex = findSampleIndex(filePath);
        if (queryIndex == kSampleIndexNotFound) {
            return {};
        }
        queryItem = &samples[queryIndex];
    }
    if (!hasUsableEmbedding(*queryItem)) {
        return {};
    }

    // Fetch k+1: the query sample is almost always its own nearest neighbor
    // (distance 0), so ask for one extra to still return k real results
    // after excluding it below.
    size_t kk = std::min(k + 1, static_cast<size_t>(hnswIndex->index->cur_element_count));
    auto result = hnswIndex->index->searchKnn(queryItem->embedding.data(), kk);

    // hnswlib's searchKnn returns a max-heap (farthest-first on pop) --
    // collect then sort ascending so callers get a properly ranked
    // nearest-first list rather than relying on undocumented pop order.
    std::vector<std::pair<float, size_t>> candidates;
    candidates.reserve(result.size());
    while (!result.empty()) {
        candidates.push_back({ result.top().first, static_cast<size_t>(result.top().second) });
        result.pop();
    }
    std::sort(candidates.begin(), candidates.end(),
              [](const auto& a, const auto& b) { return a.first < b.first; });

    std::vector<SampleItem> similar;
    similar.reserve(k);
    for (const auto& candidate : candidates) {
        size_t label = candidate.second;
        if (label >= samples.size()) continue; // defensive, shouldn't happen
        if (samples[label].filePath == filePath) continue; // exclude the query itself
        similar.push_back(samples[label]);
        if (similar.size() >= k) break;
    }
    return similar;
}

// === RECOVERY PHASE R3 -- Intelligence Stack ============================
// R3-A Weighted Find Similar / R3-B Timbre Refinement / R3-C Reference
// Search / R3-D Near-Duplicates / R3-E Auto-Tagging / R3-F Map Clusters.
// See docs/SLO_R3_INTELLIGENCE_RECOVERY.md for full evidence/classification
// per subsystem.

namespace {

// Per-field normalization ranges for the restored R2 AudioAnalysisResult
// fields used below. No historical normalization constants survived the
// incident (brief section 17) -- these are a documented, deterministic
// derivation from the R2 contract's own field-range comments
// (SampleManagerEngine.h: spectralCentroid in Hz up to Nyquist at the 32kHz
// analysis rate, crestFactor >= 1.0, onsetCount an unbounded-but-typically-
// small per-5s-window integer, zeroCrossingRate already in [0,1]). Classified
// NEW IMPLEMENTATION DUE TO INSUFFICIENT HISTORICAL EVIDENCE for these exact
// coefficients specifically, distinct from the overall hybrid-formula shape
// (which IS evidence-backed -- see docs/SMART_SAMPLE_MANAGER_FEATURE_ROADMAP.md).
float normalizeCentroidHz(float hz) { return juce::jlimit(0.0f, 1.0f, hz / 8000.0f); }
float normalizeCrestFactor(float ratio) { return juce::jlimit(0.0f, 1.0f, (ratio - 1.0f) / 9.0f); }
float normalizeOnsetCount(int count) { return juce::jlimit(0.0f, 1.0f, static_cast<float>(count) / 10.0f); }
float normalizeZcr(float zcr) { return juce::jlimit(0.0f, 1.0f, zcr); }

// Symmetric weighted DSP distance between two feature sets, in [0,1]
// regardless of the weights' absolute magnitudes (divides by their sum) --
// used by findSimilarWeighted (R3-A). A field whose weight is 0 contributes
// nothing, so all-zero weights make this 0 for every candidate (degenerating
// findSimilarWeighted to pure embedding similarity, matching
// findSimilarSamples' ordering).
float weightedDspDistance(const AudioAnalysisResult& q, const AudioAnalysisResult& c,
                           float centroidWeight, float crestWeight, float onsetWeight)
{
    float totalWeight = centroidWeight + crestWeight + onsetWeight;
    if (totalWeight <= 0.0f) return 0.0f;

    float dist = 0.0f;
    dist += centroidWeight * std::abs(normalizeCentroidHz(q.spectralCentroid) - normalizeCentroidHz(c.spectralCentroid));
    dist += crestWeight * std::abs(normalizeCrestFactor(q.crestFactor) - normalizeCrestFactor(c.crestFactor));
    dist += onsetWeight * std::abs(normalizeOnsetCount(q.onsetCount) - normalizeOnsetCount(c.onsetCount));
    return dist / totalWeight;
}

} // namespace

std::vector<SampleItem> SampleManagerEngine::findSimilarWeighted(const std::string& filePath,
                                                                   const FeatureWeights& weights,
                                                                   float dspWeight, size_t k)
{
    const juce::ScopedLock sl(dbLock);

    if (hnswIndex == nullptr || hnswIndex->index == nullptr || hnswIndex->index->cur_element_count == 0)
        return {};

    const SampleItem* queryItem = nullptr;
    const size_t queryIndex = findSampleIndex(filePath);
    if (queryIndex == kSampleIndexNotFound)
        return {};
    queryItem = &samples[queryIndex];
    if (!hasUsableEmbedding(*queryItem))
        return {};

    dspWeight = juce::jlimit(0.0f, 1.0f, dspWeight);

    // Over-fetch a wider embedding-candidate pool than k so the DSP rerank
    // below has real headroom to change the final top-k ordering (brief
    // section 21/22: DSP weights must actually be able to affect the
    // result, not just tie-break within an already-tiny embedding top-k).
    size_t poolSize = std::min<size_t>(std::max<size_t>(k * 5, 20) + 1,
                                        static_cast<size_t>(hnswIndex->index->cur_element_count));
    auto result = hnswIndex->index->searchKnn(queryItem->embedding.data(), poolSize);

    struct Candidate { size_t label; float embDist; };
    std::vector<Candidate> candidates;
    candidates.reserve(result.size());
    float maxEmbDist = 0.0f;
    while (!result.empty()) {
        float d = result.top().first;
        candidates.push_back({ static_cast<size_t>(result.top().second), d });
        maxEmbDist = std::max(maxEmbDist, d);
        result.pop();
    }

    struct Scored { size_t label; float score; };
    std::vector<Scored> scored;
    scored.reserve(candidates.size());
    for (const auto& c : candidates) {
        if (c.label >= samples.size()) continue;
        if (samples[c.label].filePath == filePath) continue; // never return the query itself (brief section 20)

        float normEmbDist = (maxEmbDist > 0.0f) ? (c.embDist / maxEmbDist) : 0.0f;
        float dspDist = weightedDspDistance(queryItem->audioFeatures, samples[c.label].audioFeatures,
                                             weights.spectralCentroidWeight, weights.crestFactorWeight,
                                             weights.onsetCountWeight);
        float hybrid = (1.0f - dspWeight) * normEmbDist + dspWeight * dspDist;
        scored.push_back({ c.label, hybrid });
    }

    // Deterministic ranking (brief section 21): ascending score, tie-broken
    // by file path so identical scores never depend on hash/insertion order.
    std::sort(scored.begin(), scored.end(), [this](const Scored& a, const Scored& b) {
        if (a.score != b.score) return a.score < b.score;
        return samples[a.label].filePath < samples[b.label].filePath;
    });

    std::vector<SampleItem> out;
    out.reserve(k);
    for (const auto& s : scored) {
        out.push_back(samples[s.label]);
        if (out.size() >= k) break;
    }
    return out;
}

std::vector<SampleItem> SampleManagerEngine::findSimilarRefined(const std::string& filePath,
                                                                  const TimbreRefinement& refinement, size_t k)
{
    const juce::ScopedLock sl(dbLock);

    if (hnswIndex == nullptr || hnswIndex->index == nullptr || hnswIndex->index->cur_element_count == 0)
        return {};

    const SampleItem* queryItem = nullptr;
    const size_t queryIndex = findSampleIndex(filePath);
    if (queryIndex == kSampleIndexNotFound)
        return {};
    queryItem = &samples[queryIndex];
    if (!hasUsableEmbedding(*queryItem))
        return {};

    // Semantic -> DSP mapping (brief section 26, documented in the header):
    // Brightness->spectralCentroid, Punch->crestFactor, Noise->zeroCrossingRate.
    // Each control shifts the *target* value for its field away from the
    // query's own value (rather than just re-weighting a symmetric distance,
    // which can't express directionality -- "brighter than me", not merely
    // "however different in brightness"). At shift==0 the target collapses
    // back to the query's own value, so the field distance becomes the
    // ordinary symmetric distance-to-query -- this is what makes neutral
    // parity (brief section 27) hold by construction, not by a separate
    // special case.
    float brightness = juce::jlimit(-1.0f, 1.0f, refinement.brightnessShift);
    float punch = juce::jlimit(-1.0f, 1.0f, refinement.punchShift);
    float noise = juce::jlimit(-1.0f, 1.0f, refinement.noiseShift);
    constexpr float kShiftMagnitude = 0.5f; // how far a full +-1 shift moves the target within [0,1]

    float centroidTarget = juce::jlimit(0.0f, 1.0f, normalizeCentroidHz(queryItem->audioFeatures.spectralCentroid) + brightness * kShiftMagnitude);
    float crestTarget = juce::jlimit(0.0f, 1.0f, normalizeCrestFactor(queryItem->audioFeatures.crestFactor) + punch * kShiftMagnitude);
    float zcrTarget = juce::jlimit(0.0f, 1.0f, normalizeZcr(queryItem->audioFeatures.zeroCrossingRate) + noise * kShiftMagnitude);

    // Fixed neutral DSP contribution (brief section 27's "findSimilarRefined(query, neutral)
    // should reproduce baseline weighted similarity" -- this constant defines that baseline
    // for this function's own neutral configuration).
    constexpr float kDspWeight = 0.3f;

    size_t poolSize = std::min<size_t>(std::max<size_t>(k * 5, 20) + 1,
                                        static_cast<size_t>(hnswIndex->index->cur_element_count));
    auto result = hnswIndex->index->searchKnn(queryItem->embedding.data(), poolSize);

    struct Candidate { size_t label; float embDist; };
    std::vector<Candidate> candidates;
    candidates.reserve(result.size());
    float maxEmbDist = 0.0f;
    while (!result.empty()) {
        float d = result.top().first;
        candidates.push_back({ static_cast<size_t>(result.top().second), d });
        maxEmbDist = std::max(maxEmbDist, d);
        result.pop();
    }

    struct Scored { size_t label; float score; };
    std::vector<Scored> scored;
    scored.reserve(candidates.size());
    for (const auto& c : candidates) {
        if (c.label >= samples.size()) continue;
        if (samples[c.label].filePath == filePath) continue;

        const auto& cf = samples[c.label].audioFeatures;
        float fieldDist = std::abs(normalizeCentroidHz(cf.spectralCentroid) - centroidTarget)
                         + std::abs(normalizeCrestFactor(cf.crestFactor) - crestTarget)
                         + std::abs(normalizeZcr(cf.zeroCrossingRate) - zcrTarget);
        fieldDist /= 3.0f;

        float normEmbDist = (maxEmbDist > 0.0f) ? (c.embDist / maxEmbDist) : 0.0f;
        float hybrid = (1.0f - kDspWeight) * normEmbDist + kDspWeight * fieldDist;
        scored.push_back({ c.label, hybrid });
    }

    std::sort(scored.begin(), scored.end(), [this](const Scored& a, const Scored& b) {
        if (a.score != b.score) return a.score < b.score;
        return samples[a.label].filePath < samples[b.label].filePath;
    });

    std::vector<SampleItem> out;
    out.reserve(k);
    for (const auto& s : scored) {
        out.push_back(samples[s.label]);
        if (out.size() >= k) break;
    }
    return out;
}

// RECOVERY PHASE R3-C -- Reference Search. Pipeline restored verbatim from
// docs/SMART_SAMPLE_MANAGER_FEATURE_ARCHITECTURE.md §4 (pre-incident doc):
// decode+resample -> one-off ONNX inference -> query existing HNSW index ->
// sort ascending -> top K. The reference file's embedding lives only in a
// local variable; it is never written to `samples`, the cache DB, or the
// UMAP index (brief section 32).
std::vector<SampleItem> SampleManagerEngine::findSimilarToReference(const std::string& referencePath, size_t k)
{
    if (engineState.load(std::memory_order_acquire) != EngineInitState::Ready)
        return {}; // no model available -- never fabricate a result (brief section 45's "no fake intelligence" principle applies here too)

    juce::File refFile(referencePath);
    if (!refFile.existsAsFile())
        return {};

    double targetRate = 32000.0;
    int targetSamplesCount = 160000;
    std::vector<float> waveform = loadAndResampleWaveform(referencePath, targetRate, targetSamplesCount, nullptr, nullptr);
    if (waveform.empty())
        return {}; // malformed/undecodable reference file -- fail safe, not fake (brief section 34)

    std::vector<float> embedding;
    try {
        std::vector<int64_t> input_shape = { 1, static_cast<int64_t>(targetSamplesCount) };
        auto memory_info = Ort::MemoryInfo::CreateCpu(OrtDeviceAllocator, OrtMemTypeCPU);
        Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
            memory_info, waveform.data(), waveform.size(), input_shape.data(), input_shape.size());

        const char* input_names[] = { "input" };
        const char* output_names[] = { "output" };
        auto output_tensors = session->Run(Ort::RunOptions{ nullptr }, input_names, &input_tensor, 1, output_names, 1);

        if (output_tensors.size() != 1
            || !hasExpectedEmbeddingOutput(output_tensors.front(), 1))
        {
            throw std::runtime_error("ONNX reference embedding output must be one float tensor shaped [1, 512]");
        }

        float* output_data = output_tensors.front().GetTensorMutableData<float>();
        embedding.assign(output_data, output_data + 512);
        if (!AcousticClassifier::isValidEmbedding(embedding.data()))
            return {};
    } catch (const std::exception& e) {
        AppLogger::getInstance().logError(juce::String("Reference search inference failed: ") + e.what());
        return {};
    }

    const juce::ScopedLock sl(dbLock);
    if (hnswIndex == nullptr || hnswIndex->index == nullptr || hnswIndex->index->cur_element_count == 0)
        return {};

    size_t kk = std::min(k, static_cast<size_t>(hnswIndex->index->cur_element_count));
    auto result = hnswIndex->index->searchKnn(embedding.data(), kk);

    std::vector<std::pair<float, size_t>> candidates;
    candidates.reserve(result.size());
    while (!result.empty()) {
        candidates.push_back({ result.top().first, static_cast<size_t>(result.top().second) });
        result.pop();
    }
    std::sort(candidates.begin(), candidates.end(), [](const auto& a, const auto& b) { return a.first < b.first; });

    std::vector<SampleItem> out;
    out.reserve(k);
    for (const auto& c : candidates) {
        if (c.second >= samples.size()) continue;
        out.push_back(samples[c.second]);
        if (out.size() >= k) break;
    }
    return out;
}

// RECOVERY PHASE R3-D -- Near-Duplicate Detection. Cosine similarity over
// 512D embeddings, O(N^2) (brief section 41: restore correctness first).
// Threshold default 0.98 -- the exact value named in
// docs/SMART_SAMPLE_MANAGER_FEATURE_ROADMAP.md's V1.1 entry and in
// Source/test_near_duplicates_main.cpp. Grouping via union-find into
// connected components (a chain of pairwise-similar-enough samples forms one
// group, not just isolated pairs) -- the roadmap doc doesn't specify pairs
// vs. components, so components were chosen as the more useful "flag
// everything related to prune" behavior a cleanup UI would actually want;
// classified accordingly in the R3 synthesis. Purely read-only (brief
// section 38) -- returns groups, never deletes/moves files.
std::vector<DuplicateGroup> SampleManagerEngine::findNearDuplicates(float cosineThreshold)
{
    const juce::ScopedLock sl(dbLock);

    std::vector<size_t> indices;
    indices.reserve(samples.size());
    for (size_t i = 0; i < samples.size(); ++i) {
        if (hasUsableEmbedding(samples[i]))
            indices.push_back(i);
    }

    size_t n = indices.size();
    std::vector<size_t> parent(n);
    for (size_t i = 0; i < n; ++i) parent[i] = i;
    std::function<size_t(size_t)> find = [&](size_t x) {
        while (parent[x] != x) { parent[x] = parent[parent[x]]; x = parent[x]; }
        return x;
    };
    auto unite = [&](size_t a, size_t b) {
        size_t ra = find(a), rb = find(b);
        if (ra != rb) parent[ra] = rb;
    };

    for (size_t i = 0; i < n; ++i) {
        const auto& a = samples[indices[i]].embedding;
        float normA = VectorMath::dotProduct(a.data(), a.data(), 512);
        if (normA <= 0.0f) continue;
        for (size_t j = i + 1; j < n; ++j) {
            const auto& b = samples[indices[j]].embedding;
            float normB = VectorMath::dotProduct(b.data(), b.data(), 512);
            if (normB <= 0.0f) continue;
            float dot = VectorMath::dotProduct(a.data(), b.data(), 512);
            float cosine = dot / (std::sqrt(normA) * std::sqrt(normB));
            if (cosine >= cosineThreshold)
                unite(i, j);
        }
    }

    std::unordered_map<size_t, std::vector<SampleItem>> byRoot;
    for (size_t i = 0; i < n; ++i)
        byRoot[find(i)].push_back(samples[indices[i]]);

    std::vector<DuplicateGroup> groups;
    for (auto& [root, items] : byRoot) {
        if (items.size() < 2) continue;
        // Deterministic member order within a group.
        std::sort(items.begin(), items.end(), [](const SampleItem& a, const SampleItem& b) {
            return a.filePath < b.filePath;
        });
        // contentHash is reused as the group's identity string only if every
        // member shares one (i.e. they're also exact byte/content
        // duplicates); otherwise left empty to signal "near, not exact"
        // (brief section 37's duplicate-vs-near-duplicate distinction).
        std::string groupHash = items.front().contentHash;
        for (const auto& it : items)
            if (it.contentHash != groupHash) { groupHash.clear(); break; }
        groups.push_back(DuplicateGroup{ groupHash, std::move(items) });
    }

    std::sort(groups.begin(), groups.end(), [](const DuplicateGroup& a, const DuplicateGroup& b) {
        if (a.items.size() != b.items.size()) return a.items.size() > b.items.size();
        return a.items.front().filePath < b.items.front().filePath; // deterministic tie-break
    });

    return groups;
}

// RECOVERY PHASE R3-E -- Auto-Tagging. Deterministic, profile-based (brief
// section 45 -- no LLM/cloud/new neural network). Pure function of already-
// computed category/subcategory/secondaryTags (AbletonTaxonomy) and R2's
// AudioAnalysisResult, matching docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md
// §3's description of predictedTags as "a pure function of category/
// audioFeatures/instrumentType". Deliberately excludes the raw category
// string itself (brief section 46: historical UX work found broad
// Drum/Percussion tags redundant with Category, once that redundancy was
// identified) -- subcategory (more specific) and derived attribute tags are
// kept.
std::vector<std::string> generatePredictedTags(const SampleItem& item)
{
    std::vector<std::string> tags;

    if (!item.subcategory.empty())
        tags.push_back(item.subcategory);
    for (const auto& t : item.secondaryTags)
        tags.push_back(t);

    const auto& f = item.audioFeatures;
    if (item.featureVersion > 0) {
        // Thresholds derived from the same normalization ranges used by
        // R3-A/B above -- no historical thresholds survived (brief section
        // 47: document rather than hide arbitrary thresholds).
        if (f.spectralCentroid >= 4000.0f) tags.push_back("Bright");
        else if (f.spectralCentroid > 0.0f && f.spectralCentroid < 1200.0f) tags.push_back("Dark");

        if (f.crestFactor >= 4.0f) tags.push_back("Punchy");
        if (f.onsetCount >= 3) tags.push_back("Transient");

        if (f.zeroCrossingRate >= 0.15f) tags.push_back("Noisy");
        else if (f.zeroCrossingRate > 0.0f && f.zeroCrossingRate < 0.03f) tags.push_back("Tonal");

        // Long/Short Decay -- absolute envelope decay-time thresholds
        // calibrated against the real 620-file B-006 corpus (see
        // docs/classification/DECAY_ATTRIBUTE_TAG_V1_REPORT.md): 2.0s sits
        // between Riser's median (1.15s) and Bass Loop's (1.96s), well
        // below Atmosphere's (6.05s); 0.12s sits inside the tight cluster
        // of percussive-class medians (Snare/Hi-Hat/Clap ~0.09-0.11s), well
        // below Bass One-Shot's (0.50s). A deliberately wide untagged middle
        // band, same pattern as Bright/Dark and Noisy/Tonal above. A
        // "Sustained"/"Percussive" pair using decayTimeSeconds/duration was
        // investigated and rejected -- that ratio was found to be dominated
        // by where the envelope peak falls within the file rather than true
        // sustain character (Riser had the LOWEST median ratio and Bass
        // One-Shot the HIGHEST, backwards from intuition), so it doesn't
        // ship as a producer-facing attribute.
        if (f.decayTimeSeconds >= 2.0f) tags.push_back("Long Decay");
        else if (f.decayTimeSeconds > 0.0f && f.decayTimeSeconds < 0.12f) tags.push_back("Short Decay");

        // Wide/Mono -- real corpus evidence (see docs/classification/
        // WIDE_MONO_ATTRIBUTE_TAG_V1_REPORT.md) found L/R correlation a
        // genuine separating signal matching known mixing conventions
        // (bass/kick/vocals kept mono/centered -- median correlation
        // 0.97-1.00; risers/pads/foley often stereo-widened -- median
        // 0.18-0.59). A genuinely mono source file (originalChannels == 1)
        // is unambiguously "Mono", no threshold needed. For stereo files,
        // >= 0.98 correlation is mono-compatible in practice (identical or
        // near-identical channels, whether genuinely mono-summed or actual
        // mono content stored in a stereo container); < 0.5 is a real,
        // audibly wide stereo image. Deliberately wide untagged middle band,
        // same pattern as every other attribute pair above.
        if (item.audioFeatures.originalChannels == 1) {
            tags.push_back("Mono");
        } else if (item.audioFeatures.originalChannels >= 2) {
            if (f.stereoCorrelation >= 0.98f) tags.push_back("Mono");
            else if (f.stereoCorrelation < 0.5f) tags.push_back("Wide");
        }

        // FFT sidecar: expose a conservative rhythmic-evidence tag without
        // changing the frozen acoustic head or taxonomy labels. Requiring an
        // existing loop decision plus sustained energy prevents a one-shot
        // from being called rhythmic solely because it has an onset.
        const bool loopLike = std::find(item.secondaryTags.begin(), item.secondaryTags.end(), "Loop")
            != item.secondaryTags.end();
        if (loopLike && item.durationSeconds >= 1.5f
            && f.energyDecayRatio >= 0.55f
            && f.spectralFluxPeakRate >= 1.0f
            && f.spectralFluxPeakRate <= 12.0f)
            tags.push_back("Rhythmic");
    }

    // Stable, deterministic ordering (brief section 48) -- insertion order
    // above is already deterministic given deterministic inputs; de-dup
    // defensively without reordering (subcategory/secondaryTags could in
    // principle collide with an attribute tag).
    std::vector<std::string> deduped;
    for (auto& t : tags)
        if (std::find(deduped.begin(), deduped.end(), t) == deduped.end())
            deduped.push_back(t);
    return deduped;
}

std::vector<std::string> SampleManagerEngine::getPredictedTags(const std::string& filePath)
{
    const juce::ScopedLock sl(dbLock);
    const size_t idx = findSampleIndex(filePath);
    if (idx == kSampleIndexNotFound)
        return {};
    return generatePredictedTags(samples[idx]);
}

// RECOVERY PHASE R3-F -- Map Clusters. Restored honestly (brief section 53)
// as CATEGORY CENTROIDS, not genuine spatial clustering: the mean UMAP
// position of each AbletonTaxonomy category's members. Categories with
// fewer than minGroupSize members (or no category yet) are omitted.
std::vector<SampleManagerEngine::MapClusterLabel> SampleManagerEngine::computeMapClusters(int minGroupSize)
{
    const juce::ScopedLock sl(dbLock);

    std::unordered_map<std::string, std::pair<double, double>> sums; // category -> (sumX, sumY)
    std::unordered_map<std::string, int> counts;

    for (const auto& s : samples) {
        if (s.category.empty() || !s.isProcessed) continue;
        sums[s.category].first += s.x;
        sums[s.category].second += s.y;
        counts[s.category]++;
    }

    std::vector<MapClusterLabel> clusters;
    for (const auto& [category, count] : counts) {
        if (count < minGroupSize) continue;
        MapClusterLabel label;
        label.category = category;
        label.sampleCount = count;
        label.x = static_cast<float>(sums[category].first / count);
        label.y = static_cast<float>(sums[category].second / count);
        clusters.push_back(label);
    }

    // Deterministic ordering: alphabetical by category.
    std::sort(clusters.begin(), clusters.end(), [](const MapClusterLabel& a, const MapClusterLabel& b) {
        return a.category < b.category;
    });
    return clusters;
}

void SampleManagerEngine::runUMAPInternal(bool forceFullRecompute)
{
    const juce::ScopedLock sl(dbLock);

    if (samples.empty()) return;

    if (forceFullRecompute || !umapBootstrapped) {
        // If every processed sample already carries a still-valid persisted
        // layout (loaded from the cache in tryLoadFromCache -- see
        // SampleItem::umapPositionFromCache), the expensive UMAP epoch
        // computation is entirely redundant: the coordinates it would
        // produce are already sitting on the samples. This is the common
        // case for a relaunch against an unchanged library, and for a
        // prune-forced rebuild (which only needs the HNSW index rebuilt,
        // not the projection recomputed). Skip straight to the cheap HNSW
        // rebuild in that case.
        bool anyProcessed = false;
        bool allHaveCachedLayout = true;
        for (const auto& s : samples) {
            // Only samples with a real embedding ever get projected at all --
            // a failed/retryable/permanent embedding attempt (isProcessed
            // true, embedding cleared -- see docs/ONNX_FAILURE_HANDLING.md)
            // will never have a cached layout to restore, and shouldn't force
            // a full recompute for every other (successfully embedded) sample.
            if (!hasUsableEmbedding(s)) continue;
            anyProcessed = true;
            if (!s.umapPositionFromCache) { allHaveCachedLayout = false; break; }
        }

        if (anyProcessed && allHaveCachedLayout) {
            AppLogger::getInstance().logInfo(
                "UMAP layout fully restored from cache -- skipping recompute.");
        } else {
            runFullUMAP();
            persistUmapPositions(0);
        }

        rebuildHnswIndexFull();
        umapBootstrapped = true;
        umapProjectedCount = samples.size();
        // Every existing point's position may have just changed — bump the
        // version so pollers do a full resync rather than trusting whatever
        // (possibly stale, e.g. default (0,0)) positions the FIFO fast path
        // already delivered for samples added since the last projection.
        samplesVersion.fetch_add(1, std::memory_order_relaxed);
        return;
    }

    if (samples.size() <= umapProjectedCount) {
        return; // nothing new since the last projection
    }

    placeNewSamplesIncrementally();
    persistUmapPositions(umapProjectedCount);
    umapProjectedCount = samples.size();
    // The samples just placed above were already pushed to the canvas FIFO (with
    // their pre-UMAP default (0,0) position) back when their embedding was
    // committed in runInferenceBatch — bump the version so the editor's full-pull
    // fallback corrects them to their real coordinates.
    samplesVersion.fetch_add(1, std::memory_order_relaxed);
}

// Definition backing the header-declared collectUmapEligibleSamples() (see
// the declaration in SampleManagerEngine.h). Deliberately at global scope,
// not inside an anonymous namespace, so the header declaration and this are
// the same entity and tests calling it from other translation units bind to
// exactly the predicate runFullUMAP() uses.
std::vector<SampleItem*> collectUmapEligibleSamples(std::vector<SampleItem>& samples)
{
    std::vector<SampleItem*> eligible;
    for (auto& s : samples) {
        if (hasUsableEmbedding(s)) eligible.push_back(&s);
    }
    return eligible;
}

// Definition backing the header-declared writeBackUmapCoordinates() (see the
// declaration in SampleManagerEngine.h). Global scope for the same reason as
// collectUmapEligibleSamples() -- tests bind to this exact entity.
bool writeBackUmapCoordinates(std::vector<SampleItem>& samples,
                              const std::vector<size_t>& snapshotIndices,
                              const std::vector<double>& embedding2d)
{
    // Re-derive the eligible set now (the caller holds dbLock, so this is a
    // consistent view of `samples`) and require an exact match with the
    // snapshot the projection was built from. A size or element mismatch means
    // a scan appended, a prune erased, or a resort reordered samples while the
    // projection ran lock-free; applying rows of embedding2d to the snapshot's
    // indices would then stamp coordinates onto the wrong items.
    const auto current = collectUmapEligibleSamples(samples);
    if (current.size() != snapshotIndices.size()) return false;
    for (size_t r = 0; r < current.size(); ++r) {
        if (static_cast<size_t>(current[r] - samples.data()) != snapshotIndices[r]) return false;
    }

    // A short/empty projection buffer would read out of bounds below; fail
    // closed rather than writing garbage.
    if (embedding2d.size() < snapshotIndices.size() * 2) return false;

    for (size_t r = 0; r < snapshotIndices.size(); ++r) {
        samples[snapshotIndices[r]].x = static_cast<float>(embedding2d[r * 2]);
        samples[snapshotIndices[r]].y = static_cast<float>(embedding2d[r * 2 + 1]);
    }
    return true;
}

bool SampleManagerEngine::runFullUMAP()
{
    // Three phases with respect to dbLock (engineering/SLO dbLock-scope):
    //   1. snapshot -- under dbLock, freeze the eligible set + embeddings;
    //   2. project   -- NO lock, the expensive umappp epochs;
    //   3. publish   -- under dbLock, guarded write-back by index.
    // The old code held dbLock across all three, freezing the message thread
    // (canvas painting, audition, find-similar) for the whole projection.
    //
    // One eligible set drives every loop: the snapshot, flatEmbeddings, and the
    // write-back all iterate it in the same order. isProcessed alone does not
    // imply a usable embedding -- a failed/retryable/permanent attempt is
    // isProcessed==true with the embedding cleared (see
    // docs/ONNX_FAILURE_HANDLING.md) -- so a mismatch between the build loop
    // and the write-back loop would read baseline data out of bounds and write
    // coordinates to the wrong items. See collectUmapEligibleSamples() and
    // writeBackUmapCoordinates().
    std::vector<size_t> snapshotIndices;
    std::vector<double> flatEmbeddings;
    int nobs = 0;
    int ndim = 0;

    // --- Phase 1: snapshot, holding dbLock -----------------------------
    {
        const juce::ScopedLock sl(dbLock);

        std::vector<SampleItem*> eligible = collectUmapEligibleSamples(samples);
        // Guard the int width before narrowing: umappp takes an int nobs, and
        // the flat matrix length below is a product whose int form overflows
        // well before this anyway. A pathological library can't reach this in
        // practice, but failing closed (skip + log) beats a negative int
        // silently wrapping into a huge size_t that throws bad_alloc on the
        // message thread.
        if (eligible.size() > static_cast<size_t>(std::numeric_limits<int>::max())) {
            AppLogger::getInstance().logError(
                "UMAP: eligible sample count exceeds INT_MAX; skipping projection");
            return true; // nothing to project; caller proceeds to persist/rebuild
        }
        nobs = static_cast<int>(eligible.size());

        if (nobs < 2) return true;

        if (nobs < kMinSamplesForUmapProjection) {
            // umappp's internal SVD step can fail outright below this size
            // (observed at nobs=2 -- see docs/SEARCH_QUALITY_AUDIT.md). Rather
            // than let that surface as a scary internal error log for a user
            // who simply has a tiny library, place samples deterministically on
            // a small circle -- distinct positions, no false adjacency implied,
            // and callers (canvas, "find similar") work identically either way
            // since actual similarity ranking uses embeddings/HNSW, not x/y.
            // Cheap enough to stay entirely under the lock.
            int idx = 0;
            for (auto* s : eligible) {
                float angle = 2.0f * juce::MathConstants<float>::pi * static_cast<float>(idx) / static_cast<float>(nobs);
                s->x = std::cos(angle) * 10.0f;
                s->y = std::sin(angle) * 10.0f;
                idx++;
            }
            AppLogger::getInstance().logInfo(
                "Library has fewer than " + juce::String(kMinSamplesForUmapProjection)
                + " samples -- using a simple placement instead of a full UMAP projection.");
            return true;
        }

        // Width tied to the embedding predicate above (hasSafeEmbeddingBuffer
        // guarantees exactly pannsDim elements), not a magic 512.
        ndim = AcousticClassifier::pannsDim;
        // Size arithmetic in size_t: `ndim * nobs` computed as int overflows
        // past ~4.19M eligible samples (512 * 4.19M > INT_MAX), and `nobs * 2`
        // past ~1.07B. Both are well within reach of the scale tiers this path
        // is meant to serve, so keep the products unsigned.
        const size_t nobsCount = static_cast<size_t>(nobs);
        snapshotIndices.reserve(nobsCount);
        for (auto* s : eligible) {
            snapshotIndices.push_back(static_cast<size_t>(s - samples.data()));
        }
        flatEmbeddings.assign(static_cast<size_t>(ndim) * nobsCount, 0.0);
        for (size_t r = 0; r < nobsCount; ++r) {
            const auto& embedding = eligible[r]->embedding;
            for (int d = 0; d < ndim; ++d) {
                flatEmbeddings[r * static_cast<size_t>(ndim) + static_cast<size_t>(d)] =
                    static_cast<double>(embedding[d]);
            }
        }
    } // <-- dbLock released: the projection below runs lock-free

    // --- Phase 2: projection, NO lock held -----------------------------
    // Set up VP tree builder for Euclidean distances (nearest neighbor search)
    knncolle::VptreeBuilder<int, double, double> vp_builder(
        std::make_shared<knncolle::EuclideanDistance<double, double>>()
    );

    std::vector<double> embedding2d(static_cast<size_t>(nobs) * 2, 0.0);

    umappp::Options opt;
    // Set custom neighbors count
    opt.num_neighbors = std::min(15, nobs - 1);
    // Quick completion for responsive rendering
    opt.num_epochs = 200;
    // UMAP phase: every phase (initialize, spectral, optimize) ships
    // single-threaded by default (umappp Options.hpp: num_threads* = 1).
    // num_threads_optimize is documented output-identical, so it is safe to
    // raise behind a dev-only hook; spectral is deliberately left at 1
    // because it changes coordinates. See docs/SCALE_TIER_RESULTS.md §UMAP.
    // SLO_UMAP_OPTIMIZE_THREADS: dev-only benchmark hook (0/empty = keep 1).
    opt.num_threads_optimize = 1;
    if (const char* envUmapThreads = std::getenv("SLO_UMAP_OPTIMIZE_THREADS")) {
        const long v = std::strtol(envUmapThreads, nullptr, 10);
        if (v > 1 && v <= 64) opt.num_threads_optimize = static_cast<int>(v);
    }

    try {
        auto status = umappp::initialize(
            ndim, nobs, flatEmbeddings.data(),
            vp_builder,
            2, embedding2d.data(),
            opt
        );
        status.run(embedding2d.data());
    }
    catch (const std::exception& e) {
        AppLogger::getInstance().logError(juce::String("UMAP error: ") + e.what());
        // Match the previous behaviour: no write-back, but the caller still
        // persists/rebuilds the index and records the bootstrap as done.
        return true;
    }

    // --- Phase 3: guarded write-back, holding dbLock -------------------
    {
        const juce::ScopedLock sl(dbLock);
        if (!writeBackUmapCoordinates(samples, snapshotIndices, embedding2d)) {
            AppLogger::getInstance().logInfo(
                "UMAP: sample set changed during projection -- discarding this layout and retrying on the next pass.");
            return false;
        }
    }
    return true;
}

namespace {
// FNV-1a 64-bit over raw float bytes. Not cryptographic -- doesn't need to
// be, since this is content-identity for duplicate detection within a local
// library, not a security boundary. Deterministic and fast enough to run on
// every file during a scan.
std::string computeContentHashHex(const std::vector<float>& samples)
{
    uint64_t hash = 0xcbf29ce484222325ULL;
    constexpr uint64_t prime = 0x100000001b3ULL;
    const auto* bytes = reinterpret_cast<const unsigned char*>(samples.data());
    const size_t numBytes = samples.size() * sizeof(float);
    for (size_t i = 0; i < numBytes; ++i) {
        hash ^= bytes[i];
        hash *= prime;
    }
    char buf[17];
    std::snprintf(buf, sizeof(buf), "%016llx", static_cast<unsigned long long>(hash));
    return std::string(buf);
}
}

std::vector<float> SampleManagerEngine::loadAndResampleWaveform(const std::string& filePath, double targetSampleRate, int targetNumSamples, std::string* outContentHash, float* outDurationSeconds)
{
    // JUCE's WAV reader is intentionally tolerant of a truncated data chunk.
    // Preserve the existing dr_wav validation contract before handing WAV
    // audio to the generic reader below, so corrupt RIFF files remain
    // fail-closed while non-WAV formats gain generic-reader support.
    if (juce::File(filePath).getFileExtension().toLowerCase() == ".wav") {
        drwav wav;
        if (!drwav_init_file(&wav, filePath.c_str(), nullptr))
            return {};

        const unsigned int channels = wav.channels;
        const drwav_uint64 totalFrames = wav.totalPCMFrameCount;
        if (channels == 0 || totalFrames == 0
            || totalFrames > static_cast<drwav_uint64>(std::numeric_limits<int>::max())) {
            drwav_uninit(&wav);
            return {};
        }

        std::vector<float> validationBuffer(static_cast<size_t>(totalFrames) * channels);
        const drwav_uint64 framesRead = drwav_read_pcm_frames_f32(
            &wav, totalFrames, validationBuffer.data());
        drwav_uninit(&wav);
        if (framesRead == 0)
            return {};
    }

    // Use the same JUCE format registry that controls scan admission. This
    // supports every format enabled by registerBasicFormats() while keeping
    // malformed or decoder-unavailable files fail-closed. WAV has the extra
    // validation guard above because its generic reader is more permissive.
    juce::AudioFormatManager decoder;
    decoder.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> reader(
        decoder.createReaderFor(juce::File(filePath)));
    if (reader == nullptr || reader->lengthInSamples <= 0 || reader->numChannels <= 0
        || reader->sampleRate <= 0.0) {
        return {};
    }

    const int channels = reader->numChannels;
    const double sourceSampleRate = reader->sampleRate;
    const int64_t totalFrames = reader->lengthInSamples;

    if (totalFrames > static_cast<int64_t>(std::numeric_limits<int>::max()))
        return {};

    // True original duration -- captured before any resampling/padding to
    // the fixed embedding window below, which would otherwise clip a long
    // file to 5 seconds and misreport its actual length.
    if (outDurationSeconds != nullptr && sourceSampleRate > 0.0) {
        *outDurationSeconds = static_cast<float>(static_cast<double>(totalFrames) / sourceSampleRate);
    }

    const int sourceSamplesCount = static_cast<int>(totalFrames);

    // JUCE decodes directly into planar float buffers, handling the source bit
    // depth/format conversion for WAV, AIFF, FLAC, OGG, and other registered
    // readers. Keep one mono copy for the existing DSP/resampling pipeline.
    juce::AudioBuffer<float> decoded(channels, sourceSamplesCount);
    decoded.clear();
    if (!reader->read(&decoded, 0, sourceSamplesCount, 0, true, true))
        return {};

    // Downmix to mono
    std::vector<float> monoSource;
    if (channels == 1) {
        monoSource.assign(decoded.getReadPointer(0),
                          decoded.getReadPointer(0) + sourceSamplesCount);
    } else {
        monoSource.assign(static_cast<size_t>(sourceSamplesCount), 0.0f);
        for (int i = 0; i < sourceSamplesCount; ++i) {
            float sum = 0.0f;
            for (int c = 0; c < channels; ++c) {
                sum += decoded.getSample(c, i);
            }
            monoSource[static_cast<size_t>(i)] = sum / static_cast<float>(channels);
        }
    }

    if (outContentHash != nullptr) {
        *outContentHash = computeContentHashHex(monoSource);
    }

    // Linear Interpolation Resampler
    std::vector<float> resampled;
    if (sourceSampleRate == targetSampleRate) {
        resampled = std::move(monoSource);
    } else {
        double ratio = sourceSampleRate / targetSampleRate;
        resampled.reserve(static_cast<size_t>(static_cast<double>(sourceSamplesCount) / ratio) + 1);
        double srcIndex = 0.0;
        while (srcIndex < sourceSamplesCount) {
            int idx1 = static_cast<int>(srcIndex);
            int idx2 = std::min(idx1 + 1, sourceSamplesCount - 1);
            float t = static_cast<float>(srcIndex - idx1);
            float sample = (1.0f - t) * monoSource[static_cast<size_t>(idx1)] + t * monoSource[static_cast<size_t>(idx2)];
            resampled.push_back(sample);
            srcIndex += ratio;
        }
    }

    // Pad or Truncate to targetNumSamples
    std::vector<float> output(targetNumSamples, 0.0f);
    int copyLength = std::min(static_cast<int>(resampled.size()), targetNumSamples);
    std::copy(resampled.begin(), resampled.begin() + copyLength, output.begin());

    return output;
}

std::vector<float> SampleManagerEngine::computeMelSpectrogram(const std::vector<float>& audioData, double sampleRate, int& outFrames, int& outMelBins)
{
    const int fftSize = 2048;
    const int hopSize = 512;
    outMelBins = 64;
    
    // Hann Window setup
    std::vector<float> hannWindow(fftSize);
    for (int i = 0; i < fftSize; ++i) {
        hannWindow[i] = static_cast<float>(0.5 * (1.0 - std::cos(2.0 * M_PI * i / (fftSize - 1))));
    }

    // Setup Mel Filterbank
    // Map Hz to Mel and Mel to Hz
    auto hzToMel = [](double hz) { return 2595.0 * std::log10(1.0 + hz / 700.0); };
    auto melToHz = [](double mel) { return 700.0 * (std::pow(10.0, mel / 2595.0) - 1.0); };

    double melMin = hzToMel(0.0);
    double melMax = hzToMel(sampleRate / 2.0);

    std::vector<double> melPoints(outMelBins + 2);
    std::vector<int> fftBins(outMelBins + 2);
    for (int i = 0; i < outMelBins + 2; ++i) {
        double mel = melMin + i * (melMax - melMin) / (outMelBins + 1);
        double hz = melToHz(mel);
        fftBins[i] = static_cast<int>(std::floor((fftSize + 1) * hz / sampleRate));
    }

    // Calculate Mel filterbank weights, stored *sparsely* as [start, end] + a
    // contiguous weight array per bin. Each triangular filter only covers a small
    // slice of the fftSize/2+1 = 1025-wide spectrum (typically a few dozen bins),
    // so applying it as a dense 1025-wide dot product (as before) spent the vast
    // majority of its multiply-adds multiplying by zero.
    const int numMagBins = fftSize / 2 + 1;
    std::vector<int> filterStart(outMelBins), filterEnd(outMelBins);
    std::vector<std::vector<float>> filterWeights(outMelBins);
    for (int m = 0; m < outMelBins; ++m) {
        int start = juce::jlimit(0, numMagBins - 1, fftBins[m]);
        int center = juce::jlimit(0, numMagBins - 1, fftBins[m + 1]);
        int end = juce::jlimit(0, numMagBins - 1, fftBins[m + 2]);

        filterStart[m] = start;
        filterEnd[m] = end;
        filterWeights[m].assign(static_cast<size_t>(end - start + 1), 0.0f);

        for (int k = start; k < center; ++k) {
            if (center != start) {
                filterWeights[m][static_cast<size_t>(k - start)] = static_cast<float>(k - start) / (center - start);
            }
        }
        for (int k = center; k <= end; ++k) {
            if (end != center) {
                filterWeights[m][static_cast<size_t>(k - start)] = static_cast<float>(end - k) / (end - center);
            }
        }
    }

    // Compute Spectrogram frames
    juce::dsp::FFT fft(11); // 2048 point FFT (uses Accelerate/vDSP internally on Apple platforms)
    std::vector<float> melSpectrogram;
    outFrames = 0;

    std::vector<float> fftData(static_cast<size_t>(fftSize) * 2, 0.0f);
    std::vector<float> magnitude(static_cast<size_t>(numMagBins), 0.0f);

    int numSamples = static_cast<int>(audioData.size());
    for (int offset = 0; offset + fftSize <= numSamples; offset += hopSize) {
        // Apply Hann window
        VectorMath::multiply(audioData.data() + offset, hannWindow.data(), fftData.data(), fftSize);
        // Zero the imaginary-packing tail so performRealOnlyForwardTransform always
        // sees a clean scratch buffer (vDSP_vmul above only wrote the first fftSize floats).
        std::fill(fftData.begin() + fftSize, fftData.end(), 0.0f);

        // FFT forward transform
        fft.performRealOnlyForwardTransform(fftData.data());

        // Extract magnitude spectrum
        for (int k = 0; k < numMagBins; ++k) {
            float real = fftData[static_cast<size_t>(2 * k)];
            float imag = fftData[static_cast<size_t>(2 * k + 1)];
            magnitude[static_cast<size_t>(k)] = std::sqrt(real * real + imag * imag);
        }

        // Apply Mel Filterbank — only over each bin's non-zero [start, end] range
        for (int m = 0; m < outMelBins; ++m) {
            int start = filterStart[m];
            int width = filterEnd[m] - start + 1;
            float melEnergy = VectorMath::dotProduct(magnitude.data() + start, filterWeights[m].data(), width);
            // Log amplitude scaling
            melSpectrogram.push_back(std::log(melEnergy + 1e-6f));
        }
        outFrames++;
    }

    return melSpectrogram;
}

std::string SampleManagerEngine::detectKeyFromAudio(const float* data, int numSamples, double sampleRate)
{
    if (numSamples < 2048) return "Unknown";
    
    int N = std::min(numSamples, 4096);
    int minLag = static_cast<int>(sampleRate / 1000.0); // 1000 Hz
    int maxLag = static_cast<int>(sampleRate / 50.0);   // 50 Hz
    
    float r0 = 0.0f;
    for (int i = 0; i < N; ++i)
    {
        r0 += data[i] * data[i];
    }
    
    std::vector<float> r(maxLag + 1, 0.0f);
    float maxVal = 0.0f;
    int bestLag = -1;
    
    for (int lag = minLag; lag <= maxLag; ++lag)
    {
        float sum = 0.0f;
        for (int i = 0; i < N - lag; ++i)
        {
            sum += data[i] * data[i + lag];
        }
        r[lag] = sum;
        if (sum > maxVal)
        {
            maxVal = sum;
            bestLag = lag;
        }
    }
    
    if (bestLag < 0) return "Unknown";
    
    float pitchConfidence = (r0 > 1e-9f) ? (maxVal / r0) : 0.0f;
    
    int crossings = 0;
    for (int i = 1; i < N; ++i)
    {
        if ((data[i - 1] >= 0.0f && data[i] < 0.0f) || (data[i - 1] < 0.0f && data[i] >= 0.0f))
        {
            crossings++;
        }
    }
    float localZcr = static_cast<float>(crossings) / static_cast<float>(N);
    
    // Tonal gating check: if signal has low pitch confidence or is highly noisy,
    // do not assign a key.
    if (pitchConfidence < 0.25f || localZcr > 0.15f)
    {
        return "Unknown";
    }
    
    // Use the autocorrelation pitch as a stable fallback/root prior, then
    // inspect a short multi-frame chroma summary to distinguish major from
    // minor.  A single sinusoid is intentionally treated as the prior note
    // with a Major tie-break (there is no musical mode information in one
    // isolated partial), while chords with a clear third can select Minor.
    double freq = sampleRate / bestLag;
    double noteDouble = 12.0 * std::log2(freq / 440.0) + 69.0;
    int note = static_cast<int>(std::round(noteDouble));
    if (note < 0) return "Unknown";

    const char* noteNames[] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" };
    const int autocorrPitchClass = ((note % 12) + 12) % 12;
    int pitchClass = autocorrPitchClass;
    bool isMinor = false;

    constexpr int fftSize = 4096;
    constexpr int hopSize = 2048;
    if (numSamples >= fftSize && sampleRate > 2000.0)
    {
        juce::dsp::FFT chromaFft(12); // 4096-point real FFT
        std::vector<float> fftData(static_cast<size_t>(fftSize) * 2, 0.0f);
        std::array<float, 12> chroma{};
        const int analysisSamples = std::min(numSamples,
            static_cast<int>(std::min<double>(numSamples, sampleRate * 8.0)));
        const double nyquist = sampleRate * 0.5;
        std::array<float, fftSize> window{};
        for (int i = 0; i < fftSize; ++i)
            window[static_cast<size_t>(i)] = static_cast<float>(
                0.5 * (1.0 - std::cos(2.0 * M_PI * i / (fftSize - 1))));

        for (int offset = 0; offset + fftSize <= analysisSamples; offset += hopSize)
        {
            std::fill(fftData.begin(), fftData.end(), 0.0f);
            for (int i = 0; i < fftSize; ++i)
                fftData[static_cast<size_t>(i)] = data[offset + i] * window[static_cast<size_t>(i)];
            chromaFft.performRealOnlyForwardTransform(fftData.data());

            for (int k = 1; k <= fftSize / 2; ++k)
            {
                const double binHz = static_cast<double>(k) * sampleRate / fftSize;
                if (binHz < 55.0 || binHz > std::min(2000.0, nyquist)) continue;
                // JUCE 8's FFT::performRealOnlyForwardTransform() writes the
                // standard interleaved complex bins for k = 0..N/2 (every
                // engine normalises to this layout -- see
                // juce_dsp/frequency/juce_FFT.cpp), so bin k sits at
                // fftData[2k] / fftData[2k + 1]. Bin fftSize/2 is the
                // Nyquist; it is never reached here because the gate above
                // already stops at min(2000, nyquist).
                const float real = fftData[static_cast<size_t>(2 * k)];
                const float imag = fftData[static_cast<size_t>(2 * k + 1)];
                const float magnitude = std::sqrt(real * real + imag * imag);
                if (!(magnitude > 1e-5f) || !std::isfinite(magnitude)) continue;
                const double midi = 69.0 + 12.0 * std::log2(binHz / 440.0);
                const int midiNote = static_cast<int>(std::round(midi));
                const int pc = ((midiNote % 12) + 12) % 12;
                // Mildly de-emphasise high harmonics so bright transients do
                // not overwhelm the fundamental/third relationship.
                const float weight = magnitude / static_cast<float>(std::sqrt(binHz / 110.0));
                chroma[static_cast<size_t>(pc)] += weight;
            }
        }

        float chromaTotal = 0.0f;
        for (float v : chroma) chromaTotal += v;
        if (chromaTotal > 1e-4f && std::isfinite(chromaTotal))
        {
            constexpr std::array<float, 12> majorProfile =
                { 6.35f, 2.23f, 3.48f, 2.33f, 4.38f, 4.09f, 2.52f, 5.19f, 2.39f, 3.66f, 2.29f, 2.88f };
            constexpr std::array<float, 12> minorProfile =
                { 6.33f, 2.68f, 3.52f, 5.38f, 2.60f, 3.53f, 2.54f, 4.75f, 3.98f, 2.69f, 3.34f, 3.17f };
            // Score all roots, but only move away from the autocorrelation
            // pitch when the chroma winner is clearly separated. Relative-key
            // swaps (for example C major vs E minor) are common when a chord's
            // harmonics dominate; a weak global margin therefore falls back to
            // the time-domain pitch prior and only chooses its mode.
            float bestScore = -std::numeric_limits<float>::max();
            float secondScore = -std::numeric_limits<float>::max();
            int bestRoot = autocorrPitchClass;
            bool bestMinor = false;
            for (int root = 0; root < 12; ++root)
            {
                for (int mode = 0; mode < 2; ++mode)
                {
                    const auto& profile = mode == 0 ? majorProfile : minorProfile;
                    float score = 0.0f;
                    for (int i = 0; i < 12; ++i)
                        score += (chroma[static_cast<size_t>((root + i) % 12)] / chromaTotal)
                            * profile[static_cast<size_t>(i)];
                    if (score > bestScore)
                    {
                        secondScore = bestScore;
                        bestScore = score;
                        bestRoot = root;
                        bestMinor = mode == 1;
                    }
                    else if (score > secondScore)
                        secondScore = score;
                }
            }

            if (bestScore - secondScore > 0.12f)
            {
                pitchClass = bestRoot;
                isMinor = bestMinor;
            }
            else
            {
                float majorScore = 0.0f;
                float minorScore = 0.0f;
                for (int i = 0; i < 12; ++i)
                {
                    const float value = chroma[static_cast<size_t>((autocorrPitchClass + i) % 12)] / chromaTotal;
                    majorScore += value * majorProfile[static_cast<size_t>(i)];
                    minorScore += value * minorProfile[static_cast<size_t>(i)];
                }
                if (std::abs(minorScore - majorScore) > 0.035f)
                    isMinor = minorScore > majorScore;
            }
        }
    }

    return std::string(noteNames[pitchClass]) + (isMinor ? " Minor" : " Major");
}

bool SampleManagerEngine::readAudioMetadata(const std::string& filePath, float& bpm, std::string& key, std::string& instrumentType)
{
    bpm = 0.0f;
    key = "";
    instrumentType = "Unknown";

    // Metadata travels with imported files and is therefore untrusted. Keep
    // malformed/non-finite BPM values out of the cache and apply the same
    // conservative upper bound to every admitted container format. The
    // fallback chain can still obtain BPM from the filename or audio when
    // this parser rejects a tag.
    const auto acceptBpm = [](const std::string& text, float& destination) -> bool {
        try {
            std::size_t consumed = 0;
            const float parsed = std::stof(text, &consumed);
            const bool onlyWhitespaceRemains = text.find_first_not_of(
                " \t\r\n", consumed) == std::string::npos;
            if (onlyWhitespaceRemains && std::isfinite(parsed)
                && parsed > 0.0f && parsed <= 1000.0f) {
                destination = parsed;
                return true;
            }
        }
        catch (...) {
            // Invalid metadata is untrusted; filename/audio fallback remains
            // authoritative for the missing field.
        }
        return false;
    };

    const auto extension = juce::File(filePath).getFileExtension().toLowerCase();

    // WAV uses a project-specific ID3 TXXX frame for InstrumentType, so keep
    // the existing concrete RIFF/WAV path for compatibility. Other admitted
    // formats use TagLib's format-neutral PropertyMap (BPM/KEY and an
    // explicit instrument property when the container exposes one).
    if (extension != ".wav") {
        try {
            TagLib::FileRef file(filePath.c_str(), false);
            if (file.isNull()) return false;

            const TagLib::PropertyMap properties = file.properties();
            const auto firstValue = [&properties](std::initializer_list<const char*> names) {
                for (const char* name : names) {
                    const TagLib::StringList values = properties.value(TagLib::String(name, TagLib::String::UTF8));
                    if (!values.isEmpty()) {
                        const std::string value = values.front().to8Bit(true);
                        if (!value.empty()) return value;
                    }
                }
                return std::string();
            };

            const std::string bpmText = firstValue({"BPM", "TEMPO"});
            if (!bpmText.empty()) {
                acceptBpm(bpmText, bpm);
            }

            key = firstValue({"KEY", "INITIALKEY"});
            const std::string genericInstrument = firstValue({"INSTRUMENTTYPE", "INSTRUMENT"});
            if (!genericInstrument.empty()) instrumentType = genericInstrument;

            return bpm > 0.0f || !key.empty() || instrumentType != "Unknown";
        }
        catch (...) {
            return false;
        }
    }

    try {
        TagLib::RIFF::WAV::File file(filePath.c_str());
        TagLib::ID3v2::Tag* tag = file.ID3v2Tag();
        if (!tag) {
            return false;
        }

        // 1. BPM (TBPM)
        auto bpmFrames = tag->frameList("TBPM");
        if (!bpmFrames.isEmpty()) {
            acceptBpm(bpmFrames.front()->toString().to8Bit(true), bpm);
        }

        // 2. Key (TKEY)
        auto keyFrames = tag->frameList("TKEY");
        if (!keyFrames.isEmpty()) {
            key = keyFrames.front()->toString().to8Bit(true);
        }

        // 3. Instrument Type (TXXX custom frame)
        for (auto* frame : tag->frameList("TXXX")) {
            auto* userFrame = dynamic_cast<TagLib::ID3v2::UserTextIdentificationFrame*>(frame);
            if (userFrame && userFrame->description() == "InstrumentType") {
                // fieldList()[0] is the description ("InstrumentType") and
                // [1] is the actual value set by writeWavMetadata's
                // setText() below -- fieldList().toString() joins the
                // whole list with spaces, which silently prepends the
                // description onto every read (e.g. "InstrumentType Kick"
                // instead of "Kick"). Read the value field directly.
                const auto& fields = userFrame->fieldList();
                instrumentType = (fields.size() > 1 ? fields[1] : TagLib::String()).to8Bit(true);
                if (instrumentType.empty()) instrumentType = "Unknown";
                break;
            }
        }

        return true;
    }
    catch (...) {
        return false;
    }
}

void SampleManagerEngine::writeWavMetadata(const std::string& filePath, float bpm, const std::string& key, const std::string& instrumentType)
{
    try {
        TagLib::RIFF::WAV::File file(filePath.c_str());
        TagLib::ID3v2::Tag* tag = file.ID3v2Tag(); // Always returns a valid pointer (creates if missing)
        if (!tag) return;

        // 1. Save BPM (TBPM)
        tag->removeFrames("TBPM");
        TagLib::ID3v2::TextIdentificationFrame* bpmFrame = 
            new TagLib::ID3v2::TextIdentificationFrame("TBPM", TagLib::String::Latin1);
        bpmFrame->setText(std::to_string(static_cast<int>(bpm)));
        tag->addFrame(bpmFrame);

        // 2. Save Key (TKEY)
        tag->removeFrames("TKEY");
        TagLib::ID3v2::TextIdentificationFrame* keyFrame = 
            new TagLib::ID3v2::TextIdentificationFrame("TKEY", TagLib::String::Latin1);
        keyFrame->setText(key);
        tag->addFrame(keyFrame);

        // 3. Save Instrument Type (TXXX with description="InstrumentType")
        for (auto* frame : tag->frameList("TXXX")) {
            auto* userFrame = dynamic_cast<TagLib::ID3v2::UserTextIdentificationFrame*>(frame);
            if (userFrame && userFrame->description() == "InstrumentType") {
                tag->removeFrame(userFrame);
                break;
            }
        }
        TagLib::ID3v2::UserTextIdentificationFrame* instFrame = 
            new TagLib::ID3v2::UserTextIdentificationFrame(TagLib::String::UTF8);
        instFrame->setDescription("InstrumentType");
        instFrame->setText(instrumentType);
        tag->addFrame(instFrame);

        file.save();
        AppLogger::getInstance().logInfo("Saved metadata to WAV file: " + juce::String(filePath));
    }
    catch (const std::exception& e) {
        AppLogger::getInstance().logError(juce::String("Failed to write WAV metadata: ") + e.what());
    }
}

// Wwise convention: SFX/VO/MX bus prefix based on content type. Most game-audio
// categories this engine detects (Kick, Explosion, Footstep, UI, etc.) are all
// "SFX" in Wwise terms; only vocals and sustained loop/music beds get their own bus.
juce::String getWwiseBusPrefix(const juce::String& category)
{
    juce::String c = category.toLowerCase();
    if (c.contains("vocal") || c.contains("voc")) return "VO";
    if (c.contains("loop")) return "MX";
    return "SFX";
}

// Wwise object/event names are simple identifiers — strip anything that isn't
// alphanumeric rather than trying to preserve spacing/punctuation.
juce::String sanitizeWwiseToken(const juce::String& s)
{
    juce::String result;
    for (int i = 0; i < s.length(); ++i) {
        juce::juce_wchar c = s[i];
        if (juce::CharacterFunctions::isLetterOrDigit(c)) {
            result += juce::String::charToString(c);
        }
    }
    return result.isEmpty() ? "X" : result;
}

// Derives the "object" portion of a Wwise-style name (the part after
// Bus_Category_) from the original filename: tokenizes it the same way the
// other naming styles do, then drops tokens that are just an existing take/
// variation number or that redundantly repeat the category name, and
// PascalCase-joins whatever's left.
juce::String getWwiseObjectName(const juce::String& originalName, const juce::String& category)
{
    juce::StringArray tokens;
    juce::String currentToken;

    for (int i = 0; i < originalName.length(); ++i) {
        juce::juce_wchar c = originalName[i];
        if (c == ' ' || c == '_' || c == '-') {
            if (currentToken.isNotEmpty()) { tokens.add(currentToken); currentToken = ""; }
        } else if (i > 0 && juce::CharacterFunctions::isUpperCase(c) && !juce::CharacterFunctions::isUpperCase(originalName[i - 1])) {
            if (currentToken.isNotEmpty()) tokens.add(currentToken);
            currentToken = juce::String::charToString(c);
        } else {
            currentToken += juce::String::charToString(c);
        }
    }
    if (currentToken.isNotEmpty()) tokens.add(currentToken);

    juce::String categoryLower = category.toLowerCase();
    juce::StringArray keptTokens;
    for (auto& tok : tokens) {
        juce::String t = tok.trim();
        if (t.isEmpty()) continue;
        if (t.containsOnly("0123456789")) continue;       // existing take/variation number — we assign our own
        if (t.toLowerCase() == categoryLower) continue;    // redundant with the Category_ segment
        keptTokens.add(t);
    }

    if (keptTokens.isEmpty()) return "Sound";

    juce::String result;
    for (auto& t : keptTokens) {
        result += t.substring(0, 1).toUpperCase() + t.substring(1).toLowerCase();
    }
    return sanitizeWwiseToken(result);
}

// `category` and `key` (and, for namingStyle 1, `originalName`) ultimately
// trace back to sample.instrumentType / sample.key, which readAudioMetadata()
// populates from an imported WAV file's embedded TagLib tags -- untrusted
// input from the user's perspective, since it travels with a file rather
// than being typed in-app. Without this, a crafted tag value like
// "../../../Library/LaunchAgents" would let reorganizeSamples() write files
// outside the scanned library root (path traversal). Strips path
// separators and leading dots so the result is always safe to use as a
// single folder/filename path component.
juce::String sanitizePathComponent(const juce::String& raw, const juce::String& fallback)
{
    juce::String s = raw.replaceCharacters("/\\:", "___");
    while (s.startsWith("."))
        s = s.substring(1);
    s = s.trim();
    return s.isEmpty() ? fallback : s;
}

juce::String formatKeyForSampleName(const juce::String& key, bool oneShot)
{
    juce::String clean = key.trim();
    if (!oneShot || clean.isEmpty())
        return clean.replace(" ", "");

    // Stored keys are canonicalized as "B Major" / "C# Minor".  A one-shot
    // contains one pitched event, so expose only its pitch class in the
    // producer filename.  Keep this conservative: if the value is not a
    // recognized note-plus-mode shape, return the existing compact token.
    juce::String lower = clean.toLowerCase();
    for (const auto* mode : {" major", " minor"}) {
        if (lower.endsWith(mode)) {
            juce::String note = clean.dropLastCharacters(static_cast<int>(std::strlen(mode))).trim();
            const juce::String noteLower = note.toLowerCase();
            const bool natural = noteLower.length() == 1 && noteLower[0] >= 'a' && noteLower[0] <= 'g';
            const bool sharp = noteLower.length() == 2 && noteLower[0] >= 'a' && noteLower[0] <= 'g' && noteLower[1] == '#';
            const bool flat = noteLower.length() == 2 && noteLower[0] >= 'a' && noteLower[0] <= 'g' && noteLower[1] == 'b';
            if (natural || sharp || flat)
                return note;
        }
    }
    return clean.replace(" ", "");
}

juce::String getFormattedFilename(const juce::String& originalName,
                                  const juce::String& category,
                                  const juce::String& subcategory,
                                  const juce::String& key,
                                  float bpm,
                                  int namingStyle,
                                  int wwiseVariationNumber)
{
    if (namingStyle == 1) // Original Name
        return originalName;
    if (namingStyle == 7) // Ableton Places (Category/Subcategory) -- folder does the sorting, filename stays as-is
        return originalName;

    // Tokenize originalName by splitting at spaces, underscores, hyphens, and casing changes
    juce::StringArray tokens;
    juce::String currentToken = "";
    
    for (int i = 0; i < originalName.length(); ++i)
    {
        juce::juce_wchar c = originalName[i];
        
        // Split markers
        if (c == ' ' || c == '_' || c == '-')
        {
            if (currentToken.isNotEmpty())
            {
                tokens.add(currentToken);
                currentToken = "";
            }
        }
        else if (i > 0 && juce::CharacterFunctions::isUpperCase(c) && !juce::CharacterFunctions::isUpperCase(originalName[i - 1]))
        {
            // Casing split (e.g. myKick -> my, Kick)
            if (currentToken.isNotEmpty())
            {
                tokens.add(currentToken);
            }
            currentToken = juce::String::charToString(c);
        }
        else
        {
            currentToken += juce::String::charToString(c);
        }
    }
    if (currentToken.isNotEmpty())
        tokens.add(currentToken);

    if (namingStyle == 2) // lowerCamelCase
    {
        juce::String result = "";
        for (int i = 0; i < tokens.size(); ++i)
        {
            juce::String tok = tokens[i].toLowerCase();
            if (i == 0) {
                result += tok;
            } else {
                result += tok.substring(0, 1).toUpperCase() + tok.substring(1);
            }
        }
        return result.isEmpty() ? originalName : result;
    }
    else if (namingStyle == 3) // snake_case
    {
        juce::StringArray lowerTokens;
        for (auto& tok : tokens)
            lowerTokens.add(tok.toLowerCase());
            
        juce::String result = lowerTokens.joinIntoString("_");
        return result.isEmpty() ? originalName : result;
    }
    else if (namingStyle == 4) // Prefix Category
    {
        juce::String cleanCat = category.isEmpty() ? "Other" : category;
        cleanCat = cleanCat.replace(" ", "");
        return cleanCat + "_" + originalName;
    }
    else if (namingStyle == 5) // Suffix Details
    {
        const bool isLoop = isLoopTaxonomyLabel(subcategory.toStdString());
        juce::String cleanKey = key.isEmpty() ? juce::String() : formatKeyForSampleName(key, !isLoop);
        const bool hasKey = !cleanKey.isEmpty() && !cleanKey.equalsIgnoreCase("Unknown") && !cleanKey.equalsIgnoreCase("UnknownKey");
        // A tempo suffix is meaningful only for repeatable material.  This
        // also makes the formatter safe when handed a legacy cached 120 BPM
        // value before the taxonomy normalizer has run.
        const bool hasBpm = isLoop && bpm > 0.0f && std::isfinite(bpm);
        juce::String suffix;
        if (hasBpm) suffix += juce::String(static_cast<int>(std::round(bpm))) + "BPM";
        if (hasKey) suffix += (suffix.isEmpty() ? juce::String() : "_") + cleanKey;
        return suffix.isEmpty() ? originalName : originalName + "_" + suffix;
    }
    else if (namingStyle == 6) // Wwise (Bus_Category_Object_##)
    {
        juce::String bus = getWwiseBusPrefix(category);
        juce::String cleanCat = sanitizeWwiseToken(category.isEmpty() ? "Other" : category);
        juce::String object = getWwiseObjectName(originalName, category);

        juce::String result = bus + "_" + cleanCat + "_" + object;
        if (wwiseVariationNumber > 0) {
            // Zero-padded round-robin variation suffix, matching how Wwise Random/
            // Sequence Containers expect their child sounds numbered.
            result += "_" + juce::String(wwiseVariationNumber).paddedLeft('0', 2);
        }
        return result;
    }
    else if (namingStyle == 8) // ThinkSpace (sx_category_action_##)
    {
        // Games-audio naming convention: prefix_category_[subcategory]_action_
        // [subaction]_variation, e.g. sx_ambience_cavern_bigDrop. This engine
        // has no dialogue/voiceover/music classifier anywhere -- instrumentType
        // only distinguishes SFX-flavored categories (Kick, Synth, Vocal, Loop,
        // etc.), never asset type (SFX vs Dialogue vs Voiceover vs Music).
        // Rather than fake a dx_/vo_/mx_ detector that doesn't exist, the
        // prefix is unconditionally sx_ (SFX), matching what's actually
        // knowable from the data this app has (see AbletonTaxonomy.h for the
        // same "don't claim capability you don't actually have" stance).
        juce::String cleanCat = sanitizeWwiseToken(category.isEmpty() ? "Other" : category).toLowerCase();

        // Action segment: lowerCamelCase-joined original-name tokens, same
        // join logic as namingStyle 2. The spec's optional [subcategory]/
        // [subaction/sublayer] segments have no signal to populate them from
        // in this codebase, so they're skipped entirely rather than invented.
        juce::String action = "";
        for (int i = 0; i < tokens.size(); ++i)
        {
            juce::String tok = tokens[i].toLowerCase();
            if (i == 0) {
                action += tok;
            } else {
                action += tok.substring(0, 1).toUpperCase() + tok.substring(1);
            }
        }
        if (action.isEmpty()) action = "sound";

        juce::String result = "sx_" + cleanCat + "_" + action;
        if (wwiseVariationNumber > 0) {
            // Zero-padded round-robin variation suffix, reusing the same
            // per-group numbering mechanism as the Wwise style (namingStyle 6)
            // to satisfy the spec's "_01/_02/_03" variation requirement.
            result += "_" + juce::String(wwiseVariationNumber).paddedLeft('0', 2);
        }
        return result;
    }
    else if (namingStyle == 9) // Smart Producer: [Subcategory] - [OriginalName] [- [BPM]bpm] [- [Key]]
    {
        juce::String sub = subcategory.trim();
        if (sub.isEmpty())
            sub = category.trim();
        if (sub.isEmpty() || sub.equalsIgnoreCase("Unknown") || sub.equalsIgnoreCase("Unclassified"))
            sub = "Sample";

        bool isLoop = sub.containsIgnoreCase("Loop") || category.equalsIgnoreCase("Loops");
        bool hasKey = key.isNotEmpty() && !key.equalsIgnoreCase("Unknown") && !key.equalsIgnoreCase("UnknownKey") && !key.equalsIgnoreCase("None");
        bool hasBpm = isLoop && bpm > 0.0f && std::isfinite(bpm);

        juce::String cleanKey = hasKey ? formatKeyForSampleName(key, !isLoop) : juce::String();
        juce::String bpmStr = hasBpm ? (juce::String(static_cast<int>(std::round(bpm))) + "bpm") : juce::String();

        if (isLoop)
        {
            if (hasBpm && hasKey)
                return sub + " - " + originalName + " - " + bpmStr + " - " + cleanKey;
            if (hasBpm)
                return sub + " - " + originalName + " - " + bpmStr;
            if (hasKey)
                return sub + " - " + originalName + " - " + cleanKey;
            return sub + " - " + originalName;
        }
        else if (hasKey) // Tonal One-Shot
        {
            return sub + " - " + originalName + " - " + cleanKey;
        }
        else // Non-tonal / Drums
        {
            return sub + " - " + originalName;
        }
    }

    return originalName;
}

juce::File getCommonRootDirectory(const std::vector<SampleItem>& items)
{
    if (items.empty()) return {};

    juce::String commonPath = juce::File(items.front().filePath).getParentDirectory().getFullPathName();

    for (size_t i = 1; i < items.size(); ++i)
    {
        juce::String path = juce::File(items[i].filePath).getParentDirectory().getFullPathName();
        
        int len = std::min(commonPath.length(), path.length());
        int commonLen = 0;
        for (int j = 0; j < len; ++j)
        {
            if (commonPath[j] == path[j]) {
                commonLen++;
            } else {
                break;
            }
        }
        commonPath = commonPath.substring(0, commonLen);
    }
    
    // Make sure we end on a folder boundary (e.g. if common prefix is "/Volumes/Jack/Samples/Ki", it should be "/Volumes/Jack/Samples")
    juce::File resultDir(commonPath);
    while (commonPath.isNotEmpty() && !resultDir.isDirectory())
    {
        int lastSlash = commonPath.lastIndexOfChar('/');
        if (lastSlash < 0) {
            lastSlash = commonPath.lastIndexOfChar('\\');
        }
        if (lastSlash <= 0) {
            return juce::File(juce::File(items.front().filePath).getParentDirectory());
        }
        commonPath = commonPath.substring(0, lastSlash);
        resultDir = juce::File(commonPath);
    }
    
    if (commonPath.isEmpty() || !resultDir.isDirectory())
    {
        return juce::File(items.front().filePath).getParentDirectory();
    }
    return resultDir;
}

SampleManagerEngine::BetaSortPreview SampleManagerEngine::previewBetaSort() const
{
    // PREVIEW ONLY. Reads state, touches no file, mutates nothing. This is what
    // the beta UI calls to answer "what would happen if I sorted?" BEFORE the
    // user agrees to anything -- the whole point of the beta contract is that
    // SLO shows its intent first.
    BetaSortPreview p;
    const juce::ScopedLock sl(dbLock);
    for (const auto& sample : samples) {
        if (!sample.isProcessed) continue;
        ++p.total;
        const juce::File f(sample.filePath);
        const auto d = slo::decideBeta(sample.subcategory, sample.tagConfidence,
                                       sample.filePath,
                                       f.getFileName().toStdString(),
                                       sample.tagUserOverridden,
                                       betaPolicyGate.load(std::memory_order_relaxed));
        switch (d.action) {
            case slo::BetaAction::AutoRenameEligible: ++p.autoRenameEligible; break;
            case slo::BetaAction::Suggest:            ++p.suggest;            break;
            case slo::BetaAction::NeverAct:           ++p.neverAct;           break;
            case slo::BetaAction::Review:             ++p.review;             break;
        }
    }
    return p;
}

SampleManagerEngine::SortPreviewResult SampleManagerEngine::previewSortLibrary(int namingStyle, bool copyInsteadOfMove, juce::File customTargetDir) const
{
    SortPreviewResult result;
    const juce::ScopedLock sl(dbLock);
    if (samples.empty()) return result;

    juce::File rootDir = (customTargetDir != juce::File() && customTargetDir.isDirectory())
        ? customTargetDir
        : getCommonRootDirectory(samples);
    result.rootDirectory = rootDir.getFullPathName().toStdString();

    std::map<std::string, int> wwiseGroupTotals;
    std::vector<int> wwiseVariationNumber(samples.size(), 0);

    if (namingStyle == 6 || namingStyle == 8) {
        auto wwiseGroupKeyFor = [namingStyle](const SampleItem& s) {
            juce::String category = s.instrumentType.empty() ? "Other" : juce::String(s.instrumentType);
            juce::File f(s.filePath);
            if (namingStyle == 8) {
                return getFormattedFilename(f.getFileNameWithoutExtension(), category,
                                             juce::String(s.subcategory),
                                             juce::String(s.key), s.bpm, 8, 0).toStdString();
            }
            return (getWwiseBusPrefix(category) + "_" + sanitizeWwiseToken(category) + "_"
                    + getWwiseObjectName(f.getFileNameWithoutExtension(), category)).toStdString();
        };

        for (size_t i = 0; i < samples.size(); ++i) {
            if (!samples[i].isProcessed) continue;
            wwiseGroupTotals[wwiseGroupKeyFor(samples[i])]++;
        }

        std::map<std::string, int> runningCount;
        for (size_t i = 0; i < samples.size(); ++i) {
            if (!samples[i].isProcessed) continue;
            std::string key = wwiseGroupKeyFor(samples[i]);
            if (wwiseGroupTotals[key] > 1) {
                wwiseVariationNumber[i] = ++runningCount[key];
            }
        }
    }

    std::set<juce::String> reservedDestinations;

    for (size_t i = 0; i < samples.size(); ++i) {
        const auto& sample = samples[i];
        if (!sample.isProcessed) continue;

        juce::File sourceFile(sample.filePath);
        if (!sourceFile.existsAsFile()) continue;

        result.totalCount++;

        SortPreviewItem item;
        item.sampleIndex = static_cast<int>(i);
        item.sourcePath = sample.filePath;
        item.sourceFilename = sourceFile.getFileName().toStdString();
        item.category = sample.instrumentType.empty() ? "Other" : sample.instrumentType;
        item.subcategory = sample.subcategory;
        item.key = sample.key;
        item.bpm = sample.bpm;
        item.eligible = true;
        item.policyReason = "Eligible";

        if (betaPolicyGateEnabled.load(std::memory_order_relaxed)) {
            const auto decision = slo::decideBeta(
                sample.subcategory, sample.tagConfidence,
                sample.filePath, sourceFile.getFileName().toStdString(),
                sample.tagUserOverridden,
                betaPolicyGate.load(std::memory_order_relaxed));
            if (!slo::isEligibleForSort(decision)) {
                item.eligible = false;
                item.policyReason = slo::toString(decision.action);
            }
        }

        if (item.eligible) {
            result.eligibleCount++;
        } else {
            result.skippedCount++;
        }

        juce::String category = sample.instrumentType.empty() ? "Other" : juce::String(sample.instrumentType);
        category = sanitizePathComponent(category, "Other");

        juce::File categoryDir;
        if (namingStyle == 7 || namingStyle == 9) {
            juce::String abletonCategory = sample.category.empty()
                ? (!sample.instrumentType.empty() ? sanitizePathComponent(juce::String(sample.instrumentType), "Unclassified") : "Unclassified")
                : sanitizePathComponent(juce::String(sample.category), "Unclassified");
            juce::String abletonSubcategory = sample.subcategory.empty()
                ? abletonCategory
                : sanitizePathComponent(juce::String(sample.subcategory), "Unclassified");

            categoryDir = rootDir.getChildFile(abletonCategory).getChildFile(abletonSubcategory);
            if (!isInsideDirectory(categoryDir, rootDir)) {
                categoryDir = rootDir.getChildFile("Unclassified").getChildFile("Unclassified");
            }
        } else {
            categoryDir = rootDir.getChildFile(category);
            if (!isInsideDirectory(categoryDir, rootDir)) {
                categoryDir = rootDir.getChildFile("Other");
            }
        }

        juce::String formattedBase = getFormattedFilename(sourceFile.getFileNameWithoutExtension(),
                                                          category,
                                                          sample.subcategory,
                                                          sample.key,
                                                          sample.bpm,
                                                          namingStyle,
                                                          wwiseVariationNumber[i]);
        const auto sourceExtension = sourceFile.getFileExtension();
        juce::String formattedName = sanitizePathComponent(formattedBase, "sample") + sourceExtension;
        juce::File destFile = categoryDir.getChildFile(formattedName);

        if (item.eligible) {
            juce::String destPath = destFile.getFullPathName();
            if ((destFile.existsAsFile() && destFile != sourceFile) || reservedDestinations.count(destPath) > 0) {
                item.willCollide = true;
                result.collisionCount++;
                destFile = chooseNonDestructiveDestination(destFile, sourceFile);
            }
            reservedDestinations.insert(destFile.getFullPathName());
        }

        item.destinationPath = destFile.getFullPathName().toStdString();
        item.destinationFilename = destFile.getFileName().toStdString();

        result.items.push_back(item);
    }

    return result;
}

void SampleManagerEngine::reorganizeSamplesAsync(int namingStyle, bool copyInsteadOfMove,
                                                   std::function<void(int moved, int failed, bool cancelled)> onComplete)
{
    if (sortInProgress.exchange(true, std::memory_order_relaxed)) {
        // Already running -- ignore rather than start a second overlapping pass
        // (both would be mutating samples/disk under the same dbLock, so the
        // second would just block, but starting it would reset the progress
        // counters the first pass is reporting mid-flight).
        return;
    }
    sortCancelRequested.store(false, std::memory_order_relaxed);
    sortDone.store(0, std::memory_order_relaxed);
    sortFailed.store(0, std::memory_order_relaxed);
    {
        const juce::ScopedLock sl(dbLock);
        sortTotal.store(static_cast<int>(samples.size()), std::memory_order_relaxed);
    }

    // Engine-owned std::thread, joined in ~SampleManagerEngine() -- not an
    // unmanaged juce::Thread::launch(). This function touches `this`
    // (samples/dbLock/sortDone/sortFailed/sortInProgress); an earlier,
    // structurally identical bug in initAsync() (see docs/ASYNC_STARTUP.md)
    // was a real, reproduced use-after-free from exactly this pattern --
    // fixed there, and fixed here proactively before it had a chance to be
    // found the same way (a fast destroy-during-sort).
    //
    // If a previous sortThread object is still joinable here, join it first:
    // sortInProgress being false (we didn't early-return above) means that
    // thread's work already finished, but the std::thread object itself may
    // not have been joined yet -- assigning over a still-joinable
    // std::thread calls std::terminate(), so this join is required for
    // correctness, not just tidiness.
    if (sortThread.joinable())
        sortThread.join();

    sortThread = std::thread([this, namingStyle, copyInsteadOfMove, onComplete]() {
        reorganizeSamples(namingStyle, copyInsteadOfMove);
        bool wasCancelled = sortCancelRequested.load(std::memory_order_relaxed);
        int movedCount = sortDone.load(std::memory_order_relaxed) - sortFailed.load(std::memory_order_relaxed);
        int failedCount = sortFailed.load(std::memory_order_relaxed);
        sortInProgress.store(false, std::memory_order_relaxed);

        if (onComplete) {
            juce::MessageManager::callAsync([onComplete, movedCount, failedCount, wasCancelled]() {
                onComplete(movedCount, failedCount, wasCancelled);
            });
        }
    });
}

void SampleManagerEngine::reorganizeSamples(int namingStyle, bool copyInsteadOfMove, juce::File customTargetDir)
{
    const juce::ScopedLock sl(dbLock);
    if (samples.empty()) return;

    // Use the resolved common root directory of all scanned files, or customTargetDir if provided
    juce::File rootDir = (customTargetDir != juce::File() && customTargetDir.isDirectory())
        ? customTargetDir
        : getCommonRootDirectory(samples);

    // Fail closed if the operation cannot establish a durable journal first.
    // A sort is a user-visible filesystem mutation; without an exact mapping
    // there is no safe way to explain or undo a partial run.
    const auto journalName = ".slo_sort_journal_"
        + juce::Uuid().toString().removeCharacters("{}-") + ".csv";
    const auto journalFile = rootDir.getChildFile(journalName);
    auto journalStream = std::make_unique<juce::FileOutputStream>(journalFile);
    if (!journalStream->openedOk()) {
        sortFailed.fetch_add(static_cast<int>(samples.size()), std::memory_order_relaxed);
        return;
    }
    journalStream->writeText(
        "version,operation,status,source,destination,timestamp\n",
        false, false, nullptr);
    journalStream->flush();
    lastSortJournalPath = journalFile.getFullPathName().toStdString();
    const auto journalOperation = copyInsteadOfMove ? "copy" : "move";

    // For the Wwise and ThinkSpace naming styles, group samples that share the
    // same prefix+category+object/action combination so round-robin variations
    // get sequential _01/_02/... suffixes (matching what a Wwise Random/Sequence
    // Container expects, and what the ThinkSpace spec's "_01/_02/_03 variation"
    // segment calls for) instead of colliding or keeping arbitrary original
    // numbering. Singleton groups (only one file with that name) get no suffix.
    std::map<std::string, int> wwiseGroupTotals;
    std::vector<int> wwiseVariationNumber(samples.size(), 0);

    if (namingStyle == 6 || namingStyle == 8) {
        auto wwiseGroupKeyFor = [namingStyle](const SampleItem& s) {
            juce::String category = s.instrumentType.empty() ? "Other" : juce::String(s.instrumentType);
            juce::File f(s.filePath);
            if (namingStyle == 8) {
                // Reuse getFormattedFilename itself (variation number 0 = no
                // suffix) so the group key can never drift out of sync with
                // the actual namingStyle-8 formatting logic above.
                return getFormattedFilename(f.getFileNameWithoutExtension(), category,
                                             juce::String(s.subcategory),
                                             juce::String(s.key), s.bpm, 8, 0).toStdString();
            }
            return (getWwiseBusPrefix(category) + "_" + sanitizeWwiseToken(category) + "_"
                    + getWwiseObjectName(f.getFileNameWithoutExtension(), category)).toStdString();
        };

        for (size_t i = 0; i < samples.size(); ++i) {
            if (!samples[i].isProcessed) continue;
            wwiseGroupTotals[wwiseGroupKeyFor(samples[i])]++;
        }

        std::map<std::string, int> runningCount;
        for (size_t i = 0; i < samples.size(); ++i) {
            if (!samples[i].isProcessed) continue;
            std::string key = wwiseGroupKeyFor(samples[i]);
            if (wwiseGroupTotals[key] > 1) {
                wwiseVariationNumber[i] = ++runningCount[key];
            }
        }
    }

    for (size_t i = 0; i < samples.size(); ++i)
    {
        // Checked once per file (not more granularly -- an individual
        // move/copy is already an atomic juce::File operation, so there's no
        // safe finer-grained cancellation point mid-file). Already-moved
        // files stay moved; this stops before the *next* one.
        if (sortCancelRequested.load(std::memory_order_relaxed)) break;
        sortDone.fetch_add(1, std::memory_order_relaxed);

        auto& sample = samples[i];
        if (!sample.isProcessed) continue;

        juce::File sourceFile(sample.filePath);
        if (!sourceFile.existsAsFile()) continue;

        // BETA SAFETY GATE. Sorting moves or copies a user's files based on a
        // classifier that is ~69.6% accurate on libraries it has not seen.
        // Acting on all of it would relocate roughly one file in three to the
        // wrong folder. The beta decision policy restricts the operation to the
        // historical high-confidence preview slice and permanently excludes
        // classes that cannot be made safe by any threshold -- Percussion and
        // impulse responses, which measure a room rather than being a sample.
        // Current collection-held-out audits have not promoted any automatic
        // action tier; this operation still requires the user's explicit
        // Copy/Move confirmation.
        // Skipped files are left exactly where the user put them.
        if (betaPolicyGateEnabled.load(std::memory_order_relaxed)) {
            const auto decision = slo::decideBeta(
                sample.subcategory, sample.tagConfidence,
                sample.filePath, sourceFile.getFileName().toStdString(),
                sample.tagUserOverridden,
                betaPolicyGate.load(std::memory_order_relaxed));
            if (!slo::isEligibleForSort(decision)) {
                sortSkippedByPolicy.fetch_add(1, std::memory_order_relaxed);
                continue;
            }
        }

        juce::String category = sample.instrumentType;
        if (category.isEmpty()) {
            category = "Other";
        }
        category = sanitizePathComponent(category, "Other");

        juce::File categoryDir;
        if (namingStyle == 7 || namingStyle == 9) {
            // Ableton Places & Smart Producer: folder hierarchy organized into Category/Subcategory.
            // A nested folder tree is the one Ableton-tagging mechanism that's fully reliable
            // and not reverse-engineered (see AbletonTaxonomy.h) -- Live's Places panel and
            // Browser both navigate real folders natively.
            // Uses the taxonomy fields (sample.category/subcategory), falling back to instrumentType.
            juce::String abletonCategory = sample.category.empty()
                ? (!sample.instrumentType.empty() ? sanitizePathComponent(juce::String(sample.instrumentType), "Unclassified") : "Unclassified")
                : sanitizePathComponent(juce::String(sample.category), "Unclassified");
            juce::String abletonSubcategory = sample.subcategory.empty()
                ? abletonCategory
                : sanitizePathComponent(juce::String(sample.subcategory), "Unclassified");

            categoryDir = rootDir.getChildFile(abletonCategory).getChildFile(abletonSubcategory);
            if (!isInsideDirectory(categoryDir, rootDir)) {
                categoryDir = rootDir.getChildFile("Unclassified").getChildFile("Unclassified");
            }
        } else {
            // Clean category folder name (e.g. Kick, Snare, Hi-Hat, etc.)
            categoryDir = rootDir.getChildFile(category);
            // Defense in depth, matching the destFile check below: confirm
            // sanitizePathComponent's output didn't somehow still resolve
            // outside rootDir before creating anything on disk.
            if (!isInsideDirectory(categoryDir, rootDir)) {
                categoryDir = rootDir.getChildFile("Other");
            }
        }
        categoryDir.createDirectory();

        juce::String formattedBase = getFormattedFilename(sourceFile.getFileNameWithoutExtension(),
                                                          category,
                                                          sample.subcategory,
                                                          sample.key,
                                                          sample.bpm,
                                                          namingStyle,
                                                          wwiseVariationNumber[i]);
        // sample.key (naming style 5) is the other untrusted-metadata field
        // that reaches this filename, alongside category above -- sanitize
        // the fully-assembled name rather than each contributing field
        // individually, so this stays correct even if a naming style is
        // added later that folds in another metadata field.
        // Preserve the container extension.  Renaming an AIFF/FLAC as .wav
        // changes the meaning of the path without transcoding the bytes and
        // can make downstream tools reject an otherwise valid sample.
        const auto sourceExtension = sourceFile.getFileExtension();
        juce::String formattedName = sanitizePathComponent(formattedBase, "sample")
            + sourceExtension;
        juce::File destFile = categoryDir.getChildFile(formattedName);

        // Defense in depth: even after sanitizing the inputs above, confirm
        // the resolved destination is still actually inside categoryDir
        // before touching the filesystem, rather than trusting the string
        // sanitization was exhaustive.
        if (!isInsideDirectory(destFile, categoryDir)) {
            continue;
        }

        // Never overwrite a different file.  If a collision exists, choose a
        // deterministic sibling (name_01, name_02, ...) and leave both files
        // intact.  An exhausted namespace is a normal per-file failure, not a
        // reason to delete or guess at a destination.
        destFile = chooseNonDestructiveDestination(destFile, sourceFile);
        if (destFile.getFullPathName().isEmpty()) {
            appendSortJournalRow(*journalStream, journalOperation, "FAILED",
                                 sourceFile, destFile);
            sortFailed.fetch_add(1, std::memory_order_relaxed);
            continue;
        }

        appendSortJournalRow(*journalStream, journalOperation, "PLANNED",
                             sourceFile, destFile);
        bool success = false;
        if (copyInsteadOfMove) {
            success = sourceFile.copyFileTo(destFile);
        } else {
            if (sourceFile.getFullPathName() == destFile.getFullPathName()) {
                success = true;
            } else {
                success = sourceFile.moveFileTo(destFile);
            }
        }

        if (success) {
            appendSortJournalRow(*journalStream, journalOperation, "COMMITTED",
                                 sourceFile, destFile);
            // Keep database path in sync so auditioning and dragging continue to work
            sample.filePath = destFile.getFullPathName().toStdString();
        } else {
            appendSortJournalRow(*journalStream, journalOperation, "FAILED",
                                 sourceFile, destFile);
            sortFailed.fetch_add(1, std::memory_order_relaxed);
        }
    }

    // Rewrites existing items' filePath in place (no size change, so the FIFO
    // fast path doesn't cover it) — bump the version so pollers pick up the new
    // paths (stale paths here would break play/drag-out).
    samplesVersion.fetch_add(1, std::memory_order_relaxed);

    notifyUpdateNow();
}

juce::File SampleManagerEngine::getMostRecentSortJournal() const
{
    const juce::ScopedLock sl(dbLock);
    if (!lastSortJournalPath.empty()) {
        juce::File f(lastSortJournalPath);
        if (f.existsAsFile())
            return f;
    }
    if (samples.empty())
        return {};

    juce::File rootDir = getCommonRootDirectory(samples);
    if (!rootDir.isDirectory())
        return {};

    juce::Array<juce::File> journals;
    rootDir.findChildFiles(journals, juce::File::findFiles, false, ".slo_sort_journal_*.csv");
    juce::File bestJournal;
    juce::Time bestTime(0);
    for (const auto& j : journals) {
        if (j.getFileName().endsWith(".undone"))
            continue;
        auto modTime = j.getLastModificationTime();
        if (modTime > bestTime) {
            bestTime = modTime;
            bestJournal = j;
        }
    }
    return bestJournal;
}

bool SampleManagerEngine::canUndoSort() const
{
    auto j = getMostRecentSortJournal();
    return j.existsAsFile();
}

SampleManagerEngine::UndoSortResult SampleManagerEngine::undoLastSort()
{
    const juce::ScopedLock sl(dbLock);
    UndoSortResult result;

    auto journalFile = getMostRecentSortJournal();
    if (!journalFile.existsAsFile()) {
        result.success = false;
        result.errorMessage = "No sort journal found to undo.";
        return result;
    }

    result.journalPath = journalFile.getFullPathName().toStdString();

    juce::StringArray lines;
    journalFile.readLines(lines);

    if (lines.size() <= 1) {
        result.success = false;
        result.errorMessage = "Journal file is empty.";
        return result;
    }

    struct JournalRow {
        juce::String version;
        juce::String operation;
        juce::String status;
        juce::String source;
        juce::String destination;
        juce::String timestamp;
    };
    std::vector<JournalRow> committedRows;

    for (int lineIdx = 1; lineIdx < lines.size(); ++lineIdx) {
        const auto& line = lines[lineIdx].trim();
        if (line.isEmpty()) continue;
        auto tokens = parseJournalCsvLine(line);
        if (tokens.size() >= 5) {
            if (tokens[2] == "COMMITTED") {
                committedRows.push_back({ tokens[0], tokens[1], tokens[2], tokens[3], tokens[4], tokens.size() > 5 ? tokens[5] : "" });
            }
        }
    }

    if (committedRows.empty()) {
        result.success = false;
        result.errorMessage = "No committed actions found in journal.";
        return result;
    }

    std::set<juce::String> affectedDirs;

    for (auto it = committedRows.rbegin(); it != committedRows.rend(); ++it) {
        const auto& row = *it;
        juce::File sourceFile(row.source);
        juce::File destFile(row.destination);

        if (row.operation == "move") {
            if (destFile.existsAsFile()) {
                affectedDirs.insert(destFile.getParentDirectory().getFullPathName());
                sourceFile.getParentDirectory().createDirectory();
                if (destFile.moveFileTo(sourceFile)) {
                    result.revertedCount++;
                    for (auto& s : samples) {
                        if (s.filePath == destFile.getFullPathName().toStdString()) {
                            s.filePath = sourceFile.getFullPathName().toStdString();
                            break;
                        }
                    }
                } else {
                    result.failedCount++;
                }
            } else if (sourceFile.existsAsFile()) {
                result.revertedCount++;
                for (auto& s : samples) {
                    if (s.filePath == destFile.getFullPathName().toStdString()) {
                        s.filePath = sourceFile.getFullPathName().toStdString();
                        break;
                    }
                }
            } else {
                result.failedCount++;
            }
        } else if (row.operation == "copy") {
            if (destFile.existsAsFile()) {
                affectedDirs.insert(destFile.getParentDirectory().getFullPathName());
                if (destFile.deleteFile()) {
                    result.revertedCount++;
                } else {
                    result.failedCount++;
                }
            } else {
                result.revertedCount++;
            }
            for (auto& s : samples) {
                if (s.filePath == destFile.getFullPathName().toStdString()) {
                    s.filePath = sourceFile.getFullPathName().toStdString();
                    break;
                }
            }
        }
    }

    juce::File rootDir = getCommonRootDirectory(samples);
    for (const auto& dirPath : affectedDirs) {
        juce::File dir(dirPath);
        if (dir.isDirectory() && dir != rootDir && isInsideDirectory(dir, rootDir)) {
            if (dir.getNumberOfChildFiles(juce::File::findFilesAndDirectories) == 0) {
                dir.deleteFile();
                juce::File parent = dir.getParentDirectory();
                if (parent != rootDir && isInsideDirectory(parent, rootDir) && parent.getNumberOfChildFiles(juce::File::findFilesAndDirectories) == 0) {
                    parent.deleteFile();
                }
            }
        }
    }

    juce::File undoneJournal(journalFile.getFullPathName() + ".undone");
    journalFile.moveFileTo(undoneJournal);
    lastSortJournalPath.clear();

    samplesVersion.fetch_add(1, std::memory_order_relaxed);
    notifyUpdateNow();

    result.success = (result.failedCount == 0);
    return result;
}

void SampleManagerEngine::undoLastSortAsync(std::function<void(UndoSortResult)> onComplete)
{
    if (sortInProgress.exchange(true, std::memory_order_relaxed)) {
        if (onComplete) {
            UndoSortResult res;
            res.success = false;
            res.errorMessage = "Another sort or undo operation is currently in progress.";
            juce::MessageManager::callAsync([onComplete, res]() { onComplete(res); });
        }
        return;
    }

    if (sortThread.joinable())
        sortThread.join();

    sortThread = std::thread([this, onComplete]() {
        auto res = undoLastSort();
        sortInProgress.store(false, std::memory_order_relaxed);
        if (onComplete) {
            juce::MessageManager::callAsync([onComplete, res]() { onComplete(res); });
        }
    });
}
