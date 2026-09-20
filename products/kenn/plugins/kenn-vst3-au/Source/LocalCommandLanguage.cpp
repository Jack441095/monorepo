#include "LocalCommandLanguage.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <regex>

namespace kenn
{
namespace
{

std::string normalise(std::string_view input)
{
    std::string output;
    output.reserve(std::min<std::size_t>(input.size(), 4000));
    bool previousSpace = true;
    for (const auto character : input.substr(0, 4000))
    {
        const auto lower = static_cast<char>(std::tolower(static_cast<unsigned char>(character)));
        if (std::isspace(static_cast<unsigned char>(lower)))
        {
            if (!previousSpace) output.push_back(' ');
            previousSpace = true;
        }
        else
        {
            output.push_back(lower);
            previousSpace = false;
        }
    }
    while (!output.empty() && output.back() == ' ') output.pop_back();
    return output;
}

std::string trim(std::string value)
{
    const auto first = value.find_first_not_of(' ');
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(' ');
    return value.substr(first, last - first + 1);
}

bool containsWord(const std::string& text, const char* word)
{
    const auto isWordCharacter = [](char character) {
        const auto value = static_cast<unsigned char>(character);
        return std::isalnum(value) || character == '_';
    };
    const std::string needle(word);
    std::size_t position = 0;
    while ((position = text.find(needle, position)) != std::string::npos)
    {
        const auto startsWord = position == 0 || ! isWordCharacter(text[position - 1]);
        const auto end = position + needle.size();
        const auto endsWord = end >= text.size() || ! isWordCharacter(text[end]);
        if (startsWord && endsWord) return true;
        position = end;
    }
    return false;
}

bool findTrackNumber(const std::string& text, int& number)
{
    static const std::regex numericExpression(
        R"(\b(?:track|trk|channel|chan|ch)\s*#?\s*(\d+)\b)", std::regex::icase);
    std::smatch match;
    if (std::regex_search(text, match, numericExpression))
    {
        try
        {
            number = std::stoi(match[1].str());
        }
        catch (...)
        {
            return false;
        }
        return number > 0 && number <= 999;
    }

    static const std::regex ordinalBeforeTrackExpression(
        R"(\b(?:the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:track|trk|channel|chan|ch)\b)",
        std::regex::icase);
    if (std::regex_search(text, match, ordinalBeforeTrackExpression))
    {
        static const std::pair<const char*, int> ordinalValues[] = {
            {"first", 1}, {"second", 2}, {"third", 3}, {"fourth", 4}, {"fifth", 5},
            {"sixth", 6}, {"seventh", 7}, {"eighth", 8}, {"ninth", 9}, {"tenth", 10},
        };
        for (const auto& [word, value] : ordinalValues)
        {
            if (match[1].str() == word)
            {
                number = value;
                return true;
            }
        }
    }

    static const std::regex spokenExpression(
        R"(\b(?:track|trk|channel|chan|ch)\s+(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|one|two|three|four|five|six|seven|eight|nine|ten)\b)",
        std::regex::icase);
    if (!std::regex_search(text, match, spokenExpression)) return false;
    static const std::pair<const char*, int> spokenValues[] = {
        {"first", 1}, {"second", 2}, {"third", 3}, {"fourth", 4}, {"fifth", 5},
        {"sixth", 6}, {"seventh", 7}, {"eighth", 8}, {"ninth", 9}, {"tenth", 10},
        {"one", 1}, {"two", 2}, {"three", 3}, {"four", 4}, {"five", 5},
        {"six", 6}, {"seven", 7}, {"eight", 8}, {"nine", 9}, {"ten", 10},
    };
    auto spoken = match[1].str();
    std::transform(spoken.begin(), spoken.end(), spoken.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    for (const auto& [word, value] : spokenValues)
    {
        if (spoken == word)
        {
            number = value;
            return true;
        }
    }
    return false;
}

bool findNumber(const std::string& text, double& value, std::string& unit, std::string& side)
{
    static const std::regex expression(
        R"((-?(?:\d+(?:\.\d+)?|\.\d+))\s*(%|percent|db|hz)?\s*(left|right)?)",
        std::regex::icase);
    std::smatch match;
    if (!std::regex_search(text, match, expression)) return false;
    try
    {
        value = std::stod(match[1].str());
    }
    catch (...)
    {
        return false;
    }
    unit = match[2].str();
    side = match[3].str();
    std::transform(unit.begin(), unit.end(), unit.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    std::transform(side.begin(), side.end(), side.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return std::isfinite(value);
}

void setTrackError(LocalCommandIntent& result)
{
    if (result.trackNumber <= 0)
        result.clarification = "The local parser needs a numbered Live track; named-track resolution remains snapshot-bound.";
}

} // namespace

LocalCommandIntent parseLocalCommand(std::string_view command)
{
    LocalCommandIntent result;
    result.canonical = normalise(command);
    if (result.canonical.empty())
    {
        result.clarification = "Type a Live command first.";
        return result;
    }

    result.recipe = result.canonical.find(" then ") != std::string::npos || result.canonical.find(';') != std::string::npos;
    if (containsWord(result.canonical, "delete") || containsWord(result.canonical, "remove")
        || containsWord(result.canonical, "overwrite") || containsWord(result.canonical, "replace"))
    {
        result.clarification = "Destructive Live actions are disabled by KENN.";
        return result;
    }

    findTrackNumber(result.canonical, result.trackNumber);

    static const std::regex createMidiTrackExpression(
        R"(^\s*(?:create|add|make)\s+(?:a\s+)?(?:new\s+)?midi\s+track\b(?:\s+(?:called|named|with\s+name)\s+['\"]?([^'\"]+?)['\"]?)?\s*$)",
        std::regex::icase);
    static const std::regex createAudioTrackExpression(
        R"(^\s*(?:create|add|make)\s+(?:an?\s+)?(?:new\s+)?audio\s+track\b(?:\s+(?:called|named|with\s+name)\s+['\"]?([^'\"]+?)['\"]?)?\s*$)",
        std::regex::icase);
    std::smatch trackCreationMatch;
    if (std::regex_match(result.canonical, trackCreationMatch, createMidiTrackExpression))
    {
        result.action = "create_midi_track";
        if (trackCreationMatch.size() > 1 && trackCreationMatch[1].matched)
            result.newTrackName = trim(trackCreationMatch[1].str());
    }
    else if (std::regex_match(result.canonical, trackCreationMatch, createAudioTrackExpression))
    {
        result.action = "create_audio_track";
        if (trackCreationMatch.size() > 1 && trackCreationMatch[1].matched)
            result.newTrackName = trim(trackCreationMatch[1].str());
    }
    else if (containsWord(result.canonical, "play") && !containsWord(result.canonical, "display"))
        result.action = "transport_play";
    else if (containsWord(result.canonical, "stop"))
        result.action = "transport_stop";
    else if (containsWord(result.canonical, "unmute") || containsWord(result.canonical, "unsilence"))
    {
        result.action = "set_mute";
        result.hasValue = true;
        result.value = 0.0;
        result.unit = "boolean";
    }
    else if (containsWord(result.canonical, "mute") || containsWord(result.canonical, "silence"))
    {
        result.action = "set_mute";
        result.hasValue = true;
        result.value = 1.0;
        result.unit = "boolean";
    }
    else if (containsWord(result.canonical, "unsolo") || containsWord(result.canonical, "unisolate"))
    {
        result.action = "set_solo";
        result.hasValue = true;
        result.value = 0.0;
        result.unit = "boolean";
    }
    else if (containsWord(result.canonical, "solo") || containsWord(result.canonical, "isolate"))
    {
        result.action = "set_solo";
        result.hasValue = true;
        result.value = 1.0;
        result.unit = "boolean";
    }
    else if (containsWord(result.canonical, "disarm"))
    {
        result.action = "set_arm";
        result.hasValue = true;
        result.value = 0.0;
        result.unit = "boolean";
    }
    else if (containsWord(result.canonical, "arm") || containsWord(result.canonical, "record-enable"))
    {
        result.action = "set_arm";
        result.hasValue = true;
        result.value = 1.0;
        result.unit = "boolean";
    }
    else if (containsWord(result.canonical, "pan"))
    {
        result.action = "set_pan";
        double amount = 0.0;
        std::string unit;
        std::string side;
        const auto trackMatch = result.canonical.find("track ") != std::string::npos
            || result.canonical.find("channel ") != std::string::npos
            || result.canonical.find("chan ") != std::string::npos
            || result.canonical.find("ch ") != std::string::npos;
        std::string valueText = result.canonical;
        if (trackMatch)
        {
            const auto marker = result.canonical.find("pan");
            if (marker != std::string::npos) valueText = result.canonical.substr(marker + 3);
            static const std::regex afterTrack(
                R"((?:track|trk|channel|chan|ch)\s*#?\s*\d+\s+(.+))", std::regex::icase);
            std::smatch afterMatch;
            if (std::regex_search(valueText, afterMatch, afterTrack)) valueText = afterMatch[1].str();
        }
        if (!findNumber(valueText, amount, unit, side))
        {
            result.clarification = "Pan needs a numeric amount.";
            return result;
        }
        if (side == "left") amount = -std::abs(amount);
        if (side == "right") amount = std::abs(amount);
        result.value = unit == "%" || unit == "percent" ? amount / 100.0 : amount;
        result.hasValue = std::isfinite(result.value) && result.value >= -1.0 && result.value <= 1.0;
        result.unit = "normalized";
        if (!result.hasValue)
        {
            result.clarification = "Pan must be between -1.0 and 1.0.";
            return result;
        }
    }
    else if (containsWord(result.canonical, "volume") || containsWord(result.canonical, "level"))
    {
        result.action = "set_volume";
        double db = 0.0;
        std::string unit;
        std::string side;
        // The track/channel reference (e.g. "track 4") contains its own digit
        // and must not be mistaken for the requested dB value, regardless of
        // whether it appears before or after the value in the sentence.
        static const std::regex trackToken(
            R"(\b(?:track|trk|channel|chan|ch)\s*#?\s*\d+\b)", std::regex::icase);
        const auto valueText = std::regex_replace(result.canonical, trackToken, " ");
        if (!findNumber(valueText, db, unit, side) || (unit != "db" && unit != ""))
        {
            result.clarification = "Volume needs an explicit dB value.";
            return result;
        }
        result.value = std::pow(10.0, db / 20.0);
        result.hasValue = std::isfinite(result.value) && result.value >= 0.0 && result.value <= 1.0;
        result.unit = "normalized";
        if (!result.hasValue)
        {
            result.clarification = "The volume dB value is outside KENN's normalized range.";
            return result;
        }
    }
    else if (containsWord(result.canonical, "set") || containsWord(result.canonical, "change")
        || containsWord(result.canonical, "adjust") || containsWord(result.canonical, "lower")
        || containsWord(result.canonical, "raise") || containsWord(result.canonical, "reduce")
        || containsWord(result.canonical, "increase"))
    {
        struct DevicePhrase { const char* text; const char* name; };
        static constexpr DevicePhrase devicePhrases[] = {
            { "glue compressor", "Glue Compressor" },
            { "auto filter", "Auto Filter" },
            { "drum buss", "Drum Buss" },
            { "eq eight", "EQ Eight" },
            { "eq 8", "EQ Eight" },
            { "saturator", "Saturator" },
            // These are recognized here only as advisory local metadata; the
            // companion still re-resolves the exact device against a fresh
            // Live snapshot before any proposal is created, and none of
            // these are insertable until each passes real-Live parameter
            // qualification (see DEVICE_INSERTION_ALLOWLIST).
            { "multiband dynamics", "Multiband Dynamics" },
            { "vinyl distortion", "Vinyl Distortion" },
            { "beat repeat", "Beat Repeat" },
            { "auto pan", "Auto Pan" },
            { "compressor", "Compressor" },
            { "hybrid reverb", "Hybrid Reverb" },
            { "reverb", "Reverb" },
            { "echo", "Echo" },
            { "limiter", "Limiter" },
            { "utility", "Utility" },
            { "overdrive", "Overdrive" },
            { "vocoder", "Vocoder" },
            { "erosion", "Erosion" },
            { "chorus", "Chorus" },
            { "phaser", "Phaser" },
            { "corpus", "Corpus" },
            { "redux", "Redux" },
            { "gate", "Gate" },
            { "amp", "Amp" },
            { "delay", "Delay" },
            { "eq", "EQ Eight" },
        };
        const DevicePhrase* matchedDevice = nullptr;
        std::size_t devicePosition = std::string::npos;
        for (const auto& candidate : devicePhrases)
        {
            const auto position = result.canonical.find(candidate.text);
            if (position != std::string::npos && (matchedDevice == nullptr || position < devicePosition
                                                   || (position == devicePosition
                                                       && std::string_view(candidate.text).size() > std::string_view(matchedDevice->text).size())))
            {
                matchedDevice = &candidate;
                devicePosition = position;
            }
        }
        const auto delimiterTo = result.canonical.find(" to ", devicePosition == std::string::npos ? 0 : devicePosition);
        const auto delimiterBy = result.canonical.find(" by ", devicePosition == std::string::npos ? 0 : devicePosition);
        const auto delimiter = delimiterTo != std::string::npos && (delimiterBy == std::string::npos || delimiterTo < delimiterBy)
            ? delimiterTo : delimiterBy;
        if (matchedDevice == nullptr || delimiter == std::string::npos || delimiter <= devicePosition)
        {
            result.clarification = "The local parser needs an exact device parameter and target value.";
            return result;
        }
        auto parameter = trim(result.canonical.substr(devicePosition + std::string(matchedDevice->text).size(), delimiter - devicePosition - std::string(matchedDevice->text).size()));
        if (parameter.rfind("parameter ", 0) == 0) parameter.erase(0, 10);
        if (parameter.rfind("the ", 0) == 0) parameter.erase(0, 4);
        parameter = trim(parameter);
        if (parameter.empty())
        {
            result.clarification = "The local parser needs an exact device parameter name.";
            return result;
        }
        auto valueText = result.canonical.substr(delimiter + 4);
        for (const auto& marker : { std::string(" on track "), std::string(" on channel "), std::string(" on chan "), std::string(" on ch ") })
        {
            const auto end = valueText.find(marker);
            if (end != std::string::npos) valueText.erase(end);
        }
        double value = 0.0;
        std::string unit;
        std::string side;
        if (!findNumber(valueText, value, unit, side) || unit != "db")
        {
            result.clarification = "Device parameter changes need an explicit dB value.";
            return result;
        }
        result.action = "set_device_parameter";
        result.deviceName = matchedDevice->name;
        result.parameterName = parameter;
        result.relative = delimiter == delimiterBy;
        // "Reduce ... by 3 dB" and "lower ... by 3 dB" mean decrease by that
        // magnitude, not increase; the phrase never carries an explicit sign
        // for the amount, so the verb must supply it for a relative change.
        if (result.relative && (containsWord(result.canonical, "reduce") || containsWord(result.canonical, "lower")))
            value = -std::abs(value);
        else if (result.relative && (containsWord(result.canonical, "raise") || containsWord(result.canonical, "increase")))
            value = std::abs(value);
        result.value = value;
        result.hasValue = true;
        result.unit = "dB";
    }
    else if (containsWord(result.canonical, "add") || containsWord(result.canonical, "append")
        || containsWord(result.canonical, "insert") || containsWord(result.canonical, "put")
        || containsWord(result.canonical, "load"))
    {
        // Kept in sync with DEVICE_INSERTION_ALLOWLIST
        // (apps/backend/src/kenn/core/live_action_service.py) and live_intent.py's
        // _INSERT_DEVICE_ALIASES -- "glue\s+compressor" must stay before the
        // bare "compressor" alternative resolves to the wrong device at the
        // same match; leftmost-starting-position search already gives
        // "glue compressor" priority since it starts earlier in the input
        // than the "compressor" substring within it.
        static const std::regex deviceExpression(
            R"(\b(eq(?:ualizer)?(?:\s+eight)?|eq\s*8|glue\s+compressor|auto\s+filter|drum\s+buss|saturator|hybrid\s+reverb|echo|compressor)\b)",
            std::regex::icase);
        std::smatch deviceMatch;
        if (!std::regex_search(result.canonical, deviceMatch, deviceExpression))
        {
            result.clarification = "The local parser needs an allow-listed device name.";
            return result;
        }
        auto name = deviceMatch[1].str();
        std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        result.deviceName = name.find("glue") != std::string::npos ? "Glue Compressor"
            : name.find("auto") != std::string::npos ? "Auto Filter"
            : name.find("drum") != std::string::npos ? "Drum Buss"
            : name.find("saturator") != std::string::npos ? "Saturator"
            : name.find("hybrid") != std::string::npos ? "Hybrid Reverb"
            : name.find("echo") != std::string::npos ? "Echo"
            : name.find("compressor") != std::string::npos ? "Compressor" : "EQ Eight";
        result.action = "insert_device";
    }
    else
    {
        result.clarification = "The local parser does not recognise this Live action yet.";
        return result;
    }

    if (result.action != "transport_play" && result.action != "transport_stop"
        && result.action != "create_midi_track" && result.action != "create_audio_track")
        setTrackError(result);
    result.recognized = result.clarification.empty() && !result.action.empty();
    return result;
}

} // namespace kenn
