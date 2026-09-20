#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    // Clear any leftover history
    auto initialHistory = engine.getRecentPreviews(250);
    for (const auto& entry : initialHistory) {
        // No explicit delete API for history as it's auto-trimmed, but we can clear database or just run tests with unique paths
    }

    std::string pathA = "/tmp/preview_a.wav";
    std::string pathB = "/tmp/preview_b.wav";
    std::string pathC = "/tmp/preview_c.wav";

    // Record previews
    engine.recordPreview(pathA);
    juce::Thread::sleep(10);
    engine.recordPreview(pathB);
    juce::Thread::sleep(10);
    engine.recordPreview(pathC);

    auto history = engine.getRecentPreviews(10);
    if (history.size() < 3) {
        std::cerr << "FAIL: expected at least 3 history entries, got " << history.size() << std::endl;
        return 1;
    }

    // Verify ordering: most recent first (C -> B -> A)
    if (history[0].filePath != pathC || history[1].filePath != pathB || history[2].filePath != pathA) {
        std::cerr << "FAIL: history ordering is incorrect" << std::endl;
        return 1;
    }

    // Test bounded growth: record 250 items, should trim to 200
    for (int i = 0; i < 250; ++i) {
        engine.recordPreview("/tmp/trim_test_" + std::to_string(i) + ".wav");
    }

    auto fullHistory = engine.getRecentPreviews(300);
    if (fullHistory.size() > 200) {
        std::cerr << "FAIL: history exceeded 200-item bound, got " << fullHistory.size() << std::endl;
        return 1;
    }

    // Test persistence across restart
    {
        SampleManagerEngine engine2;
        if (!engine2.init(modelPath)) {
            std::cerr << "FAIL: engine2 init failed" << std::endl;
            return 1;
        }

        auto history2 = engine2.getRecentPreviews(10);
        if (history2.empty()) {
            std::cerr << "FAIL: history did not persist across restart" << std::endl;
            return 1;
        }

        // Test cache clear survival
        engine2.clearCache();
        auto history3 = engine2.getRecentPreviews(10);
        if (history3.empty()) {
            std::cerr << "FAIL: history did not survive clearCache()" << std::endl;
            return 1;
        }
    }

    std::cout << "ALL HISTORY TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
