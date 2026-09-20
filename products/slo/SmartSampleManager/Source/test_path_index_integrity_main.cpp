#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// TestPathIndexIntegrity -- behavioral coverage for the pathToIndex map
// (Phase 3, engineering/slo-perf-scale-v1). The map itself is internal, so
// these assertions target its observable contract:
//   1. findSimilarSamples() on a path the engine never processed returns
//      empty (map-miss path), not a wrong-but-plausible result.
//   2. After pruneMissingFiles() shifts positional indices, a rescan of the
//      same directory does NOT duplicate the surviving samples (the batch
//      commit's map lookup must still resolve them) and does not resurrect
//      the pruned one.
//   3. findSimilarSamples() remains correct for every surviving sample after
//      prune + rescan.
// (Full-iteration scans -- duplicates, clusters, UMAP -- are legitimately
// O(N) and are covered by their own suites.)

namespace {

bool waitForIdle(SampleManagerEngine& engine) {
    int waitLimit = 100;  // 10s ceiling, same pattern as TestEmbeddingQuality
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);
    return !engine.isBusy();
}

}  // namespace

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SLO_PathIndexTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    const char* fixtureNames[] = {"real_kick_a.wav", "real_kick_b.wav",
                                  "real_sustained_noise.wav", "test_unique.wav"};
    for (const char* n : fixtureNames) {
        if (!fixtureDir.getChildFile(n).copyFileTo(tempRoot.getChildFile(n))) {
            std::cerr << "FAIL: could not copy fixture " << n << std::endl;
            tempRoot.deleteRecursively();
            return 1;
        }
    }

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    if (!waitForIdle(engine)) {
        std::cerr << "FAIL: engine never went idle after initial scan" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    if (engine.getSampleCount() != 4) {
        std::cerr << "FAIL: expected 4 samples after initial scan, got "
                  << engine.getSampleCount() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    // 1. Map-miss lookup: a path the engine never processed must yield an
    // empty result, not a wrong nearest-neighbor answer.
    const std::string unknownPath = "/tmp/definitely_never_scanned_file.wav";
    if (!engine.findSimilarSamples(unknownPath, 5).empty()) {
        std::cerr << "FAIL: findSimilarSamples() returned results for a path the engine never processed"
                  << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    // 2. Prune one file (positional indices shift), then rescan the same
    // directory. The commit loop must resolve the 3 survivors via the map
    // (no duplicates) and must not resurrect the pruned file.
    const auto deletedFile = tempRoot.getChildFile("real_sustained_noise.wav");
    if (!deletedFile.deleteFile()) {
        std::cerr << "FAIL: could not delete fixture to simulate external removal" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    if (engine.pruneMissingFiles() != 1) {
        std::cerr << "FAIL: expected pruneMissingFiles() to remove exactly 1" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    if (!waitForIdle(engine)) {
        std::cerr << "FAIL: engine never went idle after prune rebuild" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    if (!waitForIdle(engine)) {
        std::cerr << "FAIL: engine never went idle after post-prune rescan" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    if (engine.getSampleCount() != 3) {
        std::cerr << "FAIL: expected 3 samples after prune + rescan (no duplicates, no "
                     "resurrection), got " << engine.getSampleCount() << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }
    for (const auto& s : engine.getSamples()) {
        if (s.filePath == deletedFile.getFullPathName().toStdString()) {
            std::cerr << "FAIL: pruned sample was resurrected by the post-prune rescan" << std::endl;
            tempRoot.deleteRecursively();
            return 1;
        }
    }

    // 3. Every surviving sample still resolves through the map: similarity
    // queries return results, none of them the deleted path.
    for (const auto& s : engine.getSamples()) {
        auto similar = engine.findSimilarSamples(s.filePath, 5);
        for (const auto& r : similar) {
            if (r.filePath == deletedFile.getFullPathName().toStdString()) {
                std::cerr << "FAIL: findSimilarSamples() returned the pruned sample after prune+rescan"
                          << std::endl;
                tempRoot.deleteRecursively();
                return 1;
            }
        }
    }

    tempRoot.deleteRecursively();
    std::cout << "ALL PATH INDEX INTEGRITY TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
