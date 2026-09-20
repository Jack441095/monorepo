#include <algorithm>
#include <iostream>
#include "SampleManagerEngine.h"
#include "AbletonXmpWriter.h"
#include "TestCacheDbIsolation.h"

namespace {

struct ScopedFixtureDirectory
{
    juce::File dir = juce::File::getSpecialLocation(juce::File::tempDirectory)
                         .getChildFile("SmartSampleManagerJourneyTest_" + juce::Uuid().toString());

    ScopedFixtureDirectory() { dir.createDirectory(); }
    ~ScopedFixtureDirectory() { dir.deleteRecursively(); }

    ScopedFixtureDirectory(const ScopedFixtureDirectory&) = delete;
    ScopedFixtureDirectory& operator=(const ScopedFixtureDirectory&) = delete;
};

} // namespace

int main(int argc, char* argv[]) {
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    // Initialize JUCE MessageManager for async calls
    juce::MessageManager::getInstance();

    SampleManagerEngine engine;
    
    // Load ONNX model
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: Engine initialization failed." << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }

    // CLI mode is deliberately read-only.  This executable participates in
    // release qualification and must be safe when pointed at a real library;
    // the old path automatically called reorganizeSamples(..., move=false)
    // after scanning, which could relocate a user's source files merely by
    // running a diagnostic command.
    if (argc > 1) {
        std::string scanPath = argv[1];
        std::cout << "CLI Mode (read-only): Scanning path: " << scanPath << std::endl;
        
        engine.addPathToQueue(scanPath);

        // Wait for background processing threads to finish
        std::cout << "Processing samples on background thread..." << std::endl;
        while (engine.isBusy()) {
            juce::Thread::sleep(200);
        }

        auto samples = engine.getSamples();
        std::cout << "\nScanned and mapped " << samples.size() << " samples:" << std::endl;
        std::cout << "==========================================" << std::endl;
        for (const auto& s : samples) {
            std::cout << "  * Name: " << s.name << "\n"
                      << "    Path: " << s.filePath << "\n"
                      << "    Type: " << s.instrumentType << "\n"
                      << "    Key:  " << s.key << "\n"
                      << "    BPM:  " << s.bpm << "\n"
                      << "    UMAP: (" << s.x << ", " << s.y << ")\n"
                      << "------------------------------------------" << std::endl;
        }

        std::cout << "\nRead-only diagnostic complete; no source files or metadata were changed."
                  << std::endl;

        juce::MessageManager::deleteInstance();
        return 0;
    }

    // Standard integration test mode
    std::cout << "Starting Smart Sample Manager Integration Test..." << std::endl;

    // All write-capable assertions below run against a disposable copy.  The
    // prior test used the checked-in test_kick.wav directly for XMP and
    // TagLib writes, so a normal qualification run mutated repository data.
    ScopedFixtureDirectory fixtureDirectory;
    const auto sourceFixture = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR))
                                   .getChildFile("test_kick.wav");
    const auto disposableFixture = fixtureDirectory.dir.getChildFile("test_kick.wav");
    if (!sourceFixture.copyFileTo(disposableFixture)) {
        std::cerr << "FAIL: could not create disposable integration fixture." << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }

    // Queue and process the disposable WAV file.
    std::string testFile = disposableFixture.getFullPathName().toStdString();
    std::cout << "Processing test file: " << testFile << std::endl;
    engine.addPathToQueue(testFile);

    // Wait for background processing threads to finish
    int waitLimit = 50; // 5 seconds max
    while (engine.isBusy() && waitLimit > 0) {
        juce::Thread::sleep(100);
        waitLimit--;
    }

    // Verify embedding extraction and UMAP mapping coordinates
    auto samples = engine.getSamples();
    if (samples.empty()) {
        std::cerr << "FAIL: No samples processed." << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }

    const auto& s = samples.front();
    std::cout << "SUCCESS: Sample processed." << std::endl;
    std::cout << "  Name: " << s.name << std::endl;
    std::cout << "  Original BPM: " << s.bpm << std::endl;
    std::cout << "  Original Key: " << s.key << std::endl;
    std::cout << "  Original Type: " << s.instrumentType << std::endl;
    std::cout << "  Embedding dimension: " << s.embedding.size() << std::endl;

    if (s.embedding.size() != 512) {
        std::cerr << "FAIL: Embedding size mismatch (expected 512, got " << s.embedding.size() << ")." << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }

    // Ableton taxonomy classification runs as part of the same prepareFile()
    // pass -- verify it actually produced a result through the real pipeline
    // (file scan -> DSP features -> AbletonTaxonomy::classify), not just in
    // TestTaxonomy's isolated unit tests.
    std::cout << "  Ableton Category: " << s.category << std::endl;
    std::cout << "  Ableton Subcategory: " << s.subcategory << std::endl;
    std::cout << "  Tag confidence: " << s.tagConfidence << " (source: " << s.tagSource << ")" << std::endl;
    std::cout << "  Duration: " << s.durationSeconds << "s" << std::endl;
    if (s.category.empty() || s.subcategory.empty() || s.tagSource != "heuristic" || s.durationSeconds <= 0.0f) {
        std::cerr << "FAIL: test_kick.wav was not classified by the Ableton taxonomy pipeline." << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }
    std::cout << "SUCCESS: Ableton taxonomy classification verified end-to-end." << std::endl;

    // Full Tier 2 -> Tier 3 pipeline: the classification above should be
    // writable straight through to a real Ableton XMP sidecar, proving the
    // engine's writeAbletonXmpTags() glue (category/subcategory -> keyword
    // string, secondaryTags -> flat keywords) works against real classifier
    // output, not just synthetic input like TestXmpWriter's unit tests use.
    auto xmpResult = engine.writeAbletonXmpTags(testFile);
    if (!xmpResult.success) {
        std::cerr << "FAIL: writeAbletonXmpTags failed: " << xmpResult.errorMessage << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }
    auto writtenTags = AbletonXmpWriter::readTagsForFile(testFile);
    std::string expectedKeyword = s.category + "|" + s.subcategory;
    bool foundExpectedKeyword = std::find(writtenTags.begin(), writtenTags.end(), expectedKeyword) != writtenTags.end();
    if (!foundExpectedKeyword) {
        std::cerr << "FAIL: Ableton XMP sidecar did not contain the expected keyword \""
                   << expectedKeyword << "\"." << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }
    std::cout << "SUCCESS: full pipeline verified -- classification (\"" << expectedKeyword
               << "\") was written through to a real Ableton XMP sidecar and read back correctly." << std::endl;
    // The sidecar lives inside ScopedFixtureDirectory and is removed by its
    // destructor together with the disposable audio copy.

    // Test Metadata editing via TagLib
    std::cout << "Updating metadata (BPM=128, Key=A Minor, Type=Kick)..." << std::endl;
    engine.updateMetadataAsync(testFile, 128.0f, "A Minor", "Kick");

    // Wait for the async write to complete
    juce::Thread::sleep(1200);

    // Retrieve updated data
    samples = engine.getSamples();
    const auto& s2 = samples.front();
    std::cout << "Updated Metadata read back:" << std::endl;
    std::cout << "  BPM: " << s2.bpm << std::endl;
    std::cout << "  Key: " << s2.key << std::endl;
    std::cout << "  Type: " << s2.instrumentType << std::endl;

    if (static_cast<int>(s2.bpm) != 128 || s2.key != "A Minor" || s2.instrumentType != "Kick") {
        std::cerr << "FAIL: Metadata update read-back mismatch." << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }

    std::cout << "SUCCESS: TagLib metadata read/write verified." << std::endl;

    // Clean up JUCE message manager
    juce::MessageManager::deleteInstance();
    std::cout << "ALL INTEGRATION TESTS PASSED SUCCESSFULLY!" << std::endl;
    return 0;
}
