#include <cstdlib>
#include <iostream>

#include "ClassificationPresentation.h"

namespace {

int failures = 0;

void expectEqual(const std::string& actual, const std::string& expected, const char* label)
{
    if (actual != expected) {
        std::cerr << "FAIL: " << label << " (got '" << actual
                  << "', expected '" << expected << "')" << std::endl;
        ++failures;
    }
}

void expectTrue(bool condition, const char* label)
{
    if (!condition) {
        std::cerr << "FAIL: " << label << std::endl;
        ++failures;
    }
}

} // namespace

int main()
{
    expectEqual(ClassificationPresentation::primaryLabel("", "", "Kick", "ml_ood"),
                "Needs review",
                "ML OOD must not fall back to the stale coarse label");
    expectEqual(ClassificationPresentation::filterText("", "", "Kick", "ml_ood"),
                "Unknown Other",
                "ML OOD must remain visible through the default Other filter");
    expectTrue(!ClassificationPresentation::isNeutral("Needs review"),
               "Needs review is an intentional visible state");

    expectEqual(ClassificationPresentation::primaryLabel("Drums", "Kick", "Kick", "heuristic"),
                "Kick",
                "known taxonomy should use the subcategory label");
    expectEqual(ClassificationPresentation::filterText("Drums", "Kick", "Kick", "heuristic"),
                "Kick Drums Kick",
                "known taxonomy filter text should retain taxonomy and legacy fields");
    expectEqual(ClassificationPresentation::filterCategory("Drums", "Kick"),
                "Drums",
                "category pills should prefer the broad taxonomy category");
    expectEqual(ClassificationPresentation::filterCategory("", "Kick"),
                "Kick",
                "legacy rows should fall back to their instrument label");
    expectEqual(ClassificationPresentation::filterCategory("", "Unknown"),
                "Other",
                "unknown sentinel should not become a clickable filter");
    expectTrue(ClassificationPresentation::matchesCategoryFilter("Kick Drums Kick", "Drums"),
               "category filter should match taxonomy text");
    expectTrue(ClassificationPresentation::matchesCategoryFilter("Hi-Hat", "Hi-Hat"),
               "category filter should preserve the hi-hat alias");
    expectTrue(!ClassificationPresentation::matchesCategoryFilter("Bass Loop", "Vocals"),
               "category filter should reject unrelated taxonomy text");
    expectEqual(ClassificationPresentation::primaryLabel("", "", "Bass", "metadata"),
                "Bass",
                "metadata-only fallback should remain visible");
    expectEqual(ClassificationPresentation::primaryLabel("", "", "Unknown", "unclassified"),
                "",
                "unknown unclassified sample should have no known label");

    expectEqual(ClassificationPresentation::evidenceLabel("heuristic", "EMBEDDED_METADATA"),
                "metadata-assisted",
                "embedded metadata provenance should be explicit");
    expectEqual(ClassificationPresentation::evidenceLabel("heuristic", "DSP"),
                "audio-only",
                "DSP provenance should be explicit");
    expectEqual(ClassificationPresentation::evidenceLabel("physics", "PHYSICS"),
                "physical acoustics",
                "Physical acoustics provenance should be explicit");
    expectEqual(ClassificationPresentation::evidenceLabel("ml_ood", "UNKNOWN"),
                "OOD abstention",
                "OOD provenance should be explicit");
    expectEqual(ClassificationPresentation::evidenceLabel("user", "USER_OVERRIDE"),
                "user override",
                "user provenance should be explicit");
    expectEqual(ClassificationPresentation::taxonomyVersionLabel(1),
                "taxonomy v1",
                "taxonomy version should be visible");
    expectEqual(ClassificationPresentation::taxonomyVersionLabel(0),
                "taxonomy not run",
                "unclassified taxonomy should be explicit");
    expectEqual(ClassificationPresentation::uncertaintyReason("ml_ood", "UNKNOWN", 0.95f),
                "outside the known audio domain",
                "OOD should explain why it abstained");
    expectEqual(ClassificationPresentation::uncertaintyReason("heuristic", "FILENAME", 0.82f),
                "name or folder evidence only",
                "filename-only evidence should be called out");
    expectEqual(ClassificationPresentation::uncertaintyReason("ml_v3", "DSP", 0.42f),
                "weak evidence agreement",
                "low confidence should expose a reason");
    expectEqual(ClassificationPresentation::uncertaintyReason("user", "USER_OVERRIDE", 1.0f),
                "",
                "user overrides should not be marked uncertain");

    if (failures != 0) {
        std::cerr << failures << " classification presentation test(s) failed" << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << "Classification presentation tests passed" << std::endl;
    return EXIT_SUCCESS;
}
