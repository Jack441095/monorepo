/*
  ==============================================================================
    AudioToo_Limiter — JUCE VST3 & Audio Unit (AU) Plugin Implementation
  ==============================================================================
*/

#include "PluginProcessor.h"
#include <cmath>

AudioTooLimiterAudioProcessor::AudioTooLimiterAudioProcessor()
    : AudioProcessor(BusesProperties()
                     .withInput("Input", juce::AudioChannelSet::stereo(), true)
                     .withOutput("Output", juce::AudioChannelSet::stereo(), true)),
      apvts(*this, nullptr, "Parameters", createParameterLayout())
{
    registerTransportChangeListener(this);
}

AudioTooLimiterAudioProcessor::~AudioTooLimiterAudioProcessor()
{
    unregisterAllTransportChangeListeners(this);
}

// The carried look-ahead backlog is up to 10 ms of already-processed audio, so
// without this a transport restart would play the tail of the previous take out
// of the delay line. Safe to reset here: the envelope re-attacks on the first
// hot sample of the new take either way, and a stop is silence regardless.
void AudioTooLimiterAudioProcessor::transportChanged()
{
    resetLimiterState();
}

juce::AudioProcessorValueTreeState::ParameterLayout AudioTooLimiterAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;

    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("threshold_db", 1), "Threshold (dB)", juce::NormalisableRange<float>(-30.0f, 0.0f, 0.1f), -6.0f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("ceiling_db", 1), "Ceiling (dB)", juce::NormalisableRange<float>(-12.0f, 0.0f, 0.1f), -0.1f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("release_ms", 1), "Release (ms)", juce::NormalisableRange<float>(1.0f, 500.0f, 1.0f), 50.0f));
    params.push_back(std::make_unique<juce::AudioParameterFloat>(
        juce::ParameterID("lookahead_ms", 1), "Look-Ahead (ms)", juce::NormalisableRange<float>(0.5f, 10.0f, 0.5f), 5.0f));

    return { params.begin(), params.end() };
}

void AudioTooLimiterAudioProcessor::prepareToPlay(double sampleRate, int samplesPerBlock)
{
    inLDouble.resize(static_cast<std::size_t>(samplesPerBlock));
    inRDouble.resize(static_cast<std::size_t>(samplesPerBlock));
    outLDouble.resize(static_cast<std::size_t>(samplesPerBlock));
    outRDouble.resize(static_cast<std::size_t>(samplesPerBlock));

    // Allocated here rather than in the constructor: the kernel's deque grows
    // on first use, and doing that on the audio thread is how you get a dropout
    // the first time a user nudges the look-ahead knob.
    if (limiterState == nullptr)
        limiterState = limiter_stereo_state_create();
    else
        limiter_stereo_state_reset(limiterState);

    const float lookaheadMs = apvts.getRawParameterValue("lookahead_ms")->load();
    const int latencySamples = static_cast<int>((lookaheadMs / 1000.0f) * sampleRate);
    setLatencySamples(latencySamples);
}

void AudioTooLimiterAudioProcessor::resetLimiterState()
{
    if (limiterState != nullptr)
        limiter_stereo_state_reset(limiterState);
}

void AudioTooLimiterAudioProcessor::releaseResources()
{
    limiter_stereo_state_destroy(limiterState);
    limiterState = nullptr;
}

bool AudioTooLimiterAudioProcessor::isBusesLayoutSupported(const BusesLayout& layouts) const
{
    if (layouts.getMainOutputChannelSet() != juce::AudioChannelSet::stereo())
        return false;
    if (layouts.getMainInputChannelSet() != juce::AudioChannelSet::stereo())
        return false;
    return true;
}

void AudioTooLimiterAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midiMessages)
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
    const float thresholdDb = apvts.getRawParameterValue("threshold_db")->load();
    const float ceilingDb = apvts.getRawParameterValue("ceiling_db")->load();
    const float releaseMs = apvts.getRawParameterValue("release_ms")->load();
    const float lookaheadMs = apvts.getRawParameterValue("lookahead_ms")->load();

    const double inputGain = std::pow(10.0, -thresholdDb / 20.0);
    const double ceilingLin = std::pow(10.0, ceilingDb / 20.0);
    const int lookaheadSamples = std::max(1, static_cast<int>((lookaheadMs / 1000.0) * sampleRate));
    const double alphaRel = std::exp(-1.0 / ((releaseMs / 1000.0) * sampleRate));

    // One stereo-linked call, not one per channel. The gain comes from
    // max(|L|,|R|) and is applied to both, so the image survives gain
    // reduction instead of the two sides drifting apart under an envelope
    // each channel computed for itself.
    const std::size_t produced = limiter_gain_envelope_stereo(
        limiterState,
        inLDouble.data(), inRDouble.data(), static_cast<std::size_t>(numSamples),
        inputGain, ceilingLin, alphaRel, lookaheadSamples,
        nullptr, outLDouble.data(), outRDouble.data()
    );

    float* leftOut = buffer.getWritePointer(0);
    float* rightOut = buffer.getWritePointer(1);

    for (std::size_t i = 0; i < produced; ++i) {
        leftOut[i] = static_cast<float>(outLDouble[i]);
        rightOut[i] = static_cast<float>(outRDouble[i]);
    }

    // The first block after prepareToPlay is short by the look-ahead window: the
    // kernel has not seen the samples that would complete those envelopes yet.
    // We declare that delay via setLatencySamples, so silence here is the host's
    // accounting, not dropped audio.
    for (std::size_t i = produced; i < static_cast<std::size_t>(numSamples); ++i) {
        leftOut[i] = 0.0f;
        rightOut[i] = 0.0f;
    }
}

juce::AudioProcessorEditor* AudioTooLimiterAudioProcessor::createEditor()
{
    return new juce::GenericAudioProcessorEditor(*this);
}

void AudioTooLimiterAudioProcessor::getStateInformation(juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    std::unique_ptr<juce::XmlElement> xml(state.createXml());
    copyXmlToBinary(*xml, destData);
}

void AudioTooLimiterAudioProcessor::setStateInformation(const void* data, int sizeInBytes)
{
    std::unique_ptr<juce::XmlElement> xmlState(getXmlFromBinary(data, sizeInBytes));
    if (xmlState != nullptr && xmlState->hasTagName(apvts.state.getType()))
        apvts.replaceState(juce::ValueTree::fromXml(*xmlState));
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AudioTooLimiterAudioProcessor();
}
