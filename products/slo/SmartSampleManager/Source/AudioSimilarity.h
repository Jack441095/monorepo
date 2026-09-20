#pragma once

#include "AudioEvidence.h"

#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <map>
#include <string>
#include <vector>

namespace SloAudioSimilarity {

// Product-facing aspect weights inspired by similarity browsers. All weights
// are non-negative; zero disables an aspect. This type is retrieval-only and
// deliberately contains no taxonomy or rename action.
struct AspectWeights {
    float embedding = 1.0f;
    float spectrum = 1.0f;
    float timbre = 1.0f;
    float pitch = 1.0f;
    float amplitude = 1.0f;
    // Sound DNA physical dimensions
    float material = 1.0f;  // Q factor / high-frequency dissipation
    float impact = 1.0f;    // Hertzian contact duration tau_c
    float stiffness = 1.0f; // Inharmonicity B & modal dispersion
};

struct AspectScores {
    float overall = 0.0f;
    float embedding = 0.0f;
    float spectrum = 0.5f;
    float timbre = 0.5f;
    float pitch = 0.5f;
    float amplitude = 0.5f;
    // Sound DNA physical scores
    float material = 0.5f;
    float impact = 0.5f;
    float stiffness = 0.5f;
};

inline float clamp01(float value)
{
    return std::max(0.0f, std::min(1.0f, value));
}

inline float cosineSimilarity(const std::vector<float>& a, const std::vector<float>& b)
{
    if (a.empty() || a.size() != b.size()) return 0.0f;
    double dot = 0.0, aa = 0.0, bb = 0.0;
    for (size_t i = 0; i < a.size(); ++i) {
        dot += static_cast<double>(a[i]) * b[i];
        aa += static_cast<double>(a[i]) * a[i];
        bb += static_cast<double>(b[i]) * b[i];
    }
    if (aa <= 1e-12 || bb <= 1e-12) return 0.0f;
    return clamp01(static_cast<float>((dot / std::sqrt(aa * bb) + 1.0) * 0.5));
}

inline float measurementSimilarity(const SloAudioEvidence::Record& a,
                                    const SloAudioEvidence::Record& b,
                                    std::initializer_list<std::pair<const char*, float>> fields)
{
    float total = 0.0f;
    int count = 0;
    for (const auto& [name, range] : fields) {
        const auto ia = a.measurements.find(name);
        const auto ib = b.measurements.find(name);
        if (ia == a.measurements.end() || ib == b.measurements.end()
            || !ia->second.valid || !ib->second.valid || range <= 0.0f)
            continue;
        total += clamp01(1.0f - static_cast<float>(std::abs(ia->second.value - ib->second.value) / range));
        ++count;
    }
    return count == 0 ? 0.5f : total / static_cast<float>(count);
}

inline AspectScores score(const SloAudioEvidence::Record& query,
                          const SloAudioEvidence::Record& candidate,
                          const std::vector<float>& queryEmbedding = {},
                          const std::vector<float>& candidateEmbedding = {},
                          const AspectWeights& weights = {})
{
    AspectScores result;
    result.embedding = cosineSimilarity(queryEmbedding, candidateEmbedding);
    result.spectrum = measurementSimilarity(query, candidate,
        {{"spectral_centroid", 8000.0f}, {"spectral_rolloff", 12000.0f},
         {"zero_crossing_rate", 1.0f}});
    result.timbre = measurementSimilarity(query, candidate,
        {{"spectral_centroid", 8000.0f}, {"zero_crossing_rate", 1.0f},
         {"stereo_correlation", 2.0f}, {"crest_factor", 9.0f}});
    // Pitch is neutral when neither record has an explicit pitch measurement;
    // this is safer than inventing a mismatch from missing data.
    result.pitch = measurementSimilarity(query, candidate,
        {{"fundamental_hz", 2000.0f}, {"pitch_drop_cents", 6000.0f},
         {"pitch_slope", 50.0f}, {"bpm", 240.0f}});
    result.amplitude = measurementSimilarity(query, candidate,
        {{"duration", 60.0f}, {"decay_time", 10.0f}, {"crest_factor", 9.0f},
         {"rms_amplitude", 1.0f}});

    // Sound DNA physical similarity:
    // 1. Material (Q factor in log10 space)
    const auto qA = query.measurements.find("quality_factor_q");
    const auto qB = candidate.measurements.find("quality_factor_q");
    if (qA != query.measurements.end() && qB != candidate.measurements.end()
        && qA->second.valid && qB->second.valid && qA->second.value > 0.0 && qB->second.value > 0.0)
    {
        float logDiff = static_cast<float>(std::abs(std::log10(qA->second.value + 1.0) - std::log10(qB->second.value + 1.0)));
        result.material = clamp01(1.0f - logDiff / 2.5f);
    }
    else
    {
        result.material = 0.5f;
    }

    // 2. Impact (Hertzian contact duration tau_c in log10 space)
    const auto tA = query.measurements.find("contact_duration_ms");
    const auto tB = candidate.measurements.find("contact_duration_ms");
    if (tA != query.measurements.end() && tB != candidate.measurements.end()
        && tA->second.valid && tB->second.valid && tA->second.value > 0.0 && tB->second.value > 0.0)
    {
        float logDiff = static_cast<float>(std::abs(std::log10(tA->second.value + 0.1) - std::log10(tB->second.value + 0.1)));
        result.impact = clamp01(1.0f - logDiff / 2.0f);
    }
    else
    {
        result.impact = 0.5f;
    }

    // 3. Stiffness (inharmonicity B and modal dispersion)
    result.stiffness = measurementSimilarity(query, candidate,
        {{"inharmonicity_b", 0.02f}, {"membrane_fit", 1.0f},
         {"plate_bar_fit", 1.0f}, {"harmonic_fit", 1.0f}});

    const float total = std::max(0.0f, weights.embedding)
                      + std::max(0.0f, weights.spectrum)
                      + std::max(0.0f, weights.timbre)
                      + std::max(0.0f, weights.pitch)
                      + std::max(0.0f, weights.amplitude)
                      + std::max(0.0f, weights.material)
                      + std::max(0.0f, weights.impact)
                      + std::max(0.0f, weights.stiffness);
    if (total > 0.0f) {
        result.overall = (
            std::max(0.0f, weights.embedding) * result.embedding
            + std::max(0.0f, weights.spectrum) * result.spectrum
            + std::max(0.0f, weights.timbre) * result.timbre
            + std::max(0.0f, weights.pitch) * result.pitch
            + std::max(0.0f, weights.amplitude) * result.amplitude
            + std::max(0.0f, weights.material) * result.material
            + std::max(0.0f, weights.impact) * result.impact
            + std::max(0.0f, weights.stiffness) * result.stiffness) / total;
    }
    return result;
}

} // namespace SloAudioSimilarity

