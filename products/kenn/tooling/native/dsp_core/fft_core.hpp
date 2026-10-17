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

struct ComplexFFTPlan {
    std::size_t n = 0;
    std::vector<std::pair<std::size_t, std::size_t>> swap_pairs;
    std::vector<Complex> twiddles;

    explicit ComplexFFTPlan(std::size_t fft_size) : n(fft_size)
    {
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
                swap_pairs.emplace_back(i, j);
        }

        twiddles.reserve(n);
        for (std::size_t length = 2; length <= n; length <<= 1)
        {
            const std::size_t half = length / 2;
            const double step = -2.0 * std::numbers::pi / static_cast<double>(length);
            for (std::size_t offset = 0; offset < half; ++offset)
            {
                const double angle = step * static_cast<double>(offset);
                twiddles.emplace_back(std::cos(angle), std::sin(angle));
            }
        }
    }

    void execute(std::vector<Complex>& values) const
    {
        for (const auto& [i, j] : swap_pairs)
            std::swap(values[i], values[j]);

        std::size_t twiddle_offset = 0;
        for (std::size_t length = 2; length <= n; length <<= 1)
        {
            const std::size_t half = length / 2;
            const Complex* stage_twiddles = twiddles.data() + twiddle_offset;
            for (std::size_t start = 0; start < n; start += length)
            {
                for (std::size_t offset = 0; offset < half; ++offset)
                {
                    const Complex even = values[start + offset];
                    const Complex odd = stage_twiddles[offset] * values[start + offset + half];
                    values[start + offset] = even + odd;
                    values[start + offset + half] = even - odd;
                }
            }
            twiddle_offset += half;
        }
    }
};

inline void fft_in_place(std::vector<Complex>& values)
{
    const std::size_t n = values.size();
    if (n == 0 || (n & (n - 1)) != 0)
        throw std::invalid_argument("FFT size must be a non-zero power of two");

    thread_local std::vector<ComplexFFTPlan> plans;
    for (const auto& plan : plans)
    {
        if (plan.n == n)
        {
            plan.execute(values);
            return;
        }
    }
    plans.emplace_back(n);
    plans.back().execute(values);
}

// Half-length real-input FFT plan using Structure-of-Arrays (separate real and
// imaginary buffers) and precomputed stage/unpack twiddle tables so scalar
// builds (-DKENN_USE_ACCELERATE=OFF) vectorize cleanly without per-frame
// trigonometric calls or heap allocations.
class RealFFTPlan {
public:
    explicit RealFFTPlan(std::size_t fft_size)
        : n_(fft_size), half_(fft_size / 2)
    {
        if (n_ < 4 || (n_ & (n_ - 1)) != 0)
            throw std::invalid_argument("RealFFTPlan requires a power-of-two FFT size >= 4");

        bit_reversed_.resize(half_);
        std::size_t j = 0;
        for (std::size_t i = 0; i < half_; ++i)
        {
            bit_reversed_[i] = j;
            std::size_t bit = half_ >> 1;
            while (bit > 0 && (j & bit) != 0)
            {
                j ^= bit;
                bit >>= 1;
            }
            j ^= bit;
        }

        twiddle_re_.reserve(half_);
        twiddle_im_.reserve(half_);
        for (std::size_t length = 2; length <= half_; length <<= 1)
        {
            const std::size_t span = length / 2;
            const double step = -2.0 * std::numbers::pi / static_cast<double>(length);
            for (std::size_t offset = 0; offset < span; ++offset)
            {
                const double angle = step * static_cast<double>(offset);
                twiddle_re_.push_back(std::cos(angle));
                twiddle_im_.push_back(std::sin(angle));
            }
        }

        const std::size_t quarter = half_ / 2;
        unpack_re_.resize(quarter + 1);
        unpack_im_.resize(quarter + 1);
        const double unpack_step = -2.0 * std::numbers::pi / static_cast<double>(n_);
        for (std::size_t k = 0; k <= quarter; ++k)
        {
            const double angle = unpack_step * static_cast<double>(k);
            unpack_re_[k] = std::cos(angle);
            unpack_im_[k] = std::sin(angle);
        }

        re_.resize(half_);
        im_.resize(half_);
    }

    void power_spectrum(const double* time_domain, std::vector<double>& powers)
    {
        powers.resize(half_ + 1);
        double* __restrict re = re_.data();
        double* __restrict im = im_.data();
        const std::size_t* __restrict br = bit_reversed_.data();

        for (std::size_t i = 0; i < half_; ++i)
        {
            const std::size_t dst = br[i];
            re[dst] = time_domain[2 * i];
            im[dst] = time_domain[2 * i + 1];
        }

        // Stage length = 2 (twiddle = 1 + 0i).
        for (std::size_t start = 0; start < half_; start += 2)
        {
            const double er = re[start];
            const double ei = im[start];
            const double or_val = re[start + 1];
            const double oi = im[start + 1];
            re[start] = er + or_val;
            im[start] = ei + oi;
            re[start + 1] = er - or_val;
            im[start + 1] = ei - oi;
        }

        std::size_t twiddle_offset = 1;
        for (std::size_t length = 4; length <= half_; length <<= 1)
        {
            const std::size_t span = length / 2;
            const double* __restrict wr = twiddle_re_.data() + twiddle_offset;
            const double* __restrict wi = twiddle_im_.data() + twiddle_offset;
            for (std::size_t start = 0; start < half_; start += length)
            {
                double* __restrict re0 = re + start;
                double* __restrict im0 = im + start;
                double* __restrict re1 = re0 + span;
                double* __restrict im1 = im0 + span;
                for (std::size_t offset = 0; offset < span; ++offset)
                {
                    const double tr = wr[offset] * re1[offset] - wi[offset] * im1[offset];
                    const double ti = wr[offset] * im1[offset] + wi[offset] * re1[offset];
                    const double ur = re0[offset];
                    const double ui = im0[offset];
                    re0[offset] = ur + tr;
                    im0[offset] = ui + ti;
                    re1[offset] = ur - tr;
                    im1[offset] = ui - ti;
                }
            }
            twiddle_offset += span;
        }

        const double dc = re[0] + im[0];
        const double nyquist = re[0] - im[0];
        powers[0] = dc * dc;
        powers[half_] = nyquist * nyquist;

        const std::size_t quarter = half_ / 2;
        const double* __restrict ur = unpack_re_.data();
        const double* __restrict ui = unpack_im_.data();
        for (std::size_t k = 1; k <= quarter; ++k)
        {
            const std::size_t mk = half_ - k;
            const double r1 = re[k];
            const double i1 = im[k];
            const double r2 = re[mk];
            const double i2 = -im[mk];

            const double er = 0.5 * (r1 + r2);
            const double ei = 0.5 * (i1 + i2);
            const double or_val = 0.5 * (i1 - i2);
            const double oi = 0.5 * (r2 - r1);

            const double wr = ur[k] * or_val - ui[k] * oi;
            const double wi = ur[k] * oi + ui[k] * or_val;

            const double xk_re = er + wr;
            const double xk_im = ei + wi;
            powers[k] = xk_re * xk_re + xk_im * xk_im;

            const double xmk_re = er - wr;
            const double xmk_im = wi - ei;
            powers[mk] = xmk_re * xmk_re + xmk_im * xmk_im;
        }
    }

private:
    std::size_t n_;
    std::size_t half_;
    std::vector<std::size_t> bit_reversed_;
    std::vector<double> twiddle_re_;
    std::vector<double> twiddle_im_;
    std::vector<double> unpack_re_;
    std::vector<double> unpack_im_;
    std::vector<double> re_;
    std::vector<double> im_;
};

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
