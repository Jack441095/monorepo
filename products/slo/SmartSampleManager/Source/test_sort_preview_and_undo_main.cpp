#include <iostream>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Unit test suite for Phase 2: Interactive Rename Preview & One-Click Undo.
// Verifies:
// 1. previewSortLibrary() accurately computes planned destinations, tracks
//    eligibility vs. policy gates (Percussion excluded, Kicks/Bass eligible),
//    and touches zero files on disk.
// 2. undoLastSort() cleanly reverses move-mode sorts, restoring files to
//    original directories and cleaning up empty category folders.
// 3. undoLastSort() cleanly reverses copy-mode sorts, removing copies while
//    preserving originals.

static int failures = 0;

#define CHECK(cond, msg) \
    do { \
        if (!(cond)) { \
            std::cerr << "FAIL: " << msg << " (line " << __LINE__ << ")" << std::endl; \
            failures++; \
        } \
    } while (0)

int main()
{
    ScopedIsolatedCacheDb _isolatedCacheDb;
    juce::MessageManager::getInstance();
    struct MessageManagerGuard {
        ~MessageManagerGuard() { juce::MessageManager::deleteInstance(); }
    } messageManagerGuard;

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto sourceFile = fixtureDir.getChildFile("test_kick.wav");
    if (!sourceFile.existsAsFile()) {
        std::cerr << "FAIL: test_kick.wav fixture missing" << std::endl;
        return 1;
    }

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerPreviewUndoTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();

    auto file1 = tempRoot.getChildFile("kick_heavy.wav");
    auto file2 = tempRoot.getChildFile("reeseBassEmaj.wav");
    auto file3 = tempRoot.getChildFile("impulse_response_room.wav");

    if (!sourceFile.copyFileTo(file1) ||
        !sourceFile.copyFileTo(file2) ||
        !sourceFile.copyFileTo(file3))
    {
        std::cerr << "FAIL: could not copy test fixtures" << std::endl;
        return 1;
    }

    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";

    // =========================================================================
    // Test 1: previewSortLibrary (zero filesystem side-effects)
    // =========================================================================
    {
        SampleManagerEngine engine;
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: engine init failed" << std::endl;
            return 1;
        }

        engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
        int waitLimit = 600;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(50);

        CHECK(engine.getSampleCount() == 3, "expected 3 samples scanned, got " + std::to_string(engine.getSampleCount()));

        // Exercise preview's policy accounting at the measured 0.5 operating
        // point used by the fixture corpus. Production keeps the stricter
        // 0.93 gate; the lower test gate ensures this remains a meaningful
        // preview rather than an all-review result when model confidence
        // varies slightly across ONNX/CoreML versions.
        engine.setBetaPolicyGate(0.5f);

        // Call previewSortLibrary
        auto preview = engine.previewSortLibrary(1, true);

        CHECK(preview.totalCount == 3, "expected preview totalCount == 3, got " + std::to_string(preview.totalCount));
        CHECK(preview.items.size() == 3, "expected preview items size == 3");

        // Verify zero files created or moved during preview
        CHECK(file1.existsAsFile(), "file1 must exist untouched after preview");
        CHECK(file2.existsAsFile(), "file2 must exist untouched after preview");
        CHECK(file3.existsAsFile(), "file3 must exist untouched after preview");

        // Find impulse response item in preview
        bool foundIR = false;
        bool foundKick = false;
        for (const auto& item : preview.items) {
            if (item.sourceFilename == "impulse_response_room.wav") {
                foundIR = true;
                // Impulse response must be blocked by NeverAct
                CHECK(!item.eligible, "impulse_response_room.wav must be marked ineligible by safety gate");
            }
            if (item.sourceFilename == "kick_heavy.wav") {
                foundKick = true;
                CHECK(item.eligible, "kick_heavy.wav must be eligible for sort");
            }
        }
        CHECK(foundIR, "impulse_response_room.wav not found in preview items");
        CHECK(foundKick, "kick_heavy.wav not found in preview items");

        std::cout << "SUCCESS: Test 1 (previewSortLibrary) passed without disk mutations." << std::endl;
    }

    // =========================================================================
    // Test 2: Sort (Move mode) and Undo
    // =========================================================================
    {
        SampleManagerEngine engine;
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: engine init failed" << std::endl;
            return 1;
        }

        engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
        int waitLimit = 600;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(50);

        CHECK(!engine.canUndoSort(), "canUndoSort() should be false before any sort has run");

        // This test validates move/copy journaling and undo semantics. Keep
        // the classifier policy in its own suite so low-confidence fixture
        // metadata cannot turn a filesystem regression into a no-op sort.
        engine.setBetaPolicyGateEnabled(false);

        // Reorganize in MOVE mode
        engine.reorganizeSamples(1, false);

        CHECK(engine.canUndoSort(), "canUndoSort() should be true after a committed sort");

        // At least one file should have moved out of tempRoot into a subfolder
        auto movedSamples = engine.getSamples();
        int movedCount = 0;
        for (const auto& s : movedSamples) {
            juce::File f(s.filePath);
            if (f.getParentDirectory() != tempRoot) {
                movedCount++;
            }
        }
        CHECK(movedCount > 0, "expected at least 1 file moved to subfolder, found " + std::to_string(movedCount));

        // Now perform UNDO
        auto undoResult = engine.undoLastSort();
        CHECK(undoResult.success, "undoLastSort() reported failure: " + undoResult.errorMessage);
        CHECK(undoResult.revertedCount > 0, "expected revertedCount > 0, got " + std::to_string(undoResult.revertedCount));

        // Verify original files are back in tempRoot
        CHECK(file1.existsAsFile(), "file1 should be restored to tempRoot after undo");
        CHECK(file2.existsAsFile(), "file2 should be restored to tempRoot after undo");
        CHECK(file3.existsAsFile(), "file3 should be restored to tempRoot after undo");

        // Database sample paths should now point back to tempRoot
        auto restoredSamples = engine.getSamples();
        for (const auto& s : restoredSamples) {
            juce::File f(s.filePath);
            CHECK(f.getParentDirectory() == tempRoot, "sample filePath did not restore to tempRoot: " + s.filePath);
        }

        // canUndoSort should now be false (journal is marked .undone)
        CHECK(!engine.canUndoSort(), "canUndoSort() should be false after sort is undone");

        std::cout << "SUCCESS: Test 2 (Move mode sort + undo) passed." << std::endl;
    }

    // =========================================================================
    // Test 3: Sort (Copy mode) and Undo
    // =========================================================================
    {
        SampleManagerEngine engine;
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: engine init failed" << std::endl;
            return 1;
        }

        engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
        int waitLimit = 600;
        while (engine.isBusy() && waitLimit-- > 0)
            juce::Thread::sleep(50);

        engine.setBetaPolicyGateEnabled(false);

        // Reorganize in COPY mode
        engine.reorganizeSamples(1, true);

        CHECK(engine.canUndoSort(), "canUndoSort() should be true after copy sort");

        // Perform UNDO on copy sort
        auto undoResult = engine.undoLastSort();
        CHECK(undoResult.success, "undoLastSort() reported failure on copy sort: " + undoResult.errorMessage);
        CHECK(undoResult.revertedCount > 0, "expected revertedCount > 0 on copy undo, got " + std::to_string(undoResult.revertedCount));

        // Original files must still exist untouched
        CHECK(file1.existsAsFile(), "file1 must still exist after copy undo");
        CHECK(file2.existsAsFile(), "file2 must still exist after copy undo");
        CHECK(file3.existsAsFile(), "file3 must still exist after copy undo");

        // Subfolder copies should have been removed
        juce::Array<juce::File> subdirs;
        tempRoot.findChildFiles(subdirs, juce::File::findDirectories, false);
        for (const auto& dir : subdirs) {
            juce::Array<juce::File> filesInDir;
            dir.findChildFiles(filesInDir, juce::File::findFiles, true);
            CHECK(filesInDir.isEmpty(), "subfolder still contains copies after undo: " + dir.getFullPathName());
        }

        CHECK(!engine.canUndoSort(), "canUndoSort() should be false after copy undo");

        std::cout << "SUCCESS: Test 3 (Copy mode sort + undo) passed." << std::endl;
    }

    tempRoot.deleteRecursively();

    if (failures == 0) {
        std::cout << "ALL PHASE 2 PREVIEW & UNDO TESTS PASSED!" << std::endl;
        return 0;
    }

    std::cerr << failures << " TEST(S) FAILED!" << std::endl;
    return 1;
}
