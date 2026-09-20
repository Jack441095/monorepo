from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import project_path, resolve_project_path


@dataclass
class ClipMetrics:
    name: str
    path: str
    duration_s: float
    tempo_bpm: Optional[float]
    onset_rate_hz: Optional[float]
    grid_pref: Optional[str]
    grid16_mean_abs_err_s: Optional[float]
    grid8_mean_abs_err_s: Optional[float]
    energy_arc_rms: Optional[List[float]]
    energy_arc_onset_rate_hz: Optional[List[float]]
    motif_rhythm_repetition: Optional[float]
    motif_chroma_repetition: Optional[float]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "duration_s": float(self.duration_s),
            "tempo_bpm": None if self.tempo_bpm is None else float(self.tempo_bpm),
            "onset_rate_hz": None if self.onset_rate_hz is None else float(self.onset_rate_hz),
            "grid_pref": self.grid_pref,
            "grid16_mean_abs_err_s": None if self.grid16_mean_abs_err_s is None else float(self.grid16_mean_abs_err_s),
            "grid8_mean_abs_err_s": None if self.grid8_mean_abs_err_s is None else float(self.grid8_mean_abs_err_s),
            "energy_arc_rms": None if self.energy_arc_rms is None else [float(x) for x in self.energy_arc_rms],
            "energy_arc_onset_rate_hz": None
            if self.energy_arc_onset_rate_hz is None
            else [float(x) for x in self.energy_arc_onset_rate_hz],
            "motif_rhythm_repetition": None
            if self.motif_rhythm_repetition is None
            else float(self.motif_rhythm_repetition),
            "motif_chroma_repetition": None
            if self.motif_chroma_repetition is None
            else float(self.motif_chroma_repetition),
            "warnings": list(self.warnings or []),
        }


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def _grid_mean_abs_error(onset_times_s: List[float], grid_s: float) -> Optional[float]:
    if not onset_times_s:
        return None
    g = float(grid_s)
    if g <= 1e-12:
        return None
    errs = []
    for t in onset_times_s:
        q = round(float(t) / g)
        errs.append(abs(float(t) - float(q) * g))
    return float(sum(errs) / max(1, len(errs)))


def _pref_from_errors(grid16_err: Optional[float], grid8_err: Optional[float]) -> Optional[str]:
    if grid16_err is None or grid8_err is None:
        return None
    e16 = float(grid16_err)
    e8 = float(grid8_err)
    # Require a margin so “mixed” doesn’t oscillate on noise.
    if e16 < e8 * 0.92:
        return "16th"
    if e8 < e16 * 0.92:
        return "8th"
    return "mixed"


def _autocorr_peak_strength(x: "Any") -> Optional[float]:
    """
    Return a 0..1-ish score representing how strongly the signal repeats.
    Uses the strongest autocorrelation peak after lag 0.
    """
    try:
        a = np.asarray(x, dtype=float)
        if a.size < 8:
            return None
        a = a - float(np.mean(a))
        denom = float(np.dot(a, a))
        if denom <= 1e-12:
            return 0.0
        ac = np.correlate(a, a, mode="full")
        ac = ac[ac.size // 2 :]
        ac = ac / float(ac[0] if abs(float(ac[0])) > 1e-12 else 1.0)
        # Search a musically plausible lag window (exclude lag 0).
        # With onset envelopes, repeated cells often show up early.
        lo = 4
        hi = min(int(ac.size) - 1, 256)
        if hi <= lo:
            return None
        peak = float(np.max(ac[lo:hi]))
        return float(max(0.0, min(1.0, peak)))
    except Exception:
        return None


def _analyze_with_librosa(path: Path, *, sr: int = 22050, hop_length: int = 512, arc_windows: int = 8) -> ClipMetrics:
    warnings: List[str] = []
    try:
        import numpy as np
        import librosa
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"librosa unavailable: {e}") from e

    y, sr2 = librosa.load(str(path), sr=int(sr), mono=True)
    if y is None or len(y) == 0:
        return ClipMetrics(
            name=path.stem,
            path=str(path),
            duration_s=0.0,
            tempo_bpm=None,
            onset_rate_hz=None,
            grid_pref=None,
            grid16_mean_abs_err_s=None,
            grid8_mean_abs_err_s=None,
            energy_arc_rms=None,
            energy_arc_onset_rate_hz=None,
            motif_rhythm_repetition=None,
            motif_chroma_repetition=None,
            warnings=["empty audio"],
        )
    dur = float(len(y) / float(sr2))

    oenv = librosa.onset.onset_strength(y=y, sr=sr2, hop_length=int(hop_length))
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=oenv,
        sr=sr2,
        hop_length=int(hop_length),
        backtrack=False,
        pre_max=8,
        post_max=8,
        pre_avg=8,
        post_avg=8,
        delta=0.2,
        wait=0,
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr2, hop_length=int(hop_length))
    onset_times_list = [float(t) for t in list(onset_times)]

    tempo_bpm: Optional[float]
    try:
        tempo_bpm = float(librosa.beat.tempo(onset_envelope=oenv, sr=sr2, hop_length=int(hop_length), aggregate=np.median)[0])
        tempo_bpm = _safe_float(tempo_bpm)
    except Exception:
        tempo_bpm = None
        warnings.append("tempo_estimate_failed")

    onset_rate = float(len(onset_times_list) / dur) if dur > 1e-6 else 0.0

    grid16_err = grid8_err = None
    grid_pref = None
    if tempo_bpm is not None and tempo_bpm > 1e-6:
        beat_s = 60.0 / float(tempo_bpm)
        grid8_s = beat_s / 2.0
        grid16_s = beat_s / 4.0
        grid16_err = _grid_mean_abs_error(onset_times_list, grid16_s)
        grid8_err = _grid_mean_abs_error(onset_times_list, grid8_s)
        grid_pref = _pref_from_errors(grid16_err, grid8_err)

    # Energy arc: windowed RMS and windowed onset rate
    energy_arc_rms: List[float] = []
    energy_arc_onsets: List[float] = []
    if arc_windows > 1 and dur > 1e-6:
        win = float(dur) / float(arc_windows)
        # RMS per window
        for i in range(int(arc_windows)):
            t0 = i * win
            t1 = min(dur, (i + 1) * win)
            s0 = int(round(t0 * sr2))
            s1 = int(round(t1 * sr2))
            seg = y[s0:s1] if s1 > s0 else y[0:0]
            if seg.size <= 0:
                energy_arc_rms.append(0.0)
                energy_arc_onsets.append(0.0)
                continue
            rms = float(np.sqrt(np.mean(np.square(seg))))
            energy_arc_rms.append(rms)
            # Onset rate per window
            n_on = sum(1 for t in onset_times_list if t0 <= float(t) < t1)
            energy_arc_onsets.append(float(n_on) / max(1e-6, (t1 - t0)))

    # Motif proxies: repetition in onset envelope + chroma
    motif_rhythm = _autocorr_peak_strength(oenv)
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr2)
        # collapse chroma to a scalar time series (total chroma energy changes)
        chroma_ts = np.mean(chroma, axis=0)
        motif_chroma = _autocorr_peak_strength(chroma_ts)
    except Exception:
        motif_chroma = None
        warnings.append("chroma_failed")

    return ClipMetrics(
        name=path.stem,
        path=str(path),
        duration_s=float(dur),
        tempo_bpm=tempo_bpm,
        onset_rate_hz=float(onset_rate),
        grid_pref=grid_pref,
        grid16_mean_abs_err_s=grid16_err,
        grid8_mean_abs_err_s=grid8_err,
        energy_arc_rms=energy_arc_rms or None,
        energy_arc_onset_rate_hz=energy_arc_onsets or None,
        motif_rhythm_repetition=motif_rhythm,
        motif_chroma_repetition=motif_chroma,
        warnings=warnings,
    )


def _analyze_basic(path: Path) -> ClipMetrics:
    """
    Fallback analysis: duration only (no tempo/onset/grid) if librosa isn't available.
    """
    import wave

    warnings = ["librosa_unavailable_reduced_metrics"]
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        dur = float(n) / float(sr) if sr else 0.0
    return ClipMetrics(
        name=path.stem,
        path=str(path),
        duration_s=float(dur),
        tempo_bpm=None,
        onset_rate_hz=None,
        grid_pref=None,
        grid16_mean_abs_err_s=None,
        grid8_mean_abs_err_s=None,
        energy_arc_rms=None,
        energy_arc_onset_rate_hz=None,
        motif_rhythm_repetition=None,
        motif_chroma_repetition=None,
        warnings=warnings,
    )


def _canonical_emotion_key(stem: str) -> str:
    s = (stem or "").strip().lower()
    # handle common filename typos in the provided set
    alias = {
        "nutural": "neutral",
        "optimistic": "optimism",
        "amusment": "amusement",
        "disapointed": "disappointment",
        "disproval": "disapproval",
        "embaressed": "embarrassment",
        "excitment": "excitement",
        "greif": "grief",
    }
    return alias.get(s, s)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument(
        "--input_dir",
        default=os.path.expanduser("~/Downloads/002_With_Atmos"),
        help="Directory containing emotion wavs (default: ~/Downloads/002_With_Atmos)",
    )
    ap.add_argument(
        "--output",
        default=".cache/reference_metrics.json",
        help="Output JSON path (default: .cache/reference_metrics.json)",
    )
    ap.add_argument("--sr", type=int, default=22050, help="Analysis sample rate (default: 22050)")
    ap.add_argument("--arc_windows", type=int, default=8, help="Energy arc windows (default: 8)")
    args = ap.parse_args()

    in_dir = Path(str(args.input_dir)).expanduser().resolve()
    out_path = resolve_project_path(str(args.output))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Some environments fail importing librosa's numba-decorated modules unless an
    # explicit writable cache path is available. Keep this local to the repo cache.
    os.environ.setdefault("NUMBA_CACHE_DIR", str(project_path(".cache", "numba").resolve()))

    wavs = sorted(in_dir.glob("*.wav"))
    if not wavs:
        raise SystemExit(f"No .wav files found in {in_dir}")

    # Detect librosa availability once.
    use_librosa = True
    try:
        import librosa  # noqa: F401
        import numpy  # noqa: F401
    except Exception:
        use_librosa = False

    by_emotion: Dict[str, Dict[str, Any]] = {}
    per_file: List[Dict[str, Any]] = []
    for p in wavs:
        try:
            m = _analyze_with_librosa(p, sr=int(args.sr), arc_windows=int(args.arc_windows)) if use_librosa else _analyze_basic(p)
        except Exception as e:
            m = ClipMetrics(
                name=p.stem,
                path=str(p),
                duration_s=0.0,
                tempo_bpm=None,
                onset_rate_hz=None,
                grid_pref=None,
                grid16_mean_abs_err_s=None,
                grid8_mean_abs_err_s=None,
                energy_arc_rms=None,
                energy_arc_onset_rate_hz=None,
                motif_rhythm_repetition=None,
                motif_chroma_repetition=None,
                warnings=[f"analysis_failed:{type(e).__name__}:{str(e)[:180]}"],
            )
        per_file.append(m.to_dict())
        by_emotion[_canonical_emotion_key(p.stem)] = m.to_dict()

    payload = {
        "input_dir": str(in_dir),
        "used_librosa": bool(use_librosa),
        "files": per_file,
        "by_emotion": by_emotion,
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Wrote {out_path} ({len(per_file)} wavs; librosa={use_librosa})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
