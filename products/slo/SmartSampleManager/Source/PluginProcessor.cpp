#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "AuditionTempo.h"

SmartSampleManagerAudioProcessor::SmartSampleManagerAudioProcessor()
    : AudioProcessor(BusesProperties()
                     // Ableton requires an audio-effect VST3 to expose a
                     // valid input bus.  The processor still clears that
                     // input before audition playback; the bus exists for
                     // host compatibility, not pass-through audio.
                     .withInput("Input", juce::AudioChannelSet::stereo(), true)
                     .withOutput("Output", juce::AudioChannelSet::stereo(), true))
{
    formatManager.registerBasicFormats();

    // Background read-ahead thread for audition playback -- prep is complete
    // before any preview reader can be wrapped, so BufferingAudioReader never
    // registers itself against a stopped time-slice thread.
    bufferingThread.startThread();

    // Kicks off model loading on a background thread and returns
    // immediately -- ONNX Env/Session construction (including the CoreML EP
    // compile) used to block this constructor synchronously, stalling DAW
    // project load. See docs/ASYNC_STARTUP.md.
    engine.initAsync();
}

SmartSampleManagerAudioProcessor::~SmartSampleManagerAudioProcessor()
{
    // Retire any unconsumed pending audition start without touching the
    // transport -- during teardown there is no audio callback left to run it.
    delete pendingPlayback.exchange(nullptr, std::memory_order_acq_rel);

    // Drop the current reader (and its buffering reader) before stopping the
    // read-ahead thread, so no time-slice client outlives its thread.
    transportSource.setSource(nullptr);
    readerSource.reset();

    // Any reader the audio thread retired mid-audition is still queued. There is
    // no audio thread left to publish more, so this is the last chance to free
    // them; do it before stopping bufferingThread so nothing touches a dead
    // time-slice client.
    drainRetiredReaders();

    bufferingThread.stopThread(2000);
}

void SmartSampleManagerAudioProcessor::prepareToPlay(double sampleRate, int samplesPerBlock)
{
    transportSource.prepareToPlay(samplesPerBlock, sampleRate);
}

void SmartSampleManagerAudioProcessor::releaseResources()
{
    transportSource.releaseResources();
}

bool SmartSampleManagerAudioProcessor::isBusesLayoutSupported(const BusesLayout& layouts) const
{
    const auto input = layouts.getMainInputChannelSet();
    const auto output = layouts.getMainOutputChannelSet();
    return input == output
        && (output == juce::AudioChannelSet::mono()
            || output == juce::AudioChannelSet::stereo());
}

void SmartSampleManagerAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midiMessages)
{
    juce::ScopedNoDenormals noDenormals;

    // The input bus is present solely for audio-effect host compatibility.
    // This remains an auditioning tool, so discard incoming audio before
    // mixing the selected sample playback below.
    buffer.clear();

    // 1. Fetch DAW Sync information from the playhead
    double currentBeat = 0.0;
    if (auto* playHead = getPlayHead()) {
        auto posInfo = playHead->getPosition();
        if (posInfo.hasValue()) {
            if (posInfo->getBpm().hasValue()) {
                dawBpm.store(*(posInfo->getBpm()), std::memory_order_relaxed);
            }
            isDawPlaying.store(posInfo->getIsPlaying(), std::memory_order_relaxed);
            if (posInfo->getPpqPosition().hasValue()) {
                currentBeat = *(posInfo->getPpqPosition());
            }
        }
    }

    // Check beat boundary crossing for quantized audition starts. Peek the
    // handoff pointer only to decide WHETHER to start; the exchange below is
    // the single point of truth for which handoff (if any) is taken, so a
    // start published a beat early is queued for the next boundary and a
    // cancel racing this callback simply yields a null exchange.
    PendingPlayback* peeked = pendingPlayback.load(std::memory_order_acquire);
    bool shouldTriggerStart = false;
    if (peeked != nullptr) {
        if (!isDawPlaying.load(std::memory_order_relaxed)) {
            shouldTriggerStart = true;
        } else {
            double nextBoundary = std::floor(lastBeatPosition) + 1.0;
            if (lastBeatPosition < nextBoundary && currentBeat >= nextBoundary) {
                shouldTriggerStart = true;
            } else if (currentBeat < lastBeatPosition) {
                // Playhead looped or jumped backwards
                shouldTriggerStart = true;
            }
        }
    }
    // Only remember the beat when the playhead actually reported one. Some hosts
    // return a position with no PPQ for a few callbacks around transport start;
    // writing 0.0 into lastBeatPosition there made the next callback see
    // "jumped backwards" and fire a queued audition immediately, silently
    // defeating beat quantisation.
    if (currentBeat > 0.0 || lastBeatPosition <= 0.0) {
        lastBeatPosition = currentBeat;
    }

    if (shouldTriggerStart) {
        std::unique_ptr<PendingPlayback> taken(pendingPlayback.exchange(nullptr, std::memory_order_acq_rel));
        // Realtime-safe: the reader was already opened and buffered on the
        // message thread back when playSample() was called (see below) --
        // this is just a pointer handoff plus transportSource.start().
        if (taken != nullptr) {
            startPreparedPlayback(
                std::unique_ptr<juce::AudioFormatReaderSource>(taken->reader), taken->sampleRate);
        }
    }

    // 2. Mix in audition playback if active
    if (transportSource.isPlaying()) {
        juce::AudioSourceChannelInfo channelInfo(&buffer, 0, buffer.getNumSamples());
        transportSource.getNextAudioBlock(channelInfo);

        if (fadeOutRequested.exchange(false) || stopRequested.exchange(false)) {
            // One-block gain ramp before the cut, otherwise stopping mid-waveform
            // clicks at the cut sample.
            buffer.applyGainRamp(0, buffer.getNumSamples(), 1.0f, 0.0f);
            // Never AudioTransportSource::stop() from here. In JUCE 8.0.2 it is
            // a bounded spin of 500 x Thread::sleep(2) -- a full second --
            // whose exit condition (`stopped`) is cleared only inside
            // getNextAudioBlock() (juce_AudioTransportSource.cpp:133). On the
            // audio thread nothing else runs that function, so the loop could
            // never exit early and every STOP cost ~1 s of blocked audio plus
            // a second of digital silence, since the buffer is already ramped
            // to zero by the time we get here. Measured at 1396 ms against an
            // 11.61 ms deadline before this changed; see
            // test_rt_deadline_stress_main.cpp.
            //
            // setSource(nullptr) clears `playing` under JUCE's own callbackLock,
            // which getNextAudioBlock above already takes on every single
            // block, so this adds no new lock the callback was not already
            // paying for. It also frees only the ResamplingAudioSource; the
            // AudioFormatReaderSource stays owned by readerSource and is
            // retired through the lock-free ring.
            transportSource.setSource(nullptr);
        }
    }
    else if (stopRequested.exchange(false)) {
        // Stop asked for while the transport was already idle. Still clear the
        // request, and drop the source so the next audition starts clean.
        transportSource.setSource(nullptr);
    }
}

juce::AudioProcessorEditor* SmartSampleManagerAudioProcessor::createEditor()
{
    return new SmartSampleManagerAudioProcessorEditor(*this);
}

void SmartSampleManagerAudioProcessor::playSample(const std::string& filePath)
{
    // Must run on the message thread: createReaderFor() touches the
    // filesystem, and the BPM lookup takes the engine's lock. Preparing this
    // here -- rather than at the beat boundary inside processBlock() -- is
    // what keeps the realtime audio callback free of file I/O and locking.
    // See prepareReaderSource().
    engine.recordPreview(filePath);
    double playSampleRate = 44100.0;
    auto reader = prepareReaderSource(filePath, 0.0f, playSampleRate);
    if (reader == nullptr) return;

    if (isDawPlaying.load(std::memory_order_relaxed)) {
        // Quantized start: hand the already-opened, already-buffered reader
        // to the audio thread via the lock-free handoff; processBlock() picks
        // it up at the next beat boundary (or on a loop jump).
        publishPendingPlayback(reader.release(), playSampleRate);
    } else {
        // Transport stopped, so there is no beat boundary coming to hand this
        // over: publish it exactly the same way and let the audio thread take it
        // on its next callback. Calling startPreparedPlayback() from here used
        // to write readerSource and reconfigure the transport from the message
        // thread while processBlock() could be inside getNextAudioBlock() --
        // a data race, and a use-after-free on the reader itself.
        publishPendingPlayback(reader.release(), playSampleRate);
    }

    // Reclaim whatever the audio thread retired since the last UI call.
    drainRetiredReaders();
}

void SmartSampleManagerAudioProcessor::publishPendingPlayback(
    juce::AudioFormatReaderSource* reader, double playSampleRate)
{
    auto* fresh = new PendingPlayback { reader, playSampleRate };
    PendingPlayback* superseded = pendingPlayback.exchange(fresh, std::memory_order_acq_rel);
    // Whoever ends up replacing an unconsumed handoff owns and retires it:
    // its reader was prepared but never started, so deleting it here returns
    // the file handle without disturbing playback. If the audio thread took
    // the old handoff first, exchange returns nullptr and nothing is retired.
    delete superseded;
}

std::unique_ptr<juce::AudioFormatReaderSource>
SmartSampleManagerAudioProcessor::prepareReaderSource(const std::string& filePath, float sampleBpm,
                                                        double& outPlaySampleRate)
{
    juce::File file(filePath);
    auto* reader = formatManager.createReaderFor(file);
    if (reader == nullptr) return nullptr;

    double speedBpm = sampleBpm;
    if (speedBpm <= 0.0f) {
        // Single-field lookup -- no full-library getSamples() deep copy (each
        // item carries a 512-float embedding vector, so the old whole-list
        // copy was thousands of allocations per audition click).
        speedBpm = engine.getSampleBpm(filePath);
    }

    const double currentDawBpm = dawBpm.load(std::memory_order_relaxed);
    outPlaySampleRate = slo::auditionSourceRate(reader->sampleRate, speedBpm, currentDawBpm);
    if (outPlaySampleRate <= 0.0) {
        delete reader;
        return nullptr;
    }

    // Wrap the format reader in a BufferingAudioReader that pre-reads whole
    // chunks on bufferingThread, so the audio callback's getNextAudioBlock()
    // pulls from an in-memory buffer instead of touching the filesystem
    // (decode happens on the read-ahead thread at whatever rate the disk
    // sustains). Timeout stays at the JUCE default of 0 = never block the
    // caller; an underrun yields silence on that callback rather than a
    // stalled audio thread.
    constexpr int kAuditionBufferedSamples = 32768;
    auto* buffered = new juce::BufferingAudioReader(reader, bufferingThread, kAuditionBufferedSamples);
    return std::make_unique<juce::AudioFormatReaderSource>(buffered, true);
}

void SmartSampleManagerAudioProcessor::startPreparedPlayback(
    std::unique_ptr<juce::AudioFormatReaderSource> newReaderSource, double playSampleRate)
{
    // transportSource is touched here from the audio thread only -- playSample()
    // and stopSample() no longer call into it, they publish commands instead, so
    // there is no race with the message thread.
    //
    // No stop() call on purpose. The setSource(nullptr) below is what actually
    // detaches the outgoing source, and it clears `playing` in the same place,
    // so the stop() in front of it was pure overhead -- and on the audio thread
    // that overhead was the full 500 x 2 ms spin JUCE's stop() performs. See the
    // note in processBlock.
    transportSource.setSource(nullptr);

    // The outgoing source is handed to the message thread rather than freed
    // here. Destroying it runs ~BufferingAudioReader and closes a file
    // descriptor; both belong on a thread that is allowed to block. Taking
    // ownership of the new source and moving the old one out in a single
    // expression also avoids leaving a window where readerSource is null.
    auto outgoing = std::move(readerSource);
    readerSource = std::move(newReaderSource);
    if (outgoing != nullptr) {
        retireReaderOnAudioThread(outgoing.release());
    }

    transportSource.setSource(readerSource.get(), 0, nullptr, playSampleRate);
    transportSource.start();
}

void SmartSampleManagerAudioProcessor::retireReaderOnAudioThread(
    juce::AudioFormatReaderSource* source) noexcept
{
    // Wait-free: one relaxed fetch_add and one store into a fixed array. No
    // allocation and no lock, which is the whole point -- this runs inside
    // processBlock.
    const int slot = retiredWriteIndex.fetch_add(1, std::memory_order_acq_rel);
    if (slot >= 0 && slot < kRetiredReaderSlots) {
        retiredReaders[slot].store(source, std::memory_order_release);
        return;
    }

    // Overflow. Deleting here would be the audio-thread free we are avoiding,
    // and dropping it would leak. Deliberately leak one reader and say so: the
    // alternative is a real-time stall or a silent leak in a plugin that is
    // being torn down anyway. The comment is the honest record.
    juce::Logger::outputDebugString(
        "[SLO] retired-reader ring overflow; one AudioFormatReaderSource leaked "
        "rather than freed on the audio thread. This is a bug; report it.\n");
}

void SmartSampleManagerAudioProcessor::drainRetiredReaders()
{
    // Message thread. Frees every reader the audio thread handed over. Publishes
    // go to increasing slots; draining takes the whole published range at once
    // so a concurrent push lands in a slot this call will not touch.
    const int published = retiredWriteIndex.load(std::memory_order_acquire);
    for (int slot = 0; slot < published && slot < kRetiredReaderSlots; ++slot) {
        auto* outgoing = retiredReaders[slot].exchange(nullptr, std::memory_order_acq_rel);
        delete outgoing;
    }
}

void SmartSampleManagerAudioProcessor::stopSample()
{
    // Cancel a queued quantized start before anything else -- a pending
    // handoff must never fire after the user has asked to stop.
    delete pendingPlayback.exchange(nullptr, std::memory_order_acq_rel);

    // Ask the audio thread to stop; do not touch transportSource from here.
    // Reading isPlaying() and calling stop() on the message thread raced
    // processBlock() while it was inside getNextAudioBlock(), which mutates
    // positionSeconds and the reader's own position. The transport is now owned
    // by the audio thread alone.
    stopRequested.store(true, std::memory_order_release);

    // Reclaim whatever the audio thread retired since the last UI call.
    drainRetiredReaders();
}

// Schema for the versioned project-state chunk below. Bump this and add a
// migration branch in setStateInformation() if the shape of the persisted
// state ever changes -- never assume an old project's chunk matches the
// current fields.
static constexpr int kStateSchemaVersion = 1;

void SmartSampleManagerAudioProcessor::getStateInformation(juce::MemoryBlock& destData)
{
    // Only small, editor-scoped preferences go in the DAW project chunk --
    // the sample database itself is global (SQLite cache, shared across DAW
    // projects) and must never be serialized here. See
    // docs/PLUGIN_STATE_ARCHITECTURE.md for the reasoning.
    juce::ValueTree state("SMARTSAMPLEMANAGER_STATE");
    state.setProperty("schemaVersion", kStateSchemaVersion, nullptr);
    state.setProperty("searchText", editorSearchText, nullptr);
    state.setProperty("namingStyleId", editorNamingStyleId, nullptr);

    if (auto xml = state.createXml())
        copyXmlToBinary(*xml, destData);
}

void SmartSampleManagerAudioProcessor::setStateInformation(const void* data, int sizeInBytes)
{
    // Malformed/foreign state must fail gracefully -- keep current defaults
    // rather than crash or half-apply a corrupt chunk.
    auto xml = getXmlFromBinary(data, sizeInBytes);
    if (xml == nullptr)
        return;

    auto state = juce::ValueTree::fromXml(*xml);
    if (!state.isValid() || !state.hasType("SMARTSAMPLEMANAGER_STATE"))
        return;

    int schemaVersion = state.getProperty("schemaVersion", 0);
    if (schemaVersion <= 0 || schemaVersion > kStateSchemaVersion)
        return; // Unknown/future schema -- ignore rather than misinterpret.

    editorSearchText = state.getProperty("searchText", juce::String()).toString();
    editorNamingStyleId = static_cast<int>(state.getProperty("namingStyleId", 9));
}

// This handles plugin instantiation
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new SmartSampleManagerAudioProcessor();
}
