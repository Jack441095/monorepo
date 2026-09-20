"""Case construction for Real-Audio Validation V1.

Two hard-separated classes (sprint §11):

A. CONTROLLED  — real source + known perturbation (delay/fractional/polarity/
                 filter/distortion). Measures recovery accuracy.
B. NATURAL     — real layer pairs as they occur in production. Measures
                 perceptual usefulness / harm / NO_ACTION quality.

The FROZEN engine is treated as a black box here: no thresholds, no
parameters are passed beyond the pair itself.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.nla import corpus as C            # noqa: E402 — transforms only
from eval.audio_io import LoadedAudio       # noqa: E402


# ------------------------------------------------------------------ cases

@dataclass
class PairCase:
    case_id: str
    klass: str                    # CONTROLLED | NATURAL | HEALTHY | SMOKE_*
    category: str                 # kick/snare/bass/percussion/synth/vocal/multimic/other
    relationship: str             # e.g. body+click, sub+mid, double, octave...
    fs: int
    a: np.ndarray
    b: np.ndarray
    source_group_a: str = ""
    source_group_b: str = ""
    provenance_category: str = "UNVERIFIED"
    truth_offset_samples: float | None = None
    truth_polarity: int = 1
    expected_action: str = "UNKNOWN"   # NO_ACTION / ACTION_KNOWN / UNKNOWN
    processing: dict = field(default_factory=dict)
    blind_eligible: bool = True
    notes: str = ""

    def meta(self) -> dict:
        return {
            "case_id": self.case_id,
            "class": self.klass,
            "category": self.category,
            "relationship": self.relationship,
            "fs": self.fs,
            "samples": int(len(self.a)),
            "duration_s": round(len(self.a) / self.fs, 3),
            "source_group_a": self.source_group_a,
            "source_group_b": self.source_group_b,
            "provenance_category": self.provenance_category,
            "truth_offset_samples": self.truth_offset_samples,
            "truth_polarity": self.truth_polarity,
            "expected_action": self.expected_action,
            "processing": self.processing,
            "blind_eligible": self.blind_eligible,
            "notes": self.notes,
        }


def case_seed(case_id: str) -> int:
    return hashlib.sha256(case_id.encode()).hexdigest()[:8] \
        and int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16) % (1 << 31)


# ------------------------------------------------------- controlled cases

CONTROL_GRID = [
    # (label, delay_samples, polarity, filter, distortion)
    ("int_delay", 37.0, 1, False, False),
    ("neg_delay", -23.0, 1, False, False),
    ("frac_delay", 12.5, 1, False, False),
    ("polarity", 14.0, -1, False, False),
    ("filtered", 21.0, 1, True, False),
    ("distorted", 9.0, 1, False, True),
]


def make_controlled(source: LoadedAudio, group: str, prov: str,
                    category: str, case_prefix: str,
                    grid=None, max_pairs_per_source: int = 6) -> list[PairCase]:
    """Derive controlled positive cases from ONE real recording.

    B = perturbed copy of A (exact freq-domain delay etc.). The pair is
    taken from the strongest-energy window of the source to avoid silence.
    """
    from scipy import signal as sps
    rng_global = np.random.default_rng(case_seed(case_prefix + "|grid"))
    x = source.samples
    n_needed = min(len(x), 1 << 15)
    # strongest window start
    win = 4096
    if len(x) > n_needed:
        steps = np.arange(0, len(x) - n_needed, win)
        energies = np.array([np.sum(x[s:s + n_needed] ** 2)
                             for s in steps])
        start = int(steps[np.argmax(energies)])
    else:
        start = 0
    seg = x[start:start + n_needed]

    out = []
    grid = grid or CONTROL_GRID
    for label, d, pol, do_filter, do_dist in grid[:max_pairs_per_source]:
        cid = f"{case_prefix}|{label}"
        rng = np.random.default_rng(case_seed(cid))
        log = C.TransformLog()
        a = seg.copy()
        b = seg.copy()
        if do_filter:
            r2 = np.random.default_rng(case_seed(cid + "|f"))
            b = C.apply_minphase_eq(b, source.sample_rate, r2, log)
        if do_dist:
            b = C.apply_distortion(b, 4.0, log)
        b = C.apply_polarity(b, pol == -1, log)
        b = C.apply_delay_exact(b, d, source.sample_rate, log)
        out.append(PairCase(
            case_id=cid, klass="CONTROLLED", category=category,
            relationship="self_perturbed",
            fs=source.sample_rate, a=a / (np.max(np.abs(a)) + 1e-12),
            b=b / (np.max(np.abs(b)) + 1e-12),
            source_group_a=group, source_group_b=group,
            provenance_category=prov,
            truth_offset_samples=float(d), truth_polarity=pol,
            expected_action="ACTION_KNOWN" if abs(d) >= 0.5 or pol == -1
                            else "NO_ACTION",
            processing={"filter": do_filter, "distortion": do_dist},
        ))
    return out


# ---------------------------------------------------------- pairing rules

def align_lengths(a: np.ndarray, b: np.ndarray,
                  target_s: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    n = min(len(a), len(b))
    if target_s:
        pass  # caller already sliced
    return a[:n], b[:n]
