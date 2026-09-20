#pragma once

#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <array>
#include <sstream>
#include <iomanip>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace PhysicalAcoustics
{

enum class ResonatorType
{
    HarmonicStringPipe,  // 1D resonator: strings, open/closed air columns, brass, voice (integer modes 1, 2, 3...)
    CircularMembrane,    // 2D membrane: drum heads, toms, congas (Bessel modes 1.0, 1.594, 2.136...)
    MetallicPlateBar,    // 2D/3D rigid metal: cymbals, bells, chimes, bars (stiff modes 1.0, 2.756, 5.404...)
    NoiseAtonal,         // No discrete modal resonances (snare rattle, white noise, shakers)
    Unknown
};

enum class PitchGlideType
{
    StableFlat,          // Steady pitch (df0/dt ~ 0): sustained notes, pads, bass holds
    DownwardDive,        // Downward pitch sweep (df0/dt < -5 semitones/s): 808 attack, kick punch, tom drop
    UpwardSweep,         // Upward pitch sweep (df0/dt > +5 semitones/s): risers, sweeps
    Modulated,           // Pitch modulation (4-8 Hz vibrato/flutter): vocals, rhodes tremolo
    Atonal               // Unpitched / unvoiced
};

enum class PhysicalMaterial
{
    Wood,                // High internal damping at high frequencies (Q ~ 50-350)
    Metal,               // Extremely low loss factor, long modal ring (Q > 1500)
    SkinMylar,           // Fast air cavity dissipation and tension relaxation
    GlassCeramic,        // Sharp inharmonic ring with high initial Q
    Unknown
};

inline std::string materialToString(PhysicalMaterial m)
{
    switch (m)
    {
        case PhysicalMaterial::Wood: return "Wood";
        case PhysicalMaterial::Metal: return "Metal";
        case PhysicalMaterial::SkinMylar: return "Skin";
        case PhysicalMaterial::GlassCeramic: return "Glass";
        case PhysicalMaterial::Unknown: return "Unknown";
    }
    return "Unknown";
}

enum class MalletHardness
{
    SoftFelt,            // Contact duration tau_c > 8 ms (timpani mallet, soft hammer)
    MediumRubber,        // Contact duration tau_c in [3, 8] ms (vibraphone mallet, padded beater)
    HardWood,            // Contact duration tau_c in [1, 3] ms (drumstick tip, xylophone)
    HardMetal,           // Contact duration tau_c < 1 ms (Dirac transient, slap, metallic click)
    Continuous           // Non-impact driven excitation (bow, blown, synth sustain)
};

enum class BoreGeometry
{
    CylindricalClosed,   // Odd harmonics dominant (R_odd/even >> 2.2) e.g. Clarinet, closed pipe
    ConicalOrOpen,       // All integer harmonics present e.g. Saxophone, Flute, open pipe
    NonBore
};

struct SpectralPeak
{
    float frequencyHz = 0.0f;
    float magnitude = 0.0f;
};

struct Analysis
{
    ResonatorType resonator = ResonatorType::Unknown;
    PitchGlideType pitchGlide = PitchGlideType::Atonal;
    PhysicalMaterial material = PhysicalMaterial::Unknown;
    MalletHardness mallet = MalletHardness::Continuous;
    BoreGeometry bore = BoreGeometry::NonBore;

    float f0Hz = 0.0f;
    float harmonicFit = 0.0f;      // [0, 1] fit to integer harmonic series
    float membraneFit = 0.0f;      // [0, 1] fit to circular Bessel membrane modes
    float plateBarFit = 0.0f;      // [0, 1] fit to rigid bar / plate modes
    float inharmonicityB = 0.0f;    // Stiff string parameter B in fn = n*f0*sqrt(1 + B*n^2)
    float pitchSlopeSemitonesPerSec = 0.0f; // df0/dt
    float oddEvenHarmonicRatio = 1.0f;      // Ratio of odd to even partial energy
    float harmonicToNoiseRatio = 0.0f;     // Ratio of modal energy to background noise
    float qualityFactorQ = 0.0f;           // Resonator Q factor (pi * f0 * tau)
    float contactDurationMs = 0.0f;        // Hertzian mallet contact duration (tau_c)

    std::string physicalClass;     // e.g. "Kick", "Snare", "Tom", "Crash", "Hi-Hat", "Bass", "Piano/Keys", "Sustained Tonal", "Riser"
    std::string physicalBadge;     // Short summary badge e.g. "Membrane (65 Hz) • Fast Attack"
    std::string physicalDetails;   // Detailed acoustic diagnostic
};

// Known physical mode templates (ratios relative to f0)
inline const std::array<float, 10>& getHarmonicTemplate() noexcept
{
    static const std::array<float, 10> t = { 1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f, 8.0f, 9.0f, 10.0f };
    return t;
}

inline const std::array<float, 8>& getMembraneTemplate() noexcept
{
    // Bessel zero modes for circular membrane clamped at boundary: J_m(k r) = 0
    static const std::array<float, 8> t = { 1.000f, 1.594f, 2.136f, 2.296f, 2.653f, 2.918f, 3.156f, 3.501f };
    return t;
}

inline const std::array<float, 4>& getPlateBarTemplate() noexcept
{
    // Euler-Bernoulli free-free beam & Kirchhoff plate dispersion modes
    static const std::array<float, 4> t = { 1.000f, 2.756f, 5.404f, 8.933f };
    return t;
}

template <size_t N>
inline float computeTemplateFit(const std::vector<SpectralPeak>& peaks, const std::array<float, N>& tmpl, float tolerance = 0.07f)
{
    if (peaks.size() < 2) return 0.0f;

    const float f0 = peaks.front().frequencyHz;
    if (f0 <= 20.0f) return 0.0f;

    float totalWeight = 0.0f;
    for (const auto& p : peaks) totalWeight += p.magnitude;
    if (totalWeight <= 1.0e-9f) return 0.0f;

    float score = 0.0f;
    for (const auto& p : peaks)
    {
        const float r = p.frequencyHz / f0;
        float minRelDist = 1.0e9f;
        for (size_t i = 0; i < N; ++i)
        {
            const float diff = std::abs(r - tmpl[i]) / std::max(tmpl[i], 1.0e-4f);
            if (diff < minRelDist) minRelDist = diff;
        }

        const float weight = p.magnitude / totalWeight;
        const float match = std::exp(-(minRelDist * minRelDist) / (2.0f * tolerance * tolerance));
        score += weight * match;
    }

    return std::min(1.0f, std::max(0.0f, score));
}

inline float estimateInharmonicityB(const std::vector<SpectralPeak>& peaks)
{
    if (peaks.size() < 4) return 0.0f;

    const float f0 = peaks.front().frequencyHz;
    if (f0 <= 20.0f) return 0.0f;

    double bSum = 0.0;
    int count = 0;

    for (size_t i = 1; i < peaks.size() && count < 6; ++i)
    {
        const float fn = peaks[i].frequencyHz;
        const float n = std::round(fn / f0);
        if (n >= 2.0f && n <= 10.0f)
        {
            const double ratioSq = static_cast<double>(fn * fn) / static_cast<double>(n * n * f0 * f0);
            if (ratioSq > 1.0)
            {
                const double bEst = (ratioSq - 1.0) / static_cast<double>(n * n);
                if (bEst > 0.0 && bEst < 0.05)
                {
                    bSum += bEst;
                    count++;
                }
            }
        }
    }

    return count > 0 ? static_cast<float>(bSum / count) : 0.0f;
}

inline float computeOddEvenRatio(const std::vector<SpectralPeak>& peaks)
{
    if (peaks.size() < 2) return 1.0f;
    const float f0 = peaks.front().frequencyHz;
    if (f0 <= 20.0f) return 1.0f;

    float oddMag = 0.0f;
    float evenMag = 0.0f;

    for (const auto& p : peaks)
    {
        const int n = static_cast<int>(std::round(p.frequencyHz / f0));
        if (n >= 1 && n <= 10)
        {
            if (n % 2 == 1) oddMag += p.magnitude;
            else evenMag += p.magnitude;
        }
    }
    return (evenMag > 1.0e-9f) ? (oddMag / evenMag) : (oddMag > 0.0f ? 10.0f : 1.0f);
}

inline std::vector<SpectralPeak> extractSpectralPeaksFromBuffer(const float* data, int numSamples, double sampleRate, int maxPeaks = 12)
{
    std::vector<SpectralPeak> peaks;
    if (data == nullptr || numSamples < 64 || sampleRate <= 0.0) return peaks;

    // Use an analysis window up to 4096 samples
    const int N = std::min(4096, numSamples);
    if (N < 64) return peaks;

    // Compute power spectrum over logarithmically spaced bins from 30Hz to 8000Hz
    const int numBins = 180;
    std::vector<float> mag(static_cast<size_t>(numBins), 0.0f);
    std::vector<float> freqs(static_cast<size_t>(numBins), 0.0f);

    const double minFreq = 30.0;
    const double maxFreq = std::min(sampleRate * 0.45, 8000.0);
    if (maxFreq <= minFreq) return peaks;

    const double logMin = std::log(minFreq);
    const double logMax = std::log(maxFreq);

    for (int k = 0; k < numBins; ++k)
    {
        const double f = std::exp(logMin + (logMax - logMin) * (static_cast<double>(k) / (numBins - 1)));
        freqs[static_cast<size_t>(k)] = static_cast<float>(f);
        const double omega = 2.0 * M_PI * f / sampleRate;

        double realSum = 0.0;
        double imagSum = 0.0;
        for (int n = 0; n < N; ++n)
        {
            // Hann window
            const double w = 0.5 * (1.0 - std::cos(2.0 * M_PI * n / (N - 1)));
            const double val = static_cast<double>(data[n]) * w;
            realSum += val * std::cos(omega * n);
            imagSum -= val * std::sin(omega * n);
        }
        mag[static_cast<size_t>(k)] = static_cast<float>(std::sqrt(realSum * realSum + imagSum * imagSum));
    }

    // Find local maxima with magnitude threshold
    float maxMag = 1e-9f;
    for (float m : mag) if (m > maxMag) maxMag = m;

    for (int k = 1; k < numBins - 1; ++k)
    {
        const size_t idx = static_cast<size_t>(k);
        if (mag[idx] > mag[idx - 1] && mag[idx] > mag[idx + 1] && (mag[idx] / maxMag) > 0.04f)
        {
            // Sub-bin parabolic interpolation for precision frequency
            const float alpha = mag[idx - 1];
            const float beta = mag[idx];
            const float gamma = mag[idx + 1];
            const float denom = alpha - 2.0f * beta + gamma;
            const float p = (std::abs(denom) > 1e-9f) ? (0.5f * (alpha - gamma) / denom) : 0.0f;
            const float interpFreq = freqs[idx] + p * (freqs[idx] - freqs[idx - 1]);

            if (interpFreq >= 30.0f && interpFreq <= maxFreq)
            {
                peaks.push_back({ interpFreq, mag[idx] / maxMag });
            }
        }
    }

    // Sort by magnitude descending and take top maxPeaks
    std::sort(peaks.begin(), peaks.end(), [](const SpectralPeak& a, const SpectralPeak& b) {
        return a.magnitude > b.magnitude;
    });

    if (peaks.size() > static_cast<size_t>(maxPeaks))
        peaks.resize(static_cast<size_t>(maxPeaks));

    // Sort chosen peaks by frequency ascending
    std::sort(peaks.begin(), peaks.end(), [](const SpectralPeak& a, const SpectralPeak& b) {
        return a.frequencyHz < b.frequencyHz;
    });

    return peaks;
}

inline float estimatePitchSlope(const float* data, int numSamples, double sampleRate)
{
    if (data == nullptr || numSamples < 512 || sampleRate <= 0.0) return 0.0f;

    // Window 1: early attack
    const int winSize = std::min(1024, numSamples / 2);
    if (winSize < 256) return 0.0f;

    auto earlyPeaks = extractSpectralPeaksFromBuffer(data, winSize, sampleRate, 4);
    
    // Window 2: decay/sustain
    const int offset = std::min(numSamples - winSize, winSize);
    auto latePeaks = extractSpectralPeaksFromBuffer(data + offset, winSize, sampleRate, 4);

    if (!earlyPeaks.empty() && !latePeaks.empty())
    {
        const float fEarly = earlyPeaks.front().frequencyHz;
        const float fLate = latePeaks.front().frequencyHz;
        if (fEarly > 30.0f && fLate > 30.0f)
        {
            const float semitones = 12.0f * static_cast<float>(std::log2(fLate / fEarly));
            const float dtSeconds = static_cast<float>(offset) / static_cast<float>(sampleRate);
            if (dtSeconds > 0.001f)
            {
                return semitones / dtSeconds;
            }
        }
    }
    return 0.0f;
}

inline float estimateContactDurationMs(const float* mono, int numFrames, double sampleRate)
{
    if (mono == nullptr || numFrames < 64 || sampleRate <= 0.0)
        return 0.0f;

    const int maxScan = std::min(numFrames, static_cast<int>(sampleRate * 0.10));
    float maxVal = 0.0f;
    int peakIdx = 0;
    for (int i = 0; i < maxScan; ++i)
    {
        const float val = std::abs(mono[i]);
        if (val > maxVal)
        {
            maxVal = val;
            peakIdx = i;
        }
    }

    if (maxVal < 1.0e-4f || peakIdx <= 0)
        return 0.0f;

    const float thresh10 = 0.10f * maxVal;
    const float thresh90 = 0.90f * maxVal;

    int idx10 = 0;
    int idx90 = peakIdx;

    for (int i = 0; i <= peakIdx; ++i)
    {
        if (std::abs(mono[i]) >= thresh10)
        {
            idx10 = i;
            break;
        }
    }
    for (int i = idx10; i <= peakIdx; ++i)
    {
        if (std::abs(mono[i]) >= thresh90)
        {
            idx90 = i;
            break;
        }
    }

    const float riseSamples = static_cast<float>(std::max(1, idx90 - idx10));
    return (riseSamples / static_cast<float>(sampleRate)) * 1000.0f;
}

inline Analysis analyze(const std::vector<SpectralPeak>& peaks,
                        float f0Hz,
                        float pitchSlopeSemitonesPerSec,
                        float zeroCrossingRate,
                        float crestFactor,
                        float decayTimeSeconds,
                        float energyDecayRatio,
                        float contactDurationMs = 0.0f)
{
    Analysis result;
    result.f0Hz = f0Hz > 20.0f ? f0Hz : (peaks.empty() ? 0.0f : peaks.front().frequencyHz);
    result.pitchSlopeSemitonesPerSec = pitchSlopeSemitonesPerSec;
    result.contactDurationMs = contactDurationMs;

    // Resonator Q factor approximation: Q = pi * f0 * tau_decay
    if (result.f0Hz > 20.0f && decayTimeSeconds > 0.01f)
    {
        result.qualityFactorQ = static_cast<float>(M_PI) * result.f0Hz * decayTimeSeconds;
    }
    else
    {
        result.qualityFactorQ = 0.0f;
    }

    // Pitch trajectory classification
    if (result.f0Hz <= 20.0f || peaks.empty())
    {
        result.pitchGlide = PitchGlideType::Atonal;
    }
    else if (pitchSlopeSemitonesPerSec < -6.0f)
    {
        result.pitchGlide = PitchGlideType::DownwardDive;
    }
    else if (pitchSlopeSemitonesPerSec > +6.0f)
    {
        result.pitchGlide = PitchGlideType::UpwardSweep;
    }
    else
    {
        result.pitchGlide = PitchGlideType::StableFlat;
    }

    // Modal template matching
    if (!peaks.empty())
    {
        result.harmonicFit = computeTemplateFit(peaks, getHarmonicTemplate(), 0.06f);
        result.membraneFit = computeTemplateFit(peaks, getMembraneTemplate(), 0.07f);
        result.plateBarFit = computeTemplateFit(peaks, getPlateBarTemplate(), 0.08f);
        result.inharmonicityB = estimateInharmonicityB(peaks);
        result.oddEvenHarmonicRatio = computeOddEvenRatio(peaks);

        float totalMag = 0.0f;
        for (const auto& p : peaks) totalMag += p.magnitude;
        result.harmonicToNoiseRatio = std::min(1.0f, totalMag);

        // Determine dominant resonator
        if (zeroCrossingRate > 0.22f && result.harmonicFit < 0.45f)
        {
            result.resonator = ResonatorType::NoiseAtonal;
        }
        else if (result.harmonicFit > 0.65f && result.harmonicFit >= result.membraneFit && result.harmonicFit >= result.plateBarFit)
        {
            result.resonator = ResonatorType::HarmonicStringPipe;
        }
        else if (result.membraneFit > 0.55f && result.membraneFit >= result.plateBarFit && zeroCrossingRate <= 0.22f)
        {
            result.resonator = ResonatorType::CircularMembrane;
        }
        else if (result.plateBarFit > 0.50f)
        {
            result.resonator = ResonatorType::MetallicPlateBar;
        }
        else if (zeroCrossingRate > 0.18f && result.harmonicFit < 0.35f)
        {
            result.resonator = ResonatorType::NoiseAtonal;
        }
        else
        {
            result.resonator = (result.harmonicFit > 0.45f) ? ResonatorType::HarmonicStringPipe : ResonatorType::Unknown;
        }
    }
    else
    {
        result.resonator = (zeroCrossingRate > 0.25f) ? ResonatorType::NoiseAtonal : ResonatorType::Unknown;
    }

    // Physical Classification Mapping (Deterministic Acoustic Rules)
    const bool isImpulsive = crestFactor >= 3.0f || decayTimeSeconds < 0.8f;
    const bool isSustained = energyDecayRatio >= 0.25f && decayTimeSeconds >= 1.5f;

    if (result.resonator == ResonatorType::CircularMembrane)
    {
        if (result.f0Hz < 120.0f && (result.pitchGlide == PitchGlideType::DownwardDive || isImpulsive))
        {
            result.physicalClass = "Kick";
        }
        else if (result.f0Hz >= 100.0f && result.f0Hz <= 350.0f && result.pitchGlide == PitchGlideType::DownwardDive)
        {
            result.physicalClass = "Tom";
        }
        else if (result.harmonicFit < 0.40f && zeroCrossingRate >= 0.08f)
        {
            result.physicalClass = "Snare";
        }
        else
        {
            result.physicalClass = "Percussion (Membrane)";
        }
    }
    else if (result.resonator == ResonatorType::MetallicPlateBar)
    {
        if (decayTimeSeconds >= 1.0f || energyDecayRatio >= 0.15f)
        {
            result.physicalClass = "Crash / Cymbal";
        }
        else
        {
            result.physicalClass = "Metallic Percussion";
        }
    }
    else if (result.resonator == ResonatorType::NoiseAtonal)
    {
        if (zeroCrossingRate >= 0.25f && decayTimeSeconds < 0.6f)
        {
            result.physicalClass = "Hi-Hat";
        }
        else if (zeroCrossingRate >= 0.10f && zeroCrossingRate < 0.25f && isImpulsive)
        {
            result.physicalClass = "Clap / Snare Noise";
        }
        else
        {
            result.physicalClass = "Atonal Texture / Noise";
        }
    }
    else if (result.resonator == ResonatorType::HarmonicStringPipe)
    {
        if (result.inharmonicityB > 0.0005f && isImpulsive)
        {
            result.physicalClass = "Piano / Plucked String";
        }
        else if (result.f0Hz < 120.0f)
        {
            result.physicalClass = isSustained ? "Bass Loop" : "Bass One-Shot";
        }
        else if (isSustained)
        {
            result.physicalClass = "Sustained Tonal / Lead / Pad";
        }
        else
        {
            result.physicalClass = "Tonal Hit / Pluck";
        }
    }
    else
    {
        if (result.pitchGlide == PitchGlideType::UpwardSweep)
        {
            result.physicalClass = "Riser / Sweep";
        }
        else if (isSustained)
        {
            result.physicalClass = "Sustained Sound";
        }
        else
        {
            result.physicalClass = "Percussive Hit";
        }
    }

    // Classify Mallet Hardness
    if (!isImpulsive)
    {
        result.mallet = MalletHardness::Continuous;
    }
    else if (result.contactDurationMs > 8.0f)
    {
        result.mallet = MalletHardness::SoftFelt;
    }
    else if (result.contactDurationMs >= 3.0f)
    {
        result.mallet = MalletHardness::MediumRubber;
    }
    else if (result.contactDurationMs >= 1.0f)
    {
        result.mallet = MalletHardness::HardWood;
    }
    else
    {
        result.mallet = MalletHardness::HardMetal;
    }

    // Classify Bore Geometry
    if (result.resonator == ResonatorType::HarmonicStringPipe)
    {
        if (result.oddEvenHarmonicRatio > 2.2f)
            result.bore = BoreGeometry::CylindricalClosed;
        else
            result.bore = BoreGeometry::ConicalOrOpen;
    }
    else
    {
        result.bore = BoreGeometry::NonBore;
    }

    // Classify Physical Material from Q factor and resonator
    if (result.resonator == ResonatorType::CircularMembrane)
    {
        result.material = PhysicalMaterial::SkinMylar;
    }
    else if (result.resonator == ResonatorType::MetallicPlateBar || (result.qualityFactorQ > 1500.0f && zeroCrossingRate > 0.15f))
    {
        result.material = PhysicalMaterial::Metal;
    }
    else if (result.inharmonicityB > 0.003f && isImpulsive)
    {
        result.material = PhysicalMaterial::GlassCeramic;
    }
    else if (isImpulsive && result.qualityFactorQ < 450.0f && result.f0Hz > 80.0f)
    {
        result.material = PhysicalMaterial::Wood;
    }
    else
    {
        result.material = PhysicalMaterial::Unknown;
    }

    // Generate physical description badge
    std::ostringstream ss;
    if (result.material == PhysicalMaterial::Metal)
        ss << "Metal ";
    else if (result.material == PhysicalMaterial::Wood)
        ss << "Wood ";

    switch (result.resonator)
    {
        case ResonatorType::HarmonicStringPipe:
            if (result.bore == BoreGeometry::CylindricalClosed)
                ss << "Closed Pipe (Cylindrical)";
            else
                ss << "1D Harmonic Resonator";
            break;
        case ResonatorType::CircularMembrane:
            ss << "2D Circular Membrane";
            break;
        case ResonatorType::MetallicPlateBar:
            ss << "2D Rigid Plate/Bar";
            break;
        case ResonatorType::NoiseAtonal:
            ss << "Stochastic Noise";
            break;
        case ResonatorType::Unknown:
        default:
            ss << "Acoustic Signal";
            break;
    }

    if (result.f0Hz > 20.0f)
    {
        ss << " (" << static_cast<int>(std::round(result.f0Hz)) << " Hz)";
    }

    if (result.pitchGlide == PitchGlideType::DownwardDive)
        ss << " • Downward Pitch Dive";
    else if (result.pitchGlide == PitchGlideType::UpwardSweep)
        ss << " • Upward Pitch Sweep";

    if (result.mallet == MalletHardness::SoftFelt)
        ss << " • Soft Felt Strike";
    else if (result.mallet == MalletHardness::HardWood)
        ss << " • Wood Stick Strike";
    else if (result.mallet == MalletHardness::HardMetal)
        ss << " • Sharp Metal Impact";
    else if (isImpulsive)
        ss << " • Impulsive Attack";
    else if (isSustained)
        ss << " • Sustained";

    result.physicalBadge = ss.str();
    return result;
}

inline Analysis analyzeFromAudioBuffer(const float* mono,
                                      int numFrames,
                                      double sampleRate,
                                      float zeroCrossingRate,
                                      float crestFactor,
                                      float decayTimeSeconds,
                                      float energyDecayRatio)
{
    auto peaks = extractSpectralPeaksFromBuffer(mono, numFrames, sampleRate);
    const float f0 = peaks.empty() ? 0.0f : peaks.front().frequencyHz;
    const float pitchSlope = estimatePitchSlope(mono, numFrames, sampleRate);
    const float contactDurationMs = estimateContactDurationMs(mono, numFrames, sampleRate);

    return analyze(peaks, f0, pitchSlope, zeroCrossingRate, crestFactor, decayTimeSeconds, energyDecayRatio, contactDurationMs);
}

struct MixCollisionDiagnostic
{
    bool lowEndMaskingDetected = false;
    float dominantCollisionFreqHz = 0.0f;
    float phaseCorrelation = 1.0f;
    float recommendedHighPassHz = 0.0f;
    std::string advisoryMessage;
};

inline MixCollisionDiagnostic evaluateMixCollision(const float* stemA,
                                                   const float* stemB,
                                                   int numFrames,
                                                   double sampleRate)
{
    MixCollisionDiagnostic diag;
    if (stemA == nullptr || stemB == nullptr || numFrames <= 0 || sampleRate <= 0.0)
        return diag;

    double sumAA = 0.0, sumBB = 0.0, sumAB = 0.0;
    double lowEnergyA = 0.0, lowEnergyB = 0.0;

    // Simple single-pole low-pass filter state (~150 Hz cutoff) for low-end isolation
    const double dt = 1.0 / sampleRate;
    const double rc = 1.0 / (2.0 * M_PI * 150.0);
    const double alpha = dt / (rc + dt);

    double lpA = 0.0;
    double lpB = 0.0;

    for (int i = 0; i < numFrames; ++i)
    {
        const double a = stemA[i];
        const double b = stemB[i];

        sumAA += a * a;
        sumBB += b * b;
        sumAB += a * b;

        lpA += alpha * (a - lpA);
        lpB += alpha * (b - lpB);

        lowEnergyA += lpA * lpA;
        lowEnergyB += lpB * lpB;
    }

    const double denom = std::sqrt(sumAA * sumBB) + 1.0e-12;
    diag.phaseCorrelation = static_cast<float>(sumAB / denom);

    const double totalEnergyA = sumAA + 1.0e-12;
    const double totalEnergyB = sumBB + 1.0e-12;
    const double lowRatioA = lowEnergyA / totalEnergyA;
    const double lowRatioB = lowEnergyB / totalEnergyB;

    // Masking occurs if both stems have substantial low-end content (>25% energy below 150 Hz)
    if (lowRatioA > 0.25 && lowRatioB > 0.25)
    {
        diag.lowEndMaskingDetected = true;
        diag.dominantCollisionFreqHz = 80.0f;
        diag.recommendedHighPassHz = 100.0f;

        if (diag.phaseCorrelation < 0.0f)
        {
            diag.advisoryMessage = "Severe Low-End Phase Cancellation: Stems are destructive in sub-150Hz. Invert phase or high-pass secondary stem.";
        }
        else if (diag.phaseCorrelation < 0.3f)
        {
            diag.advisoryMessage = "Sub-Bass Frequency Masking: Low frequencies overlap. Sidechain compression or HPF at 90Hz recommended.";
        }
        else
        {
            diag.advisoryMessage = "Coherent Low-End Summation: Moderate overlap in sub frequencies.";
        }
    }
    else
    {
        diag.advisoryMessage = "No significant low-end clashing detected.";
    }

    return diag;
}

} // namespace PhysicalAcoustics

