"""First-run setup: find Live's User Library, install KENN's AbletonOSC, report readiness."""

from __future__ import annotations

from pathlib import Path

from kenn.core import live_setup


def _library_cfg(preferences: Path, version: str, user_library_parent: Path) -> None:
    folder = preferences / f"Live {version}"
    folder.mkdir(parents=True)
    (folder / "Library.cfg").write_text(
        f'<?xml version="1.0"?><Ableton><ContentLibrary><UserLibrary><LibraryProject>'
        f'<ProjectPath Value="{user_library_parent}" /></LibraryProject></UserLibrary></ContentLibrary></Ableton>'
    )


def test_newest_live_versions_user_library_wins(tmp_path) -> None:
    prefs = tmp_path / "prefs"
    _library_cfg(prefs, "11.3.21", tmp_path / "old")
    _library_cfg(prefs, "12.4.6", tmp_path / "ssd")
    _library_cfg(prefs, "12.0b29", tmp_path / "beta")
    assert live_setup.user_library_remote_scripts(prefs, tmp_path) == tmp_path / "ssd" / "User Library" / "Remote Scripts"


def test_default_user_library_without_a_config(tmp_path) -> None:
    assert live_setup.user_library_remote_scripts(tmp_path / "none", tmp_path) == (
        tmp_path / "Music" / "Ableton" / "User Library" / "Remote Scripts")


def test_install_stamps_the_bundle_and_hides_the_previous_copy(tmp_path) -> None:
    remote_scripts = tmp_path / "Remote Scripts"
    (remote_scripts / "AbletonOSC").mkdir(parents=True)
    (remote_scripts / "AbletonOSC" / "old.py").write_text("# old")

    result = live_setup.install_remote_script(remote_scripts)

    assert result["ok"]
    stamp = live_setup.installed_stamp(remote_scripts)
    assert stamp["content_hash"] == live_setup.bundle_hash()
    assert (remote_scripts / "AbletonOSC" / "abletonosc" / "song.py").is_file()
    assert not (remote_scripts / "AbletonOSC" / "old.py").exists()
    backups = list((remote_scripts / ".kenn-backups").iterdir())
    assert len(backups) == 1 and (backups[0] / "old.py").is_file()
    # Only the hidden backup folder and the fresh package are visible to Live.
    assert sorted(p.name for p in remote_scripts.iterdir()) == [".kenn-backups", "AbletonOSC"]


class _Client:
    def __init__(self, status: str) -> None:
        self.status = status

    def probe_connection(self):
        return {"status": self.status}


def test_status_reports_each_check_with_a_fix(tmp_path) -> None:
    remote_scripts = tmp_path / "Remote Scripts"
    before = live_setup.setup_status(_Client("offline"), remote_scripts=remote_scripts)
    checks = {check["id"]: check for check in before["checks"]}
    assert before["ready"] is False
    assert not checks["remote_script"]["ok"] and "Install" in checks["remote_script"]["fix"]
    assert not checks["live_connected"]["ok"] and "Control Surface" in checks["live_connected"]["fix"]

    live_setup.install_remote_script(remote_scripts)
    after = live_setup.setup_status(_Client("connected"), remote_scripts=remote_scripts)
    checks = {check["id"]: check for check in after["checks"]}
    assert checks["remote_script"]["ok"] and checks["live_connected"]["ok"]


def test_app_and_deploy_tool_agree_on_the_bundle() -> None:
    from scripts import abletonosc_bundle  # the tooling copy the deploy tool and preflight use

    assert abletonosc_bundle.bundle_hash() == live_setup.bundle_hash()
    assert abletonosc_bundle.bundle_files() == live_setup.bundle_files()
