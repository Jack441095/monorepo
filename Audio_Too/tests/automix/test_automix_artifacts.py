"""AutoMix output graph registration tests."""

from __future__ import annotations

import sys
from pathlib import Path
import json

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import artifact_store  # noqa: E402
import automix_worker  # noqa: E402
import db  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(db, "_migration_done", False)
    monkeypatch.setattr(artifact_store, "ARTIFACT_ROOT", tmp_path / "artifacts")
    artifact_store.reset_connection_state()
    artifact_store.ensure_schema()
    yield tmp_path
    artifact_store.reset_connection_state()


def delivery(root: Path) -> dict:
    paths = {
        "zip_path": root / "mix_package_v1.zip",
        "wav_path": root / "mixdown_v1.wav",
        "report_path": root / "mix_report_v1.html",
        "decisions_md_path": root / "mix_decisions_v1.md",
        "decisions_json_path": root / "mix_decisions_v1.json",
    }
    for key, path in paths.items():
        path.write_bytes(f"{key} data".encode())
    return {
        "version": 1,
        **{key: str(path) for key, path in paths.items()},
        "additional_format_paths": {},
    }


def test_delivery_graph_links_sources_mix_reports_and_package(env: Path) -> None:
    source_path = env / "stems.zip"
    source_path.write_bytes(b"source stems")
    source = artifact_store.register_file(
        source_path,
        kind="audio.source.upload",
        media_type="application/zip",
        producer="stem-upload",
        producer_version="1.0.0",
        project_id="project-1",
        external_key="stem-upload:one",
    )

    artifacts = automix_worker._register_delivery_artifacts(
        "job-1", "project-1", delivery(env)
    )

    assert artifacts["mix"]["parent_ids"] == [source["id"]]
    assert artifacts["report"]["parent_ids"] == [artifacts["mix"]["artifact_id"]]
    assert artifacts["manifest"]["parent_ids"] == [artifacts["mix"]["artifact_id"]]
    assert set(artifacts["package"]["parent_ids"]) == {
        artifacts["mix"]["artifact_id"],
        artifacts["report"]["artifact_id"],
        artifacts["decisions_markdown"]["artifact_id"],
        artifacts["manifest"]["artifact_id"],
    }
    assert all(artifact_store.verify(item["artifact_id"])["ok"] for item in artifacts.values())


def test_delivery_graph_failure_rolls_back_records_and_output_files(
    env: Path, monkeypatch
) -> None:
    payload = delivery(env)
    original = artifact_store.register_prepared
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated registry failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(artifact_store, "register_prepared", fail_second)
    with pytest.raises(RuntimeError, match="registry failure"):
        automix_worker._register_delivery_artifacts("job-1", "project-1", payload)

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM artifact_blobs").fetchone()[0] == 0
    assert not any(Path(payload[key]).exists() for key in (
        "zip_path", "wav_path", "report_path", "decisions_md_path", "decisions_json_path"
    ))


def test_advisor_shadow_receipt_is_internal_content_addressed_artifact(env: Path) -> None:
    source_path = env / "vocal.wav"
    source_path.write_bytes(b"source audio")
    source = artifact_store.register_file(
        source_path,
        kind="audio.source.upload",
        media_type="audio/wav",
        producer="stem-upload",
        producer_version="1.0.0",
        project_id="project-1",
        external_key="stem-upload:vocal",
    )
    receipt = {
        "schema": "audio-too.kenn-advisor-shadow/v1",
        "correlation_id": "automix-job:job-1",
        "source_plan_revision": "sha256:" + "a" * 64,
        "status": "no_proposal",
        "proposal": None,
        "operation_count": 0,
        "would_change": [],
        "rejection_reason": "",
        "latency_ms": 0.1,
    }
    artifact = automix_worker._register_advisor_shadow_receipt(
        "job-1", "project-1", receipt
    )
    assert artifact["kind"] == "audio.automix.advisor-shadow"
    assert artifact["parent_ids"] == [source["id"]]
    assert artifact_store.verify(artifact["artifact_id"])["ok"] is True
    stored = json.loads(
        artifact_store.resolve_path(artifact["artifact_id"]).read_text(encoding="utf-8")
    )
    assert stored == receipt


def test_advisor_preview_artifacts_are_atomic_and_lineaged(env: Path) -> None:
    shadow_path = env / "shadow.json"
    shadow_path.write_text("{}", encoding="utf-8")
    shadow = artifact_store.register_file(
        shadow_path,
        kind="audio.automix.advisor-shadow",
        media_type="application/json",
        producer="test",
        producer_version="1",
        project_id="project-1",
        external_key="automix-job:job-1:advisor-shadow",
    )
    preview = {
        "schema": "audio-too.kenn-advisor-preview/v1",
        "source_plan_revision": "sha256:" + "a" * 64,
        "sample_rate": 44100,
        "duration_samples": 44100,
        "baseline": {"mixdown_wav_bytes": b"RIFF baseline"},
        "baseline_lufs": -14.0,
        "candidates": [
            {
                "operation_index": 0,
                "render": {"mixdown_wav_bytes": b"RIFF candidate"},
                "measured_lufs": -14.1,
                "loudness_bias_lu": -0.1,
                "rms_delta": 0.02,
            }
        ],
        "rejected": [],
        "truncated_operations": 0,
    }
    summary = automix_worker._register_advisor_preview_artifacts(
        "job-1", "project-1", shadow["id"], preview
    )
    baseline = artifact_store.get(summary["baseline_artifact_id"])
    candidate = artifact_store.get(summary["candidates"][0]["preview_artifact_id"])
    assert baseline["kind"] == "audio.automix.advisor-preview-baseline"
    assert baseline["parent_ids"] == (shadow["id"],)
    assert candidate["kind"] == "audio.automix.advisor-preview"
    assert set(candidate["parent_ids"]) == {baseline["id"], shadow["id"]}
    assert candidate["metadata"]["operation_index"] == 0
    assert candidate["metadata"]["shadow_artifact_id"] == shadow["id"]
    assert artifact_store.verify(baseline["id"])["ok"] is True
    assert artifact_store.verify(candidate["id"])["ok"] is True
