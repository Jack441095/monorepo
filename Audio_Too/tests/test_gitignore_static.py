"""Static checks for generated artifact ignore rules."""

from __future__ import annotations

from pathlib import Path

import scripts.repo_hygiene as repo_hygiene


ROOT = Path(__file__).resolve().parent.parent


def test_kenn_training_artifacts_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "studio/kenn/kenn/artifacts/training/*.json" in gitignore
    assert "studio/kenn/kenn/artifacts/training/*.jsonl" in gitignore


def test_repo_hygiene_blocks_generated_tracked_files() -> None:
    issues = repo_hygiene.tracked_file_issues(
        [
            "studio/kenn/kenn/data/index/chunks.jsonl",
            "studio/kenn/kenn/Training_Data_PDF/live12-manual-en.pdf",
            "studio/kenn/kenn/Training_Data_PDF/audio-too-workflow-checklist.pdf",
            "studio/kenn/kenn/chat.py",
        ],
        root=ROOT,
    )

    blocked = {issue.path for issue in issues}
    assert "studio/kenn/kenn/data/index/chunks.jsonl" in blocked
    assert "studio/kenn/kenn/Training_Data_PDF/live12-manual-en.pdf" in blocked
    assert "studio/kenn/kenn/Training_Data_PDF/audio-too-workflow-checklist.pdf" not in blocked
    assert "studio/kenn/kenn/chat.py" not in blocked


def test_repo_hygiene_reports_tracked_files_by_size(tmp_path) -> None:
    small = tmp_path / "small.txt"
    large = tmp_path / "large.txt"
    small.write_text("small", encoding="utf-8")
    large.write_text("x" * 100, encoding="utf-8")

    files = repo_hygiene.tracked_files(["small.txt", "large.txt"], root=tmp_path)

    assert [item.path for item in files] == ["large.txt", "small.txt"]
    assert repo_hygiene.human_size(1024 * 1024) == "1.0 MB"


def test_local_data_doctor_reports_known_targets() -> None:
    targets = repo_hygiene.local_data_targets(root=ROOT)
    labels = {target.label for target in targets}

    assert "KENN PDFs" in labels
    assert "KENN index" in labels
    assert "Mix Review data" in labels


def test_repo_hygiene_docs_and_precommit_config_exist() -> None:
    docs = (ROOT / "docs" / "REPO_HYGIENE.md").read_text(encoding="utf-8")
    precommit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "python3 main.py hygiene" in docs
    assert "repo_hygiene.py check" in precommit
