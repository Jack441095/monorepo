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

#if defined(KENN_HAS_ACCELERATE)
#include <Accelerate/Accelerate.h>
#endif

namespace nb = nanobind;

using FloatMatrixInput = nb::ndarray<nb::numpy, const float, nb::ndim<2>, nb::c_contig, nb::device::cpu>;

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

// scipy.signal.resample_poly(x, 4, 1) uses firwin(81, 0.25,
// window=("kaiser", 5.0)) * 4 by default. Keeping the audited coefficients
// here lets the native true-peak candidate use the same zero-phase FIR rather
// than substituting a perceptually different interpolator.
constexpr std::array<double, 81> kTruePeakFilter {{
    -1.4319646207876955e-18, -0.0011305975791844614, -0.0021031678617178758, -0.0019016679348927712,
    3.7090410940238961e-18, 0.0029265141089618871, 0.0050185309234718201, 0.0042523190668551048,
    -6.9891223043615986e-18, -0.0059320518437837155, -0.0097908339711988927, -0.0080261254612654931,
    1.1214237028997421e-17, 0.010605090076805454, 0.017115155028976113, 0.01375395907063175,
    -1.6183952382363027e-17, -0.017579165251157443, -0.02798327701095811, -0.022219885567699757,
    2.1564830647503017e-17, 0.027866916359520887, 0.044051484099836259, 0.034795254750361118,
    -2.6922559134588186e-17, -0.043423086442114837, -0.068688534985681365, -0.054425491068782507,
    3.177298294598318e-17, 0.068972338798174965, 0.11058973007292544, 0.089283348532046142,
    -3.5644656557647813e-17, -0.1201343501545469, -0.20188442282305527, -0.17397774297154042,
    3.8143133424221183e-17, 0.29654281960437512, 0.63347608687987322, 0.89963257101020833,
    1.0006365650891118, 0.89963257101020833, 0.63347608687987322, 0.29654281960437512,
    3.8143133424221183e-17, -0.17397774297154042, -0.20188442282305527, -0.1201343501545469,
    -3.5644656557647813e-17, 0.089283348532046142, 0.11058973007292544, 0.068972338798174965,
    3.177298294598318e-17, -0.054425491068782507, -0.068688534985681365, -0.043423086442114837,
    -2.6922559134588186e-17, 0.034795254750361118, 0.044051484099836259, 0.027866916359520887,
    2.1564830647503017e-17, -0.022219885567699757, -0.02798327701095811, -0.017579165251157443,
    -1.6183952382363027e-17, 0.01375395907063175, 0.017115155028976113, 0.010605090076805454,
    1.1214237028997421e-17, -0.0080261254612654931, -0.0097908339711988927, -0.0059320518437837155,
    -6.9891223043615986e-18, 0.0042523190668551048, 0.0050185309234718201, 0.0029265141089618871,
    3.7090410940238961e-18, -0.0019016679348927712, -0.0021031678617178758, -0.0011305975791844614,
    -1.4319646207876955e-18,
}};

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

std::vector<BlockMeasurement> measure_blocks(
    const std::vector<std::vector<double>>& channels,
    double sample_rate,
    double block_seconds,
    double overlap)
{
    if (channels.empty() || channels.front().empty())
        return {};
    const auto frame_count = channels.front().size();
    const double duration = static_cast<double>(frame_count) / sample_rate;
    const double step = 1.0 - overlap;
    const auto block_count = static_cast<long long>(std::llround(
        (duration - block_seconds) / (block_seconds * step))) + 1;
    if (block_count <= 0)
        return {};

    const auto channel_count = channels.size();
    // The BS.1770 windows overlap heavily (75% for integrated loudness and
    // 97% for LRA). Calling vDSP_svesqD independently for every window would
    // rescan most samples many times. Build one prefix sum of squares per
    // channel so each block power is two reads instead of another full scan.
    // The accumulation stays in double, matching the existing native
    // channel representation and keeping the reference-level numerical
    // tolerance unchanged.
    std::vector<std::vector<double>> squared_prefix(channel_count);
    for (std::size_t channel = 0; channel < channel_count; ++channel) {
        const auto& source = channels[channel];
        auto& prefix = squared_prefix[channel];
        prefix.resize(frame_count + 1, 0.0);
        for (std::size_t index = 0; index < frame_count; ++index)
            prefix[index + 1] = prefix[index] + source[index] * source[index];
    }
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
    std::array<double, 82> padded_filter {};
    for (std::size_t index = 0; index < kTruePeakFilter.size(); ++index)
        padded_filter[index + 1] = kTruePeakFilter[index];
    double peak = 0.0;
#if defined(KENN_HAS_ACCELERATE)
    // Split the zero-inserted 4x interpolation into four polyphase FIRs.
    // Reversing the source lets vDSP_convD evaluate each phase as a forward
    // correlation while preserving scipy's zero-padded boundary behavior.
    // The scratch buffers are owned by true_peak_dbtp and reused across
    // channels/phases. This avoids one large allocation per phase and avoids
    // materialising a contiguous copy for each interleaved channel.
    std::fill(reversed.begin(), reversed.end(), 0.0);
    for (std::size_t index = 0; index < frame_count; ++index)
        reversed[41 + index] = static_cast<double>(samples[(frame_count - 1 - index) * sample_stride]);
    for (std::size_t phase = 0; phase < 4; ++phase) {
        const auto taps = (81 - phase) / 4 + 1;
        std::array<double, 21> coefficients {};
        for (std::size_t tap = 0; tap < taps; ++tap)
            coefficients[tap] = padded_filter[phase + tap * 4];
        const auto first_r = (41 - phase + 3) / 4;
        const auto last_r = (4 * frame_count + 40 - phase) / 4;
        if (last_r < first_r)
            continue;
        const auto output_count = last_r - first_r + 1;
        const auto source_offset = static_cast<std::ptrdiff_t>(41 + frame_count - 1 - last_r);
        vDSP_convD(
            reversed.data() + source_offset, 1, coefficients.data(), 1,
            output.data(), 1, static_cast<vDSP_Length>(output_count),
            static_cast<vDSP_Length>(taps));
        for (std::size_t index = 0; index < output_count; ++index)
            peak = std::max(peak, std::abs(output[index]));
    }
#else
    for (std::size_t output_index = 0; output_index < frame_count * 4; ++output_index) {
        const auto time_index = output_index + 41;
        double value = 0.0;
        for (std::size_t tap = 0; tap < padded_filter.size(); ++tap) {
            const auto source_index = time_index >= tap ? time_index - tap : 0;
            if (time_index < tap || source_index % 4 != 0)
                continue;
            const auto frame = source_index / 4;
            if (frame < frame_count)
                value += padded_filter[tap] * static_cast<double>(samples[frame * sample_stride]);
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
    // One reusable workspace covers all channels and all four polyphase
    // passes. The output vector is sized to the largest phase result; only
    // the prefix requested by vDSP_convD is read on each pass.
    std::vector<double> reversed(frame_count + 82, 0.0);
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

nb::dict loudness_metrics(FloatMatrixInput samples, std::size_t sample_rate)
{
    if (samples.ndim() != 2 || samples.shape(0) == 0 || samples.shape(1) == 0 || samples.shape(1) > 2)
        throw nb::value_error("samples must be a non-empty float32 matrix with one or two channels");
    if (sample_rate == 0)
        throw nb::value_error("sample_rate must be positive");
    if (samples.shape(0) < static_cast<std::size_t>(0.4 * sample_rate))
        throw nb::value_error("samples are shorter than the 400 ms BS.1770 gating block");

    std::vector<std::vector<double>> filtered;
    std::optional<double> true_peak;
    {
        nb::gil_scoped_release release;
        true_peak = true_peak_dbtp(samples.data(), samples.shape(0), samples.shape(1));
        filtered = k_weight_channels(samples.data(), samples.shape(0), samples.shape(1), static_cast<double>(sample_rate));
    }
    const auto integrated_blocks = measure_blocks(filtered, static_cast<double>(sample_rate), 0.4, 0.75);
    const auto integrated = integrated_loudness(integrated_blocks);

    const auto silence_count = static_cast<std::size_t>(1.5 * sample_rate);
    for (auto& channel : filtered)
        channel.resize(channel.size() + silence_count, 0.0);
    const auto lra_blocks = measure_blocks(filtered, static_cast<double>(sample_rate), 3.0, 0.97);
    const auto lra = loudness_range(lra_blocks);

    nb::dict output;
    if (integrated.has_value())
        output["integrated_lufs"] = *integrated;
    else
        output["integrated_lufs"] = nb::none();
    if (lra.has_value() && std::isfinite(*lra))
        output["loudness_range_lu"] = *lra;
    else
        output["loudness_range_lu"] = nb::none();
    if (true_peak.has_value() && std::isfinite(*true_peak))
        output["true_peak_dbtp"] = *true_peak;
    else
        output["true_peak_dbtp"] = nb::none();
    output["backend"] = "cpp-native-k-weighting";
    return output;
}

} // namespace

void init_loudness_bindings(nb::module_& module)
{
    module.def("loudness_metrics", &loudness_metrics,
               nb::arg("samples"), nb::arg("sample_rate"),
               "Compute opt-in BS.1770 K-weighted integrated loudness and LRA.");
}
