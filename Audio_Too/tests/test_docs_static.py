"""Static documentation coverage checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_creative_repair_training_doc_is_linked_and_actionable() -> None:
    doc = (ROOT / "docs" / "CREATIVE_REPAIR_TRAINING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    ableton_doc = (ROOT / "docs" / "ABLETON_LM.md").read_text(encoding="utf-8")
    commands = (ROOT / "docs" / "commands.md").read_text(encoding="utf-8")

    assert "Creative Lab repair-training loop" in doc
    assert "python3 main.py repair-training" in doc
    assert "python3 main.py repair-training --validate" in doc
    assert "creative_lab_repair_records.approved.jsonl" in doc
    assert "creative_lab_repair_records.approved.manifest.json" in doc
    assert "Validation checks" in doc
    assert "docs/CREATIVE_REPAIR_TRAINING.md" in readme
    assert "python3 main.py repair-training --summary-only" in readme
    assert "CREATIVE_REPAIR_TRAINING.md" in ableton_doc
    assert "python3 main.py repair-training" in commands
    assert "python3 main.py repair-training --validate" in commands
    assert "repair-training summary smoke" in commands
    assert "docs/CREATIVE_REPAIR_TRAINING.md" in commands


def test_kenn_readiness_command_is_documented() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commands = (ROOT / "docs" / "commands.md").read_text(encoding="utf-8")

    assert "python main.py kenn-ready" in readme
    assert "python3 main.py kenn-ready" in commands
    assert "Deeper KENN report" in commands


def test_hygiene_command_is_documented() -> None:
    commands = (ROOT / "docs" / "commands.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "REPO_HYGIENE.md").read_text(encoding="utf-8")

    assert "python3 main.py hygiene" in commands
    assert "hygiene doctor" in commands
    assert "python3 main.py hygiene" in doc


def test_architecture_ownership_and_dependency_map_are_documented() -> None:
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "Runtime dependency map" in architecture
    assert "Dependencies point downward" in architecture
    for domain in ["Business", "KENN", "Audio Analysis", "Automix", "Thursday", "AudioGen"]:
        assert f"| {domain} |" in architecture
    assert "server/app/server.py" in architecture
    assert "server/app/routes/" in architecture
    assert "private audio streamed through authenticated routes" in architecture


def test_remaining_http_mutations_are_inventoried() -> None:
    inventory = (ROOT / "docs" / "MUTATION_INVENTORY.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    for route in [
        "POST /api/automix/upload",
        "POST /api/automix/reference/upload",
        "POST /api/admin/draft",
        "POST /api/admin/status",
    ]:
        assert route in inventory
    assert "docs/MUTATION_INVENTORY.md" in architecture


def test_versioned_api_contract_is_documented() -> None:
    api_doc = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "GET /api/v1/openapi.json" in api_doc
    assert "/api/v1/automix/jobs" in api_doc
    assert "Idempotency-Key" in api_doc
    assert "idempotency_conflict" in api_doc
    assert "1 January 2027" in api_doc
    assert "docs/API.md" in architecture
