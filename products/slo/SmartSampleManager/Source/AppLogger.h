#pragma once

#include <JuceHeader.h>

// Structured logging (mission section 21): leveled, persisted to a
// dated log file in the OS-conventional logs location
// (~/Library/Logs/SmartSampleManager/ on macOS), rather than the scattered
// std::cout/std::cerr calls this codebase previously relied on. Also
// installs itself as JUCE's current Logger, so JUCE's own internal
// DBG/Logger::writeToLog calls land in the same file.
//
// Deliberately never logs credentials, license secrets, or auth tokens --
// see the licensing code, which never routes signature bytes or the raw
// signed token through here, only status strings.
class AppLogger {
public:
    static AppLogger& getInstance();

    void logInfo(const juce::String& message);
    void logWarning(const juce::String& message);
    void logError(const juce::String& message);
    void logDebug(const juce::String& message);

    // For a "Reveal Diagnostics" preferences action.
    juce::File getLogFile() const;

    JUCE_DECLARE_NON_COPYABLE(AppLogger)

private:
    AppLogger();
    ~AppLogger();

    void write(const char* levelTag, const juce::String& message);

    std::unique_ptr<juce::FileLogger> fileLogger;
};
