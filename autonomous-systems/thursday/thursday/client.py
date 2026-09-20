"""Unified API Client — typed wrappers for all Thursday-accessible modules.

Each wrapper catches errors, returns structured dicts with:
    {"ok": bool, "data": ..., "error": str | None}

This consolidates all the direct imports, subprocess calls, and CLI commands
that were scattered throughout orchestrator.py.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from thursday.repo_root import audio_too_root

ROOT = audio_too_root()
AUDIO_ANALYSIS_ROOT = ROOT / "studio" / "audio_analysis"
WEBSITE_ROOT = ROOT / "business" / "app"
BUSINESS_ROOT = ROOT / "business"
STUDIO_ROOT = ROOT / "studio"
KENN_ROOT = STUDIO_ROOT / "kenn"
SCRIPTS_ROOT = ROOT / "scripts"
if str(WEBSITE_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBSITE_ROOT))
if str(BUSINESS_ROOT) not in sys.path:
    # automix_jobs.py (and others under business/app) do `from app.api_schemas
    # import ...` — a namespace-package import that needs business/ (app's
    # parent) on the path, not just business/app itself.
    sys.path.insert(0, str(BUSINESS_ROOT))
if str(AUDIO_ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(AUDIO_ANALYSIS_ROOT))
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))
if str(KENN_ROOT) not in sys.path:
    sys.path.insert(0, str(KENN_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

logger = logging.getLogger(__name__)


class KennAnswer(str):
    """Legacy string answer that retains KENN's structured evidence payload."""

    kenn_payload: dict

    def __new__(cls, answer: str, payload: dict):
        instance = super().__new__(cls, answer)
        instance.kenn_payload = dict(payload)
        return instance


def _empty_records(_name: str) -> list[dict]:
    return []


def _identity_add(_name: str, record: dict) -> dict:
    return record


def _noop_update(*_args: Any, **_kwargs: Any) -> None:
    return None


# ─── Result type ─────────────────────────────────────────────────────────


def ok(data: Any = None) -> dict:
    return {"ok": True, "data": data, "error": None}


def fail(error: str) -> dict:
    return {"ok": False, "data": None, "error": error}


# ─── Helpers ──────────────────────────────────────────────────────────────


def _cli_cmd(*args: str, timeout: int = 60) -> str:
    """Run an agent CLI command via the launcher and return output.

    Preferred path is in-process: the launcher module is imported once per
    Thursday process and its ``main()`` dispatched directly, eliminating the
    per-call interpreter/import subprocess cost (~7s measured). Any
    in-process failure falls back to the original subprocess path honestly.
    Disable with AUDIO_TOO_BUSINESS_INPROCESS=0.
    """
    if os.environ.get("AUDIO_TOO_BUSINESS_INPROCESS", "1") != "0":
        try:
            return _cli_cmd_inprocess(*args)
        except Exception:
            logger.warning("in-process agent dispatch failed; using subprocess", exc_info=True)
    return _cli_cmd_subprocess(*args, timeout=timeout)


_INPROCESS_LOCK = threading.Lock()
_AGENT_MODULE: Any = None


def _load_agent_module() -> Any:
    """Import the business agent launcher once and cache the module."""
    global _AGENT_MODULE
    if _AGENT_MODULE is None:
        import importlib.machinery
        import importlib.util
        import types

        launcher = ROOT / "business" / "agents" / "agent"
        if not launcher.exists():
            raise ImportError(f"agent launcher missing at {launcher}")
        # The launcher has no .py extension; load it explicitly by source.
        loader = importlib.machinery.SourceFileLoader(
            "audio_too_business_agent", str(launcher)
        )
        spec = importlib.util.spec_from_loader(
            loader.name, loader, origin=str(launcher)
        )
        if spec is None:
            raise ImportError(f"cannot build import spec for {launcher}")
        module = types.ModuleType(loader.name)
        module.__file__ = str(launcher)
        module.__loader__ = loader
        sys.modules[loader.name] = module
        # As a script, Python implicitly puts the script's directory on
        # sys.path (this is how `from Shared.… import …` resolves).
        # Mirror that for in-process execution.
        launcher_dir = str(launcher.parent)
        path_added = False
        if launcher_dir not in sys.path:
            sys.path.insert(0, launcher_dir)
            path_added = True
        try:
            loader.exec_module(module)  # one-time heavy import cost
        except Exception:
            if path_added:
                try:
                    sys.path.remove(launcher_dir)
                except ValueError:
                    pass
            sys.modules.pop(loader.name, None)
            raise
        _AGENT_MODULE = module
    return _AGENT_MODULE


def _cli_cmd_inprocess(*args: str) -> str:
    """Dispatch an agent CLI command inside this process (no subprocess).

    The business main() reads sys.argv and prints to stdout; both are
    swapped under a lock so concurrent Thursday threads stay isolated.
    A non-zero exit code mirrors the subprocess path's failure contract.
    """
    import contextlib
    import io

    module = _load_agent_module()
    buf = io.StringIO()
    old_argv = sys.argv
    try:
        with _INPROCESS_LOCK:
            sys.argv = [str(ROOT / "business" / "agents" / "agent"), *args]
            with contextlib.redirect_stdout(buf):
                returncode = module.main()
    finally:
        sys.argv = old_argv

    out = (buf.getvalue() or "").strip()
    if returncode:
        logger.error("in-process agent command failed rc=%s cmd=%s", returncode, args[0] if args else "?")
        return "Service command failed (error code: service_unavailable)."
    return out


def _cli_cmd_subprocess(*args: str, timeout: int = 60) -> str:
    """Original subprocess dispatch — retained as fallback."""
    LAUNCHER = ROOT / "business" / "agents" / "agent"
    try:
        r = subprocess.run(
            [sys.executable, str(LAUNCHER), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode:
            logger.error("Agent CLI failed returncode=%s stderr=%s", r.returncode, err)
            return "Service command failed (error code: service_unavailable)."
        if err:
            logger.warning("Agent CLI wrote stderr: %s", err)
        return out
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception:
        logger.exception("Agent CLI execution failed")
        return "Service command failed (error code: service_unavailable)."


def _run_agent(agent_path: str, *args: str, timeout: int = 60) -> str:
    """Run one of the named agents (Admin, Marketing, Research) and return output."""
    full_path = ROOT / "business" / "agents" / agent_path / "main.py" if "/" not in agent_path else ROOT / agent_path
    try:
        r = subprocess.run(
            [sys.executable, str(full_path), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode:
            logger.error(
                "Named agent failed agent=%s returncode=%s stderr=%s",
                agent_path,
                r.returncode,
                err,
            )
            return "Agent request failed (error code: service_unavailable)."
        if err:
            logger.warning("Named agent wrote stderr agent=%s stderr=%s", agent_path, err)
        return out
    except subprocess.TimeoutExpired:
        return f"{agent_path} agent timed out."
    except Exception:
        logger.exception("Named agent execution failed agent=%s", agent_path)
        return "Agent request failed (error code: service_unavailable)."


def _root_script(*args: str, timeout: int = 120) -> str:
    """Run main.py (root-level) with given args and return output."""
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), *args],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(ROOT),
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode:
            logger.error("Root command failed returncode=%s stderr=%s", r.returncode, err)
            return "Service command failed (error code: service_unavailable)."
        if err:
            logger.warning("Root command wrote stderr: %s", err)
        return out
    except subprocess.TimeoutExpired:
        return f"Command timed out ({timeout}s)."
    except Exception:
        logger.exception("Root command execution failed")
        return "Service command failed (error code: service_unavailable)."


# ─── Business Ops (CLI agent commands) ───────────────────────────────────


def business_status() -> str:
    return _cli_cmd("status")


def weekly_review() -> str:
    return _cli_cmd("weekly")


def week_ahead() -> str:
    return _cli_cmd("week-ahead")


def pipeline_summary() -> str:
    return _cli_cmd("pipeline-summary")


def reminders() -> str:
    return _cli_cmd("reminders")


def monthly_report() -> str:
    return _cli_cmd("report", "monthly")


def snapshot() -> str:
    return _cli_cmd("snapshot")


def list_snapshots() -> str:
    return _cli_cmd("snapshots")


def daily_maintenance() -> str:
    return _cli_cmd("cron-daily")


def weekly_maintenance() -> str:
    return _cli_cmd("cron-weekly")


# ─── Client / Search / Sessions ──────────────────────────────────────────


def search_all(list_records: Callable, query: str) -> str:
    from Shared.search import search_all as _search
    return _search(list_records, query)


def client_summary(list_records: Callable, name: str, *, date_range: tuple[str, str] | None = None) -> str:
    from Shared.client_history import client_summary as _summary
    return _summary(list_records, name, date_range=date_range)


def client_timeline(list_records: Callable, name: str, *, date_range: tuple[str, str] | None = None) -> str:
    from Shared.client_history import client_timeline as _timeline
    return _timeline(list_records, name, date_range=date_range)


def list_enquiries(list_records: Callable) -> list[dict]:
    return list_records("enquiries")


def list_sessions_cli() -> str:
    return _cli_cmd("sessions")


def schedule_session(text: str) -> str:
    return _cli_cmd("schedule", text)


# ─── Financial ────────────────────────────────────────────────────────────


def expenses_list(list_records: Callable) -> str:
    from Shared.expenses import list_expenses as _list
    return _list(list_records)


def expenses_by_category(list_records: Callable) -> str:
    from Shared.expenses import expenses_by_category as _by_cat
    return _by_cat(list_records)


def add_expense(list_records: Callable, add_record: Callable, text: str) -> str:
    from Shared.expenses import add_expense as _add
    return _add(list_records, add_record, text)


def profit_report(list_records: Callable, year: int | None = None) -> str:
    from Shared.expenses import profit_report as _profit
    return _profit(list_records, year)


def invoices_list() -> str:
    return _cli_cmd("admin", "invoices")


def invoice_pdf(list_records: Callable, invoice_id: str) -> str:
    try:
        from app.invoice_pdf import write_invoice_pdf
        invs = list_records("invoices")
        target = next((i for i in invs if i.get("id", "").lower() == invoice_id.lower()), None)
        if target:
            return f"Invoice PDF written to {write_invoice_pdf(target)}"
        return f"Invoice not found: {invoice_id}"
    except ImportError:
        return "Invoice PDF module not available."


def drafts_pending(list_records: Callable) -> str:
    from Shared.draft_sender import pending_since
    return pending_since(list_records)


def send_all_approved_drafts(list_records: Callable, add_record: Callable, update_record: Callable) -> str:
    from Shared.draft_sender import send_all_approved
    return send_all_approved(list_records, add_record, update_record)


def send_draft(list_records: Callable, add_record: Callable, update_record: Callable, draft_id: str) -> str:
    from Shared.draft_sender import send_draft
    return send_draft(list_records, add_record, update_record, draft_id)


# ─── KENN ─────────────────────────────────────────────────────────────────


def ask_kenn(
    question: str,
    fast: bool = False,
    history: list[dict] | None = None,
    session_id: str = "",
) -> str:
    """Ask KENN in-process so retrieval and conversation memory stay warm."""
    try:
        from kenn.core.chat import answer_payload

        payload = answer_payload(
            question,
            limit=4 if fast else 5,
            history=history,
            session_id=session_id,
        )
        answer = str(payload.get("answer") or "").strip()
        return KennAnswer(answer or "KENN returned an empty answer.", payload)
    except (ImportError, OSError):
        # Keep the existing isolated bridge as a compatibility fallback for
        # installations where KENN's optional dependencies are unavailable.
        from Shared.kenn_bridge import ask_kenn as _ask

        return _ask(question, limit=4 if fast else 5, fast=fast)
    except Exception:
        return (
            "I couldn't get a reliable answer from KENN just now. "
            "The knowledge service failed before it could verify its sources; try the question once more."
        )


# ─── Templates ────────────────────────────────────────────────────────────


def templates() -> str:
    return _cli_cmd("templates")


# ─── Agents ───────────────────────────────────────────────────────────────


def admin_agent(sub_command: str, text: str) -> str:
    return _run_agent("Admin", sub_command, text)


def marketing_agent(sub_command: str, *fields: str) -> str:
    # Variadic, not a single `text` blob: Marketing/main.py's real functions
    # (generate_social_post(platform, topic), create_campaign(type, target),
    # draft_outreach(lead, context)) each need two distinct fields, not one
    # combined string -- see registry/handlers.py::_handle_marketing_agent,
    # which is what actually splits a chat request into the right fields.
    return _run_agent("Marketing", sub_command, *fields)


def research_agent(sub_command: str, *fields: str) -> str:
    return _run_agent("Research", sub_command, *fields)


# ─── Audio Analysis / Mix Review ──────────────────────────────────────────


def audio_scan(path: str | None = None, timeout: int = 120) -> str:
    """Run an audio scan on a given path or default Portfolio/audio dir."""
    if path is None:
        audio_dir = ROOT / "Portfolio" / "audio"
        if not audio_dir.exists():
            return "Audio directory not found. Try specifying a path."
        path = str(audio_dir)
    return _root_script("audio-scan", path, timeout=timeout)


def mix_review_compare() -> str:
    return _cli_cmd("mix-review", "compare")


def mix_review_status() -> str:
    return _cli_cmd("mix-review", "status")


def list_mix_reviews(limit: int = 20) -> list[dict]:
    """List the most recent mix reviews."""
    try:
        from audio_analysis.mix_review.mix_review import list_reviews
        return list_reviews(limit=limit)
    except ImportError:
        return []


def mix_review_by_id(review_id: str) -> dict | None:
    """Fetch a single mix review by its ID."""
    try:
        from audio_analysis.mix_review.mix_review import review_by_id
        return review_by_id(review_id)
    except ImportError:
        return None


def mix_review_track_timeline(title: str) -> dict:
    """Show the version timeline for a given track title."""
    try:
        from audio_analysis.mix_review.mix_review import track_timeline
        return track_timeline(title, limit=80)
    except ImportError:
        return {"ok": False, "error": "Mix review module not available."}


def mix_review_version_diff(review_id_a: str, review_id_b: str | None = None) -> dict:
    """Compare two versions of a mix review."""
    try:
        from audio_analysis.mix_review.mix_review import version_diff
        return version_diff(review_id_a, review_id_b)
    except ImportError:
        return {"ok": False, "error": "Mix review module not available."}


def mix_review_report_html(review_id: str) -> str | None:
    """Get the HTML report for a mix review."""
    try:
        from audio_analysis.mix_review.mix_review import report_html
        return report_html(review_id)
    except ImportError:
        return None


def mix_review_generate_correction_rack(review_id: str) -> bytes | None:
    """Generate an Ableton correction rack for a mix review."""
    try:
        from audio_analysis.mix_review.mix_review import generate_correction_rack
        return generate_correction_rack(review_id)
    except ImportError:
        return None


def mix_review_analyze_stems_masking(stems: list[dict]) -> dict:
    """Analyze frequency masking between audio stems."""
    try:
        from audio_analysis.mix_review.mix_review import analyze_stems_masking
        return analyze_stems_masking(stems)
    except ImportError:
        return {"ok": False, "error": "Stem analysis module not available."}


def mix_review_list_references(limit: int = 50) -> list[dict]:
    """List saved reference tracks."""
    try:
        from audio_analysis.mix_review.mix_review import list_references
        return list_references(limit=limit)
    except ImportError:
        return []


def mix_review_batch_qa_summary(scan_payload: dict) -> dict:
    """Rank scanned audio items by quality risk."""
    try:
        from audio_analysis.mix_review.mix_review import batch_qa_summary
        return batch_qa_summary(scan_payload)
    except ImportError:
        return {"ok": False, "error": "Batch QA module not available."}


def mix_review_batch_music_analysis(scan_payload: dict) -> dict:
    """Run music-theory analysis over a scan result."""
    try:
        from audio_analysis.mix_review.mix_review import batch_music_analysis
        return batch_music_analysis(scan_payload)
    except ImportError:
        return {"ok": False, "error": "Music analysis module not available."}


def mix_review_refresh_closed_loop(review_id: str) -> dict:
    """Refresh the closed-loop action plan for a review."""
    try:
        from audio_analysis.mix_review.mix_review import refresh_closed_loop_payloads, review_by_id
        report = review_by_id(review_id)
        if not report:
            return {"ok": False, "error": f"Review not found: {review_id}"}
        return refresh_closed_loop_payloads(report)
    except ImportError:
        return {"ok": False, "error": "Closed-loop module not available."}


# ─── Ableton Bridge# ─── Ableton Bridge ───────────────────────────────────────────────────────


def ableton_web_health() -> str:
    """Check Ableton web interface health."""
    try:
        from app.ableton_bridge import web_health
        return web_health()
    except ImportError:
        return "Ableton bridge module not available."


def ableton_list_notes() -> str:
    try:
        from app.ableton_bridge import list_notes
        return str(list_notes())
    except ImportError:
        return "Ableton bridge module not available."


def ableton_read_note(name: str) -> dict:
    try:
        from app.ableton_bridge import read_note
        return read_note(name)
    except (ImportError, FileNotFoundError):
        logger.exception("Ableton note read failed")
        return {"ok": False, "error_code": "not_found"}


def ableton_approve_note(name: str) -> dict:
    try:
        from app.ableton_bridge import approve_note
        return approve_note(name)
    except (ImportError, FileNotFoundError):
        logger.exception("Ableton note approval failed")
        return {"ok": False, "error_code": "not_found"}


def ableton_create_note(question: str) -> dict:
    try:
        from app.ableton_bridge import create_note_from_question_api
        return create_note_from_question_api(question)
    except ImportError:
        logger.exception("Ableton note creation failed")
        return {"ok": False, "error_code": "service_unavailable"}


def ableton_build_index() -> str:
    try:
        from app.ableton_bridge import build_index
        return build_index()
    except ImportError:
        return "Ableton bridge module not available."


def ableton_osc_status() -> dict:
    """Check whether the live OSC bridge to Ableton is importable.

    This does not confirm Ableton is actually open and listening (OSC over
    UDP is fire-and-forget, see ableton_live_api.py) — it only confirms the
    client module loaded, matching /api/ableton/status in kenn/server.py.
    """
    try:
        from agents.MixReview.ableton_live_api import AbletonOSCClient  # noqa: F401
        return {"ok": True, "status": "initialized", "port": 9000}
    except ImportError:
        return {"ok": False, "status": "error", "error": "Ableton client not available"}


def ableton_apply_repair_chain(repair_chain: dict) -> dict:
    """Push a repair chain (track/device/param indices) live to Ableton via OSC.

    Gated behind the same daw_control action-policy flag as the KENN web
    endpoint's /api/ableton/apply-repair (studio/kenn/kenn/server.py) — this
    sends real UDP messages that change an open Ableton Live session, so it
    stays off by default until AUDIO_TOO_ALLOW_DAW_CONTROL is explicitly set.
    """
    try:
        from action_policy import action_allowed, action_denied_message
    except ImportError:
        return {"ok": False, "error": "Action policy module not available."}
    if not action_allowed("daw_control"):
        return {"ok": False, "error": action_denied_message("daw_control")}
    try:
        from agents.MixReview.ableton_live_api import AbletonOSCClient
    except ImportError:
        return {"ok": False, "error": "Ableton client not available."}
    success = AbletonOSCClient().apply_repair_chain(repair_chain)
    return {"ok": success}


def ableton_set_parameter(track: str | int, device: int, parameter: int, value: float) -> dict:
    """Set a single Ableton device parameter live via OSC (same daw_control gate as above)."""
    try:
        from action_policy import action_allowed, action_denied_message
    except ImportError:
        return {"ok": False, "error": "Action policy module not available."}
    if not action_allowed("daw_control"):
        return {"ok": False, "error": action_denied_message("daw_control")}
    try:
        from agents.MixReview.ableton_live_api import AbletonOSCClient
    except ImportError:
        return {"ok": False, "error": "Ableton client not available."}
    try:
        track_idx = -1 if isinstance(track, str) and track.strip().lower() == "master" else int(track)
    except ValueError:
        track_idx = 0
    AbletonOSCClient().set_parameter(track_idx, int(device), int(parameter), float(value))
    return {"ok": True}


# ─── AudioGen ─────────────────────────────────────────────────────────────


def audiogen_generate(text: str) -> str:
    """Generate audio via AudioGen (emotion-based or keyword)."""
    try:
        from LLM_AudioGen.main import generate_for_kenn_text
        return generate_for_kenn_text(text)
    except ImportError:
        return "AudioGen module not available."


def audiogen_status() -> dict:
    """Get AudioGen system status, available emotions, and counts."""
    try:
        from app.audiogen_bridge import status as _status
        return _status()
    except ImportError:
        return {"ok": False, "error": "AudioGen bridge not available."}


def audiogen_render_full_song(
    *,
    emotion: str = "joy",
    bars: int = 4,
    k: int = 1,
    publish: bool = True,
    project_id: str = "",
    chain_to_automix: bool = False,
    genre: str = "",
    style_prefs: dict | None = None,
) -> dict:
    """Queue a full-song render in AudioGen."""
    try:
        from app.audiogen_bridge import enqueue_full_song_render
        return enqueue_full_song_render(
            emotion=emotion,
            bars=bars,
            k=k,
            publish=publish,
            project_id=project_id,
            chain_to_automix=chain_to_automix,
            genre=genre,
            style_prefs=style_prefs,
        )
    except ImportError:
        return {"ok": False, "error": "AudioGen bridge not available."}


def audiogen_render_job_status(job_id: str) -> dict:
    """Check the status of a render job."""
    try:
        from app.audiogen_bridge import render_job
        return render_job(job_id)
    except ImportError:
        return {"ok": False, "error": "AudioGen bridge not available."}


def audiogen_render_queue() -> dict:
    """Snapshot of the current render queue."""
    try:
        from app.audiogen_bridge import render_queue_snapshot
        return render_queue_snapshot()
    except ImportError:
        return {"ok": False, "error": "AudioGen bridge not available."}


def audiogen_cancel_render(job_id: str) -> dict:
    """Cancel a queued or running render job."""
    try:
        from app.audiogen_bridge import cancel_render_job
        return cancel_render_job(job_id)
    except ImportError:
        return {"ok": False, "error": "AudioGen bridge not available."}


def audiogen_retry_render(job_id: str) -> dict:
    """Re-queue a failed render job."""
    try:
        from app.audiogen_bridge import retry_render_job
        return retry_render_job(job_id)
    except ImportError:
        return {"ok": False, "error": "AudioGen bridge not available."}


def audiogen_render_history(limit: int = 20) -> list[dict]:
    """List recent AudioGen render history."""
    try:
        from app.audiogen_bridge import list_render_history
        return list_render_history(limit=limit)
    except ImportError:
        return []


def audiogen_infer_emotion(prompt: str) -> str:
    """Infer an emotion from a text prompt."""
    try:
        from app.audiogen_bridge import infer_emotion
        return infer_emotion(prompt)
    except ImportError:
        return "joy"


# ─── AutoMix ──────────────────────────────────────────────────────────────
# Previously unreachable from Thursday at all — see
# docs/THURSDAY_ORCHESTRATOR_AUDIT_2026-07-08.md (P0). Mirrors the AudioGen
# wrapper pattern above; wraps the same automix_jobs API the HTTP routes use.


def automix_start(
    project_id: str,
    *,
    genre: str = "pop",
    target_lufs: float | None = None,
    style_prefs: dict | None = None,
    correlation_id: str = "",
) -> dict:
    """Queue an AutoMix job for a project's already-uploaded stems.

    style_prefs is passed straight through to the job (e.g. sliders, revision
    feedback, and Stage H's opt-in "autonomous_kenn" flag) -- it is off unless
    the caller explicitly sets it. correlation_id, when Thursday's caller
    supplied one (thursday/command_gateway.py's CommandEnvelope), threads
    through to the job row so the worker/advisor/feedback domain events it
    generates share that same trace id instead of minting their own.
    """
    try:
        import uuid

        from app.api_schemas import AutomixStartRequest
        import automix_jobs
        request = AutomixStartRequest(
            project_id=project_id,
            genre=genre,
            style_prefs=style_prefs or {},
            target_lufs=target_lufs,
            correlation_id=correlation_id,
        )
        status, response = automix_jobs.queue_job(request, idempotency_key=uuid.uuid4().hex)
        return response
    except ImportError:
        return {"ok": False, "error": "AutoMix module not available."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def automix_status(job_id: str) -> dict:
    """Check the status of an AutoMix job, including its status history."""
    try:
        import automix_jobs
        payload = automix_jobs.get_job_status(job_id)
        return payload if payload else {"ok": False, "error": f"AutoMix job not found: {job_id}"}
    except ImportError:
        return {"ok": False, "error": "AutoMix module not available."}


def automix_list_jobs(*, project_id: str | None = None, limit: int = 10) -> list[dict]:
    """List recent AutoMix jobs, optionally filtered to one project."""
    try:
        import automix_jobs
        return automix_jobs.list_recent_jobs(project_id=project_id, limit=limit)
    except ImportError:
        return []


# ─── Creative Lab

# ─── Creative Lab ────────────────────────────────────────────────────────


def creative_lab_snapshot(limit: int = 20) -> dict:
    """Get the Creative Lab snapshot with recent sessions and feedback."""
    try:
        from app.creative_lab import snapshot
        return snapshot(limit=limit)
    except ImportError:
        return {"ok": False, "error": "Creative Lab module not available."}


def creative_lab_repair_recommendations(limit: int = 8) -> list[dict]:
    """Get pending repair recommendations."""
    try:
        from app.creative_lab import repair_recommendations
        return repair_recommendations(limit=limit)
    except ImportError:
        return []


def creative_lab_run_repair_recommendation(feedback_id: str) -> dict:
    """Run a repair recommendation for the given feedback ID."""
    try:
        from app.creative_lab import run_repair_recommendation
        return run_repair_recommendation(feedback_id)
    except ImportError:
        return {"ok": False, "error": "Creative Lab module not available."}


def creative_lab_promote_repair(feedback_id: str) -> dict:
    """Promote a repair to approved/training status."""
    try:
        from app.creative_lab import promote_repair
        return promote_repair(feedback_id)
    except ImportError:
        return {"ok": False, "error": "Creative Lab module not available."}


def creative_lab_promote_repair_eval(feedback_id: str) -> dict:
    """Add a passing repair case to the KENN regression suite."""
    try:
        from app.creative_lab import promote_repair_eval_case
        return promote_repair_eval_case(feedback_id)
    except ImportError:
        return {"ok": False, "error": "Creative Lab module not available."}


def creative_lab_record_session_event(payload: dict) -> dict:
    """Record a Creative Lab session event."""
    try:
        from app.creative_lab import record_session_event
        return record_session_event(payload)
    except ImportError:
        return {"ok": False, "error": "Creative Lab module not available."}


def creative_lab_record_feedback(payload: dict) -> dict:
    """Record Creative Lab feedback."""
    try:
        from app.creative_lab import record_feedback
        return record_feedback(payload)
    except ImportError:
        return {"ok": False, "error": "Creative Lab module not available."}


def creative_lab_create_repair_artifacts(feedback_id: str) -> dict:
    """Create KENN repair draft artifacts from feedback."""
    try:
        from app.creative_lab import create_repair_artifacts
        return create_repair_artifacts(feedback_id)
    except ImportError:
        return {"ok": False, "error": "Creative Lab module not available."}


# ─── Portfolio ────────────────────────────────────────────────────────────


def portfolio_list_audio() -> list[dict]:
    """List published portfolio audio files."""
    try:
        from app.portfolio_ops import load_data
        return load_data().get("audio", [])
    except ImportError:
        return []


def portfolio_publish_audio(filename: str, title: str = "", description: str = "") -> dict:
    """Publish an audio file to the portfolio."""
    try:
        from app.portfolio_ops import publish_audio
        return publish_audio(filename, title=title, description=description)
    except ImportError:
        return {"ok": False, "error": "Portfolio module not available."}


def portfolio_discover_audio_files() -> list[dict]:
    """Discover new audio files not yet in the portfolio."""
    try:
        from app.portfolio_ops import discover_audio_files
        return discover_audio_files()
    except ImportError:
        return []


# ─── Dashboard / KENN Admin ──────────────────────────────────────────────


def dashboard_web_health() -> dict:
    """Check all web-based subsystem health."""
    results = {}
    try:
        from app.audiogen_bridge import exists as ag_exists
        results["audiogen"] = ag_exists()
    except ImportError:
        results["audiogen"] = False
    try:
        from app.audiogen_bridge import status as ag_status
        s = ag_status()
        results["audiogen_status"] = s.get("ok", False)
    except ImportError:
        pass
    try:
        from audio_analysis.mix_review.mix_review_config import DECODABLE_SUFFIXES
        results["audio_analysis"] = True
        results["decodable_formats"] = list(DECODABLE_SUFFIXES)
    except ImportError:
        results["audio_analysis"] = False
    return results


def dashboard_list_notes() -> list[dict]:
    """List KENN training notes from the Ableton bridge."""
    try:
        from app.ableton_routes import list_notes
        return list_notes()
    except ImportError:
        return []


def dashboard_build_index() -> str:
    """Trigger a KENN index rebuild."""
    try:
        from app.ableton_routes import rebuild_index
        return rebuild_index()
    except ImportError:
        return "Index rebuild module not available."


def dashboard_list_improvements() -> dict:
    """List pending KENN improvements from feedback."""
    try:
        from app.ableton_routes import list_improvements
        return list_improvements()
    except ImportError:
        return {"ok": False, "error": "Improvements module not available."}


def mix_review_storage_stats() -> dict:
    try:
        from audio_analysis.mix_review.mix_review import get_storage_stats
        return get_storage_stats()
    except ImportError:
        return {"ok": False, "error": "Mix review storage module not available."}


def mix_review_cleanup_audiogen(dry_run: bool = True) -> dict:
    try:
        from audio_analysis.mix_review.mix_review import cleanup_audiogen_exports
        return cleanup_audiogen_exports(dry_run=dry_run)
    except ImportError:
        return {"ok": False, "error": "Mix review cleanup module not available."}


def mix_review_cleanup_orphans(dry_run: bool = True) -> dict:
    try:
        from audio_analysis.mix_review.mix_review import cleanup_orphaned_uploads
        return cleanup_orphaned_uploads(dry_run=dry_run)
    except ImportError:
        return {"ok": False, "error": "Mix review cleanup module not available."}


# ─── Data Store (generic) ────────────────────────────────────────────────


def list_records(list_records_func: Callable, record_type: str) -> list[dict]:
    return list_records_func(record_type)


# ─── Canonical structured client ─────────────────────────────────────────


class APIClient:
    """Typed facade matching the Thursday upgrade-plan API.

    The existing module functions remain available to the registry for
    backwards compatibility. New orchestration code can use this facade and
    always receives ``{ok, data, error}``.
    """

    def __init__(self, list_records_func: Callable | None = None,
                 add_record_func: Callable | None = None,
                 update_record_func: Callable | None = None):
        if list_records_func is None:
            try:
                from app.db import list_records as list_records_func
            except ImportError:
                list_records_func = _empty_records
        if add_record_func is None:
            try:
                from app.db import add_record as add_record_func
            except ImportError:
                add_record_func = _identity_add
        if update_record_func is None:
            try:
                from app.db import update_record as update_record_func
            except ImportError:
                update_record_func = _noop_update
        self._list_records = list_records_func
        self._add_record = add_record_func
        self._update_record = update_record_func

    @staticmethod
    def _call(func: Callable, *args: Any, **kwargs: Any) -> dict:
        try:
            return ok(func(*args, **kwargs))
        except Exception:
            logger.exception("Thursday API client call failed function=%s", func.__name__)
            return fail("The service call could not be completed.")

    # Ableton / KENN bridge
    def web_health(self) -> dict:
        from app.ableton_bridge import web_health
        return self._call(web_health)

    def list_notes(self, **kwargs: Any) -> dict:
        from app.ableton_bridge import list_notes
        return self._call(list_notes, **kwargs)

    def read_note(self, name: str) -> dict:
        from app.ableton_bridge import read_note
        return self._call(read_note, name)

    def approve_note(self, name: str) -> dict:
        from app.ableton_bridge import approve_note
        return self._call(approve_note, name)

    def build_index(self) -> dict:
        from app.ableton_bridge import build_index
        return self._call(build_index)

    def ask(self, question: str, **kwargs: Any) -> dict:
        from app.ableton_bridge import ask
        return self._call(ask, question, **kwargs)

    def suggest_questions(self, query: str = "", **kwargs: Any) -> dict:
        from app.ableton_bridge import suggest_questions
        return self._call(suggest_questions, query, **kwargs)

    def create_note_from_question(self, question: str, topics: list | None = None) -> dict:
        from app.ableton_bridge import create_note_from_question_api
        return self._call(create_note_from_question_api, question, topics)

    # Agents
    def run_agent_task(self, task: str, agent: str = "Admin") -> dict:
        return self._call(_run_agent, agent, "auto", task)

    # Creative Lab
    def creative_snapshot(self, limit: int = 20) -> dict:
        return self._call(creative_lab_snapshot, limit)

    def snapshot(self, limit: int = 20) -> dict:
        return self.creative_snapshot(limit)

    def repair_queue(self, limit: int = 20) -> dict:
        from app.creative_lab import repair_queue
        return self._call(repair_queue, limit=limit)

    def repair_recommendations(self, limit: int = 8) -> dict:
        return self._call(creative_lab_repair_recommendations, limit)

    def run_repair_recommendation(self, feedback_id: str) -> dict:
        return self._call(creative_lab_run_repair_recommendation, feedback_id)

    def record_session_event(self, payload: dict) -> dict:
        return self._call(creative_lab_record_session_event, payload)

    def record_feedback(self, payload: dict) -> dict:
        return self._call(creative_lab_record_feedback, payload)

    def promote_repair(self, feedback_id: str) -> dict:
        return self._call(creative_lab_promote_repair, feedback_id)

    def create_repair_artifacts(self, feedback_id: str) -> dict:
        return self._call(creative_lab_create_repair_artifacts, feedback_id)

    # AudioGen
    def generate_loop(self, prompt: str) -> dict:
        return self._call(audiogen_generate, prompt)

    def render_full_song(self, **kwargs: Any) -> dict:
        return self._call(audiogen_render_full_song, **kwargs)

    def status(self) -> dict:
        return self._call(audiogen_status)

    def infer_emotion(self, prompt: str) -> dict:
        return self._call(audiogen_infer_emotion, prompt)

    def enqueue_full_song_render(self, **kwargs: Any) -> dict:
        return self._call(audiogen_render_full_song, **kwargs)

    def render_queue_snapshot(self) -> dict:
        return self._call(audiogen_render_queue)

    def cancel_render_job(self, job_id: str) -> dict:
        return self._call(audiogen_cancel_render, job_id)

    def retry_render_job(self, job_id: str) -> dict:
        return self._call(audiogen_retry_render, job_id)

    def list_render_history(self, limit: int = 20) -> dict:
        return self._call(audiogen_render_history, limit)

    # Portfolio
    def list_audio(self) -> dict:
        return self._call(portfolio_list_audio)

    def publish_audio(self, filename: str, title: str = "", description: str = "") -> dict:
        return self._call(portfolio_publish_audio, filename, title, description)

    def discover_audio_files(self) -> dict:
        return self._call(portfolio_discover_audio_files)

    # Mix review / audio analysis
    def analyze_wav(self, file_bytes: bytes, filename: str = "mix.wav", **kwargs: Any) -> dict:
        from audio_analysis.mix_review.mix_review import analyze_wav
        return self._call(analyze_wav, file_bytes, filename, **kwargs)

    def save_review(self, **kwargs: Any) -> dict:
        from audio_analysis.mix_review.mix_review import save_review
        return self._call(save_review, **kwargs)

    def list_reviews(self, limit: int = 50) -> dict:
        return self._call(list_mix_reviews, limit)

    def review_by_id(self, review_id: str) -> dict:
        return self._call(mix_review_by_id, review_id)

    def scan_audio_files(self, root: str, **kwargs: Any) -> dict:
        from audio_analysis.mix_review.mix_review import scan_audio_files
        return self._call(scan_audio_files, Path(root).expanduser(), **kwargs)

    def scan_audio_benchmark(self, payload: dict) -> dict:
        from audio_analysis.mix_review.mix_review import scan_audio_benchmark
        return self._call(scan_audio_benchmark, payload)

    def batch_qa_summary(self, payload: dict) -> dict:
        return self._call(mix_review_batch_qa_summary, payload)

    def batch_music_analysis(self, payload: dict) -> dict:
        return self._call(mix_review_batch_music_analysis, payload)

    def version_diff(self, first: str, second: str | None = None) -> dict:
        return self._call(mix_review_version_diff, first, second)

    def track_timeline(self, title: str) -> dict:
        return self._call(mix_review_track_timeline, title)

    def report_html(self, review_id: str) -> dict:
        return self._call(mix_review_report_html, review_id)

    def report_json_bytes(self, review_id: str) -> dict:
        from audio_analysis.mix_review.mix_review import report_json_bytes
        return self._call(report_json_bytes, review_id)

    def review_audio_path(self, review_id: str, type: str = "mix") -> dict:
        from audio_analysis.mix_review.mix_review import review_audio_path
        return self._call(review_audio_path, review_id, type)

    def generate_correction_rack(self, review_id: str) -> dict:
        return self._call(mix_review_generate_correction_rack, review_id)

    def analyze_stems_masking(self, stems: list[dict]) -> dict:
        return self._call(mix_review_analyze_stems_masking, stems)

    def compare_metrics(self, mix: dict, reference: dict) -> dict:
        from audio_analysis.mix_review.mix_review import compare_metrics
        return self._call(compare_metrics, mix, reference)

    def refresh_closed_loop_payloads(self, review_id: str) -> dict:
        return self._call(mix_review_refresh_closed_loop, review_id)

    def list_references(self, limit: int = 100) -> dict:
        return self._call(mix_review_list_references, limit)

    def save_reference(self, **kwargs: Any) -> dict:
        from audio_analysis.mix_review.mix_review import save_reference
        return self._call(save_reference, **kwargs)

    def mix_review_status(self, review_id: str) -> dict:
        from audio_analysis.mix_review.mix_review import mix_review_status
        return self._call(mix_review_status, review_id)

    def cleanup_audiogen_exports(self, dry_run: bool = True) -> dict:
        from audio_analysis.mix_review.mix_review import cleanup_audiogen_exports
        return self._call(cleanup_audiogen_exports, dry_run)

    def cleanup_orphaned_uploads(self, dry_run: bool = True) -> dict:
        from audio_analysis.mix_review.mix_review import cleanup_orphaned_uploads
        return self._call(cleanup_orphaned_uploads, dry_run)

    def get_storage_stats(self) -> dict:
        from audio_analysis.mix_review.mix_review import get_storage_stats
        return self._call(get_storage_stats)

    # Data, expenses, sessions, workflow
    def records(self, record_type: str) -> dict:
        return self._call(self._list_records, record_type)

    def list_records(self, record_type: str) -> dict:
        return self.records(record_type)

    def add_record(self, record_type: str, record: dict) -> dict:
        return self._call(self._add_record, record_type, record)

    def update_record(self, record_type: str, identifier: str, updates: dict,
                      search_fields: list[str] | None = None) -> dict:
        return self._call(self._update_record, record_type, identifier, updates, search_fields)

    def list_expenses(self) -> dict:
        return self._call(expenses_list, self._list_records)

    def add_expense(self, text: str) -> dict:
        return self._call(add_expense, self._list_records, self._add_record, text)

    def profit_report(self, year: int | None = None) -> dict:
        return self._call(profit_report, self._list_records, year)

    def ask_kenn(self, question: str) -> dict:
        return self._call(ask_kenn, question)

    def list_sessions(self) -> dict:
        return self._call(list_sessions_cli)

    def schedule_session(self, text: str) -> dict:
        return self._call(schedule_session, text)

    def pipeline_summary(self) -> dict:
        return self._call(pipeline_summary)

    def convert_enquiry(self, enquiry_id: str, details: str = "") -> dict:
        from Shared.workflow import convert_enquiry_to_client_and_project
        return self._call(
            convert_enquiry_to_client_and_project,
            self._list_records, self._add_record, enquiry_id,
        )

    def convert_lead(self, lead_id: str, details: str = "") -> dict:
        from Shared.workflow import convert_lead_to_client_and_project
        return self._call(
            convert_lead_to_client_and_project,
            self._list_records, self._add_record, lead_id,
        )
