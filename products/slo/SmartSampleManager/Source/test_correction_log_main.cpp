#include "CorrectionLog.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <filesystem>
static int fails = 0;
static void check(const char* n, bool c) {
    std::cout << (c ? "  PASS  " : "  FAIL  ") << n << "\n"; if (!c) ++fails;
}
int main() {
    using namespace slo;
    std::cout << "correction log:\n";
    const std::string tmp = "/tmp/slo_corr_test.jsonl";
    std::filesystem::remove(tmp);

    CorrectionRecord r;
    r.filePath = "/lib/Perc/Shaker \"odd\" name.wav";
    r.contentHash = "abc123";
    r.originalCategory = "Drums"; r.originalSubcategory = "Percussion";
    r.originalEvidence = "DSP"; r.originalConfidence = 0.42f;
    r.correctedCategory = "Drums"; r.correctedSubcategory = "Hi-Hat";
    r.correctionType = "taxonomy_gap";
    r.userNote = "it's a closed hat\nnot perc";
    r.taxonomyVersion = 7; r.classifierVersion = 4;

    check("a real correction is written", appendCorrection(r, tmp));
    check("file exists", std::filesystem::exists(tmp));

    CorrectionRecord noop = r;
    noop.correctedSubcategory = "Percussion"; noop.userNote = "";
    check("a no-op edit is NOT logged", !appendCorrection(noop, tmp));

    r.correctedSubcategory = "Clap";
    check("a second correction appends", appendCorrection(r, tmp));
    std::ifstream in(tmp);
    std::stringstream ss; ss << in.rdbuf();
    const std::string text = ss.str();
    int lines = 0;
    for (char c : text) if (c == '\n') ++lines;
    check("append-only: two records, nothing rewritten", lines == 2);

    check("quotes and newlines are escaped, one record per line",
          text.find("\\\"odd\\\"") != std::string::npos && text.find("\\n") != std::string::npos);
    check("the ORIGINAL prediction is captured",
          text.find("\"original_subcategory\":\"Percussion\"") != std::string::npos);
    check("original confidence captured", text.find("\"original_confidence\":0.42") != std::string::npos);
    check("correction semantics captured", text.find("\"correction_type\":\"taxonomy_gap\"") != std::string::npos);
    check("versions stamped", text.find("\"taxonomy_version\":7") != std::string::npos
                              && text.find("\"classifier_version\":4") != std::string::npos);
    check("lands as pending, not ground truth", text.find("\"status\":\"pending\"") != std::string::npos);
    check("NO audio is stored", text.find("pcm") == std::string::npos && text.find("samples\":[") == std::string::npos);

    CorrectionRecord empty; empty.correctedSubcategory = "Kick";
    check("an empty path is rejected", !appendCorrection(empty, tmp));
    check("a bad log path fails quietly, never throws",
          !appendCorrection(r, "/nonexistent-root-xyz/a/b.jsonl"));

    std::filesystem::remove(tmp);
    std::cout << (fails == 0 ? "\nall correction log tests passed\n" : "\nFAILURES\n");
    return fails == 0 ? 0 : 1;
}
