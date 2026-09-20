#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>

#include "AcousticClassifier.h"
#include "BassTimbreClassifier.h"
#include "HiHatTypeClassifier.h"

// Pure-logic regression test for the classifier's embedding boundary.  This
// intentionally has no JUCE, ONNX, or audio dependency so it can run as part
// of the low-cost qualification groups.

namespace {

int failures = 0;

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
    float zeroEmbedding[AcousticWeights::embeddingDim] = {};
    expectTrue(!AcousticClassifier::isValidEmbedding(zeroEmbedding),
               "zero embedding must be rejected");

    float nanEmbedding[AcousticWeights::embeddingDim] = {};
    nanEmbedding[0] = std::numeric_limits<float>::quiet_NaN();
    expectTrue(!AcousticClassifier::isValidEmbedding(nanEmbedding),
               "NaN embedding must be rejected");

    float infEmbedding[AcousticWeights::embeddingDim] = {};
    infEmbedding[0] = std::numeric_limits<float>::infinity();
    expectTrue(!AcousticClassifier::isValidEmbedding(infEmbedding),
               "Inf embedding must be rejected");

    expectTrue(!AcousticClassifier::isValidEmbedding(nullptr),
               "null embedding must be rejected");

    float extremeEmbedding[AcousticWeights::embeddingDim] = {};
    extremeEmbedding[0] = std::numeric_limits<float>::max();
    expectTrue(!AcousticClassifier::isValidEmbedding(extremeEmbedding),
               "an arithmetic-overflow-scale embedding must be rejected");

    const auto extremeResult = AcousticClassifier::classify(extremeEmbedding);
    expectTrue(extremeResult.subcategory.empty() && extremeResult.isOod,
               "an arithmetic-overflow-scale embedding must remain unknown");

    const auto invalidResult = AcousticClassifier::classify(nanEmbedding);
    expectTrue(invalidResult.subcategory.empty(),
               "invalid embedding must not produce a subcategory");
    expectTrue(invalidResult.confidence == 0.0f,
               "invalid embedding must have zero confidence");
    expectTrue(invalidResult.isOod,
               "invalid embedding must be marked OOD");

    expectTrue(BassTimbreClassifier::classify(nullptr).label.empty(),
               "bass timbre classifier must reject null embedding");
    expectTrue(BassTimbreClassifier::classify(zeroEmbedding).label.empty(),
               "bass timbre classifier must reject zero embedding");
    expectTrue(BassTimbreClassifier::classify(nanEmbedding).label.empty(),
               "bass timbre classifier must reject non-finite embedding");
    expectTrue(HiHatTypeClassifier::classify(nullptr).label.empty(),
               "hi-hat classifier must reject null embedding");
    expectTrue(HiHatTypeClassifier::classify(zeroEmbedding).label.empty(),
               "hi-hat classifier must reject zero embedding");
    expectTrue(HiHatTypeClassifier::classify(nanEmbedding).label.empty(),
               "hi-hat classifier must reject non-finite embedding");

    float finiteEmbedding[AcousticWeights::embeddingDim] = {};
    finiteEmbedding[0] = 1.0f;
    expectTrue(AcousticClassifier::isValidEmbedding(finiteEmbedding),
               "ordinary finite embedding must be accepted");

    const auto finiteResult = AcousticClassifier::classify(finiteEmbedding);
    expectTrue(std::isfinite(finiteResult.confidence),
               "finite embedding classification confidence must be finite");
    expectTrue(std::isfinite(finiteResult.embeddingNorm),
               "finite embedding norm must be finite");
    expectTrue(std::isfinite(finiteResult.centroidCosineSimilarity),
               "finite embedding centroid score must be finite");
    expectTrue(std::isfinite(finiteResult.logitEnergy),
               "finite embedding logit energy must be finite");

    // The validator accepts vectors whose total squared norm is close to the
    // largest representable float. The classifier's derived norm must remain
    // finite too; this guards against reintroducing a float-only accumulation
    // in the OOD cosine path after the input boundary has passed.
    float nearLimitEmbedding[AcousticWeights::embeddingDim] = {};
    const float nearLimitComponent = std::sqrt(
        std::numeric_limits<float>::max() * 0.49f);
    nearLimitEmbedding[0] = nearLimitComponent;
    nearLimitEmbedding[1] = nearLimitComponent;
    expectTrue(AcousticClassifier::isValidEmbedding(nearLimitEmbedding),
               "near-limit finite embedding remains within the validated norm bound");
    const auto nearLimitResult = AcousticClassifier::classify(nearLimitEmbedding);
    expectTrue(std::isfinite(nearLimitResult.confidence),
               "near-limit accepted embedding has finite classifier confidence");
    expectTrue(std::isfinite(nearLimitResult.entropy),
               "near-limit accepted embedding has finite classifier entropy");
    expectTrue(std::isfinite(nearLimitResult.embeddingNorm),
               "near-limit accepted embedding has a finite runtime norm");
    expectTrue(std::isfinite(nearLimitResult.centroidCosineSimilarity),
               "near-limit accepted embedding has a finite centroid score");
    expectTrue(std::isfinite(nearLimitResult.logitEnergy),
               "near-limit accepted embedding has finite logit energy");
    const auto nearLimitBass = BassTimbreClassifier::classify(nearLimitEmbedding);
    expectTrue(std::isfinite(nearLimitBass.confidence)
                   && std::isfinite(nearLimitBass.margin),
               "near-limit accepted embedding has finite bass-timbre diagnostics");
    const auto nearLimitHiHat = HiHatTypeClassifier::classify(nearLimitEmbedding);
    expectTrue(std::isfinite(nearLimitHiHat.confidence)
                   && std::isfinite(nearLimitHiHat.margin),
               "near-limit accepted embedding has finite hi-hat diagnostics");

    if (failures != 0) {
        std::cerr << failures << " classifier input safety test(s) failed" << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << "AcousticClassifier input safety tests passed" << std::endl;
    return EXIT_SUCCESS;
}
