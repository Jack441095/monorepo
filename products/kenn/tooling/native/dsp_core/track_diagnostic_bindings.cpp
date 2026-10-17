#include "track_diagnostic_bindings.hpp"

#include "fft_core.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <optional>
#include <stdexcept>
#include <utility>
#include <vector>

#include <nanobind/ndarray.h>
#include <nanobind/nanobind.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/vector.h>

namespace nb = nanobind;

using FloatMatrixInput = nb::ndarray<nb::numpy, const float, nb::ndim<2>, nb::c_contig, nb::device::cpu>;

namespace {

// Replaces the pure-Python loops, librosa (centroid, flatness) and scipy (Welch
// resonance peaks) in core/track_diagnostic.py, 17 Oct 2026. The waveform,
// spectrogram and resonance peaks follow the old code's arithmetic so the
// route's numbers do not move; centroid and flatness deliberately differ by
// leaving silent frames out (see spectral_shape). Rounding and dB conversion
// stay in Python so they keep their exact old behaviour.

// librosa's defaults for spectral_centroid/flatness: 2048-point frames (46 ms
// at 44.1 kHz) every 512 samples, Hann window, zero-padded centred frames.
constexpr std::size_t kShapeFftSize = 2048;
constexpr std::size_t kShapeHop = 512;
// librosa's flatness floor on power, so an all-zero bin cannot take log(0).
constexpr double kFlatnessPowerFloor = 1e-10;
// Frames more than 60 dB (1e-6 in power) under the loudest frame are silence.
// Bug found 17 Oct 2026: librosa scores a silent frame as perfectly flat
// (about 0.99), so a guitar stem that was 38% silence read flatness 0.376
// where its playing frames average 0.0002, and its centroid read 998 Hz
// instead of 1524 Hz. Same floor as the key/tempo chroma.
constexpr double kSilentFramePowerRatio = 1e-6;

// The old Goertzel spectrogram used at most 2048 points (46 ms at 44.1 kHz)
// from the start of each time slice and skipped slices shorter than 64.
constexpr std::size_t kSpectrogramMaxPoints = 2048;
constexpr std::size_t kSpectrogramMinSlice = 64;
constexpr std::size_t kSpectrogramMinSliceLength = 512;

struct Signal {
    std::vector<double> samples;
    double peak = 0.0;
    double rms = 0.0;
};

// Peak over every channel, RMS as the mean of per-channel RMS (as analyze_wav
// does), and the one signal the displays read: the mono mean, or the side
// signal when a stereo pair cancels in the sum.
Signal analysis_signal(const float* data, std::size_t frames, std::size_t channels)
{
    Signal signal;
    double rms_total = 0.0;
    for (std::size_t channel = 0; channel < channels; ++channel)
    {
        double squares = 0.0;
        for (std::size_t frame = 0; frame < frames; ++frame)
        {
            const double value = data[frame * channels + channel];
            squares += value * value;
            signal.peak = std::max(signal.peak, std::abs(value));
        }
        rms_total += std::sqrt(squares / static_cast<double>(frames));
    }
    signal.rms = rms_total / static_cast<double>(channels);

    signal.samples.resize(frames);
    double mono_peak = 0.0;
    for (std::size_t frame = 0; frame < frames; ++frame)
    {
        double sum = 0.0;
        for (std::size_t channel = 0; channel < channels; ++channel)
            sum += data[frame * channels + channel];
        signal.samples[frame] = sum / static_cast<double>(channels);
        mono_peak = std::max(mono_peak, std::abs(signal.samples[frame]));
    }
    // 0.001 is -60 dB under the louder channel: the sum is gone but the
    // channels are not (L = -R), so show the side signal instead of a blank.
    if (channels == 2 && signal.peak > 0.0 && mono_peak < signal.peak * 0.001)
    {
        for (std::size_t frame = 0; frame < frames; ++frame)
            signal.samples[frame] = (static_cast<double>(data[frame * 2]) - data[frame * 2 + 1]) * 0.5;
    }
    return signal;
}

std::pair<std::vector<double>, std::vector<double>> waveform_envelope(const std::vector<double>& samples, std::size_t points)
{
    std::vector<double> peaks(points, 0.0);
    std::vector<double> rms(points, 0.0);
    const std::size_t chunk = std::max<std::size_t>(1, samples.size() / points);
    for (std::size_t point = 0; point < points; ++point)
    {
        const std::size_t start = point * chunk;
        if (start >= samples.size())
            continue; // past the end of a short file: the old code drew zeros here too
        const std::size_t end = std::min(samples.size(), start + chunk);
        double peak = 0.0;
        double squares = 0.0;
        for (std::size_t index = start; index < end; ++index)
        {
            peak = std::max(peak, std::abs(samples[index]));
            squares += samples[index] * samples[index];
        }
        peaks[point] = peak;
        rms[point] = std::sqrt(squares / static_cast<double>(end - start));
    }
    return { peaks, rms };
}

// Linear magnitudes, one row per time slice; a NaN marks a cell the caller
// reports at the -80 dB floor (slice too short, or band above Nyquist).
std::vector<std::vector<double>> goertzel_spectrogram(const std::vector<double>& samples, double rate,
                                                      const std::vector<double>& bands, std::size_t slices)
{
    const double nan = std::numeric_limits<double>::quiet_NaN();
    std::vector<std::vector<double>> matrix(slices, std::vector<double>(bands.size(), nan));
    const std::size_t slice_length = std::max(kSpectrogramMinSliceLength, samples.size() / slices);
    const double nyquist = rate / 2.0;
    std::vector<double> windowed;
    for (std::size_t slice = 0; slice < slices; ++slice)
    {
        const std::size_t start = slice * slice_length;
        if (start >= samples.size() || samples.size() - start < kSpectrogramMinSlice)
            continue;
        const std::size_t points = std::min({ kSpectrogramMaxPoints, slice_length, samples.size() - start });
        windowed.resize(points);
        // Symmetric Hann over points - 1, as the old Python loop built it.
        for (std::size_t n = 0; n < points; ++n)
            windowed[n] = samples[start + n] * (0.5 * (1.0 - std::cos(2.0 * std::numbers::pi * static_cast<double>(n) / static_cast<double>(points - 1))));
        for (std::size_t band = 0; band < bands.size(); ++band)
        {
            if (bands[band] >= nyquist)
                continue;
            // nearbyint rounds half to even, matching Python's round().
            const double k = std::nearbyint(bands[band] * static_cast<double>(points) / rate);
            const double coeff = 2.0 * std::cos(2.0 * std::numbers::pi * k / static_cast<double>(points));
            double q1 = 0.0;
            double q2 = 0.0;
            for (const double sample : windowed)
            {
                const double q0 = coeff * q1 - q2 + sample;
                q2 = q1;
                q1 = q0;
            }
            const double power = q1 * q1 + q2 * q2 - q1 * q2 * coeff;
            matrix[slice][band] = std::sqrt(std::max(0.0, power)) / (static_cast<double>(points) / 2.0);
        }
    }
    return matrix;
}

struct SpectralShape {
    std::optional<double> centroid_hz;
    std::optional<double> flatness;
    std::size_t frames = 0;
    std::size_t silent_frames = 0;
};

SpectralShape spectral_shape(const std::vector<double>& samples, double rate)
{
    SpectralShape shape;
    const std::size_t frame_count = 1 + samples.size() / kShapeHop;
    const std::size_t bins = kShapeFftSize / 2 + 1;
    std::vector<double> window(kShapeFftSize);
    // Periodic Hann, as librosa's STFT uses.
    for (std::size_t n = 0; n < kShapeFftSize; ++n)
        window[n] = 0.5 * (1.0 - std::cos(2.0 * std::numbers::pi * static_cast<double>(n) / static_cast<double>(kShapeFftSize)));

    std::vector<double> frame_power(frame_count, 0.0);
    std::vector<double> centroids(frame_count, 0.0);
    std::vector<double> flatness(frame_count, 0.0);
    std::vector<kenn::dsp::Complex> buffer(kShapeFftSize);
    const auto half = static_cast<std::ptrdiff_t>(kShapeFftSize / 2);
    for (std::size_t frame = 0; frame < frame_count; ++frame)
    {
        // Centred frames with zero padding at both ends, like librosa's
        // center=True with pad_mode="constant".
        const auto origin = static_cast<std::ptrdiff_t>(frame * kShapeHop) - half;
        for (std::size_t n = 0; n < kShapeFftSize; ++n)
        {
            const auto index = origin + static_cast<std::ptrdiff_t>(n);
            const double value = index >= 0 && index < static_cast<std::ptrdiff_t>(samples.size()) ? samples[static_cast<std::size_t>(index)] : 0.0;
            buffer[n] = { value * window[n], 0.0 };
        }
        kenn::dsp::fft_in_place(buffer);
        double magnitude_sum = 0.0;
        double weighted = 0.0;
        double log_sum = 0.0;
        double power_sum = 0.0;
        double floored_sum = 0.0;
        for (std::size_t bin = 0; bin < bins; ++bin)
        {
            const double power = std::norm(buffer[bin]);
            const double magnitude = std::sqrt(power);
            magnitude_sum += magnitude;
            weighted += magnitude * static_cast<double>(bin) * rate / static_cast<double>(kShapeFftSize);
            const double floored = std::max(kFlatnessPowerFloor, power);
            log_sum += std::log(floored);
            floored_sum += floored;
            power_sum += power;
        }
        frame_power[frame] = power_sum;
        centroids[frame] = magnitude_sum > 0.0 ? weighted / magnitude_sum : 0.0;
        flatness[frame] = std::exp(log_sum / static_cast<double>(bins)) / (floored_sum / static_cast<double>(bins));
    }

    const double loudest = *std::max_element(frame_power.begin(), frame_power.end());
    shape.frames = frame_count;
    if (loudest <= 0.0)
    {
        // Digital silence has neither a centroid nor a flatness; None says so
        // where librosa would have said 0 Hz and perfectly flat.
        shape.silent_frames = frame_count;
        return shape;
    }
    double centroid_total = 0.0;
    double flatness_total = 0.0;
    std::size_t kept = 0;
    for (std::size_t frame = 0; frame < frame_count; ++frame)
    {
        if (frame_power[frame] < loudest * kSilentFramePowerRatio)
        {
            ++shape.silent_frames;
            continue;
        }
        centroid_total += centroids[frame];
        flatness_total += flatness[frame];
        ++kept;
    }
    shape.centroid_hz = centroid_total / static_cast<double>(kept);
    shape.flatness = flatness_total / static_cast<double>(kept);
    return shape;
}

// One-sided DFT power of a real segment whose length is not a power of two.
// Only files under 16384 samples (0.37 s at 44.1 kHz) get such a Welch
// segment, at most 4095 points over about seven segments, so a direct DFT
// with a twiddle table (well under 0.1 s) beats carrying a Bluestein FFT.
void direct_power(const std::vector<double>& segment, std::vector<double>& powers, const std::vector<double>& cosines,
                  const std::vector<double>& sines)
{
    const std::size_t n = segment.size();
    for (std::size_t bin = 0; bin < powers.size(); ++bin)
    {
        double real = 0.0;
        double imag = 0.0;
        std::size_t phase = 0;
        for (std::size_t index = 0; index < n; ++index)
        {
            real += segment[index] * cosines[phase];
            imag -= segment[index] * sines[phase];
            phase += bin;
            if (phase >= n)
                phase -= n;
        }
        powers[bin] = real * real + imag * imag;
    }
}

// scipy.signal.welch with its defaults (periodic Hann, half overlap, constant
// detrend, density scaling, one-sided) at the old segment length rule.
std::pair<std::vector<double>, std::vector<double>> welch_psd(const std::vector<double>& samples, double rate)
{
    // nperseg = min(4096, max(512, n // 4)), and scipy shrinks it to the
    // signal length when the file is shorter than that.
    std::size_t length = std::min<std::size_t>(4096, std::max<std::size_t>(512, samples.size() / 4));
    length = std::min(length, samples.size());
    const std::size_t overlap = length / 2;
    const std::size_t step = length - overlap;
    const std::size_t segments = (samples.size() - overlap) / step;
    const std::size_t bins = length / 2 + 1;

    std::vector<double> window(length);
    double window_power = 0.0;
    for (std::size_t n = 0; n < length; ++n)
    {
        window[n] = 0.5 * (1.0 - std::cos(2.0 * std::numbers::pi * static_cast<double>(n) / static_cast<double>(length)));
        window_power += window[n] * window[n];
    }
    const bool power_of_two = (length & (length - 1)) == 0;
    std::vector<double> cosines;
    std::vector<double> sines;
    if (!power_of_two)
    {
        cosines.resize(length);
        sines.resize(length);
        for (std::size_t n = 0; n < length; ++n)
        {
            cosines[n] = std::cos(2.0 * std::numbers::pi * static_cast<double>(n) / static_cast<double>(length));
            sines[n] = std::sin(2.0 * std::numbers::pi * static_cast<double>(n) / static_cast<double>(length));
        }
    }

    std::vector<double> psd(bins, 0.0);
    std::vector<double> segment(length);
    std::vector<double> powers(bins);
    std::vector<kenn::dsp::Complex> buffer(power_of_two ? length : 0);
    for (std::size_t index = 0; index < segments; ++index)
    {
        const std::size_t start = index * step;
        double mean = 0.0;
        for (std::size_t n = 0; n < length; ++n)
            mean += samples[start + n];
        mean /= static_cast<double>(length);
        for (std::size_t n = 0; n < length; ++n)
            segment[n] = (samples[start + n] - mean) * window[n];
        if (power_of_two)
        {
            for (std::size_t n = 0; n < length; ++n)
                buffer[n] = { segment[n], 0.0 };
            kenn::dsp::fft_in_place(buffer);
            for (std::size_t bin = 0; bin < bins; ++bin)
                powers[bin] = std::norm(buffer[bin]);
        }
        else
        {
            direct_power(segment, powers, cosines, sines);
        }
        for (std::size_t bin = 0; bin < bins; ++bin)
            psd[bin] += powers[bin];
    }

    std::vector<double> frequencies(bins);
    const double scale = 1.0 / (rate * window_power * static_cast<double>(segments));
    for (std::size_t bin = 0; bin < bins; ++bin)
    {
        psd[bin] *= scale;
        // One-sided density doubles every bin but DC, and Nyquist when the
        // segment length is even (it has no mirror image).
        if (bin != 0 && !(length % 2 == 0 && bin == bins - 1))
            psd[bin] *= 2.0;
        frequencies[bin] = static_cast<double>(bin) * rate / static_cast<double>(length);
    }
    return { frequencies, psd };
}

// scipy.signal.find_peaks(x, distance=, prominence=) without wlen: local
// maxima with plateaus resolved to their middle, then the distance cull
// (highest first), then the prominence test.
std::vector<std::size_t> find_peaks(const std::vector<double>& x, std::size_t distance, double min_prominence)
{
    std::vector<std::size_t> peaks;
    const std::size_t n = x.size();
    std::size_t i = 1;
    while (n >= 3 && i < n - 1)
    {
        if (x[i - 1] < x[i])
        {
            std::size_t ahead = i + 1;
            while (ahead < n - 1 && x[ahead] == x[i])
                ++ahead;
            if (x[ahead] < x[i])
            {
                peaks.push_back((i + ahead - 1) / 2);
                i = ahead;
            }
        }
        ++i;
    }

    // scipy sorts by height (stable) and walks from the highest, so among
    // equal heights the later peak wins; keep that tie order.
    std::vector<std::size_t> order(peaks.size());
    for (std::size_t k = 0; k < order.size(); ++k)
        order[k] = k;
    std::stable_sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) { return x[peaks[a]] < x[peaks[b]]; });
    std::vector<bool> keep(peaks.size(), true);
    for (std::size_t rank = order.size(); rank-- > 0;)
    {
        const std::size_t k = order[rank];
        if (!keep[k])
            continue;
        for (std::size_t j = k; j-- > 0 && peaks[k] - peaks[j] < distance;)
            keep[j] = false;
        for (std::size_t j = k + 1; j < peaks.size() && peaks[j] - peaks[k] < distance; ++j)
            keep[j] = false;
    }

    std::vector<std::size_t> result;
    for (std::size_t k = 0; k < peaks.size(); ++k)
    {
        if (!keep[k])
            continue;
        const std::size_t peak = peaks[k];
        double left_min = x[peak];
        for (std::size_t j = peak + 1; j-- > 0 && x[j] <= x[peak];)
            left_min = std::min(left_min, x[j]);
        double right_min = x[peak];
        for (std::size_t j = peak; j < n && x[j] <= x[peak]; ++j)
            right_min = std::min(right_min, x[j]);
        if (x[peak] - std::max(left_min, right_min) >= min_prominence)
            result.push_back(peak);
    }
    return result;
}

nb::dict track_diagnostic_features(FloatMatrixInput samples, double sample_rate, std::vector<double> band_frequencies_hz,
                                   std::size_t time_slices, std::size_t waveform_points)
{
    if (samples.shape(0) == 0 || samples.shape(1) == 0)
        throw nb::value_error("samples must be a non-empty (frames, channels) float32 array");
    if (!(sample_rate > 0.0) || time_slices == 0 || waveform_points == 0)
        throw nb::value_error("sample_rate, time_slices and waveform_points must be positive");

    Signal signal;
    std::pair<std::vector<double>, std::vector<double>> envelope;
    std::vector<std::vector<double>> spectrogram;
    SpectralShape shape;
    std::pair<std::vector<double>, std::vector<double>> psd;
    std::vector<std::size_t> peaks;
    {
        nb::gil_scoped_release release;
        signal = analysis_signal(samples.data(), samples.shape(0), samples.shape(1));
        envelope = waveform_envelope(signal.samples, waveform_points);
        spectrogram = goertzel_spectrogram(signal.samples, sample_rate, band_frequencies_hz, time_slices);
        shape = spectral_shape(signal.samples, sample_rate);
        psd = welch_psd(signal.samples, sample_rate);
        // The old scipy call: 10*log10 of the density floored at 1e-12, peaks
        // at least 5 dB proud and 8 bins apart.
        for (double& value : psd.second)
            value = 10.0 * std::log10(std::max(value, 1e-12));
        peaks = find_peaks(psd.second, 8, 5.0);
    }

    std::vector<std::pair<double, double>> resonances;
    for (const std::size_t peak : peaks)
        resonances.emplace_back(psd.first[peak], psd.second[peak]);

    nb::dict result;
    result["peak"] = signal.peak;
    result["rms"] = signal.rms;
    result["waveform_peaks"] = envelope.first;
    result["waveform_rms"] = envelope.second;
    result["spectrogram"] = spectrogram;
    result["spectral_centroid_hz"] = shape.centroid_hz ? nb::cast(*shape.centroid_hz) : nb::none();
    result["spectral_flatness"] = shape.flatness ? nb::cast(*shape.flatness) : nb::none();
    result["shape_frames"] = shape.frames;
    result["shape_silent_frames"] = shape.silent_frames;
    result["resonances"] = resonances;
    return result;
}

} // namespace

void init_track_diagnostic_bindings(nb::module_& module)
{
    module.def("track_diagnostic_features", &track_diagnostic_features,
               nb::arg("samples"), nb::arg("sample_rate"), nb::arg("band_frequencies_hz"),
               nb::arg("time_slices"), nb::arg("waveform_points"),
               "Waveform envelope, Goertzel spectrogram, spectral shape and Welch resonance peaks for a (frames, channels) float32 array.");
}
