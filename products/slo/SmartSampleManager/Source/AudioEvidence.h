#pragma once

#include "AbletonTaxonomy.h"

#include <algorithm>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace SloAudioEvidence {

constexpr const char* kSchemaVersion = "1.0.0";

enum class ClaimState { observed, predicted, user, unknown, rejected };

struct Claim {
    std::string value;
    float confidence = 0.0f;
    std::string source = "unknown";
    ClaimState state = ClaimState::unknown;
    std::vector<std::pair<std::string, float>> alternatives;

    bool isValid() const
    {
        if (confidence < 0.0f || confidence > 1.0f) return false;
        if ((state == ClaimState::observed || state == ClaimState::predicted
             || state == ClaimState::user) && value.empty()) return false;
        for (const auto& alternative : alternatives)
            if (alternative.first.empty() || alternative.second < 0.0f
                || alternative.second > 1.0f) return false;
        return true;
    }
};

struct PhysicalMeasurement {
    double value = 0.0;
    std::string unit;
    std::string method;
    bool valid = true;
};

// Decision-neutral interchange record.  There is intentionally no action,
// approval, destination path, or rename field in this type.
struct Record {
    std::string schemaVersion = kSchemaVersion;
    std::string contentId;
    std::string sourcePath;
    Claim identity;
    Claim family;
    Claim form;
    std::map<std::string, Claim> attributes;
    std::map<std::string, PhysicalMeasurement> measurements;
    std::map<std::string, std::string> metadata;
    std::string duplicateGroup;
    std::map<std::string, std::string> modelVersions;

    // Exact compatibility snapshot used to prove the migration has not
    // changed the current taxonomy result.
    AbletonTaxonomy::Classification legacy;

    bool isValid() const
    {
        if (schemaVersion != kSchemaVersion || contentId.empty()
            || sourcePath.empty()) return false;
        if (!identity.isValid() || !family.isValid() || !form.isValid())
            return false;
        for (const auto& item : attributes)
            if (item.first.empty() || !item.second.isValid()) return false;
        for (const auto& item : measurements)
            if (item.first.empty() || item.second.unit.empty()
                || item.second.method.empty()) return false;
        return true;
    }
};

inline bool hasTag(const std::vector<std::string>& tags, const std::string& wanted)
{
    return std::find(tags.begin(), tags.end(), wanted) != tags.end();
}

inline std::pair<std::string, std::string> splitLegacyIdentityAndForm(
    const std::string& subcategory, const std::vector<std::string>& tags)
{
    std::string identity = subcategory;
    std::string form = "unknown";
    if (hasTag(tags, "Loop") || subcategory == "Music Loop"
        || (subcategory.size() > 5
            && subcategory.compare(subcategory.size() - 5, 5, " Loop") == 0))
        form = "loop";
    else if (hasTag(tags, "One-Shot")
             || (subcategory.size() > 9
                 && subcategory.compare(subcategory.size() - 9, 9, " One-Shot") == 0))
        form = "one-shot";
    else if (subcategory.find("Phrase") != std::string::npos)
        form = "phrase";
    else if (subcategory.find("Fill") != std::string::npos)
        form = "fill";

    for (const std::string suffix : {" Loop", " One-Shot", " Phrase"}) {
        if (identity.size() >= suffix.size()
            && identity.compare(identity.size() - suffix.size(), suffix.size(), suffix) == 0) {
            identity.erase(identity.size() - suffix.size());
            break;
        }
    }
    if (identity == "Music") identity.clear();
    return {identity, form};
}

inline Record fromLegacyTaxonomy(const std::string& contentId,
                                 const std::string& sourcePath,
                                 const AbletonTaxonomy::Classification& legacy,
                                 int taxonomyVersion,
                                 int classificationModelVersion,
                                 const std::map<std::string, PhysicalMeasurement>& measurements = {},
                                 const std::map<std::string, std::string>& metadata = {})
{
    const auto identityAndForm = splitLegacyIdentityAndForm(
        legacy.subcategory, legacy.secondaryTags);
    const std::string source = legacy.winningEvidence.empty()
        ? "unknown" : legacy.winningEvidence;

    Record record;
    record.contentId = contentId;
    record.sourcePath = sourcePath;
    record.legacy = legacy;
    record.measurements = measurements;
    record.metadata = metadata;
    record.identity = {identityAndForm.first,
                       identityAndForm.first.empty() ? 0.0f : legacy.confidence,
                       source,
                       identityAndForm.first.empty() ? ClaimState::unknown : ClaimState::predicted,
                       {}};
    record.family = {legacy.category,
                     legacy.category.empty() ? 0.0f : legacy.confidence,
                     source,
                     legacy.category.empty() ? ClaimState::unknown : ClaimState::predicted,
                     {}};
    record.form = {identityAndForm.second,
                   identityAndForm.second == "unknown" ? 0.0f : legacy.confidence,
                   source,
                   identityAndForm.second == "unknown" ? ClaimState::unknown : ClaimState::predicted,
                   {}};
    for (const auto& tag : legacy.secondaryTags) {
        if (tag == "Loop" || tag == "One-Shot") continue;
        record.attributes.emplace(tag, Claim{tag, legacy.confidence,
            "legacy_secondary_tag", ClaimState::predicted, {}});
    }
    record.modelVersions["taxonomy"] = std::to_string(taxonomyVersion);
    record.modelVersions["classification"] = std::to_string(classificationModelVersion);
    return record;
}

} // namespace SloAudioEvidence
