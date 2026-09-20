#include "PluginProcessor.h"
#include "PluginEditor.h"

namespace
{
    void setUpRotary(juce::Slider& s)
    {
        s.setSliderStyle(juce::Slider::RotaryHorizontalVerticalDrag);
        s.setTextBoxStyle(juce::Slider::TextBoxBelow, false, 70, 18);
    }

    void setUpLabel(juce::Label& l, juce::Component& owner, const juce::String& text)
    {
        l.setText(text, juce::dontSendNotification);
        l.setJustificationType(juce::Justification::centred);
        l.setFont(juce::Font(13.0f));
        owner.addAndMakeVisible(l);
    }
}

MidiGeneratorAudioProcessorEditor::MidiGeneratorAudioProcessorEditor(MidiGeneratorAudioProcessor& p)
    : AudioProcessorEditor(&p), midiProcessor(p), noteRoll(p)
{
    auto& apvts = midiProcessor.apvts;

    addAndMakeVisible(rootNoteBox);
    rootNoteAttachment = std::make_unique<ComboBoxAttachment>(apvts, "rootNote", rootNoteBox);
    setUpLabel(rootNoteLabel, *this, "Root Note");

    addAndMakeVisible(scaleBox);
    scaleAttachment = std::make_unique<ComboBoxAttachment>(apvts, "scale", scaleBox);
    setUpLabel(scaleLabel, *this, "Scale / Emotion");

    for (auto* s : { &densitySlider, &intensitySlider, &velocityMinSlider, &velocityMaxSlider,
                      &octaveMinSlider, &octaveMaxSlider, &patternLengthSlider })
    {
        setUpRotary(*s);
        addAndMakeVisible(s);
    }

    densityAttachment = std::make_unique<SliderAttachment>(apvts, "density", densitySlider);
    setUpLabel(densityLabel, *this, "Density");

    intensityAttachment = std::make_unique<SliderAttachment>(apvts, "intensity", intensitySlider);
    setUpLabel(intensityLabel, *this, "Intensity");

    velocityMinAttachment = std::make_unique<SliderAttachment>(apvts, "velocityMin", velocityMinSlider);
    velocityMaxAttachment = std::make_unique<SliderAttachment>(apvts, "velocityMax", velocityMaxSlider);
    setUpLabel(velocityLabel, *this, "Velocity Min / Max");

    octaveMinAttachment = std::make_unique<SliderAttachment>(apvts, "octaveMin", octaveMinSlider);
    octaveMaxAttachment = std::make_unique<SliderAttachment>(apvts, "octaveMax", octaveMaxSlider);
    setUpLabel(octaveLabel, *this, "Octave Min / Max");

    patternLengthAttachment = std::make_unique<SliderAttachment>(apvts, "patternLength", patternLengthSlider);
    setUpLabel(patternLengthLabel, *this, "Pattern Length");

    addAndMakeVisible(generateButton);
    generateButton.onClick = [this] { midiProcessor.triggerGeneration(); };

    addAndMakeVisible(saveMidiButton);
    saveMidiButton.onClick = [this]
    {
        fileChooser = std::make_unique<juce::FileChooser>("Save generated MIDI as...",
                                                            juce::File::getSpecialLocation(juce::File::userDocumentsDirectory)
                                                                .getChildFile("Generated.mid"),
                                                            "*.mid");
        fileChooser->launchAsync(juce::FileBrowserComponent::saveMode | juce::FileBrowserComponent::warnAboutOverwriting,
                                  [this](const juce::FileChooser& fc)
                                  {
                                      auto file = fc.getResult();
                                      if (file != juce::File{})
                                          midiProcessor.writePatternToMidiFile(file);
                                  });
    };

    addAndMakeVisible(noteRoll);

    setResizable(true, true);
    setResizeLimits(560, 420, 1400, 1000);
    setSize(760, 520);
}

MidiGeneratorAudioProcessorEditor::~MidiGeneratorAudioProcessorEditor()
{
}

void MidiGeneratorAudioProcessorEditor::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(0xff121216));
    g.setColour(juce::Colours::white);
    g.setFont(juce::Font(18.0f, juce::Font::bold));
    g.drawText("MIDI Generator", getLocalBounds().removeFromTop(30), juce::Justification::centred);
}

void MidiGeneratorAudioProcessorEditor::resized()
{
    auto area = getLocalBounds().reduced(12);
    area.removeFromTop(28); // title

    auto controls = area.removeFromTop(200);

    auto combos = controls.removeFromTop(56);
    auto rootArea = combos.removeFromLeft(combos.getWidth() / 3);
    rootNoteLabel.setBounds(rootArea.removeFromTop(16));
    rootNoteBox.setBounds(rootArea.reduced(4, 0));

    auto scaleArea = combos;
    scaleLabel.setBounds(scaleArea.removeFromTop(16));
    scaleBox.setBounds(scaleArea.reduced(4, 0));

    controls.removeFromTop(8);

    const int numKnobColumns = 5;
    const int colWidth = controls.getWidth() / numKnobColumns;

    auto layoutKnobPair = [&](juce::Rectangle<int> col, juce::Label& label,
                               juce::Slider& a, juce::Slider& b)
    {
        label.setBounds(col.removeFromTop(16));
        auto halves = col;
        a.setBounds(halves.removeFromLeft(halves.getWidth() / 2).reduced(2));
        b.setBounds(halves.reduced(2));
    };

    auto col1 = controls.removeFromLeft(colWidth);
    densityLabel.setBounds(col1.removeFromTop(16));
    densitySlider.setBounds(col1.reduced(4));

    auto col2 = controls.removeFromLeft(colWidth);
    intensityLabel.setBounds(col2.removeFromTop(16));
    intensitySlider.setBounds(col2.reduced(4));

    auto col3 = controls.removeFromLeft(colWidth);
    layoutKnobPair(col3, velocityLabel, velocityMinSlider, velocityMaxSlider);

    auto col4 = controls.removeFromLeft(colWidth);
    layoutKnobPair(col4, octaveLabel, octaveMinSlider, octaveMaxSlider);

    auto col5 = controls;
    patternLengthLabel.setBounds(col5.removeFromTop(16));
    patternLengthSlider.setBounds(col5.reduced(4));

    area.removeFromTop(8);
    auto buttonRow = area.removeFromTop(32);
    generateButton.setBounds(buttonRow.removeFromLeft(buttonRow.getWidth() / 2).reduced(6, 0));
    saveMidiButton.setBounds(buttonRow.reduced(6, 0));

    area.removeFromTop(8);
    noteRoll.setBounds(area);
}
