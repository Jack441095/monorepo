#!/usr/bin/env python3
"""Evaluate KENN's evidence-backed Internal Beta 0.1 release gates.

The ``pilot`` profile is narrower than a qualified beta: it permits a
supervised, disposable-set pilot when the technical boundary and documentation
gates pass, while reporting human review as pending. The ``qualified`` profile
additionally requires complete independent human review, an explicit
adjudication decision, a clean/reproducible source snapshot, and a verified
Developer ID signed and notarized macOS plug-in archive, corpus-bound
intelligence benchmarks, a reconnect-aware 24-hour soak receipt, and a
consented real-mix evaluation receipt.

This command is read-only unless ``--output`` is used to write its report. It
never manufactures evidence, reviewer scores, or an approval decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from adjudicate_human_review import ReviewInputError, adjudicate


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REAL_REPORT = (
    REPO_ROOT / "docs" / "evidence" / "ABLETON_LIVE_REAL_QUALIFICATION_2026-09-01.md"
    if (REPO_ROOT / "docs" / "evidence" / "ABLETON_LIVE_REAL_QUALIFICATION_2026-09-01.md").exists()
    else REPO_ROOT / "docs" / "ABLETON_LIVE_REAL_QUALIFICATION_2026-09-01.md"
)
DEFAULT_PACKET = (
    REPO_ROOT / "docs" / "evidence" / "ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json"
    if (REPO_ROOT / "docs" / "evidence" / "ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json").exists()
    else REPO_ROOT / "docs" / "ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json"
)
DEFAULT_MATRIX = (
    REPO_ROOT / "docs" / "evidence" / "ABLETON_LIVE_SUPPORT_MATRIX.json"
    if (REPO_ROOT / "docs" / "evidence" / "ABLETON_LIVE_SUPPORT_MATRIX.json").exists()
    else REPO_ROOT / "docs" / "ABLETON_LIVE_SUPPORT_MATRIX.json"
)
DEFAULT_PLUGIN_ARCHIVE = REPO_ROOT / "dist" / "KENN-Mix-Assistant-0.1.0-macOS.zip"
DEFAULT_PLUGIN_HOST_REPORT = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_PLUGIN_HOST_VALIDATION.json"
DEFAULT_SOAK_REPORT = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_COMPANION_24H_SOAK.json"
DEFAULT_REAL_MIX_REPORT = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_REAL_MIX_EVALUATION.json"
DEFAULT_PILOT_REPORT = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_SUPERVISED_PILOT_EVALUATION.json"
DEFAULT_PLANNER_BAKEOFF = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_DELIBERATIVE_MODEL_BAKEOFF.json"
DEFAULT_REAL_LIVE_ASSISTANT = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_REAL_LIVE_ASSISTANT_TASK.json"
DEFAULT_AUTOMATED_SUITE_REPORT = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_AUTOMATED_SUITE_QUALIFICATION.json"
DEFAULT_INTELLIGENCE_REPORT = REPO_ROOT / "tooling" / "evaluation" / "results" / "KENN_INTELLIGENCE_QUALIFICATION.json"
DEFAULT_INDEX_ROOT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "data" / "index"
DEFAULT_EMBEDDING_MODEL_ROOT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "artifacts" / "models" / "minilm"
SCHEMA = "kenn.internal_beta_readiness.v1"
_SOURCE_SNAPSHOT_IGNORED_UNTRACKED_PREFIXES = ("UX/KENN_ui sent to me/",)
MAX_PLUGIN_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_PLUGIN_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_PLUGIN_ARCHIVE_MEMBERS = 10_000


@dataclass(frozen=True)
class Gate:
    gate_id: str
    name: str
    status: str
    required_for: tuple[str, ...]
    evidence: list[str]
    details: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.gate_id,
            "name": self.name,
            "status": self.status,
            "required_for": list(self.required_for),
            "evidence": self.evidence,
            "details": self.details,
        }


def _gate(
    gate_id: str,
    name: str,
    status: str,
    required_for: tuple[str, ...],
    evidence: list[Path | str],
    details: str,
) -> Gate:
    rendered: list[str] = []
    for item in evidence:
        if isinstance(item, Path) and item.is_absolute() and REPO_ROOT in item.parents:
            rendered.append(str(item.relative_to(REPO_ROOT)))
        else:
            rendered.append(str(item))
    return Gate(gate_id, name, status, required_for, rendered, details)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _required_files_gate() -> Gate:
    paths = [
        REPO_ROOT / "docs" / "reports" / "ABLETON_ASSISTANT_READINESS_REPORT.md",
        REPO_ROOT / "docs" / "plans" / "ABLETON_ASSISTANT_UPGRADE_PLAN.md",
        REPO_ROOT / "docs" / "reports" / "ABLETON_ASSISTANT_CURRENT_STATE.md",
        REPO_ROOT / "docs" / "runbooks" / "ABLETON_ASSISTANT_SUPPORT_RUNBOOK.md",
        REPO_ROOT / "docs" / "plans" / "ABLETON_ASSISTANT_ROLLBACK_PLAN.md",
        REPO_ROOT / "docs" / "ABLETON_ASSISTANT_TESTER_GUIDE.md",
        REPO_ROOT / "tooling" / "scripts" / "install_abletonosc.py",
        REPO_ROOT / "integrations" / "ableton-osc" / "__init__.py",
        REPO_ROOT / "integrations" / "ableton-osc" / "LICENSE.md",
    ]
    missing = [path for path in paths if not path.is_file()]
    details = (
        "All required release documents and the pinned AbletonOSC vendor are present."
        if not missing
        else "Missing required artifacts: " + ", ".join(str(path.relative_to(REPO_ROOT)) for path in missing)
    )
    return _gate("artifacts", "Release artifacts and AbletonOSC identity", "pass" if not missing else "fail", ("pilot", "qualified"), paths, details)


def _real_live_gate(real_report: Path) -> Gate:
    text = _read(real_report)
    normalized_text = text.casefold()
    required_phrases = [
        "Status: **passed for the qualified read-only, track/transport",
        "Ableton Live 12 Suite 12.4.5",
        "AbletonOSC",
        "| Volume |",
        "| Pan |",
        "| Mute |",
        "| Solo |",
        "| Arm |",
        "| Transport play |",
        "| Transport stop |",
        "EQ Eight",
        "Compressor",
        "Utility",
        "saved-set retained-state recovery",
        "failure receipt",
        "no readback",
    ]
    missing = [phrase for phrase in required_phrases if phrase.casefold() not in normalized_text]
    details = (
        "The captured report contains the qualified read-only, reversible track/transport, device, failure, and saved-set recovery evidence."
        if text and not missing
        else ("Missing evidence phrases: " + ", ".join(missing) if text else "Qualification report is missing or unreadable.")
    )
    return _gate("real_live", "Real Ableton Live qualification", "pass" if text and not missing else "fail", ("pilot", "qualified"), [real_report], details)


def _support_matrix_gate(matrix_path: Path, real_report: Path = DEFAULT_REAL_REPORT) -> Gate:
    if not matrix_path.is_file():
        return _gate("support_matrix", "Explicit supported Live/OS matrix", "fail", ("pilot", "qualified"), [matrix_path], "No supported-matrix manifest exists; support cannot be inferred from prose alone.")
    try:
        data = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _gate("support_matrix", "Explicit supported Live/OS matrix", "fail", ("pilot", "qualified"), [matrix_path], f"Invalid matrix manifest: {exc}")
    entries = data.get("supported_configurations") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        return _gate("support_matrix", "Explicit supported Live/OS matrix", "fail", ("pilot", "qualified"), [matrix_path], "Matrix manifest has no supported configurations.")
    invalid: list[str] = []
    for item in entries:
        if not isinstance(item, dict) or item.get("status") != "qualified":
            invalid.append("every matrix entry must be explicitly marked qualified")
            continue
        evidence = item.get("evidence")
        evidence_path = (REPO_ROOT / evidence).resolve() if isinstance(evidence, str) else None
        if evidence_path is not None and not evidence_path.is_file():
            alt = REPO_ROOT / "docs" / "evidence" / Path(evidence).name
            if alt.is_file():
                evidence_path = alt.resolve()
        if evidence_path is None or REPO_ROOT not in evidence_path.parents or not evidence_path.is_file():
            invalid.append(f"{item.get('id', 'entry')} cites missing evidence")
            continue
        report_text = _read(evidence_path).casefold()
        for field in ("ableton_live", "os", "architecture", "bridge"):
            value = str(item.get(field) or "").casefold()
            if not value or value not in report_text:
                invalid.append(f"{item.get('id', 'entry')} does not match its evidence for {field}")
    report_text = _read(real_report).casefold()
    valid = not invalid and bool(report_text)
    if valid and not all(str(item.get("id") or "").casefold() in report_text for item in entries):
        invalid.append("matrix configuration id is not recorded in the supplied real-Live report")
        valid = False
    details = f"{len(entries)} explicitly qualified Live/OS configuration(s) are declared and cross-checked against cited evidence." if valid else "; ".join(invalid) or "Matrix evidence report is missing."
    return _gate("support_matrix", "Explicit supported Live/OS matrix", "pass" if valid else "fail", ("pilot", "qualified"), [matrix_path], details)


def _validated_human_review_packet(packet_path: Path) -> dict[str, Any]:
    packet_data = json.loads(packet_path.read_text(encoding="utf-8"))
    provenance = packet_data.get("provenance") if isinstance(packet_data.get("provenance"), dict) else {}
    active_index = provenance.get("active_index") if isinstance(provenance.get("active_index"), dict) else {}
    version_id = (DEFAULT_INDEX_ROOT / "CURRENT").read_text(encoding="ascii").strip()
    manifest = json.loads((DEFAULT_INDEX_ROOT / "versions" / version_id / "manifest.json").read_text(encoding="utf-8"))
    embedding = manifest.get("build", {}).get("embedding_model", {})
    expected_index = {
        "version_id": version_id,
        "content_sha256": str(manifest.get("content_sha256") or ""),
        "chunk_count": int(manifest.get("chunk_count") or 0),
        "retrieval_mode": "hybrid" if embedding.get("model_sha256") else "bm25_only",
        "embedding_model": {
            "id": str(embedding.get("id") or ""),
            "model_sha256": str(embedding.get("model_sha256") or ""),
            "tokenizer_sha256": str(embedding.get("tokenizer_sha256") or ""),
        },
    }
    if provenance.get("generator_sha256") != hashlib.sha256((REPO_ROOT / "tooling" / "scripts" / "build_human_review_packet.py").read_bytes()).hexdigest():
        raise ReviewInputError("review packet generator_sha256 is stale")
    if provenance.get("questions_sha256") != hashlib.sha256((REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json").read_bytes()).hexdigest():
        raise ReviewInputError("review packet questions_sha256 is stale")
    if active_index != expected_index:
        raise ReviewInputError("review packet active index identity is stale")
    packet_revision = str(provenance.get("source_revision") or "")
    if len(packet_revision) != 40:
        raise ReviewInputError("review packet source_revision is invalid")
    subprocess.run(["git", "merge-base", "--is-ancestor", packet_revision, "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True)
    unchanged = subprocess.run(
        ["git", "diff", "--quiet", packet_revision, "HEAD", "--", *_HUMAN_REVIEW_ANSWER_INPUTS],
        cwd=REPO_ROOT,
    ).returncode == 0
    if not unchanged:
        raise ReviewInputError("review packet answer-engine inputs changed after packet generation")
    return packet_data


def _human_review_gate(packet_path: Path, reviewer_a: Path | None, reviewer_b: Path | None, adjudication: Path | None) -> Gate:
    evidence: list[Path | str] = [packet_path]
    if reviewer_a:
        evidence.append(reviewer_a)
    if reviewer_b:
        evidence.append(reviewer_b)
    if adjudication:
        evidence.append(adjudication)
    if not packet_path.is_file():
        return _gate("human_review", "Independent human review and adjudication", "fail", ("qualified",), evidence, "The 100-case review packet is missing.")
    try:
        packet_data = _validated_human_review_packet(packet_path)
    except (OSError, json.JSONDecodeError, ReviewInputError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return _gate("human_review", "Independent human review and adjudication", "fail", ("qualified",), evidence, f"Review packet provenance is invalid: {exc}")
    if not reviewer_a or not reviewer_b:
        return _gate("human_review", "Independent human review and adjudication", "pending", ("qualified",), evidence, "Two independent reviewer score files are still required; no scores are assumed.")
    if not reviewer_a.is_file() or not reviewer_b.is_file():
        return _gate("human_review", "Independent human review and adjudication", "pending", ("qualified",), evidence, "One or both independent reviewer score files are missing.")
    if not adjudication or not adjudication.is_file():
        return _gate("human_review", "Independent human review and adjudication", "pending", ("qualified",), evidence, "Complete reviewer files exist, but an adjudication decision artifact is still required.")
    try:
        reviewer_a_data = json.loads(reviewer_a.read_text(encoding="utf-8"))
        reviewer_b_data = json.loads(reviewer_b.read_text(encoding="utf-8"))
        expected_packet_sha256 = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        for reviewer_name, reviewer_data in (("reviewer_a", reviewer_a_data), ("reviewer_b", reviewer_b_data)):
            if reviewer_data.get("packet_sha256") != expected_packet_sha256:
                raise ReviewInputError(f"{reviewer_name}: packet_sha256 does not match the review packet")
        adjudication_report = adjudicate(packet_data, reviewer_a_data, reviewer_b_data)
        data = json.loads(adjudication.read_text(encoding="utf-8"))
        expected_bindings = {
            "packet_sha256": expected_packet_sha256,
            "reviewer_a_sha256": hashlib.sha256(reviewer_a.read_bytes()).hexdigest(),
            "reviewer_b_sha256": hashlib.sha256(reviewer_b.read_bytes()).hexdigest(),
        }
        if data.get("schema") != "kenn.human_review_decision.v1":
            raise ReviewInputError("adjudication decision has an unsupported schema")
        for field, expected in expected_bindings.items():
            if data.get(field) != expected:
                raise ReviewInputError(f"adjudication decision {field} does not match its reviewed input")
        if data.get("case_count") != adjudication_report.get("case_count"):
            raise ReviewInputError("adjudication decision case_count does not match the completed review")
        if not str(data.get("adjudicator_id") or "").strip():
            raise ReviewInputError("adjudication decision requires adjudicator_id")
        if data.get("disagreements_reviewed") is not True:
            raise ReviewInputError("adjudication decision must confirm disagreement review")
    except (OSError, json.JSONDecodeError, ReviewInputError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return _gate("human_review", "Independent human review and adjudication", "fail", ("qualified",), evidence, f"Reviewer or adjudication evidence is invalid: {exc}")
    complete = adjudication_report.get("case_count") == len(packet_data.get("cases", []))
    quality_passed = adjudication_report.get("thresholds", {}).get("qualified") is True
    approved = complete and quality_passed and data.get("release_decision") == "approved_for_internal_beta" and data.get("status") == "adjudicated"
    if approved:
        details = "Independent scores meet the packet-bound quality thresholds and the adjudicator explicitly approved the internal beta."
    elif not quality_passed:
        details = "Independent scores do not meet the packet-bound human-review quality thresholds."
    else:
        details = "Adjudication artifact is present but does not contain an explicit internal-beta approval."
    return _gate("human_review", "Independent human review and adjudication", "pass" if approved else "fail", ("qualified",), evidence, details)


def _source_status_is_ignored(entry: str, output_path: Path | None = None) -> bool:
    if output_path is not None:
        try:
            relative_output = output_path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            relative_output = ""
        if len(entry) >= 4 and entry[2] == " " and entry[3:] == relative_output:
            return True
    if not entry.startswith("?? "):
        return False
    path = entry[3:]
    return any(path.startswith(prefix) for prefix in _SOURCE_SNAPSHOT_IGNORED_UNTRACKED_PREFIXES)


def _source_gate(output_path: Path | None = None) -> Gate:
    try:
        status_output = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        status_entries = [entry for entry in status_output.split("\0") if entry]
        relevant_entries = [entry for entry in status_entries if not _source_status_is_ignored(entry, output_path)]
        ignored_entries = [entry for entry in status_entries if _source_status_is_ignored(entry, output_path)]
        dirty = bool(relevant_entries)
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return _gate("source_snapshot", "Reproducible source snapshot", "fail", ("qualified",), ["git metadata"], "Git metadata could not be read.")
    if dirty:
        details = f"HEAD is {commit}, but the KENN source snapshot has uncommitted changes; package a reviewed snapshot before qualification."
    else:
        details = f"HEAD is {commit}; KENN source snapshot is clean."
        if output_path is not None and any(
            _source_status_is_ignored(entry, output_path)
            and not _source_status_is_ignored(entry)
            for entry in ignored_entries
        ):
            details += " Ignored the exact requested gate-report output path."
        if any(_source_status_is_ignored(entry) for entry in ignored_entries):
            details += " Ignored only the declared untracked, out-of-scope colleague UX handoff directory."
    return _gate("source_snapshot", "Reproducible source snapshot", "pass" if not dirty else "pending", ("qualified",), ["git metadata"], details)


def _plugin_distribution_gate(archive: Path, host_report: Path | None = None) -> Gate:
    """Verify the exact distributable, not unrelated installed dev bundles."""
    checksum_path = Path(str(archive) + ".sha256")
    evidence: list[Path | str] = [archive, checksum_path]
    if host_report:
        evidence.append(host_report)
    if not archive.is_file() or not checksum_path.is_file():
        return _gate(
            "plugin_distribution",
            "Signed and notarized macOS plug-in archive",
            "pending",
            ("qualified",),
            evidence,
            "No complete signed/notarized plug-in archive and checksum are present; run tooling/scripts/package_macos_plugins.sh with release credentials.",
        )
    try:
        if archive.stat().st_size > MAX_PLUGIN_ARCHIVE_BYTES:
            raise ValueError("plug-in archive exceeds the compressed size limit")
        expected_digest = checksum_path.read_text(encoding="utf-8").split()[0].lower()
        actual_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    except (OSError, IndexError) as exc:
        return _gate("plugin_distribution", "Signed and notarized macOS plug-in archive", "fail", ("qualified",), evidence, f"Plug-in checksum could not be read: {exc}")
    if expected_digest != actual_digest:
        return _gate("plugin_distribution", "Signed and notarized macOS plug-in archive", "fail", ("qualified",), evidence, "Plug-in archive SHA-256 does not match its checksum file.")

    try:
        with tempfile.TemporaryDirectory(prefix="kenn-plugin-gate-") as temp_name:
            temp_root = Path(temp_name).resolve()
            with zipfile.ZipFile(archive) as package:
                members = package.infolist()
                names = [member.filename for member in members]
                if len(members) > MAX_PLUGIN_ARCHIVE_MEMBERS:
                    raise ValueError("plug-in archive contains too many members")
                if len(set(names)) != len(names):
                    raise ValueError("plug-in archive contains duplicate member paths")
                if sum(member.file_size for member in members) > MAX_PLUGIN_UNCOMPRESSED_BYTES:
                    raise ValueError("plug-in archive exceeds the uncompressed size limit")
                for member in members:
                    member_path = PurePosixPath(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(f"unsafe archive member: {member.filename}")
                    if member.flag_bits & 0x1:
                        raise ValueError(f"encrypted archive member is not allowed: {member.filename}")
                    if stat.S_ISLNK(member.external_attr >> 16):
                        raise ValueError(f"symbolic-link archive member is not allowed: {member.filename}")
                    destination = (temp_root / Path(*member_path.parts)).resolve()
                    if destination != temp_root and temp_root not in destination.parents:
                        raise ValueError(f"archive member escapes extraction root: {member.filename}")
                package.extractall(temp_root)
            vst3 = list(temp_root.rglob("KENN Mix Assistant.vst3"))
            au = list(temp_root.rglob("KENN Mix Assistant.component"))
            if len(vst3) != 1 or len(au) != 1:
                raise ValueError("archive must contain exactly one KENN VST3 and one KENN Audio Unit")
            team_ids: set[str] = set()
            for bundle in (vst3[0], au[0]):
                verify = subprocess.run(
                    ["codesign", "--verify", "--strict", "--verbose=2", str(bundle)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                identity = subprocess.run(
                    ["codesign", "-dv", "--verbose=4", str(bundle)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                identity_text = identity.stdout + identity.stderr
                stapled = subprocess.run(
                    ["xcrun", "stapler", "validate", str(bundle)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                accepted = subprocess.run(
                    ["spctl", "-a", "-vv", "-t", "install", str(bundle)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if verify.returncode != 0:
                    raise ValueError(f"codesign verification failed for {bundle.name}")
                if "Authority=Developer ID Application:" not in identity_text or "TeamIdentifier=not set" in identity_text:
                    raise ValueError(f"{bundle.name} is not signed with a Developer ID Application identity")
                team_match = re.search(r"^TeamIdentifier=([A-Z0-9]+)$", identity_text, re.MULTILINE)
                if team_match is None:
                    raise ValueError(f"{bundle.name} has no valid Developer Team identity")
                team_ids.add(team_match.group(1))
                if stapled.returncode != 0:
                    raise ValueError(f"notarization ticket validation failed for {bundle.name}")
                if accepted.returncode != 0:
                    raise ValueError(f"Gatekeeper rejected {bundle.name}")
            if len(team_ids) != 1:
                raise ValueError("VST3 and Audio Unit are signed by different Developer Teams")
            developer_team_id = next(iter(team_ids))
    except (OSError, subprocess.TimeoutExpired, zipfile.BadZipFile, ValueError) as exc:
        return _gate("plugin_distribution", "Signed and notarized macOS plug-in archive", "fail", ("qualified",), evidence, f"Plug-in distribution verification failed: {exc}")

    if host_report is None or not host_report.is_file():
        return _gate(
            "plugin_distribution", "Signed and notarized macOS plug-in archive", "pending", ("qualified",),
            evidence, "The archive passes local signature/notarization checks, but exact-archive clean-host validation evidence is missing.",
        )
    try:
        host = json.loads(host_report.read_text(encoding="utf-8"))
        tested_at = datetime.fromisoformat(str(host.get("tested_at") or ""))
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        checks = host.get("checks") if isinstance(host.get("checks"), dict) else {}
        required_checks = (
            "auval_passed", "vst3_validator_passed", "ableton_au_discovered",
            "ableton_vst3_discovered", "rollback_verified",
        )
        host_valid = (
            host.get("schema") == "kenn.plugin_host_validation.v1"
            and host.get("archive_sha256") == actual_digest
            and host.get("source_git_commit") == head
            and host.get("developer_team_id") == developer_team_id
            and host.get("environment") in {"clean_local_account", "second_mac"}
            and tested_at.tzinfo is not None and tested_at <= datetime.now(timezone.utc)
            and all(checks.get(name) is True for name in required_checks)
            and host.get("tester_signoff") is True
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return _gate("plugin_distribution", "Signed and notarized macOS plug-in archive", "fail", ("qualified",), evidence, f"Plug-in host-validation evidence is invalid: {exc}")
    if not host_valid:
        return _gate("plugin_distribution", "Signed and notarized macOS plug-in archive", "fail", ("qualified",), evidence, "Host-validation receipt does not prove exact-archive AU/VST3 validation, Ableton discovery, rollback, and tester sign-off on a clean environment.")

    return _gate(
        "plugin_distribution",
        "Signed and notarized macOS plug-in archive",
        "pass",
        ("qualified",),
        evidence,
        f"Archive SHA-256 {actual_digest} matches; signatures, notarization, Gatekeeper, clean-host AU/VST3 validation, Ableton discovery, and rollback all pass.",
    )


# The four package roots that actually make up KENN's own suite (matching
# docs/ABLETON_ASSISTANT_TESTER_GUIDE.md's documented command exactly). A
# bare `pytest -q` with no path args instead auto-discovers everything
# pytest can find under REPO_ROOT -- including unrelated, uncommitted
# content that happens to sit there (e.g. a colleague's separate project
# folder dropped alongside this repo for review). That unrelated content's
# own collection failures can interrupt the whole run and report a false
# "fail" that has nothing to do with KENN's actual test health -- found and
# fixed 2026-09-06 after --run-suite reported 84 errors that were entirely
# from such a folder, not from this repository's own tests.
_SUITE_TARGETS = ("apps/backend/src/kenn/tests", "chat/tests", "mix-review/tests", "automix/tests")
_SUITE_COMMAND_DISPLAY = "python3 -m pytest " + " ".join(_SUITE_TARGETS) + " -q"

_DURABLE_QUALIFICATION_REPORTS = {
    "evaluation/results/KENN_AUTOMATED_SUITE_QUALIFICATION.json",
    "evaluation/results/KENN_INTELLIGENCE_QUALIFICATION.json",
}

_HUMAN_REVIEW_ANSWER_INPUTS = (
    "chat",
    "apps/backend/src/kenn/core/chat.py",
    "apps/backend/src/kenn/core/chat_answer.py",
    "apps/backend/src/kenn/core/chat_constants.py",
    "apps/backend/src/kenn/core/chat_formatting.py",
    "apps/backend/src/kenn/core/chat_grounding.py",
    "apps/backend/src/kenn/core/chat_retrieval.py",
    "apps/backend/src/kenn/core/chat_routing.py",
    "apps/backend/src/kenn/core/branches.py",
    "apps/backend/src/kenn/core/diagnostic_framework.py",
    "apps/backend/src/kenn/core/diagnostic_state.py",
    "apps/backend/src/kenn/core/evidence.py",
    "apps/backend/src/kenn/core/feedback_signals.py",
    "apps/backend/src/kenn/core/knowledge_graph.py",
    "apps/backend/src/kenn/core/lm_identity.py",
    "apps/backend/src/kenn/core/session_memory.py",
    "apps/backend/src/kenn/core/suggestions.py",
    "apps/backend/src/kenn/retrieval",
    "apps/backend/src/kenn/evals/questions.json",
    "apps/backend/src/kenn/Training_Data_Sources",
    "apps/backend/src/kenn/data/index",
    "tooling/scripts/build_human_review_packet.py",
)

_QUALIFICATION_SOURCE_PREFIXES = (
    "source/",
    "chat/",
    "mix-review/",
    "automix/",
    "tooling/scripts/",
    "third_party/",
    "common/",
)
_QUALIFICATION_SOURCE_ROOT_FILES = {
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "pytest.ini",
    "requirements.txt",
    "requirements-training.txt",
}


def _tracked_source_sha256() -> str:
    """Hash tracked repository inputs while excluding the receipts themselves."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
    )
    digest = hashlib.sha256()
    for raw_path in sorted(filter(None, completed.stdout.split(b"\0"))):
        relative = raw_path.decode("utf-8", errors="surrogateescape")
        if not (
            relative in _QUALIFICATION_SOURCE_ROOT_FILES
            or relative.startswith(_QUALIFICATION_SOURCE_PREFIXES)
        ):
            continue
        if relative in _DURABLE_QUALIFICATION_REPORTS:
            continue
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_qualification_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    temporary.chmod(0o644)
    temporary.replace(path)


def _load_qualification_receipt(path: Path, schema: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != schema or payload.get("source_sha256") != _tracked_source_sha256():
            return None
        return payload
    except (OSError, json.JSONDecodeError, subprocess.SubprocessError):
        return None


def _automated_gate(run_suite: bool, receipt_path: Path | None = None) -> Gate:
    if not run_suite:
        if receipt_path is not None:
            receipt = _load_qualification_receipt(receipt_path, "kenn.automated_suite_qualification.v1")
            if receipt is not None and receipt.get("passed") is True:
                return _gate("automated_suite", "Automated regression suite", "pass", ("pilot", "qualified"), [receipt_path], str(receipt.get("summary", "Qualified automated suite.")))
        return _gate("automated_suite", "Automated regression suite", "pending", ("pilot", "qualified"), [_SUITE_COMMAND_DISPLAY], "Not run by this invocation; pass --run-suite to execute it.")
    try:
        environment = os.environ.copy()
        import_paths = [str(REPO_ROOT / "apps" / "backend" / "src"), str(REPO_ROOT / "packages" / "chat"), str(REPO_ROOT / "packages" / "mix-review"), str(REPO_ROOT / "packages" / "automix")]
        existing_pythonpath = environment.get("PYTHONPATH")
        if existing_pythonpath:
            import_paths.append(existing_pythonpath)
        environment["PYTHONPATH"] = os.pathsep.join(import_paths)
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", *_SUITE_TARGETS, "-q"],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _gate("automated_suite", "Automated regression suite", "fail", ("pilot", "qualified"), [_SUITE_COMMAND_DISPLAY], f"Suite execution failed: {exc}")
    # pytest's real summary line ("N passed...") is the last line of stdout,
    # but a stray warning (e.g. an interpreter-shutdown DeprecationWarning)
    # can land on stderr after it -- naively taking the very last combined
    # line picked up that warning instead of the actual result summary.
    stdout_lines = completed.stdout.strip().splitlines()
    summary = stdout_lines[-1] if stdout_lines else (completed.stderr.strip().splitlines() or ["no pytest summary"])[-1]
    passed = completed.returncode == 0
    if receipt_path is not None:
        _write_qualification_receipt(receipt_path, {
            "schema": "kenn.automated_suite_qualification.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_sha256": _tracked_source_sha256(),
            "command": _SUITE_COMMAND_DISPLAY,
            "passed": passed,
            "summary": summary,
        })
    return _gate("automated_suite", "Automated regression suite", "pass" if passed else "fail", ("pilot", "qualified"), [receipt_path or _SUITE_COMMAND_DISPLAY], summary)


def evaluate_intelligence_results(results: list[dict[str, Any]]) -> tuple[bool, str]:
    """Apply the release thresholds to real component outputs.

    Kept separate from subprocess execution so a constrained workstation can
    run each deterministic benchmark independently and later assemble the
    same fail-closed qualification receipt.
    """
    if len(results) != 5 or any(not isinstance(result, dict) for result in results):
        return False, "Expected exactly five intelligence benchmark result objects."
    hard_cases, retrieval_modes, session_grounded, assistant_recovery, arrangement_intelligence = results
    valid = (
        hard_cases.get("schema") == "kenn.chat_hard_case_benchmark.v1"
        and hard_cases.get("qualified") is True
        and int(hard_cases.get("case_count", 0)) > 0
        and retrieval_modes.get("schema") == "kenn.retrieval_mode_comparison.v1"
        and retrieval_modes.get("decision", {}).get("no_quality_regression") is True
        and float(retrieval_modes.get("modes", {}).get("hybrid", {}).get("summary", {}).get("recall_at_4", 0)) >= 0.95
        and hard_cases.get("corpus_sha256") == retrieval_modes.get("corpus_sha256")
        and session_grounded.get("schema") == "kenn.session_grounded_advice_benchmark.v1"
        and session_grounded.get("qualified") is True
        and int(session_grounded.get("case_count", 0)) > 0
        and assistant_recovery.get("schema") == "kenn.assistant_recovery_qualification.v1"
        and assistant_recovery.get("passed") is True
        and int(assistant_recovery.get("case_count", 0)) >= 8
        and assistant_recovery.get("passed_count") == assistant_recovery.get("case_count")
        and assistant_recovery.get("safety_passed_count") == assistant_recovery.get("safety_case_count")
        and assistant_recovery.get("execution_authorized") is False
        and arrangement_intelligence.get("schema") == "kenn.arrangement_intelligence_evaluation.v1"
        and arrangement_intelligence.get("all_cases_passed") is True
        and int(arrangement_intelligence.get("case_count", 0)) >= 4
        and arrangement_intelligence.get("passed_case_count") == arrangement_intelligence.get("case_count")
        and arrangement_intelligence.get("execution_authorized") is False
    )
    details = (
        f"Hard cases {hard_cases.get('passed')}/{hard_cases.get('case_count')}; hybrid recall@4 "
        f"{retrieval_modes.get('modes', {}).get('hybrid', {}).get('summary', {}).get('recall_at_4')}; corpus hashes match; "
        f"session-grounded advice {session_grounded.get('passed')}/{session_grounded.get('case_count')}; "
        f"assistant recovery {assistant_recovery.get('passed_count')}/{assistant_recovery.get('case_count')} "
        f"with {assistant_recovery.get('safety_passed_count')}/{assistant_recovery.get('safety_case_count')} safety cases; "
        f"arrangement intelligence {arrangement_intelligence.get('passed_case_count')}/{arrangement_intelligence.get('case_count')}."
        if valid else "Benchmark receipts did not satisfy schema, corpus binding, grounding, retrieval, session-evidence, recovery, or arrangement thresholds."
    )
    return valid, details


def _intelligence_gate(run_intelligence: bool, receipt_path: Path | None = None) -> Gate:
    commands = [
        [sys.executable, "tooling/scripts/evaluate_chat_hard_cases.py"],
        [sys.executable, "tooling/scripts/evaluate_retrieval_modes.py"],
        [sys.executable, "tooling/scripts/evaluate_session_grounded_advice.py"],
        [sys.executable, "tooling/scripts/qualify_assistant_recovery.py"],
        [sys.executable, "tooling/scripts/evaluate_arrangement_intelligence.py"],
    ]
    evidence = [
        "python3 tooling/scripts/evaluate_chat_hard_cases.py",
        "python3 tooling/scripts/evaluate_retrieval_modes.py",
        "python3 tooling/scripts/evaluate_session_grounded_advice.py",
        "python3 tooling/scripts/qualify_assistant_recovery.py",
        "python3 tooling/scripts/evaluate_arrangement_intelligence.py",
    ]
    if not run_intelligence:
        if receipt_path is not None:
            receipt = _load_qualification_receipt(receipt_path, "kenn.intelligence_qualification.v1")
            if receipt is not None and receipt.get("passed") is True:
                return _gate("intelligence", "Intelligence and recovery qualification", "pass", ("qualified",), [receipt_path], str(receipt.get("details", "Qualified intelligence benchmarks.")))
        return _gate("intelligence", "Intelligence and recovery qualification", "pending", ("qualified",), evidence, "Not run; pass --run-intelligence to execute all grounding, retrieval, and assistant-recovery benchmarks.")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "apps" / "backend" / "src"), str(REPO_ROOT / "packages" / "chat")])
    environment["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "apps" / "backend" / "src"), str(REPO_ROOT / "packages" / "chat"), str(REPO_ROOT / "packages" / "mix-review" / "core")])
    results: list[dict[str, Any]] = []
    try:
        for command in commands:
            completed = subprocess.run(command, cwd=REPO_ROOT, env=environment, capture_output=True, text=True, timeout=180, check=False)
            result = json.loads(completed.stdout)
            if completed.returncode != 0:
                raise ValueError(f"{Path(command[1]).name} returned {completed.returncode}")
            results.append(result)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as exc:
        return _gate("intelligence", "Intelligence and recovery qualification", "fail", ("qualified",), evidence, f"Intelligence benchmark failed: {exc}")
    valid, details = evaluate_intelligence_results(results)
    if receipt_path is not None:
        _write_qualification_receipt(receipt_path, {
            "schema": "kenn.intelligence_qualification.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_sha256": _tracked_source_sha256(),
            "commands": evidence,
            "passed": valid,
            "details": details,
        })
    return _gate(
        "intelligence", "Intelligence and recovery qualification", "pass" if valid else "fail",
        ("qualified",), [receipt_path] if receipt_path is not None else evidence, details,
    )


def _planner_bakeoff_gate(path: Path) -> Gate:
    """Require repeated model planning, safety, and recovery evidence."""
    if not path.is_file():
        return _gate(
            "planner_bakeoff", "Repeated deliberative model qualification", "pending",
            ("qualified",), [path],
            "A complete, input-bound, three-repeat planner bake-off artifact is required.",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hashes = data.get("input_sha256")
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError("input_sha256 is missing")
        for relative, expected in hashes.items():
            candidate = (REPO_ROOT / str(relative)).resolve()
            if candidate != REPO_ROOT and REPO_ROOT not in candidate.parents:
                raise ValueError("input hash path escapes the repository")
            if not candidate.is_file():
                raise ValueError(f"bound input is missing: {relative}")
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"bound input changed: {relative}")
        required_inputs = {
            "tooling/scripts/run_deliberative_transformers_bakeoff.py",
            "apps/backend/src/kenn/core/deliberative_plan.py",
            "apps/backend/src/kenn/core/deliberative_planner.py",
            "apps/backend/src/kenn/core/deliberative_benchmark.py",
            "apps/backend/src/kenn/core/deliberative_bakeoff.py",
            "apps/backend/src/kenn/core/model_recovery_eval.py",
            "packages/chat/evals/ableton_deliberative_holdout.json",
            "packages/chat/evals/ableton_deliberative_adversarial.json",
        }
        if not required_inputs <= set(hashes):
            raise ValueError("input hashes do not cover every planner and sealed-suite input")
        progress = data.get("progress") if isinstance(data.get("progress"), dict) else {}
        models = data.get("models") if isinstance(data.get("models"), list) else []
        recommended = str(data.get("recommended_model") or "")
        model = next((item for item in models if isinstance(item, dict) and item.get("model_id") == recommended), None)
        expected_benchmarks = {
            "ableton-deliberative-holdout-2026-09-08",
            "ableton-deliberative-adversarial-2026-09-08",
        }
        valid = bool(
            data.get("schema") == "kenn.deliberative_model_bakeoff.v1"
            and progress.get("complete") is True
            and progress.get("status") == "complete"
            and int(progress.get("completed_run_count", 0)) == int(progress.get("expected_run_count", -1))
            and int(data.get("eligible_model_count", 0)) >= 1
            and model
            and model.get("eligible") is True
            and model.get("all_runs_passed") is True
            and int(model.get("repeat_count", 0)) >= 3
            and set(model.get("benchmark_ids") or []) == expected_benchmarks
            and float(model.get("minimum_contract_valid_rate", 0)) == 1.0
            and float(model.get("minimum_safety_pass_rate", 0)) == 1.0
            and model.get("model_recovery_passed") is True
            and int(model.get("model_recovery_runs", 0)) >= 3
            and float((model.get("pass_rate") or {}).get("minimum", 0)) == 1.0
            and model.get("latency_evidence_complete") is True
            and model.get("latency_passed") is True
            and float(model.get("mean_latency_ms", float("inf"))) <= 5_000.0
            and float(model.get("maximum_p95_latency_ms", float("inf"))) <= 15_000.0
        )
        if not valid:
            raise ValueError("planner thresholds or repeat coverage were not satisfied")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return _gate(
            "planner_bakeoff", "Repeated deliberative model qualification", "fail",
            ("qualified",), [path], f"Planner bake-off evidence is invalid: {exc}",
        )
    return _gate(
        "planner_bakeoff", "Repeated deliberative model qualification", "pass",
        ("qualified",), [path],
        f"{recommended} passed three or more complete repeats of both sealed suites with 100% contract, safety, trajectory, and model-plan recovery results, plus the 5 s mean / 15 s p95 latency ceiling.",
    )


def _real_live_assistant_gate(path: Path, planner_bakeoff: Path = DEFAULT_PLANNER_BAKEOFF) -> Gate:
    """Require one restored, model-planned, end-to-end real-Live trajectory."""
    if not path.is_file():
        return _gate(
            "real_live_assistant", "Real-Live model-planned assistant lifecycle", "pending",
            ("qualified",), [path],
            "A proposal, confirmed apply, verified receipt, replay rejection, and exact undo on a disposable real Live set are required.",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        planner_data = json.loads(planner_bakeoff.read_text(encoding="utf-8"))
        recommended_planner = str(planner_data.get("recommended_model") or "")
        recommended_provider = str(planner_data.get("provider") or "")
        planner_evidence_sha256 = hashlib.sha256(planner_bakeoff.read_bytes()).hexdigest()
        head_parts = subprocess.run(
            ["git", "rev-list", "--parents", "-n", "1", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip().split()
        head = head_parts[0]
        head_parents = set(head_parts[1:])
        runner_digest = hashlib.sha256(
            (REPO_ROOT / "tooling" / "scripts" / "qualify_assistant_live_task.py").read_bytes()
        ).hexdigest()
        if not recommended_planner or not recommended_provider:
            raise ValueError("the bound planner bake-off has no model/provider recommendation")
        serialized = json.dumps(data, sort_keys=True).casefold()
        write_receipt = data.get("write_receipt") if isinstance(data.get("write_receipt"), dict) else {}
        undo_receipt = data.get("undo_receipt") if isinstance(data.get("undo_receipt"), dict) else {}
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
        proposal = data.get("proposal") if isinstance(data.get("proposal"), dict) else {}
        events = data.get("events") if isinstance(data.get("events"), list) else []
        stages = [str(event.get("stage") or "") for event in events if isinstance(event, dict)]
        required_stages = (
            "initial_context", "planned", "proposal", "applied", "replay",
            "undo_proposal", "undo_applied", "final_context",
        )
        initial_fingerprint = str(data.get("initial_snapshot_fingerprint") or "")
        final_fingerprint = str(data.get("final_snapshot_fingerprint") or "")
        session_id = str(data.get("session_id") or "").strip()
        task_id = str(data.get("task_id") or "").strip()
        write_receipt_id = str(write_receipt.get("receipt_id") or "").strip()
        undo_receipt_id = str(undo_receipt.get("receipt_id") or "").strip()
        initial_events = [event for event in events if isinstance(event, dict) and event.get("stage") == "initial_context"]
        final_events = [event for event in events if isinstance(event, dict) and event.get("stage") == "final_context"]
        initial_context = initial_events[0].get("context") if len(initial_events) == 1 else {}
        final_context = final_events[0].get("context") if len(final_events) == 1 else {}
        initial_context = initial_context if isinstance(initial_context, dict) else {}
        final_context = final_context if isinstance(final_context, dict) else {}
        event_by_stage = {
            stage: next((event for event in events if isinstance(event, dict) and event.get("stage") == stage), {})
            for stage in required_stages
        }
        planned_result = event_by_stage["planned"].get("result")
        proposal_result = event_by_stage["proposal"].get("result")
        applied_result = event_by_stage["applied"].get("result")
        replay_result = event_by_stage["replay"].get("result")
        undo_proposal_result = event_by_stage["undo_proposal"].get("result")
        undo_applied_result = event_by_stage["undo_applied"].get("result")
        planned_result = planned_result if isinstance(planned_result, dict) else {}
        proposal_result = proposal_result if isinstance(proposal_result, dict) else {}
        applied_result = applied_result if isinstance(applied_result, dict) else {}
        replay_result = replay_result if isinstance(replay_result, dict) else {}
        undo_proposal_result = undo_proposal_result if isinstance(undo_proposal_result, dict) else {}
        undo_applied_result = undo_applied_result if isinstance(undo_applied_result, dict) else {}
        planned_task = planned_result.get("task") if isinstance(planned_result.get("task"), dict) else {}
        event_proposal = proposal_result.get("proposal") if isinstance(proposal_result.get("proposal"), dict) else {}
        applied_receipt = applied_result.get("receipt") if isinstance(applied_result.get("receipt"), dict) else {}
        applied_binding = applied_result.get("assistant_task") if isinstance(applied_result.get("assistant_task"), dict) else {}
        applied_task = applied_binding.get("task") if isinstance(applied_binding.get("task"), dict) else {}
        undo_proposal = undo_proposal_result.get("proposal") if isinstance(undo_proposal_result.get("proposal"), dict) else {}
        event_undo_receipt = undo_applied_result.get("receipt") if isinstance(undo_applied_result.get("receipt"), dict) else {}
        proposal_action_id = str(proposal.get("action_id") or proposal.get("id") or "").strip()
        undo_action_id = str(undo_proposal.get("action_id") or undo_proposal.get("id") or "").strip()
        valid = bool(
            data.get("schema") == "kenn.real_live_assistant_task_qualification.v1"
            and data.get("evidence_kind") == "real_live"
            and data.get("status") == "passed"
            and data.get("changed") is False
            and data.get("restored_exactly") is True
            and data.get("replay_rejected") is True
            and data.get("assistant_task_completed") is True
            # A tracked evidence receipt is committed after the run that
            # produced it, so its source snapshot is normally HEAD's
            # immediate parent.  Accept HEAD as well for proposal-only or
            # untracked receipts, while rejecting evidence older than the
            # commit that immediately precedes the evidence commit.
            and data.get("source_git_commit") in ({head} | head_parents)
            and data.get("runner_sha256") == runner_digest
            and session_id and task_id
            and isinstance(plan.get("steps"), list) and bool(plan["steps"])
            and proposal_action_id
            and all(stages.count(stage) == 1 for stage in required_stages)
            and [stages.index(stage) for stage in required_stages] == sorted(
                stages.index(stage) for stage in required_stages
            )
            and data.get("planner_provider") == recommended_provider
            and data.get("planner_id") == recommended_planner
            and data.get("planner_evidence_sha256") == planner_evidence_sha256
            and (
                data.get("planner_provider") != "transformers"
                or data.get("planner_transport_sha256") == hashlib.sha256(
                    (REPO_ROOT / "tooling" / "scripts" / "serve_transformers_ollama_compat.py").read_bytes()
                ).hexdigest()
            )
            and write_receipt.get("status") == "applied"
            and write_receipt.get("verified") is True
            and write_receipt_id
            and undo_receipt.get("status") == "applied"
            and undo_receipt.get("verified") is True
            and undo_receipt_id and undo_receipt_id != write_receipt_id
            and re.fullmatch(r"sha256:[0-9a-f]{64}", initial_fingerprint)
            and final_fingerprint == initial_fingerprint
            and initial_context.get("session_id") == session_id
            and initial_context.get("snapshot_fingerprint") == initial_fingerprint
            and initial_context.get("transport_status") == "connected"
            and final_context.get("session_id") == session_id
            and final_context.get("snapshot_fingerprint") == final_fingerprint
            and final_context.get("transport_status") == "connected"
            and planned_result.get("ok") is True
            and planned_result.get("planner_source") == "model_sketch"
            and planned_task.get("task_id") == task_id
            and planned_task.get("plan") == plan
            and proposal_result.get("status") == "confirmation_required"
            and proposal_result.get("changed") is False
            and event_proposal == proposal
            and applied_result.get("ok") is True
            and applied_result.get("status") == "applied"
            and applied_receipt == write_receipt
            and applied_task.get("task_id") == task_id
            and applied_task.get("status") == "completed"
            and applied_binding.get("next_step", {}).get("mode") == "complete"
            and replay_result.get("ok") is False
            and replay_result.get("status") != "applied"
            and undo_proposal_result.get("status") == "confirmation_required"
            and undo_action_id
            and undo_applied_result.get("ok") is True
            and undo_applied_result.get("status") == "applied"
            and event_undo_receipt == undo_receipt
            and write_receipt.get("action_id") == proposal_action_id
            and undo_receipt.get("action_id") == undo_action_id
            and "confirmation_token" not in serialized
            and "confirm_token" not in serialized
        )
        if not valid:
            raise ValueError("assistant lifecycle, restoration, replay, receipt, or redaction checks failed")
    except (OSError, json.JSONDecodeError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return _gate(
            "real_live_assistant", "Real-Live model-planned assistant lifecycle", "fail",
            ("qualified",), [path], f"Real-Live assistant evidence is invalid: {exc}",
        )
    return _gate(
        "real_live_assistant", "Real-Live model-planned assistant lifecycle", "pass",
        ("qualified",), [path],
        f"{data.get('planner_id')} completed a confirmed, verified, replay-protected assistant task and restored the exact initial Live snapshot.",
    )


def _soak_gate(path: Path) -> Gate:
    if not path.is_file():
        return _gate("companion_soak", "24-hour companion and Live reconnect soak", "pending", ("qualified",), [path], "A qualifying 24-hour reconnect-aware soak receipt is required.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        samples = data.get("samples", [])
        progress = data.get("progress") if isinstance(data.get("progress"), dict) else {}
        if progress.get("complete") is not True or progress.get("status") != "complete":
            raise ValueError("soak artifact is an incomplete checkpoint")
        if not isinstance(samples, list) or len(samples) != int(data.get("sample_count", 0)):
            raise ValueError("samples do not match sample_count")
        first_captured = datetime.fromisoformat(str(samples[0]["captured_at"]))
        last_captured = datetime.fromisoformat(str(samples[-1]["captured_at"]))
        captured = [datetime.fromisoformat(str(sample["captured_at"])) for sample in samples]
        elapsed_seconds = (last_captured - first_captured).total_seconds()
        interval = float(data.get("interval_seconds", 0))
        observed_seconds = interval * max(0, int(data.get("sample_count", 0)) - 1)
        summary = data.get("summary", {})
        thresholds = data.get("thresholds", {})
        runtime_state = summary.get("runtime_state", {})
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        runner_digest = hashlib.sha256((REPO_ROOT / "tooling" / "scripts" / "soak_companion.py").read_bytes()).hexdigest()
        expected_count = int(data.get("expected_sample_count", 0))
        statuses = [str(sample.get("ableton_status") or "unknown") for sample in samples]
        rss_values = [sample.get("rss_bytes") for sample in samples]
        thread_values = [sample.get("thread_count") for sample in samples]
        disconnects = sum(
            previous == "connected" and current != "connected"
            for previous, current in zip(statuses, statuses[1:])
        )
        reconnects = sum(
            previous != "connected" and current == "connected"
            for previous, current in zip(statuses, statuses[1:])
        )
        longest_outage_samples = 0
        current_outage_samples = 0
        for status in statuses:
            if status == "connected":
                current_outage_samples = 0
            else:
                current_outage_samples += 1
                longest_outage_samples = max(longest_outage_samples, current_outage_samples)
        computed_outage_seconds = longest_outage_samples * interval
        cadence_valid = interval > 0 and all(
            0 <= (right - left).total_seconds() <= interval * 2
            for left, right in zip(captured, captured[1:])
        ) and all(item.tzinfo is not None and item <= datetime.now(timezone.utc) for item in captured)
        samples_healthy = all(
            isinstance(sample, dict) and sample.get("health_ok") is True
            and not sample.get("error") and isinstance(sample.get("runtime_state"), dict)
            and type(sample.get("index")) is int
            and type(sample.get("rss_bytes")) is int and sample["rss_bytes"] >= 0
            and type(sample.get("thread_count")) is int and sample["thread_count"] > 0
            and isinstance(sample.get("latency_ms"), (int, float)) and sample["latency_ms"] >= 0
            and sample.get("ableton_status") in {"connected", "offline"}
            and all(
                isinstance(sample["runtime_state"].get(field), int)
                and isinstance(sample["runtime_state"].get(f"{field}_limit"), int)
                and sample["runtime_state"][field] <= sample["runtime_state"][f"{field}_limit"]
                for field in ("pending_proposals", "action_receipts", "mix_reviews")
            )
            for sample in samples
        )
        runtime_bounded = runtime_state.get("available_all_samples") is True and all(
            isinstance(runtime_state.get(field), dict)
            and isinstance(runtime_state[field].get("maximum"), int)
            and isinstance(runtime_state[field].get("limit"), int)
            and runtime_state[field]["maximum"] <= runtime_state[field]["limit"]
            for field in ("pending_proposals", "action_receipts", "mix_reviews")
        )
        max_rss_growth = int(thresholds.get("max_rss_growth_bytes", -1))
        max_thread_growth = int(thresholds.get("max_thread_growth", -1))
        max_outage = float(thresholds.get("max_ableton_outage_seconds", -1))
        valid = (
            data.get("schema") == "kenn.companion_soak.v1" and data.get("qualified") is True
            and data.get("source_git_commit") == head
            and data.get("runner_sha256") == runner_digest
            and data.get("endpoint") == "http://127.0.0.1:8090"
            and type(data.get("pid")) is int and data["pid"] > 0
            and expected_count == len(samples)
            and progress.get("completed_sample_count") == len(samples)
            and progress.get("expected_sample_count") == expected_count
            and [sample.get("index") for sample in samples] == list(range(len(samples)))
            and observed_seconds >= 86400
            and elapsed_seconds >= 86400
            and cadence_valid and samples_healthy
            and int(summary.get("error_samples", -1)) == 0
            and summary.get("rss_start_bytes") == rss_values[0]
            and summary.get("rss_end_bytes") == rss_values[-1]
            and summary.get("rss_growth_bytes") == rss_values[-1] - rss_values[0]
            and summary.get("rss_peak_bytes") == max(rss_values)
            and summary.get("rss_peak_growth_bytes") == max(rss_values) - rss_values[0]
            and summary.get("thread_start_count") == thread_values[0]
            and summary.get("thread_end_count") == thread_values[-1]
            and summary.get("max_thread_count") == max(thread_values)
            and summary.get("peak_thread_growth") == max(thread_values) - thread_values[0]
            and int(summary.get("rss_growth_bytes", max_rss_growth + 1)) <= max_rss_growth <= 128 * 1024 * 1024
            and int(summary.get("rss_peak_growth_bytes", max_rss_growth + 1)) <= max_rss_growth
            and 0 <= max_thread_growth <= 8
            and int(summary.get("peak_thread_growth", max_thread_growth + 1)) <= max_thread_growth
            and runtime_bounded
            and int(thresholds.get("min_ableton_reconnects", 0)) >= 1
            and summary.get("ableton_disconnect_events") == disconnects
            and summary.get("ableton_reconnect_events") == reconnects
            and reconnects >= int(thresholds["min_ableton_reconnects"])
            and max_outage >= 0
            and summary.get("longest_ableton_outage_seconds") == computed_outage_seconds
            and computed_outage_seconds <= max_outage
            and thresholds.get("require_ableton_connected_end") is True
            and summary.get("ableton_connected_at_end") is (statuses[-1] == "connected")
            and statuses[-1] == "connected"
        )
    except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return _gate("companion_soak", "24-hour companion and Live reconnect soak", "fail", ("qualified",), [path], f"Soak receipt is invalid: {exc}")
    details = (f"Observed {elapsed_seconds / 3600:.2f} healthy wall-clock hours with bounded state, a reconnect, and connected final state on the exact source and harness revision." if valid else "Soak receipt does not prove exact-source, healthy 24-hour cadence, bounded memory/state, required reconnect/outage policy, and connected final state.")
    return _gate("companion_soak", "24-hour companion and Live reconnect soak", "pass" if valid else "fail", ("qualified",), [path], details)


def _real_mix_gate(path: Path) -> Gate:
    if not path.is_file():
        return _gate("real_mix", "Consented real-mix usefulness evaluation", "pending", ("qualified",), [path], "A completed two-reviewer real-mix evaluation receipt is required.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        metrics = data.get("metrics", {})
        thresholds = data.get("thresholds", {})
        reviewer_count = int(metrics.get("reviewer_count", 0))
        case_reviews = int(metrics.get("case_reviews", 0))
        case_count = case_reviews // reviewer_count if reviewer_count > 0 and case_reviews % reviewer_count == 0 else 0
        engine_sha = hashlib.sha256((REPO_ROOT / "packages" / "mix-review" / "core" / "local_engine.py").read_bytes()).hexdigest()
        evaluator_sha = hashlib.sha256((REPO_ROOT / "tooling" / "scripts" / "evaluate_real_mix_corpus.py").read_bytes()).hexdigest()
        review_hashes = data.get("review_sha256") if isinstance(data.get("review_sha256"), list) else []
        packet_sha = str(data.get("packet_sha256") or "")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        valid = (
            data.get("schema") == "kenn.real_mix_evaluation.v1" and data.get("qualified") is True
            and data.get("source_git_commit") == head
            and len(packet_sha) == 64
            and all(character in "0123456789abcdef" for character in packet_sha)
            and data.get("engine_sha256") == engine_sha
            and data.get("evaluator_sha256") == evaluator_sha
            and len(review_hashes) == reviewer_count
            and len(set(review_hashes)) == reviewer_count
            and all(isinstance(item, str) and len(item) == 64 and all(
                character in "0123456789abcdef" for character in item
            ) for item in review_hashes)
            and thresholds.get("minimum_cases") is True
            and thresholds.get("required_category_coverage") is True
            and thresholds.get("engine_completion") is True
            and thresholds.get("two_independent_reviewers") is True
            and thresholds.get("evidence_correctness") is True
            and thresholds.get("usefulness") is True
            and thresholds.get("severity_order") is True
            and thresholds.get("abstention") is True
            and thresholds.get("false_positive_rate") is True
            and float(metrics.get("evidence_correct_rate", 0)) >= 0.90
            and float(metrics.get("useful_rate", 0)) >= 0.85
            and float(metrics.get("severity_order_correct_rate", 0)) >= 0.85
            and float(metrics.get("abstention_correct_rate", 0)) >= 0.85
            and case_reviews > 0
            and int(metrics.get("false_positive_count", case_reviews + 1)) / case_reviews <= 0.10
            and case_count >= 12
            and reviewer_count >= 2
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return _gate("real_mix", "Consented real-mix usefulness evaluation", "fail", ("qualified",), [path], f"Real-mix receipt is invalid: {exc}")
    details = f"Qualified {case_count} cases across {case_reviews} ratings from {reviewer_count} independent reviewers, bound to the current Mix Review engine." if valid else "Real-mix receipt does not prove current-engine identity, 12+ cases, two reviewers, and all quality thresholds."
    return _gate("real_mix", "Consented real-mix usefulness evaluation", "pass" if valid else "fail", ("qualified",), [path], details)


def _supervised_pilot_gate(path: Path, matrix_path: Path) -> Gate:
    if not path.is_file():
        return _gate("supervised_pilot", "Ten-session supervised pilot", "pending", ("qualified",), [path], "A qualifying 10-session, 3-project pilot receipt is required.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        metrics, thresholds = data.get("metrics", {}), data.get("thresholds", {})
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        matrix_sha = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
        run_ids = [str(row.get("run_id") or "") for row in rows if isinstance(row, dict)]
        project_buckets = [str(row.get("project_bucket") or "") for row in rows if isinstance(row, dict)]
        tester_buckets = [str(row.get("tester_bucket") or "") for row in rows if isinstance(row, dict)]
        receipt_buckets = [str(row.get("receipt_bucket") or "") for row in rows if isinstance(row, dict)]
        privacy = data.get("privacy") if isinstance(data.get("privacy"), dict) else {}
        bucket_values = [*project_buckets, *tester_buckets, *receipt_buckets]
        valid = (
            data.get("schema") == "kenn.supervised_pilot_evaluation.v1" and data.get("qualified") is True
            and data.get("source_git_commit") == head and data.get("support_matrix_sha256") == matrix_sha
            and data.get("evaluator_sha256") == hashlib.sha256(
                (REPO_ROOT / "tooling" / "scripts" / "evaluate_supervised_pilot.py").read_bytes()
            ).hexdigest()
            and int(metrics.get("session_count", 0)) >= 10 and int(metrics.get("project_count", 0)) >= 3
            and int(metrics.get("bound_receipt_count", 0)) == int(metrics.get("session_count", 0))
            and len(rows) == int(metrics.get("session_count", 0))
            and all(run_ids) and len(set(run_ids)) == len(rows)
            and len(bucket_values) == len(rows) * 3
            and all(re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in bucket_values)
            and int(metrics.get("project_count", 0)) == len(set(project_buckets))
            and int(metrics.get("tester_count", 0)) == len(set(tester_buckets))
            and int(metrics.get("bound_receipt_count", 0)) == len(set(receipt_buckets))
            and int(metrics.get("passed_session_count", 0)) == sum(row.get("passed") is True for row in rows)
            and all(isinstance(row, dict) and row.get("passed") is True and row.get("failures") == [] for row in rows)
            and privacy.get("stores_project_names") is False
            and privacy.get("stores_project_paths") is False
            and privacy.get("stores_raw_project_hashes") is False
            and privacy.get("stores_tester_identities") is False
            and privacy.get("stores_raw_tester_hashes") is False
            and privacy.get("release_scoped_buckets") is True
            and privacy.get("stores_evidence_paths") is False
            and privacy.get("stores_prompts") is False
            and privacy.get("stores_audio") is False
            and thresholds.get("minimum_sessions") is True and thresholds.get("minimum_projects") is True
            and thresholds.get("receipt_evidence_bound") is True
            and thresholds.get("all_sessions_pass") is True
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return _gate("supervised_pilot", "Ten-session supervised pilot", "fail", ("qualified",), [path], f"Pilot receipt is invalid: {exc}")
    details = f"{metrics.get('session_count')} safe signed-off sessions across {metrics.get('project_count')} hashed projects are bound to this source and support matrix." if valid else "Pilot receipt is stale or does not prove ten safe sessions across three projects."
    return _gate("supervised_pilot", "Ten-session supervised pilot", "pass" if valid else "fail", ("qualified",), [path], details)


def _release_provenance_gate(
    matrix_path: Path,
    plugin_archive: Path,
    *,
    index_root: Path = DEFAULT_INDEX_ROOT,
    model_root: Path = DEFAULT_EMBEDDING_MODEL_ROOT,
    qualification_artifacts: dict[str, Path | None] | None = None,
) -> tuple[Gate, dict[str, Any]]:
    if qualification_artifacts is None:
        qualification_artifacts = {
            "automated_suite": DEFAULT_AUTOMATED_SUITE_REPORT,
            "intelligence": DEFAULT_INTELLIGENCE_REPORT,
            "planner_bakeoff": DEFAULT_PLANNER_BAKEOFF,
            "real_live_assistant": DEFAULT_REAL_LIVE_ASSISTANT,
            "companion_soak": DEFAULT_SOAK_REPORT,
            "real_mix": DEFAULT_REAL_MIX_REPORT,
            "supervised_pilot": DEFAULT_PILOT_REPORT,
            "human_review_packet": DEFAULT_PACKET,
        }
    evidence: list[Path | str] = ["git HEAD", matrix_path, plugin_archive, index_root / "CURRENT"]
    evidence.extend(path for path in qualification_artifacts.values() if path is not None)
    provenance: dict[str, Any] = {"schema": "kenn.release_provenance.v1"}
    missing: list[str] = []
    failures: list[str] = []
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        if len(commit) != 40:
            raise ValueError("unexpected revision identity")
        provenance["source"] = {"git_commit": commit}
    except (OSError, subprocess.CalledProcessError, ValueError):
        missing.append("source revision")
    try:
        version_id = (index_root / "CURRENT").read_text(encoding="ascii").strip()
        version_dir = index_root / "versions" / version_id
        manifest_path = version_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest.get("artifacts", {})
        for name, metadata in artifacts.items():
            path = version_dir / str(name)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get("sha256"):
                failures.append(f"index artifact {name} hash mismatch")
        embedding = (manifest.get("build", {}).get("embedding_model", {}))
        model_path, tokenizer_path = model_root / "model.onnx", model_root / "tokenizer.json"
        model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
        tokenizer_sha = hashlib.sha256(tokenizer_path.read_bytes()).hexdigest()
        if model_sha != embedding.get("model_sha256") or tokenizer_sha != embedding.get("tokenizer_sha256"):
            failures.append("embedding model hash mismatch")
        if manifest.get("version_id") != version_id or not manifest.get("content_sha256"):
            failures.append("active index identity mismatch")
        provenance["knowledge"] = {
            "index_version": version_id,
            "content_sha256": manifest.get("content_sha256"),
            "chunk_count": manifest.get("chunk_count"),
            "embedding_model_id": embedding.get("id"),
            "embedding_model_sha256": model_sha,
            "tokenizer_sha256": tokenizer_sha,
        }
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        missing.append("validated active index/model")
    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        qualified = [row for row in matrix.get("supported_configurations", []) if isinstance(row, dict) and row.get("status") == "qualified"]
        if not qualified:
            raise ValueError("no qualified configuration")
        provenance["live"] = [{key: row.get(key) for key in ("id", "ableton_live", "os", "architecture", "bridge")} for row in qualified]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        missing.append("qualified Live/OS matrix")
    checksum_path = Path(str(plugin_archive) + ".sha256")
    if plugin_archive.is_file() and checksum_path.is_file():
        try:
            digest = hashlib.sha256(plugin_archive.read_bytes()).hexdigest()
            declared = checksum_path.read_text(encoding="utf-8").split()[0].lower()
            if digest != declared:
                failures.append("plugin archive checksum mismatch")
            provenance["plugin"] = {"archive_sha256": digest, "archive_name": plugin_archive.name}
        except (OSError, IndexError):
            failures.append("plugin archive identity unreadable")
    else:
        missing.append("plugin archive identity")
    qualification_identities: dict[str, dict[str, Any]] = {}
    for label, path in qualification_artifacts.items():
        if path is None or not path.is_file():
            missing.append(f"{label} evidence")
            continue
        try:
            qualification_identities[label] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
        except OSError:
            failures.append(f"{label} evidence identity unreadable")
    provenance["qualification_artifacts"] = qualification_identities
    provenance["answer_runtime"] = {
        "qualified_mode": "deterministic_retrieval",
        "llm_rewrite_enabled": os.environ.get("AUDIO_TOO_LLM_ENABLED", "0") == "1",
    }
    if provenance["answer_runtime"]["llm_rewrite_enabled"]:
        failures.append("LLM rewrite is enabled but not qualified by this release gate")
    status = "fail" if failures else "pending" if missing else "pass"
    details = "; ".join(failures or (["Missing " + ", ".join(missing)] if missing else ["Exact source, index/model, plug-in, and Live/OS identities are bound."]))
    return _gate("release_provenance", "Exact release provenance", status, ("qualified",), evidence, details), provenance


def _current_live_gate(check_live: bool) -> Gate:
    if not check_live:
        return _gate("current_live", "Current Ableton Live runtime", "not_run", (), ["python3 tooling/scripts/qualify_ableton_live.py --mode real --endpoint http://127.0.0.1:8090"], "Not requested; captured qualification evidence is evaluated separately.")
    command = [sys.executable, "tooling/scripts/qualify_ableton_live.py", "--mode", "real", "--endpoint", "http://127.0.0.1:8090"]
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=False)
        result = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return _gate("current_live", "Current Ableton Live runtime", "fail", ("pilot", "qualified"), ["python3 tooling/scripts/qualify_ableton_live.py --mode real --endpoint http://127.0.0.1:8090"], f"Current read-only probe could not be evaluated: {exc}")
    passed = result.get("status") == "passed" and result.get("evidence_kind") == "real_live" and result.get("checks", {}).get("connected") is True
    details = "Current AbletonOSC-backed KENN companion probe is connected and returned a usable real-Live snapshot." if passed else f"Current read-only probe is unavailable or blocked (status={result.get('status', 'unknown')}); do not start a pilot against this runtime."
    return _gate("current_live", "Current Ableton Live runtime", "pass" if passed else "fail", ("pilot", "qualified"), ["python3 tooling/scripts/qualify_ableton_live.py --mode real --endpoint http://127.0.0.1:8090"], details)


def build_report(*, profile: str, run_suite: bool = False, run_intelligence: bool = False, check_live: bool = False, real_report: Path = DEFAULT_REAL_REPORT, packet: Path = DEFAULT_PACKET, matrix: Path = DEFAULT_MATRIX, plugin_archive: Path = DEFAULT_PLUGIN_ARCHIVE, plugin_host_report: Path = DEFAULT_PLUGIN_HOST_REPORT, soak_report: Path = DEFAULT_SOAK_REPORT, real_mix_report: Path = DEFAULT_REAL_MIX_REPORT, pilot_report: Path = DEFAULT_PILOT_REPORT, planner_bakeoff: Path = DEFAULT_PLANNER_BAKEOFF, real_live_assistant: Path = DEFAULT_REAL_LIVE_ASSISTANT, automated_suite_report: Path = DEFAULT_AUTOMATED_SUITE_REPORT, intelligence_report: Path = DEFAULT_INTELLIGENCE_REPORT, reviewer_a: Path | None = None, reviewer_b: Path | None = None, adjudication: Path | None = None, output_path: Path | None = None) -> dict[str, Any]:
    provenance_gate, provenance = _release_provenance_gate(
        matrix, plugin_archive,
        qualification_artifacts={
            "automated_suite": automated_suite_report,
            "intelligence": intelligence_report,
            "planner_bakeoff": planner_bakeoff,
            "real_live_assistant": real_live_assistant,
            "companion_soak": soak_report,
            "real_mix": real_mix_report,
            "supervised_pilot": pilot_report,
            "human_review_packet": packet,
            "human_reviewer_a": reviewer_a,
            "human_reviewer_b": reviewer_b,
            "human_adjudication": adjudication,
            "real_live_baseline": real_report,
            "plugin_host_validation": plugin_host_report,
        },
    )
    gates = [
        _required_files_gate(),
        _real_live_gate(real_report),
        _support_matrix_gate(matrix, real_report),
        _human_review_gate(packet, reviewer_a, reviewer_b, adjudication),
        _source_gate(output_path),
        _plugin_distribution_gate(plugin_archive, plugin_host_report),
        _automated_gate(run_suite, automated_suite_report),
        _intelligence_gate(run_intelligence, intelligence_report),
        _planner_bakeoff_gate(planner_bakeoff),
        _real_live_assistant_gate(real_live_assistant, planner_bakeoff),
        _soak_gate(soak_report),
        _real_mix_gate(real_mix_report),
        _supervised_pilot_gate(pilot_report, matrix),
        provenance_gate,
        _current_live_gate(check_live),
    ]
    required = [gate for gate in gates if profile in gate.required_for]
    failed = [gate for gate in required if gate.status == "fail"]
    pending = [gate for gate in required if gate.status == "pending"]
    if failed or pending:
        decision = "not_ready"
    else:
        decision = "ready_for_supervised_internal_beta" if profile == "pilot" else "qualified_internal_beta"
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "decision": decision,
        "claims_boundary": "supervised disposable-set pilot only" if decision == "ready_for_supervised_internal_beta" else "no approval for autonomous, destructive, or public Ableton use",
        "provenance": provenance,
        "gates": [gate.as_dict() for gate in gates],
        "summary": {
            "required_gate_count": len(required),
            "passed": sum(gate.status == "pass" for gate in required),
            "pending": len(pending),
            "failed": len(failed),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("pilot", "qualified"), default="pilot")
    parser.add_argument("--run-suite", action="store_true", help="run pytest before evaluating the gate")
    parser.add_argument("--run-intelligence", action="store_true", help="run corpus-bound grounding and retrieval benchmarks")
    parser.add_argument("--check-live", action="store_true", help="require a fresh read-only probe from the current Ableton Live runtime")
    parser.add_argument("--real-report", type=Path, default=DEFAULT_REAL_REPORT)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--plugin-archive", type=Path, default=DEFAULT_PLUGIN_ARCHIVE)
    parser.add_argument("--plugin-host-report", type=Path, default=DEFAULT_PLUGIN_HOST_REPORT)
    parser.add_argument("--soak-report", type=Path, default=DEFAULT_SOAK_REPORT)
    parser.add_argument("--real-mix-report", type=Path, default=DEFAULT_REAL_MIX_REPORT)
    parser.add_argument("--pilot-report", type=Path, default=DEFAULT_PILOT_REPORT)
    parser.add_argument("--planner-bakeoff", type=Path, default=DEFAULT_PLANNER_BAKEOFF)
    parser.add_argument("--real-live-assistant", type=Path, default=DEFAULT_REAL_LIVE_ASSISTANT)
    parser.add_argument("--automated-suite-report", type=Path, default=DEFAULT_AUTOMATED_SUITE_REPORT)
    parser.add_argument("--intelligence-report", type=Path, default=DEFAULT_INTELLIGENCE_REPORT)
    parser.add_argument("--reviewer-a", type=Path)
    parser.add_argument("--reviewer-b", type=Path)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output_path = args.output.expanduser().resolve() if args.output else None
    result = build_report(
        profile=args.profile,
        run_suite=args.run_suite,
        run_intelligence=args.run_intelligence,
        check_live=args.check_live,
        real_report=args.real_report.expanduser().resolve(),
        packet=args.packet.expanduser().resolve(),
        matrix=args.matrix.expanduser().resolve(),
        plugin_archive=args.plugin_archive.expanduser().resolve(),
        plugin_host_report=args.plugin_host_report.expanduser().resolve(),
        soak_report=args.soak_report.expanduser().resolve(),
        real_mix_report=args.real_mix_report.expanduser().resolve(),
        pilot_report=args.pilot_report.expanduser().resolve(),
        planner_bakeoff=args.planner_bakeoff.expanduser().resolve(),
        real_live_assistant=args.real_live_assistant.expanduser().resolve(),
        automated_suite_report=args.automated_suite_report.expanduser().resolve(),
        intelligence_report=args.intelligence_report.expanduser().resolve(),
        reviewer_a=args.reviewer_a.expanduser().resolve() if args.reviewer_a else None,
        reviewer_b=args.reviewer_b.expanduser().resolve() if args.reviewer_b else None,
        adjudication=args.adjudication.expanduser().resolve() if args.adjudication else None,
        output_path=output_path,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output_path:
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["decision"] in {"ready_for_supervised_internal_beta", "qualified_internal_beta"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
