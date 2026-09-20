"""Tests for the shared song-lifecycle Project entity (Phase 2 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md)."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))


def _init_db(tmp_path, monkeypatch):
    import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    db.init_db()
    return db


def test_create_project_mints_id_and_persists(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project(title="Neon Skies")
    assert project["id"].startswith("kenn-")
    assert project["title"] == "Neon Skies"
    assert project["crm_project_id"] is None

    fetched = song_projects.get_project(project["id"])
    assert fetched == project


def test_get_project_returns_none_for_unknown_id(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    assert song_projects.get_project("does-not-exist") is None
    assert song_projects.get_project("") is None


def test_two_projects_get_distinct_ids(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    a = song_projects.create_project()
    b = song_projects.create_project()
    assert a["id"] != b["id"]


def test_link_to_crm_requires_existing_project(tmp_path, monkeypatch) -> None:
    db = _init_db(tmp_path, monkeypatch)
    import song_projects

    assert song_projects.link_to_crm("missing-project", "crm-1") is False

    project = song_projects.create_project()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO projects
               (id, client, project, service, status, deadline, waiting_on, follow_up,
                next_action, source, created_at, updated_at)
               VALUES ('crm-1', 'Jordan', 'EP mix', 'Mixing', 'Open', '', '', '', '',
                       'test', '2026-08-05', '2026-08-05')"""
        )
        conn.commit()

    assert song_projects.link_to_crm(project["id"], "crm-1") is True
    fetched = song_projects.get_project(project["id"])
    assert fetched["crm_project_id"] == "crm-1"


def test_new_project_has_no_reference_track(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    assert project["reference_track_id"] is None
    assert song_projects.get_project(project["id"])["reference_track_id"] is None


def test_set_reference_track_requires_existing_project(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    assert song_projects.set_reference_track("missing-project", "ref-1") is False

    project = song_projects.create_project()
    assert song_projects.set_reference_track(project["id"], "ref-1") is True
    assert song_projects.get_project(project["id"])["reference_track_id"] == "ref-1"


def test_get_revision_history_is_empty_for_a_fresh_project(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    assert song_projects.get_revision_history(project["id"]) == []


def test_record_revision_request_is_recalled_newest_first(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    song_projects.record_revision_request(project["id"], "make the vocal louder")
    song_projects.record_revision_request(project["id"], "add reverb to the snare")

    history = song_projects.get_revision_history(project["id"])
    assert [h["feedback_text"] for h in history] == [
        "add reverb to the snare",
        "make the vocal louder",
    ]


def test_record_revision_request_ignores_blank_feedback(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    song_projects.record_revision_request(project["id"], "   ")
    assert song_projects.get_revision_history(project["id"]) == []


def test_record_revision_request_noops_on_empty_project_id(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    # Should not raise even though no project exists.
    song_projects.record_revision_request("", "make it louder")


def test_get_revision_history_respects_limit(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    for i in range(5):
        song_projects.record_revision_request(project["id"], f"change {i}")

    history = song_projects.get_revision_history(project["id"], limit=2)
    assert len(history) == 2
    assert history[0]["feedback_text"] == "change 4"


def test_new_revision_request_has_empty_outcome(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    song_projects.record_revision_request(project["id"], "make it brighter")

    history = song_projects.get_revision_history(project["id"])
    assert history[0]["outcome"] == ""


def test_record_revision_request_returns_the_new_row_id(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    revision_id = song_projects.record_revision_request(project["id"], "make it brighter")

    assert isinstance(revision_id, int)
    assert song_projects.record_revision_request("", "no project") is None
    assert song_projects.record_revision_request(project["id"], "   ") is None


def test_record_revision_outcome_kept(tmp_path, monkeypatch) -> None:
    # §13.6.2 (docs/KENN_FUTURE_PLAN.md): "applied revisions log --
    # track what KENN applied + whether you kept it."
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    revision_id = song_projects.record_revision_request(project["id"], "make it brighter")

    assert song_projects.record_revision_outcome(revision_id, "kept") is True
    history = song_projects.get_revision_history(project["id"])
    assert history[0]["outcome"] == "kept"


def test_record_revision_outcome_reverted(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    revision_id = song_projects.record_revision_request(project["id"], "make it brighter")

    assert song_projects.record_revision_outcome(revision_id, "reverted") is True
    history = song_projects.get_revision_history(project["id"])
    assert history[0]["outcome"] == "reverted"


def test_record_revision_outcome_rejects_invalid_values(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    project = song_projects.create_project()
    revision_id = song_projects.record_revision_request(project["id"], "make it brighter")

    assert song_projects.record_revision_outcome(revision_id, "maybe") is False
    assert song_projects.get_revision_history(project["id"])[0]["outcome"] == ""


def test_record_revision_outcome_returns_false_for_unknown_id(tmp_path, monkeypatch) -> None:
    _init_db(tmp_path, monkeypatch)
    import song_projects

    song_projects.create_project()
    assert song_projects.record_revision_outcome(999999, "kept") is False
