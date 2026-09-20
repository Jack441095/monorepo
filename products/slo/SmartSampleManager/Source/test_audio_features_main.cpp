#include <iostream>
#include <cmath>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

namespace {

struct ScopedQuickWinDirectory
{
    juce::File root = juce::File::getSpecialLocation(juce::File::tempDirectory)
                          .getChildFile("SLOAudioFeatures_" + juce::Uuid().toString());
    juce::File dir = root.getChildFile("fixtures");

    ScopedQuickWinDirectory() { dir.createDirectory(); }
    ~ScopedQuickWinDirectory() { root.deleteRecursively(); }

    ScopedQuickWinDirectory(const ScopedQuickWinDirectory&) = delete;
    ScopedQuickWinDirectory& operator=(const ScopedQuickWinDirectory&) = delete;
};

} // namespace

int main() {
    constexpr float kPi = 3.14159265358979323846f;
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    auto fixtureDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    auto kickFixture = fixtureDir.getChildFile("test_kick.wav");

    SampleManagerEngine engine;
    std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        return 1;
    }

    engine.addPathToQueue(kickFixture.getFullPathName().toStdString());
    int waitLimit = 100;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    auto samples = engine.getSamples();
    if (samples.empty()) {
        std::cerr << "FAIL: no samples loaded" << std::endl;
        return 1;
    }

    const auto& sample = samples.front();
    const auto& features = sample.audioFeatures;

    std::cout << "Peak: " << features.peakAmplitude << "\n"
              << "RMS: " << features.rmsAmplitude << "\n"
              << "Centroid: " << features.spectralCentroid << "\n"
              << "Rolloff: " << features.spectralRolloff << "\n"
              << "ZCR: " << features.zeroCrossingRate << "\n"
              << "Crest Factor: " << features.crestFactor << "\n"
              << "Onsets: " << features.onsetCount << "\n"
              << "Original Sample Rate: " << features.originalSampleRate << "\n"
              << "Original Channels: " << features.originalChannels << "\n"
              << "Original Bit Depth: " << features.originalBitDepth << std::endl;

    // Feature Sanity Asserts
    if (features.peakAmplitude <= 0.0f || features.peakAmplitude > 1.0f) {
        std::cerr << "FAIL: invalid peak amplitude: " << features.peakAmplitude << std::endl;
        return 1;
    }

    if (features.rmsAmplitude <= 0.0f || features.rmsAmplitude > features.peakAmplitude) {
        std::cerr << "FAIL: invalid RMS amplitude: " << features.rmsAmplitude << std::endl;
        return 1;
    }

    if (features.spectralCentroid <= 0.0f || features.spectralCentroid > 16000.0f) {
        std::cerr << "FAIL: invalid spectral centroid: " << features.spectralCentroid << std::endl;
        return 1;
    }

    if (features.spectralRolloff <= 0.0f || features.spectralRolloff > 16000.0f) {
        std::cerr << "FAIL: invalid spectral rolloff: " << features.spectralRolloff << std::endl;
        return 1;
    }

    if (features.zeroCrossingRate < 0.0f || features.zeroCrossingRate > 1.0f) {
        std::cerr << "FAIL: invalid zero crossing rate: " << features.zeroCrossingRate << std::endl;
        return 1;
    }

    if (features.crestFactor < 1.0f) {
        std::cerr << "FAIL: crest factor must be >= 1.0: " << features.crestFactor << std::endl;
        return 1;
    }

    if (features.originalSampleRate <= 0) {
        std::cerr << "FAIL: invalid original sample rate" << std::endl;
        return 1;
    }

    if (features.originalChannels <= 0) {
        std::cerr << "FAIL: invalid original channels" << std::endl;
        return 1;
    }

    if (sample.featureVersion != kFeatureAnalysisVersion) {
        std::cerr << "FAIL: featureVersion mismatch" << std::endl;
        return 1;
    }

    // --- QUICK WINS VALIDATION ---
    std::cout << "Starting Quick-Wins Validation Tests..." << std::endl;
    
    // Use a fresh disposable directory on every run. The former fixed
    // source-tree scratch path retained fixtures after an early failure, so
    // the first directory scan could race with later fixture rewrites and
    // intermittently observe a half-written loop with BPM 0.
    ScopedQuickWinDirectory quickWinDirectory;
    juce::File tempDir = quickWinDirectory.dir;
    
    auto writeTestWav = [](const juce::File& file, double sampleRate, int numSamples, bool isNoise, float freq = 100.0f) {
        file.deleteFile();
        juce::WavAudioFormat format;
        std::unique_ptr<juce::AudioFormatWriter> writer(format.createWriterFor(
            new juce::FileOutputStream(file), sampleRate, 1, 16, {}, 0));
        
        if (writer != nullptr) {
            juce::AudioBuffer<float> buffer(1, numSamples);
            auto* writePointer = buffer.getWritePointer(0);
            
            // Fixed seed keeps the atonal fixture reproducible; time-seeded
            // noise made the tempo-abstention assertion intermittently pass
            // or fail across otherwise identical qualification runs.
            juce::Random rand(0x534c4f);
            for (int i = 0; i < numSamples; ++i) {
                if (isNoise) {
                    writePointer[i] = rand.nextFloat() * 2.0f - 1.0f;
                } else {
                    writePointer[i] = std::sin(2.0f * 3.14159265f * freq * i / static_cast<float>(sampleRate));
                }
            }
            
            writer->writeFromAudioSampleBuffer(buffer, 0, numSamples);
        }
    };

    auto writeChordWav = [](const juce::File& file, double sampleRate,
                            int numSamples, std::initializer_list<float> frequencies) {
        file.deleteFile();
        juce::WavAudioFormat format;
        std::unique_ptr<juce::AudioFormatWriter> writer(format.createWriterFor(
            new juce::FileOutputStream(file), sampleRate, 1, 16, {}, 0));
        if (writer == nullptr) return;
        juce::AudioBuffer<float> buffer(1, numSamples);
        buffer.clear();
        auto* dst = buffer.getWritePointer(0);
        for (int i = 0; i < numSamples; ++i) {
            const float t = static_cast<float>(i / sampleRate);
            float value = 0.0f;
            for (float frequency : frequencies)
                value += std::sin(2.0f * 3.14159265f * frequency * t);
            dst[i] = 0.22f * value / static_cast<float>(frequencies.size());
        }
        writer->writeFromAudioSampleBuffer(buffer, 0, numSamples);
    };

    auto writeClickLoopWav = [](const juce::File& file, double sampleRate,
                                float durationSeconds, float bpm) {
        file.deleteFile();
        juce::WavAudioFormat format;
        const int numSamples = static_cast<int>(std::ceil(sampleRate * durationSeconds));
        std::unique_ptr<juce::AudioFormatWriter> writer(format.createWriterFor(
            new juce::FileOutputStream(file), sampleRate, 1, 16, {}, 0));
        if (writer == nullptr) return;
        juce::AudioBuffer<float> buffer(1, numSamples);
        buffer.clear();
        auto* dst = buffer.getWritePointer(0);
        const int beatSamples = static_cast<int>(std::llround(sampleRate * 60.0 / bpm));
        const int clickLength = static_cast<int>(std::ceil(sampleRate * 0.01));
        for (int onset = 0; onset < numSamples; onset += beatSamples)
            for (int i = 0; i < clickLength && onset + i < numSamples; ++i)
                dst[onset + i] = std::exp(-static_cast<float>(i) / 40.0f);
        writer->writeFromAudioSampleBuffer(buffer, 0, numSamples);
    };

    // 1. Filename classification boundary matching tests
    juce::File fKick01 = tempDir.getChildFile("kick_01.wav");
    juce::File fKickstart = tempDir.getChildFile("kickstart.wav");
    juce::File fHiHat = tempDir.getChildFile("hi-hat.wav");
    juce::File fHatchet = tempDir.getChildFile("hatchet.wav");
    juce::File fBassoon = tempDir.getChildFile("bassoon.wav");
    
    juce::File fVocal01 = tempDir.getChildFile("vox_adlib_01.wav");
    juce::File fAcapella = tempDir.getChildFile("acapella_lead.wav");
    
    // Generate sine waves for all of them so we test filename heuristics only
    writeTestWav(fKick01, 44100.0, 44100, false);
    writeTestWav(fKickstart, 44100.0, 44100, false);
    writeTestWav(fHiHat, 44100.0, 44100, false);
    writeTestWav(fHatchet, 44100.0, 44100, false);
    writeTestWav(fBassoon, 44100.0, 44100, false);
    writeTestWav(fVocal01, 44100.0, 44100, false);
    writeTestWav(fAcapella, 44100.0, 44100, false);
    
    SampleManagerEngine qwEngine;
    if (!qwEngine.init(modelPath)) {
        std::cerr << "FAIL: QW engine init failed" << std::endl;
        return 1;
    }
    
    qwEngine.addPathToQueue(tempDir.getFullPathName().toStdString());
    waitLimit = 150;
    while (qwEngine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);
        
    auto qwSamples = qwEngine.getSamples();
    std::cout << "Processed " << qwSamples.size() << " test samples for quick-wins." << std::endl;
    
    bool foundKick01 = false;
    bool foundKickstart = false;
    bool foundHiHat = false;
    bool foundHatchet = false;
    bool foundBassoon = false;
    bool foundVocal01 = false;
    bool foundAcapella = false;
    
    for (const auto& s : qwSamples) {
        juce::File f(s.filePath);
        std::string filename = f.getFileName().toStdString();
        
        if (filename == "kick_01.wav") {
            foundKick01 = true;
            if (s.instrumentType != "Kick") {
                std::cerr << "FAIL: kick_01.wav classified as " << s.instrumentType << " (expected Kick)" << std::endl;
                return 1;
            }
            if (s.winningEvidence != "FILENAME") {
                std::cerr << "FAIL: kick_01.wav winningEvidence is " << s.winningEvidence << " (expected FILENAME)" << std::endl;
                return 1;
            }
        } else if (filename == "kickstart.wav") {
            foundKickstart = true;
            if (s.winningEvidence == "FILENAME" || s.winningEvidence == "FOLDER") {
                std::cerr << "FAIL: kickstart.wav matched via filename/folder heuristics (should NOT match due to token boundary)" << std::endl;
                return 1;
            }
        } else if (filename == "hi-hat.wav") {
            foundHiHat = true;
            if (s.instrumentType != "Hi-Hat" || s.subcategory != "Hi-Hat") {
                std::cerr << "FAIL: hi-hat.wav category mismatch: " << s.instrumentType << "/" << s.subcategory << " (expected Hi-Hat/Hi-Hat)" << std::endl;
                return 1;
            }
            if (s.winningEvidence != "FILENAME") {
                std::cerr << "FAIL: hi-hat.wav winningEvidence is " << s.winningEvidence << " (expected FILENAME)" << std::endl;
                return 1;
            }
        } else if (filename == "hatchet.wav") {
            foundHatchet = true;
            if (s.winningEvidence == "FILENAME" || s.winningEvidence == "FOLDER") {
                std::cerr << "FAIL: hatchet.wav matched via filename/folder heuristics (should NOT match)" << std::endl;
                return 1;
            }
        } else if (filename == "bassoon.wav") {
            foundBassoon = true;
            if (s.winningEvidence == "FILENAME" || s.winningEvidence == "FOLDER") {
                std::cerr << "FAIL: bassoon.wav matched via filename/folder heuristics (should NOT match)" << std::endl;
                return 1;
            }
        } else if (filename == "vox_adlib_01.wav") {
            foundVocal01 = true;
            if (s.instrumentType != "Vocal" || s.category != "Vocals") {
                std::cerr << "FAIL: vox_adlib_01.wav classified as " << s.instrumentType << "/" << s.category << " (expected Vocal/Vocals)" << std::endl;
                return 1;
            }
            if (s.winningEvidence != "FILENAME") {
                std::cerr << "FAIL: vox_adlib_01.wav winningEvidence is " << s.winningEvidence << " (expected FILENAME)" << std::endl;
                return 1;
            }
        } else if (filename == "acapella_lead.wav") {
            foundAcapella = true;
            if (s.instrumentType != "Vocal" || s.category != "Vocals") {
                std::cerr << "FAIL: acapella_lead.wav classified as " << s.instrumentType << "/" << s.category << " (expected Vocal/Vocals)" << std::endl;
                return 1;
            }
            if (s.winningEvidence != "FILENAME") {
                std::cerr << "FAIL: acapella_lead.wav winningEvidence is " << s.winningEvidence << " (expected FILENAME)" << std::endl;
                return 1;
            }
        }
    }
    
    if (!foundKick01 || !foundKickstart || !foundHiHat || !foundHatchet || !foundBassoon || !foundVocal01 || !foundAcapella) {
        std::cerr << "FAIL: Missing some of the quick-win test files in scan results." << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: Filename token-boundary classification and Hi-Hat subcategory canonicalization verified!" << std::endl;
    
    // 2. Key detection tonal gating and atonal noise check
    juce::File fTonal = tempDir.getChildFile("pure_tonal.wav");
    juce::File fNoise = tempDir.getChildFile("pure_noise.wav");
    // Deliberately use key-neutral filenames so filename parsing cannot mask
    // the acoustic mode detector under test.
    juce::File fMajorChord = tempDir.getChildFile("harmonic_fixture_one.wav");
    juce::File fMinorChord = tempDir.getChildFile("harmonic_fixture_two.wav");
    juce::File fFSharpMajorChord = tempDir.getChildFile("harmonic_fixture_three.wav");
    juce::File fAMinorChord = tempDir.getChildFile("harmonic_fixture_four.wav");
    juce::File fDMinorChord = tempDir.getChildFile("harmonic_fixture_five.wav");
    juce::File fShortLoop = tempDir.getChildFile("vocal_loop_tempo_fixture.wav");
    
    // Write 44100 samples (1s) of 440Hz sine wave (A Major / A4)
    writeTestWav(fTonal, 44100.0, 44100, false, 440.0f);
    // Write noise
    writeTestWav(fNoise, 44100.0, 44100, true);
    writeChordWav(fMajorChord, 44100.0, 88200, { 261.63f, 329.63f, 392.00f });
    writeChordWav(fMinorChord, 44100.0, 88200, { 261.63f, 311.13f, 392.00f });
    writeChordWav(fFSharpMajorChord, 44100.0, 88200, { 369.99f, 466.16f, 554.37f });
    writeChordWav(fAMinorChord, 44100.0, 88200, { 440.00f, 523.25f, 659.25f });
    writeChordWav(fDMinorChord, 44100.0, 88200, { 293.66f, 349.23f, 440.00f });
    writeClickLoopWav(fShortLoop, 32000.0, 8.0f, 120.0f);
    
    SampleManagerEngine keyEngine;
    if (!keyEngine.init(modelPath)) {
        std::cerr << "FAIL: Key engine init failed" << std::endl;
        return 1;
    }
    
    keyEngine.addPathToQueue(fTonal.getFullPathName().toStdString());
    keyEngine.addPathToQueue(fNoise.getFullPathName().toStdString());
    keyEngine.addPathToQueue(fMajorChord.getFullPathName().toStdString());
    keyEngine.addPathToQueue(fMinorChord.getFullPathName().toStdString());
    keyEngine.addPathToQueue(fFSharpMajorChord.getFullPathName().toStdString());
    keyEngine.addPathToQueue(fAMinorChord.getFullPathName().toStdString());
    keyEngine.addPathToQueue(fDMinorChord.getFullPathName().toStdString());
    keyEngine.addPathToQueue(fShortLoop.getFullPathName().toStdString());
    waitLimit = 150;
    while (keyEngine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);
        
    auto keySamples = keyEngine.getSamples();
    std::string tonalKey = "";
    std::string noiseKey = "";
    std::string majorChordKey = "";
    std::string minorChordKey = "";
    std::string fSharpMajorChordKey = "";
    std::string aMinorChordKey = "";
    std::string dMinorChordKey = "";
    float shortLoopBpm = 0.0f;
    std::string shortLoopSubcategory;
    std::string shortLoopTagSource;
    std::string shortLoopEvidence;
    float shortLoopObservedDuration = 0.0f;
    
    for (const auto& s : keySamples) {
        juce::File f(s.filePath);
        if (f.getFileName() == "pure_tonal.wav") tonalKey = s.key;
        if (f.getFileName() == "pure_noise.wav") noiseKey = s.key;
        if (f.getFileName() == "harmonic_fixture_one.wav") majorChordKey = s.key;
        if (f.getFileName() == "harmonic_fixture_two.wav") minorChordKey = s.key;
        if (f.getFileName() == "harmonic_fixture_three.wav") fSharpMajorChordKey = s.key;
        if (f.getFileName() == "harmonic_fixture_four.wav") aMinorChordKey = s.key;
        if (f.getFileName() == "harmonic_fixture_five.wav") dMinorChordKey = s.key;
        if (f.getFileName() == "vocal_loop_tempo_fixture.wav") {
            shortLoopBpm = s.bpm;
            shortLoopSubcategory = s.subcategory;
            shortLoopTagSource = s.tagSource;
            shortLoopEvidence = s.winningEvidence;
            shortLoopObservedDuration = s.durationSeconds;
        }
    }
    
    std::cout << "Tonal File Key: " << tonalKey << std::endl;
    std::cout << "Noise File Key: " << noiseKey << std::endl;
    
    if (tonalKey == "Unknown") {
        std::cerr << "FAIL: Tonal sine wave received Key = Unknown" << std::endl;
        return 1;
    }
    if (noiseKey != "Unknown") {
        std::cerr << "FAIL: Atonal noise received Key = " << noiseKey << " (expected Unknown)" << std::endl;
        return 1;
    }
    if (majorChordKey != "C Major") {
        std::cerr << "FAIL: C-major chord received Key = " << majorChordKey << std::endl;
        return 1;
    }
    if (minorChordKey != "C Minor") {
        std::cerr << "FAIL: C-minor chord received Key = " << minorChordKey << std::endl;
        return 1;
    }
    if (fSharpMajorChordKey != "F# Major") {
        std::cerr << "FAIL: F#-major chord received Key = " << fSharpMajorChordKey << std::endl;
        return 1;
    }
    if (aMinorChordKey != "A Minor") {
        std::cerr << "FAIL: A-minor chord received Key = " << aMinorChordKey << std::endl;
        return 1;
    }
    if (dMinorChordKey != "D Minor") {
        std::cerr << "FAIL: D-minor chord received Key = " << dMinorChordKey << std::endl;
        return 1;
    }
    // An unaccented click every 0.5 seconds is acoustically compatible with
    // either 120 BPM quarter notes or 60 BPM eighth notes. The real-corpus
    // report therefore tracks octave-aware error separately; this integration
    // assertion must do the same instead of pretending the waveform contains
    // a downbeat that can disambiguate the notation.
    const bool shortLoopTempoIsOctaveEquivalent = std::abs(shortLoopBpm - 120.0f) <= 1.0f
        || std::abs(shortLoopBpm - 60.0f) <= 1.0f;
    if (!shortLoopTempoIsOctaveEquivalent) {
        std::cerr << "FAIL: 8-second loop integration tempo was " << shortLoopBpm
                  << " (duration=" << shortLoopObservedDuration
                  << ", subcategory=" << shortLoopSubcategory
                  << ", source=" << shortLoopTagSource
                  << ", evidence=" << shortLoopEvidence << ")"
                  << " (expected 120 or octave-equivalent 60)" << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: Key detection tonal gating verified!" << std::endl;

    // 3. Honest BPM verification (No fake 120.0f fallback)
    for (const auto& s : keySamples) {
        juce::File f(s.filePath);
        if (f.getFileName() == "pure_noise.wav" || f.getFileName() == "pure_tonal.wav") {
            if (s.bpm == 120.0f) {
                std::cerr << "FAIL: " << f.getFileName().toStdString() << " received hardcoded 120.0f BPM fallback!" << std::endl;
                return 1;
            }
        }
    }
    std::cout << "SUCCESS: Honest zero BPM fallback verified (no fake 120.0f values)!" << std::endl;

    // 4. Semantic CamelCase Key & BPM Parsing Verification
    std::string camelKey = parseKeyFromFilename("reeseBassEmaj");
    if (camelKey != "E Major") {
        std::cerr << "FAIL: parseKeyFromFilename(\"reeseBassEmaj\") returned '" << camelKey << "' (expected 'E Major')" << std::endl;
        return 1;
    }
    std::string compoundKey = parseKeyFromFilename("ambientPad_C#m");
    if (compoundKey != "C# Minor") {
        std::cerr << "FAIL: parseKeyFromFilename(\"ambientPad_C#m\") returned '" << compoundKey << "' (expected 'C# Minor')" << std::endl;
        return 1;
    }
    float camelBpm = parseBpmFromFilename("synthLead128bpm");
    if (camelBpm != 128.0f) {
        std::cerr << "FAIL: parseBpmFromFilename(\"synthLead128bpm\") returned " << camelBpm << " (expected 128.0)" << std::endl;
        return 1;
    }
    float spaceBpm = parseBpmFromFilename("TechHouse 125 BPM");
    if (spaceBpm != 125.0f) {
        std::cerr << "FAIL: parseBpmFromFilename(\"TechHouse 125 BPM\") returned " << spaceBpm << " (expected 125.0)" << std::endl;
        return 1;
    }
    const float loopKeyBpm = parseBpmFromFilename("KSHMR_India_DR_Drum_Loop_90_A.wav");
    if (loopKeyBpm != 90.0f) {
        std::cerr << "FAIL: loop-plus-key BPM convention returned " << loopKeyBpm
                  << " (expected 90.0)" << std::endl;
        return 1;
    }
    const float indexedLoopBpm = parseBpmFromFilename("Loop_01_160_C#.wav");
    if (indexedLoopBpm != 160.0f) {
        std::cerr << "FAIL: indexed loop BPM convention returned " << indexedLoopBpm
                  << " (expected 160.0)" << std::endl;
        return 1;
    }
    if (parseBpmFromFilename("Loop_10_A.wav") != 0.0f) {
        std::cerr << "FAIL: bare loop index was incorrectly promoted to BPM" << std::endl;
        return 1;
    }

    // Producer naming: a tonal one-shot is one note, not a major/minor key.
    // Loops retain the full mode because the mode describes the repeated
    // musical material rather than a single hit.
    const juce::String oneShotName = getFormattedFilename(
        "Hit", "Bass", "Bass One-Shot", "B Major", 0.0f, 9);
    if (oneShotName != "Bass One-Shot - Hit - B") {
        std::cerr << "FAIL: one-shot key presentation returned '"
                  << oneShotName << "' (expected 'Bass One-Shot - Hit - B')" << std::endl;
        return 1;
    }
    const juce::String loopName = getFormattedFilename(
        "Loop", "Instruments", "Music Loop", "B Major", 120.0f, 9);
    if (loopName != "Music Loop - Loop - 120bpm - BMajor") {
        std::cerr << "FAIL: loop key presentation returned '"
                  << loopName << "' (expected full mode)" << std::endl;
        return 1;
    }
    const juce::String noTempoName = getFormattedFilename(
        "Hit", "Bass", "Bass One-Shot", "Unknown", 120.0f, 5);
    if (noTempoName != "Hit") {
        std::cerr << "FAIL: non-loop naming retained an untrusted BPM value: '"
                  << noTempoName << "'" << std::endl;
        return 1;
    }

    // Audio tempo detection: a periodic 120-BPM click train should produce a
    // measured tempo, while the short one-shot checks above remain unknown.
    constexpr double tempoRate = 32000.0;
    constexpr float tempoDuration = 8.0f;
    std::vector<float> clickTrain(static_cast<size_t>(tempoRate * tempoDuration), 0.0f);
    const int beatSamples = static_cast<int>(tempoRate * 0.5); // 120 BPM
    for (int onset = 0; onset < static_cast<int>(clickTrain.size()); onset += beatSamples) {
        for (int i = 0; i < static_cast<int>(tempoRate * 0.01) && onset + i < static_cast<int>(clickTrain.size()); ++i)
            clickTrain[static_cast<size_t>(onset + i)] = std::exp(-static_cast<float>(i) / 40.0f);
    }
    const float detectedTempo = estimateBpmFromAudio(
        clickTrain.data(), static_cast<int>(clickTrain.size()), tempoRate, tempoDuration);
    if (detectedTempo <= 0.0f || std::abs(detectedTempo - 120.0f) > 1.0f) {
        std::cerr << "FAIL: synthetic 120-BPM loop estimated as " << detectedTempo << std::endl;
        return 1;
    }
    // The same periodic material must not be promoted when the caller reports
    // a short source file.  The fixed/padded analysis buffer is not evidence
    // of a real loop; the true decoded duration is the authoritative gate.
    if (estimateBpmFromAudio(clickTrain.data(), static_cast<int>(clickTrain.size()),
                             tempoRate, 1.5f) != 0.0f) {
        std::cerr << "FAIL: sub-2-second source was assigned a tempo" << std::endl;
        return 1;
    }
    std::vector<float> noisyLoop(clickTrain.size(), 0.0f);
    juce::Random tempoNoise(42);
    for (float& noiseSample : noisyLoop)
        noiseSample = tempoNoise.nextFloat() * 2.0f - 1.0f;
    if (estimateBpmFromAudio(noisyLoop.data(), static_cast<int>(noisyLoop.size()),
                             tempoRate, tempoDuration) != 0.0f) {
        std::cerr << "FAIL: atonal noise was assigned a tempo" << std::endl;
        return 1;
    }
    // A short (but valid) loop remains measurable when tempo receives the
    // exact decoded sample count rather than the model's padded buffer.
    constexpr float shortLoopDuration = 3.0f;
    const int shortLoopSamples = static_cast<int>(tempoRate * shortLoopDuration);
    std::vector<float> shortClickTrain(static_cast<size_t>(shortLoopSamples), 0.0f);
    for (int onset = 0; onset < shortLoopSamples; onset += beatSamples) {
        for (int i = 0; i < static_cast<int>(tempoRate * 0.01)
                    && onset + i < shortLoopSamples; ++i)
            shortClickTrain[static_cast<size_t>(onset + i)] = std::exp(-static_cast<float>(i) / 40.0f);
    }
    const float shortLoopTempo = estimateBpmFromAudio(
        shortClickTrain.data(), shortLoopSamples, tempoRate, shortLoopDuration);
    if (shortLoopTempo <= 0.0f || std::abs(shortLoopTempo - 120.0f) > 1.0f) {
        std::cerr << "FAIL: 3-second loop duration-bound estimate was invalid" << std::endl;
        return 1;
    }

    // Multi-band regression fixtures: a low-end pulse with a regular high-
    // frequency subdivision should still resolve the beat, rather than the
    // hat grid.  These cover the common 90 BPM bass groove and 174 BPM
    // drum-and-bass range that previously exposed octave/subdivision errors.
    const auto makeLayeredTempoFixture = [&](float bpm) {
        std::vector<float> audio(static_cast<size_t>(tempoRate * tempoDuration), 0.0f);
        const double beatPeriod = 60.0 / static_cast<double>(bpm);
        const int beatCount = static_cast<int>(std::ceil(tempoDuration / beatPeriod));
        for (int beat = 0; beat < beatCount; ++beat) {
            const int onset = static_cast<int>(std::llround(beat * beatPeriod * tempoRate));
            // 70 Hz kick/bass body, ~90 ms, with a fast attack.
            const int bodyLength = static_cast<int>(tempoRate * 0.09);
            for (int i = 0; i < bodyLength && onset + i < static_cast<int>(audio.size()); ++i) {
                const float t = static_cast<float>(i / tempoRate);
                const float env = std::exp(-24.0f * t);
                audio[static_cast<size_t>(onset + i)] += 0.85f * env
                    * std::sin(2.0f * kPi * 70.0f * t);
            }
            // Four quiet, bright subdivisions per beat.  They are deliberately
            // weaker than the bass pulse, but regular enough to tempt a naive
            // broadband detector into reporting 4x the true grid.
            const double subdivision = beatPeriod / 4.0;
            for (int sub = 1; sub < 4; ++sub) {
                const int hatOnset = static_cast<int>(std::llround((beat * beatPeriod + sub * subdivision) * tempoRate));
                const int hatLength = static_cast<int>(tempoRate * 0.006);
                for (int i = 0; i < hatLength && hatOnset + i < static_cast<int>(audio.size()); ++i) {
                    const float t = static_cast<float>(i / tempoRate);
                    audio[static_cast<size_t>(hatOnset + i)] += 0.16f * std::exp(-110.0f * t)
                        * std::sin(2.0f * kPi * 6500.0f * t);
                }
            }
        }
        return audio;
    };

    for (const float expectedTempo : { 90.0f, 174.0f }) {
        const auto layered = makeLayeredTempoFixture(expectedTempo);
        const float layeredTempo = estimateBpmFromAudio(
            layered.data(), static_cast<int>(layered.size()), tempoRate, tempoDuration);
        if (layeredTempo <= 0.0f || std::abs(layeredTempo - expectedTempo) > 1.0f) {
            std::cerr << "FAIL: layered " << expectedTempo << "-BPM loop estimated as "
                      << layeredTempo << std::endl;
            return 1;
        }
    }
    std::cout << "SUCCESS: Multi-band 90/174 BPM tempo detection verified!" << std::endl;
    std::cout << "SUCCESS: CamelCase, key presentation, and BPM naming verified!" << std::endl;
    
    // Clean up temp files
    tempDir.deleteRecursively();

    std::cout << "ALL AUDIO FEATURE METADATA TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
