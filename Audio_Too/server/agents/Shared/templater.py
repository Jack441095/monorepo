"""Template management for Audio_Too agents.

Lists, shows, and manages templates across Admin and Marketing agents.
Templates are .md files stored in agent-specific template directories.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_DIRS = {
    "Admin": ROOT / "Admin" / "templates",
    "Marketing": ROOT / "Marketing" / "templates",
    "Admin/Workflow": ROOT / "Admin" / "workflows",
}

AGENT_LABELS = {
    "Admin": "Admin templates",
    "Marketing": "Marketing templates",
    "Admin/Workflow": "Admin workflows",
}


def discover_templates() -> dict[str, list[dict]]:
    """Discover all templates across agent directories.

    Returns:
        {agent_label: [{"name": str, "path": Path, "agent": str}, ...]}
    """
    result: dict[str, list[dict]] = {}
    for agent_key, template_dir in TEMPLATE_DIRS.items():
        if not template_dir.is_dir():
            continue
        templates = []
        for fpath in sorted(template_dir.iterdir()):
            if fpath.suffix in (".md", ".txt") and not fpath.name.startswith("."):
                templates.append({
                    "name": fpath.stem,
                    "filename": fpath.name,
                    "path": fpath,
                    "agent": agent_key,
                })
        if templates:
            result[AGENT_LABELS.get(agent_key, agent_key)] = templates
    return result


def list_templates() -> str:
    """List all available templates grouped by agent."""
    grouped = discover_templates()
    if not grouped:
        return "No templates found."

    lines = ["\U0001f4c4 Available Templates", "=" * 40]
    for label, templates in grouped.items():
        lines.append(f"\n{label}:")
        for t in templates:
            lines.append(f"  - {t['name']} ({t['filename']})")
    lines.append(f"\nTotal: {sum(len(v) for v in grouped.values())} templates")
    return "\n".join(lines)


def show_template(name: str) -> str:
    """Show a template's content by name (matches stem, case-insensitive)."""
    grouped = discover_templates()
    needle = name.strip().lower()

    for templates in grouped.values():
        for t in templates:
            if t["name"].lower() == needle:
                content = t["path"].read_text(encoding="utf-8")
                return (
                    f"Template: {t['name']} ({t['agent']})\n"
                    f"File: {t['path']}\n"
                    f"{'=' * 50}\n"
                    f"{content}"
                )

    # Try partial match
    for templates in grouped.values():
        for t in templates:
            if needle in t["name"].lower():
                content = t["path"].read_text(encoding="utf-8")
                return (
                    f"Template: {t['name']} ({t['agent']})\n"
                    f"File: {t['path']}\n"
                    f"{'=' * 50}\n"
                    f"{content}"
                )

    return f"Template not found: {name}. Use `./agent templates` to list available templates."


def create_template(name: str, content: str, agent: str = "Admin") -> str:
    """Create a new template file.

    Args:
        name: Template name (without extension)
        content: Template content
        agent: "Admin" or "Marketing" or "Admin/Workflow"

    Returns:
        Success or error message.
    """
    agent_key = None
    for key in TEMPLATE_DIRS:
        if key.lower() == agent.lower():
            agent_key = key
            break
        # Also match "admin" -> "Admin", "marketing" -> "Marketing"
        if key.split("/")[0].lower() == agent.lower():
            agent_key = key
            break

    if not agent_key:
        valid = ", ".join(TEMPLATE_DIRS.keys())
        return f"Unknown agent: {agent}. Valid options: {valid}"

    template_dir = TEMPLATE_DIRS[agent_key]
    template_dir.mkdir(parents=True, exist_ok=True)

    # Sanitise name
    safe_name = name.strip().lower().replace(" ", "_").replace("/", "_")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
    if not safe_name:
        return "Invalid template name."

    fpath = template_dir / f"{safe_name}.md"
    if fpath.exists():
        return f"Template already exists: {fpath.name}"

    # Add header if not present
    if not content.startswith("# "):
        header = f"# {name.strip()} Template\n\n"
        content = header + content

    fpath.write_text(content.strip() + "\n", encoding="utf-8")
    return f"Created template: {fpath}"


def delete_template(name: str, agent: str | None = None) -> str:
    """Delete a template by name.

    Args:
        name: Template name (stem or filename)
        agent: Optional agent filter ("Admin", "Marketing")

    Returns:
        Success or error message.
    """
    grouped = discover_templates()
    needle = name.strip().lower()

    found = None
    for label, templates in grouped.items():
        for t in templates:
            if t["name"].lower() == needle or t["filename"].lower() == needle:
                if agent and agent.lower() not in label.lower():
                    continue
                found = t
                break
        if found:
            break

    if not found:
        msg = f"Template not found: {name}"
        if agent:
            msg += f" in {agent}"
        return msg

    found["path"].unlink()
    return f"Deleted template: {found['filename']} ({found['agent']})"
