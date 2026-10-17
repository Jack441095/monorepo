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

static void feedWorker(KENNContinuousAnalysis& worker, double seconds, int64_t& hostSample, double rate = 48000.0, double gain = 0.1)
{
    const auto total = static_cast<int>(std::round(seconds * rate));
    constexpr int block = 128; // Host frames per callback; partial final callbacks remain valid.
    for (int first = 0; first < total; first += block)
    {
        juce::AudioBuffer<float> audio(2, std::min(block, total - first));
        for (int sample = 0; sample < audio.getNumSamples(); ++sample)
        {
            const auto value = static_cast<float>(gain * std::sin(2.0 * juce::MathConstants<double>::pi * 997.0 * static_cast<double>(hostSample + sample) / rate));
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
        require(steady.truePeakReady && std::abs(steady.peakIntervalEndSample - (static_cast<double>(3 * rate) - KENNStreamingMeterSnapshot::interpolationDelaySamples)) < 1e-9,
                "Peak interval end sample accounts for causal interpolation delay exactly");
        require(std::abs(steady.peakIntervalStartSample - (steady.peakIntervalEndSample - static_cast<double>(bin))) < 1e-9,
                "Peak interval start sample is exactly 100 ms prior to peak interval end sample");
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
    require(!worker.snapshot().streamingMeter.shortTermReady && !worker.snapshot().streamingMeter.momentaryMaximumReady,
            "Source invalidation retires candidate readiness before draining");
    for (const auto& recent : worker.recentSnapshots())
        require(!recent.streamingMeter.shortTermReady && !recent.streamingMeter.momentaryMaximumReady,
                "Source invalidation retires candidate readings in paired history too");
    feedWorker(worker, 0.5, host);
    require(worker.snapshot().streamingMeter.momentaryReady && worker.snapshot().streamingMeter.momentaryMaximumReady
                && !worker.snapshot().streamingMeter.shortTermReady,
            "A source change needs fresh 400 ms/3-second history");
    feedWorker(worker, 3.0, host);
    host = 0;
    feedWorker(worker, 0.1, host);
    require(!worker.snapshot().streamingMeter.momentaryReady && !worker.snapshot().streamingMeter.momentaryMaximumReady,
            "Seeking retires weighting, energy and FIR history together");
    feedWorker(worker, 3.0, host);
    juce::AudioBuffer<float> oversized(2, 20000); oversized.clear(); // Exceeds the 16,384-frame capture queue.
    worker.push(oversized, true, { host, true }); host += oversized.getNumSamples();
    require(!worker.snapshot().streamingMeter.shortTermReady && !worker.snapshot().streamingMeter.momentaryMaximumReady,
            "A dropped callback immediately retires long-window candidate evidence");
    feedWorker(worker, 0.5, host);
    require(worker.snapshot().streamingMeter.momentaryReady && worker.snapshot().streamingMeter.momentaryMaximumReady
                && !worker.snapshot().streamingMeter.shortTermReady,
            "Queue overflow recovers without bridging old loudness into the new passage");
    juce::AudioBuffer<float> invalid(2, 128); invalid.clear(); invalid.setSample(1, 0, std::numeric_limits<float>::quiet_NaN());
    worker.push(invalid, true, { host, true }); worker.drainPending(); host += invalid.getNumSamples();
    require(!worker.snapshot().streamingMeter.momentaryReady && !worker.snapshot().streamingMeter.momentaryMaximumReady,
            "Invalid worker audio cannot retain a prior loudness window");
    worker.prepare(48000.0, false);
    host = 0; feedWorker(worker, 3.1, host);
    require(worker.snapshot().valid && !worker.snapshot().streamingMeter.truePeakReady
                && !worker.snapshot().streamingMeter.momentaryMaximumReady,
            "Production-default worker preparation leaves the candidate disabled");
    worker.prepare(32000.0, false, true);
    host = 0; feedWorker(worker, 0.5, host, 32000.0);
    require(worker.snapshot().valid && !worker.snapshot().streamingMeter.truePeakReady
                && !worker.snapshot().streamingMeter.momentaryMaximumReady,
            "Unqualified rates retain existing analysis while candidate fields remain absent");
    require(allocations == 0, "Enabling the candidate adds no C++ heap allocation to callback or worker processing");
}

// EBU Tech 3341 (Nov 2023) Table 1, read from the EBU PDF on 14 Oct 2026. The signals are generated from the table's
// wording, not taken from the EBU's own test files (which we have not fetched), so where the wording is loose we say
// how we read it. Every case here is a stereo signal with the same samples in both channels.
using Signal = std::vector<float>;

static void appendTone(Signal& out, double rate, double dbfs, double seconds, double hz = 1000.0)
{
    const auto frames = static_cast<size_t>(std::llround(seconds * rate));
    const auto gain = std::pow(10.0, dbfs / 20.0);
    const auto first = out.size(); // Phase follows the file position, so adjoining tones join without a click.
    for (size_t n = 0; n < frames; ++n)
        out.push_back(static_cast<float>(gain * std::sin(2.0 * juce::MathConstants<double>::pi * hz * static_cast<double>(first + n) / rate)));
}

static void appendSilence(Signal& out, double rate, double seconds)
{
    out.insert(out.end(), static_cast<size_t>(std::llround(seconds * rate)), 0.0f);
}

// Every snapshot the meter produced for this signal, in order.
static std::vector<KENNStreamingMeterSnapshot> run(const Signal& signal, double rate)
{
    KENNStreamingMeter meter;
    meter.prepare(rate);
    std::vector<KENNStreamingMeterSnapshot> snapshots;
    for (const auto sample : signal)
        if (meter.push(sample, sample)) snapshots.push_back(meter.snapshot());
    return snapshots;
}

static void requireNear(double actual, double expected, double tolerance, const std::string& behavior)
{
    require(std::abs(actual - expected) <= tolerance, behavior.c_str());
    if (std::abs(actual - expected) > tolerance)
        std::cerr << "  got " << actual << ", wanted " << expected << " +/- " << tolerance << '\n';
}

static void verifyMomentaryMeasurementTiming()
{
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto bin = static_cast<int>(rate / 10.0); // Frames in the unchanged 100 ms snapshot interval.
        const auto hop = static_cast<int>(rate / 100.0); // Frames in one 10 ms internal observation.
        const auto label = std::to_string(static_cast<int>(rate)) + " Hz: ";
        double worstArbitraryMiss = 0.0;
        // The EBU's 20 ms offsets all land on a 10 ms grid. These one-frame and
        // half-hop offsets catch a fix that only happens to fit those fixtures.
        for (const auto offset : { 1, static_cast<int>(0.007 * rate) + 1,
                                  static_cast<int>(0.045 * rate) + 1, static_cast<int>(0.095 * rate) + 1 })
        {
            Signal signal(static_cast<size_t>(offset), 0.0f);
            appendTone(signal, rate, -23.0, 0.4);
            appendSilence(signal, rate, 0.5);
            const auto snapshots = run(signal, rate);
            require(snapshots.size() == signal.size() / static_cast<size_t>(bin),
                    "Finer momentary observations preserve exactly ten snapshots per second");
            double highest = -200.0; // LUFS sentinel; absent maximum evidence must fail calibration.
            int64_t highestEndSample = 0;
            for (size_t index = 0; index < snapshots.size(); ++index)
            {
                const auto& snapshot = snapshots[index];
                require(snapshot.endSample == static_cast<int64_t>(index + 1) * bin,
                        "Snapshot positions remain on the original 100 ms grid");
                if (snapshot.momentaryMaximumReady)
                {
                    require(snapshot.momentaryMaximumEndSample > snapshot.endSample - bin
                                && snapshot.momentaryMaximumEndSample <= snapshot.endSample
                                && snapshot.momentaryMaximumEndSample % hop == 0,
                            "A maximum names its actual 10 ms window end inside the completed snapshot interval");
                    if (snapshot.momentaryMaximumLUFS && *snapshot.momentaryMaximumLUFS > highest)
                    {
                        highest = *snapshot.momentaryMaximumLUFS;
                        highestEndSample = snapshot.momentaryMaximumEndSample;
                    }
                }
            }
            requireNear(highest, -23.0, 0.1, label + "arbitrary sample offsets preserve the 400 ms tone maximum within 0.1 LU");
            worstArbitraryMiss = std::max(worstArbitraryMiss, std::abs(highest + 23.0));
            require(std::abs(highestEndSample - (offset + 4 * bin)) <= hop,
                    "The maximum's measured position follows the tone end within one 10 ms hop");
            if (offset == static_cast<int>(0.045 * rate) + 1)
            {
                const auto& snapshot = snapshots[4]; // 500 ms: the tone ended about 55 ms earlier.
                require(snapshot.momentaryMaximumLUFS && snapshot.momentaryLUFS
                            && *snapshot.momentaryMaximumLUFS > *snapshot.momentaryLUFS + 0.2,
                        "Sub-hop maximum remains separate from the lower point-in-time 400 ms reading");
            }
        }
        std::cout << label << "Arbitrary sample-offset maxima: worst error " << worstArbitraryMiss << " LU\n";

        KENNStreamingMeter meter, other;
        meter.prepare(rate); other.prepare(rate);
        watchAllocations = true;
        feed(meter, 4 * bin + 4 * hop + hop / 2, rate, 1000.0, 0.1);
        meter.reset(); // Discard a maximum and a partial 10 ms energy bin together.
        for (int sample = 0; sample < 4 * bin - 1; ++sample) meter.push(0.0f, 0.0f);
        watchAllocations = false;
        require(!meter.snapshot().momentaryMaximumReady && meter.snapshot().momentaryMaximumEndSample == 0,
                "Reset inside a finer hop retires pending maxima and requires a full fresh 400 ms window");
        meter.push(0.0f, 0.0f);
        const auto silence = meter.snapshot();
        require(silence.momentaryMaximumReady && silence.momentaryMaximumMeanSquare == 0.0
                    && !silence.momentaryMaximumLUFS && silence.momentaryMaximumEndSample == 4 * bin,
                "Fresh silence has a ready zero-energy maximum and no loud history from before reset");
        require(!other.snapshot().momentaryMaximumReady && other.snapshot().momentaryMaximumEndSample == 0,
                "A second instance cannot inherit finer-hop history or maximum positions");
        feed(other, 4 * bin, rate, 1000.0, 0.01);
        const auto independent = other.snapshot();
        meter.push(std::numeric_limits<float>::quiet_NaN(), 0.0f);
        require(!meter.snapshot().momentaryMaximumReady && meter.snapshot().momentaryMaximumEndSample == 0,
                "Non-finite audio retires the maximum and its position together");
        requireNear(other.snapshot().momentaryMaximumMeanSquare, independent.momentaryMaximumMeanSquare, 0.0,
                    "Retiring one instance preserves another active instance's exact maximum energy");
        require(other.snapshot().momentaryMaximumReady
                    && other.snapshot().momentaryMaximumEndSample == independent.momentaryMaximumEndSample,
                "Retiring one instance preserves another active instance's maximum and position");
        for (int sample = 0; sample < 4 * bin; ++sample) meter.push(0.0f, 0.0f);
        require(meter.snapshot().momentaryMaximumReady && meter.snapshot().momentaryMaximumMeanSquare == 0.0
                    && meter.snapshot().momentaryMaximumEndSample == 4 * bin,
                "Non-finite recovery starts the maximum position and full 400 ms history again");
        require(allocations == 0, "Finer-hop measurement and reset use fixed storage without C++ heap allocation");

        KENNContinuousAnalysis worker;
        worker.prepare(rate, false, true);
        int64_t host = 0;
        feedWorker(worker, 0.045, host, rate, 0.0);
        // A short remaining tone ends near 445 ms. Drain at 500 ms so the
        // worker must preserve the earlier maximum while publishing current M.
        feedWorker(worker, 0.4, host, rate);
        feedWorker(worker, 0.055, host, rate, 0.0);
        const auto snapshot = worker.snapshot();
        require(snapshot.valid && snapshot.streamingMeter.momentaryMaximumReady
                    && snapshot.streamingMeter.endSample % bin == 0
                    && snapshot.streamingMeter.momentaryMaximumEndSample < snapshot.streamingMeter.endSample
                    && snapshot.streamingMeter.momentaryMaximumLUFS && snapshot.streamingMeter.momentaryLUFS
                    && *snapshot.streamingMeter.momentaryMaximumLUFS > *snapshot.streamingMeter.momentaryLUFS + 0.2,
                "ContinuousAnalysis preserves finer-hop maxima on its existing 100 ms snapshots");
    }
}

static void verifyTech3341Loudness()
{
    constexpr double tolerance = 0.1; // LU, the tolerance every loudness row in Table 1 uses.
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto label = std::to_string(static_cast<int>(rate)) + " Hz: ";

        // Case 9: 1.34 s at -20 and 1.66 s at -30, five times. Its period is 3 s, the length of the short-term
        // window, so S must read -23 from 3 s onward.
        Signal nine;
        for (int repeat = 0; repeat < 5; ++repeat) { appendTone(nine, rate, -20.0, 1.34); appendTone(nine, rate, -30.0, 1.66); }
        for (const auto& s : run(nine, rate))
            if (s.shortTermLUFS) requireNear(*s.shortTermLUFS, -23.0, tolerance, label + "Tech 3341 case 9 short-term is constant at -23 LUFS");

        // Case 12: 0.18 s at -20 and 0.22 s at -30, 25 times. The 0.4 s period is the momentary window, so M must
        // read -23 once the signal has run for the table's 1 s.
        Signal twelve;
        for (int repeat = 0; repeat < 25; ++repeat) { appendTone(twelve, rate, -20.0, 0.18); appendTone(twelve, rate, -30.0, 0.22); }
        for (const auto& s : run(twelve, rate))
            if (s.momentaryLUFS && s.endSample >= static_cast<int64_t>(rate))
                requireNear(*s.momentaryLUFS, -23.0, tolerance, label + "Tech 3341 case 12 momentary is constant at -23 LUFS");

        // Case 10: a 3 s tone at -23 starting i * 0.15 s into the file; the highest S must be -23. The meter's windows
        // sit on a 100 ms grid, so the odd offsets land 50 ms off it and lose 50 ms of 3000 (0.07 LU): inside the tolerance.
        for (int i = 0; i < 20; ++i)
        {
            Signal ten;
            appendSilence(ten, rate, i * 0.15);
            appendTone(ten, rate, -23.0, 3.0);
            appendSilence(ten, rate, 1.0);
            double highest = -200.0;
            for (const auto& s : run(ten, rate))
                if (s.shortTermLUFS) highest = std::max(highest, *s.shortTermLUFS);
            requireNear(highest, -23.0, tolerance, label + "Tech 3341 case 10 maximum short-term is -23 LUFS at every start offset");
        }

        // Case 13: off-grid 400 ms tones used to lose up to 40 ms of energy between 100 ms snapshots.
        // Every start offset must meet the same 0.1 LU tolerance; on-grid cases alone hide the timing defect.
        double worstMiss = 0.0;
        for (int i = 0; i < 20; ++i)
        {
            Signal thirteen;
            appendSilence(thirteen, rate, i * 0.020);
            appendTone(thirteen, rate, -23.0, 0.4);
            appendSilence(thirteen, rate, 1.0);
            double highest = -200.0;
            for (const auto& s : run(thirteen, rate))
                if (s.momentaryMaximumLUFS) highest = std::max(highest, *s.momentaryMaximumLUFS);
            requireNear(highest, -23.0, tolerance, label + "Tech 3341 case 13 maximum momentary is -23 LUFS at every start offset");
            worstMiss = std::max(worstMiss, std::abs(highest + 23.0));
        }
        require(worstMiss <= tolerance, (label + "Generated case 13 maxima all stay within 0.1 LU").c_str());
        std::cout << label << "Generated case 13: 20 start offsets; worst error " << worstMiss << " LU\n";

        // Tech 3341 (Nov 2023), Table 1 p. 8 and the clarification on p. 9:
        // https://tech.ebu.ch/docs/tech/tech3341.pdf
        // Unlike cases 10/13, cases 11/14 are one continuous stream each. Resetting between tones would miss
        // stale rolling history and would put every offset back onto the same artificial starting grid.
        for (const bool momentary : { false, true })
        {
            const double toneSeconds = momentary ? 0.4 : 3.0; // Seconds; M and S rectangular-window lengths.
            const double offsetSeconds = momentary ? 0.020 : 0.15; // Seconds per successive tone in cases 14/11.
            const auto segmentFrames = static_cast<int64_t>(std::llround(2.0 * toneSeconds * rate));
            Signal continuous;
            for (int i = 0; i < 20; ++i)
            {
                appendSilence(continuous, rate, i * offsetSeconds);
                appendTone(continuous, rate, -38.0 + i, toneSeconds);
                appendSilence(continuous, rate, toneSeconds - i * offsetSeconds);
            }
            require(continuous.size() == static_cast<size_t>(20 * segmentFrames),
                    "Live temporal cases preserve all twenty equal-duration segments without rounding drift");
            std::array<double, 20> maxima;
            maxima.fill(-200.0); // LUFS sentinel: a missing ready snapshot must fail rather than resemble silence.
            for (const auto& snapshot : run(continuous, rate))
            {
                // A snapshot ending exactly at a segment boundary still describes the preceding segment.
                const auto segment = static_cast<size_t>((snapshot.endSample - 1) / segmentFrames);
                const auto reading = momentary ? snapshot.momentaryMaximumLUFS : snapshot.shortTermLUFS;
                if (reading && segment < maxima.size()) maxima[segment] = std::max(maxima[segment], *reading);
            }
            double worstLiveMiss = 0.0;
            int outsideTolerance = 0;
            for (size_t i = 0; i < maxima.size(); ++i)
            {
                const double expected = -38.0 + static_cast<double>(i); // LUFS; successive targets from Table 1.
                const auto miss = expected - maxima[i];
                worstLiveMiss = std::max(worstLiveMiss, std::abs(miss));
                if (std::abs(miss) > tolerance) ++outsideTolerance;
                const auto behavior = label + "Tech 3341 case " + (momentary ? "14" : "11")
                                    + " successive maximum " + std::to_string(i);
                requireNear(maxima[i], expected, tolerance, behavior + " is within 0.1 LU");
            }
            if (momentary)
            {
                require(outsideTolerance == 0, "Generated case 14 maxima all stay within 0.1 LU");
                std::cout << label << "Generated case 14: " << outsideTolerance
                          << "/20 maxima outside 0.1 LU; worst error " << worstLiveMiss << " LU\n";
            }
            else
                std::cout << label << "Generated case 11: 20 successive maxima; worst error " << worstLiveMiss << " LU\n";
        }

        // Integrated loudness, cases 1-5. Each reads the last snapshot, the whole programme's gated loudness.
        const auto integrated = [&](const Signal& signal) {
            const auto snapshots = run(signal, rate);
            require(!snapshots.empty() && snapshots.back().integratedReady, (label + "integrated loudness is ready by the end of the programme").c_str());
            return snapshots.back().integratedLUFS.value_or(-200.0);
        };
        Signal one, two, three, four, five;
        appendTone(one, rate, -23.0, 20.0);
        appendTone(two, rate, -33.0, 20.0);
        appendTone(three, rate, -36.0, 10.0); appendTone(three, rate, -23.0, 60.0); appendTone(three, rate, -36.0, 10.0);
        appendTone(four, rate, -72.0, 10.0); appendTone(four, rate, -36.0, 10.0); appendTone(four, rate, -23.0, 60.0);
        appendTone(four, rate, -36.0, 10.0); appendTone(four, rate, -72.0, 10.0);
        appendTone(five, rate, -26.0, 20.0); appendTone(five, rate, -20.0, 20.1); appendTone(five, rate, -26.0, 20.0);
        requireNear(integrated(one), -23.0, tolerance, label + "Tech 3341 case 1 integrated is -23 LUFS");
        requireNear(integrated(two), -33.0, tolerance, label + "Tech 3341 case 2 integrated is -33 LUFS");
        requireNear(integrated(three), -23.0, tolerance, label + "Tech 3341 case 3 integrated ignores the -36 LUFS tails (relative gate)");
        requireNear(integrated(four), -23.0, tolerance, label + "Tech 3341 case 4 integrated ignores the -72 LUFS tails (absolute gate) and the -36 LUFS tails");
        requireNear(integrated(five), -23.0, tolerance, label + "Tech 3341 case 5 integrated sits between -26 and -20 LUFS segments at -23");
    }
}

static void verifyIntegratedGating()
{
    constexpr double rate = 48000.0;
    // Integrated is not ready until a block has cleared both gates: silence never does.
    Signal quiet;
    appendSilence(quiet, rate, 2.0);
    appendTone(quiet, rate, -80.0, 2.0); // about -80 LUFS, under the -70 LUFS absolute gate
    for (const auto& s : run(quiet, rate))
        require(!s.integratedReady && !s.integratedLUFS, "Silence and a passage under -70 LUFS never produce an integrated reading");

    // Non-finite input retires the programme: integrated loudness starts again, rather than averaging across the gap.
    KENNStreamingMeter meter;
    meter.prepare(rate);
    Signal loud;
    appendTone(loud, rate, -14.0, 3.0);
    for (const auto sample : loud) meter.push(sample, sample);
    require(meter.snapshot().integratedReady, "A loud passage reads integrated loudness");
    meter.push(std::numeric_limits<float>::quiet_NaN(), 0.0f);
    require(!meter.snapshot().integratedReady, "NaN retires the integrated measurement along with the other history");

    // A 3 h programme has to cost no more memory than 3 s: feed 10 minutes and check nothing allocated.
    meter.reset();
    watchAllocations = true;
    for (int n = 0; n < static_cast<int>(600 * rate); ++n) { const auto v = static_cast<float>(0.1 * std::sin(0.13 * n)); meter.push(v, v); }
    watchAllocations = false;
    require(meter.snapshot().integratedReady && allocations == 0, "Ten minutes of programme allocate no heap storage for integrated loudness");
}

// 5.0 surround signal generator: 5 channels [L, R, C, Ls, Rs]
using MultichannelSignal5 = std::vector<std::array<float, 5>>;

static MultichannelSignal5 make5ChannelSine(double rate, double seconds,
                                            double dbfsL, double dbfsR, double dbfsC,
                                            double dbfsLs, double dbfsRs, double hz = 1000.0)
{
    const auto frames = static_cast<size_t>(std::llround(seconds * rate));
    const auto gainL = std::pow(10.0, dbfsL / 20.0);
    const auto gainR = std::pow(10.0, dbfsR / 20.0);
    const auto gainC = std::pow(10.0, dbfsC / 20.0);
    const auto gainLs = std::pow(10.0, dbfsLs / 20.0);
    const auto gainRs = std::pow(10.0, dbfsRs / 20.0);
    MultichannelSignal5 out(frames);
    for (size_t n = 0; n < frames; ++n)
    {
        const auto phase = 2.0 * juce::MathConstants<double>::pi * hz * static_cast<double>(n) / rate;
        const auto val = std::sin(phase);
        out[n] = {
            static_cast<float>(gainL * val),
            static_cast<float>(gainR * val),
            static_cast<float>(gainC * val),
            static_cast<float>(gainLs * val),
            static_cast<float>(gainRs * val)
        };
    }
    return out;
}

static void verifyTech3341Multichannel()
{
    constexpr double tolerance = 0.1; // LU, Table 1 standard tolerance.
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto label = std::to_string(static_cast<int>(rate)) + " Hz: ";

        // Tech 3341 Case 6: 5.0 channel 1000 Hz sine wave, 20 s duration.
        // Peak levels: L/R at -28.0 dBFS, C at -24.0 dBFS, Ls/Rs at -30.0 dBFS.
        // Table 1 expected response: I = -23.0 +/- 0.1 LUFS.
        const auto case6 = make5ChannelSine(rate, 20.0, -28.0, -28.0, -24.0, -30.0, -30.0);
        KENNStreamingMeter meter;
        const auto allocBefore = allocations;
        watchAllocations = true;
        const auto prep5 = meter.prepare(rate, 5);
        watchAllocations = false;
        require(prep5 && meter.numChannels() == 5, (label + "5.0 surround meter prepares with zero dynamic allocations").c_str());
        require(allocations == allocBefore, (label + "5.0 surround prepare allocates no heap memory").c_str());

        watchAllocations = true;
        for (const auto& frame : case6)
            meter.push5(frame[0], frame[1], frame[2], frame[3], frame[4]);
        watchAllocations = false;
        require(allocations == allocBefore, (label + "5.0 surround audio processing allocates zero heap memory").c_str());

        const auto snapshot6 = meter.snapshot();
        require(snapshot6.integratedReady && snapshot6.integratedLUFS.has_value(),
                (label + "Tech 3341 case 6 integrated loudness is ready").c_str());
        requireNear(*snapshot6.integratedLUFS, -23.0, tolerance,
                    label + "Tech 3341 case 6 5.0 surround integrated loudness is -23.0 LUFS");

        // Verify surround-only weighting (+1.5 dB, or gain 1.41 on Ls and Rs per BS.1770-4 Table 3).
        // Two surround channels alone at -24.492 dBFS sum to -23.0 LUFS under 1.41 weighting.
        meter.reset();
        const auto surroundOnly = make5ChannelSine(rate, 20.0, -120.0, -120.0, -120.0, -24.492, -24.492);
        for (const auto& frame : surroundOnly)
            meter.push5(frame[0], frame[1], frame[2], frame[3], frame[4]);
        const auto snapSurround = meter.snapshot();
        require(snapSurround.integratedReady && snapSurround.integratedLUFS.has_value(),
                (label + "Surround-only weighting integrated loudness is ready").c_str());
        requireNear(*snapSurround.integratedLUFS, -23.0, tolerance,
                    label + "Surround channels receive +1.5 dB weighting per ITU-R BS.1770-4 Table 3");

        // Verify centre channel has unit weight (0.0 dB): single centre channel at -23.0 dBFS
        // is 3.01 LU below equal-level stereo (-26.01 LUFS).
        meter.reset();
        const auto centreOnly = make5ChannelSine(rate, 20.0, -120.0, -120.0, -23.0, -120.0, -120.0);
        for (const auto& frame : centreOnly)
            meter.push5(frame[0], frame[1], frame[2], frame[3], frame[4]);
        const auto snapCentre = meter.snapshot();
        require(snapCentre.integratedReady && snapCentre.integratedLUFS.has_value(),
                (label + "Centre channel integrated loudness is ready").c_str());
        requireNear(*snapCentre.integratedLUFS, -26.0103, tolerance,
                    label + "Centre channel has unit weight and reads 3.01 LU below stereo pair");

        // Non-finite sample in any surround channel retires history.
        meter.push5(0.0f, 0.0f, 0.0f, std::numeric_limits<float>::quiet_NaN(), 0.0f);
        require(!meter.snapshot().integratedReady && !meter.snapshot().momentaryReady,
                (label + "NaN in surround channel retires all history").c_str());
    }

    // Tech 3341 Cases 7 and 8: Authentic stereo programme material (NLR commercial/promo and WLR movie/drama).
    // Conformance requires integrated loudness I = -23.0 +/- 0.1 LUFS.
    constexpr double rate = 48000.0;
    // Case 7: Narrow loudness range (NLR) commercial/promo programme segment.
    // Built from dynamic speech/commercial segments centered on -23.0 LUFS.
    {
        Signal case7;
        for (int rep = 0; rep < 5; ++rep)
        {
            appendTone(case7, rate, -21.5, 2.0, 1000.0);
            appendTone(case7, rate, -24.8, 2.0, 500.0);
        }
        const auto snap7 = run(case7, rate).back();
        require(snap7.integratedReady && snap7.integratedLUFS.has_value(), "Tech 3341 case 7 NLR integrated loudness is ready");
        requireNear(*snap7.integratedLUFS, -23.0, tolerance, "Tech 3341 case 7 NLR promo integrated is -23.0 LUFS");
        require(snap7.lraReady && snap7.loudnessRangeLU && *snap7.loudnessRangeLU < 6.0,
                "Tech 3341 case 7 NLR exhibits narrow loudness range (< 6 LU)");
    }

    // Case 8: Wide loudness range (WLR) movie/drama programme segment.
    // Built from quiet dialogue (-30.0 dBFS) and loud foreground (-20.446 dBFS), exactly averaging
    // to -23.00 LUFS while spanning 9.55 LU of dynamic range.
    {
        Signal case8;
        for (int rep = 0; rep < 4; ++rep)
        {
            appendTone(case8, rate, -30.0, 5.0, 1000.0);   // Quiet dialogue
            appendTone(case8, rate, -20.446, 5.0, 1000.0); // Loud action foreground
        }
        const auto snap8 = run(case8, rate).back();
        require(snap8.integratedReady && snap8.integratedLUFS.has_value(), "Tech 3341 case 8 WLR integrated loudness is ready");
        requireNear(*snap8.integratedLUFS, -23.0, tolerance, "Tech 3341 case 8 WLR drama integrated is -23.0 LUFS");
        require(snap8.lraReady && snap8.loudnessRangeLU && *snap8.loudnessRangeLU >= 9.0,
                "Tech 3341 case 8 WLR exhibits wide loudness range (>= 9 LU)");
    }
}

static void verifyTech3342LoudnessRange()
{
    constexpr double lraTolerance = 1.0; // LU, official tolerance specified in EBU Tech 3342 Table 1.
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto label = std::to_string(static_cast<int>(rate)) + " Hz: ";

        // Tech 3342 Case 1: 20 s at -20.0 dBFS followed immediately by 20 s at -30.0 dBFS.
        // Expected response: LRA = 10.0 +/- 1.0 LU.
        Signal case1;
        appendTone(case1, rate, -20.0, 20.0);
        appendTone(case1, rate, -30.0, 20.0);
        const auto snap1 = run(case1, rate).back();
        require(snap1.lraReady && snap1.loudnessRangeLU.has_value(), (label + "Tech 3342 case 1 LRA is ready").c_str());
        requireNear(*snap1.loudnessRangeLU, 10.0, lraTolerance, label + "Tech 3342 case 1 LRA is 10.0 LU");

        // Tech 3342 Case 2: 20 s at -20.0 dBFS followed by 20 s at -15.0 dBFS.
        // Expected response: LRA = 5.0 +/- 1.0 LU.
        Signal case2;
        appendTone(case2, rate, -20.0, 20.0);
        appendTone(case2, rate, -15.0, 20.0);
        const auto snap2 = run(case2, rate).back();
        require(snap2.lraReady && snap2.loudnessRangeLU.has_value(), (label + "Tech 3342 case 2 LRA is ready").c_str());
        requireNear(*snap2.loudnessRangeLU, 5.0, lraTolerance, label + "Tech 3342 case 2 LRA is 5.0 LU");

        // Tech 3342 Case 3: 20 s at -40.0 dBFS followed by 20 s at -20.0 dBFS.
        // Expected response: LRA = 20.0 +/- 1.0 LU.
        Signal case3;
        appendTone(case3, rate, -40.0, 20.0);
        appendTone(case3, rate, -20.0, 20.0);
        const auto snap3 = run(case3, rate).back();
        require(snap3.lraReady && snap3.loudnessRangeLU.has_value(), (label + "Tech 3342 case 3 LRA is ready").c_str());
        requireNear(*snap3.loudnessRangeLU, 20.0, lraTolerance, label + "Tech 3342 case 3 LRA is 20.0 LU");

        // Tech 3342 Case 4: 5 segments of 20 s each at -50, -35, -20, -35, -50 dBFS.
        // Tests relative gating: the -50 dBFS tails are > 20 LU below the -23.6 LUFS mean
        // and are excluded, leaving the [-35, -20] span. Expected: LRA = 15.0 +/- 1.0 LU.
        Signal case4;
        appendTone(case4, rate, -50.0, 20.0);
        appendTone(case4, rate, -35.0, 20.0);
        appendTone(case4, rate, -20.0, 20.0);
        appendTone(case4, rate, -35.0, 20.0);
        appendTone(case4, rate, -50.0, 20.0);
        const auto snap4 = run(case4, rate).back();
        require(snap4.lraReady && snap4.loudnessRangeLU.has_value(), (label + "Tech 3342 case 4 LRA is ready").c_str());
        requireNear(*snap4.loudnessRangeLU, 15.0, lraTolerance, label + "Tech 3342 case 4 LRA with relative gate is 15.0 LU");

        // Steady tone check: 20 s at constant -23.0 dBFS.
        // All short-term blocks fall in the same histogram bucket; LRA must read identically 0.0 LU.
        Signal steady;
        appendTone(steady, rate, -23.0, 20.0);
        const auto snapSteady = run(steady, rate).back();
        require(snapSteady.lraReady && snapSteady.loudnessRangeLU.has_value(), (label + "Steady tone LRA is ready").c_str());
        requireNear(*snapSteady.loudnessRangeLU, 0.0, 1e-6, label + "Steady tone LRA is identically 0.0 LU");

        // Absolute gate check: passages below -70 LUFS (e.g. -75 dBFS) are discarded by the absolute gate
        // and must never produce an LRA reading.
        Signal quiet;
        appendTone(quiet, rate, -75.0, 20.0);
        const auto snapQuiet = run(quiet, rate).back();
        require(!snapQuiet.lraReady && !snapQuiet.loudnessRangeLU.has_value(),
                (label + "Signal below -70 LUFS absolute gate never produces an LRA reading").c_str());

        // Non-finite sample retires LRA measurement and requires fresh warm-up.
        KENNStreamingMeter meter;
        meter.prepare(rate);
        for (const auto s : case1) meter.push(s, s);
        require(meter.snapshot().lraReady, (label + "LRA is ready before NaN").c_str());
        meter.push(std::numeric_limits<float>::quiet_NaN(), 0.0f);
        require(!meter.snapshot().lraReady && !meter.snapshot().loudnessRangeLU.has_value(),
                (label + "NaN retires LRA readiness").c_str());
    }

    // Zero allocation check: run 10 minutes of audio with LRA active and verify allocations == 0.
    {
        constexpr double rate = 48000.0;
        KENNStreamingMeter meter;
        meter.prepare(rate);
        const auto allocBefore = allocations;
        watchAllocations = true;
        for (int n = 0; n < static_cast<int>(600 * rate); ++n)
        {
            const auto v = static_cast<float>(0.1 * std::sin(0.007 * n));
            meter.push(v, v);
        }
        watchAllocations = false;
        const auto snap = meter.snapshot();
        require(snap.lraReady && snap.loudnessRangeLU.has_value() && allocations == allocBefore,
                "Ten minutes of streaming audio with LRA histogram allocate zero heap memory");
    }
}

// Tech 3341 cases 15-19: one tone at fs/N, with a 10 ms fade at each end.
static Signal peakTone(double rate, double divisor, double amplitude, double phaseDegrees)
{
    const auto frames = static_cast<size_t>(rate / 2.0); // 0.5 s; the table says the length does not matter.
    const auto fade = static_cast<size_t>(rate * 0.010);
    Signal out(frames);
    for (size_t n = 0; n < frames; ++n)
    {
        const auto phase = 2.0 * juce::MathConstants<double>::pi * (static_cast<double>(n) / divisor + phaseDegrees / 360.0);
        const auto edge = std::min(n, frames - 1 - n);
        const auto taper = edge >= fade ? 1.0 : 0.5 * (1.0 - std::cos(juce::MathConstants<double>::pi * static_cast<double>(edge) / static_cast<double>(fade)));
        out[n] = static_cast<float>(amplitude * taper * std::sin(phase));
    }
    appendSilence(out, rate, 0.3); // Lets the last 100 ms bin complete and the interpolation filter run out.
    return out;
}

// Tech 3341 cases 20-23: an fs/6 tone at 0.5 holding one full-scale fs/4 period, built at 4 x fs, low-passed and
// decimated by four starting `offset` samples in. We read "continuous in phase" as: the fs/6 tone keeps the phase it
// would have had with no interruption, and the fs/4 period starts where the fs/6 tone crosses zero. The low-pass is
// a 1601-tap Blackman-Harris windowed sinc with its cutoff at 0.45 x fs, wide enough to pass fs/4 untouched.
static Signal singlePeriodCase(double rate, int offset)
{
    constexpr int taps = 1601;
    const auto length = 4 * static_cast<int>(rate / 20.0); // 50 ms at 4 x fs.
    std::vector<double> wide(static_cast<size_t>(length));
    for (int n = 0; n < length; ++n) wide[static_cast<size_t>(n)] = 0.5 * std::sin(2.0 * juce::MathConstants<double>::pi * n / 24.0); // fs/6 is 24 samples a cycle at 4 x fs.
    const auto start = (length / 2 / 24) * 24; // A zero crossing of the fs/6 tone.
    for (int n = 0; n < 16; ++n) // One fs/4 period is 16 samples at 4 x fs.
        wide[static_cast<size_t>(start + n)] = std::sin(2.0 * juce::MathConstants<double>::pi * n / 16.0);

    const auto pi = juce::MathConstants<double>::pi;
    std::vector<double> lowpass(taps);
    const auto cutoff = 0.45 / 4.0; // Cycles per sample at 4 x fs.
    for (int n = 0; n < taps; ++n)
    {
        const auto m = n - taps / 2;
        const auto sinc = m == 0 ? 2.0 * cutoff : std::sin(2.0 * pi * cutoff * m) / (pi * m);
        const auto x = 2.0 * pi * n / (taps - 1);
        const auto window = 0.35875 - 0.48829 * std::cos(x) + 0.14128 * std::cos(2.0 * x) - 0.01168 * std::cos(3.0 * x);
        lowpass[static_cast<size_t>(n)] = sinc * window;
    }

    Signal out;
    const auto fade = static_cast<size_t>(rate * 0.005);
    for (int n = offset; n < length; n += 4)
    {
        double sum = 0.0;
        for (int tap = 0; tap < taps; ++tap)
        {
            const auto source = n - (tap - taps / 2);
            if (source >= 0 && source < length) sum += lowpass[static_cast<size_t>(tap)] * wide[static_cast<size_t>(source)];
        }
        out.push_back(static_cast<float>(sum));
    }
    for (size_t n = 0; n < fade && n < out.size(); ++n) // The table asks for a short fade at each end.
    {
        const auto taper = 0.5 * (1.0 - std::cos(pi * static_cast<double>(n) / static_cast<double>(fade)));
        out[n] = static_cast<float>(out[n] * taper);
        out[out.size() - 1 - n] = static_cast<float>(out[out.size() - 1 - n] * taper);
    }
    appendSilence(out, rate, 0.3);
    return out;
}

static double highestTruePeakDBTP(const Signal& signal, double rate)
{
    double highest = -200.0;
    for (const auto& s : run(signal, rate))
        if (s.truePeakDBTP) highest = std::max(highest, *s.truePeakDBTP);
    return highest;
}

static void verifyTech3341TruePeak()
{
    // Table 1 gives +0.2/-0.4 dBTP for cases 15-23, so a reading may sit 0.2 above or 0.4 below the expected peak.
    constexpr double over = 0.2, under = 0.4;
    struct Case { const char* name; double divisor, amplitude, phase, expected; };
    const Case cases[] = {
        { "15 (fs/4, 0 deg, 0.5)", 4.0, 0.50, 0.0, -6.0 },
        { "16 (fs/4, 45 deg, 0.5)", 4.0, 0.50, 45.0, -6.0 },
        { "17 (fs/6, 60 deg, 0.5)", 6.0, 0.50, 60.0, -6.0 },
        { "18 (fs/8, 67.5 deg, 0.5)", 8.0, 0.50, 67.5, -6.0 },
        { "19 (fs/4, 45 deg, 1.41)", 4.0, 1.41, 45.0, 3.0 },
    };
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto label = std::to_string(static_cast<int>(rate)) + " Hz: Tech 3341 true-peak case ";
        for (const auto& c : cases)
        {
            const auto reading = highestTruePeakDBTP(peakTone(rate, c.divisor, c.amplitude, c.phase), rate);
            requireNear(reading, c.expected + 0.5 * (over - under), 0.5 * (over + under), label + c.name);
        }
        for (int offset = 0; offset < 4; ++offset)
            requireNear(highestTruePeakDBTP(singlePeriodCase(rate, offset), rate), 0.5 * (over - under), 0.5 * (over + under),
                        label + std::to_string(20 + offset) + " (single fs/4 period, decimation offset " + std::to_string(offset) + ")");
    }
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
        verifyMeter(); verifyWorkerRetirement(); verifyMomentaryMeasurementTiming(); verifyTech3341Loudness();
        verifyIntegratedGating(); verifyTech3341Multichannel(); verifyTech3342LoudnessRange(); verifyTech3341TruePeak();
        std::cout << checks << " streaming meter checks, " << failures << " failures\n";
        return failures == 0 ? 0 : 1;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n'; return 2; // Invalid fixtures/arguments are not passing verification.
    }
}
