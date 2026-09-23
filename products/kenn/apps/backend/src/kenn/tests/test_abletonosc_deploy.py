import json
import shutil
import sys
from pathlib import Path

import pytest

import scripts.abletonosc_bundle as bundle
import scripts.deploy_abletonosc as deploy
from kenn.ableton_osc_bridge import AbletonOSCClient


def _copy_source(tmp_path: Path) -> Path:
    target = tmp_path / "AbletonOSC"
    shutil.copytree(bundle.SOURCE_DIR, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def test_bundle_excludes_tests_clients_docs_and_stamp(tmp_path: Path) -> None:
    files = bundle.bundle_files()
    assert "abletonosc/view.py" in files and "manager.py" in files
    assert not any(f.startswith(("tests/", "client/")) or f.endswith(".md") for f in files)
    assert not any(f.split("/")[-1].startswith("test_") for f in files)
    target = _copy_source(tmp_path)
    (target / bundle.STAMP_RELATIVE).write_text("{}")
    assert bundle.bundle_hash(target) == bundle.bundle_hash()


def test_hash_changes_when_any_deployable_file_changes(tmp_path: Path) -> None:
    target = _copy_source(tmp_path)
    before = bundle.bundle_hash(target)
    (target / "abletonosc" / "view.py").write_text("# changed\n")
    assert bundle.bundle_hash(target) != before


def test_deploy_plans_then_applies_and_stamps(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _copy_source(tmp_path)
    (target / "abletonosc" / "view.py").write_text("# stale\n")
    (target / "manager.py").write_text("# stale manager\n")
    monkeypatch.setattr(deploy, "KENN_ROOT", tmp_path)

    monkeypatch.setattr(sys, "argv", ["deploy", "--target", str(target)])
    assert deploy.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "plan_only"
    assert set(plan["changed"]) == {"abletonosc/view.py", "manager.py"}
    assert plan["restart_required_for"] == ["manager.py"]

    monkeypatch.setattr(sys, "argv", ["deploy", "--target", str(target), "--apply"])
    assert deploy.main() == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["status"] == "applied"
    assert applied["installed_hash"] == bundle.bundle_hash()
    stamp = json.loads((target / bundle.STAMP_RELATIVE).read_text())
    assert stamp["content_hash"] == bundle.bundle_hash()
    assert Path(applied["backup"]).is_dir()


def test_deploy_refuses_a_target_without_abletonosc(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["deploy", "--target", str(tmp_path)])
    assert deploy.main() == 2
    assert "refused" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("reply", "success"),
    [(None, False), (["unstamped", "", ""], False), (["abc123", "5d7089c", "2026-09-23"], True)],
)
def test_bridge_reports_remote_script_version(reply, success) -> None:
    client = AbletonOSCClient.__new__(AbletonOSCClient)
    client._query_args = lambda *_args, **_kwargs: reply
    result = client.get_remote_script_version()
    assert result["success"] is success
    if success:
        assert result["content_hash"] == "abc123" and result["git_commit"] == "5d7089c"
