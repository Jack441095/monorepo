#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    std::string testFile1 = "/tmp/fake_sample_1.wav";
    std::string testFile2 = "/tmp/fake_sample_2.wav";

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    // Verify initial state
    if (engine.isFavorite(testFile1) || engine.isFavorite(testFile2)) {
        std::cerr << "FAIL: initial favorite state should be false" << std::endl;
        return 1;
    }

    // Set favorite
    engine.setFavorite(testFile1, true);
    if (!engine.isFavorite(testFile1)) {
        std::cerr << "FAIL: expected testFile1 to be favorite" << std::endl;
        return 1;
    }

    auto favs = engine.getFavorites();
    if (favs.size() != 1 || favs[0] != testFile1) {
        std::cerr << "FAIL: expected exactly 1 favorite (testFile1)" << std::endl;
        return 1;
    }

    // Toggle favorite
    engine.setFavorite(testFile1, false);
    if (engine.isFavorite(testFile1)) {
        std::cerr << "FAIL: expected testFile1 to be unfavorited" << std::endl;
        return 1;
    }

    // Toggle back on
    engine.setFavorite(testFile1, true);
    engine.setFavorite(testFile2, true);
    favs = engine.getFavorites();
    if (favs.size() != 2) {
        std::cerr << "FAIL: expected 2 favorites" << std::endl;
        return 1;
    }

    // Test persistence across restart
    {
        SampleManagerEngine engine2;
        if (!engine2.init(modelPath)) {
            std::cerr << "FAIL: engine2 init failed" << std::endl;
            return 1;
        }

        if (!engine2.isFavorite(testFile1) || !engine2.isFavorite(testFile2)) {
            std::cerr << "FAIL: favorites did not persist across engine restart" << std::endl;
            return 1;
        }

        // Test cache clear survival (user data must survive cache clear)
        engine2.clearCache();

        if (!engine2.isFavorite(testFile1) || !engine2.isFavorite(testFile2)) {
            std::cerr << "FAIL: favorites did not survive clearCache()" << std::endl;
            return 1;
        }

        // Cleanup
        engine2.setFavorite(testFile1, false);
        engine2.setFavorite(testFile2, false);
    }

    std::cout << "ALL FAVORITES TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
