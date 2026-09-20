#pragma once

#include <JuceHeader.h>

// Reusable, allocation-free analysis core for Audio Too plug-ins.  This is
// intentionally limited to inexpensive feature extraction; AI, I/O and
// heavyweight analysis must remain off the audio thread.
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
    void reset(double newSampleRate)
    {
        sampleRate.store(newSampleRate); peak.store(0.0f); energy.store(0.0); samples.store(0);
        correlation.store(1.0f); width.store(0.0f); low.store(0.0f); mid.store(0.0f); high.store(0.0f); transient.store(0.0f); clipped.store(0);
        lowState = midState = previousMono = 0.0f;
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
        float blockPeak = 0.0f; double totalEnergy = 0.0, ll = 0.0, rr = 0.0, lr = 0.0, midSide = 0.0, side = 0.0;
        double lowE = 0.0, midE = 0.0, highE = 0.0, differenceEnergy = 0.0;
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
            const double m = 0.5 * (l + r), s = 0.5 * (l - r); midSide += m*m; side += s*s;
        }
        // Decaying metrics describe recent program material rather than the
        // entire lifetime of the plug-in instance.  This keeps handoffs and
        // the editor truthful after a loud section has passed.
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
private:
    std::atomic<float> peak { 0 }, correlation { 1 }, width { 0 }, low { 0 }, mid { 0 }, high { 0 }, transient { 0 };
    std::atomic<double> energy { 0 }, sampleRate { 0 }; std::atomic<juce::int64> samples { 0 }; std::atomic<int> clipped { 0 };
    float lowState = 0.0f, midState = 0.0f, previousMono = 0.0f;
};
