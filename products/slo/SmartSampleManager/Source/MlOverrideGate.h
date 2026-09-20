#pragma once

#include <atomic>
#include <string>
#include "AbletonTaxonomy.h"

// V4-H: the V4-D/V4-G ML-override-vs-OOD decision (previously inline in
// SampleManagerEngine.cpp's prepareFile(), lines ~3181-3224) extracted into
// a small, pure, directly-unit-testable function. Behavior is unchanged --
// this is a refactor for testability (spec §20/§27: "Preserve the V4-G bug
// fix... with a dedicated regression test"), not a redesign. No ONNX/JUCE
// dependency, so it can be exercised by a lightweight test binary without
// pulling in the full engine or embedding pipeline.
//
// See docs/SLO_CLASSIFICATION_V4H_FINAL_CALIBRATION_REPORT.md for the
// full rationale.
namespace MlOverrideGate
{
    // Minimum ML softmax confidence required for an ML override to be
    // applied at all, even when the sample is not OOD. Unchanged from
    // V4-D/V4-G (SampleManagerEngine.cpp's prior inline `>= 0.40f` check).
    static constexpr float minConfidenceForOverride = 0.40f;

    // P2-1 FUSION V2 promotion gates (wiring only — values mirror the corpus
    // gates the owner must pass before V2 ships; they do NOT change runtime
    // behaviour while g_fusionV2Enabled is false):
    //   * adversarial accuracy (filename-lies cases) >= 0.40
    //   * fused cross-vendor accuracy >= 0.65
    // QC-01 (2026-09-18): named here so the gate is auditable and the
    // benchmark receipt can assert against kPromotion* constants instead of
    // magic numbers scattered across scripts._FILENAME evidence weight cap:
    // symbolic evidence alone must never outrank a confident non-OOD acoustic
    // verdict on loop-length audio — enforced by the duration rule below, not
    // by a numeric weight, so there is no hidden linear-weight to drift.
    static constexpr float kFusionV2AdversarialPromotionFloor = 0.40f;
    static constexpr float kFusionV2FusedPromotionFloor = 0.65f;
    inline std::atomic<bool> g_fusionV2Enabled{false};
    inline void setFusionV2Enabled(bool on) noexcept
    {
        g_fusionV2Enabled.store(on, std::memory_order_relaxed);
    }
    inline bool fusionV2Enabled() noexcept
    {
        return g_fusionV2Enabled.load(std::memory_order_relaxed);
    }
    // Loop-length evidence: a one-shot label on a file this long disagrees
    // with the audio's own duration. Only the long->loop direction ships in
    // the spike; short->one-shot is intentionally out (risers and short
    // loops exist, so that direction needs its own calibration).
    static constexpr double kFusionV2LoopDurationSeconds = 4.0;

    struct Input
    {
        bool isOod = false;
        float mlConfidence = 0.0f;
        std::string winningEvidence;      // pre-ML evidence tier: "EMBEDDED_METADATA" / "FILENAME" / "FOLDER" / "DSP" / ""
        std::string preMlCategory;        // heuristic taxonomy category before the ML gate ran (may be empty)
        std::string preMlSubcategory;
        float preMlConfidence = 0.0f;
        std::string mlSubcategory;        // AcousticClassifier::Result::subcategory (raw acoustic class name)
        // Domain-specific filename evidence can be stronger than a generic
        // acoustic Vocal Phrase prediction for the fine-grained Vocal Loop
        // decision.  This is intentionally explicit and narrow; callers must
        // only set it after the taxonomy evidence detector has confirmed it.
        bool preserveVocalLoopEvidence = false;
        // True audio duration in seconds (0.0 = unknown: the V2 duration
        // rule requires an explicit long duration, so unknown never fires).
        double durationSeconds = 0.0;
    };

    struct Decision
    {
        std::string category;
        std::string subcategory;
        float tagConfidence = 0.0f;
        std::string tagSource;            // "heuristic" (unchanged) / "ml_v3" (override applied) / "ml_ood" (cleared)
        std::string winningEvidence;
        bool overrideApplied = false;
        bool fusionV2Applied = false;     // true iff the V2 duration rule (not V1) decided
    };

    // Mirrors SampleManagerEngine.cpp's prepareFile() ML-gate branch exactly:
    //   if (!isOod && confidence >= 0.40) {
    //       if (evidence in {DSP, FOLDER} || category.empty()) -> apply ML override (tagSource="ml_v3")
    //   } else if (isOod) {
    //       if (evidence in {DSP, UNKNOWN} || category.empty()) -> clear category/subcategory (tagSource="ml_ood",
    //                                                     winningEvidence="UNKNOWN") -- the V4-G fix:
    //                                                     an OOD result must not retain a stale label.
    //   }
    //   (any other combination: the pre-ML heuristic result stands untouched --
    //    this is how strong FILENAME/EMBEDDED_METADATA evidence, and FOLDER
    //    evidence under an OOD flag, are preserved per the evidence hierarchy.)
    inline Decision evaluate(const Input& in)
    {
        Decision d;
        d.category = in.preMlCategory;
        d.subcategory = in.preMlSubcategory;
        d.tagConfidence = in.preMlConfidence;
        d.tagSource = "heuristic";
        d.winningEvidence = in.winningEvidence;

        if (!in.isOod && in.mlConfidence >= minConfidenceForOverride)
        {
            if (!in.preserveVocalLoopEvidence
                && (in.winningEvidence == "DSP" || in.winningEvidence == "FOLDER" || in.preMlCategory.empty()))
            {
                std::string mlCat, mlSub;
                if (AbletonTaxonomy::mapAcousticClassToTaxonomy(in.mlSubcategory, mlCat, mlSub))
                {
                    d.category = mlCat;
                    d.subcategory = mlSub;
                    d.tagConfidence = in.mlConfidence;
                    d.tagSource = "ml_v3";
                    d.overrideApplied = true;
                }
            }
            // P2-1 FUSION V2 (flagged, default OFF): filename evidence naming
            // a one-shot on loop-length audio loses to a confident ML loop
            // verdict. Narrow by construction: non-OOD only, ML confident,
            // V1 did not already override, evidence is symbolic (FILENAME),
            // pre-ML label is a one-shot, ML maps to a loop, duration is
            // known-long. Everything else falls through untouched.
            if (!d.overrideApplied && fusionV2Enabled()
                && !in.preserveVocalLoopEvidence
                && in.winningEvidence == "FILENAME"
                && in.durationSeconds >= kFusionV2LoopDurationSeconds)
            {
                const bool preMlIsLoop = in.preMlSubcategory.find("Loop") != std::string::npos
                    || in.preMlSubcategory.find("loop") != std::string::npos;
                std::string mlCat, mlSub;
                if (!preMlIsLoop
                    && AbletonTaxonomy::mapAcousticClassToTaxonomy(in.mlSubcategory, mlCat, mlSub)
                    && (mlSub.find("Loop") != std::string::npos
                        || mlSub.find("loop") != std::string::npos))
                {
                    d.category = mlCat;
                    d.subcategory = mlSub;
                    d.tagConfidence = in.mlConfidence;
                    d.tagSource = "ml_v3";
                    d.overrideApplied = true;
                    d.fusionV2Applied = true;
                }
            }
        }
        else if (in.isOod)
        {
            // UNKNOWN means no trusted symbolic evidence survived hydration;
            // an OOD result must not let a freshly rebuilt heuristic category
            // turn that explicit abstention back into a known label.
            if (in.winningEvidence == "DSP"
                || in.winningEvidence == "UNKNOWN"
                || in.preMlCategory.empty())
            {
                // V4-G FIX (spec §14 / "UNKNOWN must remain honest"): clear the
                // untrustworthy stale guess instead of leaving it displayed next
                // to an internal "this is OOD" flag nothing else reads.
                d.category.clear();
                d.subcategory.clear();
                d.tagConfidence = 0.0f;
                d.winningEvidence = "UNKNOWN";
                d.tagSource = "ml_ood";
            }
        }

        return d;
    }
}
