#include <iostream>
#include <thread>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression test for multi-instance concurrent SQLite cache access -- Phase
// 2 Section 30 ("simulate multiple SmartSampleManager instances accessing
// the shared cache... ensure failures do not produce corruption, deadlock,
// unexplained missing data, or persistent SQLITE_BUSY loops"). The
// busy_timeout=5000 fix (see docs/DATABASE_HARDENING.md) was implemented
// but never had a dedicated concurrency test -- this is that test.
//
// Two SampleManagerEngine instances are constructed in the same process
// (the same way two plugin instances loaded into one DAW process would be)
// and both scan overlapping sets of real files into the *same* on-disk
// cache DB (getCacheDbFile() resolves to one fixed path, matching real
// multi-instance behavior) concurrently, from separate threads.

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } } while (0)

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerMultiInstanceTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    // A handful of distinct real fixtures, split into two overlapping-ish
    // sets so both engines are genuinely writing to the cache concurrently,
    // not just reading each other's already-committed rows.
    std::vector<juce::File> fixtureSources = {
        fixtureDir.getChildFile("test_kick.wav"),
        fixtureDir.getChildFile("test_unique.wav"),
        fixtureDir.getChildFile("real_kick_a.wav"),
        fixtureDir.getChildFile("real_kick_b.wav"),
        fixtureDir.getChildFile("real_sustained_noise.wav"),
    };

    auto dirA = tempRoot.getChildFile("dirA");
    auto dirB = tempRoot.getChildFile("dirB");
    dirA.createDirectory();
    dirB.createDirectory();

    // Each source file copied into BOTH directories under a distinct name
    // per directory, so each engine scans its own 5 files (10 total,
    // distinct paths -- avoids the two engines racing to insert the exact
    // same cache row, which tests something different from "two engines
    // hitting the same DB file concurrently with different data").
    int copyIndex = 0;
    for (const auto& src : fixtureSources) {
        auto nameNoExt = src.getFileNameWithoutExtension();
        if (!src.copyFileTo(dirA.getChildFile(nameNoExt + "_a.wav")) ||
            !src.copyFileTo(dirB.getChildFile(nameNoExt + "_b.wav"))) {
            std::cerr << "FAIL: could not set up fixture " << copyIndex << std::endl;
            return 1;
        }
        copyIndex++;
    }

    SampleManagerEngine engineA;
    SampleManagerEngine engineB;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engineA.init(modelPath) || !engineB.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    // Kick off both scans as close to simultaneously as possible from
    // separate threads -- this is the actual concurrency under test.
    std::thread threadA([&]() { engineA.addPathToQueue(dirA.getFullPathName().toStdString()); });
    std::thread threadB([&]() { engineB.addPathToQueue(dirB.getFullPathName().toStdString()); });
    threadA.join();
    threadB.join();

    // Bounded wait -- a deadlock or a persistent-SQLITE_BUSY livelock would
    // hang here forever without this cap, which is itself part of what's
    // being tested (this test process exiting normally is meaningful).
    int waitLimit = 200; // up to 20s combined
    while ((engineA.isBusy() || engineB.isBusy()) && waitLimit-- > 0)
        juce::Thread::sleep(100);

    CHECK(waitLimit > 0, "engines did not finish scanning within the bounded wait window -- "
          "possible deadlock or persistent SQLITE_BUSY livelock");

    CHECK(engineA.getSampleCount() == 5, "engine A should have scanned exactly 5 files, got "
          + std::to_string(engineA.getSampleCount()));
    CHECK(engineB.getSampleCount() == 5, "engine B should have scanned exactly 5 files, got "
          + std::to_string(engineB.getSampleCount()));

    // The shared cache DB must still be structurally sound after concurrent
    // writes from both engines -- this is the actual corruption check.
    CHECK(engineA.checkCacheIntegrity(), "shared cache DB failed integrity check after concurrent multi-instance writes (engine A's view)");
    CHECK(engineB.checkCacheIntegrity(), "shared cache DB failed integrity check after concurrent multi-instance writes (engine B's view)");

    // Confirm no cross-contamination: each engine only ever sees its own
    // scanned files, never the other engine's in-memory sample list (the
    // cache DB is shared on disk, but each engine's in-memory `samples`
    // vector is only ever populated by its own scans).
    bool crossContamination = false;
    for (const auto& s : engineA.getSamples()) {
        if (s.filePath.find(dirB.getFullPathName().toStdString()) != std::string::npos) {
            crossContamination = true;
        }
    }
    CHECK(!crossContamination, "engine A's in-memory sample list should never contain engine B's files");

    // A third, fresh engine construction (simulating a new plugin instance
    // opening after the first two did their concurrent writes) must be able
    // to open and use the same cache DB cleanly -- proves the file itself
    // is left in a genuinely reusable state, not just "didn't crash yet."
    {
        SampleManagerEngine engineC;
        CHECK(engineC.checkCacheIntegrity(), "a fresh third engine instance should find a healthy cache DB after the concurrent A/B writes");
    }

    tempRoot.deleteRecursively();

    if (failures > 0) {
        std::cerr << failures << " check(s) failed." << std::endl;
        return 1;
    }

    std::cout << "SUCCESS: two engine instances scanning concurrently into the same shared "
                 "cache DB completed without deadlock, corruption, or cross-contamination, "
                 "and a third fresh instance opened the resulting cache cleanly." << std::endl;
    std::cout << "ALL MULTI-INSTANCE TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
