#include <iostream>
#include <chrono>
#include <mach/mach.h>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Benchmark harness for docs/PERFORMANCE_BASELINE.md. Not part of the
// shipped product -- dev tooling only (see CMakeLists.txt's
// BUILD_BENCHMARK option). Scans a directory of synthetic fixtures
// (see generate_benchmark_fixtures.py) through the real production
// pipeline and reports timing/memory/DB-size measurements. No results
// are fabricated -- if a size tier wasn't actually run, it isn't in the
// generated report.

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

int main(int argc, char** argv)
{
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    if (argc < 2) {
        std::cerr << "Usage: BenchmarkScan <fixture_dir>" << std::endl;
        return 1;
    }
    juce::MessageManager::getInstance();

    juce::File fixtureDir(argv[1]);
    if (!fixtureDir.isDirectory()) {
        std::cerr << "FAIL: " << argv[1] << " is not a directory" << std::endl;
        return 1;
    }

    // Fresh cache every run so "full scan" numbers reflect real
    // decode+embed+index cost, not a cache hit from a prior run.
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

    auto t0 = std::chrono::steady_clock::now();
    engine.addPathToQueue(fixtureDir.getFullPathName().toStdString());
    auto t1 = std::chrono::steady_clock::now();
    double enumerateDispatchMs = std::chrono::duration<double, std::milli>(t1 - t0).count();

    // Progress-based wait (Phase 4): abort only if processed count stalls,
    // not on absolute elapsed time. The old fixed 10-minute cap silently
    // truncated the 5,000-file tier (3012/5000) in docs/MEMORY_PROFILE.md.
    auto waitUntilIdle = [&engine]() {
        size_t lastProcessed = 0;
        int stallPolls = 0;
        while (engine.isBusy()) {
            juce::Thread::sleep(100);
            const size_t processed = engine.getSampleCount();
            if (processed != lastProcessed) {
                lastProcessed = processed;
                stallPolls = 0;
            } else if (++stallPolls > 3600) {  // 6 min with zero progress
                std::cerr << "WARN: scan stalled (no progress for 6 min) at "
                          << processed << " samples" << std::endl;
                break;
            }
        }
    };
    waitUntilIdle();
    auto t2 = std::chrono::steady_clock::now();
    double fullScanMs = std::chrono::duration<double, std::milli>(t2 - t0).count();

    // UMAP layout is performed by the scan coordinator *before* it clears
    // busyFlag, so isBusy()-based timing above folds canvas layout into what
    // would otherwise look like per-file scan cost. Capture it now (the
    // incremental rescan below overwrites it) so the report can separate the
    // two. See SampleManagerEngine::getLastLayoutDurationMs().
    const double layoutMs = engine.getLastLayoutDurationMs();
    const double scanOnlyMs = fullScanMs - layoutMs;

    size_t sampleCount = engine.getSampleCount();
    size_t memAfterScan = residentMemoryBytes();

    // Incremental rescan: same directory, nothing new -- measures the
    // "did I already process this" cache-check cost, not a full re-embed.
    auto t3 = std::chrono::steady_clock::now();
    engine.addPathToQueue(fixtureDir.getFullPathName().toStdString());
    waitUntilIdle();
    auto t4 = std::chrono::steady_clock::now();
    double incrementalRescanMs = std::chrono::duration<double, std::milli>(t4 - t3).count();
    // Same layout-vs-scan separation for the cache-hit rescan path.
    const double incrementalLayoutMs = engine.getLastLayoutDurationMs();

    // Search latency: measure findSimilarSamples() over a sample of queries.
    auto samples = engine.getSamples();
    std::vector<double> searchLatenciesMs;
    size_t queryCount = std::min<size_t>(samples.size(), 200);
    for (size_t i = 0; i < queryCount; ++i) {
        auto qStart = std::chrono::steady_clock::now();
        engine.findSimilarSamples(samples[i].filePath, 10);
        auto qEnd = std::chrono::steady_clock::now();
        searchLatenciesMs.push_back(std::chrono::duration<double, std::milli>(qEnd - qStart).count());
    }
    std::sort(searchLatenciesMs.begin(), searchLatenciesMs.end());
    double searchP50 = searchLatenciesMs.empty() ? 0.0 : searchLatenciesMs[searchLatenciesMs.size() / 2];
    double searchP99 = searchLatenciesMs.empty() ? 0.0 : searchLatenciesMs[static_cast<size_t>(searchLatenciesMs.size() * 0.99)];

    size_t memPeak = residentMemoryBytes();
    // Use the engine's own resolver, which honors the ScopedIsolatedCacheDb
    // override active in this process. Previously this hand-built the
    // PRODUCTION path (~/Library/SmartSampleManager/sample_cache.sqlite3),
    // which is untouched under isolation -- so db_size_bytes measured an
    // unrelated, likely-empty file and the per-sample figure it produced
    // (e.g. "103.26 bytes/sample" at 100k) was meaningless.
    juce::File dbFile = SampleManagerEngine::getCacheDbFile();
    int64_t dbSizeBytes = dbFile.existsAsFile() ? dbFile.getSize() : 0;

    std::cout << "=== BENCHMARK RESULTS (fixture dir: " << fixtureDir.getFullPathName() << ") ===" << std::endl;
    std::cout << "files_requested_dir_entries: " << fixtureDir.getNumberOfChildFiles(juce::File::findFiles, "*.wav") << std::endl;
    std::cout << "samples_processed: " << sampleCount << std::endl;
    std::cout << "enumerate_and_dispatch_ms: " << enumerateDispatchMs << std::endl;
    std::cout << "full_scan_total_ms: " << fullScanMs << std::endl;
    std::cout << "full_scan_ms_per_file: " << (sampleCount > 0 ? fullScanMs / static_cast<double>(sampleCount) : 0.0) << std::endl;
    // Reported separately because full_scan_* above INCLUDES canvas layout
    // (the coordinator runs triggerUMAP() before clearing busyFlag).
    std::cout << "umap_layout_ms: " << layoutMs << std::endl;
    std::cout << "scan_only_total_ms: " << scanOnlyMs << std::endl;
    std::cout << "scan_only_ms_per_file: " << (sampleCount > 0 ? scanOnlyMs / static_cast<double>(sampleCount) : 0.0) << std::endl;
    std::cout << "incremental_rescan_ms: " << incrementalRescanMs << std::endl;
    std::cout << "incremental_umap_layout_ms: " << incrementalLayoutMs << std::endl;
    std::cout << "search_queries_run: " << queryCount << std::endl;
    std::cout << "search_latency_p50_ms: " << searchP50 << std::endl;
    std::cout << "search_latency_p99_ms: " << searchP99 << std::endl;
    std::cout << "rss_before_mb: " << (memBefore / 1024.0 / 1024.0) << std::endl;
    std::cout << "rss_after_scan_mb: " << (memAfterScan / 1024.0 / 1024.0) << std::endl;
    std::cout << "rss_peak_mb: " << (memPeak / 1024.0 / 1024.0) << std::endl;
    std::cout << "db_size_bytes: " << dbSizeBytes << std::endl;
    std::cout << "db_size_bytes_per_sample: " << (sampleCount > 0 ? static_cast<double>(dbSizeBytes) / static_cast<double>(sampleCount) : 0.0) << std::endl;
    std::cout << "=== END BENCHMARK RESULTS ===" << std::endl;

    return 0;
}
