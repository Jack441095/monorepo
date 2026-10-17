#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <numbers>
#include <numeric>
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
#include "key_tempo_bindings.hpp"
#include "loudness_bindings.hpp"
#include "track_diagnostic_bindings.hpp"

namespace nb = nanobind;
using FloatInput = nb::ndarray<nb::numpy, const float, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using FloatMatrixInput = nb::ndarray<nb::numpy, const float, nb::ndim<2>, nb::c_contig, nb::device::cpu>;
using DoubleInput = nb::ndarray<nb::numpy, const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
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
    std::size_t total_frame_count = 0;
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
// 1024 frames (~21.3 ms at 48 kHz, ~23.2 ms at 44.1 kHz) spans at least a full
// cycle down to 47 Hz and half a cycle down to 23.4 Hz, preventing individual
// zero-crossing samples in a continuous tone from being counted as silence.
constexpr std::size_t kSilenceBlockSamples = 1024;

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

std::uint16_t read_be_u16(const std::uint8_t* data)
{
    return static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(data[0]) << 8) |
        static_cast<std::uint16_t>(data[1]));
}

std::uint32_t read_be_u32(const std::uint8_t* data)
{
    return (static_cast<std::uint32_t>(data[0]) << 24) |
        (static_cast<std::uint32_t>(data[1]) << 16) |
        (static_cast<std::uint32_t>(data[2]) << 8) |
        static_cast<std::uint32_t>(data[3]);
}

std::int32_t read_be_i24(const std::uint8_t* data)
{
    std::int32_t value = (static_cast<std::int32_t>(data[0]) << 16) |
        (static_cast<std::int32_t>(data[1]) << 8) |
        static_cast<std::int32_t>(data[2]);
    if ((value & 0x00800000) != 0)
        value |= static_cast<std::int32_t>(0xff000000);
    return value;
}

double read_be_f80(const std::uint8_t* data)
{
    const std::uint16_t sign_exp = read_be_u16(data);
    const std::uint64_t mantissa =
        (static_cast<std::uint64_t>(read_be_u32(data + 2)) << 32) |
        static_cast<std::uint64_t>(read_be_u32(data + 6));
    const int sign = (sign_exp >> 15) & 1;
    const int exp = sign_exp & 0x7FFF;
    if (exp == 0 && mantissa == 0)
        return 0.0;
    if (exp == 0x7FFF)
        return std::numeric_limits<double>::quiet_NaN();
    // 80-bit IEEE 754 extended has an explicit integer bit at bit 63 of the
    // mantissa and an exponent bias of 16383: value = mantissa * 2^(exp - 16383 - 63).
    const double magnitude = std::ldexp(static_cast<double>(mantissa), exp - 16383 - 63);
    return sign ? -magnitude : magnitude;
}

DecodedWav decode_pcm(
    const std::uint8_t* payload,
    std::size_t length,
    bool allow_8bit = false,
    std::size_t max_channels = 2,
    bool allow_aiff = false,
    std::size_t max_frames = 0)
{
    // Cap channel count at 64 even when callers request multichannel support so
    // a corrupt header cannot allocate tens of thousands of channel arrays.
    const std::size_t channel_limit = std::clamp<std::size_t>(max_channels, 1, 64);

    if (length < 12)
        throw nb::value_error("invalid audio container: payload shorter than 12-byte header");

    const std::string magic(reinterpret_cast<const char*>(payload), 4);
    const std::string form_type(reinterpret_cast<const char*>(payload + 8), 4);
    const bool is_wav = (magic == "RIFF" && form_type == "WAVE");
    const bool is_aiff = allow_aiff && (magic == "FORM" && (form_type == "AIFF" || form_type == "AIFC"));
    if (!is_wav && !is_aiff)
        throw nb::value_error("invalid WAV: file does not start with RIFF/WAVE id");

    bool have_format = false;
    std::size_t channels = 0;
    std::size_t sample_width = 0;
    std::size_t sample_rate = 0;
    std::uint16_t audio_format = 0;
    bool little_endian = is_wav;
    bool unsigned_8bit = is_wav;
    const std::uint8_t* raw = nullptr;
    std::size_t raw_length = 0;
    std::size_t position = 12;

    if (is_wav) {
        while (position + 8 <= length) {
            const auto* chunk = payload + position;
            const auto chunk_size = static_cast<std::size_t>(read_u32(chunk + 4));
            const auto data_start = position + 8;
            const auto available = std::min(chunk_size, length - data_start);
            const auto* chunk_data = payload + data_start;
            const std::string chunk_id(reinterpret_cast<const char*>(chunk), 4);
            if (chunk_id == "fmt " && available >= 16) {
                audio_format = read_u16(chunk_data);
                channels = read_u16(chunk_data + 2);
                sample_rate = read_u32(chunk_data + 4);
                const std::uint16_t bits_per_sample = read_u16(chunk_data + 14);
                sample_width = (bits_per_sample % 8 == 0) ? (bits_per_sample / 8) : 0;
                if (audio_format == 0xfffe && available >= 26)
                    audio_format = read_u16(chunk_data + 24);
                have_format = true;
            } else if (chunk_id == "data") {
                raw = chunk_data;
                raw_length = available;
            }
            const auto advance = 8 + chunk_size + (chunk_size & 1U);
            if (advance > length - position)
                break;
            position += advance;
        }
    } else {
        const bool is_aifc = (form_type == "AIFC");
        while (position + 8 <= length) {
            const auto* chunk = payload + position;
            const auto chunk_size = static_cast<std::size_t>(read_be_u32(chunk + 4));
            const auto data_start = position + 8;
            const auto available = std::min(chunk_size, length - data_start);
            const auto* chunk_data = payload + data_start;
            const std::string chunk_id(reinterpret_cast<const char*>(chunk), 4);
            if (chunk_id == "COMM" && available >= 18) {
                channels = read_be_u16(chunk_data);
                const std::uint16_t bits_per_sample = read_be_u16(chunk_data + 6);
                sample_width = (bits_per_sample % 8 == 0) ? (bits_per_sample / 8) : 0;
                const double rate_f = read_be_f80(chunk_data + 8);
                if (std::isfinite(rate_f) && rate_f > 0.0 && rate_f <= 1e9)
                    sample_rate = static_cast<std::size_t>(std::llround(rate_f));
                audio_format = 1;
                little_endian = false;
                if (is_aifc) {
                    if (available < 22) {
                        audio_format = 0;
                    } else {
                        const std::string comp(reinterpret_cast<const char*>(chunk_data + 18), 4);
                        if (comp == "NONE" || comp == "twos") {
                            audio_format = 1;
                            little_endian = false;
                        } else if (comp == "sowt") {
                            audio_format = 1;
                            little_endian = true;
                        } else if (comp == "fl32" || comp == "FL32") {
                            audio_format = 3;
                            little_endian = false;
                        } else {
                            audio_format = 0;
                        }
                    }
                }
                have_format = true;
            } else if (chunk_id == "SSND" && available >= 8) {
                const auto ssnd_offset = static_cast<std::size_t>(read_be_u32(chunk_data));
                if (8 + ssnd_offset <= available) {
                    raw = chunk_data + 8 + ssnd_offset;
                    raw_length = available - (8 + ssnd_offset);
                }
            }
            const auto advance = 8 + chunk_size + (chunk_size & 1U);
            if (advance > length - position)
                break;
            position += advance;
        }
    }

    if (!have_format)
        throw nb::value_error("invalid WAV: fmt chunk missing in WAV file");
    if (raw == nullptr)
        throw nb::value_error("invalid WAV: data chunk missing in WAV file");
    if (channels < 1 || channels > channel_limit)
        throw nb::value_error("only mono and stereo WAV files are supported");
    const bool valid_width = (sample_width == 2 || sample_width == 3 || sample_width == 4)
        || (allow_8bit && sample_width == 1 && audio_format == 1);
    if (!valid_width)
        throw nb::value_error("only 16-bit, 24-bit, and 32-bit WAV files are supported");
    if (audio_format != 1 && (audio_format != 3 || sample_width != 4))
        throw nb::value_error("unsupported WAV audio format tag");
    if (sample_rate == 0 || raw_length == 0)
        throw nb::value_error("WAV contains no audio frames");

    const auto bytes_per_frame = channels * sample_width;
    const auto total_frame_count = raw_length / bytes_per_frame;
    if (total_frame_count == 0)
        throw nb::value_error("WAV contains no audio frames");
    const auto frame_count = (max_frames > 0)
        ? std::min(total_frame_count, max_frames)
        : total_frame_count;

    DecodedWav result;
    result.sample_rate = sample_rate;
    result.bit_depth = sample_width * 8;
    result.frame_count = frame_count;
    result.total_frame_count = total_frame_count;
    result.channels.resize(channels);
    for (auto& channel : result.channels)
        channel = std::make_unique<float[]>(frame_count);
    for (std::size_t frame = 0; frame < frame_count; ++frame) {
        for (std::size_t channel = 0; channel < channels; ++channel) {
            const auto* sample = raw + frame * bytes_per_frame + channel * sample_width;
            float value = 0.0f;
            if (sample_width == 1) {
                if (unsigned_8bit) {
                    value = static_cast<float>(static_cast<int>(sample[0]) - 128) / 128.0f;
                } else {
                    value = static_cast<float>(static_cast<std::int8_t>(sample[0])) / 128.0f;
                }
            } else if (sample_width == 2) {
                const auto integer = static_cast<std::int16_t>(
                    little_endian ? read_u16(sample) : read_be_u16(sample));
                value = static_cast<float>(integer) / 32768.0f;
            } else if (sample_width == 3) {
                const auto integer = little_endian ? read_i24(sample) : read_be_i24(sample);
                value = static_cast<float>(integer) / 8388608.0f;
            } else if (audio_format == 3) {
                std::uint32_t bits = little_endian ? read_u32(sample) : read_be_u32(sample);
                float decoded;
                std::memcpy(&decoded, &bits, sizeof(decoded));
                if (!std::isfinite(decoded))
                    throw nb::value_error("invalid WAV: IEEE float data contains NaN or infinite samples");
                value = decoded;
            } else {
                const auto integer = static_cast<std::int32_t>(
                    little_endian ? read_u32(sample) : read_be_u32(sample));
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
    for (std::size_t block_start = 0; block_start < length; block_start += kSilenceBlockSamples)
    {
        const std::size_t block_end = std::min(length, block_start + kSilenceBlockSamples);
        double block_squares = 0.0;
        for (std::size_t index = block_start; index < block_end; ++index)
        {
            const double value = static_cast<double>(samples[index]);
            if (!std::isfinite(value))
                throw std::invalid_argument("audio samples must be finite");
            const double magnitude = std::abs(value);
            sum += value;
            const double sq = value * value;
            sum_squares += sq;
            block_squares += sq;
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
        }
        const std::size_t block_len = block_end - block_start;
        if (std::sqrt(block_squares / static_cast<double>(block_len)) < kSilenceThreshold)
            result.silence_count += block_len;
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
    // A flat channel (digital silence, or pure DC) has no correlation at all.
    // NaN carries that out so stereo_metrics can report None, as the Python
    // reference does; returning 0.0 here read as "fully decorrelated" and
    // disagreed with the reference on a file with one silent side.
    if (denominator == 0.0)
        return std::numeric_limits<double>::quiet_NaN();
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
        // Evaluate the vertex of the log-power parabola so off-bin tones do not
        // Divide out the Hann mainlobe attenuation W(d) = sin(pi*d)/(pi*d*(1-d^2))
        // at the fractional bin offset d so off-bin tones do not lose up to
        // 1.42 dB (0.62 dB at 1/3-bin offset) to Hann scalloping.
        const double pi_d = std::numbers::pi * offset;
        const double hann_gain = std::abs(offset) < 1e-9
            ? 1.0
            : std::sin(pi_d) / (pi_d * (1.0 - offset * offset));
        const double peak_power = std::max(powers[index] / (hann_gain * hann_gain), 1e-30);
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
    for (std::size_t i = 0; i < length; ++i) {
        if (!std::isfinite(samples[i]))
            throw std::invalid_argument("audio samples must be finite");
    }
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
    for (std::size_t i = 0; i < length; ++i) {
        if (!std::isfinite(samples[i]))
            throw std::invalid_argument("audio samples must be finite");
    }

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
    std::size_t frame_silence_count = 0;
    {
        nb::gil_scoped_release release;
        const std::size_t length = left.shape(0);
        left_summary = summarize_channel(left.data(), length);
        right_summary = summarize_channel(right.data(), length);
        channel_correlation = correlation_with_offsets(
            left.data(), right.data(), length, left_summary.dc_offset, right_summary.dc_offset);
        constexpr double kSilencePowerThreshold = kSilenceThreshold * kSilenceThreshold;
        double mono_block_sum_squares = 0.0;
        double left_block_sum_squares = 0.0;
        double right_block_sum_squares = 0.0;
        std::size_t block_len = 0;
        for (std::size_t index = 0; index < length; ++index)
        {
            const double l = static_cast<double>(left(index));
            const double r = static_cast<double>(right(index));
            const double mid = (l + r) * 0.5;
            const double side = (l - r) * 0.5;
            mono_sum_squares += mid * mid;
            side_sum_squares += side * side;
            mono_block_sum_squares += mid * mid;
            left_block_sum_squares += l * l;
            right_block_sum_squares += r * r;
            ++block_len;
            if (block_len == kSilenceBlockSamples || index + 1 == length)
            {
                const double block_threshold = static_cast<double>(block_len) * kSilencePowerThreshold;
                if (mono_block_sum_squares < block_threshold)
                    mono_silence_count += block_len;
                // A frame block is silent only when both channels fall below
                // -60 dBFS RMS. The mono-sum count alone reads a polarity-flipped
                // file (L = -R) as silent.
                if (left_block_sum_squares < block_threshold && right_block_sum_squares < block_threshold)
                    frame_silence_count += block_len;
                mono_block_sum_squares = 0.0;
                left_block_sum_squares = 0.0;
                right_block_sum_squares = 0.0;
                block_len = 0;
            }
        }
    }

    nb::dict output;
    output["left"] = channel_summary_dict(left_summary, left.shape(0));
    output["right"] = channel_summary_dict(right_summary, right.shape(0));
    if (std::isnan(channel_correlation))
        output["correlation"] = nb::none();
    else
        output["correlation"] = channel_correlation;
    output["mono_rms"] = std::sqrt(mono_sum_squares / static_cast<double>(left.shape(0)));
    output["side_rms"] = std::sqrt(side_sum_squares / static_cast<double>(left.shape(0)));
    output["mono_silence_percentage"] = 100.0 * static_cast<double>(mono_silence_count) / static_cast<double>(left.shape(0));
    output["silence_percentage"] = 100.0 * static_cast<double>(frame_silence_count) / static_cast<double>(left.shape(0));
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

nb::dict decode_pcm_wav(
    ByteInput payload,
    bool allow_8bit,
    std::size_t max_channels,
    bool allow_aiff,
    std::size_t max_frames)
{
    if (payload.ndim() != 1 || payload.shape(0) == 0)
        throw nb::value_error("payload must be a non-empty one-dimensional uint8 NumPy array");

    DecodedWav decoded;
    {
        nb::gil_scoped_release release;
        decoded = decode_pcm(
            payload.data(),
            payload.shape(0),
            allow_8bit,
            max_channels,
            allow_aiff,
            max_frames);
    }
    nb::list channel_outputs;
    for (auto& channel : decoded.channels)
        channel_outputs.append(make_owned_float_output(std::move(channel), decoded.frame_count));
    nb::dict output;
    output["channels"] = channel_outputs;
    output["sample_rate"] = decoded.sample_rate;
    output["channel_count"] = decoded.channels.size();
    output["bit_depth"] = decoded.bit_depth;
    output["total_frames"] = decoded.total_frame_count;
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

std::vector<double> compute_erb_spectrum_kernel(
    const double* magnitudes,
    std::size_t bin_count,
    std::int64_t sample_rate,
    std::int64_t fft_size,
    std::int64_t num_bands)
{
    const auto band_count = static_cast<std::size_t>(num_bands);
    std::vector<double> energies(band_count, 0.0);
    for (std::size_t i = 0; i < bin_count; ++i) {
        if (!std::isfinite(magnitudes[i])) {
            throw std::invalid_argument("magnitudes must contain only finite values");
        }
    }
    if (bin_count == 0 || sample_rate <= 0 || fft_size <= 0) {
        // An empty spectrum or non-positive rate/FFT size maps no bins into 20 Hz..20 kHz,
        // so returning all-zero band energies matches the psychoacoustic contract.
        return energies;
    }

    // Glasberg & Moore (1990) ERB-rate scale: E(f) = 21.4 * log10(0.00437 * f + 1.0),
    // partitioned into num_bands equal-ERB steps across the 20 Hz..20 kHz audible range.
    constexpr double kMinFreqHz = 20.0;
    constexpr double kMaxFreqHz = 20000.0;
    constexpr double kErbScale = 21.4;
    constexpr double kErbSlopePerHz = 0.00437;
    const double e_min = kErbScale * std::log10(kErbSlopePerHz * kMinFreqHz + 1.0);
    const double e_max = kErbScale * std::log10(kErbSlopePerHz * kMaxFreqHz + 1.0);
    const double e_span = e_max - e_min;
    const double bin_freq_step_hz = static_cast<double>(sample_rate) / static_cast<double>(fft_size);

    for (std::size_t i = 0; i < bin_count; ++i) {
        const double freq_hz = static_cast<double>(i) * bin_freq_step_hz;
        if (freq_hz < kMinFreqHz || freq_hz > kMaxFreqHz) {
            // Bins outside 20 Hz..20 kHz sit outside the auditory band grid.
            continue;
        }
        const double erb = kErbScale * std::log10(kErbSlopePerHz * freq_hz + 1.0);
        const auto band_idx = static_cast<std::int64_t>(
            (erb - e_min) / e_span * static_cast<double>(num_bands));
        if (band_idx >= 0 && band_idx < num_bands) {
            const double mag = magnitudes[i];
            energies[static_cast<std::size_t>(band_idx)] += mag * mag;
        }
    }
    return energies;
}

DoubleVectorOutput erb_spectrum(
    DoubleInput magnitudes,
    std::int64_t sample_rate,
    std::int64_t fft_size,
    std::int64_t num_bands)
{
    if (magnitudes.ndim() != 1)
        throw nb::value_error("magnitudes must be a one-dimensional float64 NumPy array");
    // Cap at 4096 bands so a corrupted band-count argument cannot allocate unbounded memory.
    if (num_bands <= 0 || num_bands > 4096)
        throw nb::value_error("num_bands must be in 1..4096");

    std::vector<double> energies;
    {
        nb::gil_scoped_release release;
        energies = compute_erb_spectrum_kernel(
            magnitudes.data(), magnitudes.shape(0), sample_rate, fft_size, num_bands);
    }
    return make_owned_double_vector_output(std::move(energies));
}

double bessel_i0_resample(double x)
{
    // Power series for the zero-order modified Bessel function I0(x); at the
    // Kaiser beta of 5.0 it converges to double precision in ~20 terms, so 60
    // is a hard loop cap rather than the typical iteration count.
    double sum = 1.0;
    double term = 1.0;
    for (int k = 1; k < 60; ++k) {
        term *= (x / (2.0 * static_cast<double>(k))) * (x / (2.0 * static_cast<double>(k)));
        sum += term;
        if (term < sum * 1e-17)
            break;
    }
    return sum;
}

std::vector<float> resample_mono_window_kernel(
    const float* samples,
    std::size_t frame_count,
    std::size_t channel_count,
    std::int64_t sample_rate,
    std::int64_t target_sample_rate,
    std::int64_t target_samples)
{
    if (frame_count == 0 || channel_count == 0)
        throw std::invalid_argument("samples must be non-empty");
    // Refuse implausible rates outside 8..768 kHz so a malformed WAV header
    // cannot trigger multi-gigabyte allocations or degenerate filter ratios.
    if (sample_rate < 8000 || sample_rate > 768000)
        throw std::invalid_argument("sample_rate must be in 8000..768000 Hz");
    if (target_sample_rate < 8000 || target_sample_rate > 768000)
        throw std::invalid_argument("target_sample_rate must be in 8000..768000 Hz");
    // Cap at 16,000,000 output samples (~500 s at 32 kHz, 64 MiB float32).
    if (target_samples <= 0 || target_samples > 16000000)
        throw std::invalid_argument("target_samples must be in 1..16000000");

    // Crop input to the target window duration before resampling, matching
    // librosa.load(..., sr=target_sample_rate, mono=True, duration=target_samples/target_sample_rate).
    const auto max_in_frames = static_cast<std::size_t>(std::max<std::int64_t>(
        1,
        std::llround(static_cast<double>(target_samples) * static_cast<double>(sample_rate)
                     / static_cast<double>(target_sample_rate))));
    const std::size_t in_frames = std::min(frame_count, max_in_frames);

    std::vector<double> mono(in_frames, 0.0);
    const double inv_channels = 1.0 / static_cast<double>(channel_count);
    for (std::size_t frame = 0; frame < in_frames; ++frame) {
        double sum = 0.0;
        const float* row = samples + frame * channel_count;
        for (std::size_t ch = 0; ch < channel_count; ++ch) {
            const float value = row[ch];
            if (!std::isfinite(value))
                throw std::invalid_argument("audio samples must be finite");
            sum += static_cast<double>(value);
        }
        mono[frame] = sum * inv_channels;
    }

    const auto out_capacity = static_cast<std::size_t>(target_samples);
    std::vector<float> output(out_capacity, 0.0f);
    if (sample_rate == target_sample_rate) {
        // Already at target rate; copy mono samples directly and leave any tail zero-padded.
        const std::size_t copy_count = std::min(in_frames, out_capacity);
        for (std::size_t i = 0; i < copy_count; ++i)
            output[i] = static_cast<float>(mono[i]);
        return output;
    }

    const std::int64_t g = std::gcd(target_sample_rate, sample_rate);
    const auto up = static_cast<std::size_t>(target_sample_rate / g);
    const auto down = static_cast<std::size_t>(sample_rate / g);
    const std::size_t max_rate = std::max(up, down);
    const std::size_t out_frames = std::min(
        out_capacity,
        static_cast<std::size_t>((static_cast<std::uint64_t>(in_frames) * up + down - 1) / down));

    // Standard audio rates (8, 11.025, 16, 22.05, 24, 32, 44.1, 48, 88.2, 96,
    // 176.4, 192, 352.8, 384, 768 kHz -> 32 kHz) all have max(up, down) <= 1411.
    // Use the exact scipy.signal.resample_poly Kaiser (beta = 5.0, half_len = 10 * max_rate)
    // polyphase FIR when max_rate <= 2048, and fall back to direct continuous-time
    // Kaiser-sinc evaluation for arbitrary coprime rates so filter memory stays bounded.
    constexpr double kKaiserBeta = 5.0;
    const double denom_i0 = bessel_i0_resample(kKaiserBeta);
    if (max_rate <= 2048) {
        const std::size_t half_len = 10 * max_rate;
        const std::size_t taps = 2 * half_len + 1;
        const double cutoff = 1.0 / static_cast<double>(max_rate);
        std::vector<double> h(taps, 0.0);
        double h_sum = 0.0;
        for (std::size_t idx = 0; idx < taps; ++idx) {
            const double m = static_cast<double>(idx) - static_cast<double>(half_len);
            const double x = cutoff * m;
            const double sinc = (x == 0.0)
                ? 1.0
                : std::sin(std::numbers::pi * x) / (std::numbers::pi * x);
            const double ratio = 2.0 * static_cast<double>(idx) / static_cast<double>(taps - 1) - 1.0;
            const double win = bessel_i0_resample(
                kKaiserBeta * std::sqrt(std::max(0.0, 1.0 - ratio * ratio))) / denom_i0;
            h[idx] = cutoff * sinc * win;
            h_sum += h[idx];
        }
        const double gain = static_cast<double>(up) / h_sum;
        for (double& coeff : h)
            coeff *= gain;

        const std::size_t taps_per_phase = (taps + up - 1) / up;
        std::vector<double> poly(up * taps_per_phase, 0.0);
        for (std::size_t phase = 0; phase < up; ++phase) {
            double* row = poly.data() + phase * taps_per_phase;
            for (std::size_t k = 0; phase + k * up < taps; ++k)
                row[k] = h[phase + k * up];
        }

        for (std::size_t y_idx = 0; y_idx < out_frames; ++y_idx) {
            const std::uint64_t u = static_cast<std::uint64_t>(y_idx) * down + half_len;
            const auto phase = static_cast<std::size_t>(u % up);
            const auto base_n = static_cast<std::size_t>(u / up);
            const std::size_t k_min = (base_n >= in_frames) ? (base_n - (in_frames - 1)) : 0;
            const std::size_t max_k_for_phase = (taps - 1 - phase) / up;
            const std::size_t k_max = std::min(base_n, max_k_for_phase);
            const double* phase_row = poly.data() + phase * taps_per_phase;
            double acc = 0.0;
            for (std::size_t k = k_min; k <= k_max; ++k)
                acc += phase_row[k] * mono[base_n - k];
            output[y_idx] = static_cast<float>(acc);
        }
        return output;
    }

    const double step = static_cast<double>(sample_rate) / static_cast<double>(target_sample_rate);
    const double cutoff = std::min(1.0, 1.0 / step);
    const double half_width = 10.0 / cutoff;
    for (std::size_t y_idx = 0; y_idx < out_frames; ++y_idx) {
        const double center = static_cast<double>(y_idx) * step;
        const auto n_min = std::max<std::int64_t>(
            0, static_cast<std::int64_t>(std::ceil(center - half_width)));
        const auto n_max = std::min<std::int64_t>(
            static_cast<std::int64_t>(in_frames) - 1,
            static_cast<std::int64_t>(std::floor(center + half_width)));
        double acc = 0.0;
        for (std::int64_t n = n_min; n <= n_max; ++n) {
            const double delta = center - static_cast<double>(n);
            const double x = cutoff * delta;
            const double sinc = (x == 0.0)
                ? 1.0
                : std::sin(std::numbers::pi * x) / (std::numbers::pi * x);
            const double ratio = delta / half_width;
            const double win = bessel_i0_resample(
                kKaiserBeta * std::sqrt(std::max(0.0, 1.0 - ratio * ratio))) / denom_i0;
            acc += cutoff * sinc * win * mono[static_cast<std::size_t>(n)];
        }
        output[y_idx] = static_cast<float>(acc);
    }
    return output;
}

FloatVectorOutput resample_mono_window(
    FloatMatrixInput samples,
    std::int64_t sample_rate,
    std::int64_t target_sample_rate,
    std::int64_t target_samples)
{
    if (samples.ndim() != 2 || samples.shape(0) == 0 || samples.shape(1) == 0)
        throw nb::value_error("samples must be a non-empty 2D (frames, channels) float32 NumPy array");

    std::vector<float> resampled;
    {
        nb::gil_scoped_release release;
        resampled = resample_mono_window_kernel(
            samples.data(),
            samples.shape(0),
            samples.shape(1),
            sample_rate,
            target_sample_rate,
            target_samples);
    }
    return make_owned_float_vector_output(std::move(resampled));
}

} // namespace

NB_MODULE(_kenn_dsp_native, module)
{
    module.doc() = "KENN native offline DSP kernels";
    module.def("decode_pcm", &decode_pcm_wav,
               nb::arg("payload"),
               nb::arg("allow_8bit") = false,
               nb::arg("max_channels") = 2,
               nb::arg("allow_aiff") = false,
               nb::arg("max_frames") = 0,
               "Decode a bounded PCM/float WAV or AIFF/AIFC payload into contiguous float32 channel arrays.");
    module.def("spectral_power", &spectral_power,
               nb::arg("samples"), nb::arg("fft_size") = 16384,
               nb::arg("sample_rate") = 0, nb::arg("include_ltas") = false,
               "Compute Hann-windowed one-sided power spectra for a contiguous float32 array.");
    module.def("masking_band_energy", &masking_band_energy,
               nb::arg("samples"), nb::arg("sample_rate"),
               nb::arg("fft_size") = 4096, nb::arg("hop") = 2048,
               "Compute per-frame masking-band RMS magnitudes for a contiguous float32 array.");
    module.def("erb_spectrum", &erb_spectrum,
               nb::arg("magnitudes"), nb::arg("sample_rate") = 44100,
               nb::arg("fft_size") = 4096, nb::arg("num_bands") = 40,
               "Group one-sided FFT magnitudes into discrete Glasberg & Moore ERB band energies.");
    module.def("resample_mono_window", &resample_mono_window,
               nb::arg("samples"), nb::arg("sample_rate"),
               nb::arg("target_sample_rate") = 32000, nb::arg("target_samples") = 160000,
               "Fold multichannel audio to mono, resample via a Kaiser-windowed polyphase FIR, and pad/truncate to target_samples.");
    module.def("mono_metrics", &mono_metrics,
               nb::arg("samples"),
               "Compute bulk mono channel statistics for an opt-in native analysis path.");
    module.def("stereo_metrics", &stereo_metrics,
               nb::arg("left"), nb::arg("right"),
               "Compute bulk stereo channel statistics and correlation.");
    init_automix_bindings(module);
    init_loudness_bindings(module);
    init_key_tempo_bindings(module);
    init_track_diagnostic_bindings(module);
}
