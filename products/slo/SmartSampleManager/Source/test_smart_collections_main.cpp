#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerColTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickFixture = fixtureDir.getChildFile("test_kick.wav");

    if (!kickFixture.copyFileTo(tempRoot.getChildFile("col_kick.wav"))) {
        std::cerr << "FAIL: could not copy fixture" << std::endl;
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

    // Create a smart collection: Drums
    std::string queryRules = "{\"category\": \"Drums\"}";
    engine.createSmartCollection("Dynamic Drums", queryRules);

    auto names = engine.getSmartCollectionNames();
    if (names.size() != 1 || names[0] != "Dynamic Drums") {
        std::cerr << "FAIL: dynamic collection creation failed" << std::endl;
        return 1;
    }

    auto collected = engine.getSmartCollectionSamples("Dynamic Drums");
    if (collected.size() != 1) {
        std::cerr << "FAIL: expected 1 sample in Drums collection, got " << collected.size() << std::endl;
        return 1;
    }

    // Create another collection that matches nothing (e.g. key: C Minor)
    std::string mismatchRules = "{\"key\": \"C Minor\"}";
    engine.createSmartCollection("Empty Collection", mismatchRules);
    
    auto emptyCol = engine.getSmartCollectionSamples("Empty Collection");
    if (!emptyCol.empty()) {
        std::cerr << "FAIL: expected empty collection" << std::endl;
        return 1;
    }

    // Test physical_class smart collection
    auto samples = engine.getSamples();
    std::string actualClass = samples.empty() ? "Percussive Hit" : samples[0].audioFeatures.physics.physicalClass;
    std::string physRules = "{\"physical_class\": \"" + actualClass + "\"}";
    engine.createSmartCollection("Physical Match", physRules);
    auto physCollected = engine.getSmartCollectionSamples("Physical Match");
    if (physCollected.empty()) {
        std::cerr << "FAIL: expected sample in Physical Match collection" << std::endl;
        return 1;
    }

    // Test material query using the material actually inferred for the
    // fixture. This keeps the test about filtering semantics rather than
    // assuming every synthetic fixture is wooden.
    std::string actualMaterial = samples.empty()
        ? "Unknown"
        : PhysicalAcoustics::materialToString(samples[0].audioFeatures.physics.material);
    std::string matRules = "{\"material\": \"" + actualMaterial + "\"}";
    engine.createSmartCollection("Wood Hits", matRules);
    auto matCollected = engine.getSmartCollectionSamples("Wood Hits");
    if (samples.empty() ? !matCollected.empty() : matCollected.empty()) {
        std::cerr << "FAIL: expected material-matching sample in collection" << std::endl;
        return 1;
    }

    // Test mismatching physical_class query (e.g. "Crash / Cymbal")
    std::string mismatchPhysRules = "{\"physical_class\": \"Crash / Cymbal\"}";
    engine.createSmartCollection("Cymbals", mismatchPhysRules);
    auto emptyPhys = engine.getSmartCollectionSamples("Cymbals");
    if (!emptyPhys.empty()) {
        std::cerr << "FAIL: expected empty collection for mismatching physical class" << std::endl;
        return 1;
    }

    // Clean up
    engine.deleteSmartCollection("Dynamic Drums");
    engine.deleteSmartCollection("Empty Collection");
    engine.deleteSmartCollection("Physical Match");
    engine.deleteSmartCollection("Wood Hits");
    engine.deleteSmartCollection("Cymbals");

    tempRoot.deleteRecursively();
    std::cout << "ALL SMART COLLECTION TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
