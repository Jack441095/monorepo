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
        juce::AudioFormatReaderSource* reader; // owned; prepared, not yet started
        double sampleRate;
    };
    std::atomic<PendingPlayback*> pendingPlayback { nullptr };

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
    // waveform otherwise produces an audible click at the cut sample.
    std::atomic<bool> fadeOutRequested { false };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(SmartSampleManagerAudioProcessor)
};
