#include "ContinuousAnalysis.h"
#include <vector>

// Sharing one low-priority worker avoids one polling thread per insert. The
// registry lock protects lifetime/prepare only; the audio producer bypasses it.
class KENNAnalysisWorker final : public juce::Thread
{
public:
    static KENNAnalysisWorker& instance() { static KENNAnalysisWorker worker; return worker; }
    void add(KENNContinuousAnalysis& analyser)
    {
        const juce::ScopedLock lock(registryLock);
        instances.push_back(&analyser);
    }
    void remove(KENNContinuousAnalysis& analyser)
    {
        const juce::ScopedLock lock(registryLock);
        instances.erase(std::remove(instances.begin(), instances.end(), &analyser), instances.end());
    }
    void run() override
    {
        while (! threadShouldExit())
        {
            {
                const juce::ScopedLock lock(registryLock);
                for (auto* analyser : instances) analyser->drainPending();
            }
            wait(2); // 2 ms polling avoids a callback-side condition-variable wake-up.
        }
    }
private:
    KENNAnalysisWorker() : juce::Thread("KENN insert analysis") { startThread(juce::Thread::Priority::low); }
    ~KENNAnalysisWorker() override { stopThread(-1); } // Never destroy storage while the reader can use it.
    juce::CriticalSection registryLock;
    std::vector<KENNContinuousAnalysis*> instances;
};

KENNContinuousAnalysis::~KENNContinuousAnalysis() { release(); }

void KENNContinuousAnalysis::release()
{
    if (registered)
    {
        KENNAnalysisWorker::instance().remove(*this);
        registered = false;
    }
    invalidate(); // A released stream cannot retain a current diagnostic window.
}

void KENNContinuousAnalysis::prepare(double sampleRate, bool startWorker, bool enableStreamingCandidate)
{
    release();
    rate = juce::jmax(1.0, sampleRate);
    windowSamples = juce::jmax(1, static_cast<int>(std::round(rate * windowSeconds)));
    ticksPerSample = static_cast<double>(juce::Time::getHighResolutionTicksPerSecond()) / rate;
    fifo.reset(); producerSamples = analysedSamples = 0; sequence = 0;
    dropped.store(0); invalid.store(0); previouslyEnabled = true; producerInputChannels = 0;
    workerMilliseconds.store(0.0);
    workerGeneration = sourceGeneration.load(); workerDropped = 0; expectedSample = -1;
    workerTransportEpoch = transportEpoch.fetch_add(1) + 1;
    producerHostValid = false; producerExpectedHost = 0;
    fastFFT.prepare(rate); lowFFT.prepare(rate);
    streamingCandidateEnabled = enableStreamingCandidate && streamingMeter.prepare(rate);
    streamingMeter.reset();
    AudioTooRealtimeCore bandDefinitions;
    spectrum = bandDefinitions.spectrumSnapshot();
    for (size_t band = 0; band < AudioTooRealtimeSpectrumBandCount; ++band)
    {
        const auto& bounds = spectrum.bands[band];
        const auto coefficient = [this](double hz) {
            return static_cast<float>(1.0 - std::exp(-2.0 * juce::MathConstants<double>::pi * juce::jmin(hz, rate * 0.45) / rate));
        };
        lowAlpha[band] = coefficient(bounds.lowHz); highAlpha[band] = coefficient(bounds.highHz);
    }
    const auto envelopeCoefficient = [this](double seconds) { return 1.0 - std::exp(-1.0 / (rate * seconds)); };
    fastAttack = envelopeCoefficient(0.001); fastRelease = envelopeCoefficient(0.015); // 1/15 ms fast envelope.
    slowAttack = envelopeCoefficient(0.050); slowRelease = envelopeCoefficient(0.100); // 50/100 ms sustain envelope.
    resetWindow(true);
    {
        const juce::ScopedLock lock(publicationLock);
        published = {}; published.features.sampleRate = rate;
        recent = {};
    }
    if (startWorker)
    {
        KENNAnalysisWorker::instance().add(*this);
        registered = true;
    }
}

void KENNContinuousAnalysis::push(const juce::AudioBuffer<float>& buffer, bool enabled, KENNHostPosition host) noexcept
{
    static_assert(std::atomic<uint64_t>::is_always_lock_free, "Audio counters must not use hidden locks");
    if (! enabled)
    {
        // Disabling analysis retires queued audio once, without racing a FIFO reset.
        if (previouslyEnabled) invalidate();
        previouslyEnabled = false;
        return;
    }
    previouslyEnabled = true;
    const int samples = buffer.getNumSamples();
    if (samples <= 0 || buffer.getNumChannels() == 0)
        return; // Empty host callbacks neither fabricate progress nor change playback.
    const int inputChannels = juce::jmin(2, buffer.getNumChannels());
    if (producerInputChannels != 0 && inputChannels != producerInputChannels)
        invalidate(); // Retire queued/published stereo evidence before a new layout can complete a window.
    producerInputChannels = inputChannels;
    if (host.valid != producerHostValid || (host.valid && host.firstSample != producerExpectedHost))
        transportEpoch.fetch_add(1); // Seek/loop/clock loss retires evidence, without expiring the track binding.
    producerHostValid = host.valid;
    producerExpectedHost = host.firstSample + samples;
    const auto first = producerSamples;
    producerSamples += samples;
    const auto needed = (samples - 1) / packetSamples + 1;
    if (needed > fifo.getFreeSpace())
    {
        // Drop the entire block: partial enqueue would conceal a discontinuity.
        dropped.fetch_add(static_cast<uint64_t>(samples));
        return;
    }
    int start1, size1, start2, size2;
    fifo.prepareToWrite(needed, start1, size1, start2, size2);
    const auto* left = buffer.getReadPointer(0);
    const auto* right = buffer.getNumChannels() > 1 ? buffer.getReadPointer(1) : left;
    const auto ticks = juce::Time::getHighResolutionTicks();
    const auto generation = sourceGeneration.load();
    const auto epoch = transportEpoch.load();
    const auto lost = dropped.load();
    int offset = 0;
    for (int index = 0; index < needed; ++index)
    {
        auto& packet = packets[static_cast<size_t>(index < size1 ? start1 + index : start2 + index - size1)];
        packet.count = juce::jmin(packetSamples, samples - offset);
        packet.firstSample = first + offset; packet.generation = generation; packet.dropped = lost;
        packet.transportEpoch = epoch; packet.hostTimelineValid = host.valid;
        packet.inputChannels = static_cast<uint8_t>(inputChannels);
        packet.hostFirstSample = host.firstSample + offset;
        packet.endTicks = ticks - static_cast<juce::int64>((samples - offset - packet.count) * ticksPerSample);
        std::copy_n(left + offset, packet.count, packet.left.begin());
        std::copy_n(right + offset, packet.count, packet.right.begin());
        offset += packet.count;
    }
    fifo.finishedWrite(size1 + size2);
}

void KENNContinuousAnalysis::resetWindow(bool resetFilters)
{
    count = clipped = 0; ll = rr = lr = side = peak = onsetEnergy = sustainEnergy = 0.0;
    bandEnergy.fill(0.0);
    if (resetFilters)
    {
        // Gaps/source changes break envelope history; do not bridge two passages.
        for (auto& values : lowState) values.fill(0.0f);
        for (auto& values : highState) values.fill(0.0f);
        fastEnvelope = slowEnvelope = 0.0;
        fastFFT.reset(); lowFFT.reset();
        streamingMeter.reset();
        const juce::ScopedLock lock(publicationLock);
        recent = {}; // History must never straddle a source, transport or audio discontinuity.
    }
}

void KENNContinuousAnalysis::drainPending()
{
    juce::ScopedNoDenormals noDenormals;
    int start1, size1, start2, size2;
    // One bounded sweep per insert gives other instances a turn even if a host
    // produces faster than wall time during an offline render.
    fifo.prepareToRead(fifo.getNumReady(), start1, size1, start2, size2);
    const auto beginTicks = juce::Time::getHighResolutionTicks();
    for (int index = 0; index < size1 + size2; ++index)
        consume(packets[static_cast<size_t>(index < size1 ? start1 + index : start2 + index - size1)]);
    fifo.finishedRead(size1 + size2);
    if (size1 + size2 > 0)
        workerMilliseconds.store(workerMilliseconds.load() + 1000.0 * juce::Time::highResolutionTicksToSeconds(juce::Time::getHighResolutionTicks()-beginTicks));
}

void KENNContinuousAnalysis::consume(const Packet& packet)
{
    if (packet.generation != sourceGeneration.load() || packet.transportEpoch != transportEpoch.load())
        return; // Queued audio from a retired source or passage cannot restore freshness.
    if (packet.generation != workerGeneration || packet.firstSample != expectedSample || packet.dropped != workerDropped || packet.transportEpoch != workerTransportEpoch)
    {
        resetWindow(true);
        workerGeneration = packet.generation; workerDropped = packet.dropped;
        workerTransportEpoch = packet.transportEpoch;
    }
    for (int index = 0; index < packet.count; ++index)
    {
        const double l = packet.left[static_cast<size_t>(index)], r = packet.right[static_cast<size_t>(index)];
        if (! std::isfinite(l) || ! std::isfinite(r))
        {
            // Invalid input stays transparent in playback but cannot enter evidence.
            invalid.fetch_add(1); resetWindow(true); continue;
        }
        ++analysedSamples;
        fastFFT.push(static_cast<float>(l), static_cast<float>(r));
        lowFFT.push(static_cast<float>(l), static_cast<float>(r));
        if (count == 0)
        {
            // Different inserts may start at different callbacks. Wait for the
            // next 100 ms host-sample boundary rather than inventing alignment.
            if (packet.hostTimelineValid && (packet.hostFirstSample + index) % windowSamples != 0) continue;
            firstSample = packet.firstSample + index;
            hostFirstSample = packet.hostFirstSample + index;
        }
        ++count;
        // Start the candidate on the same complete host-grid window. Samples
        // discarded before initial alignment cannot count towards its warm-up.
        if (streamingCandidateEnabled) streamingMeter.push(static_cast<float>(l), static_cast<float>(r));
        peak = juce::jmax(peak, std::abs(l), std::abs(r)); ll += l*l; rr += r*r; lr += l*r;
        const auto s = 0.5 * (l-r); side += s*s;
        if (std::abs(l) >= 0.999 || std::abs(r) >= 0.999) ++clipped; // Sample frames, not channels, near full scale.
        const auto energy = 0.5 * (l*l+r*r);
        fastEnvelope += (energy > fastEnvelope ? fastAttack : fastRelease) * (energy-fastEnvelope);
        slowEnvelope += (energy > slowEnvelope ? slowAttack : slowRelease) * (energy-slowEnvelope);
        const auto onset = juce::jmax(0.0, std::sqrt(fastEnvelope)-std::sqrt(slowEnvelope));
        onsetEnergy += onset*onset; sustainEnergy += slowEnvelope;
        for (size_t band = 0; band < AudioTooRealtimeSpectrumBandCount; ++band)
            for (size_t channel = 0; channel < 2; ++channel)
            {
                const auto input = static_cast<float>(channel == 0 ? l : r);
                auto& low = lowState[channel][band]; auto& high = highState[channel][band];
                low += lowAlpha[band] * (input-low); high += highAlpha[band] * (input-high);
                const double signal = high-low;
                bandEnergy[band] += 0.5 * signal*signal; // Average channel power avoids mono-sum cancellation.
            }
        if (count == windowSamples) { publish(packet, index); resetWindow(false); }
    }
    expectedSample = packet.firstSample + packet.count;
}

void KENNContinuousAnalysis::publish(const Packet& packet, int lastSample)
{
    KENNAnalysisSnapshot frame;
    if (streamingCandidateEnabled) frame.streamingMeter = streamingMeter.snapshot();
    auto& f = frame.features;
    f.sampleRate = rate; f.analysedSamples = analysedSamples;
    f.peakDbfs = juce::Decibels::gainToDecibels(static_cast<float>(peak), -100.0f);
    f.rmsDbfs = juce::Decibels::gainToDecibels(static_cast<float>(std::sqrt(0.5*(ll+rr)/count)), -100.0f);
    f.crestDb = juce::jmax(0.0f, f.peakDbfs-f.rmsDbfs); f.clippedSamples = clipped;
    const auto denominator = std::sqrt(ll*rr);
    f.correlation = denominator > 1e-12 ? static_cast<float>(juce::jlimit(-1.0, 1.0, lr/denominator)) : 1.0f; // Silence has no phase evidence.
    frame.inputChannels = packet.inputChannels;
    // Reuse the existing accumulated-energy floor; duplicated mono and the
    // +1 fallback for a silent channel must not become scored stereo evidence.
    frame.correlationValid = frame.inputChannels == 2 && denominator > 1e-12;
    f.stereoWidth = static_cast<float>(juce::jlimit(0.0, 1.0, 2.0*side/juce::jmax(1e-12, ll+rr)));
    f.transientRatio = static_cast<float>(juce::jmin(10.0, std::sqrt(onsetEnergy/juce::jmax(1e-12, sustainEnergy)))); // Bounded fast-envelope excess over sustain.
    frame.spectrum = spectrum;
    for (size_t band = 0; band < AudioTooRealtimeSpectrumBandCount; ++band)
    {
        const auto energy = static_cast<float>(bandEnergy[band]/count);
        frame.spectrum.energy[band] = energy;
        const auto hz = spectrum.bands[band].centerHz;
        if (hz < 250.0f) f.lowEnergy += energy; // Broad, uncalibrated filter-bank sums: below 250 Hz / 2.5 kHz / above.
        else if (hz < 2500.0f) f.midEnergy += energy;
        else f.highEnergy += energy;
    }
    frame.firstSample = firstSample; frame.endSample = packet.firstSample + lastSample + 1;
    frame.capturedTicks = packet.endTicks - static_cast<juce::int64>((packet.count-lastSample-1)*ticksPerSample);
    frame.generation = workerGeneration; frame.sequence = ++sequence; frame.droppedSamples = workerDropped;
    frame.transportEpoch = workerTransportEpoch; frame.hostTimelineValid = packet.hostTimelineValid;
    frame.hostFirstSample = hostFirstSample; frame.hostEndSample = packet.hostFirstSample + lastSample + 1;
    frame.fastSpectrum = fastFFT.measure(rate, frame.endSample);
    // The long transform runs at 5 Hz. Host-grid parity aligns its capture
    // interval across inserts; local sequence parity is only an unpaired fallback.
    const auto grid = packet.hostTimelineValid ? frame.hostEndSample / windowSamples : static_cast<juce::int64>(sequence);
    if (grid % 2 == 0) frame.lowSpectrum = lowFFT.measure(rate, frame.endSample);
    else frame.lowSpectrum = lowFFT.snapshot();
    frame.invalidSamples = invalid.load(); frame.windowSeconds = count/rate; frame.valid = true;
    const juce::ScopedLock lock(publicationLock);
    published = frame;
    std::move(recent.begin() + 1, recent.end(), recent.begin()); recent.back() = frame;
}

std::array<KENNAnalysisSnapshot, 6> KENNContinuousAnalysis::recentSnapshots() const
{
    const juce::ScopedLock lock(publicationLock);
    auto frames = recent;
    const auto generation = sourceGeneration.load(), epoch = transportEpoch.load(), lost = dropped.load(), invalidCount = invalid.load();
    for (auto& frame : frames)
    {
        frame.valid = frame.valid && frame.generation == generation && frame.transportEpoch == epoch
            && frame.droppedSamples == lost && frame.invalidSamples == invalidCount;
        if (!frame.valid)
        {
            // Neither phase evidence nor candidate readiness may outlive its owning passage.
            frame.correlationValid = false; frame.streamingMeter = {};
        }
    }
    return frames;
}

KENNAnalysisSnapshot KENNContinuousAnalysis::snapshot() const
{
    const juce::ScopedLock lock(publicationLock);
    auto frame = published;
    // Use each counter once: a callback overflow between two reads must not
    // attach a newer drop count to evidence already judged valid.
    const auto lost = dropped.load(), invalidCount = invalid.load();
    frame.valid = frame.valid && frame.generation == sourceGeneration.load()
        && frame.transportEpoch == transportEpoch.load()
        && frame.droppedSamples == lost && frame.invalidSamples == invalidCount;
    frame.droppedSamples = lost; frame.invalidSamples = invalidCount;
    frame.workerMilliseconds = workerMilliseconds.load(); frame.queuedPackets = fifo.getNumReady();
    if (!frame.valid)
    {
        // Readers retire evidence immediately, before the next worker drain.
        frame.correlationValid = false; frame.streamingMeter = {};
    }
    return frame; // A gap retires evidence until a full contiguous window recovers.
}
