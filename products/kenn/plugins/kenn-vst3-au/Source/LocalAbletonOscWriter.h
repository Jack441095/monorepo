#pragma once

#include <juce_core/juce_core.h>

namespace kenn
{
struct AbletonOscMutationResult
{
    bool sent = false;
    bool verified = false;
    double beforeValue = 0.0;
    double afterValue = 0.0;
    juce::String error;
};

// Guarded parameter mutation primitive for the future self-contained path.
// It claims the fixed response port, re-reads the exact device/parameter,
// rejects stale before-values, sends one allow-listed OSC write, and verifies
// the requested value with a fresh readback. The plug-in does not activate
// this primitive until the real disposable-set qualification is complete.
AbletonOscMutationResult setAbletonOscParameterWithReadback(
    const juce::String& host,
    int sendPort,
    int responsePort,
    int trackIndex,
    int deviceIndex,
    int parameterIndex,
    const juce::String& deviceName,
    const juce::String& parameterName,
    double expectedBefore,
    double requestedValue,
    double tolerance = 0.0005,
    int timeoutMs = 500);
}
