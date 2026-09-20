"""Blind review pack builder (sprint §17-§23, §67-§69).

For every ACTIONABLE engine result we render:
  ORIGINAL mix  = a + b
  SUGGESTED mix = a + align(b, suggestion)
Level bias control (§18): the SUGGESTED mix is scalar-scaled so its
broadband RMS equals the ORIGINAL's RMS. One gain, applied to the whole
suggested mix — timing/spectral interaction is preserved, pure level
advantage removed. The unmatched RMS delta is recorded in the manifest so
the energy change remains visible evidence.

A/B assignment is deterministic from sha256(case_id | BLIND_SEED).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.audio_io import write_wav            # noqa: E402
from src.nla import interaction as I           # noqa: E402

BLIND_SEED = "NLA-REAL-V1-BLIND-SEED-7f3a"


def _assign(case_id: str) -> tuple[str, str]:
    h = int(hashlib.sha256((BLIND_SEED + case_id).encode()).hexdigest()[:8], 16)
    return ("SUGGESTED", "ORIGINAL") if h % 2 else ("ORIGINAL", "SUGGESTED")


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2)) + 1e-12)


def build_pack(cases_results: list[dict], out_dir: Path,
               sr_default: int = 48000, max_seconds: float = 6.0) -> dict:
    """cases_results: entries from the natural/controlled pipeline carrying
    keys: meta, product_output, feat, rec, a, b, fs."""
    out_dir = Path(out_dir)
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for res in cases_results:
        po = res["product_output"]
        trap = bool(res.get("_trap_original_only"))
        if po.get("action") != "ALIGN" and not trap:
            continue
        cid = res["meta"]["case_id"] + ("|TRAP" if trap else "")
        fs = res["fs"]
        n = min(len(res["_a"]), len(res["_b"]), int(max_seconds * fs))
        a = res["_a"][:n].astype(np.float64)
        b = res["_b"][:n].astype(np.float64)

        if trap:
            original = a + b
            suggested_matched = original.copy()
            rms_o = rms(original)
            gain = 1.0
        else:
            delay = float(po.get("offset_samples", 0.0))
            flip = -1 if po.get("apply_polarity_flip") else 1
            b_fixed = I.apply_alignment(b, delay, fs, flip)
            original = a + b
            suggested = a + b_fixed
            rms_o, rms_s = rms(original), rms(suggested)
            gain = rms_o / rms_s                   # level-match suggested
            suggested_matched = suggested * gain

        slot_a, slot_b = _assign(cid)
        fa = f"{hashlib.sha1(cid.encode()).hexdigest()[:12]}_A.wav"
        fb = f"{hashlib.sha1(cid.encode()).hexdigest()[:12]}_B.wav"
        write_wav(audio_dir / fa,
                  suggested_matched if slot_a == "SUGGESTED" else original, fs)
        write_wav(audio_dir / fb,
                  suggested_matched if slot_b == "SUGGESTED" else original, fs)
        entries.append({
            "case_id": cid,
            "class": res["meta"]["class"],
            "category": res["meta"]["category"],
            "relationship": res["meta"].get("relationship", ""),
            "slot_a": slot_a, "slot_b": slot_b,
            "file_a": fa, "file_b": fb,
            "rms_original": round(rms_o, 5),
            "rms_suggested_unmatched": round(rms_s, 5),
            "level_match_gain_db": round(20 * np.log10(gain + 1e-12), 2),
            "expected_benefit_db": po.get("expected_benefit_db"),
        })

    # deterministic repeat set for self-consistency (~20%)
    base_ids = [e["case_id"] for e in entries]
    rng = np.random.default_rng(int(hashlib.sha256(
        (BLIND_SEED + "|repeats").encode()).hexdigest()[:8], 16) % (1 << 31))
    n_rep = max(1, len(base_ids) // 5)
    repeats = []
    for cid in rng.choice(base_ids, size=min(n_rep, len(base_ids)),
                          replace=False):
        src = next(e for e in entries if e["case_id"] == cid)
        rep = dict(src)
        rep["case_id"] = cid + "|REPEAT"
        rep["repeat_of"] = cid
        # same files, same slots — consistency check
        repeats.append(rep)
    all_entries = entries + repeats

    pack = {
        "blind_seed": BLIND_SEED,
        "level_match_policy":
            "scalar broadband-RMS match of SUGGESTED to ORIGINAL; "
            "unmatched delta recorded",
        "order_seed_sha256": hashlib.sha256(
            (BLIND_SEED + "|order").encode()).hexdigest(),
        "entries": all_entries,
    }
    (out_dir / "pack_manifest.json").write_text(json.dumps(pack, indent=1))

    # deterministic presentation order
    order = sorted(all_entries, key=lambda e: hashlib.sha256(
        (BLIND_SEED + e["case_id"]).encode()).hexdigest())
    (out_dir / "presentation_order.json").write_text(json.dumps(order, indent=1))
    return pack
