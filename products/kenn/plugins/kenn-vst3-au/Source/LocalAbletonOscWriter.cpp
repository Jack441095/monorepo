#include "LocalAbletonOscWriter.h"

#include "LocalAbletonOscProbe.h"
#include "LocalAbletonOscProtocol.h"

#include <array>
#include <cmath>
#include <vector>

#if defined(__APPLE__) || defined(__linux__) || defined(__FreeBSD__)
#include <sys/socket.h>
#endif

namespace kenn
{
namespace
{
bool claimResponsePort(juce::DatagramSocket& socket, int responsePort)
{
#if defined(__APPLE__) || defined(__linux__) || defined(__FreeBSD__)
    const int disabled = 0;
    const auto handle = socket.getRawSocketHandle();
    if (handle < 0 || setsockopt(handle, SOL_SOCKET, SO_REUSEADDR, &disabled, sizeof(disabled)) != 0)
        return false;
#if defined(SO_REUSEPORT)
    if (setsockopt(handle, SOL_SOCKET, SO_REUSEPORT, &disabled, sizeof(disabled)) != 0)
        return false;
#endif
#endif
    return socket.bindToPort(responsePort, "127.0.0.1");
}

bool sendParameterValue(const juce::String& host, int sendPort, int responsePort,
                        int trackIndex, int deviceIndex, int parameterIndex, float value)
{
    juce::DatagramSocket socket(false);
    if (!claimResponsePort(socket, responsePort)) return false;
    kenn::osc::Argument track;
    track.kind = kenn::osc::ArgumentKind::integer;
    track.integer = trackIndex;
    kenn::osc::Argument device;
    device.kind = kenn::osc::ArgumentKind::integer;
    device.integer = deviceIndex;
    kenn::osc::Argument parameter;
    parameter.kind = kenn::osc::ArgumentKind::integer;
    parameter.integer = parameterIndex;
    kenn::osc::Argument requested;
    requested.kind = kenn::osc::ArgumentKind::floating;
    requested.floating = value;
    const std::array<kenn::osc::Argument, 4> arguments { track, device, parameter, requested };
    const auto packet = kenn::osc::encodeMessage("/live/device/set/parameter/value", arguments);
    return !packet.empty()
        && socket.write(host, sendPort, packet.data(), static_cast<int>(packet.size())) > 0;
}
}

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
    double tolerance,
    int timeoutMs)
{
    AbletonOscMutationResult result;
    if (trackIndex < 0 || deviceIndex < 0 || parameterIndex < 0
        || !std::isfinite(expectedBefore) || !std::isfinite(requestedValue)
        || !std::isfinite(tolerance) || tolerance < 0.0)
    {
        result.error = "The guarded C++ parameter write received invalid identity or numeric bounds.";
        return result;
    }

    const auto before = readAbletonOscParameters(host, sendPort, responsePort,
                                                 trackIndex, deviceIndex, timeoutMs);
    if (!before.connected || before.deviceName != deviceName)
    {
        result.error = before.error.isNotEmpty() ? before.error
            : "The guarded C++ parameter write found a different device identity.";
        return result;
    }
    const AbletonOscParameter* matched = nullptr;
    for (const auto& parameter : before.parameters)
    {
        if (parameter.index == parameterIndex && parameter.name == parameterName)
        {
            matched = &parameter;
            break;
        }
    }
    if (matched == nullptr || !matched->hasValue)
    {
        result.error = "The guarded C++ parameter write could not verify the exact parameter identity/value.";
        return result;
    }
    result.beforeValue = matched->value;
    if (std::abs(static_cast<double>(matched->value) - expectedBefore) > tolerance)
    {
        result.error = "The guarded C++ parameter write was rejected because the target is stale.";
        return result;
    }
    if (requestedValue < static_cast<double>(matched->minimum) - tolerance
        || requestedValue > static_cast<double>(matched->maximum) + tolerance)
    {
        result.error = "The guarded C++ parameter write is outside the current Live parameter range.";
        return result;
    }

    if (!sendParameterValue(host, sendPort, responsePort, trackIndex, deviceIndex,
                            parameterIndex, static_cast<float>(requestedValue)))
    {
        result.error = "The guarded C++ parameter write could not claim the response port or send OSC.";
        return result;
    }
    result.sent = true;

    const auto after = readAbletonOscParameters(host, sendPort, responsePort,
                                                trackIndex, deviceIndex, timeoutMs);
    if (!after.connected || after.deviceName != deviceName)
    {
        result.error = after.error.isNotEmpty() ? after.error
            : "The guarded C++ parameter write lost the exact device identity during readback.";
        return result;
    }
    for (const auto& parameter : after.parameters)
    {
        if (parameter.index == parameterIndex && parameter.name == parameterName && parameter.hasValue)
        {
            result.afterValue = parameter.value;
            result.verified = std::abs(static_cast<double>(parameter.value) - requestedValue) <= tolerance;
            if (!result.verified)
                result.error = "The guarded C++ parameter write was sent but failed readback verification.";
            return result;
        }
    }
    result.error = "The guarded C++ parameter write could not find the exact parameter during readback.";
    return result;
}
}
