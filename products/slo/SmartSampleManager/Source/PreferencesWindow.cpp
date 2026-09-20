#include "PreferencesWindow.h"
#include "Licensing/LicenseManager.h"
#include "AppLogger.h"
#include "DesignTokens.h"

namespace {
juce::String describeStatus(Licensing::Status s) {
    switch (s) {
        case Licensing::Status::notActivated:     return "Not Activated";
        case Licensing::Status::active:            return "Active";
        case Licensing::Status::needsRevalidation: return "Needs Revalidation (offline grace period expired)";
        case Licensing::Status::invalid:           return "Invalid";
    }
    return "Unknown";
}

juce::String formatBytes(juce::int64 bytes) {
    if (bytes < 1024) return juce::String(bytes) + " B";
    if (bytes < 1024 * 1024) return juce::String(bytes / 1024.0, 1) + " KB";
    return juce::String(bytes / (1024.0 * 1024.0), 1) + " MB";
}
}

PreferencesComponent::PreferencesComponent(SmartSampleManagerAudioProcessor& processor)
    : audioProcessor(processor)
{
    addAndMakeVisible(versionLabel);
    versionLabel.setText("SLO -- version 1.0.0 (dev build)", juce::dontSendNotification);
    versionLabel.setFont(juce::Font(juce::FontOptions().withHeight(14.0f).withStyle("Bold")));
    versionLabel.setColour(juce::Label::textColourId, Tokens::foreground);

    addAndMakeVisible(licenseGroup);
    licenseGroup.setText("LICENSE");
    licenseGroup.setColour(juce::GroupComponent::outlineColourId, Tokens::border);
    licenseGroup.setColour(juce::GroupComponent::textColourId, Tokens::mutedDim);

    addAndMakeVisible(licenseStatusLabel);
    licenseStatusLabel.setFont(juce::Font(juce::FontOptions().withHeight(13.0f)));
    licenseStatusLabel.setColour(juce::Label::textColourId, Tokens::foreground);

    addAndMakeVisible(licenseDetailLabel);
    licenseDetailLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    licenseDetailLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    licenseDetailLabel.setJustificationType(juce::Justification::topLeft);
    licenseDetailLabel.setMinimumHorizontalScale(1.0f);

    addAndMakeVisible(cacheGroup);
    cacheGroup.setText("SAMPLE CACHE");
    cacheGroup.setColour(juce::GroupComponent::outlineColourId, Tokens::border);
    cacheGroup.setColour(juce::GroupComponent::textColourId, Tokens::mutedDim);

    addAndMakeVisible(cacheLocationLabel);
    cacheLocationLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    cacheLocationLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    addAndMakeVisible(cacheSizeLabel);
    cacheSizeLabel.setFont(juce::Font(juce::FontOptions().withHeight(13.0f)));
    cacheSizeLabel.setColour(juce::Label::textColourId, Tokens::foreground);

    addAndMakeVisible(clearCacheButton);
    clearCacheButton.setButtonText("CLEAR CACHE");
    clearCacheButton.setColour(juce::TextButton::buttonColourId, Tokens::dangerSurface);
    clearCacheButton.setColour(juce::TextButton::textColourOffId, Tokens::danger);
    clearCacheButton.onClick = [this]() {
        juce::AlertWindow::showOkCancelBox(juce::MessageBoxIconType::WarningIcon,
            "Clear Sample Cache?",
            "This deletes the cached analysis data (BPM/key detection, embeddings) for every "
            "sample. Nothing on disk in your sample library is touched -- the next scan will "
            "just be slower, since everything gets reprocessed from scratch instead of hitting "
            "the cache.",
            "Clear Cache", "Cancel", this,
            juce::ModalCallbackFunction::create([this](int result) {
                if (result == 1) {
                    audioProcessor.getEngine().clearCache();
                    refreshCacheInfo();
                }
            }));
    };

    addAndMakeVisible(diagnosticsGroup);
    diagnosticsGroup.setText("DIAGNOSTICS");
    diagnosticsGroup.setColour(juce::GroupComponent::outlineColourId, Tokens::border);
    diagnosticsGroup.setColour(juce::GroupComponent::textColourId, Tokens::mutedDim);

    addAndMakeVisible(revealLogButton);
    revealLogButton.setButtonText("REVEAL LOG FILE");
    revealLogButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    revealLogButton.setColour(juce::TextButton::textColourOffId, Tokens::accentInteractive);
    revealLogButton.onClick = [this]() {
        auto logFile = AppLogger::getInstance().getLogFile();
        if (logFile.existsAsFile()) {
            logFile.revealToUser();
        } else {
            juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::WarningIcon,
                "No Log File", "No log file has been created yet this session.");
        }
    };

    refreshLicenseStatus();
    refreshCacheInfo();

    setSize(420, 380);
}

void PreferencesComponent::refreshLicenseStatus() {
    LicenseManager licenseManager;
    auto state = licenseManager.loadPersisted();

    licenseStatusLabel.setText("Status: " + describeStatus(state.status), juce::dontSendNotification);

    if (state.status == Licensing::Status::active || state.status == Licensing::Status::needsRevalidation) {
        juce::String detail;
        detail << "Tier: " << state.token.tier << "\n";
        detail << "Licensed to: " << state.token.customerEmail << "\n";
        detail << "Device ID: " << licenseManager.getDeviceId() << "\n";
        detail << (state.token.isPerpetual() ? "Perpetual license" : "Subscription/term license");
        licenseDetailLabel.setText(detail, juce::dontSendNotification);
    } else {
        licenseDetailLabel.setText(
            "No active license on this device. (Activation UI isn't wired up yet -- see "
            "licensing_server/README.md for the current state of the licensing backend.)",
            juce::dontSendNotification);
    }
}

void PreferencesComponent::refreshCacheInfo() {
    auto cacheFile = SampleManagerEngine::getCacheDbFile();
    cacheLocationLabel.setText(cacheFile.getFullPathName(), juce::dontSendNotification);

    juce::int64 totalBytes = cacheFile.existsAsFile() ? cacheFile.getSize() : 0;
    auto walFile = cacheFile.getSiblingFile(cacheFile.getFileName() + "-wal");
    if (walFile.existsAsFile()) totalBytes += walFile.getSize();

    cacheSizeLabel.setText("Cache size: " + formatBytes(totalBytes), juce::dontSendNotification);
}

void PreferencesComponent::resized() {
    auto area = getLocalBounds().reduced(16);

    versionLabel.setBounds(area.removeFromTop(24));
    area.removeFromTop(12);

    auto licenseArea = area.removeFromTop(100);
    licenseGroup.setBounds(licenseArea);
    auto licenseContent = licenseArea.reduced(12, 16);
    licenseStatusLabel.setBounds(licenseContent.removeFromTop(20));
    licenseContent.removeFromTop(4);
    licenseDetailLabel.setBounds(licenseContent);

    area.removeFromTop(12);

    auto cacheArea = area.removeFromTop(120);
    cacheGroup.setBounds(cacheArea);
    auto cacheContent = cacheArea.reduced(12, 16);
    cacheLocationLabel.setBounds(cacheContent.removeFromTop(16));
    cacheContent.removeFromTop(4);
    cacheSizeLabel.setBounds(cacheContent.removeFromTop(20));
    cacheContent.removeFromTop(8);
    clearCacheButton.setBounds(cacheContent.removeFromTop(28).removeFromLeft(140));

    area.removeFromTop(12);

    auto diagnosticsArea = area.removeFromTop(60);
    diagnosticsGroup.setBounds(diagnosticsArea);
    auto diagnosticsContent = diagnosticsArea.reduced(12, 16);
    revealLogButton.setBounds(diagnosticsContent.removeFromTop(28).removeFromLeft(160));
}

void showPreferencesDialog(SmartSampleManagerAudioProcessor& processor) {
    auto* content = new PreferencesComponent(processor);

    juce::DialogWindow::LaunchOptions options;
    options.content.setOwned(content);
    options.dialogTitle = "Preferences";
    options.dialogBackgroundColour = Tokens::background;
    options.escapeKeyTriggersCloseButton = true;
    options.useNativeTitleBar = true;
    options.resizable = false;

    options.launchAsync();
}
