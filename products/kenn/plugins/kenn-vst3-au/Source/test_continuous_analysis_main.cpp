#include "ContinuousAnalysis.h"
#include "PluginProcessor.h"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>

static thread_local bool watchCallback = false;
static thread_local size_t callbackAllocations = 0;
void* operator new(size_t bytes)
{
    if (watchCallback) ++callbackAllocations;
    if (auto* memory = std::malloc(juce::jmax(size_t(1), bytes))) return memory;
    throw std::bad_alloc(); // Keep OOM visible; the allocation guard cannot hide it.
}
void* operator new[](size_t bytes) { return ::operator new(bytes); }
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete[](void* memory) noexcept { std::free(memory); }

static int checks = 0, failures = 0;
static void require(bool condition, const char* behavior)
{
    ++checks;
    if (! condition) { ++failures; std::cerr << "FAIL: " << behavior << '\n'; }
}

class SyntheticPlayHead final : public juce::AudioPlayHead
{
public:
    juce::Optional<PositionInfo> getPosition() const override
    {
        if (missing) return {}; // Hosts may omit the entire transport packet.
        PositionInfo info; info.setTimeInSamples(firstSample); info.setIsPlaying(playing);
        return info;
    }
    juce::int64 firstSample = 0;
    bool playing = true, missing = false;
};

template<size_t Size>
static void verifyFFTAgainstTimeDomainPower()
{
    KENNCachedSpectrum<Size> fft; fft.prepare(48000.0);
    double weightedPower = 0.0, windowPower = 0.0;
    constexpr int bin = 7; // An integer-bin sinusoid makes the peak-frequency expectation exact.
    for (size_t sample = 0; sample < Size; ++sample)
    {
        const double phase = 2.0 * juce::MathConstants<double>::pi * static_cast<double>(sample) / Size;
        const auto value = static_cast<float>(0.5 * std::sin(bin * phase) + 0.125);
        const auto hann = 0.5 - 0.5 * std::cos(phase);
        weightedPower += value * value * hann * hann; windowPower += hann * hann;
        fft.push(value, -value);
    }
    const auto frame = fft.measure(48000.0, Size);
    require(frame.valid && frame.endSample-frame.firstSample == Size, "Completed FFT retains its own exact sample interval");
    require(std::abs(frame.meanSquare-weightedPower/windowPower) < 1e-7, "FFT Parseval power matches an independent Hann-weighted time-domain calculation including DC");
    require(std::abs(frame.peakHz-bin*48000.0/Size) < 1e-8, "FFT peak frequency reports discrete bin resolution");
    fft.reset(); fft.push(0.5f, 0.5f);
    require(! fft.measure(48000.0, Size+1).valid, "A reset cannot reuse a pre-gap spectrum during warm-up");
}

static KENNAnalysisSnapshot hostWindow(int start, int end, int block)
{
    KENNContinuousAnalysis analyser; analyser.prepare(48000.0, false);
    for (int first = start; first < end; first += block)
    {
        juce::AudioBuffer<float> audio(2, juce::jmin(block, end-first));
        for (int sample = 0; sample < audio.getNumSamples(); ++sample)
        {
            const auto value = static_cast<float>(0.5 * std::sin(2.0 * juce::MathConstants<double>::pi * 60.0 * (first+sample)/48000.0));
            audio.setSample(0, sample, value); audio.setSample(1, sample, -value);
        }
        analyser.push(audio, true, { first, true }); analyser.drainPending();
    }
    return analyser.snapshot();
}

static KENNAnalysisSnapshot sineWindow(double rate, int blockSize, bool inverted = false)
{
    KENNContinuousAnalysis analyser;
    analyser.prepare(rate, false);
    for (int first = 0; first < static_cast<int>(rate); first += blockSize)
    {
        juce::AudioBuffer<float> audio(2, juce::jmin(blockSize, static_cast<int>(rate)-first));
        for (int sample = 0; sample < audio.getNumSamples(); ++sample)
        {
            const auto value = static_cast<float>(0.5 * std::sin(2.0 * juce::MathConstants<double>::pi * 1000.0 * (first+sample)/rate));
            audio.setSample(0, sample, value); audio.setSample(1, sample, inverted ? -value : value);
        }
        watchCallback = true;
        analyser.push(audio, true);
        watchCallback = false;
        analyser.drainPending();
    }
    return analyser.snapshot();
}

static void pushConstant(KENNContinuousAnalysis& analyser, int channels, int samples, float left, float right = 0.0f)
{
    juce::AudioBuffer<float> audio(channels, samples);
    for (int channel = 0; channel < channels; ++channel)
        juce::FloatVectorOperations::fill(audio.getWritePointer(channel), channel == 0 ? left : right, samples);
    watchCallback = true; analyser.push(audio, true); watchCallback = false;
}

static void verifyCorrelationUsesActualInputLayout()
{
    // A duplicated mono buffer and silent-channel fallback used to look like
    // measured +1 stereo correlation once the input layout had been discarded.
    KENNContinuousAnalysis analyser;
    analyser.prepare(48000.0, false);
    require(analyser.snapshot().inputChannels == 0 && ! analyser.snapshot().correlationValid,
        "Unpublished audio has neither an invented input layout nor phase evidence");
    struct Example { int channels; float left, right, expected; bool correlationValid; };
    for (const auto& example : {
        Example { 1, 0.5f, 0.0f, 1.0f, false },
        Example { 1, 0.0f, 0.0f, 1.0f, false },
        Example { 2, 0.5f, 0.5f, 1.0f, true },
        Example { 2, 0.5f, -0.5f, -1.0f, true },
        Example { 2, 0.5f, 0.0f, 1.0f, false },
        Example { 2, 0.0f, 0.5f, 1.0f, false },
        Example { 2, 0.0f, 0.0f, 1.0f, false },
        Example { 2, 1e-9f, -1e-9f, 1.0f, false }, // Accumulated channel energy remains below the existing 1e-12 floor.
        Example { 2, 1e-7f, -1e-7f, -1.0f, true } })
    {
        analyser.prepare(48000.0, false);
        pushConstant(analyser, example.channels, 4800, example.left, example.right); analyser.drainPending();
        const auto frame = analyser.snapshot();
        require(frame.valid && frame.inputChannels == example.channels && frame.correlationValid == example.correlationValid,
            "Each complete window retains its actual input layout and defined-energy correlation validity");
        require(std::abs(frame.features.correlation-example.expected) < 1e-6f,
            "Adding correlation validity preserves the measured number and legacy +1 fallback");
        require(! frame.streamingMeter.momentaryReady && ! frame.streamingMeter.truePeakReady,
            "Input metadata does not enable the unqualified streaming meter candidate");
        for (const auto& captured : analyser.recentSnapshots())
            if (captured.valid)
                require(captured.inputChannels == frame.inputChannels && captured.correlationValid == frame.correlationValid,
                    "Retained feature history carries the owning window's channel and phase metadata");
    }

    analyser.prepare(48000.0, false);
    pushConstant(analyser, 2, 4800, 0.5f, -0.5f); analyser.drainPending();
    const auto stereo = analyser.snapshot();
    pushConstant(analyser, 1, 2400, 0.5f);
    require(! analyser.snapshot().valid && ! analyser.snapshot().correlationValid,
        "A stereo-to-mono change retires earlier phase evidence before the worker drains");
    for (const auto& captured : analyser.recentSnapshots())
        require(! captured.valid && ! captured.correlationValid, "A layout change immediately retires every retained window");
    analyser.drainPending();
    require(! analyser.snapshot().valid, "Half a mono window cannot reuse the earlier stereo half");
    pushConstant(analyser, 1, 2400, 0.5f); analyser.drainPending();
    auto mono = analyser.snapshot();
    require(mono.valid && mono.inputChannels == 1 && ! mono.correlationValid && mono.generation > stereo.generation
        && mono.firstSample == 4800 && mono.endSample == 9600,
        "A complete mono window recovers with new source provenance and no stereo grade evidence");
    require(! mono.lowSpectrum.valid, "A layout change also retires cached long spectra until fresh warm-up");

    analyser.prepare(48000.0, false);
    pushConstant(analyser, 2, 2400, 0.5f, -0.5f);
    pushConstant(analyser, 1, 2400, 0.5f); analyser.drainPending();
    require(! analyser.snapshot().valid, "Queued old-layout packets cannot complete a mixed-layout window");
    pushConstant(analyser, 1, 2400, 0.5f); analyser.drainPending();
    mono = analyser.snapshot();
    require(mono.valid && mono.inputChannels == 1 && ! mono.correlationValid
        && mono.firstSample == 2400 && mono.endSample == 7200,
        "Only the new layout contributes after old queued packets are discarded");
    pushConstant(analyser, 2, 2400, 0.5f, -0.5f); analyser.drainPending();
    require(! analyser.snapshot().valid, "A mono-to-stereo change waits for a whole new stereo window");
    pushConstant(analyser, 2, 2400, 0.5f, -0.5f); analyser.drainPending();
    require(analyser.snapshot().valid && analyser.snapshot().inputChannels == 2 && analyser.snapshot().correlationValid
        && analyser.snapshot().features.correlation < -0.999f,
        "Stereo correlation recovers after a full new-layout window");
    for (const auto& captured : analyser.recentSnapshots())
        if (captured.valid)
            require(captured.inputChannels == 2 && captured.correlationValid && captured.generation == analyser.snapshot().generation,
                "Recovered stereo history contains no earlier mono windows");

    KENNContinuousAnalysis other; other.prepare(48000.0, false);
    pushConstant(other, 1, 4800, 0.5f); other.drainPending();
    const auto independent = analyser.snapshot();
    other.invalidate();
    require(! other.snapshot().valid && ! other.snapshot().correlationValid
        && analyser.snapshot().valid && analyser.snapshot().correlationValid
        && analyser.snapshot().generation == independent.generation,
        "Source reset and channel validity remain isolated between inserts");
    analyser.release();
    require(! analyser.snapshot().correlationValid, "Released input cannot retain phase evidence");
    analyser.prepare(48000.0, false);
    require(analyser.snapshot().inputChannels == 0 && ! analyser.snapshot().correlationValid,
        "Prepare clears the former input layout before new audio arrives");
}

int main()
{
    verifyCorrelationUsesActualInputLayout();
    verifyFFTAgainstTimeDomainPower<2048>(); verifyFFTAgainstTimeDomainPower<8192>();
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
    {
        const auto reference = sineWindow(rate, 64);
        for (const int block : { 32, 128, 257, 512, 2048 })
        {
            const auto frame = sineWindow(rate, block);
            require(frame.valid && frame.sequence == 10 && frame.endSample == static_cast<juce::int64>(rate), "Exactly ten contiguous 100 ms windows independent of block size");
            require(frame.inputChannels == 2 && frame.correlationValid, "Positive stereo remains defined across rates and buffer partitions");
            require(std::abs(frame.features.rmsDbfs + 9.0309f) < 0.001f && std::abs(frame.features.crestDb-3.0103f) < 0.001f, "Sine RMS and crest use the same exact window");
            require(std::abs(frame.features.transientRatio-reference.features.transientRatio) < 1e-6f, "Envelope time constants do not depend on host blocks");
            for (size_t band = 0; band < AudioTooRealtimeSpectrumBandCount; ++band)
                require(std::abs(frame.spectrum.energy[band]-reference.spectrum.energy[band]) < 1e-7f, "Spectrum is invariant under buffer partitioning");
            require(frame.fastSpectrum.valid && frame.lowSpectrum.valid, "Both FFT sizes finish warm-up on a continuous passage");
            require(std::abs(frame.fastSpectrum.meanSquare-0.125) < 1e-6 && std::abs(frame.lowSpectrum.meanSquare-0.125) < 1e-6, "Stereo sine FFT power matches analytic RMS squared");
            for (size_t band = 0; band < KENNFFTBandCount; ++band)
                require(std::abs(frame.lowSpectrum.energy[band]-reference.lowSpectrum.energy[band]) < 1e-8, "Cached FFT power is independent of host buffer partitioning");
        }
        const auto inverted = sineWindow(rate, 128, true);
        require(inverted.inputChannels == 2 && inverted.correlationValid, "Negative stereo remains defined at every supported test rate");
        require(inverted.features.correlation < -0.999f && inverted.features.stereoWidth > 0.999f, "Opposite-phase stereo reports phase risk");
        require(inverted.spectrum.energy[8] > 0.001f, "Opposite-phase stereo retains measured channel spectral energy");
    }

    KENNContinuousAnalysis analyser;
    analyser.prepare(48000.0, false);
    juce::AudioBuffer<float> audio(1, 4800); audio.clear();
    analyser.push(audio, true); analyser.drainPending();
    auto frame = analyser.snapshot();
    require(frame.valid && frame.features.rmsDbfs <= -99.9f && frame.features.clippedSamples == 0, "Mono silence produces a finite window without false clipping");
    for (int sample = 0; sample < 4800; ++sample) audio.setSample(0, sample, 1.0f);
    analyser.push(audio, true); analyser.drainPending();
    require(analyser.snapshot().features.clippedSamples == 4800, "Clipping counts sample frames across an entire window");

    // A stopped consumer must never stall the producer or silently join audio
    // across the rejected block. A complete later window must recover.
    for (int block = 0; block < 5; ++block) analyser.push(audio, true);
    require(! analyser.snapshot().valid, "Queue overflow retires previously published evidence immediately");
    analyser.drainPending();
    analyser.push(audio, true); analyser.drainPending();
    frame = analyser.snapshot();
    require(frame.valid && frame.droppedSamples == 9600 && frame.endSample-frame.firstSample == 4800, "Overflow recovery requires a full contiguous window with visible drop counts");
    analyser.invalidate();
    require(! analyser.snapshot().valid, "Rename/source generation invalidates current evidence");
    analyser.push(audio, true); analyser.invalidate(); analyser.drainPending();
    require(! analyser.snapshot().valid, "Queued audio from an old source cannot restore freshness");
    analyser.push(audio, true); analyser.drainPending();
    require(analyser.snapshot().valid, "New source recovers after one full window");
    analyser.push(audio, false);
    require(! analyser.snapshot().valid, "Disabling analysis retires old evidence without waiting for the worker");
    audio.setSample(0, 2500, std::numeric_limits<float>::quiet_NaN());
    analyser.push(audio, true); analyser.drainPending();
    require(! analyser.snapshot().valid, "Invalid samples break a window rather than becoming fabricated silence");
    audio.clear(); analyser.push(audio, true); analyser.drainPending();
    require(analyser.snapshot().valid && analyser.snapshot().invalidSamples == 1, "Invalid input recovers with counted discontinuity");

    const auto aligned = hostWindow(0, 24000, 257), late = hostWindow(97, 24000, 512);
    require(aligned.hostTimelineValid && late.hostTimelineValid && aligned.hostFirstSample == late.hostFirstSample && aligned.hostEndSample == late.hostEndSample, "Inserts starting on different callbacks align on the host sample grid");
    require(aligned.firstSample != late.firstSample && aligned.lowSpectrum.endSample != late.lowSpectrum.endSample, "Different insert-local counters are never treated as a shared clock");
    for (size_t band = 0; band < KENNFFTBandCount; ++band)
        require(std::abs(aligned.lowSpectrum.energy[band]-late.lowSpectrum.energy[band]) < 1e-8, "Aligned long spectra cover identical host samples despite different insert start times");
    const auto preroll = hostWindow(-4800, 0, 128);
    require(preroll.hostTimelineValid && preroll.hostFirstSample == -4800 && preroll.hostEndSample == 0, "Negative host preroll samples remain signed timing evidence");
    analyser.prepare(48000.0, false); audio.clear();
    analyser.push(audio, true, { 0, true }); analyser.drainPending();
    const auto generation = analyser.snapshot().generation, epoch = analyser.snapshot().transportEpoch;
    analyser.push(audio, true, { 0, true }); // Looping to the same samples retires the earlier passage immediately.
    require(! analyser.snapshot().valid, "Loop/seek invalidates published evidence before the worker drains");
    analyser.drainPending(); frame = analyser.snapshot();
    require(frame.valid && frame.generation == generation && frame.transportEpoch > epoch && ! frame.lowSpectrum.valid, "Transport discontinuities reset FFT history without changing track identity");
    analyser.push(audio, true); require(! analyser.snapshot().valid, "Loss of host timing retires the aligned window");
    analyser.drainPending(); require(analyser.snapshot().valid && ! analyser.snapshot().hostTimelineValid, "Missing host timing preserves individual analysis with unknown alignment");

    // The production processor, not only its queue helper, must remain a
    // zero-allocation, zero-latency pass-through with no editor constructed.
    KENNMixAssistantAudioProcessor processor;
    processor.prepareToPlay(48000.0, 4800);
    SyntheticPlayHead playHead; processor.setPlayHead(&playHead);
    juce::MidiBuffer midi;
    audio.setSample(0, 123, 0.37f);
    const auto original = audio.getSample(0, 123);
    watchCallback = true; processor.processBlock(audio, midi); watchCallback = false;
    require(callbackAllocations == 0, "Prepared callback performs no C++ heap allocations");
    require(std::abs(audio.getSample(0, 123)-original) < 1e-7f && processor.getLatencySamples() == 0, "Production callback preserves samples and declares zero latency");
    for (int attempt = 0; attempt < 200 && ! processor.analysisSnapshot().valid; ++attempt) juce::Thread::sleep(2); // At most 400 ms to observe the shared worker.
    require(processor.analysisSnapshot().valid, "Shared worker publishes with the editor closed");
    require(processor.analysisSnapshot().inputChannels == 1 && ! processor.analysisSnapshot().correlationValid,
        "The actual production callback retains mono attribution without inventing stereo phase evidence");
    require(processor.analysisSnapshot().hostTimelineValid, "Production callback obtains playing host sample time without allocation");
    playHead.playing = false;
    watchCallback = true; processor.processBlock(audio, midi); watchCallback = false;
    require(callbackAllocations == 0, "Stopped transport position handling does not allocate");
    for (int attempt = 0; attempt < 200 && ! processor.analysisSnapshot().valid; ++attempt) juce::Thread::sleep(2);
    require(! processor.analysisSnapshot().hostTimelineValid, "Stopped transports cannot manufacture paired alignment");
    require(processor.localDiagnosticSummary().contains("100 ms window"), "Local diagnosis uses the same coherent continuous window");
    processor.releaseResources();
    require(processor.localDiagnosticSummary().contains("No current complete audio window"), "Released input cannot remain current in local advice");

    KENNContinuousAnalysis other;
    other.prepare(48000.0, false);
    require(other.snapshot().sequence == 0 && ! other.snapshot().valid, "A second insert cannot inherit another insert's publication");
    std::cout << "Continuous analysis: " << checks << " checks, " << failures << " failures; queue storage " << KENNContinuousAnalysis::queueStorageBytes()
        << " bytes per insert; snapshot " << sizeof(KENNAnalysisSnapshot) << " bytes; analyser " << sizeof(KENNContinuousAnalysis) << " bytes\n";
    return failures == 0 ? 0 : 1;
}
