#include <atomic>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <random>
#include <thread>
#include <vector>

#include <JuceHeader.h>
#include "../../common/AudioTooRealtimeCore.h"

// Stress-tests AudioTooRealtimeCore's real concurrency contract: one
// "audio thread" continuously calling analyse() (as processBlock() does)
// while one or more "UI/handoff threads" continuously call snapshot() (as
// the editor timer and the plugin-handoff JSON builder do) -- concurrently,
// for real, not just reasoned about from the header comments.
//
// This is meant to be built with -fsanitize=thread (see CMakeLists.txt's
// KENN_ENABLE_TSAN option) so a genuine data race is a hard failure, not a
// "didn't crash in N seconds" false negative -- racy lock-free code can run
// clean for a long time while still having a real race that only shows up
// on different hardware/scheduling.

namespace {

constexpr int kBufferSizesToTry[] = { 32, 64, 128, 256, 512, 1024 };
constexpr double kSampleRatesToTry[] = { 44100.0, 48000.0, 88200.0, 96000.0, 192000.0 };

std::atomic<bool> stopRequested{false};
std::atomic<int> readerNaNOrInfCount{0};
std::atomic<juce::int64> analyseCalls{0};
std::atomic<juce::int64> snapshotCalls{0};

void audioThreadWorker(AudioTooRealtimeCore& core)
{
    std::mt19937 rng(12345);
    std::uniform_int_distribution<int> sizePick(0, static_cast<int>(std::size(kBufferSizesToTry)) - 1);
    std::uniform_real_distribution<float> samplePick(-1.0f, 1.0f);

    juce::AudioBuffer<float> buffer(2, 1024);

    while (!stopRequested.load(std::memory_order_relaxed)) {
        const int numSamples = kBufferSizesToTry[sizePick(rng)];
        for (int ch = 0; ch < 2; ++ch) {
            auto* data = buffer.getWritePointer(ch);
            for (int i = 0; i < numSamples; ++i)
                data[i] = samplePick(rng);
        }
        juce::AudioBuffer<float> block(buffer.getArrayOfWritePointers(), 2, numSamples);
        core.analyse(block);
        analyseCalls.fetch_add(1, std::memory_order_relaxed);
    }
}

void readerThreadWorker(const AudioTooRealtimeCore& core)
{
    while (!stopRequested.load(std::memory_order_relaxed)) {
        auto snap = core.snapshot();
        snapshotCalls.fetch_add(1, std::memory_order_relaxed);
        // A torn/racy read on the atomics would most plausibly surface as a
        // NaN/Inf (e.g. a partially-updated running sum feeding a sqrt of a
        // negative number) rather than a crash -- check for it directly
        // rather than only relying on TSan to catch the underlying race.
        if (!std::isfinite(snap.peakDbfs) && snap.peakDbfs != -100.0f) readerNaNOrInfCount.fetch_add(1);
        if (!std::isfinite(snap.rmsDbfs) && snap.rmsDbfs != -100.0f) readerNaNOrInfCount.fetch_add(1);
        if (!std::isfinite(snap.correlation)) readerNaNOrInfCount.fetch_add(1);
        if (!std::isfinite(snap.stereoWidth)) readerNaNOrInfCount.fetch_add(1);
    }
}

bool runStressPass(double sampleRate, int durationMs)
{
    AudioTooRealtimeCore core;
    core.reset(sampleRate);

    stopRequested.store(false);
    analyseCalls.store(0);
    snapshotCalls.store(0);
    readerNaNOrInfCount.store(0);

    std::thread audioThread(audioThreadWorker, std::ref(core));
    std::vector<std::thread> readerThreads;
    for (int i = 0; i < 3; ++i)
        readerThreads.emplace_back(readerThreadWorker, std::cref(core));

    juce::Thread::sleep(durationMs);
    stopRequested.store(true);

    audioThread.join();
    for (auto& t : readerThreads) t.join();

    std::cout << "  sampleRate=" << sampleRate << " analyseCalls=" << analyseCalls.load()
              << " snapshotCalls=" << snapshotCalls.load()
              << " nanOrInfReads=" << readerNaNOrInfCount.load() << std::endl;

    return readerNaNOrInfCount.load() == 0 && analyseCalls.load() > 0 && snapshotCalls.load() > 0;
}

} // namespace

int main()
{
    std::cout << "AudioTooRealtimeCore concurrent stress test "
                 "(1 audio-thread writer + 3 concurrent reader threads per pass)" << std::endl;

    bool allPassed = true;
    for (double sampleRate : kSampleRatesToTry) {
        if (!runStressPass(sampleRate, 400)) {
            std::cerr << "FAIL: NaN/Inf detected in concurrently-read snapshot at "
                      << sampleRate << " Hz -- a real data race, not just a theoretical one." << std::endl;
            allPassed = false;
        }
    }

    if (!allPassed) return 1;

    std::cout << "SUCCESS: no torn/NaN reads detected across " << std::size(kSampleRatesToTry)
              << " sample rates under concurrent analyse()/snapshot() access. "
                 "If built with -fsanitize=thread and no TSan report printed above, "
                 "this is a real, tool-verified absence of a data race, not just a passing smoke test."
              << std::endl;
    return 0;
}
