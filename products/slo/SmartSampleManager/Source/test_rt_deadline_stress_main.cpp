// SLO Master Plan V2, Phase 8 (B-010): RT deadline-stress + allocation
// instrumentation for SmartSampleManagerAudioProcessor::processBlock().
//
// Diagnostic tool, not a pass/fail correctness test -- same posture as
// ClassificationBenchmark's perf/soak modes. Drives processBlock() at a real
// block size/sample rate under simulated audio-callback timing pressure,
// interleaved with playSample() start/stop/source-change calls the way a
// live DAW session actually behaves, and reports deadline misses plus heap
// allocation activity during the tracked callback window. Writes a JSON
// receipt; does not fail the build on a bad result -- this exists to
// produce honest evidence, not to gate on a threshold nobody has set yet.
//
// See docs/SLO_RT_THREADING_AUDIT_V1.md for the source-review-only
// assessment this instruments for real, and the master plan's Phase 8 for
// why this needed its own dedicated pass (PluginProcessor.cpp isn't part of
// the lightweight ssm_engine_core_test object library the other Test*
// binaries link against -- this target adds it plus PluginEditor.cpp as
// EXTRA_SOURCES against the ssm_juce_ui tier instead).

#include <JuceHeader.h>
#include "PluginProcessor.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <new>
#include <vector>

// --- Allocation tracking -----------------------------------------------
//
// thread_local, increment-only, thin passthrough to malloc/free. Safe to
// install process-wide: it never changes what gets allocated or how, only
// counts calls while g_trackingActive is true on the calling thread. Every
// other thread (engine background threads, ONNX, etc.) is completely
// unaffected -- the counter is thread-local, not global.
static thread_local bool g_trackingActive = false;
static thread_local std::size_t g_allocCount = 0;

void* operator new(std::size_t size)
{
    if (g_trackingActive) ++g_allocCount;
    void* p = std::malloc(size);
    if (p == nullptr) throw std::bad_alloc();
    return p;
}

void operator delete(void* p) noexcept
{
    if (g_trackingActive) ++g_allocCount;
    std::free(p);
}

void* operator new[](std::size_t size)
{
    if (g_trackingActive) ++g_allocCount;
    void* p = std::malloc(size);
    if (p == nullptr) throw std::bad_alloc();
    return p;
}

void operator delete[](void* p) noexcept
{
    if (g_trackingActive) ++g_allocCount;
    std::free(p);
}

int main()
{
    // Must happen before any SampleManagerEngine is constructed --
    // SmartSampleManagerAudioProcessor's constructor builds one internally
    // via engine.initAsync(). Without this override, the engine's fail-closed
    // production-cache guard aborts rather than risk touching a real user's
    // sample library database. Same pattern as classification_benchmark_main.cpp.
    juce::File customCacheDir = juce::File::getCurrentWorkingDirectory()
        .getChildFile("fixtures").getChildFile("cache_rt_stress");
    customCacheDir.createDirectory();
    SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(customCacheDir);

    juce::MessageManager::getInstance();

    constexpr double sampleRate = 44100.0;
    constexpr int blockSize = 512;
    constexpr double deadlineMs = (static_cast<double>(blockSize) / sampleRate) * 1000.0; // ~11.61ms
    constexpr int numIterations = 2000; // ~23s of simulated audio at this block size
    constexpr int playSampleEveryN = 100; // stress start/stop/source-change periodically

    std::cout << "RT deadline-stress: " << numIterations << " iterations, block=" << blockSize
              << " @ " << sampleRate << "Hz, deadline=" << deadlineMs << "ms" << std::endl;

    SmartSampleManagerAudioProcessor processor;
    processor.prepareToPlay(sampleRate, blockSize);

    const std::string fixturePath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/test_kick.wav";

    // Warm-up: let JIT/caches/engine async init settle, not tracked or timed.
    for (int i = 0; i < 10; ++i) {
        juce::AudioBuffer<float> buffer(2, blockSize);
        juce::MidiBuffer midi;
        processor.processBlock(buffer, midi);
    }

    std::vector<double> callbackMs;
    callbackMs.reserve(numIterations);
    std::vector<std::size_t> allocCounts;
    allocCounts.reserve(numIterations);
    int deadlineMisses = 0;

    for (int i = 0; i < numIterations; ++i) {
        // Message-thread work happens BETWEEN callbacks, same as a real DAW
        // session -- never inside the tracked/timed window below.
        if (i > 0 && i % playSampleEveryN == 0) {
            processor.playSample(fixturePath);
        }

        juce::AudioBuffer<float> buffer(2, blockSize);
        juce::MidiBuffer midi;

        g_allocCount = 0;
        g_trackingActive = true;
        auto t0 = std::chrono::steady_clock::now();
        processor.processBlock(buffer, midi);
        auto t1 = std::chrono::steady_clock::now();
        g_trackingActive = false;

        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        callbackMs.push_back(ms);
        allocCounts.push_back(g_allocCount);
        if (ms > deadlineMs) ++deadlineMisses;
    }

    processor.releaseResources();

    double sum = 0.0, maxMs = 0.0;
    for (double ms : callbackMs) { sum += ms; if (ms > maxMs) maxMs = ms; }
    double meanMs = sum / static_cast<double>(callbackMs.size());

    std::vector<double> sorted = callbackMs;
    std::sort(sorted.begin(), sorted.end());
    double p99Ms = sorted[static_cast<size_t>(sorted.size() * 0.99)];

    std::size_t totalAllocs = 0, maxAllocsInOneCallback = 0;
    int callbacksWithAnyAlloc = 0;
    for (std::size_t c : allocCounts) {
        totalAllocs += c;
        if (c > maxAllocsInOneCallback) maxAllocsInOneCallback = c;
        if (c > 0) ++callbacksWithAnyAlloc;
    }

    std::cout << "Deadline misses: " << deadlineMisses << "/" << numIterations
              << " (" << (100.0 * deadlineMisses / numIterations) << "%)" << std::endl;
    std::cout << "Callback duration: mean=" << meanMs << "ms max=" << maxMs << "ms p99=" << p99Ms << "ms"
              << std::endl;
    std::cout << "Allocations during tracked callbacks: total=" << totalAllocs
              << ", callbacks-with-any-alloc=" << callbacksWithAnyAlloc << "/" << numIterations
              << ", max-in-one-callback=" << maxAllocsInOneCallback << std::endl;

    juce::File outFile(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/tools/classification_benchmark/results_rt_deadline_stress.json");
    outFile.deleteFile();
    juce::FileOutputStream stream(outFile);
    if (stream.openedOk()) {
        juce::String json;
        json << "{\n"
             << "  \"num_iterations\": " << numIterations << ",\n"
             << "  \"block_size\": " << blockSize << ",\n"
             << "  \"sample_rate\": " << sampleRate << ",\n"
             << "  \"deadline_ms\": " << deadlineMs << ",\n"
             << "  \"deadline_misses\": " << deadlineMisses << ",\n"
             << "  \"deadline_miss_pct\": " << (100.0 * deadlineMisses / numIterations) << ",\n"
             << "  \"callback_mean_ms\": " << meanMs << ",\n"
             << "  \"callback_max_ms\": " << maxMs << ",\n"
             << "  \"callback_p99_ms\": " << p99Ms << ",\n"
             << "  \"total_allocations\": " << totalAllocs << ",\n"
             << "  \"callbacks_with_any_alloc\": " << callbacksWithAnyAlloc << ",\n"
             << "  \"max_allocations_in_one_callback\": " << maxAllocsInOneCallback << "\n"
             << "}\n";
        stream.writeText(json, false, false, nullptr);
        std::cout << "Results saved to: " << outFile.getFullPathName() << std::endl;
    }

    juce::MessageManager::deleteInstance();
    return 0;
}
