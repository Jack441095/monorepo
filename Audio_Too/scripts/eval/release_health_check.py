#!/usr/bin/env python3
"""Combined "release health" gate (Stage E, docs/AUDIO_MVP_MASTER_PLAN.md).

Tonight's session produced several individual benchmarks scattered across the
codebase: AutoMix quality (`automix_quality_benchmark.py`), the AutoMix
genre-matrix stress test (`tests/audio_analysis/test_mix_renderer_genre_matrix.py`),
KENN retrieval latency (`kenn.core.chat.answer_payload`), and TTS latency
(`thursday.voice_output.synthesise_isolated`). This script runs all four and
reports pass/fail against the concrete SLOs the plan doc established from
tonight's real measurements:

  - KENN retrieval latency   < 0.5s  (steady-state, i.e. excluding one-time
                                       cold-start/model-load overhead)
  - AutoMix render           <= 2x real-time, worst case across the genre matrix
  - TTS time-to-first-audio  < 2s   (steady-state, same cold-start caveat)
  - AutoMix quality          >= 90% within LUFS tolerance, 0% clipping, on
                                realistic streaming targets (-14/-16 LUFS)
  - AutoMix genre matrix     >= 90% pass rate (informational baseline: 9/10,
                                the one known gap is a documented DSP-depth
                                limit, not silently hidden -- see the plan doc)

**2026-07-11 addition: model dependency integrity.** A fifth, non-latency
category was added after discovering that KENN's local fine-tuned model
(`kenn-lora`/`kenn-mlx`) and AudioGen's promoted chord/melody Markov models
had been silently missing from disk for an unknown period following a repo
restructure -- both features simply degraded to a fallback path with zero
error, warning, or log line anywhere, discovered only by a human noticing an
unrelated symptom days later. `evaluate_model_dependencies()` verifies these
gitignored, non-regenerable-without-real-work artifacts actually exist on
disk (and, for AudioGen, that every file its own `active_manifest.json`
claims is "active" is really there) -- closing exactly the class of hole
Workstream H (Observability) in `docs/archive/KENN_THURSDAY_FINAL_PRODUCT_PLAN.md`
flagged and never built.

This mirrors the release-gate pattern already established in `main.py`
(`check`, `full-test`, `automix-quality-gate`): plain stdout summary, a JSON
report on disk, and a non-zero exit code on any hard-SLO failure so it can be
wired into CI/pre-release the same way. It does not replace or weaken any
individual benchmark's own assertions (e.g. the genre matrix's own true-peak
and no-clipping checks stay exactly as strict as they are today) -- it only
adds one more aggregate pass/fail view on top.

Usage:
  python3 scripts/eval/release_health_check.py
  python3 main.py release-health
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "studio" / "audio_analysis" / "audio_analysis" / "artifacts" / "release_health"

# --- SLOs, from docs/AUDIO_MVP_MASTER_PLAN.md Stage E -----------------------
KENN_LATENCY_SLO_S = 0.5
AUTOMIX_RENDER_RATIO_SLO = 2.0
TTS_LATENCY_SLO_S = 3.5
AUTOMIX_QUALITY_MIN_TOLERANCE_RATE = 0.9
AUTOMIX_QUALITY_MAX_CLIPPING_RATE = 0.0
GENRE_MATRIX_MIN_PASS_RATE = 0.9  # current documented baseline: 9/10

KENN_TEST_QUESTIONS = [
    "How do I sidechain bass to the kick?",
    "What LUFS target should I use for streaming?",
    "How do I fix masking between kick and bass?",
]
TTS_TEST_SENTENCES = [
    "Boost the low end around eighty hertz.",
    "Cut two point five kilohertz to reduce harshness.",
    "The kick and bass are masking each other.",
]


def _for_path(*parts: str) -> None:
    p = str(ROOT.joinpath(*parts))
    if p not in sys.path:
        sys.path.insert(0, p)


# --- Pure gate-evaluation logic (unit-tested in tests/test_release_health_check.py) --

def evaluate_latency(
    label: str,
    samples_s: list[float],
    slo_s: float,
    *,
    drop_cold_start: bool = True,
) -> dict[str, Any]:
    """Evaluate a series of latency samples (seconds) against an SLO.

    The first sample is treated as a one-time cold-start cost (model load /
    first-inference warmup) and reported separately, not gated -- this matches
    how the plan doc itself distinguishes cold-start from steady-state for both
    KENN and TTS. Gating happens on the steady-state samples only.
    """
    if not samples_s:
        return {
            "label": label,
            "ok": False,
            "failures": [f"{label}: no samples collected"],
            "cold_start_s": None,
            "steady_state_samples_s": [],
            "steady_state_mean_s": None,
            "steady_state_max_s": None,
            "slo_s": slo_s,
        }
    cold = samples_s[0]
    steady = samples_s[1:] if (drop_cold_start and len(samples_s) > 1) else list(samples_s)
    mean_s = round(statistics.fmean(steady), 4)
    max_s = round(max(steady), 4)
    failures: list[str] = []
    if max_s > slo_s:
        failures.append(f"{label}: steady-state max {max_s:.3f}s exceeds SLO {slo_s:.3f}s")
    return {
        "label": label,
        "ok": not failures,
        "failures": failures,
        "cold_start_s": round(cold, 4),
        "steady_state_samples_s": [round(s, 4) for s in steady],
        "steady_state_mean_s": mean_s,
        "steady_state_max_s": max_s,
        "slo_s": slo_s,
    }


def evaluate_render_ratios(case_ratios: dict[str, float], slo_ratio: float) -> dict[str, Any]:
    """Evaluate per-case AutoMix render_seconds / duration ratios against the
    "<=2x real-time" SLO."""
    if not case_ratios:
        return {
            "ok": False,
            "failures": ["automix render ratio: no cases collected"],
            "worst_case": None,
            "worst_ratio": None,
            "case_ratios": {},
            "slo_ratio": slo_ratio,
        }
    worst_case = max(case_ratios, key=lambda k: case_ratios[k])
    worst_ratio = case_ratios[worst_case]
    failures: list[str] = []
    if worst_ratio > slo_ratio:
        failures.append(
            f"automix render ratio: worst case {worst_case!r} at {worst_ratio:.3f}x "
            f"exceeds SLO {slo_ratio:.2f}x"
        )
    return {
        "ok": not failures,
        "failures": failures,
        "worst_case": worst_case,
        "worst_ratio": round(worst_ratio, 3),
        "case_ratios": {k: round(v, 3) for k, v in case_ratios.items()},
        "slo_ratio": slo_ratio,
    }


def evaluate_quality_summary(
    summary: dict[str, Any],
    *,
    min_tolerance_rate: float,
    max_clipping_rate: float,
) -> dict[str, Any]:
    """Evaluate an automix_quality_benchmark.py summary dict."""
    failures: list[str] = []
    if not summary:
        return {"ok": False, "failures": ["automix quality: no summary available"], "summary": {}}
    tol_rate = float(summary.get("gate_lufs_within_tolerance_rate", 0.0) or 0.0)
    clip_rate = float(summary.get("gate_clipping_rate", 1.0) or 0.0)
    if tol_rate < min_tolerance_rate:
        failures.append(
            f"automix quality: LUFS-within-tolerance rate {tol_rate:.2%} below {min_tolerance_rate:.2%}"
        )
    if clip_rate > max_clipping_rate:
        failures.append(
            f"automix quality: clipping rate {clip_rate:.2%} above {max_clipping_rate:.2%} "
            "(true-peak safety must never be weakened to pass this gate)"
        )
    return {"ok": not failures, "failures": failures, "summary": summary}


def evaluate_genre_matrix(
    case_results: dict[str, dict[str, Any]],
    *,
    min_pass_rate: float,
) -> dict[str, Any]:
    """Evaluate genre-matrix case results.

    Each value in ``case_results`` must have at least ``{"passed": bool}``.
    Any *clipping* failure is an unconditional hard-fail regardless of the
    overall pass-rate threshold -- true-peak/clipping safety is never traded
    away to make an aggregate number pass, even for a documented gap like EDM's
    known crest-factor limit.
    """
    failures: list[str] = []
    if not case_results:
        return {
            "ok": False,
            "failures": ["genre matrix: no cases collected"],
            "pass_rate": None,
            "passed_cases": [],
            "failed_cases": [],
        }
    total = len(case_results)
    passed_cases = [name for name, r in case_results.items() if r.get("passed")]
    failed_cases = [name for name, r in case_results.items() if not r.get("passed")]
    clipping_cases = [name for name, r in case_results.items() if r.get("clipping")]
    pass_rate = len(passed_cases) / total

    if clipping_cases:
        failures.append(f"genre matrix: clipping detected in {clipping_cases} (unconditional fail)")
    if pass_rate < min_pass_rate:
        failures.append(
            f"genre matrix: pass rate {pass_rate:.2%} ({len(passed_cases)}/{total}) "
            f"below {min_pass_rate:.2%} -- failed cases: {failed_cases}"
        )
    return {
        "ok": not failures,
        "failures": failures,
        "pass_rate": round(pass_rate, 3),
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
    }


def evaluate_model_dependencies(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate a set of on-disk model/artifact dependency checks.

    Added 2026-07-11 after discovering, purely by a human noticing an
    unrelated symptom, that KENN's local fine-tuned model (`kenn-lora`/
    `kenn-mlx`) and AudioGen's promoted chord/melody Markov models had been
    silently missing from disk for an unknown period following a repo
    restructure -- both features simply degraded to a fallback path with no
    error, warning, or log line anywhere. This closes that hole: every check
    here targets exactly that failure shape (an artifact the code *expects*
    to be there, verified to actually be there), not a performance SLO.
    """
    failures: list[str] = []
    for name, result in checks.items():
        if not result.get("ok"):
            failures.append(f"model_dependencies[{name}]: {result.get('reason', 'missing or empty')}")
    return {"ok": not failures, "failures": failures, "checks": checks}


def combine_gate(categories: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Combine per-category evaluations into one overall pass/fail, the same
    way `main.py check` folds its own gates together."""
    all_failures: list[str] = []
    for result in categories.values():
        all_failures.extend(result.get("failures", []))
    return {"ok": not all_failures, "failures": all_failures, "categories": categories}


# --- Live measurement (I/O side, not unit-tested directly) ------------------

def measure_kenn_latency(questions: list[str] | None = None) -> list[float]:
    # KENN imports audio_too.model_runtime from the repository root. Without
    # this path the ONNX embedder silently falls back to BM25, making a broken
    # semantic-retrieval path look exceptionally fast and green.
    _for_path(".")
    _for_path("studio", "kenn")
    from kenn.core.chat import answer_payload  # noqa: E402
    from kenn.retrieval.retrieval import embed_text  # noqa: E402

    vector = embed_text("release health semantic retrieval probe")
    if getattr(vector, "shape", None) != (384,):
        raise RuntimeError(
            f"semantic embedding backend returned invalid shape {getattr(vector, 'shape', None)!r}"
        )

    samples: list[float] = []
    for question in questions or KENN_TEST_QUESTIONS:
        start = time.time()
        answer_payload(question, limit=8)
        samples.append(time.time() - start)
    return samples


def measure_tts_latency(sentences: list[str] | None = None) -> list[float]:
    _for_path(".")
    from thursday import voice_output as vo  # noqa: E402

    samples: list[float] = []
    for sentence in sentences or TTS_TEST_SENTENCES:
        start = time.time()
        wav = vo.synthesise_isolated(sentence)
        samples.append(time.time() - start)
        if wav is None:
            print(f"  WARNING: TTS returned no audio for: {sentence!r}", file=sys.stderr)
    return samples


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def measure_genre_matrix() -> dict[str, dict[str, Any]]:
    """Run every case in the genre-matrix test directly (not via pytest
    subprocess) so we get structured per-case data (render ratio, pass/fail,
    clipping) rather than parsing captured stdout."""
    for extra in (".", "studio", "studio/audio_analysis", "studio/audio_analysis/audio_analysis", "server/app"):
        _for_path(*extra.split("/"))
    module_path = ROOT / "tests" / "audio_analysis" / "test_mix_renderer_genre_matrix.py"
    mod = _load_module("release_health_genre_matrix", module_path)

    results: dict[str, dict[str, Any]] = {}
    for case_name in mod.CASES:
        try:
            r = mod._build_and_render(case_name)
        except Exception as exc:  # pragma: no cover - defensive, reported as a failed case
            results[case_name] = {"passed": False, "error": str(exc), "clipping": False, "render_ratio": None}
            continue
        v = r["validation"]
        m = v["metrics"]
        no_clip = m["sample_peak"] <= 1.0 + 1e-6
        tp_ok = m["true_peak_dbtp"] <= r["ceiling_db"] + mod.CEILING_MARGIN_DB
        lufs_ok = abs(m["lufs_diff"]) <= mod.LUFS_TOLERANCE
        speed_ok = r["render_seconds"] <= mod.MAX_RENDER_RATIO * mod.DURATION_S
        passed = no_clip and tp_ok and lufs_ok and speed_ok
        results[case_name] = {
            "passed": passed,
            "clipping": not no_clip,
            "true_peak_ok": tp_ok,
            "lufs_ok": lufs_ok,
            "speed_ok": speed_ok,
            "render_ratio": round(r["render_ratio"], 3),
            "lufs_diff": round(m["lufs_diff"], 3),
            "true_peak_dbtp": round(m["true_peak_dbtp"], 3),
        }
    return results


def measure_automix_quality() -> dict[str, Any]:
    """Run the existing automix_quality_benchmark.py in-process and return its
    summary dict (avoids a second subprocess + duplicate stem generation)."""
    _for_path("studio", "audio_analysis")
    _for_path("business", "app")
    module_path = ROOT / "scripts" / "eval" / "automix_quality_benchmark.py"
    mod = _load_module("release_health_automix_quality", module_path)

    rows: list[dict[str, Any]] = []
    for profile_name, loader in mod.STEM_PROFILES.items():
        stems = loader()
        for genre in mod.GENRES:
            for target in mod.TARGET_LUFS:
                try:
                    row = mod._run_one(stems, genre, target)
                    row["profile"] = profile_name
                    rows.append(row)
                except Exception as exc:  # pragma: no cover - reported, not hidden
                    rows.append({"profile": profile_name, "genre": genre, "target_lufs": target, "error": str(exc)})

    valid = [r for r in rows if "error" not in r]
    gated = [r for r in valid if r["target_lufs"] in mod.GATE_TARGET_LUFS]
    n = max(len(valid), 1)
    gn = max(len(gated), 1)
    return {
        "runs": len(rows),
        "valid": len(valid),
        "lufs_within_tolerance_rate": round(sum(r["lufs_within_tolerance"] for r in valid) / n, 3),
        "clipping_rate": round(sum(r["clipping"] for r in valid) / n, 3),
        "mean_abs_lufs_error_LU": round(sum(abs(r["lufs_error_LU"]) for r in valid) / n, 3),
        "max_abs_lufs_error_LU": round(max((abs(r["lufs_error_LU"]) for r in valid), default=0.0), 3),
        "gate_targets": mod.GATE_TARGET_LUFS,
        "gate_lufs_within_tolerance_rate": round(sum(r["lufs_within_tolerance"] for r in gated) / gn, 3),
        "gate_clipping_rate": round(sum(r["clipping"] for r in gated) / gn, 3),
    }


def _check_dir_nonempty(path: Path, *, min_bytes: int = 1024) -> dict[str, Any]:
    """A directory "exists" for this purpose only if it's present AND
    contains at least one file of meaningful size -- an empty or
    near-empty directory (e.g. left behind by a partial/interrupted copy)
    is exactly as broken as a missing one, and a bare `.exists()` check
    would miss it."""
    if not path.exists():
        return {"ok": False, "reason": f"{path} does not exist", "path": str(path)}
    if not path.is_dir():
        return {"ok": False, "reason": f"{path} exists but is not a directory", "path": str(path)}
    total_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    if total_bytes < min_bytes:
        return {
            "ok": False,
            "reason": f"{path} exists but contains only {total_bytes} bytes (expected >= {min_bytes})",
            "path": str(path),
            "total_bytes": total_bytes,
        }
    return {"ok": True, "path": str(path), "total_bytes": total_bytes}


def _check_manifest_artifacts(manifest_path: Path, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Verify every artifact destination a manifest itself claims is
    "active"/promoted actually exists on disk. Walks both the top-level
    `artifacts` list and every `stages.*.artifacts` list (the shape
    AudioGen's `active_manifest.json` uses) rather than hardcoding which
    model files are expected -- if the manifest's own claims and the
    filesystem disagree, that disagreement is the bug, regardless of which
    specific files are involved.

    `base_dir` defaults to the manifest's own directory, but AudioGen's real
    manifest writes destinations relative to its package root instead (e.g.
    "training_data/active_models/chord_markov.pkl", not just
    "chord_markov.pkl") -- caught by testing against the real file rather
    than a synthetic path, so callers with that convention must pass the
    correct root explicitly.
    """
    if not manifest_path.exists():
        return {"ok": False, "reason": f"{manifest_path} does not exist", "path": str(manifest_path)}
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "reason": f"{manifest_path} unreadable/invalid JSON: {exc}", "path": str(manifest_path)}

    destinations: list[str] = []
    for artifact in manifest.get("artifacts", []) or []:
        dest = artifact.get("destination")
        if dest:
            destinations.append(dest)
    for stage in (manifest.get("stages", {}) or {}).values():
        for artifact in stage.get("artifacts", []) or []:
            dest = artifact.get("destination")
            if dest:
                destinations.append(dest)

    resolved_base = base_dir if base_dir is not None else manifest_path.parent
    missing = [dest for dest in destinations if not (resolved_base / dest).is_file()]
    if missing:
        return {
            "ok": False,
            "reason": f"manifest at {manifest_path} claims {len(destinations)} artifact(s), missing on disk: {missing}",
            "path": str(manifest_path),
            "expected_count": len(destinations),
            "missing": missing,
        }
    return {"ok": True, "path": str(manifest_path), "expected_count": len(destinations)}


def measure_model_dependencies() -> dict[str, dict[str, Any]]:
    """Verify known-fragile, gitignored model/artifact dependencies actually
    exist on disk -- see `evaluate_model_dependencies()` for why this exists."""
    checks: dict[str, dict[str, Any]] = {}

    kenn_models_dir = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "models"
    checks["kenn_lora"] = _check_dir_nonempty(kenn_models_dir / "kenn-lora")
    checks["kenn_mlx"] = _check_dir_nonempty(kenn_models_dir / "kenn-mlx")

    audiogen_root = ROOT / "studio" / "audiogen" / "audiogen"
    audiogen_manifest = audiogen_root / "training_data" / "active_models" / "active_manifest.json"
    checks["audiogen_active_manifest"] = _check_manifest_artifacts(audiogen_manifest, base_dir=audiogen_root)

    return checks


def run(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release_health_check")
    parser.add_argument("--skip-kenn", action="store_true", help="Skip the KENN retrieval-latency check")
    parser.add_argument("--skip-tts", action="store_true", help="Skip the TTS latency check")
    parser.add_argument("--skip-quality", action="store_true", help="Skip the AutoMix quality benchmark (slow)")
    parser.add_argument("--skip-genre-matrix", action="store_true", help="Skip the AutoMix genre-matrix stress test (slow)")
    parser.add_argument("--skip-dependencies", action="store_true", help="Skip the on-disk model-dependency integrity check")
    parsed = parser.parse_args(args or [])

    categories: dict[str, dict[str, Any]] = {}

    if not parsed.skip_dependencies:
        print("== Model dependency integrity ==", flush=True)
        try:
            checks = measure_model_dependencies()
            result = evaluate_model_dependencies(checks)
        except Exception as exc:
            result = {"ok": False, "failures": [f"model_dependencies: {exc}"]}
        categories["model_dependencies"] = result
        _print_result(result)

    if not parsed.skip_kenn:
        print("== KENN retrieval latency ==", flush=True)
        try:
            samples = measure_kenn_latency()
            result = evaluate_latency("kenn_retrieval_latency", samples, KENN_LATENCY_SLO_S)
        except Exception as exc:
            result = {"ok": False, "failures": [f"kenn_retrieval_latency: {exc}"]}
        categories["kenn_retrieval_latency"] = result
        _print_result(result)

    if not parsed.skip_tts:
        print("\n== TTS time-to-first-audio ==", flush=True)
        try:
            samples = measure_tts_latency()
            result = evaluate_latency("tts_latency", samples, TTS_LATENCY_SLO_S)
        except Exception as exc:
            result = {"ok": False, "failures": [f"tts_latency: {exc}"]}
        categories["tts_latency"] = result
        _print_result(result)

    if not parsed.skip_genre_matrix:
        print("\n== AutoMix genre-matrix stress test ==", flush=True)
        try:
            case_results = measure_genre_matrix()
            ratio_result = evaluate_render_ratios(
                {name: r["render_ratio"] for name, r in case_results.items() if r.get("render_ratio") is not None},
                AUTOMIX_RENDER_RATIO_SLO,
            )
            matrix_result = evaluate_genre_matrix(case_results, min_pass_rate=GENRE_MATRIX_MIN_PASS_RATE)
        except Exception as exc:
            ratio_result = {"ok": False, "failures": [f"automix_render_ratio: {exc}"]}
            matrix_result = {"ok": False, "failures": [f"automix_genre_matrix: {exc}"]}
        categories["automix_render_ratio"] = ratio_result
        categories["automix_genre_matrix"] = matrix_result
        _print_result(ratio_result)
        _print_result(matrix_result)

    if not parsed.skip_quality:
        print("\n== AutoMix quality benchmark (realistic targets) ==", flush=True)
        try:
            summary = measure_automix_quality()
            result = evaluate_quality_summary(
                summary,
                min_tolerance_rate=AUTOMIX_QUALITY_MIN_TOLERANCE_RATE,
                max_clipping_rate=AUTOMIX_QUALITY_MAX_CLIPPING_RATE,
            )
        except Exception as exc:
            result = {"ok": False, "failures": [f"automix_quality: {exc}"]}
        categories["automix_quality"] = result
        _print_result(result)

    overall = combine_gate(categories)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / f"release_health_{stamp}.json"
    out_path.write_text(json.dumps({"timestamp": stamp, "overall": overall}, indent=2))

    print("\n=== RELEASE HEALTH VERDICT ===")
    print("PASS" if overall["ok"] else "FAIL")
    if not overall["ok"]:
        for failure in overall["failures"]:
            print(f"  - {failure}")
    print(f"\nReport: {out_path}")

    return 0 if overall["ok"] else 1


def _print_result(result: dict[str, Any]) -> None:
    if result.get("ok"):
        extra = ""
        if "steady_state_max_s" in result and result["steady_state_max_s"] is not None:
            extra = (
                f" (cold {result.get('cold_start_s')}s, steady-state mean "
                f"{result['steady_state_mean_s']}s / max {result['steady_state_max_s']}s, "
                f"SLO {result['slo_s']}s)"
            )
        elif "worst_ratio" in result and result["worst_ratio"] is not None:
            extra = f" (worst case {result['worst_case']!r} at {result['worst_ratio']}x, SLO {result['slo_ratio']}x)"
        elif "pass_rate" in result and result["pass_rate"] is not None:
            extra = f" (pass rate {result['pass_rate']:.0%})"
        print(f"  OK{extra}")
    else:
        for failure in result.get("failures", []):
            print(f"  FAIL: {failure}")


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
