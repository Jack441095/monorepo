#include <iostream>
#include <cmath>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Verifies embedding quality through the REAL production pipeline (dr_wav
// decode -> the engine's own linear-interpolation resampler -> ONNX
// inference), not a from-scratch Python check -- the resampler in
// loadAndResampleWaveform is simple linear interpolation, not a
// high-quality resampler, so this confirms that path doesn't degrade
// feature quality enough to break the semantic structure verified
// separately in Python (see model_export/export_cnn10.py's own checks).
//
// Fixtures (Source/../model_export/real_*.wav) are 44.1kHz synthesized
// sounds -- deliberately NOT the model's native 32kHz, so the engine's own
// resample path is genuinely exercised, not bypassed.

namespace {
float cosineSim(const std::vector<float>& a, const std::vector<float>& b) {
    float dot = 0.0f, normA = 0.0f, normB = 0.0f;
    for (size_t i = 0; i < a.size(); ++i) {
        dot += a[i] * b[i];
        normA += a[i] * a[i];
        normB += b[i] * b[i];
    }
    return dot / (std::sqrt(normA) * std::sqrt(normB));
}
}

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    if (!fixtureDir.getChildFile("real_kick_a.wav").existsAsFile()) {
        std::cerr << "FAIL: test fixtures not found in " << fixtureDir.getFullPathName() << std::endl;
        return 1;
    }

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    engine.addPathToQueue(fixtureDir.getChildFile("real_kick_a.wav").getFullPathName().toStdString());
    engine.addPathToQueue(fixtureDir.getChildFile("real_kick_b.wav").getFullPathName().toStdString());
    engine.addPathToQueue(fixtureDir.getChildFile("real_sustained_noise.wav").getFullPathName().toStdString());

    int waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    auto samples = engine.getSamples();
    if (samples.size() != 3) {
        std::cerr << "FAIL: expected 3 samples, got " << samples.size() << std::endl;
        return 1;
    }

    const SampleItem* kickA = nullptr;
    const SampleItem* kickB = nullptr;
    const SampleItem* noise = nullptr;
    for (const auto& s : samples) {
        if (s.name == "real_kick_a") kickA = &s;
        else if (s.name == "real_kick_b") kickB = &s;
        else if (s.name == "real_sustained_noise") noise = &s;
    }
    if (!kickA || !kickB || !noise) {
        std::cerr << "FAIL: could not find all 3 expected samples by name" << std::endl;
        return 1;
    }
    if (kickA->embedding.size() != 512 || kickB->embedding.size() != 512 || noise->embedding.size() != 512) {
        std::cerr << "FAIL: expected 512D embeddings, got kickA=" << kickA->embedding.size()
                  << " (status=" << static_cast<int>(kickA->embeddingStatus) << "), kickB=" << kickB->embedding.size()
                  << " (status=" << static_cast<int>(kickB->embeddingStatus) << "), noise=" << noise->embedding.size()
                  << " (status=" << static_cast<int>(noise->embeddingStatus) << ")" << std::endl;
        return 1;
    }

    float kickToKick = cosineSim(kickA->embedding, kickB->embedding);
    float kickToNoiseA = cosineSim(kickA->embedding, noise->embedding);
    float kickToNoiseB = cosineSim(kickB->embedding, noise->embedding);

    std::cout << "kick_a <-> kick_b similarity:        " << kickToKick << std::endl;
    std::cout << "kick_a <-> sustained_noise similarity: " << kickToNoiseA << std::endl;
    std::cout << "kick_b <-> sustained_noise similarity: " << kickToNoiseB << std::endl;

    if (!(kickToKick > kickToNoiseA && kickToKick > kickToNoiseB)) {
        std::cerr << "FAIL: two kicks should be more similar to each other than either is to "
                     "sustained noise -- the real production pipeline (including its own "
                     "resampler) is not producing acoustically meaningful embeddings."
                  << std::endl;
        return 1;
    }

    std::cout << "SUCCESS: the real production pipeline (dr_wav decode -> engine's own "
                 "resampler -> ONNX inference) produces acoustically meaningful embeddings -- "
                 "two kicks cluster together and are clearly separated from sustained noise."
              << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
