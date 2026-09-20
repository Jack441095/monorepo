#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "ScaleTable.h"

namespace
{
    constexpr const char* rootNoteNames[] = { "C", "C#", "D", "D#", "E", "F",
                                               "F#", "G", "G#", "A", "A#", "B" };

    const juce::StringArray& paramIdsThatTriggerRegeneration()
    {
        static const juce::StringArray ids { "rootNote", "scale", "density", "intensity",
                                              "velocityMin", "velocityMax",
                                              "octaveMin", "octaveMax", "patternLength" };
        return ids;
    }
}

juce::AudioProcessorValueTreeState::ParameterLayout MidiGeneratorAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;

    juce::StringArray rootChoices;
    for (auto* n : rootNoteNames)
        rootChoices.add(n);

    params.push_back(std::make_unique<juce::AudioParameterChoice>(
        juce::ParameterID { "rootNote", 1 }, "Root Note", rootChoices, 0));

    params.push_back(std::make_unique<juce::AudioParameterChoice>(
        juce::ParameterID { "scale", 1 }, "Scale / Emotion", ScaleTable::getNames(), 0));

    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID { "density", 1 }, "Note Density",
        juce::NormalisableRange<float>(0.0f, 1.0f), 0.6f));

    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID { "intensity", 1 }, "Intensity",
        juce::NormalisableRange<float>(0.0f, 1.0f), 0.5f));

    params.push_back(std::make_unique<juce::AudioParameterInt>(
        juce::ParameterID { "velocityMin", 1 }, "Velocity Min", 1, 127, 70));

    params.push_back(std::make_unique<juce::AudioParameterInt>(
        juce::ParameterID { "velocityMax", 1 }, "Velocity Max", 1, 127, 110));

    params.push_back(std::make_unique<juce::AudioParameterInt>(
        juce::ParameterID { "octaveMin", 1 }, "Octave Min", -3, 3, -1));

    params.push_back(std::make_unique<juce::AudioParameterInt>(
        juce::ParameterID { "octaveMax", 1 }, "Octave Max", -3, 3, 1));

    params.push_back(std::make_unique<juce::AudioParameterInt>(
        juce::ParameterID { "patternLength", 1 }, "Pattern Length (beats)", 1, 64, 8));

    return { params.begin(), params.end() };
}

MidiGeneratorAudioProcessor::MidiGeneratorAudioProcessor()
    : AudioProcessor(BusesProperties()),
      apvts(*this, nullptr, "PARAMS", createParameterLayout())
{
    for (auto& id : paramIdsThatTriggerRegeneration())
        apvts.addParameterListener(id, this);

    triggerGeneration();
}

MidiGeneratorAudioProcessor::~MidiGeneratorAudioProcessor()
{
    for (auto& id : paramIdsThatTriggerRegeneration())
        apvts.removeParameterListener(id, this);
}

void MidiGeneratorAudioProcessor::parameterChanged(const juce::String&, float)
{
    triggerGeneration();
}

GenerationParams MidiGeneratorAudioProcessor::collectParams() const
{
    GenerationParams p;
    p.rootNote = (int) apvts.getRawParameterValue("rootNote")->load();
    p.scaleIndex = (int) apvts.getRawParameterValue("scale")->load();
    p.density = apvts.getRawParameterValue("density")->load();
    p.intensity = apvts.getRawParameterValue("intensity")->load();
    p.velocityMin = (int) apvts.getRawParameterValue("velocityMin")->load();
    p.velocityMax = (int) apvts.getRawParameterValue("velocityMax")->load();
    p.octaveMin = (int) apvts.getRawParameterValue("octaveMin")->load();
    p.octaveMax = (int) apvts.getRawParameterValue("octaveMax")->load();
    p.patternLengthBeats = (int) apvts.getRawParameterValue("patternLength")->load();
    return p;
}

void MidiGeneratorAudioProcessor::triggerGeneration()
{
    engine.requestGeneration(collectParams());
}

void MidiGeneratorAudioProcessor::prepareToPlay(double, int)
{
    activeNotes.clear();
    lastPpqPosition = 0.0;
    wasPlaying = false;
}

void MidiGeneratorAudioProcessor::releaseResources()
{
}

bool MidiGeneratorAudioProcessor::isBusesLayoutSupported(const BusesLayout&) const
{
    return true; // pure MIDI effect: no audio buses to validate
}

void MidiGeneratorAudioProcessor::flushAllNotesOff(juce::MidiBuffer& midi, int sampleOffset)
{
    for (auto& n : activeNotes)
        midi.addEvent(juce::MidiMessage::noteOff(n.channel, n.pitch), sampleOffset);
    activeNotes.clear();
}

void MidiGeneratorAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midiMessages)
{
    juce::ScopedNoDenormals noDenormals;
    buffer.clear();
    midiMessages.clear();

    const int numSamples = buffer.getNumSamples();
    if (numSamples <= 0)
        return;

    double bpm = 120.0;
    double blockStartBeat = lastPpqPosition;
    bool isPlaying = true;

    if (auto* playHead = getPlayHead())
    {
        auto posInfo = playHead->getPosition();
        if (posInfo.hasValue())
        {
            if (posInfo->getBpm().hasValue())
                bpm = *posInfo->getBpm();
            isPlaying = posInfo->getIsPlaying();
            if (posInfo->getPpqPosition().hasValue())
                blockStartBeat = *posInfo->getPpqPosition();
        }
    }

    if (wasPlaying && ! isPlaying)
        flushAllNotesOff(midiMessages, 0);

    if (isPlaying && blockStartBeat + 1.0e-6 < lastPpqPosition)
        flushAllNotesOff(midiMessages, 0); // host looped or rewound

    wasPlaying = isPlaying;
    lastKnownBeat.store(blockStartBeat);

    if (! isPlaying)
    {
        lastPpqPosition = blockStartBeat;
        return;
    }

    const double sr = getSampleRate() > 0.0 ? getSampleRate() : 44100.0;
    const double beatsPerSample = bpm / 60.0 / sr;
    const double blockEndBeat = blockStartBeat + (double) numSamples * beatsPerSample;

    auto pattern = engine.getCurrentPattern();
    const int patternLen = juce::jmax(1, pattern->lengthBeats);

    auto beatToSample = [&](double beat) -> int
    {
        return juce::jlimit(0, numSamples - 1,
                             (int) std::round((beat - blockStartBeat) / beatsPerSample));
    };

    const int loopStart = (int) std::floor(blockStartBeat / (double) patternLen);
    const int loopEnd = (int) std::floor((blockEndBeat - 1.0e-9) / (double) patternLen);

    auto scheduleLayer = [&](const std::vector<GeneratedNote>& layerNotes, int channel)
    {
        for (int loopIndex = loopStart; loopIndex <= loopEnd; ++loopIndex)
        {
            const double loopOrigin = (double) loopIndex * (double) patternLen;
            for (auto& note : layerNotes)
            {
                const double absStart = loopOrigin + note.startBeat;
                if (absStart < blockStartBeat || absStart >= blockEndBeat)
                    continue;

                const int sampleOffset = beatToSample(absStart);
                midiMessages.addEvent(juce::MidiMessage::noteOn(channel, note.pitch, (juce::uint8) note.velocity),
                                       sampleOffset);
                activeNotes.push_back({ note.pitch, channel, absStart + note.lengthBeats });
            }
        }
    };

    scheduleLayer(pattern->notes, 1);
    scheduleLayer(pattern->chordNotes, 2);

    for (size_t i = activeNotes.size(); i-- > 0;)
    {
        auto& n = activeNotes[i];
        if (n.offBeat >= blockStartBeat && n.offBeat < blockEndBeat)
        {
            midiMessages.addEvent(juce::MidiMessage::noteOff(n.channel, n.pitch), beatToSample(n.offBeat));
            activeNotes.erase(activeNotes.begin() + (long) i);
        }
    }

    lastPpqPosition = blockEndBeat;
}

bool MidiGeneratorAudioProcessor::writePatternToMidiFile(const juce::File& destination) const
{
    auto pattern = engine.getCurrentPattern();
    if (pattern == nullptr)
        return false;

    constexpr int ticksPerQuarterNote = 960;
    constexpr int microsecondsPerQuarterNoteAt120Bpm = 500000;

    juce::MidiFile midiFile;
    midiFile.setTicksPerQuarterNote(ticksPerQuarterNote);

    juce::MidiMessageSequence tempoTrack;
    tempoTrack.addEvent(juce::MidiMessage::tempoMetaEvent(microsecondsPerQuarterNoteAt120Bpm));
    midiFile.addTrack(tempoTrack);

    auto layerToTrack = [&](const std::vector<GeneratedNote>& layerNotes, int channel)
    {
        juce::MidiMessageSequence track;
        for (auto& n : layerNotes)
        {
            auto on = juce::MidiMessage::noteOn(channel, n.pitch, (juce::uint8) n.velocity);
            on.setTimeStamp(n.startBeat * (double) ticksPerQuarterNote);
            track.addEvent(on);

            auto off = juce::MidiMessage::noteOff(channel, n.pitch);
            off.setTimeStamp((n.startBeat + n.lengthBeats) * (double) ticksPerQuarterNote);
            track.addEvent(off);
        }
        track.updateMatchedPairs();
        midiFile.addTrack(track);
    };

    layerToTrack(pattern->notes, 1);
    layerToTrack(pattern->chordNotes, 2);

    juce::TemporaryFile tempFile(destination);
    {
        juce::FileOutputStream stream(tempFile.getFile());
        if (! stream.openedOk() || ! midiFile.writeTo(stream))
            return false;
    }
    return tempFile.overwriteTargetFileWithTemporary();
}

juce::AudioProcessorEditor* MidiGeneratorAudioProcessor::createEditor()
{
    return new MidiGeneratorAudioProcessorEditor(*this);
}

void MidiGeneratorAudioProcessor::getStateInformation(juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    std::unique_ptr<juce::XmlElement> xml(state.createXml());
    copyXmlToBinary(*xml, destData);
}

void MidiGeneratorAudioProcessor::setStateInformation(const void* data, int sizeInBytes)
{
    std::unique_ptr<juce::XmlElement> xml(getXmlFromBinary(data, sizeInBytes));
    if (xml != nullptr && xml->hasTagName(apvts.state.getType()))
        apvts.replaceState(juce::ValueTree::fromXml(*xml));
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new MidiGeneratorAudioProcessor();
}
