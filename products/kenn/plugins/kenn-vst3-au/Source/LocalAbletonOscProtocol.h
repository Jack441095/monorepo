#pragma once

#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace kenn::osc
{
enum class ArgumentKind
{
    integer,
    floating,
    string,
    unsupported
};

struct Argument
{
    ArgumentKind kind = ArgumentKind::unsupported;
    std::int32_t integer = 0;
    float floating = 0.0f;
    std::string string;
};

struct Message
{
    std::string address;
    std::vector<Argument> arguments;
};

// Encode one standard OSC message. The direct Live path uses only bounded
// integer/string/float getter arguments; unsupported values are rejected.
std::vector<std::uint8_t> encodeMessage(std::string_view address, std::span<const Argument> arguments);

// Convenience form for a read-only OSC getter with no arguments.
std::vector<std::uint8_t> encodeNoArgumentMessage(std::string_view address);

// Decode one bounded OSC message. Bundles and unsupported argument payloads
// are rejected so the plug-in never guesses at a response format.
bool decodeMessage(std::span<const std::uint8_t> bytes, Message& message);
}
