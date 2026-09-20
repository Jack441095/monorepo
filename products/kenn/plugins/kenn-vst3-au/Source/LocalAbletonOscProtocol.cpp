#include "LocalAbletonOscProtocol.h"

#include <algorithm>
#include <cstring>

namespace kenn::osc
{
namespace
{
constexpr std::size_t maxOscStringBytes = 4096;
constexpr std::size_t maxOscArguments = 128;

std::size_t paddedSize(std::size_t size)
{
    return (size + 4u) & ~std::size_t(3u);
}

void appendPaddedString(std::vector<std::uint8_t>& output, std::string_view value)
{
    const auto start = output.size();
    output.insert(output.end(), value.begin(), value.end());
    output.push_back(0);
    output.resize(start + paddedSize(value.size()), 0);
}

bool readPaddedString(std::span<const std::uint8_t> bytes, std::size_t& offset, std::string& value)
{
    if (offset >= bytes.size()) return false;
    const auto remaining = bytes.size() - offset;
    const auto terminator = std::find(bytes.begin() + static_cast<std::ptrdiff_t>(offset), bytes.end(), std::uint8_t(0));
    if (terminator == bytes.end()) return false;
    const auto length = static_cast<std::size_t>(std::distance(bytes.begin() + static_cast<std::ptrdiff_t>(offset), terminator));
    if (length > maxOscStringBytes) return false;
    const auto total = paddedSize(length);
    if (total > remaining) return false;
    value.assign(reinterpret_cast<const char*>(bytes.data() + offset), length);
    offset += total;
    return true;
}

bool readBigEndian32(std::span<const std::uint8_t> bytes, std::size_t& offset, std::uint32_t& value)
{
    if (bytes.size() - std::min(offset, bytes.size()) < 4) return false;
    value = (static_cast<std::uint32_t>(bytes[offset]) << 24)
        | (static_cast<std::uint32_t>(bytes[offset + 1]) << 16)
        | (static_cast<std::uint32_t>(bytes[offset + 2]) << 8)
        | static_cast<std::uint32_t>(bytes[offset + 3]);
    offset += 4;
    return true;
}

bool skipBlob(std::span<const std::uint8_t> bytes, std::size_t& offset)
{
    std::uint32_t length = 0;
    if (!readBigEndian32(bytes, offset, length)) return false;
    if (length > bytes.size() - std::min(offset, bytes.size())) return false;
    offset += paddedSize(length);
    return offset <= bytes.size();
}
}

std::vector<std::uint8_t> encodeMessage(std::string_view address, std::span<const Argument> arguments)
{
    if (address.empty() || address.size() > maxOscStringBytes || address.front() != '/') return {};
    std::vector<std::uint8_t> result;
    if (arguments.size() > maxOscArguments) return {};
    std::string typeTags = ",";
    typeTags.reserve(arguments.size() + 1);
    for (const auto& argument : arguments)
    {
        switch (argument.kind)
        {
            case ArgumentKind::integer: typeTags.push_back('i'); break;
            case ArgumentKind::floating: typeTags.push_back('f'); break;
            case ArgumentKind::string: typeTags.push_back('s'); break;
            case ArgumentKind::unsupported: return {};
        }
    }
    result.reserve(paddedSize(address.size()) + paddedSize(typeTags.size()) + arguments.size() * 4u);
    appendPaddedString(result, address);
    appendPaddedString(result, typeTags);
    for (const auto& argument : arguments)
    {
        if (argument.kind == ArgumentKind::integer)
        {
            const auto raw = static_cast<std::uint32_t>(argument.integer);
            result.push_back(static_cast<std::uint8_t>(raw >> 24));
            result.push_back(static_cast<std::uint8_t>(raw >> 16));
            result.push_back(static_cast<std::uint8_t>(raw >> 8));
            result.push_back(static_cast<std::uint8_t>(raw));
        }
        else if (argument.kind == ArgumentKind::floating)
        {
            std::uint32_t raw = 0;
            static_assert(sizeof(raw) == sizeof(argument.floating));
            std::memcpy(&raw, &argument.floating, sizeof(raw));
            result.push_back(static_cast<std::uint8_t>(raw >> 24));
            result.push_back(static_cast<std::uint8_t>(raw >> 16));
            result.push_back(static_cast<std::uint8_t>(raw >> 8));
            result.push_back(static_cast<std::uint8_t>(raw));
        }
        else
        {
            appendPaddedString(result, argument.string);
        }
    }
    return result;
}

std::vector<std::uint8_t> encodeNoArgumentMessage(std::string_view address)
{
    return encodeMessage(address, {});
}

bool decodeMessage(std::span<const std::uint8_t> bytes, Message& message)
{
    message = {};
    if (bytes.empty() || bytes.size() > 65507) return false;

    std::size_t offset = 0;
    if (!readPaddedString(bytes, offset, message.address)
        || message.address.empty() || message.address.front() != '/')
        return false;

    // A bundle has a different framing contract. Keep this tiny codec strict.
    if (message.address == "#bundle") return false;

    std::string typeTags;
    if (!readPaddedString(bytes, offset, typeTags) || typeTags.empty() || typeTags.front() != ',') return false;
    if (typeTags.size() - 1 > maxOscArguments) return false;

    message.arguments.reserve(typeTags.size() - 1);
    for (const auto type : std::string_view(typeTags).substr(1))
    {
        Argument argument;
        switch (type)
        {
            case 'i':
            {
                std::uint32_t raw = 0;
                if (!readBigEndian32(bytes, offset, raw)) return false;
                argument.kind = ArgumentKind::integer;
                argument.integer = static_cast<std::int32_t>(raw);
                break;
            }
            case 'f':
            {
                std::uint32_t raw = 0;
                if (!readBigEndian32(bytes, offset, raw)) return false;
                std::memcpy(&argument.floating, &raw, sizeof(argument.floating));
                argument.kind = ArgumentKind::floating;
                break;
            }
            case 's':
                if (!readPaddedString(bytes, offset, argument.string)) return false;
                argument.kind = ArgumentKind::string;
                break;
            case 'b':
                if (!skipBlob(bytes, offset)) return false;
                argument.kind = ArgumentKind::unsupported;
                break;
            case 'h':
            case 't':
            case 'd':
            case 'c':
            case 'r':
            case 'm':
                // These OSC payloads are not needed by the liveness probe.
                // Reject instead of advancing with an incorrect width.
                return false;
            case 'T':
            case 'F':
            case 'N':
            case 'I':
                argument.kind = ArgumentKind::unsupported;
                break;
            default:
                return false;
        }
        message.arguments.push_back(std::move(argument));
    }
    return offset == bytes.size();
}
}
