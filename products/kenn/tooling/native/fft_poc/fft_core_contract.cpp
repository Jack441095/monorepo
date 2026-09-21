#include "../dsp_core/fft_core.hpp"

#include <cmath>
#include <complex>
#include <iostream>
#include <stdexcept>
#include <vector>

int main()
{
    using kenn::dsp::Complex;

    if (kenn::dsp::next_power_of_two(0) != 1
        || kenn::dsp::next_power_of_two(1) != 1
        || kenn::dsp::next_power_of_two(3) != 4
        || kenn::dsp::next_power_of_two(16385) != 32768)
    {
        std::cerr << "next_power_of_two contract failed\n";
        return 1;
    }

    const auto short_starts = kenn::dsp::window_starts(100, 256);
    if (short_starts != std::vector<std::size_t> { 0 })
    {
        std::cerr << "short window placement contract failed\n";
        return 1;
    }
    const auto long_starts = kenn::dsp::window_starts(1000, 256);
    if (long_starts != std::vector<std::size_t> { 0, 248, 496, 744 })
    {
        std::cerr << "multi-window placement contract failed\n";
        return 1;
    }

    std::vector<Complex> impulse(8, Complex { 0.0, 0.0 });
    impulse[0] = Complex { 1.0, 0.0 };
    kenn::dsp::fft_in_place(impulse);
    for (const auto value : impulse)
    {
        if (std::abs(value - Complex { 1.0, 0.0 }) > 1e-12)
        {
            std::cerr << "impulse FFT contract failed\n";
            return 1;
        }
    }

    for (const auto invalid_size : { std::size_t { 0 }, std::size_t { 3 }, std::size_t { 6 } })
    {
        try
        {
            std::vector<Complex> invalid(invalid_size);
            kenn::dsp::fft_in_place(invalid);
            std::cerr << "invalid FFT size was accepted\n";
            return 1;
        }
        catch (const std::invalid_argument&)
        {
            // Expected contract failure.
        }
    }

    std::cout << "FFT core contract smoke passed\n";
    return 0;
}
