#pragma once

#include "LocalCommandLanguage.h"

#include <string>
#include <vector>

namespace kenn
{

struct LocalLiveDevice
{
    int index = -1;
    std::string name;
};

struct LocalLiveTrack
{
    int index = -1;
    std::string name;
    std::vector<LocalLiveDevice> devices;
};

struct LocalLiveTopology
{
    bool connected = false;
    std::vector<LocalLiveTrack> tracks;
    std::string error;
};

struct LocalLiveParameter
{
    int index = -1;
    std::string name;
    double value = 0.0;
    double minimum = 0.0;
    double maximum = 1.0;
    bool hasValue = false;
};

struct LocalLiveParameterSnapshot
{
    bool connected = false;
    int trackIndex = -1;
    int deviceIndex = -1;
    std::string deviceName;
    std::vector<LocalLiveParameter> parameters;
    std::string error;
};

// A deterministic, read-only plan candidate. This deliberately stops before
// confirmation-token issuance, OSC mutation, readback, or undo.
struct LocalLivePlan
{
    bool ready = false;
    std::string schema = "kenn.ableton_local_plan.v1";
    std::string action;
    std::string clarification;
    int trackIndex = -1;
    std::string trackName;
    std::string deviceName;
    std::string parameterName;
    int deviceIndex = -1;
    int insertionIndex = -1;
    int parameterIndex = -1;
    double beforeValue = 0.0;
    double afterValue = 0.0;
    double parameterMinimum = 0.0;
    double parameterMaximum = 1.0;
    bool relative = false;
    bool hasParameterValue = false;
    std::vector<LocalLiveDevice> beforeDevices;
    std::vector<LocalLiveDevice> afterDevices;
    std::string beforeDeviceFingerprint;
};

// Translate the bounded local language result against a fresh, read-only
// topology snapshot. Currently qualified for append-only device insertion;
// every other action remains companion-owned until its complete snapshot and
// safety contract has a C++ parity test.
LocalLivePlan makeLocalLivePlan(const LocalCommandIntent& intent,
                                const LocalLiveTopology& topology);

// Resolve one exact parameter against a separately acquired device snapshot.
// The result remains a non-executable read/plan object; the companion owns all
// confirmation, transport, readback, and undo semantics.
LocalLivePlan makeLocalLiveParameterPlan(const LocalCommandIntent& intent,
                                         const LocalLiveTopology& topology,
                                         const LocalLiveParameterSnapshot& parameters);

} // namespace kenn
