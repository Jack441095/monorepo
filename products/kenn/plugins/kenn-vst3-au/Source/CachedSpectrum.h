#pragma once

#include <array>
#include <algorithm>
#include <complex>
#include <cmath>
#include <cstdint>

// Fixed logarithmic groups bound the handoff size. Raw FFT bins stay local;
// each group sums one-sided, Hann-power-normalised mean-square energy.
inline constexpr size_t KENNFFTBandCount = 32;
struct KENNFFTSnapshot
{
    std::array<float, KENNFFTBandCount> energy {};
    int size = 0;
    int64_t firstSample = 0, endSample = 0;
    double meanSquare = 0.0, peakHz = 0.0;
    bool valid = false;
};

// The cached radix-2 plan avoids adding another library/module dependency.
// Plans, Hann windows, input rings and scratch are prepared off the callback;
// push/measure below belong exclusively to the analysis worker.
template<size_t Size>
class KENNCachedSpectrum
{
    static_assert(Size == 2048 || Size == 8192, "Only the qualified FFT sizes are supported");
    struct Plan
    {
        std::array<size_t, Size> reversed {};
        std::array<std::complex<float>, Size / 2> roots {};
        std::array<float, Size> hann {};
        double windowPower = 0.0;
        Plan()
        {
            constexpr double pi = 3.14159265358979323846;
            for (size_t index = 0; index < Size; ++index)
            {
                size_t value = index, reverse = 0;
                for (size_t bit = Size; bit > 1; bit >>= 1) { reverse = (reverse << 1) | (value & 1); value >>= 1; }
                reversed[index] = reverse;
                hann[index] = static_cast<float>(0.5 - 0.5 * std::cos(2.0 * pi * static_cast<double>(index) / Size)); // Periodic Hann, dimensionless.
                windowPower += hann[index] * hann[index];
                if (index < Size / 2) roots[index] = std::polar(1.0f, static_cast<float>(-2.0 * pi * static_cast<double>(index) / Size));
            }
        }
    };
    static const Plan& plan() { static const Plan cached; return cached; }
public:
    void prepare(double rate)
    {
        (void) plan(); // First construction must occur before the worker starts.
        for (size_t bin = 0; bin <= Size / 2; ++bin)
        {
            const auto hz = static_cast<double>(bin) * rate / Size;
            // Cache rate-dependent grouping too: logarithms do not belong in
            // every FFT publication. -1 means outside 20 Hz–20 kHz.
            groups[bin] = hz >= 20.0 && hz < 20000.0
                ? static_cast<int>(std::min(double(KENNFFTBandCount - 1), std::floor(std::log(hz / 20.0) / std::log(1000.0) * KENNFFTBandCount))) : -1;
        }
        reset();
    }
    void reset() { cursor = filled = 0; latest = {}; }
    void push(float left, float right)
    {
        input[0][cursor] = left; input[1][cursor] = right;
        cursor = (cursor + 1) % Size;
        if (filled < Size) ++filled;
    }
    KENNFFTSnapshot measure(double rate, int64_t endSample)
    {
        if (filled < Size) return latest; // A partial ring cannot describe the requested FFT duration.
        const auto& cached = plan();
        KENNFFTSnapshot frame;
        frame.size = static_cast<int>(Size); frame.firstSample = endSample - static_cast<int64_t>(Size); frame.endSample = endSample;
        double peakPower = 0.0;
        power.fill(0.0);
        for (size_t channel = 0; channel < 2; ++channel)
        {
            for (size_t index = 0; index < Size; ++index)
                scratch[cached.reversed[index]] = { input[channel][(cursor + index) % Size] * cached.hann[index], 0.0f };
            for (size_t width = 2; width <= Size; width <<= 1)
                for (size_t first = 0; first < Size; first += width)
                    for (size_t index = 0; index < width / 2; ++index)
                    {
                        const auto even = scratch[first + index];
                        const auto odd = scratch[first + index + width / 2] * cached.roots[index * Size / width];
                        scratch[first + index] = even + odd; scratch[first + index + width / 2] = even - odd;
                    }
            for (size_t bin = 0; bin <= Size / 2; ++bin)
            {
                // Parseval: divide raw DFT power by N*sum(Hann^2), double only
                // interior positive bins, then average separate channel powers.
                const double weight = bin == 0 || bin == Size / 2 ? 0.5 : 1.0;
                power[bin] += weight * std::norm(scratch[bin]) / (Size * cached.windowPower);
            }
        }
        for (size_t bin = 0; bin <= Size / 2; ++bin)
        {
            const auto hz = static_cast<double>(bin) * rate / Size;
            frame.meanSquare += power[bin];
            if (bin > 0 && power[bin] > peakPower) { peakPower = power[bin]; frame.peakHz = hz; }
            if (groups[bin] >= 0)
            {
                // 32 equal log-frequency groups span 20 Hz to 20 kHz. Bin
                // centres assign power once; edge resolution remains rate/N Hz.
                frame.energy[static_cast<size_t>(groups[bin])] += static_cast<float>(power[bin]);
            }
        }
        frame.valid = true; latest = frame;
        return frame;
    }
    KENNFFTSnapshot snapshot() const { return latest; }
private:
    std::array<std::array<float, Size>, 2> input {};
    std::array<std::complex<float>, Size> scratch {};
    std::array<double, Size / 2 + 1> power {};
    std::array<int, Size / 2 + 1> groups {};
    size_t cursor = 0, filled = 0;
    KENNFFTSnapshot latest;
};
