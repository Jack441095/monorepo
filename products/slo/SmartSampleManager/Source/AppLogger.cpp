#include "AppLogger.h"

AppLogger& AppLogger::getInstance() {
    static AppLogger instance;
    return instance;
}

AppLogger::AppLogger() {
    fileLogger.reset(juce::FileLogger::createDateStampedLogger(
        "SmartSampleManager", "SmartSampleManager_", ".log",
        "Smart Sample Manager log started"));

    // Deliberately NOT installed as juce::Logger::setCurrentLogger. A global
    // FileLogger takes a CriticalSection and does a write() plus flush() per
    // message, and JUCE routes some of its own internal diagnostics through
    // whichever thread hits them first -- including processBlock(). In a
    // standalone app that is merely a slow log line; inside a host plugin it is
    // locked file I/O on a real-time thread, which is exactly the stall the
    // audition BufferingAudioReader/TimeSliceThread design exists to avoid.
    //
    // Our own logInfo/logWarning/logError/logDebug calls go straight to
    // fileLogger, so the file still gets everything SLO itself reports. What is
    // given up is JUCE's internal chatter, which is duplicated by our own error
    // reporting at every site that mattered.
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
