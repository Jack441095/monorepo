#include <iostream>

#include <JuceHeader.h>
#include "PluginProcessor.h"

// Proves the actual compiled plugin binary (not just its source read) talks
// correctly to a real, running apps/backend/src/kenn/server.py -- constructs the real
// KENNMixAssistantAudioProcessor (the same class createPluginFilter() hands
// to a DAW) and calls its public network methods directly, exactly as the
// editor's button handlers do. Requires a KENN server already running at
// KENN_TEST_ENDPOINT (default http://127.0.0.1:8090); skips (exit 0) rather
// than failing if none is reachable, since this is an integration check
// against a live local process, not a self-contained unit test.

int main()
{
    KENNMixAssistantAudioProcessor processor;

    const auto endpoint = juce::SystemStats::getEnvironmentVariable("KENN_TEST_ENDPOINT", "http://127.0.0.1:8090");
    juce::String connectError;
    if (!processor.setKennConnection(endpoint, "vst3-integration-test", connectError))
    {
        std::cerr << "FAIL: could not configure connection: " << connectError << std::endl;
        return 1;
    }

    std::cout << "Testing connection to " << endpoint << " ..." << std::endl;
    juce::String healthResult;
    const bool healthOk = processor.testKennConnection(healthResult);
    std::cout << "  /api/health + AbletonOSC capability probe -> " << (healthOk ? "OK: " : "FAIL: ") << healthResult << std::endl;
    if (!healthOk)
    {
        std::cout << "SKIP: no KENN server reachable at " << endpoint
                   << " -- start one with `python3 apps/backend/src/kenn/server.py` to exercise this test."
                   << std::endl;
        return 0;
    }

    // Chat is intentionally optional here. The Live control path is
    // deterministic and must stay fast even when an optional local model is
    // absent or takes tens of seconds to answer. Set KENN_TEST_CHAT=1 when a
    // separate model/chat qualification is explicitly wanted.
    if (juce::SystemStats::getEnvironmentVariable("KENN_TEST_CHAT", "0") == "1")
    {
        std::cout << "Asking KENN a real mix-engineering question through the compiled plugin binary..." << std::endl;
        juce::String answer;
        const bool askOk = processor.askKenn("Why does my mix collapse when I check it in mono?", answer);
        std::cout << "  /api/ask -> " << (askOk ? "OK" : "FAIL") << std::endl;
        std::cout << "  answer (" << answer.length() << " chars): "
                   << answer.substring(0, 200) << (answer.length() > 200 ? "..." : "") << std::endl;
        if (!askOk || answer.isEmpty())
        {
            std::cerr << "FAIL: /api/ask did not return a usable answer through the compiled plugin binary." << std::endl;
            return 1;
        }
    }
    else
    {
        std::cout << "Skipping optional /api/ask model check; deterministic Live control remains the smoke-test boundary."
                  << std::endl;
    }

    std::cout << "Planning a read-only Live command through the compiled plugin binary..." << std::endl;
    juce::var proposal;
    juce::String commandAnswer;
    const bool commandOk = processor.planLiveCommand("show my tracks", proposal, commandAnswer);
    std::cout << "  /api/ableton/command -> " << (commandOk ? "OK" : "FAIL") << ": " << commandAnswer.substring(0, 200) << std::endl;
    if (!commandOk || commandAnswer.isEmpty())
    {
        std::cerr << "FAIL: the compiled plugin command client did not receive a usable response." << std::endl;
        return 1;
    }

    std::cout << "SUCCESS: the compiled KENN Mix Assistant plugin binary reached a live KENN server "
                 "and received real, non-empty responses through its health and deterministic Live-command "
                 "client paths. Optional chat qualification is available with KENN_TEST_CHAT=1." << std::endl;
    return 0;
}
