#include "LocalAbletonOscProtocol.h"

#include "TestCheck.h"
#include <cstdint>
#include <iostream>
#include <vector>

namespace
{
void append32(std::vector<std::uint8_t>& bytes, std::uint32_t value)
{
    bytes.push_back(static_cast<std::uint8_t>(value >> 24));
    bytes.push_back(static_cast<std::uint8_t>(value >> 16));
    bytes.push_back(static_cast<std::uint8_t>(value >> 8));
    bytes.push_back(static_cast<std::uint8_t>(value));
}

void appendString(std::vector<std::uint8_t>& bytes, const char* value)
{
    const auto start = bytes.size();
    while (*value != '\0') bytes.push_back(static_cast<std::uint8_t>(*value++));
    bytes.push_back(0);
    while ((bytes.size() - start) % 4 != 0) bytes.push_back(0);
}
}

int main()
{
    const auto query = kenn::osc::encodeNoArgumentMessage("/live/song/get/num_tracks");
    KENN_TEST_CHECK(!query.empty());
    kenn::osc::Message decoded;
    KENN_TEST_CHECK(kenn::osc::decodeMessage(query, decoded));
    KENN_TEST_CHECK(decoded.address == "/live/song/get/num_tracks");
    KENN_TEST_CHECK(decoded.arguments.empty());

    std::vector<std::uint8_t> countReply;
    appendString(countReply, "/live/song/get/num_tracks");
    appendString(countReply, ",i");
    append32(countReply, 4);
    KENN_TEST_CHECK(kenn::osc::decodeMessage(countReply, decoded));
    KENN_TEST_CHECK(decoded.arguments.size() == 1);
    KENN_TEST_CHECK(decoded.arguments.front().kind == kenn::osc::ArgumentKind::integer);
    KENN_TEST_CHECK(decoded.arguments.front().integer == 4);

    std::vector<std::uint8_t> namesReply;
    appendString(namesReply, "/live/song/get/track_names");
    appendString(namesReply, ",ssss");
    appendString(namesReply, "1-MIDI");
    appendString(namesReply, "2-MIDI");
    appendString(namesReply, "3-Audio");
    appendString(namesReply, "4-Audio");
    KENN_TEST_CHECK(kenn::osc::decodeMessage(namesReply, decoded));
    KENN_TEST_CHECK(decoded.arguments.size() == 4);
    KENN_TEST_CHECK(decoded.arguments[3].string == "4-Audio");

    namesReply.push_back(0x01);
    KENN_TEST_CHECK(!kenn::osc::decodeMessage(namesReply, decoded));
    std::cout << "Local AbletonOSC protocol: getter/count/name/malformed cases passed" << std::endl;
    return 0;
}
