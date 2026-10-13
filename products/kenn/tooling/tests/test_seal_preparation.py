"""Draft packets keep rights unresolved and final wording outside development review."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

from seal_experiment.preparation import COUNTS, COVERAGE, emit, prepare
from seal_experiment.records import digest, generation_prompt, read, validate_dataset, write


@pytest.fixture
def spec():
    groups = []
    for split, count in COUNTS.items():
        # Distinct fixture vocabulary avoids accidentally testing the lexical leakage guard.
        for context in range(4 if split == "train" else 1):
            family = f"{split}-family-{context}"
            variants = []
            for row in range(2 if split == "train" else count):
                variant = {"question": f"{split}{context}word{row} explain?",
                           "answer": f"{split} supported response {context}/{row}."}
                if split == "train":
                    variant["kind"] = "explanation"
                else:
                    variant.update(id=f"{split}-{row}", coverage=sorted(COVERAGE)[row % len(COVERAGE)])
                variants.append(variant)
            groups.append({"id": family, "family": family, "split": split,
                           "text": f"Human-only reference sentinel {family}.",
                           "related_facts": [family], "task_templates": [f"template-{family}"],
                           "references": ["https://www.ableton.com/en/live-manual/12/"],
                           "origin_kind": "synthetic-test-fixture", "live_version": "12",
                           "privacy": "public", "variants": variants})
    return {"schema": "kenn.seal.specialist_draft.v1", "groups": groups}


def test_preparation_has_exact_counts_and_cannot_grant_review_or_training_rights(spec):
    # An input's old approval must not authorize newly derived wording.
    spec["approvals"] = {"old-note": {"verdict": "approved"}}
    spec["groups"][0].update(training_permission=True, license="claimed license", review="approved")
    data, sealed, receipt = prepare(spec)
    assert len(data["ordinary_examples"]) == 8
    assert sum(t["split"] == "reward" for t in data["tasks"]) == 24
    assert sum(t["split"] == "retention" for t in data["tasks"]) == 12
    assert len(sealed["tasks"]) == 24
    assert data["approvals"] == {}
    assert all(s["training_permission"] is False for s in data["sources"].values())
    assert all(s["license"] == "rights review pending" for s in data["sources"].values())
    assert receipt["training_allowed"] is False
    assert receipt["semantic_review"] == "pending"
    assert data["sealed_sha256"] == digest(sealed)
    with pytest.raises(ValueError, match="permission and semantic review"):
        validate_dataset(data)


@pytest.mark.parametrize("privacy", [None, "private", "session"])
def test_private_or_unclassified_context_cannot_be_relabelled_public(spec, privacy):
    spec["groups"][0]["privacy"] = privacy
    with pytest.raises(ValueError, match="explicit public"):
        prepare(spec)


@pytest.mark.parametrize("key", ["related_facts", "task_templates"])
def test_renamed_fact_or_task_family_cannot_cross_partitions(spec, key):
    spec["groups"][4][key] = spec["groups"][0][key]
    with pytest.raises(ValueError, match="crosses partitions"):
        prepare(spec)


def test_identical_source_bytes_cannot_hide_behind_a_new_family_name(spec):
    spec["groups"][4]["text"] = spec["groups"][0]["text"]
    with pytest.raises(ValueError, match="identical source content"):
        prepare(spec)


@pytest.mark.parametrize("change", ["count", "contexts", "two_targets", "coverage", "task_id", "question"])
def test_incomplete_or_duplicate_packet_fails_before_emission(spec, tmp_path, change):
    if change == "count":
        spec["groups"][4]["variants"].pop()
    elif change == "contexts":
        spec["groups"].pop(0)
    elif change == "two_targets":
        spec["groups"][0]["variants"].pop()
    elif change == "coverage":
        for variant in spec["groups"][4]["variants"]:
            variant["coverage"] = "technical"
    elif change == "task_id":
        spec["groups"][4]["variants"][1]["id"] = spec["groups"][4]["variants"][0]["id"]
    else:
        spec["groups"][4]["variants"][1]["question"] = spec["groups"][4]["variants"][0]["question"].upper()
    output = tmp_path / "packet"
    with pytest.raises(ValueError):
        emit(spec, output)
    assert not output.exists()


@pytest.mark.parametrize("field,value", [("question", ""), ("answer", "  "),
                                        ("history", [{"role": "tool", "content": "raw session"}]),
                                        ("history", [None])])
def test_invalid_evaluation_text_or_history_cannot_be_emitted(spec, field, value):
    spec["groups"][4]["variants"][0][field] = value
    with pytest.raises(ValueError, match="nonempty text|valid role/content"):
        prepare(spec)


def test_knowledge_only_inference_cannot_receive_the_review_reference_or_answer(spec):
    data, sealed, _ = prepare(spec)
    for task in [*data["tasks"], *sealed["tasks"]]:
        prompt = json.dumps(task["messages"])
        assert "Human-only reference sentinel" not in prompt
        assert task["accepted_answers"][0] not in prompt
        assert task["scope"] == "knowledge_only"
    generator = json.dumps(generation_prompt("train-family-0", data["sources"]["train-family-0"], 2))
    assert "final-family" not in generator
    assert "reward-family" not in generator


def test_overlap_flags_show_hashes_without_opening_final_wording(spec):
    spec["groups"][-1]["variants"][0]["question"] = "Shared rare question wording reserved?"
    spec["groups"][4]["variants"][0]["question"] = "Shared rare question wording development?"
    _, _, receipt = prepare(spec)
    assert receipt["lexical_overlap_flags"]
    flag = receipt["lexical_overlap_flags"][0]
    assert len(flag["question_sha256"]) == 2
    assert "questions" not in flag
    assert "Shared rare question" not in json.dumps(receipt)


def test_four_card_review_pages_reserve_final_targets_and_preserve_packet_identity(spec, tmp_path):
    output = tmp_path / "packet"
    receipt = emit(spec, output)
    assert not (output / "spec.draft.json").exists()
    assert read(output / "reserved/spec.draft.json") == spec
    assert digest(read(output / "data.draft.json")) == receipt["dataset_sha256"]
    assert digest(read(output / "reserved/sealed.draft.json")) == receipt["sealed_sha256"]
    for page in [*(output / "review").glob("*.md"), *(output / "reserved/review").glob("*.md")]:
        assert 1 <= page.read_text().count(". Review card") <= 4
        assert "Source text SHA-256:" in page.read_text()
    for page in (output / "review").glob("*.md"):
        assert "final supported response" not in page.read_text()
        assert "final0word" not in page.read_text()
    original = (output / "data.draft.json").read_bytes()
    changed = copy.deepcopy(spec)
    changed["groups"][0]["variants"][0]["answer"] += " changed"
    with pytest.raises(ValueError, match="already exists"):
        emit(changed, output)
    assert (output / "data.draft.json").read_bytes() == original
    for steps in (4, 8, 16):
        limits = read(output / f"limits-{steps}.json")
        assert limits["values"]["steps"] == limits["values"]["policy_steps"] == steps
        assert limits["values"]["training_tokens"] == steps * 2048
        assert limits["values"]["contexts"] == 4
        assert limits["values"]["examples"] == 2
        assert "specialist_overrides" in limits["reasons"]


def test_direct_emission_rejects_tracked_product_paths(spec):
    with pytest.raises(ValueError, match="outside the Git checkout"):
        emit(spec, ROOT / "docs/forbidden-packet")
    assert not (ROOT / "docs/forbidden-packet").exists()


def test_prepare_cli_emits_a_draft_without_live_ollama_or_cuda(spec, tmp_path):
    source = tmp_path / "spec.json"
    write(source, spec)
    command = [sys.executable, str(ROOT / "tooling/scripts/prepare_seal_specialist.py"),
               "--spec", str(source), "--out", str(tmp_path / "packet")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "owner review pending, training disabled" in result.stdout
    assert read(tmp_path / "packet/data.draft.json")["approvals"] == {}
    reused = subprocess.run(command, capture_output=True, text=True)
    assert reused.returncode == 2
    assert "already exists" in reused.stderr
    rejected = subprocess.run([*command[:-1], str(ROOT / "docs/forbidden-cli-packet")],
                              capture_output=True, text=True)
    assert rejected.returncode == 2
    assert "outside the Git checkout" in rejected.stderr
    assert not (ROOT / "docs/forbidden-cli-packet").exists()
