#include "AppLogger.h"

AppLogger& AppLogger::getInstance() {
    static AppLogger instance;
    return instance;
}

AppLogger::AppLogger() {
    fileLogger.reset(juce::FileLogger::createDateStampedLogger(
        "SmartSampleManager", "SmartSampleManager_", ".log",
        "Smart Sample Manager log started"));

    if (fileLogger != nullptr) {
        juce::Logger::setCurrentLogger(fileLogger.get());
    }
}

AppLogger::~AppLogger() {
    juce::Logger::setCurrentLogger(nullptr);
}

juce::File AppLogger::getLogFile() const {
    if (fileLogger != nullptr) {
        return fileLogger->getLogFile();
    }
    return {};
}

void AppLogger::write(const char* levelTag, const juce::String& message) {
    auto timestamp = juce::Time::getCurrentTime().formatted("%H:%M:%S");
    juce::String line = "[" + timestamp + "] [" + levelTag + "] " + message;

    if (fileLogger != nullptr) {
        // FileLogger::logMessage() already calls DBG(message) internally,
        // which mirrors to the console in debug builds -- no need to
        // duplicate that here.
        fileLogger->logMessage(line);
    }
}

void AppLogger::logInfo(const juce::String& message)    { write("INFO", message); }
void AppLogger::logWarning(const juce::String& message) { write("WARN", message); }
void AppLogger::logError(const juce::String& message)   { write("ERROR", message); }
void AppLogger::logDebug(const juce::String& message)   { write("DEBUG", message); }
