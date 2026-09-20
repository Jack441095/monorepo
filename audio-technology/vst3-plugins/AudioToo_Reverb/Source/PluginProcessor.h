/*
  ==============================================================================
    AudioToo_Reverb — JUCE VST3 & Audio Unit (AU) Plugin Header
    Encapsulates native C++ Schroeder-Moorer Reverb kernel for DAWs.
  ==============================================================================
*/

#pragma once

#include <JuceHeader.h>
#include <vector>

// Forward declaration of native schroeder_reverb kernel function
extern "C" {
    void schroeder_reverb(
        const double* left, const double* right, std::size_t n,
        int pre_delay_samples, double room_size, double decay_time, double damping, double wet_dry, double sample_rate,
        double* out_l, double* out_r);
}

class AudioTooReverbAudioProcessor : public juce::AudioProcessor
{
public:
    AudioTooReverbAudioProcessor();
    ~AudioTooReverbAudioProcessor() override;

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
    double getTailLengthSeconds() const override { return 4.0; }

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
    std::vector<double> outLDouble;
    std::vector<double> outRDouble;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AudioTooReverbAudioProcessor)
};
