from __future__ import annotations

from dataclasses import dataclass
import time
from pathlib import Path

from audio_analysis.utils.media_safety import validate_media_upload
from typing import Callable

from stem_uploads import sanitize_filename


@dataclass(frozen=True)
class ScanContext:
    discover_paths: Callable
    decode_audio_file: Callable
    analyze_wav: Callable
    compare_metrics: Callable
    comparison_advice: Callable
    reference_coaching: Callable
    report_summary: Callable
    priority_actions: Callable
    revision_lesson: Callable
    refresh_report_interpretation: Callable
    refresh_closed_loop_payloads: Callable
    kenn_handoff: Callable
    mix_goal_info: Callable


def validate_audio_upload(
    file_bytes: bytes,
    filename: str,
    *,
    label: str,
    max_upload_bytes: int,
    audio_suffixes: set[str],
) -> dict:
    if not file_bytes:
        return {"ok": False, "error": f"{label} is empty."}
    if len(file_bytes) > max_upload_bytes:
        return {"ok": False, "error": f"File exceeds {max_upload_bytes // (1024 * 1024)} MB limit."}
    safe_name = sanitize_filename(filename)
    if Path(safe_name).suffix.lower() not in audio_suffixes:
        return {"ok": False, "error": f"{label} must be a supported audio file: {', '.join(sorted(audio_suffixes))}."}
    try:
        validate_media_upload(file_bytes, safe_name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "safe_name": safe_name}


def discover_audio_paths(root: Path, *, recursive: bool = True, audio_suffixes: set[str]) -> list[Path]:
    root = Path(root)
    if root.is_file():
        return [root] if root.suffix.lower() in audio_suffixes else []
    if not root.exists():
        return []
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(path for path in iterator if path.is_file() and path.suffix.lower() in audio_suffixes)


def scan_audio_files(
    root: Path,
    *,
    recursive: bool,
    mix_goal: str,
    reference_path: Path | None,
    context: ScanContext,
) -> dict:
    started = time.perf_counter()
    root = Path(root)
    items = []
    analyzed = failed = skipped = 0
    reference_payload = None
    reference_metrics = None
    if reference_path:
        reference_path = Path(reference_path)
        reference_decoded = context.decode_audio_file(reference_path)
        reference_report = context.analyze_wav(reference_decoded["wav_bytes"], reference_path.name, mix_goal=mix_goal)
        reference_metrics = reference_report.get("metrics") or {}
        reference_metrics["source_format"] = reference_decoded.get("source_format", reference_metrics.get("source_format"))
        reference_metrics["decoder"] = reference_decoded.get("decoder", reference_metrics.get("decoder"))
        reference_payload = {
            "path": str(reference_path),
            "filename": reference_path.name,
            "metrics": reference_metrics,
            "summary": reference_report.get("summary", ""),
        }
    for path in context.discover_paths(root, recursive=recursive):
        relative_path = str(path.relative_to(root)) if root.is_dir() else path.name
        suffix = path.suffix.lower()
        item = {
            "path": str(path),
            "relative_path": relative_path,
            "filename": path.name,
            "suffix": suffix,
            "size_bytes": path.stat().st_size,
        }
        file_started = time.perf_counter()
        try:
            decoded = context.decode_audio_file(path)
            report = context.analyze_wav(decoded["wav_bytes"], path.name, mix_goal=mix_goal)
            elapsed = time.perf_counter() - file_started
            metrics = report.get("metrics", {})
            duration = float(metrics.get("duration_seconds") or 0)
            metrics["source_format"] = decoded.get("source_format", metrics.get("source_format"))
            metrics["decoder"] = decoded.get("decoder", metrics.get("decoder"))
            if reference_metrics and reference_payload and path.resolve() != Path(reference_payload["path"]).resolve():
                comparison = context.compare_metrics(metrics, reference_metrics)
                report["reference"] = {
                    "filename": reference_payload["filename"],
                    "path": reference_payload["path"],
                    "metrics": reference_metrics,
                }
                report["comparison"] = comparison
                report["comparison_advice"] = context.comparison_advice(comparison)
                report["reference_coaching"] = context.reference_coaching(comparison, metrics, report["reference"])
                report["summary"] = context.report_summary(metrics, report.get("flags", []), comparison)
                report["action_plan"] = context.priority_actions(metrics, report.get("flags", []), comparison)
                report["revision_lesson"] = context.revision_lesson(report)
                context.refresh_report_interpretation(report)
                context.refresh_closed_loop_payloads(report)
            item.update(
                {
                    "ok": True,
                    "status": "analyzed",
                    "elapsed_seconds": round(elapsed, 3),
                    "analysis_speed_x": round(duration / elapsed, 2) if elapsed else None,
                    "summary": report.get("summary", ""),
                    "metrics": metrics,
                    "technical_metrics": report.get("technical_metrics", {}),
                    "judgment": report.get("judgment", {}),
                    "flags": report.get("flags", []),
                    "action_plan": report.get("action_plan", []),
                    "closed_loop_action_plan": report.get("closed_loop_action_plan", {}),
                    "ableton_repair_chains": report.get("ableton_repair_chains", {}),
                    "comparison": report.get("comparison"),
                    "comparison_advice": report.get("comparison_advice", []),
                    "reference_coaching": report.get("reference_coaching"),
                    "kenn_handoff": context.kenn_handoff(report),
                }
            )
            analyzed += 1
        except Exception as exc:
            item.update(
                {
                    "ok": False,
                    "status": "failed",
                    "elapsed_seconds": round(time.perf_counter() - file_started, 3),
                    "error": str(exc),
                }
            )
            failed += 1
        items.append(item)
    elapsed_total = time.perf_counter() - started
    return {
        "ok": failed == 0,
        "root": str(root),
        "recursive": recursive,
        "mix_goal": context.mix_goal_info(mix_goal),
        "reference": reference_payload,
        "summary": {
            "found": len(items),
            "analyzed": analyzed,
            "failed": failed,
            "skipped": skipped,
            "elapsed_seconds": round(elapsed_total, 3),
        },
        "items": items,
    }


def scan_audio_benchmark(payload: dict, *, metric_float: Callable, percentile: Callable) -> dict:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    analyzed_items = [item for item in items if isinstance(item, dict) and item.get("ok")]
    failed_items = [item for item in items if isinstance(item, dict) and item.get("ok") is False]
    elapsed_values = [metric_float(item.get("elapsed_seconds")) for item in analyzed_items]
    durations = [
        metric_float((item.get("metrics") if isinstance(item.get("metrics"), dict) else {}).get("duration_seconds"))
        for item in analyzed_items
    ]
    total_elapsed = metric_float((payload.get("summary") or {}).get("elapsed_seconds"))
    total_audio_seconds = round(sum(durations), 3)
    file_count = len(items)
    analyzed_count = len(analyzed_items)
    slowest = sorted(
        (
            {
                "filename": str(item.get("filename") or item.get("relative_path") or ""),
                "elapsed_seconds": metric_float(item.get("elapsed_seconds")),
                "duration_seconds": metric_float((item.get("metrics") or {}).get("duration_seconds")),
                "analysis_speed_x": item.get("analysis_speed_x"),
            }
            for item in analyzed_items
        ),
        key=lambda item: item["elapsed_seconds"],
        reverse=True,
    )[:5]
    return {
        "files_found": file_count,
        "files_analyzed": analyzed_count,
        "files_failed": len(failed_items),
        "total_elapsed_seconds": round(total_elapsed, 3),
        "total_audio_seconds": total_audio_seconds,
        "audio_speed_x": round(total_audio_seconds / total_elapsed, 2) if total_elapsed else None,
        "files_per_second": round(analyzed_count / total_elapsed, 3) if total_elapsed else None,
        "average_file_seconds": round(sum(elapsed_values) / analyzed_count, 3) if analyzed_count else 0.0,
        "p50_file_seconds": round(percentile(elapsed_values, 0.50), 3) if elapsed_values else 0.0,
        "p95_file_seconds": round(percentile(elapsed_values, 0.95), 3) if elapsed_values else 0.0,
        "slowest_files": slowest,
    }
