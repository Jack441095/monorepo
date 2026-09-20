"""Thursday proactive ambient intelligence — file watcher and daily briefing.

Watches a folder for new audio files and auto-runs mix analysis + KENN
action plan. Also provides a daily briefing spoken on first startup.

Usage:
    python main.py thursday --watch ~/Desktop/Mixes
    python main.py thursday --watch  (uses THURSDAY_WATCH_DIR env var)

Supported audio formats: .wav, .aif, .aiff
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "business" / "agents"))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from thursday.atomic_io import atomic_write

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff"}
DEFAULT_WATCH_DIR = os.environ.get(
    "THURSDAY_WATCH_DIR",
    str(Path.home() / "Desktop" / "Mixes"),
)
SEEN_CACHE_FILE = Path(__file__).parent / ".watcher_seen.txt"
POLL_INTERVAL = 5  # seconds


# ── seen-file cache ───────────────────────────────────────────────────────────

def _load_seen() -> set[str]:
    if SEEN_CACHE_FILE.exists():
        return set(SEEN_CACHE_FILE.read_text().splitlines())
    return set()


def _save_seen(seen: set[str]) -> None:
    try:
        atomic_write(SEEN_CACHE_FILE, "\n".join(sorted(seen)))
    except OSError:
        logger.warning("Failed to persist watcher seen-file cache to %s", SEEN_CACHE_FILE, exc_info=True)


def _file_key(path: Path) -> str:
    """Stable key: path + size (avoids re-processing on rename)."""
    try:
        return f"{path}:{path.stat().st_size}"
    except OSError:
        return str(path)


def _wait_for_stable_size(
    path: Path, poll_interval: float = 0.5, max_wait: float = 10.0,
) -> None:
    """Block until ``path``'s size stops changing across consecutive polls.

    Replaces a flat ``time.sleep(1.5)`` "wait for the file to finish
    writing" that was too short for large multitrack renders or slow
    (network-drive) copies, and too long for small files that finish
    instantly. Gives up after ``max_wait`` seconds and returns regardless
    (best effort -- callers proceed with whatever size the file has, same
    as the flat-sleep behavior it replaces).

    Not airtight: if a poll happens to land in a genuine pause between
    writes that's >= ``poll_interval``, this can conclude "stable" and
    return before writing has actually finished, re-opening (for that one
    poll) the same race this was written to close. Lowering
    ``poll_interval`` narrows the window but can't eliminate it for an
    arbitrarily bursty writer. Still strictly better than a flat sleep for
    every write pattern with gaps shorter than ``poll_interval``.
    """
    deadline = time.monotonic() + max_wait
    try:
        last_size = path.stat().st_size
    except OSError:
        return
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            size = path.stat().st_size
        except OSError:
            return
        if size == last_size:
            return
        last_size = size


# ── mix analysis ──────────────────────────────────────────────────────────────

def analyse_file(path: Path) -> str:
    """Run mix analysis on an audio file and return a spoken summary."""
    try:
        sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
        from audio_analysis.analysis_core.analysis_core import analyze_wav, AnalysisContext
    except ImportError:
        logger.exception("Mix analysis import failed")
        return "Mix analysis is unavailable (error code: service_unavailable)."

    try:
        raw = path.read_bytes()
        ctx = AnalysisContext(mix_goal="general", sample_rate=44100)
        result = analyze_wav(raw, filename=path.name, mix_goal="general", context=ctx)
    except TypeError:
        # Older API without AnalysisContext
        try:
            from audio_analysis.analysis_core.analysis_core import analyze_wav as _aw
            result = _aw(path.read_bytes(), filename=path.name, mix_goal="general")
        except Exception:
            logger.exception("Legacy mix analysis failed")
            return "Mix analysis failed (error code: execution_error)."
    except Exception:
        logger.exception("Mix analysis failed")
        return "Mix analysis failed (error code: execution_error)."

    # Build a short spoken summary from the result dict
    lines = [f"Mix analysis for {path.stem}:"]

    lufs = result.get("integrated_lufs") or result.get("lufs")
    if lufs is not None:
        lines.append(f"Loudness is {lufs:.1f} LUFS.")

    true_peak = result.get("true_peak_dbfs") or result.get("true_peak")
    if true_peak is not None:
        flag = " — over ceiling, watch out" if true_peak > -1.0 else ""
        lines.append(f"True peak {true_peak:.1f} dBFS{flag}.")

    flags = result.get("flags") or result.get("warnings") or []
    if flags:
        lines.append(f"{len(flags)} flag{'s' if len(flags) != 1 else ''}: " + ". ".join(str(f) for f in flags[:3]) + ".")

    if len(lines) == 1:
        lines.append("No critical issues detected.")

    return " ".join(lines)


def _ask_kenn_action_plan(file_summary: str) -> str:
    """Ask KENN for a prioritised action plan based on the analysis summary."""
    try:
        from Shared.kenn_bridge import ask_kenn
        question = f"Based on this mix analysis, what should I fix first? {file_summary}"
        return ask_kenn(question)
    except Exception:
        return ""


# ── daily briefing ────────────────────────────────────────────────────────────

from thursday.runtime_paths import BRIEFING_STAMP


def _today_str() -> str:
    import datetime
    return datetime.date.today().isoformat()


def briefing_due() -> bool:
    if not BRIEFING_STAMP.exists():
        return True
    return BRIEFING_STAMP.read_text().strip() != _today_str()


def daily_briefing(speak: bool = True) -> str:
    """Generate and optionally speak the daily studio briefing.

    Converged onto the canonical composed brief via its speakable renderer
    (same structured facts as the visual brief — no second briefing brain).
    Falls back to a minimal agenda-only line if composition fails.
    """
    import datetime

    today = datetime.date.today().strftime("%A, %d %B %Y")
    lines = [f"Good morning. Today is {today}."]

    try:
        from thursday.daily_brief import build_daily_brief, render_speakable_brief

        brief_dict, _ = build_daily_brief()
        spoken = render_speakable_brief(brief_dict)
        if spoken:
            lines.append(spoken)
    except Exception:
        pass

    # Pending sessions from Thursday scheduling
    try:
        from thursday.scheduling import agenda_for_day
        agenda = agenda_for_day()
        if agenda and "No reminders" not in agenda:
            lines.append("Your agenda: " + agenda.replace("\n", " "))
        else:
            lines.append("No reminders scheduled for today.")
    except Exception:
        pass

    # KENN knowledge base size
    try:
        notes_dir = ROOT / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
        note_count = len(list(notes_dir.glob("*.md"))) if notes_dir.exists() else 0
        if note_count:
            lines.append(f"KENN has {note_count} training notes.")
    except Exception:
        pass

    lines.append("Thursday is ready when you are.")
    briefing = " ".join(lines)

    if speak:
        try:
            from thursday.voice_output import speak as _speak
            _speak(briefing)
        except Exception:
            pass

    BRIEFING_STAMP.write_text(_today_str())
    return briefing


# ── file watcher loop ─────────────────────────────────────────────────────────

def watch(
    directory: str | Path | None = None,
    on_new_file: Callable[[Path, str], None] | None = None,
    speak: bool = True,
) -> None:
    """Watch a directory for new audio files and run mix analysis.

    Args:
        directory:   Folder to watch. Defaults to THURSDAY_WATCH_DIR.
        on_new_file: Optional callback(path, analysis_text). If None, prints + speaks.
        speak:       Whether to speak analysis results via macOS say.
    """
    watch_dir = Path(directory or DEFAULT_WATCH_DIR)

    if not watch_dir.exists():
        print(f"[watcher] Creating watch directory: {watch_dir}")
        watch_dir.mkdir(parents=True, exist_ok=True)

    seen = _load_seen()

    print(f"[watcher] Watching {watch_dir} for new audio files.")
    print("[watcher] Drop a .wav or .aif file to trigger auto-analysis.")
    print("[watcher] Press Ctrl+C to stop.\n")

    # Daily briefing on startup
    if briefing_due():
        briefing = daily_briefing(speak=speak)
        print(f"[briefing] {briefing}\n")

    try:
        while True:
            for path in sorted(watch_dir.glob("*")):
                if path.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                # Cheap pre-check against the file's current (possibly
                # still-growing) size, so an already-fully-processed file
                # doesn't pay the stabilization wait below on every poll.
                if _file_key(path) in seen:
                    continue

                print(f"\n[watcher] New file detected: {path.name}")

                # Wait for the file to finish writing/copying (large
                # multitrack renders or a slow network-drive copy can take
                # much longer than a flat delay would allow for).
                _wait_for_stable_size(path)

                # Recompute the key from the now-stable size *before*
                # recording it as seen. Recording the pre-wait key here
                # used to mean a file caught mid-write got a key with a
                # smaller size than its final one -- once the write
                # finished, the next poll would see a "new" (different)
                # key for the same file and re-trigger analysis a second
                # time.
                key = _file_key(path)
                if key in seen:
                    continue
                seen.add(key)
                _save_seen(seen)

                summary = analyse_file(path)
                print(f"[analysis] {summary}")

                # Get KENN action plan
                kenn_plan = _ask_kenn_action_plan(summary)
                if kenn_plan:
                    short = kenn_plan[:300]
                    print(f"[kenn] {short}")

                full_output = summary
                if kenn_plan:
                    full_output += " " + kenn_plan[:200]

                # Publish event to EventBus
                try:
                    from thursday.events import get_event_bus, Event, EventPriority
                    get_event_bus().publish(Event(
                        event_type="AUDIO_FILE_ADDED",
                        topic="filesystem",
                        priority=EventPriority.NORMAL,
                        payload={"path": str(path), "summary": summary, "output": full_output},
                        source="watcher",
                    ))
                except Exception:
                    pass

                if on_new_file:
                    on_new_file(path, full_output)
                elif speak:
                    try:
                        from thursday.voice_output import speak_async, extract_for_voice
                        speak_async(extract_for_voice(full_output))
                    except Exception:
                        pass

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n[watcher] Stopped.")
