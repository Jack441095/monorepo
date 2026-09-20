#include "PluginProcessor.h"
#include "PluginEditor.h"

KENNMixAssistantAudioProcessor::KENNMixAssistantAudioProcessor()
    : AudioProcessor(BusesProperties().withInput("Input", juce::AudioChannelSet::stereo(), true)
                                      .withOutput("Output", juce::AudioChannelSet::stereo(), true)),
      apvts(*this, nullptr, "PARAMS", createParameterLayout())
{
    // Avoid silently merging different plug-in instances into one companion
    // context. This value is persisted with the DAW project and can be
    // replaced with a KENN chat session ID when the user explicitly wants it.
    kennSessionId = "plugin-" + juce::Uuid().toString();
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

void KENNMixAssistantAudioProcessor::prepareToPlay(double sampleRate, int) { realtimeCore.reset(sampleRate); }

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
    if (apvts.getRawParameterValue("analysis_enabled")->load() >= 0.5f) realtimeCore.analyse(buffer);
    // Intentional transparent pass-through.  AutoMix rendering is offline and
    // stem-based, therefore no processing is silently applied to this bus.
}

juce::var KENNMixAssistantAudioProcessor::handoffPayload() const
{
    const auto data = meterSnapshot();
    auto message = std::make_unique<juce::DynamicObject>();
    message->setProperty("schema", "kenn.plugin_handoff.v1");
    message->setProperty("audio_feature_schema", "audio_feature_frame.v1");
    message->setProperty("kind", "mix_review_snapshot");
    message->setProperty("plugin", "KENN Mix Assistant");
    message->setProperty("assistant_mode", getAssistantMode());
    message->setProperty("session_id", getKennSessionId());
    message->setProperty("target_lufs", apvts.getRawParameterValue("target_lufs")->load());
    auto pluginState = std::make_unique<juce::DynamicObject>();
    pluginState->setProperty("assistant_mode", getAssistantMode());
    pluginState->setProperty("target_lufs", apvts.getRawParameterValue("target_lufs")->load());
    pluginState->setProperty("analysis_enabled", apvts.getRawParameterValue("analysis_enabled")->load() >= 0.5f);
    pluginState->setProperty("live_context_enabled", apvts.getRawParameterValue("live_context_enabled")->load() >= 0.5f);
    message->setProperty("plugin_state", juce::var(pluginState.release()));
    message->setProperty("peak_dbfs", data.peakDb); message->setProperty("rms_dbfs", data.rmsDb);
    message->setProperty("stereo_correlation", data.correlation); message->setProperty("stereo_width", data.stereoWidth);
    message->setProperty("sample_rate", data.sampleRate); message->setProperty("analysed_samples", data.analysedSamples);
    const auto features = realtimeCore.snapshot();
    message->setProperty("low_energy", features.lowEnergy); message->setProperty("mid_energy", features.midEnergy); message->setProperty("high_energy", features.highEnergy);
    message->setProperty("crest_db", features.crestDb); message->setProperty("transient_ratio", features.transientRatio); message->setProperty("clipped_samples", features.clippedSamples);
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

bool KENNMixAssistantAudioProcessor::askKenn(const juce::String& question, juce::String& result) const
{
    const auto cleanQuestion = question.trim();
    if (cleanQuestion.isEmpty()) { result = "Type a question for KENN first."; return false; }
    if (cleanQuestion.length() > 4000) { result = "Keep the KENN question under 4,000 characters."; return false; }
    auto payload = std::make_unique<juce::DynamicObject>();
    payload->setProperty("question", cleanQuestion);
    payload->setProperty("session_id", getKennSessionId());
    const auto url = juce::URL(getKennEndpoint() + "/api/ask").withPOSTData(juce::JSON::toString(juce::var(payload.release()), false));
    int httpStatus = 0;
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(30000).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN Companion is not running locally."; return false; }
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

bool KENNMixAssistantAudioProcessor::requestSafeTargetProposal(float& proposedTarget, juce::String& result) const
{
    const auto body = juce::JSON::toString(handoffPayload(), false);
    int httpStatus = 0;
    const auto url = juce::URL(getKennEndpoint() + "/api/plugin-handoff").withPOSTData(body);
    const auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
        .withConnectionTimeoutMs(1200).withNumRedirectsToFollow(0).withStatusCode(&httpStatus);
    auto response = url.createInputStream(options);
    if (response == nullptr) { result = "KENN Companion is not running locally."; return false; }
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
        result = "Cannot reach KENN at " + endpoint + ". Start KENN or check its local port.";
        return false;
    }
    const auto parsed = juce::JSON::parse(response->readEntireStreamAsString());
    if (auto* object = parsed.getDynamicObject(); httpStatus == 200 && object != nullptr && object->getProperty("ok"))
    {
        result = "Connected to " + object->getProperty("app").toString() + ".";
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
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() { return new KENNMixAssistantAudioProcessor(); }
