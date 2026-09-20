#pragma once

#include <JuceHeader.h>
#include <array>
#include <vector>
#include <string>

// Scale/emotion interval tables. The classic scales are standard modal formulas;
// the emotion entries are ported verbatim from
// studio/audiogen/audiogen/data/emotion_scales.py (_DEFAULT_MELODY_SCALE_INTERVALS_BY_EMOTION),
// which is how audiogen's Markov melody generator maps an emotional input to a scale.
struct ScaleEntry
{
    const char* name;
    std::vector<int> intervals; // semitone offsets from root, ascending, within one octave
};

namespace ScaleTable
{
    inline const std::vector<ScaleEntry>& getAll()
    {
        static const std::vector<ScaleEntry> table = {
            // --- Classic scales ---
            { "Major",            { 0, 2, 4, 5, 7, 9, 11 } },
            { "Natural Minor",    { 0, 2, 3, 5, 7, 8, 10 } },
            { "Harmonic Minor",   { 0, 2, 3, 5, 7, 8, 11 } },
            { "Melodic Minor",    { 0, 2, 3, 5, 7, 9, 11 } },
            { "Dorian",           { 0, 2, 3, 5, 7, 9, 10 } },
            { "Phrygian",         { 0, 1, 3, 5, 7, 8, 10 } },
            { "Lydian",           { 0, 2, 4, 6, 7, 9, 11 } },
            { "Mixolydian",       { 0, 2, 4, 5, 7, 9, 10 } },
            { "Locrian",          { 0, 1, 3, 5, 6, 8, 10 } },
            { "Major Pentatonic", { 0, 2, 4, 7, 9 } },
            { "Minor Pentatonic", { 0, 3, 5, 7, 10 } },
            { "Blues",            { 0, 3, 5, 6, 7, 10 } },
            { "Chromatic",        { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 } },

            // --- Emotion-driven scales (from audiogen emotion_scales.py) ---
            { "Emotion: Admiration",     { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Amusement",      { 0, 2, 4, 5, 7, 9, 10 } },
            { "Emotion: Anger",          { 0, 1, 4, 5, 7, 8, 10 } },
            { "Emotion: Annoyance",      { 0, 1, 3, 5, 7, 8, 10 } },
            { "Emotion: Approval",       { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Caring",         { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Confusion",      { 0, 1, 3, 5, 6, 8, 10 } },
            { "Emotion: Curiosity",      { 0, 2, 4, 6, 7, 9, 11 } },
            { "Emotion: Desire",         { 0, 2, 3, 5, 7, 9, 10 } },
            { "Emotion: Disappointment", { 0, 2, 3, 5, 7, 8, 10 } },
            { "Emotion: Disapproval",    { 0, 1, 3, 5, 7, 8, 10 } },
            { "Emotion: Disgust",        { 0, 1, 3, 4, 6, 7, 10 } },
            { "Emotion: Embarrassment",  { 0, 2, 3, 5, 7, 8, 10 } },
            { "Emotion: Excitement",     { 0, 2, 4, 5, 7, 9, 10 } },
            { "Emotion: Fear",           { 0, 1, 3, 4, 6, 7, 10 } },
            { "Emotion: Gratitude",      { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Grief",          { 0, 2, 3, 5, 7, 8, 10 } },
            { "Emotion: Joy",            { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Love",           { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Nervousness",    { 0, 1, 3, 4, 6, 7, 10 } },
            { "Emotion: Neutral",        { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Optimism",       { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Pride",          { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Realization",    { 0, 2, 3, 5, 7, 9, 10 } },
            { "Emotion: Relief",         { 0, 2, 4, 5, 7, 9, 11 } },
            { "Emotion: Remorse",        { 0, 2, 3, 5, 7, 8, 10 } },
            { "Emotion: Sadness",        { 0, 2, 3, 5, 7, 8, 10 } },
            { "Emotion: Surprise",       { 0, 1, 2, 4, 5, 7, 10 } },
        };
        return table;
    }

    // Low-arousal ("calm") emotions bias the rhythm chain toward longer, sparser
    // durations by default; everything else (including all classic scales) is neutral.
    // Matches the intensity coloring audiogen's tension/intensity model applies per emotion.
    inline bool isLowArousalEmotion(int index)
    {
        static const std::vector<std::string> lowArousal = {
            "Emotion: Grief", "Emotion: Sadness", "Emotion: Relief",
            "Emotion: Caring", "Emotion: Neutral", "Emotion: Disappointment"
        };
        const auto& table = getAll();
        if (index < 0 || (size_t) index >= table.size())
            return false;
        for (auto& n : lowArousal)
            if (n == table[(size_t) index].name)
                return true;
        return false;
    }

    inline juce::StringArray getNames()
    {
        juce::StringArray names;
        for (auto& e : getAll())
            names.add(e.name);
        return names;
    }
}
