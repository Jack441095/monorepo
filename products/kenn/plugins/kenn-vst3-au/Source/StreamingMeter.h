#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>

struct KENNStreamingMeterSnapshot
{
    int64_t endSample = 0; // Contiguous frames since prepare/reset, not a host position.
    double momentaryMeanSquare = 0.0, shortTermMeanSquare = 0.0, truePeakLinear = 0.0;
    bool momentaryReady = false, shortTermReady = false, truePeakReady = false;
    // Gated programme loudness since prepare/reset (BS.1770-5 §5.1, two-stage gate). Ready once one 400 ms block has
    // cleared both gates; a passage that never does (digital silence, or everything under -70 LUFS) stays not ready.
    double integratedMeanSquare = 0.0;
    bool integratedReady = false;
    // EBU Tech 3342 Loudness Range (LRA) since prepare/reset. Computed over short-term (3.0 s)
    // loudness blocks using a fixed 1600-bucket histogram (-70 LUFS to +10 LUFS) with a -70 LUFS
    // absolute gate and -20 LU relative gate. Ready once at least two blocks pass both gates.
    double lraLU = 0.0;
    bool lraReady = false;
    std::optional<double> loudnessRangeLU;
    // Ready silence has zero energy and no finite logarithmic reading. Warm-up
    // remains separate so callers cannot confuse missing history with silence.
    std::optional<double> momentaryLUFS, shortTermLUFS, integratedLUFS, truePeakDBTP;
    // The greatest 400 ms energy measured on the internal 10 ms grid in the
    // preceding 100 ms ending at endSample, with its own window end position.
    // Keep it separate from momentaryMeanSquare, which ends at endSample: a
    // maximum is evidence about an earlier window, not the current loudness.
    double momentaryMaximumMeanSquare = 0.0;
    int64_t momentaryMaximumEndSample = 0;
    bool momentaryMaximumReady = false;
    std::optional<double> momentaryMaximumLUFS;
    static constexpr double interpolationDelaySamples = 5.875; // (48 FIR taps - 1) / (2 * 4x).
    // Momentary and short-term windows end at endSample and span 400 ms and 3 s.
    // Causal polyphase FIR upsampling delays output by interpolationDelaySamples
    // input frames, so the 100 ms peak scan corresponds to this exact input interval.
    double peakIntervalStartSample = 0.0;
    double peakIntervalEndSample = 0.0;
};

// Offline candidate, owned by one analysis consumer. Call reset after a gap,
// seek or source change. No storage grows with playback duration; no input is
// modified. Integrated loudness and EBU Tech 3342 LRA are kept as fixed-size
// histograms (1600 buckets of 0.05 LU width from -70 to +10 LUFS), so a
// multi-hour programme costs zero audio-thread allocations and constant memory.
// Supports mono (1ch), stereo (2ch), and 5.0 surround (5ch with ITU-R BS.1770-4
// [1.0, 1.0, 1.0, 1.41, 1.41] channel weighting).
class KENNStreamingMeter
{
    struct Biquad
    {
        std::array<double, 3> b {}, a { 1.0, 0.0, 0.0 };
        double z1 = 0.0, z2 = 0.0;
        double filter(double value) noexcept
        {
            const auto output = b[0] * value + z1;
            z1 = b[1] * value - a[1] * output + z2;
            z2 = b[2] * value - a[2] * output;
            return output;
        }
        void reset() noexcept { z1 = z2 = 0.0; }
    };

public:
    // Only these rates have offline qualification. An unsupported rate retires
    // previous readings rather than silently rounding the 100 ms sample grid.
    // Supports 1 (mono), 2 (stereo), and 5 (5.0 surround) channel layouts per
    // ITU-R BS.1770-4 Table 3.
    bool prepare(double rate, size_t channels = 2) noexcept
    {
        samplesPerBin = 0;
        samplesPerMeasurement = 0;
        reset();
        if (rate != 44100.0 && rate != 48000.0 && rate != 96000.0)
            return false; // No qualified coefficients/grid: publish absence, not an approximation.
        if (channels != 1 && channels != 2 && channels != 5)
            return false; // Qualified channel configurations: 1 (mono), 2 (stereo), 5 (5.0 surround).
        activeChannels = channels;
        samplesPerBin = static_cast<int>(rate / 10.0); // Frames in one exact 100 ms bin.
        samplesPerMeasurement = static_cast<int>(rate / 100.0); // Exact 10 ms hops at every qualified rate.

        channelWeights.fill(1.0);
        if (channels == 5)
        {
            // ITU-R BS.1770-4 Table 3 and EBU Tech 3341 Case 6: Left, Right, and Centre
            // have unit weight (1.0 = 0.0 dB). Left surround and Right surround receive
            // +1.5 dB weighting (gain factor ~1.41, or 10^(1.5/10)).
            channelWeights[0] = 1.0;  // Left
            channelWeights[1] = 1.0;  // Right
            channelWeights[2] = 1.0;  // Centre
            channelWeights[3] = 1.41; // Left surround (+1.5 dB)
            channelWeights[4] = 1.41; // Right surround (+1.5 dB)
        }

        // BS.1770-5 Annex 1, Tables 1/2: the supplied coefficients are for
        // 48 kHz. Map their analogue prototype through the bilinear transform
        // at the requested rate, retaining the specified 48 kHz response.
        // https://www.itu.int/rec/R-REC-BS.1770-5-202311-I/en
        for (size_t channel = 0; channel < activeChannels; ++channel)
        {
            shelf[channel] = atRate({ 1.53512485958697, -2.69169618940638, 1.19839281085285 },
                                    { 1.0, -1.69065929318241, 0.73248077421585 }, rate);
            highPass[channel] = atRate({ 1.0, -2.0, 1.0 },
                                       { 1.0, -1.99004745483398, 0.99007225036621 }, rate);
        }
        return true;
    }

    void reset() noexcept
    {
        for (auto& stage : shelf) stage.reset();
        for (auto& stage : highPass) stage.reset();
        for (auto& channel : peakHistory) channel.fill(0.0);
        bins.fill(0.0);
        momentaryBins.fill(0.0);
        gatedCount.fill(0); gatedEnergy.fill(0.0);
        absoluteGatedBlocks = 0; absoluteGatedEnergy = 0.0;
        lraCount.fill(0); lraEnergy.fill(0.0);
        absoluteGatedLraBlocks = 0; absoluteGatedLraEnergy = 0.0;
        binFrames = binCursor = completedBins = peakCursor = 0;
        measurementFrames = measurementCursor = completedMeasurements = 0;
        measurementEnergy = intervalMaximumEnergy = 0.0;
        intervalMaximumEndSample = 0;
        frames = 0; binEnergy = binPeak = 0.0; latest = {};
    }

    size_t numChannels() const noexcept { return activeChannels; }

    // Multi-channel push supporting 1 (mono), 2 (stereo), and 5 (5.0 surround) channels.
    // Returns true only when a new 100 ms snapshot completes. Non-finite input
    // retires all history; the next finite passage has to warm up again.
    bool pushChannels(const float* channelSamples, size_t numChannels) noexcept
    {
        if (samplesPerBin == 0 || channelSamples == nullptr || numChannels != activeChannels)
            return false; // Unprepared, null, or channel layout mismatch cannot generate evidence.
        for (size_t ch = 0; ch < activeChannels; ++ch)
        {
            if (!std::isfinite(channelSamples[ch]))
            {
                reset();
                return false; // Keep bad audio out of recursive filters and rolling energy.
            }
        }
        double frameEnergy = 0.0;
        for (size_t channel = 0; channel < activeChannels; ++channel)
        {
            const double input = channelSamples[channel];
            const auto weighted = highPass[channel].filter(shelf[channel].filter(input));
            frameEnergy += channelWeights[channel] * (weighted * weighted);
            auto& history = peakHistory[channel];
            history[peakCursor] = history[peakCursor + peakTaps] = input;
            // Duplicate the 12-frame ring so all four phase dot products have
            // contiguous history without per-tap modulo or temporary buffers.
            const auto* newest = history.data() + peakCursor + peakTaps;
            for (const auto& phase : peakCoefficients)
            {
                double value = 0.0;
                for (size_t tap = 0; tap < peakTaps; ++tap) value += phase[tap] * newest[-static_cast<int>(tap)];
                binPeak = std::max(binPeak, std::abs(value));
            }
        }
        peakCursor = (peakCursor + 1) % peakTaps;
        ++frames;
        binEnergy += frameEnergy;
        measurementEnergy += frameEnergy;
        if (++measurementFrames == samplesPerMeasurement)
        {
            momentaryBins[measurementCursor] = measurementEnergy / samplesPerMeasurement;
            measurementCursor = (measurementCursor + 1) % momentaryMeasurements;
            completedMeasurements = std::min(completedMeasurements + 1, momentaryMeasurements);
            if (completedMeasurements == momentaryMeasurements)
            {
                // At most 5 ms of a 400 ms tone falls between observations:
                // the ideal timing loss is <=0.055 LU, inside the 0.1 LU test
                // margin. Re-summing 40 bins avoids loud-to-quiet cancellation.
                double energy = 0.0;
                for (const auto bin : momentaryBins) energy += bin;
                energy /= momentaryMeasurements;
                // The first observation also marks ready digital silence:
                // zero energy still has a measured position after warm-up.
                if (intervalMaximumEndSample == 0 || energy > intervalMaximumEnergy)
                {
                    intervalMaximumEnergy = energy;
                    intervalMaximumEndSample = frames;
                }
            }
            measurementFrames = 0;
            measurementEnergy = 0.0;
        }
        if (++binFrames != samplesPerBin) return false; // Preserve the partial bin across host callbacks.
        bins[binCursor] = binEnergy / samplesPerBin;
        binCursor = (binCursor + 1) % shortTermBins;
        completedBins = std::min(completedBins + 1, shortTermBins);
        latest = {};
        latest.endSample = frames;
        latest.momentaryMaximumReady = intervalMaximumEndSample != 0;
        latest.momentaryMaximumMeanSquare = intervalMaximumEnergy;
        latest.momentaryMaximumEndSample = intervalMaximumEndSample;
        latest.momentaryMaximumLUFS = loudness(intervalMaximumEnergy);
        latest.momentaryReady = completedBins >= momentaryWindowBins;
        latest.shortTermReady = completedBins == shortTermBins;
        // Re-sum a bounded 30-value ring instead of repeatedly subtracting a
        // loud expired bin. Subtractive cancellation leaves false energy in a
        // later quiet/DC window; this costs only 340 additions/second/insert.
        if (latest.momentaryReady)
        {
            for (size_t age = 0; age < momentaryWindowBins; ++age)
                latest.momentaryMeanSquare += bins[(binCursor + shortTermBins - 1 - age) % shortTermBins];
            latest.momentaryMeanSquare /= momentaryWindowBins;
            latest.momentaryLUFS = loudness(latest.momentaryMeanSquare);
            // BS.1770-5 gating blocks are 400 ms long and overlap by 75%, which is exactly one momentary window
            // every 100 ms bin, so each completed window is one gating block.
            addGatingBlock(latest.momentaryMeanSquare);
            integrate();
        }
        if (latest.shortTermReady)
        {
            for (const auto energy : bins) latest.shortTermMeanSquare += energy;
            latest.shortTermMeanSquare /= shortTermBins;
            latest.shortTermLUFS = loudness(latest.shortTermMeanSquare);
            // EBU Tech 3342 §3: LRA is computed over sliding 3.0 s short-term blocks
            // updated at least every 0.1 s. Each completed 100 ms bin adds one short-term block.
            addLraBlock(latest.shortTermMeanSquare);
            integrateLra();
        }
        // This peak describes FIR output in the completed 100 ms interval,
        // delayed 5.875 input frames. It has no added playback latency;
        // record the exact input interval it represents.
        latest.truePeakReady = frames >= static_cast<int64_t>(peakTaps);
        latest.truePeakLinear = binPeak;
        if (binPeak > 0.0) latest.truePeakDBTP = 20.0 * std::log10(binPeak);
        latest.peakIntervalEndSample = static_cast<double>(frames) - KENNStreamingMeterSnapshot::interpolationDelaySamples;
        latest.peakIntervalStartSample = latest.peakIntervalEndSample - static_cast<double>(samplesPerBin);
        binFrames = 0; binEnergy = binPeak = 0.0;
        intervalMaximumEnergy = 0.0;
        intervalMaximumEndSample = 0;
        return true;
    }

    bool push(float left, float right) noexcept
    {
        const std::array<float, 2> input { left, right };
        return pushChannels(input.data(), 2);
    }

    bool push1(float mono) noexcept
    {
        return pushChannels(&mono, 1);
    }

    bool push5(float left, float right, float center, float leftSurround, float rightSurround) noexcept
    {
        const std::array<float, 5> input { left, right, center, leftSurround, rightSurround };
        return pushChannels(input.data(), 5);
    }

    KENNStreamingMeterSnapshot snapshot() const noexcept { return latest; }

private:
    static Biquad atRate(std::array<double, 3> b, std::array<double, 3> a, double rate) noexcept
    {
        if (rate == 48000.0) return { b, a }; // Preserve the published reference coefficients verbatim.
        const auto remap = [ratio = rate / 48000.0](const std::array<double, 3>& v) {
            // Substitute z^-1=(1-s/(2fs))/(1+s/(2fs)) in each polynomial,
            // then substitute the new sampling rate. The common factor cancels.
            const auto c0 = v[0] + v[1] + v[2];
            const auto c1 = 2.0 * (v[0] - v[2]) * ratio;
            const auto c2 = (v[0] - v[1] + v[2]) * ratio * ratio;
            return std::array<double, 3> { c0 + c1 + c2, 2.0 * (c0 - c2), c0 - c1 + c2 };
        };
        b = remap(b); a = remap(a);
        const auto scale = a[0];
        for (auto& value : b) value /= scale;
        for (auto& value : a) value /= scale;
        return { b, a };
    }
    // Buckets a block by its loudness so the relative gate can be found without keeping every block. Each bucket
    // holds the block count and the exact energy sum, so the mean is not rounded to the bucket width; only whether
    // a block counts as above the relative gate is decided at bucket resolution.
    void addGatingBlock(double energy) noexcept
    {
        if (energy <= 0.0) return; // Digital silence has no loudness and is below any gate.
        const auto blockLUFS = -0.691 + 10.0 * std::log10(energy);
        if (blockLUFS <= absoluteGateLUFS) return; // Absolute gate: BS.1770-5 drops blocks at or under -70 LUFS.
        // A block louder than the top bucket (+10 LUFS, far above digital full scale) is counted in it; its energy
        // is still summed exactly, so only the gate membership is approximate and nothing quiet depends on it.
        const auto bucket = std::min(static_cast<size_t>((blockLUFS - absoluteGateLUFS) / bucketWidthLU), gateBuckets - 1);
        ++gatedCount[bucket];
        gatedEnergy[bucket] += energy;
        ++absoluteGatedBlocks;
        absoluteGatedEnergy += energy;
    }

    // Applies the relative gate (10 LU under the mean of everything past the absolute gate) and averages what is left.
    void integrate() noexcept
    {
        if (absoluteGatedBlocks == 0) return;
        const auto relativeGateLUFS = loudness(absoluteGatedEnergy / static_cast<double>(absoluteGatedBlocks)).value() - 10.0;
        // First bucket whose lower edge is at or above the gate; the single bucket straddling the gate is left out.
        // At 0.05 LU wide that bucket can only hold blocks within 0.05 LU of a threshold the spec already sets
        // loosely, and the Tech 3341 cases below confirm it moves the result well inside the +/-0.1 LU tolerance.
        const auto first = relativeGateLUFS <= absoluteGateLUFS
            ? size_t { 0 }
            : static_cast<size_t>(std::ceil((relativeGateLUFS - absoluteGateLUFS) / bucketWidthLU));
        int64_t blocks = 0;
        double energy = 0.0;
        for (size_t bucket = first; bucket < gateBuckets; ++bucket)
        {
            blocks += gatedCount[bucket];
            energy += gatedEnergy[bucket];
        }
        if (blocks == 0) return;
        latest.integratedReady = true;
        latest.integratedMeanSquare = energy / static_cast<double>(blocks);
        latest.integratedLUFS = loudness(latest.integratedMeanSquare);
    }

    // Buckets a 3.0 s short-term block by its loudness for EBU Tech 3342 Loudness Range (LRA).
    // Gated at -70.0 LUFS absolute gate (Tech 3342 §3.1).
    void addLraBlock(double energy) noexcept
    {
        if (energy <= 0.0) return; // Digital silence carries no loudness and falls below the absolute gate.
        const auto blockLUFS = -0.691 + 10.0 * std::log10(energy);
        if (blockLUFS < absoluteGateLUFS) return; // Tech 3342 §3.1: ABS_THRES = -70 LUFS.
        const auto bucket = std::min(static_cast<size_t>((blockLUFS - absoluteGateLUFS) / bucketWidthLU), gateBuckets - 1);
        ++lraCount[bucket];
        lraEnergy[bucket] += energy;
        ++absoluteGatedLraBlocks;
        absoluteGatedLraEnergy += energy;
    }

    // Computes EBU Tech 3342 Loudness Range (LRA) using a -20.0 LU relative gate
    // (Tech 3342 §3.2) and percentile difference P95 - P10 (Tech 3342 §3.3 & §5).
    void integrateLra() noexcept
    {
        if (absoluteGatedLraBlocks < 2) return; // Minimum 2 short-term blocks required for a valid distribution.
        const auto meanAbsEnergy = absoluteGatedLraEnergy / static_cast<double>(absoluteGatedLraBlocks);
        if (meanAbsEnergy <= 0.0) return;
        const auto relThresholdLUFS = loudness(meanAbsEnergy).value() - 20.0; // Tech 3342 §3.2: -20 LU relative gate.

        const auto firstBucket = relThresholdLUFS <= absoluteGateLUFS
            ? size_t { 0 }
            : static_cast<size_t>(std::ceil((relThresholdLUFS - absoluteGateLUFS) / bucketWidthLU));
        if (firstBucket >= gateBuckets) return;

        int64_t relGatedBlocks = 0;
        for (size_t b = firstBucket; b < gateBuckets; ++b)
            relGatedBlocks += lraCount[b];

        if (relGatedBlocks < 2) return;

        // Rank indices per MATLAB reference in Tech 3342 §5:
        // stl_perc_low = stl_sorted_vec(round((n-1)*0.10 + 1)) -> 0-based: round((n-1)*0.10)
        // stl_perc_high = stl_sorted_vec(round((n-1)*0.95 + 1)) -> 0-based: round((n-1)*0.95)
        const auto kLow = static_cast<int64_t>(std::llround(static_cast<double>(relGatedBlocks - 1) * 0.10));
        const auto kHigh = static_cast<int64_t>(std::llround(static_cast<double>(relGatedBlocks - 1) * 0.95));

        size_t bLow = firstBucket;
        size_t bHigh = firstBucket;
        int64_t cumulative = 0;
        bool foundLow = false;
        bool foundHigh = false;

        for (size_t b = firstBucket; b < gateBuckets; ++b)
        {
            cumulative += lraCount[b];
            if (!foundLow && cumulative > kLow)
            {
                bLow = b;
                foundLow = true;
            }
            if (!foundHigh && cumulative > kHigh)
            {
                bHigh = b;
                foundHigh = true;
                break;
            }
        }

        if (!foundLow || !foundHigh) return;

        // If both percentiles land in the same 0.05 LU bucket (e.g. steady tone),
        // LRA is identically 0.0 LU without intra-bucket rank jitter.
        const double lra = (bHigh == bLow) ? 0.0 : static_cast<double>(bHigh - bLow) * bucketWidthLU;
        latest.lraLU = lra;
        latest.lraReady = true;
        latest.loudnessRangeLU = lra;
    }

    static std::optional<double> loudness(double energy) noexcept
    {
        if (energy <= 0.0) return {}; // Exact silence has no finite LUFS; do not invent a meter floor.
        return -0.691 + 10.0 * std::log10(energy); // BS.1770 Annex 1 calibration offset, dB.
    }
    static constexpr size_t momentaryWindowBins = 4, shortTermBins = 30; // 400 ms and 3 s, ungated (Tech 3341 §2.2).
    static constexpr size_t momentaryMeasurements = 40; // 400 ms / 10 ms; independent of snapshots and integrated gating.
    // 0.05 LU buckets from -70 LUFS to +10 LUFS: 1600 count/energy pairs, 25 KiB per meter.
    static constexpr double absoluteGateLUFS = -70.0, bucketWidthLU = 0.05;
    static constexpr size_t gateBuckets = 1600;
    static constexpr size_t peakTaps = 12; // 48 FIR coefficients, split into four interpolation phases.
    static constexpr size_t maxChannels = 5; // Qualified for 1 (mono), 2 (stereo), and 5 (5.0 surround).
    // BS.1770-5 Annex 2's published interpolator, dimensionless coefficients.
    // Floating point needs no initial 12.04 dB fixed-point headroom shift.
    // 4x is used at all three rates; this is not a universal accuracy guarantee.
    static constexpr std::array<std::array<double, peakTaps>, 4> peakCoefficients {{
        {{ .0017089843750, .0109863281250, -.0196533203125, .0332031250000, -.0594482421875, .1373291015625,
            .9721679687500, -.1022949218750, .0476074218750, -.0266113281250, .0148925781250, -.0083007812500 }},
        {{ -.0291748046875, .0292968750000, -.0517578125000, .0891113281250, -.1665039062500, .4650878906250,
            .7797851562500, -.2003173828125, .1015625000000, -.0582275390625, .0330810546875, -.0189208984375 }},
        {{ -.0189208984375, .0330810546875, -.0582275390625, .1015625000000, -.2003173828125, .7797851562500,
            .4650878906250, -.1665039062500, .0891113281250, -.0517578125000, .0292968750000, -.0291748046875 }},
        {{ -.0083007812500, .0148925781250, -.0266113281250, .0476074218750, -.1022949218750, .9721679687500,
            .1373291015625, -.0594482421875, .0332031250000, -.0196533203125, .0109863281250000, .0017089843750 }}
    }};
    std::array<Biquad, maxChannels> shelf, highPass;
    std::array<std::array<double, peakTaps * 2>, maxChannels> peakHistory {};
    std::array<double, maxChannels> channelWeights { 1.0, 1.0, 1.0, 1.41, 1.41 };
    size_t activeChannels = 2;
    std::array<double, shortTermBins> bins {};
    std::array<double, momentaryMeasurements> momentaryBins {};
    std::array<int64_t, gateBuckets> gatedCount {};
    std::array<double, gateBuckets> gatedEnergy {};
    int64_t absoluteGatedBlocks = 0;
    double absoluteGatedEnergy = 0.0;
    std::array<int64_t, gateBuckets> lraCount {};
    std::array<double, gateBuckets> lraEnergy {};
    int64_t absoluteGatedLraBlocks = 0;
    double absoluteGatedLraEnergy = 0.0;
    int samplesPerBin = 0, binFrames = 0;
    int samplesPerMeasurement = 0, measurementFrames = 0;
    size_t measurementCursor = 0, completedMeasurements = 0;
    double measurementEnergy = 0.0, intervalMaximumEnergy = 0.0;
    int64_t intervalMaximumEndSample = 0;
    size_t binCursor = 0, completedBins = 0, peakCursor = 0;
    int64_t frames = 0;
    double binEnergy = 0.0, binPeak = 0.0;
    KENNStreamingMeterSnapshot latest;
};
