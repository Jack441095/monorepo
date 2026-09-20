/*
  ==============================================================================
    AudioToo_Limiter — JUCE VST3 & Audio Unit (AU) Plugin Header
    Encapsulates native C++ Look-Ahead Brickwall Limiter kernel for DAWs.
  ==============================================================================
*/

#pragma once

#include <JuceHeader.h>
#include <vector>

extern "C" {
    void limiter_gain_envelope(
        const double* x, std::size_t n,
        double input_gain, double ceiling_lin, double alpha_rel, int L,
        double* gain_out, double* audio_out);
}

class AudioTooLimiterAudioProcessor : public juce::AudioProcessor
{
public:
    AudioTooLimiterAudioProcessor();
    ~AudioTooLimiterAudioProcessor() override;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;

    bool isBusesLayoutSupported(const BusesLayout& layouts) const override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }

    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.1; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int index) override {}
    const juce::String getProgramName(int index) override { return {}; }
    void changeProgramName(int index, const juce::String& newName) override {}

    void getStateInformation(juce::MemoryBlock& destData) override;
    void setStateInformation(const void* data, int sizeInBytes) override;

    juce::AudioProcessorValueTreeState apvts;

private:
    juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    std::vector<double> inLDouble;
    std::vector<double> inRDouble;
    std::vector<double> gainLDouble;
    std::vector<double> gainRDouble;
    std::vector<double> outLDouble;
    std::vector<double> outRDouble;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AudioTooLimiterAudioProcessor)
};
