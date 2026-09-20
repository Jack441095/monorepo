#pragma once

#include <JuceHeader.h>
#include <array>

struct AudioTooSpectrumBand
{
    float centerHz = 0.0f;
    float lowHz = 0.0f;
    float highHz = 0.0f;
};

constexpr size_t AudioTooRealtimeSpectrumBandCount = 13;

struct AudioTooSpectrumFrame
{
    std::array<AudioTooSpectrumBand, AudioTooRealtimeSpectrumBandCount> bands {};
    std::array<float, AudioTooRealtimeSpectrumBandCount> energy {};
};

// Reusable, allocation-free analysis core for Audio Too plug-ins. AI, I/O,
// and heavyweight analysis remain outside the audio thread.
struct AudioTooFeatureFrame
{
    float peakDbfs = -100.0f;
    float rmsDbfs = -100.0f;
    float correlation = 1.0f;
    float stereoWidth = 0.0f;
    float lowEnergy = 0.0f;
    float midEnergy = 0.0f;
    float highEnergy = 0.0f;
    float crestDb = 0.0f;
    float transientRatio = 0.0f;
    int clippedSamples = 0;
    double sampleRate = 0.0;
    juce::int64 analysedSamples = 0;
};

class AudioTooRealtimeCore
{
public:
    static constexpr size_t spectrumBandCount = AudioTooRealtimeSpectrumBandCount;

    void reset(double newSampleRate)
    {
        sampleRate.store(newSampleRate); peak.store(0.0f); energy.store(0.0); samples.store(0);
        correlation.store(1.0f); width.store(0.0f); low.store(0.0f); mid.store(0.0f); high.store(0.0f); transient.store(0.0f); clipped.store(0);
        lowState = midState = previousMono = 0.0f;
        spectrumLowStates.fill(0.0f);
        spectrumHighStates.fill(0.0f);
        for (auto& value : spectrumEnergy) value.store(0.0f);
    }

    void analyse(const juce::AudioBuffer<float>& buffer)
    {
        const auto count = buffer.getNumSamples();
        if (count <= 0 || buffer.getNumChannels() == 0) return;
        const auto* left = buffer.getReadPointer(0);
        const auto* right = buffer.getNumChannels() > 1 ? buffer.getReadPointer(1) : left;
        const auto rate = juce::jmax(1.0, sampleRate.load());
        const float lowAlpha = 1.0f - std::exp((float) (-2.0 * juce::MathConstants<double>::pi * 250.0 / rate));
        const float midAlpha = 1.0f - std::exp((float) (-2.0 * juce::MathConstants<double>::pi * 2500.0 / rate));
        std::array<float, spectrumBandCount> spectrumLowAlpha {};
        std::array<float, spectrumBandCount> spectrumHighAlpha {};
        for (size_t band = 0; band < spectrumBandCount; ++band)
        {
            const auto lowCutoff = spectrumBands[band].lowHz;
            const auto highCutoff = juce::jmin(spectrumBands[band].highHz, (float) (rate * 0.45));
            spectrumLowAlpha[band] = 1.0f - std::exp((float) (-2.0 * juce::MathConstants<double>::pi * lowCutoff / rate));
            spectrumHighAlpha[band] = 1.0f - std::exp((float) (-2.0 * juce::MathConstants<double>::pi * highCutoff / rate));
        }
        float blockPeak = 0.0f; double totalEnergy = 0.0, ll = 0.0, rr = 0.0, lr = 0.0, midSide = 0.0, side = 0.0;
        double lowE = 0.0, midE = 0.0, highE = 0.0, differenceEnergy = 0.0;
        std::array<double, spectrumBandCount> spectrumBlockEnergy {};
        int blockClipped = 0;
        for (int i = 0; i < count; ++i)
        {
            const float l = left[i], r = right[i], mono = 0.5f * (l + r);
            blockPeak = juce::jmax(blockPeak, std::abs(l), std::abs(r)); totalEnergy += 0.5 * ((double) l*l + (double) r*r);
            if (std::abs(l) >= 0.999f || std::abs(r) >= 0.999f) ++blockClipped;
            const float difference = mono - previousMono; differenceEnergy += difference * difference; previousMono = mono;
            ll += (double) l*l; rr += (double) r*r; lr += (double) l*r;
            const float lowPass = lowState += lowAlpha * (mono - lowState);
            const float midPass = midState += midAlpha * (mono - midState);
            const float middle = midPass - lowPass, highPass = mono - midPass;
            lowE += lowPass*lowPass; midE += middle*middle; highE += highPass*highPass;
            for (size_t band = 0; band < spectrumBandCount; ++band)
            {
                const float bandLowPass = spectrumLowStates[band] += spectrumLowAlpha[band] * (mono - spectrumLowStates[band]);
                const float bandHighPass = spectrumHighStates[band] += spectrumHighAlpha[band] * (mono - spectrumHighStates[band]);
                const float bandSignal = bandHighPass - bandLowPass;
                spectrumBlockEnergy[band] += (double) bandSignal * bandSignal;
            }
            const double m = 0.5 * (l + r), s = 0.5 * (l - r); midSide += m*m; side += s*s;
        }
        peak.store(juce::jmax(blockPeak, peak.load() * 0.995f));
        energy.store(0.9 * energy.load() + 0.1 * (totalEnergy / count));
        samples.store(samples.load() + count);
        const auto denominator = std::sqrt(ll * rr);
        const auto blockCorrelation = (float) (denominator > 1e-12 ? juce::jlimit(-1.0, 1.0, lr / denominator) : 1.0);
        const auto blockWidth = (float) (side / juce::jmax(1e-12, midSide + side));
        correlation.store(0.9f * correlation.load() + 0.1f * blockCorrelation);
        width.store(0.9f * width.load() + 0.1f * blockWidth);
        low.store(0.9f * low.load() + 0.1f * (float) (lowE / count));
        mid.store(0.9f * mid.load() + 0.1f * (float) (midE / count));
        high.store(0.9f * high.load() + 0.1f * (float) (highE / count));
        for (size_t band = 0; band < spectrumBandCount; ++band)
            spectrumEnergy[band].store(0.9f * spectrumEnergy[band].load() + 0.1f * (float) (spectrumBlockEnergy[band] / count));
        const auto blockRms = std::sqrt(totalEnergy / count);
        transient.store(0.9f * transient.load() + 0.1f * (float) (std::sqrt(differenceEnergy / count) / juce::jmax(1e-12, blockRms)));
        clipped.store(blockClipped);
    }

    AudioTooFeatureFrame snapshot() const
    {
        const auto n = samples.load(); const auto rms = n > 0 ? std::sqrt(energy.load()) : 0.0;
        const auto peakDb = juce::Decibels::gainToDecibels(peak.load(), -100.0f);
        const auto rmsDb = juce::Decibels::gainToDecibels((float) rms, -100.0f);
        return { peakDb, rmsDb, correlation.load(), width.load(), low.load(), mid.load(), high.load(), juce::jmax(0.0f, peakDb - rmsDb), transient.load(), clipped.load(), sampleRate.load(), n };
    }

    AudioTooSpectrumFrame spectrumSnapshot() const
    {
        AudioTooSpectrumFrame result;
        for (size_t band = 0; band < spectrumBandCount; ++band)
        {
            result.bands[band] = spectrumBands[band];
            result.energy[band] = spectrumEnergy[band].load();
        }
        return result;
    }

private:
    inline static constexpr std::array<AudioTooSpectrumBand, spectrumBandCount> spectrumBands {{
        { 31.5f, 28.1f, 35.4f }, { 63.0f, 56.1f, 70.7f }, { 125.0f, 111.4f, 140.3f },
        { 250.0f, 222.7f, 280.6f }, { 315.0f, 280.6f, 353.6f }, { 400.0f, 353.6f, 445.4f },
        { 500.0f, 445.4f, 561.2f }, { 630.0f, 561.2f, 707.1f }, { 1000.0f, 891.0f, 1122.5f },
        { 2000.0f, 1782.0f, 2245.0f }, { 4000.0f, 3564.0f, 4489.0f }, { 8000.0f, 7127.0f, 8979.0f },
        { 16000.0f, 14254.0f, 17959.0f },
    }};
    std::atomic<float> peak { 0 }, correlation { 1 }, width { 0 }, low { 0 }, mid { 0 }, high { 0 }, transient { 0 };
    std::atomic<double> energy { 0 }, sampleRate { 0 }; std::atomic<juce::int64> samples { 0 }; std::atomic<int> clipped { 0 };
    float lowState = 0.0f, midState = 0.0f, previousMono = 0.0f;
    std::array<float, spectrumBandCount> spectrumLowStates {};
    std::array<float, spectrumBandCount> spectrumHighStates {};
    std::array<std::atomic<float>, spectrumBandCount> spectrumEnergy {};
};
