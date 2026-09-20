"""Phase 3 handler helpers for Thursday orchestrator.

These handle complex multi-step operations for AudioGen, Mix Review,
Creative Lab, Portfolio, and Dashboard sections.
"""

from __future__ import annotations

import json
import re
from typing import Any


def handle_audiogen_status(api: Any, text: str) -> str:
    """Handle AudioGen status requests.

    Detects sub-intents: queue check, emotion list, history, or general status.
    """
    text_lower = text.lower()

    if "queue" in text_lower or "render queue" in text_lower:
        q = api.audiogen_render_queue()
        running = q.get("running", [])
        queued = q.get("queued", [])
        recent = q.get("recent", [])
        sections = []
        if running:
            sections.append("Running:")
            for j in running:
                sections.append(
                    f"  {j.get('id','?')[:10]} - {j.get('emotion','?')} "
                    f"({j.get('progress',0)}%)"
                )
        if queued:
            sections.append("Queued:")
            for j in queued:
                sections.append(
                    f"  {j.get('id','?')[:10]} - {j.get('emotion','?')}"
                )
        if not running and not queued:
            sections.append("No active renders. Queue is empty.")
        sections.append(f"Recent: {len(recent)} jobs in history")
        return "\n".join(sections)

    if "emotion" in text_lower or "what emotions" in text_lower:
        s = api.audiogen_status()
        emotions = s.get("emotions", [])
        lines = ["Supported AudioGen emotions:"]
        for e in emotions:
            lines.append(f"  - {e}")
        return "\n".join(lines)

    if "history" in text_lower or "render history" in text_lower:
        h = api.audiogen_render_history(limit=15)
        if not h:
            return "No render history yet."
        lines = ["AudioGen Render History:"]
        for entry in h[-15:]:
            lines.append(
                f"  - {entry.get('emotion','?')} ({entry.get('kind','?')}) "
                f"- {entry.get('created_at','?')}"
            )
        return "\n".join(lines)

    s = api.audiogen_status()
    ok = s.get("ok", False)
    lines = [
        "AudioGen System Status",
        f"  Available: {'Yes' if ok else 'No'}",
        f"  Python: {s.get('python', '?')}",
        f"  Has main_llm: {s.get('has_main_llm', False)}",
        f"  Has full_song render: {s.get('has_full_render', False)}",
        f"  Portfolio audio count: {s.get('portfolio_audio_count', 0)}",
        f"  Emotions: {len(s.get('emotions', []))}",
    ]
    q = s.get("render_queue", {})
    lines.append(
        f"  Queue: {len(q.get('running', []))} running, "
        f"{len(q.get('queued', []))} queued"
    )
    lines.append(f"  Render history: {s.get('render_history_count', 0)}")
    return "\n".join(lines)


def handle_audiogen_render(api: Any, text: str, ctx: dict | None = None) -> str:
    """Handle AudioGen full song render requests."""
    text_lower = text.lower()

    emotion = api.audiogen_infer_emotion(text)

    bars = 4
    m = re.search(r"(\d+)\s*(?:bar|measure)", text_lower)
    if m:
        try:
            bars = max(1, min(16, int(m.group(1))))
        except ValueError:
            pass

    k = 1
    m = re.search(r"(\d+)\s*(?:variation|version|variant)", text_lower)
    if m:
        try:
            k = max(1, min(4, int(m.group(1))))
        except ValueError:
            pass

    chain_to_automix = False
    try:
        from app.audiogen_bridge import requests_automix_chain
        chain_to_automix = requests_automix_chain(text)
    except ImportError:
        pass

    chain_project_id = ""
    if chain_to_automix and ctx:
        session_id = ctx.get("_session_id")
        if session_id:
            try:
                from kenn.core.chat_routing import _resolve_or_create_automix_project
                chain_project_id = _resolve_or_create_automix_project(session_id)
            except ImportError:
                pass

    if chain_to_automix:
        result = api.audiogen_render_full_song(
            emotion=emotion,
            bars=bars,
            k=k,
            project_id=chain_project_id,
            chain_to_automix=chain_to_automix,
        )
    else:
        result = api.audiogen_render_full_song(
            emotion=emotion,
            bars=bars,
            k=k,
        )

    if result.get("ok"):
        job = result.get("job", {})
        msg = (
            f"Full song render queued!\n"
            f"  Emotion: {emotion}\n"
            f"  Bars: {bars}\n"
            f"  Variations: {k}\n"
            f"  Job ID: {job.get('id', '')[:12]}\n"
            f"  Status: {job.get('status', 'queued')}"
        )
        if chain_to_automix:
            msg += "\n  AutoMix: Chained (stems will be mixed automatically on completion)"
        return msg
    return "The render could not be queued (error code: service_unavailable)."


def handle_audiogen_job(api: Any, text: str, ctx: dict) -> str:
    """Handle AudioGen job control requests (check, cancel, retry)."""
    text_lower = text.lower()

    job_id = None
    m = re.search(r"([a-f0-9]{8,16})", text_lower)
    if m:
        job_id = m.group(1)

    if not job_id:
        job_id = ctx.get("current_audiogen_job")

    if not job_id:
        return (
            "I need a render job ID. You can also set one by "
            "starting a render first."
        )

    if "cancel" in text_lower or "stop" in text_lower:
        r = api.audiogen_cancel_render(job_id)
        if r.get("ok"):
            job = r.get("job", {})
            return (
                f"Cancelled render {job_id[:12]}. "
                f"Status: {job.get('status', 'cancelled')}"
            )
        return "The render could not be cancelled (error code: service_unavailable)."

    if "retry" in text_lower:
        r = api.audiogen_retry_render(job_id)
        if r.get("ok"):
            job = r.get("job", {})
            return (
                f"Re-queued render {job_id[:12]}. "
                f"New job ID: {job.get('id','?')[:12]}"
            )
        return "The render could not be retried (error code: service_unavailable)."

    r = api.audiogen_render_job_status(job_id)
    if r.get("ok"):
        job = r.get("job", {})
        status = job.get("status", "?")
        emotion = job.get("emotion", "?")
        progress = job.get("progress", 0)
        return (
            f"Render Job: {job_id[:12]}\n"
            f"  Status: {status} ({progress}%)\n"
            f"  Emotion: {emotion}\n"
            f"  Created: {job.get('created_at', '?')}"
        )
    return f"Job not found: {job_id[:12]}"


def handle_mix_review_list(api: Any, text: str) -> str:
    """Handle mix review listing."""
    m = re.search(r"(\d+)", text)
    limit = min(int(m.group(1)), 50) if m else 20

    reviews = api.list_mix_reviews(limit=limit)
    if not reviews:
        return (
            "No mix reviews found. Try scanning some audio files first."
        )

    lines = [f"Mix Reviews (last {len(reviews)}):"]
    for r in reviews:
        rid = str(r.get("review_id") or r.get("id") or "?")[:12]
        title = r.get("title", "Untitled")[:30]
        score = r.get("overall_score", r.get("score", "?"))
        created = str(
            r.get("created_at", r.get("updated_at", "?"))
        )[:10]
        lines.append(
            f"  - {rid} - {title} (score: {score}, {created})"
        )
    return "\n".join(lines)


def handle_mix_review_detail(api: Any, text: str) -> str:
    """Handle fetching a specific mix review."""
    m = re.search(r"([a-f0-9]{8,16})", text)
    if not m:
        return "I need a review ID. Try 'show mix reviews' first."

    review_id = m.group(1)
    review = api.mix_review_by_id(review_id)
    if not review:
        return f"Mix review not found: {review_id[:12]}"

    html = api.mix_review_report_html(review_id)
    if html:
        return f"Mix Review HTML report for {review_id[:12]}:\n{html[:2000]}"

    return (
        f"Mix Review: {review_id[:12]}\n"
        f"  Title: {review.get('title', 'Untitled')}\n"
        f"  Score: {review.get('overall_score', review.get('score', 'N/A'))}\n"
        f"  Created: {str(review.get('created_at', ''))[:10]}\n"
        f"  Status: {review.get('status', 'completed')}"
    )


def handle_mix_review_timeline(api: Any, text: str) -> str:
    """Handle track timeline requests."""
    title = text
    for prefix in [
        "timeline for", "timeline of", "version history of",
        "history for", "track timeline for", "show timeline for",
        "show history of",
    ]:
        if prefix in text.lower():
            title = text.lower().split(prefix, 1)[-1].strip()
            break

    if not title or title in (
        "the track", "my track", "that track", "the mix", "my mix"
    ):
        return "Which track? Try 'show timeline for Track Name'."

    timeline = api.mix_review_track_timeline(title)
    if isinstance(timeline, dict) and timeline.get("ok") is False:
        return "The mix timeline could not be loaded (error code: service_unavailable)."

    versions = timeline.get("versions", timeline.get("items", []))
    if not versions:
        return f"No versions found for track: {title}"

    lines = [f"Version Timeline for '{title}':"]
    for v in versions:
        vid = v.get("version_label") or str(v.get("id") or v.get("review_id") or "?")[:12]
        created = str(v.get("created_at", "?"))[:10]
        lines.append(f"  - {vid} - {created}")
    return "\n".join(lines)


def handle_mix_review_version_diff(
    api: Any, text: str, ctx: dict
) -> str:
    """Handle version comparison requests."""
    ids = re.findall(r"([a-f0-9]{8,16})", text)

    if len(ids) >= 2:
        result = api.mix_review_version_diff(ids[0], ids[1])
    elif len(ids) == 1:
        result = api.mix_review_version_diff(ids[0])
    else:
        return (
            "I need one or two review IDs to compare. "
            "Try 'compare abc123 and def456'."
        )

    if isinstance(result, dict) and result.get("ok") is False:
        return "The mix versions could not be compared (error code: service_unavailable)."

    if isinstance(result, dict):
        lines = ["Version Comparison:"]
        for key, value in result.items():
            if key != "id":
                lines.append(f"  {key}: {str(value)[:80]}")
        return "\n".join(lines)

    return str(result)[:1500]


def handle_mix_review_rack(api: Any, text: str) -> str:
    """Handle correction rack generation."""
    m = re.search(r"([a-f0-9]{8,16})", text)
    if not m:
        return (
            "I need a review ID to generate a correction rack. "
            "Try 'generate correction rack for abc123'."
        )

    review_id = m.group(1)
    rack_data = api.mix_review_generate_correction_rack(review_id)

    if rack_data is None:
        return (
            f"No correction rack data found for review "
            f"{review_id[:12]}."
        )

    if isinstance(rack_data, bytes):
        return (
            f"Ableton correction rack generated for review "
            f"{review_id[:12]} ({len(rack_data)} bytes)"
        )

    return (
        f"Generated correction rack data for review {review_id[:12]}."
    )


def handle_mix_review_references(api: Any, text: str) -> str:
    """Handle reference track listing."""
    refs = api.mix_review_list_references(limit=30)
    if not refs:
        return (
            "No reference tracks saved yet. "
            "Try uploading one via the dashboard."
        )

    lines = ["Reference Tracks:"]
    for r in refs:
        title = r.get("title", r.get("name", "Untitled"))[:40]
        ref_id = r.get("id", "?")[:12]
        lines.append(f"  - {ref_id} - {title}")
    return "\n".join(lines)


def handle_creative_lab(api: Any, text: str) -> str:
    """Handle Creative Lab snapshot requests."""
    text_lower = text.lower()

    if "session" in text_lower and "record" in text_lower:
        return (
            "To record a session event, use the Creative Lab "
            "dashboard or provide session details."
        )

    s = api.creative_lab_snapshot(limit=10)
    sessions = s.get("sessions", [])
    feedback = s.get("feedback", [])

    lines = ["Creative Lab Snapshot:"]
    lines.append(f"  Sessions: {len(sessions)}")
    lines.append(f"  Feedback entries: {len(feedback)}")
    if sessions:
        latest = sessions[-1]
        lines.append(
            f"  Latest session: "
            f"{latest.get('id','?')[:12]} - "
            f"{latest.get('created_at','?')}"
        )
    return "\n".join(lines)


def handle_creative_lab_repairs(api: Any, text: str) -> str:
    """Handle Creative Lab repair requests."""
    text_lower = text.lower()

    if "recommendation" in text_lower or "suggestion" in text_lower:
        recs = api.creative_lab_repair_recommendations(limit=10)
        if not recs:
            return "No pending repair recommendations."
        lines = ["Repair Recommendations:"]
        for r in recs:
            fb_id = r.get("feedback_id", r.get("id", "?"))[:12]
            desc = r.get("description", r.get("note", "No details"))[:60]
            lines.append(f"  - {fb_id} - {desc}")
        return "\n".join(lines)

    if "create" in text_lower or "artifact" in text_lower:
        m = re.search(r"([a-f0-9]{8,16})", text)
        if not m:
            return "I need a feedback ID to create repair artifacts."
        result = api.creative_lab_create_repair_artifacts(m.group(1))
        return (
            json.dumps(result, indent=2)
            if isinstance(result, dict)
            else str(result)
        )

    if "promote" in text_lower:
        m = re.search(r"([a-f0-9]{8,16})", text)
        if not m:
            return "I need a feedback ID to promote."
        is_eval = "eval" in text_lower or "regression" in text_lower
        if is_eval:
            result = api.creative_lab_promote_repair_eval(m.group(1))
        else:
            result = api.creative_lab_promote_repair(m.group(1))
        return (
            json.dumps(result, indent=2)
            if isinstance(result, dict)
            else str(result)
        )

    if "run" in text_lower:
        m = re.search(r"([a-f0-9]{8,16})", text)
        if not m:
            return "I need a feedback ID to run a repair."
        result = api.creative_lab_run_repair_recommendation(m.group(1))
        return (
            json.dumps(result, indent=2)
            if isinstance(result, dict)
            else str(result)
        )

    return (
        "What repair operation? Try 'show repair recommendations', "
        "'promote repair abc123', 'run repair recommendation def456'."
    )


def handle_portfolio(api: Any, text: str) -> str:
    """Handle portfolio requests."""
    text_lower = text.lower()

    if "discover" in text_lower or "new audio" in text_lower or "find" in text_lower:
        files = api.portfolio_discover_audio_files()
        if not files:
            return "No new audio files discovered."
        lines = [f"Discovered {len(files)} new audio files:"]
        for f in files:
            lines.append(f"  - {f.get('filename', f.get('title', '?'))}")
        return "\n".join(lines)

    if "publish" in text_lower or "upload" in text_lower or "add to" in text_lower:
        m = re.search(r"publish\s+([\w\-\.]+\.\w+)", text_lower)
        if m:
            result = api.portfolio_publish_audio(m.group(1))
            if result.get("ok"):
                entry = result.get("entry", {})
                return (
                    f"Published {m.group(1)} to portfolio: "
                    f"{entry.get('title', 'Untitled')}"
                )
            return "Portfolio publishing failed (error code: service_unavailable)."
        return (
            "I need a filename. Try 'publish my_song.wav' "
            "or 'list audio' to see available files."
        )

    audio = api.portfolio_list_audio()
    if not audio:
        return (
            "Portfolio is empty. "
            "Try 'discover audio files' or 'publish' some."
        )
    lines = ["Portfolio Audio:"]
    for a in audio:
        title = a.get("title", a.get("filename", "Untitled"))[:40]
        lines.append(f"  - {title}")
    return "\n".join(lines)


def handle_dashboard(api: Any, text: str) -> str:
    """Handle dashboard and system health requests."""
    text_lower = text.lower()

    note_match = re.search(r"(?:approve|read|show)\s+note\s+([^\s]+)", text, re.IGNORECASE)
    if note_match:
        note_name = note_match.group(1)
        if "approve" in text_lower:
            result = api.ableton_approve_note(note_name)
        else:
            result = api.ableton_read_note(note_name)
        return json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

    if "notes" in text_lower or "kenn note" in text_lower:
        notes = api.dashboard_list_notes()
        if not notes:
            return "No KENN training notes found."
        lines = ["KENN Training Notes:"]
        for n in notes[:10]:
            q = n.get("question", n.get("title", "?"))[:60]
            lines.append(f"  - {q}")
        return "\n".join(lines)

    if "improvement" in text_lower:
        imps = api.dashboard_list_improvements()
        if isinstance(imps, dict) and imps.get("ok") is False:
            return "Improvements could not be loaded (error code: service_unavailable)."
        return (
            json.dumps(imps, indent=2)[:1500]
            if isinstance(imps, dict)
            else str(imps)[:1500]
        )

    if "rebuild" in text_lower or "index" in text_lower:
        result = api.dashboard_build_index()
        return f"Index rebuild result: {result}"

    health = api.dashboard_web_health()
    lines = ["System Health Dashboard:", "---"]
    for key, val in health.items():
        icon = "OK" if val else "X"
        if isinstance(val, list):
            icon = f"({len(val)} formats)"
        lines.append(f"  [{icon}] {key}: {val}")

    ag = api.audiogen_status()
    ag_ok = ag.get("ok", False)
    lines.append(
        f"  [{'OK' if ag_ok else 'X'}] "
        f"AudioGen: {'Available' if ag_ok else 'Not available'}"
    )

    return "\n".join(lines)
