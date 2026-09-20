#include "LocalLivePlan.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <functional>
#include <iomanip>
#include <sstream>

#if defined(__APPLE__)
#include <CommonCrypto/CommonDigest.h>
#endif

namespace kenn
{
namespace
{
std::string lower(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

void appendUnicodeEscape(std::string& output, unsigned int codepoint)
{
    auto appendUnit = [&output](unsigned int unit) {
        std::ostringstream escaped;
        escaped << "\\u" << std::hex << std::nouppercase << std::setfill('0') << std::setw(4) << unit;
        output += escaped.str();
    };

    if (codepoint <= 0xffffu)
    {
        appendUnit(codepoint);
        return;
    }
    codepoint -= 0x10000u;
    appendUnit(0xd800u + (codepoint >> 10u));
    appendUnit(0xdc00u + (codepoint & 0x3ffu));
}

std::string jsonEscapeAscii(std::string_view value)
{
    std::string output;
    output.reserve(value.size() + 8u);
    output.push_back('"');
    for (std::size_t index = 0; index < value.size();)
    {
        const auto byte = static_cast<unsigned char>(value[index]);
        if (byte < 0x80u)
        {
            ++index;
            switch (byte)
            {
                case '"': output += "\\\""; break;
                case '\\': output += "\\\\"; break;
                case '\b': output += "\\b"; break;
                case '\f': output += "\\f"; break;
                case '\n': output += "\\n"; break;
                case '\r': output += "\\r"; break;
                case '\t': output += "\\t"; break;
                default:
                    if (byte < 0x20u) appendUnicodeEscape(output, byte);
                    else output.push_back(static_cast<char>(byte));
                    break;
            }
            continue;
        }

        unsigned int codepoint = 0;
        int continuation = 0;
        if (byte >= 0xc2u && byte <= 0xdfu) { codepoint = byte & 0x1fu; continuation = 1; }
        else if (byte >= 0xe0u && byte <= 0xefu) { codepoint = byte & 0x0fu; continuation = 2; }
        else if (byte >= 0xf0u && byte <= 0xf4u) { codepoint = byte & 0x07u; continuation = 3; }
        else
        {
            appendUnicodeEscape(output, 0xfffdu);
            ++index;
            continue;
        }

        bool valid = index + static_cast<std::size_t>(continuation) < value.size();
        for (int offset = 1; valid && offset <= continuation; ++offset)
        {
            const auto next = static_cast<unsigned char>(value[index + static_cast<std::size_t>(offset)]);
            if ((next & 0xc0u) != 0x80u) valid = false;
            else codepoint = (codepoint << 6u) | (next & 0x3fu);
        }
        const auto firstContinuation = continuation > 0
            ? static_cast<unsigned char>(value[index + 1u]) : 0u;
        if (!valid || codepoint > 0x10ffffu || (codepoint >= 0xd800u && codepoint <= 0xdfffu)
            || (byte == 0xe0u && firstContinuation < 0xa0u)
            || (byte == 0xedu && firstContinuation >= 0xa0u)
            || (byte == 0xf0u && firstContinuation < 0x90u)
            || (byte == 0xf4u && firstContinuation >= 0x90u))
        {
            appendUnicodeEscape(output, 0xfffdu);
            ++index;
            continue;
        }
        appendUnicodeEscape(output, codepoint);
        index += static_cast<std::size_t>(continuation + 1);
    }
    output.push_back('"');
    return output;
}

std::string deviceFingerprint(const std::vector<LocalLiveDevice>& devices)
{
    std::string canonical = "[";
    for (std::size_t position = 0; position < devices.size(); ++position)
    {
        if (position != 0) canonical.push_back(',');
        const auto& device = devices[position];
        // Python's sort_keys=True orders these fields as index, name, position.
        canonical += "{\"index\":" + std::to_string(device.index)
            + ",\"name\":" + jsonEscapeAscii(device.name)
            + ",\"position\":" + std::to_string(position) + "}";
    }
    canonical += "]";
#if defined(__APPLE__)
    unsigned char digest[CC_SHA256_DIGEST_LENGTH] = {};
    CC_SHA256(canonical.data(), static_cast<CC_LONG>(canonical.size()), digest);
    std::ostringstream hex;
    hex << std::hex << std::nouppercase << std::setfill('0');
    for (const auto byte : digest) hex << std::setw(2) << static_cast<unsigned int>(byte);
    return hex.str();
#else
    // The shipped plug-in is currently qualified on macOS. Keep non-macOS
    // test builds deterministic while leaving the native SHA-256 authority
    // explicit for the supported platform.
    const auto value = std::hash<std::string>{}(canonical);
    std::ostringstream hex;
    hex << std::hex << std::setfill('0') << std::setw(16) << value;
    return hex.str();
#endif
}

bool isAllowedDevice(const std::string& name)
{
    static constexpr const char* allowed[] = {
        "EQ Eight", "Glue Compressor", "Saturator", "Auto Filter", "Drum Buss"
    };
    return std::any_of(std::begin(allowed), std::end(allowed), [&](const auto* candidate) {
        return lower(candidate) == lower(name);
    });
}
}

LocalLivePlan makeLocalLivePlan(const LocalCommandIntent& intent,
                                const LocalLiveTopology& topology)
{
    LocalLivePlan plan;
    plan.action = intent.action;
    if (!intent.recognized)
    {
        plan.clarification = intent.clarification.empty()
            ? "The local command is not exact enough for a safe plan."
            : intent.clarification;
        return plan;
    }
    if (intent.action != "insert_device")
    {
        plan.clarification = "C++ proposal parity currently supports append-only device insertion; this action remains companion-owned.";
        return plan;
    }
    if (!topology.connected)
    {
        plan.clarification = topology.error.empty()
            ? "AbletonOSC returned no usable topology snapshot."
            : topology.error;
        return plan;
    }
    if (intent.trackNumber <= 0 || intent.trackNumber > static_cast<int>(topology.tracks.size()))
    {
        plan.clarification = "The requested numbered Live track is not present in the fresh topology snapshot.";
        return plan;
    }
    if (!isAllowedDevice(intent.deviceName))
    {
        plan.clarification = "The requested device is not in KENN's append-only allow-list.";
        return plan;
    }

    const auto& track = topology.tracks[static_cast<std::size_t>(intent.trackNumber - 1)];
    if (track.index != intent.trackNumber - 1)
    {
        plan.clarification = "The topology snapshot has a non-contiguous or mismatched track identity.";
        return plan;
    }
    const auto requested = lower(intent.deviceName);
    for (const auto& device : track.devices)
    {
        if (lower(device.name) == requested)
        {
            plan.clarification = "The target track already contains " + intent.deviceName + "; choose the exact existing device instead.";
            return plan;
        }
    }

    plan.ready = true;
    plan.trackIndex = track.index;
    plan.trackName = track.name;
    plan.deviceName = intent.deviceName;
    plan.insertionIndex = static_cast<int>(track.devices.size());
    plan.beforeDevices = track.devices;
    plan.afterDevices = track.devices;
    plan.afterDevices.push_back({ plan.insertionIndex, plan.deviceName });
    plan.beforeDeviceFingerprint = deviceFingerprint(plan.beforeDevices);
    return plan;
}

LocalLivePlan makeLocalLiveParameterPlan(const LocalCommandIntent& intent,
                                         const LocalLiveTopology& topology,
                                         const LocalLiveParameterSnapshot& parameters)
{
    LocalLivePlan plan;
    plan.action = intent.action;
    if (!intent.recognized)
    {
        plan.clarification = intent.clarification.empty()
            ? "The local command is not exact enough for a safe parameter plan."
            : intent.clarification;
        return plan;
    }
    if (intent.action != "set_device_parameter")
    {
        plan.clarification = "C++ parameter planning supports exact existing-device parameter changes only.";
        return plan;
    }
    if (!topology.connected || !parameters.connected)
    {
        plan.clarification = !parameters.error.empty() ? parameters.error
            : (!topology.error.empty() ? topology.error : "AbletonOSC returned no usable parameter snapshot.");
        return plan;
    }
    if (intent.trackNumber <= 0 || intent.trackNumber > static_cast<int>(topology.tracks.size()))
    {
        plan.clarification = "The requested numbered Live track is not present in the fresh topology snapshot.";
        return plan;
    }
    const auto& track = topology.tracks[static_cast<std::size_t>(intent.trackNumber - 1)];
    if (track.index != intent.trackNumber - 1 || parameters.trackIndex != track.index)
    {
        plan.clarification = "The parameter snapshot does not match the requested Live track identity.";
        return plan;
    }

    const auto requestedDevice = lower(intent.deviceName);
    const LocalLiveDevice* matchedDevice = nullptr;
    for (const auto& device : track.devices)
    {
        if (lower(device.name) != requestedDevice) continue;
        if (matchedDevice != nullptr)
        {
            plan.clarification = "The target device name is duplicated; specify an exact device index.";
            return plan;
        }
        matchedDevice = &device;
    }
    if (matchedDevice == nullptr || matchedDevice->index != parameters.deviceIndex
        || lower(parameters.deviceName) != requestedDevice)
    {
        plan.clarification = "The parameter snapshot does not match one unique exact device identity.";
        return plan;
    }

    const auto requestedParameter = lower(intent.parameterName);
    const LocalLiveParameter* matchedParameter = nullptr;
    for (const auto& parameter : parameters.parameters)
    {
        if (lower(parameter.name) != requestedParameter) continue;
        if (matchedParameter != nullptr)
        {
            plan.clarification = "The target parameter name is duplicated; use its exact parameter index.";
            return plan;
        }
        matchedParameter = &parameter;
    }
    if (matchedParameter == nullptr)
    {
        plan.clarification = "The requested parameter is not present in the fresh device snapshot.";
        return plan;
    }
    if (!matchedParameter->hasValue || !std::isfinite(matchedParameter->value)
        || !std::isfinite(matchedParameter->minimum) || !std::isfinite(matchedParameter->maximum)
        || matchedParameter->minimum > matchedParameter->maximum)
    {
        plan.clarification = "The requested parameter has no safe current value or range.";
        return plan;
    }
    const auto after = intent.relative ? matchedParameter->value + intent.value : intent.value;
    if (!std::isfinite(after) || after < matchedParameter->minimum || after > matchedParameter->maximum)
    {
        plan.clarification = "The requested parameter value is outside the exact Live parameter range.";
        return plan;
    }

    plan.ready = true;
    plan.trackIndex = track.index;
    plan.trackName = track.name;
    plan.deviceName = matchedDevice->name;
    plan.deviceIndex = matchedDevice->index;
    plan.parameterName = matchedParameter->name;
    plan.parameterIndex = matchedParameter->index;
    plan.beforeValue = matchedParameter->value;
    plan.afterValue = after;
    plan.parameterMinimum = matchedParameter->minimum;
    plan.parameterMaximum = matchedParameter->maximum;
    plan.relative = intent.relative;
    plan.hasParameterValue = true;
    return plan;
}

} // namespace kenn
