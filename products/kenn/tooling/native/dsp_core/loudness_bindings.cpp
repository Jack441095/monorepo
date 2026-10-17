#include "loudness_bindings.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <numbers>
#include <optional>
#include <stdexcept>
#include <utility>
#include <vector>

#include <nanobind/ndarray.h>
#include <nanobind/nanobind.h>
#include <nanobind/stl/vector.h>

#if defined(KENN_HAS_ACCELERATE)
#include <Accelerate/Accelerate.h>
#endif

namespace nb = nanobind;

using FloatMatrixInput = nb::ndarray<nb::numpy, const float, nb::ndim<2>, nb::c_contig, nb::device::cpu>;
using DoubleVectorInput = nb::ndarray<nb::numpy, const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

namespace {

struct Biquad {
    double b0 = 0.0;
    double b1 = 0.0;
    double b2 = 0.0;
    double a1 = 0.0;
    double a2 = 0.0;
};

struct BlockMeasurement {
    double loudness = -std::numeric_limits<double>::infinity();
    std::vector<double> channel_powers;
};

// True peak is read at 8x since 17 Oct 2026 (owner's call), in step with
// TRUE_PEAK_OVERSAMPLE_FACTOR in local_engine.py, which records the tone sweep.
// The whole loudness call took 0.34 s on 4 minutes of 44.1 kHz stereo noise
// (Jack's Mac, Accelerate build, 17 Oct 2026).
constexpr std::size_t kTruePeakUp = 8;
// scipy.signal.resample_poly(x, 8, 1) designs firwin(2 * 10 * 8 + 1, 1 / 8,
// window=("kaiser", 5.0)) * 8 by default. We design the same filter here rather
// than substituting another interpolator, so the Python reference and this
// kernel agree to rounding.
constexpr std::size_t kTruePeakHalfLength = 10 * kTruePeakUp;
constexpr std::size_t kTruePeakTaps = 2 * kTruePeakHalfLength + 1;
// resample_poly front-pads the filter by one zero and drops the first
// half-length + 1 outputs, which keeps the interpolation zero-phase.
constexpr std::size_t kTruePeakPadded = kTruePeakTaps + 1;
constexpr std::size_t kTruePeakDelay = kTruePeakHalfLength + 1;
[[maybe_unused]] constexpr std::size_t kTruePeakPhaseTaps = kTruePeakTaps / kTruePeakUp + 1;

double bessel_i0(double x)
{
    // Power series; at the Kaiser beta of 5 it converges to double precision
    // in about 20 terms, so 60 is a cap, not the expected count.
    double sum = 1.0;
    double term = 1.0;
    for (int k = 1; k < 60; ++k) {
        term *= (x / (2.0 * k)) * (x / (2.0 * k));
        sum += term;
        if (term < sum * 1e-17)
            break;
    }
    return sum;
}

std::array<double, kTruePeakPadded> make_true_peak_filter()
{
    constexpr double beta = 5.0;
    constexpr double cutoff = 1.0 / static_cast<double>(kTruePeakUp);
    std::array<double, kTruePeakPadded> padded {};
    double sum = 0.0;
    for (std::size_t index = 0; index < kTruePeakTaps; ++index) {
        const double m = static_cast<double>(index) - static_cast<double>(kTruePeakHalfLength);
        const double x = cutoff * m;
        const double sinc = x == 0.0 ? 1.0 : std::sin(std::numbers::pi * x) / (std::numbers::pi * x);
        const double ratio = 2.0 * static_cast<double>(index) / static_cast<double>(kTruePeakTaps - 1) - 1.0;
        const double window = bessel_i0(beta * std::sqrt(1.0 - ratio * ratio)) / bessel_i0(beta);
        padded[index + 1] = cutoff * sinc * window;
        sum += padded[index + 1];
    }
    // firwin scales to unity gain at DC; resample_poly then multiplies by the
    // up factor to restore the level lost to zero insertion.
    for (auto& value : padded)
        value *= static_cast<double>(kTruePeakUp) / sum;
    return padded;
}

const std::array<double, kTruePeakPadded> kTruePeakFilter = make_true_peak_filter();

Biquad rbj_filter(double gain_db, double q, double frequency_hz, double sample_rate, bool high_shelf)
{
    const double amplitude = std::pow(10.0, gain_db / 40.0);
    const double w0 = 2.0 * std::numbers::pi * (frequency_hz / sample_rate);
    const double alpha = std::sin(w0) / (2.0 * q);
    const double cosine = std::cos(w0);
    double b0;
    double b1;
    double b2;
    double a0;
    double a1;
    double a2;
    if (high_shelf) {
        b0 = amplitude * ((amplitude + 1.0) + (amplitude - 1.0) * cosine + 2.0 * std::sqrt(amplitude) * alpha);
        b1 = -2.0 * amplitude * ((amplitude - 1.0) + (amplitude + 1.0) * cosine);
        b2 = amplitude * ((amplitude + 1.0) + (amplitude - 1.0) * cosine - 2.0 * std::sqrt(amplitude) * alpha);
        a0 = (amplitude + 1.0) - (amplitude - 1.0) * cosine + 2.0 * std::sqrt(amplitude) * alpha;
        a1 = 2.0 * ((amplitude - 1.0) - (amplitude + 1.0) * cosine);
        a2 = (amplitude + 1.0) - (amplitude - 1.0) * cosine - 2.0 * std::sqrt(amplitude) * alpha;
    } else {
        b0 = (1.0 + cosine) / 2.0;
        b1 = -(1.0 + cosine);
        b2 = (1.0 + cosine) / 2.0;
        a0 = 1.0 + alpha;
        a1 = -2.0 * cosine;
        a2 = 1.0 - alpha;
    }
    return { b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0 };
}

#if !defined(KENN_HAS_ACCELERATE)
void apply_biquad(std::vector<double>& values, const Biquad& filter)
{
    double x1 = 0.0;
    double x2 = 0.0;
    double y1 = 0.0;
    double y2 = 0.0;
    for (auto& value : values) {
        const double input = value;
        const double output = filter.b0 * input + filter.b1 * x1 + filter.b2 * x2
            - filter.a1 * y1 - filter.a2 * y2;
        value = output;
        x2 = x1;
        x1 = input;
        y2 = y1;
        y1 = output;
    }
}
#endif

std::vector<std::vector<double>> k_weight_channels(
    const float* samples,
    std::size_t frame_count,
    std::size_t channel_count,
    double sample_rate)
{
    std::vector<std::vector<double>> channels(channel_count, std::vector<double>(frame_count));
    const auto shelf = rbj_filter(4.0, 1.0 / std::sqrt(2.0), 1500.0, sample_rate, true);
    const auto highpass = rbj_filter(0.0, 0.5, 38.0, sample_rate, false);
#if defined(KENN_HAS_ACCELERATE)
    const std::array<double, 10> coefficients {{
        shelf.b0, shelf.b1, shelf.b2, shelf.a1, shelf.a2,
        highpass.b0, highpass.b1, highpass.b2, highpass.a1, highpass.a2,
    }};
    auto* setup = vDSP_biquad_CreateSetupD(coefficients.data(), 2);
    if (setup == nullptr)
        throw std::runtime_error("Accelerate K-weighting setup allocation failed");
#endif
    for (std::size_t channel = 0; channel < channel_count; ++channel) {
        auto& output = channels[channel];
        for (std::size_t frame = 0; frame < frame_count; ++frame)
            output[frame] = static_cast<double>(samples[frame * channel_count + channel]);
        // These are the exact RBJ K-weighting stages used by pyloudnorm's
        // default Meter("K-weighting") path.
#if defined(KENN_HAS_ACCELERATE)
        std::array<double, 6> delay {};
        vDSP_biquadD(setup, delay.data(), output.data(), 1, output.data(), 1,
                     static_cast<vDSP_Length>(frame_count));
#else
        apply_biquad(output, shelf);
        apply_biquad(output, highpass);
#endif
    }
#if defined(KENN_HAS_ACCELERATE)
    vDSP_biquad_DestroySetupD(setup);
#endif
    return channels;
}

// The BS.1770 and EBU Tech 3341/3342 windows overlap heavily (75% for
// integrated/momentary, 67% for 1 Hz short-term, and 97% for pyloudnorm LRA).
// Build one double-precision prefix sum of squares per channel so every block
// power in all four passes is two reads instead of another full scan.
std::vector<std::vector<double>> build_squared_prefix(
    const std::vector<std::vector<double>>& channels)
{
    const auto channel_count = channels.size();
    const auto frame_count = channel_count > 0 ? channels.front().size() : 0;
    std::vector<std::vector<double>> squared_prefix(channel_count);
    for (std::size_t channel = 0; channel < channel_count; ++channel) {
        const auto& source = channels[channel];
        auto& prefix = squared_prefix[channel];
        prefix.resize(frame_count + 1, 0.0);
        for (std::size_t index = 0; index < frame_count; ++index)
            prefix[index + 1] = prefix[index] + source[index] * source[index];
    }
    return squared_prefix;
}

std::vector<BlockMeasurement> measure_blocks(
    const std::vector<std::vector<double>>& squared_prefix,
    std::size_t frame_count,
    double sample_rate,
    double block_seconds,
    double overlap)
{
    if (squared_prefix.empty() || frame_count == 0)
        return {};
    const double duration = static_cast<double>(frame_count) / sample_rate;
    const double step = 1.0 - overlap;
    const auto block_count = static_cast<long long>(std::llround(
        (duration - block_seconds) / (block_seconds * step))) + 1;
    if (block_count <= 0)
        return {};

    const auto channel_count = squared_prefix.size();
    std::vector<BlockMeasurement> result;
    result.reserve(static_cast<std::size_t>(block_count));
    for (long long block = 0; block < block_count; ++block) {
        const auto lower = static_cast<std::size_t>(
            block_seconds * (static_cast<double>(block) * step) * sample_rate);
        const auto upper = std::min(frame_count, static_cast<std::size_t>(
            block_seconds * (static_cast<double>(block) * step + 1.0) * sample_rate));
        if (upper <= lower)
            continue;
        BlockMeasurement measurement;
        measurement.channel_powers.resize(channel_count, 0.0);
        for (std::size_t channel = 0; channel < channel_count; ++channel) {
            const auto& prefix = squared_prefix[channel];
            const double sum = prefix[upper] - prefix[lower];
            measurement.channel_powers[channel] = sum / (block_seconds * sample_rate);
        }
        double total_power = 0.0;
        for (const auto power : measurement.channel_powers)
            total_power += power;
        if (total_power > 0.0)
            measurement.loudness = -0.691 + 10.0 * std::log10(total_power);
        result.push_back(std::move(measurement));
    }
    return result;
}

// Evaluates full-length K-weighted rectangular windows at an integer sample
// hop (0.4 s at 0.1 s hop for momentary, 3.0 s at 1.0 s hop for short-term).
// Windows below the -70.0 LUFS BS.1770 absolute gate are omitted so digital
// silence never reports a finite reading.
std::vector<double> measure_sliding_windows(
    const std::vector<std::vector<double>>& squared_prefix,
    std::size_t frame_count,
    double sample_rate,
    double window_seconds,
    double hop_seconds)
{
    const auto window = static_cast<std::size_t>(window_seconds * sample_rate);
    const auto hop = static_cast<std::size_t>(hop_seconds * sample_rate);
    if (squared_prefix.empty() || window == 0 || hop == 0 || frame_count < window)
        return {};
    const auto channel_count = squared_prefix.size();
    std::vector<double> values;
    values.reserve((frame_count - window) / hop + 1);
    for (std::size_t start = 0; start + window <= frame_count; start += hop) {
        const auto upper = start + window;
        double total_power = 0.0;
        for (std::size_t channel = 0; channel < channel_count; ++channel) {
            const auto& prefix = squared_prefix[channel];
            total_power += (prefix[upper] - prefix[start]) / static_cast<double>(window);
        }
        if (total_power > 0.0) {
            const double loudness = -0.691 + 10.0 * std::log10(total_power);
            if (loudness >= -70.0 && std::isfinite(loudness))
                values.push_back(loudness);
        }
    }
    return values;
}

std::optional<double> integrated_loudness(const std::vector<BlockMeasurement>& blocks)
{
    if (blocks.empty())
        return std::nullopt;
    std::vector<std::size_t> absolute;
    for (std::size_t index = 0; index < blocks.size(); ++index) {
        if (blocks[index].loudness >= -70.0)
            absolute.push_back(index);
    }
    if (absolute.empty())
        return std::nullopt;

    const auto channel_count = blocks.front().channel_powers.size();
    std::vector<double> gated_power(channel_count, 0.0);
    for (const auto index : absolute) {
        for (std::size_t channel = 0; channel < channel_count; ++channel)
            gated_power[channel] += blocks[index].channel_powers[channel];
    }
    double absolute_power = 0.0;
    for (auto& power : gated_power) {
        power /= static_cast<double>(absolute.size());
        absolute_power += power;
    }
    if (absolute_power <= 0.0)
        return std::nullopt;
    const double relative_threshold = -0.691 + 10.0 * std::log10(absolute_power) - 10.0;

    std::vector<std::size_t> relative;
    for (const auto index : absolute) {
        if (blocks[index].loudness > relative_threshold)
            relative.push_back(index);
    }
    if (relative.empty())
        return std::nullopt;
    std::fill(gated_power.begin(), gated_power.end(), 0.0);
    for (const auto index : relative) {
        for (std::size_t channel = 0; channel < channel_count; ++channel)
            gated_power[channel] += blocks[index].channel_powers[channel];
    }
    double relative_power = 0.0;
    for (const auto power : gated_power)
        relative_power += power / static_cast<double>(relative.size());
    return relative_power > 0.0
        ? std::optional<double>(-0.691 + 10.0 * std::log10(relative_power))
        : std::nullopt;
}

double percentile(std::vector<double> values, double fraction)
{
    if (values.empty())
        return std::numeric_limits<double>::quiet_NaN();
    std::sort(values.begin(), values.end());
    const double position = fraction * static_cast<double>(values.size() - 1);
    const auto lower = static_cast<std::size_t>(std::floor(position));
    const auto upper = std::min(values.size() - 1, lower + 1);
    const double amount = position - static_cast<double>(lower);
    return values[lower] + (values[upper] - values[lower]) * amount;
}

std::optional<double> loudness_range(const std::vector<BlockMeasurement>& blocks)
{
    std::vector<double> absolute;
    for (const auto& block : blocks) {
        if (block.loudness >= -70.0)
            absolute.push_back(block.loudness);
    }
    if (absolute.empty())
        return std::nullopt;
    double mean_power = 0.0;
    for (const auto value : absolute)
        mean_power += std::pow(10.0, value / 10.0);
    mean_power /= static_cast<double>(absolute.size());
    if (mean_power <= 0.0)
        return std::nullopt;
    const double relative_threshold = 10.0 * std::log10(mean_power) - 20.0;
    std::vector<double> relative;
    for (const auto value : absolute) {
        if (value >= relative_threshold)
            relative.push_back(value);
    }
    if (relative.empty())
        return std::nullopt;
    return percentile(relative, 0.95) - percentile(relative, 0.10);
}

// EBU Tech 3342 loudness range over an explicit short-term LUFS sequence:
// -70.0 LUFS absolute gate and -20.0 LU relative gate, requiring at least two
// surviving windows at each stage so a single window cannot report 0.0 LU.
std::optional<double> loudness_range_from_short_term(const double* values, std::size_t count)
{
    std::vector<double> gated;
    gated.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        const double value = values[index];
        if (std::isfinite(value) && value > -70.0)
            gated.push_back(value);
    }
    if (gated.size() < 2)
        return std::nullopt;
    double mean_power = 0.0;
    for (const double value : gated)
        mean_power += std::pow(10.0, value / 10.0);
    mean_power /= static_cast<double>(gated.size());
    if (mean_power <= 0.0)
        return std::nullopt;
    const double relative_threshold = 10.0 * std::log10(mean_power) - 20.0;
    std::vector<double> kept;
    kept.reserve(gated.size());
    for (const double value : gated) {
        if (value > relative_threshold)
            kept.push_back(value);
    }
    if (kept.size() < 2)
        return std::nullopt;
    return percentile(kept, 0.95) - percentile(kept, 0.10);
}

std::optional<double> sample_peak_dbfs(const float* samples, std::size_t sample_count)
{
    if (sample_count == 0)
        return std::nullopt;
    float peak = 0.0f;
#if defined(KENN_HAS_ACCELERATE)
    vDSP_maxmgv(samples, 1, &peak, static_cast<vDSP_Length>(sample_count));
#else
    for (std::size_t index = 0; index < sample_count; ++index)
        peak = std::max(peak, std::abs(samples[index]));
#endif
    if (peak <= 0.0f)
        return std::nullopt;
    return 20.0 * std::log10(static_cast<double>(peak));
}

double true_peak_channel(
    const float* samples,
    std::size_t frame_count,
    std::size_t sample_stride
#if defined(KENN_HAS_ACCELERATE)
    ,
    std::vector<double>& reversed,
    std::vector<double>& output
#endif
)
{
    if (frame_count == 0)
        return 0.0;
    double peak = 0.0;
#if defined(KENN_HAS_ACCELERATE)
    // Split the zero-inserted interpolation into one polyphase FIR per output
    // phase. Reversing the source lets vDSP_convD evaluate each phase as a
    // forward correlation while preserving scipy's zero-padded boundary behavior.
    // The scratch buffers are owned by true_peak_dbtp and reused across
    // channels/phases. This avoids one large allocation per phase and avoids
    // materialising a contiguous copy for each interleaved channel.
    std::fill(reversed.begin(), reversed.end(), 0.0);
    for (std::size_t index = 0; index < frame_count; ++index)
        reversed[kTruePeakDelay + index] = static_cast<double>(samples[(frame_count - 1 - index) * sample_stride]);
    for (std::size_t phase = 0; phase < kTruePeakUp; ++phase) {
        const auto taps = (kTruePeakTaps - phase) / kTruePeakUp + 1;
        std::array<double, kTruePeakPhaseTaps> coefficients {};
        for (std::size_t tap = 0; tap < taps; ++tap)
            coefficients[tap] = kTruePeakFilter[phase + tap * kTruePeakUp];
        const auto first_r = (kTruePeakDelay - phase + kTruePeakUp - 1) / kTruePeakUp;
        const auto last_r = (kTruePeakUp * frame_count + kTruePeakDelay - 1 - phase) / kTruePeakUp;
        if (last_r < first_r)
            continue;
        const auto output_count = last_r - first_r + 1;
        const auto source_offset = static_cast<std::ptrdiff_t>(kTruePeakDelay + frame_count - 1 - last_r);
        vDSP_convD(
            reversed.data() + source_offset, 1, coefficients.data(), 1,
            output.data(), 1, static_cast<vDSP_Length>(output_count),
            static_cast<vDSP_Length>(taps));
        for (std::size_t index = 0; index < output_count; ++index)
            peak = std::max(peak, std::abs(output[index]));
    }
#else
    for (std::size_t output_index = 0; output_index < frame_count * kTruePeakUp; ++output_index) {
        const auto time_index = output_index + kTruePeakDelay;
        double value = 0.0;
        for (std::size_t tap = 0; tap < kTruePeakFilter.size(); ++tap) {
            const auto source_index = time_index >= tap ? time_index - tap : 0;
            if (time_index < tap || source_index % kTruePeakUp != 0)
                continue;
            const auto frame = source_index / kTruePeakUp;
            if (frame < frame_count)
                value += kTruePeakFilter[tap] * static_cast<double>(samples[frame * sample_stride]);
        }
        peak = std::max(peak, std::abs(value));
    }
#endif
    return peak;
}

std::optional<double> true_peak_dbtp(
    const float* samples,
    std::size_t frame_count,
    std::size_t channel_count)
{
    double peak = 0.0;
#if defined(KENN_HAS_ACCELERATE)
    // One reusable workspace covers all channels and all eight polyphase
    // passes. The output vector is sized to the largest phase result; only
    // the prefix requested by vDSP_convD is read on each pass.
    std::vector<double> reversed(frame_count + kTruePeakPadded, 0.0);
    std::vector<double> output(frame_count + 1, 0.0);
#endif
    for (std::size_t channel = 0; channel < channel_count; ++channel) {
#if defined(KENN_HAS_ACCELERATE)
        peak = std::max(peak, true_peak_channel(
            samples + channel,
            frame_count,
            channel_count,
            reversed,
            output
        ));
#else
        peak = std::max(peak, true_peak_channel(
            samples + channel,
            frame_count,
            channel_count
        ));
#endif
    }
    if (peak <= 0.0)
        return std::nullopt;
    return 20.0 * std::log10(peak);
}

nb::object true_peak_dbtp_binding(FloatMatrixInput samples)
{
    if (samples.ndim() != 2 || samples.shape(0) == 0 || samples.shape(1) == 0)
        throw nb::value_error("samples must be a non-empty 2D float32 matrix");
    std::optional<double> result;
    {
        nb::gil_scoped_release release;
        result = true_peak_dbtp(samples.data(), samples.shape(0), samples.shape(1));
    }
    if (result.has_value() && std::isfinite(*result))
        return nb::cast(*result);
    return nb::none();
}

nb::object loudness_range_lu_binding(DoubleVectorInput short_term)
{
    if (short_term.ndim() != 1)
        throw nb::value_error("short_term must be a 1D float64 array");
    std::optional<double> result;
    {
        nb::gil_scoped_release release;
        result = loudness_range_from_short_term(short_term.data(), short_term.shape(0));
    }
    if (result.has_value() && std::isfinite(*result))
        return nb::cast(*result);
    return nb::none();
}

std::vector<double> windowed_loudness_binding(
    FloatMatrixInput samples,
    std::size_t sample_rate,
    double window_s,
    double hop_s)
{
    if (samples.ndim() != 2 || samples.shape(0) == 0 || samples.shape(1) == 0 || samples.shape(1) > 2)
        throw nb::value_error("samples must be a non-empty float32 matrix with one or two channels");
    if (sample_rate == 0 || window_s <= 0.0 || hop_s <= 0.0)
        throw nb::value_error("sample_rate, window_s and hop_s must be positive");
    const auto frame_count = samples.shape(0);
    const auto channel_count = samples.shape(1);
    const float* data = samples.data();
    std::vector<double> result;
    {
        nb::gil_scoped_release release;
        const auto filtered = k_weight_channels(data, frame_count, channel_count, static_cast<double>(sample_rate));
        const auto squared_prefix = build_squared_prefix(filtered);
        result = measure_sliding_windows(
            squared_prefix, frame_count, static_cast<double>(sample_rate), window_s, hop_s);
    }
    return result;
}

nb::dict loudness_metrics(FloatMatrixInput samples, std::size_t sample_rate)
{
    if (samples.ndim() != 2 || samples.shape(0) == 0 || samples.shape(1) == 0 || samples.shape(1) > 2)
        throw nb::value_error("samples must be a non-empty float32 matrix with one or two channels");
    if (sample_rate == 0)
        throw nb::value_error("sample_rate must be positive");
    const auto frame_count = samples.shape(0);
    const auto channel_count = samples.shape(1);
    if (frame_count < static_cast<std::size_t>(0.4 * sample_rate))
        throw nb::value_error("samples are shorter than the 400 ms BS.1770 gating block");

    const float* data = samples.data();
    std::optional<double> true_peak;
    std::optional<double> sample_peak;
    std::optional<double> integrated;
    std::optional<double> lra;
    std::optional<double> short_term_lra;
    std::optional<double> momentary_max;
    std::optional<double> short_term_max;
    {
        nb::gil_scoped_release release;
        const double rate = static_cast<double>(sample_rate);
        true_peak = true_peak_dbtp(data, frame_count, channel_count);
        sample_peak = sample_peak_dbfs(data, frame_count * channel_count);
        const auto filtered = k_weight_channels(data, frame_count, channel_count, rate);
        auto squared_prefix = build_squared_prefix(filtered);

        const auto integrated_blocks = measure_blocks(squared_prefix, frame_count, rate, 0.4, 0.75);
        integrated = integrated_loudness(integrated_blocks);

        const auto momentary_windows = measure_sliding_windows(squared_prefix, frame_count, rate, 0.4, 0.1);
        if (!momentary_windows.empty())
            momentary_max = *std::max_element(momentary_windows.begin(), momentary_windows.end());

        const auto short_term_windows = measure_sliding_windows(squared_prefix, frame_count, rate, 3.0, 1.0);
        if (!short_term_windows.empty()) {
            short_term_max = *std::max_element(short_term_windows.begin(), short_term_windows.end());
            short_term_lra = loudness_range_from_short_term(
                short_term_windows.data(), short_term_windows.size());
        }

        // pyloudnorm appends 1.5 s of silence for its 97%-overlap LRA pass;
        // extending the prefix sum with its final value avoids resizing the
        // channel buffers or rescanning the K-weighted frames a second time.
        const auto silence_count = static_cast<std::size_t>(1.5 * sample_rate);
        for (auto& prefix : squared_prefix)
            prefix.resize(frame_count + silence_count + 1, prefix.back());
        const auto lra_blocks = measure_blocks(
            squared_prefix, frame_count + silence_count, rate, 3.0, 0.97);
        lra = loudness_range(lra_blocks);
    }

    nb::dict output;
    if (integrated.has_value() && std::isfinite(*integrated))
        output["integrated_lufs"] = *integrated;
    else
        output["integrated_lufs"] = nb::none();
    if (lra.has_value() && std::isfinite(*lra))
        output["loudness_range_lu"] = *lra;
    else
        output["loudness_range_lu"] = nb::none();
    if (short_term_lra.has_value() && std::isfinite(*short_term_lra))
        output["short_term_lra_lu"] = *short_term_lra;
    else
        output["short_term_lra_lu"] = nb::none();
    if (short_term_max.has_value() && std::isfinite(*short_term_max))
        output["short_term_max_lufs"] = *short_term_max;
    else
        output["short_term_max_lufs"] = nb::none();
    if (momentary_max.has_value() && std::isfinite(*momentary_max))
        output["momentary_max_lufs"] = *momentary_max;
    else
        output["momentary_max_lufs"] = nb::none();
    if (true_peak.has_value() && std::isfinite(*true_peak))
        output["true_peak_dbtp"] = *true_peak;
    else
        output["true_peak_dbtp"] = nb::none();
    if (sample_peak.has_value() && std::isfinite(*sample_peak))
        output["sample_peak_dbfs"] = *sample_peak;
    else
        output["sample_peak_dbfs"] = nb::none();
    output["backend"] = "cpp-native-k-weighting";
    return output;
}

} // namespace

void init_loudness_bindings(nb::module_& module)
{
    module.def("loudness_metrics", &loudness_metrics,
               nb::arg("samples"), nb::arg("sample_rate"),
               "Compute BS.1770 K-weighted integrated/momentary/short-term loudness, LRA and 8x true peak.");
    module.def("true_peak_dbtp", &true_peak_dbtp_binding,
               nb::arg("samples"),
               "Compute 8x oversampled inter-sample true peak in dBTP for a (frames, channels) float32 matrix.");
    module.def("loudness_range_lu", &loudness_range_lu_binding,
               nb::arg("short_term"),
               "Compute EBU Tech 3342 gated loudness range (P95 - P10) from short-term LUFS values.");
    module.def("windowed_loudness", &windowed_loudness_binding,
               nb::arg("samples"), nb::arg("sample_rate"), nb::arg("window_s"), nb::arg("hop_s"),
               "Compute K-weighted rectangular window LUFS values at the given window and hop seconds.");
}
