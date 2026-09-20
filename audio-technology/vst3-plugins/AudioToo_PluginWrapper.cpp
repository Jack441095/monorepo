/*
 * AudioToo_PluginWrapper.cpp — JUCE VST3 & Audio Unit (AU) C++ Plugin Wrapper.
 * Wraps AutoMix's zero-allocation native C++ Schroeder-Moorer Reverb kernel for DAWs.
 */

#include <JuceHeader.h>
#include "AudioToo_DSP.h"

class AudioTooReverbProcessor : public juce::AudioProcessor {
public:
    AudioTooReverbProcessor()
        : AudioProcessor(BusesProperties()
            .withInput("Input", juce::AudioChannelSet::stereo(), true)
            .withOutput("Output", juce::AudioChannelSet::stereo(), true))
    {
        addParameter(roomSizeParam = new juce::AudioParameterFloat({"roomSize", 1}, "Room Size", 0.0f, 1.0f, 0.5f));
        addParameter(decayTimeParam = new juce::AudioParameterFloat({"decayTime", 1}, "Decay Time (s)", 0.1f, 10.0f, 1.5f));
        addParameter(dampingParam = new juce::AudioParameterFloat({"damping", 1}, "Damping", 0.0f, 1.0f, 0.3f));
        addParameter(wetDryParam = new juce::AudioParameterFloat({"wetDry", 1}, "Wet/Dry Mix", 0.0f, 1.0f, 0.3f));
    }

    ~AudioTooReverbProcessor() override = default;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override {
        currentSampleRate = sampleRate;
    }

    void releaseResources() override {}

    bool isBusesLayoutSupported(const BusesLayout& layouts) const override {
        if (layouts.getMainOutputChannelSet() != juce::AudioChannelSet::mono()
         && layouts.getMainOutputChannelSet() != juce::AudioChannelSet::stereo())
            return false;
        return layouts.getMainOutputChannelSet() == layouts.getMainInputChannelSet();
    }

    void processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midiMessages) override {
        juce::ScopedNoDenormals noDenormals;
        const int numSamples = buffer.getNumSamples();
        const int numChannels = buffer.getNumChannels();

        if (numChannels < 2 || numSamples == 0) return;

        const float* leftIn = buffer.getReadPointer(0);
        const float* rightIn = buffer.getReadPointer(1);

        // Convert float to double buffers for zero-allocation C++ kernel
        leftDouble.resize(numSamples);
        rightDouble.resize(numSamples);
        outLeftDouble.resize(numSamples);
        outRightDouble.resize(numSamples);

        for (int i = 0; i < numSamples; ++i) {
            leftDouble[i] = static_cast<double>(leftIn[i]);
            rightDouble[i] = static_cast<double>(rightIn[i]);
        }

        schroeder_reverb(
            leftDouble.data(), rightDouble.data(), static_cast<std::size_t>(numSamples),
            0, roomSizeParam->get(), decayTimeParam->get(), dampingParam->get(), wetDryParam->get(), currentSampleRate,
            outLeftDouble.data(), outRightDouble.data()
        );

        float* leftOut = buffer.getWritePointer(0);
        float* rightOut = buffer.getWritePointer(1);

        for (int i = 0; i < numSamples; ++i) {
            leftOut[i] = static_cast<float>(outLeftDouble[i]);
            rightOut[i] = static_cast<float>(outRightDouble[i]);
        }
    }

    juce::AudioProcessorEditor* createEditor() override { return new juce::GenericAudioProcessorEditor(*this); }
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "AudioToo Reverb"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return decayTimeParam->get(); }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int index) override {}
    const juce::String getProgramName(int index) override { return {}; }
    void changeProgramName(int index, const juce::String& newName) override {}

    void getStateInformation(juce::MemoryBlock& destData) override {}
    void setStateInformation(const void* data, int sizeInBytes) override {}

private:
    double currentSampleRate = 44100.0;
    juce::AudioParameterFloat* roomSizeParam;
    juce::AudioParameterFloat* decayTimeParam;
    juce::AudioParameterFloat* dampingParam;
    juce::AudioParameterFloat* wetDryParam;

    std::vector<double> leftDouble;
    std::vector<double> rightDouble;
    std::vector<double> outLeftDouble;
    std::vector<double> outRightDouble;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AudioTooReverbProcessor)
};

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() {
    return new AudioTooReverbProcessor();
}
