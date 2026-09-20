from __future__ import annotations

from pathlib import Path

from thursday import runtime_paths


def test_explicit_thursday_state_dir_is_the_complete_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("THURSDAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AUDIO_TOO_STATE_DIR", str(tmp_path / "ignored"))

    assert runtime_paths.state_root() == tmp_path / "state"
    assert runtime_paths.runtime_dir("profiles", "UNSET_OVERRIDE") == tmp_path / "state" / "profiles"


def test_shared_audio_too_state_dir_gets_a_thursday_namespace(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("THURSDAY_STATE_DIR", raising=False)
    monkeypatch.setenv("AUDIO_TOO_STATE_DIR", str(tmp_path / "state"))

    assert runtime_paths.state_root() == tmp_path / "state" / "thursday"


def test_default_state_root_is_outside_the_source_package(monkeypatch, tmp_path) -> None:
    for name in ("THURSDAY_STATE_DIR", "AUDIO_TOO_STATE_DIR", "XDG_STATE_HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    assert not runtime_paths.state_root().is_relative_to(runtime_paths.PACKAGE_DIR)


def test_subsystem_override_wins(monkeypatch, tmp_path) -> None:
    override = tmp_path / "custom-profiles"
    monkeypatch.setenv("THURSDAY_PROFILE_DIR", str(override))

    assert runtime_paths.runtime_dir("profiles", "THURSDAY_PROFILE_DIR") == override


def test_legacy_migration_copies_without_overwriting_or_deleting(monkeypatch, tmp_path) -> None:
    legacy = tmp_path / "legacy"
    destination = tmp_path / "external"
    (legacy / "user_data").mkdir(parents=True)
    (legacy / "profiles").mkdir()
    old_feedback = legacy / "user_data" / "feedback.jsonl"
    old_feedback.write_text("legacy feedback\n", encoding="utf-8")
    old_profile = legacy / "profiles" / "default.json"
    old_profile.write_text('{"source": "legacy"}\n', encoding="utf-8")
    (destination / "profiles").mkdir(parents=True)
    new_profile = destination / "profiles" / "default.json"
    new_profile.write_text('{"source": "new"}\n', encoding="utf-8")

    monkeypatch.setattr(runtime_paths, "DATA_DIR", destination / "user_data")
    monkeypatch.setattr(runtime_paths, "PROFILE_DIR", destination / "profiles")
    monkeypatch.setattr(runtime_paths, "ANALYTICS_DIR", destination / "analytics")
    monkeypatch.setattr(runtime_paths, "SESSION_DIR", destination / "sessions")
    monkeypatch.setattr(runtime_paths, "ALERTS_DIR", destination / "alerts")
    monkeypatch.setattr(runtime_paths, "CALENDAR_DIR", destination / "calendar_data")
    monkeypatch.setattr(runtime_paths, "BRIEFING_STAMP", destination / ".last_briefing.txt")
    monkeypatch.setattr(runtime_paths, "SESSION_FILE", destination / "current_session")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "empty-home"))

    assert runtime_paths.migrate_legacy_state(legacy_root=legacy) == 1
    assert (destination / "user_data" / "feedback.jsonl").read_text() == "legacy feedback\n"
    assert new_profile.read_text() == '{"source": "new"}\n'
    assert old_feedback.exists()
    assert old_profile.exists()
    assert runtime_paths.migrate_legacy_state(legacy_root=legacy) == 0
