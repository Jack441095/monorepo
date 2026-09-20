#include <JuceHeader.h>
#include "SampleManagerEngine.h"
#include <iostream>

// Fine-Grained Subcategorization V1, Phase 10: kick length secondary tag
// (Short/Long) regression test. Real engine, real fixture audio -- not a
// synthetic-only sanity check of an isolated pure function, since this
// logic lives inline in SampleManagerEngine::prepareFile() rather than a
// separately-testable classifier (unlike BassTimbreClassifier). Uses
// test_kick.wav (1.0s, real fixture, expect Long) and test_kick_short.wav
// (0.3s, synthetic, generated for this test specifically since no existing
// fixture was under the 0.7s threshold -- see
// docs/classification/BASS_TIMBRE_TAG_V1_REPORT.md's sibling report for the
// kick-length methodology).

static int failures = 0;
#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } \
         else { std::cout << "  ok: " << msg << std::endl; } } while (0)

static bool hasTag(const std::vector<std::string>& tags, const std::string& tag)
{
    for (const auto& t : tags) if (t == tag) return true;
    return false;
}

int main()
{
    std::cout << "Running kick-length regression tests..." << std::endl;

    juce::File customCacheDir = juce::File::getCurrentWorkingDirectory()
        .getChildFile("fixtures").getChildFile("cache_kick_length");
    customCacheDir.createDirectory();
    SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(customCacheDir);

    juce::MessageManager::getInstance();

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    CHECK(engine.init(modelPath), "engine initializes against the real embedding model");

    engine.clearCache();
    engine.addPathToQueue(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/test_kick.wav");
    engine.addPathToQueue(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/test_kick_short.wav");
    while (engine.isBusy()) {
        juce::Thread::sleep(50);
    }

    auto samples = engine.getSamples();
    CHECK(samples.size() == 2, "both fixture files scanned");

    for (const auto& s : samples) {
        bool isShortFile = juce::String(s.filePath).contains("test_kick_short.wav");
        if (isShortFile) {
            CHECK(s.subcategory == "Kick", "test_kick_short.wav classifies as Kick");
            CHECK(hasTag(s.secondaryTags, "Short"), "test_kick_short.wav (0.3s) tagged Short");
            CHECK(!hasTag(s.secondaryTags, "Long"), "test_kick_short.wav is not also tagged Long");
        } else if (juce::String(s.filePath).contains("test_kick.wav")) {
            CHECK(s.subcategory == "Kick", "test_kick.wav classifies as Kick");
            CHECK(hasTag(s.secondaryTags, "Long"), "test_kick.wav (1.0s) tagged Long");
            CHECK(!hasTag(s.secondaryTags, "Short"), "test_kick.wav is not also tagged Short");
        }
    }

    if (failures > 0) {
        std::cerr << failures << " check(s) FAILED" << std::endl;
        return 1;
    }
    std::cout << "ALL KICK LENGTH REGRESSION CHECKS PASSED" << std::endl;
    return 0;
}
