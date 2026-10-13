#include "PluginProcessor.h"
#include <chrono>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <thread>
#include <vector>
#if JUCE_MAC || JUCE_LINUX
 #include <sys/resource.h>
#endif
#if JUCE_MAC
 #include <malloc/malloc.h>
 #include <mach/mach.h>
#endif

static uint64_t processPhysicalFootprintBytes()
{
#if JUCE_MAC
    task_vm_info_data_t info {};
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, reinterpret_cast<task_info_t>(&info), &count) == KERN_SUCCESS)
        return static_cast<uint64_t>(info.phys_footprint);
    return 0; // Missing task accounting leaves retained-memory qualification to the supervised profiler.
#else
    return 0; // Peak RSS remains available; other hosts need a current private-footprint profiler.
#endif
}

static uint64_t processLiveHeapBytes()
{
#if JUCE_MAC
    malloc_statistics_t statistics {};
    malloc_zone_statistics(nullptr, &statistics); // A null zone sums live bytes across all macOS allocator zones.
    return static_cast<uint64_t>(statistics.size_in_use);
#else
    return 0; // Other hosts report RSS; retained-object qualification needs their allocator profiler.
#endif
}

static uint64_t processPeakRssBytes()
{
#if JUCE_MAC || JUCE_LINUX
    rusage usage {};
    if (getrusage(RUSAGE_SELF, &usage) != 0) return 0; // An unavailable OS counter leaves RSS qualification to the supervised host profiler.
   #if JUCE_MAC
    return static_cast<uint64_t>(usage.ru_maxrss); // macOS reports bytes; Linux reports KiB.
   #else
    return static_cast<uint64_t>(usage.ru_maxrss) * 1024;
   #endif
#else
    return 0; // Other hosts retain functional/latency gates; this POSIX RSS probe is optional.
#endif
}

// Wall-paced callbacks exercise the accepting queue path and the shared worker.
// A tight offline loop would mostly measure overflow returns and hide DSP cost.
class BenchmarkPlayHead final : public juce::AudioPlayHead
{
public:
    juce::Optional<PositionInfo> getPosition() const override
    {
        PositionInfo position; position.setTimeInSamples(sample); position.setIsPlaying(true);
        return position;
    }
    juce::int64 sample = 0;
};

int main()
{
    bool passed = true;
    const auto publishEndpoint = juce::SystemStats::getEnvironmentVariable("KENN_TEST_PUBLISH_ENDPOINT", "");
    const auto publishSeconds = juce::SystemStats::getEnvironmentVariable("KENN_TEST_PUBLISH_SECONDS", "");
    const auto sustainedSeconds = publishSeconds.getDoubleValue();
    if (publishSeconds.isNotEmpty() && (publishEndpoint.isEmpty() || ! std::isfinite(sustainedSeconds)
        || sustainedSeconds < 3.0 || sustainedSeconds > 600.0))
    {
        std::cerr << "KENN_TEST_PUBLISH_SECONDS needs a fixture endpoint and 3–600 seconds.\n";
        return 1; // An explicit profile must not silently run the shorter, non-network matrix.
    }
    std::cout << std::fixed << std::setprecision(3);
    for (const double rate : { 44100.0, 48000.0, 96000.0 })
        for (const int bufferSize : { 64, 128, 256, 512, 1024 })
            for (const int instanceCount : { 1, 8, 32, 64 })
            {
                // The opt-in HTTP fixture profiles four longer cells. Ordinary
                // CTest never contacts a companion or changes its 60-cell matrix.
                if (publishEndpoint.isNotEmpty() && (rate != 48000.0 || bufferSize != 128)) continue;
                if (publishSeconds.isNotEmpty() && instanceCount != 64) continue; // Sustained transport profiles isolate the 64-insert cell.
                BenchmarkPlayHead clock;
                std::vector<std::unique_ptr<KENNMixAssistantAudioProcessor>> processors;
                for (int instance = 0; instance < instanceCount; ++instance)
                {
                    auto processor = std::make_unique<KENNMixAssistantAudioProcessor>();
                    processor->prepareToPlay(rate, bufferSize);
                    processor->setPlayHead(&clock);
                    if (publishEndpoint.isNotEmpty())
                    {
                        juce::String error;
                        if (! processor->setKennConnection(publishEndpoint, "publish-profile-" + juce::String(instanceCount), error))
                        {
                            std::cerr << error << '\n';
                            return 1; // An invalid fixture URL must not fall back to the producer's companion.
                        }
                        processor->apvts.getParameter("live_context_enabled")->setValueNotifyingHost(1.0f);
                        std::cout << "publisher instances=" << instanceCount << " insert=" << processor->getKennInsertId() << '\n';
                    }
                    processors.push_back(std::move(processor));
                }
                juce::AudioBuffer<float> audio(2, bufferSize);
                for (int sample = 0; sample < bufferSize; ++sample)
                    for (int channel = 0; channel < 2; ++channel)
                        audio.setSample(channel, sample, static_cast<float>(0.25 * std::sin(2.0 * juce::MathConstants<double>::pi * 997.0 * sample/rate)));
                juce::MidiBuffer midi;
                const double blockSeconds = bufferSize/rate;
                const double runSeconds = publishSeconds.isNotEmpty() ? sustainedSeconds : (publishEndpoint.isNotEmpty() ? 3.0 : 0.4); // 3 s short HTTP cells; 400 ms DSP-only cells.
                const int blocks = static_cast<int>(std::ceil(runSeconds/blockSeconds));
                std::vector<double> durations;
                durations.reserve(static_cast<size_t>(blocks*instanceCount));
                uint64_t warmRss = 0, warmHeap = 0, warmFootprint = 0, warmTimingBytes = 0;
                bool sampledWarmRss = false;
                const auto started = std::chrono::steady_clock::now();
                for (int block = 0; block < blocks; ++block)
                {
                    clock.sample = static_cast<juce::int64>(block) * bufferSize;
                    for (auto& processor : processors)
                    {
                        const auto before = juce::Time::getHighResolutionTicks();
                        processor->processBlock(audio, midi);
                        const auto us = juce::Time::highResolutionTicksToSeconds(juce::Time::getHighResolutionTicks()-before)*1e6;
                        if (block*blockSeconds >= 0.1) durations.push_back(us); // Exclude the first 100 ms from tail statistics.
                    }
                    std::this_thread::sleep_until(started + std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>((block+1)*blockSeconds)));
                    if (publishSeconds.isNotEmpty() && ! sampledWarmRss && block*blockSeconds >= 5.0)
                    {
                        sampledWarmRss = true; // Unsupported counters must not be retried on every subsequent callback.
                        warmRss = processPeakRssBytes(); // Five seconds warms the FFT/HTTP paths before measuring retained growth.
                        warmHeap = processLiveHeapBytes();
                        warmFootprint = processPhysicalFootprintBytes();
                        warmTimingBytes = durations.size() * sizeof(double);
                    }
                }
                std::sort(durations.begin(), durations.end());
                const auto average = std::accumulate(durations.begin(), durations.end(), 0.0)/static_cast<double>(durations.size());
                const auto p99 = durations[static_cast<size_t>(0.99*static_cast<double>(durations.size()-1))];
                const auto max = durations.back();
                double workerMs = 0.0, oldestMs = 0.0;
                uint64_t dropped = 0;
                bool allValid = true;
                for (auto& processor : processors)
                {
                    const auto frame = processor->analysisSnapshot();
                    workerMs += frame.workerMilliseconds; dropped += frame.droppedSamples;
                    allValid = allValid && frame.valid && frame.hostTimelineValid && frame.fastSpectrum.valid && frame.lowSpectrum.valid;
                    oldestMs = juce::jmax(oldestMs, 1000.0 * juce::Time::highResolutionTicksToSeconds(juce::Time::getHighResolutionTicks()-frame.capturedTicks));
                }
                const auto budgetPercent = average/(blockSeconds*1e6)*100.0;
                const auto rss = processPeakRssBytes();
                const auto rssGrowth = warmRss > 0 && rss > warmRss ? rss - warmRss : 0;
                const auto timingGrowth = durations.size()*sizeof(double) - warmTimingBytes;
                const auto heap = processLiveHeapBytes();
                const auto heapGrowth = warmHeap > 0 && heap > warmHeap ? heap - warmHeap : 0;
                const auto footprint = processPhysicalFootprintBytes();
                const auto footprintGrowth = warmFootprint > 0 && footprint > warmFootprint ? footprint - warmFootprint : 0;
                // The timing vector's full capacity is allocated before warm-up,
                // so only RSS grows as later callbacks touch its reserved pages.
                // Bound current private footprint instead of high-water RSS:
                // 8 MiB covers one <=1 MiB request's JSON/UTF-8/network copies,
                // but not one retained body per upload. Host RSS is a separate gate.
                const bool boundedMemory = warmFootprint == 0 || footprintGrowth <= timingGrowth + 8*1024*1024;
                // Average callback cost below 1% per insert and windows younger
                // than 250 ms are local gates. p99/max are evidence, not OS deadlines.
                const bool ok = budgetPercent < 1.0 && dropped == 0 && allValid && oldestMs < 250.0 && boundedMemory;
                passed = passed && ok;
                std::cout << "rate=" << rate << " buffer=" << bufferSize << " instances=" << instanceCount
                          << " callbacks=" << durations.size() << " avg=" << average << "us p99=" << p99 << "us max=" << max
                          << "us perInsertBudget=" << budgetPercent << "% workerElapsed=" << workerMs
                          << "ms age=" << oldestMs << "ms dropped=" << dropped
                          << " rssBytes=" << rss << " rssGrowthBytes=" << rssGrowth << " timingGrowthBytes=" << timingGrowth
                          << " liveHeapBytes=" << heap << " heapGrowthBytes=" << heapGrowth
                          << " footprintBytes=" << footprint << " footprintGrowthBytes=" << footprintGrowth
                          << " queueMiB=" << static_cast<double>(static_cast<size_t>(instanceCount)*KENNContinuousAnalysis::queueStorageBytes())/(1024.0*1024.0)
                          << " " << (ok ? "PASS" : "FAIL") << '\n';
            }
    return passed ? 0 : 1;
}
