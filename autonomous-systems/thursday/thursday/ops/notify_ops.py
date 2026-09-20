"""Proactive push notifications via ntfy (founder request, 2026-09-02).

Closes a real, previously-named gap: Thursday's monitor.py already runs
real background checks (stale leads, overdue invoices, financial health,
etc.) and already publishes them to the internal EventBus as
PROACTIVE_ALERT events -- but until now, nothing outside this process
ever saw them. The founder had to remember to ask "what's pending" to
find out anything went wrong. This subscribes a real push notification to
that same, already-existing EventBus so a critical/warning alert reaches
the phone the moment it's raised, not only when asked.

ntfy (https://ntfy.sh, MIT-licensed, self-hostable) chosen for the same
reasons as Tavily in research_ops.py: minimal, a single HTTP POST, no
account/SDK required, and works with the free public instance out of the
box. Configure via two env vars in Audio_Too/.env:
  NTFY_TOPIC        -- required. A real ntfy topic name (pick something
                        unguessable -- anyone who knows the topic name can
                        read/send to it on the public server). No default;
                        this module degrades honestly, never silently
                        sends nowhere.
  NTFY_SERVER_URL    -- optional, defaults to https://ntfy.sh (the public
                        instance). Set this to a self-hosted server URL
                        instead if privacy of alert content matters more
                        than convenience.

Setup on the phone: install the ntfy app (iOS/Android), subscribe to the
same topic name as NTFY_TOPIC.

**What this deliberately does NOT do:** decide alert severity or content
-- that's monitor.py's existing, already-tested logic. This module is
purely a delivery mechanism: real alerts in, a real push notification
out, or an honest "not configured" if NTFY_TOPIC is unset. Info-severity
alerts are not pushed (would be noise on every background check pass);
only warning/critical.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_DEFAULT_NTFY_SERVER = "https://ntfy.sh"

_SEVERITY_TO_NTFY_PRIORITY = {"critical": "urgent", "warning": "high", "info": "default"}
_SEVERITY_TO_TAG = {"critical": "rotating_light", "warning": "warning", "info": "information_source"}


def _topic() -> str | None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    return topic or None


def _server_url() -> str:
    return os.environ.get("NTFY_SERVER_URL", "").strip() or _DEFAULT_NTFY_SERVER


def send_push_notification(
    title: str, message: str, *, priority: str = "default", tags: list[str] | None = None,
) -> dict:
    """Real HTTP POST to ntfy. Returns {"ok": bool, "error": str | None}.
    Never raises -- network/config failures are returned as a typed
    error, matching this codebase's client.py convention.
    """
    topic = _topic()
    if topic is None:
        return {
            "ok": False,
            "error": (
                "Evidence missing — push notifications not configured. "
                "Add NTFY_TOPIC to Audio_Too/.env (pick an unguessable topic "
                "name), then subscribe to that topic in the ntfy app on your phone."
            ),
        }

    url = f"{_server_url().rstrip('/')}/{topic}"
    headers = {
        "Title": title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)

    request = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"ntfy API error ({exc.code}): {exc.reason}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": f"Push notification failed: {exc}"}

    return {"ok": True, "error": None}


def notify_from_alert(alert: dict) -> dict:
    """Formats one monitor.py alert dict (see monitor._make_alert) into a
    push notification. Only warning/critical severities are pushed --
    info-level alerts would fire on every background check pass and
    become noise, defeating the point of a push channel.
    """
    severity = alert.get("severity", "info").lower()
    if severity not in ("warning", "critical"):
        return {"ok": False, "error": f"Severity '{severity}' is not pushed (only warning/critical)."}

    alert_type = alert.get("type", "alert").replace("_", " ").title()
    title = f"Thursday: {alert_type}"
    priority = _SEVERITY_TO_NTFY_PRIORITY.get(severity, "default")
    tags = [_SEVERITY_TO_TAG.get(severity, "information_source")]
    return send_push_notification(title, alert.get("message", ""), priority=priority, tags=tags)


def _alert_push_handler(event) -> None:
    result = notify_from_alert(event.payload)
    if not result["ok"] and "not configured" not in (result.get("error") or ""):
        logger.warning("notify_ops: push notification failed: %s", result.get("error"))


def register_alert_push_handler() -> None:
    """Subscribes a push-notification handler to the real, already-
    existing EventBus PROACTIVE_ALERT topic (see monitor.run_checks(),
    which already publishes every new alert there). Call once at server
    startup, alongside start_background_monitor(). Module-level handler
    (not a closure) so tests can unsubscribe it via unregister_alert_push_handler()
    and avoid leaking a subscription onto the shared EventBus singleton
    across test runs.
    """
    from thursday.events import get_event_bus

    get_event_bus().subscribe("PROACTIVE_ALERT", _alert_push_handler)


def unregister_alert_push_handler() -> None:
    from thursday.events import get_event_bus

    get_event_bus().unsubscribe("PROACTIVE_ALERT", _alert_push_handler)


_NOTIFY_ME_PREFIXES = ["notify me:", "send notification:", "push notification:", "send me a notification:"]


def parse_notify_me_command(text: str) -> str | None:
    """Manual test/ad-hoc push -- returns the message tail, or None if
    this isn't a notify-me command or the tail is empty (no sensible
    default message to send).
    """
    stripped = text.strip()
    lower = stripped.lower()
    for prefix in sorted(_NOTIFY_ME_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix.lower()):
            tail = stripped[len(prefix):].strip()
            return tail or None
    return None


def render_notify_result(result: dict) -> str:
    if result["ok"]:
        return "Notification sent."
    return f"NOTIFICATION\n\n{result['error']}"
