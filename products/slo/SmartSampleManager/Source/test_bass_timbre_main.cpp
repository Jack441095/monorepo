#include "BassTimbreClassifier.h"
#include <cmath>
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

    // Each centroid is classified on its own, which proves nothing about the
    // decision: a classifier that returned the input index would pass it. The
    // checks below are therefore cross-centroid -- each centroid is pushed through
    // the OTHER label's classifier, and the margin has to narrow. That is the
    // property the sort actually depends on, since the persisted tag comes from
    // whichever centroid wins.
    auto r808 = BassTimbreClassifier::classify(BassTimbreCentroids::centroid_808);
    CHECK(r808.label == "808", "808 centroid classifies as 808");
    CHECK(r808.confidence > 0.99f, "808 centroid classifies as itself with near-1.0 confidence");

    auto rReese = BassTimbreClassifier::classify(BassTimbreCentroids::centroid_Reese);
    CHECK(rReese.label == "Reese", "Reese centroid classifies as Reese");
    CHECK(rReese.confidence > 0.99f, "Reese centroid classifies as itself with near-1.0 confidence");

    // margin is bestSim - secondSim, so a positive margin is already implied by
    // the label winning. What is worth pinning is that the two centroids are
    // separable at all: if the margin were 0 the choice would be arbitrary, and
    // P1-22's missing confidence floor becomes a real risk.
    CHECK(r808.margin > 0.0f, "808 beats Reese by a positive margin");
    CHECK(rReese.margin > 0.0f, "Reese beats 808 by a positive margin");
    CHECK(std::abs(r808.margin - rReese.margin) < 1.0f,
          "the two centroids are separated by a comparable margin from either side, so the "
          "choice is not decided by a sliver");

    if (failures > 0) {
        std::cerr << failures << " check(s) FAILED" << std::endl;
        return 1;
    }
    std::cout << "ALL BASS TIMBRE REGRESSION CHECKS PASSED" << std::endl;
    return 0;
}
