#!/usr/bin/env python3
"""Tool definitions for agent function calling.

Each tool is a callable the agent can invoke. The tool registry maps tool
names to schemas and handlers. This is intentionally small and local-friendly.
"""

from __future__ import annotations

from typing import Any, Callable


class Tool:
    def __init__(self, name: str, description: str, schema: dict[str, Any], handler: Callable[..., str]):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler


# Shared tool implementations

def _ensure_leads_dir(ROOT):
    leads = ROOT / "leads"
    leads.mkdir(parents=True, exist_ok=True)
    return leads


def tool_marketing_new_lead(ROOT, **kwargs):
    name = kwargs.get("name", "[Lead]")
    contact = kwargs.get("contact", "")
    service = kwargs.get("service", "[Service]")
    status = kwargs.get("status", "New")
    next_action = kwargs.get("next_action", "Research and draft personalized outreach")
    leads = _ensure_leads_dir(ROOT)
    content = (
        f"Lead: {name}\n"
        f"Contact: {contact}\n"
        f"Type: {kwargs.get('type', 'prospect')}\n"
        f"Service fit: {service}\n"
        f"Status: {status}\n"
        f"Source: {kwargs.get('source', 'agent-tool')}\n"
        f"Next action: {next_action}\n"
        f"Waiting on: [Waiting on]\n"
        f"Follow up: [Follow up]\n"
        f"Notes: Created by agent tool call.\n"
    )
    path = leads / f"{name.lower().replace(' ', '-')}-{service.lower().replace(' ', '-')}.md"
    path.write_text(content, encoding="utf-8")
    return f"Created lead: {path}"


def tool_admin_new_client(ROOT, **kwargs):
    from Shared.data_store import add_record
    name = kwargs.get("name", "[Client]")
    contact = kwargs.get("contact", "[Contact]")
    status = kwargs.get("status", "Active")
    add_record("clients", {"name": name, "contact": contact, "status": status, "notes": "Created by agent tool call"})
    return f"Created client: {name} / {contact} / status {status}"


def tool_admin_save_project_note(ROOT, **kwargs):
    from Shared.data_store import add_record
    client = kwargs.get("client", "[Client]")
    project = kwargs.get("project", "[Project]")
    service = kwargs.get("service", "[Service]")
    status = kwargs.get("status", "Open")
    deadline = kwargs.get("deadline", "[Deadline]")
    waiting_on = kwargs.get("waiting_on", "")
    next_action = kwargs.get("next_action", "")
    PROJECTS = ROOT / "projects"
    PROJECTS.mkdir(parents=True, exist_ok=True)
    content = (
        f"Project: {project}\nClient: {client}\nService: {service}\nStatus: {status}\n"
        f"Deadline: {deadline}\nBudget/Rate: [Budget/Rate]\nPayment status: [Payment status]\n"
        f"Files received: [Files received]\nFiles needed: [Files needed]\n"
        f"Revision status: [Revision status]\nNext action: {next_action}\nWaiting on: {waiting_on}\n"
        "Internal notes: Created by agent tool call.\n"
    )
    path = PROJECTS / f"{client.lower().replace(' ', '-')}-{project.lower().replace(' ', '-')}.md"
    path.write_text(content, encoding="utf-8")
    add_record(
        "projects",
        {
            "client": client,
            "project": project,
            "service": service,
            "status": status,
            "deadline": deadline,
            "waiting_on": waiting_on,
            "follow_up": "",
            "next_action": next_action,
            "source_file": str(path.relative_to(ROOT)),
        },
    )
    return f"Saved project note: {path}"


def tool_list_leads(ROOT, **kwargs):
    from Shared.data_store import list_records
    records = list_records("leads")
    if not records:
        return "No leads found."
    return "\n".join(
        f"- {r.get('lead')}: {r.get('service_fit')} / {r.get('status')} / next: {r.get('next_action')}"
        for r in records
    )


def tool_list_projects(ROOT, **kwargs):
    from Shared.data_store import list_records
    records = list_records("projects")
    if not records:
        return "No projects found."
    return "\n".join(
        f"- {r.get('project')}: {r.get('client')} / {r.get('service')} / {r.get('status')}"
        for r in records
    )


TOOL_REGISTRY = {
    "marketing.new_lead": Tool(
        name="marketing.new_lead",
        description="Create a new marketing lead record.",
        schema={"name": "string", "contact": "string", "service": "string", "status": "string"},
        handler=lambda **kw: "ROOT_REQUIRED",
    ),
    "admin.new_client": Tool(
        name="admin.new_client",
        description="Create a new client record.",
        schema={"name": "string", "contact": "string", "status": "string"},
        handler=lambda **kw: "ROOT_REQUIRED",
    ),
    "admin.save_project": Tool(
        name="admin.save_project",
        description="Save a project note.",
        schema={"client": "string", "project": "string", "service": "string", "status": "string", "deadline": "string", "next_action": "string"},
        handler=lambda **kw: "ROOT_REQUIRED",
    ),
    "shared.list_leads": Tool(
        name="shared.list_leads",
        description="List marketing leads.",
        schema={},
        handler=lambda **kw: "ROOT_REQUIRED",
    ),
    "shared.list_projects": Tool(
        name="shared.list_projects",
        description="List projects.",
        schema={},
        handler=lambda **kw: "ROOT_REQUIRED",
    ),
}


def get_tool(name: str):
    return TOOL_REGISTRY.get(name)


def execute_tool(name: str, root, **kwargs):
    if name == "marketing.new_lead":
        return tool_marketing_new_lead(root, **kwargs)
    if name == "admin.new_client":
        return tool_admin_new_client(root, **kwargs)
    if name == "admin.save_project":
        return tool_admin_save_project_note(root, **kwargs)
    if name == "shared.list_leads":
        return tool_list_leads(root, **kwargs)
    if name == "shared.list_projects":
        return tool_list_projects(root, **kwargs)
    return f"Unknown tool: {name}"