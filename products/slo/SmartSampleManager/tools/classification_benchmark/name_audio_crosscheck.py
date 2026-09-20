#!/usr/bin/env python3
"""
Task 5/6 -- confirm or refute a filename claim with physics.

A filename says what someone called a file. Physics says what the file IS. Where
they agree the claim is strengthened; where they disagree the audio wins and the
file goes to review.

One rule matters more than the rest and is easy to get wrong:

  AGREEMENT IS NOT INDEPENDENT EVIDENCE WHEN BOTH SOURCES READ THE SAME TOKEN.

"antique_shop_snap.wav" is a recorded Foley snap. The detector reads "snap" and
says Clap. A Clap-trained prototype, hearing a short bright transient, also says
Clap. They agree, and they are both wrong for the same reason. So an identity-
hazard token caps the action regardless of agreement -- concordance between two
readers of the same bad token is not corroboration.

Confirmation profiles are physical, stated as testable conditions:

  Snare   sharp transient, broadband/noisy, short-to-medium decay, weak pitch
  Kick    strong transient, dominant low-frequency body, short-medium decay
  808     strong sub fundamental, long decay, often a downward pitch glide
  Reese   sustained, low/mid, harmonic beating, dense partials
  Sub     near-pure sine at a low fundamental, sustained, NO glide
  Hi-Hat  bright, noisy, very short decay, negligible sub
  Clap    multi-burst noise, mid-band, short decay, low harmonicity
"""
import os, json
from dataclasses import dataclass, field, asdict

CROSSCHECK_VERSION = "xcheck_v1"


def _c(ev, k, d=0.0):
    return float(ev.get(k, d)) if ev else d


PROFILES = {
    "Snare": lambda e: [
        ("sharp transient",      _c(e, "transient_strength") > 3.0),
        ("noisy, not tonal",     _c(e, "noise_tonal_ratio") > 0.02),
        ("short-medium decay",   0.02 < _c(e, "decay_seconds") < 1.5),
        ("weak stable pitch",    _c(e, "pitch_confidence") < 0.85),
        ("mid-band energy",      _c(e, "mid_energy_ratio") > 0.10),
    ],
    "Kick": lambda e: [
        ("strong transient",     _c(e, "transient_strength") > 2.5),
        ("low-frequency body",   _c(e, "sub_energy_ratio") + _c(e, "low_energy_ratio") > 0.35),
        ("short-medium decay",   _c(e, "decay_seconds") < 2.0),
        ("little high content",  _c(e, "high_energy_ratio") < 0.45),
    ],
    "808": lambda e: [
        ("strong sub",           _c(e, "sub_energy_ratio") > 0.25),
        ("long decay",           _c(e, "decay_seconds") > 0.5),
        ("low harmonic density", _c(e, "harmonic_density") < 12.0),
        ("downward glide",       _c(e, "pitch_drop_cents") > 60),
    ],
    "Reese Bass": lambda e: [
        ("sustained",            _c(e, "sustain_ratio") > 0.12),
        ("low/mid energy",       _c(e, "low_energy_ratio") + _c(e, "mid_energy_ratio") > 0.30),
        ("harmonic beating",     _c(e, "beating_depth") > 0.01),
        ("dense partials",       _c(e, "partial_count") >= 4),
    ],
    "Sub Bass": lambda e: [
        ("near-pure sine",       _c(e, "spectral_purity") > 0.55),
        ("few partials",         _c(e, "partial_count") <= 3),
        ("low fundamental",      0 < _c(e, "fundamental_hz") < 120),
        ("no strong glide",      abs(_c(e, "pitch_drop_cents")) < 200),
    ],
    "Hi-Hat": lambda e: [
        ("bright",               _c(e, "spectral_centroid") > 3000),
        ("very short decay",     _c(e, "decay_seconds") < 0.8),
        ("negligible sub",       _c(e, "sub_energy_ratio") < 0.15),
    ],
    "Clap": lambda e: [
        ("noisy",                _c(e, "noise_tonal_ratio") > 0.01),
        ("mid/high energy",      _c(e, "mid_energy_ratio") + _c(e, "high_energy_ratio") > 0.35),
        ("short decay",          _c(e, "decay_seconds") < 1.2),
        ("low harmonicity",      _c(e, "harmonicity") < 0.8),
    ],
}


@dataclass
class CrossCheck:
    claim: str = ""
    supported: bool = False
    support_ratio: float = 0.0
    conditions_met: list = field(default_factory=list)
    conditions_failed: list = field(default_factory=list)
    verdict: str = "unconfirmed"    # confirmed | contradicted | unconfirmed | untestable
    reason: str = ""
    version: str = CROSSCHECK_VERSION

    def as_dict(self):
        return asdict(self)


def crosscheck(claim, evidence, threshold=0.75):
    cc = CrossCheck(claim=claim)
    prof = PROFILES.get(claim)
    if prof is None:
        cc.verdict = "untestable"
        cc.reason = f"no physical profile defined for {claim}"
        return cc
    if not evidence:
        cc.verdict = "untestable"
        cc.reason = "no acoustic evidence available for this file"
        return cc
    conds = prof(evidence)
    cc.conditions_met = [n for n, ok in conds if ok]
    cc.conditions_failed = [n for n, ok in conds if not ok]
    cc.support_ratio = round(len(cc.conditions_met) / max(len(conds), 1), 3)
    cc.supported = cc.support_ratio >= threshold
    if cc.supported:
        cc.verdict = "confirmed"
        cc.reason = (f"audio supports {claim}: "
                     + ", ".join(cc.conditions_met))
    elif cc.support_ratio <= 0.34:
        cc.verdict = "contradicted"
        cc.reason = (f"audio contradicts {claim}: missing "
                     + ", ".join(cc.conditions_failed))
    else:
        cc.verdict = "unconfirmed"
        cc.reason = (f"audio partially supports {claim} "
                     f"({len(cc.conditions_met)}/{len(conds)}); missing "
                     + ", ".join(cc.conditions_failed))
    return cc


def combine(name_ev, audio_class, audio_conf, evidence):
    """Produce a final recommendation from name + audio + physics."""
    out = {"name_tokens": name_ev.tokens, "name_risk": name_ev.risk_level,
           "audio_class": audio_class, "audio_confidence": round(audio_conf, 3),
           "action_hint": "review", "confidence_delta": 0.0, "reason": ""}

    if name_ev.risk_level == "high":
        cc = crosscheck(audio_class, evidence)
        out["crosscheck"] = cc.as_dict()
        out["action_hint"] = "suggest" if cc.verdict == "confirmed" else "review"
        # A contradicted claim must LOWER confidence, not merely fail to raise
        # it. Leaving the delta at 0 here meant a risky token whose physics
        # actively disagreed scored the same as one with no physics at all,
        # which is the wrong ordering for a confidence-gated renamer.
        out["confidence_delta"] = {"confirmed": +0.05,
                                   "contradicted": -0.15}.get(cc.verdict, -0.05)
        out["reason"] = (f"filename token is measured unreliable, so it cannot "
                         f"contribute a class; decided on audio alone "
                         f"({cc.verdict})")
        return out

    claims = name_ev.candidate_classes
    if not claims:
        out["reason"] = "no usable filename claim; audio alone decides"
        out["action_hint"] = "suggest" if audio_conf >= 0.5 else "review"
        return out

    agrees = audio_class in claims
    cc = crosscheck(audio_class if agrees else claims[0], evidence)
    out["crosscheck"] = cc.as_dict()

    if agrees and cc.verdict == "confirmed":
        out["action_hint"] = "auto_rename_eligible"
        out["confidence_delta"] = +0.10
        out["reason"] = (f"filename and audio agree on {audio_class}, and the "
                         f"physics confirms it ({', '.join(cc.conditions_met)})")
    elif agrees and cc.verdict == "contradicted":
        out["action_hint"] = "review"
        out["confidence_delta"] = -0.15
        out["reason"] = (f"filename and audio both say {audio_class} but the "
                         f"physics contradicts it -- agreement between two "
                         f"readers of the same name is not corroboration")
    elif agrees:
        out["action_hint"] = "suggest"
        out["confidence_delta"] = +0.05
        out["reason"] = f"filename and audio agree on {audio_class}; physics neutral"
    else:
        out["action_hint"] = "review"
        out["confidence_delta"] = -0.10
        out["reason"] = (f"filename suggests {claims} but audio says "
                         f"{audio_class}; audio wins, file sent to review")
    return out


if __name__ == "__main__":
    import acoustic_evidence as ae, name_evidence as ne, sys
    if len(sys.argv) > 1:
        p = sys.argv[1]
        ev = ae.extract(p)
        nev = ne.extract(os.path.basename(p))
        print(json.dumps({"name": nev.as_dict(),
                          "acoustic": ev,
                          "explain": ae.describe(ev)}, indent=2, default=float))
    else:
        print(f"profiles: {sorted(PROFILES)}")
