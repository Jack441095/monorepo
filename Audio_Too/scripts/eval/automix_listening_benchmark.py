#!/usr/bin/env python3
"""Validate and score AutoMix Listening Benchmark v1.

This tool deliberately separates *benchmark infrastructure* from a benchmark-ready
corpus. A project is eligible only when its audio inputs exist and a usage-rights
record explicitly permits internal evaluation. Pending slots remain visible in the
coverage report but can never count toward readiness.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import random
import secrets
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from collections.abc import Callable

SOURCE_ROOT = Path(__file__).resolve().parents[2]
ROOT = SOURCE_ROOT
ANALYSIS_ROOT = SOURCE_ROOT / "studio" / "audio_analysis"
sys.path.insert(0, str(ANALYSIS_ROOT))
DEFAULT_MANIFEST = (
    ROOT / "studio" / "audio_analysis" / "audio_analysis" / "evals" / "listening_benchmark_v1.json"
)
SCHEMA = "audio-too.automix-listening-benchmark/v1"
RATING_SCHEMA = "audio-too.automix-listening-rating/v1"
MIN_PROJECTS = 20
REQUIRED_GENRES = {"pop", "rap", "electronic", "rock", "acoustic", "podcast"}
REQUIRED_DENSITIES = {"sparse", "dense"}
REQUIRED_SOURCE_QUALITY = {"clean", "problematic"}
SCORE_FIELDS = (
    "balance",
    "lead_focus",
    "low_end_clarity",
    "masking",
    "punch",
    "depth",
    "width",
    "tonal_character",
    "artifact_freedom",
    "intent_preservation",
    "overall_preference",
)
FAILURE_CATEGORIES = {
    "too_bright",
    "too_dull",
    "lead_too_forward",
    "lead_too_far_back",
    "lost_punch",
    "weak_low_end",
    "muddy_low_end",
    "over_compressed",
    "too_wet",
    "too_dry",
    "too_wide",
    "too_narrow",
    "masking",
    "audible_artifact",
    "intent_changed",
    "other",
}
MIN_DECISIVE_PROJECTS = 20
MIN_RATERS_PER_PROJECT = 2
MIN_AGREEMENT_KAPPA = 0.20
MIN_RELATIONSHIP_PROJECTS_PER_STRATEGY = 5
MIN_RELATIONSHIP_DECISIVE_ASSIGNMENTS = 10
MAX_LOUDNESS_BIAS_LU = 0.5
MIN_RMS_DIFFERENCE = 1e-7
TRUE_PEAK_CEILING_DBTP = -1.0


class ManifestError(ValueError):
    """Raised when the benchmark contract is malformed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError("Manifest root must be an object")
    return value


def _repo_path(value: object, *, field: str, required: bool) -> Path | None:
    if value in (None, ""):
        if required:
            raise ManifestError(f"{field} is required for an eligible project")
        return None
    if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ManifestError(f"{field} must be a repository-relative path")
    path = (ROOT / value).resolve()
    if ROOT.resolve() not in path.parents and path != ROOT.resolve():
        raise ManifestError(f"{field} escapes the repository")
    return path


def validate_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = _load_json(path)
    if data.get("schema") != SCHEMA:
        raise ManifestError(f"schema must be {SCHEMA}")
    projects = data.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ManifestError("projects must be a non-empty array")

    ids: set[str] = set()
    eligible: list[dict[str, Any]] = []
    pending: list[dict[str, str]] = []
    coverage: dict[str, Counter[str]] = {
        "genre": Counter(),
        "density": Counter(),
        "source_quality": Counter(),
    }
    errors: list[str] = []

    for index, project in enumerate(projects):
        label = f"projects[{index}]"
        if not isinstance(project, dict):
            errors.append(f"{label} must be an object")
            continue
        project_id = project.get("id")
        if not isinstance(project_id, str) or not project_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if project_id in ids:
            errors.append(f"duplicate project id: {project_id}")
            continue
        ids.add(project_id)
        status = project.get("status")
        if status not in {"pending_assets", "eligible", "retired"}:
            errors.append(f"{project_id}: invalid status")
            continue
        if status != "eligible":
            pending.append({"id": project_id, "status": str(status)})
            continue

        try:
            genre = project["genre"]
            density = project["density"]
            source_quality = project["source_quality"]
            if not all(isinstance(v, str) and v for v in (genre, density, source_quality)):
                raise ManifestError("coverage labels must be non-empty strings")
            rights = project.get("rights")
            if not isinstance(rights, dict) or rights.get("internal_evaluation_allowed") is not True:
                raise ManifestError("rights must explicitly allow internal evaluation")
            if rights.get("status") not in {"owned", "licensed", "public_domain", "consented"}:
                raise ManifestError("rights.status is not an eligible value")
            rights_file = _repo_path(rights.get("evidence_path"), field="rights.evidence_path", required=True)
            stems = _repo_path(project.get("stems_path"), field="stems_path", required=True)
            rough = _repo_path(project.get("rough_mix_path"), field="rough_mix_path", required=True)
            if rights_file is None or not rights_file.is_file():
                raise ManifestError("rights evidence file does not exist")
            if stems is None or not stems.is_dir() or not any(stems.glob("*.wav")):
                raise ManifestError("stems_path has no WAV stems")
            if rough is None or not rough.is_file():
                raise ManifestError("rough_mix_path does not exist")
            human = _repo_path(project.get("human_mix_path"), field="human_mix_path", required=False)
            if human is not None and not human.is_file():
                raise ManifestError("human_mix_path does not exist")
            target_lufs = project.get("target_lufs", -14.0)
            if not isinstance(target_lufs, (int, float)) or isinstance(target_lufs, bool) or not math.isfinite(target_lufs):
                raise ManifestError("target_lufs must be finite")
            render_seed = project.get("render_seed")
            if not isinstance(render_seed, int) or isinstance(render_seed, bool):
                raise ManifestError("render_seed must be an integer")
            if "arrangement_corrections" in project:
                from audio_analysis.mixdown.arrangement import (
                    validate_arrangement_correction_payload,
                )
                validate_arrangement_correction_payload(project["arrangement_corrections"])
        except (KeyError, ManifestError) as exc:
            errors.append(f"{project_id}: {exc}")
            continue

        eligible.append(project)
        coverage["genre"][genre] += 1
        coverage["density"][density] += 1
        coverage["source_quality"][source_quality] += 1

    missing_coverage = {
        "genre": sorted(REQUIRED_GENRES - set(coverage["genre"])),
        "density": sorted(REQUIRED_DENSITIES - set(coverage["density"])),
        "source_quality": sorted(REQUIRED_SOURCE_QUALITY - set(coverage["source_quality"])),
    }
    ready = (
        not errors
        and len(eligible) >= MIN_PROJECTS
        and not any(missing_coverage.values())
    )
    return {
        "schema": SCHEMA,
        "manifest": str(path),
        "declared_projects": len(projects),
        "eligible_projects": len(eligible),
        "pending_projects": pending,
        "errors": errors,
        "coverage": {key: dict(value) for key, value in coverage.items()},
        "missing_coverage": missing_coverage,
        "minimum_projects": MIN_PROJECTS,
        "ready": ready,
    }


def blind_assignment(project_id: str, comparison_id: str, secret: str) -> dict[str, str]:
    """Return a stable concealed A/B mapping for one comparison."""
    if not secret:
        raise ValueError("A non-empty study secret is required")
    digest = hashlib.sha256(f"{secret}\0{project_id}\0{comparison_id}".encode()).digest()
    if digest[0] & 1:
        return {"A": "candidate", "B": "baseline"}
    return {"A": "baseline", "B": "candidate"}


def public_assignment(project_id: str, comparison_id: str, secret: str) -> dict[str, str]:
    return assignment_bundle(project_id, comparison_id, secret)["public"]


def assignment_bundle(project_id: str, comparison_id: str, secret: str) -> dict[str, dict[str, str]]:
    """Create separate listener-safe and reviewer-only assignment records."""
    mapping = blind_assignment(project_id, comparison_id, secret)
    token = secrets.token_urlsafe(12)
    commitment = hashlib.sha256(
        f"{token}\0{mapping['A']}\0{mapping['B']}\0{secret}".encode()
    ).hexdigest()
    public = {
        "schema": "audio-too.automix-blind-assignment/v1",
        "assignment_id": token,
        "project_id": project_id,
        "comparison_id": comparison_id,
        "a_label": "A",
        "b_label": "B",
        "mapping_commitment": commitment,
    }
    private = {
        "schema": "audio-too.automix-blind-key/v1",
        "assignment_id": token,
        "project_id": project_id,
        "comparison_id": comparison_id,
        "A": mapping["A"],
        "B": mapping["B"],
        "mapping_commitment": commitment,
    }
    return {"public": public, "private": private}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_render_lineage(value: dict[str, Any]) -> None:
    required = {
        "schema",
        "code_revision",
        "render_seed",
        "baseline_system",
        "candidate_system",
        "configuration",
    }
    if set(value) != required:
        raise ManifestError(f"render lineage must contain exactly {sorted(required)}")
    if value["schema"] != "audio-too.automix-render-lineage/v1":
        raise ManifestError("render lineage schema is invalid")
    if not all(isinstance(value[key], str) and value[key] for key in (
        "code_revision", "baseline_system", "candidate_system"
    )):
        raise ManifestError("render lineage system and code identities must be non-empty strings")
    if not isinstance(value["render_seed"], int) or isinstance(value["render_seed"], bool):
        raise ManifestError("render_seed must be an integer")
    if not isinstance(value["configuration"], dict):
        raise ManifestError("configuration must be an object")


def build_blind_package(
    *,
    project_id: str,
    comparison_id: str,
    baseline_path: Path,
    candidate_path: Path,
    lineage_path: Path,
    secret: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Create an atomic, loudness-matched listener package and private lineage key."""
    import numpy as np

    from audio_analysis.analysis_core.loudness import (
        calculate_loudness_profile,
        calculate_true_peak_numpy,
    )
    from audio_analysis.export.ab_playback import prepare_ab_comparison
    from audio_analysis.mixdown.stem_prep import read_wav_stereo, write_wav

    if output_dir.exists():
        raise ManifestError(f"output directory already exists: {output_dir}")
    for label, path in (("baseline", baseline_path), ("candidate", candidate_path)):
        if not path.is_file():
            raise ManifestError(f"{label} WAV does not exist: {path}")
    lineage = _load_json(lineage_path)
    _validate_render_lineage(lineage)
    bundle = assignment_bundle(project_id, comparison_id, secret)
    baseline_bytes = baseline_path.read_bytes()
    candidate_bytes = candidate_path.read_bytes()
    try:
        prepared = prepare_ab_comparison(
            {"wav_bytes": baseline_bytes},
            {"wav_bytes": candidate_bytes},
            label_a="baseline",
            label_b="candidate",
            level_match_enabled=True,
            output_bit_depth=24,
        )
    except (OSError, ValueError) as exc:
        raise ManifestError(f"cannot prepare A/B audio: {exc}") from exc
    sync = prepared["sync_metadata"]
    if sync["length_a_samples"] != sync["length_b_samples"]:
        raise ManifestError("baseline and candidate lengths differ; benchmark pairs must align exactly")

    decoded_a = read_wav_stereo(prepared["wav_bytes_a"])
    decoded_b = read_wav_stereo(prepared["wav_bytes_b"])
    left_a = np.asarray(decoded_a["left"], dtype=np.float64)
    right_a = np.asarray(decoded_a["right"], dtype=np.float64)
    left_b = np.asarray(decoded_b["left"], dtype=np.float64)
    right_b = np.asarray(decoded_b["right"], dtype=np.float64)
    sample_rate = int(decoded_a["sample_rate"])
    initial_true_peaks = (
        float(calculate_true_peak_numpy(left_a, right_a)),
        float(calculate_true_peak_numpy(left_b, right_b)),
    )
    common_safety_gain_db = min(0.0, TRUE_PEAK_CEILING_DBTP - max(initial_true_peaks))
    if common_safety_gain_db < 0.0:
        common_gain = 10.0 ** (common_safety_gain_db / 20.0)
        left_a *= common_gain
        right_a *= common_gain
        left_b *= common_gain
        right_b *= common_gain
    lufs_a = float(calculate_loudness_profile(left_a.tolist(), right_a.tolist(), sample_rate)["integrated_lufs"])
    lufs_b = float(calculate_loudness_profile(left_b.tolist(), right_b.tolist(), sample_rate)["integrated_lufs"])
    true_peak_a = float(calculate_true_peak_numpy(left_a, right_a))
    true_peak_b = float(calculate_true_peak_numpy(left_b, right_b))
    loudness_bias = lufs_b - lufs_a
    if not (
        np.isfinite(lufs_a)
        and np.isfinite(lufs_b)
        and all(np.isfinite(channel).all() for channel in (left_a, right_a, left_b, right_b))
    ):
        raise ManifestError("prepared comparison contains non-finite audio or loudness")
    if abs(loudness_bias) > MAX_LOUDNESS_BIAS_LU:
        raise ManifestError(f"level-matched pair differs by {loudness_bias:.3f} LU")
    peak = float(max(np.max(np.abs(left_a)), np.max(np.abs(right_a)),
                     np.max(np.abs(left_b)), np.max(np.abs(right_b))))
    if peak > 1.0:
        raise ManifestError(f"prepared comparison exceeds full scale ({peak:.6f})")
    if max(true_peak_a, true_peak_b) > TRUE_PEAK_CEILING_DBTP + 0.05:
        raise ManifestError("prepared comparison exceeds the true-peak ceiling")
    rms_difference = float(np.sqrt(np.mean(
        np.square(left_b - left_a) + np.square(right_b - right_a)
    ) / 2.0))
    if rms_difference <= MIN_RMS_DIFFERENCE:
        raise ManifestError("baseline and candidate are effectively identical")

    mapping = bundle["private"]
    system_wavs = {
        "baseline": write_wav(left_a.tolist(), right_a.tolist(), sample_rate, bit_depth=24),
        "candidate": write_wav(left_b.tolist(), right_b.tolist(), sample_rate, bit_depth=24),
    }
    public = bundle["public"] | {
        "schema": "audio-too.automix-listening-package/v1",
        "files": {"A": "A.wav", "B": "B.wav"},
        "sample_rate": sample_rate,
        "duration_seconds": prepared["duration_seconds"],
        "loudness_match_tolerance_lu": MAX_LOUDNESS_BIAS_LU,
        "scorecard_schema": RATING_SCHEMA,
    }
    private = {
        "schema": "audio-too.automix-listening-package-key/v1",
        "assignment": mapping,
        "source_hashes": {
            "baseline_sha256": _sha256(baseline_path),
            "candidate_sha256": _sha256(candidate_path),
            "lineage_sha256": _sha256(lineage_path),
        },
        "render_lineage": lineage,
        "comparison_metrics": {
            "baseline_lufs": round(lufs_a, 3),
            "candidate_lufs_matched": round(lufs_b, 3),
            "loudness_bias_lu": round(loudness_bias, 3),
            "candidate_gain_db": prepared["level_match"]["applied_gain_db"],
            "candidate_clip_safety_gain_db": prepared["level_match"]["clip_safety_gain_db"],
            "common_true_peak_safety_gain_db": round(common_safety_gain_db, 3),
            "baseline_true_peak_dbtp": round(true_peak_a, 3),
            "candidate_true_peak_dbtp": round(true_peak_b, 3),
            "true_peak_ceiling_dbtp": TRUE_PEAK_CEILING_DBTP,
            "peak": round(peak, 8),
            "rms_difference": round(rms_difference, 10),
        },
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        for label in ("A", "B"):
            (temporary / f"{label}.wav").write_bytes(system_wavs[mapping[label]])
        (temporary / "listener_manifest.json").write_text(
            json.dumps(public, indent=2, sort_keys=True), encoding="utf-8"
        )
        key_path = temporary / "private_lineage.json"
        key_path.write_text(json.dumps(private, indent=2, sort_keys=True), encoding="utf-8")
        key_path.chmod(0o600)
        private["output_hashes"] = {
            "A_sha256": _sha256(temporary / "A.wav"),
            "B_sha256": _sha256(temporary / "B.wav"),
        }
        key_path.write_text(json.dumps(private, indent=2, sort_keys=True), encoding="utf-8")
        key_path.chmod(0o600)
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "output_dir": str(output_dir),
        "assignment_id": public["assignment_id"],
        "loudness_bias_lu": round(loudness_bias, 3),
        "rms_difference": round(rms_difference, 10),
    }


def _pipeline_code_revision() -> str:
    files = (
        Path(__file__),
        ANALYSIS_ROOT / "audio_analysis" / "integration" / "kenn_advisor.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "mix_decision_engine.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "mix_renderer.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "mix_validator.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "automation_preview.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "relationship_audition.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "relationships.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "mono_compatibility.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "stem_classifier.py",
        ANALYSIS_ROOT / "audio_analysis" / "mixdown" / "stem_prep.py",
    )
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(SOURCE_ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _seeded_render(prepared: list[dict], plan: Any, seed: int) -> dict[str, Any]:
    import numpy as np

    from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
    from audio_analysis.mixdown.mix_validator import validate_and_correct_mix

    python_state = random.getstate()
    numpy_state = np.random.get_state()
    try:
        random.seed(seed)
        np.random.seed(seed & 0xFFFFFFFF)
        return validate_and_correct_mix(
            prepared,
            copy.deepcopy(plan),
            render_fn=mix_and_render_stems,
            max_iterations=3,
        )
    finally:
        random.setstate(python_state)
        np.random.set_state(numpy_state)


def build_relationship_candidate_packages(
    *,
    project_id: str,
    prepared_stems: list[dict],
    mix_plan: Any,
    relationships: list[dict],
    render_seed: int,
    secret: str,
    output_root: Path,
    rights_authorized: bool,
    render_fn: Callable[[list[dict], Any, int], dict[str, Any]] = _seeded_render,
) -> dict[str, Any]:
    """Render and blind offline-only isolated A/B packages for relationship candidates."""
    from audio_analysis.mixdown.relationship_audition import apply_candidate_to_prepared_stems

    if not project_id or not secret:
        raise ManifestError("relationship auditions require a project ID and study secret")
    if rights_authorized is not True:
        raise ManifestError("relationship auditions require explicit internal-evaluation rights")
    if output_root.exists():
        raise ManifestError(f"output directory already exists: {output_root}")
    if not isinstance(render_seed, int) or isinstance(render_seed, bool):
        raise ManifestError("render_seed must be an integer")
    candidates = [
        (relationship, candidate)
        for relationship in relationships
        if isinstance(relationship, dict)
        for candidate in relationship.get("candidate_strategies", [])
        if isinstance(candidate, dict)
    ]
    if not candidates:
        raise ManifestError("no actionable relationship candidates are available for audition")

    baseline_render = render_fn(prepared_stems, mix_plan, render_seed)
    if not isinstance(baseline_render.get("mixdown_wav_bytes"), bytes):
        raise ManifestError("control render did not produce WAV bytes")
    baseline_gate = baseline_render.get("quality_gate")
    if isinstance(baseline_gate, dict) and baseline_gate.get("passed") is False:
        raise ManifestError("control render failed the quality gate")
    parent = output_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=parent))
    reviewer_rows = []
    try:
        control_path = temporary / ".control.wav"
        control_path.write_bytes(baseline_render["mixdown_wav_bytes"])
        for relationship, candidate in candidates:
            candidate_id = str(candidate.get("candidate_id", ""))
            modified, audit = apply_candidate_to_prepared_stems(
                prepared_stems, relationship, candidate_id
            )
            candidate_render = render_fn(modified, mix_plan, render_seed)
            if not isinstance(candidate_render.get("mixdown_wav_bytes"), bytes):
                raise ManifestError(f"candidate render {candidate_id} did not produce WAV bytes")
            gate = candidate_render.get("quality_gate")
            if isinstance(gate, dict) and gate.get("passed") is False:
                raise ManifestError(f"candidate render {candidate_id} failed the quality gate")
            opaque_id = hashlib.sha256(
                f"{secret}\0{project_id}\0{relationship.get('relationship_id')}\0{candidate_id}".encode()
            ).hexdigest()[:20]
            working = temporary / f".source-{opaque_id}"
            working.mkdir()
            candidate_path = working / "candidate.wav"
            lineage_path = working / "lineage.json"
            candidate_path.write_bytes(candidate_render["mixdown_wav_bytes"])
            lineage = {
                "schema": "audio-too.automix-render-lineage/v1",
                "code_revision": _pipeline_code_revision(),
                "render_seed": render_seed,
                "baseline_system": "automix-relationship-control-v1",
                "candidate_system": "automix-relationship-candidate-offline-v1",
                "configuration": {
                    "audition": audit,
                    "candidate": candidate,
                    "relationship": {
                        "relationship_id": relationship.get("relationship_id"),
                        "relationship_type": relationship.get("relationship_type"),
                        "source_stems": relationship.get("source_stems"),
                        "protected_stem": relationship.get("protected_stem"),
                        "intervention_target": relationship.get("intervention_target"),
                    },
                    "production_processing_enabled": False,
                },
            }
            lineage_path.write_text(
                json.dumps(lineage, indent=2, sort_keys=True), encoding="utf-8"
            )
            package = build_blind_package(
                project_id=project_id,
                comparison_id=f"relationship-audition:{opaque_id}",
                baseline_path=control_path,
                candidate_path=candidate_path,
                lineage_path=lineage_path,
                secret=secret,
                output_dir=temporary / f"pair-{opaque_id}",
            )
            reviewer_rows.append({
                "opaque_id": opaque_id,
                "relationship_id": relationship.get("relationship_id"),
                "relationship_type": relationship.get("relationship_type"),
                "candidate_id": candidate_id,
                "strategy": candidate.get("strategy"),
                "predicted_score": candidate.get("score"),
                "package": Path(package["output_dir"]).name,
                "assignment_id": package["assignment_id"],
                "loudness_bias_lu": package["loudness_bias_lu"],
                "rms_difference": package["rms_difference"],
            })
            shutil.rmtree(working)
        control_path.unlink()
        reviewer_index = temporary / "reviewer_index.json"
        reviewer_index.write_text(json.dumps({
            "schema": "audio-too.relationship-candidate-study-index.v1",
            "project_id": project_id,
            "production_processing_enabled": False,
            "comparisons": reviewer_rows,
        }, indent=2, sort_keys=True), encoding="utf-8")
        reviewer_index.chmod(0o600)
        os.replace(temporary, output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "schema": "audio-too.relationship-candidate-render-report.v1",
        "project_id": project_id,
        "package_count": len(reviewer_rows),
        "output_root": str(output_root),
        "production_processing_enabled": False,
    }


def build_automation_preview_package(
    *,
    project_id: str,
    prepared_stems: list[dict],
    mix_plan: Any,
    relationships: list[dict],
    render_seed: int,
    secret: str,
    output_dir: Path,
    rights_authorized: bool,
    render_fn: Callable[[list[dict], Any, int], dict[str, Any]] = _seeded_render,
) -> dict[str, Any]:
    """Build one blind static-plan versus coordinated-automation preview package."""
    from audio_analysis.mixdown.automation_preview import (
        apply_automation_preview,
        build_automation_preview,
    )

    if not project_id or not secret:
        raise ManifestError("automation preview requires a project ID and study secret")
    if rights_authorized is not True:
        raise ManifestError("automation preview requires explicit internal-evaluation rights")
    if output_dir.exists():
        raise ManifestError(f"output directory already exists: {output_dir}")
    if not isinstance(render_seed, int) or isinstance(render_seed, bool):
        raise ManifestError("render_seed must be an integer")
    preview = build_automation_preview(relationships)
    if not preview.moves:
        return {
            "schema": "audio-too.automation-preview-render-report.v1",
            "project_id": project_id,
            "status": "no_safe_moves",
            "move_count": 0,
            "production_processing_enabled": False,
        }
    modified, audit = apply_automation_preview(prepared_stems, preview)
    baseline_render = render_fn(prepared_stems, mix_plan, render_seed)
    candidate_render = render_fn(modified, mix_plan, render_seed)
    for label, render in (("control", baseline_render), ("automation preview", candidate_render)):
        if not isinstance(render.get("mixdown_wav_bytes"), bytes):
            raise ManifestError(f"{label} render did not produce WAV bytes")
        gate = render.get("quality_gate")
        if isinstance(gate, dict) and gate.get("passed") is False:
            raise ManifestError(f"{label} render failed the quality gate")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    working = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-source-", dir=output_dir.parent))
    try:
        baseline_path = working / "control.wav"
        candidate_path = working / "automation-preview.wav"
        lineage_path = working / "lineage.json"
        baseline_path.write_bytes(baseline_render["mixdown_wav_bytes"])
        candidate_path.write_bytes(candidate_render["mixdown_wav_bytes"])
        preview_payload = preview.to_dict()
        lineage_path.write_text(json.dumps({
            "schema": "audio-too.automix-render-lineage/v1",
            "code_revision": _pipeline_code_revision(),
            "render_seed": render_seed,
            "baseline_system": "automix-static-plan-control-v1",
            "candidate_system": "automix-coordinated-automation-preview-v1",
            "configuration": {
                "automation_preview": preview_payload,
                "audition": audit,
                "production_processing_enabled": False,
            },
        }, indent=2, sort_keys=True), encoding="utf-8")
        opaque_id = hashlib.sha256(
            f"{secret}\0{project_id}\0automation-preview-v1".encode()
        ).hexdigest()[:20]
        package = build_blind_package(
            project_id=project_id,
            comparison_id=f"automation-preview:{opaque_id}",
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            lineage_path=lineage_path,
            secret=secret,
            output_dir=output_dir,
        )
    finally:
        shutil.rmtree(working, ignore_errors=True)
    return {
        "schema": "audio-too.automation-preview-render-report.v1",
        "project_id": project_id,
        "status": "packaged",
        "move_count": len(preview.moves),
        "suppressed_move_count": len(preview.suppressed_moves),
        "package": package,
        "production_processing_enabled": False,
    }


def render_project_pair(
    project: dict[str, Any],
    *,
    output_dir: Path,
    secret: str,
    proposal_provider: Callable[..., Any] | None = None,
    relationship_output_dir: Path | None = None,
    automation_preview_output_dir: Path | None = None,
) -> dict[str, Any]:
    """Render a production rule baseline and real validated advisor candidate."""
    from audio_analysis.analysis_core.dsp_metrics import spectral_bands
    from audio_analysis.integration.kenn_advisor import (
        apply_advisor_proposal,
        evaluate_supplied_proposal_shadow,
        get_kenn_adjustments,
    )
    from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
    from audio_analysis.mixdown.stem_analysis import analyze_stems_masking
    from audio_analysis.mixdown.stem_classifier import classify_stems
    from audio_analysis.mixdown.stem_prep import prepare_stems
    from audio_analysis.mixdown.musical_roles import infer_musical_roles
    from audio_analysis.mixdown.arrangement import (
        apply_arrangement_corrections,
        infer_arrangement,
    )
    from audio_analysis.mixdown.relationships import infer_relationships
    from audio_analysis.mixdown.mono_compatibility import analyze_mono_compatibility
    from audio_analysis.mixdown.automation_preview import build_automation_preview
    from audio_analysis.analysis_core.sidechain_detection import analyze_stems_for_dynamics
    from audio_analysis.utils.audio_io import read_wav_mono

    project_id = str(project.get("id", ""))
    if not project_id or project.get("status") != "eligible":
        raise ManifestError("rendering requires one eligible project record")
    rights = project.get("rights")
    if not isinstance(rights, dict) or rights.get("internal_evaluation_allowed") is not True:
        raise ManifestError("rendering requires explicit internal-evaluation rights")
    rights_path = _repo_path(rights.get("evidence_path"), field="rights.evidence_path", required=True)
    rough_path = _repo_path(project.get("rough_mix_path"), field="rough_mix_path", required=True)
    if rights_path is None or not rights_path.is_file() or rough_path is None or not rough_path.is_file():
        raise ManifestError("rendering requires existing rights evidence and rough mix")
    stems_dir = _repo_path(project.get("stems_path"), field="stems_path", required=True)
    if stems_dir is None:
        raise ManifestError("stems_path is required")
    stem_paths = sorted(stems_dir.glob("*.wav"))
    if not stem_paths:
        raise ManifestError("eligible project contains no WAV stems")
    stems = [{"name": path.name, "file_bytes": path.read_bytes()} for path in stem_paths]
    genre = str(project.get("genre", "pop"))
    target_lufs = float(project.get("target_lufs", -14.0))
    render_seed = project.get("render_seed")
    if not isinstance(render_seed, int) or isinstance(render_seed, bool):
        raise ManifestError("render_seed must be an integer")

    profiles = classify_stems(stems, read_wav_mono_fn=read_wav_mono, max_samples=131072)
    prepared = prepare_stems(
        stems,
        read_wav_mono_fn=read_wav_mono,
        target_sample_rate=44100,
        trim=True,
        normalise=False,
        max_samples=0,
    )
    masking = analyze_stems_masking(
        stems,
        read_wav_mono=read_wav_mono,
        spectral_bands=spectral_bands,
    )
    baseline_plan = generate_mix_plan(
        profiles,
        masking,
        genre=genre,
        target_lufs=target_lufs,
    )
    roles = infer_musical_roles(profiles, prepared)
    baseline_plan.musical_roles = [role.to_dict() for role in roles]
    baseline_plan.arrangement = apply_arrangement_corrections(
        infer_arrangement(prepared),
        project.get("arrangement_corrections"),
        [str(stem.get("name")) for stem in prepared],
    ).to_dict()
    baseline_plan.mono_compatibility = analyze_mono_compatibility(
        prepared, baseline_plan.arrangement
    ).to_dict()
    existing_dynamics = analyze_stems_for_dynamics(
        prepared, profiles, prepared[0]["sample_rate"] if prepared else 44_100
    )
    baseline_plan.relationships = [
        relationship.to_dict() for relationship in infer_relationships(
            profiles, masking, roles, baseline_plan.arrangement, prepared,
            existing_dynamics,
        )
    ]
    baseline_plan.automation_preview = build_automation_preview(
        baseline_plan.relationships
    ).to_dict()
    relationship_study = None
    if relationship_output_dir is not None:
        if any(item.get("candidate_strategies") for item in baseline_plan.relationships):
            relationship_study = build_relationship_candidate_packages(
                project_id=project_id,
                prepared_stems=prepared,
                mix_plan=baseline_plan,
                relationships=baseline_plan.relationships,
                render_seed=render_seed,
                secret=secret,
                output_root=relationship_output_dir,
                rights_authorized=True,
            )
        else:
            relationship_study = {
                "schema": "audio-too.relationship-candidate-render-report.v1",
                "project_id": project_id,
                "package_count": 0,
                "status": "no_actionable_candidates",
                "production_processing_enabled": False,
            }
    automation_study = None
    if automation_preview_output_dir is not None:
        automation_study = build_automation_preview_package(
            project_id=project_id,
            prepared_stems=prepared,
            mix_plan=baseline_plan,
            relationships=baseline_plan.relationships,
            render_seed=render_seed,
            secret=secret,
            output_dir=automation_preview_output_dir,
            rights_authorized=True,
        )
    correlation_id = f"automix-listening-benchmark:{project_id}"
    provider = proposal_provider or get_kenn_adjustments
    proposal = provider(
        baseline_plan,
        profiles,
        genre,
        target_lufs,
        correlation_id=correlation_id,
    )
    receipt = evaluate_supplied_proposal_shadow(
        baseline_plan,
        proposal,
        correlation_id=correlation_id,
    )
    base_report = {
        "project_id": project_id,
        "status": receipt["status"],
        "operation_count": receipt["operation_count"],
        "rejection_reason": receipt["rejection_reason"],
        "source_plan_revision": receipt["source_plan_revision"],
    }
    if relationship_study is not None:
        base_report["relationship_candidate_study"] = relationship_study
    if automation_study is not None:
        base_report["automation_preview_study"] = automation_study
    if receipt["status"] != "valid" or not isinstance(receipt.get("proposal"), dict):
        return base_report

    candidate_plan = apply_advisor_proposal(baseline_plan, receipt["proposal"])
    baseline_render = _seeded_render(prepared, baseline_plan, render_seed)
    candidate_render = _seeded_render(prepared, candidate_plan, render_seed)
    for label, render in (("baseline", baseline_render), ("candidate", candidate_render)):
        if not isinstance(render.get("mixdown_wav_bytes"), bytes):
            raise ManifestError(f"{label} render did not produce WAV bytes")
        gate = render.get("quality_gate")
        if isinstance(gate, dict) and gate.get("passed") is False:
            raise ManifestError(
                f"{label} render failed the production quality gate "
                f"(score={gate.get('technical_score')}, minimum={gate.get('minimum_score')}, "
                f"failures={gate.get('failures', [])})"
            )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    working = Path(tempfile.mkdtemp(prefix=f".{project_id}-render-", dir=output_dir.parent))
    try:
        baseline_path = working / "baseline.wav"
        candidate_path = working / "candidate.wav"
        lineage_path = working / "render-lineage.json"
        baseline_path.write_bytes(baseline_render["mixdown_wav_bytes"])
        candidate_path.write_bytes(candidate_render["mixdown_wav_bytes"])
        lineage = {
            "schema": "audio-too.automix-render-lineage/v1",
            "code_revision": _pipeline_code_revision(),
            "render_seed": render_seed,
            "baseline_system": "automix-rule-only",
            "candidate_system": str(receipt["proposal"].get("model_version", "kenn-advisor")),
            "configuration": {
                "genre": genre,
                "target_lufs": target_lufs,
                "stem_sha256": {path.name: _sha256(path) for path in stem_paths},
                "proposal": receipt["proposal"],
            },
        }
        lineage_path.write_text(json.dumps(lineage, indent=2, sort_keys=True), encoding="utf-8")
        comparison_id = f"{lineage['candidate_system']}:{receipt['proposal'].get('prompt_version', '')}"
        packaged = build_blind_package(
            project_id=project_id,
            comparison_id=comparison_id,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            lineage_path=lineage_path,
            secret=secret,
            output_dir=output_dir,
        )
    finally:
        shutil.rmtree(working, ignore_errors=True)
    return base_report | {"status": "packaged", "package": packaged}


def render_manifest(
    manifest_path: Path,
    *,
    output_root: Path,
    secret: str,
    proposal_provider: Callable[..., Any] | None = None,
    relationship_output_root: Path | None = None,
    automation_preview_output_root: Path | None = None,
) -> dict[str, Any]:
    """Render every valid eligible project, continuing after per-project abstention/failure."""
    if not secret:
        raise ManifestError("a non-empty study secret is required")
    validation = validate_manifest(manifest_path)
    if validation["errors"]:
        raise ManifestError("manifest has invalid eligible projects; fix validation errors first")
    manifest = _load_json(manifest_path)
    projects = [item for item in manifest["projects"] if item.get("status") == "eligible"]
    results = []
    for project in projects:
        try:
            result = render_project_pair(
                project,
                output_dir=output_root / project["id"],
                secret=secret,
                proposal_provider=proposal_provider,
                relationship_output_dir=(
                    relationship_output_root / project["id"]
                    if relationship_output_root is not None else None
                ),
                automation_preview_output_dir=(
                    automation_preview_output_root / project["id"]
                    if automation_preview_output_root is not None else None
                ),
            )
        except Exception as exc:
            result = {
                "project_id": project.get("id", ""),
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(result)
    counts = Counter(item["status"] for item in results)
    return {
        "schema": "audio-too.automix-listening-render-report/v1",
        "manifest": str(manifest_path),
        "eligible_projects": len(projects),
        "status_counts": dict(counts),
        "results": results,
    }


def _load_rating_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ratings: set[tuple[str, str]] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"ratings line {line_number}: {exc}") from exc
        if row.get("schema") != RATING_SCHEMA:
            raise ManifestError(f"ratings line {line_number}: invalid schema")
        if row.get("preferred") not in {"A", "B", "tie"}:
            raise ManifestError(f"ratings line {line_number}: preferred must be A, B, or tie")
        if not isinstance(row.get("listener_experience"), str) or not row["listener_experience"]:
            raise ManifestError(f"ratings line {line_number}: listener_experience is required")
        listener_id = row.get("listener_id")
        assignment_id = row.get("assignment_id")
        project_id = row.get("project_id")
        if not all(isinstance(value, str) and value for value in (listener_id, assignment_id, project_id)):
            raise ManifestError(
                f"ratings line {line_number}: listener_id, assignment_id, and project_id are required"
            )
        rating_key = (listener_id, assignment_id)
        if rating_key in seen_ratings:
            raise ManifestError(f"ratings line {line_number}: duplicate listener/assignment rating")
        seen_ratings.add(rating_key)
        confidence = row.get("confidence")
        if not isinstance(confidence, int) or isinstance(confidence, bool) or not 1 <= confidence <= 5:
            raise ManifestError(f"ratings line {line_number}: confidence must be integer 1-5")
        scores = row.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(SCORE_FIELDS):
            raise ManifestError(f"ratings line {line_number}: scores must contain the v1 scorecard")
        if any(not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5 for v in scores.values()):
            raise ManifestError(f"ratings line {line_number}: every score must be integer 1-5")
        flags = row.get("failure_flags", [])
        if not isinstance(flags, list):
            raise ManifestError(f"ratings line {line_number}: failure_flags must be an array")
        for flag_index, flag in enumerate(flags):
            if not isinstance(flag, dict) or set(flag) - {"category", "version", "stem_role", "section"}:
                raise ManifestError(
                    f"ratings line {line_number}: failure_flags[{flag_index}] is malformed"
                )
            if flag.get("category") not in FAILURE_CATEGORIES:
                raise ManifestError(
                    f"ratings line {line_number}: failure_flags[{flag_index}] has unknown category"
                )
            if flag.get("version") not in {"A", "B", "both"}:
                raise ManifestError(
                    f"ratings line {line_number}: failure_flags[{flag_index}] has invalid version"
                )
            for optional in ("stem_role", "section"):
                if optional in flag and (not isinstance(flag[optional], str) or not flag[optional].strip()):
                    raise ManifestError(
                        f"ratings line {line_number}: failure_flags[{flag_index}].{optional} is invalid"
                    )
        rows.append(row)
    return rows


def score_ratings(
    path: Path,
    key_path: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    rows = _load_rating_rows(path)

    project_metadata: dict[str, dict[str, Any]] = {}
    if manifest_path is not None:
        manifest = _load_json(manifest_path)
        if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("projects"), list):
            raise ManifestError("rating manifest does not satisfy the benchmark v1 contract")
        project_metadata = {
            item["id"]: item
            for item in manifest["projects"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        unknown_projects = sorted({row["project_id"] for row in rows} - set(project_metadata))
        if unknown_projects:
            raise ManifestError(f"ratings name projects absent from manifest: {unknown_projects}")

    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_project[str(row.get("project_id", ""))].append(row)
    preferences = Counter(row["preferred"] for row in rows)
    system_preferences: Counter[str] = Counter()
    if key_path is not None:
        key_data = _load_json(key_path)
        keys = key_data.get("assignments")
        if not isinstance(keys, list):
            raise ManifestError("unblinding key must contain an assignments array")
        by_assignment = {
            item.get("assignment_id"): item
            for item in keys
            if isinstance(item, dict) and item.get("schema") == "audio-too.automix-blind-key/v1"
        }
        for row in rows:
            key = by_assignment.get(row.get("assignment_id"))
            if key is None:
                raise ManifestError(f"missing unblinding key for {row.get('assignment_id')}")
            row["version_mapping"] = {"A": key.get("A"), "B": key.get("B")}
            if row["preferred"] == "tie":
                system_preferences["tie"] += 1
                row["preferred_system"] = "tie"
                continue
            system = key.get(row["preferred"])
            if system not in {"baseline", "candidate"}:
                raise ManifestError("unblinding key contains an invalid mapping")
            system_preferences[system] += 1
            row["preferred_system"] = system
    raters_per_project = {key: len(value) for key, value in by_project.items()}
    agreement = _preference_agreement(rows)
    failure_ranking = _failure_ranking(
        rows,
        unblinded=key_path is not None,
        project_metadata=project_metadata,
    )
    project_preferences = _project_preferences(rows) if key_path is not None else None
    promotion_gate = _promotion_gate(
        raters_per_project,
        agreement,
        project_preferences,
    ) if key_path is not None else None
    return {
        "ratings": len(rows),
        "projects_rated": len(by_project),
        "preferences": dict(preferences),
        "system_preferences": dict(system_preferences) if key_path is not None else None,
        "mean_confidence": round(sum(row["confidence"] for row in rows) / len(rows), 3) if rows else None,
        "projects_with_multiple_raters": sum(count >= 2 for count in raters_per_project.values()),
        "minimum_two_raters_every_project": bool(by_project) and all(
            count >= 2 for count in raters_per_project.values()
        ),
        "inter_rater_agreement": agreement,
        "failure_ranking": failure_ranking,
        "project_preferences": project_preferences,
        "promotion_gate": promotion_gate,
        "score_means": {
            field: round(sum(row["scores"][field] for row in rows) / len(rows), 3)
            for field in SCORE_FIELDS
        } if rows else {},
    }


def _load_relationship_study_roots(study_roots: list[Path]) -> dict[str, dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    for root in study_roots:
        index = _load_json(root / "reviewer_index.json")
        if index.get("schema") != "audio-too.relationship-candidate-study-index.v1":
            raise ManifestError(f"invalid relationship study index: {root}")
        if index.get("production_processing_enabled") is not False:
            raise ManifestError("relationship study index must remain offline-only")
        project_id = index.get("project_id")
        comparisons = index.get("comparisons")
        if not isinstance(project_id, str) or not project_id or not isinstance(comparisons, list):
            raise ManifestError("relationship study index is malformed")
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                raise ManifestError("relationship study comparison is malformed")
            package_name = comparison.get("package")
            if (
                not isinstance(package_name, str)
                or Path(package_name).name != package_name
                or not package_name.startswith("pair-")
            ):
                raise ManifestError("relationship study package path is unsafe")
            private = _load_json(root / package_name / "private_lineage.json")
            assignment = private.get("assignment")
            lineage = private.get("render_lineage")
            if (
                private.get("schema") != "audio-too.automix-listening-package-key/v1"
                or not isinstance(assignment, dict)
                or not isinstance(lineage, dict)
            ):
                raise ManifestError("relationship study private lineage is malformed")
            configuration = lineage.get("configuration")
            if not isinstance(configuration, dict) or configuration.get("production_processing_enabled") is not False:
                raise ManifestError("relationship study lineage must remain offline-only")
            candidate = configuration.get("candidate")
            relationship = configuration.get("relationship")
            if (
                assignment.get("schema") != "audio-too.automix-blind-key/v1"
                or lineage.get("candidate_system") != "automix-relationship-candidate-offline-v1"
                or not isinstance(candidate, dict)
                or candidate.get("schema") != "audio-too.relationship-candidate.v1"
                or not isinstance(relationship, dict)
            ):
                raise ManifestError("relationship study candidate lineage is missing")
            assignment_id = assignment.get("assignment_id")
            expected = {
                "project_id": project_id,
                "assignment_id": comparison.get("assignment_id"),
                "relationship_id": comparison.get("relationship_id"),
                "relationship_type": comparison.get("relationship_type"),
                "candidate_id": comparison.get("candidate_id"),
                "strategy": comparison.get("strategy"),
                "predicted_score": comparison.get("predicted_score"),
            }
            actual = {
                "project_id": assignment.get("project_id"),
                "assignment_id": assignment_id,
                "relationship_id": relationship.get("relationship_id"),
                "relationship_type": relationship.get("relationship_type"),
                "candidate_id": candidate.get("candidate_id"),
                "strategy": candidate.get("strategy"),
                "predicted_score": candidate.get("score"),
            }
            if actual != expected:
                raise ManifestError("relationship reviewer index and private lineage disagree")
            if not all(
                isinstance(actual[key], str) and actual[key]
                for key in (
                    "project_id", "assignment_id", "relationship_id", "relationship_type",
                    "candidate_id", "strategy",
                )
            ):
                raise ManifestError("relationship study lineage identifiers must be non-empty strings")
            predicted_score = actual["predicted_score"]
            if (
                isinstance(predicted_score, bool)
                or not isinstance(predicted_score, (int, float))
                or not math.isfinite(float(predicted_score))
                or not 0.0 <= float(predicted_score) <= 1.0
            ):
                raise ManifestError("relationship candidate predicted score must be within 0-1")
            actual["predicted_score"] = float(predicted_score)
            if assignment.get("A") not in {"baseline", "candidate"} or assignment.get("B") not in {
                "baseline", "candidate"
            } or assignment.get("A") == assignment.get("B"):
                raise ManifestError("relationship study assignment mapping is invalid")
            if not isinstance(assignment_id, str) or assignment_id in assignments:
                raise ManifestError("relationship study assignment IDs must be unique")
            assignments[assignment_id] = actual | {
                "mapping": {"A": assignment["A"], "B": assignment["B"]},
            }
    if not assignments:
        raise ManifestError("relationship study roots contain no comparisons")
    return assignments


def score_relationship_candidate_ratings(path: Path, study_roots: list[Path]) -> dict[str, Any]:
    """Score isolated candidate auditions without allowing vote-rich projects to dominate."""
    rows = _load_rating_rows(path)
    if not rows:
        raise ManifestError("relationship candidate ratings file is empty")
    assignments = _load_relationship_study_roots(study_roots)
    for row in rows:
        metadata = assignments.get(row["assignment_id"])
        if metadata is None:
            raise ManifestError(f"rating references unknown relationship assignment: {row['assignment_id']}")
        if row["project_id"] != metadata["project_id"]:
            raise ManifestError("rating project conflicts with relationship study lineage")
        row["relationship_metadata"] = metadata
        row["version_mapping"] = metadata["mapping"]
        row["preferred_system"] = (
            "tie" if row["preferred"] == "tie" else metadata["mapping"][row["preferred"]]
        )

    rows_by_assignment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_assignment[row["assignment_id"]].append(row)
    assignment_outcomes = []
    for assignment_id, assignment_rows in sorted(rows_by_assignment.items()):
        votes = Counter(row["preferred_system"] for row in assignment_rows)
        outcome = (
            "candidate" if votes["candidate"] > votes["baseline"]
            else "baseline" if votes["baseline"] > votes["candidate"]
            else "tie"
        )
        metadata = assignments[assignment_id]
        assignment_outcomes.append({
            "assignment_id": assignment_id,
            "project_id": metadata["project_id"],
            "relationship_id": metadata["relationship_id"],
            "relationship_type": metadata["relationship_type"],
            "candidate_id": metadata["candidate_id"],
            "strategy": metadata["strategy"],
            "predicted_score": metadata["predicted_score"],
            "raters": len(assignment_rows),
            "votes": dict(votes),
            "outcome": outcome,
        })

    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in assignment_outcomes:
        by_strategy[outcome["strategy"]].append(outcome)
    strategy_reports = {}
    available_by_strategy: Counter[str] = Counter(
        metadata["strategy"] for metadata in assignments.values()
    )
    for strategy in sorted(available_by_strategy):
        outcomes = by_strategy.get(strategy, [])
        strategy_rows = [
            row for row in rows if row["relationship_metadata"]["strategy"] == strategy
        ]
        counts = Counter(outcome["outcome"] for outcome in outcomes)
        decisive = counts["candidate"] + counts["baseline"]
        projects = {outcome["project_id"] for outcome in outcomes}
        interval = _wilson_interval(counts["candidate"], decisive)
        agreement = _preference_agreement(strategy_rows)
        artifact_flags = Counter()
        for row in strategy_rows:
            for flag in row.get("failure_flags", []):
                if flag["category"] != "audible_artifact" or flag["version"] == "both":
                    continue
                artifact_flags[row["version_mapping"][flag["version"]]] += 1
        checks = {
            "all_available_assignments_rated": len(outcomes) == available_by_strategy[strategy],
            "at_least_five_projects": len(projects) >= MIN_RELATIONSHIP_PROJECTS_PER_STRATEGY,
            "at_least_ten_decisive_assignments": decisive >= MIN_RELATIONSHIP_DECISIVE_ASSIGNMENTS,
            "at_least_two_raters_each": bool(outcomes) and all(
                outcome["raters"] >= MIN_RATERS_PER_PROJECT for outcome in outcomes
            ),
            "agreement_kappa_at_least_0_20": (
                agreement.get("kappa") is not None and agreement["kappa"] >= MIN_AGREEMENT_KAPPA
            ),
            "candidate_95ci_above_chance": interval is not None and interval[0] > 0.5,
            "candidate_artifacts_not_worse": artifact_flags["candidate"] <= artifact_flags["baseline"],
        }
        strategy_reports[strategy] = {
            "projects": len(projects),
            "assignments": len(outcomes),
            "available_assignments": available_by_strategy[strategy],
            "decisive_assignments": decisive,
            "outcomes": dict(counts),
            "candidate_win_rate": round(counts["candidate"] / decisive, 4) if decisive else None,
            "candidate_win_rate_95ci": interval,
            "inter_rater_agreement": agreement,
            "audible_artifact_flags": dict(artifact_flags),
            "calibration_evidence_gate": {"passed": all(checks.values()), "checks": checks},
        }

    relationship_type_reports = {}
    outcomes_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in assignment_outcomes:
        outcomes_by_type[outcome["relationship_type"]].append(outcome)
    for relationship_type, outcomes in sorted(outcomes_by_type.items()):
        counts = Counter(outcome["outcome"] for outcome in outcomes)
        decisive = counts["candidate"] + counts["baseline"]
        relationship_type_reports[relationship_type] = {
            "projects": len({outcome["project_id"] for outcome in outcomes}),
            "assignments": len(outcomes),
            "outcomes": dict(counts),
            "candidate_win_rate": round(counts["candidate"] / decisive, 4) if decisive else None,
            "candidate_win_rate_95ci": _wilson_interval(counts["candidate"], decisive),
        }

    score_bands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in assignment_outcomes:
        score = outcome["predicted_score"]
        band = "low_0_00_0_69" if score < 0.70 else "medium_0_70_0_84" if score < 0.85 else "high_0_85_1_00"
        score_bands[band].append(outcome)
    score_calibration = {}
    for band, outcomes in sorted(score_bands.items()):
        counts = Counter(outcome["outcome"] for outcome in outcomes)
        decisive = counts["candidate"] + counts["baseline"]
        score_calibration[band] = {
            "assignments": len(outcomes),
            "mean_predicted_score": round(
                sum(outcome["predicted_score"] for outcome in outcomes) / len(outcomes), 4
            ),
            "outcomes": dict(counts),
            "empirical_candidate_win_rate": (
                round(counts["candidate"] / decisive, 4) if decisive else None
            ),
            "empirical_win_rate_95ci": _wilson_interval(counts["candidate"], decisive),
        }

    failure_counts: Counter[tuple[str, str, str]] = Counter()
    failure_projects: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        strategy = row["relationship_metadata"]["strategy"]
        for flag in row.get("failure_flags", []):
            system = (
                "both" if flag["version"] == "both"
                else row["version_mapping"][flag["version"]]
            )
            key = (strategy, flag["category"], system)
            failure_counts[key] += 1
            failure_projects[key].add(row["project_id"])
    failure_ranking = [
        {
            "strategy": key[0], "category": key[1], "system": key[2],
            "count": count, "project_count": len(failure_projects[key]),
        }
        for key, count in sorted(
            failure_counts.items(), key=lambda item: (-len(failure_projects[item[0]]), -item[1], item[0])
        )
    ]
    return {
        "schema": "audio-too.relationship-candidate-score-report.v1",
        "ratings": len(rows),
        "projects_rated": len({row["project_id"] for row in rows}),
        "assignments_rated": len(rows_by_assignment),
        "assignments_available": len(assignments),
        "assignment_coverage": round(len(rows_by_assignment) / len(assignments), 4),
        "assignment_outcomes": assignment_outcomes,
        "strategies": strategy_reports,
        "relationship_types": relationship_type_reports,
        "predicted_score_calibration": score_calibration,
        "failure_ranking": failure_ranking,
        "production_promotion_authorized": False,
    }


def _preference_agreement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Generalized Fleiss-style kappa for variable raters per assignment."""
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    totals = Counter()
    for row in rows:
        groups[row["assignment_id"]][row["preferred"]] += 1
        totals[row["preferred"]] += 1
    agreeing_pairs = 0
    all_pairs = 0
    groups_with_pairs = 0
    for counts in groups.values():
        count = sum(counts.values())
        if count < 2:
            continue
        groups_with_pairs += 1
        all_pairs += count * (count - 1)
        agreeing_pairs += sum(value * (value - 1) for value in counts.values())
    if all_pairs == 0 or not rows:
        return {"kappa": None, "observed_agreement": None, "groups_with_multiple_raters": 0}
    observed = agreeing_pairs / all_pairs
    total = len(rows)
    expected = sum((totals[label] / total) ** 2 for label in ("A", "B", "tie"))
    kappa = (observed - expected) / (1.0 - expected) if expected < 1.0 else None
    return {
        "kappa": round(kappa, 4) if kappa is not None else None,
        "observed_agreement": round(observed, 4),
        "expected_agreement": round(expected, 4),
        "groups_with_multiple_raters": groups_with_pairs,
    }


def _failure_ranking(
    rows: list[dict[str, Any]],
    *,
    unblinded: bool,
    project_metadata: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str, str, str, str]] = Counter()
    projects: dict[tuple[str, str, str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        mapping = row.get("version_mapping", {})
        for flag in row.get("failure_flags", []):
            version = flag["version"]
            system = mapping.get(version, version) if version != "both" else "both"
            genre = str(project_metadata.get(row["project_id"], {}).get("genre", ""))
            key = (flag["category"], system, genre, flag.get("stem_role", ""), flag.get("section", ""))
            counts[key] += 1
            projects[key].add(row["project_id"])
    return [
        {
            "category": key[0],
            "system" if unblinded else "version": key[1],
            "genre": key[2] or None,
            "stem_role": key[3] or None,
            "section": key[4] or None,
            "count": count,
            "project_count": len(projects[key]),
        }
        for key, count in sorted(
            counts.items(), key=lambda item: (-len(projects[item[0]]), -item[1], item[0])
        )
    ]


def _wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> list[float] | None:
    if trials <= 0:
        return None
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (proportion + z * z / (2.0 * trials)) / denominator
    margin = z * math.sqrt(
        proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials)
    ) / denominator
    return [round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)]


def _project_preferences(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_project: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        system = row.get("preferred_system", "tie") if row["preferred"] != "tie" else "tie"
        by_project[row["project_id"]][system] += 1
    outcomes = Counter()
    details = []
    for project_id, counts in sorted(by_project.items()):
        candidate = counts["candidate"]
        baseline = counts["baseline"]
        outcome = "candidate" if candidate > baseline else "baseline" if baseline > candidate else "tie"
        outcomes[outcome] += 1
        details.append({"project_id": project_id, "outcome": outcome, "votes": dict(counts)})
    decisive = outcomes["candidate"] + outcomes["baseline"]
    return {
        "outcomes": dict(outcomes),
        "decisive_projects": decisive,
        "candidate_win_rate": round(outcomes["candidate"] / decisive, 4) if decisive else None,
        "candidate_win_rate_95ci": _wilson_interval(outcomes["candidate"], decisive),
        "details": details,
    }


def _promotion_gate(
    raters_per_project: dict[str, int],
    agreement: dict[str, Any],
    project_preferences: dict[str, Any] | None,
) -> dict[str, Any]:
    preferences = project_preferences or {}
    interval = preferences.get("candidate_win_rate_95ci")
    checks = {
        "at_least_20_projects": len(raters_per_project) >= MIN_DECISIVE_PROJECTS,
        "at_least_two_raters_each": bool(raters_per_project) and all(
            count >= MIN_RATERS_PER_PROJECT for count in raters_per_project.values()
        ),
        "at_least_20_decisive_projects": preferences.get("decisive_projects", 0) >= MIN_DECISIVE_PROJECTS,
        "agreement_kappa_at_least_0_20": (
            agreement.get("kappa") is not None and agreement["kappa"] >= MIN_AGREEMENT_KAPPA
        ),
        "candidate_95ci_above_chance": interval is not None and interval[0] > 0.5,
    }
    return {"passed": all(checks.values()), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    assign = sub.add_parser("assign")
    assign.add_argument("project_id")
    assign.add_argument("comparison_id")
    assign.add_argument("--secret-file", type=Path, required=True)
    assign.add_argument("--public-output", type=Path, required=True)
    assign.add_argument("--key-output", type=Path, required=True)
    package = sub.add_parser("package")
    package.add_argument("project_id")
    package.add_argument("comparison_id")
    package.add_argument("--baseline", type=Path, required=True)
    package.add_argument("--candidate", type=Path, required=True)
    package.add_argument("--lineage", type=Path, required=True)
    package.add_argument("--secret-file", type=Path, required=True)
    package.add_argument("--output-dir", type=Path, required=True)
    render = sub.add_parser("render")
    render.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    render.add_argument("--secret-file", type=Path, required=True)
    render.add_argument("--output-root", type=Path, required=True)
    render.add_argument("--report", type=Path)
    render.add_argument(
        "--relationship-candidates-output-root",
        type=Path,
        help="Offline-only blind A/B packages for bounded relationship candidates.",
    )
    render.add_argument(
        "--automation-preview-output-root",
        type=Path,
        help="Offline-only blind static versus coordinated section-automation previews.",
    )
    score = sub.add_parser("score")
    score.add_argument("ratings", type=Path)
    score.add_argument("--key-file", type=Path)
    score.add_argument("--manifest", type=Path, required=True)
    score_relationships = sub.add_parser("score-relationships")
    score_relationships.add_argument("ratings", type=Path)
    score_relationships.add_argument("--study-root", type=Path, action="append", required=True)
    score_relationships.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            result = validate_manifest(args.manifest)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["ready"] else 2
        if args.command == "assign":
            secret = args.secret_file.read_text(encoding="utf-8").strip()
            bundle = assignment_bundle(args.project_id, args.comparison_id, secret)
            args.public_output.parent.mkdir(parents=True, exist_ok=True)
            args.key_output.parent.mkdir(parents=True, exist_ok=True)
            args.public_output.write_text(json.dumps(bundle["public"], indent=2), encoding="utf-8")
            args.key_output.write_text(
                json.dumps({"assignments": [bundle["private"]]}, indent=2), encoding="utf-8"
            )
            args.key_output.chmod(0o600)
            print(json.dumps({"public_output": str(args.public_output), "key_output": str(args.key_output)}))
            return 0
        if args.command == "package":
            secret = args.secret_file.read_text(encoding="utf-8").strip()
            result = build_blind_package(
                project_id=args.project_id,
                comparison_id=args.comparison_id,
                baseline_path=args.baseline,
                candidate_path=args.candidate,
                lineage_path=args.lineage,
                secret=secret,
                output_dir=args.output_dir,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "render":
            secret = args.secret_file.read_text(encoding="utf-8").strip()
            result = render_manifest(
                args.manifest,
                output_root=args.output_root,
                secret=secret,
                relationship_output_root=args.relationship_candidates_output_root,
                automation_preview_output_root=args.automation_preview_output_root,
            )
            rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.report.with_suffix(args.report.suffix + ".tmp")
                temporary.write_text(rendered, encoding="utf-8")
                os.replace(temporary, args.report)
            print(rendered, end="")
            return int(result["status_counts"].get("failed", 0) > 0)
        if args.command == "score-relationships":
            result = score_relationship_candidate_ratings(args.ratings, args.study_root)
            rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.output.with_suffix(args.output.suffix + ".tmp")
                temporary.write_text(rendered, encoding="utf-8")
                os.replace(temporary, args.output)
            print(rendered, end="")
            return 0
        result = score_ratings(args.ratings, args.key_file, args.manifest)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ManifestError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
