from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_real_mix_corpus.py"
module = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("real_mix_eval", SCRIPT))
assert spec.loader
spec.loader.exec_module(module)


def _manifest(tmp_path: Path, count: int = 1) -> Path:
    audio_root = tmp_path / "audio"; audio_root.mkdir()
    cases = []
    for index in range(count):
        payload = b"wav-fixture-" + str(index).encode()
        name = f"case-{index}.wav"; (audio_root / name).write_bytes(payload)
        categories = ["vocals", "drums", "bass", "dense_electronic", "sparse_acoustic"]
        cases.append({"case_id": f"case-{index}", "audio_file": name,
            "sha256": hashlib.sha256(payload).hexdigest(), "consent_confirmed": True,
            "rights_basis": "owned", "mix_category": categories[index % len(categories)],
            "ground_truth": {"observations": [{"fault_family": "clipping", "confidence": "high", "acceptable_alternatives": []}]},
            "subjective_exclusions": []})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema": module.MANIFEST_SCHEMA, "cases": cases}))
    return path


def test_prepare_omits_paths_and_audio_and_binds_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet, review = module.prepare(_manifest(tmp_path), tmp_path / "audio")
    rendered = json.dumps(packet)
    assert "audio_file" not in rendered and str(tmp_path) not in rendered
    assert packet["privacy"]["audio_embedded"] is False
    assert packet["engine_sha256"] == hashlib.sha256(module.ENGINE_PATH.read_bytes()).hexdigest()
    assert packet["source_git_commit"] == module.source_revision()
    assert review["scores"][0]["case_id"] == "case-0"


def test_prepare_rejects_path_traversal(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    value = json.loads(path.read_text()); value["cases"][0]["audio_file"] = "../secret.wav"
    path.write_text(json.dumps(value))
    with pytest.raises(module.IntakeError, match="relative WAV"):
        module.prepare(path, tmp_path / "audio")


def test_prepare_rejects_audio_hash_mismatch(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    value = json.loads(path.read_text()); value["cases"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(value))
    with pytest.raises(module.IntakeError, match="SHA-256 mismatch"):
        module.prepare(path, tmp_path / "audio")


def test_prepare_rejects_empty_or_unstructured_ground_truth(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    value = json.loads(path.read_text()); value["cases"][0]["ground_truth"]["observations"] = []
    path.write_text(json.dumps(value))
    with pytest.raises(module.IntakeError, match="at least one"):
        module.prepare(path, tmp_path / "audio")


def test_prepare_command_writes_two_separate_bound_reviewer_forms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet = tmp_path / "packet.json"; reviewer_a = tmp_path / "reviewer-a.json"; reviewer_b = tmp_path / "reviewer-b.json"
    monkeypatch.setattr(sys, "argv", ["evaluate_real_mix_corpus.py", "prepare", "--manifest", str(_manifest(tmp_path)), "--audio-root", str(tmp_path / "audio"), "--packet", str(packet), "--reviewer-a-template", str(reviewer_a), "--reviewer-b-template", str(reviewer_b)])
    assert module.main() == 0
    a = json.loads(reviewer_a.read_text()); b = json.loads(reviewer_b.read_text())
    assert a["packet_sha256"] == b["packet_sha256"]
    assert a["reviewer_slot"] != b["reviewer_slot"]


def test_score_requires_bound_complete_independent_reviews(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet, template = module.prepare(_manifest(tmp_path, 12), tmp_path / "audio")
    packet_path = tmp_path / "packet.json"; packet_path.write_text(json.dumps(packet))
    paths = []
    for reviewer in ("engineer-a", "engineer-b"):
        review = json.loads(json.dumps(template)); review["reviewer_id"] = reviewer; review["reviewer_slot"] = reviewer; review["independent_review_confirmed"] = True
        for row in review["scores"]: row.update(evidence_correct=True, usefulness_1_to_5=4, severity_order_correct=True, abstention_correct=True)
        path = tmp_path / f"{reviewer}.json"; path.write_text(json.dumps(review)); paths.append(path)
    result = module.score(packet_path, paths)
    assert result["qualified"] is True
    assert result["metrics"]["reviewer_count"] == 2
    assert result["thresholds"]["required_category_coverage"] is True
    assert result["engine_sha256"] == packet["engine_sha256"]
    assert result["evaluator_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert len(result["review_sha256"]) == 2
    assert len(set(result["review_sha256"])) == 2


def test_score_fails_closed_without_required_category_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    manifest_path = _manifest(tmp_path, 12)
    manifest = json.loads(manifest_path.read_text())
    for case in manifest["cases"]: case["mix_category"] = "drums"
    manifest_path.write_text(json.dumps(manifest))
    packet, template = module.prepare(manifest_path, tmp_path / "audio")
    packet_path = tmp_path / "packet.json"; packet_path.write_text(json.dumps(packet))
    paths = []
    for reviewer in ("engineer-a", "engineer-b"):
        review = json.loads(json.dumps(template)); review["reviewer_id"] = reviewer; review["reviewer_slot"] = reviewer; review["independent_review_confirmed"] = True
        for row in review["scores"]: row.update(evidence_correct=True, usefulness_1_to_5=5, severity_order_correct=True, abstention_correct=True)
        path = tmp_path / f"{reviewer}.json"; path.write_text(json.dumps(review)); paths.append(path)
    result = module.score(packet_path, paths)
    assert result["qualified"] is False
    assert result["thresholds"]["required_category_coverage"] is False


def test_score_rejects_duplicate_reviewer_identity_case_insensitively(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet, template = module.prepare(_manifest(tmp_path, 12), tmp_path / "audio")
    packet_path = tmp_path / "packet.json"; packet_path.write_text(json.dumps(packet))
    paths = []
    for position, reviewer in enumerate(("Engineer-A", " engineer-a ")):
        review = json.loads(json.dumps(template)); review["reviewer_id"] = reviewer; review["reviewer_slot"] = f"reviewer-{position}"; review["independent_review_confirmed"] = True
        for row in review["scores"]: row.update(evidence_correct=True, usefulness_1_to_5=4, severity_order_correct=True, abstention_correct=True)
        path = tmp_path / f"review-{position}.json"; path.write_text(json.dumps(review)); paths.append(path)

    with pytest.raises(module.IntakeError, match="duplicates another reviewer"):
        module.score(packet_path, paths)


def test_score_rejects_duplicate_slots_and_malformed_family_lists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet, template = module.prepare(_manifest(tmp_path, 12), tmp_path / "audio")
    packet_path = tmp_path / "packet.json"; packet_path.write_text(json.dumps(packet))
    paths = []
    for position in range(2):
        review = json.loads(json.dumps(template))
        review.update(reviewer_id=f"engineer-{position}", reviewer_slot="same-slot", independent_review_confirmed=True)
        for row in review["scores"]:
            row.update(evidence_correct=True, usefulness_1_to_5=4, severity_order_correct=True, abstention_correct=True)
        path = tmp_path / f"review-{position}.json"; path.write_text(json.dumps(review)); paths.append(path)
    with pytest.raises(module.IntakeError, match="unique reviewer slot"):
        module.score(packet_path, paths)

    review = json.loads(paths[0].read_text())
    review["scores"][0]["false_positive_families"] = "not-a-list"
    paths[0].write_text(json.dumps(review))
    with pytest.raises(module.IntakeError, match="invalid false_positive_families"):
        module.score(packet_path, [paths[0]])


def test_score_fails_closed_below_quality_thresholds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet, review = module.prepare(_manifest(tmp_path, 12), tmp_path / "audio")
    packet_path = tmp_path / "packet.json"; packet_path.write_text(json.dumps(packet))
    review["reviewer_id"] = "one"; review["reviewer_slot"] = "reviewer-1"; review["independent_review_confirmed"] = True
    for row in review["scores"]: row.update(evidence_correct=False, usefulness_1_to_5=2, severity_order_correct=False, abstention_correct=False)
    review_path = tmp_path / "review.json"; review_path.write_text(json.dumps(review))
    result = module.score(packet_path, [review_path])
    assert result["qualified"] is False
    assert result["thresholds"]["two_independent_reviewers"] is False


def test_score_rejects_blank_severity_or_abstention_scores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet, review = module.prepare(_manifest(tmp_path, 12), tmp_path / "audio")
    packet_path = tmp_path / "packet.json"; packet_path.write_text(json.dumps(packet))
    review["reviewer_id"] = "engineer"; review["reviewer_slot"] = "reviewer-1"; review["independent_review_confirmed"] = True
    for row in review["scores"]: row.update(evidence_correct=True, usefulness_1_to_5=5)
    review_path = tmp_path / "review.json"; review_path.write_text(json.dumps(review))
    with pytest.raises(module.IntakeError, match="severity-order"):
        module.score(packet_path, [review_path])


def test_score_rejects_duplicate_packet_case_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {"ok": True, "analysis_status": "complete", "findings": [], "limitations": []})
    packet, _review = module.prepare(_manifest(tmp_path, 12), tmp_path / "audio")
    packet["cases"][1]["case_id"] = packet["cases"][0]["case_id"]
    packet_path = tmp_path / "packet.json"; packet_path.write_text(json.dumps(packet))
    with pytest.raises(module.IntakeError, match="unique"):
        module.score(packet_path, [])


def test_score_rejects_packet_from_another_source_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "analyze_wav", lambda *_args, **_kwargs: {
        "ok": True, "analysis_status": "complete", "findings": [], "limitations": [],
    })
    packet, _review = module.prepare(_manifest(tmp_path), tmp_path / "audio")
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet))
    monkeypatch.setattr(module, "source_revision", lambda: "0" * 40)

    with pytest.raises(module.IntakeError, match="current source Git revision"):
        module.score(packet_path, [])
