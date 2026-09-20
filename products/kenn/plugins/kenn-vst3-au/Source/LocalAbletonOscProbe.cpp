#include "LocalAbletonOscProbe.h"
#include "LocalAbletonOscProtocol.h"

#include <chrono>
#include <optional>
#include <vector>

#if defined(__APPLE__) || defined(__linux__) || defined(__FreeBSD__)
#include <sys/socket.h>
#endif

namespace kenn
{
namespace
{
constexpr auto trackCountAddress = "/live/song/get/num_tracks";
constexpr auto trackNamesAddress = "/live/song/get/track_names";
constexpr auto deviceCountAddress = "/live/track/get/num_devices";
constexpr auto deviceNamesAddress = "/live/track/get/devices/name";
constexpr auto deviceNameAddress = "/live/device/get/name";
constexpr auto parameterNamesAddress = "/live/device/get/parameters/name";
constexpr auto parameterValuesAddress = "/live/device/get/parameters/value";
constexpr auto parameterMinimumsAddress = "/live/device/get/parameters/min";
constexpr auto parameterMaximumsAddress = "/live/device/get/parameters/max";

struct Query
{
    std::string address;
    int trackIndex = -1;
    int deviceIndex = -1;
};

bool disablePortReuse(juce::DatagramSocket& socket)
{
#if defined(__APPLE__) || defined(__linux__) || defined(__FreeBSD__)
    const int disabled = 0;
    const auto handle = socket.getRawSocketHandle();
    return handle >= 0
        && setsockopt(handle, SOL_SOCKET, SO_REUSEADDR, &disabled, sizeof(disabled)) == 0
#if defined(SO_REUSEPORT)
        && setsockopt(handle, SOL_SOCKET, SO_REUSEPORT, &disabled, sizeof(disabled)) == 0
#endif
        ;
#else
    // The JUCE target is currently qualified on macOS. Other platforms use
    // the JUCE socket implementation until their port-ownership semantics
    // receive an equivalent qualification.
    juce::ignoreUnused(socket);
    return true;
#endif
}

bool sendQuery(juce::DatagramSocket& socket, const juce::String& host, int sendPort, const Query& query)
{
    std::vector<osc::Argument> arguments;
    if (query.trackIndex >= 0)
    {
        osc::Argument argument;
        argument.kind = osc::ArgumentKind::integer;
        argument.integer = query.trackIndex;
        arguments.push_back(argument);
    }
    if (query.deviceIndex >= 0)
    {
        osc::Argument argument;
        argument.kind = osc::ArgumentKind::integer;
        argument.integer = query.deviceIndex;
        arguments.push_back(argument);
    }
    const auto packet = osc::encodeMessage(query.address, arguments);
    return !packet.empty() && socket.write(host, sendPort, packet.data(), static_cast<int>(packet.size())) > 0;
}

// Reads until every query has a response or the deadline passes, matching
// each incoming message to the first still-empty query slot whose address
// and echoed track/device index agree. Read-only OSC has no delivery
// guarantee, so a reply can occasionally be lost or arrive late even on
// loopback; the caller is expected to resend whatever is still missing
// rather than treat one lost datagram as a hard failure.
void collectResponses(juce::DatagramSocket& socket,
                      const std::vector<Query>& queries,
                      std::vector<std::optional<osc::Message>>& responses,
                      std::chrono::steady_clock::time_point deadline)
{
    std::vector<std::uint8_t> buffer(65507);
    while (std::chrono::steady_clock::now() < deadline)
    {
        bool complete = true;
        for (const auto& response : responses) complete = complete && response.has_value();
        if (complete) break;

        const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
        if (socket.waitUntilReady(true, juce::jmax(1, static_cast<int>(remaining))) <= 0) break;
        juce::String sender;
        int senderPort = 0;
        const auto length = socket.read(buffer.data(), static_cast<int>(buffer.size()), false, sender, senderPort);
        if (length <= 0) continue;
        osc::Message message;
        if (!osc::decodeMessage(std::span<const std::uint8_t>(buffer.data(), static_cast<std::size_t>(length)), message)) continue;

        for (std::size_t index = 0; index < queries.size(); ++index)
        {
            if (responses[index].has_value() || message.address != queries[index].address) continue;
            if (queries[index].trackIndex >= 0)
            {
                if (message.arguments.empty()
                    || message.arguments.front().kind != osc::ArgumentKind::integer
                    || message.arguments.front().integer != queries[index].trackIndex)
                    continue;
            }
            if (queries[index].deviceIndex >= 0)
            {
                if (message.arguments.size() < 2
                    || message.arguments[1].kind != osc::ArgumentKind::integer
                    || message.arguments[1].integer != queries[index].deviceIndex)
                    continue;
            }
            responses[index] = std::move(message);
            break;
        }
    }
}

std::vector<std::optional<osc::Message>> exchangeQueries(juce::DatagramSocket& socket,
                                                          const juce::String& host,
                                                          int sendPort,
                                                          const std::vector<Query>& queries,
                                                          int timeoutMs)
{
    std::vector<std::optional<osc::Message>> responses(queries.size());
    for (const auto& query : queries)
        if (!sendQuery(socket, host, sendPort, query)) return {};

    const auto boundedTimeoutMs = juce::jmax(20, timeoutMs);
    collectResponses(socket, queries, responses,
                      std::chrono::steady_clock::now() + std::chrono::milliseconds(boundedTimeoutMs));

    // A single missing read-only reply on an otherwise-idle loopback socket
    // is most often a one-off delivery hiccup, not evidence that Live or
    // AbletonOSC actually failed to answer. Resend exactly the still-missing
    // queries once more (idempotent; nothing already answered is repeated)
    // before reporting an incomplete snapshot.
    std::vector<std::size_t> missing;
    for (std::size_t index = 0; index < responses.size(); ++index)
        if (!responses[index].has_value()) missing.push_back(index);
    if (!missing.empty())
    {
        for (const auto index : missing)
            if (!sendQuery(socket, host, sendPort, queries[index])) return responses;
        collectResponses(socket, queries, responses,
                          std::chrono::steady_clock::now() + std::chrono::milliseconds(boundedTimeoutMs));
    }
    return responses;
}

bool firstInteger(const osc::Message& message, int& value)
{
    for (const auto& argument : message.arguments)
    {
        if (argument.kind == osc::ArgumentKind::integer)
        {
            value = argument.integer;
            return true;
        }
    }
    return false;
}

bool echoedInteger(const osc::Message& message, int expected, int& value)
{
    if (message.arguments.size() < 2
        || message.arguments[0].kind != osc::ArgumentKind::integer
        || message.arguments[0].integer != expected
        || message.arguments[1].kind != osc::ArgumentKind::integer)
        return false;
    value = message.arguments[1].integer;
    return true;
}

bool echoedPair(const osc::Message& message, int expectedTrack, int expectedDevice)
{
    return message.arguments.size() >= 2
        && message.arguments[0].kind == osc::ArgumentKind::integer
        && message.arguments[0].integer == expectedTrack
        && message.arguments[1].kind == osc::ArgumentKind::integer
        && message.arguments[1].integer == expectedDevice;
}

std::vector<juce::String> stringsAfter(const osc::Message& message, std::size_t prefix)
{
    std::vector<juce::String> values;
    if (message.arguments.size() < prefix) return values;
    for (std::size_t index = prefix; index < message.arguments.size(); ++index)
        if (message.arguments[index].kind == osc::ArgumentKind::string)
            values.emplace_back(message.arguments[index].string);
    return values;
}

std::vector<float> numbersAfter(const osc::Message& message, std::size_t prefix)
{
    std::vector<float> values;
    if (message.arguments.size() < prefix) return values;
    for (std::size_t index = prefix; index < message.arguments.size(); ++index)
    {
        const auto& argument = message.arguments[index];
        if (argument.kind == osc::ArgumentKind::floating)
            values.push_back(argument.floating);
        else if (argument.kind == osc::ArgumentKind::integer)
            values.push_back(static_cast<float>(argument.integer));
    }
    return values;
}
}

AbletonOscProbeResult probeAbletonOscDirect(const juce::String& host, int sendPort, int responsePort, int timeoutMs)
{
    AbletonOscProbeResult result;
    juce::DatagramSocket socket(false);
    if (!disablePortReuse(socket) || !socket.bindToPort(responsePort, "127.0.0.1"))
    {
        result.error = "AbletonOSC direct probe could not claim response port " + juce::String(responsePort) + ".";
        return result;
    }

    const auto countPacket = osc::encodeNoArgumentMessage(trackCountAddress);
    const auto namesPacket = osc::encodeNoArgumentMessage(trackNamesAddress);
    if (countPacket.empty() || namesPacket.empty()
        || socket.write(host, sendPort, countPacket.data(), static_cast<int>(countPacket.size())) <= 0
        || socket.write(host, sendPort, namesPacket.data(), static_cast<int>(namesPacket.size())) <= 0)
    {
        result.error = "AbletonOSC direct probe could not send standard read-only queries.";
        return result;
    }

    bool gotCount = false;
    bool gotNames = false;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(juce::jmax(20, timeoutMs));
    std::vector<std::uint8_t> buffer(65507);
    while ((!gotCount || !gotNames) && std::chrono::steady_clock::now() < deadline)
    {
        const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
        if (socket.waitUntilReady(true, juce::jmax(1, static_cast<int>(remaining))) <= 0) break;
        juce::String sender;
        int senderPort = 0;
        const auto length = socket.read(buffer.data(), static_cast<int>(buffer.size()), false, sender, senderPort);
        if (length <= 0) continue;
        osc::Message message;
        if (!osc::decodeMessage(std::span<const std::uint8_t>(buffer.data(), static_cast<std::size_t>(length)), message)) continue;
        if (message.address == trackCountAddress && !gotCount)
        {
            gotCount = firstInteger(message, result.trackCount) && result.trackCount >= 0 && result.trackCount <= 1024;
        }
        else if (message.address == trackNamesAddress && !gotNames)
        {
            for (const auto& argument : message.arguments)
                if (argument.kind == osc::ArgumentKind::string) result.trackNames.add(juce::String(argument.string));
            gotNames = !result.trackNames.isEmpty();
        }
    }

    if (!gotCount || !gotNames || result.trackNames.size() < result.trackCount)
    {
        result.error = "AbletonOSC direct probe returned an incomplete track snapshot.";
        return result;
    }
    if (result.trackNames.size() > result.trackCount)
        result.trackNames.removeRange(result.trackCount, result.trackNames.size() - result.trackCount);
    result.connected = true;
    return result;
}

AbletonOscTopologyResult readAbletonOscTopology(const juce::String& host, int sendPort, int responsePort, int timeoutMs)
{
    AbletonOscTopologyResult result;
    juce::DatagramSocket socket(false);
    if (!disablePortReuse(socket) || !socket.bindToPort(responsePort, "127.0.0.1"))
    {
        result.error = "AbletonOSC topology probe could not claim response port " + juce::String(responsePort) + ".";
        return result;
    }

    const auto header = exchangeQueries(socket, host, sendPort,
                                         { { trackCountAddress, -1 }, { trackNamesAddress, -1 } }, timeoutMs);
    if (header.size() != 2 || !header[0].has_value() || !header[1].has_value())
    {
        result.error = "AbletonOSC topology probe returned no complete song header.";
        return result;
    }
    int trackCount = -1;
    if (!firstInteger(*header[0], trackCount) || trackCount < 0 || trackCount > 1024)
    {
        result.error = "AbletonOSC topology probe returned an invalid track count.";
        return result;
    }

    std::vector<juce::String> names;
    for (const auto& argument : header[1]->arguments)
        if (argument.kind == osc::ArgumentKind::string) names.emplace_back(argument.string);
    if (static_cast<int>(names.size()) != trackCount)
    {
        result.error = "AbletonOSC topology probe returned an incomplete track-name list.";
        return result;
    }

    std::vector<Query> queries;
    queries.reserve(static_cast<std::size_t>(trackCount) * 2u);
    for (int trackIndex = 0; trackIndex < trackCount; ++trackIndex)
    {
        queries.push_back({ deviceCountAddress, trackIndex, -1 });
        queries.push_back({ deviceNamesAddress, trackIndex, -1 });
    }
    const auto topology = exchangeQueries(socket, host, sendPort, queries, timeoutMs);
    if (topology.size() != queries.size())
    {
        result.error = "AbletonOSC topology probe could not send its track queries.";
        return result;
    }

    for (int trackIndex = 0; trackIndex < trackCount; ++trackIndex)
    {
        const auto& countResponse = topology[static_cast<std::size_t>(trackIndex) * 2u];
        const auto& namesResponse = topology[static_cast<std::size_t>(trackIndex) * 2u + 1u];
        if (!countResponse.has_value() || !namesResponse.has_value())
        {
            result.error = "AbletonOSC topology probe returned an incomplete device response for track "
                + juce::String(trackIndex) + ".";
            return result;
        }
        int deviceCount = -1;
        if (!echoedInteger(*countResponse, trackIndex, deviceCount) || deviceCount < 0 || deviceCount > 1024)
        {
            result.error = "AbletonOSC topology probe returned an invalid device count for track "
                + juce::String(trackIndex) + ".";
            return result;
        }
        std::vector<juce::String> deviceNames;
        for (std::size_t argumentIndex = 1; argumentIndex < namesResponse->arguments.size(); ++argumentIndex)
            if (namesResponse->arguments[argumentIndex].kind == osc::ArgumentKind::string)
                deviceNames.emplace_back(namesResponse->arguments[argumentIndex].string);
        if (static_cast<int>(deviceNames.size()) != deviceCount)
        {
            result.error = "AbletonOSC topology probe returned an incomplete device-name list for track "
                + juce::String(trackIndex) + ".";
            return result;
        }
        AbletonOscTrack track;
        track.index = trackIndex;
        track.name = names[static_cast<std::size_t>(trackIndex)];
        for (int deviceIndex = 0; deviceIndex < deviceCount; ++deviceIndex)
            track.devices.push_back({ deviceIndex, deviceNames[static_cast<std::size_t>(deviceIndex)] });
        result.tracks.push_back(std::move(track));
    }
    result.connected = true;
    return result;
}

AbletonOscParameterResult readAbletonOscParameters(const juce::String& host,
                                                   int sendPort,
                                                   int responsePort,
                                                   int trackIndex,
                                                   int deviceIndex,
                                                   int timeoutMs)
{
    AbletonOscParameterResult result;
    result.trackIndex = trackIndex;
    result.deviceIndex = deviceIndex;
    if (trackIndex < 0 || deviceIndex < 0)
    {
        result.error = "AbletonOSC parameter probe requires non-negative track and device indices.";
        return result;
    }

    juce::DatagramSocket socket(false);
    if (!disablePortReuse(socket) || !socket.bindToPort(responsePort, "127.0.0.1"))
    {
        result.error = "AbletonOSC parameter probe could not claim response port " + juce::String(responsePort) + ".";
        return result;
    }

    const std::vector<Query> queries = {
        { parameterNamesAddress, trackIndex, deviceIndex },
        { parameterValuesAddress, trackIndex, deviceIndex },
        { parameterMinimumsAddress, trackIndex, deviceIndex },
        { parameterMaximumsAddress, trackIndex, deviceIndex },
        { deviceNameAddress, trackIndex, deviceIndex },
    };
    const auto responses = exchangeQueries(socket, host, sendPort, queries, timeoutMs);
    if (responses.size() != queries.size()
        || !responses[0].has_value() || !responses[1].has_value()
        || !responses[2].has_value() || !responses[3].has_value()
        || !responses[4].has_value())
    {
        result.error = "AbletonOSC parameter probe returned an incomplete device response.";
        return result;
    }
    for (const auto& response : responses)
    {
        if (!echoedPair(*response, trackIndex, deviceIndex))
        {
            result.error = "AbletonOSC parameter probe returned a mismatched device identity.";
            return result;
        }
    }

    const auto names = stringsAfter(*responses[0], 2);
    const auto values = numbersAfter(*responses[1], 2);
    const auto minimums = numbersAfter(*responses[2], 2);
    const auto maximums = numbersAfter(*responses[3], 2);
    const auto deviceNames = stringsAfter(*responses[4], 2);
    if (deviceNames.size() != 1 || names.size() != minimums.size() || names.size() != maximums.size()
        || values.size() > names.size())
    {
        result.error = "AbletonOSC parameter probe returned inconsistent parameter lists.";
        return result;
    }

    result.deviceName = deviceNames.front();
    result.parameters.reserve(names.size());
    for (std::size_t index = 0; index < names.size(); ++index)
    {
        AbletonOscParameter parameter;
        parameter.index = static_cast<int>(index);
        parameter.name = names[index];
        parameter.minimum = minimums[index];
        parameter.maximum = maximums[index];
        if (index < values.size())
        {
            parameter.value = values[index];
            parameter.hasValue = true;
        }
        result.parameters.push_back(std::move(parameter));
    }
    result.connected = true;
    return result;
}
}
