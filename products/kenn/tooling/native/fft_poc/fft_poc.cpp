#include <chrono>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string_view>
#include <vector>

#include "../dsp_core/fft_core.hpp"

namespace {

using Complex = kenn::dsp::Complex;
using kenn::dsp::fft_in_place;

std::size_t parse_iterations(int argc, char** argv)
{
    for (int i = 1; i + 1 < argc; ++i)
    {
        if (std::string_view(argv[i]) == "--iterations")
            return static_cast<std::size_t>(std::stoul(argv[i + 1]));
    }
    return 100;
}

} // namespace

int main(int argc, char** argv)
{
    constexpr std::size_t fftSize = 16384;
    constexpr std::size_t windows = 4;
    constexpr double sampleRate = 48000.0;
    constexpr double toneHz = 1000.0;
    const auto iterations = parse_iterations(argc, argv);
    if (iterations == 0)
    {
        std::cerr << "--iterations must be positive\n";
        return EXIT_FAILURE;
    }

    std::vector<std::vector<Complex>> inputs;
    inputs.reserve(windows);
    for (std::size_t window = 0; window < windows; ++window)
    {
        std::vector<Complex> values(fftSize);
        for (std::size_t index = 0; index < fftSize; ++index)
        {
            const auto globalSample = window * fftSize + index;
            const auto sample = 0.25 * std::sin(2.0 * std::numbers::pi * toneHz * static_cast<double>(globalSample) / sampleRate);
            const auto hann = 0.5 - 0.5 * std::cos(2.0 * std::numbers::pi * static_cast<double>(index) / static_cast<double>(fftSize - 1));
            values[index] = sample * hann;
        }
        inputs.push_back(std::move(values));
    }

    // Verify the deterministic signal before timing the candidate.
    auto check = inputs.front();
    fft_in_place(check);
    std::size_t dominantBin = 1;
    for (std::size_t bin = 2; bin < fftSize / 2; ++bin)
    {
        if (std::norm(check[bin]) > std::norm(check[dominantBin]))
            dominantBin = bin;
    }
    const auto dominantHz = static_cast<double>(dominantBin) * sampleRate / static_cast<double>(fftSize);
    if (std::abs(dominantHz - toneHz) > sampleRate / static_cast<double>(fftSize) * 2.0)
    {
        std::cerr << "deterministic FFT parity probe failed: dominant frequency " << dominantHz << " Hz\n";
        return EXIT_FAILURE;
    }

    const auto started = std::chrono::steady_clock::now();
    double checksum = 0.0;
    for (std::size_t iteration = 0; iteration < iterations; ++iteration)
    {
        for (const auto& input : inputs)
        {
            auto values = input;
            fft_in_place(values);
            checksum += std::norm(values[dominantBin]);
        }
    }
    const auto elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    const auto fftCount = static_cast<double>(iterations * windows);

    std::cout << std::fixed << std::setprecision(6)
              << "[kenn_fft_poc] fft_size=" << fftSize
              << " windows=" << windows
              << " iterations=" << iterations
              << " dominant_hz=" << dominantHz
              << " total_ms=" << elapsed
              << " avg_fft_us=" << (elapsed * 1000.0 / fftCount)
              << " checksum=" << checksum
              << " status=PASS\n";
    return EXIT_SUCCESS;
}
