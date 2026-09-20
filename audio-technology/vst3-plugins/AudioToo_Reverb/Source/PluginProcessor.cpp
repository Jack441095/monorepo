/*
  ==============================================================================
    AudioToo_Reverb — JUCE VST3 & Audio Unit (AU) Plugin Implementation
  ==============================================================================
*/

#include "PluginProcessor.h"

AudioTooReverbAudioProcessor::AudioTooReverbAudioProcessor()
    : AudioProcessor(BusesProperties()
                     .withInput("Input", juce::AudioChannelSet::stereo(), true)
                     .withOutput("Output", juce::AudioChannelSet::stereo(), true)),
      apvts(*this, nullptr, "Parameters", createParameterLayout())
{
}

AudioTooReverbAudioProcessor::~AudioTooReverbAudioProcessor()
{
}

juce::AudioProcessorValueTreeState::ParameterLayout AudioTooReverbAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;

    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("room_size", 1), "Room Size", juce::NormalisableRange<float>(0.0f, 1.0f, 0.01f), 0.5f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("decay_time", 1), "Decay Time (s)", juce::NormalisableRange<float>(0.1f, 10.0f, 0.1f), 2.0f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("damping", 1), "Damping", juce::NormalisableRange<float>(0.0f, 1.0f, 0.01f), 0.3f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("pre_delay_ms", 1), "Pre-Delay (ms)", juce::NormalisableRange<float>(0.0f, 200.0f, 1.0f), 10.0f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("wet_dry", 1), "Wet/Dry", juce::NormalisableRange<float>(0.0f, 1.0f, 0.01f), 0.35f));

    return { params.begin(), params.end() };
}

void AudioTooReverbAudioProcessor::prepareToPlay(double sampleRate, int samplesPerBlock)
{
    inLDouble.resize(static_cast<std::size_t>(samplesPerBlock));
    inRDouble.resize(static_cast<std::size_t>(samplesPerBlock));
    outLDouble.resize(static_cast<std::size_t>(samplesPerBlock));
    outRDouble.resize(static_cast<std::size_t>(samplesPerBlock));
}

void AudioTooReverbAudioProcessor::releaseResources()
{
}

bool AudioTooReverbAudioProcessor::isBusesLayoutSupported(const BusesLayout& layouts) const
{
    if (layouts.getMainOutputChannelSet() != juce::AudioChannelSet::stereo())
        return false;
    if (layouts.getMainInputChannelSet() != juce::AudioChannelSet::stereo())
        return false;
    return true;
}

void AudioTooReverbAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midiMessages)
{
    juce::ScopedNoDenormals noDenormals;
    const int totalNumInputChannels  = getTotalNumInputChannels();
    const int totalNumOutputChannels = getTotalNumOutputChannels();

    for (int i = totalNumInputChannels; i < totalNumOutputChannels; ++i)
        buffer.clear(i, 0, buffer.getNumSamples());

    const int numSamples = buffer.getNumSamples();
    if (numSamples == 0 || totalNumInputChannels < 2) return;

    if (inLDouble.size() < static_cast<std::size_t>(numSamples)) {
        inLDouble.resize(numSamples);
        inRDouble.resize(numSamples);
        outLDouble.resize(numSamples);
        outRDouble.resize(numSamples);
    }

    const float* leftIn = buffer.getReadPointer(0);
    const float* rightIn = buffer.getReadPointer(1);

    for (int i = 0; i < numSamples; ++i) {
        inLDouble[i] = static_cast<double>(leftIn[i]);
        inRDouble[i] = static_cast<double>(rightIn[i]);
    }

    const double sampleRate = getSampleRate();
    const float roomSize = apvts.getRawParameterValue("room_size")->load();
    const float decayTime = apvts.getRawParameterValue("decay_time")->load();
    const float damping = apvts.getRawParameterValue("damping")->load();
    const float preDelayMs = apvts.getRawParameterValue("pre_delay_ms")->load();
    const float wetDry = apvts.getRawParameterValue("wet_dry")->load();

    const int preDelaySamples = static_cast<int>((preDelayMs / 1000.0f) * sampleRate);

    schroeder_reverb(
        inLDouble.data(), inRDouble.data(), static_cast<std::size_t>(numSamples),
        preDelaySamples, static_cast<double>(roomSize), static_cast<double>(decayTime),
        static_cast<double>(damping), static_cast<double>(wetDry), sampleRate,
        outLDouble.data(), outRDouble.data()
    );

    float* leftOut = buffer.getWritePointer(0);
    float* rightOut = buffer.getWritePointer(1);

    for (int i = 0; i < numSamples; ++i) {
        leftOut[i] = static_cast<float>(outLDouble[i]);
        rightOut[i] = static_cast<float>(outRDouble[i]);
    }
}

juce::AudioProcessorEditor* AudioTooReverbAudioProcessor::createEditor()
{
    return new juce::GenericAudioProcessorEditor(*this);
}

void AudioTooReverbAudioProcessor::getStateInformation(juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    std::unique_ptr<juce::XmlElement> xml(state.createXml());
    copyXmlToBinary(*xml, destData);
}

void AudioTooReverbAudioProcessor::setStateInformation(const void* data, int sizeInBytes)
{
    std::unique_ptr<juce::XmlElement> xmlState(getXmlFromBinary(data, sizeInBytes));
    if (xmlState != nullptr && xmlState->hasTagName(apvts.state.getType()))
        apvts.replaceState(juce::ValueTree::fromXml(*xmlState));
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AudioTooReverbAudioProcessor();
}
