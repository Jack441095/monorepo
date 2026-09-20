#include <JuceHeader.h>
#include "SampleManagerEngine.h"
#include <sodium.h>
#include <iostream>
#include <map>

// Real SHA-256 over raw file bytes, via libsodium (already a dependency of
// this codebase, see Source/Licensing/LicenseManager.cpp) -- juce::SHA256
// lives in a JUCE module (juce_cryptography) this build tier doesn't link,
// so this avoids pulling in a new module just for a checksum.
static juce::String sha256HexOfFile(const juce::File& f)
{
    juce::MemoryBlock data;
    f.loadFileAsData(data);
    unsigned char digest[crypto_hash_sha256_BYTES];
    crypto_hash_sha256(digest, static_cast<const unsigned char*>(data.getData()), data.getSize());
    juce::String hex;
    for (unsigned char b : digest) hex << juce::String::toHexString(static_cast<int>(b)).paddedLeft('0', 2);
    return hex;
}

// SLO private beta readiness: read-only safety qualification.
//
// Proves, with real evidence (not an architectural claim), that scanning and
// classifying a sample library through the real, production
// SampleManagerEngine code path never mutates the audio files themselves:
// no delete, no move, no rename, no content change, no new/missing files.
// Uses a fixture-only library (never the owner's real sample library, per
// the safety rules this test was written under). Writes a JSON receipt with
// per-file before/after SHA-256 checksums as durable evidence.
//
// Deliberately does NOT call reorganizeSamples()/reorganizeSamplesAsync()
// (the Sort Library feature) -- that is a separate, already explicitly
// consent-gated, copy-by-default operation (see B-011 in
// SLO_BETA_BLOCKER_REGISTER_V1.md and PluginEditor.cpp's confirmation
// dialog). This test's job is to prove the SCAN path specifically -- the
// one that runs automatically, with no per-file consent prompt -- is
// read-only.

static int failures = 0;
#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } \
         else { std::cout << "  ok: " << msg << std::endl; } } while (0)

int main()
{
    std::cout << "Read-only safety qualification: scan-path fixture test" << std::endl;

    if (sodium_init() < 0) {
        std::cerr << "FATAL: libsodium failed to initialize" << std::endl;
        return 1;
    }

    juce::MessageManager::getInstance();

    // Isolated cache -- never the production DB (see
    // test_safety_regression_main.cpp's documented incident this pattern
    // exists to prevent).
    juce::File customCacheDir = juce::File::getCurrentWorkingDirectory()
        .getChildFile("fixtures").getChildFile("cache_readonly_safety");
    customCacheDir.createDirectory();
    SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(customCacheDir);

    // A dedicated, disposable fixture library -- built from this repo's own
    // real (non-owner-library) test fixture audio, copied into an isolated
    // scratch directory so this test can safely assert on file count and
    // checksums without any risk of touching a real source-controlled file.
    juce::File fixtureLibraryDir = juce::File::getCurrentWorkingDirectory()
        .getChildFile("fixtures").getChildFile("readonly_safety_library");
    fixtureLibraryDir.deleteRecursively();
    fixtureLibraryDir.createDirectory();

    juce::File sourceDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    juce::StringArray fixtureNames { "test_kick.wav", "real_kick_a.wav", "real_kick_b.wav", "real_sustained_noise.wav" };
    int copiedCount = 0;
    for (const auto& name : fixtureNames) {
        juce::File src = sourceDir.getChildFile(name);
        if (src.existsAsFile()) {
            src.copyFileTo(fixtureLibraryDir.getChildFile(name));
            ++copiedCount;
        }
    }
    CHECK(copiedCount >= 3, "at least 3 real fixture audio files copied into the disposable test library");

    // BEFORE snapshot: real SHA-256 of every file's actual bytes, plus size
    // and the exact file set.
    std::map<std::string, juce::String> beforeHashes;
    std::map<std::string, juce::int64> beforeSizes;
    for (auto& f : fixtureLibraryDir.findChildFiles(juce::File::findFiles, false)) {
        beforeHashes[f.getFileName().toStdString()] = sha256HexOfFile(f);
        beforeSizes[f.getFileName().toStdString()] = f.getSize();
    }
    CHECK(static_cast<int>(beforeHashes.size()) == copiedCount, "BEFORE snapshot captured one hash per fixture file");

    // Exercise the REAL production scan/classify path -- not a mock.
    {
        SampleManagerEngine engine;
        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
        CHECK(engine.init(modelPath), "engine initializes against the real embedding model");

        engine.clearCache();
        engine.addPathToQueue(fixtureLibraryDir.getFullPathName().toStdString());
        while (engine.isBusy()) {
            juce::Thread::sleep(50);
        }

        auto samples = engine.getSamples();
        CHECK(static_cast<int>(samples.size()) == copiedCount, "engine scanned and classified every fixture file");
    }

    // AFTER snapshot.
    std::map<std::string, juce::String> afterHashes;
    std::map<std::string, juce::int64> afterSizes;
    for (auto& f : fixtureLibraryDir.findChildFiles(juce::File::findFiles, false)) {
        afterHashes[f.getFileName().toStdString()] = sha256HexOfFile(f);
        afterSizes[f.getFileName().toStdString()] = f.getSize();
    }

    CHECK(afterHashes.size() == beforeHashes.size(), "file count unchanged after scan (no files created or deleted)");
    bool anyMismatch = false;
    for (const auto& [name, hashBefore] : beforeHashes) {
        auto it = afterHashes.find(name);
        if (it == afterHashes.end()) {
            std::cerr << "FAIL: file present before scan is missing after scan: " << name << std::endl;
            anyMismatch = true;
            continue;
        }
        if (it->second != hashBefore) {
            std::cerr << "FAIL: checksum changed for " << name << " (before=" << hashBefore << " after=" << it->second << ")" << std::endl;
            anyMismatch = true;
        }
        if (afterSizes[name] != beforeSizes[name]) {
            std::cerr << "FAIL: size changed for " << name << std::endl;
            anyMismatch = true;
        }
    }
    if (anyMismatch) failures++;
    CHECK(!anyMismatch, "every fixture file's SHA-256 checksum and size is byte-identical before vs after scan");

    // Durable evidence receipt.
    juce::File receiptFile(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/tools/classification_benchmark/results_readonly_safety_receipt.json");
    receiptFile.deleteFile();
    juce::FileOutputStream stream(receiptFile);
    if (stream.openedOk()) {
        juce::String json;
        json << "{\n  \"files\": [\n";
        bool first = true;
        for (const auto& [name, hashBefore] : beforeHashes) {
            if (!first) json << ",\n";
            first = false;
            json << "    {\n"
                 << "      \"file\": \"" << name << "\",\n"
                 << "      \"sha256_before\": \"" << beforeHashes[name] << "\",\n"
                 << "      \"sha256_after\": \"" << afterHashes[name] << "\",\n"
                 << "      \"size_before\": " << beforeSizes[name] << ",\n"
                 << "      \"size_after\": " << afterSizes[name] << ",\n"
                 << "      \"identical\": " << ((afterHashes[name] == hashBefore && afterSizes[name] == beforeSizes[name]) ? "true" : "false") << "\n"
                 << "    }";
        }
        json << "\n  ],\n"
             << "  \"file_count_before\": " << beforeHashes.size() << ",\n"
             << "  \"file_count_after\": " << afterHashes.size() << ",\n"
             << "  \"all_checks_passed\": " << (failures == 0 ? "true" : "false") << "\n"
             << "}\n";
        stream.writeText(json, false, false, nullptr);
        std::cout << "Receipt written to: " << receiptFile.getFullPathName() << std::endl;
    }

    fixtureLibraryDir.deleteRecursively(); // clean up this test's own disposable scratch dir, not the source fixtures

    if (failures > 0) {
        std::cerr << failures << " check(s) FAILED" << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }
    std::cout << "ALL READ-ONLY SAFETY CHECKS PASSED" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
