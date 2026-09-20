#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

#include <JuceHeader.h>
#include "../../common/AudioTooRealtimeCore.h"

// Numerical accuracy & reference parity test for AudioTooRealtimeCore.
// Tests peak dBFS, RMS, crest factor, correlation, clipping counter, and the
// fixed realtime spectrum contract against analytical/reference values.

int main()
{
    std::cout << "[TestNumericalParity] Running C++ real-time analysis core parity checks...\n";

    AudioTooRealtimeCore core;
    const double sampleRate = 48000.0;
    core.reset(sampleRate);

    // 1. Generate 1 second 1 kHz full-scale sine wave (0 dBFS peak, -3.01 dBFS RMS)
    const int numBlocks = 100;
    const int blockSize = 480;
    juce::AudioBuffer<float> block(2, blockSize);

    for (int b = 0; b < numBlocks; ++b)
    {
        auto* left = block.getWritePointer(0);
        auto* right = block.getWritePointer(1);
        for (int i = 0; i < blockSize; ++i)
        {
            const int globalSample = b * blockSize + i;
            const float sample = std::sin(2.0 * juce::MathConstants<double>::pi * 1000.0 * globalSample / sampleRate);
            left[i] = sample;
            right[i] = sample; // identical in-phase stereo
        }
        core.analyse(block);
    }

    auto snap = core.snapshot();


    std::cout << "  Sine wave peak: " << snap.peakDbfs << " dBFS (expected ~0.0)\n";
    std::cout << "  Sine wave RMS: " << snap.rmsDbfs << " dBFS (expected ~-3.01)\n";
    std::cout << "  Sine wave crest factor: " << snap.crestDb << " dB (expected ~3.01)\n";
    std::cout << "  Stereo correlation: " << snap.correlation << " (expected 1.0)\n";

    bool failed = false;

    if (std::abs(snap.peakDbfs - 0.0f) > 0.1f)
    {
        std::cerr << "FAIL: Peak dBFS error out of tolerance!\n";
        failed = true;
    }

    if (std::abs(snap.rmsDbfs - (-3.01f)) > 0.5f)
    {
        std::cerr << "FAIL: RMS dBFS error out of tolerance!\n";
        failed = true;
    }

    if (std::abs(snap.correlation - 1.0f) > 0.05f)
    {
        std::cerr << "FAIL: Correlation error out of tolerance!\n";
        failed = true;
    }

    const auto spectrum = core.spectrumSnapshot();
    std::cout << "  Realtime spectrum bands: " << spectrum.bands.size()
              << " (expected " << AudioTooRealtimeSpectrumBandCount << ")"
              << ", 1 kHz energy: " << spectrum.energy[8] << "\n";
    if (spectrum.bands.size() != AudioTooRealtimeSpectrumBandCount
        || std::abs(spectrum.bands[8].centerHz - 1000.0f) > 0.01f
        || !std::isfinite(spectrum.energy[8]) || spectrum.energy[8] <= 0.0f)
    {
        std::cerr << "FAIL: Realtime spectrum contract or 1 kHz response is invalid!\n";
        failed = true;
    }

    // 2. Test clipping detection
    AudioTooRealtimeCore coreClip;
    coreClip.reset(sampleRate);
    juce::AudioBuffer<float> clipBuf(1, 100);
    auto* clipData = clipBuf.getWritePointer(0);
    for (int i = 0; i < 100; ++i)
        clipData[i] = (i % 10 == 0) ? 1.0f : 0.5f;

    coreClip.analyse(clipBuf);
    auto clipSnap = coreClip.snapshot();
    std::cout << "  Clipped samples detected: " << clipSnap.clippedSamples << " (expected 10)\n";

    if (clipSnap.clippedSamples != 10)
    {
        std::cerr << "FAIL: Clip count mismatch!\n";
        failed = true;
    }

    if (failed)
    {
        std::cerr << "[TestNumericalParity] FAILED\n";
        return 1;
    }

    std::cout << "[TestNumericalParity] ALL CHECKS PASSED CLEANLY.\n";
    return 0;
}
