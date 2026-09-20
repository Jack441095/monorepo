#pragma once

#include <JuceHeader.h>
#include "MeterAnalyzer.h"

class KENNLiveContextPublisherThread;

class KENNMixAssistantAudioProcessor : public juce::AudioProcessor
{
public:
    KENNMixAssistantAudioProcessor();
    ~KENNMixAssistantAudioProcessor() override;
    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported(const BusesLayout& layouts) const override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }
    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }
    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return {}; }
    void changeProgramName(int, const juce::String&) override {}
    void getStateInformation(juce::MemoryBlock&) override;
    void setStateInformation(const void*, int) override;

    KENNMeterSnapshot meterSnapshot() const { const auto f = realtimeCore.snapshot(); return { f.peakDbfs, f.rmsDbfs, f.correlation, f.stereoWidth, f.crestDb, f.transientRatio, f.clippedSamples, f.sampleRate, f.analysedSamples }; }
    bool writeHandoffFile(juce::String& error) const;
    bool sendHandoffToKenn(juce::String& result) const;
    juce::String localDiagnosticSummary() const;
    bool askKenn(const juce::String& question, juce::String& result) const;
    bool inspectLiveControls(juce::String& result) const;
    bool planLiveCommand(const juce::String& command, juce::var& proposal, juce::String& result) const;
    bool confirmLiveCommand(const juce::var& proposal, juce::String& result) const;
    bool confirmLiveCommand(const juce::var& proposal, juce::var& receipt, juce::String& result) const;
    bool planLiveUndo(const juce::var& receipt, juce::var& proposal, juce::String& result) const;
    bool confirmLiveUndo(const juce::var& receipt, const juce::var& proposal, juce::var& undoReceipt, juce::String& result) const;
    bool requestSafeTargetProposal(float& proposedTarget, juce::String& result) const;
    bool testKennConnection(juce::String& result) const;
    bool startAutoMix(const juce::Array<juce::File>& stems, juce::String& result) const;
    bool fetchAutoMixStatus(const juce::String& jobId, juce::String& result, bool& complete) const;
    juce::String getAssistantMode() const;
    juce::String getKennEndpoint() const;
    juce::String getKennSessionId() const;
    bool setKennConnection(const juce::String& endpoint, const juce::String& sessionId, juce::String& error);
    void recordTargetAction(const juce::String& event, float before, float after, const juce::String& reason);
    juce::String latestTargetActionSummary() const;
    bool syncWebParameters();
    juce::AudioProcessorValueTreeState apvts;

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();
    juce::var handoffPayload() const;
    static bool validateLocalEndpoint(const juce::String& endpoint, juce::String& normalised, juce::String& error);
    AudioTooRealtimeCore realtimeCore;
    mutable juce::CriticalSection connectionLock;
    struct TargetActionLog { juce::String timestamp, event, reason; float before = 0.0f, after = 0.0f; };
    mutable juce::CriticalSection actionLogLock;
    juce::Array<TargetActionLog> targetActionLog;
    juce::String kennEndpoint { "http://127.0.0.1:8090" };
    juce::String kennSessionId { "plugin-local" };
    std::unique_ptr<KENNLiveContextPublisherThread> liveContextPublisher;
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(KENNMixAssistantAudioProcessor)
};
