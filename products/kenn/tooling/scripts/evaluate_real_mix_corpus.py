#!/usr/bin/env python3
"""Prepare and score privacy-safe, human-reviewed real-mix evaluation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = REPO_ROOT / "packages" / "mix-review" / "core" / "local_engine.py"
sys.path.insert(0, str(REPO_ROOT / "packages" / "mix-review" / "core"))
from local_engine import analyze_wav  # noqa: E402

MANIFEST_SCHEMA = "kenn.real_mix_corpus.v1"
PACKET_SCHEMA = "kenn.real_mix_review_packet.v1"
REVIEW_SCHEMA = "kenn.real_mix_reviewer_scores.v1"
RESULT_SCHEMA = "kenn.real_mix_evaluation.v1"
RIGHTS_BASES = {"owned", "commissioned", "explicit_permission", "cc_licensed", "public_domain"}
MIN_QUALIFYING_CASES = 12
REQUIRED_MIX_CATEGORIES = {"vocals", "drums", "bass", "dense_electronic", "sparse_acoustic"}
GROUND_TRUTH_CONFIDENCE = {"low", "medium", "high"}


class IntakeError(ValueError):
    pass


def source_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        # Isolated source archives intentionally omit .git.  Keep their
        # packets visibly unbound so unit/evaluation mechanics remain
        # runnable; the release gate still requires a real Git revision.
        return "unavailable"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntakeError(f"Could not read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise IntakeError("JSON root must be an object")
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(manifest_path: Path, audio_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load(manifest_path)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise IntakeError(f"manifest schema must be {MANIFEST_SCHEMA}")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise IntakeError("manifest cases must be a non-empty list")
    root = audio_root.expanduser().resolve()
    seen: set[str] = set()
    packet_cases = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise IntakeError(f"case {index} must be an object")
        case_id = str(case.get("case_id") or "").strip()
        if not case_id or case_id in seen:
            raise IntakeError(f"case {index} has a missing or duplicate case_id")
        seen.add(case_id)
        if case.get("consent_confirmed") is not True or case.get("rights_basis") not in RIGHTS_BASES:
            raise IntakeError(f"case {case_id} lacks confirmed consent and an accepted rights basis")
        relative = Path(str(case.get("audio_file") or ""))
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".wav":
            raise IntakeError(f"case {case_id} audio_file must be a relative WAV path")
        audio_path = (root / relative).resolve()
        if root not in audio_path.parents or not audio_path.is_file():
            raise IntakeError(f"case {case_id} audio file is missing or outside audio_root")
        audio = audio_path.read_bytes()
        digest = _sha256(audio)
        expected_digest = str(case.get("sha256") or "").lower()
        if expected_digest != digest:
            raise IntakeError(f"case {case_id} SHA-256 mismatch")
        ground_truth = case.get("ground_truth")
        observations = ground_truth.get("observations") if isinstance(ground_truth, dict) else None
        if not isinstance(observations, list) or not observations:
            raise IntakeError(f"case {case_id} requires at least one human ground_truth observation")
        for observation_index, observation in enumerate(observations):
            if not isinstance(observation, dict) or not str(observation.get("fault_family") or "").strip():
                raise IntakeError(f"case {case_id} observation {observation_index} requires a fault_family")
            if observation.get("confidence") not in GROUND_TRUTH_CONFIDENCE:
                raise IntakeError(f"case {case_id} observation {observation_index} requires low, medium, or high confidence")
            if not isinstance(observation.get("acceptable_alternatives"), list):
                raise IntakeError(f"case {case_id} observation {observation_index} requires acceptable_alternatives")
        if not isinstance(case.get("subjective_exclusions"), list):
            raise IntakeError(f"case {case_id} requires a subjective_exclusions list")
        mix_category = str(case.get("mix_category") or "").strip().lower()
        if not mix_category:
            raise IntakeError(f"case {case_id} requires a mix_category")
        result = analyze_wav(audio, filename=f"{case_id}.wav")
        packet_cases.append({
            "case_id": case_id,
            "audio_sha256": digest,
            "mix_category": mix_category[:64],
            "ground_truth": ground_truth,
            "subjective_exclusions": list(case.get("subjective_exclusions") or []),
            "engine": {
                "ok": result.get("ok"),
                "analysis_status": result.get("analysis_status"),
                "findings": result.get("findings", []),
                "limitations": result.get("limitations", []),
            },
        })
    manifest_sha = _sha256(manifest_path.read_bytes())
    observed_categories = sorted({row["mix_category"] for row in packet_cases})
    missing_categories = sorted(REQUIRED_MIX_CATEGORIES - set(observed_categories))
    packet = {
        "schema": PACKET_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": source_revision(),
        "manifest_sha256": manifest_sha,
        "engine_sha256": _sha256(ENGINE_PATH.read_bytes()),
        "case_count": len(packet_cases),
        "category_coverage": {"observed": observed_categories, "required": sorted(REQUIRED_MIX_CATEGORIES), "missing": missing_categories},
        "privacy": {"audio_embedded": False, "audio_paths_embedded": False, "source_audio_used_for_training": False},
        "cases": packet_cases,
        "qualification_ready": len(packet_cases) >= MIN_QUALIFYING_CASES and not missing_categories,
    }
    review = {
        "schema": REVIEW_SCHEMA,
        "packet_sha256": _sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()),
        "reviewer_id": "",
        "independent_review_confirmed": False,
        "scores": [{
            "case_id": row["case_id"], "evidence_correct": None, "usefulness_1_to_5": None,
            "severity_order_correct": None, "abstention_correct": None,
            "false_positive_families": [], "missed_issue_families": [], "notes": "",
        } for row in packet_cases],
    }
    return packet, review


def score(packet_path: Path, review_paths: list[Path]) -> dict[str, Any]:
    packet = _load(packet_path)
    if packet.get("schema") != PACKET_SCHEMA:
        raise IntakeError("invalid packet schema")
    revision = source_revision()
    if packet.get("source_git_commit") != revision:
        raise IntakeError("packet was not prepared from the current source Git revision")
    canonical_sha = _sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode())
    packet_cases = packet.get("cases")
    if not isinstance(packet_cases, list) or not packet_cases or not all(isinstance(row, dict) for row in packet_cases):
        raise IntakeError("packet cases must be a non-empty list of objects")
    case_ids = [str(row.get("case_id") or "").strip() for row in packet_cases]
    if any(not case_id for case_id in case_ids) or len(set(case_ids)) != len(case_ids):
        raise IntakeError("packet case IDs must be non-empty and unique")
    observed_categories = {str(row.get("mix_category") or "") for row in packet_cases if isinstance(row, dict)}
    evidence: list[bool] = []; usefulness: list[int] = []; severity_order: list[bool] = []; abstention: list[bool] = []; false_positives = 0; missed = 0
    reviewers = []
    reviewer_slots: set[str] = set()
    review_sha256: list[str] = []
    for path in review_paths:
        review = _load(path)
        if review.get("schema") != REVIEW_SCHEMA or review.get("packet_sha256") != canonical_sha:
            raise IntakeError(f"review {path.name} is not bound to this packet")
        if review.get("independent_review_confirmed") is not True or not str(review.get("reviewer_id") or "").strip():
            raise IntakeError(f"review {path.name} lacks reviewer identity/independence confirmation")
        reviewer_slot = str(review.get("reviewer_slot") or "").strip().casefold()
        if not reviewer_slot or reviewer_slot in reviewer_slots:
            raise IntakeError(f"review {path.name} lacks a unique reviewer slot")
        reviewer_slots.add(reviewer_slot)
        rows = review.get("scores")
        if not isinstance(rows, list) or [row.get("case_id") for row in rows if isinstance(row, dict)] != case_ids:
            raise IntakeError(f"review {path.name} has incomplete or reordered cases")
        for row in rows:
            if row.get("evidence_correct") not in {True, False}:
                raise IntakeError(f"review {path.name} has an incomplete evidence score")
            value = row.get("usefulness_1_to_5")
            if not isinstance(value, int) or not 1 <= value <= 5:
                raise IntakeError(f"review {path.name} has an invalid usefulness score")
            if row.get("severity_order_correct") not in {True, False}:
                raise IntakeError(f"review {path.name} has an incomplete severity-order score")
            if row.get("abstention_correct") not in {True, False}:
                raise IntakeError(f"review {path.name} has an incomplete abstention score")
            for family_field in ("false_positive_families", "missed_issue_families"):
                families = row.get(family_field)
                if (
                    not isinstance(families, list)
                    or any(not isinstance(item, str) or not item.strip() for item in families)
                    or len({item.strip().casefold() for item in families}) != len(families)
                ):
                    raise IntakeError(f"review {path.name} has an invalid {family_field}")
            evidence.append(row["evidence_correct"]); usefulness.append(value)
            severity_order.append(row["severity_order_correct"]); abstention.append(row["abstention_correct"])
            false_positives += len(row.get("false_positive_families") or [])
            missed += len(row.get("missed_issue_families") or [])
        reviewer_identity = str(review["reviewer_id"]).strip().casefold()
        if reviewer_identity in reviewers:
            raise IntakeError(f"review {path.name} duplicates another reviewer identity")
        reviewers.append(reviewer_identity)
        review_sha256.append(_sha256(path.read_bytes()))
    total = len(evidence)
    metrics = {
        "reviewer_count": len(reviewers), "case_reviews": total,
        "evidence_correct_rate": sum(evidence) / total if total else 0.0,
        "useful_rate": sum(value >= 4 for value in usefulness) / total if total else 0.0,
        "mean_usefulness": sum(usefulness) / total if total else 0.0,
        "severity_order_correct_rate": sum(severity_order) / total if total else 0.0,
        "abstention_correct_rate": sum(abstention) / total if total else 0.0,
        "false_positive_count": false_positives, "missed_issue_count": missed,
    }
    thresholds = {"minimum_cases": len(case_ids) >= MIN_QUALIFYING_CASES,
                  "required_category_coverage": REQUIRED_MIX_CATEGORIES <= observed_categories,
                  "engine_completion": len(packet_cases) == len(case_ids) and all(
                      isinstance(row, dict) and isinstance(row.get("engine"), dict)
                      and row["engine"].get("ok") is True and row["engine"].get("analysis_status") == "complete"
                      for row in packet_cases
                  ),
                  "two_independent_reviewers": len(set(reviewers)) >= 2,
                  "evidence_correctness": metrics["evidence_correct_rate"] >= 0.90,
                  "usefulness": metrics["useful_rate"] >= 0.85,
                  "severity_order": metrics["severity_order_correct_rate"] >= 0.85,
                  "abstention": metrics["abstention_correct_rate"] >= 0.85,
                  "false_positive_rate": false_positives / total <= 0.10 if total else False}
    engine_sha = str(packet.get("engine_sha256") or "")
    if len(engine_sha) != 64 or any(character not in "0123456789abcdef" for character in engine_sha):
        raise IntakeError("packet is missing a valid engine_sha256")
    return {"schema": RESULT_SCHEMA, "source_git_commit": revision,
            "packet_sha256": canonical_sha, "engine_sha256": engine_sha,
            "evaluator_sha256": _sha256(Path(__file__).read_bytes()),
            "review_sha256": sorted(review_sha256), "metrics": metrics,
            "thresholds": thresholds, "qualified": all(thresholds.values()),
            "limitations": ["Human ratings qualify only this consented corpus and engine packet."]}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("--manifest", type=Path, required=True); prep.add_argument("--audio-root", type=Path, required=True); prep.add_argument("--packet", type=Path, required=True); prep.add_argument("--review-template", type=Path); prep.add_argument("--reviewer-a-template", type=Path); prep.add_argument("--reviewer-b-template", type=Path)
    scoring = sub.add_parser("score"); scoring.add_argument("--packet", type=Path, required=True); scoring.add_argument("--review", type=Path, action="append", required=True); scoring.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            packet, review = prepare(args.manifest, args.audio_root)
            review_outputs = [path for path in (args.reviewer_a_template, args.reviewer_b_template) if path]
            if args.review_template:
                review_outputs.append(args.review_template)
            if not review_outputs or bool(args.reviewer_a_template) != bool(args.reviewer_b_template):
                raise IntakeError("provide --review-template or both --reviewer-a-template and --reviewer-b-template")
            outputs = [(args.packet, packet)]
            for slot, path in enumerate(review_outputs, start=1):
                form = dict(review)
                form["reviewer_slot"] = f"reviewer-{slot}"
                outputs.append((path, form))
            for path, value in outputs:
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return 0
        result = score(args.packet, args.review); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"); print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result["qualified"] else 1
    except IntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
