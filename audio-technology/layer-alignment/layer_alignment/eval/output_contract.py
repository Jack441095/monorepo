"""Product output contract — maps FROZEN engine semantics to the
machine-readable recommendation schema (sprint §58).

Field names mirror actual engine outputs; nothing is invented.
"""
from __future__ import annotations

from typing import Optional


def _relationship_text(cls: dict) -> str:
    if cls.get("non_overlapping"):
        return "harmonically_related_non_overlapping"
    if cls.get("ambiguous_periodic"):
        return "periodically_ambiguous"
    return {"RELATED": "related", "UNRELATED": "unrelated",
            "AMBIGUOUS": "ambiguous"}[cls["label"]]


def _abstain_reason(rec: dict, feat: dict) -> str:
    cls = rec["classification"]
    if cls.get("non_overlapping"):
        return ("layers share little spectrum; a time shift cannot "
                "meaningfully align them")
    if cls.get("ambiguous_periodic"):
        return ("multiple equally plausible offsets (tonal/ringing "
                "material); refusing to guess")
    reason = rec.get("reason", "")
    return reason or cls["label"].lower()


def to_product_output(feat: dict, cls: dict, rec: dict,
                      fs: int) -> dict:
    """Frozen-engine result -> product JSON contract."""
    est = feat["estimates"]
    d_hat = float(est["gcc_soft"])
    pol = int(feat["polarity"]["polarity"])

    base = {
        "engine": "LAYER_ALIGNMENT_FROZEN_ENGINE_V1",
        "confidence": round(float(cls["confidence"]), 3),
        "relationship": _relationship_text(cls),
        "estimated_offset_samples": round(d_hat, 2),
        "polarity": "INVERTED" if pol == -1 else "NORMAL",
        "band_offsets_samples": {k: round(v, 1)
                                 for k, v in feat["band_offsets"].items()},
        "coherence_relationship": round(
            float(feat.get("coh_relationship", 0.0)), 3),
        "spectral_overlap": round(float(feat.get("spectral_overlap", 0.0)),
                                  3),
        "ambiguity_ratio": round(float(feat.get("ambiguity_ratio", 0.0)),
                                 3),
    }

    action = rec["action"]
    sugg = rec["suggestions"][0] if rec["suggestions"] else None

    if action == "NO_ACTION":
        out = {"action": "NO_ACTION",
               "reason": rec.get("reason", "no justified correction")}
        out.update(base)
        return out

    if action == "PARTIAL_SUGGESTION" or (sugg and
                                          sugg.get("type") == "BAND_OFFSETS"):
        out = {"action": "BANDWISE_WARNING",
               "reason": ("frequency-dependent phase relationship cannot "
                          "be safely corrected by one global delay; "
                          "per-band offsets reported"),
               "band_offsets_samples": base["band_offsets_samples"]}
        out.update({k: v for k, v in base.items()
                    if k != "band_offsets_samples"})
        return out

    # SUGGEST_ALIGNMENT
    delay = float(sugg.get("delay_samples", d_hat))
    out = {
        "action": "ALIGN",
        "offset_samples": round(delay, 2),
        "offset_ms": round(delay / fs * 1000.0, 3) if fs else None,
        "apply_polarity_flip": bool(int(sugg.get("polarity", 1)) == -1),
        "expected_benefit_db": sugg.get("improvement_db"),
        "benefit_band_gains_db": sugg.get("band_gains_db"),
        "peak_ratio_predicted": sugg.get("peak_ratio"),
        "tradeoff": sugg.get("tradeoff", ""),
    }
    out.update(base)
    return out
