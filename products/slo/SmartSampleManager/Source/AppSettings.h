#pragma once

#include <JuceHeader.h>

// Persistent user settings (window size, last-used folders, etc.) --
// mission section 2's "persistent user settings" / "professional
// application lifecycle". Backed by juce::PropertiesFile, which JUCE
// already resolves to the correct per-OS app-data location, so nothing
// platform-specific needs handling here.
//
// A process-wide singleton (not per-editor-instance) so settings stay
// consistent across DAW-hosted and Standalone launches of the same install,
// and so a future preferences dialog has one place to read/write from.
class AppSettings {
public:
    static AppSettings& getInstance();

    juce::PropertiesFile& getProps() { return *props; }

    JUCE_DECLARE_NON_COPYABLE(AppSettings)

private:
    AppSettings();

    std::unique_ptr<juce::PropertiesFile> props;
};
