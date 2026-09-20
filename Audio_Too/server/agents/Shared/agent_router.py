"""Route plain-English requests to Admin or Marketing agent commands."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from Shared.activity_log import log_event


ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
LEGACY_PYTHON = ROOT / ".venv" / "bin" / "python"

ADMIN_HINTS = (
    "invoice",
    "quote",
    "client",
    "session",
    "project",
    "stem",
    "stems",
    "payment",
    "mastering",
    "mixing",
)

MARKETING_HINTS = (
    "outreach",
    "marketing",
    "lead",
    "leads",
    "campaign",
    "post",
    "social",
    "offer",
    "artist",
    "podcaster",
)

# These hints name the marketing action itself (each has its own routing
# branch below), unlike generic business nouns like "client"/"mastering"
# that describe the subject of a request but say nothing about whether the
# request IS marketing or admin work. A request mentioning one of these is
# marketing regardless of how many generic Admin nouns it also contains —
# e.g. "send a mastering offer to the new client" scores 2 Admin hints
# ("mastering", "client") vs. 1 Marketing hint ("offer"), which used to
# silently misroute it to Admin's session-prep checklist.
STRONG_MARKETING_ACTIONS = ("offer", "campaign", "post", "social", "outreach")

ADMIN_ALIASES = {
    "projects": "list-projects",
    "list": "list-projects",
    "clients": "clients",
    "records": "records",
    "invoices": "invoices",
    "export-invoices": "export-invoices",
    "export-invoices-xlsx": "export-invoices-xlsx",
    "save-invoice": "save-invoice",
    "update-invoice": "update-invoice",
    "update-project": "update-project",
    "follow-up": "followups",
    "follow-ups": "followups",
}

MARKETING_ALIASES = {
    "leads": "list-leads",
    "list": "list-leads",
    "pipeline": "pipeline",
    "export-leads": "export-leads",
    "export-leads-xlsx": "export-leads-xlsx",
    "update-lead": "update-lead",
    "score-leads": "score-leads",
    "sequence": "sequence",
    "follow-up": "followups",
    "follow-ups": "followups",
}

READ_ONLY_COMMANDS = {
    "list-projects",
    "projects",
    "list",
    "clients",
    "records",
    "invoices",
    "export-invoices",
    "export-invoices-xlsx",
    "followups",
    "weekly",
    "list-leads",
    "pipeline",
    "export-leads",
    "export-leads-xlsx",
    "score-leads",
    "sequence",
    "--help",
    "-h",
    "help",
}

# Dashboard web API: read-only listing plus draft-generating commands only.
DASHBOARD_ALLOWED_COMMANDS = READ_ONLY_COMMANDS | {
    "email",
    "outreach",
    "post",
    "offer",
    "campaign",
}


def python_cmd() -> str:
    if PYTHON.exists():
        return str(PYTHON)
    if LEGACY_PYTHON.exists():
        return str(LEGACY_PYTHON)
    return sys.executable


def route_request(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()
    marketing_score = sum(1 for hint in MARKETING_HINTS if hint in lowered)
    admin_score = sum(1 for hint in ADMIN_HINTS if hint in lowered)
    has_strong_marketing_action = any(hint in lowered for hint in STRONG_MARKETING_ACTIONS)

    if has_strong_marketing_action or marketing_score > admin_score:
        if "post" in lowered or "social" in lowered:
            return "Marketing", ["post", text]
        if "campaign" in lowered:
            return "Marketing", ["campaign", text]
        if "offer" in lowered:
            return "Marketing", ["offer", text]
        return "Marketing", ["outreach", text]

    return "Admin", ["auto", text]


def normalize_args(folder: str, args: list[str]) -> list[str]:
    if not args:
        return ["--help"]
    if folder == "Admin":
        return [ADMIN_ALIASES.get(args[0], args[0]), *args[1:]]
    if folder == "Marketing":
        return [MARKETING_ALIASES.get(args[0], args[0]), *args[1:]]
    return args


def should_log_agent_command(command: str) -> bool:
    return command.lower() not in READ_ONLY_COMMANDS


def resolve_admin_auto_command(task: str) -> str:
    from Admin.local_agent import classify_task_auto

    return classify_task_auto(task).lower()


def dashboard_command_allowed(folder: str, args: list[str], task: str) -> tuple[bool, str]:
    if not args:
        return False, "No command specified."
    command_name = args[0].lower()
    if command_name == "auto":
        if folder != "Admin":
            return False, "Auto routing is only supported for the Admin agent from the dashboard."
        command_name = resolve_admin_auto_command(task)
    if command_name not in DASHBOARD_ALLOWED_COMMANDS:
        return False, (
            f"Command '{command_name}' is not allowed from the dashboard. "
            "Use the CLI for writes (invoices, new clients, updates)."
        )
    return True, command_name


def run_agent_task(text: str, *, agent: str = "auto", source: str = "cli") -> dict:
    task = text.strip()
    if not task:
        return {"ok": False, "error": "Task text is required."}

    choice = agent.strip().lower()
    if choice in {"admin", "a"}:
        folder, args = "Admin", ["auto", task]
    elif choice in {"marketing", "market", "m"}:
        folder, args = "Marketing", ["outreach", task]
    else:
        folder, args = route_request(task)

    args = normalize_args(folder, args)
    if source == "dashboard":
        allowed, message = dashboard_command_allowed(folder, args, task)
        if not allowed:
            return {
                "ok": False,
                "error": message,
                "agent": folder.lower(),
                "command": args[0].lower(),
            }
        command_name = message
    else:
        command_name = args[0].lower()
    detail = " ".join(args[1:]).strip()
    if len(detail) > 180:
        detail = detail[:177] + "..."

    command = [python_cmd(), str(ROOT / folder / "main.py"), *args]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    output = (completed.stdout or "").strip()
    if completed.stderr:
        err = completed.stderr.strip()
        output = f"{output}\n{err}".strip() if output else err

    if completed.returncode == 0 and should_log_agent_command(command_name):
        actor = folder.lower()
        summary = command_name if not detail else f"{command_name}: {detail}"
        log_event(f"{actor}_command", summary, actor="dashboard")

    return {
        "ok": completed.returncode == 0,
        "agent": folder.lower(),
        "command": command_name,
        "output": output or "(no output)",
    }
