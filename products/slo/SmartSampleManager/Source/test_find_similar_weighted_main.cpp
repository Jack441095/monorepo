#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickA = fixtureDir.getChildFile("real_kick_a.wav");
    auto kickB = fixtureDir.getChildFile("real_kick_b.wav");
    auto noise = fixtureDir.getChildFile("real_sustained_noise.wav");

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerColTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    if (!kickA.copyFileTo(tempRoot.getChildFile("kick_a.wav")) ||
        !kickB.copyFileTo(tempRoot.getChildFile("kick_b.wav")) ||
        !noise.copyFileTo(tempRoot.getChildFile("noise.wav"))) {
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

    // Call findSimilarWeighted
    SampleManagerEngine::FeatureWeights weights;
    weights.spectralCentroidWeight = 1.0f; // Shift match towards similar brightness

    auto results = engine.findSimilarWeighted(tempRoot.getChildFile("kick_a.wav").getFullPathName().toStdString(), weights, 0.5f, 5);
    if (results.empty()) {
        std::cerr << "FAIL: expected weighted search results" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    std::cout << "SUCCESS: Weighted search results returned " << results.size() << " items." << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL FIND SIMILAR WEIGHTED TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
