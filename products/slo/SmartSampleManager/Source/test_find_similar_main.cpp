#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression test for findSimilarSamples(): scans the same real_kick_a /
// real_kick_b / real_sustained_noise fixtures used by
// TestEmbeddingQuality (44.1kHz, exercising the engine's real resample
// path) and confirms querying "similar to kick_a" ranks kick_b above the
// noise texture, and never returns the query sample itself.

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickA = fixtureDir.getChildFile("real_kick_a.wav");
    if (!kickA.existsAsFile()) {
        std::cerr << "FAIL: test fixtures not found in " << fixtureDir.getFullPathName() << std::endl;
        return 1;
    }

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    engine.addPathToQueue(kickA.getFullPathName().toStdString());
    engine.addPathToQueue(fixtureDir.getChildFile("real_kick_b.wav").getFullPathName().toStdString());
    engine.addPathToQueue(fixtureDir.getChildFile("real_sustained_noise.wav").getFullPathName().toStdString());

    int waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    auto samples = engine.getSamples();
    if (samples.size() != 3) {
        std::cerr << "FAIL: expected 3 samples, got " << samples.size() << std::endl;
        return 1;
    }

    // Before any UMAP/HNSW build has happened, the index should gracefully
    // return nothing rather than crash -- but by now the scan + its
    // triggerUMAP(false) bootstrap has already run since isBusy() only
    // clears after that completes, so proceed to the real query.

    auto results = engine.findSimilarSamples(kickA.getFullPathName().toStdString(), 5);
    if (results.empty()) {
        std::cerr << "FAIL: expected at least 1 similar result, got 0" << std::endl;
        return 1;
    }
    if (results.size() != 2) {
        std::cerr << "FAIL: expected exactly 2 results (the other 2 samples), got " << results.size() << std::endl;
        return 1;
    }

    for (const auto& r : results) {
        if (r.filePath == kickA.getFullPathName().toStdString()) {
            std::cerr << "FAIL: findSimilarSamples returned the query sample itself" << std::endl;
            return 1;
        }
    }

    if (results.front().name != "real_kick_b") {
        std::cerr << "FAIL: expected real_kick_b to rank as the #1 most similar result to "
                     "real_kick_a, got '" << results.front().name << "' instead -- the "
                     "similarity ranking is not acoustically meaningful."
                  << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: real_kick_b correctly ranked as the most similar sample to real_kick_a "
                 "(over the unrelated sustained-noise texture), and the query sample itself was "
                 "correctly excluded from its own results."
              << std::endl;

    // A nonexistent/unscanned path should return no results, not crash.
    auto emptyResults = engine.findSimilarSamples("/no/such/file.wav", 5);
    if (!emptyResults.empty()) {
        std::cerr << "FAIL: expected no results for an unknown file path, got " << emptyResults.size() << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: an unknown file path correctly returns no results instead of crashing." << std::endl;

    std::cout << "ALL FIND-SIMILAR TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
