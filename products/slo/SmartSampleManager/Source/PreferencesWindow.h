#pragma once

#include <JuceHeader.h>
#include "PluginProcessor.h"

// Preferences dialog content -- read-only license status (surfaces the
// Licensing/ scaffold in the UI for the first time; no activation flow
// wired up yet since there's no production backend to activate against),
// cache location/size, and a "Clear Cache" action for when a user needs to
// force a full rescan.
class PreferencesComponent : public juce::Component {
public:
    explicit PreferencesComponent(SmartSampleManagerAudioProcessor& processor);

    void resized() override;

private:
    SmartSampleManagerAudioProcessor& audioProcessor;

    juce::Label versionLabel;

    juce::GroupComponent licenseGroup;
    juce::Label licenseStatusLabel;
    juce::Label licenseDetailLabel;

    juce::GroupComponent cacheGroup;
    juce::Label cacheLocationLabel;
    juce::Label cacheSizeLabel;
    juce::TextButton clearCacheButton;

    juce::GroupComponent diagnosticsGroup;
    juce::TextButton revealLogButton;

    void refreshLicenseStatus();
    void refreshCacheInfo();

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(PreferencesComponent)
};

// Launches the preferences dialog as a standalone modal-ish DialogWindow.
void showPreferencesDialog(SmartSampleManagerAudioProcessor& processor);
