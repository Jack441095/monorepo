#include "AudioToo_DSP.h"

#include <cmath>
#include <cstddef>
#include <iostream>
#include <vector>

extern "C" {
void biquad_sos_filter(const double*, std::size_t, const double*, std::size_t, double*);
void smooth_attack_release(const double*, std::size_t, double, double, double, bool, double*);
void gate_envelope(const double*, std::size_t, double, double, double, int, double, double, double*);
void rolling_median_mad_threshold(const double*, std::size_t, int, double, double, double*);
}

namespace {

bool all_finite(const std::vector<double>& values)
{
    for (const auto value : values)
    {
        if (!std::isfinite(value))
            return false;
    }
    return true;
}

} // namespace

int main()
{
    constexpr std::size_t sample_count = 256;
    std::vector<double> left(sample_count, 0.0);
    std::vector<double> right(sample_count, 0.0);
    for (std::size_t index = 0; index < sample_count; ++index)
    {
        const auto phase = static_cast<double>(index) * 0.17;
        left[index] = 0.25 * std::sin(phase);
        right[index] = left[index];
    }
    left[0] = 1.0;
    right[0] = 1.0;

    std::vector<double> gain(sample_count, 0.0);
    std::vector<double> limited(sample_count, 0.0);
    limiter_gain_envelope(left.data(), sample_count, 1.0, 0.9, 0.1, 4, gain.data(), limited.data());

    std::vector<double> saturated(sample_count, 0.0);
    saturator_waveshape(left.data(), sample_count, 1.4, 0.15, 1.0,
                        left.data(), sample_count, saturated.data());

    std::vector<double> reverberated_left(sample_count, 0.0);
    std::vector<double> reverberated_right(sample_count, 0.0);
    schroeder_reverb(left.data(), right.data(), sample_count, 8, 0.5, 0.8, 0.2, 0.25, 48000.0,
                     reverberated_left.data(), reverberated_right.data());

    const double identity_sos[] = { 1.0, 0.0, 0.0, 1.0, 0.0, 0.0 };
    std::vector<double> filtered(sample_count, 0.0);
    biquad_sos_filter(identity_sos, 1, left.data(), sample_count, filtered.data());

    std::vector<double> smoothed(sample_count, 0.0);
    smooth_attack_release(left.data(), sample_count, 0.2, 0.8, 0.0, false, smoothed.data());

    std::vector<double> levels(sample_count, -60.0);
    levels[0] = -3.0;
    std::vector<double> gated(sample_count, 0.0);
    gate_envelope(levels.data(), sample_count, -20.0, 0.2, 0.8, 4, 1.0, 0.0, gated.data());

    std::vector<double> threshold(sample_count, 0.0);
    rolling_median_mad_threshold(left.data(), sample_count, 8, 0.015, 3.0, threshold.data());

    double best_correlation = 0.0;
    int best_lag = 0;
    direct_cross_correlation(left.data(), right.data(), sample_count, 8, &best_correlation, &best_lag);

    if (!all_finite(gain) || !all_finite(limited) || !all_finite(saturated)
        || !all_finite(reverberated_left) || !all_finite(reverberated_right)
        || !all_finite(filtered) || !all_finite(smoothed) || !all_finite(gated)
        || !all_finite(threshold)
        || !std::isfinite(best_correlation) || best_correlation < 0.99 || best_lag != 0)
    {
        std::cerr << "recovered AutoMix kernel link/runtime smoke failed\n";
        return 1;
    }

    std::cout << "recovered AutoMix kernel link/runtime smoke passed\n";
    return 0;
}
