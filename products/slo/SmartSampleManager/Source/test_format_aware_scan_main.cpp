#include <iostream>
#include <algorithm>
#include <memory>

#include <taglib/fileref.h>
#include <taglib/tpropertymap.h>

#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } } while (0)

static bool writeAudioFile(const juce::File& destination,
                           juce::AudioFormat& format,
                           const juce::AudioBuffer<float>& audio,
                           double sampleRate)
{
    auto stream = std::make_unique<juce::FileOutputStream>(destination);
    if (!stream->openedOk())
        return false;

    std::unique_ptr<juce::AudioFormatWriter> writer(format.createWriterFor(
        stream.get(), sampleRate, static_cast<unsigned int>(audio.getNumChannels()),
        16, {}, 0));
    if (writer == nullptr)
        return false;

    // A successful writer takes ownership of the stream.
    stream.release();
    return writer->writeFromAudioSampleBuffer(audio, 0, audio.getNumSamples());
}

static bool writeGenericMetadata(const juce::File& destination,
                                 const char* bpm,
                                 const char* key)
{
    TagLib::FileRef file(destination.getFullPathName().toRawUTF8(), false);
    if (file.isNull()) return false;

    TagLib::PropertyMap properties;
    properties[TagLib::String("BPM", TagLib::String::UTF8)].append(
        TagLib::String(bpm, TagLib::String::UTF8));
    properties[TagLib::String("KEY", TagLib::String::UTF8)].append(
        TagLib::String(key, TagLib::String::UTF8));

    return file.setProperties(properties).isEmpty() && file.save();
}

int main()
{
    ScopedIsolatedCacheDb _isolatedCacheDb;
    juce::MessageManager::getInstance();

    const auto sourceDir = juce::File(std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR));
    const auto sourceFile = sourceDir.getChildFile("test_kick.wav");
    const auto tempRoot = juce::File::getSpecialLocation(juce::File::tempDirectory)
                              .getChildFile("SmartSampleManagerFormatAwareScanTest_"
                                            + juce::Uuid().toString());
    tempRoot.createDirectory();

    juce::AudioFormatManager formatManager;
    formatManager.registerBasicFormats();
    std::unique_ptr<juce::AudioFormatReader> sourceReader(
        formatManager.createReaderFor(sourceFile));
    CHECK(sourceReader != nullptr, "the checked-in WAV fixture must be readable");
    if (sourceReader == nullptr) {
        tempRoot.deleteRecursively();
        return 1;
    }

    juce::AudioBuffer<float> audio(sourceReader->numChannels,
                                   static_cast<int>(sourceReader->lengthInSamples));
    CHECK(sourceReader->read(&audio, 0, audio.getNumSamples(), 0, true, true),
          "the checked-in WAV fixture must decode into a test buffer");

    auto wavFile = tempRoot.getChildFile("from_wav.wav");
    // Use loop-shaped names so the tempo assertions exercise the metadata
    // reader without conflicting with the production contract that BPM is
    // unknown for one-shots/FX.  The payload itself remains the checked-in
    // kick fixture; only the container metadata path is under test here.
    auto aiffFile = tempRoot.getChildFile("from_aiff_loop.aiff");
    auto flacFile = tempRoot.getChildFile("from_flac_loop.flac");
    auto unsupportedFile = tempRoot.getChildFile("valid_audio.txt");
    auto malformedFlac = tempRoot.getChildFile("malformed.flac");
    auto symlinkFile = tempRoot.getChildFile("linked_copy.wav");

    CHECK(sourceFile.copyFileTo(wavFile), "should create disposable WAV fixture");
    juce::AiffAudioFormat aiffFormat;
    juce::FlacAudioFormat flacFormat;
    CHECK(writeAudioFile(aiffFile, aiffFormat, audio, sourceReader->sampleRate),
          "should create disposable AIFF fixture");
    CHECK(writeAudioFile(flacFile, flacFormat, audio, sourceReader->sampleRate),
          "should create disposable FLAC fixture");
    CHECK(writeGenericMetadata(aiffFile, "128", "C#m"),
          "should write generic BPM/key properties to the AIFF fixture");
    CHECK(writeGenericMetadata(flacFile, "96", "F#m"),
          "should write generic BPM/key properties to the FLAC fixture");
    CHECK(sourceFile.copyFileTo(unsupportedFile),
          "should create a valid-audio file with an unsupported extension");
    malformedFlac.replaceWithText("not a FLAC stream");
    CHECK(wavFile.createSymbolicLink(symlinkFile, true),
          "should create a disposable symlink fixture");

    SampleManagerEngine engine;
    const std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR)
                                  + "/Models/panns_cnn10_embedding.onnx";
    if (!engine.init(modelPath)) {
        std::cerr << "FAIL: engine init failed" << std::endl;
        tempRoot.deleteRecursively();
        return 1;
    }

    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    // An overlapping rescan must not create a second in-memory row for any
    // path, and the symlink must not widen the scan outside the fixture root.
    engine.addPathToQueue(tempRoot.getFullPathName().toStdString());
    int waitLimit = 200;
    while (engine.isBusy() && waitLimit-- > 0)
        juce::Thread::sleep(100);

    const auto samples = engine.getSamples();
    CHECK(samples.size() == 3,
          "the scan should deduplicate overlapping work, admit WAV/AIFF/FLAC, reject unsupported text, malformed FLAC, and symlinks");

    for (const auto& sample : samples) {
        CHECK(sample.filePath != unsupportedFile.getFullPathName().toStdString(),
              "a valid audio payload with an unsupported extension must not be queued");
        CHECK(sample.filePath != malformedFlac.getFullPathName().toStdString(),
              "a malformed supported-format file must not enter the library");
        CHECK(sample.filePath != symlinkFile.getFullPathName().toStdString(),
              "a symlink to an admitted audio file must not enter the library");
        CHECK(sample.isProcessed, "every admitted mixed-format fixture must finish processing");
        CHECK(sample.embeddingStatus == EmbeddingStatus::Valid,
              "every admitted mixed-format fixture must receive a real embedding");
        if (sample.filePath == aiffFile.getFullPathName().toStdString()) {
            CHECK(std::abs(sample.bpm - 128.0f) < 0.01f,
                  "AIFF generic BPM metadata should be read before fallback inference");
            CHECK(sample.key == "C#m",
                  "AIFF generic key metadata should be read before filename/audio fallback");
        }
        if (sample.filePath == flacFile.getFullPathName().toStdString()) {
            CHECK(std::abs(sample.bpm - 96.0f) < 0.01f,
                  "FLAC generic BPM metadata should be read before fallback inference");
            CHECK(sample.key == "F#m",
                  "FLAC generic key metadata should be read before filename/audio fallback");
        }
    }

    const std::vector<std::string> expectedPaths = {
        wavFile.getFullPathName().toStdString(),
        aiffFile.getFullPathName().toStdString(),
        flacFile.getFullPathName().toStdString()
    };
    for (const auto& expected : expectedPaths) {
        bool found = false;
        for (const auto& sample : samples)
            found = found || sample.filePath == expected;
        CHECK(found, "each registered audio format must be present in the library: " + expected);
    }

    std::vector<std::string> observedPaths;
    for (const auto& sample : samples)
        observedPaths.push_back(sample.filePath);
    std::sort(observedPaths.begin(), observedPaths.end());
    CHECK(std::adjacent_find(observedPaths.begin(), observedPaths.end()) == observedPaths.end(),
          "overlapping scans must not produce duplicate in-memory paths");

    tempRoot.deleteRecursively();
    if (failures != 0)
        return 1;

    std::cout << "SUCCESS: format-aware scan admitted WAV/AIFF/FLAC, ignored an unsupported "
                 "extension, and rejected malformed FLAC without poisoning the batch.\n";
    juce::MessageManager::deleteInstance();
    return 0;
}
