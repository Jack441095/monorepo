#include <iostream>
#include <cassert>
#include <cmath>
#include "PhysicalAcoustics.h"
#include "PhysicalSynthesizer.h"

void expectTrue(bool condition, const std::string& message)
{
    if (!condition)
    {
        std::cerr << "FAIL: " << message << std::endl;
        std::exit(1);
    }
}

int main()
{
    std::cout << "Starting Physical Acoustics tests..." << std::endl;

    // 1. Test Harmonic Resonator Template Matching (Strings, Pianos, Organs, Voice)
    {
        std::vector<PhysicalAcoustics::SpectralPeak> harmonicPeaks = {
            { 100.0f, 1.0f },
            { 200.0f, 0.8f },
            { 300.0f, 0.6f },
            { 400.0f, 0.4f },
            { 500.0f, 0.3f }
        };

        auto analysis = PhysicalAcoustics::analyze(harmonicPeaks, 100.0f, 0.0f, 0.02f, 2.0f, 2.0f, 0.60f);
        expectTrue(analysis.harmonicFit > 0.90f, "Harmonic fit should be > 0.90 for integer partials");
        expectTrue(analysis.resonator == PhysicalAcoustics::ResonatorType::HarmonicStringPipe,
                   "Resonator should be HarmonicStringPipe");
        expectTrue(analysis.pitchGlide == PhysicalAcoustics::PitchGlideType::StableFlat,
                   "Pitch glide should be StableFlat");
        expectTrue(analysis.physicalClass == "Bass Loop",
                   "100Hz sustained harmonic resonator should classify physically as Bass Loop");
        std::cout << "  ✓ Harmonic Resonator test passed (fit: " << analysis.harmonicFit << ")" << std::endl;
    }

    // 2. Test Circular Membrane Template Matching (Drum Heads, Kicks, Toms)
    {
        std::vector<PhysicalAcoustics::SpectralPeak> membranePeaks = {
            { 60.0f, 1.0f },
            { 60.0f * 1.594f, 0.7f },
            { 60.0f * 2.136f, 0.5f },
            { 60.0f * 2.296f, 0.4f },
            { 60.0f * 2.653f, 0.3f }
        };

        auto analysis = PhysicalAcoustics::analyze(membranePeaks, 60.0f, -10.0f, 0.03f, 4.0f, 0.4f, 0.05f);
        expectTrue(analysis.membraneFit > 0.85f, "Membrane fit should be > 0.85 for Bessel modes");
        expectTrue(analysis.resonator == PhysicalAcoustics::ResonatorType::CircularMembrane,
                   "Resonator should be CircularMembrane");
        expectTrue(analysis.pitchGlide == PhysicalAcoustics::PitchGlideType::DownwardDive,
                   "Pitch glide should be DownwardDive");
        expectTrue(analysis.physicalClass == "Kick",
                   "60Hz impulsive membrane with downward pitch dive should classify physically as Kick");
        std::cout << "  ✓ Circular Membrane (Kick) test passed (fit: " << analysis.membraneFit << ")" << std::endl;
    }

    // 3. Test Metallic Plate / Bar Template Matching (Cymbals, Bells, Metallic Hits)
    {
        std::vector<PhysicalAcoustics::SpectralPeak> platePeaks = {
            { 500.0f, 1.0f },
            { 500.0f * 2.756f, 0.8f },
            { 500.0f * 5.404f, 0.6f },
            { 500.0f * 8.933f, 0.4f }
        };

        auto analysis = PhysicalAcoustics::analyze(platePeaks, 500.0f, 0.0f, 0.35f, 2.5f, 2.5f, 0.20f);
        expectTrue(analysis.plateBarFit > 0.85f, "Plate fit should be > 0.85 for bar/plate modes");
        expectTrue(analysis.resonator == PhysicalAcoustics::ResonatorType::MetallicPlateBar,
                   "Resonator should be MetallicPlateBar");
        expectTrue(analysis.physicalClass == "Crash / Cymbal",
                   "Long-decay metallic plate resonator should classify physically as Crash / Cymbal");
        std::cout << "  ✓ Metallic Plate / Cymbal test passed (fit: " << analysis.plateBarFit << ")" << std::endl;
    }

    // 4. Test Inharmonic Stiff-String Dispersion (Piano / Slap Bass)
    {
        const float f0 = 110.0f; // A2
        const float B = 0.0015f;
        std::vector<PhysicalAcoustics::SpectralPeak> pianoPeaks;
        for (int n = 1; n <= 6; ++n)
        {
            float fn = n * f0 * std::sqrt(1.0f + B * n * n);
            pianoPeaks.push_back({ fn, 1.0f / n });
        }

        auto analysis = PhysicalAcoustics::analyze(pianoPeaks, f0, 0.0f, 0.04f, 3.5f, 0.7f, 0.05f);
        expectTrue(analysis.inharmonicityB > 0.0005f, "Estimated B should be > 0.0005 for stiff string");
        expectTrue(analysis.physicalClass == "Piano / Plucked String",
                   "Impulsive stiff-string resonator should classify physically as Piano / Plucked String");
        std::cout << "  ✓ Stiff String (Piano/Pluck) test passed (B: " << analysis.inharmonicityB << ")" << std::endl;
    }

    // 5. Test Riser / Pitch Sweep Dynamics
    {
        std::vector<PhysicalAcoustics::SpectralPeak> sweepPeaks = {
            { 440.0f, 1.0f },
            { 880.0f, 0.5f }
        };

        auto analysis = PhysicalAcoustics::analyze(sweepPeaks, 440.0f, +12.0f, 0.05f, 1.5f, 3.0f, 0.70f);
        expectTrue(analysis.pitchGlide == PhysicalAcoustics::PitchGlideType::UpwardSweep,
                   "Pitch glide should be UpwardSweep for +12 semitones/s");
        expectTrue(analysis.physicalClass == "Riser / Sweep" || analysis.physicalClass == "Sustained Tonal / Lead / Pad",
                   "Upward pitch sweep should classify appropriately");
        std::cout << "  ✓ Pitch Sweep Dynamics test passed" << std::endl;
    }

    // 6. Test analyzeFromAudioBuffer on Synthetic 1D Harmonic Audio Buffer
    {
        const double sampleRate = 44100.0;
        const int numSamples = 44100; // 1 second
        std::vector<float> buffer(numSamples, 0.0f);
        const float f0 = 220.0f;

        for (int i = 0; i < numSamples; ++i)
        {
            float t = static_cast<float>(i) / static_cast<float>(sampleRate);
            buffer[i] = 0.5f * std::sin(2.0f * 3.14159265f * f0 * t)
                      + 0.3f * std::sin(2.0f * 3.14159265f * 2.0f * f0 * t)
                      + 0.2f * std::sin(2.0f * 3.14159265f * 3.0f * f0 * t);
        }

        auto analysis = PhysicalAcoustics::analyzeFromAudioBuffer(
            buffer.data(), numSamples, sampleRate, 0.02f, 1.4f, 1.0f, 0.90f);

        expectTrue(analysis.harmonicFit > 0.80f, "Buffer harmonic fit should be > 0.80");
        expectTrue(analysis.resonator == PhysicalAcoustics::ResonatorType::HarmonicStringPipe,
                   "Buffer resonator should be HarmonicStringPipe");
        std::cout << "  ✓ Synthetic Harmonic Buffer test passed (f0: " << analysis.f0Hz << " Hz, fit: " << analysis.harmonicFit << ")" << std::endl;
    }

    // 7. Test analyzeFromAudioBuffer on Synthetic 2D Membrane Drum Hit Buffer
    {
        const double sampleRate = 44100.0;
        const int numSamples = 22050; // 0.5 seconds
        std::vector<float> buffer(numSamples, 0.0f);
        const float f0 = 60.0f;

        for (int i = 0; i < numSamples; ++i)
        {
            float t = static_cast<float>(i) / static_cast<float>(sampleRate);
            float env = std::exp(-t * 12.0f); // Fast decay
            // Instantaneous frequency drops: phase phi(t) = 2*pi*(f0*t + 0.5*alpha*t^2)
            float freqGlide = f0 + (120.0f - f0) * std::exp(-t * 30.0f);
            buffer[i] = env * (0.7f * std::sin(2.0f * 3.14159265f * freqGlide * t)
                             + 0.3f * std::sin(2.0f * 3.14159265f * f0 * 1.594f * t));
        }

        auto analysis = PhysicalAcoustics::analyzeFromAudioBuffer(
            buffer.data(), numSamples, sampleRate, 0.02f, 4.5f, 0.25f, 0.01f);

        expectTrue(analysis.membraneFit > 0.50f || analysis.pitchSlopeSemitonesPerSec < -5.0f,
                   "Membrane drum should exhibit membrane modal fit or downward pitch trajectory");
        std::cout << "  ✓ Synthetic Membrane Drum Buffer test passed (pitch slope: " << analysis.pitchSlopeSemitonesPerSec << " st/s)" << std::endl;
    }

    // 8. Test analyzeFromAudioBuffer on Stochastic Noise (Hi-Hat)
    {
        const double sampleRate = 44100.0;
        const int numSamples = 8820; // 0.2 seconds
        std::vector<float> buffer(numSamples, 0.0f);

        // Simple high-passed white noise
        float prev = 0.0f;
        for (int i = 0; i < numSamples; ++i)
        {
            float t = static_cast<float>(i) / static_cast<float>(sampleRate);
            float env = std::exp(-t * 25.0f);
            float white = (static_cast<float>(std::rand()) / static_cast<float>(RAND_MAX)) * 2.0f - 1.0f;
            float hp = white - prev;
            prev = white;
            buffer[i] = env * hp * 0.5f;
        }

        auto analysis = PhysicalAcoustics::analyzeFromAudioBuffer(
            buffer.data(), numSamples, sampleRate, 0.35f, 3.8f, 0.15f, 0.01f);

        expectTrue(analysis.resonator == PhysicalAcoustics::ResonatorType::NoiseAtonal,
                   "Noise buffer should be NoiseAtonal");
        expectTrue(analysis.physicalClass == "Hi-Hat",
                   "Short impulsive high-ZCR noise should be Hi-Hat");
        std::cout << "  ✓ Synthetic Stochastic Noise (Hi-Hat) test passed (class: " << analysis.physicalClass << ")" << std::endl;
    }

    // 9. Test evaluateMixCollision for Low-End Masking and Phase Detection
    {
        const double sampleRate = 44100.0;
        const int numSamples = 44100;
        std::vector<float> kick(numSamples, 0.0f);
        std::vector<float> bassClashing(numSamples, 0.0f);
        std::vector<float> hihatClean(numSamples, 0.0f);

        for (int i = 0; i < numSamples; ++i)
        {
            float t = static_cast<float>(i) / static_cast<float>(sampleRate);
            kick[i] = std::sin(2.0f * 3.14159265f * 60.0f * t) * std::exp(-t * 8.0f);
            bassClashing[i] = -0.8f * std::sin(2.0f * 3.14159265f * 60.0f * t); // Inverted phase sub bass
            hihatClean[i] = ((static_cast<float>(std::rand()) / RAND_MAX) * 2.0f - 1.0f) * std::exp(-t * 20.0f);
        }

        auto collisionDiag = PhysicalAcoustics::evaluateMixCollision(
            kick.data(), bassClashing.data(), numSamples, sampleRate);
        expectTrue(collisionDiag.lowEndMaskingDetected, "Low-end masking should be detected between kick and sub-bass");
        expectTrue(collisionDiag.phaseCorrelation < 0.0f, "Phase correlation should be negative for inverted sub");

        auto cleanDiag = PhysicalAcoustics::evaluateMixCollision(
            kick.data(), hihatClean.data(), numSamples, sampleRate);
        expectTrue(!cleanDiag.lowEndMaskingDetected, "Kick and hi-hat should not trigger low-end masking");

        std::cout << "  ✓ Mix Collision & Masking Diagnostic test passed" << std::endl;
    }

    // 10. Test Material Loss Matrix (Metal vs Wood)
    {
        std::vector<PhysicalAcoustics::SpectralPeak> metalPeaks = {
            { 500.0f, 1.0f },
            { 1378.0f, 0.7f },
            { 2702.0f, 0.5f }
        };
        // Metal plate: long ring (tau = 2.5s) -> Q = pi * 500 * 2.5 = 3927
        auto metalAnalysis = PhysicalAcoustics::analyze(metalPeaks, 500.0f, 0.0f, 0.18f, 3.5f, 2.5f, 0.05f);
        expectTrue(metalAnalysis.material == PhysicalAcoustics::PhysicalMaterial::Metal,
                   "Long ringing plate should be classified as Metal");
        expectTrue(metalAnalysis.qualityFactorQ > 1500.0f,
                   "Metal Q factor should exceed 1500");

        std::vector<PhysicalAcoustics::SpectralPeak> woodPeaks = {
            { 400.0f, 1.0f },
            { 800.0f, 0.4f }
        };
        // Wooden block: fast internal damping (tau = 0.08s) -> Q = pi * 400 * 0.08 = 100
        auto woodAnalysis = PhysicalAcoustics::analyze(woodPeaks, 400.0f, 0.0f, 0.05f, 4.0f, 0.08f, 0.001f);
        expectTrue(woodAnalysis.material == PhysicalAcoustics::PhysicalMaterial::Wood,
                   "Short decaying tonal hit should be classified as Wood");
        expectTrue(woodAnalysis.qualityFactorQ < 450.0f,
                   "Wood Q factor should be under 450");
        std::cout << "  ✓ Material Loss Matrix test passed (Metal Q=" << metalAnalysis.qualityFactorQ << ", Wood Q=" << woodAnalysis.qualityFactorQ << ")" << std::endl;
    }

    // 11. Test Hertzian Contact Time & Mallet Hardness
    {
        const double sampleRate = 44100.0;
        const int numSamples = 4410; // 100ms
        std::vector<float> softStrike(numSamples, 0.0f);
        std::vector<float> hardStrike(numSamples, 0.0f);

        // Soft felt strike: slow rise ~12ms (530 samples)
        for (int i = 0; i < 530; ++i)
        {
            float t = static_cast<float>(i) / 530.0f;
            softStrike[i] = t * std::sin(2.0f * 3.14159265f * 100.0f * (static_cast<float>(i) / 44100.0f));
        }

        // Hard metal strike: fast impulse rise ~0.5ms (22 samples)
        for (int i = 0; i < 22; ++i)
        {
            float t = static_cast<float>(i) / 22.0f;
            hardStrike[i] = t * std::sin(2.0f * 3.14159265f * 1000.0f * (static_cast<float>(i) / 44100.0f));
        }

        float softContactMs = PhysicalAcoustics::estimateContactDurationMs(softStrike.data(), numSamples, sampleRate);
        float hardContactMs = PhysicalAcoustics::estimateContactDurationMs(hardStrike.data(), numSamples, sampleRate);

        expectTrue(softContactMs > 6.0f, "Soft strike contact time should be > 6ms");
        expectTrue(hardContactMs < 2.0f, "Hard strike contact time should be < 2ms");
        std::cout << "  ✓ Hertzian Mallet Contact test passed (Soft=" << softContactMs << "ms, Hard=" << hardContactMs << "ms)" << std::endl;
    }

    // 12. Test Bore Geometry (Odd Harmonics Closed Cylinder vs Conical/Open)
    {
        // Odd harmonic series: f0, 3*f0, 5*f0, 7*f0 (Clarinet / Closed pipe)
        std::vector<PhysicalAcoustics::SpectralPeak> oddPeaks = {
            { 220.0f, 1.0f },
            { 660.0f, 0.8f },
            { 1100.0f, 0.6f },
            { 1540.0f, 0.4f }
        };
        auto oddAnalysis = PhysicalAcoustics::analyze(oddPeaks, 220.0f, 0.0f, 0.02f, 1.5f, 2.0f, 0.8f);
        expectTrue(oddAnalysis.bore == PhysicalAcoustics::BoreGeometry::CylindricalClosed,
                   "Odd-harmonic acoustic spectrum should be CylindricalClosed bore");
        expectTrue(oddAnalysis.oddEvenHarmonicRatio > 2.0f,
                   "Odd/even harmonic ratio should be > 2.0");

        // Full harmonic series: f0, 2*f0, 3*f0, 4*f0 (Sax / Flute / Open pipe / Saw)
        std::vector<PhysicalAcoustics::SpectralPeak> fullPeaks = {
            { 220.0f, 1.0f },
            { 440.0f, 0.8f },
            { 660.0f, 0.6f },
            { 880.0f, 0.5f }
        };
        auto fullAnalysis = PhysicalAcoustics::analyze(fullPeaks, 220.0f, 0.0f, 0.02f, 1.5f, 2.0f, 0.8f);
        expectTrue(fullAnalysis.bore == PhysicalAcoustics::BoreGeometry::ConicalOrOpen,
                   "Full-harmonic acoustic spectrum should be ConicalOrOpen bore");
        std::cout << "  ✓ Bore Geometry test passed (Odd/Even=" << oddAnalysis.oddEvenHarmonicRatio << " vs " << fullAnalysis.oddEvenHarmonicRatio << ")" << std::endl;
    }

    // 13. Physical Resynthesis & Sound Morphing Engine
    {
        PhysicalAcoustics::Analysis mockAnalysis;
        mockAnalysis.resonator = PhysicalAcoustics::ResonatorType::CircularMembrane;
        mockAnalysis.f0Hz = 65.4f; // C2
        mockAnalysis.pitchSlopeSemitonesPerSec = -15.0f; // Kick dive
        mockAnalysis.contactDurationMs = 4.0f;
        mockAnalysis.material = PhysicalAcoustics::PhysicalMaterial::SkinMylar;
        mockAnalysis.qualityFactorQ = 250.0f;

        auto syn = PhysicalSynthesizer::PhysicalResynthesizer::fromAnalysis(mockAnalysis, 44100.0f, 0.5f);
        expectTrue(syn.getPartials().size() > 0, "Partials should be populated");
        expectTrue(std::abs(syn.getF0Hz() - 65.4f) < 0.1f, "f0 should match analysis");

        std::vector<float> audio;
        syn.render(audio);
        expectTrue(audio.size() == 22050, "Render buffer size should match 0.5s at 44.1kHz");

        float maxVal = 0.0f;
        for (float s : audio)
        {
            expectTrue(std::isfinite(s), "Audio samples must be finite");
            maxVal = std::max(maxVal, std::abs(s));
        }
        expectTrue(maxVal > 0.5f, "Rendered audio should be normalized and active");

        // Test Material Morphing
        syn.morphMaterial(1.0f); // Pure metal
        expectTrue(syn.getQ() > 2000.0f, "Metal Q factor should be > 2000");

        // Test Mallet Hardness Modulation
        syn.adjustMalletHardness(0.5f); // Dirac metal beater
        expectTrue(std::abs(syn.getContactDurationMs() - 0.5f) < 1e-4f, "Contact duration should be 0.5ms");

        // Test Membrane Tension Retune (+12 semitones / 1 octave)
        syn.retuneMembraneTension(12.0f);
        expectTrue(std::abs(syn.getF0Hz() - 130.8f) < 0.5f, "f0 should double after +12 semitones");

        // Test Inharmonic Stiffness Injection
        syn.setInharmonicStiffness(0.002f);
        expectTrue(syn.getInharmonicityB() > 0.0015f, "Stiffness B should be injected");

        std::cout << "  ✓ Physical Resynthesis & Morphing test passed (Modes=" << syn.getPartials().size() << ", Retuned f0=" << syn.getF0Hz() << " Hz)" << std::endl;
    }

    std::cout << "ALL PHYSICAL ACOUSTICS TESTS PASSED SUCCESSFULLY!" << std::endl;
    return 0;
}


