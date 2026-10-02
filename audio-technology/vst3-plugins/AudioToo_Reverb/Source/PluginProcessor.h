/*
  ==============================================================================
    AudioToo_Reverb — JUCE VST3 & Audio Unit (AU) Plugin Header
    Encapsulates native C++ Schroeder-Moorer Reverb kernel for DAWs.
  ==============================================================================
*/

#pragma once

#include <JuceHeader.h>
#include <vector>

// The native kernel, included rather than forward-declared: the streaming
// entry point needs SchroederReverbState by value as a member, and that
// struct holds the comb, all-pass, pre-delay and spread rings. The header
// pulls in nothing but <cstddef> and <vector>, so it is safe next to
// JuceHeader.
#include "../../../audio-analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.h"

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

    // Survives processBlock. The kernel's own batch entry point starts every
    // call from silence, so at a 128-512 sample host block size it skipped
    // every comb (the shortest delay is 1395 samples at room_size 0.5) and
    // left the wet path silent; this is what carries that 12.7-31.6 ms of
    // history from one block to the next.
    SchroederReverbState reverbState;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AudioTooReverbAudioProcessor)
};
