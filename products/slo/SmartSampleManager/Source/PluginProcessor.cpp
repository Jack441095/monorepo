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
    lastBeatPosition = currentBeat;

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

        if (fadeOutRequested.exchange(false)) {
            buffer.applyGainRamp(0, buffer.getNumSamples(), 1.0f, 0.0f);
            transportSource.stop();
        }
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
        startPreparedPlayback(std::move(reader), playSampleRate);
    }
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
    transportSource.stop();
    transportSource.setSource(nullptr);
    readerSource = std::move(newReaderSource);
    transportSource.setSource(readerSource.get(), 0, nullptr, playSampleRate);
    transportSource.start();
}

void SmartSampleManagerAudioProcessor::stopSample()
{
    // Cancel a queued quantized start before anything else -- a pending
    // handoff must never fire after the user has asked to stop.
    delete pendingPlayback.exchange(nullptr, std::memory_order_acq_rel);
    if (transportSource.isPlaying())
        fadeOutRequested = true;
    else
        transportSource.stop();
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
