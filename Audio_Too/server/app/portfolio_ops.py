"""Portfolio publishing helpers for completed work and dropped audio files."""

from __future__ import annotations

import json
import re
from pathlib import Path

from db import list_records

ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_ROOT = ROOT / "portfolio"
DATA_PATH = PORTFOLIO_ROOT / "portfolio_data.json"
AUDIO_DIR = PORTFOLIO_ROOT / "audio"
AUDIO_EXTENSIONS = {".wav", ".wave", ".mp3", ".aiff", ".aif", ".m4a"}


def _clean(value: object) -> str:
    return str(value or "").strip()


def slug_label(path: Path) -> str:
    words = re.sub(r"[-_]+", " ", path.stem).strip()
    return words[:1].upper() + words[1:] if words else path.name


def load_data() -> dict:
    if not DATA_PATH.exists():
        return {"codebases": [], "audio": [], "stats": []}
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    data.setdefault("codebases", [])
    data.setdefault("audio", [])
    data.setdefault("stats", [])
    return data


def save_data(data: dict) -> None:
    PORTFOLIO_ROOT.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def public_project_entry(project: dict) -> dict:
    service = _clean(project.get("service")) or "Audio project"
    title = _clean(project.get("project")) or f"{service} project"
    source = _clean(project.get("source"))
    tags = [service]
    if source:
        tags.append(source)
    tags.extend(["Project workflow", "Client delivery"])
    return {
        "type": service,
        "title": title,
        "description": (
            f"Public-safe case study draft for a {service.lower()} project, focused on workflow, "
            "delivery, and outcome rather than private client details."
        ),
        "tags": list(dict.fromkeys(tags)),
    }


def _is_portfolio_candidate(project: dict) -> bool:
    status = _clean(project.get("status")).lower()
    if status in {"delivered", "complete", "completed", "closed"}:
        return True
    action = _clean(project.get("next_action")).lower()
    return "portfolio" in action


def _existing_titles(data: dict) -> set[str]:
    return {_clean(item.get("title")).lower() for item in data.get("codebases", []) if _clean(item.get("title"))}


def candidate_projects(limit: int = 20) -> list[dict]:
    data = load_data()
    existing = _existing_titles(data)
    out: list[dict] = []
    for project in list_records("projects"):
        if not _is_portfolio_candidate(project):
            continue
        entry = public_project_entry(project)
        if entry["title"].lower() in existing:
            continue
        out.append(
            {
                "id": _clean(project.get("id")),
                "project": _clean(project.get("project")),
                "client": _clean(project.get("client")),
                "service": _clean(project.get("service")),
                "status": _clean(project.get("status")),
                "entry": entry,
                "private_fields_excluded": ["client", "notes", "waiting_on", "follow_up"],
            }
        )
    return out[: max(1, min(100, limit))]


def discover_audio_files() -> list[dict]:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    published = {_clean(item.get("src")) for item in data.get("audio", [])}
    files: list[dict] = []
    for path in sorted(AUDIO_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        src = f"/portfolio/audio/{path.name}"
        files.append(
            {
                "filename": path.name,
                "title": slug_label(path),
                "src": src,
                "published": src in published,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            }
        )
    return files


def snapshot() -> dict:
    data = load_data()
    audio_files = discover_audio_files()
    unpublished_audio = [item for item in audio_files if not item["published"]]
    candidates = candidate_projects()
    return {
        "ok": True,
        "candidates": candidates,
        "audio_files": audio_files,
        "unpublished_audio": unpublished_audio,
        "summary": {
            "candidate_projects": len(candidates),
            "audio_files": len(audio_files),
            "unpublished_audio": len(unpublished_audio),
            "published_audio": len(data.get("audio", [])),
            "published_codebases": len(data.get("codebases", [])),
        },
    }


def publish_project(project_id: str) -> dict:
    project = next((item for item in list_records("projects") if _clean(item.get("id")) == project_id), None)
    if not project:
        return {"ok": False, "error": "Project not found."}
    entry = public_project_entry(project)
    data = load_data()
    existing = _existing_titles(data)
    if entry["title"].lower() in existing:
        return {"ok": False, "error": "Portfolio entry already exists."}
    data.setdefault("codebases", []).append(entry)
    save_data(data)
    return {"ok": True, "entry": entry, "message": f"Portfolio entry published: {entry['title']}"}


def publish_audio(filename: str, title: str = "", description: str = "") -> dict:
    safe_name = Path(filename).name
    path = AUDIO_DIR / safe_name
    if not path.exists() or path.suffix.lower() not in AUDIO_EXTENSIONS:
        return {"ok": False, "error": "Audio file not found in portfolio/audio."}
    src = f"/portfolio/audio/{safe_name}"
    data = load_data()
    if any(_clean(item.get("src")) == src for item in data.get("audio", [])):
        return {"ok": False, "error": "Audio entry already exists."}
    entry = {
        "title": _clean(title) or slug_label(path),
        "description": _clean(description) or "Audio_Too music, mix, master, podcast, or sound design example.",
        "src": src,
    }
    data.setdefault("audio", []).append(entry)
    save_data(data)
    return {"ok": True, "entry": entry, "message": f"Audio entry published: {entry['title']}"}
