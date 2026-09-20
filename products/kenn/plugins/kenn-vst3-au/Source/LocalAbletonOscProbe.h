#pragma once

#include <juce_core/juce_core.h>

#include <vector>

namespace kenn
{
struct AbletonOscProbeResult
{
    bool connected = false;
    int trackCount = -1;
    juce::StringArray trackNames;
    juce::String error;
};

// Read-only fallback for the plug-in Test button. It binds the documented
// AbletonOSC response port only when the companion HTTP path is unavailable.
// It never sends a mutation and reports failure if another KENN instance owns
// the response port.
AbletonOscProbeResult probeAbletonOscDirect(const juce::String& host = "127.0.0.1",
                                            int sendPort = 11000,
                                            int responsePort = 11001,
                                            int timeoutMs = 180);

struct AbletonOscDevice
{
    int index = -1;
    juce::String name;
};

struct AbletonOscTrack
{
    int index = -1;
    juce::String name;
    std::vector<AbletonOscDevice> devices;
};

struct AbletonOscTopologyResult
{
    bool connected = false;
    std::vector<AbletonOscTrack> tracks;
    juce::String error;
};

// Read-only topology parity path for the future self-contained local mode.
// Every per-track reply must echo the requested track index; otherwise the
// result is rejected rather than mapped by arrival order.
AbletonOscTopologyResult readAbletonOscTopology(const juce::String& host = "127.0.0.1",
                                                int sendPort = 11000,
                                                int responsePort = 11001,
                                                int timeoutMs = 300);

struct AbletonOscParameter
{
    int index = -1;
    juce::String name;
    float value = 0.0f;
    float minimum = 0.0f;
    float maximum = 1.0f;
    bool hasValue = false;
};

struct AbletonOscParameterResult
{
    bool connected = false;
    int trackIndex = -1;
    int deviceIndex = -1;
    juce::String deviceName;
    std::vector<AbletonOscParameter> parameters;
    juce::String error;
};

// Read one exact device's bounded parameter profile. This is deliberately
// separate from the topology call so callers can inspect only the device
// needed for a command instead of paying for every device in a large set.
AbletonOscParameterResult readAbletonOscParameters(const juce::String& host = "127.0.0.1",
                                                   int sendPort = 11000,
                                                   int responsePort = 11001,
                                                   int trackIndex = 0,
                                                   int deviceIndex = 0,
                                                   int timeoutMs = 500);
}
