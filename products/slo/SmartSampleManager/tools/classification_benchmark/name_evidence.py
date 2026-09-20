#!/usr/bin/env python3
"""
Name evidence -- producer shorthand, with measured risk, never trusted alone.

A filename is a claim made by whoever named the file. Treating it as evidence is
right; treating it as truth is how SLO moves a Foley snap into a Clap folder.

RISK LEVELS ARE MEASURED, NOT ASSUMED. Every token below was scored against the
by-ear corpus: how often does a file containing this token actually carry the
class the token implies?

  token   fires  intended      hit%   what it actually is
  bd          4  Kick          100%
  clp         6  Clap          100%
  clap       91  Clap           97%
  kick       80  Kick           89%
  snare     102  Snare          87%
  crash       7  Crash          86%
  cymbal     12  Crash          83%
  tom        11  Percussion     82%
  hat        40  Hi-Hat         78%
  fx         26  SFX            77%
  impact      7  Impact         71%
  foley      26  Foley          69%
  rim        12  Rimshot        67%
  808        29  808            55%
  reese      10  Reese Bass     50%
  shaker     14  Percussion     43%   -> usually Percussion LOOP
  top        10  Top Loop       40%   -> half are Hi-Hat Loop
  perc       58  Percussion     29%   -> usually Percussion LOOP
  snap        7  Clap           14%   -> Foley
  sub        18  Sub Bass       11%   -> Reese / Synth Bass
  loop      112  Loop            2%   -> a specific loop type
  bass       30  Bass            0%   -> a specific bass type
  sd          8  Snare           0%   -> KICK  (6 of 8)
  hit         6  Impact          0%   -> Foley
  chord      12  Chord Loop      0%   -> Synth
  texture     6  Atmosphere      0%

Two kinds of failure, and they are not the same:

  IDENTITY error  the token names the wrong thing entirely. `sd` -> Snare is
                  wrong 100% of the time and six of its eight files are KICKS.
                  `snap` -> Clap is wrong 86% of the time. These are dangerous.
  GRANULARITY err the token names the right FAMILY at the wrong resolution.
                  `perc` is usually a Percussion LOOP; `loop` is a specific kind
                  of loop. The family is right, the form is wrong -- useful
                  evidence, wrong answer.

The extractor reports both, so the decision policy can use the family claim
while refusing the exact claim.
"""
import os, re, json
from dataclasses import dataclass, field, asdict

EVIDENCE_VERSION = "name_v1"

# token -> (exact class, family, measured precision %, n observed)
# precision None = not enough observations to measure; treated as medium risk.
TOKENS = {
    # --- Snare -------------------------------------------------------------
    r"\bsnare\b":        ("Snare", "Snare", 87, 102),
    r"\bsnr\b":          ("Snare", "Snare", None, 0),
    r"\bsn\b":           ("Snare", "Snare", None, 0),
    # --- Kick --------------------------------------------------------------
    r"\bkick\b":         ("Kick", "Kick", 89, 80),
    r"\bkik\b":          ("Kick", "Kick", None, 0),
    r"\bbd\b":           ("Kick", "Kick", 100, 4),
    r"\bbass\s*drum\b":  ("Kick", "Kick", None, 0),
    # --- Hi-Hat ------------------------------------------------------------
    r"\bhi[\s-]*hat\b":  ("Hi-Hat", "Hi-Hat", None, 0),
    r"\bhat\b":          ("Hi-Hat", "Hi-Hat", 78, 40),
    r"\bhats\b":         ("Hi-Hat", "Hi-Hat", None, 0),
    r"\bhh\b":           ("Hi-Hat", "Hi-Hat", None, 0),
    r"\bchh\b":          ("Hi-Hat", "Hi-Hat", None, 0),
    r"\bohh\b":          ("Hi-Hat", "Hi-Hat", None, 0),
    r"\bclosed\s*hat\b": ("Hi-Hat", "Hi-Hat", None, 0),
    r"\bopen\s*hat\b":   ("Hi-Hat", "Hi-Hat", None, 0),
    # --- Clap --------------------------------------------------------------
    r"\bclap\b":         ("Clap", "Clap", 97, 91),
    r"\bclp\b":          ("Clap", "Clap", 100, 6),
    # --- Rimshot -----------------------------------------------------------
    r"\brimshot\b":      ("Rimshot", "Rimshot", None, 0),
    r"\brim\b":          ("Rimshot", "Rimshot", 67, 12),
    # --- Cymbals -----------------------------------------------------------
    r"\bcrash\b":        ("Crash", "Crash", 86, 7),
    r"\bcymbal\b":       ("Crash", "Crash", 83, 12),
    # --- Bass family -------------------------------------------------------
    r"\b808\b":          ("808", "Bass", 55, 29),
    r"\breese\b":        ("Reese Bass", "Bass", 50, 10),
    r"\bsub\b":          (None, "Bass", 11, 18),
    r"\bbass\b":         (None, "Bass", 0, 30),
    r"\bbs\b":           (None, "Bass", None, 0),
    # --- Percussion --------------------------------------------------------
    r"\btom\b":          ("Percussion", "Percussion", 82, 11),
    r"\bshaker\b":       (None, "Percussion", 43, 14),
    r"\bperc(ussion)?\b": (None, "Percussion", 29, 58),
    r"\b(conga|bongo|djembe|cajon|timbale)\b": (None, "Percussion", None, 0),
    r"\b(tamb(ourine)?|cowbell|clave|guiro|cabasa)\b": (None, "Percussion", None, 0),
    # --- Loops -------------------------------------------------------------
    r"\bdrum\s*loop\b":  ("Drum Loop", "Loop", None, 0),
    r"\bbreak\b":        ("Drum Loop", "Loop", None, 0),
    r"\btops?\b":        (None, "Loop", 40, 10),
    r"\bgroove\b":       (None, "Loop", None, 0),
    r"\bloop\b":         (None, "Loop", 2, 112),
    r"\blp\b":           (None, "Loop", None, 0),
    # --- FX / Foley --------------------------------------------------------
    r"\bfoley\b":        ("Foley", "Foley", 69, 26),
    r"\b(sfx|fx)\b":     ("SFX", "FX", 77, 26),
    r"\bimpact\b":       ("Impact", "FX", 71, 7),
    r"\briser\b":        ("Riser", "FX", None, 0),
    r"\btexture\b":      (None, "FX", 0, 6),
    r"\bhit\b":          (None, None, 0, 6),
    r"\bsnap\b":         (None, None, 14, 7),
    r"\bchord\b":        (None, None, 0, 12),
    # --- Vocal -------------------------------------------------------------
    r"\b(vox|vocal)\b":  (None, "Vocal", None, 0),
}

# Tokens whose measured failure is an IDENTITY error -- they name the wrong
# thing, not merely the wrong resolution. These can never contribute an exact
# class, whatever the audio says.
IDENTITY_HAZARDS = {r"\bsd\b", r"\bsnap\b", r"\bhit\b", r"\bchord\b",
                    r"\btexture\b", r"\bsub\b"}

COMPILED = [(re.compile(p, re.I), p, v) for p, v in TOKENS.items()]


def _norm(name):
    # separators BEFORE token matching: "_" is a word character, so \bsnr\b
    # never matches "kick_snr_01". This bug halved detector coverage once.
    return re.sub(r"[_\-.]+", " ", os.path.splitext(name)[0])


@dataclass
class NameEvidence:
    tokens: list = field(default_factory=list)
    candidate_classes: list = field(default_factory=list)
    candidate_subtypes: list = field(default_factory=list)
    candidate_families: list = field(default_factory=list)
    token_confidence: float = 0.0
    risk_level: str = "high"
    requires_audio_confirmation: bool = True
    reason: str = ""
    evidence_version: str = EVIDENCE_VERSION

    def as_dict(self):
        return asdict(self)


def extract(filename):
    text = _norm(os.path.basename(filename))
    hits = []
    for rx, pat, (exact, family, prec, n) in COMPILED:
        if rx.search(text):
            hits.append({"pattern": pat, "match": rx.search(text).group(0),
                         "exact": exact, "family": family,
                         "precision": prec, "n": n,
                         "identity_hazard": pat in IDENTITY_HAZARDS})
    ev = NameEvidence()
    if not hits:
        ev.risk_level = "none"
        ev.reason = "no recognised token in the filename"
        ev.requires_audio_confirmation = True
        return ev

    ev.tokens = [h["match"] for h in hits]
    hazard = any(h["identity_hazard"] for h in hits)
    # exact-class claims, only from tokens that are not identity hazards
    exacts = [h for h in hits if h["exact"] and not h["identity_hazard"]]
    fams = [h["family"] for h in hits if h["family"]]
    ev.candidate_classes = sorted({h["exact"] for h in exacts})
    ev.candidate_families = sorted(set(fams))

    measured = [h["precision"] for h in hits if h["precision"] is not None]
    best = max(measured) if measured else None
    # An unmeasured abbreviation (snr, kik, hh, clp...) is treated as MEDIUM:
    # plausible shorthand, but no evidence that it holds on real libraries.
    ev.token_confidence = round((best or 60) / 100.0, 3)

    if hazard:
        ev.risk_level = "high"
        bad = [h["match"] for h in hits if h["identity_hazard"]]
        ev.reason = (f"token(s) {bad} name the wrong class more often than the "
                     f"right one in the measured corpus; family kept, exact "
                     f"class discarded")
    elif best is not None and best >= 80:
        ev.risk_level = "low"
        ev.reason = f"token measured {best}% accurate on the by-ear corpus"
    elif best is not None and best >= 50:
        ev.risk_level = "medium"
        ev.reason = f"token measured {best}% accurate -- needs audio agreement"
    elif best is not None:
        ev.risk_level = "high"
        ev.reason = (f"token measured only {best}% accurate; usually indicates "
                     f"the right family at the wrong resolution")
        ev.candidate_classes = []          # family survives, exact does not
    else:
        ev.risk_level = "medium"
        ev.reason = "recognised producer shorthand, but unmeasured on this corpus"

    # Nothing here is ever sufficient alone. Audio always has to agree.
    ev.requires_audio_confirmation = True
    return ev


if __name__ == "__main__":
    tests = ["SNR_01.wav", "kick_BD_02.wav", "CHH_closed.wav", "CLP_808.wav",
             "Leek Snap.wav", "perc_loop_120.wav", "SD_Kick_heavy.wav",
             "reese_bass_growl.wav", "sub_drop.wav", "tops_128.wav",
             "mystery_thing.wav"]
    for t in tests:
        e = extract(t)
        print(f"{t:26} {e.risk_level:7} conf={e.token_confidence:.2f} "
              f"classes={e.candidate_classes} families={e.candidate_families}")
        print(f"{'':26} {e.reason[:76]}")
