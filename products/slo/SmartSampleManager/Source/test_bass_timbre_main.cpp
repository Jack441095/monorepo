#include "BassTimbreClassifier.h"
#include <iostream>

// Fine-Grained Subcategorization V1, Phase 9. Regression sanity test:
// each class's own centroid must classify as itself with a clean margin --
// guards against a future accidental centroid/header regeneration mistake
// (e.g. swapped class order) rather than re-deriving the full held-out
// accuracy number, which is already reported in
// docs/classification/BASS_TIMBRE_TAG_V1_REPORT.md and not re-verified here.

static int failures = 0;
#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } \
         else { std::cout << "  ok: " << msg << std::endl; } } while (0)

int main()
{
    std::cout << "Running BassTimbreClassifier regression tests..." << std::endl;

    auto r808 = BassTimbreClassifier::classify(BassTimbreCentroids::centroid_808);
    CHECK(r808.label == "808", "808 centroid classifies as 808");
    CHECK(r808.confidence > 0.99f, "808 centroid classifies as itself with near-1.0 confidence");
    CHECK(r808.margin > 0.0f, "808 centroid has a positive margin over Reese");

    auto rReese = BassTimbreClassifier::classify(BassTimbreCentroids::centroid_Reese);
    CHECK(rReese.label == "Reese", "Reese centroid classifies as Reese");
    CHECK(rReese.confidence > 0.99f, "Reese centroid classifies as itself with near-1.0 confidence");
    CHECK(rReese.margin > 0.0f, "Reese centroid has a positive margin over 808");

    if (failures > 0) {
        std::cerr << failures << " check(s) FAILED" << std::endl;
        return 1;
    }
    std::cout << "ALL BASS TIMBRE REGRESSION CHECKS PASSED" << std::endl;
    return 0;
}
