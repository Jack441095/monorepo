"""Release packaging integrity and privacy tests."""

from __future__ import annotations

from pathlib import Path

from nite_core.release_package import RELEASE_ROOTS, build_package, extract_and_verify


def test_current_release_package_is_complete_relocatable_and_private(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parent.parent
    archive = tmp_path / "audio-too.tar.gz"

    created = build_package(root, archive)
    package_root, verified = extract_and_verify(archive, tmp_path / "install")

    assert created["file_count"] == verified["file_count"]
    assert verified["index_version"]
    assert (package_root / "audio-too").stat().st_mode & 0o111
    assert (package_root / "server/app/server.py").is_file()
    assert (package_root / "thursday/orchestrator.py").is_file()
    assert (package_root / "studio/kenn/kenn/artifacts/models/minilm/model.onnx").is_file()
    assert (package_root / "studio/kenn/kenn/artifacts/models/kokoro/kokoro-v1.0.int8.onnx").is_file()
    assert (package_root / "studio/audiogen/audiogen/composition").is_dir()
    assert not (package_root / ".env").exists()
    assert not list(package_root.rglob("*.db"))
    assert not (package_root / "thursday/sessions").exists()
    assert not (package_root / "thursday/user_data").exists()
    assert not (package_root / "server/agents/Shared/data").exists()


def test_every_kenn_subpackage_is_in_release_roots() -> None:
    """Regression for a real 2026-07-11 incident: studio/kenn/kenn/knowledge/
    (Stage G's autonomous-maintenance code -- contradictions.py,
    reasoning.py, reflection.py, trust_scores.py, maintenance_scheduler.py)
    was added to the source tree but never added to RELEASE_ROOTS, so every
    packaged release silently shipped a KENN server that crashed at import
    time with `ModuleNotFoundError: No module named 'kenn.knowledge'` --
    undetected because the currently-running dev server predated the
    omission and was never restarted. Catches the next missing subpackage
    the same way, not just this specific one.
    """
    kenn_dir = Path(__file__).resolve().parent.parent / "studio" / "kenn" / "kenn"
    real_subpackages = {
        p.parent.relative_to(kenn_dir.parent.parent.parent).as_posix()
        for p in kenn_dir.glob("*/__init__.py")
    }
    covered = set(RELEASE_ROOTS)
    missing = real_subpackages - covered
    assert not missing, (
        f"studio/kenn/kenn subpackage(s) not listed in RELEASE_ROOTS: {missing} -- "
        "a packaged release would ship a KENN server that fails at import time."
    )
