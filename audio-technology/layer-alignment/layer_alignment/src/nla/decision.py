"""Relationship classification, confidence, abstention and recommendation.

Design goals (from research questions 6/7/8/22):
  - never reduce the pair to one number: use coherence + prominence +
    cross-method agreement + band structure
  - explicit NO ACTION outcome with calibrated thresholds
  - explicit abstention when relationship is weak
"""
from __future__ import annotations

import numpy as np

from . import methods as M

EPS = 1e-12

# thresholds calibrated on the deterministic corpus (see bake-off report)
TH = {
    "coh_related": 0.45,
    "coh_unrelated": 0.22,
    "prom_related": 12.0,
    "prom_unrelated": 5.0,
    "agree_tol_samples": 3.0,
}


def analyze_pair(a, b, fs, max_lag=256) -> dict:
    """Full analysis suite for one layer pair."""
    coh = M.coherence_summary(a, b, fs, bands=((60, 250), (250, 2000),
                                               (2000, 8000)))
    g_classic = M.gcc_phat(a, b, max_lag, fs)
    g_soft = M.gcc_soft(a, b, max_lag, fs)
    xc = M.xcorr_plain(a, b, min(max_lag, 256))
    ps = M.phase_slope_offset(a, b, fs)
    gd = M.group_delay_offset(a, b, fs)
    pol = M.polarity_decision(a, b, min(max_lag, 128))
    onset = M.onset_alignment(a, b, fs)
    bands = M.bandwise_analysis(a, b, fs, max_lag)

    est = {
        "xcorr_plain": xc["offset_samples"],
        "gcc_phat": g_classic["offset_samples"],
        "gcc_soft": g_soft["offset_samples"],
        "phase_slope": ps["offset_samples"],
        "group_delay": gd["offset_samples"],
        "onset": onset["offset_samples"],
    }
    # cross-method agreement among time/frequency estimators (excl onset)
    core = np.array([est[k] for k in ("xcorr_plain", "gcc_soft",
                                      "phase_slope")])
    spread = float(np.max(core) - np.min(core)) if len(core) else 999.0

    active_bands = {k: v for k, v in bands.items() if v.get("active")}
    band_offsets = {k: v["offset_samples"] for k, v in active_bands.items()}

    return {
        "estimates": est,
        "primary_offset": xc["offset_samples"],
        "ambiguity_ratio": xc["ambiguity_ratio"],
        "spectral_overlap": M.spectral_overlap(a, b, fs),
        "coh_relationship": M.relationship_coherence(a, b, fs),
        "spread_core_samples": spread,
        "coherence": coh,
        "coh_60_8k": float(np.mean([coh.get("250-2000", 0),
                                    coh.get("2000-8000", 0)])),
        "prominence_classic": g_classic["prominence"],
        "prominence_soft": g_soft["prominence"],
        "polarity": pol,
        "onset_diff": onset["onset_diff"],
        "onset_offset": onset["offset_samples"],
        "bands": bands,
        "band_offsets": band_offsets,
    }


def classify(feat: dict) -> dict:
    """RELATED / UNRELATED / AMBIGUOUS + confidence + abstention flag.

    Ambiguity override: when the correlation surface has a near-equal
    secondary peak (periodic ambiguity from tonal/ringing material), the
    offset estimate is untrustworthy regardless of coherence. Onset
    agreement can rescue it (two transients at the reported lag).
    """
    c = feat.get("coh_relationship",
                 feat.get("coh_60_8k", 0.0))
    # classic PHAT prominence is the validated related/unrelated
    # discriminator (measured ~120-150 related vs ~5-8 unrelated);
    # the soft variant's profile has a high sidelobe floor.
    p = feat["prominence_classic"]
    amb = feat.get("ambiguity_ratio", 0.0)
    overlap = feat.get("spectral_overlap", 1.0)
    onset = feat.get("onset_offset")
    primary = feat.get("primary_offset")
    onset_rescue = (onset is not None and primary is not None and
                    abs(onset - primary) <= 3.0)
    ambiguous_periodic = amb > 0.85 and not onset_rescue
    # harmonically related but spectrally non-overlapping pairs (octave
    # tones) produce sharp whitened structure yet cannot be aligned by
    # any delay — abstain regardless of prominence.
    non_overlapping = overlap < 0.15

    related_score = 0.0
    if c >= TH["coh_related"]:
        related_score += 1
    elif c <= TH["coh_unrelated"]:
        related_score -= 1
    if p >= TH["prom_related"]:
        related_score += 1
    elif p <= TH["prom_unrelated"]:
        related_score -= 1
    if feat["spread_core_samples"] <= TH["agree_tol_samples"]:
        related_score += 0.5
    elif feat["spread_core_samples"] > 10 * TH["agree_tol_samples"]:
        related_score -= 0.5

    if ambiguous_periodic or non_overlapping:
        label = "AMBIGUOUS"
    elif related_score >= 1.0:
        label = "RELATED"
    elif related_score <= -1.0:
        label = "UNRELATED"
    else:
        label = "AMBIGUOUS"

    conf = float(np.clip(0.5 * abs(related_score) +
                         0.25 * min(c, 1.0) +
                         0.25 * min(p / TH["prom_related"], 1.0), 0, 1))
    if ambiguous_periodic or non_overlapping:
        conf = min(conf, 0.35)
    return {"label": label, "score": float(related_score),
            "confidence": conf, "abstain": label != "RELATED",
            "ambiguous_periodic": bool(ambiguous_periodic),
            "non_overlapping": bool(non_overlapping),
            "onset_rescued_ambiguity": bool(onset_rescue and
                                            ambiguous_periodic)}


def recommend(feat: dict, a=None, b=None, fs=None, cls=None,
              min_improvement_db=0.25, do_search=False, max_lag=128):
    """Produce ranked suggestions or an explicit NO ACTION.

    Policy:
      UNRELATED/AMBIGUOUS -> NO ACTION (abstention)
      RELATED but estimated offset < 0.5 samples and polarity normal
          and no band divergence -> NO ACTION (already aligned)
      else evaluate candidate(s); require weighted improvement above
          threshold to recommend.
    """
    cls = cls or classify(feat)
    out = {"classification": cls, "suggestions": [], "action": None}

    def set_no_action(reason):
        out["action"] = "NO_ACTION"
        out["reason"] = reason
        return out

    if cls["abstain"]:
        return set_no_action(
            f"relationship={cls['label']} (abstention)")

    est = feat["estimates"]
    d_hat = float(est["gcc_soft"])
    pol = int(feat["polarity"]["polarity"])

    # already aligned?
    aligned = abs(d_hat) < 0.5 and pol == 1
    if aligned:
        return set_no_action("layers already aligned (|d|<0.5, polarity normal)")

    # band divergence check: single global delay cannot describe dispersive
    # phase relationships
    bo = feat["band_offsets"]
    active = [v for v in bo.values()]
    divergent = False
    if len(active) >= 2:
        arr = np.array(active)
        divergent = bool(arr.size >= 2 and
                         (arr.min() < -4) != (arr.max() > 4) or
                         (arr.max() - arr.min()) > 24)

    if divergent and not do_search:
        out["action"] = "PARTIAL_SUGGESTION"
        out["reason"] = ("frequency-dependent phase detected; bandwise "
                         "offsets reported instead of a single delay")
        out["suggestions"] = [
            {"type": "BAND_OFFSETS", "offsets": bo}]
        return out

    if a is None or b is None or fs is None:
        # measurement-only mode: suggest measured offset/polarity directly
        out["action"] = "SUGGEST_ALIGNMENT" if abs(d_hat) >= 0.5 or pol == -1 \
            else "NO_ACTION"
        if out["action"] == "SUGGEST_ALIGNMENT":
            out["suggestions"] = [{
                "type": "DELAY_POLARITY",
                "delay_samples": round(d_hat, 2),
                "delay_ms": round(d_hat / fs, 3) if fs else None,
                "polarity": pol,
                "confidence": cls["confidence"],
            }]
        return out

    if do_search:
        from . import interaction as I
        d_prior = (feat.get("primary_offset") if cls.get("label") == "RELATED"
                   else None)
        best = I.fast_search(a, b, fs, max_lag,
                             d_prior=float(d_prior) if d_prior is not None
                             else 0.0)
        imp = best["improvement_over_identity"]
        bg = best["band_gains"]
        er = best.get("band_energy_ratio", {})

        # Gate 1: the candidate must produce genuinely constructive
        # summation in bands where the layers actually overlap.
        # Energy gains in near-silent bands are noise-floor artefacts.
        low_active = max(er.get("band0", 0), er.get("band1", 0)) > 0.02
        if low_active:
            gate_gain = bg.get("band0_gain_db", -99) + \
                bg.get("band1_gain_db", -99)
            gate_name = "sub+bass"
            gate_min = 2.5          # dB summed, vs 6 dB perfect ceiling
        else:
            gate_gain = bg.get("band2_gain_db", -99)
            gate_name = "active broadband"
            gate_min = 1.0
        if imp < min_improvement_db:
            return set_no_action(
                f"best bounded search improves objective by only "
                f"{imp:.2f} dB (< {min_improvement_db} dB)")
        if gate_gain < gate_min:
            return set_no_action(
                f"constructive {gate_name} gain only {gate_gain:.2f} dB "
                f"(>= {gate_min} dB required) — characteristic of "
                f"decorrelated layers or non-overlapping content")
        out["action"] = "SUGGEST_ALIGNMENT"
        out["suggestions"] = [{
            "type": "SEARCHED",
            "delay_samples": round(float(best["delay_samples"]), 2),
            "polarity": int(best["polarity"]),
            "improvement_db": round(imp, 2),
            "band_gains_db": {k: round(v, 2)
                              for k, v in best["band_gains"].items()},
            "peak_ratio": best["peak_ratio"],
            "confidence": cls["confidence"],
            "tradeoff": _tradeoff_text(best),
        }]
        return out

    # default: measured offset/polarity as suggestion, gated by improvement
    from . import interaction as I
    cand = I.candidate_score(a, b, fs, d_hat, pol)
    ident = cand["J_identity"]
    if cand["J"] - ident < min_improvement_db:
        return set_no_action(
            f"measured alignment improves objective by only "
            f"{cand['J'] - ident:.2f} dB")
    out["action"] = "SUGGEST_ALIGNMENT"
    out["suggestions"] = [{
        "type": "DELAY_POLARITY",
        "delay_samples": round(d_hat, 2),
        "delay_ms": None,
        "polarity": pol,
        "improvement_db": round(float(cand["J"] - ident), 2),
        "sub_gain_db": cand["sub_gain_db"],
        "peak_ratio": cand["peak_ratio"],
        "confidence": cls["confidence"],
        "tradeoff": _tradeoff_text(cand),
    }]
    if fs:
        out["suggestions"][0]["delay_ms"] = round(d_hat / fs, 3)
    return out


def _tradeoff_text(cand: dict) -> str:
    bits = []
    if "peak_ratio" in cand:
        if cand["peak_ratio"] < 0.95:
            bits.append("reduces summed peak level")
        elif cand["peak_ratio"] > 1.05:
            bits.append("increases summed peak level")
    if cand.get("crest_delta", 1.0) < 0.95:
        bits.append("lowers crest factor (denser sound)")
    sub = cand.get("sub_gain_db",
                   cand.get("band_gains", {}).get("band0_gain_db"))
    if sub is not None and sub < 0.3:
        bits.append("little low-band summation gain")
    return "; ".join(bits) if bits else "minor character change possible"


def explain(feat: dict, rec: dict, fs: int) -> dict:
    """Structured producer-facing explanation (report §23)."""
    cls = rec["classification"]
    rel = {"RELATED": "strongly related", "UNRELATED": "unrelated layers",
           "AMBIGUOUS": "weakly related"}[cls["label"]]
    bo = feat["band_offsets"]
    low_cancel = any(v is not None and v < -1.0
                     for k, v in _interactions(feat).items()
                     if k in ("sub", "bass"))
    primary = "no significant interaction"
    if low_cancel:
        primary = "low-frequency cancellation"
    elif _interactions(feat) and max(_interactions(feat).values(),
                                     default=0) > 1.0:
        primary = "constructive reinforcement in some bands"
    est = feat["estimates"]
    d_hat = est["gcc_soft"]
    sugg = rec["suggestions"][0] if rec["suggestions"] else None
    return {
        "RELATIONSHIP": rel,
        "PRIMARY_INTERACTION": primary,
        "ESTIMATED_OFFSET": f"{d_hat:+.1f} samples "
                            f"({d_hat / fs * 1000:+.2f} ms)",
        "POLARITY": "inverted" if feat["polarity"]["polarity"] == -1
                    else "normal",
        "BAND_OFFSETS": {k: round(v, 1) for k, v in bo.items()},
        "CONFIDENCE": ("high" if cls["confidence"] > 0.66 else
                       "medium" if cls["confidence"] > 0.4 else "low"),
        "SUGGESTION": (f"audition ~{-sugg['delay_samples']:.1f} samples on "
                       f"Layer B" if sugg and sugg.get("delay_samples")
                       else "none — no action recommended"),
        "TRADE_OFF": sugg.get("tradeoff", "") if sugg else "",
        "ACTION": rec["action"],
    }


def _interactions(feat: dict) -> dict:
    return {k: v.get("interaction_db") for k, v in feat["bands"].items()
            if isinstance(v, dict) and v.get("active")}
