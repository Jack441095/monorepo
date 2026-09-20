"""Run the FROZEN engine over pair cases; produce analysis records.

The engine is a black box here: analyze_pair -> classify -> recommend
-> to_product_output. Nothing is tuned; every record keeps full feature
evidence for forensics and calibration.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.nla import decision as D          # noqa: E402
from eval.output_contract import to_product_output   # noqa: E402


def analyse_case(case, max_analysis_seconds: float = 10.0) -> dict:
    """Analyse one pair with the FROZEN engine.

    Analysis window cap implements the capture/analyse product strategy:
    sessions submit bounded captures, not whole songs. The cap is harness
    policy and recorded in every record's meta."""
    fs = case.fs
    a = np.asarray(case.a, dtype=np.float64)
    b = np.asarray(case.b, dtype=np.float64)
    n = min(len(a), len(b), int(max_analysis_seconds * fs))
    a, b = a[:n], b[:n]

    feat = D.analyze_pair(a, b, fs, max_lag=256)
    cls = D.classify(feat)
    rec = D.recommend(feat, a, b, fs, cls, do_search=True, max_lag=96)
    po = to_product_output(feat, cls, rec, fs)

    return {
        "meta": {**case.meta(), "analysis_samples": int(n),
                 "analysis_seconds": round(n / fs, 3)},
        "fs": fs,
        "feat": {
            "estimates": {k: round(float(v), 3)
                          for k, v in feat["estimates"].items()},
            "primary_offset": round(float(feat["primary_offset"]), 3),
            "coh_relationship": round(
                float(feat.get("coh_relationship", 0.0)), 4),
            "spectral_overlap": round(float(feat["spectral_overlap"]), 4),
            "ambiguity_ratio": round(float(feat["ambiguity_ratio"]), 4),
            "prominence_classic": round(float(feat["prominence_classic"]),
                                        2),
            "polarity": int(feat["polarity"]["polarity"]),
            "onset_diff": feat.get("onset_diff"),
        },
        "classification": cls,
        "recommendation": {
            "action": rec["action"],
            "reason": rec.get("reason"),
            "suggestion": rec["suggestions"][0] if rec["suggestions"] else None,
        },
        "product_output": po,
        # kept in memory for blind-pack rendering; stripped before JSON dump
        "_a": a, "_b": b,
    }


def records_to_json(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        rr = {k: v for k, v in r.items() if not k.startswith("_")}
        out.append(rr)
    return out


def strip_audio(record: dict) -> dict:
    return {k: v for k, v in record.items() if not k.startswith("_")}


def keep_audio(record: dict) -> dict:
    return record
