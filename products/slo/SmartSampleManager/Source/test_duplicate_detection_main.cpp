#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression test for findDuplicateGroups(): three renamed copies of the
// same audio content should be grouped together, a genuinely different file
// should not join that group, and retagging one of the duplicates (changing
// its embedded metadata, not its audio) must not break the grouping --
// content identity is based on decoded PCM, not file bytes or tags.

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerDupTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickFixture = fixtureDir.getChildFile("test_kick.wav");
    auto uniqueFixture = fixtureDir.getChildFile("test_unique.wav");

    if (!kickFixture.copyFileTo(tempRoot.getChildFile("kick_copy_a.wav")) ||
        !kickFixture.copyFileTo(tempRoot.getChildFile("kick_copy_b.wav")) ||
        !kickFixture.copyFileTo(tempRoot.getChildFile("kick_copy_c.wav")) ||
        !uniqueFixture.copyFileTo(tempRoot.getChildFile("totally_different.wav"))) {
        std::cerr << "FAIL: could not set up test fixtures" << std::endl;
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

    auto samples = engine.getSamples();
    if (samples.size() != 4) {
        std::cerr << "FAIL: expected 4 samples processed, got " << samples.size() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    auto groups = engine.findDuplicateGroups();
    if (groups.size() != 1) {
        std::cerr << "FAIL: expected exactly 1 duplicate group, got " << groups.size() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    if (groups[0].items.size() != 3) {
        std::cerr << "FAIL: expected the duplicate group to have 3 members, got "
                  << groups[0].items.size() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    for (const auto& item : groups[0].items) {
        if (juce::String(item.filePath).contains("totally_different")) {
            std::cerr << "FAIL: the genuinely different file was incorrectly grouped as a duplicate" << std::endl;
            tempRoot.deleteRecursively();
            return 1;
        }
    }
    std::cout << "SUCCESS: 3 renamed copies correctly grouped, the different file correctly excluded." << std::endl;

    // Retag one duplicate's metadata (not its audio) and confirm it's still
    // recognized as a duplicate -- content_hash must be metadata-independent.
    auto retaggedPath = groups[0].items.front().filePath;
    engine.updateMetadataAsync(retaggedPath, 140.0f, "F# Minor", "Snare");
    juce::Thread::sleep(1200);

    // Force a fresh full rescan by clearing in-memory state via a new engine
    // instance pointed at the same folder -- exercises the cache-hit path too.
    SampleManagerEngine engine2;
    if (!engine2.init(modelPath)) {
        std::cerr << "FAIL: second engine init failed" << std::endl;
        return 1;
    }
    engine2.addPathToQueue(tempRoot.getFullPathName().toStdString());
    waitLimit = 100;
    while (engine2.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    auto groups2 = engine2.findDuplicateGroups();
    if (groups2.size() != 1 || groups2[0].items.size() != 3) {
        std::cerr << "FAIL: retagging broke duplicate grouping -- got " << groups2.size()
                  << " groups, expected 1 group of 3" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    std::cout << "SUCCESS: retagging one duplicate's metadata did not break content-based grouping." << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL DUPLICATE DETECTION TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
