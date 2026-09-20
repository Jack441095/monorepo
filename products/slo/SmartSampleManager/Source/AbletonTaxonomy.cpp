#include "AbletonTaxonomy.h"
#include <cstdlib>
#include <cctype>
#include <string>

namespace AbletonTaxonomy {

bool isFoleySourced(const std::string& fileName)
{
    // Lowercase and normalise separators so "clock_shop" and "Clock-Shop"
    // both read as word-separated (underscores are word characters, so a
    // naive boundary match misses them -- the same trap that halved the
    // Python detector's coverage until it was fixed).
    std::string n;
    n.reserve(fileName.size());
    for (char ch : fileName) {
        const unsigned char u = static_cast<unsigned char>(ch);
        n.push_back((ch == '_' || ch == '-' || ch == '.') ? ' '
                    : static_cast<char>(std::tolower(u)));
    }

    auto hasWord = [&n](const char* w) {
        const std::string needle(w);
        size_t pos = n.find(needle);
        while (pos != std::string::npos) {
            const bool leftOk  = (pos == 0) || !std::isalnum(static_cast<unsigned char>(n[pos - 1]));
            const size_t end   = pos + needle.size();
            const bool rightOk = (end >= n.size()) || !std::isalnum(static_cast<unsigned char>(n[end]));
            if (leftOk && rightOk) return true;
            pos = n.find(needle, pos + 1);
        }
        return false;
    };

    // Explicit foley wording -- the highest-precision signal (75%).
    for (const char* w : {"foley", "found sound", "field rec", "household"})
        if (hasWord(w)) return true;

    // Unambiguous physical objects. Excluded on measurement: dirt/dirty
    // (means distorted), knock (snare punch), metal (often genre), spring,
    // match, tap, fan, water, wind, fire -- all common as non-objects.
    for (const char* w : {"kitchen", "wood", "glass", "ceramic", "porcelain", "bottle",
                          "cup", "mug", "plate", "bowl", "spoon", "fork", "knife",
                          "coin", "book", "box", "bag", "zipper", "door", "drawer",
                          "chair", "table", "cupboard", "window", "stair", "footstep",
                          "scrape", "rustle", "crumple", "squeak", "creak", "splash",
                          "drip", "gravel", "chain", "rope", "hinge", "latch",
                          "lighter", "clock", "typewriter", "suitcase", "umbrella",
                          "hammer", "drill", "paper", "cardboard", "cloth", "fabric",
                          "leather", "rubber", "stone", "cutlery", "crockery"})
        if (hasWord(w)) return true;

    return false;
}

LoopDetectionResult detectLoopVsOneShot(float durationSeconds, float decayTimeSeconds,
                                        float energyDecayRatio)
{
    // See the header for the measurement. Two thresholds, both validated
    // held-out: length, and whether energy actually persists to the end.
    static constexpr float kMinLoopSeconds = 1.5f;
    static constexpr float kMinSustainedRatio = 0.10f;

    (void) decayTimeSeconds;   // superseded; kept for signature compatibility

    const bool longEnough = durationSeconds >= kMinLoopSeconds;
    const bool sustained  = energyDecayRatio >= kMinSustainedRatio;
    // Samples >= 4.0s in music production are sustained loops or musical phrases,
    // even with natural reverb/release tails.
    const bool veryLong = durationSeconds >= 4.0f;

    LoopDetectionResult result;
    if (longEnough && (sustained || veryLong)) {
        result.isLoop = true;
        result.confidence = 0.85f;      // 96.4% held-out when both agree
    } else if (!longEnough) {
        // Too short to tile. The strongest one-shot signal available.
        result.isLoop = false;
        result.confidence = 0.85f;
    } else {
        // Long but decayed to silence: a one-shot with a natural tail --
        // a crash, a reverb-tailed hit, a sustained vocal note. This is the
        // case the previous heuristic got wrong.
        // a crash, a reverb-tailed hit, a sustained vocal note.
        result.isLoop = false;
        result.confidence = 0.70f;
    }
    return result;
}

LoopDetectionResult detectLoopVsOneShot(float durationSeconds, float decayTimeSeconds)
{
    // Back-compat path for callers that cannot supply energyDecayRatio.
    //
    // This deliberately preserves the ORIGINAL duration/decay-ratio heuristic
    // rather than forwarding a neutral ratio. Forwarding 1.0 ("sustained")
    // would classify every file >= 1.5s as a loop, silently breaking the
    // long-but-fast-decaying one-shot case (a crash, a reverb tail) for any
    // caller that has not been updated. Behaviour here is unchanged; only
    // callers passing a real ratio get the measured rule.
    const bool longEnough = durationSeconds > 1.5f;
    const bool sustained = decayTimeSeconds > 0.0f && durationSeconds > 0.0f
        && (decayTimeSeconds / durationSeconds) > 0.9f;

    LoopDetectionResult result;
    if (longEnough && sustained) {
        result.isLoop = true;  result.confidence = 0.65f;
    } else if (!longEnough && decayTimeSeconds < 0.35f) {
        result.isLoop = false; result.confidence = 0.6f;
    } else {
        result.isLoop = false; result.confidence = 0.25f;
    }
    return result;
}

namespace {

// existingInstrumentType values that reach here are drawn from two sources
// upstream in prepareFile(): the filename/folder heuristic block (Clap,
// Percussion, Synth, Vocal, Powerup, Jump, Coin, Footstep, Impact, and also
// Kick/Snare/Hi-Hat/Bass/Loop/UI/Explosion by name match) and, only when
// that finds no match, classifyAudioFeatures()'s own DSP-only fallback
// (UI, Laser, Kick, Hi-Hat, Snare, Explosion, Bass, Loop, Other). Both
// sources are handled uniformly here since the field means the same thing
// either way by the time it reaches this function.

struct BaseMapping {
    std::string category;
    std::string subcategoryOneShot;
    std::string subcategoryLoop;   // empty means: this instrumentType has no loop variant, ignore loop detection
    float baseConfidence;          // how directly instrumentType maps onto this specific subcategory
};

bool lookupBaseMapping(const std::string& instrumentType, BaseMapping& out)
{
    // Crisp, well-supported drum / percussion subcategories
    // Loop variants. Drums previously collapsed ALL loop forms to "Drum Loop",
    // while melodic instruments each kept a specific one (Pad->Pad Loop etc).
    // Measured against 649 by-ear labels: when a filename carries a type token
    // AND the file is a loop, the specific variant is correct -- Kick Loop 2/2,
    // Hi-Hat 3/3, Percussion 10/13. So the specific variant is used for those
    // types (small n; the direction is consistent and matches the melodic
    // convention already in this table).
    //
    // "Drum Loop" remains the default for everything else, which the same
    // measurement supports: 40 of 41 by-ear Drum Loops carry NO type token at
    // all -- a real drum loop is a full beat named "113BPM_2", not "kick".
    // Clap/Crash/Ride/Tom/Rimshot keep "Drum Loop": loop forms of those are
    // rare and unevidenced here, so inventing a variant would be guessing.
    if (instrumentType == "Kick")        { out = {"Drums", "Kick", "Kick Loop", 0.85f}; return true; }
    if (instrumentType == "Snare")       { out = {"Drums", "Snare", "Snare Loop", 0.8f}; return true; }
    if (instrumentType == "Hi-Hat")      { out = {"Drums", "Hi-Hat", "Hi-Hat Loop", 0.8f}; return true; }
    if (instrumentType == "Clap")        { out = {"Drums", "Clap", "Drum Loop", 0.8f}; return true; }
    if (instrumentType == "Percussion")  { out = {"Drums", "Percussion", "Percussion Loop", 0.7f}; return true; }
    if (instrumentType == "Rimshot")     { out = {"Drums", "Rimshot", "Drum Loop", 0.8f}; return true; }
    if (instrumentType == "Crash")       { out = {"Drums", "Crash", "Drum Loop", 0.8f}; return true; }
    if (instrumentType == "Ride")        { out = {"Drums", "Ride", "Drum Loop", 0.8f}; return true; }
    if (instrumentType == "Tom")         { out = {"Drums", "Tom", "Drum Loop", 0.8f}; return true; }
    if (instrumentType == "Drum Fill")   { out = {"Drums", "Drum Fill", "Drum Loop", 0.85f}; return true; }

    // Bass
    if (instrumentType == "Bass")        { out = {"Bass", "Bass One-Shot", "Bass Loop", 0.75f}; return true; }

    // Melodic Instruments (Expanded Roster)
    if (instrumentType == "Pad")         { out = {"Instruments", "Pad", "Pad Loop", 0.85f}; return true; }
    if (instrumentType == "Piano")       { out = {"Instruments", "Piano", "Piano Loop", 0.85f}; return true; }
    if (instrumentType == "Guitar")      { out = {"Instruments", "Guitar", "Guitar Loop", 0.85f}; return true; }
    if (instrumentType == "Pluck")       { out = {"Instruments", "Pluck", "Pluck Loop", 0.8f}; return true; }
    if (instrumentType == "Lead")        { out = {"Instruments", "Lead", "Lead Loop", 0.8f}; return true; }
    if (instrumentType == "Brass")       { out = {"Instruments", "Brass", "Brass Loop", 0.8f}; return true; }
    if (instrumentType == "Strings")     { out = {"Instruments", "Strings", "Strings Loop", 0.8f}; return true; }
    if (instrumentType == "Organ")       { out = {"Instruments", "Organ", "Organ Loop", 0.8f}; return true; }
    if (instrumentType == "Synth")       { out = {"Instruments", "Synth", "Synth Loop", 0.6f}; return true; }

    // Vocals (Expanded Roster)
    if (instrumentType == "Vocal Chop")  { out = {"Vocals", "Vocal Chop", "Vocal Loop", 0.85f}; return true; }
    if (instrumentType == "Vocal Lead")  { out = {"Vocals", "Vocal Lead", "Vocal Loop", 0.85f}; return true; }
    if (instrumentType == "Vocal")       { out = {"Vocals", "Vocal Phrase", "Vocal Loop", 0.7f}; return true; }

    // FX / Sound Design (Expanded Roster)
    if (instrumentType == "Riser")       { out = {"FX", "Riser", "", 0.8f}; return true; }
    if (instrumentType == "Downlifter")  { out = {"FX", "Downlifter", "", 0.8f}; return true; }
    if (instrumentType == "Explosion")   { out = {"FX", "Impact", "", 0.6f}; return true; }
    if (instrumentType == "Impact")      { out = {"FX", "Impact", "", 0.6f}; return true; }
    if (instrumentType == "Laser")       { out = {"FX", "Riser", "", 0.45f}; return true; }
    if (instrumentType == "Powerup")     { out = {"FX", "FX", "", 0.4f}; return true; }
    if (instrumentType == "Jump")        { out = {"FX", "FX", "", 0.4f}; return true; }
    if (instrumentType == "Coin")        { out = {"FX", "FX", "", 0.4f}; return true; }
    if (instrumentType == "UI")          { out = {"FX", "FX", "", 0.5f}; return true; }
    if (instrumentType == "Footstep")    { out = {"FX", "Foley", "", 0.6f}; return true; }

    // "Loop" from classifyAudioFeatures() is itself a catch-all for
    // "sustained, complex, not obviously percussive" -- genuinely
    // ambiguous between a music loop and an ambience/texture bed. Resolve
    // further using zcr/energy in classify() below rather than here.
    return false;
}

bool containsAnyOf(const std::vector<std::string>& tokens, std::initializer_list<const char*> searchList)
{
    for (const auto& token : tokens)
        for (const auto* search : searchList)
            if (token == search)
                return true;
    return false;
}

// Same key vocabulary as SampleManagerEngine.cpp's parseKeyFromFilename
// (lowercased, atomic tokens only -- that function's own "c_minor"-style
// entries can never actually match post-split and are omitted here too).
bool isMusicalKeyToken(const std::string& t)
{
    static const std::initializer_list<const char*> keys = {
        "c", "d", "e", "f", "g", "a", "b",
        "c#", "db", "d#", "eb", "f#", "gb", "g#", "ab", "a#", "bb",
        "cm", "cmin", "dm", "dmin", "em", "emin", "fm", "fmin",
        "gm", "gmin", "am", "amin", "bm", "bmin",
        "c#m", "dbm", "d#m", "ebm", "f#m", "gbm", "g#m", "abm", "a#m", "bbm",
        "cmaj", "dmaj", "emaj", "fmaj", "gmaj", "amaj", "bmaj"
    };
    for (const auto* k : keys)
        if (t == k) return true;
    return false;
}

bool isPlausibleBpmToken(const std::string& t)
{
    if (t.empty()) return false;
    for (char c : t)
        if (!(c >= '0' && c <= '9')) return false;
    // Same broad range as parseBpmFromFilename's bare-number branch.
    int val = std::atoi(t.c_str());
    return val >= 40 && val <= 220;
}

// extractSemanticFilenameTokens() deliberately preserves punctuation so key
// spellings such as C# survive.  Vendor BPM suffixes, however, are commonly
// wrapped in brackets/parentheses ("[72 BPM]", "(120 BPM)").  Normalize only
// boundary punctuation for the adjacency checks; do not alter the original
// token stream used for ordinary word evidence.
std::string trimEvidenceBoundaryPunctuation(const std::string& token)
{
    size_t begin = 0;
    size_t end = token.size();
    const auto isTokenChar = [](char c) {
        return std::isalnum(static_cast<unsigned char>(c)) || c == '#';
    };
    while (begin < end && !isTokenChar(token[begin])) ++begin;
    while (end > begin && !isTokenChar(token[end - 1])) --end;
    return token.substr(begin, end - begin);
}

// True if any adjacent pair of raw (digit-preserving) filename segments is
// a plausible-BPM-number next to a recognized musical-key token, in either
// order ("<bpm>_<key>" and "<key>_<bpm>" both appear in real vendor naming).
bool hasAdjacentTempoKeyPair(const std::vector<std::string>& rawSegments)
{
    for (size_t i = 0; i + 1 < rawSegments.size(); ++i) {
        const std::string a = trimEvidenceBoundaryPunctuation(rawSegments[i]);
        const std::string b = trimEvidenceBoundaryPunctuation(rawSegments[i + 1]);
        const bool aBpm = isPlausibleBpmToken(a);
        const bool bBpm = isPlausibleBpmToken(b);
        const bool aKey = isMusicalKeyToken(a);
        const bool bKey = isMusicalKeyToken(b);
        if ((aBpm && bKey) || (aKey && bBpm)) return true;

        // Bracketed vendor suffixes are often split into three semantic
        // segments: "[73 BPM] (F#)" -> "[73", "bpm]", "(f#)".
        // Treat the literal BPM marker as a bridge while keeping the key
        // requirement intact; this does not broaden bare-number matching.
        if (i + 2 < rawSegments.size()) {
            const std::string c = trimEvidenceBoundaryPunctuation(rawSegments[i + 2]);
            const bool aBpmWithMarker = aBpm && b == "bpm";
            const bool cBpmWithMarker = c == "bpm" && bBpm;
            const bool cKey = isMusicalKeyToken(c);
            if ((aBpmWithMarker && cKey) || (aKey && cBpmWithMarker)) return true;
        }
    }
    return false;
}

bool hasAdjacentTempoMarker(const std::vector<std::string>& rawSegments)
{
    for (size_t i = 0; i + 1 < rawSegments.size(); ++i) {
        const std::string a = trimEvidenceBoundaryPunctuation(rawSegments[i]);
        const std::string b = trimEvidenceBoundaryPunctuation(rawSegments[i + 1]);
        const bool aBpm = isPlausibleBpmToken(a);
        const bool bBpm = isPlausibleBpmToken(b);
        const bool aMarker = a == "bpm";
        const bool bMarker = b == "bpm";
        if ((aBpm && bMarker) || (aMarker && bBpm)) return true;
    }
    return false;
}

} // namespace

FilenameSubcategoryEvidence detectFilenameSubcategoryEvidence(
    const std::vector<std::string>& nameTokens,
    const std::vector<std::string>& folderTokens,
    const std::vector<std::string>& rawNameSegments)
{
    // Deliberately narrow token sets: only tokens that directly describe
    // THIS sample's loop-ness once category is already known, not the
    // broader vocabulary used for category detection upstream. "oneshot"
    // covers the unhyphenated spelling; tokenizeString() splits on '-' and
    // digits, so "one-shot" itself tokenizes to {"one","shot"} -- those are
    // too generic to treat as reliable evidence here, so deliberately left
    // unmatched (falls through to the DSP heuristic, same as today).
    FilenameSubcategoryEvidence evidence;
    evidence.hasLoopToken = containsAnyOf(nameTokens, {"loop", "loops"})
        || containsAnyOf(folderTokens, {"loop", "loops"});
    auto matchesLoopToken = [](const std::vector<std::string>& tokens) {
        for (const auto& t : tokens) {
            if (t == "loop" || t == "loops" || t == "drumloop" || t == "toploop" || t == "bassloop" || t == "synthloop")
                return true;
            if (t.find("loop") != std::string::npos)
                return true;
            if (t.find("loo") != std::string::npos && t.find("p") != std::string::npos)
                return true; // catches elongated spellings like "looop"
        }
        return false;
    };
    evidence.hasLoopToken = matchesLoopToken(nameTokens) || matchesLoopToken(folderTokens);
    evidence.hasOneShotToken = containsAnyOf(nameTokens, {"phrase", "phrases", "chop", "chops", "oneshot"})
        || containsAnyOf(folderTokens, {"phrase", "phrases", "chop", "chops", "oneshot"});
    evidence.hasTempoKeySuffix = hasAdjacentTempoKeyPair(rawNameSegments);
    evidence.hasTempoMarker = hasAdjacentTempoMarker(rawNameSegments);
    return evidence;
}

Classification classify(const ClassificationInput& input)
{
    Classification result;
    result.winningEvidence = input.winningEvidence;

    BaseMapping mapping;
    if (input.existingInstrumentType == "Loop") {
        // High zcr with no strong low-end dominance reads as noise-like /
        // atonal content (wind, static, granular texture) rather than a
        // tonal/rhythmic music loop -- distinguishing "Ambience" from
        // "Instruments" this way is a real, if soft, signal from the
        // existing features, not a fabricated one.
        const bool noiseLike = input.zcr > 0.25f && input.lowEnergyRatio < 0.5f;
        result.category = noiseLike ? "Ambience" : "Instruments";
        result.subcategory = noiseLike ? "Atmosphere" : "Music Loop";
        result.secondaryTags.push_back("Loop");
        if (noiseLike) result.secondaryTags.push_back("Atonal");
        result.confidence = 0.4f;
        return result;
    }

    if (!lookupBaseMapping(input.existingInstrumentType, mapping)) {
        // "Other" or any unrecognized value: don't invent a subcategory.
        result.category = "";
        result.subcategory = "";
        result.confidence = 0.0f;
        return result;
    }

    float evidenceMultiplier = 1.0f;
    if (input.winningEvidence == "EMBEDDED_METADATA") evidenceMultiplier = 1.0f;
    else if (input.winningEvidence == "FILENAME") evidenceMultiplier = 0.95f;
    else if (input.winningEvidence == "FOLDER") evidenceMultiplier = 0.85f;
    else if (input.winningEvidence == "DSP") evidenceMultiplier = 0.75f;
    const float effectiveBaseConfidence = mapping.baseConfidence * evidenceMultiplier;

    if (mapping.subcategoryLoop.empty()) {
        // No loop variant for this bucket -- use the one-shot label as-is.
        result.category = mapping.category;
        result.subcategory = mapping.subcategoryOneShot;
        result.secondaryTags.push_back("One-Shot");
        result.confidence = effectiveBaseConfidence;
        return result;
    }

    // V4-H Vocal Loop fix: for Vocal specifically, unambiguous filename/
    // folder evidence for loop-ness is domain-specific multi-token evidence
    // for THIS choice and beats the generic DSP-only duration/decay
    // heuristic below, which was silently discarding it entirely -- see
    // docs/SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md for the forensics. Two
    // independent signals count as "loop evidence": an explicit "loop"
    // word token, and a BPM+musical-key filename suffix (the dominant
    // signal on the real vendor corpus forensics used -- vendors rarely
    // spell out the word "loop", but tempo/key-locked loops are almost
    // always suffixed with their BPM and key, while one-shots/phrases are
    // not). "phrase"/"chop"/"oneshot" word tokens are the one-shot-side
    // signal. Scoped to Vocal only (not generalized to Kick/Bass/Synth/
    // etc.) per V4-H's root-cause finding that only Vocal Loop/Phrase was
    // affected; widening scope was explicitly out of bounds for this fix.
    // When both sides have evidence (or neither does) the signal is
    // ambiguous (or absent) and this deliberately falls through to the
    // existing DSP-only path below, unchanged.
    const bool loopEvidence = input.filenameEvidence.hasLoopToken
        || input.filenameEvidence.hasTempoKeySuffix
        || input.filenameEvidence.hasTempoMarker;
    const bool oneShotEvidence = input.filenameEvidence.hasOneShotToken;
    if (input.existingInstrumentType == "Vocal" && loopEvidence != oneShotEvidence) {
        // P2-2 LOOP V2 (flagged, default OFF): when confident DSP disagrees
        // with one-sided filename evidence, the filename no longer decides
        // alone. The DSP verdict wins at a disagreement-discounted
        // confidence with a "Contested" tag (future review-queue filter);
        // weak-DSP and agreement cases fall through to V1 unchanged.
        if (loopV2Enabled())
        {
            const LoopDetectionResult dspVote = detectLoopVsOneShot(
                input.durationSeconds, input.decayTimeSeconds, input.energyDecayRatio);
            if (dspVote.confidence >= kLoopV2DspConfidenceFloor
                && dspVote.isLoop != loopEvidence)
            {
                result.category = mapping.category;
                result.subcategory = dspVote.isLoop ? mapping.subcategoryLoop : mapping.subcategoryOneShot;
                result.secondaryTags.push_back(dspVote.isLoop ? "Loop" : "One-Shot");
                result.secondaryTags.push_back("Contested");
                result.confidence = effectiveBaseConfidence
                    * (0.5f + 0.5f * dspVote.confidence) * 0.7f;
                return result;
            }
        }
        result.category = mapping.category;
        result.subcategory = loopEvidence ? mapping.subcategoryLoop : mapping.subcategoryOneShot;
        result.secondaryTags.push_back(loopEvidence ? "Loop" : "One-Shot");
        // A literal loop token or tempo+key pair is stronger than a tempo-only
        // marker. Keep the latter useful for recall, but make its lower
        // evidential strength visible to the policy layer.
        const bool tempoOnly = input.filenameEvidence.hasTempoMarker
            && !input.filenameEvidence.hasLoopToken
            && !input.filenameEvidence.hasTempoKeySuffix;
        result.confidence = effectiveBaseConfidence * (tempoOnly ? 0.8f : 0.9f);
        return result;
    }

    const LoopDetectionResult loopDetection = detectLoopVsOneShot(
        input.durationSeconds, input.decayTimeSeconds, input.energyDecayRatio);
    result.category = mapping.category;
    result.subcategory = loopDetection.isLoop ? mapping.subcategoryLoop : mapping.subcategoryOneShot;
    result.secondaryTags.push_back(loopDetection.isLoop ? "Loop" : "One-Shot");
    // Provenance attribute, orthogonal to the functional subcategory.
    if (isFoleySourced(input.fileName)) result.secondaryTags.push_back("Foley");
    result.confidence = effectiveBaseConfidence * (0.5f + 0.5f * loopDetection.confidence);
    return result;
}

bool mapAcousticClassToTaxonomy(const std::string& acousticClass, std::string& outCategory, std::string& outSubcategory)
{
    if (acousticClass == "Kick") { outCategory = "Drums"; outSubcategory = "Kick"; return true; }
    if (acousticClass == "Snare") { outCategory = "Drums"; outSubcategory = "Snare"; return true; }
    if (acousticClass == "Hi-Hat") { outCategory = "Drums"; outSubcategory = "Hi-Hat"; return true; }
    if (acousticClass == "Clap") { outCategory = "Drums"; outSubcategory = "Clap"; return true; }
    if (acousticClass == "Percussion") { outCategory = "Drums"; outSubcategory = "Percussion"; return true; }
    if (acousticClass == "Bass One-Shot") { outCategory = "Bass"; outSubcategory = "Bass One-Shot"; return true; }
    if (acousticClass == "Bass Loop") { outCategory = "Bass"; outSubcategory = "Bass Loop"; return true; }
    if (acousticClass == "Synth") { outCategory = "Instruments"; outSubcategory = "Synth"; return true; }
    if (acousticClass == "Synth Loop") { outCategory = "Instruments"; outSubcategory = "Synth Loop"; return true; }
    if (acousticClass == "Music Loop") { outCategory = "Instruments"; outSubcategory = "Music Loop"; return true; }
    if (acousticClass == "Vocal Phrase") { outCategory = "Vocals"; outSubcategory = "Vocal Phrase"; return true; }
    if (acousticClass == "Vocal Loop") { outCategory = "Vocals"; outSubcategory = "Vocal Loop"; return true; }
    if (acousticClass == "FX") { outCategory = "FX"; outSubcategory = "FX"; return true; }
    if (acousticClass == "Foley") { outCategory = "FX"; outSubcategory = "Foley"; return true; }
    if (acousticClass == "Impact") { outCategory = "FX"; outSubcategory = "Impact"; return true; }
    if (acousticClass == "Riser") { outCategory = "FX"; outSubcategory = "Riser"; return true; }
    return false;
}

} // namespace AbletonTaxonomy
