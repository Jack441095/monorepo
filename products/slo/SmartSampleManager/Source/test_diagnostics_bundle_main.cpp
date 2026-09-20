#include <iostream>
#include "SampleManagerEngine.h"
#include "AbletonTaxonomy.h"
#include "AcousticClassifierWeights.h"
#include "TestCacheDbIsolation.h"

// F-04 contract test for buildDiagnosticsBundle(): scans two fixtures plus
// one non-audio file (which must be counted as skipped, not admitted), then
// proves the exported JSON parses and carries every required section with
// sane values. Export-only shape -- never touches the evidence-packet import
// contract (distinct record_type).

static int fails = 0;
static void check(const char* name, bool cond) {
    std::cout << (cond ? "  PASS  " : "  FAIL  ") << name << "\n";
    if (!cond) ++fails;
}

int main() {
    ScopedIsolatedCacheDb _isolatedCacheDb; // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                        .getChildFile("SmartSampleManagerDiagTest_" + juce::Uuid().toString());
    tempRoot.createDirectory();
    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    if (!fixtureDir.getChildFile("test_kick.wav").copyFileTo(tempRoot.getChildFile("a.wav"))
        || !fixtureDir.getChildFile("test_unique.wav").copyFileTo(tempRoot.getChildFile("b.wav"))
        || !tempRoot.getChildFile("notes.txt").replaceWithText("not audio")) {
        std::cerr << "FAIL: could not set up test fixtures" << std::endl;
        return 1;
    }

    SampleManagerEngine engine;
    const std::string modelPath =
        std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    int waitLimit = 200;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);
    if (engine.isBusy()) {
        std::cerr << "FAIL: engine still busy after scan wait" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    const std::string bundle = engine.buildDiagnosticsBundle();
    check("bundle non-empty", !bundle.empty());

    juce::var parsed;
    const juce::Result parseResult = juce::JSON::parse(bundle, parsed);
    check("bundle parses as JSON", parseResult.wasOk() && parsed.isObject());
    if (!parsed.isObject()) {
        tempRoot.deleteRecursively();
        return fails == 0 ? 0 : 1;
    }

    check("record_type is slo_diagnostics_bundle",
          parsed["record_type"].toString() == "slo_diagnostics_bundle");
    check("schema_version is 1", static_cast<int>(parsed["schema_version"]) == 1);

    const juce::var models = parsed["models"];
    check("models section present", models.isObject());
    check("classification_head version matches frozen weights",
          static_cast<int>(models["classification_head"]) == AcousticWeights::modelVersion);
    check("taxonomy version matches live taxonomy",
          static_cast<int>(models["taxonomy"]) == AbletonTaxonomy::kTaxonomyVersion);
    check("embedding version present",
          static_cast<int>(models["embedding"]) == kEmbeddingModelVersion);
    check("onnxruntime version non-empty",
          models["onnxruntime"].toString().isNotEmpty());

    const juce::var ood = parsed["ood_gate"];
    check("ood_gate section present", ood.isObject());
    const juce::var perClass = ood["per_class"];
    check("16 per-class thresholds", perClass.isArray() && perClass.size() == 16);
    bool thresholdsSane = perClass.isArray() && perClass.size() == 16;
    for (int i = 0; thresholdsSane && i < perClass.size(); ++i) {
        const double t = static_cast<double>(perClass[i]["threshold"]);
        const bool nameOk = perClass[i]["class"].toString().isNotEmpty();
        thresholdsSane = nameOk && t > 0.0 && t < 1.0;
    }
    check("per-class thresholds sane (named, in (0,1))", thresholdsSane);

    const juce::var library = parsed["library"];
    check("library.samples == 2", static_cast<int>(library["samples"]) == 2);
    const juce::var receipt = library["last_scan_receipt"];
    check("receipt.added == 2", static_cast<int>(receipt["added"]) == 2);
    check("receipt.skipped_non_audio >= 1 (the .txt)",
          static_cast<int>(receipt["skipped_non_audio"]) >= 1);

    const juce::var splits = parsed["evidence_splits"];
    check("evidence_splits.tag_source present", splits["tag_source"].isObject());
    check("evidence_splits.winning_evidence present", splits["winning_evidence"].isObject());

    const juce::var logTail = parsed["log_tail"];
    check("log_tail.path present", logTail["path"].toString().isNotEmpty());

    tempRoot.deleteRecursively();
    std::cout << (fails == 0 ? "ALL DIAGNOSTICS BUNDLE CHECKS PASSED"
                             : "DIAGNOSTICS BUNDLE CHECKS FAILED") << std::endl;
    juce::MessageManager::deleteInstance();
    return fails == 0 ? 0 : 1;
}
