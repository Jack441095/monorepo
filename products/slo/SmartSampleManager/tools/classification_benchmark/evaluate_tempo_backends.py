#!/usr/bin/env python3
"""Compare the production tempo estimate with a research-only beat tracker.

This tool is deliberately evaluation-only.  It consumes an existing tempo
receipt, decodes only rows already marked as eligible, and writes a new
receipt; it never changes the native estimator, cache, metadata, or files.
The beat tracker is a comparison arm, not an automatic promotion candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import librosa
import numpy as np


VERSION = "tempo_backend_comparison_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("tempo receipt must be a JSON list or an object with rows")
    return rows


def _scalar(value: Any) -> float:
    array = np.asarray(value).reshape(-1)
    return float(array[0]) if array.size else 0.0


def _metrics(references: np.ndarray, estimates: np.ndarray) -> dict[str, Any]:
    valid = np.isfinite(estimates) & (estimates > 0.0)
    accepted_refs = references[valid]
    accepted = estimates[valid]
    absolute = np.abs(accepted - accepted_refs)
    # Half/double-time is a real ambiguity.  Report it separately, never use
    # it to silently relabel the primary absolute-error metric.
    octave_error = np.minimum.reduce([
        np.abs(accepted - accepted_refs),
        np.abs(accepted * 2.0 - accepted_refs),
        np.abs(accepted / 2.0 - accepted_refs),
    ]) if accepted.size else np.empty(0, dtype=float)
    return {
        "reference_count": int(len(references)),
        "accepted_count": int(len(accepted)),
        "coverage": float(np.mean(valid)) if len(references) else 0.0,
        "mae_bpm_accepted": float(np.mean(absolute)) if accepted.size else None,
        "median_abs_error_bpm_accepted": float(np.median(absolute)) if accepted.size else None,
        "within_2_bpm_accepted": int(np.sum(absolute <= 2.0)),
        "within_5_bpm_accepted": int(np.sum(absolute <= 5.0)),
        "octave_aware_mae_bpm_accepted": float(np.mean(octave_error)) if accepted.size else None,
        "octave_aware_within_2_bpm_accepted": int(np.sum(octave_error <= 2.0)),
        "octave_aware_within_5_bpm_accepted": int(np.sum(octave_error <= 5.0)),
    }


def evaluate(receipt: Path, out: Path, duration: float = 20.0) -> dict[str, Any]:
    if duration < 2.0 or not np.isfinite(duration):
        raise ValueError("duration must be finite and at least two seconds")
    rows = _load_rows(receipt)
    eligible = [
        row for row in rows
        if row.get("referenceEligible") is True
        and float(row.get("referenceBpm", 0.0) or 0.0) > 0.0
    ]
    references: list[float] = []
    incumbent: list[float] = []
    beat_estimates: list[float] = []
    evaluated_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for row in eligible:
        path = Path(str(row.get("filePath", "")))
        reference = float(row["referenceBpm"])
        references.append(reference)
        incumbent.append(float(row.get("estimatedBpm", 0.0) or 0.0))
        result: dict[str, Any] = {
            "filePath": str(path),
            "referenceBpm": reference,
            "incumbentEstimatedBpm": incumbent[-1],
        }
        try:
            if not path.is_file():
                raise FileNotFoundError(str(path))
            waveform, sample_rate = librosa.load(
                str(path), sr=22050, mono=True, duration=float(duration)
            )
            if len(waveform) < int(sample_rate * 2.0):
                raise ValueError("decoded audio is shorter than two seconds")
            tempo, _ = librosa.beat.beat_track(
                y=waveform, sr=sample_rate, units="time", trim=False
            )
            estimate = _scalar(tempo)
            if not np.isfinite(estimate) or estimate <= 0.0:
                raise ValueError("beat tracker returned an invalid BPM")
            beat_estimates.append(estimate)
            result["beatTrackerBpm"] = estimate
            result["status"] = "ok"
        except Exception as exc:  # one bad file must not hide the receipt
            beat_estimates.append(0.0)
            result["beatTrackerBpm"] = 0.0
            result["status"] = "error"
            result["error"] = f"{type(exc).__name__}: {exc}"
            errors.append({"filePath": str(path), "error": result["error"]})
        evaluated_rows.append(result)

    reference_array = np.asarray(references, dtype=float)
    incumbent_array = np.asarray(incumbent, dtype=float)
    beat_array = np.asarray(beat_estimates, dtype=float)
    result = {
        "record_type": "slo_tempo_backend_comparison",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(receipt.resolve()),
        "source_receipt_sha256": _sha256(receipt),
        "backend": {
            "name": "librosa.beat.beat_track",
            "librosa_version": str(getattr(librosa, "__version__", "unknown")),
            "sample_rate_hz": 22050,
            "max_duration_seconds": float(duration),
        },
        "eligible_rows": len(eligible),
        "evaluated_rows": len(evaluated_rows),
        "decode_or_tracker_errors": errors,
        "incumbent": _metrics(reference_array, incumbent_array),
        "beat_tracker": _metrics(reference_array, beat_array),
        "rows": evaluated_rows,
        "accuracy_claim": None,
        "promotion_decision": "research_only",
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "cache_modified": False,
            "production_policy_changed": False,
            "automatic_metadata_action": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=20.0)
    args = parser.parse_args()
    result = evaluate(args.receipt, args.out, args.duration)
    print(json.dumps({
        "out": str(args.out),
        "eligible_rows": result["eligible_rows"],
        "incumbent": result["incumbent"],
        "beat_tracker": result["beat_tracker"],
        "read_only": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
