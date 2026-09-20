#pragma once

// Append-only log of user label corrections.
//
// Measurement across this whole programme is unambiguous: by-ear labels are the
// ONLY intervention that has ever improved SLO on unseen libraries (+3.29pp
// accuracy and -17.9pp false-accept per 500). Twenty-plus method-side routes --
// nine encoders, six feature families, LoRA, GroupDRO, DANN, CORAL,
// augmentation, factorised taxonomy, taxonomy expansion -- produced nothing.
//
// So every time a user corrects a tag, that is the single most valuable event
// SLO can observe: a by-ear label on a file the model got wrong, drawn from the
// real deployment distribution rather than a curated sample. This captures it.
//
// Design constraints, all safety constraints:
//   * NO AUDIO. A path and metadata only. The log can be inspected or shared
//     without moving a single licensed sample.
//   * APPEND-ONLY JSONL. A partial line from a crash costs one record, never
//     the file. Nothing is ever rewritten in place.
//   * CAPTURES THE ORIGINAL. updateTaxonomyAsync overwrites the model's
//     prediction the moment a user edits it, so the original must be read
//     BEFORE the write or the correction loses the thing that makes it useful.
//   * NEVER THROWS, NEVER BLOCKS A DECISION. A logging failure must not affect
//     what the user sees or what the engine does.
//   * PENDING BY DEFAULT. Nothing here is ground truth. Promotion into the
//     dataset is a separate, explicit, owner-driven act.

// Standard library only -- deliberately no JUCE. BetaDecisionPolicy.h is pure
// for the same reason: a header that cannot be tested without linking the whole
// framework does not get tested, and this one guards the most valuable asset
// SLO has.
#include <string>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <ctime>
#include <chrono>
#include <filesystem>
#include <cstdlib>

namespace slo {

struct CorrectionRecord {
    std::string filePath;
    std::string contentHash;        // identity that survives a rename
    std::string originalCategory;   // what the model said, BEFORE the user edit
    std::string originalSubcategory;
    std::string originalEvidence;   // FILENAME | FOLDER | DSP | EMBEDDED_METADATA
    float       originalConfidence = 0.0f;
    std::string correctedCategory;  // what the user said
    std::string correctedSubcategory;
    // Explicit correction semantics. This prevents an unlabeled "Unknown"
    // escape from being mistaken for a normal taxonomy edit.
    std::string correctionType = "label_correction";
    std::string userNote;
    int         taxonomyVersion = 0;
    int         classifierVersion = 0;
    std::string policyVersion = "1.0.0";
};

inline std::string defaultCorrectionLogPath() {
    const char* home = std::getenv("HOME");
    std::filesystem::path p = home ? std::filesystem::path(home) : std::filesystem::path(".");
    return (p / "Library" / "Application Support" / "SLO" / "corrections.jsonl").string();
}

inline std::string jsonEscape(const std::string& s) {
    std::ostringstream o;
    for (unsigned char c : s) {
        switch (c) {
            case '"':  o << "\\\""; break;
            case '\\': o << "\\\\"; break;
            case '\n': o << "\\n";  break;
            case '\r': o << "\\r";  break;
            case '\t': o << "\\t";  break;
            default:
                if (c < 0x20) o << "\\u" << std::hex << std::setw(4)
                                 << std::setfill('0') << (int) c << std::dec;
                else o << (char) c;
        }
    }
    return o.str();
}

inline std::string isoNow() {
    const auto t = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &t);
#else
    gmtime_r(&t, &tm);
#endif
    std::ostringstream o;
    o << std::put_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
    return o.str();
}

inline std::string toJsonLine(const CorrectionRecord& r) {
    std::ostringstream j;
    j << "{\"ts\":\"" << isoNow() << "\""
      << ",\"file_path\":\"" << jsonEscape(r.filePath) << "\""
      << ",\"content_hash\":\"" << jsonEscape(r.contentHash) << "\""
      << ",\"original_category\":\"" << jsonEscape(r.originalCategory) << "\""
      << ",\"original_subcategory\":\"" << jsonEscape(r.originalSubcategory) << "\""
      << ",\"original_evidence\":\"" << jsonEscape(r.originalEvidence) << "\""
      << ",\"original_confidence\":" << r.originalConfidence
      << ",\"corrected_category\":\"" << jsonEscape(r.correctedCategory) << "\""
      << ",\"corrected_subcategory\":\"" << jsonEscape(r.correctedSubcategory) << "\""
      << ",\"correction_type\":\"" << jsonEscape(r.correctionType) << "\""
      << ",\"user_note\":\"" << jsonEscape(r.userNote) << "\""
      << ",\"taxonomy_version\":" << r.taxonomyVersion
      << ",\"classifier_version\":" << r.classifierVersion
      << ",\"policy_version\":\"" << jsonEscape(r.policyVersion) << "\""
      << ",\"status\":\"pending\"}";
    return j.str();
}

// Returns false on failure. Callers deliberately ignore it: a correction that
// cannot be logged must never change what the engine does for the user.
inline bool appendCorrection(const CorrectionRecord& r,
                             const std::string& logPath = defaultCorrectionLogPath()) {
    // A no-op edit is not a correction. Recording it would inflate the value of
    // the log with events that carry no information.
    if (r.originalCategory == r.correctedCategory
        && r.originalSubcategory == r.correctedSubcategory
        && r.userNote.empty())
        return false;
    if (r.filePath.empty())
        return false;
    std::error_code ec;
    std::filesystem::create_directories(
        std::filesystem::path(logPath).parent_path(), ec);
    std::ofstream out(logPath, std::ios::app);   // append; never rewrite
    if (!out.is_open())
        return false;
    out << toJsonLine(r) << "\n";
    return out.good();
}

} // namespace slo
