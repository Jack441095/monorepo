#include <iostream>
#include <algorithm>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

namespace {
bool hasTag(const std::vector<std::string>& tags, const std::string& tag) {
    return std::find(tags.begin(), tags.end(), tag) != tags.end();
}

// Long/Short Decay direct unit tests -- thresholds calibrated against the
// real 620-file B-006 corpus, see
// docs/classification/DECAY_ATTRIBUTE_TAG_V1_REPORT.md. Exercised directly
// against generatePredictedTags() with synthetic AudioAnalysisResult values
// (no audio decode needed) since it's a pure function of already-computed
// features.
bool testDecayAttributeTags() {
    SampleItem item;
    item.featureVersion = 1; // gate that enables the audioFeatures-derived tags

    item.audioFeatures.decayTimeSeconds = 2.5f; // >= 2.0s threshold
    if (!hasTag(generatePredictedTags(item), "Long Decay")) {
        std::cerr << "FAIL: expected 'Long Decay' tag for decayTimeSeconds=2.5s" << std::endl;
        return false;
    }

    item.audioFeatures.decayTimeSeconds = 0.05f; // < 0.12s threshold
    if (!hasTag(generatePredictedTags(item), "Short Decay")) {
        std::cerr << "FAIL: expected 'Short Decay' tag for decayTimeSeconds=0.05s" << std::endl;
        return false;
    }

    item.audioFeatures.decayTimeSeconds = 0.5f; // deliberately untagged middle band
    auto midTags = generatePredictedTags(item);
    if (hasTag(midTags, "Long Decay") || hasTag(midTags, "Short Decay")) {
        std::cerr << "FAIL: decayTimeSeconds=0.5s should not get Long or Short Decay" << std::endl;
        return false;
    }

    std::cout << "SUCCESS: Long/Short Decay attribute tags verified" << std::endl;
    return true;
}

// Wide/Mono direct unit tests -- thresholds calibrated against the real
// 620-file B-006 corpus, see
// docs/classification/WIDE_MONO_ATTRIBUTE_TAG_V1_REPORT.md.
bool testWideMonoAttributeTags() {
    SampleItem item;
    item.featureVersion = 1;

    item.audioFeatures.originalChannels = 1; // genuinely mono source file
    item.audioFeatures.stereoCorrelation = 1.0f;
    if (!hasTag(generatePredictedTags(item), "Mono")) {
        std::cerr << "FAIL: expected 'Mono' tag for a mono source file" << std::endl;
        return false;
    }

    item.audioFeatures.originalChannels = 2;
    item.audioFeatures.stereoCorrelation = 0.995f; // >= 0.98 threshold: mono-compatible stereo
    if (!hasTag(generatePredictedTags(item), "Mono")) {
        std::cerr << "FAIL: expected 'Mono' tag for stereo with correlation=0.995" << std::endl;
        return false;
    }

    item.audioFeatures.stereoCorrelation = 0.2f; // < 0.5 threshold: wide
    if (!hasTag(generatePredictedTags(item), "Wide")) {
        std::cerr << "FAIL: expected 'Wide' tag for stereo with correlation=0.2" << std::endl;
        return false;
    }

    item.audioFeatures.stereoCorrelation = 0.7f; // deliberately untagged middle band
    auto midTags = generatePredictedTags(item);
    if (hasTag(midTags, "Mono") || hasTag(midTags, "Wide")) {
        std::cerr << "FAIL: stereo correlation=0.7 should not get Mono or Wide" << std::endl;
        return false;
    }

    std::cout << "SUCCESS: Wide/Mono attribute tags verified" << std::endl;
    return true;
}

bool testFftRhythmicTag() {
    SampleItem item;
    item.featureVersion = 7;
    item.durationSeconds = 4.0f;
    item.secondaryTags = { "Loop" };
    item.audioFeatures.energyDecayRatio = 0.9f;
    item.audioFeatures.spectralFluxPeakRate = 3.0f;
    if (!hasTag(generatePredictedTags(item), "Rhythmic")) {
        std::cerr << "FAIL: sustained loop with regular FFT peaks should be Rhythmic" << std::endl;
        return false;
    }

    item.secondaryTags.clear();
    if (hasTag(generatePredictedTags(item), "Rhythmic")) {
        std::cerr << "FAIL: FFT evidence must not label a sample Rhythmic without loop evidence" << std::endl;
        return false;
    }

    std::cout << "SUCCESS: FFT Rhythmic evidence tag verified" << std::endl;
    return true;
}
} // namespace

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    if (!testDecayAttributeTags()) {
        return 1;
    }
    if (!testWideMonoAttributeTags()) {
        return 1;
    }
    if (!testFftRhythmicTag()) {
        return 1;
    }

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickFixture = fixtureDir.getChildFile("test_kick.wav");

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerTagTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    if (!kickFixture.copyFileTo(tempRoot.getChildFile("tag_kick.wav"))) {
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

    auto tags = engine.getPredictedTags(tempRoot.getChildFile("tag_kick.wav").getFullPathName().toStdString());
    if (tags.empty()) {
        std::cerr << "FAIL: expected auto-tagging labels, got none" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    std::cout << "SUCCESS: Auto-tags found: ";
    for (const auto& tag : tags) {
        std::cout << tag << " ";
    }
    std::cout << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL AUTO-TAGGING TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
