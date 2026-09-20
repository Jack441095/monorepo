"""Contract tests for AutoMix Listening Benchmark v1."""

from __future__ import annotations

import copy
import importlib.util
import json
import stat
from pathlib import Path

import numpy as np
import pytest

from audio_analysis.mixdown.stem_prep import read_wav_stereo, write_wav

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "eval" / "automix_listening_benchmark.py"
SPEC = importlib.util.spec_from_file_location("automix_listening_benchmark", SCRIPT)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def _wav(path: Path, *, frequency: float, amplitude: float, seconds: float = 1.0,
         sample_rate: int = 44100) -> None:
    time = np.arange(int(seconds * sample_rate), dtype=np.float64) / sample_rate
    audio = amplitude * np.sin(2.0 * np.pi * frequency * time)
    path.write_bytes(write_wav(audio.tolist(), audio.tolist(), sample_rate, bit_depth=24))


def _lineage(path: Path) -> None:
    path.write_text(json.dumps({
        "schema": "audio-too.automix-render-lineage/v1",
        "code_revision": "git:test-revision",
        "render_seed": 42,
        "baseline_system": "rule-only-v1",
        "candidate_system": "advisor-preview-v1",
        "configuration": {"genre": "pop", "target_lufs": -14},
    }), encoding="utf-8")


def _relationship_study(
    root: Path, *, project_id: str = "p1", assignment_id: str = "assignment-1",
    strategy: str = "section_level_automation", candidate_label: str = "A",
) -> None:
    package = root / "pair-opaque"
    package.mkdir(parents=True)
    candidate_id = "rel-001-candidate-01"
    relationship_type = "kick_bass_competition"
    private = {
        "schema": "audio-too.automix-listening-package-key/v1",
        "assignment": {
            "schema": "audio-too.automix-blind-key/v1",
            "assignment_id": assignment_id,
            "project_id": project_id,
            "comparison_id": "relationship-audition:opaque",
            "A": "candidate" if candidate_label == "A" else "baseline",
            "B": "candidate" if candidate_label == "B" else "baseline",
        },
        "render_lineage": {
            "candidate_system": "automix-relationship-candidate-offline-v1",
            "configuration": {
                "production_processing_enabled": False,
                "candidate": {
                    "schema": "audio-too.relationship-candidate.v1",
                    "candidate_id": candidate_id,
                    "strategy": strategy,
                    "score": 0.8,
                },
                "relationship": {
                    "relationship_id": "rel-001",
                    "relationship_type": relationship_type,
                },
            },
        },
    }
    (package / "private_lineage.json").write_text(json.dumps(private), encoding="utf-8")
    (root / "reviewer_index.json").write_text(json.dumps({
        "schema": "audio-too.relationship-candidate-study-index.v1",
        "project_id": project_id,
        "production_processing_enabled": False,
        "comparisons": [{
            "package": "pair-opaque",
            "assignment_id": assignment_id,
            "relationship_id": "rel-001",
            "relationship_type": relationship_type,
            "candidate_id": candidate_id,
            "strategy": strategy,
            "predicted_score": 0.8,
        }],
    }), encoding="utf-8")


def _rating(project_id: str, assignment_id: str, listener: str, preferred: str) -> dict:
    return {
        "schema": benchmark.RATING_SCHEMA,
        "project_id": project_id,
        "assignment_id": assignment_id,
        "listener_id": listener,
        "listener_experience": "professional",
        "confidence": 4,
        "preferred": preferred,
        "scores": {field: 4 for field in benchmark.SCORE_FIELDS},
        "failure_flags": [],
    }


def test_checked_in_manifest_declares_twenty_slots_but_is_not_false_evidence() -> None:
    result = benchmark.validate_manifest()

    assert result["declared_projects"] == 20
    assert result["eligible_projects"] == 0
    assert len(result["pending_projects"]) == 20
    assert result["ready"] is False


def test_eligible_project_requires_explicit_rights_and_real_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    stems = tmp_path / "assets" / "stems"
    stems.mkdir(parents=True)
    (stems / "lead.wav").write_bytes(b"RIFF")
    (tmp_path / "assets" / "rough.wav").write_bytes(b"RIFF")
    (tmp_path / "assets" / "rights.md").write_text("consented", encoding="utf-8")
    manifest = {
        "schema": benchmark.SCHEMA,
        "projects": [{
            "id": "p1",
            "status": "eligible",
            "genre": "pop",
            "density": "dense",
            "source_quality": "clean",
            "render_seed": 1,
            "stems_path": "assets/stems",
            "rough_mix_path": "assets/rough.wav",
            "human_mix_path": None,
            "rights": {
                "status": "consented",
                "internal_evaluation_allowed": True,
                "evidence_path": "assets/rights.md",
            },
        }],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = benchmark.validate_manifest(path)

    assert result["eligible_projects"] == 1
    assert result["errors"] == []
    assert result["ready"] is False  # still below 20 and missing required coverage


def test_missing_rights_evidence_disqualifies_claimed_eligible_project(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    manifest = {
        "schema": benchmark.SCHEMA,
        "projects": [{
            "id": "p1", "status": "eligible", "genre": "pop", "density": "dense",
            "source_quality": "clean", "stems_path": "missing", "rough_mix_path": "missing.wav",
            "render_seed": 1,
            "rights": {"status": "licensed", "internal_evaluation_allowed": True,
                       "evidence_path": "missing-rights.md"},
        }],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = benchmark.validate_manifest(path)

    assert result["eligible_projects"] == 0
    assert "rights evidence file does not exist" in result["errors"][0]
    assert result["ready"] is False


def test_blind_assignment_is_stable_and_public_record_hides_mapping() -> None:
    first = benchmark.blind_assignment("project", "candidate-v2", "study-secret")
    second = benchmark.blind_assignment("project", "candidate-v2", "study-secret")
    public = benchmark.public_assignment("project", "candidate-v2", "study-secret")

    assert first == second
    assert set(first) == {"A", "B"}
    assert set(first.values()) == {"baseline", "candidate"}
    assert "baseline" not in public.values()
    assert "candidate" not in public.values()
    assert len(public["mapping_commitment"]) == 64


def test_assignment_bundle_separates_public_record_from_unblinding_key() -> None:
    bundle = benchmark.assignment_bundle("project", "candidate-v2", "study-secret")

    assert "A" not in bundle["public"] or bundle["public"]["A"] not in {"baseline", "candidate"}
    assert set((bundle["private"]["A"], bundle["private"]["B"])) == {"baseline", "candidate"}
    assert bundle["public"]["mapping_commitment"] == bundle["private"]["mapping_commitment"]


def test_blind_package_level_matches_and_preserves_private_lineage(tmp_path) -> None:
    baseline = tmp_path / "baseline.wav"
    candidate = tmp_path / "candidate.wav"
    lineage = tmp_path / "lineage.json"
    output = tmp_path / "study" / "pair"
    _wav(baseline, frequency=440, amplitude=0.15)
    _wav(candidate, frequency=330, amplitude=0.65)
    _lineage(lineage)

    result = benchmark.build_blind_package(
        project_id="lbv1-001",
        comparison_id="candidate-v1",
        baseline_path=baseline,
        candidate_path=candidate,
        lineage_path=lineage,
        secret="study-secret",
        output_dir=output,
    )

    assert abs(result["loudness_bias_lu"]) <= benchmark.MAX_LOUDNESS_BIAS_LU
    assert result["rms_difference"] > benchmark.MIN_RMS_DIFFERENCE
    assert set(path.name for path in output.iterdir()) == {
        "A.wav", "B.wav", "listener_manifest.json", "private_lineage.json"
    }
    public = json.loads((output / "listener_manifest.json").read_text(encoding="utf-8"))
    private = json.loads((output / "private_lineage.json").read_text(encoding="utf-8"))
    assert "baseline" not in public.values()
    assert "candidate" not in public.values()
    assert set((private["assignment"]["A"], private["assignment"]["B"])) == {
        "baseline", "candidate"
    }
    assert private["render_lineage"]["render_seed"] == 42
    assert len(private["source_hashes"]["baseline_sha256"]) == 64
    assert len(private["output_hashes"]["A_sha256"]) == 64
    assert stat.S_IMODE((output / "private_lineage.json").stat().st_mode) == 0o600
    assert read_wav_stereo((output / "A.wav").read_bytes())["sample_rate"] == 44100


def test_blind_package_rejects_identical_or_misaligned_pairs(tmp_path) -> None:
    baseline = tmp_path / "baseline.wav"
    identical = tmp_path / "identical.wav"
    shorter = tmp_path / "shorter.wav"
    lineage = tmp_path / "lineage.json"
    _wav(baseline, frequency=440, amplitude=0.2)
    identical.write_bytes(baseline.read_bytes())
    _wav(shorter, frequency=330, amplitude=0.2, seconds=0.8)
    _lineage(lineage)

    with pytest.raises(benchmark.ManifestError, match="effectively identical"):
        benchmark.build_blind_package(
            project_id="p", comparison_id="c", baseline_path=baseline,
            candidate_path=identical, lineage_path=lineage, secret="secret",
            output_dir=tmp_path / "identical-output",
        )
    with pytest.raises(benchmark.ManifestError, match="lengths differ"):
        benchmark.build_blind_package(
            project_id="p", comparison_id="c", baseline_path=baseline,
            candidate_path=shorter, lineage_path=lineage, secret="secret",
            output_dir=tmp_path / "short-output",
        )


def test_blind_package_refuses_to_overwrite_existing_study(tmp_path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(benchmark.ManifestError, match="already exists"):
        benchmark.build_blind_package(
            project_id="p", comparison_id="c", baseline_path=tmp_path / "none",
            candidate_path=tmp_path / "none2", lineage_path=tmp_path / "none3",
            secret="secret", output_dir=output,
        )


def test_relationship_candidate_packages_are_blind_atomic_and_offline_only(tmp_path) -> None:
    sample_rate = 8_000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    prepared = [
        {"name": "Kick.wav", "samples": (0.2 * np.sin(2 * np.pi * 100 * time)).tolist(),
         "sample_rate": sample_rate},
        {"name": "Bass.wav", "samples": (0.2 * np.sin(2 * np.pi * 220 * time)).tolist(),
         "sample_rate": sample_rate},
    ]
    relationship = {
        "schema": "audio-too.relationship.v1",
        "relationship_id": "rel-001",
        "relationship_type": "kick_bass_competition",
        "intervention_target": "Bass.wav",
        "protected_stem": "Kick.wav",
        "applies_automatically": False,
        "candidate_strategies": [{
            "schema": "audio-too.relationship-candidate.v1",
            "candidate_id": "rel-001-candidate-01",
            "strategy": "section_level_automation",
            "target_stem": "Bass.wav",
            "section_ids": ["section-001"],
            "section_ranges": [{
                "section_id": "section-001", "start_seconds": 0.0, "end_seconds": 1.0,
            }],
            "parameters": {"gain_db": -2.0, "attack_ms": 80.0, "release_ms": 180.0},
            "applies_automatically": False,
        }],
    }
    original = copy.deepcopy(prepared)
    seeds = []

    def render(stems, _plan, seed):
        seeds.append(seed)
        summed = np.sum([np.asarray(stem["samples"]) for stem in stems], axis=0) * 0.5
        return {
            "mixdown_wav_bytes": write_wav(
                summed.tolist(), summed.tolist(), sample_rate, bit_depth=24
            ),
            "quality_gate": {"passed": True},
        }

    output = tmp_path / "relationship-study"
    result = benchmark.build_relationship_candidate_packages(
        project_id="rights-cleared-project",
        prepared_stems=prepared,
        mix_plan=object(),
        relationships=[relationship],
        render_seed=91,
        secret="study-secret",
        output_root=output,
        rights_authorized=True,
        render_fn=render,
    )

    assert result["package_count"] == 1
    assert result["production_processing_enabled"] is False
    assert prepared == original
    assert seeds == [91, 91]
    reviewer = json.loads((output / "reviewer_index.json").read_text(encoding="utf-8"))
    assert reviewer["production_processing_enabled"] is False
    assert reviewer["comparisons"][0]["strategy"] == "section_level_automation"
    assert stat.S_IMODE((output / "reviewer_index.json").stat().st_mode) == 0o600
    pair = output / reviewer["comparisons"][0]["package"]
    public_text = (pair / "listener_manifest.json").read_text(encoding="utf-8")
    assert "section_level_automation" not in public_text
    assert "rel-001-candidate-01" not in public_text
    private = json.loads((pair / "private_lineage.json").read_text(encoding="utf-8"))
    assert private["render_lineage"]["configuration"]["production_processing_enabled"] is False


def test_relationship_candidate_packages_require_explicit_rights(tmp_path) -> None:
    with pytest.raises(benchmark.ManifestError, match="explicit internal-evaluation rights"):
        benchmark.build_relationship_candidate_packages(
            project_id="project",
            prepared_stems=[],
            mix_plan=object(),
            relationships=[],
            render_seed=1,
            secret="secret",
            output_root=tmp_path / "study",
            rights_authorized=False,
        )


def test_coordinated_automation_preview_builds_one_blind_offline_package(tmp_path) -> None:
    sample_rate = 8_000
    time = np.arange(sample_rate * 2, dtype=np.float64) / sample_rate
    prepared = [
        {"name": "Vocal.wav", "samples": (0.2 * np.sin(2 * np.pi * 330 * time)).tolist(),
         "sample_rate": sample_rate},
        {"name": "Pad.wav", "samples": (0.2 * np.sin(2 * np.pi * 220 * time)).tolist(),
         "sample_rate": sample_rate},
    ]
    relationship = {
        "schema": "audio-too.relationship.v1",
        "relationship_id": "rel-001",
        "relationship_type": "vocal_instrument_competition",
        "source_stems": ["Vocal.wav", "Pad.wav"],
        "protected_stem": "Vocal.wav",
        "intervention_target": "Pad.wav",
        "status": "candidate",
        "evidence": {
            "section_ids": ["section-001"],
            "section_collision_scores": {"section-001": 0.9},
            "collision_score": 0.9,
        },
        "candidate_strategies": [{
            "schema": "audio-too.relationship-candidate.v1",
            "candidate_id": "rel-001-candidate-01",
            "strategy": "section_level_automation",
            "target_stem": "Pad.wav",
            "section_ids": ["section-001"],
            "section_ranges": [{
                "section_id": "section-001", "start_seconds": 0.0, "end_seconds": 2.0,
            }],
            "parameters": {"gain_db": -1.5, "attack_ms": 80.0, "release_ms": 180.0},
            "score": 0.9,
            "applies_automatically": False,
        }],
        "applies_automatically": False,
    }
    original = copy.deepcopy(prepared)

    def render(stems, _plan, _seed):
        summed = np.sum([np.asarray(stem["samples"]) for stem in stems], axis=0) * 0.5
        return {
            "mixdown_wav_bytes": write_wav(
                summed.tolist(), summed.tolist(), sample_rate, bit_depth=24
            ),
            "quality_gate": {"passed": True},
        }

    output = tmp_path / "automation-preview"
    result = benchmark.build_automation_preview_package(
        project_id="rights-cleared-project",
        prepared_stems=prepared,
        mix_plan=object(),
        relationships=[relationship],
        render_seed=12,
        secret="study-secret",
        output_dir=output,
        rights_authorized=True,
        render_fn=render,
    )

    assert result["status"] == "packaged"
    assert result["move_count"] == 1
    assert result["production_processing_enabled"] is False
    assert prepared == original
    public_text = (output / "listener_manifest.json").read_text(encoding="utf-8")
    assert "Pad.wav" not in public_text
    assert "section_level_automation" not in public_text
    private = json.loads((output / "private_lineage.json").read_text(encoding="utf-8"))
    configuration = private["render_lineage"]["configuration"]
    assert configuration["production_processing_enabled"] is False
    assert configuration["automation_preview"]["moves"][0]["target_stem"] == "Pad.wav"


def test_automation_preview_reports_no_safe_moves_without_creating_package(tmp_path) -> None:
    output = tmp_path / "automation-preview"
    result = benchmark.build_automation_preview_package(
        project_id="rights-cleared-project",
        prepared_stems=[],
        mix_plan=object(),
        relationships=[],
        render_seed=12,
        secret="study-secret",
        output_dir=output,
        rights_authorized=True,
    )

    assert result["status"] == "no_safe_moves"
    assert result["move_count"] == 0
    assert not output.exists()


def test_render_project_pair_validates_plan_proposal_and_packages_seeded_renders(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    stems = tmp_path / "assets" / "stems"
    stems.mkdir(parents=True)
    _wav(stems / "vocal.wav", frequency=330, amplitude=0.15, seconds=1.2)
    _wav(stems / "kick.wav", frequency=60, amplitude=0.25, seconds=1.2)
    _wav(tmp_path / "assets" / "rough.wav", frequency=220, amplitude=0.15, seconds=1.2)
    (tmp_path / "assets" / "rights.md").write_text("owned test fixture", encoding="utf-8")
    project = {
        "id": "lbv1-test",
        "status": "eligible",
        "genre": "pop",
        "density": "sparse",
        "source_quality": "clean",
        "target_lufs": -14.0,
        "render_seed": 17,
        "stems_path": "assets/stems",
        "rough_mix_path": "assets/rough.wav",
        "rights": {
            "status": "owned",
            "internal_evaluation_allowed": True,
            "evidence_path": "assets/rights.md",
        },
    }

    def provider(plan, profiles, genre, target_lufs, *, correlation_id):
        del profiles, genre, target_lufs
        from audio_analysis.integration.kenn_advisor import mix_plan_revision

        return {
            "schema": "audio-too.kenn-advisor/v1",
            "source_plan_revision": mix_plan_revision(plan),
            "model_version": "fixture-advisor-v1",
            "prompt_version": "fixture-prompt-v1",
            "correlation_id": correlation_id,
            "operations": [{
                "stem_id": plan.stems[0].stem_name,
                "operation": "gain_delta",
                "value": 1.0,
                "unit": "dB",
                "evidence_source_ids": ["fixture-evidence"],
                "confidence": 0.9,
                "reason": "Exercise the real bounded candidate path.",
            }],
        }

    def seeded_render(prepared, plan, seed):
        del prepared
        amplitude = 0.08 * (10.0 ** (plan.stems[0].gain_db / 20.0))
        time = np.arange(44100, dtype=np.float64) / 44100
        audio = (
            amplitude * np.sin(2.0 * np.pi * (220 + seed) * time)
            + 0.06 * np.sin(2.0 * np.pi * 440 * time)
        )
        return {
            "mixdown_wav_bytes": write_wav(audio.tolist(), audio.tolist(), 44100, bit_depth=24),
            "quality_gate": {"passed": True, "technical_score": 90, "minimum_score": 65},
        }

    monkeypatch.setattr(benchmark, "_seeded_render", seeded_render)

    result = benchmark.render_project_pair(
        project,
        output_dir=tmp_path / "study" / "lbv1-test",
        secret="study-secret",
        proposal_provider=provider,
    )

    assert result["status"] == "packaged"
    assert result["operation_count"] == 1
    private = json.loads(
        (tmp_path / "study" / "lbv1-test" / "private_lineage.json").read_text(encoding="utf-8")
    )
    assert private["render_lineage"]["candidate_system"] == "fixture-advisor-v1"
    assert private["render_lineage"]["configuration"]["proposal"]["operations"][0]["value"] == 1.0
    assert len(private["render_lineage"]["configuration"]["stem_sha256"]) == 2


def test_render_project_pair_records_real_advisor_abstention_without_false_candidate(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    stems = tmp_path / "assets" / "stems"
    stems.mkdir(parents=True)
    _wav(stems / "vocal.wav", frequency=330, amplitude=0.15)
    _wav(tmp_path / "assets" / "rough.wav", frequency=220, amplitude=0.15)
    (tmp_path / "assets" / "rights.md").write_text("owned", encoding="utf-8")
    project = {
        "id": "abstain", "status": "eligible", "genre": "pop", "target_lufs": -14.0,
        "render_seed": 1, "stems_path": "assets/stems", "rough_mix_path": "assets/rough.wav",
        "rights": {"status": "owned", "internal_evaluation_allowed": True,
                   "evidence_path": "assets/rights.md"},
    }

    result = benchmark.render_project_pair(
        project,
        output_dir=tmp_path / "study" / "abstain",
        secret="study-secret",
        proposal_provider=lambda *args, **kwargs: None,
    )

    assert result["status"] == "no_proposal"
    assert not (tmp_path / "study" / "abstain").exists()


def test_batch_render_requires_secret_even_when_corpus_has_no_eligible_projects(tmp_path) -> None:
    with pytest.raises(benchmark.ManifestError, match="non-empty study secret"):
        benchmark.render_manifest(
            benchmark.DEFAULT_MANIFEST,
            output_root=tmp_path / "study",
            secret="",
        )


def test_rating_scorecard_is_strict_and_reports_multi_rater_coverage(tmp_path) -> None:
    def row(listener: str, preferred: str) -> dict:
        return {
            "schema": benchmark.RATING_SCHEMA,
            "project_id": "p1",
            "assignment_id": "blind-1",
            "listener_id": listener,
            "listener_experience": "professional",
            "confidence": 4,
            "preferred": preferred,
            "scores": {field: 4 for field in benchmark.SCORE_FIELDS},
        }

    path = tmp_path / "ratings.jsonl"
    path.write_text("\n".join(json.dumps(value) for value in [row("l1", "A"), row("l2", "B")]),
                    encoding="utf-8")

    report = benchmark.score_ratings(path)

    assert report["ratings"] == 2
    assert report["preferences"] == {"A": 1, "B": 1}
    assert report["projects_with_multiple_raters"] == 1
    assert report["minimum_two_raters_every_project"] is True

    key_path = tmp_path / "key.json"
    key_path.write_text(json.dumps({"assignments": [{
        "schema": "audio-too.automix-blind-key/v1",
        "assignment_id": "blind-1",
        "A": "candidate",
        "B": "baseline",
    }]}), encoding="utf-8")
    unblinded = benchmark.score_ratings(path, key_path)
    assert unblinded["system_preferences"] == {"candidate": 1, "baseline": 1}


def test_rating_rejects_partial_scorecard(tmp_path) -> None:
    path = tmp_path / "ratings.jsonl"
    path.write_text(json.dumps({
        "schema": benchmark.RATING_SCHEMA,
        "project_id": "p1",
        "assignment_id": "blind-1",
        "listener_id": "l1",
        "listener_experience": "professional",
        "confidence": 5,
        "preferred": "A",
        "scores": {"balance": 5},
    }), encoding="utf-8")

    with pytest.raises(benchmark.ManifestError, match="v1 scorecard"):
        benchmark.score_ratings(path)


def test_rating_rejects_duplicates_and_unknown_failure_categories(tmp_path) -> None:
    base = {
        "schema": benchmark.RATING_SCHEMA,
        "project_id": "p1",
        "assignment_id": "a1",
        "listener_id": "l1",
        "listener_experience": "professional",
        "confidence": 4,
        "preferred": "A",
        "scores": {field: 4 for field in benchmark.SCORE_FIELDS},
        "failure_flags": [],
    }
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(f"{json.dumps(base)}\n{json.dumps(base)}\n", encoding="utf-8")
    with pytest.raises(benchmark.ManifestError, match="duplicate listener/assignment"):
        benchmark.score_ratings(duplicate)

    malformed = dict(base)
    malformed["failure_flags"] = [{"category": "sounds_bad", "version": "A"}]
    bad_flag = tmp_path / "bad-flag.jsonl"
    bad_flag.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(benchmark.ManifestError, match="unknown category"):
        benchmark.score_ratings(bad_flag)


def test_statistics_use_projects_not_repeated_listener_votes_for_promotion(tmp_path) -> None:
    rows = []
    keys = []
    for project_index in range(20):
        project_id = f"p{project_index:02d}"
        assignment_id = f"a{project_index:02d}"
        candidate_label = "A" if project_index % 2 == 0 else "B"
        baseline_label = "B" if candidate_label == "A" else "A"
        keys.append({
            "schema": "audio-too.automix-blind-key/v1",
            "assignment_id": assignment_id,
            candidate_label: "candidate",
            baseline_label: "baseline",
        })
        for listener_index in range(2):
            rows.append({
                "schema": benchmark.RATING_SCHEMA,
                "project_id": project_id,
                "assignment_id": assignment_id,
                "listener_id": f"l{listener_index}",
                "listener_experience": "professional",
                "confidence": 5,
                "preferred": candidate_label,
                "scores": {field: 5 for field in benchmark.SCORE_FIELDS},
                "failure_flags": [{
                    "category": "muddy_low_end",
                    "version": baseline_label,
                    "stem_role": "bass",
                    "section": "chorus",
                }],
            })
    ratings = tmp_path / "ratings.jsonl"
    ratings.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    key_path = tmp_path / "keys.json"
    key_path.write_text(json.dumps({"assignments": keys}), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema": benchmark.SCHEMA,
        "projects": [{"id": f"p{index:02d}", "genre": "pop"} for index in range(20)],
    }), encoding="utf-8")

    report = benchmark.score_ratings(ratings, key_path, manifest_path)

    assert report["inter_rater_agreement"]["kappa"] == 1.0
    assert report["project_preferences"]["outcomes"] == {"candidate": 20}
    assert report["project_preferences"]["candidate_win_rate_95ci"][0] > 0.5
    assert report["promotion_gate"]["passed"] is True
    assert report["failure_ranking"][0] == {
        "category": "muddy_low_end",
        "system": "baseline",
        "genre": "pop",
        "stem_role": "bass",
        "section": "chorus",
        "count": 40,
        "project_count": 20,
    }


def test_many_votes_on_one_project_cannot_pass_promotion_gate(tmp_path) -> None:
    rows = [{
        "schema": benchmark.RATING_SCHEMA,
        "project_id": "only-project",
        "assignment_id": "only-assignment",
        "listener_id": f"listener-{index}",
        "listener_experience": "professional",
        "confidence": 5,
        "preferred": "A",
        "scores": {field: 5 for field in benchmark.SCORE_FIELDS},
        "failure_flags": [],
    } for index in range(25)]
    ratings = tmp_path / "ratings.jsonl"
    ratings.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    key_path = tmp_path / "keys.json"
    key_path.write_text(json.dumps({"assignments": [{
        "schema": "audio-too.automix-blind-key/v1",
        "assignment_id": "only-assignment",
        "A": "candidate",
        "B": "baseline",
    }]}), encoding="utf-8")

    report = benchmark.score_ratings(ratings, key_path)

    assert report["ratings"] == 25
    assert report["projects_rated"] == 1
    assert report["promotion_gate"]["passed"] is False
    assert report["promotion_gate"]["checks"]["at_least_20_projects"] is False


def test_relationship_scoring_collapses_votes_to_assignment_and_stays_non_promotional(
    tmp_path,
) -> None:
    study = tmp_path / "study-p1"
    _relationship_study(study)
    ratings = tmp_path / "relationship-ratings.jsonl"
    rows = [
        _rating("p1", "assignment-1", "listener-1", "A"),
        _rating("p1", "assignment-1", "listener-2", "A"),
        _rating("p1", "assignment-1", "listener-3", "A"),
    ]
    ratings.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    report = benchmark.score_relationship_candidate_ratings(ratings, [study])

    assert report["ratings"] == 3
    assert report["assignments_rated"] == 1
    assert report["assignment_outcomes"] == [{
        "assignment_id": "assignment-1",
        "project_id": "p1",
        "relationship_id": "rel-001",
        "relationship_type": "kick_bass_competition",
        "candidate_id": "rel-001-candidate-01",
        "strategy": "section_level_automation",
        "predicted_score": 0.8,
        "raters": 3,
        "votes": {"candidate": 3},
        "outcome": "candidate",
    }]
    strategy = report["strategies"]["section_level_automation"]
    assert strategy["outcomes"] == {"candidate": 1}
    assert strategy["calibration_evidence_gate"]["passed"] is False
    assert strategy["calibration_evidence_gate"]["checks"]["at_least_five_projects"] is False
    assert report["production_promotion_authorized"] is False


def test_relationship_scoring_rejects_unknown_assignment_and_tampered_lineage(tmp_path) -> None:
    study = tmp_path / "study-p1"
    _relationship_study(study)
    ratings = tmp_path / "ratings.jsonl"
    ratings.write_text(
        json.dumps(_rating("p1", "unknown", "listener-1", "A")), encoding="utf-8"
    )
    with pytest.raises(benchmark.ManifestError, match="unknown relationship assignment"):
        benchmark.score_relationship_candidate_ratings(ratings, [study])

    ratings.write_text(
        json.dumps(_rating("p1", "assignment-1", "listener-1", "A")), encoding="utf-8"
    )
    index_path = study / "reviewer_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["comparisons"][0]["strategy"] = "static_eq"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(benchmark.ManifestError, match="private lineage disagree"):
        benchmark.score_relationship_candidate_ratings(ratings, [study])


def test_relationship_calibration_gate_requires_broad_consistent_assignment_evidence(
    tmp_path,
) -> None:
    roots = []
    rows = []
    for index in range(10):
        project_id = f"project-{index % 5}"
        assignment_id = f"assignment-{index}"
        candidate_label = "A" if index % 2 == 0 else "B"
        root = tmp_path / f"study-{index}"
        _relationship_study(
            root,
            project_id=project_id,
            assignment_id=assignment_id,
            candidate_label=candidate_label,
        )
        roots.append(root)
        rows.extend([
            _rating(project_id, assignment_id, f"listener-a-{index}", candidate_label),
            _rating(project_id, assignment_id, f"listener-b-{index}", candidate_label),
        ])
    ratings = tmp_path / "ratings.jsonl"
    ratings.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    report = benchmark.score_relationship_candidate_ratings(ratings, roots)
    strategy = report["strategies"]["section_level_automation"]

    assert strategy["projects"] == 5
    assert strategy["decisive_assignments"] == 10
    assert strategy["candidate_win_rate_95ci"][0] > 0.5
    assert strategy["inter_rater_agreement"]["kappa"] == 1.0
    assert strategy["calibration_evidence_gate"]["passed"] is True
    assert report["production_promotion_authorized"] is False


def test_unrated_relationship_strategy_remains_visible_and_fails_coverage_gate(tmp_path) -> None:
    automation = tmp_path / "automation"
    static_eq = tmp_path / "static-eq"
    _relationship_study(automation, assignment_id="rated")
    _relationship_study(
        static_eq, assignment_id="omitted", strategy="static_eq", candidate_label="B"
    )
    ratings = tmp_path / "ratings.jsonl"
    ratings.write_text(
        json.dumps(_rating("p1", "rated", "listener", "A")), encoding="utf-8"
    )

    report = benchmark.score_relationship_candidate_ratings(ratings, [automation, static_eq])

    assert report["assignment_coverage"] == 0.5
    omitted = report["strategies"]["static_eq"]
    assert omitted["assignments"] == 0
    assert omitted["available_assignments"] == 1
    assert omitted["calibration_evidence_gate"]["checks"][
        "all_available_assignments_rated"
    ] is False
    assert omitted["calibration_evidence_gate"]["passed"] is False
