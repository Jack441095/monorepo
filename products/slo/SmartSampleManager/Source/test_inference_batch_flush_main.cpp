#include <iostream>
#include <chrono>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// TestInferenceBatchFlush -- verifies the batched-inference pipeline's TAIL
// behavior: sub-kMinBatch batches (the end of every scan) must flush and
// commit promptly instead of being dropped, and must not sit through the
// kFlushWaitMs grace period once the scan pool has drained (the grace-skip
// added in engineering/slo-perf-scale-v1 Phase 1). Exercises BOTH enqueue
// paths (fresh-decode and cache-hit) with a tail batch of one. Precise
// latency deltas are measured by BenchmarkScan, not here.

namespace {

double elapsedMsSince(std::chrono::steady_clock::time_point t0) {
    return std::chrono::duration<double, std::milli>(
               std::chrono::steady_clock::now() - t0).count();
}

bool waitForIdle(SampleManagerEngine& engine) {
    int waitLimit = 100;  // 10s ceiling, same pattern as TestEmbeddingQuality
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);
    return !engine.isBusy();
}

bool hasValidEmbedding(const std::vector<SampleItem>& samples, const char* name) {
    for (const auto& s : samples)
        if (s.name == name) return s.embedding.size() == 512;
    return false;
}

}  // namespace

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

    const std::string kickA =
        fixtureDir.getChildFile("real_kick_a.wav").getFullPathName().toStdString();

    // ---- Case 1: single fresh-decode file -> tail batch of 1 (cache-miss path)
    auto t0 = std::chrono::steady_clock::now();
    engine.addPathToQueue(kickA);
    if (!waitForIdle(engine)) {
        std::cerr << "FAIL: engine never went idle after single-file scan" << std::endl;
        return 1;
    }
    double case1Ms = elapsedMsSince(t0);
    std::cout << "case1 single-file fresh-decode tail flush: " << case1Ms << " ms" << std::endl;
    if (case1Ms > 9000.0) {
        std::cerr << "FAIL: single-file scan took " << case1Ms
                  << " ms -- tail batch appears stalled" << std::endl;
        return 1;
    }
    auto samples = engine.getSamples();
    if (samples.size() != 1 || !hasValidEmbedding(samples, "real_kick_a")) {
        std::cerr << "FAIL: expected 1 sample with a valid 512D embedding after tail flush" << std::endl;
        return 1;
    }

    // ---- Case 2: re-scan same file -> cache-hit enqueue path, tail batch of 1.
    // The path was released after case 1, so addPathToQueue re-admits it; the
    // cached row short-circuits decode but still flows through the batch
    // pipeline (embeddingAlreadyKnown).
    engine.clearCache();
    t0 = std::chrono::steady_clock::now();
    engine.addPathToQueue(kickA);
    if (!waitForIdle(engine)) {
        std::cerr << "FAIL: engine never went idle after re-scan" << std::endl;
        return 1;
    }
    double case2Ms = elapsedMsSince(t0);
    std::cout << "case2 single-file tail flush (cache cleared, re-decode): " << case2Ms << " ms" << std::endl;
    if (case2Ms > 9000.0) {
        std::cerr << "FAIL: re-scan took " << case2Ms << " ms -- tail batch appears stalled" << std::endl;
        return 1;
    }
    samples = engine.getSamples();
    if (samples.size() != 1 || !hasValidEmbedding(samples, "real_kick_a")) {
        std::cerr << "FAIL: tail flush lost or invalidated the sample" << std::endl;
        return 1;
    }

    // ---- Case 2b: re-scan again WITHOUT clearing the cache -> exercises the
    // cache-hit enqueue path (embeddingAlreadyKnown) as a tail batch of 1.
    // Must not duplicate the sample and must keep the embedding valid.
    t0 = std::chrono::steady_clock::now();
    engine.addPathToQueue(kickA);
    if (!waitForIdle(engine)) {
        std::cerr << "FAIL: engine never went idle after cache-hit re-scan" << std::endl;
        return 1;
    }
    double case2bMs = elapsedMsSince(t0);
    std::cout << "case2b single-file cache-hit tail flush: " << case2bMs << " ms" << std::endl;
    if (case2bMs > 9000.0) {
        std::cerr << "FAIL: cache-hit re-scan took " << case2bMs
                  << " ms -- tail batch appears stalled" << std::endl;
        return 1;
    }
    samples = engine.getSamples();
    if (samples.size() != 1 || !hasValidEmbedding(samples, "real_kick_a")) {
        std::cerr << "FAIL: cache-hit tail flush duplicated or invalidated the sample (size="
                  << samples.size() << ")" << std::endl;
        return 1;
    }

    // ---- Case 3: three fresh files -> sub-kMinBatch tail batch of 3, none dropped
    juce::File tmpDir = juce::File::getSpecialLocation(juce::File::tempDirectory)
                            .getChildFile("slo_batch_flush_test");
    tmpDir.deleteRecursively();
    tmpDir.createDirectory();
    const char* fixtureNames[] = {"real_kick_a.wav", "real_kick_b.wav", "real_sustained_noise.wav"};
    for (const char* n : fixtureNames) {
        auto src = fixtureDir.getChildFile(n);
        auto dst = tmpDir.getChildFile(n);
        if (!src.copyFileTo(dst)) {
            std::cerr << "FAIL: could not copy fixture " << n << " to temp dir" << std::endl;
            return 1;
        }
        engine.addPathToQueue(dst.getFullPathName().toStdString());
    }
    if (!waitForIdle(engine)) {
        std::cerr << "FAIL: engine never went idle after 3-file scan" << std::endl;
        return 1;
    }
    samples = engine.getSamples();
    // Case 1/2 used the fixture in the source dir; the case-3 copies are
    // distinct paths, so 1 + 3 = 4 samples total.
    if (samples.size() != 4) {
        std::cerr << "FAIL: expected 4 samples total, got " << samples.size() << std::endl;
        return 1;
    }
    if (!hasValidEmbedding(samples, "real_kick_a") ||
        !hasValidEmbedding(samples, "real_kick_b") ||
        !hasValidEmbedding(samples, "real_sustained_noise")) {
        std::cerr << "FAIL: sub-kMinBatch tail batch dropped or invalidated a sample" << std::endl;
        return 1;
    }

    tmpDir.deleteRecursively();
    std::cout << "ALL INFERENCE BATCH FLUSH TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
