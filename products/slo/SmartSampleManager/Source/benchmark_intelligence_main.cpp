#include <iostream>
#include <chrono>
#include <mach/mach.h>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Benchmark harness for the V1.1/V1.5 intelligence-layer UX integration pass
// (docs/SMART_SAMPLE_MANAGER_UX_RUNTIME_VALIDATION.md). Dev tooling only, not
// part of the shipped product -- mirrors benchmark_scan_main.cpp's structure
// but times the NEW engine entry points (Smart Collections, weighted/refined
// Find Similar, near-duplicates, map clusters) against a REAL sample
// directory instead of synthetic fixtures, so the numbers reported in the
// final synthesis are measured, not guessed.

static size_t residentMemoryBytes()
{
    mach_task_basic_info_data_t info;
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO,
                   reinterpret_cast<task_info_t>(&info), &count) != KERN_SUCCESS) {
        return 0;
    }
    return info.resident_size;
}

template <typename Fn>
static double timeMs(Fn&& fn)
{
    auto t0 = std::chrono::steady_clock::now();
    fn();
    auto t1 = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::milli>(t1 - t0).count();
}

int main(int argc, char** argv)
{
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    if (argc < 2) {
        std::cerr << "Usage: BenchmarkIntelligence <real_sample_dir>" << std::endl;
        return 1;
    }
    juce::MessageManager::getInstance();

    juce::File sampleDir(argv[1]);
    if (!sampleDir.isDirectory()) {
        std::cerr << "FAIL: " << argv[1] << " is not a directory" << std::endl;
        return 1;
    }

    // Fresh cache: cold-start numbers, not a cache hit from a prior run.
    {
        SampleManagerEngine warmup;
        warmup.clearCache();
    }

    size_t memBefore = residentMemoryBytes();

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    double coldStartMs = timeMs([&]() {
        engine.addPathToQueue(sampleDir.getFullPathName().toStdString());
        int waitLimit = 6000;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(100);
    });

    size_t sampleCount = engine.getSampleCount();
    size_t memAfterScan = residentMemoryBytes();

    // Cached restore: brand-new engine instance, same on-disk cache -- what a
    // real relaunch looks like once the library has already been indexed once.
    double cachedRestoreMs = 0.0;
    size_t cachedSampleCount = 0;
    {
        SampleManagerEngine engine2;
        if (engine2.init(modelPath)) {
            cachedRestoreMs = timeMs([&]() {
                engine2.addPathToQueue(sampleDir.getFullPathName().toStdString());
                int waitLimit = 6000;
                while (engine2.isBusy() && waitLimit-- > 0)
                    juce::Thread::sleep(100);
            });
            cachedSampleCount = engine2.getSampleCount();
        }
    }

    auto samples = engine.getSamples();
    size_t queryCount = std::min<size_t>(samples.size(), 100);

    // Default Find Similar (existing, unweighted)
    std::vector<double> defaultMs;
    for (size_t i = 0; i < queryCount; ++i)
        defaultMs.push_back(timeMs([&]() { engine.findSimilarSamples(samples[i].filePath, 20); }));

    // Weighted Find Similar 2.0 (default weights ~ what a "no configuration"
    // UI would send: even DSP weighting, default 0.3 dsp/embedding ratio)
    SampleManagerEngine::FeatureWeights defaultWeights;
    defaultWeights.spectralCentroidWeight = 1.0f;
    defaultWeights.crestFactorWeight = 1.0f;
    defaultWeights.zeroCrossingRateWeight = 1.0f;
    std::vector<double> weightedMs;
    for (size_t i = 0; i < queryCount; ++i)
        weightedMs.push_back(timeMs([&]() { engine.findSimilarWeighted(samples[i].filePath, defaultWeights, 0.3f, 20); }));

    // Refined Find Similar (a user has moved Brighter/Punchier/Cleaner sliders)
    SampleManagerEngine::TimbreRefinement refinement;
    refinement.brightnessShift = 0.5f;
    refinement.punchinessShift = -0.3f;
    refinement.noiseShift = 0.2f;
    std::vector<double> refinedMs;
    for (size_t i = 0; i < queryCount; ++i)
        refinedMs.push_back(timeMs([&]() { engine.findSimilarRefined(samples[i].filePath, refinement, 20); }));

    // Smart Collection evaluation (one representative rule set)
    double smartCollectionCreateMs = timeMs([&]() {
        engine.createSmartCollection("Bench: Bright & Short",
            R"({"rules":[{"field":"spectralCentroid","op":">","value":2000},{"field":"duration","op":"<","value":2.0}],"logic":"AND"})");
    });
    double smartCollectionEvalMs = timeMs([&]() {
        engine.getSmartCollectionSamples("Bench: Bright & Short");
    });
    engine.deleteSmartCollection("Bench: Bright & Short");

    // Duplicate Intelligence (near-duplicate cosine grouping -- the expensive
    // O(N^2)-shaped one)
    double nearDuplicatesMs = timeMs([&]() { engine.findNearDuplicates(0.95f); });
    double exactDuplicatesMs = timeMs([&]() { engine.findDuplicateGroups(); });

    // Visual Map clustering
    double mapClustersMs = timeMs([&]() { engine.computeMapClusters(); });

    auto pXX = [](std::vector<double> v, double pct) -> double {
        if (v.empty()) return 0.0;
        std::sort(v.begin(), v.end());
        return v[static_cast<size_t>(v.size() * pct)];
    };

    size_t memPeak = residentMemoryBytes();

    std::cout << "=== INTELLIGENCE BENCHMARK RESULTS (" << sampleDir.getFullPathName() << ") ===" << std::endl;
    std::cout << "samples_processed: " << sampleCount << std::endl;
    std::cout << "cold_start_scan_ms: " << coldStartMs << std::endl;
    std::cout << "cold_start_ms_per_file: " << (sampleCount > 0 ? coldStartMs / (double)sampleCount : 0.0) << std::endl;
    std::cout << "cached_restore_ms: " << cachedRestoreMs << std::endl;
    std::cout << "cached_restore_sample_count: " << cachedSampleCount << std::endl;
    std::cout << "queries_run: " << queryCount << std::endl;
    std::cout << "find_similar_default_p50_ms: " << pXX(defaultMs, 0.5) << std::endl;
    std::cout << "find_similar_default_p99_ms: " << pXX(defaultMs, 0.99) << std::endl;
    std::cout << "find_similar_weighted_p50_ms: " << pXX(weightedMs, 0.5) << std::endl;
    std::cout << "find_similar_weighted_p99_ms: " << pXX(weightedMs, 0.99) << std::endl;
    std::cout << "find_similar_refined_p50_ms: " << pXX(refinedMs, 0.5) << std::endl;
    std::cout << "find_similar_refined_p99_ms: " << pXX(refinedMs, 0.99) << std::endl;
    std::cout << "smart_collection_create_ms: " << smartCollectionCreateMs << std::endl;
    std::cout << "smart_collection_eval_ms: " << smartCollectionEvalMs << std::endl;
    std::cout << "near_duplicates_ms: " << nearDuplicatesMs << std::endl;
    std::cout << "exact_duplicates_ms: " << exactDuplicatesMs << std::endl;
    std::cout << "map_clusters_ms: " << mapClustersMs << std::endl;
    std::cout << "rss_before_mb: " << (memBefore / 1024.0 / 1024.0) << std::endl;
    std::cout << "rss_after_scan_mb: " << (memAfterScan / 1024.0 / 1024.0) << std::endl;
    std::cout << "rss_peak_mb: " << (memPeak / 1024.0 / 1024.0) << std::endl;
    std::cout << "=== END INTELLIGENCE BENCHMARK RESULTS ===" << std::endl;

    return 0;
}
