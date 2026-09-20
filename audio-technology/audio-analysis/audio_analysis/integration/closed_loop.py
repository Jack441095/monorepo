from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


def closed_loop_action_plan(report: dict) -> dict:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    actions = report.get("action_plan") if isinstance(report.get("action_plan"), list) else []
    repairs = report.get("ableton_repair_templates") if isinstance(report.get("ableton_repair_templates"), list) else []
    sections = metrics.get("section_analysis") if isinstance(metrics.get("section_analysis"), dict) else {}
    highlights = sections.get("highlights") if isinstance(sections.get("highlights"), dict) else {}
    chords = metrics.get("chords") if isinstance(metrics.get("chords"), dict) else {}
    steps = []
    for index, action in enumerate(actions[:5], start=1):
        if not isinstance(action, dict):
            continue
        related_repair = next(
            (repair for repair in repairs if str(repair.get("flag", "")).lower() in str(action.get("focus", "")).lower()),
            repairs[index - 1] if index - 1 < len(repairs) else {},
        )
        steps.append(
            {
                "rank": index,
                "decision": action.get("decision", "check_by_ear"),
                "focus": action.get("focus", action.get("title", "Mix decision")),
                "action": action.get("action", ""),
                "reason": action.get("reason", ""),
                "confidence": action.get("confidence", ""),
                "ableton_move": related_repair.get("move", ""),
                "device_chain": related_repair.get("device_chain", ""),
                "target": related_repair.get("target", ""),
                "check": related_repair.get("check", "Re-export and compare against this analysis."),
            }
        )
    if not steps:
        steps.append(
            {
                "rank": 1,
                "decision": "check_by_ear",
                "focus": "Reference pass",
                "action": "Level-match against a reference and make one intentional change.",
                "reason": f"Technical score is {metrics.get('technical_score', 'n/a')}/100.",
                "confidence": "medium",
                "ableton_move": "",
                "device_chain": "Utility and Spectrum",
                "target": "Preserve the current strengths while checking translation.",
                "check": "Re-upload the revision and compare flags.",
            }
        )
    loudest = highlights.get("loudest_section") if isinstance(highlights.get("loudest_section"), dict) else {}
    harmonic_notes = chords.get("analysis_notes") if isinstance(chords.get("analysis_notes"), list) else []
    return {
        "schema": "audio_too.closed_loop_action_plan.v1",
        "summary": "Make one ranked change, export a revision, then compare the result against this report.",
        "primary_focus": steps[0]["focus"],
        "steps": steps,
        "section_context": {
            "loudest_section": loudest.get("label", ""),
            "loudest_rms_dbfs": loudest.get("rms_dbfs"),
        },
        "harmonic_context": {
            "estimated_key": chords.get("estimated_key", "Unknown"),
            "key_confidence": chords.get("key_confidence", ""),
            "notes": harmonic_notes,
        },
        "revision_checklist": [
            "Save a new version label before making changes.",
            "Apply only the first one or two ranked moves.",
            "Level-match the revised export before judging tone.",
            "Re-upload the revision and compare score, flags, section highlights, and reference deltas.",
        ],
    }


def ableton_repair_chain_export(report: dict) -> dict:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    repairs = report.get("ableton_repair_templates") if isinstance(report.get("ableton_repair_templates"), list) else []
    chains = []
    for index, repair in enumerate(repairs, start=1):
        if not isinstance(repair, dict):
            continue
        chains.append(
            {
                "chain_id": f"repair-{index}",
                "name": repair.get("flag", f"Repair {index}"),
                "severity": repair.get("severity", ""),
                "devices": str(repair.get("device_chain", "")).split(", "),
                "move": repair.get("move", ""),
                "target": repair.get("target", ""),
                "verification": repair.get("check", ""),
                "automation_hint": automation_hint_for_repair(repair, metrics),
            }
        )
    return {
        "schema": "audio_too.ableton_repair_chains.v1",
        "filename": metrics.get("filename", ""),
        "technical_score": metrics.get("technical_score"),
        "chains": chains,
        "export_note": "Use these as Ableton repair instructions; apply manually, then re-upload the revised WAV.",
    }


def automation_hint_for_repair(repair: dict, metrics: dict) -> str:
    label = str(repair.get("flag", "")).lower()
    sections = metrics.get("section_analysis") if isinstance(metrics.get("section_analysis"), dict) else {}
    highlights = sections.get("highlights") if isinstance(sections.get("highlights"), dict) else {}
    loudest = highlights.get("loudest_section") if isinstance(highlights.get("loudest_section"), dict) else {}
    section_label = loudest.get("label", "the loudest section")
    if "uneven" in label or "spiky" in label or "dynamics" in label:
        return f"Check clip gain or Utility automation around {section_label} first."
    if "harsh" in label or "bright" in label or "presence" in label:
        return f"Loop {section_label} and automate the offending source before changing the master."
    if "stereo" in label or "mono" in label or "phase" in label:
        return "Automate width only where the arrangement needs it; keep kick, bass, vocal, and snare stable."
    return "Apply statically first, then automate only if one section needs a different amount."


def batch_qa_summary(scan_payload: dict) -> dict:
    items = scan_payload.get("items") if isinstance(scan_payload.get("items"), list) else []
    ranked = []
    issue_counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        flags = item.get("flags") if isinstance(item.get("flags"), list) else []
        score = metrics.get("technical_score")
        risk = qa_risk_level(score, flags, item.get("ok") is False)
        for flag in flags:
            label = str(flag.get("label", "")).strip()
            if label:
                issue_counts[label] = issue_counts.get(label, 0) + 1
        ranked.append(
            {
                "filename": item.get("filename", ""),
                "relative_path": item.get("relative_path", ""),
                "ok": item.get("ok"),
                "risk": risk,
                "technical_score": score,
                "flag_count": len(flags),
                "top_flags": [flag.get("label", "") for flag in flags[:3] if isinstance(flag, dict)],
                "summary": item.get("summary", ""),
                "error": item.get("error", ""),
            }
        )
    risk_order = {"failed": 0, "high": 1, "medium": 2, "low": 3}
    ranked.sort(key=lambda row: (risk_order.get(str(row["risk"]), 4), row["technical_score"] if row["technical_score"] is not None else 999))
    return {
        "schema": "audio_too.batch_qa_summary.v1",
        "root": scan_payload.get("root", ""),
        "totals": {
            "found": len(ranked),
            "failed": sum(1 for row in ranked if row["risk"] == "failed"),
            "high_risk": sum(1 for row in ranked if row["risk"] == "high"),
            "medium_risk": sum(1 for row in ranked if row["risk"] == "medium"),
            "low_risk": sum(1 for row in ranked if row["risk"] == "low"),
        },
        "issue_counts": dict(sorted(issue_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
        "ranked_items": ranked,
    }


def qa_risk_level(score: object, flags: list, failed: bool) -> str:
    if failed:
        return "failed"
    high_flags = sum(1 for flag in flags if isinstance(flag, dict) and str(flag.get("severity")) == "high")
    medium_flags = sum(1 for flag in flags if isinstance(flag, dict) and str(flag.get("severity")) == "medium")
    numeric_score = float(score) if isinstance(score, (int, float)) else 100.0
    if high_flags or numeric_score < 60:
        return "high"
    if medium_flags or numeric_score < 78:
        return "medium"
    return "low"


def feedback_record(report: dict, decision: str, note: str = "") -> dict:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    closed_loop = report.get("closed_loop_action_plan") if isinstance(report.get("closed_loop_action_plan"), dict) else {}
    return {
        "schema": "audio_too.analysis_feedback.v1",
        "id": str(uuid4()),
        "decision": str(decision or "").strip()[:40] or "unreviewed",
        "note": str(note or "").strip()[:500],
        "filename": metrics.get("filename", ""),
        "technical_score": metrics.get("technical_score"),
        "technical_rating": metrics.get("technical_rating", ""),
        "primary_focus": closed_loop.get("primary_focus", ""),
        "flags": [flag.get("label", "") for flag in report.get("flags", [])[:8] if isinstance(flag, dict)],
        "actions": [
            {
                "focus": action.get("focus", ""),
                "action": action.get("action", ""),
                "confidence": action.get("confidence", ""),
            }
            for action in report.get("action_plan", [])[:5]
            if isinstance(action, dict)
        ],
    }


def append_feedback_record(path: Path, report: dict, decision: str, note: str = "") -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = feedback_record(report, decision, note)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return {"ok": True, "path": str(path), "record": record}
