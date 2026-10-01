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
    bool transportReportedAPosition = false;
    bool ppqWasReported = false;
    if (auto* playHead = getPlayHead()) {
        auto posInfo = playHead->getPosition();
        if (posInfo.hasValue()) {
            transportReportedAPosition = true;
            if (posInfo->getBpm().hasValue()) {
                dawBpm.store(*(posInfo->getBpm()), std::memory_order_relaxed);
            }
            isDawPlaying.store(posInfo->getIsPlaying(), std::memory_order_relaxed);
            if (posInfo->getPpqPosition().hasValue()) {
                currentBeat = *(posInfo->getPpqPosition());
                ppqWasReported = true;
            }
        }
    }

    // A host can report a transport with no PPQ at all. That used to strand a
    // queued audition permanently: currentBeat stayed 0.0, lastBeatPosition was
    // pinned at 0.0, so nextBoundary was always 1.0 and neither "reached the
    // boundary" (0 >= 1) nor "jumped backwards" (0 < 0) could ever be true. The
    // pending handoff then held an open file descriptor and the user heard
    // nothing. With no PPQ there is no beat to quantise to, so start at once.
    const bool canQuantise = ppqWasReported;

    if (!transportReportedAPosition)
        isDawPlaying.store(false, std::memory_order_relaxed);

    // Check beat boundary crossing for quantized audition starts. Peek the
    // handoff pointer only to decide WHETHER to start; the exchange below is
    // the single point of truth for which handoff (if any) is taken, so a
    // start published a beat early is queued for the next boundary and a
    // cancel racing this callback simply yields a null exchange.
    PendingPlayback* peeked = pendingPlayback.load(std::memory_order_acquire);
    bool shouldTriggerStart = false;
    if (peeked != nullptr) {
        if (!isDawPlaying.load(std::memory_order_relaxed) || !canQuantise) {
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
                std::move(taken->reader), taken->sampleRate);
        }
    }

    // 2. Mix in audition playback if active
    if (transportSource.isPlaying()) {
        juce::AudioSourceChannelInfo channelInfo(&buffer, 0, buffer.getNumSamples());
        transportSource.getNextAudioBlock(channelInfo);

        if (stopRequested.exchange(false)) {
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

    // One handoff either way. When the transport is running, processBlock() takes
    // this at the next beat boundary (or on a loop jump); when it is stopped there
    // is no boundary coming, so the audio thread takes it on its next callback.
    //
    // The distinction used to be expressed as two branches with byte-identical
    // bodies, which read as though the transport state changed something here. It
    // does not, and it must not: calling startPreparedPlayback() from the message
    // thread instead used to write readerSource and reconfigure the transport
    // while processBlock() could be inside getNextAudioBlock(), which is a data
    // race and a use-after-free on the reader. processBlock() is the only place
    // that touches the transport.
    publishPendingPlayback(reader.release(), playSampleRate);

    // Reclaim whatever the audio thread retired since the last UI call.
    drainRetiredReaders();
}

void SmartSampleManagerAudioProcessor::publishPendingPlayback(
    juce::AudioFormatReaderSource* reader, double playSampleRate)
{
    auto* fresh = new PendingPlayback { std::unique_ptr<juce::AudioFormatReaderSource>(reader),
                                        playSampleRate };
    PendingPlayback* superseded = pendingPlayback.exchange(fresh, std::memory_order_acq_rel);
    // Whoever ends up replacing an unconsumed handoff owns and retires it: its
    // reader was prepared but never started, so destroying it here closes the
    // file without disturbing playback. The reader is a unique_ptr member, so
    // deleting the wrapper does close the file -- an earlier raw pointer here
    // meant it did not. If the audio thread took the old handoff first,
    // exchange returns nullptr and nothing is retired.
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
    // Wait-free: one fetch_add, a mask, and one store into a fixed array. No
    // allocation, no lock, and no branch that can write to stderr -- this runs
    // inside processBlock, where AppLogger.cpp explains why that is forbidden.
    const auto slot = static_cast<unsigned>(retiredWriteIndex.fetch_add(1, std::memory_order_acq_rel))
                      % static_cast<unsigned>(kRetiredReaderSlots);
    retiredReaders[slot].store(source, std::memory_order_release);
}

void SmartSampleManagerAudioProcessor::drainRetiredReaders()
{
    // Message thread. Frees every reader the audio thread handed over. Because
    // the producer wraps, a push can land in a slot this call also takes; the
    // exchange means the loser simply finds nullptr and the reader is collected
    // by the next drain. Nothing is double-freed, because only this function
    // ever deletes, and it only deletes what it successfully took.
    for (auto& slot : retiredReaders) {
        auto* outgoing = slot.exchange(nullptr, std::memory_order_acq_rel);
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

    // Bounded on read as well as on the way in: this string is written on every
    // keystroke, so an unbounded copy would let one paste inflate the DAW's
    // project chunk on every save from then on.
    editorSearchText = state.getProperty("searchText", juce::String()).toString().substring(0, 512);
    // A corrupt or hand-edited chunk yields 0, and 0 falls through every branch of
    // getFormattedFilename to "return originalName" while still relocating files into
    // category folders -- so an unvalidated project chunk would drive a filesystem move
    // with no naming scheme. Clamp to the styles that exist.
    editorNamingStyleId = juce::jlimit(1, 9, static_cast<int>(state.getProperty("namingStyleId", 9)));
}

// This handles plugin instantiation
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new SmartSampleManagerAudioProcessor();
}
