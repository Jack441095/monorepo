#pragma once

#include "BassTimbreCentroids.h"
#include <string>
#include <cmath>
#include <limits>

// SLO Master Plan: Fine-Grained Subcategorization V1, Phase 9.
//
// Additive, independent nearest-centroid lookup over the raw 512D PANNs
// embedding -- same architectural pattern as AcousticClassifier's OOD gate
// (nearest-centroid cosine similarity), but a completely separate model:
// does not read or write anything AcousticClassifier/MlOverrideGate touch,
// and does not participate in the frozen production linear head or its
// per-class OOD thresholds. Only ever consulted for samples whose top-level
// subcategory is already "Bass One-Shot" or "Bass Loop" -- see
// SampleManagerEngine.cpp's call site.
//
// Holdout accuracy (leakage-free, 42 real samples never used to compute the
// centroids): 92.9% (39/42). See BassTimbreCentroids.h and
// docs/classification/BASS_TIMBRE_TAG_V1_REPORT.md for the full method and
// caveats (24-sample Reese class is thin; margin does not cleanly separate
// correct from wrong predictions at this sample size, so this exposes a
// confidence score rather than a binary "is it confident enough" gate --
// callers decide how to present that, same posture as tagConfidence
// elsewhere in this engine).
class BassTimbreClassifier
{
public:
    struct Result
    {
        std::string label;       // "808" or "Reese"
        float confidence = 0.0f; // top1 cosine similarity, 0..1 range in practice
        float margin = 0.0f;     // top1 - top2 similarity; diagnostic only, not a hard gate (see class comment)
    };

    static Result classify(const float* embedding512D)
    {
        Result r;
        if (embedding512D == nullptr) return r;

        float bestSim = -2.0f, secondSim = -2.0f;
        int bestIdx = -1;

        // Keep the validation and accumulation numerically aligned with the
        // main AcousticClassifier boundary.  This classifier is additive, but
        // it must not turn a corrupt or overflow-scale embedding into a
        // plausible 808/Reese label when called independently.
        double embNormSq = 0.0;
        for (int d = 0; d < BassTimbreCentroids::embeddingDim; ++d)
        {
            const double value = static_cast<double>(embedding512D[d]);
            if (!std::isfinite(value)) return r;
            embNormSq += value * value;
        }
        if (!std::isfinite(embNormSq)
            || embNormSq <= 1.0e-12
            || embNormSq > static_cast<double>(std::numeric_limits<float>::max()))
            return r;
        const double embNorm = std::sqrt(embNormSq);

        for (int c = 0; c < BassTimbreCentroids::numClasses; ++c)
        {
            const float* centroid = BassTimbreCentroids::centroids[c];
            double dot = 0.0, centroidNormSq = 0.0;
            for (int d = 0; d < BassTimbreCentroids::embeddingDim; ++d)
            {
                const double centroidValue = static_cast<double>(centroid[d]);
                dot += static_cast<double>(embedding512D[d]) * centroidValue;
                centroidNormSq += centroidValue * centroidValue;
            }
            const double centroidNorm = std::sqrt(centroidNormSq);
            const double sim = (centroidNorm > 1e-9 && std::isfinite(centroidNorm))
                ? (dot / (embNorm * centroidNorm)) : -2.0;

            if (std::isfinite(sim) && sim > bestSim)
            {
                secondSim = static_cast<float>(bestSim);
                bestSim = static_cast<float>(sim);
                bestIdx = c;
            }
            else if (std::isfinite(sim) && sim > secondSim)
            {
                secondSim = static_cast<float>(sim);
            }
        }

        if (bestIdx >= 0)
        {
            r.label = BassTimbreCentroids::classNames[bestIdx];
            r.confidence = bestSim;
            r.margin = bestSim - secondSim;
        }
        return r;
    }
};
