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
    // Ready silence has zero energy and no finite logarithmic reading. Warm-up
    // remains separate so callers cannot confuse missing history with silence.
    std::optional<double> momentaryLUFS, shortTermLUFS, truePeakDBTP;
    static constexpr double interpolationDelaySamples = 5.875; // (48 FIR taps - 1) / (2 * 4x).
    // The continuous loudness window covers [endSample - samplesPerBin, endSample].
    // Causal polyphase FIR upsampling delays output by interpolationDelaySamples
    // input frames, so the 100 ms peak scan corresponds to this exact input interval.
    double peakIntervalStartSample = 0.0;
    double peakIntervalEndSample = 0.0;
};

// Offline candidate, owned by one analysis consumer. Call reset after a gap,
// seek or source change. No storage grows with playback duration; no input is
// modified. This module does not implement integrated loudness or LRA.
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
    bool prepare(double rate) noexcept
    {
        samplesPerBin = 0;
        reset();
        if (rate != 44100.0 && rate != 48000.0 && rate != 96000.0)
            return false; // No qualified coefficients/grid: publish absence, not an approximation.
        samplesPerBin = static_cast<int>(rate / 10.0); // Frames in one exact 100 ms bin.
        // BS.1770-5 Annex 1, Tables 1/2: the supplied coefficients are for
        // 48 kHz. Map their analogue prototype through the bilinear transform
        // at the requested rate, retaining the specified 48 kHz response.
        // https://www.itu.int/rec/R-REC-BS.1770-5-202311-I/en
        for (size_t channel = 0; channel < 2; ++channel)
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
        binFrames = binCursor = completedBins = peakCursor = 0;
        frames = 0; binEnergy = binPeak = 0.0; latest = {};
    }

    // Returns true only when a new 100 ms snapshot completes. Non-finite input
    // retires all history; the next finite passage has to warm up again.
    bool push(float left, float right) noexcept
    {
        if (samplesPerBin == 0) return false; // Unprepared/unsupported meters cannot generate evidence.
        if (!std::isfinite(left) || !std::isfinite(right))
        {
            reset();
            return false; // Keep bad audio out of recursive filters and rolling energy.
        }
        const std::array<double, 2> input { left, right };
        for (size_t channel = 0; channel < 2; ++channel)
        {
            const auto weighted = highPass[channel].filter(shelf[channel].filter(input[channel]));
            binEnergy += weighted * weighted; // L/R each have unit BS.1770 channel weight; never mono-sum.
            auto& history = peakHistory[channel];
            history[peakCursor] = history[peakCursor + peakTaps] = input[channel];
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
        if (++binFrames != samplesPerBin) return false; // Preserve the partial bin across host callbacks.
        bins[binCursor] = binEnergy / samplesPerBin;
        binCursor = (binCursor + 1) % shortTermBins;
        completedBins = std::min(completedBins + 1, shortTermBins);
        latest = {};
        latest.endSample = frames;
        latest.momentaryReady = completedBins >= momentaryBins;
        latest.shortTermReady = completedBins == shortTermBins;
        // Re-sum a bounded 30-value ring instead of repeatedly subtracting a
        // loud expired bin. Subtractive cancellation leaves false energy in a
        // later quiet/DC window; this costs only 340 additions/second/insert.
        if (latest.momentaryReady)
        {
            for (size_t age = 0; age < momentaryBins; ++age)
                latest.momentaryMeanSquare += bins[(binCursor + shortTermBins - 1 - age) % shortTermBins];
            latest.momentaryMeanSquare /= momentaryBins;
            latest.momentaryLUFS = loudness(latest.momentaryMeanSquare);
        }
        if (latest.shortTermReady)
        {
            for (const auto energy : bins) latest.shortTermMeanSquare += energy;
            latest.shortTermMeanSquare /= shortTermBins;
            latest.shortTermLUFS = loudness(latest.shortTermMeanSquare);
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
        return true;
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
    static std::optional<double> loudness(double energy) noexcept
    {
        if (energy <= 0.0) return {}; // Exact silence has no finite LUFS; do not invent a meter floor.
        return -0.691 + 10.0 * std::log10(energy); // BS.1770 Annex 1 calibration offset, dB.
    }
    static constexpr size_t momentaryBins = 4, shortTermBins = 30; // 400 ms and 3 s, ungated (Tech 3341 §2.2).
    static constexpr size_t peakTaps = 12; // 48 FIR coefficients, split into four interpolation phases.
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
    std::array<Biquad, 2> shelf, highPass;
    std::array<std::array<double, peakTaps * 2>, 2> peakHistory {};
    std::array<double, shortTermBins> bins {};
    int samplesPerBin = 0, binFrames = 0;
    size_t binCursor = 0, completedBins = 0, peakCursor = 0;
    int64_t frames = 0;
    double binEnergy = 0.0, binPeak = 0.0;
    KENNStreamingMeterSnapshot latest;
};
