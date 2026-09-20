#!/usr/bin/env python3
"""
SLO decision policy layer -- classifier output to a product ACTION.

The classifier is 69.6% accurate. Shipping that as renames would be actively
harmful. The product question is not "what is this sound" but "what may SLO do
about it", and those are different questions with different evidence bars.

Four action states:

  auto_rename   act without asking. Only classes with MEASURED high precision.
  suggest       show a label, require approval.
  review        uncertain -- send to the review queue.
  never_act     the class is unsafe or incoherent; do not rename, do not assert.

The class tiers are set from measured per-class precision at a 0.5 gate on
collection-held-out folds, NOT from intuition:

  Kick 94.3%, Clap 93.5%, Drum Loop 90.8%   -> auto_rename
  Snare 82.9%, Hi-Hat 80.0%, Crash 81.0%,
  Percussion Loop 61.5%, Foley 68.0%        -> suggest
  Percussion 15.4%                          -> never_act
  impulse responses                         -> never_act
  Other/none                                -> review (it IS the reject class)

Percussion is the important one. It acts on half its files at 15.4% precision --
five wrong renames for every right one. No confidence threshold rescues that,
because the class names several unrelated sounds; the fix is taxonomy work, not
tuning. Until then it must never act.

IMPORTANT -- what this layer is NOT. Per-class THRESHOLDS were measured and
rejected: they undershoot their precision promise by 12pp on unseen collections
because each is fitted on a few dozen files. This layer uses ONE global
threshold and varies only WHICH CLASSES MAY ACT. Choosing eligibility is safe;
tuning a separate threshold per class is not.
"""
import os, json, csv
from dataclasses import dataclass, asdict, field

SD = os.path.dirname(os.path.abspath(__file__))
POLICY_VERSION = "1.0.0"

AUTO_RENAME = {"Kick", "Clap", "Drum Loop"}
SUGGEST = {"Snare", "Hi-Hat", "Crash", "Percussion Loop", "Foley"}
NEVER_ACT = {"Percussion"}
REVIEW_CLASS = {"Other/none", "Misc/Review"}

# measured precision at a 0.5 gate, collection-held-out (results_rejection_boundary)
MEASURED_PRECISION = {
    "Kick": 94.3, "Clap": 93.5, "Drum Loop": 90.8, "Snare": 82.9,
    "Crash": 81.0, "Hi-Hat": 80.0, "Other/none": 72.4, "Foley": 68.0,
    "Percussion Loop": 61.5, "Percussion": 15.4,
}

# Filename tokens measured to be actively misleading. "snap" reliably means a
# recorded Foley sound, not a clap; generic tokens claim classes they cannot
# support. Where these fire, audio wins.
MISLEADING_TOKENS = {"snap", "hit", "tops", "chord", "loop"}


@dataclass
class Decision:
    action: str                 # auto_rename | suggest | review | never_act
    displayed_label: str
    confidence: float
    reason: str
    evidence: dict = field(default_factory=dict)
    requires_approval: bool = True
    subtype: str = ""
    policy_version: str = POLICY_VERSION
    taxonomy_version: str = ""

    def as_dict(self):
        return asdict(self)


def is_impulse_response(path):
    low = (path or "").lower()
    return "impluse" in low or "impulse" in low or "/ir/" in low


def filename_is_misleading(filename, fn_class):
    if not fn_class:
        return False, ""
    low = (filename or "").lower()
    for t in MISLEADING_TOKENS:
        if t in low:
            return True, t
    return False, ""


def decide(*, predicted_class, confidence, path="", filename_class=None,
           filename_confidence=0.0, audio_confidence=None, subtype="",
           threshold=0.5, arm="multi-window audio", taxonomy_version="1.1.0",
           class_precision=None, class_thresholds=None):
    """Map one classifier output to a product action. Pure function, no I/O."""
    prec = (class_precision or MEASURED_PRECISION).get(predicted_class)
    # Class-specific thresholds are opt-in research/approval configuration.
    # The shipped default remains the historical global threshold.  Ignore
    # malformed or absent entries rather than silently changing the operating
    # point; callers that load policy files must validate them before calling.
    effective_threshold = threshold
    if isinstance(class_thresholds, dict) and predicted_class in class_thresholds:
        candidate_threshold = class_thresholds[predicted_class]
        if isinstance(candidate_threshold, (int, float)) and 0.0 <= float(candidate_threshold) <= 1.0:
            effective_threshold = float(candidate_threshold)
    ev = {"arm": arm, "threshold": effective_threshold,
          "audio_confidence": audio_confidence if audio_confidence is not None
          else confidence,
          "filename_class": filename_class,
          "filename_confidence": filename_confidence,
          "measured_class_precision": prec}

    # 1. impulse responses -- a measurement of a space, never a musical sample
    if is_impulse_response(path):
        return Decision("never_act", "", confidence,
                        "impulse response: a measurement of a space, not a "
                        "sample; renaming it is never useful",
                        ev, True, subtype, taxonomy_version=taxonomy_version)

    # 2. classes that must never act, whatever the confidence
    if predicted_class in NEVER_ACT:
        return Decision("never_act", predicted_class, confidence,
                        f"{predicted_class} is an incoherent parent class "
                        f"(measured {prec}% precision); it names several "
                        f"unrelated sounds, so no threshold makes it safe",
                        ev, True, subtype, taxonomy_version=taxonomy_version)

    # 3. the rejection class routes to review, never to a rename
    if predicted_class in REVIEW_CLASS:
        return Decision("review", "", confidence,
                        "model believes this is not a supported sound; sent to "
                        "review rather than labelled",
                        ev, True, subtype, taxonomy_version=taxonomy_version)

    # 4. below the global gate -> review
    if confidence < effective_threshold:
        return Decision("review", predicted_class, confidence,
                        f"confidence {confidence:.2f} below the {effective_threshold:.2f} "
                        f"gate for the current operating point",
                        ev, True, subtype, taxonomy_version=taxonomy_version)

    # 5. A measured-unreliable filename token caps the action at 'suggest',
    #    EVEN IF the audio agrees with it. Agreement is not evidence when both
    #    sources read the same misleading token: "antique_shop_snap.wav" is a
    #    recorded Foley snap, and both the detector and a Clap-trained prototype
    #    call it a Clap. Requiring agreement would have auto-renamed it.
    misleading, tok = filename_is_misleading(os.path.basename(path),
                                             filename_class)
    if misleading:
        ev["misleading_token"] = tok
        agree = filename_class == predicted_class
        return Decision("suggest", predicted_class, confidence,
                        f"filename contains '{tok}', a token measured unreliable"
                        + (" -- and the audio agrees with it, which is not "
                           "independent evidence" if agree else
                           " and disagreeing with the audio")
                        + "; approval required",
                        ev, True, subtype, taxonomy_version=taxonomy_version)

    # 6. tiers
    if predicted_class in AUTO_RENAME:
        return Decision("auto_rename", predicted_class, confidence,
                        f"{predicted_class} measured {prec}% precision above "
                        f"the gate; cleared for automatic action",
                        ev, False, subtype, taxonomy_version=taxonomy_version)
    if predicted_class in SUGGEST:
        return Decision("suggest", predicted_class, confidence,
                        f"{predicted_class} measured {prec}% precision -- useful "
                        f"but below the bar for acting without approval",
                        ev, True, subtype, taxonomy_version=taxonomy_version)
    return Decision("review", predicted_class, confidence,
                    "class has no measured precision history; not eligible to "
                    "act until it does",
                    ev, True, subtype, taxonomy_version=taxonomy_version)


def policy_table():
    rows = []
    for c, p in sorted(MEASURED_PRECISION.items(), key=lambda kv: -kv[1]):
        a = ("never_act" if c in NEVER_ACT else
             "review" if c in REVIEW_CLASS else
             "auto_rename" if c in AUTO_RENAME else
             "suggest" if c in SUGGEST else "review")
        rows.append((c, p, a))
    return rows


if __name__ == "__main__":
    print(f"SLO decision policy v{POLICY_VERSION}\n")
    print(f"  {'class':>18} {'measured precision':>19}  action")
    for c, p, a in policy_table():
        print(f"  {c:>18} {p:18.1f}%  {a}")
    print("\nexamples:")
    for kw in (dict(predicted_class="Kick", confidence=0.9, path="/x/Kick 01.wav"),
               dict(predicted_class="Percussion", confidence=0.99, path="/x/perc.wav"),
               dict(predicted_class="Clap", confidence=0.8,
                    path="/x/antique_shop_snap.wav", filename_class="Clap"),
               dict(predicted_class="Foley", confidence=0.8,
                    path="/x/Leek Snap.wav", filename_class="Clap"),
               dict(predicted_class="Kick", confidence=0.3, path="/x/k.wav"),
               dict(predicted_class="Kick", confidence=0.99,
                    path="/x/Impluse Responce/chamber.wav")):
        d = decide(**kw)
        print(f"  {os.path.basename(kw['path'])[:30]:32} -> {d.action:12} "
              f"approval={d.requires_approval}  {d.reason[:54]}")
