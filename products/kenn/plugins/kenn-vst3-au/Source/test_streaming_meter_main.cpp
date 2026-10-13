#include "StreamingMeter.h"
#include "ContinuousAnalysis.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <new>
#include <string>
#include <time.h>
#include <vector>

static thread_local bool watchAllocations = false;
static thread_local size_t allocations = 0;
void* operator new(size_t bytes)
{
    if (watchAllocations) ++allocations;
    if (auto* memory = std::malloc(std::max(size_t(1), bytes))) return memory;
    throw std::bad_alloc(); // Allocation instrumentation must not hide genuine OOM.
}
void* operator new[](size_t bytes) { return ::operator new(bytes); }
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete[](void* memory) noexcept { std::free(memory); }

static int checks = 0, failures = 0;
static void require(bool condition, const char* behavior)
{
    ++checks;
    if (!condition) { ++failures; std::cerr << "FAIL: " << behavior << '\n'; }
}

static void feed(KENNStreamingMeter& meter, int frames, double rate, double hz, double gain,
                 int64_t first = 0, bool inverted = false, bool mono = false)
{
    for (int sample = 0; sample < frames; ++sample)
    {
        const auto value = static_cast<float>(gain * std::sin(2.0 * juce::MathConstants<double>::pi * hz * static_cast<double>(first + sample) / rate));
        meter.push(value, mono ? 0.0f : inverted ? -value : value);
    }
}

static void feedWorker(KENNContinuousAnalysis& worker, double seconds, int64_t& hostSample, double rate = 48000.0)
{
    const auto total = static_cast<int>(std::round(seconds * rate));
    constexpr int block = 128; // Host frames per callback; partial final callbacks remain valid.
    for (int first = 0; first < total; first += block)
    {
        juce::AudioBuffer<float> audio(2, std::min(block, total - first));
        for (int sample = 0; sample < audio.getNumSamples(); ++sample)
        {
            const auto value = static_cast<float>(0.1 * std::sin(2.0 * juce::MathConstants<double>::pi * 997.0 * static_cast<double>(hostSample + sample) / rate));
            audio.setSample(0, sample, value); audio.setSample(1, sample, -value);
        }
        watchAllocations = true;
        worker.push(audio, true, { hostSample, true }); worker.drainPending();
        watchAllocations = false;
        hostSample += audio.getNumSamples();
    }
}

static void verifyMeter()
{
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        KENNStreamingMeter meter;
        watchAllocations = true;
        const auto prepared = meter.prepare(rate);
        watchAllocations = false;
        require(prepared, "Qualified sample rates prepare without dynamic storage");
        const auto bin = static_cast<int>(rate / 10.0);
        feed(meter, 4 * bin - 1, rate, 1000.0, std::pow(10.0, -23.0 / 20.0));
        require(!meter.snapshot().momentaryReady, "A partial 400 ms window is unavailable");
        meter.push(0.0f, 0.0f);
        require(meter.snapshot().momentaryReady && !meter.snapshot().shortTermReady, "Momentary warms at 400 ms, short-term at 3 seconds");
        feed(meter, 26 * bin, rate, 1000.0, std::pow(10.0, -23.0 / 20.0), 4 * bin);
        const auto steady = meter.snapshot();
        require(steady.endSample == static_cast<int64_t>(3 * rate) && steady.shortTermReady,
                "Thirty complete bins produce exactly 3 seconds of contiguous history");
        require(steady.momentaryLUFS && std::abs(*steady.momentaryLUFS + 23.0) < 0.1,
                "Generated Tech 3341 case 1 momentary calibration is within 0.1 LU");
        require(steady.shortTermLUFS && std::abs(*steady.shortTermLUFS + 23.0) < 0.1,
                "Generated Tech 3341 case 1 short-term calibration is within 0.1 LU");
        meter.reset();
        feed(meter, static_cast<int>(3 * rate), rate, 1000.0, std::pow(10.0, -33.0 / 20.0), 0, true);
        require(meter.snapshot().shortTermLUFS && std::abs(*meter.snapshot().shortTermLUFS + 33.0) < 0.1,
                "Opposite-phase stereo retains loudness instead of cancelling in a mono sum");
        meter.reset();
        feed(meter, static_cast<int>(3 * rate), rate, 1000.0, std::pow(10.0, -33.0 / 20.0), 0, false, true);
        require(meter.snapshot().shortTermLUFS && std::abs(*meter.snapshot().shortTermLUFS + 36.0103) < 0.1,
                "A single occupied channel is 3.01 LU below equal-level stereo");
        meter.reset();
        feed(meter, 4 * bin, rate, 997.0, 0.1);
        feed(meter, 26 * bin, rate, 997.0, 0.001, 4 * bin);
        require(meter.snapshot().shortTermLUFS && *meter.snapshot().shortTermLUFS < -28.5,
                "Short-term includes quiet energy instead of applying an integrated-loudness gate");
        meter.reset();
        watchAllocations = true;
        for (int sample = 0; sample < static_cast<int>(5 * rate); ++sample) meter.push(0.1f, 0.1f);
        watchAllocations = false;
        require(meter.snapshot().momentaryLUFS && *meter.snapshot().momentaryLUFS < -150.0,
                "Persistent high-pass state removes DC without repeating clip-start energy");
        meter.reset();
        for (int sample = 0; sample < static_cast<int>(3 * rate); ++sample) meter.push(0.0f, 0.0f);
        const auto silence = meter.snapshot();
        require(silence.momentaryReady && silence.shortTermReady && silence.truePeakReady
                    && !silence.momentaryLUFS && !silence.shortTermLUFS && !silence.truePeakDBTP,
                "Ready silence carries zero linear measurements and absent finite logarithms");
        meter.push(std::numeric_limits<float>::quiet_NaN(), 0.0f);
        require(!meter.snapshot().momentaryReady && !meter.snapshot().truePeakReady, "NaN retires all filter/window/peak history");
        feed(meter, 4 * bin, rate, 997.0, 0.1);
        require(meter.snapshot().momentaryReady && !meter.snapshot().shortTermReady, "Finite audio recovers through a fresh warm-up");
        meter.push(0.0f, std::numeric_limits<float>::infinity());
        require(!meter.snapshot().momentaryReady, "Infinity in either channel retires measurements");
        require(!meter.prepare(32000.0) && !meter.push(0.1f, 0.1f) && !meter.snapshot().truePeakReady,
                "Unsupported rates retire previous readings rather than reusing their coefficients");
    }
    KENNStreamingMeter first, other;
    first.prepare(48000.0); other.prepare(48000.0);
    feed(first, 144000, 48000.0, 997.0, 0.1); // Three seconds at 48 kHz.
    require(first.snapshot().shortTermReady && !other.snapshot().momentaryReady, "Each insert owns its filter and rolling history");
    require(allocations == 0, "Candidate preparation/processing and deterministic worker capture/drain allocate no C++ heap storage");
}

static void verifyWorkerRetirement()
{
    KENNContinuousAnalysis worker;
    int64_t host = 42; // A deliberately unaligned insert start, in host sample frames.
    worker.prepare(48000.0, false, true);
    feedWorker(worker, 3.2, host);
    auto frame = worker.snapshot();
    require(frame.valid && frame.streamingMeter.shortTermReady && frame.hostEndSample % 4800 == 0,
            "Worker candidate warms from its first complete host-aligned window");
    require(frame.streamingMeter.endSample % 4800 == 0, "Worker candidate bins remain aligned to existing publications");
    worker.invalidate();
    require(!worker.snapshot().streamingMeter.shortTermReady, "Source invalidation retires candidate readiness before draining");
    for (const auto& recent : worker.recentSnapshots())
        require(!recent.streamingMeter.shortTermReady, "Source invalidation retires candidate readings in paired history too");
    feedWorker(worker, 0.5, host);
    require(worker.snapshot().streamingMeter.momentaryReady && !worker.snapshot().streamingMeter.shortTermReady,
            "A source change needs fresh 400 ms/3-second history");
    feedWorker(worker, 3.0, host);
    host = 0;
    feedWorker(worker, 0.1, host);
    require(!worker.snapshot().streamingMeter.momentaryReady, "Seeking retires weighting, energy and FIR history together");
    feedWorker(worker, 3.0, host);
    juce::AudioBuffer<float> oversized(2, 20000); oversized.clear(); // Exceeds the 16,384-frame capture queue.
    worker.push(oversized, true, { host, true }); host += oversized.getNumSamples();
    require(!worker.snapshot().streamingMeter.shortTermReady, "A dropped callback immediately retires long-window candidate evidence");
    feedWorker(worker, 0.5, host);
    require(worker.snapshot().streamingMeter.momentaryReady && !worker.snapshot().streamingMeter.shortTermReady,
            "Queue overflow recovers without bridging old loudness into the new passage");
    juce::AudioBuffer<float> invalid(2, 128); invalid.clear(); invalid.setSample(1, 0, std::numeric_limits<float>::quiet_NaN());
    worker.push(invalid, true, { host, true }); worker.drainPending(); host += invalid.getNumSamples();
    require(!worker.snapshot().streamingMeter.momentaryReady, "Invalid worker audio cannot retain a prior loudness window");
    worker.prepare(48000.0, false);
    host = 0; feedWorker(worker, 3.1, host);
    require(worker.snapshot().valid && !worker.snapshot().streamingMeter.truePeakReady,
            "Production-default worker preparation leaves the candidate disabled");
    worker.prepare(32000.0, false, true);
    host = 0; feedWorker(worker, 0.5, host, 32000.0);
    require(worker.snapshot().valid && !worker.snapshot().streamingMeter.truePeakReady,
            "Unqualified rates retain existing analysis while candidate fields remain absent");
    require(allocations == 0, "Enabling the candidate adds no C++ heap allocation to callback or worker processing");
}

static int trace(int rate, const char* path)
{
    KENNStreamingMeter meter;
    if (!meter.prepare(rate)) { std::cerr << "Unsupported trace sample rate\n"; return 2; } // Refuse an unqualified trace.
    std::ifstream input(path, std::ios::binary);
    if (!input) { std::cerr << "Cannot read synthetic float32 input\n"; return 2; } // Missing fixtures must fail visibly.
    std::array<float, 2> sample {};
    std::cout << std::setprecision(17);
    while (input.read(reinterpret_cast<char*>(sample.data()), sizeof(sample)))
    {
        if (!meter.push(sample[0], sample[1])) continue; // Trace only complete 100 ms publications.
        const auto frame = meter.snapshot();
        std::cout << frame.endSample << ',' << frame.momentaryReady << ',' << frame.shortTermReady << ','
                  << frame.momentaryMeanSquare << ',' << frame.shortTermMeanSquare << ',' << frame.truePeakLinear << '\n';
    }
    if (!input.eof() || input.gcount() != 0) { std::cerr << "Truncated float32 stereo input\n"; return 2; } // Never silently ignore a partial frame.
    return 0;
}

static double cpuMilliseconds()
{
    timespec value {};
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &value) != 0) throw std::runtime_error("Process CPU clock unavailable"); // Wall time is not a CPU substitute.
    return 1000.0 * static_cast<double>(value.tv_sec) + static_cast<double>(value.tv_nsec) / 1e6;
}

static void profile(int repeats)
{
    std::cout << std::setprecision(17) << "{\"schema\":\"kenn.streaming_meter_native_profile.v1\",\"meter_bytes\":"
              << sizeof(KENNStreamingMeter) << ",\"compiler\":\"" << __VERSION__
#ifdef NDEBUG
              << "\",\"assertions_enabled\":false"
#else
              << "\",\"assertions_enabled\":true" // Debug timings must remain distinguishable from the Release receipt.
#endif
              << ",\"repeats\":" << repeats << ",\"cells\":[";
    bool firstCell = true;
    double checksum = 0.0;
    for (const int rate : { 44100, 48000, 96000 })
        for (const int inserts : { 1, 8, 32, 64 })
            for (const std::string mode : { "baseline_worker", "streaming_meter", "combined_worker" })
            {
                const int bin = rate / 10;
                std::vector<juce::AudioBuffer<float>> audio;
                std::vector<std::unique_ptr<KENNContinuousAnalysis>> workers;
                std::vector<KENNStreamingMeter> meters(static_cast<size_t>(inserts));
                for (int insert = 0; insert < inserts; ++insert)
                {
                    audio.emplace_back(2, bin);
                    for (int sample = 0; sample < bin; ++sample)
                    {
                        const auto gain = 0.08 + 0.04 * insert / std::max(1, inserts - 1); // Linear full-scale amplitude, distinct per insert.
                        audio.back().setSample(0, sample, static_cast<float>(gain * std::sin(2.0 * juce::MathConstants<double>::pi * 997.0 * sample / rate)));
                        audio.back().setSample(1, sample, static_cast<float>(gain * std::sin(2.0 * juce::MathConstants<double>::pi * 53.0 * sample / rate + 0.4))); // Radians.
                    }
                    meters[static_cast<size_t>(insert)].prepare(rate);
                    if (mode != "streaming_meter")
                    {
                        workers.push_back(std::make_unique<KENNContinuousAnalysis>());
                        workers.back()->prepare(rate, false, mode == "combined_worker");
                    }
                }
                const auto tick = [&](int index) {
                    for (int insert = 0; insert < inserts; ++insert)
                    {
                        const auto& buffer = audio[static_cast<size_t>(insert)];
                        if (mode == "streaming_meter")
                        {
                            auto& meter = meters[static_cast<size_t>(insert)];
                            for (int sample = 0; sample < bin; ++sample)
                                meter.push(buffer.getSample(0, sample), buffer.getSample(1, sample));
                            const auto frame = meter.snapshot();
                            if (index >= 29 && !frame.shortTermReady) throw std::runtime_error("Profile meter did not warm up"); // Never time a disabled/partial candidate as full work.
                            checksum += frame.momentaryMeanSquare;
                        }
                        else
                        {
                            auto& worker = *workers[static_cast<size_t>(insert)];
                            for (int offset = 0; offset < bin; offset += 128) // 128 host frames per synthetic callback.
                            {
                                std::array<float*, 2> channels { const_cast<float*>(buffer.getReadPointer(0) + offset), const_cast<float*>(buffer.getReadPointer(1) + offset) };
                                juce::AudioBuffer<float> block(channels.data(), 2, std::min(128, bin - offset));
                                worker.push(block, true, { static_cast<int64_t>(index) * bin + offset, true }); worker.drainPending();
                            }
                            const auto frame = worker.snapshot();
                            if (!frame.valid || frame.droppedSamples != 0 || frame.queuedPackets != 0
                                || (mode == "combined_worker" && index >= 29 && !frame.streamingMeter.shortTermReady))
                                throw std::runtime_error("Profile worker lost evidence"); // A timing cell with missing analysis cannot support a cost claim.
                            checksum += frame.features.rmsDbfs + frame.streamingMeter.momentaryMeanSquare;
                        }
                    }
                };
                constexpr int warmups = 32; // 3.2 seconds of untimed synthetic audio warm the 3-second history and FFTs.
                for (int index = 0; index < warmups; ++index) tick(index);
                if (!firstCell) std::cout << ',';
                firstCell = false;
                std::cout << "{\"rate\":" << rate << ",\"inserts\":" << inserts << ",\"mode\":\"" << mode
                          << "\",\"warmup_ticks\":" << warmups << ",\"wall_ms\":[";
                std::vector<double> cpu;
                for (int index = 0; index < repeats; ++index)
                {
                    const auto cpuStart = cpuMilliseconds();
                    const auto start = std::chrono::steady_clock::now();
                    tick(warmups + index);
                    const auto elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
                    cpu.push_back(cpuMilliseconds() - cpuStart);
                    if (index != 0) std::cout << ',';
                    std::cout << elapsed;
                }
                std::cout << "],\"cpu_ms\":[";
                for (size_t index = 0; index < cpu.size(); ++index) { if (index != 0) std::cout << ','; std::cout << cpu[index]; }
                std::cout << "],\"processing_passed\":true}";
            }
    std::cout << "],\"checksum\":" << checksum << "}\n";
}

int main(int argc, char** argv)
{
    try
    {
        if (argc == 4 && std::string(argv[1]) == "--trace") return trace(std::stoi(argv[2]), argv[3]);
        if (argc == 3 && std::string(argv[1]) == "--profile")
        {
            const int repeats = std::stoi(argv[2]);
            if (repeats < 3 || repeats > 100) throw std::runtime_error("Profile repeats must be between 3 and 100"); // Bound local CPU work.
            profile(repeats); return 0;
        }
        if (argc != 1) throw std::runtime_error("Use --trace RATE FLOAT32_STEREO or --profile REPEATS"); // Refuse ignored/mislabelled options.
        verifyMeter(); verifyWorkerRetirement();
        std::cout << checks << " streaming meter checks, " << failures << " failures\n";
        return failures == 0 ? 0 : 1;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n'; return 2; // Invalid fixtures/arguments are not passing verification.
    }
}
