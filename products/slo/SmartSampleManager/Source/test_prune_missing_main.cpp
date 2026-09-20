#include <iostream>
#include "SampleManagerEngine.h"
#include "MissingFilePolicy.h"
#include "TestCacheDbIsolation.h"

// Regression test for pruneMissingFiles(): scans two files, deletes one from
// disk (simulating a user moving/deleting it outside the app), confirms
// pruning removes exactly that one sample and leaves the other untouched,
// then confirms a second prune is a no-op (nothing left to remove).

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

#if JUCE_MAC
    const auto disconnectedVolumeName = "SLO_Disconnected_Test_" + juce::Uuid().toString();
    const auto disconnectedSample = juce::File("/Volumes/" + disconnectedVolumeName + "/Samples/kick.wav");
    if (!shouldPreserveMissingFileForUnavailableStorage(disconnectedSample)) {
        std::cerr << "FAIL: a missing sample on a disconnected external volume would be pruned" << std::endl;
        return 1;
    }
    const auto missingLocalSample = juce::File::getSpecialLocation(juce::File::tempDirectory)
                                        .getChildFile("SLO_Missing_Local_" + juce::Uuid().toString() + ".wav");
    if (shouldPreserveMissingFileForUnavailableStorage(missingLocalSample)) {
        std::cerr << "FAIL: a normal missing local file was mistaken for unavailable storage" << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: disconnected external-drive records are preserved while missing local files remain pruneable."
              << std::endl;
#endif

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerPruneTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
#if JUCE_MAC
    const auto missingOnMountedVolume = fixtureDir.getChildFile(
        "SLO_Missing_Mounted_" + juce::Uuid().toString() + ".wav");
    if (shouldPreserveMissingFileForUnavailableStorage(missingOnMountedVolume)) {
        std::cerr << "FAIL: a missing file on a mounted volume was mistaken for disconnected storage"
                  << std::endl;
        return 1;
    }
#endif
    auto keptFile = tempRoot.getChildFile("kept.wav");
    auto deletedFile = tempRoot.getChildFile("deleted.wav");

    if (!fixtureDir.getChildFile("test_kick.wav").copyFileTo(keptFile) ||
        !fixtureDir.getChildFile("test_unique.wav").copyFileTo(deletedFile)) {
        std::cerr << "FAIL: could not set up test fixtures" << std::endl;
        return 1;
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

    auto samples = engine.getSamples();
    if (samples.size() != 2) {
        std::cerr << "FAIL: expected 2 samples processed, got " << samples.size() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    if (!deletedFile.deleteFile()) {
        std::cerr << "FAIL: could not delete test fixture to simulate an externally-removed file" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    int removed = engine.pruneMissingFiles();
    if (removed != 1) {
        std::cerr << "FAIL: expected pruneMissingFiles() to remove 1 sample, removed " << removed << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    auto afterPrune = engine.getSamples();
    if (afterPrune.size() != 1) {
        std::cerr << "FAIL: expected 1 sample remaining, got " << afterPrune.size() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    if (afterPrune.front().filePath != keptFile.getFullPathName().toStdString()) {
        std::cerr << "FAIL: the WRONG sample survived pruning -- expected " << keptFile.getFullPathName()
                  << ", got " << afterPrune.front().filePath << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    if (!keptFile.existsAsFile()) {
        std::cerr << "FAIL: pruneMissingFiles() deleted a file from disk -- it must only touch the "
                     "in-memory library list, never the filesystem."
                  << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: pruning removed exactly the deleted file's sample, kept the other, "
                 "and touched nothing on disk."
              << std::endl;

    int secondPrune = engine.pruneMissingFiles();
    if (secondPrune != 0) {
        std::cerr << "FAIL: a second prune with nothing missing should remove 0, removed " << secondPrune << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    std::cout << "SUCCESS: a second prune with nothing missing is a correct no-op." << std::endl;

    // Regression test: pruning after the HNSW index has already been built
    // (umapBootstrapped == true, the case here since the earlier scan already
    // ran its bootstrap) must invalidate the index rather than leave it
    // pointing at stale positions. hnswlib labels are the sample's index in
    // `samples` at build time; erasing an entry shifts every later index, so
    // an un-rebuilt index can resolve a "similar" hit to the wrong sample
    // entirely (see SampleManagerEngine::pruneMissingFiles /
    // forcedUmapRecomputePending). Add two more real, acoustically-distinct
    // fixtures, delete one, prune, and confirm the engine self-heals and
    // keeps returning sane (never-crashing, never-referencing-deleted-file)
    // results afterward.
    auto keptKick = tempRoot.getChildFile("kept_kick.wav");
    auto deletedKick = tempRoot.getChildFile("deleted_kick.wav");
    auto fixtureDir2 = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    if (!fixtureDir2.getChildFile("real_kick_a.wav").copyFileTo(keptKick) ||
        !fixtureDir2.getChildFile("real_kick_b.wav").copyFileTo(deletedKick)) {
        std::cerr << "FAIL: could not set up second-phase test fixtures" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    engine.addPathToQueue(keptKick.getFullPathName().toStdString());
    engine.addPathToQueue(deletedKick.getFullPathName().toStdString());
    waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    if (engine.getSampleCount() != 3) {
        std::cerr << "FAIL: expected 3 samples after second-phase scan (kept.wav + 2 new), got "
                  << engine.getSampleCount() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    if (!deletedKick.deleteFile()) {
        std::cerr << "FAIL: could not delete second-phase fixture" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    int removedAfterBootstrap = engine.pruneMissingFiles();
    if (removedAfterBootstrap != 1) {
        std::cerr << "FAIL: expected pruneMissingFiles() to remove 1 sample post-bootstrap, removed "
                  << removedAfterBootstrap << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    // pruneMissingFiles() only *requests* a forced rebuild (via notify() to
    // the coordinator thread) -- give it a moment to actually run, the same
    // way the initial scan's bootstrap is awaited above.
    waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    auto resultsAfterPrune = engine.findSimilarSamples(keptKick.getFullPathName().toStdString(), 5);
    for (const auto& r : resultsAfterPrune) {
        if (r.filePath == deletedKick.getFullPathName().toStdString()) {
            std::cerr << "FAIL: findSimilarSamples() returned a sample that was just pruned -- "
                         "the HNSW index was not correctly invalidated/rebuilt after pruning."
                      << std::endl;
            tempRoot.deleteRecursively();
            return 1;
        }
        bool stillTracked = false;
        for (const auto& s : engine.getSamples()) {
            if (s.filePath == r.filePath) { stillTracked = true; break; }
        }
        if (!stillTracked) {
            std::cerr << "FAIL: findSimilarSamples() returned '" << r.filePath
                      << "', which is not in the engine's current sample list -- stale index label."
                      << std::endl;
            tempRoot.deleteRecursively();
            return 1;
        }
    }
    std::cout << "SUCCESS: after pruning a sample from an already-bootstrapped library, "
                 "findSimilarSamples() never returns the deleted sample and only ever returns "
                 "samples the engine currently tracks -- the index correctly rebuilt."
              << std::endl;

    tempRoot.deleteRecursively();
    std::cout << "ALL PRUNE-MISSING-FILES TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
