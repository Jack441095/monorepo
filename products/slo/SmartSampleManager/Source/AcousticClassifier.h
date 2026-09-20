#pragma once

#include "AcousticClassifierWeights.h"
#include "AcousticClassifierCentroids.h"
#include <string>
#include <cmath>
#include <algorithm>
#include <limits>

class AcousticClassifier
{
public:
    // The classifier input is a 520-D concatenation, but only the first 512
    // dims (the PANNs embedding) are produced by ONNX, persisted in the
    // cache, and used by the similarity/HNSW index. The trailing 8 are
    // normalised DSP features derived from AudioAnalysisResult and are
    // rebuilt on demand at classification time.
    //
    // Keeping these separate matters: appending the 8 dims onto the
    // persisted embedding vector makes the cache blob 520 floats, which the
    // 512-float read guard rejects, and makes hasSafeEmbeddingBuffer()
    // reject every cache-hydrated row. Persist 512, classify on 520.
    static constexpr int pannsDim = 512;
    static constexpr int dspFeatureDim = 8;
    static_assert(pannsDim + dspFeatureDim == AcousticWeights::embeddingDim,
                  "classifier input must be the PANNs embedding plus the DSP feature block");

    struct Result
    {
        std::string subcategory;
        float confidence = 0.0f;
        float margin = 0.0f;
        bool isOod = false;
        // V4-G OOD DIAGNOSTICS: predictive entropy (nats) of the softmax
        // distribution, and the raw 512D embedding L2 norm -- both computed
        // for free alongside the existing forward pass, exposed purely for
        // offline OOD-method evaluation (see docs/SLO_CLASSIFICATION_V4G_OOD_REPORT.md).
        // Neither field is read by any gating decision in this struct's
        // caller unless SampleManagerEngine.cpp is explicitly changed to do so.
        float entropy = 0.0f;
        // Research-only logit energy: -logsumexp of the scaled ArcFace
        // logits.  It is recorded for offline OOD comparison and is not part
        // of the production gate until independently calibrated.
        float logitEnergy = 0.0f;
        float embeddingNorm = 0.0f;
        // V4-G BLOCKER-A FIX: best (max) cosine similarity of this sample's
        // raw 512D embedding to any known-class centroid (AcousticOodCentroids).
        // `isOod` below is now driven by this score, not by softmax margin --
        // see class-level comment for why.
        float centroidCosineSimilarity = 0.0f;
        // V4-H: which of the 16 centroids produced centroidCosineSimilarity
        // (index into AcousticOodCentroids::classNames / perClassOodThreshold).
        // Exposed for diagnostics; drives the per-class OOD threshold lookup
        // below.
        int nearestCentroidIndex = -1;
    };

    // The ONNX boundary normally supplies exactly 512 floats, but shape alone
    // does not prove that the result is usable. A failed/unstable model can
    // return NaN/Inf, and a zero vector has no meaningful direction for either
    // the linear head or the centroid OOD gate. Treat both as invalid so an
    // unusable result can never become a named class, enter the cache, or be
    // added to the similarity index. The upper bound keeps the squared norm
    // representable for the existing float-based similarity/index consumers;
    // it is an arithmetic-safety bound, not a model-calibration threshold.
    static bool isValidEmbedding(const float* embedding512D)
    {
        if (embedding512D == nullptr) return false;

        // Bound is pannsDim, not embeddingDim: every caller passes the
        // persisted 512-float PANNs vector. Looping to embeddingDim (520)
        // would read 8 floats past the end of that buffer.
        double normSq = 0.0;
        for (int d = 0; d < pannsDim; ++d)
        {
            const float value = embedding512D[d];
            if (!std::isfinite(value)) return false;
            normSq += static_cast<double>(value) * static_cast<double>(value);
        }

        return std::isfinite(normSq)
            && normSq > 1.0e-12
            && normSq <= static_cast<double>(std::numeric_limits<float>::max());
    }

    static inline float gelu(float x)
    {
        return 0.5f * x * (1.0f + std::erf(x * 0.7071067811865475f));
    }

    static inline void layerNorm(float* x, const float* w, const float* b, int dim, float eps = 1e-5f)
    {
        float sum = 0.0f;
        for (int i = 0; i < dim; ++i) sum += x[i];
        float mean = sum / static_cast<float>(dim);

        float varSum = 0.0f;
        for (int i = 0; i < dim; ++i)
        {
            float diff = x[i] - mean;
            varSum += diff * diff;
        }
        float var = varSum / static_cast<float>(dim);
        float invStd = 1.0f / std::sqrt(var + eps);

        for (int i = 0; i < dim; ++i)
        {
            x[i] = (x[i] - mean) * invStd * w[i] + b[i];
        }
    }

    static void computeLogits(const float* embedding520D, float* outScaledLogits)
    {
        constexpr int inDim = AcousticWeights::embeddingDim;
        constexpr int dim = AcousticWeights::hiddenDim;

        // 1. fc1 + ln1 + gelu: h = gelu(layerNorm(fc1(x)))
        float h[dim];
        for (int i = 0; i < dim; ++i)
        {
            float sum = AcousticWeights::fc1_biases[i];
            for (int j = 0; j < inDim; ++j)
            {
                sum += AcousticWeights::fc1_weights[i][j] * embedding520D[j];
            }
            h[i] = sum;
        }
        layerNorm(h, AcousticWeights::ln1_gamma, AcousticWeights::ln1_beta, dim);
        for (int i = 0; i < dim; ++i) h[i] = gelu(h[i]);

        // Helper macro for GatedResBlock: residual + fc2(gelu(ln2(fc1(gelu(ln1(input))))))
        auto runGatedBlock = [&](const float* input, float* output,
                                 const float fc1_w[512][512], const float fc1_b[512],
                                 const float ln1_g[512], const float ln1_b[512],
                                 const float fc2_w[512][512], const float fc2_b[512],
                                 const float ln2_g[512], const float ln2_b[512])
        {
            float stage1[dim];
            for (int i = 0; i < dim; ++i)
            {
                float sum = fc1_b[i];
                for (int j = 0; j < dim; ++j) sum += fc1_w[i][j] * input[j];
                stage1[i] = sum;
            }
            layerNorm(stage1, ln1_g, ln1_b, dim);
            for (int i = 0; i < dim; ++i) stage1[i] = gelu(stage1[i]);

            float stage2[dim];
            for (int i = 0; i < dim; ++i)
            {
                float sum = fc2_b[i];
                for (int j = 0; j < dim; ++j) sum += fc2_w[i][j] * stage1[j];
                stage2[i] = sum;
            }
            layerNorm(stage2, ln2_g, ln2_b, dim);
            for (int i = 0; i < dim; ++i) stage2[i] = gelu(stage2[i]);

            for (int i = 0; i < dim; ++i) output[i] = input[i] + stage2[i];
        };

        // 2. Block 1
        float b1[dim];
        runGatedBlock(h, b1,
                      AcousticWeights::block1_fc1_weights, AcousticWeights::block1_fc1_biases,
                      AcousticWeights::block1_ln1_gamma, AcousticWeights::block1_ln1_beta,
                      AcousticWeights::block1_fc2_weights, AcousticWeights::block1_fc2_biases,
                      AcousticWeights::block1_ln2_gamma, AcousticWeights::block1_ln2_beta);

        // 3. Block 2
        float b2[dim];
        runGatedBlock(b1, b2,
                      AcousticWeights::block2_fc1_weights, AcousticWeights::block2_fc1_biases,
                      AcousticWeights::block2_ln1_gamma, AcousticWeights::block2_ln1_beta,
                      AcousticWeights::block2_fc2_weights, AcousticWeights::block2_fc2_biases,
                      AcousticWeights::block2_ln2_gamma, AcousticWeights::block2_ln2_beta);

        // 4. Block 3
        float b3[dim];
        runGatedBlock(b2, b3,
                      AcousticWeights::block3_fc1_weights, AcousticWeights::block3_fc1_biases,
                      AcousticWeights::block3_ln1_gamma, AcousticWeights::block3_ln1_beta,
                      AcousticWeights::block3_fc2_weights, AcousticWeights::block3_fc2_biases,
                      AcousticWeights::block3_ln2_gamma, AcousticWeights::block3_ln2_beta);

        // 5. Arc Face Cosine Head: normalize h (b3), normalize arc_head_weights, dot product * scaleFactor
        float hNormSq = 0.0f;
        for (int i = 0; i < dim; ++i) hNormSq += b3[i] * b3[i];
        float hNorm = std::sqrt(std::max(hNormSq, 1e-12f));

        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            float wNormSq = 0.0f;
            float dot = 0.0f;
            for (int j = 0; j < dim; ++j)
            {
                float w = AcousticWeights::arc_head_weights[c][j];
                wNormSq += w * w;
                dot += w * b3[j];
            }
            float wNorm = std::sqrt(std::max(wNormSq, 1e-12f));
            float cosSim = dot / (hNorm * wNorm);
            outScaledLogits[c] = cosSim * AcousticWeights::scaleFactor;
        }
    }

    // Classify a fully assembled 520-D production input (512-D PANNs
    // embedding followed by the 8 normalized DSP features).  Keeping this
    // entry point explicit prevents callers from accidentally passing a
    // persisted 512-D cache vector into the 520-D linear head.
    static Result classify520(const float* embedding520D)
    {
        bool validInput = isValidEmbedding(embedding520D);
        if (validInput)
        {
            for (int d = pannsDim; d < AcousticWeights::embeddingDim; ++d)
            {
                if (!std::isfinite(embedding520D[d]))
                {
                    validInput = false;
                    break;
                }
            }
        }
        if (!validInput)
        {
            Result invalid;
            invalid.subcategory.clear();
            invalid.confidence = 0.0f;
            invalid.margin = 0.0f;
            invalid.isOod = true;
            invalid.entropy = 0.0f;
            invalid.logitEnergy = 0.0f;
            invalid.embeddingNorm = 0.0f;
            invalid.centroidCosineSimilarity = -1.0f;
            invalid.nearestCentroidIndex = -1;
            return invalid;
        }

        float scaledLogits[AcousticWeights::numClasses] = { 0.0f };
        computeLogits(embedding520D, scaledLogits);

        // Find max scaled logit for numerical stability
        float maxScaledLogit = -1e9f;
        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            if (scaledLogits[c] > maxScaledLogit)
            {
                maxScaledLogit = scaledLogits[c];
            }
        }

        // Softmax
        float expSum = 0.0f;
        float probs[AcousticWeights::numClasses] = { 0.0f };
        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            probs[c] = std::exp(scaledLogits[c] - maxScaledLogit);
            expSum += probs[c];
        }

        if (expSum > 0.0f)
        {
            for (int c = 0; c < AcousticWeights::numClasses; ++c)
            {
                probs[c] /= expSum;
            }
        }

        // Find top-1 and top-2
        int top1Idx = 0;
        float top1Val = -1.0f;
        float top2Val = -1.0f;

        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            if (probs[c] > top1Val)
            {
                top2Val = top1Val;
                top1Val = probs[c];
                top1Idx = c;
            }
            else if (probs[c] > top2Val)
            {
                top2Val = probs[c];
            }
        }

        Result r;
        r.subcategory = AcousticWeights::classNames[top1Idx];
        r.confidence = top1Val;
        r.margin = (top2Val >= 0.0f) ? (top1Val - top2Val) : top1Val;
        // `expSum` was accumulated after subtracting maxScaledLogit, so this
        // reconstruction is stable even when the head produces large logits.
        r.logitEnergy = -(maxScaledLogit + std::log(std::max(expSum, 1.0e-30f)));

        // Predictive entropy of the softmax distribution (nats)
        float ent = 0.0f;
        for (int c = 0; c < AcousticWeights::numClasses; ++c)
        {
            if (probs[c] > 1e-9f) ent -= probs[c] * std::log(probs[c]);
        }
        r.entropy = ent;

        double normSq = 0.0;
        for (int d = 0; d < AcousticWeights::embeddingDim; ++d)
        {
            const double value = static_cast<double>(embedding520D[d]);
            normSq += value * value;
        }
        const double embNorm = std::sqrt(normSq);
        r.embeddingNorm = static_cast<float>(embNorm);

        // Nearest-centroid cosine similarity in RAW 512D PANNs embedding space
        float bestCos = -1.0f;
        int bestClassIdx = -1;
        if (embNorm > 1e-9)
        {
            for (int c = 0; c < AcousticOodCentroids::numClasses; ++c)
            {
                const float* centroid = AcousticOodCentroids::centroids[c];
                float dot = 0.0f, centroidNormSq = 0.0f;
                for (int d = 0; d < AcousticOodCentroids::embeddingDim; ++d)
                {
                    dot += embedding520D[d] * centroid[d];
                    centroidNormSq += centroid[d] * centroid[d];
                }
                float centroidNorm = std::sqrt(centroidNormSq);
                if (centroidNorm > 1e-9f)
                {
                    float cos = dot / (embNorm * centroidNorm);
                    if (cos > bestCos) { bestCos = cos; bestClassIdx = c; }
                }
            }
        }
        r.centroidCosineSimilarity = bestCos;
        r.nearestCentroidIndex = bestClassIdx;

        float effectiveThreshold = AcousticOodCentroids::oodCosineSimilarityThreshold;
        if (bestClassIdx >= 0 && bestClassIdx < AcousticOodCentroids::numClasses)
        {
            effectiveThreshold = AcousticOodCentroids::perClassOodThreshold[bestClassIdx];
        }
        r.isOod = (bestCos < effectiveThreshold);

        return r;
    }

    // Classify a persisted 512-D PANNs embedding with a zero DSP feature
    // block. This is the safe compatibility path for cache/retrieval callers;
    // production inference should use classify520() with real DSP features.
    static Result classify512(const float* embedding512D)
    {
        if (!isValidEmbedding(embedding512D))
            return classify520(embedding512D);

        float input[AcousticWeights::embeddingDim] = {};
        std::copy(embedding512D, embedding512D + pannsDim, input);
        return classify520(input);
    }

    // Legacy name retained for source compatibility. It now has an explicit
    // 512-D contract rather than reading past the caller's buffer.
    static Result classify(const float* embedding512D)
    {
        return classify512(embedding512D);
    }
};
