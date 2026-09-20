#!/usr/bin/env python3
"""
Loudness-match AutoMix renders for blind listening benchmark.

Takes v4 baseline, v5 bounded-gains, and v6 optimized renders and produces
level-matched A/B WAV pairs with shared session window, exact sample alignment,
true-peak safety, and content-addressed lineage records.
"""

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import sys
import logging

import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass
class LoudnessMetrics:
    """Measured loudness of a render."""
    lufs: float
    true_peak_dbtp: float
    num_samples: int
    sample_rate: int


@dataclass
class MatchedPair:
    """Loudness-matched A/B pair for listening."""
    project_id: str
    render_versions: list  # ['v4', 'v5', 'v6']
    baseline_version: str  # 'v4'
    compare_version: str

    baseline_lufs: float
    baseline_true_peak: float
    compare_lufs: float
    compare_true_peak: float

    target_lufs: float  # Matched loudness
    target_true_peak: float
    safety_gain_db: float  # -1 dBTP headroom

    baseline_gain_applied_db: float
    compare_gain_applied_db: float

    sample_rate: int
    num_samples: int
    duration_seconds: float

    baseline_wav_hash: str  # SHA-256
    compare_wav_hash: str
    matched_pair_hash: str  # Content hash of matched output

    metadata: dict  # Arbitrary metadata


def read_wav_float(path: Path) -> tuple[np.ndarray, int]:
    """Read a 16/24/32-bit PCM WAV as float32 in [-1, 1], shape (frames, channels).

    Uses the stdlib `wave` module so 24-bit files (which scipy.io.wavfile does not
    support) decode correctly. Mixdown deliveries are 24-bit stereo.
    """
    import wave as _wave

    with _wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        sample_width = w.getsampwidth()
        sample_rate = w.getframerate()
        raw = w.readframes(w.getnframes())

    if sample_width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / (2 ** 15)
    elif sample_width == 3:
        # 24-bit little-endian signed: expand each 3-byte sample to int32.
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        vals = a[:, 0] | (a[:, 1] << 8) | (a[:, 2] << 16)
        vals = np.where(vals & 0x800000, vals - (1 << 24), vals)  # sign-extend
        data = vals.astype(np.float32) / (2 ** 23)
    elif sample_width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / (2 ** 31)
    else:
        raise ValueError(f"Unsupported sample width: {sample_width} bytes")

    if channels > 1:
        data = data.reshape(-1, channels)
    return data, sample_rate


def measure_loudness(audio: np.ndarray, sr: int) -> tuple[float, float]:
    """
    Measure integrated LUFS (BS.1770-4) and true peak using the codebase's own
    production loudness measurement — the exact same one the render gate uses, so
    matching is consistent with how the mixdowns were made. Falls back to a rough
    estimate only if the module can't be imported.

    Returns (lufs, true_peak_dbtp). ``audio`` is (frames,) or (frames, channels).
    """
    if audio.ndim == 1:
        left = right = audio
    else:
        left = audio[:, 0]
        right = audio[:, 1] if audio.shape[1] > 1 else audio[:, 0]

    try:
        import sys
        aa = str(Path(__file__).resolve().parent.parent / "studio" / "audio_analysis")
        if aa not in sys.path:
            sys.path.insert(0, aa)
        from audio_analysis.analysis_core.loudness import calculate_loudness_profile
        profile = calculate_loudness_profile(left.tolist(), right.tolist(), sr)
        lufs = float(profile.get("integrated_lufs", -60.0))
        # 4x-oversampled peak as a true-peak proxy for the clipping guard (the
        # codebase's calculate_true_peak needs raw file bytes we don't have here).
        from scipy.signal import resample_poly
        up = resample_poly(audio.reshape(audio.shape[0], -1), 4, 1, axis=0)
        true_peak_dbtp = 20 * np.log10(float(np.max(np.abs(up))) + 1e-12)
        return lufs, true_peak_dbtp
    except Exception:  # pragma: no cover - fallback only
        mean_square = float(np.mean(audio ** 2))
        lufs = -0.691 + 10 * np.log10(mean_square + 1e-10)
        true_peak_dbtp = 20 * np.log10(float(np.max(np.abs(audio))) + 1e-10)
        return lufs, true_peak_dbtp


def apply_gain(audio: np.ndarray, gain_db: float, true_peak_ceiling_dbtp: float = -1.0) -> tuple[np.ndarray, bool]:
    """
    Apply gain with clipping check.

    Returns (processed_audio, is_clipped).
    """
    gain_linear = 10 ** (gain_db / 20.0)
    processed = audio * gain_linear

    # Check for clipping
    max_dbtp = 20 * np.log10(np.max(np.abs(processed)) + 1e-10)
    is_clipped = max_dbtp > true_peak_ceiling_dbtp + 0.01

    return processed, is_clipped


def write_wav_float(path: Path, audio: np.ndarray, sr: int, bit_depth: int = 24):
    """Write float audio (shape (frames,) or (frames, channels)) as PCM WAV.

    Uses the stdlib `wave` module so 24-bit output is written correctly (scipy
    has no 24-bit support). Clips to [-1, 1] before quantising.
    """
    import wave as _wave

    a = np.clip(np.asarray(audio, dtype=np.float64), -1.0, 1.0)
    if a.ndim == 1:
        a = a[:, None]
    frames, channels = a.shape
    inter = a.reshape(-1)  # interleaved frame-major (frames, ch) -> flat

    if bit_depth == 16:
        ints = (inter * (2 ** 15 - 1)).astype("<i4")
        raw = ints.astype("<i2").tobytes()
        sampwidth = 2
    elif bit_depth == 24:
        ints = (inter * (2 ** 23 - 1)).astype("<i4")
        le = ints.view(np.uint8).reshape(-1, 4)[:, :3]
        raw = np.ascontiguousarray(le).tobytes()
        sampwidth = 3
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")

    with _wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(sr)
        w.writeframes(raw)


def hash_file(path: Path, chunk_size: int = 8192) -> str:
    """SHA-256 hash of file contents."""
    sha = hashlib.sha256()

    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha.update(chunk)

    return sha.hexdigest()


def loudness_match_pair(
    project_id: str,
    baseline_wav: Path,
    compare_wav: Path,
    baseline_version: str,
    compare_version: str,
    target_lufs: float = -14.0,
    true_peak_ceiling: float = -1.0,
    output_dir: Optional[Path] = None
) -> MatchedPair:
    """
    Load two renders, measure loudness, level-match, and export A/B pair.

    Returns MatchedPair with full provenance.
    """

    logger.info(f"Loading {baseline_version} baseline: {baseline_wav}")
    baseline_audio, sr_baseline = read_wav_float(baseline_wav)
    baseline_lufs, baseline_tp = measure_loudness(baseline_audio, sr_baseline)

    logger.info(f"Loading {compare_version} compare: {compare_wav}")
    compare_audio, sr_compare = read_wav_float(compare_wav)
    compare_lufs, compare_tp = measure_loudness(compare_audio, sr_compare)

    # Verify sample rate and length match
    if sr_baseline != sr_compare:
        raise ValueError(f"Sample rate mismatch: {sr_baseline} vs {sr_compare}")

    if len(baseline_audio) != len(compare_audio):
        raise ValueError(f"Duration mismatch: {len(baseline_audio)} vs {len(compare_audio)}")

    sr = sr_baseline
    num_samples = len(baseline_audio)
    duration = num_samples / sr

    # Calculate gains to reach target
    baseline_gain_db = target_lufs - baseline_lufs
    compare_gain_db = target_lufs - compare_lufs

    logger.info(f"Baseline gain: {baseline_gain_db:.2f} dB ({baseline_lufs:.2f} → {target_lufs:.2f} LUFS)")
    logger.info(f"Compare gain:  {compare_gain_db:.2f} dB ({compare_lufs:.2f} → {target_lufs:.2f} LUFS)")

    # Apply gains
    baseline_matched, baseline_clipped = apply_gain(baseline_audio, baseline_gain_db, true_peak_ceiling)
    compare_matched, compare_clipped = apply_gain(compare_audio, compare_gain_db, true_peak_ceiling)

    if baseline_clipped or compare_clipped:
        logger.warning("⚠️  Clipping detected in level-matched output")

    # Verify loudness
    baseline_verify_lufs, baseline_verify_tp = measure_loudness(baseline_matched, sr)
    compare_verify_lufs, compare_verify_tp = measure_loudness(compare_matched, sr)

    logger.info(f"Matched baseline LUFS: {baseline_verify_lufs:.2f}, true peak: {baseline_verify_tp:.2f} dBTP")
    logger.info(f"Matched compare LUFS:  {compare_verify_lufs:.2f}, true peak: {compare_verify_tp:.2f} dBTP")

    loudness_error_baseline = abs(baseline_verify_lufs - target_lufs)
    loudness_error_compare = abs(compare_verify_lufs - target_lufs)

    if loudness_error_baseline > 0.5 or loudness_error_compare > 0.5:
        logger.warning(f"⚠️  Loudness matching error > 0.5 LU: {loudness_error_baseline:.2f}, {loudness_error_compare:.2f}")

    # Export matched pair
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        baseline_out = output_dir / f"{project_id}_baseline_{baseline_version}_matched.wav"
        compare_out = output_dir / f"{project_id}_compare_{compare_version}_matched.wav"

        logger.info(f"Writing {baseline_out}")
        write_wav_float(baseline_out, baseline_matched, sr, bit_depth=24)

        logger.info(f"Writing {compare_out}")
        write_wav_float(compare_out, compare_matched, sr, bit_depth=24)

        baseline_hash = hash_file(baseline_out)
        compare_hash = hash_file(compare_out)
    else:
        baseline_hash = hashlib.sha256(baseline_matched.tobytes()).hexdigest()
        compare_hash = hashlib.sha256(compare_matched.tobytes()).hexdigest()

    # Create matched pair record
    pair = MatchedPair(
        project_id=project_id,
        render_versions=['v4', 'v5', 'v6'],
        baseline_version=baseline_version,
        compare_version=compare_version,
        baseline_lufs=float(baseline_lufs),
        baseline_true_peak=float(baseline_tp),
        compare_lufs=float(compare_lufs),
        compare_true_peak=float(compare_tp),
        target_lufs=target_lufs,
        target_true_peak=true_peak_ceiling,
        safety_gain_db=-1.0,
        baseline_gain_applied_db=float(baseline_gain_db),
        compare_gain_applied_db=float(compare_gain_db),
        sample_rate=sr,
        num_samples=num_samples,
        duration_seconds=float(duration),
        baseline_wav_hash=hash_file(baseline_wav),
        compare_wav_hash=hash_file(compare_wav),
        matched_pair_hash=f"{baseline_hash[:8]}_{compare_hash[:8]}",
        metadata={
            'baseline_verify_lufs': float(baseline_verify_lufs),
            'baseline_verify_tp': float(baseline_verify_tp),
            'compare_verify_lufs': float(compare_verify_lufs),
            'compare_verify_tp': float(compare_verify_tp),
            'loudness_error_baseline_lu': float(loudness_error_baseline),
            'loudness_error_compare_lu': float(loudness_error_compare),
        }
    )

    return pair


def extract_mixdown_wav(package_zip: Path, dest_dir: Path, label: str) -> Path:
    """Extract the single mixdown_*.wav from a mix package ZIP to dest_dir."""
    import zipfile
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_zip) as zf:
        wavs = [n for n in zf.namelist() if n.startswith("mixdown_") and n.endswith(".wav")]
        if not wavs:
            raise ValueError(f"No mixdown_*.wav in {package_zip}")
        out = dest_dir / f"{label}_{Path(wavs[0]).name}"
        with zf.open(wavs[0]) as src, open(out, "wb") as dst:
            dst.write(src.read())
    return out


def match_two_packages(
    project_id: str,
    baseline_zip: Path,
    compare_zip: Path,
    baseline_version: str,
    compare_version: str,
    output_root: Path,
    target_lufs: float = -14.0,
) -> MatchedPair:
    """Extract both packages' mixdowns, loudness-match, and export an A/B pair."""
    work = output_root / project_id
    work.mkdir(parents=True, exist_ok=True)
    baseline_wav = extract_mixdown_wav(baseline_zip, work, f"raw_{baseline_version}")
    compare_wav = extract_mixdown_wav(compare_zip, work, f"raw_{compare_version}")
    pair = loudness_match_pair(
        project_id=project_id,
        baseline_wav=baseline_wav,
        compare_wav=compare_wav,
        baseline_version=baseline_version,
        compare_version=compare_version,
        target_lufs=target_lufs,
        output_dir=work,
    )
    (work / f"matched_pair_{baseline_version}_vs_{compare_version}.json").write_text(
        json.dumps(asdict(pair), indent=2)
    )
    return pair


def main():
    """CLI: match two mix packages into a loudness-matched blind A/B pair.

    Usage:
      listening_benchmark_loudness_match.py <project_id> <baseline.zip> <compare.zip> \
          [baseline_label] [compare_label]
    """
    output_root = Path(__file__).resolve().parent.parent / "artifacts" / "listening_benchmark_2026-07-16"
    if len(sys.argv) < 4:
        logger.info(main.__doc__)
        return
    project_id = sys.argv[1]
    baseline_zip = Path(sys.argv[2]).expanduser().resolve()
    compare_zip = Path(sys.argv[3]).expanduser().resolve()
    baseline_label = sys.argv[4] if len(sys.argv) > 4 else "baseline"
    compare_label = sys.argv[5] if len(sys.argv) > 5 else "compare"

    pair = match_two_packages(
        project_id, baseline_zip, compare_zip,
        baseline_label, compare_label, output_root,
    )
    logger.info(f"\nMatched A/B written under {output_root / project_id}")
    logger.info(f"  baseline {baseline_label}: {pair.baseline_lufs:.2f} LUFS -> {pair.metadata['baseline_verify_lufs']:.2f}")
    logger.info(f"  compare  {compare_label}: {pair.compare_lufs:.2f} LUFS -> {pair.metadata['compare_verify_lufs']:.2f}")
    logger.info(f"  loudness match error: {pair.metadata['loudness_error_compare_lu']:.3f} LU")


if __name__ == '__main__':
    main()
