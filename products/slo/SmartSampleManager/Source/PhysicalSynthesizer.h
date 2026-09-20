#pragma once

#include "PhysicalAcoustics.h"
#include <vector>
#include <cmath>
#include <algorithm>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace PhysicalSynthesizer
{

struct ModalPartial
{
    float frequencyHz = 0.0f;
    float initialAmplitude = 0.0f;
    float decayTimeSec = 0.2f;
    float initialPhase = 0.0f;
};

class PhysicalResynthesizer
{
public:
    PhysicalResynthesizer() = default;

    // Build physical resynthesis model directly from extracted acoustic invariants
    static PhysicalResynthesizer fromAnalysis(const PhysicalAcoustics::Analysis& analysis,
                                             float sampleRate = 44100.0f,
                                             float durationSec = 1.0f)
    {
        PhysicalResynthesizer syn;
        syn.sampleRate = sampleRate > 8000.0f ? sampleRate : 44100.0f;
        syn.durationSec = durationSec > 0.05f ? durationSec : 1.0f;
        syn.f0Hz = analysis.f0Hz > 20.0f ? analysis.f0Hz : 130.81f; // Default C3
        syn.contactDurationMs = analysis.contactDurationMs > 0.1f ? analysis.contactDurationMs : 3.0f;
        syn.resonatorType = analysis.resonator;
        syn.material = analysis.material;
        syn.inharmonicityB = analysis.inharmonicityB;
        syn.pitchSlope = analysis.pitchSlopeSemitonesPerSec;
        syn.qualityFactorQ = analysis.qualityFactorQ > 10.0f ? analysis.qualityFactorQ : 300.0f;

        syn.rebuildPartials();
        return syn;
    }

    void setSampleRate(float sr) noexcept
    {
        if (sr > 8000.0f)
            sampleRate = sr;
    }

    void setDuration(float durSec) noexcept
    {
        if (durSec > 0.01f)
            durationSec = durSec;
    }

    // --- Physical Mutation Operators ---

    // 1. Material Morphing: interpolates between Wood (0.0: rapid high-freq damping) and Metal (1.0: long ringing Q)
    void morphMaterial(float woodToMetalRatio)
    {
        woodToMetalRatio = std::max(0.0f, std::min(1.0f, woodToMetalRatio));
        // Interpolate Q factor
        float woodQ = 120.0f;
        float metalQ = 2500.0f;
        qualityFactorQ = (1.0f - woodToMetalRatio) * woodQ + woodToMetalRatio * metalQ;

        // Modulate decay times across partials
        for (size_t i = 0; i < partials.size(); ++i)
        {
            float relFreq = partials[i].frequencyHz / std::max(20.0f, f0Hz);
            // High frequencies decay much faster in wood than metal
            float dampingExponent = (1.0f - woodToMetalRatio) * 1.5f + woodToMetalRatio * 0.3f;
            float baseTau = qualityFactorQ / (float(M_PI) * std::max(20.0f, f0Hz));
            partials[i].decayTimeSec = std::max(0.005f, baseTau / std::pow(relFreq, dampingExponent));
        }

        if (woodToMetalRatio > 0.6f)
            material = PhysicalAcoustics::PhysicalMaterial::Metal;
        else
            material = PhysicalAcoustics::PhysicalMaterial::Wood;
    }

    // 2. Mallet Hardness: reshape excitation contact duration tau_c
    // Soft felt > 8ms, hard wood 1-3ms, hard metal < 1ms
    void adjustMalletHardness(float newContactDurationMs)
    {
        contactDurationMs = std::max(0.05f, std::min(50.0f, newContactDurationMs));
    }

    // 3. Tension Retuning: shift fundamental frequency analytically by semitones
    void retuneMembraneTension(float semitonesShift)
    {
        float ratio = std::pow(2.0f, semitonesShift / 12.0f);
        f0Hz *= ratio;
        for (auto& p : partials)
        {
            p.frequencyHz *= ratio;
        }
    }

    // 4. Inharmonic Dispersion: Euler-Bernoulli beam stiffness injection fn = n*f0*sqrt(1 + B*n^2)
    void setInharmonicStiffness(float newB)
    {
        inharmonicityB = std::max(0.0f, std::min(0.05f, newB));
        rebuildPartials();
    }

    // Synthesize physical modal audio into buffer
    void render(std::vector<float>& outBuffer) const
    {
        const size_t numSamples = static_cast<size_t>(sampleRate * durationSec);
        outBuffer.assign(numSamples, 0.0f);

        if (partials.empty() || numSamples == 0)
            return;

        const float contactSamples = (contactDurationMs * 0.001f) * sampleRate;
        const float halfPeriodSamples = std::max(2.0f, contactSamples * 2.0f);

        // Precompute partial frequencies with optional pitch trajectory
        // For membrane kicks/808s: pitch glide df0/dt (semitones/sec)
        const float pitchGlideRate = (pitchSlope != 0.0f) ? std::pow(2.0f, pitchSlope / (12.0f * sampleRate)) : 1.0f;

        std::vector<float> currentFreqs(partials.size());
        std::vector<float> phases(partials.size());
        std::vector<float> decayPerSample(partials.size());
        std::vector<float> currentAmps(partials.size());

        for (size_t i = 0; i < partials.size(); ++i)
        {
            currentFreqs[i] = partials[i].frequencyHz;
            phases[i] = partials[i].initialPhase;
            currentAmps[i] = partials[i].initialAmplitude;
            // Linear approximation of exp(-1 / (tau * sr))
            float tauSamples = std::max(10.0f, partials[i].decayTimeSec * sampleRate);
            decayPerSample[i] = std::exp(-1.0f / tauSamples);
        }

        float maxPeak = 0.0f;

        for (size_t n = 0; n < numSamples; ++n)
        {
            // Hertzian excitation envelope e(t)
            float env = 1.0f;
            if (static_cast<float>(n) < contactSamples)
            {
                // Rising compression phase: sin(pi * t / (2 * tau_c))
                env = std::sin(float(M_PI) * static_cast<float>(n) / halfPeriodSamples);
            }

            float sampleVal = 0.0f;
            for (size_t k = 0; k < partials.size(); ++k)
            {
                if (currentAmps[k] > 0.00001f && currentFreqs[k] < sampleRate * 0.49f)
                {
                    sampleVal += currentAmps[k] * std::cos(phases[k]);

                    // Advance phase
                    phases[k] += 2.0f * float(M_PI) * currentFreqs[k] / sampleRate;
                    if (phases[k] > 2.0f * float(M_PI))
                        phases[k] -= 2.0f * float(M_PI);

                    // Decay amplitude
                    currentAmps[k] *= decayPerSample[k];

                    // Dynamic pitch glide
                    if (pitchSlope < -1.0f && currentFreqs[k] > 25.0f)
                    {
                        currentFreqs[k] *= pitchGlideRate;
                    }
                }
            }

            sampleVal *= env;
            outBuffer[n] = sampleVal;
            maxPeak = std::max(maxPeak, std::abs(sampleVal));
        }

        // Peak normalize to prevent clipping
        if (maxPeak > 1e-4f)
        {
            float normFactor = 0.95f / maxPeak;
            for (size_t n = 0; n < numSamples; ++n)
            {
                outBuffer[n] *= normFactor;
            }
        }
    }

    // Getters for inspection
    const std::vector<ModalPartial>& getPartials() const noexcept { return partials; }
    float getF0Hz() const noexcept { return f0Hz; }
    float getQ() const noexcept { return qualityFactorQ; }
    float getContactDurationMs() const noexcept { return contactDurationMs; }
    float getInharmonicityB() const noexcept { return inharmonicityB; }

private:
    void rebuildPartials()
    {
        partials.clear();

        const float baseTau = std::max(0.01f, qualityFactorQ / (float(M_PI) * std::max(20.0f, f0Hz)));

        if (resonatorType == PhysicalAcoustics::ResonatorType::CircularMembrane)
        {
            // Bessel membrane modal distribution
            const auto& t = PhysicalAcoustics::getMembraneTemplate();
            for (size_t i = 0; i < t.size(); ++i)
            {
                ModalPartial p;
                p.frequencyHz = f0Hz * t[i];
                // Bessel modes decay faster with higher radial wave numbers
                p.decayTimeSec = std::max(0.005f, baseTau / std::pow(t[i], 1.2f));
                p.initialAmplitude = 1.0f / (1.0f + static_cast<float>(i) * 0.7f);
                p.initialPhase = 0.0f;
                partials.push_back(p);
            }
        }
        else if (resonatorType == PhysicalAcoustics::ResonatorType::MetallicPlateBar)
        {
            // Rigid 2D plate / bar distribution
            const auto& t = PhysicalAcoustics::getPlateBarTemplate();
            for (size_t i = 0; i < t.size(); ++i)
            {
                ModalPartial p;
                p.frequencyHz = f0Hz * t[i];
                // Plates ring with high Q across upper modes
                p.decayTimeSec = std::max(0.02f, baseTau / std::sqrt(t[i]));
                p.initialAmplitude = 1.0f / (1.0f + static_cast<float>(i) * 0.4f);
                p.initialPhase = static_cast<float>(i) * 0.35f;
                partials.push_back(p);
            }
        }
        else
        {
            // Default 1D harmonic resonator with stiff-string dispersion B
            const int numHarmonics = 12;
            for (int n = 1; n <= numHarmonics; ++n)
            {
                ModalPartial p;
                float stretch = std::sqrt(1.0f + inharmonicityB * static_cast<float>(n * n));
                p.frequencyHz = static_cast<float>(n) * f0Hz * stretch;
                p.decayTimeSec = std::max(0.01f, baseTau / std::pow(static_cast<float>(n), 0.85f));
                p.initialAmplitude = 1.0f / static_cast<float>(n);
                p.initialPhase = 0.0f;
                partials.push_back(p);
            }
        }
    }

    float sampleRate = 44100.0f;
    float durationSec = 1.0f;
    float f0Hz = 130.81f;
    float contactDurationMs = 3.0f;
    PhysicalAcoustics::ResonatorType resonatorType = PhysicalAcoustics::ResonatorType::HarmonicStringPipe;
    PhysicalAcoustics::PhysicalMaterial material = PhysicalAcoustics::PhysicalMaterial::Wood;
    float inharmonicityB = 0.0f;
    float pitchSlope = 0.0f;
    float qualityFactorQ = 300.0f;

    std::vector<ModalPartial> partials;
};

} // namespace PhysicalSynthesizer
