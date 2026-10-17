#include "key_tempo_bindings.hpp"

#include "fft_core.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <stdexcept>
#include <vector>

#include <nanobind/ndarray.h>
#include <nanobind/nanobind.h>
#include <nanobind/stl/vector.h>

#if defined(KENN_HAS_ACCELERATE)
#include <Accelerate/Accelerate.h>
#endif

namespace nb = nanobind;

using FloatVectorInput = nb::ndarray<nb::numpy, const float, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

namespace {

// Key and tempo replace librosa's chroma_cqt and beat_track, which the app
// bundle leaves out (build_kenn_app.py), so the shipped app had neither. We do
// not reproduce librosa's CQT; accuracy is scored against labelled sample
// packs instead (CPP_DSP_KEY_TEMPO_RECEIPT.md).

// Chroma covers C1 (32.7 Hz) to B7 (3951 Hz). Bass lines carry most of the key
// in loop material, and above B7 there are few fundamentals, only harmonics
// that fold onto other pitch classes.
constexpr double kChromaLowHz = 32.703;
constexpr double kChromaHighHz = 3951.07;
// A bin counts toward a note within half a semitone of its centre, weighted
// down linearly to zero at the edge, so every bin votes for the note nearest
// it and nothing between notes is lost. A quarter semitone scored a little
// worse on the tune half of the labelled set (the receipt has the numbers).
constexpr double kChromaHalfWidthSemitones = 0.5;
// Frames 60 dB below the loudest frame are skipped, so a tail
// of silence or reverb noise does not get a full vote after normalisation.
constexpr double kChromaFrameFloorDb = -60.0;

// Onset frames every 11.6 ms (512 samples at 44.1 kHz; half librosa's 23.2 ms
// default, 512 samples at 22.05 kHz), so 120 BPM is a lag of about 43 frames.
constexpr double kOnsetHopSeconds = 512.0 / 44100.0;
constexpr std::size_t kOnsetBands = 40;
// 30 Hz starts just under an 808 or sub-kick fundamental (~32 Hz at C1), and
// 11 kHz covers hi-hat and snare transients while staying below the 22.05 kHz
// Nyquist (capped at rate / 2 for 8-16 kHz inputs).
constexpr double kOnsetLowHz = 30.0;
constexpr double kOnsetHighHz = 11000.0;
// librosa's onset strength clips the dB spectrogram 80 dB under its peak.
constexpr double kOnsetTopDb = 80.0;
// Tempo search range 30-300 BPM and librosa's prior: log-normal about
// 120 BPM with a one-octave standard deviation. The prior is what settles
// 2x/0.5x ambiguity, so changing it moves octave errors, not accuracy within one.
constexpr double kTempoMinBpm = 30.0;
constexpr double kTempoMaxBpm = 300.0;
constexpr double kTempoPriorBpm = 120.0;
constexpr double kTempoPriorOctaves = 1.0;
// Autocorrelation windows of 8 s, as librosa's tempogram (ac_size=8).
constexpr double kTempoWindowSeconds = 8.0;
// A tempo needs at least two onsets: envelope peaks where the spectrum rises
// by 4 dB or more (mean over the 40 bands). A held sine or chord peaks at
// 0.2-1.8 dB, white noise and a vibrato tone at under 4, a single drum hit
// gives one; every one of those used to get a confident BPM. 3 dB kept
// noise, 5 dB cost more loops. With the 4-frame reference and the pair rule
// below, the 258 labelled loops go from 60 to 50 within 4%, with 48 wrong
// and 78 left without a BPM (17 Oct 2026, CPP_DSP_KEY_TEMPO_RECEIPT.md).
constexpr double kOnsetMinRiseDb = 4.0;
constexpr std::size_t kTempoMinOnsets = 2;
// Each band's rise is measured from the loudest of its previous 4 frames
// (one 46 ms window), not from the frame before. Below about 45 Hz the window
// holds under two periods, so a held saw's band levels swing up and down with
// phase on alternate frames: a 40 Hz saw rose 5 dB every other frame and read
// 120 BPM at strength 0.94 (adversary review, 17 Oct 2026). Against the
// 4-frame maximum the repeating phase pattern cancels and held saws from 30 to
// 45 Hz peak at 1.3 dB; 2 frames still let 30 Hz through, 3 let an aliased
// 129 Hz square through. A real onset is louder than everything just before
// it, so it keeps its full rise.
constexpr std::size_t kOnsetReferenceFrames = 4;
// ...and the chosen period must be backed by at least two onset pairs that
// far apart. One spacing between two events is not a tempo: a one-shot with
// a second transient, or two kicks, otherwise reported the gap as a BPM.
constexpr std::size_t kTempoMinOnsetPairs = 2;

std::vector<std::size_t> onset_frames(const std::vector<double>& envelope)
{
    std::vector<std::size_t> onsets;
    for (std::size_t index = 1; index + 1 < envelope.size(); ++index)
    {
        const double value = envelope[index];
        if (value >= kOnsetMinRiseDb && value >= envelope[index - 1] && value > envelope[index + 1])
            onsets.push_back(index);
    }
    return onsets;
}

class RealFFT {
public:
    explicit RealFFT(std::size_t size)
        : size_(size)
    {
        if (size < 2 || (size & (size - 1)) != 0)
            throw std::invalid_argument("FFT size must be a power of two");
#if defined(KENN_HAS_ACCELERATE)
        while ((std::size_t { 1 } << log2_size_) < size)
            ++log2_size_;
        setup_ = vDSP_create_fftsetupD(static_cast<vDSP_Length>(log2_size_), FFT_RADIX2);
        if (setup_ == nullptr)
            throw std::runtime_error("Accelerate FFT setup allocation failed");
        real_.resize(size / 2);
        imag_.resize(size / 2);
#else
        scratch_.resize(size);
#endif
    }

#if defined(KENN_HAS_ACCELERATE)
    ~RealFFT()
    {
        if (setup_ != nullptr)
            vDSP_destroy_fftsetupD(setup_);
    }
#endif

    RealFFT(const RealFFT&) = delete;
    RealFFT& operator=(const RealFFT&) = delete;

    // Writes size/2 + 1 magnitudes of the unnormalised DFT of `input`.
    void magnitudes(const std::vector<double>& input, std::vector<double>& out)
    {
        out.resize(size_ / 2 + 1);
#if defined(KENN_HAS_ACCELERATE)
        DSPDoubleSplitComplex split { real_.data(), imag_.data() };
        vDSP_ctozD(reinterpret_cast<const DSPDoubleComplex*>(input.data()), 2, &split, 1,
                   static_cast<vDSP_Length>(size_ / 2));
        vDSP_fft_zripD(setup_, &split, 1, log2_size_, FFT_FORWARD);
        // vDSP's packed real FFT is twice the textbook DFT; halve it so both
        // builds give the same numbers.
        out[0] = 0.5 * std::abs(real_[0]);
        out[size_ / 2] = 0.5 * std::abs(imag_[0]);
        for (std::size_t bin = 1; bin < size_ / 2; ++bin)
            out[bin] = 0.5 * std::hypot(real_[bin], imag_[bin]);
#else
        for (std::size_t index = 0; index < size_; ++index)
            scratch_[index] = kenn::dsp::Complex(input[index], 0.0);
        kenn::dsp::fft_in_place(scratch_);
        for (std::size_t bin = 0; bin <= size_ / 2; ++bin)
            out[bin] = std::abs(scratch_[bin]);
#endif
    }

private:
    std::size_t size_;
#if defined(KENN_HAS_ACCELERATE)
    vDSP_Length log2_size_ = 0;
    FFTSetupD setup_ = nullptr;
    std::vector<double> real_;
    std::vector<double> imag_;
#else
    std::vector<kenn::dsp::Complex> scratch_;
#endif
};

std::vector<double> hann(std::size_t size)
{
    // Periodic Hann, as scipy/librosa use for STFT analysis.
    std::vector<double> window(size);
    for (std::size_t index = 0; index < size; ++index)
        window[index] = 0.5 - 0.5 * std::cos(2.0 * std::numbers::pi * static_cast<double>(index) / static_cast<double>(size));
    return window;
}

// Mean of per-frame peak-normalised chroma, index 0 = C.
std::array<double, 12> mean_chroma(const float* samples, std::size_t count, double rate)
{
    std::array<double, 12> total {};
    // The window must resolve a semitone at C1 (1.9 Hz), so the bin spacing
    // has to be about 1.3 Hz: 32768 samples at 44.1 kHz (743 ms). Key is a
    // whole-file average, so the time smear costs nothing here.
    const std::size_t fft_size = kenn::dsp::next_power_of_two(static_cast<std::size_t>(std::ceil(rate / 1.35)));
    const std::size_t hop = fft_size / 4;

    struct BinWeight {
        std::size_t bin;
        std::size_t note;
        double weight;
    };
    std::vector<BinWeight> weights;
    const double bin_hz = rate / static_cast<double>(fft_size);
    for (std::size_t bin = 1; bin <= fft_size / 2; ++bin)
    {
        const double hz = static_cast<double>(bin) * bin_hz;
        // Skip bins outside C1..B7 so sub-bass rumble and upper harmonics do not vote.
        if (hz < kChromaLowHz || hz > kChromaHighHz)
            continue;
        const double midi = 69.0 + 12.0 * std::log2(hz / 440.0);
        const double nearest = std::round(midi);
        const double distance = std::abs(midi - nearest);
        // The triangular weight reaches zero at kChromaHalfWidthSemitones, so
        // anything further would add a zero or negative weight.
        if (distance > kChromaHalfWidthSemitones)
            continue;
        weights.push_back({ bin, static_cast<std::size_t>(nearest), 1.0 - distance / kChromaHalfWidthSemitones });
    }
    // A linear-frequency STFT gives a semitone at 2 kHz about 90 bins and one
    // at 65 Hz about 3. Summing bins let the upper octaves, mostly harmonics,
    // outvote the fundamentals: the first run picked the fifth on 77 of 250
    // labelled files. So each note is the weighted mean of its own bins, the
    // way a constant-Q transform gives every note one bin.
    std::array<double, 128> note_weight {};
    for (const auto& item : weights)
        note_weight[item.note] += item.weight;

    const auto window = hann(fft_size);
    RealFFT fft(fft_size);
    std::vector<double> frame(fft_size);
    std::vector<double> spectrum;
    std::vector<std::array<double, 12>> frames;
    std::vector<double> energies;
    // Short files get one zero-padded frame rather than none, so a one-shot
    // still reports a pitch class.
    for (std::size_t start = 0; start == 0 || start + fft_size <= count; start += hop)
    {
        for (std::size_t index = 0; index < fft_size; ++index)
            frame[index] = start + index < count ? window[index] * static_cast<double>(samples[start + index]) : 0.0;
        fft.magnitudes(frame, spectrum);
        std::array<double, 12> chroma {};
        double energy = 0.0;
        for (const auto& item : weights)
        {
            chroma[item.note % 12] += item.weight * spectrum[item.bin] / note_weight[item.note];
            energy += spectrum[item.bin] * spectrum[item.bin];
        }
        frames.push_back(chroma);
        energies.push_back(energy);
        if (start + fft_size >= count)
            break;
    }

    const double loudest = *std::max_element(energies.begin(), energies.end());
    // All-zero or out-of-band audio has no pitch energy; returning zeros lets
    // the caller abstain on flat chroma instead of dividing by zero.
    if (!(loudest > 0.0))
        return total;
    const double floor = loudest * std::pow(10.0, kChromaFrameFloorDb / 10.0);
    for (std::size_t index = 0; index < frames.size(); ++index)
    {
        // Skip silent or tail frames so normalisation does not give room noise a full vote.
        if (energies[index] < floor)
            continue;
        const double peak = *std::max_element(frames[index].begin(), frames[index].end());
        // Guard against a zero peak before dividing to normalise the frame.
        if (!(peak > 0.0))
            continue;
        for (std::size_t pc = 0; pc < 12; ++pc)
            total[pc] += frames[index][pc] / peak;
    }
    return total;
}

// Spectral-flux onset envelope: mean positive dB rise across log bands.
std::vector<double> onset_envelope(const float* samples, std::size_t count, double rate, std::size_t hop)
{
    // The window is always four hops (46 ms), zero-padded up to the FFT size.
    // Rounding the window itself to a power of two made it 85 ms at 48 kHz
    // against 46 ms at 44.1 kHz, which smeared each rise over more frames and
    // let the 4 dB onset gate flip on sample rate alone (6 of 120 loops,
    // adversary review 17 Oct 2026).
    const std::size_t window_size = 4 * hop;
    const std::size_t fft_size = kenn::dsp::next_power_of_two(window_size);
    std::vector<double> envelope;
    // Clips shorter than one 46 ms analysis window cannot form even a single
    // onset frame; returning empty leaves the caller with no BPM.
    if (count < window_size)
        return envelope;

    // Band edges spaced evenly in log frequency; each band is a plain sum of
    // power over its bins (at least one bin, so the low bands are not empty).
    const double bin_hz = rate / static_cast<double>(fft_size);
    const double high = std::min(kOnsetHighHz, rate / 2.0);
    std::vector<std::size_t> edges(kOnsetBands + 1);
    for (std::size_t band = 0; band <= kOnsetBands; ++band)
    {
        const double hz = kOnsetLowHz * std::pow(high / kOnsetLowHz, static_cast<double>(band) / kOnsetBands);
        edges[band] = std::min(fft_size / 2, static_cast<std::size_t>(std::lround(hz / bin_hz)));
    }
    for (std::size_t band = 1; band <= kOnsetBands; ++band)
        edges[band] = std::max(edges[band], edges[band - 1] + 1);

    const auto window = hann(window_size);
    RealFFT fft(fft_size);
    std::vector<double> frame(fft_size, 0.0);
    std::vector<double> spectrum;
    const std::size_t frame_count = 1 + (count - window_size) / hop;
    std::vector<double> db(frame_count * kOnsetBands);
    double peak_db = -1e300;
    for (std::size_t index = 0; index < frame_count; ++index)
    {
        const std::size_t start = index * hop;
        for (std::size_t offset = 0; offset < window_size; ++offset)
            frame[offset] = window[offset] * static_cast<double>(samples[start + offset]);
        fft.magnitudes(frame, spectrum);
        for (std::size_t band = 0; band < kOnsetBands; ++band)
        {
            double power = 0.0;
            for (std::size_t bin = edges[band]; bin < edges[band + 1] && bin <= fft_size / 2; ++bin)
                power += spectrum[bin] * spectrum[bin];
            // 1e-10 power floor, librosa's power_to_db amin.
            const double value = 10.0 * std::log10(std::max(power, 1e-10));
            db[index * kOnsetBands + band] = value;
            peak_db = std::max(peak_db, value);
        }
    }
    for (auto& value : db)
        value = std::max(value, peak_db - kOnsetTopDb);

    // The first frames compare against however many frames exist before them;
    // frame 0 has none and stays at zero.
    envelope.assign(frame_count, 0.0);
    for (std::size_t index = 1; index < frame_count; ++index)
    {
        const std::size_t first = index > kOnsetReferenceFrames ? index - kOnsetReferenceFrames : 0;
        double rise = 0.0;
        for (std::size_t band = 0; band < kOnsetBands; ++band)
        {
            double reference = db[first * kOnsetBands + band];
            for (std::size_t previous = first + 1; previous < index; ++previous)
                reference = std::max(reference, db[previous * kOnsetBands + band]);
            rise += std::max(0.0, db[index * kOnsetBands + band] - reference);
        }
        envelope[index] = rise / kOnsetBands;
    }
    return envelope;
}

struct TempoEstimate {
    double bpm = 0.0;
    // Prior-weighted autocorrelation at the chosen lag over lag zero, 0..1.
    double strength = 0.0;
};

TempoEstimate estimate_tempo(const std::vector<double>& envelope, const std::vector<std::size_t>& onsets, double frame_rate)
{
    TempoEstimate result;
    const auto min_lag = static_cast<std::size_t>(std::floor(60.0 * frame_rate / kTempoMaxBpm));
    const auto max_lag = static_cast<std::size_t>(std::ceil(60.0 * frame_rate / kTempoMinBpm));
    // Need at least two periods of the fastest tempo (300 BPM) plus neighbours
    // for peak picking; shorter envelopes return zero BPM.
    if (envelope.size() < 2 * min_lag + 2)
        return result;
    const std::size_t window_frames = std::min(
        envelope.size(), static_cast<std::size_t>(std::lround(kTempoWindowSeconds * frame_rate)));
    const std::size_t lags = std::min(max_lag + 2, window_frames);

    // Average the local autocorrelation of 8 s windows at half-window steps.
    // Each window is mean-removed and Hann-tapered like librosa's tempogram,
    // which keeps one loud fill from owning the whole estimate.
    const auto taper = hann(window_frames);
    std::vector<double> acf(lags, 0.0);
    std::vector<double> segment(window_frames);
    const std::size_t step = std::max<std::size_t>(1, window_frames / 2);
    std::size_t windows = 0;
    for (std::size_t start = 0; start + window_frames <= envelope.size(); start += step)
    {
        double mean = 0.0;
        for (std::size_t index = 0; index < window_frames; ++index)
            mean += envelope[start + index];
        mean /= static_cast<double>(window_frames);
        for (std::size_t index = 0; index < window_frames; ++index)
            segment[index] = taper[index] * (envelope[start + index] - mean);
        for (std::size_t lag = 0; lag < lags; ++lag)
        {
            double sum = 0.0;
            for (std::size_t index = lag; index < window_frames; ++index)
                sum += segment[index] * segment[index - lag];
            acf[lag] += sum;
        }
        ++windows;
    }
    // Flat or zero-variance onset envelopes have zero lag-0 energy, so there is
    // no periodicity to normalise or score.
    if (windows == 0 || !(acf[0] > 0.0))
        return result;

    // A lag is only a candidate when at least two pairs of onsets are that far
    // apart, give or take a frame. Without this, a few isolated kicks read 148 BPM
    // whatever their spacing: the correlation peak came from the 0.4 s decay
    // of one kick, not from the gap between two (adversary review, 17 Oct
    // 2026). Any pair counts, not only neighbours, so a beat with offbeat
    // hits between still offers its beat period.
    std::vector<std::size_t> pairs_at(lags, 0);
    for (std::size_t first = 0; first < onsets.size(); ++first)
    {
        for (std::size_t second = first + 1; second < onsets.size() && onsets[second] - onsets[first] <= lags; ++second)
        {
            const std::size_t distance = onsets[second] - onsets[first];
            for (std::size_t lag = distance - 1; lag <= distance + 1; ++lag)
                if (lag < lags)
                    ++pairs_at[lag];
        }
    }

    std::size_t best = 0;
    double best_score = 0.0;
    for (std::size_t lag = std::max<std::size_t>(1, min_lag); lag < lags - 1; ++lag)
    {
        const double bpm = 60.0 * frame_rate / static_cast<double>(lag);
        // Floor/ceil rounding on min_lag and max_lag can include one lag just
        // outside 30..300 BPM; skip it rather than scoring out-of-range tempos.
        if (bpm < kTempoMinBpm || bpm > kTempoMaxBpm)
            continue;
        // Only a lag where the correlation itself peaks is a period. A held
        // tone has one onset, which after mean removal and the taper leaves a
        // smooth bump whose correlation falls steadily with lag; the prior
        // alone then made up a tempo near 120 BPM (an 8 s sine read 112 BPM,
        // adversary review 17 Oct 2026).
        if (!(acf[lag] > acf[lag - 1] && acf[lag] >= acf[lag + 1]) || pairs_at[lag] < kTempoMinOnsetPairs)
            continue;
        const double octaves = std::log2(bpm / kTempoPriorBpm) / kTempoPriorOctaves;
        const double score = acf[lag] / acf[0] * std::exp(-0.5 * octaves * octaves);
        if (score > best_score)
        {
            best_score = score;
            best = lag;
        }
    }
    // No correlation peak in range at an onset spacing: a sustained tone,
    // noise or a lone hit, where any BPM we printed would be invented.
    if (best == 0)
        return result;

    // Parabolic peak refinement, clamped to +-0.5 frames so a nearly flat peak
    // stays inside its own bin. Without refinement the answer snaps to whole
    // frame lags, about 2.8 BPM apart at 120 BPM, which is librosa's 117.5/123.0.
    double lag = static_cast<double>(best);
    const double left = acf[best - 1];
    const double centre = acf[best];
    const double right = acf[best + 1];
    const double curvature = left - 2.0 * centre + right;
    if (curvature < 0.0)
        lag += std::clamp(0.5 * (left - right) / curvature, -0.5, 0.5);
    result.bpm = 60.0 * frame_rate / lag;
    result.strength = best_score;
    return result;
}

nb::dict key_tempo_features(const FloatVectorInput& samples, int sample_rate)
{
    // Below 8 kHz the chroma FFT shrinks towards two points and its hop to
    // zero, and a WAV header declaring 2 Hz looped forever; above 768 kHz a
    // corrupt 60 MHz header allocated ~5 GB of FFT buffers (adversary reviews,
    // 17 Oct 2026). 8-768 kHz covers telephone audio up to DXD/8x rates.
    if (sample_rate < 8000 || sample_rate > 768000)
        throw std::invalid_argument("sample_rate must be between 8000 and 768000 Hz");
    const std::size_t count = samples.shape(0);
    if (count == 0)
        throw std::invalid_argument("samples must be non-empty");
    const double rate = static_cast<double>(sample_rate);
    const float* data = samples.data();

    std::array<double, 12> chroma;
    TempoEstimate tempo;
    std::size_t hop = 0;
    {
        nb::gil_scoped_release release;
        chroma = mean_chroma(data, count, rate);
        hop = std::max<std::size_t>(1, static_cast<std::size_t>(std::lround(kOnsetHopSeconds * rate)));
        const auto envelope = onset_envelope(data, count, rate, hop);
        const auto onsets = onset_frames(envelope);
        // Too few onsets leaves tempo at zero, which reports as None.
        if (onsets.size() >= kTempoMinOnsets)
            tempo = estimate_tempo(envelope, onsets, rate / static_cast<double>(hop));
    }

    nb::dict result;
    result["chroma"] = std::vector<double>(chroma.begin(), chroma.end());
    if (tempo.bpm > 0.0)
        result["tempo_bpm"] = tempo.bpm;
    else
        result["tempo_bpm"] = nb::none();
    result["tempo_strength"] = tempo.strength;
    result["onset_hop"] = hop;
#if defined(KENN_HAS_ACCELERATE)
    result["backend"] = "cpp-accelerate";
#else
    result["backend"] = "cpp-scalar";
#endif
    return result;
}

} // namespace

void init_key_tempo_bindings(nb::module_& module)
{
    module.def("key_tempo_features", &key_tempo_features,
               nb::arg("samples"), nb::arg("sample_rate"),
               "Mean 12-bin chroma (index 0 = C) and an autocorrelation tempo estimate for mono float32 audio.");
}
