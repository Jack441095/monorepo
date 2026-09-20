#include "AudioSimilarity.h"

#include <cmath>
#include <iostream>

namespace {
void check(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << "FAIL: " << message << "\n";
        std::exit(1);
    }
}
}

int main()
{
    SloAudioEvidence::Record a;
    a.contentId = "a"; a.sourcePath = "/a.wav";
    a.measurements["spectral_centroid"] = {1000.0, "Hz", "test", true};
    a.measurements["duration"] = {1.0, "seconds", "test", true};
    a.measurements["crest_factor"] = {4.0, "ratio", "test", true};

    auto b = a;
    b.contentId = "b"; b.sourcePath = "/b.wav";
    b.measurements["spectral_centroid"].value = 1100.0;
    const std::vector<float> ea{1.0f, 0.0f}, eb{0.9f, 0.1f};
    const auto s = SloAudioSimilarity::score(a, b, ea, eb);
    check(s.embedding > 0.9f, "embedding similarity should be high");
    check(s.spectrum > 0.9f, "nearby spectrum should score highly");
    check(s.overall > 0.5f && s.overall <= 1.0f, "overall score should be bounded");

    SloAudioSimilarity::AspectWeights weights;
    weights.embedding = 0.0f;
    weights.spectrum = 1.0f;
    weights.timbre = weights.pitch = weights.amplitude = 0.0f;
    weights.material = weights.impact = weights.stiffness = 0.0f;
    const auto spectrumOnly = SloAudioSimilarity::score(a, b, ea, eb, weights);
    check(std::abs(spectrumOnly.overall - spectrumOnly.spectrum) < 1e-5f,
          "single aspect weight should define overall score");

    SloAudioEvidence::Record missing;
    missing.contentId = "missing"; missing.sourcePath = "/missing.wav";
    const auto neutral = SloAudioSimilarity::score(a, missing);
    check(std::abs(neutral.pitch - 0.5f) < 1e-5f,
          "missing pitch measurements must remain neutral");
    check(std::abs(neutral.material - 0.5f) < 1e-5f,
          "missing material measurements must remain neutral");
    check(std::abs(neutral.impact - 0.5f) < 1e-5f,
          "missing impact measurements must remain neutral");

    // Test Physical Sound DNA Matching (Material Q and Hertzian contact duration)
    SloAudioEvidence::Record woodSound, metalSound;
    woodSound.contentId = "wood"; woodSound.sourcePath = "/wood.wav";
    woodSound.measurements["quality_factor_q"] = {35.0, "Q", "test", true};
    woodSound.measurements["contact_duration_ms"] = {18.0, "ms", "test", true};
    woodSound.measurements["inharmonicity_b"] = {0.0005, "dispersion", "test", true};

    metalSound.contentId = "metal"; metalSound.sourcePath = "/metal.wav";
    metalSound.measurements["quality_factor_q"] = {850.0, "Q", "test", true};
    metalSound.measurements["contact_duration_ms"] = {0.8, "ms", "test", true};
    metalSound.measurements["inharmonicity_b"] = {0.015, "dispersion", "test", true};

    auto woodCopy = woodSound;
    woodCopy.measurements["quality_factor_q"].value = 40.0;    // very close Q
    woodCopy.measurements["contact_duration_ms"].value = 16.5; // very close impact

    const auto woodToWood = SloAudioSimilarity::score(woodSound, woodCopy);
    check(woodToWood.material > 0.9f, "wood-to-wood material similarity should be high");
    check(woodToWood.impact > 0.9f, "wood-to-wood impact similarity should be high");

    const auto woodToMetal = SloAudioSimilarity::score(woodSound, metalSound);
    check(woodToMetal.material < 0.6f, "wood-to-metal material similarity should be significantly lower");
    check(woodToMetal.impact < 0.6f, "wood-to-metal impact similarity should be significantly lower");

    // Test Material-only weighting
    SloAudioSimilarity::AspectWeights matWeights;
    matWeights.embedding = matWeights.spectrum = matWeights.timbre = 0.0f;
    matWeights.pitch = matWeights.amplitude = matWeights.impact = matWeights.stiffness = 0.0f;
    matWeights.material = 1.0f;
    const auto matOnly = SloAudioSimilarity::score(woodSound, woodCopy, {}, {}, matWeights);
    check(std::abs(matOnly.overall - matOnly.material) < 1e-5f, "material-only weight should define overall score");

    std::cout << "AudioSimilarity tests passed\n";
    return 0;
}

