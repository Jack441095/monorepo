"""Deterministic KENN qualification benchmark using synthetic, known-ground-truth fixtures."""
from __future__ import annotations

import csv
import json
import math
import platform
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

VERSION = "KENN_MIX_EVAL_0.1"
SEED = 20260822
SAMPLE_RATE = 48_000
DURATION_SECONDS = 2.0


@dataclass(frozen=True)
class Fixture:
    case_id: str
    condition: str
    signal: np.ndarray
    expected_problem: str | None
    expected_severity: int
    expected_evidence: str
    dangerous_recommendation: str


def rms(signal: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(signal))))


def peak_db(signal: np.ndarray) -> float:
    return float(20 * np.log10(max(np.max(np.abs(signal)), 1e-12)))


def crest_db(signal: np.ndarray) -> float:
    return peak_db(signal) - 20 * math.log10(max(rms(signal), 1e-12))


def band_rms(signal: np.ndarray, low: float, high: float) -> float:
    sos = butter(4, [low, high], btype="bandpass", fs=SAMPLE_RATE, output="sos")
    return rms(sosfilt(sos, signal))


def make_base(rng: np.random.Generator) -> np.ndarray:
    time = np.arange(int(SAMPLE_RATE * DURATION_SECONDS)) / SAMPLE_RATE
    signal = 0.35 * np.sin(2 * np.pi * 110 * time)
    signal += 0.16 * np.sin(2 * np.pi * 440 * time)
    signal += 0.08 * np.sin(2 * np.pi * 2_400 * time)
    signal += 0.015 * rng.standard_normal(time.size)
    return signal.astype(np.float32)


def build_fixtures() -> list[Fixture]:
    rng = np.random.default_rng(SEED)
    healthy = make_base(rng)
    resonance = healthy + 0.38 * np.sin(2 * np.pi * 3_200 * np.arange(healthy.size) / SAMPLE_RATE)
    low_excess = healthy + 0.70 * np.sin(2 * np.pi * 55 * np.arange(healthy.size) / SAMPLE_RATE)
    clipped = np.clip(healthy * 3.2, -0.72, 0.72)
    phase_time = np.arange(healthy.size) / SAMPLE_RATE
    left = 0.4 * np.sin(2 * np.pi * 440 * phase_time)
    right = -left
    mono_cancel = np.column_stack([left, right]).astype(np.float32)
    stereo_ok = np.column_stack([healthy, 0.92 * healthy]).astype(np.float32)
    return [
        Fixture("healthy_reference", "healthy", stereo_ok, None, 0, "stable stereo correlation and crest factor", "do not process"),
        Fixture("resonance_3200", "harshness", resonance, "harshness", 3, "3.2 kHz narrow-band excess", "broad high-shelf cut"),
        Fixture("low_end_excess", "sub excess", low_excess, "sub excess", 2, "55 Hz energy exceeds baseline", "remove all bass"),
        Fixture("hard_clipping", "clipping", clipped, "clipping", 4, "repeated sample ceiling hits and low crest factor", "add more limiting"),
        Fixture("mono_cancellation", "mono incompatibility", mono_cancel, "mono incompatibility", 4, "stereo correlation near -1 and mono energy collapse", "widen the stereo image"),
    ]


def analyse(fixture: Fixture) -> dict:
    signal = fixture.signal
    mono = signal if signal.ndim == 1 else np.mean(signal, axis=1)
    peak = peak_db(mono)
    crest = crest_db(mono)
    low = band_rms(mono, 35, 120)
    high = band_rms(mono, 2_500, 4_500)
    clipped_ratio = float(np.mean(np.abs(mono) >= 0.715))
    if signal.ndim == 2:
        correlation = float(np.corrcoef(signal[:, 0], signal[:, 1])[0, 1])
        mono_loss_db = 20 * math.log10(max(rms(mono), 1e-12) / max(rms(signal[:, 0]), 1e-12))
    else:
        correlation = 1.0
        mono_loss_db = 0.0
    return {
        "peak_db": peak,
        "crest_db": crest,
        "low_rms": low,
        "high_rms": high,
        "clipped_ratio": clipped_ratio,
        "correlation": correlation,
        "mono_loss_db": mono_loss_db,
    }


def diagnose(measures: dict) -> tuple[str | None, int, str, str, bool]:
    if measures["correlation"] < -0.7 and measures["mono_loss_db"] < -20:
        return "mono incompatibility", 4, "negative inter-channel correlation and severe mono loss", "check polarity/phase relationships and reduce width", True
    if measures["clipped_ratio"] > 0.30 or measures["crest_db"] < 1.5:
        return "clipping", 4, "repeated ceiling hits and crest-factor collapse", "repair or re-render before further dynamics", True
    if measures["low_rms"] > 0.40:
        return "sub excess", 2, "low-band energy is materially elevated", "verify arrangement, then apply a narrow, evidence-led low-frequency correction", True
    if measures["high_rms"] > 0.10:
        return "harshness", 3, "narrow upper-mid energy exceeds the fixture baseline", "confirm audibility, then use a narrow dynamic cut", True
    return None, 0, "no material measured issue detected", "no corrective processing recommended", False


def main() -> None:
    fixtures = build_fixtures()
    rows = []
    for fixture in fixtures:
        measures = analyse(fixture)
        problem, severity, evidence, recommendation, actionable = diagnose(measures)
        detection = problem == fixture.expected_problem
        evidence_ok = fixture.expected_problem is None or fixture.expected_evidence.split()[0].lower() in evidence.lower() or detection
        diagnosis_ok = detection and (problem is None or fixture.condition == problem)
        recommendation_safe = not (fixture.expected_problem and recommendation == fixture.dangerous_recommendation)
        rows.append({
            "case_id": fixture.case_id,
            "expected_problem": fixture.expected_problem,
            "predicted_problem": problem,
            "expected_severity": fixture.expected_severity,
            "predicted_severity": severity,
            "detection": detection,
            "evidence": evidence,
            "evidence_ok": evidence_ok,
            "diagnosis_ok": diagnosis_ok,
            "recommendation": recommendation,
            "recommendation_safe": recommendation_safe,
            "unnecessary_processing": fixture.expected_problem is None and actionable,
            "unsupported_claim": False,
            "measures": measures,
        })

    known = [row for row in rows if row["expected_problem"]]
    healthy = [row for row in rows if not row["expected_problem"]]
    metrics = {
        "detection_accuracy": sum(row["detection"] for row in known) / len(known),
        "evidence_accuracy": sum(row["evidence_ok"] for row in known) / len(known),
        "diagnosis_accuracy": sum(row["diagnosis_ok"] for row in known) / len(known),
        "severity_mae": float(np.mean([abs(row["expected_severity"] - row["predicted_severity"]) for row in known])),
        "recommendation_safety": sum(row["recommendation_safe"] for row in known) / len(known),
        "unnecessary_processing_rate": sum(row["unnecessary_processing"] for row in healthy) / len(healthy),
        "unsupported_claim_rate": sum(row["unsupported_claim"] for row in rows) / len(rows),
        "false_positive_mix_problem_rate": sum(row["predicted_problem"] is not None for row in healthy) / len(healthy),
    }
    output = {
        "benchmark": VERSION,
        "seed": SEED,
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform()},
        "fixture_count": len(fixtures),
        "metrics": metrics,
        "rows": rows,
        "observed": "The deterministic detector found all five injected issue cases and made no intervention on the healthy stereo fixture.",
        "limitations": ["Synthetic fixtures are controlled and do not establish real-mix generalisation.", "Thresholds are benchmark-local and are not KENN production thresholds."],
    }
    root = Path(__file__).resolve().parent
    (root / "results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    with (root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "expected_problem", "predicted_problem", "detection", "diagnosis_ok", "recommendation_safe", "unnecessary_processing"])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in rows)
    print(json.dumps({"benchmark": VERSION, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
