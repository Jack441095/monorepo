#pragma once

#include <atomic>
#include <string>
#include <vector>

// Ableton Live-oriented sample taxonomy: Category / Subcategory / secondary
// tags, built on top of the existing heuristic instrument classifier
// (SampleManagerEngine.cpp's classifyAudioFeatures) rather than replacing
// it -- this module maps that classifier's output onto a richer, Ableton
// Browser-friendly taxonomy and adds the one genuinely new signal the
// existing pipeline didn't have: loop-vs-one-shot detection.
//
// Deliberately does NOT attempt distinctions the current DSP feature set
// (zero-crossing rate, low/high energy ratio, decay time, pitch sweep) can't
// actually support with real confidence -- e.g. Guitar vs Piano vs Keys, or
// Pad vs Lead vs Chord. Inventing those would mean presenting a guess as a
// classification, which the design explicitly rejects. Where the signal
// genuinely doesn't support a fine-grained answer, this returns a coarser
// category and a low confidence score instead of a specific, unearned one.
namespace AbletonTaxonomy {

// P2-2 LOOP V2SPIKE (default OFF): filename-never-decides-alone for the
// Vocal loop/phrase choice. Gated behind a runtime flag so shipped V1
// behavior is bit-identical until the corpus gate (loop macro-F1 >= 0.70
// vendor-held-out) passes and the owner promotes it.
inline std::atomic<bool> g_loopV2Enabled{false};
inline void setLoopV2Enabled(bool on) noexcept
{
    g_loopV2Enabled.store(on, std::memory_order_relaxed);
}
inline bool loopV2Enabled() noexcept
{
    return g_loopV2Enabled.load(std::memory_order_relaxed);
}
// Only a confident DSP vote may contest filename evidence. The detector's
// 0.70 "long but decayed" path defers to the filename; the two 0.85 paths
// may overrule it.
static constexpr float kLoopV2DspConfidenceFloor = 0.80f;

// Bumped whenever the mapping/heuristics below change in a way that would
// alter previously-produced results -- lets the engine decide whether an
// existing cached classification needs to be recomputed. Stored per-sample
// as SampleItem::taxonomyVersion.
constexpr int kTaxonomyVersion = 5;

struct Classification {
    std::string category;                   // e.g. "Drums", "Bass", "Vocals", "Instruments", "FX", "Ambience"
    std::string subcategory;                // e.g. "Kick", "Bass One-Shot", "Vocal Phrase"
    std::vector<std::string> secondaryTags;  // e.g. {"Loop"}, {"One-Shot", "Atonal", "Foley"}
    float confidence = 0.0f;                // 0..1 -- see classify()'s doc comment for how this is derived
    std::string winningEvidence = "UNKNOWN"; // "USER_OVERRIDE" | "EMBEDDED_METADATA" | "FILENAME" | "FOLDER" | "DSP" | "UNKNOWN"
};

// Domain-specific filename/folder evidence for the loop-vs-one-shot(/phrase)
// subcategory choice specifically -- distinct from, and computed in addition
// to, the existingInstrumentType detection upstream (which only decides
// *category*, e.g. "this is a Vocal"). "loop" and "phrase"/"chop"/"oneshot"
// are domain-specific multi-token evidence (they only mean something once
// existingInstrumentType has already narrowed the field to e.g. Vocal) and
// so are stronger evidence for this specific choice than the generic
// DSP-only duration/decay heuristic in detectLoopVsOneShot(). See
// docs/SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md for the root-cause analysis
// this was added to fix (V4-H's diagnosed Vocal Loop <-> Vocal Phrase
// filename-evidence defect: the DSP-only heuristic was overriding an
// explicit "loop" token in the filename with no filename evidence
// consulted at all for this specific decision).
struct FilenameSubcategoryEvidence {
    bool hasLoopToken = false;     // filename/folder tokens contain "loop"/"loops"
    bool hasOneShotToken = false;  // filename/folder tokens contain "phrase"/"phrases"/"chop"/"chops"/"oneshot"

    // A second, independent piece of domain-specific evidence for loop-ness:
    // a plausible BPM number immediately adjacent to a recognized musical
    // key token (e.g. "..._128_D.wav", "..._88_C#m.wav"). This is a
    // widespread, vendor-independent sample-library naming convention for a
    // tempo/pitch-locked musical loop -- one-shots and spoken phrases are
    // not tempo-synced and so are conventionally not given a musical key.
    // Real-corpus forensics for this fix found this is the dominant signal
    // actually distinguishing "Vocal Loop" from "Vocal Phrase" filenames in
    // practice (vendor names rarely spell out the literal word "loop"), so
    // it counts as loop evidence alongside hasLoopToken below -- see
    // docs/SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md.
    bool hasTempoKeySuffix = false;

    // Tempo-only convention (for example "Vocal_72_BPM") is weaker than a
    // tempo+key pair but remains useful for Vocal Loop review. It is kept as
    // a separate signal so callers cannot accidentally treat it as a key.
    bool hasTempoMarker = false;
};

// Computed from already-tokenized filename + parent-folder tokens (see
// SampleManagerEngine::tokenizeString, which strips digits as separators --
// fine for word-token matching but useless for the BPM+key check) plus the
// raw, digit-preserving "_ -"-split filename segments (mirroring
// parseBpmFromFilename/parseKeyFromFilename's own tokenization) used only
// for the tempo-marker adjacency checks. Pure, no JUCE/file-I/O dependency, so
// this stays trivially unit-testable here alongside classify().
FilenameSubcategoryEvidence detectFilenameSubcategoryEvidence(
    const std::vector<std::string>& nameTokens,
    const std::vector<std::string>& folderTokens,
    const std::vector<std::string>& rawNameSegments = {});

// Everything classify() needs, gathered from elsewhere in the engine and
// passed in by value -- this module does no file I/O or DSP of its own,
// which keeps it trivially unit-testable with synthetic inputs.
struct ClassificationInput {
    // The existing heuristic classifier's output (classifyAudioFeatures());
    // already incorporates filename/folder evidence upstream (see
    // SampleManagerEngine::prepareFile), so filename matching for
    // *category* is NOT re-done here -- this only maps and refines what's
    // already been decided. filenameEvidence below is the one exception:
    // it carries loop-vs-one-shot-specific token evidence that the
    // upstream category detection deliberately does not use (see
    // FilenameSubcategoryEvidence's doc comment).
    std::string existingInstrumentType;
    // Used only for the Foley source attribute (provenance), never for
    // the functional class -- see isFoleySourced().
    std::string fileName;

    float durationSeconds = 0.0f;
    float decayTimeSeconds = 0.0f;
    // Energy in the final third divided by energy in the first third. A
    // one-shot decays toward silence (crash ~0.00); a loop sustains (~0.87).
    // Default 1.0 = "sustained", so a legacy row with no stored value is not
    // spuriously demoted to one-shot.
    float energyDecayRatio = 1.0f;
    float zcr = 0.0f;
    float lowEnergyRatio = 0.0f;
    float highEnergyRatio = 0.0f;
    std::string winningEvidence = "UNKNOWN";
    FilenameSubcategoryEvidence filenameEvidence;
};

// Loop-vs-one-shot is the one genuinely new DSP signal this module adds.
// Heuristic, not a real seamless-loop-point detector -- confidence is
// capped accordingly (see .cpp for the exact reasoning and thresholds).
struct LoopDetectionResult {
    bool isLoop = false;
    float confidence = 0.0f;
};
// Loop vs one-shot from duration + sustained-energy ratio.
//
// MEASURED (649 by-ear labels, 5-fold CV with thresholds fitted on the train
// fold only): 96.4% held-out, versus 90.8% for duration alone. `duration >=
// 1.5s` was selected in all five folds.
//
// This replaces the previous duration/decayTime-ratio heuristic, which its own
// comment recorded as having "limited discriminative power" and being chosen to
// verify "net-neutral" -- i.e. it changed no outcomes. The failure mode it could
// not handle is a long one-shot with a natural tail: a crash rings >2.5s and was
// promoted to Loop. Energy-decay ratio separates those cleanly because a crash's
// energy is front-loaded (~0.00 by the final third) while a loop's is even
// (~0.87).
//
// The `decayTimeSeconds` overload is retained for callers that have not been
// updated; it forwards with a neutral ratio and therefore behaves as
// duration-only.
// Is this sample foley-SOURCED -- i.e. made by recording a physical object?
//
// Foley is a provenance fact, not an acoustic one, and it must not be a
// classifier target: measured 19-27% from audio across three independent
// encoders and 4% from handcrafted features, with an acoustic coherence of
// 0.656 (second-lowest in the taxonomy, just above the bin named "none").
// Deriving it from audio would be wrong ~75% of the time, which is exactly
// what you do not want for a category users search by.
//
// It IS reliably readable from naming: explicit foley wording plus
// unambiguous physical-object nouns gives 62% recall at 69% precision on
// by-ear labels. So it is emitted as a SECONDARY TAG that coexists with the
// functional subcategory. A hi-hat built from clock-shop recordings is
// honestly {subcategory: "Hi-Hat Loop", tags: [..., "Foley"]} -- findable
// both ways. Producers name samples after what MADE them even when they
// function as drums, which is why object nouns scored only 31% as a Foley
// CLASS detector: they were right about provenance and marked wrong for it.
//
// Vocabulary deliberately excludes producer-descriptor words that merely look
// like objects -- "dirty" means distorted, "knock" describes a snare's punch,
// "metal" is often a genre. Including those dropped precision to 32%.
bool isFoleySourced(const std::string& fileName);

LoopDetectionResult detectLoopVsOneShot(float durationSeconds, float decayTimeSeconds,
                                        float energyDecayRatio);
LoopDetectionResult detectLoopVsOneShot(float durationSeconds, float decayTimeSeconds);

// Produces a Category/Subcategory/secondary-tags classification.
//
// Confidence is the product of how directly existingInstrumentType maps to
// a specific subcategory (crisp for Kick/Snare/Clap, deliberately low for
// vaguer buckets like "Other") and the loop-detection confidence where that
// signal was used to pick between two subcategory variants. This is an
// honest, if approximate, signal -- not a calibrated probability.
Classification classify(const ClassificationInput& input);

bool mapAcousticClassToTaxonomy(const std::string& acousticClass, std::string& outCategory, std::string& outSubcategory);

} // namespace AbletonTaxonomy
