"""The packaged app's entry point: data folder and settings.json become KENN's environment."""

from __future__ import annotations

import json

from kenn import app_entry


def test_first_run_writes_default_settings_and_points_every_writable_path_at_the_data_folder(tmp_path) -> None:
    environ: dict[str, str] = {}
    root = app_entry.prepare_environment(environ, data_root=tmp_path / "KENN")

    settings = json.loads((root / "settings.json").read_text())
    assert settings["allow_daw_control"] is True and settings["live_llm_enabled"] is False
    for variable in app_entry.DATA_LOCATIONS:
        assert environ[variable].startswith(str(root))
    assert environ["KENN_ALLOW_DAW_CONTROL"] == "1" and environ["KENN_LIVE_LLM_ENABLED"] == "0"
    assert (root / "live").is_dir() and (root / "chats").is_dir()


def test_user_settings_apply_and_the_shell_environment_still_wins(tmp_path) -> None:
    root = tmp_path / "KENN"
    root.mkdir()
    (root / "settings.json").write_text(json.dumps({"port": 8123, "allow_daw_control": False, "unknown": 1}))
    environ = {"KENN_PORT": "9000"}
    app_entry.prepare_environment(environ, data_root=root)
    assert environ["KENN_PORT"] == "9000"  # shell wins
    assert environ["KENN_ALLOW_DAW_CONTROL"] == "0"
    assert "unknown" not in environ


def test_unreadable_settings_fall_back_to_defaults_without_overwriting(tmp_path) -> None:
    root = tmp_path / "KENN"
    root.mkdir()
    (root / "settings.json").write_text("{ not json")
    environ: dict[str, str] = {}
    app_entry.prepare_environment(environ, data_root=root)
    assert environ["KENN_ALLOW_DAW_CONTROL"] == "1"
    assert (root / "settings.json").read_text() == "{ not json"
