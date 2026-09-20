#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression test for the path-traversal fix in reorganizeSamples()
// (sanitizePathComponent in SampleManagerEngine.cpp): instrumentType and key
// come from WAV metadata tags, which are untrusted input from an imported
// file's perspective. This test sets a malicious instrumentType/key
// (../../../escaped-*) via the same updateMetadataAsync path a user's
// "WRITE TO FILE" button uses, then reorganizes, and fails loudly if
// anything ends up outside the scanned library folder.

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerTraversalTest_" + juce::Uuid().toString());
    auto libraryDir = tempRoot.getChildFile("library");
    libraryDir.createDirectory();

    auto fixtureWav = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/test_kick.wav");
    auto sampleWav = libraryDir.getChildFile("evil_sample.wav");
    if (!fixtureWav.copyFileTo(sampleWav)) {
        std::cerr << "FAIL: could not set up test fixture" << std::endl;
        return 1;
    }

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    engine.addPathToQueue(libraryDir.getFullPathName().toStdString());
    int waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    auto samples = engine.getSamples();
    if (samples.empty()) {
        std::cerr << "FAIL: no samples processed" << std::endl;
        return 1;
    }

    // Malicious metadata: an imported file's embedded tags, crafted to try
    // to walk the reorganizer out of libraryDir/tempRoot entirely.
    std::string maliciousInstrumentType = "../../../../escaped-instrumenttype-" + juce::Uuid().toString().toStdString();
    std::string maliciousKey = "../../../../escaped-key-" + juce::Uuid().toString().toStdString();
    engine.updateMetadataAsync(samples.front().filePath, 128.0f, maliciousKey, maliciousInstrumentType);
    juce::Thread::sleep(1200); // let the async TagLib write + in-memory update settle, matching test_main.cpp's pattern

    // namingStyle 5 (Suffix Details) is the one that embeds `key` into the
    // filename, so exercise that path specifically -- namingStyle doesn't
    // matter for the category/folder vector, which is naming-style-independent.
    engine.reorganizeSamples(5, false);

    bool escaped = false;
    juce::String escapedWhat;

    // 1) Nothing should exist directly under tempRoot's PARENT with our
    //    marker in the name (that would mean the reorganizer walked up out
    //    of tempRoot using the "../../../../" in the malicious strings).
    auto parentOfTemp = tempRoot.getParentDirectory();
    for (const auto& entry : juce::RangedDirectoryIterator(parentOfTemp, false, "*escaped-*", juce::File::findFilesAndDirectories)) {
        escaped = true;
        escapedWhat = entry.getFile().getFullPathName();
    }

    // 2) Every remaining sample's on-disk path must still be inside tempRoot.
    auto afterSamples = engine.getSamples();
    for (const auto& s : afterSamples) {
        if (!juce::String(s.filePath).startsWith(tempRoot.getFullPathName())) {
            escaped = true;
            escapedWhat = s.filePath;
        }
    }

    tempRoot.deleteRecursively();
    // Also clean up in case escape happened outside tempRoot (best-effort).
    if (escaped) {
        for (const auto& entry : juce::RangedDirectoryIterator(parentOfTemp, false, "*escaped-*", juce::File::findFilesAndDirectories))
            entry.getFile().deleteRecursively();
    }

    if (escaped) {
        std::cerr << "FAIL: malicious metadata escaped the library root -- found: "
                  << escapedWhat << std::endl;
        return 1;
    }

    std::cout << "SUCCESS: malicious instrumentType/key metadata was contained -- "
                 "reorganizeSamples() did not write outside the library root."
              << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
