#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <numbers>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#if defined(KENN_HAS_ACCELERATE)
#include <Accelerate/Accelerate.h>
#endif

#include <nanobind/ndarray.h>
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>

#include "fft_core.hpp"
#include "automix_bindings.hpp"
#include "loudness_bindings.hpp"

namespace nb = nanobind;
using FloatInput = nb::ndarray<nb::numpy, const float, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using ByteInput = nb::ndarray<nb::numpy, const std::uint8_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using FloatOutput = nb::ndarray<nb::numpy, double, nb::shape<-1, -1>, nb::device::cpu>;
using FloatVectorOutput = nb::ndarray<nb::numpy, float, nb::shape<-1>, nb::device::cpu>;
using DoubleVectorOutput = nb::ndarray<nb::numpy, double, nb::shape<-1>, nb::device::cpu>;

namespace {

struct SpectralPeak {
    double frequency_hz = 0.0;
    double level_dbfs = 0.0;
    double bandwidth_hz = 0.0;
    double confidence = 0.0;
    std::size_t fft_bin = 0;
};

struct SpectralResult {
    std::vector<double> averaged;
    std::vector<double> windows;
    std::vector<float> window_rms;
    std::vector<std::size_t> starts;
    std::array<double, 5> band_energy_dbfs {};
    std::vector<double> ltas_band_levels;
    std::vector<SpectralPeak> averaged_peaks;
    std::vector<std::vector<SpectralPeak>> window_peaks;
    bool has_band_energy = false;
    std::size_t fft_size = 0;
    double window_sum = 0.0;
    std::string backend = "cpp-scalar";
};


struct BandEnergyResult {
    std::vector<double> values;
    std::size_t frames = 0;
    std::size_t bands = 7;
    std::string backend = "cpp-scalar";
};

struct ChannelSummary {
    double rms = 0.0;
    double peak = 0.0;
    double dc_offset = 0.0;
    std::size_t clipped_sample_count = 0;
    std::size_t clipped_run_count = 0;
    std::size_t silence_count = 0;
};

struct DecodedWav {
    std::vector<std::unique_ptr<float[]>> channels;
    std::size_t frame_count = 0;
    std::size_t sample_rate = 0;
    std::size_t bit_depth = 0;
};

constexpr std::array<std::pair<double, double>, 7> kMaskingBands {{
    { 20.0, 80.0 },
    { 80.0, 250.0 },
    { 250.0, 500.0 },
    { 500.0, 2000.0 },
    { 2000.0, 4000.0 },
    { 4000.0, 8000.0 },
    { 8000.0, 16000.0 },
}};

constexpr double kClipThreshold = 0.9660508789898133; // 10^(-0.3/20)
constexpr double kSilenceThreshold = 0.001; // 10^(-60/20)

std::uint16_t read_u16(const std::uint8_t* data)
{
    return static_cast<std::uint16_t>(data[0]) |
        (static_cast<std::uint16_t>(data[1]) << 8);
}

std::uint32_t read_u32(const std::uint8_t* data)
{
    return static_cast<std::uint32_t>(data[0]) |
        (static_cast<std::uint32_t>(data[1]) << 8) |
        (static_cast<std::uint32_t>(data[2]) << 16) |
        (static_cast<std::uint32_t>(data[3]) << 24);
}

std::int32_t read_i24(const std::uint8_t* data)
{
    std::int32_t value = static_cast<std::int32_t>(data[0]) |
        (static_cast<std::int32_t>(data[1]) << 8) |
        (static_cast<std::int32_t>(data[2]) << 16);
    if ((value & 0x00800000) != 0)
        value |= static_cast<std::int32_t>(0xff000000);
    return value;
}

DecodedWav decode_pcm(const std::uint8_t* payload, std::size_t length)
{
    if (length < 12 || std::string(reinterpret_cast<const char*>(payload), 4) != "RIFF" ||
        std::string(reinterpret_cast<const char*>(payload + 8), 4) != "WAVE")
        throw nb::value_error("invalid WAV: file does not start with RIFF/WAVE id");

    bool have_format = false;
    std::size_t channels = 0;
    std::size_t sample_width = 0;
    std::size_t sample_rate = 0;
    std::uint16_t audio_format = 0;
    const std::uint8_t* raw = nullptr;
    std::size_t raw_length = 0;
    std::size_t position = 12;
    while (position + 8 <= length) {
        const auto* chunk = payload + position;
        const auto chunk_size = static_cast<std::size_t>(read_u32(chunk + 4));
        const auto data_start = position + 8;
        const auto available = std::min(chunk_size, length - data_start);
        const auto* chunk_data = payload + data_start;
        if (std::string(reinterpret_cast<const char*>(chunk), 4) == "fmt " && available >= 16) {
            audio_format = read_u16(chunk_data);
            channels = read_u16(chunk_data + 2);
            sample_rate = read_u32(chunk_data + 4);
            sample_width = read_u16(chunk_data + 14) / 8;
            if (audio_format == 0xfffe && available >= 26)
                audio_format = read_u16(chunk_data + 24);
            have_format = true;
        } else if (std::string(reinterpret_cast<const char*>(chunk), 4) == "data") {
            raw = chunk_data;
            raw_length = available;
        }
        const auto advance = 8 + chunk_size + (chunk_size & 1U);
        if (advance > length - position)
            break;
        position += advance;
    }

    if (!have_format)
        throw nb::value_error("invalid WAV: fmt chunk missing in WAV file");
    if (raw == nullptr)
        throw nb::value_error("invalid WAV: data chunk missing in WAV file");
    if (channels != 1 && channels != 2)
        throw nb::value_error("only mono and stereo WAV files are supported");
    if (sample_width != 2 && sample_width != 3 && sample_width != 4)
        throw nb::value_error("only 16-bit, 24-bit, and 32-bit WAV files are supported");
    if (audio_format != 1 && audio_format != 3)
        throw nb::value_error("unsupported WAV audio format tag");
    if (sample_rate == 0 || raw_length == 0)
        throw nb::value_error("WAV contains no audio frames");

    const auto bytes_per_frame = channels * sample_width;
    const auto frame_count = raw_length / bytes_per_frame;
    if (frame_count == 0)
        throw nb::value_error("WAV contains no audio frames");
    DecodedWav result;
    result.sample_rate = sample_rate;
    result.bit_depth = sample_width * 8;
    result.frame_count = frame_count;
    result.channels.resize(channels);
    for (auto& channel : result.channels)
        channel = std::make_unique<float[]>(frame_count);
    for (std::size_t frame = 0; frame < frame_count; ++frame) {
        for (std::size_t channel = 0; channel < channels; ++channel) {
            const auto* sample = raw + frame * bytes_per_frame + channel * sample_width;
            float value = 0.0f;
            if (sample_width == 2) {
                const auto integer = static_cast<std::int16_t>(read_u16(sample));
                value = static_cast<float>(integer) / 32768.0f;
            } else if (sample_width == 3) {
                value = static_cast<float>(read_i24(sample)) / 8388608.0f;
            } else if (audio_format == 3) {
                std::uint32_t bits = read_u32(sample);
                float decoded;
                std::memcpy(&decoded, &bits, sizeof(decoded));
                value = decoded;
            } else {
                const auto integer = static_cast<std::int32_t>(read_u32(sample));
                value = static_cast<float>(integer) / 2147483648.0f;
            }
            result.channels[channel][frame] = value;
        }
    }
    return result;
}

ChannelSummary summarize_channel(const float* samples, std::size_t length)
{
    ChannelSummary result;
    if (length == 0)
        return result;

    double sum = 0.0;
    double sum_squares = 0.0;
    bool in_clip_run = false;
    for (std::size_t index = 0; index < length; ++index)
    {
        const double value = static_cast<double>(samples[index]);
        const double magnitude = std::abs(value);
        sum += value;
        sum_squares += value * value;
        result.peak = std::max(result.peak, magnitude);
        if (magnitude >= kClipThreshold)
        {
            ++result.clipped_sample_count;
            if (!in_clip_run)
                ++result.clipped_run_count;
            in_clip_run = true;
        }
        else
        {
            in_clip_run = false;
        }
        if (magnitude < kSilenceThreshold)
            ++result.silence_count;
    }
    result.rms = std::sqrt(sum_squares / static_cast<double>(length));
    result.dc_offset = sum / static_cast<double>(length);
    return result;
}

double correlation_with_offsets(
    const float* left,
    const float* right,
    std::size_t length,
    double left_offset,
    double right_offset)
{
    if (length == 0)
        return 0.0;
    double numerator = 0.0;
    double left_energy = 0.0;
    double right_energy = 0.0;
    for (std::size_t index = 0; index < length; ++index)
    {
        const double left_delta = static_cast<double>(left[index]) - left_offset;
        const double right_delta = static_cast<double>(right[index]) - right_offset;
        numerator += left_delta * right_delta;
        left_energy += left_delta * left_delta;
        right_energy += right_delta * right_delta;
    }
    const double denominator = std::sqrt(left_energy * right_energy);
    if (denominator == 0.0)
        return 0.0;
    return std::max(-1.0, std::min(1.0, numerator / denominator));
}

#if defined(KENN_HAS_ACCELERATE)
class AccelerateFFTSetup {
public:
    explicit AccelerateFFTSetup(std::size_t fft_size)
    {
        std::size_t value = fft_size;
        while (value > 1)
        {
            value >>= 1;
            ++log2_size_;
        }
        setup_ = vDSP_create_fftsetupD(static_cast<vDSP_Length>(log2_size_), FFT_RADIX2);
        if (setup_ == nullptr)
            throw std::runtime_error("Accelerate FFT setup allocation failed");
        // Keep the vDSP scratch buffers with the setup.  The previous path
        // allocated three temporary buffers for every window/frame, which
        // made allocator traffic part of the DSP hot loop and obscured the
        // actual FFT cost for short buffers.
        real_.resize(fft_size / 2, 0.0);
        imag_.resize(fft_size / 2, 0.0);
    }

    ~AccelerateFFTSetup()
    {
        if (setup_ != nullptr)
            vDSP_destroy_fftsetupD(setup_);
    }

    AccelerateFFTSetup(const AccelerateFFTSetup&) = delete;
    AccelerateFFTSetup& operator=(const AccelerateFFTSetup&) = delete;

    void power_spectrum(const std::vector<double>& input, std::vector<double>& powers)
    {
        const auto fft_size = input.size();
        if (real_.size() != fft_size / 2) {
            real_.resize(fft_size / 2);
            imag_.resize(fft_size / 2);
        }
        DSPDoubleSplitComplex split { real_.data(), imag_.data() };
        // vDSP strides are expressed in scalar components for interleaved
        // complex input, so 2 advances one pair of adjacent real samples.
        // The real input buffer already has exactly the interleaved layout
        // vDSP expects; reinterpret it in place instead of copying every
        // even/odd pair into a temporary complex vector.
        vDSP_ctozD(reinterpret_cast<const DSPDoubleComplex*>(input.data()), 2, &split, 1,
                   static_cast<vDSP_Length>(fft_size / 2));
        vDSP_fft_zripD(setup_, &split, 1, static_cast<vDSP_Length>(log2_size_), FFT_FORWARD);

        powers.resize(fft_size / 2 + 1);
        // vDSP's packed real FFT has a factor-of-two amplitude convention;
        // match the unnormalised complex radix-2 reference power.
        constexpr double power_scale = 0.25;
        powers[0] = power_scale * split.realp[0] * split.realp[0];
        for (std::size_t bin = 1; bin < fft_size / 2; ++bin)
            powers[bin] = power_scale * (split.realp[bin] * split.realp[bin] + split.imagp[bin] * split.imagp[bin]);
        powers[fft_size / 2] = power_scale * split.imagp[0] * split.imagp[0];
    }

private:
    vDSP_Length log2_size_ = 0;
    FFTSetupD setup_ = nullptr;
    std::vector<double> real_;
    std::vector<double> imag_;
};
#endif

std::vector<SpectralPeak> find_dominant_peaks(
    const double* powers,
    std::size_t power_count,
    std::size_t sample_rate,
    std::size_t fft_size,
    double window_sum,
    std::size_t limit)
{
    std::vector<SpectralPeak> peaks;
    if (powers == nullptr || power_count < 3 || sample_rate == 0 || fft_size == 0 || limit == 0)
        return peaks;

    const auto max_power = *std::max_element(powers + 1, powers + power_count);
    struct Candidate {
        double frequency = 0.0;
        double level = 0.0;
    };
    std::vector<Candidate> candidates;
    candidates.reserve(power_count / 8);
    for (std::size_t index = 2; index + 1 < power_count; ++index) {
        if (powers[index] < max_power * 1e-5 || powers[index] < powers[index - 1] || powers[index] < powers[index + 1])
            continue;
        const double left = std::log(std::max(powers[index - 1], 1e-30));
        const double center = std::log(std::max(powers[index], 1e-30));
        const double right = std::log(std::max(powers[index + 1], 1e-30));
        const double denominator = left - 2.0 * center + right;
        double offset = std::abs(denominator) < 1e-12 ? 0.0 : 0.5 * (left - right) / denominator;
        offset = std::max(-0.5, std::min(0.5, offset));
        const double peak_power = std::max(powers[index], 1e-30);
        const double amplitude = 2.0 * std::sqrt(peak_power) / std::max(window_sum, 1.0);
        candidates.push_back({
            (static_cast<double>(index) + offset) * static_cast<double>(sample_rate) / static_cast<double>(fft_size),
            20.0 * std::log10(amplitude),
        });
    }
    std::stable_sort(candidates.begin(), candidates.end(), [](const Candidate& left, const Candidate& right) {
        return left.level > right.level;
    });

    const auto count = std::min(limit, candidates.size());
    peaks.reserve(count);
    for (std::size_t candidate_index = 0; candidate_index < count; ++candidate_index) {
        const auto& candidate = candidates[candidate_index];
        const auto rounded_bin = static_cast<long long>(std::floor(
            candidate.frequency * static_cast<double>(fft_size) / static_cast<double>(sample_rate) + 0.5));
        const auto bin_index = static_cast<std::size_t>(std::max<long long>(
            1, std::min<long long>(static_cast<long long>(power_count - 2), rounded_bin)));
        const double half_power = powers[bin_index] * 0.5;
        std::size_t left = bin_index;
        std::size_t right = bin_index;
        while (left > 1 && powers[left - 1] >= half_power)
            --left;
        while (right < power_count - 2 && powers[right + 1] >= half_power)
            ++right;
        const double level_offset = std::max(0.0, candidate.level - (-80.0));
        peaks.push_back({
            candidate.frequency,
            candidate.level,
            static_cast<double>(right - left + 1) * static_cast<double>(sample_rate) / static_cast<double>(fft_size),
            std::max(0.0, std::min(1.0, 0.55 + std::min(0.4, level_offset / 100.0))),
            bin_index,
        });
    }
    return peaks;
}

std::vector<SpectralPeak> find_dominant_peaks(
    const std::vector<double>& powers,
    std::size_t sample_rate,
    std::size_t fft_size,
    double window_sum,
    std::size_t limit)
{
    return find_dominant_peaks(powers.data(), powers.size(), sample_rate, fft_size, window_sum, limit);
}

SpectralResult compute_window_powers(
    const float* samples,
    std::size_t length,
    std::size_t requested_fft_size,
    std::size_t sample_rate,
    bool include_ltas)
{
    const auto fft_size = std::min<std::size_t>(kenn::dsp::next_power_of_two(std::max<std::size_t>(256, requested_fft_size)), 131072);
    const auto starts = kenn::dsp::window_starts(length, fft_size);
    const auto bins = fft_size / 2 + 1;
    SpectralResult result;
    result.fft_size = fft_size;
    result.starts = starts;
    result.window_sum = 0.0;
    std::vector<double> window(fft_size);
    for (std::size_t index = 0; index < fft_size; ++index)
    {
        window[index] = 0.5 - 0.5 * std::cos(2.0 * std::numbers::pi * static_cast<double>(index) / static_cast<double>(fft_size - 1));
        result.window_sum += window[index];
    }

    result.windows.resize(starts.size() * bins, 0.0);
    result.window_rms.resize(starts.size(), 0.0);
    result.averaged.resize(bins, 0.0);
    std::vector<double> segment(fft_size);
#if defined(KENN_HAS_ACCELERATE)
    AccelerateFFTSetup accelerate_setup(fft_size);
    std::vector<double> accelerated_powers;
    result.backend = "cpp-accelerate";
#else
    std::vector<kenn::dsp::Complex> spectrum(fft_size);
#endif
    for (std::size_t window_index = 0; window_index < starts.size(); ++window_index)
    {
        const auto start = starts[window_index];
        const auto valid_length = std::min(fft_size, length - start);
        double sum_squares = 0.0;
        for (std::size_t index = 0; index < fft_size; ++index)
        {
            const auto source_index = start + index;
            const auto sample = source_index < length ? static_cast<double>(samples[source_index]) : 0.0;
            if (index < valid_length)
                sum_squares += sample * sample;
            segment[index] = sample * window[index];
#if defined(KENN_HAS_ACCELERATE)
            // Keep the windowed input in a contiguous double buffer for vDSP's
            // real FFT.  Applying the window here avoids a second full pass.
#else
            spectrum[index] = segment[index];
#endif
        }
        result.window_rms[window_index] = static_cast<float>(std::sqrt(sum_squares / static_cast<double>(valid_length)));
#if defined(KENN_HAS_ACCELERATE)
        accelerate_setup.power_spectrum(segment, accelerated_powers);
        for (std::size_t bin = 0; bin < bins; ++bin)
        {
            const auto power = accelerated_powers[bin];
            result.windows[window_index * bins + bin] = power;
            result.averaged[bin] += power;
        }
#else
        kenn::dsp::fft_in_place(spectrum);
        for (std::size_t bin = 0; bin < bins; ++bin)
        {
            const auto power = std::norm(spectrum[bin]);
            result.windows[window_index * bins + bin] = power;
            result.averaged[bin] += power;
        }
#endif
    }
    for (auto& value : result.averaged)
        value /= static_cast<double>(starts.size());
    if (sample_rate > 0) {
        result.averaged_peaks = find_dominant_peaks(result.averaged, sample_rate, fft_size, result.window_sum, 12);
        result.window_peaks.resize(starts.size());
        for (std::size_t window_index = 0; window_index < starts.size(); ++window_index) {
            const auto first = result.windows.begin() + static_cast<std::ptrdiff_t>(window_index * bins);
            result.window_peaks[window_index] = find_dominant_peaks(
                &*first, bins, sample_rate, fft_size, result.window_sum, 12);
        }
        const std::array<std::pair<double, double>, 5> bands {{
            { 20.0, 250.0 },
            { 250.0, 500.0 },
            { 500.0, 2000.0 },
            { 2000.0, 6000.0 },
            { 6000.0, std::min(20000.0, static_cast<double>(sample_rate) / 2.0) },
        }};
        for (std::size_t band = 0; band < bands.size(); ++band) {
            double total = 0.0;
            for (std::size_t bin = 1; bin < bins; ++bin) {
                const auto frequency = static_cast<double>(bin) * static_cast<double>(sample_rate) /
                    static_cast<double>(fft_size);
                if (frequency >= bands[band].first && frequency < bands[band].second) {
                    const auto multiplier = bin == bins - 1 ? 1.0 : 2.0;
                    total += result.averaged[bin] * multiplier;
                }
            }
            const auto rms = std::sqrt(total / static_cast<double>(fft_size * fft_size));
            result.band_energy_dbfs[band] = rms <= 0.0 ? -120.0 : 20.0 * std::log10(rms);
        }
        result.has_band_energy = true;
        if (include_ltas) {
            constexpr std::size_t ltas_band_count = 40;
            const double lower = 20.0;
            const double upper = std::min(20000.0, static_cast<double>(sample_rate) / 2.0);
            result.ltas_band_levels.assign(ltas_band_count, std::numeric_limits<double>::quiet_NaN());
            if (upper > lower) {
                const double ratio = std::pow(upper / lower, 1.0 / static_cast<double>(ltas_band_count));
                for (std::size_t band = 0; band < ltas_band_count; ++band) {
                    const double low = lower * std::pow(ratio, static_cast<double>(band));
                    const double high = lower * std::pow(ratio, static_cast<double>(band + 1));
                    double sum = 0.0;
                    std::size_t count = 0;
                    for (std::size_t bin = 1; bin < bins; ++bin) {
                        const double frequency = static_cast<double>(bin) * static_cast<double>(sample_rate) /
                            static_cast<double>(fft_size);
                        if (frequency >= low && frequency < high) {
                            sum += result.averaged[bin];
                            ++count;
                        }
                    }
                    if (count > 0) {
                        const double rms = std::sqrt(sum / static_cast<double>(count));
                        result.ltas_band_levels[band] = rms <= 0.0 ? -120.0 : 20.0 * std::log10(rms);
                    }
                }
            }
        }
    }
    return result;
}

BandEnergyResult compute_band_energy(
    const float* samples,
    std::size_t length,
    std::size_t sample_rate,
    std::size_t fft_size,
    std::size_t hop)
{
    if (sample_rate == 0 || fft_size == 0 || hop == 0)
        throw std::invalid_argument("sample_rate, fft_size, and hop must be positive");

    BandEnergyResult result;
    result.frames = 1 + (length > fft_size ? (length - fft_size) / hop : 0);
    result.values.assign(result.frames * result.bands, 0.0);

    std::vector<double> window(fft_size);
    for (std::size_t index = 0; index < fft_size; ++index)
        window[index] = 0.5 - 0.5 * std::cos(2.0 * std::numbers::pi * static_cast<double>(index) / static_cast<double>(fft_size - 1));

    std::array<std::pair<std::size_t, std::size_t>, 7> bin_ranges {};
    for (std::size_t band = 0; band < kMaskingBands.size(); ++band)
    {
        const auto [low_hz, high_hz] = kMaskingBands[band];
        std::size_t first = 0;
        std::size_t last = 0;
        bool found = false;
        for (std::size_t bin = 0; bin <= fft_size / 2; ++bin)
        {
            const auto frequency = static_cast<double>(bin) * static_cast<double>(sample_rate) / static_cast<double>(fft_size);
            if (frequency >= low_hz && frequency < high_hz)
            {
                if (!found)
                    first = bin;
                last = bin + 1;
                found = true;
            }
        }
        bin_ranges[band] = found
            ? std::pair<std::size_t, std::size_t> { first, last }
            : std::pair<std::size_t, std::size_t> { 0, 0 };
    }

#if defined(KENN_HAS_ACCELERATE)
    AccelerateFFTSetup accelerate_setup(fft_size);
    std::vector<double> segment(fft_size);
    std::vector<double> accelerated_powers;
    result.backend = "cpp-accelerate";
#else
    std::vector<kenn::dsp::Complex> spectrum(fft_size);
#endif
    for (std::size_t frame = 0; frame < result.frames; ++frame)
    {
        const auto start = frame * hop;
        for (std::size_t index = 0; index < fft_size; ++index)
        {
            const auto source_index = start + index;
            const auto sample = source_index < length ? static_cast<double>(samples[source_index]) : 0.0;
#if defined(KENN_HAS_ACCELERATE)
            segment[index] = sample * window[index];
#else
            spectrum[index] = sample * window[index];
#endif
        }
#if defined(KENN_HAS_ACCELERATE)
        accelerate_setup.power_spectrum(segment, accelerated_powers);
#else
        kenn::dsp::fft_in_place(spectrum);
#endif
        for (std::size_t band = 0; band < result.bands; ++band)
        {
            const auto [first, last] = bin_ranges[band];
            if (first == last)
                continue;
            double sum = 0.0;
            for (std::size_t bin = first; bin < last; ++bin)
#if defined(KENN_HAS_ACCELERATE)
                sum += accelerated_powers[bin];
#else
                sum += std::norm(spectrum[bin]);
#endif
            result.values[frame * result.bands + band] = std::sqrt(sum / static_cast<double>(last - first));
        }
    }
    return result;
}

nb::dict channel_summary_dict(const ChannelSummary& summary, std::size_t length)
{
    nb::dict output;
    output["rms"] = summary.rms;
    output["peak"] = summary.peak;
    output["dc_offset"] = summary.dc_offset;
    output["clipped_sample_count"] = summary.clipped_sample_count;
    output["clipped_run_count"] = summary.clipped_run_count;
    output["silence_percentage"] = length == 0
        ? 0.0
        : 100.0 * static_cast<double>(summary.silence_count) / static_cast<double>(length);
    return output;
}

nb::dict mono_metrics(FloatInput samples)
{
    if (samples.ndim() != 1 || samples.shape(0) == 0)
        throw nb::value_error("samples must be a non-empty one-dimensional float32 NumPy array");
    ChannelSummary summary;
    {
        nb::gil_scoped_release release;
        summary = summarize_channel(samples.data(), samples.shape(0));
    }
    return channel_summary_dict(summary, samples.shape(0));
}

nb::dict stereo_metrics(FloatInput left, FloatInput right)
{
    if (left.ndim() != 1 || right.ndim() != 1 || left.shape(0) == 0 || right.shape(0) == 0)
        throw nb::value_error("left and right must be non-empty one-dimensional float32 NumPy arrays");
    if (left.shape(0) != right.shape(0))
        throw nb::value_error("left and right must have equal lengths");

    ChannelSummary left_summary;
    ChannelSummary right_summary;
    double channel_correlation = 0.0;
    double mono_sum_squares = 0.0;
    double side_sum_squares = 0.0;
    std::size_t mono_silence_count = 0;
    {
        nb::gil_scoped_release release;
        left_summary = summarize_channel(left.data(), left.shape(0));
        right_summary = summarize_channel(right.data(), right.shape(0));
        channel_correlation = correlation_with_offsets(
            left.data(), right.data(), left.shape(0), left_summary.dc_offset, right_summary.dc_offset);
        for (std::size_t index = 0; index < left.shape(0); ++index)
        {
            const double mid = (static_cast<double>(left(index)) + static_cast<double>(right(index))) * 0.5;
            const double side = (static_cast<double>(left(index)) - static_cast<double>(right(index))) * 0.5;
            mono_sum_squares += mid * mid;
            side_sum_squares += side * side;
            if (std::abs(mid) < kSilenceThreshold)
                ++mono_silence_count;
        }
    }

    nb::dict output;
    output["left"] = channel_summary_dict(left_summary, left.shape(0));
    output["right"] = channel_summary_dict(right_summary, right.shape(0));
    output["correlation"] = channel_correlation;
    output["mono_rms"] = std::sqrt(mono_sum_squares / static_cast<double>(left.shape(0)));
    output["side_rms"] = std::sqrt(side_sum_squares / static_cast<double>(left.shape(0)));
    output["mono_silence_percentage"] = 100.0 * static_cast<double>(mono_silence_count) / static_cast<double>(left.shape(0));
    return output;
}

FloatOutput make_owned_output(std::vector<double>&& values, std::size_t rows, std::size_t cols)
{
    auto* storage = new std::vector<double>(std::move(values));
    auto* data = storage->data();
    nb::capsule owner(storage, [](void* pointer) noexcept {
        delete static_cast<std::vector<double>*>(pointer);
    });
    return FloatOutput(data, { rows, cols }, owner);
}

FloatVectorOutput make_owned_float_vector_output(std::vector<float>&& values)
{
    auto* storage = new std::vector<float>(std::move(values));
    auto* data = storage->data();
    nb::capsule owner(storage, [](void* pointer) noexcept {
        delete static_cast<std::vector<float>*>(pointer);
    });
    return FloatVectorOutput(data, { storage->size() }, owner);
}

FloatVectorOutput make_owned_float_output(std::unique_ptr<float[]>&& values, std::size_t length)
{
    auto* data = values.release();
    nb::capsule owner(data, [](void* pointer) noexcept { delete[] static_cast<float*>(pointer); });
    return FloatVectorOutput(data, { length }, owner);
}

DoubleVectorOutput make_owned_double_vector_output(std::vector<double>&& values)
{
    auto* storage = new std::vector<double>(std::move(values));
    auto* data = storage->data();
    nb::capsule owner(storage, [](void* pointer) noexcept {
        delete static_cast<std::vector<double>*>(pointer);
    });
    return DoubleVectorOutput(data, { storage->size() }, owner);
}

nb::dict spectral_peak_dict(const SpectralPeak& peak)
{
    nb::dict output;
    output["frequency_hz"] = std::round(peak.frequency_hz * 1000.0) / 1000.0;
    output["level_dbfs"] = std::round(peak.level_dbfs * 100.0) / 100.0;
    output["bandwidth_hz"] = std::round(peak.bandwidth_hz * 1000.0) / 1000.0;
    output["confidence"] = std::round(peak.confidence * 100.0) / 100.0;
    output["fft_bin"] = peak.fft_bin;
    return output;
}

nb::list spectral_peak_list(const std::vector<SpectralPeak>& peaks)
{
    nb::list output;
    for (const auto& peak : peaks)
        output.append(spectral_peak_dict(peak));
    return output;
}

nb::dict decode_pcm_wav(ByteInput payload)
{
    if (payload.ndim() != 1 || payload.shape(0) == 0)
        throw nb::value_error("payload must be a non-empty one-dimensional uint8 NumPy array");

    DecodedWav decoded;
    {
        nb::gil_scoped_release release;
        decoded = decode_pcm(payload.data(), payload.shape(0));
    }
    nb::list channel_outputs;
    for (auto& channel : decoded.channels)
        channel_outputs.append(make_owned_float_output(std::move(channel), decoded.frame_count));
    nb::dict output;
    output["channels"] = channel_outputs;
    output["sample_rate"] = decoded.sample_rate;
    output["channel_count"] = decoded.channels.size();
    output["bit_depth"] = decoded.bit_depth;
    output["backend"] = "cpp-native-decoder";
    return output;
}

nb::dict spectral_power(FloatInput samples, std::size_t fft_size, std::size_t sample_rate, bool include_ltas)
{
    if (samples.ndim() != 1 || samples.shape(0) == 0)
        throw nb::value_error("samples must be a non-empty one-dimensional float32 NumPy array");
    if (fft_size == 0)
        throw nb::value_error("fft_size must be positive");

    SpectralResult result;
    {
        nb::gil_scoped_release release;
        result = compute_window_powers(samples.data(), samples.shape(0), fft_size, sample_rate, include_ltas);
    }

    const auto bins = result.fft_size / 2 + 1;
    auto averaged = make_owned_output(std::move(result.averaged), 1, bins);
    auto windows = make_owned_output(std::move(result.windows), result.starts.size(), bins);
    auto window_rms = make_owned_float_vector_output(std::move(result.window_rms));
    nb::list starts;
    for (auto value : result.starts)
        starts.append(value);
    nb::dict output;
    output["powers"] = averaged;
    output["window_powers"] = windows;
    output["window_rms"] = window_rms;
    if (result.has_band_energy) {
        nb::dict bands;
        for (std::size_t index = 0; index < result.band_energy_dbfs.size(); ++index)
            bands[std::array<const char*, 5> {{ "low", "low_mid", "mid", "upper_mid", "high" }}[index]] = result.band_energy_dbfs[index];
        output["band_energy_dbfs"] = bands;
    }
    if (!result.ltas_band_levels.empty())
        output["ltas_band_levels"] = make_owned_double_vector_output(std::move(result.ltas_band_levels));
    output["window_starts"] = starts;
    if (!result.averaged_peaks.empty()) {
        output["dominant_peaks"] = spectral_peak_list(result.averaged_peaks);
        nb::list window_peaks;
        for (const auto& peaks : result.window_peaks)
            window_peaks.append(spectral_peak_list(peaks));
        output["window_dominant_peaks"] = window_peaks;
    }
    output["fft_size"] = result.fft_size;
    output["window_sum"] = result.window_sum;
    output["copied"] = false;
    output["backend"] = result.backend;
    return output;
}

nb::dict masking_band_energy(
    FloatInput samples,
    std::size_t sample_rate,
    std::size_t fft_size,
    std::size_t hop)
{
    if (samples.ndim() != 1 || samples.shape(0) == 0)
        throw nb::value_error("samples must be a non-empty one-dimensional float32 NumPy array");
    if (sample_rate == 0 || fft_size == 0 || hop == 0)
        throw nb::value_error("sample_rate, fft_size, and hop must be positive");

    BandEnergyResult result;
    {
        nb::gil_scoped_release release;
        result = compute_band_energy(samples.data(), samples.shape(0), sample_rate, fft_size, hop);
    }

    auto energy = make_owned_output(std::move(result.values), result.frames, result.bands);
    nb::dict output;
    output["energy"] = energy;
    output["fft_size"] = fft_size;
    output["hop"] = hop;
    output["sample_rate"] = sample_rate;
    output["backend"] = result.backend;
    return output;
}

} // namespace

NB_MODULE(_kenn_dsp_native, module)
{
    module.doc() = "KENN native offline DSP kernels";
    module.def("decode_pcm", &decode_pcm_wav,
               nb::arg("payload"),
               "Decode a bounded PCM WAV payload into contiguous float32 channel arrays.");
    module.def("spectral_power", &spectral_power,
               nb::arg("samples"), nb::arg("fft_size") = 16384,
               nb::arg("sample_rate") = 0, nb::arg("include_ltas") = false,
               "Compute Hann-windowed one-sided power spectra for a contiguous float32 array.");
    module.def("masking_band_energy", &masking_band_energy,
               nb::arg("samples"), nb::arg("sample_rate"),
               nb::arg("fft_size") = 4096, nb::arg("hop") = 2048,
               "Compute per-frame masking-band RMS magnitudes for a contiguous float32 array.");
    module.def("mono_metrics", &mono_metrics,
               nb::arg("samples"),
               "Compute bulk mono channel statistics for an opt-in native analysis path.");
    module.def("stereo_metrics", &stereo_metrics,
               nb::arg("left"), nb::arg("right"),
               "Compute bulk stereo channel statistics and correlation.");
    init_automix_bindings(module);
    init_loudness_bindings(module);
}
