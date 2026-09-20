#include <iostream>
#include <algorithm>
#include <cmath>
#include <sqlite3.h>
#include "SampleManagerEngine.h"
#include "AbletonTaxonomy.h"
#include "AcousticClassifier.h"
#include "TestCacheDbIsolation.h"

// Regression tests for the version-enforcement + selective-invalidation P1 fix
// (see docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md §3-4). Before this
// pass, prepareFile()'s cache-hit path only checked path+mtime+size --
// featureVersion/taxonomyVersion/embeddingModelVersion/classificationModelVersion were written but never
// read back and compared against the current kFeatureAnalysisVersion /
// AbletonTaxonomy::kTaxonomyVersion / kEmbeddingModelVersion constants, so a
// future algorithm/model bump would have silently kept serving stale cached
// analysis forever.
//
// These tests directly manipulate the isolated test cache DB's SQLite rows
// (via a short-lived raw sqlite3 connection, mirroring TestResilience's
// pattern of corrupting a file on disk between engine instances) to simulate
// "a version constant was bumped after this row was written" without
// actually changing the constants -- exactly the situation prepareFile()'s
// version checks exist to catch.

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } \
         else { std::cout << "  ok: " << msg << std::endl; } } while (0)

// Sentinel values written directly into the cache row so a later read can
// prove, unambiguously, whether that field was left untouched (sentinel
// persists) or actually recomputed (sentinel is gone, replaced by a real
// analysis result) -- rather than inferring recompute-vs-reuse indirectly
// from timing or from values that a real recompute might coincidentally
// reproduce.
static constexpr double kSentinelPeakAmplitude = -999.0;
static const char* kSentinelCategory = "__TEST_SENTINEL_CATEGORY__";

static bool execSql(sqlite3* db, const std::string& sql)
{
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errMsg);
    if (rc != SQLITE_OK) {
        std::cerr << "  SQL error (" << sql << "): " << (errMsg ? errMsg : "unknown") << std::endl;
        sqlite3_free(errMsg);
        return false;
    }
    return true;
}

// Opens a short-lived raw sqlite3 connection to the (isolated, test-only)
// cache DB and runs an UPDATE against the sample_cache row for `path`. Must
// only be called while no SampleManagerEngine currently has the DB open, to
// avoid the write racing the engine's own connection (mirrors
// TestResilience's "scoped so the engine is fully destructed before we touch
// the file on disk" pattern).
static bool patchCacheRow(const juce::File& cacheFile, const std::string& path, const std::string& setClause)
{
    sqlite3* db = nullptr;
    if (sqlite3_open(cacheFile.getFullPathName().toRawUTF8(), &db) != SQLITE_OK) {
        std::cerr << "  FAIL: could not open cache DB for direct patch" << std::endl;
        if (db) sqlite3_close(db);
        return false;
    }

    sqlite3_stmt* stmt = nullptr;
    std::string sql = "UPDATE sample_cache SET " + setClause + " WHERE path = ?;";
    bool ok = false;
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, path.c_str(), -1, SQLITE_TRANSIENT);
        ok = (sqlite3_step(stmt) == SQLITE_DONE);
        sqlite3_finalize(stmt);
    }
    sqlite3_close(db);
    return ok;
}

// Blocks until the engine's inference queue drains, mirroring every other
// Test*_main.cpp's polling pattern.
static void waitUntilIdle(SampleManagerEngine& engine)
{
    while (engine.getEngineState() == EngineInitState::Initializing)
        juce::Thread::sleep(20);
    int waitLimit = 200;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);
}

int main()
{
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto repoRoot = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickFixture = repoRoot.getChildFile("test_kick.wav");
    if (!kickFixture.existsAsFile()) {
        std::cerr << "FAIL: fixture test_kick.wav not found at " << kickFixture.getFullPathName() << std::endl;
        return 1;
    }

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerVersionEnforcementTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();
    auto testFile = tempRoot.getChildFile("kick.wav");
    if (!kickFixture.copyFileTo(testFile)) {
        std::cerr << "FAIL: could not set up test fixture copy" << std::endl;
        return 1;
    }
    const std::string testPath = testFile.getFullPathName().toStdString();
    juce::MemoryBlock originalFileData;
    CHECK(kickFixture.loadFileAsData(originalFileData),
          "test setup: original audio fixture bytes captured for malformed-file recovery check");

    std::string modelPath = repoRoot.getFullPathName().toStdString() + "/Models/panns_cnn10_embedding.onnx";
    juce::File cacheFile = SampleManagerEngine::getCacheDbFile();

    std::vector<float> originalEmbedding;
    float originalPeakAmplitude = 0.0f;

    // === 1. Fresh scan: establish a fully-current cache row =================
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine initializes with the real embedding model");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        CHECK(samples.size() == 1, "exactly one sample after the initial scan");
        if (samples.empty()) return 1;

        const auto& s = samples.front();
        CHECK(s.embeddingModelVersion == kEmbeddingModelVersion, "fresh row: embeddingModelVersion is current");
        CHECK(s.featureVersion == kFeatureAnalysisVersion, "fresh row: featureVersion is current");
        CHECK(s.taxonomyVersion == AbletonTaxonomy::kTaxonomyVersion, "fresh row: taxonomyVersion is current");
        CHECK(s.classificationModelVersion == AcousticWeights::modelVersion, "fresh row: classificationModelVersion is current");
        CHECK(!s.embedding.empty(), "fresh row: embedding is non-empty");
        CHECK(s.audioFeatures.peakAmplitude > 0.0f, "fresh row: real (non-sentinel) peak amplitude computed");

        originalEmbedding = s.embedding;
        originalPeakAmplitude = s.audioFeatures.peakAmplitude;

        engine.setFavorite(testPath, true);
        CHECK(engine.isFavorite(testPath), "favorite set on the sample ahead of the invalidation tests below");
        engine.createSmartCollection("VersionEnforcementTestCollection", R"({"category":"Drums"})");
        auto names = engine.getSmartCollectionNames();
        CHECK(std::find(names.begin(), names.end(), "VersionEnforcementTestCollection") != names.end(),
              "Smart Collection created ahead of the invalidation tests below");
    }
    // engine destroyed here -- DB connection closed, safe to patch on disk.

    // === 2. Unchanged file + fully current versions -> cache-hit fast path, ==
    //        no recompute at all (sentinel proves it) ==========================
    CHECK(patchCacheRow(cacheFile, testPath,
              "peak_amplitude = " + std::to_string(kSentinelPeakAmplitude)),
          "test setup: sentinel peak_amplitude written directly to the cache row");
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the no-op-rescan check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        CHECK(samples.size() == 1, "no-op rescan: still exactly one sample");
        if (!samples.empty()) {
            CHECK(samples.front().audioFeatures.peakAmplitude == static_cast<float>(kSentinelPeakAmplitude),
                  "unchanged file + current versions: fast-path cache hit did NOT recompute "
                  "(sentinel value survived untouched)");
        }
    }

    // === 3. Stale DSP feature version -> DSP features recomputed, embedding ==
    //        preserved bit-for-bit (selective invalidation, not a full re-embed) =
    CHECK(patchCacheRow(cacheFile, testPath, "feature_version = 0"),
          "test setup: feature_version forced stale (simulates a kFeatureAnalysisVersion bump)");
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the stale-DSP-version check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        if (!samples.empty()) {
            const auto& s = samples.front();
            CHECK(s.featureVersion == kFeatureAnalysisVersion,
                  "stale featureVersion: recomputed back to current");
            CHECK(s.audioFeatures.peakAmplitude != static_cast<float>(kSentinelPeakAmplitude)
                      && s.audioFeatures.peakAmplitude > 0.0f,
                  "stale featureVersion: sentinel gone, real DSP features recomputed");
            CHECK(s.embedding.size() == originalEmbedding.size()
                      && std::equal(s.embedding.begin(), s.embedding.end(), originalEmbedding.begin()),
                  "stale featureVersion: embedding preserved bit-for-bit (selective path reused it, "
                  "no re-embed for an unrelated version bump)");
            CHECK(s.embeddingModelVersion == kEmbeddingModelVersion,
                  "stale featureVersion: embeddingModelVersion untouched/still current");
        }
    }

    // === 3b. Stale metadata contract repairs legacy invalid values ==========
    //        A parser hardening change must also clean rows written by the
    //        previous contract; rejecting a new tag is insufficient if the
    //        old unsafe value survives selective refresh.
    CHECK(patchCacheRow(cacheFile, testPath,
              "feature_version = 0, bpm = 5001.0, instrument_type = ''"),
          "test setup: stale feature row receives legacy invalid metadata");
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the stale-metadata repair check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        if (!samples.empty()) {
            const auto& s = samples.front();
            CHECK(std::isfinite(s.bpm) && s.bpm >= 0.0f && s.bpm <= 1000.0f,
                  "stale metadata repair: BPM is finite and within the admitted range");
            CHECK(!s.instrumentType.empty(),
                  "stale metadata repair: empty instrument metadata is normalized");
            CHECK(s.embedding.size() == originalEmbedding.size()
                      && std::equal(s.embedding.begin(), s.embedding.end(), originalEmbedding.begin()),
                  "stale metadata repair: embedding remains preserved bit-for-bit");
            CHECK(s.featureVersion == kFeatureAnalysisVersion,
                  "stale metadata repair: feature version is current after refresh");
        }
    }

    // === 4. Current embedding + stale taxonomy version -> embedding AND ======
    //        DSP features preserved, only category/tags regenerated ==========
        CHECK(patchCacheRow(cacheFile, testPath,
              std::string("taxonomy_version = 0, category = '") + kSentinelCategory
                  + "', subcategory = 'stale_ml', secondary_tags = '__stale_auto__|Loop', tag_source = 'ml_v3', winning_evidence = 'DSP'"),
          "test setup: taxonomy_version forced stale + sentinel category + prior ML result written");
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the stale-taxonomy-version check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        if (!samples.empty()) {
            const auto& s = samples.front();
            CHECK(s.taxonomyVersion == AbletonTaxonomy::kTaxonomyVersion,
                  "stale taxonomyVersion: recomputed back to current");
            CHECK(s.category != kSentinelCategory,
                  "stale taxonomyVersion: sentinel category gone, real classification recomputed");
            CHECK(s.embedding.size() == originalEmbedding.size()
                      && std::equal(s.embedding.begin(), s.embedding.end(), originalEmbedding.begin()),
                  "stale taxonomyVersion: embedding still preserved bit-for-bit");
            CHECK(s.audioFeatures.peakAmplitude == originalPeakAmplitude,
                  "stale taxonomyVersion: DSP features untouched (only taxonomy was stale, "
                  "featureVersion was already current -- selective path must not re-derive "
                  "fields that weren't stale)");

            // A cache-hit embedding must still pass through the frozen
            // classifier when the stale row previously carried an ML result.
            // Derive the expected gate outcome from the same preserved
            // embedding; the old bug silently left tagSource="heuristic"
            // because cache hydration skipped this deterministic step.
            const auto expectedMl = AcousticClassifier::classify(originalEmbedding.data());
            const std::string expectedSource = expectedMl.isOod
                ? "ml_ood"
                : (expectedMl.confidence >= 0.40f ? "ml_v3" : "heuristic");
            CHECK(s.tagSource == expectedSource,
                  "stale taxonomyVersion: prior ML result is re-evaluated from the preserved embedding");
            CHECK(std::find(s.secondaryTags.begin(), s.secondaryTags.end(), "__stale_auto__")
                      == s.secondaryTags.end(),
                  "stale taxonomyVersion: derived tags from the superseded taxonomy are removed");
            if (expectedSource == "ml_v3") {
                std::string expectedCategory;
                std::string expectedSubcategory;
                CHECK(AbletonTaxonomy::mapAcousticClassToTaxonomy(
                          expectedMl.subcategory, expectedCategory, expectedSubcategory)
                          && s.category == expectedCategory
                          && s.subcategory == expectedSubcategory,
                      "stale taxonomyVersion: refreshed ML taxonomy matches the preserved embedding");
            } else if (expectedSource == "ml_ood") {
                CHECK(s.category.empty() && s.subcategory.empty(),
                      "stale taxonomyVersion: refreshed OOD result remains unknown");
                CHECK(s.secondaryTags.empty(),
                      "stale taxonomyVersion: OOD abstention clears derived secondary tags");
            }
        }
    }

    // === 4b. Current embedding + stale classifier-head version -> acoustic ==
    //        head/gate re-run, embedding preserved ============================
    CHECK(patchCacheRow(cacheFile, testPath,
              "classification_model_version = 0, category = '" + std::string(kSentinelCategory)
                  + "', subcategory = 'stale_classifier_result', tag_source = 'ml_v3'"),
          "test setup: classification_model_version forced stale + sentinel ML result written");
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the stale-classifier-version check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        if (!samples.empty()) {
            const auto& s = samples.front();
            CHECK(s.classificationModelVersion == AcousticWeights::modelVersion,
                  "stale classificationModelVersion: refreshed to current");
            CHECK(s.category != kSentinelCategory && s.subcategory != "stale_classifier_result",
                  "stale classificationModelVersion: cached ML decision was recomputed");
            CHECK(s.embedding.size() == originalEmbedding.size()
                      && std::equal(s.embedding.begin(), s.embedding.end(), originalEmbedding.begin()),
                  "stale classificationModelVersion: embedding preserved bit-for-bit");
        }
    }

    // === 5. Stale taxonomy + undecodable source fails closed =================
    //        (old derived labels must not be promoted to the current version)
    {
        static constexpr char kMalformedAudio[] = "not an audio file";
        CHECK(testFile.replaceWithData(kMalformedAudio, sizeof(kMalformedAudio) - 1),
              "test setup: source replaced with malformed audio bytes");
        const auto malformedMtime = testFile.getLastModificationTime().toMilliseconds();
        const auto malformedSize = testFile.getSize();
        CHECK(patchCacheRow(cacheFile, testPath,
                  std::string("mtime = ") + std::to_string(malformedMtime)
                      + ", size = " + std::to_string(malformedSize)
                      + ", taxonomy_version = 0, category = '" + kSentinelCategory
                      + "', subcategory = 'stale_after_decode_failure', tag_source = 'heuristic', winning_evidence = 'FILENAME'"),
              "test setup: stale taxonomy row aligned to malformed source identity");

        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the undecodable-source check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        if (!samples.empty()) {
            const auto& s = samples.front();
            CHECK(s.taxonomyVersion == 0,
                  "undecodable stale taxonomy: version remains zero so the row is retried");
            CHECK(s.category.empty() && s.subcategory.empty() && s.secondaryTags.empty(),
                  "undecodable stale taxonomy: stale derived labels are cleared");
            CHECK(s.tagSource == "unclassified",
                  "undecodable stale taxonomy: source is not presented as a completed classification");
            CHECK(s.winningEvidence == "FILENAME",
                  "undecodable stale taxonomy: legacy evidence tier remains available for diagnostics");
            CHECK(s.embedding.size() == originalEmbedding.size()
                      && std::equal(s.embedding.begin(), s.embedding.end(), originalEmbedding.begin()),
                  "undecodable stale taxonomy: valid cached embedding is preserved");
        }
    }

    // Restore the valid fixture before the remaining cache/version checks. The
    // malformed-file row deliberately remains identity-mismatched and will be
    // replaced by the normal source-change path below.
    CHECK(testFile.replaceWithData(originalFileData.getData(), originalFileData.getSize()),
          "test cleanup: original audio fixture restored");
    CHECK(patchCacheRow(cacheFile, testPath,
              std::string("mtime = ")
                  + std::to_string(testFile.getLastModificationTime().toMilliseconds())
                  + ", size = " + std::to_string(testFile.getSize())),
          "test cleanup: cache identity restored before the remaining version checks");

    // === 6. Favorites and Smart Collections survive all of the above =========
    //        derived-cache invalidation, untouched ============================
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the user-data-survives check");
        CHECK(engine.isFavorite(testPath),
              "USER DATA: favorite survived stale-DSP-version and stale-taxonomy-version invalidation");
        auto names = engine.getSmartCollectionNames();
        CHECK(std::find(names.begin(), names.end(), "VersionEnforcementTestCollection") != names.end(),
              "USER DATA: Smart Collection survived stale-DSP-version and stale-taxonomy-version invalidation");
    }

    // === 7. Stale embedding model version -> full recompute (embedding =======
    //        itself regenerated, not just metadata) ===========================
    // NULL out the embedding blob at the same time as forcing the version
    // stale, so a successful recompute is provable unambiguously (empty ->
    // non-empty), not just inferred from an unchanged version int that a
    // buggy no-op path could also produce.
    CHECK(patchCacheRow(cacheFile, testPath, "embedding_model_version = 0, embedding = NULL"),
          "test setup: embedding_model_version forced stale + embedding blob cleared "
          "(simulates a kEmbeddingModelVersion bump)");
    {
        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the stale-embedding-version check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        if (!samples.empty()) {
            const auto& s = samples.front();
            CHECK(s.embeddingModelVersion == kEmbeddingModelVersion,
                  "stale embeddingModelVersion: recomputed back to current");
            CHECK(!s.embedding.empty(),
                  "stale embeddingModelVersion: embedding was actually regenerated via full ONNX "
                  "re-inference (NOT left empty/reused from an invalid blob)");
            CHECK(s.embeddingStatus == EmbeddingStatus::Valid,
                  "stale embeddingModelVersion: fresh embedding is a real, valid one");
        }

        // Favorites/Smart Collections must survive a full re-embed too, not
        // just the cheaper selective paths tested above.
        CHECK(engine.isFavorite(testPath),
              "USER DATA: favorite survived a full stale-embedding-version recompute");
        auto names = engine.getSmartCollectionNames();
        CHECK(std::find(names.begin(), names.end(), "VersionEnforcementTestCollection") != names.end(),
              "USER DATA: Smart Collection survived a full stale-embedding-version recompute");
    }

    // === 8. Changed source file -> recompute regardless of cached versions ===
    //        (mtime/size identity check takes priority over version checks) ==
    CHECK(patchCacheRow(cacheFile, testPath, "peak_amplitude = " + std::to_string(kSentinelPeakAmplitude)),
          "test setup: sentinel peak_amplitude re-written (versions all still current at this point)");
    {
        // Touch the file's modification time so tryLoadFromCache's mtime
        // check misses regardless of the (currently all-current) version
        // fields patched above -- proving file-identity change overrides
        // version-based cache-hit logic entirely, not just supplements it.
        auto now = juce::Time::getCurrentTime() + juce::RelativeTime::seconds(2);
        testFile.setLastModificationTime(now);

        SampleManagerEngine engine;
        CHECK(engine.init(modelPath), "engine re-initializes for the changed-file check");
        engine.addPathToQueue(testPath);
        waitUntilIdle(engine);

        auto samples = engine.getSamples();
        if (!samples.empty()) {
            CHECK(samples.front().audioFeatures.peakAmplitude != static_cast<float>(kSentinelPeakAmplitude),
                  "changed file (mtime bumped): full recompute happened even though every cached "
                  "version field was current -- file-identity mismatch alone is sufficient to force "
                  "a miss");
        }
    }

    tempRoot.deleteRecursively();

    if (failures == 0) {
        std::cout << "ALL CACHE VERSION ENFORCEMENT TESTS PASSED SUCCESSFULLY!" << std::endl;
        juce::MessageManager::deleteInstance();
        return 0;
    }

    std::cerr << failures << " CACHE VERSION ENFORCEMENT TEST(S) FAILED." << std::endl;
    juce::MessageManager::deleteInstance();
    return 1;
}
