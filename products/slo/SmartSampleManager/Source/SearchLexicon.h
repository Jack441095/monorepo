#pragma once

#include <juce_core/juce_core.h>

#include <array>

// Small, deterministic search vocabulary inspired by sample-browser products:
// filename language is useful for discovery, but producers use many aliases
// for the same family. This helper deliberately does not classify, relabel,
// or write anything; it only broadens a read-only text query.
namespace SloSearchLexicon {

inline bool matches(const juce::String& searchableText, const juce::String& query)
{
    const auto text = searchableText.toLowerCase();
    const auto q = query.trim().toLowerCase();
    if (q.isEmpty()) return true;
    if (text.contains(q)) return true;

    // Only expand a single term. Multi-word queries remain literal so a
    // search for "bass hit" cannot accidentally match every bass or every
    // impact. The groups are intentionally conservative and family-level.
    if (q.containsAnyOf(" \t\n\r")) return false;

    constexpr std::array<std::array<const char*, 8>, 22> groups = {{
        {{"kick", "bd", "bassdrum", "bass-drum", "bass_drum", "", "", ""}},
        {{"snare", "sd", "sn", "rim", "rimshot", "", "", ""}},
        {{"hihat", "hi-hat", "hi_hat", "hat", "hh", "closedhat", "openhat", ""}},
        {{"clap", "cl", "handclap", "hand-clap", "", "", "", ""}},
        {{"shaker", "tambourine", "tamb", "shak", "", "", "", ""}},
        {{"tom", "toms", "floor-tom", "floortom", "", "", "", ""}},
        {{"perc", "percussion", "percussive", "conga", "bongo", "handdrum", "hand-drum"}},
        {{"foley", "footstep", "cloth", "rustle", "", "", "", ""}},
        {{"impact", "hit", "slam", "thump", "punch", "", "", ""}},
        {{"riser", "rising", "uplifter", "up-lifter", "", "", "", ""}},
        {{"atmosphere", "ambience", "ambient", "roomtone", "room-tone", "texture", "", ""}},
        {{"vocal", "vox", "voice", "spoken", "speech", "", "", ""}},
        {{"membrane", "drumhead", "bessel", "drumskin", "", "", "", ""}},
        {{"plate", "cymbal", "crash", "ride", "bell", "chime", "metallic", ""}},
        {{"string", "strings", "harmonic", "plucked", "piano", "guitar", "", ""}},
        {{"dive", "pitchdive", "glide", "slidedown", "pitch-dive", "", "", ""}},
        {{"sweep", "pitchsweep", "slideup", "swell", "pitch-sweep", "riser", "uplifter", ""}},
        {{"stiff", "stiff-string", "stiffness", "dispersion", "", "", "", ""}},
        {{"metal", "metallic", "bronze", "brass", "steel", "chimes", "gong", ""}},
        {{"wood", "wooden", "marimba", "woodblock", "xylophone", "cajon", "", ""}},
        {{"felt", "softmallet", "soft-mallet", "muffled", "padded", "soft", "", ""}},
        {{"bore", "cylindrical", "conical", "clarinet", "flute", "pipe", "", ""}}
    }};

    for (const auto& group : groups) {
        bool queryIsAlias = false;
        for (const auto* alias : group) {
            if (alias != nullptr && alias[0] != '\0' && q == alias) {
                queryIsAlias = true;
                break;
            }
        }
        if (!queryIsAlias) continue;

        for (const auto* alias : group) {
            if (alias != nullptr && alias[0] != '\0' && text.contains(alias))
                return true;
        }
    }
    return false;
}

} // namespace SloSearchLexicon
