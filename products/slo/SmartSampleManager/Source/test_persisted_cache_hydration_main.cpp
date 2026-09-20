#include <algorithm>
#include <cmath>
#include <iostream>
#include <map>
#include <sqlite3.h>

#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

namespace {

bool waitUntilIdle(SampleManagerEngine& engine)
{
    while (engine.getEngineState() == EngineInitState::Initializing)
        juce::Thread::sleep(20);
    for (int tries = 0; engine.isBusy() && tries < 300; ++tries)
        juce::Thread::sleep(50);
    return !engine.isBusy();
}

bool waitForHydration(SampleManagerEngine& engine)
{
    for (int tries = 0; !engine.isPersistedCacheHydrationComplete() && tries < 300; ++tries)
        juce::Thread::sleep(20);
    return engine.isPersistedCacheHydrationComplete();
}

bool sameFeatures(const AudioAnalysisResult& a, const AudioAnalysisResult& b)
{
    const auto same = [](double x, double y) { return std::abs(x - y) <= 1.0e-6; };
    return same(a.peakAmplitude, b.peakAmplitude)
        && same(a.rmsAmplitude, b.rmsAmplitude)
        && same(a.crestFactor, b.crestFactor)
        && same(a.zeroCrossingRate, b.zeroCrossingRate)
        && a.onsetCount == b.onsetCount
        && same(a.spectralCentroid, b.spectralCentroid)
        && same(a.spectralRolloff, b.spectralRolloff)
        && same(a.originalSampleRate, b.originalSampleRate)
        && a.originalChannels == b.originalChannels
        && a.originalBitDepth == b.originalBitDepth
        && same(a.decayTimeSeconds, b.decayTimeSeconds)
        && same(a.lowBandEnergyRatio, b.lowBandEnergyRatio)
        && same(a.midBandEnergyRatio, b.midBandEnergyRatio)
        && same(a.highBandEnergyRatio, b.highBandEnergyRatio)
        && same(a.spectralFluxMean, b.spectralFluxMean)
        && same(a.spectralFluxStd, b.spectralFluxStd)
        && same(a.spectralFluxPeakRate, b.spectralFluxPeakRate)
        && a.physics.physicalClass == b.physics.physicalClass
        && a.physics.material == b.physics.material;
}

} // namespace

int main()
{
    ScopedIsolatedCacheDb isolatedCacheDb; // establishes fail-closed temporary DB before Engine A exists
    juce::MessageManager::getInstance();

    int failures = 0;
    const auto check = [&](bool condition, const char* message) {
        if (!condition) { std::cerr << "FAIL: " << message << std::endl; ++failures; }
        else std::cout << "  ok: " << message << std::endl;
    };

    const auto sourceDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    const auto modelPath = sourceDir.getChildFile("Models/panns_cnn10_embedding.onnx").getFullPathName().toStdString();
    const std::vector<juce::File> fixtures {
        sourceDir.getChildFile("real_kick_a.wav"),
        sourceDir.getChildFile("real_kick_b.wav"),
        sourceDir.getChildFile("real_sustained_noise.wav")
    };
    for (const auto& fixture : fixtures)
        check(fixture.existsAsFile(), "controlled audio fixture exists");
    if (failures != 0) return 1;

    std::map<std::string, SampleItem> expected;
    std::map<std::string, std::vector<std::string>> expectedSuggestedTags;
    const auto queryPath = fixtures.front().getFullPathName().toStdString();

    // Engine A is the only process allowed to scan/analyse the fixtures.
    {
        SampleManagerEngine engineA;
        check(waitForHydration(engineA), "empty isolated DB hydration completes before indexing");
        check(engineA.init(modelPath), "Engine A initializes ONNX for fixture indexing");
        while (engineA.getEngineState() == EngineInitState::Initializing)
            juce::Thread::sleep(20);
        for (const auto& fixture : fixtures)
            engineA.addPathToQueue(fixture.getFullPathName().toStdString());
        check(waitUntilIdle(engineA), "Engine A fixture scan completes");
        engineA.triggerUMAP();
        check(waitUntilIdle(engineA), "Engine A persists fixture map coordinates");

        const auto samples = engineA.getSamples();
        check(samples.size() == fixtures.size(), "Engine A persisted every fixture row");
        bool sawFftEvidence = false;
        for (const auto& sample : samples) {
            std::cout << "DEBUG sample: path=" << sample.filePath
                      << " embSize=" << sample.embedding.size()
                      << " status=" << static_cast<int>(sample.embeddingStatus) << std::endl;
            check(sample.embedding.size() == 512, "Engine A persisted a 512D embedding");
            check(sample.featureVersion == kFeatureAnalysisVersion, "Engine A persisted current audio features");
            const auto& f = sample.audioFeatures;
            sawFftEvidence = sawFftEvidence
                || (f.lowBandEnergyRatio + f.midBandEnergyRatio + f.highBandEnergyRatio > 0.5f
                    && f.spectralFluxMean >= 0.0f && f.spectralFluxStd >= 0.0f);
            expected.emplace(sample.filePath, sample);
        }
        check(sawFftEvidence, "Engine A computed FFT band/flux evidence");

        engineA.updateTaxonomyAsync(queryPath, "Drums", "Kick", { "One-Shot", "ColdHydration" });
        engineA.setFavorite(queryPath, true);
        engineA.recordPreview(queryPath);
        engineA.createSmartCollection("ColdHydrationFavorites", R"({"favorite":true})");
        const auto afterTags = engineA.getSamples();
        for (const auto& sample : afterTags) {
            expected[sample.filePath] = sample;
            expectedSuggestedTags.emplace(sample.filePath, engineA.getPredictedTags(sample.filePath));
        }
        check(!expectedSuggestedTags[queryPath].empty(),
              "Engine A exposes deterministic Suggested Tags through the public API");
        check(engineA.isFavorite(queryPath), "Engine A persisted favorite");
    }

#if JUCE_MAC
    // Simulate one indexed file living on a drive that is absent when the app
    // next launches. Keep the original cached mtime/size and change only its
    // persisted path; cold hydration must retain the catalogue row without
    // attempting raw audio I/O.
    const auto originalDisconnectedPath = fixtures.back().getFullPathName().toStdString();
    const auto disconnectedCachedPath = ("/Volumes/SLO_Disconnected_Hydration_"
        + juce::Uuid().toString() + "/Samples/real_sustained_noise.wav").toStdString();
    sqlite3* rawDb = nullptr;
    check(sqlite3_open(SampleManagerEngine::getCacheDbFile().getFullPathName().toRawUTF8(), &rawDb) == SQLITE_OK,
          "test opens isolated cache to simulate a disconnected-volume path");
    if (rawDb != nullptr) {
        sqlite3_stmt* update = nullptr;
        const bool prepared = sqlite3_prepare_v2(rawDb,
            "UPDATE sample_cache SET path = ? WHERE path = ?;", -1, &update, nullptr) == SQLITE_OK;
        check(prepared, "disconnected-volume cache-path update prepares");
        if (prepared) {
            sqlite3_bind_text(update, 1, disconnectedCachedPath.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(update, 2, originalDisconnectedPath.c_str(), -1, SQLITE_TRANSIENT);
            check(sqlite3_step(update) == SQLITE_DONE && sqlite3_changes(rawDb) == 1,
                  "exactly one cached row is moved onto the simulated disconnected volume");
        }
        sqlite3_finalize(update);
        sqlite3_close(rawDb);
    }

    auto disconnectedExpected = expected.at(originalDisconnectedPath);
    disconnectedExpected.filePath = disconnectedCachedPath;
    disconnectedExpected.name = "real_sustained_noise";
    expected.erase(originalDisconnectedPath);
    expected.emplace(disconnectedCachedPath, std::move(disconnectedExpected));
    auto suggested = expectedSuggestedTags.at(originalDisconnectedPath);
    expectedSuggestedTags.erase(originalDisconnectedPath);
    expectedSuggestedTags.emplace(disconnectedCachedPath, std::move(suggested));
#endif

    // Engine B deliberately receives no model path and no scan directories.
    // Its useful library and HNSW index must come only from the isolated cache.
    {
        SampleManagerEngine engineB;
        check(waitForHydration(engineB), "Engine B cold hydration reaches ready state");
        check(!engineB.isBusy(), "Engine B did not start a scan coordinator");
        check(engineB.getSamplesVersion() > 0,
              "Engine B publishes the hydrated model to timer-driven editors");
        const auto samples = engineB.getSamples();
        check(samples.size() == fixtures.size(), "Engine B restores the complete fixture library without scan");

        for (const auto& sample : samples) {
            const auto it = expected.find(sample.filePath);
            check(it != expected.end(), "Engine B restored an expected path");
            if (it == expected.end()) continue;
            const auto& original = it->second;
            check(sample.embedding == original.embedding && sample.embedding.size() == 512,
                  "Engine B restores embedding bit-for-bit without ONNX");
            check(sameFeatures(sample.audioFeatures, original.audioFeatures),
                  "Engine B restores cached DSP features without raw decode");
            check(sample.category == original.category && sample.subcategory == original.subcategory
                      && sample.secondaryTags == original.secondaryTags
                      && sample.tagSource == original.tagSource
                      && sample.tagUserOverridden == original.tagUserOverridden
                      && sample.winningEvidence == original.winningEvidence,
                  "Engine B restores persisted taxonomy tags without retagging");
            check(engineB.getPredictedTags(sample.filePath) == expectedSuggestedTags[sample.filePath],
                  "Engine B restores the public Suggested Tags contract without Auto-Tagging");
            check(sample.umapPositionFromCache && std::abs(sample.x - original.x) <= 1.0e-6f
                      && std::abs(sample.y - original.y) <= 1.0e-6f,
                  "Engine B restores persisted map coordinates");
        }

        check(engineB.isFavorite(queryPath), "Engine B resolves persisted favorite");
        const auto history = engineB.getRecentPreviews();
        check(!history.empty() && history.front().filePath == queryPath, "Engine B resolves persisted history");
        const auto collection = engineB.getSmartCollectionSamples("ColdHydrationFavorites");
        check(std::any_of(collection.begin(), collection.end(), [&](const auto& s) { return s.filePath == queryPath; }),
              "Engine B evaluates persisted smart collection against hydrated library");

        engineB.resetTaxonomyToAuto(queryPath);
        const auto afterReset = engineB.getSamples();
        const auto resetIt = std::find_if(afterReset.begin(), afterReset.end(),
            [&](const SampleItem& s) { return s.filePath == queryPath; });
        check(resetIt != afterReset.end(), "Engine B retains the reset sample in memory");
        if (resetIt != afterReset.end()) {
            check(resetIt->category.empty() && resetIt->subcategory.empty()
                      && resetIt->secondaryTags.empty() && !resetIt->tagUserOverridden
                      && resetIt->tagSource == "unclassified"
                      && resetIt->winningEvidence == "UNKNOWN"
                      && resetIt->taxonomyVersion == 0,
                  "Reset to Auto clears taxonomy state and provenance in memory");
        }

        const auto similar = engineB.findSimilarSamples(queryPath, 2);
        check(!similar.empty(), "Engine B cold HNSW returns Find Similar results");
        check(std::none_of(similar.begin(), similar.end(), [&](const auto& s) { return s.filePath == queryPath; }),
              "cold Find Similar excludes its query sample");
    }

    // Engine C proves the reset was persisted to both cache layers, rather
    // than only changing Engine B's in-memory copy.
    {
        SampleManagerEngine engineC;
        check(waitForHydration(engineC), "Engine C cold hydration completes after taxonomy reset");
        const auto samples = engineC.getSamples();
        const auto resetIt = std::find_if(samples.begin(), samples.end(),
            [&](const SampleItem& s) { return s.filePath == queryPath; });
        check(resetIt != samples.end(), "Engine C restores the reset sample");
        if (resetIt != samples.end()) {
            check(resetIt->category.empty() && resetIt->subcategory.empty()
                      && resetIt->secondaryTags.empty() && !resetIt->tagUserOverridden
                      && resetIt->tagSource == "unclassified"
                      && resetIt->winningEvidence == "UNKNOWN"
                      && resetIt->taxonomyVersion == 0,
                  "Engine C does not resurrect stale user taxonomy after reset");
        }
    }

    juce::MessageManager::deleteInstance();
    if (failures != 0) return 1;
    std::cout << "ALL PERSISTED CACHE HYDRATION TESTS PASSED SUCCESSFULLY!" << std::endl;
    return 0;
}
