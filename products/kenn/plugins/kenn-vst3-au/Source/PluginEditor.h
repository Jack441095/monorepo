#pragma once
#include <JuceHeader.h>
#include "PluginProcessor.h"

class KENNMixAssistantAudioProcessorEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit KENNMixAssistantAudioProcessorEditor(KENNMixAssistantAudioProcessor&);
    void paint(juce::Graphics&) override;
    void resized() override;
private:
    void timerCallback() override;
    juce::String formatLiveProposal(const juce::var& proposal, const juce::String& heading, bool isUndo) const;
    void clearPendingLiveProposal(const juce::String& message);
    void beginLiveRequest(const juce::String& stage, const juce::String& detail);
    void finishLiveRequest(const juce::String& stage, const juce::String& detail);
    void failLiveRequest(const juce::String& detail);
    bool liveRequestBusy(const juce::String& attemptedStage = {});
    KENNMixAssistantAudioProcessor& kennProcessor;
    juce::Label heading, metrics, guidance, status, actionAudit;
    juce::Label endpointLabel, sessionLabel;
    juce::Label modeLabel;
    juce::TextButton localReviewButton { "Local Mix Check" };
    juce::TextButton exportButton { "Send Mix Review to KENN" };
    juce::TextButton askButton { "Ask KENN" };
    juce::TextButton liveCommandButton { "Control Live" };
    juce::TextButton inspectLiveControlsButton { "Show Live Controls" };
    juce::TextButton automixButton { "Choose Stems & Start AutoMix" };
    juce::TextButton applySafeTargetButton { "Apply Safe Target" };
    juce::TextButton undoTargetButton { "Undo Target" };
    juce::TextButton copyAutoMixLinkButton { "Copy AutoMix Download Link" };
    juce::TextButton saveConnectionButton { "Save Connection" };
    juce::TextButton testConnectionButton { "Test" };
    juce::TextButton confirmLiveProposalButton { "Confirm Live Proposal" };
    juce::TextButton cancelLiveProposalButton { "Cancel Proposal" };
    juce::TextButton undoLiveCommandButton { "Undo Last Live Change" };
    juce::TextButton masterSpotifyButton { "Master for Spotify" };
    juce::TextButton matchRefButton { "Match Reference" };
    juce::TextButton autoGainTrimButton { "Auto-Trim Headroom" };
    juce::TextButton arrangeTransitionsButton { "Audit Arrangement" };
    juce::TextButton packageStemsButton { "Package Stems" };
    juce::TextEditor endpointEditor, sessionEditor, questionEditor, answerViewer;
    juce::TextEditor liveProposalViewer;
    juce::ComboBox modeSelector;
    juce::ToggleButton liveContextToggle { "Publish live context to local KENN every 8 seconds (no audio)" };
    juce::Slider targetLufs;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> targetAttachment;
    std::unique_ptr<juce::AudioProcessorValueTreeState::ComboBoxAttachment> modeAttachment;
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> liveContextAttachment;
    std::unique_ptr<juce::FileChooser> stemChooser;
    juce::String activeAutoMixJob;
    juce::String completedAutoMixJob;
    int pollTicks = 0;
    int paramSyncTicks = 0;
    std::atomic_bool liveRequestInFlight { false };
    std::atomic_bool liveRequestTimedOut { false };
    juce::Time liveRequestStarted;
    juce::Time liveResponseReceived;
    juce::String liveRequestStage { "idle" };
    float targetBeforeProposal = -14.0f;
    bool hasTargetUndo = false;
    juce::var pendingLiveProposal;
    juce::var pendingLiveReceipt;
    bool pendingLiveIsUndo = false;
    bool hasLiveUndo = false;
    std::unique_ptr<juce::WebBrowserComponent> webView;
    bool serverOnline = false;
    bool webViewLoaded = false;
    int serverCheckTicks = 0;
};
