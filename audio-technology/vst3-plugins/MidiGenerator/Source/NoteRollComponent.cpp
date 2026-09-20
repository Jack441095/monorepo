#include "NoteRollComponent.h"

NoteRollComponent::NoteRollComponent(MidiGeneratorAudioProcessor& processorToUse)
    : processor(processorToUse)
{
    patternSnapshot = processor.getEngine().getCurrentPattern();
    startTimerHz(30);
}

NoteRollComponent::~NoteRollComponent()
{
    stopTimer();
}

void NoteRollComponent::mouseDrag(const juce::MouseEvent& e)
{
    if (dragInProgress || e.getDistanceFromDragStart() < 10)
        return;

    auto* container = juce::DragAndDropContainer::findParentDragContainerFor(this);
    if (container == nullptr || patternSnapshot == nullptr
        || (patternSnapshot->notes.empty() && patternSnapshot->chordNotes.empty()))
        return;

    auto tempFile = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("MidiGenerator_" + juce::String(juce::Random::getSystemRandom().nextInt()) + ".mid");

    if (! processor.writePatternToMidiFile(tempFile))
        return;

    dragInProgress = true;
    container->performExternalDragDropOfFiles({ tempFile.getFullPathName() }, false, this,
                                                [this] { dragInProgress = false; });
}

void NoteRollComponent::timerCallback()
{
    patternSnapshot = processor.getEngine().getCurrentPattern();
    repaint();
}

void NoteRollComponent::paint(juce::Graphics& g)
{
    auto bounds = getLocalBounds().toFloat();
    g.setColour(juce::Colour(0xff1a1a1f));
    g.fillRect(bounds);

    if (patternSnapshot == nullptr || (patternSnapshot->notes.empty() && patternSnapshot->chordNotes.empty()))
    {
        g.setColour(juce::Colours::grey);
        g.drawText("No pattern generated yet", bounds, juce::Justification::centred);
        return;
    }

    const int lengthBeats = juce::jmax(1, patternSnapshot->lengthBeats);

    int lowPitch = 127, highPitch = 0;
    for (auto& n : patternSnapshot->notes)
    {
        lowPitch = juce::jmin(lowPitch, n.pitch);
        highPitch = juce::jmax(highPitch, n.pitch);
    }
    for (auto& n : patternSnapshot->chordNotes)
    {
        lowPitch = juce::jmin(lowPitch, n.pitch);
        highPitch = juce::jmax(highPitch, n.pitch);
    }
    lowPitch = juce::jmax(0, lowPitch - 2);
    highPitch = juce::jmin(127, highPitch + 2);
    const int pitchSpan = juce::jmax(1, highPitch - lowPitch);

    const float pxPerBeat = bounds.getWidth() / (float) lengthBeats;
    const float pxPerSemitone = bounds.getHeight() / (float) pitchSpan;

    // Beat grid, accented every 4 beats (bar lines).
    for (int b = 0; b <= lengthBeats; ++b)
    {
        const float x = (float) b * pxPerBeat;
        g.setColour(b % 4 == 0 ? juce::Colour(0xff3a3a45) : juce::Colour(0xff262630));
        g.drawVerticalLine((int) x, bounds.getY(), bounds.getBottom());
    }

    auto drawLayer = [&](const std::vector<GeneratedNote>& layerNotes, juce::Colour baseColour)
    {
        for (auto& n : layerNotes)
        {
            const float x = (float) n.startBeat * pxPerBeat;
            const float w = juce::jmax(2.0f, (float) n.lengthBeats * pxPerBeat - 1.0f);
            const float y = bounds.getHeight() - (float) (n.pitch - lowPitch + 1) * pxPerSemitone;
            const float h = juce::jmax(2.0f, pxPerSemitone - 1.0f);

            const float velocityAlpha = juce::jmap((float) n.velocity, 1.0f, 127.0f, 0.35f, 1.0f);
            g.setColour(baseColour.withAlpha(velocityAlpha));
            g.fillRoundedRectangle(x, y, w, h, 1.5f);
        }
    };

    // Chords drawn first (they sit lower/behind), melody drawn on top in a brighter colour.
    drawLayer(patternSnapshot->chordNotes, juce::Colour(0xff9a7bd8));
    drawLayer(patternSnapshot->notes, juce::Colour(0xff5ec8f0));

    // Playhead.
    const double beat = processor.getLastKnownBeat();
    const double patternBeat = std::fmod(std::fmod(beat, (double) lengthBeats) + lengthBeats, (double) lengthBeats);
    const float playheadX = (float) patternBeat * pxPerBeat;
    g.setColour(juce::Colours::orange);
    g.drawVerticalLine((int) playheadX, bounds.getY(), bounds.getBottom());
}
