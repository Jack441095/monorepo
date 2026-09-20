#pragma once

#include <string>
#include <string_view>

namespace kenn
{

struct LocalCommandIntent
{
    std::string action;
    std::string deviceName;
    std::string parameterName;
    std::string unit;
    std::string canonical;
    std::string clarification;
    std::string newTrackName;
    int trackNumber = 0; // User-facing Live number; zero means unresolved.
    double value = 0.0;
    bool hasValue = false;
    bool relative = false;
    bool recognized = false;
    bool recipe = false;
};

// Pure, allocation-bounded language extraction for the hosted plug-in UI.
// This function never touches audio, Live, OSC, the network, or a model.
LocalCommandIntent parseLocalCommand(std::string_view command);

} // namespace kenn
