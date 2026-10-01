#include "HiHatTypeClassifier.h"
#include <cmath>
#include <iostream>

// Fine-Grained Subcategorization V1, Phase 11. Regression sanity test:
// each class's own centroid must classify as itself with a clean margin --
// guards against a future accidental centroid/header regeneration mistake
// rather than re-deriving the full held-out accuracy number, which is
// already reported in docs/classification/HIHAT_TYPE_TAG_V1_REPORT.md.

static int failures = 0;
#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } \
         else { std::cout << "  ok: " << msg << std::endl; } } while (0)

int main()
{
    std::cout << "Running HiHatTypeClassifier regression tests..." << std::endl;

    // See the note in test_bass_timbre_main.cpp: a positive margin is implied by
    // the label winning, so the interesting property is separability, not each
    // centroid against itself.
    auto rOpen = HiHatTypeClassifier::classify(HiHatTypeCentroids::centroid_Open);
    CHECK(rOpen.label == "Open", "Open centroid classifies as Open");
    CHECK(rOpen.confidence > 0.99f, "Open centroid classifies as itself with near-1.0 confidence");

    auto rClosed = HiHatTypeClassifier::classify(HiHatTypeCentroids::centroid_Closed);
    CHECK(rClosed.label == "Closed", "Closed centroid classifies as Closed");
    CHECK(rClosed.confidence > 0.99f, "Closed centroid classifies as itself with near-1.0 confidence");

    CHECK(rOpen.margin > 0.0f, "Open beats Closed by a positive margin");
    CHECK(rClosed.margin > 0.0f, "Closed beats Open by a positive margin");
    CHECK(std::abs(rOpen.margin - rClosed.margin) < 1.0f,
          "the two centroids are separated by a comparable margin from either side");

    if (failures > 0) {
        std::cerr << failures << " check(s) FAILED" << std::endl;
        return 1;
    }
    std::cout << "ALL HI-HAT TYPE REGRESSION CHECKS PASSED" << std::endl;
    return 0;
}
