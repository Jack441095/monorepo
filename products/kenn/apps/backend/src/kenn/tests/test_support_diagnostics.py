from __future__ import annotations

import json
from pathlib import Path

from kenn.core.support_diagnostics import SCHEMA, build_support_diagnostics


def test_support_diagnostics_allowlist_excludes_sensitive_runtime_state(tmp_path: Path) -> None:
    token = "confirm.secret.token"
    private_path = "/Users/example/private-project/song.als"
    project_content = "Client name and unreleased arrangement"
    snapshot = {
        "status": "connected",
        "tracks": [{"index": 0, "name": project_content, "path": private_path}],
        "confirmation_token": token,
        "project_content": project_content,
    }
    result = build_support_diagnostics(live_snapshot=snapshot, repo_root=tmp_path)
    rendered = json.dumps(result)

    assert result["schema"] == SCHEMA
    assert result["ableton"] == {
        "status": "connected",
        "snapshot_available": True,
        "track_count": 1,
    }
    assert token not in rendered
    assert private_path not in rendered
    assert project_content not in rendered
    assert "tracks" not in result


def test_support_diagnostics_reports_only_boolean_repository_checks(tmp_path: Path) -> None:
    result = build_support_diagnostics(repo_root=tmp_path)

    assert result["checks"] == {
        "knowledge_index_available": False,
        "remote_script_source_available": False,
        "audio_retained_by_diagnostics": False,
        "project_content_included": False,
    }
    assert all("/" not in str(value) for value in result["checks"].values())


def test_support_diagnostics_detects_a_real_available_knowledge_index() -> None:
    # Regression guard: CURRENT is a pointer *file* holding a version id,
    # not a directory. An earlier version of this check used .is_dir(),
    # which always returned False even against a real, available index --
    # the case above (an empty tmp_path) can never catch that, since
    # either check trivially returns False there.
    real_repo_root = Path(__file__).resolve().parents[5]
    result = build_support_diagnostics(repo_root=real_repo_root)
    assert result["checks"]["knowledge_index_available"] is True
