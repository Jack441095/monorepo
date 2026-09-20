#include "AudioEvidence.h"

#include <iostream>

namespace {
int failures = 0;

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}
}

int main()
{
    using namespace SloAudioEvidence;

    AbletonTaxonomy::Classification bass;
    bass.category = "Bass";
    bass.subcategory = "Bass Loop";
    bass.secondaryTags = {"Loop", "Foley"};
    bass.confidence = 0.82f;
    bass.winningEvidence = "FILENAME";
    const auto record = fromLegacyTaxonomy(
        "sha256:abc", "/library/Bass_128_Cm.wav", bass, 2, 4);

    expect(record.isValid(), "adapted record must validate");
    expect(record.identity.value == "Bass", "identity must exclude form");
    expect(record.form.value == "loop", "form must be independent");
    expect(record.family.value == "Bass", "family must preserve category");
    expect(record.attributes.count("Foley") == 1,
           "non-form legacy tag must remain an attribute");
    expect(record.legacy.subcategory == "Bass Loop",
           "legacy result must be preserved byte-for-byte");

    AbletonTaxonomy::Classification unknown;
    const auto unknownRecord = fromLegacyTaxonomy(
        "sha256:def", "/library/mystery.wav", unknown, 2, 4);
    expect(unknownRecord.isValid(), "unknown record is valid evidence");
    expect(unknownRecord.identity.state == ClaimState::unknown,
           "missing identity must remain unknown");
    expect(unknownRecord.form.state == ClaimState::unknown,
           "missing form must remain unknown");

    auto invalid = record;
    invalid.identity.confidence = 1.1f;
    expect(!invalid.isValid(), "out-of-range confidence must fail closed");

    if (failures == 0) std::cout << "AudioEvidence tests passed\n";
    return failures == 0 ? 0 : 1;
}

