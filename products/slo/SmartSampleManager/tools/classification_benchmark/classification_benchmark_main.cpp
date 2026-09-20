#include <iostream>
#include <chrono>
#include <vector>
#include <mach/mach.h>
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

static size_t residentMemoryBytes()
{
    mach_task_basic_info_data_t info;
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO,
                   reinterpret_cast<task_info_t>(&info), &count) != KERN_SUCCESS) {
        return 0;
    }
    return info.resident_size;
}

int main(int argc, char* argv[])
{
    juce::File customCacheDir = juce::File::getCurrentWorkingDirectory()
        .getChildFile("fixtures")
        .getChildFile("cache");
    customCacheDir.createDirectory();
    SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(customCacheDir);
    juce::MessageManager::getInstance();

    if (argc < 4) {
        std::cerr << "Usage: ClassificationBenchmark <scan|perf|soak|features|stereo|tempo> <scan_dir> <output_json_path>" << std::endl;
        std::cerr << "Usage: ClassificationBenchmark <scan|perf|soak|features|stereo|tempo|organize> <scan_dir> <output_json_path> [style 1-8] [copy|move] [--beta-gate]" << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }

    std::string mode = argv[1];
    std::string scanDir = argv[2];
    std::string outPath = argv[3];

    juce::File fixtureDir(scanDir);
    if (!fixtureDir.isDirectory()) {
        std::cerr << "FAIL: " << scanDir << " is not a directory" << std::endl;
        juce::MessageManager::deleteInstance();
        return 1;
    }

    if (mode == "scan") {
        SampleManagerEngine engine;
        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: Engine initialization failed." << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }

        engine.clearCache();
        std::cout << "Scanning directory: " << scanDir << std::endl;
        engine.addPathToQueue(scanDir);

        while (engine.isBusy()) {
            juce::Thread::sleep(100);
        }

        auto samples = engine.getSamples();
        std::cout << "Scanned " << samples.size() << " samples." << std::endl;

        juce::File outFile(outPath);
        auto outputParent = outFile.getParentDirectory();
        if (!outputParent.exists() && !outputParent.createDirectory()) {
            std::cerr << "FAIL: Could not create output directory: "
                      << outputParent.getFullPathName() << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }
        auto stagingFile = outFile.getSiblingFile(outFile.getFileName() + ".staging");
        if (stagingFile.existsAsFile()) {
            std::cerr << "FAIL: Refusing to reuse stale staging output: "
                      << stagingFile.getFullPathName() << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }

        {
        juce::FileOutputStream stream(stagingFile);
        if (!stream.openedOk()) {
            std::cerr << "FAIL: Could not open output file: " << outPath << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }

        stream.writeText("[\n", false, false, nullptr);
        for (size_t i = 0; i < samples.size(); ++i) {
            const auto& s = samples[i];
            
            juce::StringArray tags;
            for (const auto& tag : s.secondaryTags) {
                tags.add(juce::String(tag));
            }

            juce::String tagsJson = "";
            for (int j = 0; j < tags.size(); ++j) {
                tagsJson << "\"" << tags[j].replace("\"", "\\\"") << "\"" << (j + 1 < tags.size() ? ", " : "");
            }

            // V4-G: dump the raw 512D embedding (when present) so the offline
            // OOD evaluation harness can compute centroid-distance / kNN-
            // distance scores without re-running ONNX inference. Local/
            // gitignored output only -- see docs/SLO_CLASSIFICATION_V4G_OOD_REPORT.md.
            juce::String embeddingJson = "";
            if (s.embeddingStatus == EmbeddingStatus::Valid && s.embedding.size() == 512) {
                for (size_t j = 0; j < s.embedding.size(); ++j) {
                    embeddingJson << s.embedding[j] << (j + 1 < s.embedding.size() ? "," : "");
                }
            }

            juce::String jsonItem;
            jsonItem << "  {\n"
                     // Preserve the full path for manifest/cache identity.
                     // Basenames are not unique in the real corpus, so a
                     // report containing only getFileName() cannot support a
                     // provenance-safe qualification receipt.
                     << "    \"filePath\": \"" << juce::File(s.filePath).getFullPathName().replace("\"", "\\\"") << "\",\n"
                     << "    \"fileName\": \"" << juce::File(s.filePath).getFileName().replace("\"", "\\\"") << "\",\n"
                     << "    \"name\": \"" << juce::String(s.name).replace("\"", "\\\"") << "\",\n"
                     << "    \"instrumentType\": \"" << s.instrumentType << "\",\n"
                     << "    \"category\": \"" << s.category << "\",\n"
                     << "    \"subcategory\": \"" << s.subcategory << "\",\n"
                     << "    \"key\": \"" << s.key << "\",\n"
                     << "    \"bpm\": " << s.bpm << ",\n"
                     << "    \"durationSeconds\": " << s.durationSeconds << ",\n"
                     << "    \"tagConfidence\": " << s.tagConfidence << ",\n"
                     << "    \"winningEvidence\": \"" << s.winningEvidence << "\",\n"
                     << "    \"tagSource\": \"" << s.tagSource << "\",\n"
                     << "    \"diagHeuristicCategoryPreML\": \"" << s.diagHeuristicCategoryPreML << "\",\n"
                     << "    \"diagHeuristicSubcategoryPreML\": \"" << s.diagHeuristicSubcategoryPreML << "\",\n"
                     << "    \"diagHeuristicEvidencePreML\": \"" << s.diagHeuristicEvidencePreML << "\",\n"
                     << "    \"diagHeuristicConfidencePreML\": " << s.diagHeuristicConfidencePreML << ",\n"
                     << "    \"diagMlSubcategory\": \"" << s.diagMlSubcategory << "\",\n"
                     << "    \"diagMlConfidence\": " << s.diagMlConfidence << ",\n"
                     << "    \"diagMlIsOod\": " << (s.diagMlIsOod ? "true" : "false") << ",\n"
                     << "    \"diagMlEvaluated\": " << (s.diagMlEvaluated ? "true" : "false") << ",\n"
                     << "    \"diagMlOverrideApplied\": " << (s.diagMlOverrideApplied ? "true" : "false") << ",\n"
                     << "    \"diagMlMargin\": " << s.diagMlMargin << ",\n"
                     << "    \"diagMlEntropy\": " << s.diagMlEntropy << ",\n"
                     << "    \"diagMlLogitEnergy\": " << s.diagMlLogitEnergy << ",\n"
                     << "    \"diagMlCentroidCos\": " << s.diagMlCentroidCos << ",\n"
                     << "    \"diagMlNearestCentroid\": " << s.diagMlNearestCentroid << ",\n"
                     << "    \"embedding\": [" << embeddingJson << "],\n"
                     << "    \"secondaryTags\": [" << tagsJson << "]\n"
                     << "  }" << (i + 1 < samples.size() ? "," : "") << "\n";
            
            stream.writeText(jsonItem, false, false, nullptr);
        }
        stream.writeText("]\n", false, false, nullptr);
        stream.flush();
        }
        if (outFile.existsAsFile() || !stagingFile.moveFileTo(outFile)) {
            stagingFile.deleteFile();
            std::cerr << "FAIL: Refusing to overwrite or publish output file: " << outPath << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }
        std::cout << "Results saved to: " << outPath << std::endl;
    }
    else if (mode == "perf") {
        std::cout << "Running performance benchmark on: " << scanDir << std::endl;
        
        // Repeated runs (e.g. 3 iterations)
        const int numIterations = 3;
        std::vector<double> coldScanTimes;
        std::vector<double> cachedScanTimes;
        size_t memPeak = 0;
        size_t memBefore = residentMemoryBytes();
        size_t sampleCount = 0;

        for (int iter = 0; iter < numIterations; ++iter) {
            std::cout << "  Iteration " << (iter + 1) << "/" << numIterations << std::endl;
            
            // Cold Scan
            {
                SampleManagerEngine engine;
                engine.clearCache();
                
                auto tStartInit = std::chrono::steady_clock::now();
                std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
                if (!engine.init(modelPath)) {
                    std::cerr << "FAIL: Engine initialization failed." << std::endl;
                    juce::MessageManager::deleteInstance();
                    return 1;
                }
                auto tEndInit = std::chrono::steady_clock::now();
                double initMs = std::chrono::duration<double, std::milli>(tEndInit - tStartInit).count();
                std::cout << "    Model Init Time: " << initMs << " ms" << std::endl;

                auto tStartScan = std::chrono::steady_clock::now();
                engine.addPathToQueue(scanDir);
                while (engine.isBusy()) {
                    juce::Thread::sleep(50);
                    size_t curRss = residentMemoryBytes();
                    if (curRss > memPeak) memPeak = curRss;
                }
                auto tEndScan = std::chrono::steady_clock::now();
                double scanMs = std::chrono::duration<double, std::milli>(tEndScan - tStartScan).count();
                coldScanTimes.push_back(scanMs);
                sampleCount = engine.getSampleCount();
            }

            // Cached Scan (reuse existing database)
            {
                SampleManagerEngine engine;
                std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
                if (!engine.init(modelPath)) {
                    std::cerr << "FAIL: Engine initialization failed." << std::endl;
                    juce::MessageManager::deleteInstance();
                    return 1;
                }

                auto tStartScan = std::chrono::steady_clock::now();
                engine.addPathToQueue(scanDir);
                while (engine.isBusy()) {
                    juce::Thread::sleep(50);
                }
                auto tEndScan = std::chrono::steady_clock::now();
                double scanMs = std::chrono::duration<double, std::milli>(tEndScan - tStartScan).count();
                cachedScanTimes.push_back(scanMs);
            }
        }

        size_t memAfter = residentMemoryBytes();

        // Calculate statistics
        double coldMean = 0, coldMin = coldScanTimes[0], coldMax = coldScanTimes[0];
        double cachedMean = 0, cachedMin = cachedScanTimes[0], cachedMax = cachedScanTimes[0];
        for (double t : coldScanTimes) {
            coldMean += t;
            if (t < coldMin) coldMin = t;
            if (t > coldMax) coldMax = t;
        }
        coldMean /= numIterations;

        for (double t : cachedScanTimes) {
            cachedMean += t;
            if (t < cachedMin) cachedMin = t;
            if (t > cachedMax) cachedMax = t;
        }
        cachedMean /= numIterations;

        double coldSd = 0;
        for (double t : coldScanTimes) {
            coldSd += (t - coldMean) * (t - coldMean);
        }
        coldSd = std::sqrt(coldSd / numIterations);

        juce::File outFile(outPath);
        outFile.deleteFile();
        juce::FileOutputStream stream(outFile);
        if (stream.openedOk()) {
            juce::String json;
            json << "{\n"
                 << "  \"sample_count\": " << sampleCount << ",\n"
                 << "  \"cold_scan_mean_ms\": " << coldMean << ",\n"
                 << "  \"cold_scan_min_ms\": " << coldMin << ",\n"
                 << "  \"cold_scan_max_ms\": " << coldMax << ",\n"
                 << "  \"cold_scan_sd_ms\": " << coldSd << ",\n"
                 << "  \"cached_scan_mean_ms\": " << cachedMean << ",\n"
                 << "  \"cached_scan_min_ms\": " << cachedMin << ",\n"
                 << "  \"cached_scan_max_ms\": " << cachedMax << ",\n"
                 << "  \"rss_before_mb\": " << (memBefore / 1024.0 / 1024.0) << ",\n"
                 << "  \"rss_peak_mb\": " << (memPeak / 1024.0 / 1024.0) << ",\n"
                 << "  \"rss_after_mb\": " << (memAfter / 1024.0 / 1024.0) << "\n"
                 << "}\n";
            stream.writeText(json, false, false, nullptr);
        }
        std::cout << "Performance metrics saved to: " << outPath << std::endl;
    }
    else if (mode == "soak") {
        // SLO Master Plan Phase 3 (B-009): a real leak-detection soak, not
        // just "run it for a while". Repeatedly construct/init/scan/destroy
        // a fresh engine against the SAME directory (cache warm after the
        // first pass, so each iteration is a realistic repeated-rescan
        // workload) and record RSS after every iteration. A healthy engine
        // should plateau; a leak shows up as RSS climbing roughly linearly
        // across iterations with no plateau.
        const int numIterations = 30;
        std::vector<double> rssPerIterationMb;
        std::vector<double> scanMsPerIteration;
        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";

        std::cout << "Running " << numIterations << "-iteration soak scan on: " << scanDir << std::endl;
        for (int iter = 0; iter < numIterations; ++iter) {
            SampleManagerEngine engine;
            if (!engine.init(modelPath)) {
                std::cerr << "FAIL: Engine initialization failed at soak iteration " << iter << std::endl;
                juce::MessageManager::deleteInstance();
                return 1;
            }
            if (iter == 0) engine.clearCache(); // first pass only: force a real cold scan to populate the cache

            auto tStart = std::chrono::steady_clock::now();
            engine.addPathToQueue(scanDir);
            while (engine.isBusy()) {
                juce::Thread::sleep(50);
            }
            auto tEnd = std::chrono::steady_clock::now();
            double scanMs = std::chrono::duration<double, std::milli>(tEnd - tStart).count();
            scanMsPerIteration.push_back(scanMs);

            double rssMb = residentMemoryBytes() / 1024.0 / 1024.0;
            rssPerIterationMb.push_back(rssMb);
            std::cout << "  Iteration " << (iter + 1) << "/" << numIterations
                       << ": rss=" << rssMb << " MB, scan=" << scanMs << " ms" << std::endl;
            // engine destroyed here (end of scope) before the next iteration constructs a fresh one
        }

        // Compare the mean RSS of the first quarter of iterations (after
        // warm-up) against the last quarter -- a simple, honest plateau-vs-
        // climb signal without needing a full regression.
        int quarter = std::max(1, numIterations / 4);
        double firstQuarterMean = 0, lastQuarterMean = 0;
        for (int i = 0; i < quarter; ++i) firstQuarterMean += rssPerIterationMb[static_cast<size_t>(i)];
        firstQuarterMean /= quarter;
        for (int i = numIterations - quarter; i < numIterations; ++i) lastQuarterMean += rssPerIterationMb[static_cast<size_t>(i)];
        lastQuarterMean /= quarter;
        double growthMb = lastQuarterMean - firstQuarterMean;
        double growthPct = (firstQuarterMean > 0.0) ? (growthMb / firstQuarterMean * 100.0) : 0.0;

        juce::File outFile(outPath);
        outFile.deleteFile();
        juce::FileOutputStream stream(outFile);
        if (stream.openedOk()) {
            juce::String rssJson, scanJson;
            for (size_t i = 0; i < rssPerIterationMb.size(); ++i) {
                rssJson << rssPerIterationMb[i] << (i + 1 < rssPerIterationMb.size() ? "," : "");
                scanJson << scanMsPerIteration[i] << (i + 1 < scanMsPerIteration.size() ? "," : "");
            }
            juce::String json;
            json << "{\n"
                 << "  \"num_iterations\": " << numIterations << ",\n"
                 << "  \"rss_per_iteration_mb\": [" << rssJson << "],\n"
                 << "  \"scan_ms_per_iteration\": [" << scanJson << "],\n"
                 << "  \"first_quarter_mean_rss_mb\": " << firstQuarterMean << ",\n"
                 << "  \"last_quarter_mean_rss_mb\": " << lastQuarterMean << ",\n"
                 << "  \"growth_mb\": " << growthMb << ",\n"
                 << "  \"growth_pct\": " << growthPct << "\n"
                 << "}\n";
            stream.writeText(json, false, false, nullptr);
        }
        std::cout << "Soak metrics saved to: " << outPath << std::endl;
    }
    else if (mode == "features") {
        // Fine-Grained Subcategorization V1, attribute-layer calibration.
        // Dumps raw DSP features (zcr/lowEnergyRatio/highEnergyRatio/
        // decayTimeSeconds/pitchSweep) per file via
        // SampleManagerEngine::analyzeFileForDiagnostics() -- diagnostic
        // only, no cache DB touched, no engine constructed. Used to get
        // real feature distributions from real audio to justify attribute
        // thresholds with evidence rather than guessing.
        std::cout << "Extracting raw DSP features from: " << scanDir << std::endl;
        juce::Array<juce::File> files;
        fixtureDir.findChildFiles(files, juce::File::findFiles, true, "*.wav;*.aif;*.aiff;*.flac");

        juce::File outFile(outPath);
        outFile.deleteFile();
        juce::FileOutputStream stream(outFile);
        if (!stream.openedOk()) {
            std::cerr << "FAIL: Could not open output file: " << outPath << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }

        stream.writeText("[\n", false, false, nullptr);
        for (int i = 0; i < files.size(); ++i) {
            AudioFeatures feat = SampleManagerEngine::analyzeFileForDiagnostics(files[i]);
            juce::String jsonItem;
            jsonItem << "  {\n"
                     << "    \"filePath\": \"" << files[i].getFileName().replace("\"", "\\\"") << "\",\n"
                     << "    \"zcr\": " << feat.zcr << ",\n"
                     << "    \"lowEnergyRatio\": " << feat.lowEnergyRatio << ",\n"
                     << "    \"highEnergyRatio\": " << feat.highEnergyRatio << ",\n"
                     << "    \"decayTimeSeconds\": " << feat.decayTimeSeconds << ",\n"
                     << "    \"pitchSweep\": " << feat.pitchSweep << "\n"
                     << "  }" << (i + 1 < files.size() ? "," : "") << "\n";
            stream.writeText(jsonItem, false, false, nullptr);
        }
        stream.writeText("]\n", false, false, nullptr);
        std::cout << "Extracted features for " << files.size() << " files. Saved to: " << outPath << std::endl;
    }
    else if (mode == "stereo") {
        // Exploratory calibration ONLY for a candidate Wide/Mono attribute
        // (see SLO_PRODUCER_TAXONOMY_REQUIREMENTS_V1.md's "genuinely still
        // missing" list) -- deliberately NOT wired into any production
        // struct/tag yet. A quick Python correlation check using the
        // stdlib `wave` module only parsed 75/447 real stereo corpus files
        // (format limitations, not a product defect) -- too thin a sample
        // to calibrate honestly. Uses JUCE's AudioFormatReader here instead,
        // the same robust decode path used everywhere else in this codebase
        // (e.g. analyzeFileForDiagnostics()), to get full real-corpus
        // coverage before deciding whether this attribute ships at all.
        std::cout << "Extracting stereo correlation from: " << scanDir << std::endl;
        juce::Array<juce::File> files;
        fixtureDir.findChildFiles(files, juce::File::findFiles, true, "*.wav;*.aif;*.aiff;*.flac");

        juce::File outFile(outPath);
        outFile.deleteFile();
        juce::FileOutputStream stream(outFile);
        if (!stream.openedOk()) {
            std::cerr << "FAIL: Could not open output file: " << outPath << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }

        juce::AudioFormatManager fm;
        fm.registerBasicFormats();

        stream.writeText("[\n", false, false, nullptr);
        int written = 0;
        for (int i = 0; i < files.size(); ++i) {
            std::unique_ptr<juce::AudioFormatReader> reader(fm.createReaderFor(files[i]));
            if (reader == nullptr || reader->lengthInSamples <= 0) continue;

            const int numChannels = static_cast<int>(reader->numChannels);
            const int numSamples = static_cast<int>(reader->lengthInSamples);

            double correlation = 1.0; // mono files: not applicable, but recorded as 1.0 (fully "narrow") for completeness
            if (numChannels >= 2) {
                juce::AudioBuffer<float> buffer(numChannels, numSamples);
                reader->read(&buffer, 0, numSamples, 0, true, true);
                const float* L = buffer.getReadPointer(0);
                const float* R = buffer.getReadPointer(1);

                double meanL = 0.0, meanR = 0.0;
                for (int s = 0; s < numSamples; ++s) { meanL += L[s]; meanR += R[s]; }
                meanL /= numSamples; meanR /= numSamples;

                double num = 0.0, denL = 0.0, denR = 0.0;
                for (int s = 0; s < numSamples; ++s) {
                    double dl = L[s] - meanL, dr = R[s] - meanR;
                    num += dl * dr;
                    denL += dl * dl;
                    denR += dr * dr;
                }
                correlation = (denL > 1e-12 && denR > 1e-12) ? (num / std::sqrt(denL * denR)) : 1.0;
            }

            juce::String jsonItem;
            jsonItem << (written > 0 ? ",\n" : "") << "  {\n"
                     << "    \"filePath\": \"" << files[i].getFileName().replace("\"", "\\\"") << "\",\n"
                     << "    \"channels\": " << numChannels << ",\n"
                     << "    \"correlation\": " << correlation << "\n"
                     << "  }";
            stream.writeText(jsonItem, false, false, nullptr);
            written++;
        }
        stream.writeText("\n]\n", false, false, nullptr);
        std::cout << "Extracted stereo correlation for " << written << " files. Saved to: " << outPath << std::endl;
    }
    else if (mode == "tempo") {
        // Acoustic-tempo qualification path.  This deliberately bypasses the
        // production filename/metadata precedence chain and evaluates only
        // the estimator against a reference BPM parsed from the filename.
        // The reference is reported as a weak, reproducible proxy (not human
        // ground truth); rows without a plausible BPM token remain in the
        // receipt but are excluded from accuracy aggregates.
        std::cout << "Evaluating acoustic tempo on: " << scanDir << std::endl;
        juce::Array<juce::File> files;
        fixtureDir.findChildFiles(files, juce::File::findFiles, true, "*.wav;*.aif;*.aiff;*.flac;*.mp3;*.ogg");

        juce::AudioFormatManager fm;
        fm.registerBasicFormats();
        juce::File outFile(outPath);
        if (outFile.existsAsFile()) {
            std::cerr << "FAIL: Refusing to overwrite existing tempo receipt: " << outPath << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }
        const juce::File outputParent = outFile.getParentDirectory();
        if (!outputParent.exists() && !outputParent.createDirectory()) {
            std::cerr << "FAIL: Could not create output directory: "
                      << outputParent.getFullPathName() << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }
        juce::FileOutputStream stream(outFile);
        if (!stream.openedOk()) {
            std::cerr << "FAIL: Could not open output file: " << outPath << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }

        int decoded = 0;
        int eligibleReferences = 0;
        int evaluated = 0;
        int unknownEligible = 0;
        int withinOne = 0;
        int withinTwo = 0;
        int written = 0;
        double absoluteError = 0.0;
        stream.writeText("[\n", false, false, nullptr);
        for (int i = 0; i < files.size(); ++i) {
            std::unique_ptr<juce::AudioFormatReader> reader(fm.createReaderFor(files[i]));
            if (reader == nullptr || reader->lengthInSamples <= 0 || reader->sampleRate <= 0.0)
                continue;

            const int channels = static_cast<int>(reader->numChannels);
            // Tempo needs several bars for sparse/half-time material.  Keep
            // this independent from the production 5-second embedding view;
            // the evaluator mirrors the bounded 20-second tempo view used by
            // prepareFile().
            const int fullLength = static_cast<int>(std::min<juce::int64>(
                reader->lengthInSamples,
                static_cast<juce::int64>(std::ceil(reader->sampleRate * 20.0))));
            if (channels <= 0 || fullLength <= 0) continue;

            juce::AudioBuffer<float> buffer(channels, fullLength);
            if (!reader->read(&buffer, 0, fullLength, 0, true, true)) continue;
            std::vector<float> mono(static_cast<size_t>(fullLength), 0.0f);
            for (int ch = 0; ch < channels; ++ch) {
                const float* channelData = buffer.getReadPointer(ch);
                for (int sample = 0; sample < fullLength; ++sample)
                    mono[static_cast<size_t>(sample)] += channelData[sample] / static_cast<float>(channels);
            }

            ++decoded;
            const int shortLength = static_cast<int>(std::min<juce::int64>(
                reader->lengthInSamples,
                static_cast<juce::int64>(std::ceil(reader->sampleRate * 5.0))));
            const float shortEstimate = estimateBpmFromAudio(
                mono.data(), shortLength, reader->sampleRate,
                static_cast<float>(reader->lengthInSamples / reader->sampleRate));
            const float longEstimate = estimateBpmFromAudio(
                mono.data(), fullLength, reader->sampleRate,
                static_cast<float>(reader->lengthInSamples / reader->sampleRate));
            // A production-safe fused value is only emitted when the two
            // temporal views agree.  If one view abstains, retain the other;
            // a disagreement is deliberately unknown rather than a guessed
            // compromise between incompatible beat hypotheses.
            float estimate = 0.0f;
            if (shortEstimate > 0.0f && longEstimate > 0.0f) {
                if (std::abs(shortEstimate - longEstimate) <= 2.0f)
                    estimate = std::round(((shortEstimate + longEstimate) * 0.5f) * 10.0f) / 10.0f;
            } else if (shortEstimate > 0.0f) {
                estimate = shortEstimate;
            } else {
                estimate = longEstimate;
            }
            const float reference = parseBpmFromFilename(files[i].getFileNameWithoutExtension().toStdString());
            const bool loopEvidence = files[i].getFullPathName().containsIgnoreCase("loop");
            const bool referenceEligible = reference > 0.0f
                && loopEvidence
                && (reader->lengthInSamples / reader->sampleRate) >= 2.0;
            if (referenceEligible) {
                ++eligibleReferences;
                if (estimate <= 0.0f) ++unknownEligible;
            }
            if (referenceEligible && estimate > 0.0f) {
                const double error = std::abs(static_cast<double>(estimate - reference));
                absoluteError += error;
                ++evaluated;
                if (error <= 1.0) ++withinOne;
                if (error <= 2.0) ++withinTwo;
            }

            juce::String jsonItem;
            jsonItem << (written > 0 ? ",\n" : "") << "  {\n"
                     << "    \"filePath\": \"" << files[i].getFullPathName().replace("\"", "\\\"") << "\",\n"
                     << "    \"fileName\": \"" << files[i].getFileName().replace("\"", "\\\"") << "\",\n"
                     << "    \"durationSeconds\": " << (reader->lengthInSamples / reader->sampleRate) << ",\n"
                     << "    \"referenceBpm\": " << reference << ",\n"
                     << "    \"referenceEligible\": " << (referenceEligible ? "true" : "false") << ",\n"
                     << "    \"estimatedBpmShort\": " << shortEstimate << ",\n"
                     << "    \"estimatedBpmLong\": " << longEstimate << ",\n"
                     << "    \"estimatedBpm\": " << estimate << "\n"
                     << "  }";
            stream.writeText(jsonItem, false, false, nullptr);
            ++written;
        }
        stream.writeText("\n]\n", false, false, nullptr);
        stream.flush();
        std::cout << "Decoded " << decoded << " files; eligible loop references " << eligibleReferences
                  << "; evaluated " << evaluated << "; unknown eligible estimates " << unknownEligible << "." << std::endl;
        if (eligibleReferences > 0) {
            if (evaluated > 0)
                std::cout << "MAE " << (absoluteError / evaluated)
                          << " BPM over non-unknown estimates; ";
            else
                std::cout << "MAE unavailable (all eligible estimates unknown); ";
            std::cout << "within +/-1 " << withinOne << "/" << eligibleReferences
                      << "; within +/-2 " << withinTwo << "/" << eligibleReferences << "." << std::endl;
        }
        std::cout << "Tempo receipt saved to: " << outPath << std::endl;
    }
    else if (mode == "organize") {
        int namingStyle = 7; // default: 7 (Ableton Places: Category/Subcategory)
        if (argc > 4) {
            namingStyle = std::atoi(argv[4]);
            if (namingStyle < 1 || namingStyle > 8) namingStyle = 7;
        }
        bool copyInsteadOfMove = true;
        if (argc > 5) {
            std::string op = argv[5];
            if (op == "move" || op == "Move") copyInsteadOfMove = false;
        }
        bool enableBetaGate = false;
        if (argc > 6) {
            std::string gateArg = argv[6];
            if (gateArg == "--beta-gate" || gateArg == "beta") enableBetaGate = true;
        }
        juce::File customTargetDir;
        if (argc > 7) {
            customTargetDir = juce::File(argv[7]);
        }

        SampleManagerEngine engine;
        engine.setBetaPolicyGateEnabled(enableBetaGate);

        std::string modelPath = std::string(SMART_SAMPLE_MANAGER_SOURCE_DIR) + "/Models/panns_cnn10_embedding.onnx";
        if (!engine.init(modelPath)) {
            std::cerr << "FAIL: Engine initialization failed." << std::endl;
            juce::MessageManager::deleteInstance();
            return 1;
        }

        engine.clearCache();
        std::cout << "Scanning & classifying library for reorganization: " << scanDir << std::endl;
        auto tStart = std::chrono::steady_clock::now();
        engine.addPathToQueue(scanDir);
        while (engine.isBusy()) {
            juce::Thread::sleep(50);
        }

        auto samples = engine.getSamples();
        std::cout << "Scanned & classified " << samples.size() << " samples." << std::endl;

        std::cout << "Reorganizing samples into hierarchical taxonomy (style=" << namingStyle
                  << ", operation=" << (copyInsteadOfMove ? "COPY" : "MOVE")
                  << ", betaGate=" << (enableBetaGate ? "ON" : "OFF");
        if (customTargetDir != juce::File()) {
            std::cout << ", targetDir=" << customTargetDir.getFullPathName();
        }
        std::cout << ")..." << std::endl;
        engine.reorganizeSamples(namingStyle, copyInsteadOfMove, customTargetDir);
        auto tEnd = std::chrono::steady_clock::now();
        double durationMs = std::chrono::duration<double, std::milli>(tEnd - tStart).count();

        std::cout << "Reorganization completed in " << durationMs << " ms." << std::endl;
        std::cout << "Journal written to: " << engine.getLastSortJournalPath() << std::endl;

        juce::File outFile(outPath);
        outFile.deleteFile();
        juce::FileOutputStream stream(outFile);
        if (stream.openedOk()) {
            std::map<std::string, int> catCounts;
            std::map<std::string, int> subcatCounts;
            for (const auto& s : samples) {
                catCounts[s.category.empty() ? "Unclassified" : s.category]++;
                subcatCounts[s.subcategory.empty() ? "Unclassified" : s.subcategory]++;
            }

            juce::String catJson = "";
            size_t idx = 0;
            for (const auto& kv : catCounts) {
                catJson << "    \"" << juce::String(kv.first).replace("\"", "\\\"") << "\": " << kv.second
                        << (++idx < catCounts.size() ? ",\n" : "\n");
            }

            juce::String subcatJson = "";
            idx = 0;
            for (const auto& kv : subcatCounts) {
                subcatJson << "    \"" << juce::String(kv.first).replace("\"", "\\\"") << "\": " << kv.second
                           << (++idx < subcatCounts.size() ? ",\n" : "\n");
            }

            juce::String json;
            json << "{\n"
                 << "  \"operation\": \"" << (copyInsteadOfMove ? "copy" : "move") << "\",\n"
                 << "  \"naming_style\": " << namingStyle << ",\n"
                 << "  \"beta_gate_enabled\": " << (enableBetaGate ? "true" : "false") << ",\n"
                 << "  \"total_samples\": " << samples.size() << ",\n"
                 << "  \"scan_dir\": \"" << juce::File(scanDir).getFullPathName().replace("\"", "\\\"") << "\",\n"
                 << "  \"journal_path\": \"" << juce::String(engine.getLastSortJournalPath()).replace("\"", "\\\"") << "\",\n"
                 << "  \"duration_ms\": " << durationMs << ",\n"
                 << "  \"categories\": {\n" << catJson << "  },\n"
                 << "  \"subcategories\": {\n" << subcatJson << "  }\n"
                 << "}\n";
            stream.writeText(json, false, false, nullptr);
        }
        std::cout << "Reorganization report saved to: " << outPath << std::endl;
    }

    juce::MessageManager::deleteInstance();
    return 0;
}
