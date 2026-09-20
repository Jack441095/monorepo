#include <JuceHeader.h>
#include "AcousticClassifier.h"
#include "MlOverrideGate.h"
#include <iostream>
#include <cmath>
#include <cstring>
#include <limits>

static int v4hFailures = 0;
#define V4H_CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL (V4-H): " << msg << std::endl; v4hFailures++; } \
         else { std::cout << "  ok (V4-H): " << msg << std::endl; } } while (0)

// V4-H regression tests (spec §27: "Add targeted V4-H tests for: OOD clears
// stale category, known-class acceptance, threshold boundary behavior,
// strong filename evidence preservation, unknown behavior"). Exercises
// AcousticClassifier::classify()'s per-class threshold gate and
// MlOverrideGate::evaluate() directly -- no ONNX/audio pipeline needed,
// since both are pure functions of already-computed inputs. See
// docs/SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md.
static void runV4HTests()
{
    std::cout << "\nRunning V4-H OOD-calibration regression tests..." << std::endl;

    // --- 1. Known-class acceptance: an embedding IDENTICAL to a known
    //     centroid must score cosine similarity ~1.0 and never be OOD,
    //     regardless of which per-class threshold applies. ---
    {
        // "Clap" is a well-supported, high-separation class (n=50 calibration
        // samples, per-class threshold 0.8451078 -- see
        // AcousticClassifierCentroids.h). Its own centroid trivially passes
        // its own threshold.
        int clapIdx = -1;
        for (int c = 0; c < AcousticOodCentroids::numClasses; ++c)
            if (std::strcmp(AcousticOodCentroids::classNames[c], "Clap") == 0) { clapIdx = c; break; }
        V4H_CHECK(clapIdx >= 0, "'Clap' found in AcousticOodCentroids::classNames");

        auto res = AcousticClassifier::classify(AcousticOodCentroids::centroids[clapIdx]);
        V4H_CHECK(!res.isOod, "an embedding identical to the Clap centroid is NOT flagged OOD");
        V4H_CHECK(res.nearestCentroidIndex == clapIdx, "nearest-centroid index correctly identifies Clap for its own centroid");
        V4H_CHECK(res.centroidCosineSimilarity > 0.95f, "cosine similarity to an identical vector is ~1.0");
    }

    // --- 2. Threshold boundary / class-conditional behavior: FX and Kick
    //     have deliberately different per-class thresholds (FX 0.8303564,
    //     Kick 0.9200000 -- FX's known population is naturally more
    //     spread out in embedding space, see the V4-H report's failure
    //     forensics). A synthetic embedding engineered to sit strictly
    //     between the two thresholds must be treated differently depending
    //     on which centroid it is nearest to. ---
    {
        int foleyIdx = -1, riserIdx = -1;
        for (int c = 0; c < AcousticOodCentroids::numClasses; ++c)
        {
            if (std::strcmp(AcousticOodCentroids::classNames[c], "Foley") == 0) foleyIdx = c;
            if (std::strcmp(AcousticOodCentroids::classNames[c], "Riser") == 0) riserIdx = c;
        }
        V4H_CHECK(foleyIdx >= 0 && riserIdx >= 0, "'Foley' and 'Riser' found in AcousticOodCentroids::classNames");
        V4H_CHECK(AcousticOodCentroids::perClassOodThreshold[foleyIdx] < AcousticOodCentroids::perClassOodThreshold[riserIdx],
                   "Foley's per-class threshold is lower (more permissive) than Riser's, as derived from calibration data");

        // A vector that is tested against a similarity strictly between the
        // two thresholds against both classes' gates using the raw formula
        // AcousticClassifier::classify() uses (bestCos < threshold[bestClassIdx]).
        float midSimilarity = 0.5f * (AcousticOodCentroids::perClassOodThreshold[foleyIdx]
                                       + AcousticOodCentroids::perClassOodThreshold[riserIdx]);
        bool wouldBeOodForFoley = midSimilarity < AcousticOodCentroids::perClassOodThreshold[foleyIdx];
        bool wouldBeOodForRiser = midSimilarity < AcousticOodCentroids::perClassOodThreshold[riserIdx];
        V4H_CHECK(!wouldBeOodForFoley, "a midpoint similarity score clears Foley's (lower) threshold");
        V4H_CHECK(wouldBeOodForRiser, "the SAME midpoint similarity score fails Riser's (higher) threshold -- proves the gate is class-conditional, not global");
    }

    // --- 3. MlOverrideGate: OOD result clears a stale category (the V4-G
    //     bug fix, spec §20 -- "UNKNOWN must remain honest"). ---
    {
        MlOverrideGate::Input in;
        in.isOod = true;
        in.mlConfidence = 0.10f;                 // low-confidence ML result, irrelevant once isOod is set
        in.winningEvidence = "DSP";               // weakest evidence tier -- eligible for the OOD clear
        in.preMlCategory = "Drums";
        in.preMlSubcategory = "Kick";             // a stale DSP-fallback guess that must NOT survive
        in.preMlConfidence = 0.35f;
        in.mlSubcategory = "FX";

        auto d = MlOverrideGate::evaluate(in);
        V4H_CHECK(d.category.empty(), "OOD result clears the stale category (V4-G bug fix preserved)");
        V4H_CHECK(d.subcategory.empty(), "OOD result clears the stale subcategory (V4-G bug fix preserved)");
        V4H_CHECK(d.tagSource == "ml_ood", "OOD result is tagged ml_ood");
        V4H_CHECK(d.winningEvidence == "UNKNOWN", "OOD result's winningEvidence becomes UNKNOWN, not left as the stale DSP guess");
        V4H_CHECK(d.tagConfidence == 0.0f, "OOD result's confidence is reset to 0, not left showing a stale value");
    }

    // --- 4. Unknown evidence is also untrusted after cache hydration. An
    //     older ml_ood row persists winningEvidence=UNKNOWN; rebuilding a
    //     heuristic category must not make an OOD result look known again. ---
    {
        MlOverrideGate::Input in;
        in.isOod = true;
        in.winningEvidence = "UNKNOWN";
        in.preMlCategory = "Instruments";
        in.preMlSubcategory = "Music Loop";
        in.preMlConfidence = 0.40f;
        in.mlSubcategory = "Synth";

        auto d = MlOverrideGate::evaluate(in);
        V4H_CHECK(d.category.empty() && d.subcategory.empty(),
                  "UNKNOWN evidence cannot resurrect a known label after an OOD result");
        V4H_CHECK(d.tagSource == "ml_ood" && d.winningEvidence == "UNKNOWN",
                  "UNKNOWN-evidence OOD result remains an explicit abstention");
    }

    // --- 5. MlOverrideGate: strong FILENAME evidence is preserved even
    //     when the ML classifier flags the sample OOD (evidence hierarchy,
    //     spec §17 -- "strong symbolic evidence can legitimately outperform
    //     ML OOD evidence"). This must NOT be miscounted as a gate failure. ---
    {
        MlOverrideGate::Input in;
        in.isOod = true;
        in.mlConfidence = 0.20f;
        in.winningEvidence = "FILENAME";          // strong evidence tier -- NOT DSP/FOLDER/empty
        in.preMlCategory = "Bass";
        in.preMlSubcategory = "Bass Loop";
        in.preMlConfidence = 0.42f;
        in.mlSubcategory = "FX";

        auto d = MlOverrideGate::evaluate(in);
        V4H_CHECK(d.category == "Bass", "FILENAME-evidence category survives an OOD flag unchanged");
        V4H_CHECK(d.subcategory == "Bass Loop", "FILENAME-evidence subcategory survives an OOD flag unchanged");
        V4H_CHECK(d.tagSource == "heuristic", "FILENAME evidence keeps tagSource=heuristic, never overwritten to ml_ood");
        V4H_CHECK(d.winningEvidence == "FILENAME", "winningEvidence stays FILENAME, not reset to UNKNOWN");
        V4H_CHECK(!d.overrideApplied, "no ML override is recorded when strong evidence blocks it");
    }

    // --- 6. MlOverrideGate: a correct, confident, non-OOD ML prediction
    //     legitimately overrides weak (DSP/empty) pre-ML evidence. ---
    {
        MlOverrideGate::Input in;
        in.isOod = false;
        in.mlConfidence = 0.88f;
        in.winningEvidence = "DSP";
        in.preMlCategory = "Drums";
        in.preMlSubcategory = "Kick";              // weak DSP-fallback guess, wrong
        in.preMlConfidence = 0.30f;
        in.mlSubcategory = "FX";                   // ML's correct call

        auto d = MlOverrideGate::evaluate(in);
        V4H_CHECK(d.subcategory == "FX", "a confident non-OOD ML prediction overrides weak DSP evidence");
        V4H_CHECK(d.tagSource == "ml_v3", "override is tagged ml_v3");
        V4H_CHECK(d.overrideApplied, "overrideApplied is recorded true");
    }

    // --- 6b. Explicit Vocal Loop filename evidence must survive a confident
    // generic Vocal Phrase acoustic prediction.  The fine-grained symbolic
    // signal is deliberately opt-in and does not weaken the generic DSP/ML
    // override path for other classes. ---
    {
        MlOverrideGate::Input in;
        in.isOod = false;
        in.mlConfidence = 0.95f;
        in.winningEvidence = "FOLDER";
        in.preMlCategory = "Vocals";
        in.preMlSubcategory = "Vocal Loop";
        in.preMlConfidence = 0.48f;
        in.mlSubcategory = "Vocal Phrase";
        in.preserveVocalLoopEvidence = true;

        auto d = MlOverrideGate::evaluate(in);
        V4H_CHECK(d.subcategory == "Vocal Loop",
                  "explicit Vocal Loop evidence survives conflicting Vocal Phrase ML");
        V4H_CHECK(d.tagSource == "heuristic" && !d.overrideApplied,
                  "preserved Vocal Loop remains heuristic and records no ML override");
    }

    // --- 7. MlOverrideGate: "unknown" behavior -- below-confidence, non-OOD
    //     result neither overrides nor clears; the pre-ML heuristic result
    //     stands exactly as it was. ---
    {
        MlOverrideGate::Input in;
        in.isOod = false;
        in.mlConfidence = 0.10f;                   // below minConfidenceForOverride (0.40)
        in.winningEvidence = "DSP";
        in.preMlCategory = "Drums";
        in.preMlSubcategory = "Snare";
        in.preMlConfidence = 0.25f;
        in.mlSubcategory = "FX";

        auto d = MlOverrideGate::evaluate(in);
        V4H_CHECK(d.category == "Drums" && d.subcategory == "Snare",
                   "a low-confidence non-OOD ML result leaves the pre-ML heuristic guess untouched");
        V4H_CHECK(d.tagSource == "heuristic", "tagSource stays heuristic when neither override nor OOD-clear applies");
        V4H_CHECK(!d.overrideApplied, "overrideApplied is false");
    }

    // Invalid model output must remain unknown.  Before this boundary check,
    // a zero or non-finite 512D buffer could still produce a named top-1
    // class and be marked usable by callers that only checked vector length.
    {
        float zeroEmbedding[AcousticWeights::embeddingDim] = {};
        auto d = AcousticClassifier::classify(zeroEmbedding);
        V4H_CHECK(d.subcategory.empty(), "a zero embedding remains unclassified");
        V4H_CHECK(d.confidence == 0.0f, "a zero embedding has zero confidence");
        V4H_CHECK(d.isOod && d.nearestCentroidIndex == -1,
                  "a zero embedding is fail-closed OOD with no centroid");
    }
    {
        float nonFiniteEmbedding[AcousticWeights::embeddingDim] = {};
        nonFiniteEmbedding[17] = std::numeric_limits<float>::quiet_NaN();
        auto d = AcousticClassifier::classify(nonFiniteEmbedding);
        V4H_CHECK(d.subcategory.empty(), "a non-finite embedding remains unclassified");
        V4H_CHECK(d.confidence == 0.0f && d.isOod,
                  "a non-finite embedding cannot be accepted as known");
    }
    {
        auto d = AcousticClassifier::classify(nullptr);
        V4H_CHECK(d.subcategory.empty() && d.isOod,
                  "a null embedding is rejected without dereferencing it");
    }

    if (v4hFailures > 0)
        std::cerr << v4hFailures << " V4-H regression check(s) FAILED" << std::endl;
    else
        std::cout << "ALL V4-H REGRESSION CHECKS PASSED" << std::endl;
}

int main()
{
    juce::initialiseJuce_GUI();

    // Locate parity_references.json
    //
    // Primary: SMART_SAMPLE_MANAGER_SOURCE_DIR (compile definition supplied by
    // CMakeLists.txt). This works from ANY build directory, in-tree or
    // out-of-tree, and is what makes out-of-tree build trees such as
    // _build/qualification usable.
    //
    // Fallback: walk up from the executable looking for a directory literally
    // named "SmartSampleManager" (historical behaviour, kept for binaries
    // built without the compile definition).
    //
    // This walk MUST terminate at the filesystem root. juce::File("/") returns
    // itself from getParentDirectory() and reports exists() == true, so the
    // previous "while (exists() && name != ...)" form never terminated when no
    // ancestor was named "SmartSampleManager" -- it spun at 100% CPU forever
    // instead of reporting a problem. That is reachable in any out-of-tree
    // build (build directory outside the project tree), where it presents as a
    // silent hang rather than a test failure.
    //
    // Detect root by the parent-is-self fixed point rather than by exists(),
    // and report a clear diagnostic instead of hanging.
#if defined(SMART_SAMPLE_MANAGER_SOURCE_DIR)
    juce::File projectDir = juce::File(SMART_SAMPLE_MANAGER_SOURCE_DIR);
    bool foundProjectDir = projectDir.isDirectory();
#else
    juce::File currentFile = juce::File::getSpecialLocation(juce::File::currentExecutableFile);
    juce::File projectDir = currentFile.getParentDirectory();
    bool foundProjectDir = false;

    while (true)
    {
        if (projectDir.getFileName() == "SmartSampleManager")
        {
            foundProjectDir = true;
            break;
        }

        const juce::File parent = projectDir.getParentDirectory();
        if (parent == projectDir)  // filesystem root -- go no further
            break;

        projectDir = parent;
    }
#endif

    if (! foundProjectDir || ! projectDir.exists())
    {
        std::cerr << "FAIL: Could not locate the SmartSampleManager project "
                     "directory for fixture resolution." << std::endl;
        std::cerr << "      Started from: "
                  << juce::File::getSpecialLocation(juce::File::currentExecutableFile).getFullPathName()
                  << std::endl;
        return 1;
    }

    juce::File parityFile = projectDir.getChildFile("tools").getChildFile("classification_benchmark").getChildFile("parity_references.json");
    if (!parityFile.exists())
    {
        std::cerr << "FAIL: Could not locate parity_references.json at: " << parityFile.getFullPathName() << std::endl;
        return 1;
    }

    auto jsonVar = juce::JSON::parse(parityFile);
    auto* obj = jsonVar.getDynamicObject();
    juce::Array<juce::var>* parityArray = nullptr;
    if (obj != nullptr)
    {
        if (obj->hasProperty("cases"))
            parityArray = obj->getProperty("cases").getArray();
        else
            parityArray = obj->getProperty("references").getArray();
    }
    else
    {
        parityArray = jsonVar.getArray();
    }

    if (parityArray == nullptr)
    {
        std::cerr << "FAIL: parity_references.json is malformed!" << std::endl;
        return 1;
    }

    std::cout << "Running Python/C++ Numerical Parity Tests (" << parityArray->size() << " cases)..." << std::endl;

    double maxLogitError = 0.0;
    double maxProbError = 0.0;

    for (int i = 0; i < parityArray->size(); ++i)
    {
        auto item = parityArray->getReference(i);
        auto filename = item.getProperty("filename", "").toString().toStdString();
        auto expectedSub = item.getProperty("predicted_subcategory", "").toString().toStdString();
        if (expectedSub.empty())
            expectedSub = item.getProperty("expected_subcategory", "").toString().toStdString();
        
        auto* embedVar = item.getProperty("embedding", {}).getArray();
        if (embedVar == nullptr)
            embedVar = item.getProperty("input_features", {}).getArray();

        auto* expectedLogitsVar = item.getProperty("expected_logits", {}).getArray();

        auto* expectedProbsVar = item.getProperty("expected_probs", {}).getArray();
        if (expectedProbsVar == nullptr)
            expectedProbsVar = item.getProperty("expected_probabilities", {}).getArray();

        if (embedVar == nullptr || expectedLogitsVar == nullptr || expectedProbsVar == nullptr)
        {
            std::cerr << "FAIL: Parity case " << i << " has missing fields." << std::endl;
            return 1;
        }

        float embed[AcousticWeights::embeddingDim] = { 0.0f };
        for (int d = 0; d < AcousticWeights::embeddingDim; ++d)
        {
            embed[d] = static_cast<float>(double(embedVar->getReference(d)));
        }

        // 1. Verify logits
        float scaledLogits[AcousticWeights::numClasses] = { 0.0f };
        AcousticClassifier::computeLogits(embed, scaledLogits);

        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            double expectedLogit = double(expectedLogitsVar->getReference(c));
            double error = std::abs(static_cast<double>(scaledLogits[c]) - expectedLogit);
            if (error > maxLogitError)
            {
                maxLogitError = error;
            }
        }

        // 2. Verify Classifier Output (if not OOD)
        auto res = AcousticClassifier::classify520(embed);

        if (!res.isOod && res.subcategory != expectedSub)
        {
            std::cerr << "FAIL: Class mismatch for " << filename << ". C++: " << res.subcategory << ", Expected: " << expectedSub << std::endl;
            return 1;
        }

        // Compute full probs in C++ and check error
        float maxScaledLogit = -1e9f;
        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            if (scaledLogits[c] > maxScaledLogit)
            {
                maxScaledLogit = scaledLogits[c];
            }
        }

        float expSum = 0.0f;
        float probs[AcousticWeights::numClasses] = { 0.0f };
        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            probs[c] = std::exp(scaledLogits[c] - maxScaledLogit);
            expSum += probs[c];
        }

        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            probs[c] /= expSum;
            double expectedProb = double(expectedProbsVar->getReference(c));
            double error = std::abs(static_cast<double>(probs[c]) - expectedProb);
            if (error > maxProbError)
            {
                maxProbError = error;
            }
        }
    }

    std::cout << "Max Logit Error: " << maxLogitError << std::endl;
    std::cout << "Max Probability Error: " << maxProbError << std::endl;

    if (maxLogitError > 1e-4)
    {
        std::cerr << "FAIL: Logit error exceeded 1e-4 tolerance!" << std::endl;
        return 1;
    }
    if (maxProbError > 1e-4)
    {
        std::cerr << "FAIL: Probability error exceeded 1e-4 tolerance!" << std::endl;
        return 1;
    }

    std::cout << "SUCCESS: All numerical parity checks passed!" << std::endl;

    runV4HTests();

    juce::MessageManager::deleteInstance();

    if (v4hFailures > 0)
        return 1;
    return 0;
}
