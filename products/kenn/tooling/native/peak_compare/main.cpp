#include <juce_dsp/juce_dsp.h>
#include "StreamingMeter.h"
#include <array>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <new>
#include <time.h>
#include <vector>

static_assert(JUCE_MAJOR_VERSION == 8 && JUCE_MINOR_VERSION == 0 && JUCE_BUILDNUMBER == 2,
              "This comparison was qualified against JUCE 8.0.2");

// This guard counts ordinary C++ new/new[] during processing. It does not
// instrument malloc or aligned allocation, so it cannot qualify all heap use.
static thread_local bool watchCppHeap = false;
static thread_local size_t cppHeapCalls = 0;
void* operator new(size_t bytes)
{
    if (watchCppHeap) ++cppHeapCalls;
    if (auto* result = std::malloc(std::max(size_t(1), bytes))) return result;
    throw std::bad_alloc(); // Instrumentation must preserve an actual allocation failure.
}
void* operator new[](size_t bytes) { return ::operator new(bytes); }
void operator delete(void* value) noexcept { std::free(value); }
void operator delete[](void* value) noexcept { std::free(value); }

using StereoFrame = std::array<float, 2>;
constexpr int blockFrames = 128; // Shared-worker input chunk for the batched alternative.

// Each comparison owns its filter state. The frame-at-a-time mode exposes the
// cost of dropping JUCE into the current push(frame) interface without batching.
class Candidate
{
public:
    Candidate(const std::string& mode, int rate) : binFrames(rate / 10)
    {
        if (mode == "current")
        {
            if (!meter.prepare(rate)) throw std::runtime_error("Unsupported meter rate"); // Keep coefficients and the 100 ms grid qualified.
            delay = KENNStreamingMeterSnapshot::interpolationDelaySamples;
            factor = 4;
            return;
        }
        if (mode != "juce4" && mode != "juce8" && mode != "juce8_frame")
            throw std::runtime_error("Unknown candidate"); // A misspelt mode must not select another implementation.
        chunkFrames = mode == "juce8_frame" ? 1 : blockFrames;
        const size_t power = mode == "juce4" ? 2 : 3; // JUCE's factor argument is log2(interpolation ratio).
        sampler = std::make_unique<juce::dsp::Oversampling<double>>(
            2, power, juce::dsp::Oversampling<double>::filterHalfBandFIREquiripple, true, false);
        sampler->initProcessing(blockFrames);
        audio.setSize(2, blockFrames);
        factor = static_cast<int>(sampler->getOversamplingFactor());
        roundTripDelay = sampler->getLatencyInSamples();
        // getLatencyInSamples includes downsampling. Locate the prepared FIR's
        // impulse centre to measure the upsampling-only delay, then retire that
        // artificial passage before feeding any qualification signal.
        audio.clear(); audio.setSample(0, 0, 1.0);
        const auto response = sampler->processSamplesUp(juce::dsp::AudioBlock<const double>(audio));
        size_t maximum = 0;
        for (size_t sample = 1; sample < response.getNumSamples(); ++sample)
            if (std::abs(response.getSample(0, sample)) > std::abs(response.getSample(0, maximum))) maximum = sample;
        if (std::abs(response.getSample(0, maximum) - 1.0) > 1e-12)
            throw std::runtime_error("Impulse centre is not unity"); // Reject an unrecognised FIR response instead of guessing its delay.
        delay = static_cast<double>(maximum) / factor;
        sampler->reset();
    }

    double processBin(const StereoFrame* input)
    {
        watchCppHeap = true;
        double peak = 0.0;
        if (!sampler)
        {
            // Include the actual meter's loudness work; the receipt explicitly
            // distinguishes this from JUCE's interpolation-only workload.
            for (int sample = 0; sample < binFrames; ++sample) meter.push(input[sample][0], input[sample][1]);
            peak = meter.snapshot().truePeakLinear;
        }
        else
        {
            for (int first = 0; first < binFrames; first += chunkFrames)
            {
                const auto count = std::min(chunkFrames, binFrames - first);
                for (int sample = 0; sample < count; ++sample)
                    for (int channel = 0; channel < 2; ++channel) audio.setSample(channel, sample, input[first + sample][channel]);
                const auto up = sampler->processSamplesUp(juce::dsp::AudioBlock<const double>(audio).getSubBlock(0, static_cast<size_t>(count)));
                for (size_t channel = 0; channel < up.getNumChannels(); ++channel)
                    for (size_t sample = 0; sample < up.getNumSamples(); ++sample) peak = std::max(peak, std::abs(up.getSample(static_cast<int>(channel), static_cast<int>(sample))));
            }
        }
        watchCppHeap = false;
        return peak;
    }

    double delay = 0.0, roundTripDelay = 0.0;
    int factor = 0;

private:
    int binFrames = 0, chunkFrames = blockFrames;
    KENNStreamingMeter meter;
    std::unique_ptr<juce::dsp::Oversampling<double>> sampler;
    juce::AudioBuffer<double> audio;
};

static int integerArgument(const char* text)
{
    size_t consumed = 0;
    const auto result = std::stoi(text, &consumed);
    if (consumed != std::string(text).size())
        throw std::runtime_error("Expected an integer argument"); // A trailing suffix must not silently select a different request.
    return result;
}

static int qualifiedRate(const char* text)
{
    const auto rate = integerArgument(text);
    if (rate != 44100 && rate != 48000 && rate != 96000)
        throw std::runtime_error("Unsupported rate"); // All comparisons use exact 100 ms grids at the three planned rates.
    return rate;
}

static double cpuMilliseconds()
{
    timespec value {};
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &value) != 0)
        throw std::runtime_error("CPU clock unavailable"); // Wall elapsed time cannot substitute for process CPU.
    return 1000.0 * static_cast<double>(value.tv_sec) + static_cast<double>(value.tv_nsec) / 1e6;
}

static void trace(const std::string& mode, int rate, const char* path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Cannot read synthetic input"); // Missing audio must fail, not look like ready silence.
    std::vector<StereoFrame> frames;
    StereoFrame frame {};
    while (file.read(reinterpret_cast<char*>(frame.data()), sizeof(frame)))
    {
        if (!std::isfinite(frame[0]) || !std::isfinite(frame[1]))
            throw std::runtime_error("Non-finite input"); // Invalid-fixture rejection is distinct from runtime gap recovery.
        frames.push_back(frame);
        if (frames.size() > static_cast<size_t>(10 * rate))
            throw std::runtime_error("Input exceeds ten seconds"); // Bound the offline fixture's owned storage.
    }
    const auto bin = static_cast<size_t>(rate / 10);
    if (!file.eof() || file.gcount() != 0 || frames.empty() || frames.size() % bin != 0)
        throw std::runtime_error("Input must contain complete stereo frames and 100 ms bins"); // Never hide an omitted tail in comparison evidence.
    Candidate candidate(mode, rate);
    cppHeapCalls = 0;
    std::cout << "{\"factor\":" << candidate.factor << ",\"upsampling_delay_frames\":" << candidate.delay
              << ",\"round_trip_delay_frames\":" << candidate.roundTripDelay << ",\"peaks\":[";
    for (size_t first = 0; first < frames.size(); first += bin)
    {
        if (first != 0) std::cout << ',';
        std::cout << candidate.processBin(frames.data() + first);
    }
    std::cout << "],\"cpp_heap_calls\":" << cppHeapCalls << "}\n";
}

static void profile(const std::string& mode, int rate, int inserts, int repeats)
{
    if ((inserts != 1 && inserts != 8 && inserts != 32 && inserts != 64) || repeats < 3 || repeats > 30)
        throw std::runtime_error("Invalid profile matrix cell"); // Keep receipts on the planned insert counts and bounded repeat range.
    const int bin = rate / 10;
    std::vector<StereoFrame> input(static_cast<size_t>(bin));
    for (int sample = 0; sample < bin; ++sample)
    {
        // 997 Hz at 0.25 full-scale avoids silence shortcuts and leaves peak
        // headroom. The same generated 100 ms passage feeds every insert.
        const auto value = static_cast<float>(0.25 * std::sin(2.0 * juce::MathConstants<double>::pi * 997.0 * sample / rate));
        input[static_cast<size_t>(sample)] = { value, -value }; // Synthetic antiphase stereo retains independent channel work.
    }
    std::vector<std::unique_ptr<Candidate>> candidates;
    for (int insert = 0; insert < inserts; ++insert) candidates.push_back(std::make_unique<Candidate>(mode, rate));
    constexpr int warmup = 32; // 3.2 s of untimed history also warms the current meter's 3 s loudness path.
    double checksum = 0.0;
    for (int tick = 0; tick < warmup; ++tick)
        for (auto& candidate : candidates) checksum += candidate->processBin(input.data());
    std::vector<double> wall, cpu;
    wall.reserve(static_cast<size_t>(repeats)); cpu.reserve(static_cast<size_t>(repeats));
    cppHeapCalls = 0;
    for (int tick = 0; tick < repeats; ++tick)
    {
        const auto start = std::chrono::steady_clock::now();
        const auto cpuStart = cpuMilliseconds();
        for (auto& candidate : candidates) checksum += candidate->processBin(input.data());
        const auto cpuEnd = cpuMilliseconds();
        wall.push_back(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count());
        cpu.push_back(cpuEnd - cpuStart);
    }
    std::cout << "{\"mode\":\"" << mode << "\",\"rate\":" << rate << ",\"inserts\":" << inserts
              << ",\"warmup_ticks\":" << warmup << ",\"cpp_heap_calls\":" << cppHeapCalls << ",\"checksum\":" << checksum << ",\"wall_ms\":[";
    for (size_t tick = 0; tick < wall.size(); ++tick) { if (tick != 0) std::cout << ','; std::cout << wall[tick]; }
    std::cout << "],\"cpu_ms\":[";
    for (size_t tick = 0; tick < cpu.size(); ++tick) { if (tick != 0) std::cout << ','; std::cout << cpu[tick]; }
    std::cout << "]}\n";
}

int main(int argc, char** argv)
{
    std::cout << std::setprecision(17);
    try
    {
        if (argc == 2 && std::string(argv[1]) == "--info")
        {
            std::cout << "{\"juce_version\":\"8.0.2\",\"compiler\":\"" << __VERSION__
                      << "\",\"pointer_bits\":" << sizeof(void*) * 8
                      << ",\"current_meter_bytes\":" << sizeof(KENNStreamingMeter)
#ifdef NDEBUG
                      << ",\"assertions_enabled\":false}\n";
#else
                      << ",\"assertions_enabled\":true}\n";
#endif
        }
        else if (argc == 5 && std::string(argv[1]) == "--trace") trace(argv[2], qualifiedRate(argv[3]), argv[4]);
        else if (argc == 6 && std::string(argv[1]) == "--profile") profile(argv[2], qualifiedRate(argv[3]), integerArgument(argv[4]), integerArgument(argv[5]));
        else throw std::runtime_error("Use --info, --trace MODE RATE FILE or --profile MODE RATE INSERTS REPEATS"); // Refuse ambiguous CLI requests.
        return 0;
    }
    catch (const std::exception& error)
    {
        watchCppHeap = false;
        std::cerr << error.what() << '\n';
        return 2; // Invalid input/tool failures must not yield a successful comparison receipt.
    }
}
