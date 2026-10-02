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
    // Mono batch envelope, kept for the offline/numpy paths that hold this
    // kernel to bit-parity with the Python limiter. NOT for processBlock: it
    // is stateless, so calling it per channel gave L and R independent
    // envelopes and reset the release one-pole at every block boundary.
    void limiter_gain_envelope(
        const double* x, std::size_t n,
        double input_gain, double ceiling_lin, double alpha_rel, int L,
        double* gain_out, double* audio_out);

    // Stereo-linked streaming envelope. One gain per sample from
    // max(|L|,|R|), with the release and the look-ahead window carried in
    // `state` across calls.
    struct LimiterStereoState;

    LimiterStereoState* limiter_stereo_state_create(void);
    void limiter_stereo_state_destroy(LimiterStereoState* state);
    void limiter_stereo_state_reset(LimiterStereoState* state);

    std::size_t limiter_gain_envelope_stereo(
        LimiterStereoState* state,
        const double* left, const double* right, std::size_t n,
        double input_gain, double ceiling_lin, double alpha_rel, int L,
        double* gain_out, double* out_left, double* out_right);

    std::size_t limiter_stereo_state_flush(
        LimiterStereoState* state,
        double* gain_out, double* out_left, double* out_right);
}

class AudioTooLimiterAudioProcessor : public juce::AudioProcessor,
                                     private juce::TransportChangeListener
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

    // Drops the release one-pole and the look-ahead backlog. Called from
    // prepareToPlay and on transport change, the two points where the signal
    // genuinely restarted rather than continued.
    void resetLimiterState();

    void transportChanged() override;

    std::vector<double> inLDouble;
    std::vector<double> inRDouble;
    std::vector<double> outLDouble;
    std::vector<double> outRDouble;

    LimiterStereoState* limiterState = nullptr;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AudioTooLimiterAudioProcessor)
};
