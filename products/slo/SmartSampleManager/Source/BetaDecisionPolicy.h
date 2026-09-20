#pragma once

// SLO beta decision policy -- what the product is ALLOWED to do with a
// classification, as distinct from what the classifier believes.
//
// The classifier is ~69.6% accurate collection-held-out. Sorting a library on
// that alone moves files on a coin-flip-plus. This header is the gate between
// "the model thinks this is a Kick" and "SLO may act on that".
//
// The candidate tiers below come from an older measured per-class receipt at a
// 0.5 gate (tools/classification_benchmark/results_rejection_boundary.json and
// SLO_DECISION_POLICY_LAYER_V1.md). The current collection-held-out audit did
// not promote any class to automatic action, so these remain *preview*
// candidates and still require explicit user approval in beta.
//
//     Kick 94.3%, Clap 93.5%, Drum Loop 90.8%   -> may act
//     Snare 82.9%, Crash 81.0%, Hi-Hat 80.0%,
//     Foley 68.0%, Percussion Loop 61.5%        -> suggest, needs approval
//     Percussion 15.4%                          -> NEVER act
//     impulse responses                         -> NEVER act
//
// Percussion is the one that matters. It is an incoherent parent class
// (silhouette -0.120) naming shakers, toms, rimshots and metallic hits at once,
// so it produces roughly five wrong moves for every right one. No confidence
// threshold repairs that -- the fix is taxonomy work. Until then it must never
// be moved or renamed automatically.
//
// Deliberately NOT per-class thresholds: those were measured and rejected for
// undershooting their precision promise by 12pp on unseen libraries. One global
// gate; only ELIGIBILITY varies by class.
//
// This header is pure and side-effect free. It never touches the filesystem.

#include <string>
#include <algorithm>
#include <cctype>

namespace slo {

enum class BetaAction {
    AutoRenameEligible,  // safe to PREVIEW a rename; still requires user approval
    Suggest,             // show the label, user applies
    Review,              // uncertain -- send to the review queue
    NeverAct             // unsafe or incoherent class; do not rename, do not assert
};

struct BetaDecision {
    BetaAction action = BetaAction::Review;
    std::string displayedLabel;
    float confidence = 0.0f;
    std::string reason;
    bool requiresApproval = true;
};

inline const char* toString(BetaAction a) {
    switch (a) {
        case BetaAction::AutoRenameEligible: return "auto_rename_eligible";
        case BetaAction::Suggest:            return "suggest";
        case BetaAction::Review:             return "review";
        case BetaAction::NeverAct:           return "never_act";
    }
    return "review";
}

inline std::string toLowerCopy(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

// An impulse response measures a SPACE; it is not a musical sample and renaming
// one is never useful. Detected by path because IR packs are foldered, and the
// audio itself can legitimately sound like the drum hit used to excite the room.
inline bool isImpulseResponsePath(const std::string& path) {
    const std::string p = toLowerCopy(path);
    return p.find("impluse") != std::string::npos   // the spelling in the wild
        || p.find("impulse") != std::string::npos
        || p.find("/ir/") != std::string::npos;
}

inline bool isNeverActClass(const std::string& subcategory) {
    return subcategory == "Percussion";
}

inline bool isAutoRenameClass(const std::string& subcategory) {
    // Historical high-confidence candidates for the user-approved rename
    // preview. This is not an automatic-action qualification.
    return subcategory == "Kick"
        || subcategory == "Clap"
        || subcategory == "Drum Loop";
}

inline bool isSuggestClass(const std::string& subcategory) {
    return subcategory == "Snare" || subcategory == "Hi-Hat" || subcategory == "Crash"
        || subcategory == "Percussion Loop" || subcategory == "Foley";
}

// Filename tokens measured to be actively misleading. "snap" reliably means a
// recorded Foley sound rather than a clap; the rest claim classes they cannot
// support. Where one is present the action is capped at Suggest EVEN IF the
// audio agrees -- agreement is not independent evidence when both the filename
// detector and the audio model are reading the same misleading token.
inline bool hasMisleadingToken(const std::string& fileName) {
    const std::string n = toLowerCopy(fileName);
    static const char* kTokens[] = { "snap", "tops", "chord" };
    for (const char* t : kTokens)
        if (n.find(t) != std::string::npos) return true;
    return false;
}

// gate: the global confidence threshold for the active operating point.
// 0.93 is a conservative preview operating point. It is intentionally not
// described as a statistically promoted automatic-action threshold: the
// current class-gate audit still requires a sealed validation set first.
inline BetaDecision decideBeta(const std::string& subcategory,
                               float confidence,
                               const std::string& filePath,
                               const std::string& fileName,
                               bool userOverridden = false,
                               float gate = 0.93f) {
    BetaDecision d;
    d.displayedLabel = subcategory;
    d.confidence = confidence;

    // A user's own label always wins and is always safe to apply.
    if (userOverridden) {
        d.action = BetaAction::AutoRenameEligible;
        d.reason = "user-assigned label";
        d.requiresApproval = false;
        return d;
    }
    if (isImpulseResponsePath(filePath)) {
        d.action = BetaAction::NeverAct;
        d.displayedLabel.clear();
        d.reason = "impulse response: a measurement of a space, not a sample";
        return d;
    }
    if (subcategory.empty() || subcategory == "Unknown" || subcategory == "Unclassified") {
        d.action = BetaAction::Review;
        d.displayedLabel.clear();
        d.reason = "not classified";
        return d;
    }
    if (isNeverActClass(subcategory)) {
        d.action = BetaAction::NeverAct;
        d.reason = "Percussion is an incoherent parent class (15.4% measured "
                   "precision); no threshold makes it safe to move";
        return d;
    }
    if (subcategory == "Other/none" || subcategory == "Misc/Review") {
        d.action = BetaAction::Review;
        d.displayedLabel.clear();
        d.reason = "model believes this is not a supported sound";
        return d;
    }
    if (confidence < gate) {
        d.action = BetaAction::Review;
        d.reason = "confidence below the gate for the current operating point";
        return d;
    }
    if (hasMisleadingToken(fileName)) {
        d.action = BetaAction::Suggest;
        d.reason = "filename contains a token measured unreliable; approval required";
        return d;
    }
    if (isAutoRenameClass(subcategory)) {
        d.action = BetaAction::AutoRenameEligible;
        d.reason = "class measured above 90% precision; eligible for rename preview";
        d.requiresApproval = true;   // BETA: eligible != automatic
        return d;
    }
    if (isSuggestClass(subcategory)) {
        d.action = BetaAction::Suggest;
        d.reason = "class is useful but below the bar for acting without approval";
        return d;
    }
    d.action = BetaAction::Review;
    d.reason = "class has no measured precision history";
    return d;
}

// True only for files SLO may include in a sort/rename operation.
// NOTE: AutoRenameEligible still requires the user to confirm the sort itself.
inline bool isEligibleForSort(const BetaDecision& d) {
    return d.action == BetaAction::AutoRenameEligible;
}

} // namespace slo
