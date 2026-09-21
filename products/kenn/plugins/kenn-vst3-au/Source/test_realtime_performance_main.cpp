#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <vector>

#include <JuceHeader.h>
#include "../../../packages/common/AudioTooRealtimeCore.h"

// Reproducible micro-benchmark for the code that runs from a plug-in's
// processBlock().  It deliberately exercises the complete analyse() path,
// including the atomic publication of the feature frame, without involving
// the editor, network, allocations, or an LLM.

namespace
{

constexpr int kBlocks = 50000;
constexpr double kSampleRate = 48000.0;
constexpr int kBufferSizes[] = { 64, 128, 256, 512, 1024 };
constexpr double kMaxRealtimeBudgetPercent = 1.0;

struct BenchmarkResult
{
    int bufferSize = 0;
    double elapsedMs = 0.0;
    double averageBlockUs = 0.0;
    double perSampleNs = 0.0;
    double realtimeBudgetPercent = 0.0;
    float peakDbfs = -100.0f;
};

BenchmarkResult benchmark(int bufferSize)
{
    AudioTooRealtimeCore core;
    core.reset(kSampleRate);

    juce::AudioBuffer<float> buffer(2, bufferSize);
    auto* left = buffer.getWritePointer(0);
    auto* right = buffer.getWritePointer(1);

    for (int i = 0; i < bufferSize; ++i)
    {
        const auto phase = 2.0 * juce::MathConstants<double>::pi
                         * 997.0 * static_cast<double>(i) / kSampleRate;
        left[i] = static_cast<float>(0.25 * std::sin(phase));
        right[i] = static_cast<float>(0.25 * std::sin(phase + 0.17));
    }

    // Warm the instruction/data paths before timing the steady-state loop.
    for (int i = 0; i < 100; ++i)
        core.analyse(buffer);

    const auto start = std::chrono::steady_clock::now();
    for (int block = 0; block < kBlocks; ++block)
        core.analyse(buffer);
    const auto end = std::chrono::steady_clock::now();

    const auto elapsedMs = std::chrono::duration<double, std::milli>(end - start).count();
    const auto totalSamples = static_cast<double>(kBlocks) * bufferSize;
    const auto audioDurationMs = totalSamples / kSampleRate * 1000.0;

    // Keep the result observable so an optimizing compiler cannot discard the
    // measured work.  The value is also useful when diagnosing a bad build.
    const auto snapshot = core.snapshot();

    return {
        bufferSize,
        elapsedMs,
        elapsedMs * 1000.0 / kBlocks,
        elapsedMs * 1'000'000.0 / totalSamples,
        elapsedMs / audioDurationMs * 100.0,
        snapshot.peakDbfs
    };
}

} // namespace

int main()
{
    std::cout << "[TestRealtimePerformance] " << kBlocks
              << " audio blocks per buffer size at " << kSampleRate << " Hz\n";
    std::cout << std::fixed << std::setprecision(3);

    bool passed = true;
    std::vector<BenchmarkResult> results;
    results.reserve(std::size(kBufferSizes));

    for (const auto bufferSize : kBufferSizes)
    {
        const auto result = benchmark(bufferSize);
        results.push_back(result);
        const bool resultPassed = result.realtimeBudgetPercent < kMaxRealtimeBudgetPercent
                                && std::isfinite(result.perSampleNs);
        passed = passed && resultPassed;

        std::cout << "  buffer=" << result.bufferSize
                  << " blocks=" << kBlocks
                  << " total=" << result.elapsedMs << " ms"
                  << " avgBlock=" << result.averageBlockUs << " us"
                  << " perSample=" << result.perSampleNs << " ns"
                  << " realtimeBudget=" << result.realtimeBudgetPercent << "%"
                  << " peak=" << result.peakDbfs << " dBFS"
                  << " status=" << (resultPassed ? "PASS" : "FAIL") << '\n';
    }

    if (!passed)
    {
        std::cerr << "[TestRealtimePerformance] FAILED: at least one buffer size exceeded the "
                  << kMaxRealtimeBudgetPercent << "% realtime CPU budget.\n";
        return 1;
    }

    std::cout << "[TestRealtimePerformance] ALL BUFFER SIZES PASSED.\n";
    return 0;
}
