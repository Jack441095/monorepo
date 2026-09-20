#pragma once

#include <JuceHeader.h>
#include "MidiGeneratorEngine.h"

class MidiGeneratorAudioProcessor : public juce::AudioProcessor,
                                     private juce::AudioProcessorValueTreeState::Listener
{
public:
    MidiGeneratorAudioProcessor();
    ~MidiGeneratorAudioProcessor() override;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;

    bool isBusesLayoutSupported(const BusesLayout& layouts) const override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "MidiGenerator"; }

    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return true; }
    bool isMidiEffect() const override { return true; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return {}; }
    void changeProgramName(int, const juce::String&) override {}

    void getStateInformation(juce::MemoryBlock& destData) override;
    void setStateInformation(const void* data, int sizeInBytes) override;

    juce::AudioProcessorValueTreeState apvts;
    MidiGeneratorEngine& getEngine() { return engine; }

    // Triggers an immediate regeneration with the current parameter values (bound to the
    // editor's Generate button, and to loop/rewind so the pattern can vary between loops).
    void triggerGeneration();

    // Last DAW beat position seen in processBlock, for the editor's playhead indicator.
    double getLastKnownBeat() const { return lastKnownBeat.load(); }
    int getPatternLengthBeats() const { return (int) apvts.getRawParameterValue("patternLength")->load(); }

    // Writes the engine's current pattern (melody + chords, separate tracks/channels) as a
    // Standard MIDI File. Used both by the editor's "Save MIDI..." button and to build the
    // temp file that gets drag-and-dropped straight onto the DAW timeline.
    bool writePatternToMidiFile(const juce::File& destination) const;

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();
    void parameterChanged(const juce::String& parameterID, float newValue) override;
    GenerationParams collectParams() const;

    MidiGeneratorEngine engine;

    std::atomic<double> lastKnownBeat { 0.0 };
    double lastPpqPosition = 0.0;
    bool wasPlaying = false;

    // Notes the plugin has sounded and not yet turned off, keyed by MIDI pitch, so
    // processBlock can emit note-offs at the right sample offset across block boundaries.
    struct ActiveNote
    {
        int pitch = 0;
        int channel = 1;
        double offBeat = 0.0;
    };
    std::vector<ActiveNote> activeNotes;

    void flushAllNotesOff(juce::MidiBuffer& midi, int sampleOffset);

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(MidiGeneratorAudioProcessor)
};
