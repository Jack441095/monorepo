#include <iostream>

#include <JuceHeader.h>
#include "PluginProcessor.h"

// Verifies the new C++ command client against the real local companion without
// depending on the slower, separate generic-chat integration path. A healthy
// offline response is still a valid command-boundary result: the client must
// receive and display it rather than treating it as a transport failure.

int main()
{
    KENNMixAssistantAudioProcessor processor;
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

    juce::var proposal;
    juce::String answer;
    const bool ok = processor.planLiveCommand("show my tracks", proposal, answer);
    std::cout << "C++ /api/ableton/command -> " << (ok ? "OK" : "FAIL") << ": " << answer << std::endl;
    if (!ok || answer.isEmpty())
    {
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
