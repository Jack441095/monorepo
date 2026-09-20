#include <iostream>
#include <fstream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression tests for Phase 2's failure-handling hardening:
//  1. Missing ONNX model -> no crash, no fake pseudo-embedding, honest
//     FailedRetryable/FailedPermanent status, engine stays in Degraded state.
//     See docs/ONNX_FAILURE_HANDLING.md, docs/ASYNC_STARTUP.md.
//  2. A corrupted cache DB is detected and quarantined-and-rebuilt on the
//     next open, rather than crashing or silently serving corrupt data.
//     See docs/DATABASE_HARDENING.md.

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } } while (0)

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerResilienceTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    // --- Test 1: missing/invalid ONNX model -------------------------------
    {
        auto testFile = tempRoot.getChildFile("missing_model_test.wav");
        if (!fixtureDir.getChildFile("test_kick.wav").copyFileTo(testFile)) {
            std::cerr << "FAIL: could not set up test fixture" << std::endl;
            return 1;
        }

        SampleManagerEngine engine;
        bool initOk = engine.init("/nonexistent/path/to/model.onnx");
        CHECK(!initOk, "init() with a nonexistent model path should return false");
        CHECK(!engine.isEmbeddingModelAvailable(),
              "isEmbeddingModelAvailable() must be false when the model failed to load");
        CHECK(engine.getEngineState() == EngineInitState::Degraded,
              "engine state should be Degraded after a failed model load, not Ready/Failed");

        engine.addPathToQueue(testFile.getFullPathName().toStdString());
        int waitLimit = 100;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(100);

        auto samples = engine.getSamples();
        CHECK(samples.size() == 1, "expected exactly 1 sample after scanning with no model");
        if (!samples.empty()) {
            const auto& s = samples.front();
            CHECK(s.isProcessed, "sample should still be marked processed (the pipeline ran, just without a model)");
            CHECK(s.embedding.empty(),
                  "embedding must be empty, never a fake/pseudo-embedding, when the model is unavailable");
            CHECK(s.embeddingStatus == EmbeddingStatus::FailedRetryable
                      || s.embeddingStatus == EmbeddingStatus::FailedPermanent,
                  "embeddingStatus must honestly reflect failure, not Valid");
        }

        // findSimilarSamples() and duplicate detection must not crash or
        // return misleading results when nothing has a real embedding.
        auto similar = engine.findSimilarSamples(testFile.getFullPathName().toStdString(), 5);
        CHECK(similar.empty(), "findSimilarSamples() should return no results when no sample has a Valid embedding");

        if (failures == 0) {
            std::cout << "SUCCESS: missing model handled honestly -- no fake embedding, no crash, "
                         "engine reports Degraded state."
                      << std::endl;
        }
    }

    // --- Test 2: corrupted cache DB is quarantined and rebuilt ------------
    {
        juce::File cacheFile = SampleManagerEngine::getCacheDbFile();

        {
            // Scoped so the engine (and its sqlite3 connection) is fully
            // destructed before we corrupt the file on disk below --
            // otherwise the corruption could be masked by SQLite's own
            // in-process page cache rather than genuinely re-read from disk.
            SampleManagerEngine engineToEstablishCache;
            CHECK(engineToEstablishCache.checkCacheIntegrity(),
                  "a freshly-opened cache DB should pass its own integrity check");
        }

        CHECK(cacheFile.existsAsFile(), "cache DB file should exist after at least one engine has opened it");

        if (cacheFile.existsAsFile()) {
            // Overwrite the SQLite header so the file is unambiguously not a
            // valid database, regardless of WAL-mode sidecar state.
            std::ofstream out(cacheFile.getFullPathName().toStdString(),
                               std::ios::binary | std::ios::in | std::ios::out);
            if (out.is_open()) {
                std::string garbage(64, '\xFF');
                out.write(garbage.data(), static_cast<std::streamsize>(garbage.size()));
                out.close();
            } else {
                std::cerr << "FAIL: could not open cache DB file to corrupt it for this test" << std::endl;
                failures++;
            }
        }

        // A new engine's constructor calls openCacheDb(), which must detect
        // the corruption via quick_check, quarantine the bad file, and end
        // up with a fresh, working cache -- never crash, never silently
        // trust corrupt data.
        SampleManagerEngine engineAfterCorruption;
        CHECK(engineAfterCorruption.checkCacheIntegrity(),
              "cache DB should be a fresh, valid database after quarantine-and-rebuild");

        // Confirm a quarantine file was actually created (not just silently
        // overwritten in place).
        bool quarantineFileFound = false;
        for (const auto& f : cacheFile.getParentDirectory().findChildFiles(
                 juce::File::TypesOfFileToFind::findFiles, false, "*.corrupt-*")) {
            juce::ignoreUnused(f);
            quarantineFileFound = true;
        }
        CHECK(quarantineFileFound, "expected a quarantined (.corrupt-<timestamp>) copy of the corrupted cache DB to exist");

        // The rebuilt cache must actually work: scan a file, confirm it's
        // retrievable, not just "integrity check passes on an empty shell."
        auto testFile = tempRoot.getChildFile("post_quarantine_test.wav");
        if (fixtureDir.getChildFile("test_unique.wav").copyFileTo(testFile)) {
            engineAfterCorruption.addPathToQueue(testFile.getFullPathName().toStdString());
            int waitLimit = 100;
            while (engineAfterCorruption.isBusy() && waitLimit-- > 0)
                juce::Thread::sleep(100);
            CHECK(engineAfterCorruption.getSampleCount() == 1,
                  "the rebuilt cache DB should still support a normal scan afterward");
        }

        if (failures == 0) {
            std::cout << "SUCCESS: corrupted cache DB was detected, quarantined, and rebuilt into a "
                         "working cache without crashing or losing source audio."
                      << std::endl;
        }
    }

    tempRoot.deleteRecursively();

    if (failures > 0) {
        std::cerr << failures << " check(s) failed." << std::endl;
        return 1;
    }

    std::cout << "ALL RESILIENCE TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
