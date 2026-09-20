#!/usr/bin/env python3
"""Create read-only energy-based windows for time-localized audio analysis.

This is a segmentation aid, not a semantic classifier. Windows can be passed
to specialist event models; the output contains no labels and never modifies
the source audio.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


VERSION = "audio_segment_windows_v1"
ANALYSIS_SR = 16_000
MAX_SECONDS = 120.0
FRAME = 1024
HOP = 256


def _db(value: float, floor: float = 1e-12) -> float:
    return float(20.0 * np.log10(max(abs(float(value)), floor)))


def _read(path: Path) -> np.ndarray:
    with sf.SoundFile(str(path)) as handle:
        source_sr = int(handle.samplerate)
        frames = min(len(handle), int(source_sr * MAX_SECONDS))
        data = handle.read(frames=frames, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    data = np.asarray(data, dtype=np.float32)
    if not len(data):
        raise ValueError("empty audio stream")
    if source_sr != ANALYSIS_SR:
        from math import gcd
        g = gcd(source_sr, ANALYSIS_SR)
        data = resample_poly(data, ANALYSIS_SR // g, source_sr // g)
    return np.asarray(data, dtype=np.float32)


def segment(path: str | Path, min_duration: float = 0.08,
            merge_gap: float = 0.15, threshold_db: float = 6.0,
            max_segments: int = 64) -> dict[str, Any]:
    if min_duration <= 0 or merge_gap < 0 or max_segments < 1:
        raise ValueError("invalid segmentation parameters")
    source = Path(path).expanduser().resolve()
    y = _read(source)
    padded = np.pad(y, (0, max(0, FRAME - len(y))))
    n_frames = 1 + max(0, (len(padded) - FRAME) // HOP)
    frames = np.lib.stride_tricks.sliding_window_view(padded, FRAME)[::HOP][:n_frames]
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    peak = np.max(np.abs(frames), axis=1)
    # Adaptive thresholding is robust to quiet sample packs: activity is
    # measured relative to the file's own RMS distribution.
    level_db = np.asarray([_db(value) for value in rms])
    baseline = float(np.percentile(level_db, 20.0))
    active = level_db >= baseline + threshold_db
    min_frames = max(1, int(round(min_duration * ANALYSIS_SR / HOP)))
    gap_frames = max(0, int(round(merge_gap * ANALYSIS_SR / HOP)))
    # Remove very short active islands.
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, flag in enumerate(active):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            if index - start >= min_frames:
                runs.append((start, index))
            start = None
    if start is not None and len(active) - start >= min_frames:
        runs.append((start, len(active)))
    merged: list[list[int]] = []
    for begin, end in runs:
        if merged and begin - merged[-1][1] <= gap_frames:
            merged[-1][1] = end
        else:
            merged.append([begin, end])
    if not merged:
        merged = [[0, len(active)]]
    if len(merged) > max_segments:
        # Keep the largest-energy windows, then restore chronological order.
        ranked = sorted(merged, key=lambda pair: float(np.max(rms[pair[0]:pair[1]])), reverse=True)
        merged = sorted(ranked[:max_segments])
    duration = len(y) / ANALYSIS_SR
    windows = []
    for index, (begin, end) in enumerate(merged):
        start_sample = min(len(y), begin * HOP)
        end_sample = min(len(y), max(start_sample + 1, end * HOP + FRAME))
        chunk = y[start_sample:end_sample]
        windows.append({
            "index": index,
            "start_seconds": round(start_sample / ANALYSIS_SR, 6),
            "end_seconds": round(end_sample / ANALYSIS_SR, 6),
            "duration_seconds": round((end_sample - start_sample) / ANALYSIS_SR, 6),
            "rms_dbfs": _db(np.sqrt(np.mean(np.square(chunk)))),
            "peak_dbfs": _db(np.max(np.abs(chunk))),
        })
    return {
        "record_type": "slo_audio_segment_windows",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "path": str(source),
        "analysis_sample_rate_hz": ANALYSIS_SR,
        "analysis_duration_seconds": round(duration, 6),
        "parameters": {"min_duration": min_duration, "merge_gap": merge_gap,
                        "threshold_db": threshold_db, "max_segments": max_segments},
        "windows": windows,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "windows_are_not_semantic_labels": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-duration", type=float, default=0.08)
    parser.add_argument("--merge-gap", type=float, default=0.15)
    parser.add_argument("--threshold-db", type=float, default=6.0)
    parser.add_argument("--max-segments", type=int, default=64)
    args = parser.parse_args()
    result = segment(args.path, args.min_duration, args.merge_gap,
                     args.threshold_db, args.max_segments)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "n_windows": len(result["windows"]),
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
