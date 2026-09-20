#pragma once

#include "HiHatTypeCentroids.h"
#include <string>
#include <cmath>
#include <limits>

// SLO Master Plan: Fine-Grained Subcategorization V1, Phase 11.
//
// Additive, independent nearest-centroid lookup over the raw 512D PANNs
// embedding -- same architectural pattern as BassTimbreClassifier and
// AcousticClassifier's OOD gate. Completely separate model: does not read
// or write anything AcousticClassifier/MlOverrideGate touch, does not
// participate in the frozen production linear head or its per-class OOD
// thresholds. Only ever consulted for samples whose top-level subcategory
// is already "Hi-Hat" -- see SampleManagerEngine.cpp's call site.
//
// Holdout accuracy (leakage-free, 52 real samples never used to compute the
// centroids): 92.3% (48/52). See HiHatTypeCentroids.h and
// docs/classification/HIHAT_TYPE_TAG_V1_REPORT.md for the full method and
// caveats.
class HiHatTypeClassifier
{
public:
    struct Result
    {
        std::string label;       // "Open" or "Closed"
        float confidence = 0.0f;
        float margin = 0.0f;
    };

    static Result classify(const float* embedding512D)
    {
        Result r;
        if (embedding512D == nullptr) return r;

        float bestSim = -2.0f, secondSim = -2.0f;
        int bestIdx = -1;

        // Match the main classifier's fail-closed numeric boundary so a
        // direct fine-grained-tag call cannot manufacture a label from
        // corrupt, zero, or overflow-scale model output.
        double embNormSq = 0.0;
        for (int d = 0; d < HiHatTypeCentroids::embeddingDim; ++d)
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

        for (int c = 0; c < HiHatTypeCentroids::numClasses; ++c)
        {
            const float* centroid = HiHatTypeCentroids::centroids[c];
            double dot = 0.0, centroidNormSq = 0.0;
            for (int d = 0; d < HiHatTypeCentroids::embeddingDim; ++d)
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
            r.label = HiHatTypeCentroids::classNames[bestIdx];
            r.confidence = bestSim;
            r.margin = bestSim - secondSim;
        }
        return r;
    }
};
