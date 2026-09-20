#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerRefTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickFixture = fixtureDir.getChildFile("test_kick.wav");
    auto uniqueFixture = fixtureDir.getChildFile("test_unique.wav");

    // We'll scan a small library of samples
    if (!kickFixture.copyFileTo(tempRoot.getChildFile("library_kick.wav")) ||
        !uniqueFixture.copyFileTo(tempRoot.getChildFile("library_unique.wav"))) {
        std::cerr << "FAIL: could not set up test library" << std::endl;
        return 1;
    }

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    // Populate library
    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    int waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    auto samplesBefore = engine.getSamples();
    if (samplesBefore.size() != 2) {
        std::cerr << "FAIL: expected 2 library samples, got " << samplesBefore.size() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    // Perform reference search using kickFixture (not in the temp library folder)
    auto results = engine.findSimilarToReference(kickFixture.getFullPathName().toStdString(), 5);
    if (results.empty()) {
        std::cerr << "FAIL: expected similar reference results, got none" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    // Verify reference file itself was NOT added to the engine's library
    auto samplesAfter = engine.getSamples();
    if (samplesAfter.size() != 2) {
        std::cerr << "FAIL: reference sound search incorrectly added the query file permanently" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    std::cout << "SUCCESS: reference search worked without modifying library." << std::endl;

    // Test model-unavailable case
    {
        SampleManagerEngine engine2;
        // Do not call init() -- model remains uninitialized
        auto emptyResults = engine2.findSimilarToReference(kickFixture.getFullPathName().toStdString(), 5);
        if (!emptyResults.empty()) {
            std::cerr << "FAIL: findSimilarToReference should return empty when model is uninitialized" << std::endl;
            tempRoot.deleteRecursively();
            return 1;
        }
    }

    tempRoot.deleteRecursively();
    std::cout << "ALL REFERENCE SEARCH TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
