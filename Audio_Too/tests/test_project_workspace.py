"""Tests for project workspace aggregation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import project_workspace  # noqa: E402


def test_project_workspace_collects_project_artifacts(monkeypatch) -> None:
    def fake_records(table: str) -> list[dict]:
        if table == "projects":
            return [
                {
                    "id": "proj1",
                    "client": "Jordan",
                    "project": "Wide Vocal Mix",
                    "service": "Mixing",
                    "status": "Active",
                    "source": "",
                }
            ]
        if table == "invoices":
            return [{"id": "inv1", "client": "Jordan", "service": "Mixing", "status": "Draft"}]
        return []

    monkeypatch.setattr(project_workspace, "list_records", fake_records)
    monkeypatch.setattr(
        project_workspace.stem_uploads,
        "list_uploads",
        lambda project_id: [{"id": "up1", "project_id": project_id, "original_name": "stems.zip"}],
    )
    monkeypatch.setattr(
        project_workspace.mix_review,
        "list_reviews",
        lambda limit=100: [{"id": "rev1", "title": "Wide Vocal Mix", "original_name": "mix.wav"}],
    )
    monkeypatch.setattr(
        project_workspace.portfolio_ops,
        "discover_audio_files",
        lambda: [{"name": "wide-vocal-mix-v1.wav", "src": "/portfolio/audio/wide-vocal-mix-v1.wav"}],
    )
    monkeypatch.setattr(
        project_workspace.audiogen_bridge,
        "render_queue_snapshot",
        lambda limit=40: {
            "recent": [
                {
                    "id": "job1",
                    "project_id": "proj1",
                    "status": "completed",
                    "emotion": "joy",
                }
            ]
        },
    )
    monkeypatch.setattr(
        project_workspace.artifact_store,
        "list_for_project",
        lambda project_id: [
            {
                "id": "art1",
                "kind": "audio.generated.full_song",
                "media_type": "audio/wav",
                "content_hash": "sha256:" + "a" * 64,
                "uri": "artifact://art1",
                "producer": "audiogen",
                "producer_version": "1.0.0",
                "project_id": project_id,
                "source_uri": "/portfolio/audio/render.wav",
                "size_bytes": 4,
                "status": "active",
                "parent_ids": (),
                "metadata": {},
                "created_at": "2026-07-02T12:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        project_workspace.event_store,
        "list_for_project",
        lambda project_id, limit=200: [
            {
                "id": "evt1",
                "event_type": "artifact.registered",
                "aggregate_type": "artifact",
                "aggregate_id": "art1",
                "project_id": project_id,
                "correlation_id": "artifact:art1",
                "actor_id": "audiogen",
                "payload": {"kind": "audio.generated.full_song"},
                "schema_version": 1,
                "occurred_at": "2026-07-02T12:00:00Z",
            }
        ],
    )

    result = project_workspace.workspace("proj1")

    assert result["ok"] is True
    assert result["summary"] == {
        "uploads": 1,
        "invoices": 1,
        "mix_reviews": 1,
        "audio": 2,
        "artifacts": 1,
        "events": 1,
    }
    assert result["project"]["project"] == "Wide Vocal Mix"
    assert result["audio"][1]["type"] == "audiogen_job"
    assert result["artifacts"][0]["artifact_id"] == "art1"
    assert result["timeline"][0]["event_type"] == "artifact.registered"
