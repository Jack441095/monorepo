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
                        .getChildFile("SmartSampleManagerNearDupTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    // Copying kickA as duplicate targets
    if (!kickA.copyFileTo(tempRoot.getChildFile("kick_original.wav")) ||
        !kickA.copyFileTo(tempRoot.getChildFile("kick_near_dup.wav")) ||
        !kickB.copyFileTo(tempRoot.getChildFile("different_kick.wav"))) {
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

    // Call findNearDuplicates (threshold = 0.98)
    auto groups = engine.findNearDuplicates(0.98f);
    if (groups.empty()) {
        std::cerr << "FAIL: expected near duplicate group, found none" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    std::cout << "SUCCESS: near duplicate group found with size: " << groups[0].items.size() << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL NEAR DUPLICATE DETECTION TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
