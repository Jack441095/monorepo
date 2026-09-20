#include <atomic>
#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression test for reorganizeSamplesAsync() -- Phase 2's background Sort
// Library workflow (see docs/SORT_LIBRARY_BACKGROUND.md). Covers the two
// behaviors that were previously undocumented gaps: the re-entrancy guard
// (a second call while one is already running must be a silent no-op) and
// cancellation (cancelSortLibrary() must actually stop the operation before
// every file is processed). Also exercises the engine-owned sortThread fix
// (a real use-after-free risk, structurally identical to the one found and
// fixed in initAsync() -- see docs/ASYNC_STARTUP.md -- proactively fixed
// here before it was ever triggered) by running a full construct -> sort ->
// destruct cycle.
//
// Deliberately polls the atomic-based getSortLibraryProgress() API rather
// than waiting on reorganizeSamplesAsync()'s onComplete callback: that
// callback is delivered via juce::MessageManager::callAsync, which needs a
// running dispatch loop to actually fire -- this test harness (like every
// other Test* binary in this suite) has none, and JUCE_MODAL_LOOPS_PERMITTED
// is off for this project (runDispatchLoopUntil isn't even available), so
// callAsync-delivered callbacks would never fire here regardless of whether
// the underlying logic is correct. Polling the plain-atomic progress struct
// sidesteps that entirely and is what every other test in this suite
// already does for isBusy()/getSamples().

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } } while (0)

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerSortAsyncTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    // A real WAV fixture, copied many times under distinct names -- enough
    // files that a real disk-move pass takes long enough for the main
    // thread to reliably call cancelSortLibrary() while it's still running.
    constexpr int kFileCount = 150;
    auto sourceFile = fixtureDir.getChildFile("test_kick.wav");
    for (int i = 0; i < kFileCount; ++i) {
        if (!sourceFile.copyFileTo(tempRoot.getChildFile("sample_" + juce::String(i) + ".wav"))) {
            std::cerr << "FAIL: could not set up fixture " << i << std::endl;
            return 1;
        }
    }

    // --- Test 1: re-entrancy guard -----------------------------------------
    {
        SampleManagerEngine engine;
        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: engine init failed" << std::endl;
            return 1;
        }

        engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
        // 180s, not 30s: 150 real files through decode/resample/batched ONNX
        // inference can legitimately take longer than a few seconds under
        // real-world CPU contention (a loaded dev machine, a busy CI runner)
        // -- this loop must tell a slow-but-correct scan apart from an
        // actually-stuck one, not treat every busy machine as a failure.
        int waitLimit = 1800;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(100);
        CHECK(engine.getSampleCount() == kFileCount, "expected all " + std::to_string(kFileCount)
              + " fixtures scanned before starting the sort, got " + std::to_string(engine.getSampleCount()));

        // This suite exercises the filesystem operation and its re-entrancy
        // / cancellation guarantees, not the separate beta classifier gate.
        // Disable that policy explicitly so fixture confidence cannot make a
        // valid sort appear to have skipped every file.
        engine.setBetaPolicyGateEnabled(false);

        int firstCallCount = 0, secondCallCount = 0;
        engine.reorganizeSamplesAsync(1, false, [&](int, int, bool) { firstCallCount++; });
        // Called immediately on the same thread -- the re-entrancy guard
        // (sortInProgress.exchange()) happens synchronously before any
        // background work is dispatched, so this deterministically exercises
        // the guard, not a race.
        engine.reorganizeSamplesAsync(1, false, [&](int, int, bool) { secondCallCount++; });

        int waitForCompletion = 1800;
        while (engine.getSortLibraryProgress().inProgress && waitForCompletion-- > 0)
            juce::Thread::sleep(100);
        CHECK(waitForCompletion > 0, "the sort did not finish within the bounded wait window");

        auto progress = engine.getSortLibraryProgress();
        CHECK(!progress.inProgress, "sort should no longer be in progress after completion");
        CHECK(progress.total == kFileCount, "the guard rejecting the second call means progress.total "
              "should reflect only the first call's scan (" + std::to_string(kFileCount) + "), got "
              + std::to_string(progress.total) + " -- a value from a second, overlapping reset would "
              "indicate the guard failed");
        CHECK(progress.done == kFileCount, "all files should have been visited by the one legitimate sort pass");

        auto sortedSamples = engine.getSamples();
        int stillFlat = 0;
        for (const auto& s : sortedSamples) {
            juce::File f(s.filePath);
            if (f.getParentDirectory().getFullPathName() == tempRoot.getFullPathName()) stillFlat++;
        }
        CHECK(stillFlat == 0, "every file should have been moved into a category subfolder exactly once -- "
              + std::to_string(stillFlat) + " file(s) are still directly in the scanned root, which would "
              "indicate either a failed sort or (if the guard failed) some files processed twice/inconsistently");

        if (failures == 0) {
            std::cout << "SUCCESS: re-entrancy guard confirmed -- calling reorganizeSamplesAsync() a "
                         "second time while the first was already running left progress state "
                         "consistent with exactly one sort pass, not two overlapping ones."
                      << std::endl;
        }
    }
    // Engine destructed here -- exercises the sortThread join-in-destructor
    // fix with a sort that had already fully completed (the common case).

    // --- Test 2: cancellation ------------------------------------------------
    {
        // Fresh fixtures (the previous test's engine already moved the first
        // batch into category subfolders) so this pass has a clean,
        // still-flat set of files to sort again.
        auto tempRoot2 = juce::File::getSpecialLocation(juce::File::tempDirectory)
                             .getChildFile("SmartSampleManagerSortAsyncTest2_" + juce::Uuid().toString());
        tempRoot2.createDirectory();
        for (int i = 0; i < kFileCount; ++i) {
            if (!sourceFile.copyFileTo(tempRoot2.getChildFile("sample_" + juce::String(i) + ".wav"))) {
                std::cerr << "FAIL: could not set up cancellation-test fixture " << i << std::endl;
                return 1;
            }
        }

        SampleManagerEngine engine;
        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: engine init failed" << std::endl;
            return 1;
        }

        engine.addPathToQueue(tempRoot2.getFullPathName().toStdString());
        int waitLimit = 1800;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(100);
        CHECK(engine.getSampleCount() == kFileCount, "expected all fixtures scanned before the cancellation test");

        engine.setBetaPolicyGateEnabled(false);
        engine.reorganizeSamplesAsync(1, false, [](int, int, bool) {});

        // Cancel essentially immediately -- with 150 real file moves (each
        // involving a category-folder creation check + a filesystem rename),
        // this should reliably land while the background thread is still
        // partway through, not after it's already finished.
        engine.cancelSortLibrary();

        int waitForCompletion = 1800;
        while (engine.getSortLibraryProgress().inProgress && waitForCompletion-- > 0)
            juce::Thread::sleep(100);
        CHECK(waitForCompletion > 0, "the cancelled sort did not finish within the bounded wait window");

        auto progress = engine.getSortLibraryProgress();
        CHECK(progress.done < kFileCount, "cancellation should have stopped the sort before all "
              + std::to_string(kFileCount) + " files were visited -- visited " + std::to_string(progress.done));

        if (failures == 0) {
            std::cout << "SUCCESS: cancelSortLibrary() stopped the operation after visiting "
                      << progress.done << " of " << kFileCount << " files." << std::endl;
        }

        tempRoot2.deleteRecursively();
    }
    // Engine destructed here -- this time while a cancelled-but-still-tearing-
    // down sort thread may still be finishing up, directly exercising the
    // destructor's sortCancelRequested + sortThread.join() fix.

    // --- Test 3: copy mode (the actual production default) -------------------
    // Tests 1 and 2 above both exercise copyInsteadOfMove=false (move) --
    // that was already covered before this pass, but the UI has only ever
    // called reorganizeSamplesAsync() with true (copy), and copy's entire
    // safety promise (originals are left untouched, see PluginEditor.cpp's
    // performSortLibrary()) had no direct regression coverage at all. Add it
    // explicitly rather than leaving the actually-shipped default unverified.
    {
        auto tempRoot3 = juce::File::getSpecialLocation(juce::File::tempDirectory)
                             .getChildFile("SmartSampleManagerSortAsyncTest3_" + juce::Uuid().toString());
        tempRoot3.createDirectory();
        for (int i = 0; i < kFileCount; ++i) {
            if (!sourceFile.copyFileTo(tempRoot3.getChildFile("sample_" + juce::String(i) + ".wav"))) {
                std::cerr << "FAIL: could not set up copy-mode fixture " << i << std::endl;
                return 1;
            }
        }

        SampleManagerEngine engine;
        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: engine init failed" << std::endl;
            return 1;
        }

        engine.addPathToQueue(tempRoot3.getFullPathName().toStdString());
        int waitLimit = 1800;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(100);
        CHECK(engine.getSampleCount() == kFileCount, "expected all fixtures scanned before the copy-mode test");

        engine.setBetaPolicyGateEnabled(false);
        int completedCount = 0;
        engine.reorganizeSamplesAsync(1, true, [&](int, int, bool) { completedCount++; });

        int waitForCompletion = 1800;
        while (engine.getSortLibraryProgress().inProgress && waitForCompletion-- > 0)
            juce::Thread::sleep(100);
        CHECK(waitForCompletion > 0, "the copy-mode sort did not finish within the bounded wait window");

        auto progress = engine.getSortLibraryProgress();
        CHECK(progress.done == kFileCount, "all files should have been visited by the copy-mode sort");

        // The defining property of copy mode: every original file must still
        // exist, untouched, at its pre-sort path -- this is the entire reason
        // Copy is the recommended default in the UI's confirmation dialog.
        int missingOriginals = 0;
        for (int i = 0; i < kFileCount; ++i) {
            if (!tempRoot3.getChildFile("sample_" + juce::String(i) + ".wav").existsAsFile())
                ++missingOriginals;
        }
        CHECK(missingOriginals == 0, std::to_string(missingOriginals) + " of " + std::to_string(kFileCount)
              + " original file(s) are missing after a copy-mode sort -- copy must never remove the source file");

        // And the new copies should actually exist in category subfolders,
        // not just be database-path updates with no real file behind them.
        auto sortedSamples = engine.getSamples();
        int copiesInSubfolder = 0;
        for (const auto& s : sortedSamples) {
            juce::File f(s.filePath);
            if (f.existsAsFile() && f.getParentDirectory().getFullPathName() != tempRoot3.getFullPathName())
                ++copiesInSubfolder;
        }
        CHECK(copiesInSubfolder == kFileCount, "expected all " + std::to_string(kFileCount)
              + " files to have a real copy on disk in a category subfolder, found " + std::to_string(copiesInSubfolder));

        if (failures == 0) {
            std::cout << "SUCCESS: copy-mode sort produced " << copiesInSubfolder
                      << " category-subfolder copies while leaving all " << kFileCount
                      << " original files untouched." << std::endl;
        }

        tempRoot3.deleteRecursively();
    }

    // --- Test 4: duplicate canonical names are non-destructive -------------
    // Two different source directories deliberately contain the same basename.
    // The reorganizer must keep both payloads, allocate a deterministic suffix,
    // and preserve the original container extension rather than deleting the
    // first destination before moving the second file.
    {
        auto tempRoot4 = juce::File::getSpecialLocation(juce::File::tempDirectory)
                             .getChildFile("SmartSampleManagerSortCollisionTest_" + juce::Uuid().toString());
        auto left = tempRoot4.getChildFile("left");
        auto right = tempRoot4.getChildFile("right");
        left.createDirectory();
        right.createDirectory();
        auto leftSource = left.getChildFile("same.wav");
        auto rightSource = right.getChildFile("same.wav");
        if (!sourceFile.copyFileTo(leftSource) || !sourceFile.copyFileTo(rightSource)) {
            std::cerr << "FAIL: could not set up duplicate-name fixtures" << std::endl;
            return 1;
        }

        SampleManagerEngine engine;
        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: engine init failed" << std::endl;
            return 1;
        }
        engine.addPathToQueue(tempRoot4.getFullPathName().toStdString());
        int waitLimit = 1800;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(100);
        CHECK(engine.getSampleCount() == 2, "expected both duplicate-name fixtures to be scanned");

        // This test targets filesystem safety, not the beta eligibility policy.
        engine.setBetaPolicyGateEnabled(false);
        engine.reorganizeSamples(1, false);

        auto sorted = engine.getSamples();
        CHECK(sorted.size() == 2, "both duplicate-name samples must remain represented");
        juce::String firstPath, secondPath;
        int existing = 0;
        int wavExtension = 0;
        for (const auto& sample : sorted) {
            juce::File f(sample.filePath);
            if (f.existsAsFile()) {
                ++existing;
                if (f.getFileExtension().equalsIgnoreCase(".wav")) ++wavExtension;
                if (firstPath.isEmpty()) firstPath = f.getFullPathName();
                else if (secondPath.isEmpty()) secondPath = f.getFullPathName();
            }
        }
        CHECK(existing == 2, "a collision must not delete either source payload");
        CHECK(wavExtension == 2, "renaming must preserve the source extension");
        CHECK(firstPath != secondPath, "colliding names must receive distinct destinations");

        tempRoot4.deleteRecursively();
    }

    tempRoot.deleteRecursively();

    if (failures > 0) {
        std::cerr << failures << " check(s) failed." << std::endl;
        return 1;
    }

    std::cout << "ALL SORT-LIBRARY-ASYNC TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
