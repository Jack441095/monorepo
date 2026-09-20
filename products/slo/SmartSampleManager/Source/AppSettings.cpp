#include "AppSettings.h"

AppSettings& AppSettings::getInstance() {
    static AppSettings instance;
    return instance;
}

AppSettings::AppSettings() {
    juce::PropertiesFile::Options options;
    options.applicationName = "SmartSampleManager";
    options.filenameSuffix = "settings";
    options.folderName = "SmartSampleManager";
    options.osxLibrarySubFolder = "Application Support";
    options.storageFormat = juce::PropertiesFile::storeAsXML;

    props = std::make_unique<juce::PropertiesFile>(options);
}
