"""Proactive Monitoring Service — checks for stale leads, overdue invoices,
expiring links, new enquiries, and financial warnings.

Generates alerts stored in Thursday/alerts/ that are prepended on the
next user request.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from thursday.atomic_io import atomic_write

logger = logging.getLogger(__name__)

from thursday.runtime_paths import ALERTS_DIR
try:
    CHECK_INTERVAL_MINUTES = max(1, int(os.environ.get("THURSDAY_CHECK_INTERVAL_MINUTES", "30")))
except ValueError:
    CHECK_INTERVAL_MINUTES = 30


# ─── Alert Schema ────────────────────────────────────────────────────────


def _make_alert(
    alert_type: str,
    severity: str,
    message: str,
    item_id: str | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4())[:12],
        "type": alert_type,
        "severity": severity,
        "message": message,
        "item_id": item_id or "",
        "created_at": datetime.now().isoformat(),
        "acknowledged": False,
    }


# ─── Alert Storage ───────────────────────────────────────────────────────


def _alert_path() -> Path:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    return ALERTS_DIR / "alerts.json"


def _load_alerts() -> list[dict]:
    path = _alert_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_alerts(alerts: list[dict]) -> None:
    path = _alert_path()
    try:
        atomic_write(path, json.dumps(alerts, indent=2))
    except OSError:
        pass


# ─── Check Functions ─────────────────────────────────────────────────────


def _check_stale_leads(list_records: Callable, days: int = 7) -> list[dict]:
    """Check for leads not touched in >days."""
    alerts = []
    try:
        leads = list_records("leads")
        now = datetime.now()
        for lead in leads:
            if (lead.get("status") or "").lower() in {"closed", "converted", "lost", "not interested"}:
                continue
            last_touch = lead.get("last_contacted_at") or lead.get("created_at")
            if last_touch:
                try:
                    last_date = datetime.fromisoformat(last_touch.replace("Z", "+00:00"))
                    # Handle timezone-naive comparison
                    if last_date.tzinfo:
                        now_compare = datetime.now(last_date.tzinfo)
                    else:
                        now_compare = now
                    if (now_compare - last_date).days > days:
                        name = lead.get("name", lead.get("id", "unknown"))
                        alerts.append(_make_alert(
                            "stale_lead",
                            "warning",
                            f"Lead '{name}' hasn't been contacted in {days}+ days.",
                            lead.get("id"),
                        ))
                except (ValueError, TypeError):
                    continue
    except Exception:
        logger.warning("_check_stale_leads failed; skipping this check", exc_info=True)
    return alerts


def _check_overdue_invoices(list_records: Callable) -> list[dict]:
    """Check for invoices past their due date."""
    alerts = []
    try:
        invoices = list_records("invoices")
        now = datetime.now()
        for inv in invoices:
            due_date = inv.get("due_date")
            status = (inv.get("status") or "").lower()
            if due_date and status not in ("paid", "cancelled", "void"):
                try:
                    due = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    if due.tzinfo:
                        now_compare = datetime.now(due.tzinfo)
                    else:
                        now_compare = now
                    if now_compare > due:
                        days_overdue = (now_compare - due).days
                        client = inv.get("client_name", inv.get("client", "unknown"))
                        amount = inv.get("total", inv.get("amount", "?"))
                        alerts.append(_make_alert(
                            "overdue_invoice",
                            "critical" if days_overdue > 30 else "warning",
                            f"Invoice for {client} ({amount}) is {days_overdue} days overdue.",
                            inv.get("id"),
                        ))
                except (ValueError, TypeError):
                    continue
    except Exception:
        logger.warning("_check_overdue_invoices failed; skipping this check", exc_info=True)
    return alerts


def _check_new_enquiries(list_records: Callable, hours: int = 24) -> list[dict]:
    """Check for unread enquiries older than hours."""
    alerts = []
    try:
        enquiries = list_records("enquiries")
        now = datetime.now()
        for enq in enquiries:
            status = (enq.get("status") or "New").lower()
            created = enq.get("created_at")
            if status == "new" and created:
                try:
                    created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if created_date.tzinfo:
                        now_compare = datetime.now(created_date.tzinfo)
                    else:
                        now_compare = now
                    hours_old = (now_compare - created_date).total_seconds() / 3600
                    if hours_old > hours:
                        name = enq.get("name", "Unknown")
                        service = enq.get("service", "?")
                        alerts.append(_make_alert(
                            "new_enquiry",
                            "info",
                            f"New enquiry from {name} ({service}) — {int(hours_old)}h old.",
                            enq.get("id"),
                        ))
                except (ValueError, TypeError):
                    continue
    except Exception:
        logger.warning("_check_new_enquiries failed; skipping this check", exc_info=True)
    return alerts


def _check_expiring_links(list_records: Callable, hours: int = 48) -> list[dict]:
    """Check session/stem upload links that expire soon."""
    alerts = []
    now = datetime.now()
    try:
        for session in list_records("sessions"):
            expiry_value = (
                session.get("upload_expires_at")
                or session.get("stem_link_expires_at")
                or session.get("expires_at")
            )
            if not expiry_value or not (session.get("upload_link") or session.get("stem_link")):
                continue
            try:
                expiry = datetime.fromisoformat(str(expiry_value).replace("Z", "+00:00"))
                now_compare = datetime.now(expiry.tzinfo) if expiry.tzinfo else now
                remaining = (expiry - now_compare).total_seconds() / 3600
                if 0 <= remaining <= hours:
                    label = session.get("client") or session.get("client_name") or session.get("id", "session")
                    alerts.append(_make_alert(
                        "expiring_link", "warning",
                        f"Stem upload link for {label} expires in {max(1, int(remaining))}h.",
                        session.get("id"),
                    ))
            except (TypeError, ValueError):
                continue
    except Exception:
        logger.warning("_check_expiring_links failed; skipping this check", exc_info=True)
        return []
    return alerts


def _check_financial_health(list_records: Callable) -> list[dict]:
    """Check for financial warnings (expenses > revenue for 2+ months)."""
    try:
        monthly: dict[str, dict[str, float]] = {}
        for invoice in list_records("invoices"):
            if (invoice.get("status") or "").lower() not in {"paid", "complete", "completed"}:
                continue
            stamp = str(invoice.get("paid_at") or invoice.get("created_at") or "")[:7]
            if len(stamp) == 7:
                monthly.setdefault(stamp, {"revenue": 0.0, "expenses": 0.0})["revenue"] += _number(
                    invoice.get("total", invoice.get("amount", 0))
                )
        for expense in list_records("expenses"):
            stamp = str(expense.get("date") or expense.get("created_at") or "")[:7]
            if len(stamp) == 7:
                monthly.setdefault(stamp, {"revenue": 0.0, "expenses": 0.0})["expenses"] += _number(
                    expense.get("amount", expense.get("total", 0))
                )
        losing = [month for month, values in sorted(monthly.items()) if values["expenses"] > values["revenue"]]
        if len(losing) >= 2 and losing[-2:] == sorted(monthly)[-2:]:
            months = ", ".join(losing[-2:])
            return [_make_alert(
                "financial_warning", "critical",
                f"Expenses exceeded recorded revenue for two consecutive months ({months}).",
                months,
            )]
    except Exception:
        logger.warning("_check_financial_health failed; skipping this check", exc_info=True)
        return []
    return []


def _number(value: Any) -> float:
    """Parse numeric and currency-formatted record values."""
    try:
        return float(str(value or 0).replace(",", "").replace("£", "").replace("$", "").replace("€", ""))
    except (TypeError, ValueError):
        return 0.0


def _hours_since(timestamp: str, now: datetime) -> float | None:
    """Hours elapsed since an ISO timestamp, or None if unparseable."""
    try:
        stamp = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        now_compare = datetime.now(stamp.tzinfo) if stamp.tzinfo else now
        return (now_compare - stamp).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def _default_list_mix_reviews() -> list[dict]:
    """Lazy import — audio_analysis pulls in torch, must not break alerts if unavailable."""
    try:
        from audio_analysis.mix_review.mix_review import list_reviews
        return list_reviews(limit=50)
    except Exception:
        logger.warning(
            "_default_list_mix_reviews: audio_analysis unavailable, mix-review alerts disabled this pass",
            exc_info=True,
        )
        return []


def _default_list_audiogen_jobs() -> list[dict]:
    """Lazy import — mirrors thursday/client.py's audiogen_render_queue()."""
    try:
        from app.audiogen_bridge import render_queue_snapshot
        return render_queue_snapshot(limit=50).get("recent", [])
    except Exception:
        logger.warning(
            "_default_list_audiogen_jobs: app.audiogen_bridge unavailable, render alerts disabled this pass",
            exc_info=True,
        )
        return []


def _check_flagged_mix_reviews(list_mix_reviews: Callable[[], list[dict]], hours: int = 24) -> list[dict]:
    """Check for mix reviews completed recently that came back with technical flags."""
    alerts = []
    now = datetime.now()
    try:
        for review in list_mix_reviews():
            flags = review.get("flags") or []
            if not flags:
                continue
            hours_old = _hours_since(review.get("created_at", ""), now)
            if hours_old is None or hours_old > hours:
                continue
            title = review.get("title") or review.get("id", "mix review")
            alerts.append(_make_alert(
                "mix_review_flagged", "warning",
                f"Mix review '{title}' flagged {len(flags)} issue(s).",
                review.get("id"),
            ))
    except Exception:
        logger.warning("_check_flagged_mix_reviews failed; skipping this check", exc_info=True)
    return alerts


def _check_finished_renders(list_audiogen_jobs: Callable[[], list[dict]], hours: int = 24) -> list[dict]:
    """Check for AudioGen render jobs that finished or failed recently."""
    alerts = []
    now = datetime.now()
    try:
        for job in list_audiogen_jobs():
            status = (job.get("status") or "").lower()
            if status not in {"completed", "failed"}:
                continue
            hours_old = _hours_since(job.get("finished_at", ""), now)
            if hours_old is None or hours_old > hours:
                continue
            job_id = job.get("id", "")
            emotion = job.get("emotion", "")
            if status == "failed":
                alerts.append(_make_alert(
                    "render_failed", "warning",
                    f"AudioGen render {job_id} ({emotion}) failed: {job.get('error') or 'unknown error'}.",
                    job_id,
                ))
            else:
                alerts.append(_make_alert(
                    "render_finished", "info",
                    f"AudioGen render {job_id} ({emotion}) finished.",
                    job_id,
                ))
    except Exception:
        logger.warning("_check_finished_renders failed; skipping this check", exc_info=True)
    return alerts


# ─── Main Check Runner ───────────────────────────────────────────────────


def run_checks(
    list_records: Callable,
    *,
    list_mix_reviews: Callable[[], list[dict]] | None = None,
    list_audiogen_jobs: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    """Run all monitoring checks and return new alerts."""
    new_alerts = []

    new_alerts.extend(_check_stale_leads(list_records))
    new_alerts.extend(_check_overdue_invoices(list_records))
    new_alerts.extend(_check_new_enquiries(list_records))
    new_alerts.extend(_check_expiring_links(list_records))
    new_alerts.extend(_check_financial_health(list_records))
    new_alerts.extend(_check_flagged_mix_reviews(list_mix_reviews or _default_list_mix_reviews))
    new_alerts.extend(_check_finished_renders(list_audiogen_jobs or _default_list_audiogen_jobs))

    if new_alerts:
        existing = _load_alerts()
        # Keep only unacknowledged alerts that are not duplicates of new alerts
        existing_ids = {a.get("item_id", "") + a.get("type", "") for a in new_alerts}
        unacknowledged = [
            a for a in existing
            if not a.get("acknowledged", False)
            and (a.get("item_id", "") + a.get("type", "")) not in existing_ids
        ]
        all_alerts = unacknowledged + new_alerts
        # Keep last 50
        all_alerts = all_alerts[-50:]
        _save_alerts(all_alerts)

        # Publish new alerts to the EventBus
        try:
            from thursday.events import get_event_bus, Event, EventPriority
            bus = get_event_bus()
            for alert in new_alerts:
                sev = alert.get("severity", "info").lower()
                prio = EventPriority.CRITICAL if sev == "critical" else (EventPriority.HIGH if sev == "warning" else EventPriority.NORMAL)
                bus.publish(Event(
                    event_type="PROACTIVE_ALERT",
                    topic="monitor",
                    priority=prio,
                    payload=alert,
                    source="monitor",
                ))
        except Exception:
            pass

    return new_alerts


def get_pending_alerts() -> list[dict]:
    """Get all unacknowledged alerts."""
    return [a for a in _load_alerts() if not a.get("acknowledged", False)]


def acknowledge_alert(alert_id: str) -> bool:
    """Mark an alert as acknowledged."""
    alerts = _load_alerts()
    for a in alerts:
        if a.get("id") == alert_id:
            a["acknowledged"] = True
            _save_alerts(alerts)
            return True
    return False


def acknowledge_all() -> int:
    """Acknowledge all pending alerts. Returns count."""
    alerts = _load_alerts()
    count = 0
    for a in alerts:
        if not a.get("acknowledged", False):
            a["acknowledged"] = True
            count += 1
    _save_alerts(alerts)
    return count


def format_alerts(alerts: list[dict]) -> str | None:
    """Format pending alerts for display."""
    if not alerts:
        return None

    # Group by severity
    critical = [a for a in alerts if a.get("severity") == "critical"]
    warnings = [a for a in alerts if a.get("severity") == "warning"]
    info = [a for a in alerts if a.get("severity") == "info"]

    parts = []
    if critical:
        parts.append(f"  CRITICAL: {len(critical)}")
        for a in critical[:3]:
            parts.append(f"    - {a['message']}")
    if warnings:
        parts.append(f"  Warnings: {len(warnings)}")
        for a in warnings[:3]:
            parts.append(f"    - {a['message']}")
    if info:
        parts.append(f"  Info: {len(info)}")
        for a in info[:2]:
            parts.append(f"    - {a['message']}")

    summary = f"{len(alerts)} alert(s) since last check."
    if critical:
        summary += f" {len(critical)} critical."
    if warnings:
        summary += f" {len(warnings)} warnings."

    return f"\U0001F4EC {summary}\n{chr(10).join(parts)}"


# Map an alert type to a safe, read-only follow-up Thursday command the user can
# run by simply replying "yes" to the surfaced alert (actionable alerts). Only
# read-only "show me X" commands are offered here, so an affirmative reply can
# never trigger a mutation on its own — the command still routes through normal
# classification (and would hit the confirmation gate if it were ever mutating).
_ALERT_SUGGESTIONS: dict[str, tuple[str, str]] = {
    "mix_review_flagged": ("list mix reviews", "show your flagged mix review"),
    "render_finished": ("list mix reviews", "show your finished renders"),
    "render_failed": ("audiogen status", "show the render status"),
    "overdue_invoice": ("show invoices", "show your overdue invoices"),
    "new_enquiry": ("show enquiries", "show your new enquiries"),
    "stale_lead": ("show pipeline", "show your pipeline"),
    "financial_warning": ("business status", "show your business status"),
}

_ALERT_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


def top_actionable_suggestion(alerts: list[dict]) -> dict | None:
    """Return {"command", "label"} for the highest-severity pending alert that
    has a safe read-only follow-up, or None. Ties break by original order so the
    surfaced suggestion is stable within a check."""
    best = None
    best_rank = 99
    for alert in alerts:
        suggestion = _ALERT_SUGGESTIONS.get(alert.get("type", ""))
        if suggestion is None:
            continue
        rank = _ALERT_SEVERITY_RANK.get(alert.get("severity", "info"), 3)
        if rank < best_rank:
            best_rank = rank
            best = {"command": suggestion[0], "label": suggestion[1]}
    return best


def should_check(last_check_path: Path | None = None) -> bool:
    """Determine if enough time has passed since last check."""
    if last_check_path is None:
        last_check_path = ALERTS_DIR / ".last_check"

    if not last_check_path.exists():
        return True

    try:
        last_check = datetime.fromisoformat(last_check_path.read_text().strip())
        elapsed = (datetime.now() - last_check).total_seconds() / 60
        return elapsed >= CHECK_INTERVAL_MINUTES
    except (ValueError, OSError):
        return True


def mark_checked() -> None:
    """Record that checks were just run."""
    last_check_path = ALERTS_DIR / ".last_check"
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        last_check_path.write_text(datetime.now().isoformat())
    except OSError:
        pass


def _resolve_list_records() -> Callable:
    try:
        from app.db import list_records as _lr

        return _lr
    except ImportError:
        return lambda _: []  # noqa: E731


def _monitor_loop(poll_seconds: float, stop_event) -> None:
    list_records = _resolve_list_records()
    while not stop_event.is_set():
        if should_check():
            try:
                run_checks(list_records)
            except Exception:
                logger.warning("Background monitor run_checks() failed", exc_info=True)
            finally:
                mark_checked()
        stop_event.wait(poll_seconds)


def start_background_monitor(poll_seconds: float = 60.0):
    """Start a daemon thread that runs proactive checks on their own
    schedule, independent of incoming requests.

    Previously proactive checks (stale leads, overdue invoices, expiring
    links, flagged mix reviews, finished renders) only ever fired inline
    from orchestrator.py's handle() when a user happened to send Thursday a
    message and CHECK_INTERVAL_MINUTES had elapsed -- if nobody talks to
    Thursday, checks never ran at all, no matter how overdue an invoice got.
    This thread polls should_check() every ``poll_seconds`` (default 1
    minute) and runs the same run_checks() the inline path uses, so checks
    happen on a real schedule. A failed check run is logged and skipped,
    never crashes the loop.

    Returns the started threading.Thread and a threading.Event that stops
    it when set (used by callers that need a clean shutdown, e.g. tests).
    """
    import threading

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_monitor_loop, args=(poll_seconds, stop_event), daemon=True, name="thursday-monitor"
    )
    thread.start()
    return thread, stop_event
