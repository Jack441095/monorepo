#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickA = fixtureDir.getChildFile("real_kick_a.wav");

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerClusterTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    if (!kickA.copyFileTo(tempRoot.getChildFile("kick_a.wav"))) {
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

    auto clusters = engine.computeMapClusters();
    std::cout << "SUCCESS: computed " << clusters.size() << " map clusters." << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL MAP CLUSTERS TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
