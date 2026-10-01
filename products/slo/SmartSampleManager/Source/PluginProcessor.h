#pragma once

#include <JuceHeader.h>
#include "SampleManagerEngine.h"

class SmartSampleManagerAudioProcessor : public juce::AudioProcessor
{
public:
    SmartSampleManagerAudioProcessor();
    ~SmartSampleManagerAudioProcessor() override;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;

    bool isBusesLayoutSupported(const BusesLayout& layouts) const override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "SLO"; }

    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int index) override {}
    const juce::String getProgramName(int index) override { return {}; }
    void changeProgramName(int index, const juce::String& newName) override {}

    void getStateInformation(juce::MemoryBlock& destData) override;
    void setStateInformation(const void* data, int sizeInBytes) override;

    // Get the background engine
    SampleManagerEngine& getEngine() { return engine; }

    // DAW Playhead sync variables
    double getDawBpm() const { return dawBpm.load(std::memory_order_relaxed); }
    bool getIsDawPlaying() const { return isDawPlaying.load(std::memory_order_relaxed); }

    // Audition playback trigger
    void playSample(const std::string& filePath);
    void stopSample();

    // Per-instance UI/editor state that should survive a DAW project save/
    // reload. Deliberately NOT the sample database (that's global, cached in
    // SQLite -- see docs/PLUGIN_STATE_ARCHITECTURE.md) -- just small,
    // editor-scoped preferences the editor reads on construction and writes
    // back whenever the user changes them, so state round-trips even though
    // the editor itself is destroyed/recreated across DAW UI show/hide.
    juce::String getEditorSearchText() const { return editorSearchText; }
    void setEditorSearchText(const juce::String& text) { editorSearchText = text; }
    int getEditorNamingStyleId() const { return editorNamingStyleId; }
    void setEditorNamingStyleId(int styleId) { editorNamingStyleId = styleId; }

private:
    // Opens the file, creates its reader, and resolves playback speed --
    // involves filesystem I/O and heap allocation, so this must only ever be
    // called from the message thread (see playSample()/processBlock()).
    std::unique_ptr<juce::AudioFormatReaderSource> prepareReaderSource(const std::string& filePath,
                                                                        float sampleBpm,
                                                                        double& outPlaySampleRate);

    // Realtime-safe: just takes ownership of an already-open reader and
    // starts it. No file I/O, no allocation beyond the trivial pointer swap.
    void startPreparedPlayback(std::unique_ptr<juce::AudioFormatReaderSource> newReaderSource,
                                double playSampleRate);

    // Message-thread-only: prepares a new pending audition handoff, retires
    // (and deletes the reader of) any unconsumed handoff it supersedes.
    void publishPendingPlayback(juce::AudioFormatReaderSource* reader, double playSampleRate);

    SampleManagerEngine engine;

    // Persisted editor state -- see getEditorSearchText()/getEditorNamingStyleId()
    // above and getStateInformation()/setStateInformation() in the .cpp.
    juce::String editorSearchText;
    int editorNamingStyleId = 9;

    // DAW sync state. dawBpm/isDawPlaying are written on the audio thread
    // (processBlock's playhead fetch) and read on the message thread
    // (playSample/getDawBpm/getIsDawPlaying), so both must be atomic.
    std::atomic<double> dawBpm { 120.0 };
    std::atomic<bool> isDawPlaying { false };
    // Audio-thread-only (tracked in processBlock); never touched off the
    // callback, so it stays a plain double.
    double lastBeatPosition = 0.0;

    // Quantized start trigger. The reader is prepared up front (on the
    // message thread, when playSample() is called) rather than at the beat
    // boundary, so processBlock() only ever does a cheap pointer handoff --
    // see the header comment on prepareReaderSource() above for why.
    //
    // publish/consume protocol (lock-free):
    //   - Message thread publishes a heap-allocated PendingPlayback via
    //     exchange(); whichever side ends up owning a non-null previous value
    //     that the audio thread never consumed retires it (whoever replaced
    //     it deletes it -- the time-slice reader it owns has not been started).
    //   - Audio thread first peeks the pointer (decide whether the beat
    //     boundary/loop-jump condition is met), then exchange(nullptr) only
    //     when it must start, moving the reader into startPreparedPlayback().
    //   - stopSample()/destructor exchange(nullptr) to cancel a pending start.
    struct PendingPlayback
    {
        // Owns the reader. A raw pointer here leaked: three sites `delete` the
        // PendingPlayback struct, which frees the 16-byte wrapper and nothing
        // else, so ~BufferingAudioReader never ran and the reader stayed
        // registered with the time-slice thread with its file descriptor open.
        // Holding it in a unique_ptr makes every one of those sites correct.
        std::unique_ptr<juce::AudioFormatReaderSource> reader; // prepared, not yet started
        double sampleRate;
    };
    std::atomic<PendingPlayback*> pendingPlayback { nullptr };

    // Retired reader sources, published by the audio thread and drained by the
    // message thread.
    //
    // Why this exists: startPreparedPlayback() used to move-assign readerSource
    // from inside processBlock(), which destroyed the *previous*
    // AudioFormatReaderSource -> BufferingAudioReader -> format reader on the
    // audio thread. That is a large free() plus a file-descriptor close on a
    // real-time thread, exactly the stall the bufferingThread design exists to
    // avoid. The audio thread now hands the old source here and never frees it.
    //
    // A ring rather than a single slot, because the audio thread may take over
    // another pending start before the message thread gets a chance to drain, and
    // a single slot would drop the older reader on the floor. Capacity is a
    // compile-time constant so the push is a bounds check and one atomic store:
    // no allocation, no lock, no unbounded growth.
    //
    // The index wraps with a modulo, deliberately. An earlier version only ever
    // fetch_add'ed it, so slot 8 and every slot after it fell into the overflow
    // branch for the remaining life of the plugin instance -- not a burst limit
    // as the comment here used to claim, but a lifetime one. Each overflow leaked
    // a reader and, worse, performed a String allocation and a blocking write(2)
    // to stderr from inside processBlock. Wrapping means a slow drain can cost
    // at most the eight entries the ring holds, and the drain always takes every
    // slot, so the push never has to be careful about what the drain is doing.
    //
    // publish/consume protocol (lock-free, same shape as pendingPlayback):
    //   - Audio thread pushes the outgoing source and never frees it.
    //   - The message thread swaps every slot out and deletes what it finds.
    static constexpr int kRetiredReaderSlots = 8;
    std::atomic<juce::AudioFormatReaderSource*> retiredReaders[kRetiredReaderSlots] {};
    std::atomic<unsigned> retiredWriteIndex { 0 };
    void retireReaderOnAudioThread(juce::AudioFormatReaderSource* source) noexcept;
    void drainRetiredReaders();

    // Playback audition classes
    juce::AudioFormatManager formatManager;
    // Background read-ahead thread for audition playback. BufferingAudioReader
    // (wrapping each preview's format reader) pulls whole chunks off disk here
    // so the audio callback never touches the filesystem -- see
    // prepareReaderSource() and docs/SLO_RT_THREADING_AUDIT_V1.md. Declared
    // before transportSource/readerSource so it is destroyed after them.
    juce::TimeSliceThread bufferingThread { "SLO Audition Pre-Read" };
    std::unique_ptr<juce::AudioFormatReaderSource> readerSource;
    juce::AudioTransportSource transportSource;

    // stopSample() defers the actual transportSource.stop() to the next
    // processBlock() so a one-block gain ramp can run first -- stopping mid-
    // waveform otherwise produces an audible click at the cut sample. The audio
    // thread is the only one that touches the transport; stopSample() just sets
    // this flag.
    std::atomic<bool> fadeOutRequested { false };
    std::atomic<bool> stopRequested { false };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(SmartSampleManagerAudioProcessor)
};
