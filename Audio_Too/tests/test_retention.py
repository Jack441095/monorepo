from __future__ import annotations

import os
from datetime import datetime, timedelta

from server.app import retention


def test_retention_roots_match_business_runtime_storage() -> None:
    assert retention.UPLOAD_ROOT == retention.BUSINESS_ROOT / "data" / "stem_uploads"
    assert retention.MIX_OUTPUT_ROOT == retention.BUSINESS_ROOT / "data" / "mix_outputs"
    assert retention.AUDIO_QUERY_ROOT == retention.BUSINESS_ROOT / "data" / "audio_queries"
    assert retention.MIX_REVIEW_ROOT == (
        retention.REPO_ROOT / "studio" / "agents" / "MixReview" / "data" / "mix_reviews"
    )


def test_configured_retention_days_defaults_and_is_bounded(monkeypatch) -> None:
    monkeypatch.delenv("AUDIO_TOO_RETENTION_DAYS", raising=False)
    assert retention.configured_retention_days() == 30

    monkeypatch.setenv("AUDIO_TOO_RETENTION_DAYS", "0")
    assert retention.configured_retention_days() == 1

    monkeypatch.setenv("AUDIO_TOO_RETENTION_DAYS", "99999")
    assert retention.configured_retention_days() == 3650

    monkeypatch.setenv("AUDIO_TOO_RETENTION_DAYS", "invalid")
    assert retention.configured_retention_days() == 30


def test_mix_output_cleanup_is_dry_run_safe_and_removes_expired_files(tmp_path) -> None:
    project_dir = tmp_path / "project-123"
    project_dir.mkdir()
    expired = project_dir / "mix_package_v1.zip"
    current = project_dir / "mix_package_v2.zip"
    expired.write_bytes(b"old")
    current.write_bytes(b"new")

    old_timestamp = (datetime.now() - timedelta(days=31)).timestamp()
    os.utime(expired, (old_timestamp, old_timestamp))

    assert retention.clean_files_older_than(tmp_path, 30, run=False) == 1
    assert expired.exists()
    assert current.exists()

    assert retention.clean_files_older_than(tmp_path, 30, run=True) == 1
    assert not expired.exists()
    assert current.exists()
    assert not project_dir.parent.joinpath("missing").exists()


def test_expired_mix_output_cleanup_uses_configured_root_and_period(monkeypatch, tmp_path) -> None:
    calls = []
    monkeypatch.setattr(retention, "MIX_OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("AUDIO_TOO_RETENTION_DAYS", "45")
    monkeypatch.setattr(
        retention,
        "clean_files_older_than",
        lambda root, days, run=False: calls.append((root, days, run)) or 2,
    )

    assert retention.cleanup_expired_mix_outputs(run=True) == 2
    assert calls == [(tmp_path, 45, True)]
