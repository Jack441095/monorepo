#include <iostream>
#include <fstream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression test for malformed/corrupt audio file handling -- Phase 2
// Section 78 of the master prompt ("dedicated malformed-audio coverage").
// Phase 1 asserted this degrades gracefully by reading loadAndResampleWaveform()'s
// dr_wav error handling, but never exercised it against a real corrupt file.
// This test does: it proves the scanner doesn't crash on genuinely broken
// input, doesn't add corrupt files to the library, doesn't poison the cache,
// and keeps scanning/processing the other, valid files in the same batch.

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } } while (0)

static void writeBytes(const juce::File& f, const std::vector<uint8_t>& bytes)
{
    std::ofstream out(f.getFullPathName().toStdString(), std::ios::binary);
    out.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
}

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerMalformedAudioTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    // A real, valid fixture alongside the malformed ones, to prove a corrupt
    // file in the same scan batch doesn't stop or poison processing of
    // legitimate files.
    auto validFile = tempRoot.getChildFile("valid.wav");
    if (!fixtureDir.getChildFile("test_kick.wav").copyFileTo(validFile)) {
        std::cerr << "FAIL: could not set up valid fixture" << std::endl;
        return 1;
    }

    // 1. Completely garbage content, .wav extension -- not a RIFF file at all.
    auto garbageFile = tempRoot.getChildFile("garbage.wav");
    writeBytes(garbageFile, { 0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x01, 0x02, 0x03, 0xFF, 0xFE });

    // 2. A truncated WAV: valid RIFF/WAVE/fmt header, but the file is cut off
    // mid-header (missing the data chunk and any sample data at all).
    auto truncatedFile = tempRoot.getChildFile("truncated.wav");
    {
        std::vector<uint8_t> bytes = {
            'R','I','F','F', 0x24,0x00,0x00,0x00, 'W','A','V','E',
            'f','m','t',' ', 0x10,0x00,0x00,0x00,
            0x01,0x00,             // PCM
            0x01,0x00,             // 1 channel
            0x44,0xAC,0x00,0x00,   // 44100 Hz
        };
        writeBytes(truncatedFile, bytes);
    }

    // 3. A zero-byte file with a .wav extension (e.g. an interrupted download/copy).
    auto emptyFile = tempRoot.getChildFile("empty.wav");
    writeBytes(emptyFile, {});

    // 4. A well-formed RIFF/WAVE header claiming a data chunk that's much
    // larger than what's actually present -- and, unlike a merely-truncated
    // file, provides ZERO actual PCM bytes after the header (the file ends
    // immediately after the "data" chunk declaration). dr_wav correctly
    // reads however many real frames are physically present in a truncated
    // file rather than rejecting it outright (verified: an earlier version
    // of this fixture that left a few real trailing bytes was correctly
    // decoded as a legitimate, if degenerate, 1-frame clip -- not a bug,
    // just the wrong fixture for testing outright rejection). This version
    // has no real sample data at all, so framesRead must be 0.
    auto lyingLengthFile = tempRoot.getChildFile("lying_length.wav");
    {
        std::vector<uint8_t> bytes = {
            'R','I','F','F', 0xFF,0xFF,0x00,0x00, 'W','A','V','E',
            'f','m','t',' ', 0x10,0x00,0x00,0x00,
            0x01,0x00, 0x01,0x00,
            0x44,0xAC,0x00,0x00, 0x88,0x58,0x01,0x00,
            0x02,0x00, 0x10,0x00,
            'd','a','t','a', 0xFF,0xFF,0x00,0x00, // claims ~65KB of data
                                                    // but the file ends right here -- 0 real bytes
        };
        writeBytes(lyingLengthFile, bytes);
    }

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    int waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    // Getting here at all (no crash, no hang) is itself most of what this
    // test verifies -- a scanner that mishandles any of the four malformed
    // files above could crash, hang, or throw uncaught.
    auto samples = engine.getSamples();

    CHECK(samples.size() == 1, "expected exactly 1 sample (only the valid file) after scanning "
          "1 valid + 4 malformed files, got " + std::to_string(samples.size()));

    bool validFileFound = false;
    for (const auto& s : samples) {
        if (s.filePath == validFile.getFullPathName().toStdString()) {
            validFileFound = true;
            CHECK(s.isProcessed, "the valid file should be fully processed");
            CHECK(s.embeddingStatus == EmbeddingStatus::Valid,
                  "the valid file should have gotten a real embedding despite malformed siblings in the same scan");
        }
        // None of the 4 malformed files should ever appear in the library at all.
        CHECK(s.filePath != garbageFile.getFullPathName().toStdString(), "garbage.wav must not appear in the library");
        CHECK(s.filePath != truncatedFile.getFullPathName().toStdString(), "truncated.wav must not appear in the library");
        CHECK(s.filePath != emptyFile.getFullPathName().toStdString(), "empty.wav must not appear in the library");
        CHECK(s.filePath != lyingLengthFile.getFullPathName().toStdString(), "lying_length.wav must not appear in the library");
    }
    CHECK(validFileFound, "the valid file should be present in the library");

    // Prove the cache wasn't poisoned: rescanning must not crash either, and
    // must still only find the one valid sample (a poisoned cache row for a
    // malformed file could cause a crash or bogus data on the next scan).
    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);
    CHECK(engine.getSampleCount() == 1, "a rescan after the malformed-file scan should still find exactly 1 sample");

    // findSimilarSamples() against the one real sample must still work
    // normally -- confirms the malformed-file scan didn't leave the engine
    // in some degraded/inconsistent state.
    auto similar = engine.findSimilarSamples(validFile.getFullPathName().toStdString(), 5);
    CHECK(similar.empty(), "with only 1 sample in the library, find-similar should return no results (nothing else to compare against), not crash");

    tempRoot.deleteRecursively();

    if (failures > 0) {
        std::cerr << failures << " check(s) failed." << std::endl;
        return 1;
    }

    std::cout << "SUCCESS: 4 distinct malformed WAV files (garbage bytes, truncated header, "
                 "zero-byte, lying data-chunk length) were all rejected cleanly -- no crash, "
                 "no hang, none added to the library, cache not poisoned, and the one valid "
                 "file in the same scan batch was still processed correctly." << std::endl;
    std::cout << "ALL MALFORMED-AUDIO TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
