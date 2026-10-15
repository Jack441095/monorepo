#pragma once

#include "MeterAnalyzer.h"
#include "CachedSpectrum.h"
#include "StreamingMeter.h"
#include <array>

// One publication contains all metrics from the same contiguous insert window.
// Local positions always exist. Host positions are supplied only by a playing
// transport with a sample clock; unavailable host timing never becomes zero.
struct KENNHostPosition
{
    juce::int64 firstSample = 0;
    bool valid = false;
};

struct KENNAnalysisSnapshot
{
    AudioTooFeatureFrame features;
    AudioTooSpectrumFrame spectrum;
    juce::int64 firstSample = 0, endSample = 0, capturedTicks = 0;
    uint64_t generation = 0, sequence = 0, droppedSamples = 0, invalidSamples = 0;
    uint64_t transportEpoch = 0;
    juce::int64 hostFirstSample = 0, hostEndSample = 0;
    bool hostTimelineValid = false;
    KENNFFTSnapshot fastSpectrum, lowSpectrum;
    KENNStreamingMeterSnapshot streamingMeter; // Offline candidate only; absent from HTTP handoff.
    double windowSeconds = 0.0;
    double workerMilliseconds = 0.0;
    int queuedPackets = 0;
    bool valid = false;
    int inputChannels = 0; // Unknown until a complete mono or stereo window is published.
    bool correlationValid = false; // Mono duplication and undefined stereo energy retain only the legacy numeric fallback.
};

class KENNAnalysisWorker;

// push() is the sole audio-thread entry: bounded copies into fixed storage,
// no allocation, mutex, wake-up syscall or I/O. All DSP runs on a shared worker.
class KENNContinuousAnalysis
{
public:
    KENNContinuousAnalysis() = default;
    ~KENNContinuousAnalysis();
    // The host must stop callbacks before prepare/release. Tests may disable the
    // shared worker and drain synchronously to compare exact synthetic windows.
    // Streaming qualification is opt-in here; plug-in callers leave it disabled.
    void prepare(double sampleRate, bool startWorker = true, bool enableStreamingCandidate = false);
    void release();
    void push(const juce::AudioBuffer<float>&, bool enabled, KENNHostPosition = {}) noexcept;
    void invalidate() noexcept { sourceGeneration.fetch_add(1); }
    KENNAnalysisSnapshot snapshot() const;
    std::array<KENNAnalysisSnapshot, 6> recentSnapshots() const; // Last 600 ms for asynchronous paired publishers.
    void drainPending(); // Only the shared worker, or a prepared synchronous test, may consume.

    static constexpr int packetSamples = 64; // Frames per copy packet, independent of host blocks.
    static constexpr int packetSlots = 257; // 256 usable packets: up to 16,384 stereo frames.
    static constexpr double windowSeconds = 0.1; // 100 ms contiguous measurement windows.
    static constexpr size_t queueStorageBytes();

private:
    friend class KENNAnalysisWorker;
    struct Packet
    {
        std::array<float, packetSamples> left {}, right {};
        juce::int64 firstSample = 0, endTicks = 0;
        uint64_t generation = 0, dropped = 0;
        uint64_t transportEpoch = 0;
        juce::int64 hostFirstSample = 0;
        bool hostTimelineValid = false;
        uint8_t inputChannels = 0; // Mono/stereo layout fits the packet's existing alignment padding.
        int count = 0;
    };
    void resetWindow(bool resetFilters);
    void consume(const Packet&);
    void publish(const Packet&, int lastSample);
    juce::AbstractFifo fifo { packetSlots };
    std::array<Packet, packetSlots> packets;
    std::atomic<uint64_t> sourceGeneration { 1 }, dropped { 0 }, invalid { 0 };
    std::atomic<uint64_t> transportEpoch { 1 };
    std::atomic<double> workerMilliseconds { 0.0 }; // Worker elapsed DSP time, not process CPU accounting.
    juce::int64 producerSamples = 0;
    bool previouslyEnabled = true, registered = false;
    int producerInputChannels = 0;
    bool producerHostValid = false;
    juce::int64 producerExpectedHost = 0;
    double rate = 0.0, ticksPerSample = 0.0;
    int windowSamples = 0, count = 0, clipped = 0;
    uint64_t workerGeneration = 0, workerDropped = 0, sequence = 0;
    uint64_t workerTransportEpoch = 0;
    juce::int64 hostFirstSample = 0;
    juce::int64 expectedSample = -1, firstSample = 0, analysedSamples = 0;
    double ll = 0.0, rr = 0.0, lr = 0.0, side = 0.0, peak = 0.0;
    double fastEnvelope = 0.0, slowEnvelope = 0.0, onsetEnergy = 0.0, sustainEnergy = 0.0;
    double fastAttack = 0.0, fastRelease = 0.0, slowAttack = 0.0, slowRelease = 0.0;
    std::array<float, AudioTooRealtimeSpectrumBandCount> lowAlpha {}, highAlpha {};
    std::array<std::array<float, AudioTooRealtimeSpectrumBandCount>, 2> lowState {}, highState {};
    std::array<double, AudioTooRealtimeSpectrumBandCount> bandEnergy {};
    AudioTooSpectrumFrame spectrum;
    KENNCachedSpectrum<2048> fastFFT;
    KENNCachedSpectrum<8192> lowFFT;
    KENNStreamingMeter streamingMeter;
    bool streamingCandidateEnabled = false; // Production callers retain the disabled default until qualification.
    mutable juce::CriticalSection publicationLock; // Worker/readers only; push() never takes it.
    KENNAnalysisSnapshot published;
    std::array<KENNAnalysisSnapshot, 6> recent {};
};

constexpr size_t KENNContinuousAnalysis::queueStorageBytes() { return sizeof(Packet) * packetSlots; }
