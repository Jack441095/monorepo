import importlib.util
import hashlib
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("review_workspace_server.py")
SPEC = importlib.util.spec_from_file_location("review_workspace_server", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _collections(tmp_path):
    path = tmp_path / "collections.json"
    source = str((tmp_path / "sound.wav").resolve())
    path.write_text(json.dumps({
        "record_type": "slo_review_collections",
        "summary": {"suggest": 1, "review": 0, "auto_rename": 0, "never_act": 0},
        "n_plan_rows": 1, "n_joined_evidence": 1,
        "source_plan_sha256": "a" * 64,
        "collections": {"suggest": [{"path": source, "action": "suggest", "predicted_class": "Kick", "review_evidence": {"facets": {"form_hint": "possibly_one_shot", "heuristic_tags": []}}}], "review": [], "auto_rename": [], "never_act": []},
    }), encoding="utf-8")
    return path, source


def test_workspace_summary_search_and_feedback(tmp_path):
    collections, source = _collections(tmp_path)
    log = tmp_path / "feedback.jsonl"
    workspace = MODULE.ReviewWorkspace(collections, log)
    assert workspace.summary()["safety"]["source_audio_served"] is False
    assert workspace.items("suggest", 10)["n_returned"] == 1
    result = workspace.search("kick spaceship", 10)
    assert result["safety"]["text_created_labels"] is False
    event = workspace.record_feedback({"path": source, "event_type": "not_in_list", "note": "machine hit"})
    assert event["promoted_to_gold"] is False
    assert len(workspace.feedback.read_events(log)) == 1


def test_workspace_rejects_unknown_path(tmp_path):
    collections, _ = _collections(tmp_path)
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl")
    try:
        workspace.record_feedback({"path": str((tmp_path / "other.wav").resolve()), "event_type": "note", "note": "x"})
    except ValueError as exc:
        assert "not in" in str(exc)
    else:
        raise AssertionError("unknown feedback path was accepted")


def test_similarity_requires_embedding_cache(tmp_path):
    collections, source = _collections(tmp_path)
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl")
    try:
        workspace.similar(source)
    except ValueError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("unconfigured similarity search was accepted")


def test_class_gate_review_queue_is_read_only_and_filterable(tmp_path):
    collections, _ = _collections(tmp_path)
    queue = tmp_path / "class_gate.json"
    queue.write_text(json.dumps({
        "record_type": "slo_class_conditional_gate_testing_review",
        "candidate_classes": {"Kick": 0.8, "Snare": 0.7},
        "testing_summary": {"n_review_candidates": 2},
        "rows": [
            {"path": "/tmp/kick.wav", "candidate_class": "Kick", "auto_approved": False},
            {"path": "/tmp/snare.wav", "candidate_class": "Snare", "auto_approved": False},
        ],
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl", class_gate_queue_path=queue)
    assert workspace.summary()["class_gate_review"]["n_candidates"] == 2
    result = workspace.class_gate_items("Kick", 10)
    assert result["n_returned"] == 1
    assert result["safety"]["rename_actions"] is False


def test_class_gate_fusion_review_packet_is_read_only_and_filterable(tmp_path):
    collections, _ = _collections(tmp_path)
    packet = tmp_path / "class_gate_fusion.json"
    packet.write_text(json.dumps({
        "record_type": "slo_class_gate_fusion_review_packet",
        "decision": "review-only; name evidence never overrides audio or gate evidence",
        "summary": {
            "n_rows": 3,
            "fusion_states": {"audio_name_agree": 1, "audio_name_conflict": 1, "audio_only_no_name_token": 1},
        },
        "safety": {"auto_approved": False},
        "rows": [
            {"path": "/tmp/kick.wav", "candidate_class": "Kick", "fusion_state": "audio_name_agree", "auto_approved": False},
            {"path": "/tmp/snare.wav", "candidate_class": "Snare", "fusion_state": "audio_name_conflict", "auto_approved": False},
            {"path": "/tmp/clap.wav", "candidate_class": "Clap", "fusion_state": "audio_only_no_name_token", "auto_approved": False},
        ],
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl", class_gate_fusion_path=packet)
    summary = workspace.summary()["class_gate_fusion_review"]
    assert summary["enabled"] is True
    assert summary["n_candidates"] == 3
    result = workspace.class_gate_fusion_items(fusion_state="audio_name_conflict", limit=10)
    assert result["n_returned"] == 1
    assert result["safety"]["rename_actions"] is False
    assert result["safety"]["auto_approved"] is False


def test_approval_gate_is_read_only_and_reason_filterable(tmp_path):
    collections, _ = _collections(tmp_path)
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({
        "record_type": "slo_rename_approval_gate_audit",
        "qualification_summary": {"suggestion_rows": 2, "duplicate_blocked_rows": 1, "suggestion_rows_without_duplicate_flags": 1},
        "counts": {"blocked": 2},
        "rows": [
            {"path": "/tmp/a.wav", "status": "blocked", "reasons": ["suggestion_requires_explicit_approval", "exact_duplicate_alias"]},
            {"path": "/tmp/b.wav", "status": "blocked", "reasons": ["suggestion_requires_explicit_approval"]},
        ],
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl", approval_gate_path=approval)
    assert workspace.summary()["approval_gate_qualification"]["duplicate_blocked_rows"] == 1
    result = workspace.approval_items(reason="exact_duplicate_alias", limit=10)
    assert result["n_returned"] == 1
    assert result["safety"]["approval_granted"] is False
    clean = workspace.approval_items(exclude_reason="exact_duplicate_alias", limit=10)
    assert clean["n_returned"] == 1
    clean_all = workspace.approval_items(exclude_reason="exact_duplicate_alias,exact_duplicate_canonical,acoustic_near_duplicate", limit=10)
    assert clean_all["n_returned"] == 1


def test_browser_page_exposes_both_discovery_modes(tmp_path):
    collections, _ = _collections(tmp_path)
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl")
    handler = MODULE.make_handler(workspace)
    # The generated page is a fixed product surface; inspect the literal HTML
    # rather than starting another server in this unit test.
    assert "/api/search?q=" in MODULE.HTML
    assert "/api/similar?path=" in MODULE.HTML
    assert "/api/class-gate-fusion?limit=" in MODULE.HTML
    assert "/api/approval-gate?limit=" in MODULE.HTML


def test_evidence_packet_can_drive_name_feedback_without_audio_access(tmp_path):
    collections, source = _collections(tmp_path)
    packet = tmp_path / "evidence.json"
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "coverage": {"ensemble": 1, "name_candidate": 1},
        "rows": [{"path": source, "semantic_label": None,
                  "review_state": "suggestion_review_required",
                  "name_candidate": {"semantic_label": None,
                                     "name_state": "suggested_review_required",
                                     "candidate_filename": "kick_one-shot.wav"}}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False},
    }), encoding="utf-8")
    log = tmp_path / "feedback.jsonl"
    workspace = MODULE.ReviewWorkspace(collections, log, evidence_packet_path=packet)
    assert workspace.summary()["evidence_packet"]["n_rows"] == 1
    assert workspace.evidence_items(10)["n_returned"] == 1
    event = workspace.record_feedback({"path": source,
                                       "event_type": "accept_name_candidate"})
    assert event["candidate_filename"] == "kick_one-shot.wav"
    assert event["promoted_to_gold"] is False

    try:
        workspace.record_feedback({"path": source,
                                   "event_type": "accept_name_candidate",
                                   "candidate_filename": "other.wav"})
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched candidate filename was accepted")


def test_advisory_name_calibration_is_exposed_without_auto_action(tmp_path):
    collections, _ = _collections(tmp_path)
    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps({
        "record_type": "slo_label_free_name_calibration",
        "n_adjudicated_paths": 12,
        "slices": {"all": {"observed_precision": 0.9}},
        "promotion_candidate_slices": [],
        "safety": {"read_only": True, "auto_action_allowed": False,
                   "rename_actions": False},
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                                       name_calibration_path=calibration)
    assert workspace.summary()["name_calibration"]["n_adjudicated_paths"] == 12
    report = workspace.name_calibration_report()
    assert report["safety"]["auto_action_allowed"] is False
    assert "/api/name-calibration" in MODULE.HTML


def test_stratified_calibration_sample_is_exposed_review_only(tmp_path):
    collections, _ = _collections(tmp_path)
    sample = tmp_path / "calibration_sample.json"
    sample.write_text(json.dumps({
        "record_type": "slo_label_free_calibration_sample_manifest",
        "method_version": "label_free_calibration_sample_v2",
        "n_source_rows": 20, "n_selected": 2,
        "lane_counts": {"model_disagreement": 1, "random_audit": 1},
        "domain_counts": {"music_sample": 2},
        "exclusions": {"sealed_holdout_collections": [], "duplicate_content_rows_excluded": 0},
        "rows": [
            {"path": "/tmp/a.wav", "semantic_label": None,
             "lane": "model_disagreement", "domain": "music_sample"},
            {"path": "/tmp/b.wav", "semantic_label": None,
             "lane": "random_audit", "domain": "music_sample"},
        ],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "audio_modified": False,
                   "human_ear_review_required_for_calibration": True},
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                                       calibration_sample_path=sample)
    summary = workspace.summary()["calibration_sample"]
    assert summary["n_selected"] == 2
    assert workspace.calibration_sample_items(lane="random_audit", limit=10)["n_returned"] == 1
    result = workspace.calibration_sample_items(domain="music_sample", limit=10)
    assert result["safety"]["human_ear_review_required"] is True
    assert "/api/calibration-sample" in MODULE.HTML


def test_calibration_sample_binds_to_unchanged_source_packet(tmp_path):
    collections, _ = _collections(tmp_path)
    packet = tmp_path / "evidence.json"
    packet.write_text(json.dumps({"record_type": "slo_label_free_evidence_packet",
                                  "rows": [], "safety": {"read_only": True}}), encoding="utf-8")
    sample = tmp_path / "calibration_sample.json"
    payload = {
        "record_type": "slo_label_free_calibration_sample_manifest",
        "method_version": "label_free_calibration_sample_v2",
        "source_packet": str(packet),
        "source_packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        "n_selected": 1,
        "exclusions": {"sealed_holdout_collections": [], "duplicate_content_rows_excluded": 0},
        "rows": [{"path": "/tmp/a.wav", "semantic_label": None}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "audio_modified": False,
                   "human_ear_review_required_for_calibration": True},
    }
    sample.write_text(json.dumps(payload), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                                       calibration_sample_path=sample)
    assert workspace.summary()["calibration_sample"]["source_packet_sha256"] == payload["source_packet_sha256"]
    packet.write_text(packet.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    try:
        MODULE.ReviewWorkspace(collections, tmp_path / "other-feedback.jsonl",
                               calibration_sample_path=sample)
    except ValueError as exc:
        assert "hash does not match" in str(exc)
    else:
        raise AssertionError("changed source packet was accepted")


def test_calibration_sample_rows_include_bound_candidate_evidence(tmp_path):
    collections, source = _collections(tmp_path)
    packet = tmp_path / "evidence.json"
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "rows": [{"path": source, "semantic_label": None,
                  "domain_route": {"domain_suggestion": "music_sample"},
                  "name_candidate": {"candidate_filename": "kick.wav",
                                     "semantic_label": None},
                  "fused_decision": {"decision": "suggest", "candidate_label": "Kick",
                                     "semantic_label": None}}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False},
    }), encoding="utf-8")
    sample = tmp_path / "calibration_sample.json"
    sample.write_text(json.dumps({
        "record_type": "slo_label_free_calibration_sample_manifest",
        "method_version": "label_free_calibration_sample_v2",
        "source_packet": str(packet),
        "source_packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        "n_selected": 1,
        "exclusions": {"sealed_holdout_collections": [], "duplicate_content_rows_excluded": 0},
        "rows": [{"path": source, "semantic_label": None, "lane": "random_audit"}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "audio_modified": False,
                   "human_ear_review_required_for_calibration": True},
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                                       evidence_packet_path=packet,
                                       calibration_sample_path=sample)
    row = workspace.calibration_sample_items(limit=1)["items"][0]
    assert row["evidence"]["name_candidate"]["candidate_filename"] == "kick.wav"
    assert row["evidence"]["fused_decision"]["candidate_label"] == "Kick"


def test_calibration_sample_rejects_different_loaded_evidence_packet(tmp_path):
    collections, source = _collections(tmp_path)
    packet_a = tmp_path / "evidence-a.json"
    packet_b = tmp_path / "evidence-b.json"
    base = {"record_type": "slo_label_free_evidence_packet", "rows": [],
            "safety": {"read_only": True}}
    packet_a.write_text(json.dumps(base), encoding="utf-8")
    packet_b.write_text(json.dumps({**base, "rows": [{"path": source, "semantic_label": None}]}), encoding="utf-8")
    sample = tmp_path / "calibration_sample.json"
    sample.write_text(json.dumps({
        "record_type": "slo_label_free_calibration_sample_manifest",
        "method_version": "label_free_calibration_sample_v2",
        "source_packet": str(packet_a),
        "source_packet_sha256": hashlib.sha256(packet_a.read_bytes()).hexdigest(),
        "n_selected": 0, "rows": [],
        "exclusions": {"sealed_holdout_collections": [], "duplicate_content_rows_excluded": 0},
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "audio_modified": False,
                   "human_ear_review_required_for_calibration": True},
    }), encoding="utf-8")
    try:
        MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                               evidence_packet_path=packet_b,
                               calibration_sample_path=sample)
    except ValueError as exc:
        assert "does not match loaded evidence packet" in str(exc)
    else:
        raise AssertionError("mismatched loaded evidence packet was accepted")


def test_calibration_sample_rejects_duplicate_or_relative_paths(tmp_path):
    collections, _ = _collections(tmp_path)
    sample = tmp_path / "calibration_sample.json"
    sample.write_text(json.dumps({
        "record_type": "slo_label_free_calibration_sample_manifest",
        "method_version": "label_free_calibration_sample_v2", "n_selected": 2,
        "exclusions": {"sealed_holdout_collections": [], "duplicate_content_rows_excluded": 0},
        "rows": [{"path": "/tmp/a.wav", "semantic_label": None},
                 {"path": "/tmp/a.wav", "semantic_label": None}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "audio_modified": False,
                   "human_ear_review_required_for_calibration": True},
    }), encoding="utf-8")
    try:
        MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                               calibration_sample_path=sample)
    except ValueError as exc:
        assert "duplicate path" in str(exc)
    else:
        raise AssertionError("duplicate calibration row was accepted")


def test_feedback_can_reference_calibration_only_rows(tmp_path):
    collections, _ = _collections(tmp_path)
    sample_path = "/tmp/calibration-only.wav"
    sample = tmp_path / "calibration_sample.json"
    sample.write_text(json.dumps({
        "record_type": "slo_label_free_calibration_sample_manifest",
        "method_version": "label_free_calibration_sample_v2", "n_selected": 1,
        "exclusions": {"sealed_holdout_collections": [], "duplicate_content_rows_excluded": 0},
        "rows": [{"path": sample_path, "semantic_label": None}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "audio_modified": False,
                   "human_ear_review_required_for_calibration": True},
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                                       calibration_sample_path=sample)
    event = workspace.record_feedback({"path": sample_path, "event_type": "note",
                                       "note": "owner review pending"})
    assert event["path"] == sample_path
    assert event["promoted_to_gold"] is False


def test_legacy_calibration_manifest_is_rejected(tmp_path):
    collections, _ = _collections(tmp_path)
    sample = tmp_path / "legacy-calibration.json"
    sample.write_text(json.dumps({
        "record_type": "slo_label_free_calibration_sample_manifest",
        "method_version": "label_free_calibration_sample_v1",
        "n_selected": 0, "rows": [],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "audio_modified": False,
                   "human_ear_review_required_for_calibration": True},
    }), encoding="utf-8")
    try:
        MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                               calibration_sample_path=sample)
    except ValueError as exc:
        assert "v2 integrity contract" in str(exc)
    else:
        raise AssertionError("legacy calibration manifest was accepted")


def test_fused_candidate_feedback_binds_to_packet_candidate(tmp_path):
    collections, source = _collections(tmp_path)
    packet = tmp_path / "evidence.json"
    packet.write_text(json.dumps({
        "record_type": "slo_label_free_evidence_packet",
        "coverage": {"ensemble": 1, "fused_decision": 1},
        "rows": [{"path": source, "semantic_label": None,
                  "fused_decision": {"decision": "suggest", "candidate_label": "Kick",
                                      "semantic_label": None}}],
        "safety": {"read_only": True, "semantic_labels_created": False,
                   "rename_actions": False, "source_audio_modified": False},
    }), encoding="utf-8")
    workspace = MODULE.ReviewWorkspace(collections, tmp_path / "feedback.jsonl",
                                       evidence_packet_path=packet)
    event = workspace.record_feedback({"path": source, "event_type": "accept_fused_candidate"})
    assert event["candidate_label"] == "Kick"
    try:
        workspace.record_feedback({"path": source, "event_type": "accept_fused_candidate",
                                   "candidate_label": "Snare"})
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched fused candidate was accepted")
