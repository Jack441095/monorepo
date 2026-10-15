#include <iostream>

#include <JuceHeader.h>
#include "PluginProcessor.h"

// Verifies the new C++ command client against the real local companion without
// depending on the slower, separate generic-chat integration path. A healthy
// offline response is still a valid command-boundary result: the client must
// receive and display it rather than treating it as a transport failure.

class PairedTestPlayHead final : public juce::AudioPlayHead
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
    KENNMixAssistantAudioProcessor processor;
    juce::AudioProcessor::TrackProperties track;
    track.name = " Kick ";
    processor.updateTrackProperties(track);
    if (processor.getHostTrackName() != "Kick")
    {
        std::cerr << "FAIL: host track name did not reach the handoff worker state.\n";
        return 1;
    }
    track.name.clear();
    processor.updateTrackProperties(track);
    if (processor.getHostTrackName().isNotEmpty())
    {
        std::cerr << "FAIL: an unknown host name retained a previous track association.\n";
        return 1;
    }
    // Offline qualification must never contact an owner's running companion.
    if (juce::SystemStats::getEnvironmentVariable("KENN_TEST_OFFLINE_ONLY", "0") == "1")
    {
        std::cout << "SUCCESS: host-name callback set and cleared insert attribution. HTTP checks skipped in offline mode.\n";
        return 0;
    }
    const auto endpoint = juce::SystemStats::getEnvironmentVariable("KENN_TEST_ENDPOINT", "http://127.0.0.1:8090");
    juce::String error;
    if (!processor.setKennConnection(endpoint, "vst3-command-integration-test", error))
    {
        std::cerr << "FAIL: could not configure connection: " << error << std::endl;
        return 1;
    }

    juce::String health;
    if (!processor.testKennConnection(health))
    {
        std::cout << "SKIP: no KENN server reachable at " << endpoint << std::endl;
        return 0;
    }

    const auto analysisTrack = juce::SystemStats::getEnvironmentVariable("KENN_TEST_ANALYSIS_TRACK", "");
    if (analysisTrack.isNotEmpty())
    {
        // The Python HTTP fixture supplies an isolated fake track and endpoint.
        // This exercises the actual native serializer and Ask client, without
        // qualifying or writing to a producer's Live session.
        processor.prepareToPlay(48000.0, 480); // 10 ms blocks at 48 kHz.
        track.name = analysisTrack;
        processor.updateTrackProperties(track);
        KENNMixAssistantAudioProcessor bass;
        if (! bass.setKennConnection(endpoint, processor.getKennSessionId(), error)) return 1; // The fixture already validated the same endpoint.
        bass.prepareToPlay(48000.0, 480);
        track.name = "Bass"; bass.updateTrackProperties(track);
        PairedTestPlayHead clock; processor.setPlayHead(&clock); bass.setPlayHead(&clock);
        if (processor.getKennInsertId() == bass.getKennInsertId()) return 1; // Shared chat ownership must never merge audio identity.
        juce::AudioBuffer<float> audio(2, 480);
        juce::MidiBuffer midi;
        for (int block = 0; block < 40; ++block)
        {
            clock.sample = block * 480;
            for (int channel = 0; channel < 2; ++channel)
                for (int sample = 0; sample < 480; ++sample)
                    audio.setSample(channel, sample, static_cast<float>(0.99 * std::sin(
                        2.0 * juce::MathConstants<double>::pi * 60.0 * static_cast<double>(clock.sample+sample)/48000.0))); // 60 Hz sine, same host interval in both inserts.
            processor.processBlock(audio, midi); bass.processBlock(audio, midi);
            juce::Thread::sleep(10); // Pace 10 ms input blocks so the test qualifies the accepting queue path.
        }
        // Grade comes before any analysis request: with background publication
        // off, only this Ask can supply the selected insert's measured window.
        if (processor.apvts.getRawParameterValue("live_context_enabled")->load() >= 0.5f)
        {
            std::cerr << "FAIL: native grade fixture requires background publication off.\n";
            return 1;
        }
        for (const auto& question : { "Grade this insert", "Please can you grade this insert",
                                      "Would you rate selected insert please", "Grade track 1", "Grade Kick" })
        {
            juce::String grade;
            if (! processor.askKenn(question, grade)
                || ! grade.contains("6 available") || ! grade.contains("100 ms")
                || ! grade.containsIgnoreCase("stereo") || ! grade.containsIgnoreCase("ungraded"))
            {
                std::cerr << "FAIL: native selected-insert grade did not return scoped measured points and omissions: " << grade << '\n';
                return 1;
            }
        }
        std::cout << "SUCCESS: native selected-insert grade supplied its own fresh window with background publication off.\n";
        juce::String analysis;
        if (!processor.askKenn("Analyse " + analysisTrack, analysis)
            || !analysis.contains("sample peak") || !analysis.contains("Proposed Live fader")
            || !analysis.contains("Nothing has changed"))
        {
            std::cerr << "FAIL: native insert analysis did not produce measured, approval-gated advice: " << analysis << '\n';
            return 1;
        }
        std::cout << "SUCCESS: native insert analysis reached the fake HTTP companion and returned a guarded fader proposal.\n";
        juce::String association;
        if (! processor.askKenn("bind this insert to track 1", association) || ! association.contains("Associated this insert"))
        {
            std::cerr << "FAIL: native binding did not reach the fake companion: " << association << '\n';
            return 1;
        }
        if (! bass.askKenn("bind this insert to track 2", association) || ! association.contains("Associated this insert"))
        {
            std::cerr << "FAIL: second native insert could not bind independently: " << association << '\n';
            return 1;
        }
        if (! processor.askKenn("Is the bass masking the kick?", analysis) || ! analysis.contains("shape similarity")
            || ! analysis.contains("does not prove audible masking"))
        {
            std::cerr << "FAIL: paired native features did not produce a qualified comparison: " << analysis << '\n';
            return 1;
        }
        std::cout << "SUCCESS: two native inserts with shared conversation ownership retained separate audio identities and matching FFT intervals.\n";
        bass.releaseResources();
        if (! bass.askKenn("unbind this insert", association)) return 1; // Metadata must remain clearable after playback stops.
        processor.releaseResources();
        if (! processor.askKenn("unbind this insert", association) || ! association.contains("Cleared this insert"))
        {
            std::cerr << "FAIL: clearing native metadata required running audio: " << association << '\n';
            return 1;
        }
        std::cout << "SUCCESS: native binding and offline unbinding reached the fake HTTP companion.\n";
        return 0;
    }

    juce::var proposal;
    juce::String answer;
    const bool ok = processor.planLiveCommand("show my tracks", proposal, answer);
    std::cout << "C++ /api/ableton/command -> " << (ok ? "OK" : "FAIL") << ": " << answer << std::endl;
    if (!ok || answer.isEmpty())
    {
        if (answer.containsIgnoreCase("AbletonOSC")
            || answer.containsIgnoreCase("fresh Live snapshot")
            || answer.containsIgnoreCase("offline")
            || answer.containsIgnoreCase("timed out while waiting"))
        {
            std::cout << "SKIP: companion is reachable but AbletonOSC is offline; Live-bound checks are deferred.\n";
            return 0;
        }
        std::cerr << "FAIL: command endpoint did not return a usable bounded response." << std::endl;
        return 1;
    }

    // Keep this check safe and repeatable against whatever disposable Live set
    // is currently open. If track 4 is empty, insertion is the correct
    // proposal to exercise; if an EQ Eight is already present, exercise the
    // compound existing-device proposal instead. Neither branch writes Live.
    juce::var insertionProposal;
    juce::String insertionAnswer;
    const bool insertionOk = processor.planLiveCommand("add EQ on track 4", insertionProposal, insertionAnswer);
    auto* insertionObject = insertionProposal.getDynamicObject();
    const bool exactInsertionProposal = insertionObject != nullptr
        && insertionObject->getProperty("schema").toString() == "kenn.ableton_device_insertion_proposal.v1"
        && insertionObject->getProperty("track_name").toString() == "4-Audio"
        && insertionObject->getProperty("device_name").toString() == "EQ Eight"
        && static_cast<bool>(insertionObject->getProperty("requires_confirmation"));

    bool exactLiveProposal = insertionOk && exactInsertionProposal;
    juce::String liveAvailabilityAnswer = insertionAnswer;
    std::cout << "C++ insertion proposal -> " << (exactLiveProposal ? "OK" : "not applicable")
              << ": " << insertionAnswer << std::endl;

    if (! exactLiveProposal)
    {
        juce::var compoundProposal;
        juce::String compoundAnswer;
        const auto compoundCommand = "retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on track 4";
        const bool compoundOk = processor.planLiveCommand(compoundCommand, compoundProposal, compoundAnswer);
        auto* compoundObject = compoundProposal.getDynamicObject();
        const bool exactCompoundProposal = compoundObject != nullptr
            && compoundObject->getProperty("schema").toString() == "kenn.ableton_eq_band_tuning_gain_proposal.v1"
            && compoundObject->getProperty("track_name").toString() == "4-Audio"
            && compoundObject->getProperty("device_name").toString() == "EQ Eight"
            && compoundObject->getProperty("eq_band").toString() == "1A"
            && compoundObject->getProperty("frequency_parameter").toString() == "1 Frequency A"
            && compoundObject->getProperty("gain_parameter").toString() == "1 Gain A"
            && static_cast<bool>(compoundObject->getProperty("requires_confirmation"));
        exactLiveProposal = compoundOk && exactCompoundProposal;
        liveAvailabilityAnswer = compoundAnswer;
        std::cout << "C++ compound EQ proposal -> " << (exactLiveProposal ? "OK" : "FAIL")
                  << ": " << compoundAnswer << std::endl;
    }

    if (! exactLiveProposal)
    {
        // The companion can be healthy while AbletonOSC is offline.  In that
        // state the compiled client has already proved its HTTP command
        // response path, but no Live-bound proposal can honestly exist; keep
        // this integration check green and defer the proposal assertions to
        // the real-Live qualification run.
        if (liveAvailabilityAnswer.containsIgnoreCase("fresh Live snapshot")
            || liveAvailabilityAnswer.containsIgnoreCase("AbletonOSC")
            || liveAvailabilityAnswer.containsIgnoreCase("offline"))
        {
            std::cout << "SKIP: companion is reachable but AbletonOSC is offline; Live-bound proposal checks are deferred.\n";
            return 0;
        }
        std::cerr << "FAIL: the compiled KENN plug-in command client did not receive an exact, confirmation-bound Live proposal." << std::endl;
        return 1;
    }

    juce::String controls;
    const bool controlsOk = processor.inspectLiveControls(controls);
    // An empty disposable set is valid: the matrix still has to return a
    // successful read-only response. Device-specific text is asserted by the
    // Python qualification suite once that device is intentionally present.
    const bool hasReadOnlyInventory = controls.contains("Live controls (read-only)")
        && controls.contains("Nothing has changed");
    std::cout << "C++ read-only Live control inventory -> "
              << (controlsOk && hasReadOnlyInventory ? "OK" : "FAIL")
              << " (" << controls.length() << " chars)" << std::endl;
    if (!controlsOk || !hasReadOnlyInventory)
    {
        std::cerr << "FAIL: the compiled KENN plug-in did not receive the exact read-only Live control inventory." << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: the compiled KENN plug-in command client received bounded Live responses, including an exact confirmation-bound proposal." << std::endl;
    return 0;
}
