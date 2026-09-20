#include "LocalAbletonOscProbe.h"
#include "LocalAbletonOscProtocol.h"
#include "LocalAbletonOscWriter.h"

#include <juce_core/juce_core.h>

#include <atomic>
#include "TestCheck.h"
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <thread>
#include <vector>

namespace
{
void appendPaddedString(std::vector<std::uint8_t>& bytes, const char* value)
{
    const auto start = bytes.size();
    while (*value != '\0') bytes.push_back(static_cast<std::uint8_t>(*value++));
    bytes.push_back(0);
    while ((bytes.size() - start) % 4 != 0) bytes.push_back(0);
}

void appendInt(std::vector<std::uint8_t>& bytes, std::int32_t value)
{
    const auto raw = static_cast<std::uint32_t>(value);
    bytes.push_back(static_cast<std::uint8_t>(raw >> 24));
    bytes.push_back(static_cast<std::uint8_t>(raw >> 16));
    bytes.push_back(static_cast<std::uint8_t>(raw >> 8));
    bytes.push_back(static_cast<std::uint8_t>(raw));
}

void appendFloat(std::vector<std::uint8_t>& bytes, float value)
{
    std::uint32_t raw = 0;
    std::memcpy(&raw, &value, sizeof(raw));
    bytes.push_back(static_cast<std::uint8_t>(raw >> 24));
    bytes.push_back(static_cast<std::uint8_t>(raw >> 16));
    bytes.push_back(static_cast<std::uint8_t>(raw >> 8));
    bytes.push_back(static_cast<std::uint8_t>(raw));
}

std::vector<std::uint8_t> countReply()
{
    std::vector<std::uint8_t> bytes;
    appendPaddedString(bytes, "/live/song/get/num_tracks");
    appendPaddedString(bytes, ",i");
    appendInt(bytes, 4);
    return bytes;
}

std::vector<std::uint8_t> namesReply()
{
    std::vector<std::uint8_t> bytes;
    appendPaddedString(bytes, "/live/song/get/track_names");
    appendPaddedString(bytes, ",ssss");
    appendPaddedString(bytes, "1-MIDI");
    appendPaddedString(bytes, "2-MIDI");
    appendPaddedString(bytes, "3-Audio");
    appendPaddedString(bytes, "4-Audio");
    return bytes;
}

std::vector<std::uint8_t> deviceCountReply(int trackIndex)
{
    std::vector<std::uint8_t> bytes;
    appendPaddedString(bytes, "/live/track/get/num_devices");
    appendPaddedString(bytes, ",ii");
    appendInt(bytes, trackIndex);
    appendInt(bytes, trackIndex == 3 ? 2 : 0);
    return bytes;
}

std::vector<std::uint8_t> deviceNamesReply(int trackIndex)
{
    std::vector<std::uint8_t> bytes;
    appendPaddedString(bytes, "/live/track/get/devices/name");
    if (trackIndex == 3)
    {
        appendPaddedString(bytes, ",iss");
        appendInt(bytes, trackIndex);
        appendPaddedString(bytes, "EQ Eight");
        appendPaddedString(bytes, "Glue Compressor");
    }
    else
    {
        appendPaddedString(bytes, ",i");
        appendInt(bytes, trackIndex);
    }
    return bytes;
}

std::vector<std::uint8_t> parameterNamesReply(int trackIndex, int deviceIndex)
{
    std::vector<std::uint8_t> bytes;
    appendPaddedString(bytes, "/live/device/get/parameters/name");
    appendPaddedString(bytes, ",iiss");
    appendInt(bytes, trackIndex);
    appendInt(bytes, deviceIndex);
    appendPaddedString(bytes, "Output");
    appendPaddedString(bytes, "1 Gain A");
    return bytes;
}

std::vector<std::uint8_t> parameterValuesReply(const char* address, int trackIndex, int deviceIndex,
                                               float first, float second)
{
    std::vector<std::uint8_t> bytes;
    appendPaddedString(bytes, address);
    appendPaddedString(bytes, ",iiff");
    appendInt(bytes, trackIndex);
    appendInt(bytes, deviceIndex);
    appendFloat(bytes, first);
    appendFloat(bytes, second);
    return bytes;
}

std::vector<std::uint8_t> deviceNameReply(int trackIndex, int deviceIndex)
{
    std::vector<std::uint8_t> bytes;
    appendPaddedString(bytes, "/live/device/get/name");
    appendPaddedString(bytes, ",iis");
    appendInt(bytes, trackIndex);
    appendInt(bytes, deviceIndex);
    appendPaddedString(bytes, "EQ Eight");
    return bytes;
}
}

int main()
{
    // A second owner of the documented response port must block the direct
    // fallback, even though JUCE normally creates reusable UDP sockets.
    juce::DatagramSocket owner(false);
    KENN_TEST_CHECK(owner.bindToPort(0, "127.0.0.1"));
    const auto ownedPort = owner.getBoundPort();
    KENN_TEST_CHECK(ownedPort > 0);
    const auto blocked = kenn::probeAbletonOscDirect("127.0.0.1", 1, ownedPort, 50);
    KENN_TEST_CHECK(!blocked.connected);
    KENN_TEST_CHECK(blocked.error.contains("could not claim response port"));

    juce::DatagramSocket fakeAbleton(false);
    KENN_TEST_CHECK(fakeAbleton.bindToPort(0, "127.0.0.1"));
    const auto fakePort = fakeAbleton.getBoundPort();
    KENN_TEST_CHECK(fakePort > 0);

    std::atomic<bool> stop { false };
    std::atomic<float> gainValue { -3.0f };
    std::thread fakeServer([&]
    {
        std::vector<char> request(65507);
        while (!stop.load())
        {
            if (fakeAbleton.waitUntilReady(true, 500) <= 0) continue;
            juce::String sender;
            int senderPort = 0;
            const auto length = fakeAbleton.read(request.data(), static_cast<int>(request.size()), false, sender, senderPort);
            if (length <= 0) continue;
            kenn::osc::Message message;
            if (!kenn::osc::decodeMessage(std::span<const std::uint8_t>(reinterpret_cast<const std::uint8_t*>(request.data()), static_cast<std::size_t>(length)), message)) continue;
            std::vector<std::uint8_t> reply;
            if (message.address == "/live/song/get/num_tracks") reply = countReply();
            else if (message.address == "/live/song/get/track_names") reply = namesReply();
            else if (message.address == "/live/track/get/num_devices"
                     && !message.arguments.empty()
                     && message.arguments.front().kind == kenn::osc::ArgumentKind::integer)
                reply = deviceCountReply(message.arguments.front().integer);
            else if (message.address == "/live/track/get/devices/name"
                     && !message.arguments.empty()
                     && message.arguments.front().kind == kenn::osc::ArgumentKind::integer)
                reply = deviceNamesReply(message.arguments.front().integer);
            else if (message.address == "/live/device/get/parameters/name"
                     && message.arguments.size() >= 2
                     && message.arguments[0].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[1].kind == kenn::osc::ArgumentKind::integer)
                reply = parameterNamesReply(message.arguments[0].integer, message.arguments[1].integer);
            else if (message.address == "/live/device/get/parameters/value"
                     && message.arguments.size() >= 2
                     && message.arguments[0].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[1].kind == kenn::osc::ArgumentKind::integer)
                reply = parameterValuesReply(message.address.c_str(), message.arguments[0].integer, message.arguments[1].integer, 0.0f, gainValue.load());
            else if (message.address == "/live/device/get/parameters/min"
                     && message.arguments.size() >= 2
                     && message.arguments[0].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[1].kind == kenn::osc::ArgumentKind::integer)
                reply = parameterValuesReply(message.address.c_str(), message.arguments[0].integer, message.arguments[1].integer, -1.0f, -12.0f);
            else if (message.address == "/live/device/get/parameters/max"
                     && message.arguments.size() >= 2
                     && message.arguments[0].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[1].kind == kenn::osc::ArgumentKind::integer)
                reply = parameterValuesReply(message.address.c_str(), message.arguments[0].integer, message.arguments[1].integer, 1.0f, 12.0f);
            else if (message.address == "/live/device/get/name"
                     && message.arguments.size() >= 2
                     && message.arguments[0].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[1].kind == kenn::osc::ArgumentKind::integer)
                reply = deviceNameReply(message.arguments[0].integer, message.arguments[1].integer);
            else if (message.address == "/live/device/set/parameter/value"
                     && message.arguments.size() >= 4
                     && message.arguments[0].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[1].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[2].kind == kenn::osc::ArgumentKind::integer
                     && message.arguments[3].kind == kenn::osc::ArgumentKind::floating
                     && message.arguments[0].integer == 3
                     && message.arguments[1].integer == 0
                     && message.arguments[2].integer == 1)
            {
                gainValue.store(message.arguments[3].floating);
                continue;
            }
            else
                continue;
            fakeAbleton.write(sender, senderPort, reply.data(), static_cast<int>(reply.size()));
        }
    });

    const auto result = kenn::probeAbletonOscDirect("127.0.0.1", fakePort, 0, 700);
    KENN_TEST_CHECK(result.connected);
    KENN_TEST_CHECK(result.trackCount == 4);
    KENN_TEST_CHECK(result.trackNames.size() == 4);
    KENN_TEST_CHECK(result.trackNames[3] == "4-Audio");

    const auto topology = kenn::readAbletonOscTopology("127.0.0.1", fakePort, 0, 700);
    if (!topology.connected) std::cerr << "DIAG topology err=" << topology.error << std::endl;
    KENN_TEST_CHECK(topology.connected);
    KENN_TEST_CHECK(topology.tracks.size() == 4);
    KENN_TEST_CHECK(topology.tracks[3].name == "4-Audio");
    KENN_TEST_CHECK(topology.tracks[3].devices.size() == 2);
    KENN_TEST_CHECK(topology.tracks[3].devices[0].name == "EQ Eight");
    KENN_TEST_CHECK(topology.tracks[3].devices[1].name == "Glue Compressor");
    const auto parameters = kenn::readAbletonOscParameters("127.0.0.1", fakePort, 0, 3, 0, 700);
    if (!parameters.connected) std::cerr << "DIAG parameters err=" << parameters.error << std::endl;
    KENN_TEST_CHECK(parameters.connected);
    KENN_TEST_CHECK(parameters.deviceName == "EQ Eight");
    KENN_TEST_CHECK(parameters.parameters.size() == 2);
    KENN_TEST_CHECK(parameters.parameters[0].name == "Output");
    KENN_TEST_CHECK(parameters.parameters[0].hasValue);
    KENN_TEST_CHECK(parameters.parameters[0].value == 0.0f);
    KENN_TEST_CHECK(parameters.parameters[1].name == "1 Gain A");
    KENN_TEST_CHECK(parameters.parameters[1].value == -3.0f);
    KENN_TEST_CHECK(parameters.parameters[1].minimum == -12.0f);
    KENN_TEST_CHECK(parameters.parameters[1].maximum == 12.0f);
    const auto mutation = kenn::setAbletonOscParameterWithReadback(
        "127.0.0.1", fakePort, 0, 3, 0, 1, "EQ Eight", "1 Gain A", -3.0, -6.0, 0.0005, 700);
    KENN_TEST_CHECK(mutation.sent && mutation.verified);
    KENN_TEST_CHECK(mutation.beforeValue == -3.0 && mutation.afterValue == -6.0);
    const auto stale = kenn::setAbletonOscParameterWithReadback(
        "127.0.0.1", fakePort, 0, 3, 0, 1, "EQ Eight", "1 Gain A", -3.0, -9.0, 0.0005, 700);
    KENN_TEST_CHECK(!stale.sent && !stale.verified);
    KENN_TEST_CHECK(stale.error.containsIgnoreCase("stale"));

    // Bounded round-trip latency measurement against the same loopback
    // fixture. This measures the C++ direct-OSC layer only (no real Ableton,
    // no companion, no network beyond localhost) and is meant to be compared
    // against the Python-side batched-read measurements in the state doc.
    //
    // Deliberately a single timed call per operation, not a repeated hot
    // loop: AbletonOSC's wire protocol has no request/response correlation
    // id, and repeatedly rebinding a fresh ephemeral response port back to
    // back against this same-process fake server was found to occasionally
    // let a still-in-flight reply from one exchange be misread as belonging
    // to the next one, which is a fire-and-forget-UDP hazard in the test
    // fixture rather than something a single real user-triggered inspection
    // (the only way this fallback is actually invoked) would hit.
    const auto timeCall = [&](const char* label, auto&& call) -> double
    {
        const auto started = std::chrono::steady_clock::now();
        call();
        const auto elapsedUs = std::chrono::duration<double, std::micro>(
            std::chrono::steady_clock::now() - started).count();
        std::cout << "  " << label << ": " << std::fixed << std::setprecision(1)
                   << elapsedUs << " us (" << (elapsedUs / 1000.0) << " ms)" << std::endl;
        return elapsedUs;
    };

    std::cout << "[TestLocalAbletonOscProbe] loopback round-trip latency:" << std::endl;
    const auto probeUs = timeCall("probeAbletonOscDirect (count+names)", [&]
    {
        const auto r = kenn::probeAbletonOscDirect("127.0.0.1", fakePort, 0, 700);
        KENN_TEST_CHECK(r.connected);
    });
    const auto topologyUs = timeCall("readAbletonOscTopology (4 tracks)", [&]
    {
        const auto r = kenn::readAbletonOscTopology("127.0.0.1", fakePort, 0, 700);
        KENN_TEST_CHECK(r.connected);
    });
    const auto parametersUs = timeCall("readAbletonOscParameters (1 device)", [&]
    {
        const auto r = kenn::readAbletonOscParameters("127.0.0.1", fakePort, 0, 3, 0, 700);
        KENN_TEST_CHECK(r.connected);
    });
    // Sanity bound only, not a tight performance assertion: exchangeQueries
    // resends whatever is still missing once if a read-only reply is lost,
    // so an unlucky call can legitimately take close to two 700 ms windows
    // before succeeding. This bound only needs to catch a call that never
    // completes at all.
    KENN_TEST_CHECK(probeUs < 2000000.0 && topologyUs < 2000000.0 && parametersUs < 2000000.0);

    stop.store(true);
    fakeServer.join();
    std::cout << "Local AbletonOSC probe: loopback read-only count/name/topology/parameter exchange passed" << std::endl;
    return 0;
}
