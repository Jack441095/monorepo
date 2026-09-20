#!/usr/bin/env python3
"""Extract a physical, human-readable definition card for audio samples.

This is an evidence layer, not a classifier. It reads audio and writes a
separate JSON receipt; it never labels, renames, moves, or modifies source
files. Heuristic form/tags are explicitly marked as provisional so they cannot
be mistaken for human ground truth.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf


FEATURE_VERSION = "definition_card_v1"
ANALYSIS_SR = 16_000
MAX_ANALYSIS_SECONDS = 60.0
AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".ogg", ".m4a", ".mp3"}


def _db(value: float, floor: float = 1e-12) -> float:
    return float(20.0 * np.log10(max(abs(float(value)), floor)))


def _finite_median(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.median(values)) if values.size else None


def _normalise_audio(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        return data.astype(np.float32, copy=False)
    return np.mean(data.astype(np.float32, copy=False), axis=1)


def _read_audio(path: Path) -> tuple[np.ndarray, int, int, bool]:
    """Read and resample one file, returning mono audio and source metadata."""
    with sf.SoundFile(str(path)) as handle:
        source_sr = int(handle.samplerate)
        source_channels = int(handle.channels)
        max_frames = int(MAX_ANALYSIS_SECONDS * source_sr)
        data = handle.read(frames=max_frames, dtype="float32", always_2d=True)
    truncated = len(data) >= max_frames
    y = _normalise_audio(data)
    if source_sr != ANALYSIS_SR and len(y):
        import librosa

        y = librosa.resample(y, orig_sr=source_sr, target_sr=ANALYSIS_SR)
    return np.asarray(y, dtype=np.float32), source_sr, source_channels, truncated


def _autocorrelation_period(onset_env: np.ndarray, sr: int, hop: int) -> tuple[float | None, float]:
    """Return the strongest plausible onset period and normalised strength."""
    if len(onset_env) < 8 or float(np.max(onset_env)) <= 0.0:
        return None, 0.0
    x = onset_env.astype(float) - float(np.mean(onset_env))
    denom = float(np.dot(x, x))
    if denom <= 1e-12:
        return None, 0.0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    ac = ac / denom
    min_lag = max(1, int(round(0.25 * sr / hop)))
    max_lag = min(len(ac) - 1, int(round(4.0 * sr / hop)))
    if max_lag <= min_lag:
        return None, 0.0
    lag = min_lag + int(np.argmax(ac[min_lag:max_lag + 1]))
    strength = float(max(0.0, min(1.0, ac[lag])))
    return float(lag * hop / sr), strength


def _heuristic_form(duration: float, onset_count: int, onset_density: float,
                    periodicity: float, periodicity_strength: float,
                    rms_db: float) -> tuple[str, float]:
    """Describe temporal form, never a semantic class."""
    if rms_db < -70.0:
        return "silent_or_near_silent", 0.99
    if periodicity is not None and periodicity_strength >= 0.55 and duration >= 1.5:
        return "possibly_loop", min(0.95, 0.55 + periodicity_strength * 0.4)
    if duration <= 1.5 and onset_count <= 3:
        return "possibly_one_shot", 0.68
    if duration >= 8.0 and onset_density <= 0.5:
        return "possibly_ambience_or_sustain", 0.62
    if duration >= 2.0 and onset_density <= 1.0:
        return "possibly_sustained", 0.55
    return "mixed_or_uncertain_form", 0.35


def analyse_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Analyse one file without producing a semantic label."""
    import librosa

    source_path = Path(path).expanduser().resolve()
    y, source_sr, source_channels, truncated = _read_audio(source_path)
    if not len(y):
        raise ValueError("empty audio stream")
    duration = float(len(y) / ANALYSIS_SR)
    peak = float(np.max(np.abs(y)))
    rms = float(np.sqrt(np.mean(np.square(y))))
    crest = float(peak / max(rms, 1e-12))
    clipped_fraction = float(np.mean(np.abs(y) >= 0.999))

    frame_length = 2048
    hop = 512
    if len(y) < frame_length:
        y = np.pad(y, (0, frame_length - len(y)))
    stft = librosa.stft(y, n_fft=frame_length, hop_length=hop, center=True)
    magnitude = np.abs(stft)
    freqs = librosa.fft_frequencies(sr=ANALYSIS_SR, n_fft=frame_length)
    energy = np.square(magnitude)
    total_energy = float(np.sum(energy))
    low_energy = float(np.sum(energy[freqs <= 250.0]))
    high_energy = float(np.sum(energy[freqs >= 2000.0]))
    centroid = float(np.mean(librosa.feature.spectral_centroid(S=magnitude, sr=ANALYSIS_SR)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(S=magnitude, sr=ANALYSIS_SR, roll_percent=0.85)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(S=magnitude)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y, frame_length=frame_length, hop_length=hop)))
    rms_frames = librosa.feature.rms(S=magnitude)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=ANALYSIS_SR, hop_length=hop)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=ANALYSIS_SR,
                                              hop_length=hop, backtrack=False)
    onset_count = int(len(onset_frames))
    onset_density = float(onset_count / max(duration, 1e-6))
    period, period_strength = _autocorrelation_period(onset_env, ANALYSIS_SR, hop)
    try:
        tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=ANALYSIS_SR, hop_length=hop)
        tempo_value = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else None
    except Exception:
        tempo_value = None

    harmonic, percussive = librosa.effects.hpss(y)
    harmonic_ratio = float(np.sum(harmonic ** 2) / max(np.sum(y ** 2), 1e-12))
    try:
        f0 = librosa.yin(y, fmin=40.0, fmax=min(4000.0, ANALYSIS_SR / 2 - 1),
                         sr=ANALYSIS_SR, frame_length=frame_length, hop_length=hop)
        voiced = f0[np.isfinite(f0)]
        pitch_hz = _finite_median(voiced)
        pitch_confidence = float(len(voiced) / max(len(f0), 1))
    except Exception:
        pitch_hz = None
        pitch_confidence = 0.0

    # Leading/trailing silence is measured against the file's own peak, not a
    # fixed recording level, so this remains useful for quiet sample packs.
    gate = max(peak * 0.01, 1e-5)
    active = np.flatnonzero(np.abs(y) >= gate)
    if active.size:
        leading_silence = float(active[0] / ANALYSIS_SR)
        trailing_silence = float((len(y) - active[-1] - 1) / ANALYSIS_SR)
    else:
        leading_silence = trailing_silence = duration

    # Stereo correlation is intentionally left null for mono sources.
    stereo_correlation: float | None = None
    if source_channels >= 2:
        with sf.SoundFile(str(source_path)) as handle:
            raw = handle.read(frames=int(MAX_ANALYSIS_SECONDS * source_sr),
                              dtype="float32", always_2d=True)
        if raw.shape[1] >= 2 and np.std(raw[:, 0]) > 1e-8 and np.std(raw[:, 1]) > 1e-8:
            stereo_correlation = float(np.corrcoef(raw[:, 0], raw[:, 1])[0, 1])

    low_ratio = low_energy / max(total_energy, 1e-12)
    high_ratio = high_energy / max(total_energy, 1e-12)
    form, form_confidence = _heuristic_form(
        duration, onset_count, onset_density, period, period_strength, _db(rms)
    )
    tags: list[str] = []
    if low_ratio >= 0.45:
        tags.append("low_end_heavy")
    if centroid >= 4000.0:
        tags.append("bright")
    elif centroid < 1200.0:
        tags.append("dark")
    if harmonic_ratio >= 0.55 and flatness < 0.25:
        tags.append("tonal_or_harmonic")
    if harmonic_ratio < 0.30 or flatness >= 0.40:
        tags.append("noisy_or_inharmonic")
    if crest >= 5.0 or onset_density >= 2.0:
        tags.append("transient_dense")
    if clipped_fraction > 0.001:
        tags.append("possible_clipping")
    if source_channels == 1 or stereo_correlation is not None and stereo_correlation >= 0.98:
        tags.append("mostly_mono")
    elif stereo_correlation is not None and stereo_correlation < 0.5:
        tags.append("wide_or_decorrelated")

    uncertainty: list[str] = []
    if truncated:
        uncertainty.append("analysis_truncated_at_60_seconds")
    if rms < 1e-4:
        uncertainty.append("very_low_level")
    if pitch_confidence < 0.2:
        uncertainty.append("weak_or_ambiguous_pitch")
    if onset_count == 0:
        uncertainty.append("no_clear_onsets")
    if period is None or period_strength < 0.35:
        uncertainty.append("weak_periodicity")
    if clipped_fraction > 0.01:
        uncertainty.append("clipping_may_distort_features")

    return {
        "record_type": "slo_audio_definition_card",
        "schema_version": "1.0.0",
        "feature_version": FEATURE_VERSION,
        "safety": {
            "source_modified": False,
            "semantic_label_created": False,
            "rename_action": False,
            "heuristics_are_not_ground_truth": True,
        },
        "path": str(source_path),
        "source": {
            "sample_rate_hz": source_sr,
            "channels": source_channels,
            "analysis_sample_rate_hz": ANALYSIS_SR,
            "analysis_duration_seconds": duration,
            "truncated": truncated,
        },
        "signal": {
            "rms_dbfs": _db(rms),
            "peak_dbfs": _db(peak),
            "crest_factor": crest,
            "clipped_fraction": clipped_fraction,
            "leading_silence_seconds": leading_silence,
            "trailing_silence_seconds": trailing_silence,
        },
        "spectrum": {
            "spectral_centroid_hz": centroid,
            "spectral_rolloff_hz": rolloff,
            "spectral_flatness": flatness,
            "zero_crossing_rate": zcr,
            "low_band_energy_ratio": low_ratio,
            "high_band_energy_ratio": high_ratio,
            "harmonic_energy_ratio": harmonic_ratio,
        },
        "temporal": {
            "onset_count": onset_count,
            "onset_density_per_second": onset_density,
            "estimated_tempo_bpm": tempo_value,
            "periodicity_seconds": period,
            "periodicity_strength": period_strength,
            "form_hint": form,
            "form_hint_confidence": form_confidence,
        },
        "pitch": {"median_f0_hz": pitch_hz, "voiced_frame_fraction": pitch_confidence},
        "spatial": {"stereo_correlation": stereo_correlation},
        "heuristic_tags": tags,
        "uncertainty_reasons": uncertainty,
    }


def _iter_paths(root: Path, limit: int | None) -> Iterable[Path]:
    paths = (p for p in sorted(root.rglob("*"))
             if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)
    for index, path in enumerate(paths):
        if limit is not None and index >= limit:
            break
        yield path


def _analyse_worker(path: str) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """Process-pool wrapper that keeps card ordering in the parent process."""
    try:
        return analyse_file(path), None
    except Exception as exc:
        return None, {"path": str(Path(path).resolve()), "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("paths", nargs="*", type=Path)
    source.add_argument("--root", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1,
                        help="parallel audio-analysis processes (default: 1)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    paths = list(_iter_paths(args.root, args.limit)) if args.root else args.paths
    cards: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if args.workers == 1:
        results = (_analyse_worker(str(path)) for path in paths)
    else:
        pool = concurrent.futures.ProcessPoolExecutor(max_workers=args.workers)
        results = pool.map(_analyse_worker, (str(path) for path in paths))
    try:
        for card, error in results:
            if card is not None:
                cards.append(card)
            elif error is not None:
                errors.append(error)
    finally:
        if args.workers != 1:
            pool.shutdown(wait=True)
    payload = {
        "record_type": "slo_audio_definition_cards",
        "schema_version": "1.0.0",
        "feature_version": FEATURE_VERSION,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "safety": {
            "read_only": True,
            "source_files_modified": False,
            "semantic_labels_created": False,
            "rename_actions": False,
        },
        "n_requested": len(paths),
        "n_cards": len(cards),
        "n_errors": len(errors),
        "cards": cards,
        "errors": errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"definition cards: {len(cards)}; errors: {len(errors)}; wrote {args.out}")


if __name__ == "__main__":
    main()
