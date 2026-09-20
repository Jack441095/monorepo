"""Source inventory, evidence-based classification and corpus construction
for Real-Audio Validation V1.

Sources (owner-authorised, READ-ONLY):
  Audio_Too/sample_pack_testing    -> controlled + healthy material
  Audio_Too/testing_track_stems    -> natural production pairs (+healthy)

Selection principle: filename keywords SHORTLIST candidates; audio
EVIDENCE (duration, spectral centroid, low-frequency energy fraction,
onset density) verifies domain before use. Evidence is recorded in the
manifest for every used file.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.audio_io import load_wav, AudioLoadError      # noqa: E402

PACK_ROOT = Path("/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/"
                 "Audio_Too/sample_pack_testing")
STEM_ROOT = Path("/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/"
                 "Audio_Too/testing_track_stems")

DOMAIN_PATTERNS = [
    ("kick", r"kick|bd[_\- ]|bass_?drum",),
    ("snare", r"snare|sd[_\- ]"),
    ("clap", r"clap"),
    ("hat", r"hat|hh[_\- ]|ride|cym|crash"),
    ("tom", r"tom"),
    ("perc", r"perc|shaker|tamb|conga|bongo|rim"),
    ("bass", r"bass|808|sub(?!_)"),
    ("vocal", r"vox|vocal|acap|choir|voice"),
    ("synth", r"synth|pad|lead|pluck|arp|keys|organ|piano|guitar|brass|melody"),
    ("fx", r"fx|riser|sweep|impact|downlift|atmos|noise|texture"),
]

EXCLUDE_RE = re.compile(r"loop|beat|groove|break|fill_|phrase", re.I)


def shortlist_domain(files: list[Path], domain: str,
                     exclude_loops: bool = True) -> list[Path]:
    pat = next(p for d, p in DOMAIN_PATTERNS if d == domain)
    rx = re.compile(pat, re.I)
    out = []
    for f in files:
        name = f.name
        if not rx.search(name):
            continue
        if exclude_loops and EXCLUDE_RE.search(name):
            continue
        out.append(f)
    return out


def audio_evidence(path: Path, max_s: float = 6.0) -> dict | None:
    """Load and compute evidence features. None on load failure."""
    try:
        la = load_wav(path)
    except AudioLoadError as e:
        return {"load_error": str(e)}
    x = la.samples[: int(max_s * la.sample_rate)]
    if len(x) < 256 or float(np.max(np.abs(x))) < 1e-5:
        return {"load_error": "silence_or_inaudible"}
    # spectral centroid + low-fraction on a central window
    seg = x[len(x) // 4: max(len(x) * 3 // 4, len(x) // 4 + 256)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / la.sample_rate)
    total = float(np.sum(X)) + 1e-12
    centroid = float(np.sum(f * X) / total)
    lowfrac = float(np.sum(X[f < 150]) / total)
    # onset density via envelope peaks
    env = np.sqrt(np.convolve(x ** 2, np.ones(256) / 256, mode="same"))
    thr = np.percentile(env, 90)
    onsets = int(np.sum((env[1:-1] > thr) & (env[1:-1] >= env[:-2]) &
                        (env[1:-1] >= env[2:]) &
                        (np.arange(1, len(env) - 1) > 1000)))
    dur = la.duration_s
    kind = "oneshot" if dur < 3.0 else "loop_or_stem"
    return {"duration_s": round(dur, 3), "sample_rate": la.sample_rate,
            "channels": la.channels, "kind": kind,
            "centroid_hz": round(centroid, 1), "low_frac": round(lowfrac, 3),
            "onsets": onsets, "sha256": la.sha256}


def refine_domain(evid: dict, nominal: str) -> str | None:
    """Reject only STRONG contradictions between filename claim and audio
    evidence. Ground truth for controlled cases is the perturbation
    itself; the domain label is metadata (recorded with evidence) used
    for breakdowns. One-shot requirement stays for drum domains."""
    c, lf, k = evid.get("centroid_hz", 0), evid.get("low_frac", 0), \
        evid.get("kind")
    if k != "oneshot" and nominal in ("kick", "snare", "clap", "hat",
                                      "tom", "perc"):
        return None
    if nominal == "kick":
        return None if (lf < 0.06 and c > 3000) else "kick"
    if nominal == "bass":
        return None if (lf < 0.05 and c > 3500) else "bass"
    if nominal == "hat":
        return None if (c < 800 and lf > 0.7) else "hat"
    return nominal


def pick_diverse(candidates: list[Path], n: int,
                 per_pack: int = 3) -> list[Path]:
    """Diversity guard: max N files per top-level pack group."""
    counts: dict[str, int] = {}
    out = []
    for f in candidates:
        try:
            group = f.relative_to(PACK_ROOT).parts[0]
        except ValueError:
            group = "stems"
        if counts.get(group, 0) >= per_pack:
            continue
        counts[group] = counts.get(group, 0) + 1
        out.append(f)
        if len(out) >= n:
            break
    return out


def list_wavs(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*")
                   if p.suffix.lower() == ".wav" and not p.name.startswith("._")])
