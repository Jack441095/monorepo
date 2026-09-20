#pragma once

#include <JuceHeader.h>
#include "../../common/AudioTooRealtimeCore.h"

// This analyser is deliberately allocation-free in processBlock.  Values are
// published atomically for the editor and handoff exporter; it never sends
// network traffic from the audio thread.
struct KENNMeterSnapshot
{
    float peakDb = -100.0f;
    float rmsDb = -100.0f;
    float correlation = 1.0f;
    float stereoWidth = 0.0f;
    float crestDb = 0.0f;
    float transientRatio = 0.0f;
    int clippedSamples = 0;
    double sampleRate = 0.0;
    juce::int64 analysedSamples = 0;
};

class KENNMeterAnalyzer
{
public:
    void reset(double newSampleRate)
    {
        sampleRate.store(newSampleRate);
        peak.store(0.0f); energySum.store(0.0); sampleCount.store(0);
        correlation.store(1.0f); width.store(0.0f);
    }

    void analyse(const juce::AudioBuffer<float>& buffer)
    {
        const auto samples = buffer.getNumSamples();
        if (samples <= 0 || buffer.getNumChannels() == 0) return;

        const auto* left = buffer.getReadPointer(0);
        const auto* right = buffer.getNumChannels() > 1 ? buffer.getReadPointer(1) : left;
        float blockPeak = 0.0f;
        double blockEnergy = 0.0, ll = 0.0, rr = 0.0, lr = 0.0, mid = 0.0, side = 0.0;
        for (int i = 0; i < samples; ++i)
        {
            const float l = left[i], r = right[i];
            blockPeak = juce::jmax(blockPeak, std::abs(l), std::abs(r));
            blockEnergy += 0.5 * ((double) l * l + (double) r * r);
            ll += (double) l * l; rr += (double) r * r; lr += (double) l * r;
            const double m = 0.5 * (l + r), s = 0.5 * (l - r);
            mid += m * m; side += s * s;
        }
        peak.store(juce::jmax(peak.load(), blockPeak));
        energySum.store(energySum.load() + blockEnergy);
        sampleCount.store(sampleCount.load() + samples);
        const double denominator = std::sqrt(ll * rr);
        correlation.store((float) (denominator > 1.0e-12 ? juce::jlimit(-1.0, 1.0, lr / denominator) : 1.0));
        width.store((float) (side / juce::jmax(1.0e-12, mid + side)));
    }

    KENNMeterSnapshot snapshot() const
    {
        const auto n = sampleCount.load();
        const auto rms = n > 0 ? std::sqrt(energySum.load() / (double) n) : 0.0;
        return { juce::Decibels::gainToDecibels(peak.load(), -100.0f),
                 juce::Decibels::gainToDecibels((float) rms, -100.0f), correlation.load(), width.load(),
                 0.0f, 0.0f, 0, sampleRate.load(), n };
    }

private:
    std::atomic<float> peak { 0.0f }, correlation { 1.0f }, width { 0.0f };
    std::atomic<double> energySum { 0.0 }, sampleRate { 0.0 };
    std::atomic<juce::int64> sampleCount { 0 };
};
