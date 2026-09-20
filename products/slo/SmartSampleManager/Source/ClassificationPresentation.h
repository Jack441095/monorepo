#pragma once

#include <cctype>
#include <string>

// Presentation-only interpretation of classification fields. This deliberately
// does not mutate SampleItem: the legacy instrumentType remains available for
// metadata editing, diagnostics, and search, while an explicit ML abstention
// must not be presented as a known taxonomy label.
namespace ClassificationPresentation
{
inline bool isMlOod(const std::string& tagSource) noexcept
{
    return tagSource == "ml_ood";
}

inline std::string primaryLabel(const std::string& category,
                                const std::string& subcategory,
                                const std::string& instrumentType,
                                const std::string& tagSource)
{
    if (isMlOod(tagSource)) return "Needs review";
    if (!subcategory.empty()) return subcategory;
    if (!category.empty()) return category;
    if (instrumentType.empty() || instrumentType == "Unknown") return {};
    return instrumentType;
}

inline std::string filterText(const std::string& category,
                              const std::string& subcategory,
                              const std::string& instrumentType,
                              const std::string& tagSource)
{
    if (isMlOod(tagSource)) return "Unknown Other";

    std::string result;
    const auto append = [&result](const std::string& value) {
        if (value.empty() || value == "Unknown") return;
        if (!result.empty()) result += ' ';
        result += value;
    };
    append(subcategory);
    append(category);
    append(instrumentType);
    if (result.empty()) result = "Other";
    return result;
}

// Stable, broad labels for the editor's category-filter pills. Prefer the
// taxonomy category; older cache rows may only have the legacy instrument
// label. Never expose the sentinel "Unknown" as a clickable category.
inline std::string filterCategory(const std::string& category,
                                  const std::string& instrumentType)
{
    if (!category.empty()) return category;
    if (!instrumentType.empty() && instrumentType != "Unknown") return instrumentType;
    return "Other";
}

inline bool matchesCategoryFilter(const std::string& filterTextValue,
                                  const std::string& activeCategory) noexcept
{
    if (activeCategory.empty()) return true;

    std::string haystack = filterTextValue;
    std::string needle = activeCategory;
    const auto lowerInPlace = [](std::string& value) {
        for (auto& c : value)
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    };
    lowerInPlace(haystack);
    lowerInPlace(needle);

    // Preserve the friendly aliases used by the visual map ("Hi-Hat" also
    // matches legacy "hat" labels; "Vocal" matches abbreviated "voc").
    if (needle == "hi-hat")
        return haystack.find("hihat") != std::string::npos
            || haystack.find("hat") != std::string::npos;
    if (needle == "vocal" || needle == "vocals")
        return haystack.find("vocal") != std::string::npos
            || haystack.find("voc") != std::string::npos;

    return haystack.find(needle) != std::string::npos;
}

inline bool isNeutral(const std::string& label) noexcept
{
    return label.empty() || label == "Unknown";
}

inline std::string evidenceLabel(const std::string& tagSource,
                                 const std::string& winningEvidence)
{
    if (tagSource == "user" || winningEvidence == "USER_OVERRIDE") return "user override";
    if (tagSource == "ml_ood") return "OOD abstention";
    if (tagSource == "physics" || winningEvidence == "PHYSICS") return "physical acoustics";
    if (tagSource == "ml_v3") return "audio model";
    if (winningEvidence == "EMBEDDED_METADATA") return "metadata-assisted";
    if (winningEvidence == "FILENAME") return "filename heuristic";
    if (winningEvidence == "FOLDER") return "folder heuristic";
    if (winningEvidence == "DSP") return "audio-only";
    if (tagSource == "unclassified") return "not run";
    return "unknown";
}

inline std::string taxonomyVersionLabel(int taxonomyVersion)
{
    return taxonomyVersion > 0
        ? "taxonomy v" + std::to_string(taxonomyVersion)
        : "taxonomy not run";
}

// A presentation-only reason for uncertainty.  This intentionally derives
// from existing provenance and confidence fields instead of adding a second
// mutable label column to the cache.  It gives the producer an actionable
// explanation while keeping the underlying classification decision-neutral.
inline std::string uncertaintyReason(const std::string& tagSource,
                                     const std::string& winningEvidence,
                                     float confidence) noexcept
{
    if (tagSource == "user" || winningEvidence == "USER_OVERRIDE") return {};
    if (tagSource == "unclassified") return "not analysed";
    if (tagSource == "ml_ood") return "outside the known audio domain";
    if (confidence < 0.5f) return "weak evidence agreement";
    if (winningEvidence == "FILENAME" || winningEvidence == "FOLDER")
        return "name or folder evidence only";
    if (confidence < 0.75f) return "mixed evidence";
    return {};
}
} // namespace ClassificationPresentation
