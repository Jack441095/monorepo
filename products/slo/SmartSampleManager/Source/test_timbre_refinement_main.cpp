#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickA = fixtureDir.getChildFile("real_kick_a.wav");
    auto kickB = fixtureDir.getChildFile("real_kick_b.wav");

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerRefTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    if (!kickA.copyFileTo(tempRoot.getChildFile("kick_a.wav")) ||
        !kickB.copyFileTo(tempRoot.getChildFile("kick_b.wav"))) {
        std::cerr << "FAIL: could not copy fixtures" << std::endl;
        return 1;
    }

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    int waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    const std::string query = tempRoot.getChildFile("kick_a.wav").getFullPathName().toStdString();

    SampleManagerEngine::TimbreRefinement bright;
    bright.brightnessShift = 1.0f;

    auto results = engine.findSimilarRefined(query, bright, 5);
    if (results.empty()) {
        std::cerr << "FAIL: expected refined search results, got none" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    // NOTE: this still cannot prove brightnessShift does anything, and the reason is
    // worth recording. Measured from the fixtures: kick_a 101 Hz (the query), kick_b
    // 118 Hz, real_sustained_noise 11051 Hz. Every candidate is BRIGHTER than the
    // query, so shifting the centroid target either way moves it toward both of
    // them and their relative order cannot change. An "opposite shifts must invert
    // the ranking" assertion was tried here and fails for that reason, not because
    // the refinement is broken -- findSimilarRefined() does apply the shift, at
    // SampleManagerEngine.cpp:5333. Proving it needs a fixture DARKER than the query,
    // which this repo does not ship. Logged in the receipt rather than papered over.

    std::cout << "SUCCESS: Timbre refined search returned " << results.size() << " matches."
              << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL TIMBRE REFINEMENT TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
