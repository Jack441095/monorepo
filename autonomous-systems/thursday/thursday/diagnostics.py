"""Self-Healing & Diagnostics — system health checks and automatic recovery.

Allows Thursday to:
  - Check all subsystem health
  - Diagnose and suggest fixes for common errors
  - Attempt automatic recovery for known issues
  - Track usage analytics
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from thursday.atomic_io import atomic_write
from thursday.redaction import get_logger as _get_redacting_logger
from thursday.repo_root import audio_too_root

logger = _get_redacting_logger(__name__)

ROOT = audio_too_root()
for _path in (
    ROOT / "business",
    ROOT / "business" / "app",
    ROOT / "studio" / "audio_analysis",
    ROOT / "studio" / "audiogen",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


# ─── Health Check Functions ──────────────────────────────────────────────


def _port_open(host: str = "127.0.0.1", port: int = 8080, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _file_exists(*path_parts: str) -> bool:
    """Check if a file exists."""
    return Path(ROOT, *path_parts).exists()


def _is_importable(module_name: str) -> bool:
    """Check if a Python module is importable."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def check_website() -> dict:
    """Check if the Website server is running on port 8080."""
    return {
        "name": "Website Server",
        "healthy": _port_open(port=8080),
        "port": 8080,
        "details": "Web dashboard and API server",
        "fix_hint": "Run: python3 business/app/server.py &",
    }


def check_kenn() -> dict:
    """Check if KENN is running on port 8090."""
    return {
        "name": "KENN Knowledge Base",
        "healthy": _port_open(port=8090),
        "port": 8090,
        "details": "KENN production Q&A backend",
        "fix_hint": "Run: python main.py start",
    }


def check_database() -> dict:
    """Check if the SQLite database is accessible."""
    db_paths = [
        Path("data/audio_too.db"),
        Path("business/app/database.db"),
        Path("business/app/data.db"),
    ]
    found_db = None
    for p in db_paths:
        full = ROOT / p
        if full.exists():
            found_db = str(full)
            break

    if found_db:
        # Try to read a byte to verify it's not corrupt
        try:
            size = os.path.getsize(found_db)
            with open(found_db, "rb") as f:
                f.read(100)
            return {
                "name": "Database",
                "healthy": True,
                "path": found_db,
                "size_kb": round(size / 1024, 1),
                "details": "SQLite database accessible",
                "fix_hint": None,
            }
        except (OSError, IOError):
            return {
                "name": "Database",
                "healthy": False,
                "path": found_db,
                "size_kb": 0,
                "details": "Database file exists but may be corrupt",
                "fix_hint": "Backup and restore from snapshot",
            }
    return {
        "name": "Database",
        "healthy": False,
        "path": None,
        "details": "No database file found in expected locations",
        "fix_hint": "Initialize database: python3 business/app/db.py (or check DBPATH env var)",
    }


def check_audiogen() -> dict:
    """Check if AudioGen environment is healthy."""
    has_main_llm = _file_exists("studio", "audiogen", "audiogen", "main.py")
    has_bridge = _is_importable("app.audiogen_bridge")

    details = []
    if has_main_llm:
        details.append("AudioGen main module importable")
    else:
        details.append("AudioGen main module NOT available")
    if has_bridge:
        details.append("AudioGen bridge importable")
    else:
        details.append("AudioGen bridge NOT available")

    return {
        "name": "AudioGen",
        "healthy": has_main_llm and has_bridge,
        "has_main_llm": has_main_llm,
        "has_bridge": has_bridge,
        "details": "; ".join(details),
        "fix_hint": "Check studio/audiogen/audiogen/ and business/app/audiogen_bridge.py exist",
    }


def check_audio_analysis() -> dict:
    """Check if audio analysis tool is importable."""
    can_import = _is_importable("audio_analysis.mix_review.mix_review")
    return {
        "name": "Audio Analysis",
        "healthy": can_import,
        "details": "Audio analysis tool module",
        "fix_hint": "Check studio/audio_analysis/audio_analysis/mix_review/ directory exists and has mix_review.py",
    }


def check_agents() -> dict:
    """Check if agent modules are accessible."""
    agent_dirs = ["Admin", "Marketing", "Research"]
    results = {}
    for agent in agent_dirs:
        main_py = ROOT / "business" / "agents" / agent / "main.py"
        results[agent] = main_py.exists()

    all_ok = all(results.values())
    missing = [k for k, v in results.items() if not v]
    return {
        "name": "Agent Modules",
        "healthy": all_ok,
        "agents": results,
        "details": f"{len([v for v in results.values() if v])}/{len(agent_dirs)} agents available"
                   + (f". Missing: {', '.join(missing)}" if missing else ""),
        "fix_hint": None if all_ok else "Run: mkdir -p business/agents/{Admin,Marketing,Research}",
    }


def check_thursday_storage() -> dict:
    """Check if Thursday session/alerts directories exist and are writable."""
    from thursday.session_manager import SESSION_DIR
    from thursday.monitor import ALERTS_DIR

    issues = []
    for name, dir_path in [("sessions", SESSION_DIR), ("alerts", ALERTS_DIR)]:
        if not dir_path.exists():
            issues.append(f"{name} directory missing")
        elif not os.access(str(dir_path), os.W_OK):
            issues.append(f"{name} directory not writable")

    return {
        "name": "Thursday Storage",
        "healthy": len(issues) == 0,
        "details": "; ".join(issues) if issues else "All storage directories OK",
        "fix_hint": "Run: mkdir -p Thursday/sessions Thursday/alerts",
    }


# ─── Comprehensive Check ─────────────────────────────────────────────────


def check_all_systems() -> dict:
    """Run all health checks and return a comprehensive status dict.

    Returns:
        {
            "timestamp": "...",
            "all_healthy": bool,
            "checks": [check_result, ...],
        }
    """
    checks = [
        check_website(),
        check_kenn(),
        check_database(),
        check_audiogen(),
        check_audio_analysis(),
        check_agents(),
        check_thursday_storage(),
    ]

    all_healthy = all(c.get("healthy") for c in checks)
    return {
        "timestamp": datetime.now().isoformat(),
        "all_healthy": all_healthy,
        "checks": checks,
        "healthy_count": sum(1 for c in checks if c.get("healthy")),
        "total_checks": len(checks),
    }


def format_health_report(health: dict | None = None) -> str:
    """Format health check results into a readable report.

    Args:
        health: Output from check_all_systems(), or None to run checks now.

    Returns:
        Formatted report string.
    """
    if health is None:
        health = check_all_systems()

    lines = ["🩺 Thursday System Health Report"]
    lines.append(f"   {health['timestamp'][:19]}")
    lines.append("")

    for check in health.get("checks", []):
        icon = "✅" if check.get("healthy") else "❌"
        name = check.get("name", "Unknown")
        details = check.get("details", "")
        lines.append(f"  {icon} {name}")
        lines.append(f"     {details}")
        fix = check.get("fix_hint")
        if fix and not check.get("healthy"):
            lines.append(f"     Fix: {fix}")

    lines.append("")
    summary = (
        f"Result: {health.get('healthy_count', 0)}/{health.get('total_checks', 0)} subsystems healthy"
    )
    if not health.get("all_healthy", True):
        unhealthy = [c.get("name") for c in health.get("checks", []) if not c.get("healthy")]
        summary += f"\nNeeds attention: {', '.join(unhealthy)}"
    lines.append(summary)

    return "\n".join(lines)


# ─── Error Diagnosis ─────────────────────────────────────────────────────


COMMON_ERRORS = {
    "Connection refused": {
        "service": "network",
        "advice": "The target server isn't running. Use 'check all systems' to see what's down.",
    },
    "Timeout": {
        "service": "network",
        "advice": "A command timed out. Try again, or check if the service is overloaded.",
    },
    "ModuleNotFoundError": {
        "service": "import",
        "advice": "A Python module is missing. Try reinstalling dependencies.",
    },
    "No such file or directory": {
        "service": "filesystem",
        "advice": "A file path doesn't exist. Double-check the path or run a scan.",
    },
    "database is locked": {
        "service": "database",
        "advice": "Another process is writing to the database. Try again in a moment.",
    },
    "disk quota exceeded": {
        "service": "filesystem",
        "advice": "Your disk is full or quota exceeded. Free up space and try again.",
    },
    "permission denied": {
        "service": "filesystem",
        "advice": "File permission issue. Run with appropriate permissions.",
    },
    "Empty as any": {
        "service": "kenn",
        "advice": "KENN returned no results. Try rephrasing your question.",
    },
    "Failed to load session": {
        "service": "session",
        "advice": "Session file may be corrupt. Start a new session with --new-session.",
    },
}


def diagnose_error(error: str, service: str | None = None) -> str:
    """Suggest fixes for common errors.

    Args:
        error: The error message string.
        service: Optional service name for context.

    Returns:
        Diagnostic advice string.
    """
    suggestions = []

    # Check against known error patterns
    for pattern, diagnosis in COMMON_ERRORS.items():
        if pattern.lower() in error.lower():
            suggestions.append(diagnosis["advice"])

    if not suggestions:
        if service:
            suggestions.append(f"The {service} module encountered an error.")
        suggestions.append("Try again or ask for something else.")
        suggestions.append("For system-level issues, try 'check all systems'.")

    parts = [f"I ran into an issue: {error[:200]}"]
    if suggestions:
        parts.append("")
        parts.append("Suggested fixes:")
        for i, s in enumerate(suggestions, 1):
            parts.append(f"  {i}. {s}")
    return "\n".join(parts)


# ─── Automatic Recovery & Self-Healing ─────────────────────────────────


class CircuitBreaker:
    """Circuit breaker for autonomous system recovery to prevent restart storms.

    Caps recovery attempts per subsystem (default: max 3 attempts within 600s / 10 mins).
    """

    def __init__(self, max_attempts: int = 3, cooldown_seconds: float = 600.0):
        self.max_attempts = max_attempts
        self.cooldown_seconds = cooldown_seconds
        self._history: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        timestamps = [t for t in self._history.get(key, []) if now - t < self.cooldown_seconds]
        self._history[key] = timestamps
        return len(timestamps) < self.max_attempts

    def record_attempt(self, key: str) -> None:
        now = time.time()
        timestamps = [t for t in self._history.get(key, []) if now - t < self.cooldown_seconds]
        timestamps.append(now)
        self._history[key] = timestamps

    def reset(self, key: str) -> None:
        self._history.pop(key, None)


_RECOVERY_CIRCUIT_BREAKER = CircuitBreaker()


def try_fix(name: str) -> dict:
    """Attempt automatic recovery for a subsystem.

    Args:
        name: Subsystem name ("website", "kenn", "database").

    Returns:
        Result dict with "ok", "action", "message".
    """
    name_lower = name.lower().strip()

    if name_lower in ("website", "server", "website server"):
        # Try to restart the website server
        server_path = ROOT / "business" / "app" / "server.py"
        if server_path.exists():
            try:
                subprocess.Popen(
                    [sys.executable, str(server_path)],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(2)
                if _port_open(port=8080):
                    return {"ok": True, "action": "restarted", "message": "Website server restarted successfully."}
                return {"ok": False, "action": "restart_failed", "message": "Could not start website server on port 8080."}
            except OSError:
                logger.exception("Website recovery start failed")
                return {
                    "ok": False,
                    "action": "error",
                    "message": "Website recovery failed (error code: service_unavailable).",
                }
        return {"ok": False, "action": "not_found", "message": f"Server script not found at {server_path}"}

    if name_lower in ("kenn", "kenn knowledge base"):
        # Check if KENN port is open
        if _port_open(port=8090):
            return {"ok": True, "action": "already_running", "message": "KENN is already running on port 8090."}
        kenn_server_path = ROOT / "studio" / "kenn" / "kenn" / "server.py"
        if kenn_server_path.exists():
            try:
                subprocess.Popen(
                    [sys.executable, str(kenn_server_path)],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(2)
                if _port_open(port=8090):
                    return {"ok": True, "action": "restarted", "message": "KENN server restarted successfully on port 8090."}
            except OSError:
                logger.exception("KENN recovery start failed")
        return {
            "ok": False,
            "action": "manual",
            "message": "KENN may need Docker or setup. Try: docker start kenn-server or check your KENN setup.",
        }

    if name_lower in ("database", "db"):
        # Attempt SQLite WAL checkpointing and quick check
        db_result = check_database()
        if db_result.get("healthy") and db_result.get("path"):
            try:
                import sqlite3
                conn = sqlite3.connect(db_result["path"], timeout=3.0)
                cursor = conn.cursor()
                cursor.execute("PRAGMA wal_checkpoint(PASSIVE);")
                cursor.execute("PRAGMA quick_check;")
                res = cursor.fetchone()
                conn.close()
                if res and res[0] == "ok":
                    return {"ok": True, "action": "checkpoint_passed", "message": "Database WAL checkpointed and verified healthy."}
            except Exception as e:
                logger.warning(f"Database recovery checkpoint failed: {e}")
        return {
            "ok": False,
            "action": "manual",
            "message": "Database issue detected. Try: python3 business/app/db.py to reinitialize.",
        }

    return {"ok": False, "action": "unknown", "message": f"I don't know how to fix '{name}'."}


def auto_heal_subsystems(circuit_breaker: CircuitBreaker | None = None) -> dict:
    """Perform autonomous health checks and auto-remediate unhealthy subsystems.

    Uses a circuit breaker to prevent restart storms.
    """
    cb = circuit_breaker or _RECOVERY_CIRCUIT_BREAKER
    health = check_all_systems()
    remediations = []

    if health.get("all_healthy"):
        return {
            "healed": True,
            "message": "All subsystems are healthy; no remediation needed.",
            "remediations": [],
            "health": health,
        }

    for check in health.get("checks", []):
        if not check.get("healthy"):
            sub_name = str(check.get("name", "")).strip()
            if not sub_name:
                continue
            key = sub_name.lower()
            if not cb.allow(key):
                remediations.append({
                    "subsystem": sub_name,
                    "ok": False,
                    "action": "circuit_breaker_tripped",
                    "message": f"Circuit breaker active for '{sub_name}'. Max recovery attempts exceeded.",
                })
                continue

            cb.record_attempt(key)
            result = try_fix(key)
            if result.get("ok"):
                cb.reset(key)
            remediations.append({
                "subsystem": sub_name,
                **result,
            })

    post_health = check_all_systems()
    return {
        "healed": post_health.get("all_healthy", False),
        "message": "Auto-healing pass completed.",
        "remediations": remediations,
        "health": post_health,
    }


# ─── Usage Analytics ─────────────────────────────────────────────────────


from thursday.runtime_paths import ANALYTICS_DIR


def _load_analytics() -> dict:
    """Load usage analytics data."""
    path = ANALYTICS_DIR / "usage.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"requests": [], "service_counts": {}, "daily_counts": {}, "errors": []}


def _save_analytics(data: dict) -> None:
    """Save usage analytics data."""
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    path = ANALYTICS_DIR / "usage.json"
    try:
        atomic_write(path, json.dumps(data, indent=2))
    except OSError:
        pass


def record_usage(
    service_id: str | None,
    intent: str | None,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    """Record a usage analytics entry.

    Args:
        service_id: The service used (or None).
        intent: The classified intent (or None).
        duration_ms: Processing duration in milliseconds.
        error: Error message if any.
    """
    analytics = _load_analytics()
    today = datetime.now().strftime("%Y-%m-%d")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "service_id": service_id,
        "intent": intent,
        "duration_ms": duration_ms,
    }
    analytics["requests"].append(entry)

    # Update service counts
    if service_id:
        counts = analytics["service_counts"]
        counts[service_id] = counts.get(service_id, 0) + 1

    # Update daily counts
    daily = analytics["daily_counts"]
    daily[today] = daily.get(today, 0) + 1

    # Track errors
    if error:
        analytics["errors"].append({
            "timestamp": datetime.now().isoformat(),
            "error": error[:200],
            "service_id": service_id,
        })

    # Trim request log to last 1000 entries
    analytics["requests"] = analytics["requests"][-1000:]
    analytics["errors"] = analytics["errors"][-100:]

    _save_analytics(analytics)


def get_usage_summary() -> str:
    """Get a summary of usage analytics.

    Returns:
        Formatted summary text.
    """
    analytics = _load_analytics()
    total_requests = len(analytics.get("requests", []))
    service_counts = analytics.get("service_counts", {})
    errors = analytics.get("errors", [])
    daily = analytics.get("daily_counts", {})

    lines = ["📊 Thursday Usage Analytics", ""]

    if total_requests == 0:
        lines.append("No usage data recorded yet.")
        return "\n".join(lines)

    lines.append(f"Total requests: {total_requests}")
    lines.append(f"Total errors: {len(errors)}")
    lines.append(f"Active days: {len(daily)}")

    if service_counts:
        lines.append("\nMost used services:")
        top_services = sorted(service_counts.items(), key=lambda x: -x[1])[:5]
        for service, count in top_services:
            pct = round(count / total_requests * 100, 1)
            lines.append(f"  - {service}: {count} ({pct}%)")

    if errors:
        lines.append(f"\nError rate: {round(len(errors) / total_requests * 100, 1)}%")
        # Show recent errors
        recent = errors[-3:]
        lines.append("Recent errors:")
        for e in recent:
            lines.append(f"  - {str(e.get('error', ''))[:60]}")

    return "\n".join(lines)
