#pragma once

#include <JuceHeader.h>
#include "PluginProcessor.h"
#include "NoteRollComponent.h"

class MidiGeneratorAudioProcessorEditor : public juce::AudioProcessorEditor,
                                           public juce::DragAndDropContainer
{
public:
    explicit MidiGeneratorAudioProcessorEditor(MidiGeneratorAudioProcessor&);
    ~MidiGeneratorAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;

private:
    using APVTS = juce::AudioProcessorValueTreeState;
    using SliderAttachment = APVTS::SliderAttachment;
    using ComboBoxAttachment = APVTS::ComboBoxAttachment;

    MidiGeneratorAudioProcessor& midiProcessor;

    juce::ComboBox rootNoteBox, scaleBox;
    juce::Slider densitySlider, intensitySlider;
    juce::Slider velocityMinSlider, velocityMaxSlider;
    juce::Slider octaveMinSlider, octaveMaxSlider;
    juce::Slider patternLengthSlider;
    juce::TextButton generateButton { "Generate" };
    juce::TextButton saveMidiButton { "Save MIDI..." };
    std::unique_ptr<juce::FileChooser> fileChooser;

    juce::Label rootNoteLabel, scaleLabel, densityLabel, intensityLabel,
                velocityLabel, octaveLabel, patternLengthLabel;

    NoteRollComponent noteRoll;

    std::unique_ptr<ComboBoxAttachment> rootNoteAttachment, scaleAttachment;
    std::unique_ptr<SliderAttachment> densityAttachment, intensityAttachment,
                                       velocityMinAttachment, velocityMaxAttachment,
                                       octaveMinAttachment, octaveMaxAttachment,
                                       patternLengthAttachment;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(MidiGeneratorAudioProcessorEditor)
};
