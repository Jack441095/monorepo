#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "LocalCommandLanguage.h"
#include "LocalAbletonOscProbe.h"
#include "LocalLivePlan.h"
#include "LocalAbletonOscWriter.h"
#include <vector>

class KENNLiveContextPublisherThread final : public juce::Thread
{
public:
    static KENNLiveContextPublisherThread& instance() { static KENNLiveContextPublisherThread publisher; return publisher; }
    void add(KENNMixAssistantAudioProcessor& owner)
    {
        const juce::ScopedLock lifetime(lifetimeLock);
        {
            const juce::ScopedLock lock(registryLock);
            entries.push_back({ &owner });
        }
        if (! isThreadRunning()) startThread(juce::Thread::Priority::low);
    }
    void remove(KENNMixAssistantAudioProcessor& owner)
    {
        const juce::ScopedLock lifetime(lifetimeLock);
        bool empty;
        {
            const juce::ScopedLock lock(registryLock);
            entries.erase(std::remove_if(entries.begin(), entries.end(), [&owner](const Entry& entry) { return entry.owner == &owner; }), entries.end());
            empty = entries.empty();
        }
        // Finish the last request/autorelease pool while JUCE networking is
        // alive. Leaving a polling singleton until static teardown crashed
        // the 2026-10-13 active HTTP profile on macOS at thread pool cleanup.
        if (empty) stopThread(-1);
    }

    void run() override
    {
        constexpr int intervalMs = 500; // At most two feature-only batches per second for up to 64 inserts on one companion.
        while (! threadShouldExit())
        {
            // A false return means the timed wait expired, which is the
            // normal publishing tick.  A stop signal also wakes the wait;
            // check the exit flag separately so the publisher keeps running
            // after each ordinary timeout.
            wait(intervalMs);
            if (threadShouldExit()) break;
            // JUCE's outer macOS autorelease pool lives until run() exits.
            // Keep all feature collection and HTTP temporaries within one tick;
            // the companion can remain connected for hours without retaining them.
            JUCE_AUTORELEASEPOOL
            {
                // The local companion shares this machine's wall clock. Anchor
                // ages before collection so serialization and stalled HTTP cannot
                // give already-exported audio a new diagnosis lifetime on receipt.
                const auto exportedAt = juce::Time::getCurrentTime().toMilliseconds() / 1000.0;
                std::vector<Batch> batches;
                {
                    const juce::ScopedLock lock(registryLock);
                    for (auto& entry : entries)
                    {
                        auto& owner = *entry.owner;
                        if (owner.apvts.getRawParameterValue("live_context_enabled")->load() < 0.5f)
                        {
                            entry.lastSequence = 0;
                            continue; // Re-enabling publication sends the latest frame once.
                        }
                        const auto frame = owner.analysisSnapshot();
                        const bool enabled = owner.apvts.getRawParameterValue("analysis_enabled")->load() >= 0.5f;
                        if (frame.sequence == 0 || (frame.sequence == entry.lastSequence && frame.generation == entry.lastGeneration
                            && frame.valid == entry.lastValid && enabled == entry.lastEnabled))
                            continue; // Stopped audio never consumes bandwidth or rejuvenates evidence.
                        entry.lastSequence = frame.sequence; entry.lastGeneration = frame.generation;
                        entry.lastValid = frame.valid; entry.lastEnabled = enabled;
                        const auto endpoint = owner.getKennEndpoint();
                        auto batch = std::find_if(batches.begin(), batches.end(), [&endpoint](const Batch& candidate) {
                            return candidate.endpoint == endpoint && candidate.frames.size() < 64; // Bounded frame count, matching the companion contract.
                        });
                        if (batch == batches.end()) { batches.push_back({ endpoint, {} }); batch = batches.end() - 1; }
                        batch->frames.add(owner.handoffPayload());
                    }
                }
                // Own the JSON before releasing the registry: destruction can now
                // remove an insert while HTTP waits, with no dangling processor access.
                for (const auto& batch : batches)
                {
                    auto payload = std::make_unique<juce::DynamicObject>();
                    payload->setProperty("schema", "kenn.plugin_handoff_batch.v1");
                    payload->setProperty("exported_at_epoch", exportedAt);
                    payload->setProperty("frames", batch.frames);
                    // Multiline indentation alone pushed the 64-insert profile
                    // over 1 MiB. Omit whitespace without rounding measured power
                    // or dropping the history needed to pair asynchronous inserts.
                    const auto body = juce::JSON::toString(juce::var(payload.release()),
                        juce::JSON::FormatOptions().withSpacing(juce::JSON::Spacing::none));
                    if (body.getNumBytesAsUTF8() > 1024 * 1024) continue; // The companion's 1 MiB limit also bounds native transport; oversized evidence expires.
                    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
                        .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0); // 1,200 ms local timeout, with no redirect to another destination.
                    auto response = juce::URL(batch.endpoint + "/api/plugin-handoff-batch").withPOSTData(body).createInputStream(options);
                    if (response == nullptr) continue; // A missing companion cannot delay playback; a newer window retries on the next tick.
                    juce::MemoryBlock acknowledgement;
                    response->readIntoMemoryBlock(acknowledgement, 64 * 1024); // 64 KiB acknowledgement cap; no response audio/body can grow native memory without bound.
                }
            }
        }
    }

private:
    struct Entry
    {
        KENNMixAssistantAudioProcessor* owner;
        uint64_t lastSequence = 0, lastGeneration = 0;
        bool lastValid = false, lastEnabled = false;
    };
    struct Batch { juce::String endpoint; juce::Array<juce::var> frames; };
    KENNLiveContextPublisherThread() : juce::Thread("KENN Live Context Publisher") {}
    ~KENNLiveContextPublisherThread() override { stopThread(-1); } // Owned payloads must finish before the shared transport disappears.
    juce::CriticalSection registryLock; // Lifetime and JSON collection only; never held during HTTP or from processBlock().
    juce::CriticalSection lifetimeLock; // Serialize final join/restart without holding the registry needed by run().
    std::vector<Entry> entries;
};

namespace
{
constexpr bool directLiveWritesEnabled()
{
#if KENN_ENABLE_DIRECT_LIVE_WRITES
    return true;
#else
    return false;
#endif
}

bool questionNeedsAbletonContext(const juce::String& question)
{
    const auto lowered = question.toLowerCase();
    for (const auto& cue : { "ableton", "live", "track", "channel", "device", "plugin", "plug-in",
                             "tempo", "bpm", "scene", "clip", "transport", "arrangement", "session",
                             "current set" })
        if (lowered.contains(cue)) return true;
    return false;
}

kenn::LocalLiveTopology localTopology(const kenn::AbletonOscTopologyResult& source)
{
    kenn::LocalLiveTopology topology;
    topology.connected = source.connected;
    topology.error = source.error.toStdString();
    topology.tracks.reserve(source.tracks.size());
    for (const auto& sourceTrack : source.tracks)
    {
        kenn::LocalLiveTrack track;
        track.index = sourceTrack.index;
        track.name = sourceTrack.name.toStdString();
        track.devices.reserve(sourceTrack.devices.size());
        for (const auto& sourceDevice : sourceTrack.devices)
            track.devices.push_back({ sourceDevice.index, sourceDevice.name.toStdString() });
        topology.tracks.push_back(std::move(track));
    }
    return topology;
}

kenn::LocalLiveParameterSnapshot localParameters(const kenn::AbletonOscParameterResult& source)
{
    kenn::LocalLiveParameterSnapshot snapshot;
    snapshot.connected = source.connected;
    snapshot.trackIndex = source.trackIndex;
    snapshot.deviceIndex = source.deviceIndex;
    snapshot.deviceName = source.deviceName.toStdString();
    snapshot.error = source.error.toStdString();
    snapshot.parameters.reserve(source.parameters.size());
    for (const auto& sourceParameter : source.parameters)
        snapshot.parameters.push_back({ sourceParameter.index, sourceParameter.name.toStdString(),
                                        static_cast<double>(sourceParameter.value),
                                        static_cast<double>(sourceParameter.minimum),
                                        static_cast<double>(sourceParameter.maximum), sourceParameter.hasValue });
    return snapshot;
}

juce::var localPlanProposal(const kenn::LocalLivePlan& plan)
{
    auto proposal = std::make_unique<juce::DynamicObject>();
    proposal->setProperty("schema", juce::String(plan.schema));
    proposal->setProperty("action", juce::String(plan.action));
    proposal->setProperty("local_only", true);
    proposal->setProperty("requires_confirmation", directLiveWritesEnabled()
        && plan.action == "set_device_parameter");
    proposal->setProperty("track_index", plan.trackIndex);
    proposal->setProperty("track_name", juce::String(plan.trackName));
    proposal->setProperty("device_name", juce::String(plan.deviceName));
    proposal->setProperty("device_index", plan.deviceIndex);
    proposal->setProperty("insertion_index", plan.insertionIndex);
    proposal->setProperty("before_device_fingerprint", juce::String(plan.beforeDeviceFingerprint));
    if (plan.hasParameterValue)
    {
        proposal->setProperty("parameter_name", juce::String(plan.parameterName));
        proposal->setProperty("parameter_index", plan.parameterIndex);
        proposal->setProperty("before", plan.beforeValue);
        proposal->setProperty("after", plan.afterValue);
        proposal->setProperty("min", plan.parameterMinimum);
        proposal->setProperty("max", plan.parameterMaximum);
        proposal->setProperty("unit", "dB");
        proposal->setProperty("relative", plan.relative);
    }

    auto toArray = [](const std::vector<kenn::LocalLiveDevice>& devices) {
        juce::Array<juce::var> values;
        for (const auto& device : devices)
        {
            auto item = std::make_unique<juce::DynamicObject>();
            item->setProperty("index", device.index);
            item->setProperty("name", juce::String(device.name));
            values.add(juce::var(item.release()));
        }
        return values;
    };
    proposal->setProperty("before_devices", juce::var(toArray(plan.beforeDevices)));
    proposal->setProperty("after_devices", juce::var(toArray(plan.afterDevices)));
    proposal->setProperty("reason", directLiveWritesEnabled() && plan.action == "set_device_parameter"
        ? "Developer direct C++ Live mode is enabled; confirm only on a disposable Live set."
        : "Read-only C++ plan; the KENN Companion is required before any Live change can be confirmed.");
    return juce::var(proposal.release());
}
}

KENNMixAssistantAudioProcessor::KENNMixAssistantAudioProcessor()
    : AudioProcessor(BusesProperties().withInput("Input", juce::AudioChannelSet::stereo(), true)
                                      .withOutput("Output", juce::AudioChannelSet::stereo(), true)),
      apvts(*this, nullptr, "PARAMS", createParameterLayout())
{
    // Start with separate conversation ownership. Producers may explicitly
    // share this persisted ID; the independent insert ID still owns audio.
    kennSessionId = "plugin-" + juce::Uuid().toString();
    KENNLiveContextPublisherThread::instance().add(*this);
}

KENNMixAssistantAudioProcessor::~KENNMixAssistantAudioProcessor()
{
    KENNLiveContextPublisherThread::instance().remove(*this);
}

juce::AudioProcessorValueTreeState::ParameterLayout KENNMixAssistantAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> parameters;
    parameters.push_back(std::make_unique<juce::AudioParameterBool>("analysis_enabled", "Analysis Enabled", true));
    parameters.push_back(std::make_unique<juce::AudioParameterBool>("live_context_enabled", "Live KENN Context", false));
    parameters.push_back(std::make_unique<juce::AudioParameterChoice>("assistant_mode", "Assistant Mode", juce::StringArray { "Ask", "Suggest", "Assist", "Auto" }, 1));
    parameters.push_back(std::make_unique<juce::AudioParameterFloat>(juce::ParameterID("target_lufs", 1), "Target LUFS", juce::NormalisableRange<float>(-24.0f, -6.0f, 0.1f), -14.0f));
    return { parameters.begin(), parameters.end() };
}

juce::String KENNMixAssistantAudioProcessor::getAssistantMode() const
{
    const auto index = juce::jlimit(0, 3, juce::roundToInt(apvts.getRawParameterValue("assistant_mode")->load()));
    return juce::StringArray { "ask", "suggest", "assist", "auto" }[index];
}

void KENNMixAssistantAudioProcessor::prepareToPlay(double sampleRate, int)
{
    continuousAnalysis.prepare(sampleRate);
}

bool KENNMixAssistantAudioProcessor::isBusesLayoutSupported(const BusesLayout& layouts) const
{
    const auto input = layouts.getMainInputChannelSet();
    const auto output = layouts.getMainOutputChannelSet();
    return input == output && (input == juce::AudioChannelSet::mono()
        || input == juce::AudioChannelSet::stereo());
}

void KENNMixAssistantAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    KENNHostPosition host;
    // JUCE reports the start of this block, only from processBlock. Missing
    // sample time or a stopped transport cannot align separate inserts.
    if (auto* playHead = getPlayHead())
        if (const auto position = playHead->getPosition())
            if (const auto samples = position->getTimeInSamples(); samples && position->getIsPlaying())
                host = { *samples, true };
    continuousAnalysis.push(buffer, apvts.getRawParameterValue("analysis_enabled")->load() >= 0.5f, host);
    // Intentional transparent pass-through.  AutoMix rendering is offline and
    // stem-based, therefore no processing is silently applied to this bus.
}

void KENNMixAssistantAudioProcessor::updateTrackProperties(const TrackProperties& properties)
{
    const juce::ScopedLock lock(hostTrackLock);
    // A host may omit or stop reporting the name. An empty name clears the
    // previous association so another track cannot inherit its measurements.
    const auto name = properties.name.trim();
    if (name != hostTrackName)
        continuousAnalysis.invalidate(); // Require a new complete window before binding a changed host name.
    hostTrackName = name;
}

juce::String KENNMixAssistantAudioProcessor::getHostTrackName() const
{
    const juce::ScopedLock lock(hostTrackLock);
    return hostTrackName;
}

juce::var KENNMixAssistantAudioProcessor::handoffPayload() const
{
    const juce::ScopedLock sourceLock(hostTrackLock);
    // Ask, file export and single uploads can wait independently of the shared
    // publisher. Their audio ages must also include collection/transport delay.
    const auto exportedAt = juce::Time::getCurrentTime().toMilliseconds() / 1000.0;
    // Rename and publication generations are checked together; all scalar
    // metrics and bands below come from one worker publication.
    const auto frame = continuousAnalysis.snapshot();
    const auto& features = frame.features;
    const KENNMeterSnapshot data { features.peakDbfs, features.rmsDbfs, features.correlation,
        features.stereoWidth, features.crestDb, features.transientRatio, features.clippedSamples,
        features.sampleRate, features.analysedSamples };
    auto message = std::make_unique<juce::DynamicObject>();
    message->setProperty("schema", "kenn.plugin_handoff.v1");
    message->setProperty("exported_at_epoch", exportedAt);
    message->setProperty("audio_feature_schema", "audio_feature_frame.v1");
    message->setProperty("kind", "mix_review_snapshot");
    message->setProperty("plugin", "KENN Mix Assistant");
    message->setProperty("assistant_mode", getAssistantMode());
    message->setProperty("session_id", getKennInsertId());
    message->setProperty("conversation_id", getKennSessionId());
    message->setProperty("host_track_name", hostTrackName);
    const auto lastTicks = frame.capturedTicks;
    if (lastTicks > 0)
        message->setProperty("audio_age_seconds", juce::jmax(0.0, juce::Time::highResolutionTicksToSeconds(
            juce::Time::getHighResolutionTicks() - lastTicks)));
    const auto encodeWindow = [](const KENNAnalysisSnapshot& captured) -> juce::var
    {
        auto window = std::make_unique<juce::DynamicObject>();
        window->setProperty("schema", "kenn.continuous_window.v1");
        window->setProperty("valid", captured.valid);
        if (captured.inputChannels > 0)
        {
            window->setProperty("input_channels", captured.inputChannels);
            window->setProperty("correlation_valid", captured.correlationValid);
        } // Before the first complete window, omit both fields rather than publish half a metadata pair.
        window->setProperty("sequence", static_cast<juce::int64>(captured.sequence));
        window->setProperty("source_generation", static_cast<juce::int64>(captured.generation));
        window->setProperty("start_sample", captured.firstSample); window->setProperty("end_sample", captured.endSample);
        window->setProperty("duration_seconds", captured.windowSeconds);
        window->setProperty("dropped_samples", static_cast<juce::int64>(captured.droppedSamples));
        window->setProperty("invalid_samples", static_cast<juce::int64>(captured.invalidSamples));
        auto timeline = std::make_unique<juce::DynamicObject>();
        timeline->setProperty("schema", "kenn.host_timeline.v1");
        timeline->setProperty("valid", captured.valid && captured.hostTimelineValid);
        timeline->setProperty("transport_epoch", static_cast<juce::int64>(captured.transportEpoch));
        timeline->setProperty("start_sample", captured.hostTimelineValid ? juce::var(captured.hostFirstSample) : juce::var());
        timeline->setProperty("end_sample", captured.hostTimelineValid ? juce::var(captured.hostEndSample) : juce::var());
        window->setProperty("host_timeline", juce::var(timeline.release()));
        return juce::var(window.release());
    };
    message->setProperty("measurement_window", encodeWindow(frame));
    auto fftSpectra = std::make_unique<juce::DynamicObject>();
    fftSpectra->setProperty("schema", "kenn.fft_spectra.v1");
    const auto encodeFFT = [](const KENNFFTSnapshot& fft, const KENNAnalysisSnapshot& captured) -> juce::var
    {
        if (! captured.valid || ! fft.valid) return {}; // Gaps and warm-up cannot publish a completed spectrum.
        auto fftData = std::make_unique<juce::DynamicObject>();
        fftData->setProperty("size_samples", fft.size);
        fftData->setProperty("start_sample", static_cast<juce::int64>(fft.firstSample));
        fftData->setProperty("end_sample", static_cast<juce::int64>(fft.endSample));
        fftData->setProperty("bin_hz", captured.features.sampleRate / fft.size);
        fftData->setProperty("mean_square", fft.meanSquare); fftData->setProperty("peak_hz", fft.peakHz);
        juce::Array<juce::var> energy;
        for (const auto value : fft.energy) energy.add(value);
        fftData->setProperty("band_power", energy); // 32 fixed log groups, 20 Hz–20 kHz; stereo mean-square power.
        return juce::var(fftData.release());
    };
    fftSpectra->setProperty("fast", encodeFFT(frame.fastSpectrum, frame));
    fftSpectra->setProperty("low", encodeFFT(frame.lowSpectrum, frame));
    message->setProperty("fft_spectra", juce::var(fftSpectra.release()));
    juce::Array<juce::var> pairedWindows;
    if (frame.valid)
        for (const auto& captured : continuousAnalysis.recentSnapshots())
        {
            if (! captured.valid || ! captured.hostTimelineValid || captured.generation != frame.generation
                || captured.transportEpoch != frame.transportEpoch || captured.endSample > frame.endSample) continue; // Retired or newer windows cannot belong to this handoff.
            auto entry = std::make_unique<juce::DynamicObject>();
            entry->setProperty("measurement_window", encodeWindow(captured));
            auto spectra = std::make_unique<juce::DynamicObject>();
            spectra->setProperty("schema", "kenn.fft_spectra.v1");
            spectra->setProperty("low", encodeFFT(captured.lowSpectrum, captured));
            entry->setProperty("fft_spectra", juce::var(spectra.release()));
            entry->setProperty("peak_dbfs", captured.features.peakDbfs); entry->setProperty("rms_dbfs", captured.features.rmsDbfs);
            entry->setProperty("stereo_correlation", captured.features.correlation); entry->setProperty("stereo_width", captured.features.stereoWidth);
            entry->setProperty("input_channels", captured.inputChannels); entry->setProperty("correlation_valid", captured.correlationValid);
            entry->setProperty("analysed_samples", captured.features.analysedSamples);
            entry->setProperty("audio_age_seconds", juce::jmax(0.0, juce::Time::highResolutionTicksToSeconds(juce::Time::getHighResolutionTicks()-captured.capturedTicks)));
            pairedWindows.add(juce::var(entry.release()));
        }
    message->setProperty("paired_windows", pairedWindows); // Six feature windows bridge the 500 ms publisher phase offset.
    message->setProperty("target_lufs", apvts.getRawParameterValue("target_lufs")->load());
    auto pluginState = std::make_unique<juce::DynamicObject>();
    pluginState->setProperty("assistant_mode", getAssistantMode());
    pluginState->setProperty("target_lufs", apvts.getRawParameterValue("target_lufs")->load());
    pluginState->setProperty("analysis_enabled", apvts.getRawParameterValue("analysis_enabled")->load() >= 0.5f);
    pluginState->setProperty("live_context_enabled", apvts.getRawParameterValue("live_context_enabled")->load() >= 0.5f);
    message->setProperty("plugin_state", juce::var(pluginState.release()));
    message->setProperty("peak_dbfs", data.peakDb); message->setProperty("rms_dbfs", data.rmsDb);
    message->setProperty("stereo_correlation", data.correlation); message->setProperty("stereo_width", data.stereoWidth);
    // Unknown layout omits the pair; a lone validity flag would fail the wire contract.
    if (frame.inputChannels > 0)
    {
        message->setProperty("input_channels", frame.inputChannels);
        message->setProperty("correlation_valid", frame.correlationValid);
    }
    message->setProperty("sample_rate", data.sampleRate); message->setProperty("analysed_samples", data.analysedSamples);
    message->setProperty("low_energy", features.lowEnergy); message->setProperty("mid_energy", features.midEnergy); message->setProperty("high_energy", features.highEnergy);
    message->setProperty("crest_db", features.crestDb); message->setProperty("transient_ratio", features.transientRatio); message->setProperty("clipped_samples", features.clippedSamples);
    // Sample peak and window RMS cannot stand in for oversampled true peak
    // or gated, K-weighted LUFS. Keep their actual units in the handoff.

    // Keep a compact, language-neutral evidence packet alongside the
    // backwards-compatible plugin handoff fields.  The audio callback never
    // constructs this object; handoffPayload() runs on the handoff/network
    // side, so this remains outside the realtime path.  Offline Mix Review
    // emits the same kenn.evidence.v1 shape from local_engine.py.
    auto evidence = std::make_unique<juce::DynamicObject>();
    evidence->setProperty("schema", "kenn.evidence.v1");
    evidence->setProperty("source", "plugin_bus_snapshot");
    evidence->setProperty("captured_at_age_seconds", lastTicks > 0 ? message->getProperty("audio_age_seconds") : juce::var());
    evidence->setProperty("observed_at_epoch", juce::var());
    juce::Array<juce::var> evidenceFacts;
    const auto addEvidenceFact = [&evidenceFacts](const char* name, const juce::var& value, const char* unit)
    {
        auto fact = std::make_unique<juce::DynamicObject>();
        fact->setProperty("name", name);
        fact->setProperty("value", value);
        fact->setProperty("unit", unit);
        fact->setProperty("source", "plugin_bus_snapshot");
        fact->setProperty("confidence", "measured");
        evidenceFacts.add(juce::var(fact.release()));
    };
    addEvidenceFact("peak_dbfs", data.peakDb, "dBFS");
    addEvidenceFact("rms_dbfs", data.rmsDb, "dBFS");
    addEvidenceFact("stereo_correlation", data.correlation, "correlation");
    addEvidenceFact("stereo_width", data.stereoWidth, "ratio");
    addEvidenceFact("sample_rate", data.sampleRate, "Hz");
    addEvidenceFact("analysed_samples", data.analysedSamples, "samples");
    addEvidenceFact("low_energy", features.lowEnergy, "linear energy");
    addEvidenceFact("mid_energy", features.midEnergy, "linear energy");
    addEvidenceFact("high_energy", features.highEnergy, "linear energy");
    addEvidenceFact("crest_db", features.crestDb, "dB");
    addEvidenceFact("transient_ratio", features.transientRatio, "ratio");
    addEvidenceFact("clipped_samples", features.clippedSamples, "samples");
    evidence->setProperty("facts", juce::var(std::move(evidenceFacts)));
    juce::Array<juce::var> evidenceLimitations;
    evidenceLimitations.add("Bus snapshot only; no track, source, routing, plug-in, automation, or clip-content analysis.");
    evidenceLimitations.add("Low/mid/high values are broad relative energy estimates, not a calibrated spectrum, LUFS, or true-peak measurement.");
    evidenceLimitations.add("A snapshot cannot establish the audible cause of a mix symptom by itself.");
    evidence->setProperty("limitations", juce::var(std::move(evidenceLimitations)));
    message->setProperty("evidence", juce::var(evidence.release()));

    const auto& spectrum = frame.spectrum;
    juce::Array<juce::var> spectrumBands;
    const auto nyquist = data.sampleRate * 0.5;
    for (size_t index = 0; index < AudioTooRealtimeSpectrumBandCount; ++index)
    {
        if (spectrum.bands[index].highHz >= nyquist)
            continue;
        auto band = std::make_unique<juce::DynamicObject>();
        band->setProperty("center_hz", spectrum.bands[index].centerHz);
        band->setProperty("low_hz", spectrum.bands[index].lowHz);
        band->setProperty("high_hz", spectrum.bands[index].highHz);
        band->setProperty("energy", spectrum.energy[index]);
        spectrumBands.add(juce::var(band.release()));
    }
    message->setProperty("spectrum_schema", "realtime_spectrum.v1");
    message->setProperty("spectrum_bands", juce::var(std::move(spectrumBands)));
    message->setProperty("limitations", "Bus metrics only. No stems, DAW track layout, plugins, or automation were captured.");
    return juce::var(message.release());
}

bool KENNMixAssistantAudioProcessor::validateLocalEndpoint(const juce::String& endpoint, juce::String& normalised, juce::String& error)
{
    normalised = endpoint.trim().trimCharactersAtEnd("/");
    if (! (normalised.startsWithIgnoreCase("http://127.0.0.1:")
        || normalised.startsWithIgnoreCase("http://localhost:")))
    {
        error = "KENN Companion must use http://127.0.0.1:<port> or http://localhost:<port>.";
        return false;
    }
    const auto portText = normalised.fromLastOccurrenceOf(":", false, false);
    if (portText.isEmpty() || ! portText.containsOnly("0123456789") || ! juce::isPositiveAndBelow(portText.getIntValue(), 65536))
    {
        error = "KENN Companion needs a valid local port.";
        return false;
    }
    return true;
}

juce::String KENNMixAssistantAudioProcessor::getKennEndpoint() const
{
    const juce::ScopedLock lock(connectionLock);
    return kennEndpoint;
}

juce::String KENNMixAssistantAudioProcessor::getKennSessionId() const
{
    const juce::ScopedLock lock(connectionLock);
    return kennSessionId;
}

bool KENNMixAssistantAudioProcessor::setKennConnection(const juce::String& endpoint, const juce::String& sessionId, juce::String& error)
{
    juce::String normalised;
    if (! validateLocalEndpoint(endpoint, normalised, error)) return false;
    const auto cleanSession = sessionId.trim().substring(0, 128);
    if (cleanSession.isEmpty()) { error = "Session ID cannot be empty."; return false; }
    const juce::ScopedLock lock(connectionLock);
    kennEndpoint = normalised;
    kennSessionId = cleanSession;
    return true;
}

void KENNMixAssistantAudioProcessor::recordTargetAction(const juce::String& event, float before, float after, const juce::String& reason)
{
    const juce::ScopedLock lock(actionLogLock);
    targetActionLog.add({ juce::Time::getCurrentTime().toISO8601(true), event, reason.substring(0, 512), before, after });
    while (targetActionLog.size() > 50) targetActionLog.remove(0);
}

juce::String KENNMixAssistantAudioProcessor::latestTargetActionSummary() const
{
    const juce::ScopedLock lock(actionLogLock);
    if (targetActionLog.isEmpty()) return "No KENN target actions recorded in this project.";
    const auto& entry = targetActionLog.getReference(targetActionLog.size() - 1);
    return "Last target action: " + entry.event + " " + juce::String(entry.before, 1) + " -> " + juce::String(entry.after, 1) + " LUFS at " + entry.timestamp;
}

bool KENNMixAssistantAudioProcessor::writeHandoffFile(juce::String& error) const
{
    const auto folder = juce::File::getSpecialLocation(juce::File::userApplicationDataDirectory).getChildFile("AudioToo/KENN/handoffs");
    if (! folder.createDirectory()) { error = "Could not create the KENN handoff folder."; return false; }
    const auto file = folder.getChildFile("kenn-mix-review-handoff.json");
    if (! file.replaceWithText(juce::JSON::toString(handoffPayload(), true))) { error = "Could not write the KENN handoff file."; return false; }
    error = file.getFullPathName(); return true;
}

bool KENNMixAssistantAudioProcessor::sendHandoffToKenn(juce::String& result) const
{
    const auto body = juce::JSON::toString(handoffPayload(), false);
    const auto url = juce::URL(getKennEndpoint() + "/api/plugin-handoff").withPOSTData(body);
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN is not running locally; saving a handoff file instead."; return false; }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    if (auto* object = parsed.getDynamicObject(); object != nullptr && object->getProperty("ok"))
    {
        if (const auto* observations = object->getProperty("observations").getArray(); observations != nullptr && ! observations->isEmpty())
            if (auto* observation = observations->getFirst().getDynamicObject(); observation != nullptr)
            {
                result = "KENN Mix Review: " + observation->getProperty("title").toString();
                const auto detail = observation->getProperty("detail").toString();
                if (detail.isNotEmpty()) result += " - " + detail;
                return true;
            }
        result = "Mix Review sent to KENN.";
        return true;
    }
    result = "KENN rejected the handoff."; return false;
}

juce::String KENNMixAssistantAudioProcessor::localDiagnosticSummary() const
{
    const auto frame = continuousAnalysis.snapshot();
    const auto& f = frame.features;
    const KENNMeterSnapshot data { f.peakDbfs, f.rmsDbfs, f.correlation, f.stereoWidth,
        f.crestDb, f.transientRatio, f.clippedSamples, f.sampleRate, f.analysedSamples };
    juce::StringArray lines;
    lines.add("Local KENN Mix Check (no companion required)");
    lines.add("Measured from the current plug-in bus; audio is not sent anywhere.");
    const auto ageSeconds = juce::Time::highResolutionTicksToSeconds(juce::Time::getHighResolutionTicks()-frame.capturedTicks);
    if (! frame.valid || data.analysedSamples <= 0 || ageSeconds > 1.0
        || apvts.getRawParameterValue("analysis_enabled")->load() < 0.5f) // 1 second matches continuous companion diagnosis.
    {
        // Gaps, disabled analysis and stopped playback cannot justify current local advice.
        lines.add("No current complete audio window. Play audio through this bus with analysis enabled, then run the check again.");
        lines.add("Available locally: peak, RMS, correlation, width, crest, transient, and clipping meters.");
        return lines.joinIntoString("\n");
    }

    lines.add("Samples: " + juce::String(data.analysedSamples) + " at " + juce::String(data.sampleRate, 0) + " Hz");
    lines.add("Peak " + juce::String(data.peakDb, 1) + " dBFS | RMS " + juce::String(data.rmsDb, 1)
        + " dBFS | Correlation " + juce::String(data.correlation, 2)
        + " | Width " + juce::String(data.stereoWidth, 2));
    lines.add("Crest " + juce::String(data.crestDb, 1) + " dB | Transient "
        + juce::String(data.transientRatio, 2) + " | Near-full-scale frames in latest 100 ms window "
        + juce::String(data.clippedSamples));

    bool finding = false;
    if (data.clippedSamples > 0)
    {
        lines.add("Finding: sample frames reached |sample| >= 0.999 in the latest 100 ms window; check upstream gain.");
        finding = true;
    }
    if (data.peakDb > -1.0f)
    {
        lines.add("Finding: sample headroom is below 1 dB; audition upstream gain reduction before judging overload.");
        finding = true;
    }
    if (data.correlation < -0.5f)
    {
        lines.add("Finding: strong negative stereo correlation suggests a polarity or mono-compatibility check.");
        finding = true;
    }
    if (data.rmsDb <= -60.0f)
    {
        lines.add("Finding: the current bus is effectively silent.");
        finding = true;
    }
    if (! finding) lines.add("No local threshold finding was detected in the current meter state.");
    lines.add("Offline limits: this check does not provide chat/RAG, calibrated LUFS/LRA, true peak, full-file FFT review, Live proposals, or AutoMix.");
    return lines.joinIntoString("\n");
}

bool KENNMixAssistantAudioProcessor::askKenn(const juce::String& question, juce::String& result) const
{
    const auto cleanQuestion = question.trim();
    if (cleanQuestion.isEmpty()) { result = "Type a question for KENN first."; return false; }
    if (cleanQuestion.length() > 4000) { result = "Keep the KENN question under 4,000 characters."; return false; }
    auto payload = std::make_unique<juce::DynamicObject>();
    payload->setProperty("question", cleanQuestion);
    payload->setProperty("session_id", getKennSessionId());
    payload->setProperty("plugin_session_id", getKennInsertId());
    // An explicit analysis question opts into a compact feature snapshot.
    // The chat worker builds it here; no audio or network work reaches the callback.
    const auto lowered = cleanQuestion.toLowerCase();
    if (lowered.contains("analys") || lowered.contains("analyz")
        || lowered.contains("masking") || lowered.contains("overlap") || lowered.contains("sidechain")
        || lowered.startsWith("bind this insert to ")
        || lowered.contains("what should i change"))
        payload->setProperty("plugin_handoff", handoffPayload());
    // Asking KENN is an explicit user action. Include the latest cached Live
    // session structure for questions that actually refer to the current set;
    // generic mix-engineering questions stay on the fast retrieval path and
    // do not wait for unnecessary DAW context. The server still treats this
    // as read-only evidence and keeps mutations on the Control Live path.
    payload->setProperty("include_ableton_context", questionNeedsAbletonContext(cleanQuestion));
    const auto url = juce::URL(getKennEndpoint() + "/api/ask").withPOSTData(juce::JSON::toString(juce::var(payload.release()), false));
    int httpStatus = 0;
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr)
    {
        // A slow optional model can outlive the chat request timeout while
        // the companion itself remains healthy. Check the cheap health route
        // before reporting the much more serious "not running" state.
        int healthStatus = 0;
        const auto healthOptions = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
            .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0).withStatusCode(&healthStatus);
        const auto healthResponse = juce::URL(getKennEndpoint() + "/api/health").createInputStream(healthOptions);
        result = healthResponse != nullptr
            ? "KENN Companion is running, but chat timed out. Try again or disable the optional local model; Local Mix Check remains available."
            : "KENN Companion is not running locally. Local Mix Check remains available.";
        return false;
    }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    auto* object = parsed.getDynamicObject();
    if (httpStatus == 200 && object != nullptr)
    {
        const auto answer = object->getProperty("answer").toString().trim();
        if (answer.isNotEmpty()) { result = answer; return true; }
    }
    if (object != nullptr && object->hasProperty("error")) result = object->getProperty("error").toString();
    else result = "KENN could not answer the question (HTTP " + juce::String(httpStatus) + ").";
    return false;
}

bool KENNMixAssistantAudioProcessor::inspectLiveControls(juce::String& result) const
{
    int httpStatus = 0;
    const auto url = juce::URL(getKennEndpoint() + "/api/ableton/device-matrix?parameters=1");
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr)
    {
        // Keep read-only session visibility useful when the optional Python
        // companion is stopped. The direct C++ path is read-only: it can
        // inspect bounded device parameters, but it never creates a
        // confirmation token or sends a mutation.
        // The response-port ownership check in the probe also prevents this
        // fallback from competing with another KENN instance.
        const auto topology = kenn::readAbletonOscTopology();
        if (! topology.connected)
        {
            result = "KENN Companion is not running locally. No Live controls were read."
                + (topology.error.isNotEmpty() ? " " + topology.error : juce::String());
            return false;
        }

        juce::StringArray lines;
        lines.add("Live topology (read-only, direct AbletonOSC)");
        lines.add("KENN Companion is offline. Direct C++ inspection includes bounded device parameters; Live changes still require the companion.");
        constexpr int maxParameterDevices = 16;
        int parameterDevicesRead = 0;
        for (const auto& track : topology.tracks)
        {
            lines.add("\n" + juce::String(track.index + 1) + ". " + track.name);
            if (track.devices.empty())
            {
                lines.add("  No devices");
                continue;
            }
            for (const auto& device : track.devices)
            {
                lines.add("  " + juce::String(device.index + 1) + ". " + device.name);
                if (parameterDevicesRead >= maxParameterDevices)
                    continue;
                const auto parameters = kenn::readAbletonOscParameters("127.0.0.1", 11000, 11001,
                                                                        track.index, device.index, 300);
                ++parameterDevicesRead;
                if (! parameters.connected)
                {
                    lines.add("     Parameters unavailable: " + parameters.error);
                    continue;
                }
                for (const auto& parameter : parameters.parameters)
                {
                    const auto current = parameter.hasValue
                        ? juce::String(parameter.value, 3) : "unreadable";
                    lines.add("     " + parameter.name + " = " + current + " ["
                        + juce::String(parameter.minimum, 3) + " .. "
                        + juce::String(parameter.maximum, 3) + "]");
                }
            }
        }
        if (parameterDevicesRead >= maxParameterDevices)
            lines.add("\nParameter inspection capped at " + juce::String(maxParameterDevices) + " devices for responsiveness.");
        result = lines.joinIntoString("\n");
        return true;
    }

    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    auto* object = parsed.getDynamicObject();
    if (httpStatus != 200 || object == nullptr)
    {
        result = object != nullptr && object->getProperty("error").toString().isNotEmpty()
            ? object->getProperty("error").toString()
            : "KENN could not read the Live control matrix (HTTP " + juce::String(httpStatus) + ").";
        return false;
    }
    if (! static_cast<bool>(object->getProperty("connected")))
    {
        result = "AbletonOSC is offline. No Live controls were read.";
        return false;
    }

    juce::StringArray lines;
    lines.add("Live controls (read-only)");
    lines.add("Exact names and ranges from the current Ableton session. Nothing has changed.");
    const auto* entries = object->getProperty("entries").getArray();
    if (entries == nullptr || entries->isEmpty())
    {
        result = lines.joinIntoString("\n") + "\n\nNo readable devices were reported.";
        return true;
    }

    for (const auto& entryValue : *entries)
    {
        auto* entry = entryValue.getDynamicObject();
        if (entry == nullptr) continue;
        const auto track = entry->getProperty("track_name").toString();
        const auto device = entry->getProperty("device_name").toString();
        const auto qualification = entry->getProperty("qualification").toString();
        lines.add("\n" + track + " -> " + device + (qualification.isNotEmpty() ? " [" + qualification + "]" : ""));
        auto* probe = entry->getProperty("parameter_probe").getDynamicObject();
        const auto* parameters = probe != nullptr ? probe->getProperty("parameters").getArray() : nullptr;
        if (parameters == nullptr || parameters->isEmpty())
        {
            lines.add("  No readable parameters reported.");
            continue;
        }
        for (const auto& parameterValue : *parameters)
        {
            auto* parameter = parameterValue.getDynamicObject();
            if (parameter == nullptr) continue;
            const auto name = parameter->getProperty("name").toString();
            if (name.isEmpty()) continue;
            lines.add("  " + name + " [" + parameter->getProperty("min").toString()
                + " .. " + parameter->getProperty("max").toString() + "]");
        }
    }
    result = lines.joinIntoString("\n");
    return true;
}

bool KENNMixAssistantAudioProcessor::planLiveCommand(const juce::String& command, juce::var& proposal, juce::String& result) const
{
    const auto cleanCommand = command.trim();
    proposal = juce::var();
    if (cleanCommand.isEmpty()) { result = "Type a Live command first."; return false; }
    if (cleanCommand.length() > 4000) { result = "Keep the Live command under 4,000 characters."; return false; }
    auto payload = std::make_unique<juce::DynamicObject>();
    payload->setProperty("command", cleanCommand);
    payload->setProperty("session_id", getKennSessionId());
    // Live commands from the hosted plug-in use KENN's deterministic local
    // language path. The optional model remains available for separate chat
    // or offline research, but can never add tens of seconds to a control
    // request made inside Ableton.
    payload->setProperty("deterministic_only", true);
    // Keep the fast C++ language extraction visible to the companion as
    // observability/handoff metadata. The companion must still resolve the
    // target from a fresh Live snapshot and never trust this hint for writes.
    const auto localIntent = kenn::parseLocalCommand(cleanCommand.toStdString());
    auto localIntentObject = std::make_unique<juce::DynamicObject>();
    localIntentObject->setProperty("route", localIntent.recognized ? "cpp_deterministic" : "snapshot_fallback");
    localIntentObject->setProperty("action", juce::String(localIntent.action));
    localIntentObject->setProperty("track_number", localIntent.trackNumber);
    localIntentObject->setProperty("new_track_name", juce::String(localIntent.newTrackName));
    localIntentObject->setProperty("has_value", localIntent.hasValue);
    if (localIntent.hasValue) localIntentObject->setProperty("value", localIntent.value);
    localIntentObject->setProperty("unit", juce::String(localIntent.unit));
    localIntentObject->setProperty("device_name", juce::String(localIntent.deviceName));
    localIntentObject->setProperty("parameter_name", juce::String(localIntent.parameterName));
    localIntentObject->setProperty("relative", localIntent.relative);
    localIntentObject->setProperty("recipe", localIntent.recipe);
    localIntentObject->setProperty("canonical", juce::String(localIntent.canonical));
    if (! localIntent.clarification.empty())
        localIntentObject->setProperty("clarification", juce::String(localIntent.clarification));
    payload->setProperty("local_intent", juce::var(localIntentObject.release()));
    const auto url = juce::URL(getKennEndpoint() + "/api/ableton/command").withPOSTData(juce::JSON::toString(juce::var(payload.release()), false));
    int httpStatus = 0;
    // A real AbletonOSC snapshot reads the Live object model one property at
    // a time. This call runs on the plug-in worker thread, so allow the local
    // companion enough time to finish a bounded snapshot instead of reporting
    // a false "not running" error after the old 1.2 s transport timeout.
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr)
    {
        // If the optional companion is absent, keep the command useful as a
        // self-contained, read-only plan. The direct C++ path can inspect the
        // exact Live topology, but it deliberately cannot issue confirmation
        // tokens or mutations.
        const auto localTopologySnapshot = kenn::readAbletonOscTopology();
        const auto localLiveTopology = localTopology(localTopologySnapshot);
        kenn::LocalLivePlan localPlan;
        if (localIntent.action == "set_device_parameter")
        {
            localPlan.action = localIntent.action;
            if (! localLiveTopology.connected)
            {
                localPlan.clarification = localLiveTopology.error.empty()
                    ? "AbletonOSC returned no usable topology for the parameter target."
                    : localLiveTopology.error;
            }
            else if (localIntent.trackNumber <= 0 || localIntent.trackNumber > static_cast<int>(localLiveTopology.tracks.size()))
            {
                localPlan.clarification = "The requested numbered Live track is not present in the direct C++ snapshot.";
            }
            else
            {
                const auto& track = localLiveTopology.tracks[static_cast<std::size_t>(localIntent.trackNumber - 1)];
                const kenn::LocalLiveDevice* matchedDevice = nullptr;
                for (const auto& device : track.devices)
                {
                    if (! device.name.empty() && juce::String(device.name).equalsIgnoreCase(juce::String(localIntent.deviceName)))
                    {
                        if (matchedDevice != nullptr)
                        {
                            localPlan.clarification = "The target device name is duplicated; use the companion for exact device selection.";
                            break;
                        }
                        matchedDevice = &device;
                    }
                }
                if (localPlan.clarification.empty() && matchedDevice == nullptr)
                    localPlan.clarification = "The requested device is not present in the direct C++ snapshot.";
                if (localPlan.clarification.empty())
                {
                    const auto directParameters = kenn::readAbletonOscParameters("127.0.0.1", 11000, 11001,
                                                                                  track.index, matchedDevice->index, 500);
                    localPlan = kenn::makeLocalLiveParameterPlan(localIntent, localLiveTopology,
                                                                  localParameters(directParameters));
                }
            }
        }
        else
        {
            localPlan = kenn::makeLocalLivePlan(localIntent, localLiveTopology);
        }
        if (localPlan.ready)
        {
            proposal = localPlanProposal(localPlan);
            result = "Read-only C++ plan ready for " + juce::String(localPlan.trackName)
                + " -> " + juce::String(localPlan.deviceName) + ". "
                "The KENN Companion is required to confirm and apply it; nothing has changed.";
            return true;
        }

        int healthStatus = 0;
        const auto healthOptions = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
            .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0).withStatusCode(&healthStatus);
        const auto healthResponse = juce::URL(getKennEndpoint() + "/api/health").createInputStream(healthOptions);
        result = healthResponse != nullptr
            ? "KENN Companion is running, but the Live command timed out while waiting for AbletonOSC. No change was made."
            : "KENN Companion is not running locally. "
                + (! localPlan.clarification.empty()
                    ? "Read-only C++ plan unavailable: " + juce::String(localPlan.clarification)
                    : "Local Mix Check remains available.");
        return false;
    }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    auto* object = parsed.getDynamicObject();
    if (object == nullptr)
    {
        result = "KENN returned an unreadable Live command response.";
        return false;
    }
    result = object->getProperty("answer").toString().trim();
    if (result.isEmpty()) result = object->getProperty("error").toString().trim();
    if (auto candidate = object->getProperty("proposal"); candidate.isObject())
    {
        if (auto* candidateObject = candidate.getDynamicObject())
            candidateObject->setProperty("lifecycle", object->getProperty("lifecycle"));
        proposal = candidate;
    }
    if (httpStatus == 200 && result.isNotEmpty()) return true;
    if (result.isEmpty()) result = "KENN could not plan the Live command (HTTP " + juce::String(httpStatus) + ").";
    return false;
}

bool KENNMixAssistantAudioProcessor::confirmLiveCommand(const juce::var& proposal, juce::String& result) const
{
    juce::var receipt;
    return confirmLiveCommand(proposal, receipt, result);
}

bool KENNMixAssistantAudioProcessor::confirmLiveCommand(const juce::var& proposal, juce::var& receipt, juce::String& result) const
{
    receipt = juce::var();
    auto* proposalObject = proposal.getDynamicObject();
    if (proposalObject == nullptr) { result = "No valid Live proposal is waiting for confirmation."; return false; }

    if (static_cast<bool>(proposalObject->getProperty("local_only")))
    {
#if KENN_ENABLE_DIRECT_LIVE_WRITES
        if (!static_cast<bool>(proposalObject->getProperty("requires_confirmation")))
        {
            result = "This local C++ plan is read-only and cannot be confirmed.";
            return false;
        }
        if (proposalObject->getProperty("action").toString() != "set_device_parameter")
        {
            result = "Direct C++ confirmation is currently limited to device-parameter changes.";
            return false;
        }
        const auto mutation = kenn::setAbletonOscParameterWithReadback(
            "127.0.0.1", 11000, 11001,
            proposalObject->getProperty("track_index").toString().getIntValue(),
            proposalObject->getProperty("device_index").toString().getIntValue(),
            proposalObject->getProperty("parameter_index").toString().getIntValue(),
            proposalObject->getProperty("device_name").toString(),
            proposalObject->getProperty("parameter_name").toString(),
            proposalObject->getProperty("before").toString().getDoubleValue(),
            proposalObject->getProperty("after").toString().getDoubleValue());
        if (!mutation.verified)
        {
            result = mutation.error.isNotEmpty() ? mutation.error : "Direct C++ Live change failed readback verification.";
            return false;
        }
        auto localReceipt = std::make_unique<juce::DynamicObject>();
        localReceipt->setProperty("schema", "kenn.ableton_local_parameter_receipt.v1");
        localReceipt->setProperty("local_only", true);
        localReceipt->setProperty("verified", true);
        localReceipt->setProperty("action", "set_device_parameter");
        localReceipt->setProperty("receipt_id", "local-receipt-" + juce::Uuid().toString());
        localReceipt->setProperty("track_index", proposalObject->getProperty("track_index"));
        localReceipt->setProperty("track_name", proposalObject->getProperty("track_name"));
        localReceipt->setProperty("device_index", proposalObject->getProperty("device_index"));
        localReceipt->setProperty("device_name", proposalObject->getProperty("device_name"));
        localReceipt->setProperty("parameter_index", proposalObject->getProperty("parameter_index"));
        localReceipt->setProperty("parameter_name", proposalObject->getProperty("parameter_name"));
        localReceipt->setProperty("before", mutation.beforeValue);
        localReceipt->setProperty("after", mutation.afterValue);
        localReceipt->setProperty("min", proposalObject->getProperty("min"));
        localReceipt->setProperty("max", proposalObject->getProperty("max"));
        receipt = juce::var(localReceipt.release());
        result = "Direct C++ Live change applied and verified by readback.";
        return true;
#else
        result = "Direct C++ Live writes are disabled in this build; the plan is read-only.";
        return false;
#endif
    }

    const auto token = proposalObject->getProperty("confirmation_token").toString();
    const auto idempotency = proposalObject->getProperty("action_id").toString().isNotEmpty()
        ? proposalObject->getProperty("action_id").toString()
        : proposalObject->getProperty("id").toString();
    if (token.isEmpty() || idempotency.isEmpty()) { result = "The Live proposal is missing its confirmation binding."; return false; }
    auto payload = std::make_unique<juce::DynamicObject>();
    payload->setProperty("command", "confirm");
    payload->setProperty("session_id", getKennSessionId());
    payload->setProperty("proposal", proposal);
    payload->setProperty("confirm_token", token);
    payload->setProperty("idempotency_key", idempotency);
    const auto url = juce::URL(getKennEndpoint() + "/api/ableton/command").withPOSTData(juce::JSON::toString(juce::var(payload.release()), false));
    int httpStatus = 0;
    // Confirmation performs a fresh-state check, the write, and a readback;
    // it must use the same real-Live budget as planning rather than timing out
    // while KENN is still enforcing its safety pipeline.
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN Companion is not running locally. Nothing was changed."; return false; }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    if (auto* object = parsed.getDynamicObject(); object != nullptr)
    {
        result = object->getProperty("answer").toString().trim();
        if (result.isEmpty()) result = object->getProperty("error").toString().trim();
        if (auto candidate = object->getProperty("receipt"); candidate.isObject())
        {
            if (auto* candidateObject = candidate.getDynamicObject())
                candidateObject->setProperty("lifecycle", object->getProperty("lifecycle"));
            receipt = candidate;
        }
    }
    if (result.isEmpty()) result = "KENN could not confirm the Live command (HTTP " + juce::String(httpStatus) + ").";
    return httpStatus == 200;
}

bool KENNMixAssistantAudioProcessor::planLiveUndo(const juce::var& receipt, juce::var& proposal, juce::String& result) const
{
    proposal = juce::var();
    auto* receiptObject = receipt.getDynamicObject();
    if (receiptObject == nullptr) { result = "No verified Live receipt is available to undo."; return false; }

    if (static_cast<bool>(receiptObject->getProperty("local_only")))
    {
#if KENN_ENABLE_DIRECT_LIVE_WRITES
        if (receiptObject->getProperty("schema").toString() != "kenn.ableton_local_parameter_receipt.v1"
            || !static_cast<bool>(receiptObject->getProperty("verified", false)))
        {
            result = "The local C++ receipt is not eligible for identity-bound undo.";
            return false;
        }
        auto inverse = std::make_unique<juce::DynamicObject>();
        inverse->setProperty("schema", "kenn.ableton_local_plan.v1");
        inverse->setProperty("local_only", true);
        inverse->setProperty("requires_confirmation", true);
        inverse->setProperty("action", "set_device_parameter");
        inverse->setProperty("track_index", receiptObject->getProperty("track_index"));
        inverse->setProperty("track_name", receiptObject->getProperty("track_name"));
        inverse->setProperty("device_index", receiptObject->getProperty("device_index"));
        inverse->setProperty("device_name", receiptObject->getProperty("device_name"));
        inverse->setProperty("parameter_index", receiptObject->getProperty("parameter_index"));
        inverse->setProperty("parameter_name", receiptObject->getProperty("parameter_name"));
        inverse->setProperty("before", receiptObject->getProperty("after"));
        inverse->setProperty("after", receiptObject->getProperty("before"));
        inverse->setProperty("min", receiptObject->getProperty("min"));
        inverse->setProperty("max", receiptObject->getProperty("max"));
        inverse->setProperty("unit", "dB");
        inverse->setProperty("reason", "Restore the prior verified direct C++ Live parameter value.");
        proposal = juce::var(inverse.release());
        result = "Read-only direct C++ undo plan ready. Confirm to restore the prior value.";
        return true;
#else
        result = "Direct C++ Live undo is disabled in this build.";
        return false;
#endif
    }

    auto payload = std::make_unique<juce::DynamicObject>();
    payload->setProperty("session_id", getKennSessionId());
    payload->setProperty("receipt", receipt);
    const auto url = juce::URL(getKennEndpoint() + "/api/ableton/osc/undo").withPOSTData(juce::JSON::toString(juce::var(payload.release()), false));
    int httpStatus = 0;
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN Companion is not running locally. Nothing was changed."; return false; }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    if (auto* object = parsed.getDynamicObject(); object != nullptr)
    {
        if (auto candidate = object->getProperty("proposal"); candidate.isObject()) proposal = candidate;
        result = object->getProperty("answer").toString().trim();
        if (result.isEmpty()) result = object->getProperty("error").toString().trim();
    }
    if (result.isEmpty()) result = httpStatus == 200 ? "Undo proposal ready." : "KENN could not prepare Live undo (HTTP " + juce::String(httpStatus) + ").";
    return httpStatus == 200 && proposal.isObject();
}

bool KENNMixAssistantAudioProcessor::confirmLiveUndo(const juce::var& receipt, const juce::var& proposal, juce::var& undoReceipt, juce::String& result) const
{
    undoReceipt = juce::var();
    auto* proposalObject = proposal.getDynamicObject();
    if (proposalObject == nullptr || receipt.getDynamicObject() == nullptr)
    {
        result = "No valid Live undo proposal is waiting for confirmation.";
        return false;
    }

    if (static_cast<bool>(proposalObject->getProperty("local_only")))
    {
#if KENN_ENABLE_DIRECT_LIVE_WRITES
        if (!static_cast<bool>(proposalObject->getProperty("requires_confirmation")))
        {
            result = "This local C++ undo plan is read-only and cannot be confirmed.";
            return false;
        }
        const auto mutation = kenn::setAbletonOscParameterWithReadback(
            "127.0.0.1", 11000, 11001,
            proposalObject->getProperty("track_index").toString().getIntValue(),
            proposalObject->getProperty("device_index").toString().getIntValue(),
            proposalObject->getProperty("parameter_index").toString().getIntValue(),
            proposalObject->getProperty("device_name").toString(),
            proposalObject->getProperty("parameter_name").toString(),
            proposalObject->getProperty("before").toString().getDoubleValue(),
            proposalObject->getProperty("after").toString().getDoubleValue());
        if (!mutation.verified)
        {
            result = mutation.error.isNotEmpty() ? mutation.error : "Direct C++ Live undo failed readback verification.";
            return false;
        }
        auto restored = std::make_unique<juce::DynamicObject>();
        restored->setProperty("schema", "kenn.ableton_local_parameter_receipt.v1");
        restored->setProperty("local_only", true);
        restored->setProperty("verified", true);
        restored->setProperty("action", "set_device_parameter");
        restored->setProperty("receipt_id", "local-receipt-" + juce::Uuid().toString());
        restored->setProperty("track_index", proposalObject->getProperty("track_index"));
        restored->setProperty("track_name", proposalObject->getProperty("track_name"));
        restored->setProperty("device_index", proposalObject->getProperty("device_index"));
        restored->setProperty("device_name", proposalObject->getProperty("device_name"));
        restored->setProperty("parameter_index", proposalObject->getProperty("parameter_index"));
        restored->setProperty("parameter_name", proposalObject->getProperty("parameter_name"));
        restored->setProperty("before", mutation.beforeValue);
        restored->setProperty("after", mutation.afterValue);
        restored->setProperty("min", proposalObject->getProperty("min"));
        restored->setProperty("max", proposalObject->getProperty("max"));
        undoReceipt = juce::var(restored.release());
        result = "Direct C++ Live undo applied and verified by readback.";
        return true;
#else
        result = "Direct C++ Live undo is disabled in this build.";
        return false;
#endif
    }

    const auto token = proposalObject->getProperty("confirmation_token").toString();
    const auto idempotency = proposalObject->getProperty("action_id").toString().isNotEmpty()
        ? proposalObject->getProperty("action_id").toString()
        : proposalObject->getProperty("id").toString();
    if (token.isEmpty() || idempotency.isEmpty()) { result = "The Live undo proposal is missing its confirmation binding."; return false; }

    auto payload = std::make_unique<juce::DynamicObject>();
    payload->setProperty("session_id", getKennSessionId());
    payload->setProperty("receipt", receipt);
    payload->setProperty("proposal", proposal);
    payload->setProperty("confirm_token", token);
    payload->setProperty("idempotency_key", idempotency);
    const auto url = juce::URL(getKennEndpoint() + "/api/ableton/osc/undo").withPOSTData(juce::JSON::toString(juce::var(payload.release()), false));
    int httpStatus = 0;
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN Companion is not running locally. Nothing was changed."; return false; }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    if (auto* object = parsed.getDynamicObject(); object != nullptr)
    {
        result = object->getProperty("answer").toString().trim();
        if (result.isEmpty()) result = object->getProperty("error").toString().trim();
        if (auto candidate = object->getProperty("receipt"); candidate.isObject()) undoReceipt = candidate;
    }
    if (result.isEmpty()) result = httpStatus == 200 ? "Live undo applied and verified." : "KENN could not confirm Live undo (HTTP " + juce::String(httpStatus) + ").";
    return httpStatus == 200 && undoReceipt.isObject();
}

bool KENNMixAssistantAudioProcessor::requestSafeTargetProposal(float& proposedTarget, juce::String& result) const
{
    const auto body = juce::JSON::toString(handoffPayload(), false);
    int httpStatus = 0;
    const auto url = juce::URL(getKennEndpoint() + "/api/plugin-handoff").withPOSTData(body);
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN Companion is not running locally. Local Mix Check remains available."; return false; }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    auto* responseObject = parsed.getDynamicObject();
    if (httpStatus != 200 || responseObject == nullptr || ! responseObject->getProperty("ok"))
    {
        result = "KENN could not create a proposal (HTTP " + juce::String(httpStatus) + ").";
        return false;
    }
    const auto* proposals = responseObject->getProperty("action_proposals").getArray();
    if (proposals == nullptr || proposals->isEmpty()) { result = "KENN found no safe target change for this snapshot."; return false; }
    for (const auto& item : *proposals)
    {
        auto* proposal = item.getDynamicObject();
        if (proposal == nullptr || proposal->getProperty("schema").toString() != "kenn.action_proposal.v1"
            || proposal->getProperty("target").toString() != "kenn_mix_assistant"
            || proposal->getProperty("parameter").toString() != "target_lufs"
            || ! static_cast<bool>(proposal->getProperty("requires_confirmation")))
            continue;
        const auto target = static_cast<float>(proposal->getProperty("after"));
        if (target >= -24.0f && target <= -6.0f)
        {
            proposedTarget = target;
            result = proposal->getProperty("reason").toString();
            return true;
        }
    }
    result = "KENN returned no supported safe proposal.";
    return false;
}

bool KENNMixAssistantAudioProcessor::testKennConnection(juce::String& result) const
{
    int httpStatus = 0;
    const auto endpoint = getKennEndpoint();
    const auto url = juce::URL(endpoint + "/api/health");
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
        .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr)
    {
        // The plug-in can still prove that AbletonOSC/Live is reachable when
        // the optional Python companion is not running. This is deliberately
        // read-only: proposals, writes, readback, receipts, and undo still
        // require the companion safety service.
        const auto probe = kenn::probeAbletonOscDirect();
        if (probe.connected)
        {
            result = "AbletonOSC is reachable directly (" + juce::String(probe.trackCount)
                + " tracks), but KENN Companion is offline. Live changes still require the local companion.";
            return true;
        }
        result = "Cannot reach KENN at " + endpoint + ". Start KENN or check its local port."
            + (probe.error.isNotEmpty() ? " Direct AbletonOSC probe: " + probe.error : juce::String());
        return false;
    }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    if (auto* object = parsed.getDynamicObject(); httpStatus == 200 && object != nullptr && object->getProperty("ok"))
    {
        const auto app = object->getProperty("app").toString().isNotEmpty()
            ? object->getProperty("app").toString() : "KENN";

        // Health proves only that the companion HTTP process is alive. Ask
        // the read-only capability route as well so the plug-in can explain
        // the important second boundary: whether AbletonOSC/Live is reachable.
        int capabilityStatus = 0;
        const auto capabilityOptions = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
            .withConnectionTimeoutMs(2000).withNumRedirectsToFollow(0).withStatusCode(&capabilityStatus);
        const auto capabilityResponse = juce::URL(endpoint + "/api/ableton/capabilities").createInputStream(capabilityOptions);
        if (capabilityResponse != nullptr)
        {
            const auto capabilityJson = juce::JSON::parse(capabilityResponse->readEntireStreamAsString());
            if (auto* capability = capabilityJson.getDynamicObject(); capabilityStatus == 200 && capability != nullptr
                && capability->getProperty("transport").toString().equalsIgnoreCase("AbletonOSC"))
            {
                const bool liveConnected = static_cast<bool>(capability->getProperty("connected"));
                if (liveConnected)
                {
                    const auto count = capability->getProperty("track_count");
                    result = "Connected to " + app + ". AbletonOSC is connected"
                        + (count.isInt() ? " (" + count.toString() + " tracks)." : ".")
                        + " Live changes require confirmation and readback.";
                }
                else
                {
                    result = "Connected to " + app + ", but AbletonOSC is offline. Open Live, select AbletonOSC, and restart Live.";
                }
                return true;
            }
        }

        result = "Connected to " + app + ".";
        return true;
    }
    result = "KENN health check failed (HTTP " + juce::String(httpStatus) + ").";
    return false;
}

bool KENNMixAssistantAudioProcessor::startAutoMix(const juce::Array<juce::File>& stems, juce::String& result) const
{
    if (stems.isEmpty()) { result = "Choose at least one audio stem."; return false; }
    if (stems.size() > 32) { result = "AutoMix accepts up to 32 stems."; return false; }
    // Leave room for multipart framing below KENN's 500 MB request limit.
    constexpr int64_t maxUploadBytes = 490LL * 1024 * 1024;
    int64_t totalBytes = 0;
    for (const auto& file : stems)
    {
        if (! file.existsAsFile() || file.getSize() <= 0) { result = "Could not read " + file.getFileName(); return false; }
        totalBytes += file.getSize();
        if (totalBytes > maxUploadBytes) { result = "Selected stems total more than 490 MB. Split the export into smaller stem groups."; return false; }
    }
    constexpr auto boundary = "----KENNMixAssistantBoundary7MA4YWxk";
    juce::MemoryOutputStream body;
    for (int index = 0; index < stems.size(); ++index)
    {
        const auto& file = stems.getReference(index);
        body << "--" << boundary << "\r\nContent-Disposition: form-data; name=\"stem_" << index
             << "\"; filename=\"" << file.getFileName().replaceCharacter('"', '_') << "\"\r\n"
             << "Content-Type: application/octet-stream\r\n\r\n";
        juce::FileInputStream input(file);
        if (! input.openedOk()) { result = "Could not open " + file.getFileName(); return false; }
        body.writeFromInputStream(input, -1);
        body << "\r\n";
    }
    body << "--" << boundary << "\r\nContent-Disposition: form-data; name=\"genre\"\r\n\r\npop\r\n"
         << "--" << boundary << "\r\nContent-Disposition: form-data; name=\"session_id\"\r\n\r\n" << getKennSessionId() << "\r\n"
         << "--" << boundary << "--\r\n";
    const auto url = juce::URL(getKennEndpoint() + "/api/automix-upload").withPOSTData(body.getMemoryBlock());
    int httpStatus = 0;
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withExtraHeaders("Content-Type: multipart/form-data; boundary=" + juce::String(boundary))
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN is not running locally."; return false; }
    const auto responseText = response->readEntireStreamAsString();
    const auto parsed = juce::JSON::parse(responseText);
    if (auto* object = parsed.getDynamicObject(); object != nullptr && object->getProperty("ok"))
    {
        result = "AutoMix queued: " + object->getProperty("job_id").toString();
        return true;
    }
    if (auto* object = parsed.getDynamicObject(); object != nullptr && object->hasProperty("error"))
        result = "AutoMix upload failed (HTTP " + juce::String(httpStatus) + "): " + object->getProperty("error").toString();
    else
        result = "AutoMix upload failed (HTTP " + juce::String(httpStatus) + ").";
    return false;
}

bool KENNMixAssistantAudioProcessor::fetchAutoMixStatus(const juce::String& jobId, juce::String& result, bool& complete) const
{
    complete = false;
    const auto url = juce::URL(getKennEndpoint() + "/api/automix-status").withParameter("id", jobId);
    auto response = url.createInputStream(juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
                                              .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0));
    if (response == nullptr) { result = "KENN is unavailable while checking AutoMix."; return false; }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    auto* object = parsed.getDynamicObject();
    if (object == nullptr || ! object->getProperty("ok")) { result = "AutoMix status is unavailable."; return false; }
    const auto state = object->getProperty("status").toString();
    result = "AutoMix " + state + " - " + object->getProperty("progress").toString() + "%";
    complete = state == "complete" || state == "failed";
    return true;
}

juce::AudioProcessorEditor* KENNMixAssistantAudioProcessor::createEditor()
{
    return new KENNMixAssistantAudioProcessorEditor(*this);
}

void KENNMixAssistantAudioProcessor::getStateInformation(juce::MemoryBlock& data)
{
    if (auto xml = std::unique_ptr<juce::XmlElement>(apvts.copyState().createXml()))
    {
        xml->setAttribute("kenn_endpoint", getKennEndpoint());
        xml->setAttribute("kenn_session_id", getKennSessionId());
        auto* logXml = xml->createNewChildElement("KENN_TARGET_ACTION_LOG");
        const juce::ScopedLock lock(actionLogLock);
        for (const auto& entry : targetActionLog)
        {
            auto* item = logXml->createNewChildElement("ACTION");
            item->setAttribute("timestamp", entry.timestamp); item->setAttribute("event", entry.event);
            item->setAttribute("reason", entry.reason); item->setAttribute("before", entry.before); item->setAttribute("after", entry.after);
        }
        copyXmlToBinary(*xml, data);
    }
}
void KENNMixAssistantAudioProcessor::setStateInformation(const void* data, int size)
{
    if (auto xml = std::unique_ptr<juce::XmlElement>(getXmlFromBinary(data, size)); xml != nullptr && xml->hasTagName(apvts.state.getType()))
    {
        {
            const juce::ScopedLock lock(actionLogLock);
            targetActionLog.clear();
            if (auto* logXml = xml->getChildByName("KENN_TARGET_ACTION_LOG"))
                for (auto* item : logXml->getChildWithTagNameIterator("ACTION"))
                    targetActionLog.add({ item->getStringAttribute("timestamp"), item->getStringAttribute("event"), item->getStringAttribute("reason"), (float) item->getDoubleAttribute("before"), (float) item->getDoubleAttribute("after") });
            while (targetActionLog.size() > 50) targetActionLog.remove(0);
        }
        if (auto* logXml = xml->getChildByName("KENN_TARGET_ACTION_LOG")) xml->removeChildElement(logXml, true);
        apvts.replaceState(juce::ValueTree::fromXml(*xml));
        juce::String ignored;
        setKennConnection(xml->getStringAttribute("kenn_endpoint", "http://127.0.0.1:8090"), xml->getStringAttribute("kenn_session_id", "plugin-local"), ignored);
    }
}

bool KENNMixAssistantAudioProcessor::syncWebParameters()
{
    const auto url = juce::URL(getKennEndpoint() + "/api/plugin/parameters?session_id=" + getKennInsertId() + "&pop_pending=1");
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
        .withConnectionTimeoutMs(200)
        .withNumRedirectsToFollow(0);
    auto stream = url.createInputStream(options);
    if (stream == nullptr)
        return false;

    const auto parsed = juce::JSON::parse(stream->readEntireStreamAsString());
    auto* obj = parsed.getDynamicObject();
    if (obj == nullptr || ! obj->getProperty("ok"))
        return false;

    auto* pending = obj->getProperty("pending_updates").getDynamicObject();
    if (pending == nullptr)
        return false;

    bool anyUpdated = false;

    if (pending->hasProperty("target_lufs"))
    {
        const float targetVal = static_cast<float>(pending->getProperty("target_lufs"));
        if (auto* param = apvts.getParameter("target_lufs"))
        {
            const float current = param->convertFrom0to1(param->getValue());
            if (std::abs(current - targetVal) >= 0.05f)
            {
                param->beginChangeGesture();
                param->setValueNotifyingHost(param->convertTo0to1(targetVal));
                param->endChangeGesture();
                recordTargetAction("applied_from_web", current, targetVal, "Synchronized from KENN Web UI");
                anyUpdated = true;
            }
        }
    }

    if (pending->hasProperty("assistant_mode"))
    {
        const juce::String mode = pending->getProperty("assistant_mode").toString().toLowerCase().trim();
        int modeIdx = -1;
        if (mode == "ask") modeIdx = 0;
        else if (mode == "suggest") modeIdx = 1;
        else if (mode == "assist") modeIdx = 2;
        else if (mode == "auto") modeIdx = 3;

        if (modeIdx >= 0)
        {
            if (auto* param = apvts.getParameter("assistant_mode"))
            {
                const int currentIdx = juce::jlimit(0, 3, juce::roundToInt(apvts.getRawParameterValue("assistant_mode")->load()));
                if (currentIdx != modeIdx)
                {
                    param->beginChangeGesture();
                    param->setValueNotifyingHost(param->convertTo0to1(static_cast<float>(modeIdx)));
                    param->endChangeGesture();
                    anyUpdated = true;
                }
            }
        }
    }

    if (pending->hasProperty("live_context_enabled"))
    {
        const bool enabled = static_cast<bool>(pending->getProperty("live_context_enabled"));
        if (auto* param = apvts.getParameter("live_context_enabled"))
        {
            const bool current = apvts.getRawParameterValue("live_context_enabled")->load() >= 0.5f;
            if (current != enabled)
            {
                param->beginChangeGesture();
                param->setValueNotifyingHost(enabled ? 1.0f : 0.0f);
                param->endChangeGesture();
                anyUpdated = true;
            }
        }
    }

    if (pending->hasProperty("analysis_enabled"))
    {
        const bool enabled = static_cast<bool>(pending->getProperty("analysis_enabled"));
        if (auto* param = apvts.getParameter("analysis_enabled"))
        {
            const bool current = apvts.getRawParameterValue("analysis_enabled")->load() >= 0.5f;
            if (current != enabled)
            {
                param->beginChangeGesture();
                param->setValueNotifyingHost(enabled ? 1.0f : 0.0f);
                param->endChangeGesture();
                anyUpdated = true;
            }
        }
    }

    return anyUpdated;
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() { return new KENNMixAssistantAudioProcessor(); }
