"""Tests for portfolio publishing helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import portfolio_ops  # noqa: E402


def test_public_project_entry_excludes_private_client_fields() -> None:
    entry = portfolio_ops.public_project_entry(
        {
            "project": "Secret Client Mix",
            "client": "Private Client",
            "service": "Mixing",
            "waiting_on": "client payment",
            "follow_up": "private note",
        }
    )

    text = " ".join(str(value) for value in entry.values())
    assert "Private Client" not in text
    assert "client payment" not in text
    assert entry["title"] == "Secret Client Mix"
    assert "Mixing" in entry["tags"]


def test_candidate_projects_uses_completed_projects(monkeypatch) -> None:
    monkeypatch.setattr(
        portfolio_ops,
        "load_data",
        lambda: {"codebases": [], "audio": [], "stats": []},
    )
    monkeypatch.setattr(
        portfolio_ops,
        "list_records",
        lambda table: [
            {
                "id": "p1",
                "project": "Delivered Mix",
                "client": "Private",
                "service": "Mixing",
                "status": "Delivered",
                "source": "Website",
            }
        ]
        if table == "projects"
        else [],
    )

    items = portfolio_ops.candidate_projects()

    assert len(items) == 1
    assert items[0]["id"] == "p1"
    assert "client" in items[0]["private_fields_excluded"]


def test_discover_audio_files_marks_published(tmp_path, monkeypatch) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    wav = audio_dir / "new-demo.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(portfolio_ops, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(
        portfolio_ops,
        "load_data",
        lambda: {
            "codebases": [],
            "audio": [{"src": "/portfolio/audio/new-demo.wav"}],
            "stats": [],
        },
    )

    files = portfolio_ops.discover_audio_files()

    assert files[0]["filename"] == "new-demo.wav"
    assert files[0]["published"] is True
