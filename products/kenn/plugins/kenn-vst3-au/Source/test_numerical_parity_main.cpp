#include <cmath>
#include <cstdlib>
#include <iostream>
#include <new>
#include <vector>

#include <JuceHeader.h>
#include "../../../packages/common/AudioTooRealtimeCore.h"

// Count heap use only while analysing a prepared block. Fixture construction
// and JUCE startup legitimately allocate outside the audio callback.
static thread_local bool watchAudioAllocations = false;
static thread_local size_t audioAllocations = 0;

void* operator new(size_t bytes)
{
    if (watchAudioAllocations) ++audioAllocations;
    // Standard new(0) still returns storage; reserve 1 byte rather than depend on malloc(0).
    if (auto* memory = std::malloc(bytes == 0 ? 1 : bytes)) return memory;
    // Preserve standard new's failure contract so the guard cannot hide OOM.
    throw std::bad_alloc();
}

void* operator new[](size_t bytes) { return ::operator new(bytes); }
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete[](void* memory) noexcept { std::free(memory); }

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
        watchAudioAllocations = true;
        core.analyse(block);
        watchAudioAllocations = false;
    }

    auto snap = core.snapshot();


    std::cout << "  Sine wave peak: " << snap.peakDbfs << " dBFS (expected ~0.0)\n";
    std::cout << "  Sine wave RMS: " << snap.rmsDbfs << " dBFS (expected ~-3.01)\n";
    std::cout << "  Sine wave crest factor: " << snap.crestDb << " dB (expected ~3.01)\n";
    std::cout << "  Stereo correlation: " << snap.correlation << " (expected 1.0)\n";

    bool failed = false;
    // A 0.5 dB tolerance covers the existing RMS smoother's one-second settling,
    // while still rejecting a changed sine crest factor or lost sample frames.
    if (audioAllocations != 0 || snap.analysedSamples != numBlocks * blockSize
        || std::abs(snap.crestDb - 3.01f) > 0.5f)
    {
        std::cerr << "FAIL: callback allocated, lost sample frames, or changed sine crest factor.\n";
        failed = true;
    }

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

    // Near-full-scale is the core's 0.999 amplitude threshold, not proof of
    // distortion. A 0.998 sample must not count and a 0.999 sample must count.
    clipBuf.clear();
    clipData[0] = 0.998f;
    clipData[1] = -0.999f;
    coreClip.analyse(clipBuf);
    if (coreClip.snapshot().clippedSamples != 1)
    {
        std::cerr << "FAIL: near-full-scale threshold changed.\n";
        failed = true;
    }

    AudioTooRealtimeCore antiPhase;
    antiPhase.reset(sampleRate);
    for (int i = 0; i < blockSize; ++i)
        block.setSample(1, i, -block.getSample(0, i));
    for (int b = 0; b < numBlocks; ++b) antiPhase.analyse(block);
    const auto anti = antiPhase.snapshot();
    // Opposite-phase stereo retains channel energy but cancels in the mono
    // spectrum. The 0.99 dimensionless bounds allow float rounding near ±1;
    // RMS keeps the same 0.5 dB settling tolerance as the in-phase sine.
    if (anti.correlation > -0.99f || anti.stereoWidth < 0.99f
        || std::abs(anti.rmsDbfs + 3.01f) > 0.5f
        || std::fpclassify(antiPhase.spectrumSnapshot().energy[8]) != FP_ZERO)
    {
        std::cerr << "FAIL: anti-phase energy, correlation, or mono cancellation changed.\n";
        failed = true;
    }

    AudioTooRealtimeCore silent;
    silent.reset(sampleRate);
    block.clear();
    silent.analyse(block);
    juce::AudioBuffer<float> empty;
    silent.analyse(empty);
    const auto silence = silent.snapshot();
    // -100 dBFS is the display floor; 0.00001 dB allows float roundoff there.
    // An empty block contributes no sample frames.
    if (std::abs(silence.peakDbfs + 100.0f) > 0.00001f
        || std::abs(silence.rmsDbfs + 100.0f) > 0.00001f
        || silence.analysedSamples != blockSize || silence.clippedSamples != 0)
    {
        std::cerr << "FAIL: silence or empty-block bounds changed.\n";
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
