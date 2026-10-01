#include <cmath>
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
                        .getChildFile("SmartSampleManagerClusterTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    // Two kicks, not one. computeMapClusters() defaults to minGroupSize 2, so a
    // single-file library cannot form a group and the call correctly returns
    // nothing -- which is why this test never asserted anything about clusters:
    // it never had enough samples to produce one.
    if (!kickA.copyFileTo(tempRoot.getChildFile("kick_a.wav"))
        || !kickB.copyFileTo(tempRoot.getChildFile("kick_b.wav"))) {
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

    // Assert something about the clusters. Printing SUCCESS for any result at
    // all meant an empty vector, non-finite coordinates or a bogus blob all
    // passed -- and this binary is a DEPENDS of ssm_build_classification and runs
    // in ctest with the classification label, so it actually gates the map.
    auto clusters = engine.computeMapClusters();
    auto samples = engine.getSamples();
    if (clusters.empty()) {
        std::cerr << "FAIL: computeMapClusters() returned no clusters for " << samples.size()
                  << " scanned sample(s)" << std::endl;
        return 1;
    }
    if (samples.empty()) {
        std::cerr << "FAIL: no samples were scanned, so there was nothing to cluster" << std::endl;
        return 1;
    }

    int placed = 0;
    for (const auto& s : samples)
        if (s.x != 0.0f || s.y != 0.0f)
            ++placed;
    if (placed == 0) {
        std::cerr << "FAIL: none of " << samples.size()
                  << " samples received a map position" << std::endl;
        return 1;
    }

    for (const auto& c : clusters)
    {
        if (!std::isfinite(c.x) || !std::isfinite(c.y))
        {
            std::cerr << "FAIL: cluster '" << c.category << "' has a non-finite centre"
                      << std::endl;
            return 1;
        }
        if (c.sampleCount <= 0)
        {
            std::cerr << "FAIL: cluster '" << c.category << "' claims " << c.sampleCount
                      << " samples; a cluster of none groups nothing" << std::endl;
            return 1;
        }
    }

    std::cout << "SUCCESS: computed " << clusters.size() << " map clusters covering "
              << placed << " placed sample(s)." << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL MAP CLUSTERS TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
