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


def test_receipts_appear_only_as_counts(monkeypatch, tmp_path: Path) -> None:
    import kenn.core.support_diagnostics as diagnostics

    rows = [
        {"receipt": {"action": "set_volume", "status": "applied", "verified": True, "timestamp": 1_790_000_000.0,
                     "target": {"track_name": "Client Vocal Take 3"}, "before": 0.5, "requested": 0.7}},
        {"receipt": {"action": "set_volume", "status": "applied", "verified": True, "timestamp": 1_790_000_060.0,
                     "target": {"track_name": "Client Vocal Take 3"}, "rolled_back": True}},
        {"receipt": {"action": "import_sample", "status": "failed", "verified": False,
                     "error": "/Users/example/Samples/secret.wav not found"}},
    ]
    monkeypatch.setattr(diagnostics, "_recent_receipts", lambda: rows)
    monkeypatch.setattr(diagnostics, "_timings", lambda: {})  # other tests' answer timings would add their own numbers
    result = build_support_diagnostics(repo_root=tmp_path)
    rendered = json.dumps(result)

    assert result["receipts"]["count"] == 3
    assert result["receipts"]["by_action"] == {"set_volume": 2, "import_sample": 1}
    assert result["receipts"]["by_status"] == {"applied": 2, "failed": 1}
    assert result["receipts"]["verified"] == 2 and result["receipts"]["rolled_back"] == 1
    assert "Client Vocal" not in rendered and "secret.wav" not in rendered
    assert '"requested"' not in rendered and '"before"' not in rendered and '"target"' not in rendered


def test_timings_are_numbers_only(tmp_path: Path) -> None:
    from kenn.core import timing_stats

    timing_stats.reset()
    for milliseconds in (100.0, 200.0, 300.0, 400.0, 5000.0):
        timing_stats.record("ask", milliseconds)
    try:
        timings = build_support_diagnostics(repo_root=tmp_path)["timings"]
    finally:
        timing_stats.reset()
    assert timings == {"ask": {"count": 5, "p50_ms": 300.0, "p95_ms": 5000.0, "max_ms": 5000.0}}


def test_saved_diagnostics_file_is_the_same_redacted_payload(tmp_path: Path) -> None:
    from kenn.core.support_diagnostics import save_support_diagnostics

    payload = build_support_diagnostics(repo_root=tmp_path)
    saved = save_support_diagnostics(payload, tmp_path / "diagnostics")
    assert saved.parent == tmp_path / "diagnostics" and saved.name.startswith("kenn-diagnostics-")
    assert json.loads(saved.read_text(encoding="utf-8")) == json.loads(json.dumps(payload))
