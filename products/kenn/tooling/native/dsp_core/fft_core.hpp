#pragma once

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <numbers>
#include <stdexcept>
#include <vector>

namespace kenn::dsp {

using Complex = std::complex<double>;

inline void fft_in_place(std::vector<Complex>& values)
{
    const std::size_t n = values.size();
    if (n == 0 || (n & (n - 1)) != 0)
        throw std::invalid_argument("FFT size must be a non-zero power of two");

    std::size_t j = 0;
    for (std::size_t i = 1; i < n; ++i)
    {
        std::size_t bit = n >> 1;
        while ((j & bit) != 0)
        {
            j ^= bit;
            bit >>= 1;
        }
        j ^= bit;
        if (i < j)
            std::swap(values[i], values[j]);
    }

    for (std::size_t length = 2; length <= n; length <<= 1)
    {
        const double angle = -2.0 * std::numbers::pi / static_cast<double>(length);
        const Complex root = std::polar(1.0, angle);
        for (std::size_t start = 0; start < n; start += length)
        {
            Complex factor { 1.0, 0.0 };
            const std::size_t half = length / 2;
            for (std::size_t offset = 0; offset < half; ++offset)
            {
                const Complex even = values[start + offset];
                const Complex odd = factor * values[start + offset + half];
                values[start + offset] = even + odd;
                values[start + offset + half] = even - odd;
                factor *= root;
            }
        }
    }
}

inline std::vector<std::size_t> window_starts(std::size_t length, std::size_t fft_size)
{
    if (length <= fft_size)
        return { 0 };
    const auto count = std::min<std::size_t>(4, std::max<std::size_t>(1, (length + fft_size - 1) / fft_size));
    const auto last = length - fft_size;
    if (count == 1)
        return { 0 };
    std::vector<std::size_t> result;
    result.reserve(count);
    for (std::size_t index = 0; index < count; ++index)
    {
        // Match Python's round() for non-negative values, including its
        // bankers-rounding behavior at exact half-integers.
        const auto value = static_cast<double>(last * index) / static_cast<double>(count - 1);
        const auto lower = std::floor(value);
        const auto fraction = value - lower;
        double rounded = lower;
        if (fraction > 0.5 || (fraction == 0.5 && std::fmod(lower, 2.0) != 0.0))
            rounded = lower + 1.0;
        result.push_back(static_cast<std::size_t>(rounded));
    }
    return result;
}

inline std::size_t next_power_of_two(std::size_t value)
{
    std::size_t result = 1;
    while (result < value)
        result <<= 1;
    return result;
}

} // namespace kenn::dsp
