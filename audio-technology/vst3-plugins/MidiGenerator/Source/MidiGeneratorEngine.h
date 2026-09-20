#pragma once

#include <JuceHeader.h>
#include <memory>
#include <vector>

// A single generated MIDI note, positioned in beats relative to the start of the pattern.
struct GeneratedNote
{
    int pitch = 60;
    int velocity = 100;
    double startBeat = 0.0;
    double lengthBeats = 0.25;
};

// One full generated pattern, looped every lengthBeats by the processor.
// notes/chordNotes are kept as separate layers so the processor can route them to
// different MIDI channels and the MIDI-file export can write them as separate tracks.
struct GeneratedPattern
{
    std::vector<GeneratedNote> notes;      // melody, channel 1
    std::vector<GeneratedNote> chordNotes; // chord accompaniment, channel 2
    int lengthBeats = 4;
};

struct GenerationParams
{
    int rootNote = 0;        // 0 = C
    int scaleIndex = 0;      // index into ScaleTable::getAll()
    float density = 0.6f;    // 0..1 probability a given rhythmic slot produces a note
    float intensity = 0.5f;  // 0..1, biases rhythm chain + velocity spread (emotional "energy")
    int velocityMin = 70;
    int velocityMax = 110;
    int octaveMin = -1;      // octaves relative to middle C, inclusive
    int octaveMax = 1;
    int patternLengthBeats = 8;
};

// Extracted/re-shaped from audiogen's Markov melody generator
// (studio/audiogen/audiogen/ai/markov/melody/*): an emotion/scale picks the pitch
// palette, and two small order-2 Markov chains shape melodic contour (interval chain)
// and rhythmic phrasing (duration chain), instead of audiogen's full trained model.
//
// Generation runs on a background juce::Thread. The audio thread and the UI both read
// the latest finished pattern via a SpinLock-guarded shared_ptr swap - they never touch
// the thread's working state directly.
class MidiGeneratorEngine : private juce::Thread
{
public:
    MidiGeneratorEngine();
    ~MidiGeneratorEngine() override;

    // Called from the message thread (parameter changes, Generate button, playhead-driven
    // auto-regeneration). Cheap: just stores params and wakes the worker.
    void requestGeneration(const GenerationParams& params);

    // Lock-free read, safe to call from the audio thread or the UI.
    std::shared_ptr<const GeneratedPattern> getCurrentPattern() const;

private:
    void run() override;
    static GeneratedPattern generate(const GenerationParams& params, juce::Random& rng);

    juce::WaitableEvent wakeEvent;
    juce::SpinLock paramsLock;
    GenerationParams pendingParams;
    bool hasPendingRequest = false;

    // Apple's libc++ doesn't provide std::atomic<std::shared_ptr<T>> even under C++20
    // (it requires T to be trivially copyable), so the lock-free pattern swap is instead
    // a SpinLock-guarded shared_ptr copy - the critical section is a refcount bump, short
    // enough to be safe to take from the audio thread.
    mutable juce::SpinLock patternLock;
    std::shared_ptr<const GeneratedPattern> currentPattern;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(MidiGeneratorEngine)
};
