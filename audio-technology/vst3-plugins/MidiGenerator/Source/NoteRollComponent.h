#pragma once

#include <JuceHeader.h>
#include "PluginProcessor.h"

// Read-only piano-roll preview of the engine's currently generated pattern, with a
// playhead line synced to the DAW transport. Polls at 30Hz rather than pushing from
// the audio thread, since the pattern pointer swap is the only thing that needs to be
// realtime-safe.
class NoteRollComponent : public juce::Component,
                           private juce::Timer
{
public:
    explicit NoteRollComponent(MidiGeneratorAudioProcessor& processorToUse);
    ~NoteRollComponent() override;

    void paint(juce::Graphics& g) override;
    void mouseDrag(const juce::MouseEvent& e) override;

private:
    void timerCallback() override;

    MidiGeneratorAudioProcessor& processor;
    std::shared_ptr<const GeneratedPattern> patternSnapshot;
    bool dragInProgress = false;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(NoteRollComponent)
};
