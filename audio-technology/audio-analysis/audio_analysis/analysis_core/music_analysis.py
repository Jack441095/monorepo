from __future__ import annotations

import csv
import io


def music_analysis_from_report(report: dict) -> dict:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    chords = metrics.get("chords") if isinstance(metrics.get("chords"), dict) else {}
    sections = metrics.get("section_analysis") if isinstance(metrics.get("section_analysis"), dict) else {}
    progression = chords.get("progression") if isinstance(chords.get("progression"), list) else []
    intervals = chords.get("intervals") if isinstance(chords.get("intervals"), list) else []
    notes = chords.get("analysis_notes") if isinstance(chords.get("analysis_notes"), list) else []
    named_progression = [str(seg.get("chord", "")) for seg in progression if isinstance(seg, dict) and seg.get("chord") != "N.C."]
    return {
        "filename": metrics.get("filename", ""),
        "source_format": metrics.get("source_format", ""),
        "decoder": metrics.get("decoder", ""),
        "duration_seconds": metrics.get("duration_seconds"),
        "sample_rate": metrics.get("sample_rate"),
        "channels": metrics.get("channels"),
        "estimated_key": chords.get("estimated_key", "Unknown"),
        "key_confidence": chords.get("key_confidence", "low"),
        "key_confidence_score": chords.get("key_confidence_score", 0.0),
        "key_confidence_explanation": chords.get("key_confidence_explanation", ""),
        "progression_summary": " | ".join(named_progression),
        "progression_confidence_summary": chords.get("progression_confidence_summary", ""),
        "analysis_notes": notes,
        "analysis_notes_summary": " | ".join(str(note) for note in notes),
        "sanity": chords.get("sanity", {}),
        "progression": progression,
        "intervals": intervals,
        "section_highlights": sections.get("highlights", {}),
        "technical_context": {
            "technical_score": metrics.get("technical_score"),
            "technical_rating": metrics.get("technical_rating", ""),
            "integrated_lufs": metrics.get("integrated_lufs"),
            "crest_factor_db": metrics.get("crest_factor_db"),
            "stereo_correlation": metrics.get("stereo_correlation"),
            "dominant_band": (metrics.get("perceptual_summary") or {}).get("dominant_band", ""),
        },
    }


def music_analysis_from_scan_item(item: dict) -> dict:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    report = {
        "metrics": metrics,
    }
    analysis = music_analysis_from_report(report)
    analysis.update(
        {
            "path": item.get("path", ""),
            "relative_path": item.get("relative_path", ""),
            "filename": item.get("filename") or analysis.get("filename", ""),
            "ok": bool(item.get("ok")),
            "status": item.get("status", ""),
            "error": item.get("error", ""),
            "analysis_elapsed_seconds": item.get("elapsed_seconds"),
            "analysis_speed_x": item.get("analysis_speed_x"),
        }
    )
    return analysis


def batch_music_analysis(scan_payload: dict) -> dict:
    items = scan_payload.get("items") if isinstance(scan_payload.get("items"), list) else []
    analyses = [music_analysis_from_scan_item(item) for item in items if isinstance(item, dict)]
    ok_items = [item for item in analyses if item.get("ok")]
    keys: dict[str, int] = {}
    for item in ok_items:
        key = str(item.get("estimated_key") or "Unknown")
        keys[key] = keys.get(key, 0) + 1
    return {
        "ok": scan_payload.get("ok", False),
        "root": scan_payload.get("root", ""),
        "benchmark": scan_payload.get("benchmark", {}),
        "qa": scan_payload.get("qa", {}),
        "summary": {
            "found": len(analyses),
            "analyzed": len(ok_items),
            "failed": len(analyses) - len(ok_items),
            "keys": keys,
        },
        "items": analyses,
    }


def batch_music_analysis_csv(batch_payload: dict) -> str:
    out = io.StringIO()
    fieldnames = [
        "filename",
        "relative_path",
        "ok",
        "status",
        "error",
        "duration_seconds",
        "estimated_key",
        "key_confidence",
        "key_confidence_score",
        "key_confidence_explanation",
        "progression_summary",
        "progression_confidence_summary",
        "analysis_notes",
        "technical_score",
        "integrated_lufs",
        "crest_factor_db",
        "stereo_correlation",
        "analysis_elapsed_seconds",
        "analysis_speed_x",
    ]
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for item in batch_payload.get("items", []):
        if not isinstance(item, dict):
            continue
        context = item.get("technical_context") if isinstance(item.get("technical_context"), dict) else {}
        writer.writerow(
            {
                "filename": item.get("filename", ""),
                "relative_path": item.get("relative_path", ""),
                "ok": item.get("ok", ""),
                "status": item.get("status", ""),
                "error": item.get("error", ""),
                "duration_seconds": item.get("duration_seconds", ""),
                "estimated_key": item.get("estimated_key", ""),
                "key_confidence": item.get("key_confidence", ""),
                "key_confidence_score": item.get("key_confidence_score", ""),
                "key_confidence_explanation": item.get("key_confidence_explanation", ""),
                "progression_summary": item.get("progression_summary", ""),
                "progression_confidence_summary": item.get("progression_confidence_summary", ""),
                "analysis_notes": item.get("analysis_notes_summary", ""),
                "technical_score": context.get("technical_score", ""),
                "integrated_lufs": context.get("integrated_lufs", ""),
                "crest_factor_db": context.get("crest_factor_db", ""),
                "stereo_correlation": context.get("stereo_correlation", ""),
                "analysis_elapsed_seconds": item.get("analysis_elapsed_seconds", ""),
                "analysis_speed_x": item.get("analysis_speed_x", ""),
            }
        )
    return out.getvalue()
