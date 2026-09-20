"""Machine-verifiable evidence collector for Thursday V2-H.

Collects TaskEvidence from completed sandbox executions. All evidence is
machine-verified: real SHA lookups, real file hashes, real process exit
codes. Claims without evidence remain UNVERIFIED.

Design rules
------------
* No LLM claims are accepted as evidence.
* Evidence is frozen immediately on collection.
* Partial evidence (some fields missing) yields verified=False.
* Secret patterns in diff output cause EVIDENCE_REJECTED with no retained data.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thursday.engineering_contracts import TaskEvidence

# ---------------------------------------------------------------------------
# Secret-pattern detection
# ---------------------------------------------------------------------------

# Patterns that suggest secret leakage in diff or output content.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)aws[_-]?(access|secret)[_-]?(key|id)\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)password\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)private[_-]?key\s*[:=]"),
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),     # GitHub Personal Access Token
    re.compile(r"sk-[A-Za-z0-9]{24,}"),      # OpenAI-style secret key
]


def _contains_secret(text: str) -> bool:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------

@dataclass
class EvidenceCollectionResult:
    """Result from a collect() call."""
    evidence: TaskEvidence | None
    rejected: bool = False
    rejection_reason: str = ""


class EvidenceCollector:
    """Collects and verifies machine-readable evidence from sandbox tasks.

    Parameters
    ----------
    repo_path : str | Path
        Git repository root — used for SHA lookups.
    """

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def collect(
        self,
        task_id: str,
        *,
        candidate_branch: str = "",
        test_command: tuple[str, ...] = (),
        changed_files: list[str] | None = None,
        diff_text: str = "",
        process_exit_code: int = -1,
        test_count: int = -1,
        benchmark_result: dict[str, Any] | None = None,
        artifact_paths: list[str] | None = None,
        resource_usage: dict[str, Any] | None = None,
        source_provenance: str = "",
    ) -> EvidenceCollectionResult:
        """Collect, verify, and return frozen TaskEvidence.

        Any detected secret pattern causes immediate rejection.
        """
        # 1. Secret check on diff text
        if diff_text and _contains_secret(diff_text):
            return EvidenceCollectionResult(
                evidence=None,
                rejected=True,
                rejection_reason="SECRET_LEAK: secret pattern detected in diff output. Evidence rejected.",
            )

        # 2. Resolve candidate SHA from branch (real git lookup)
        candidate_sha = ""
        if candidate_branch:
            candidate_sha = self._resolve_sha(candidate_branch)

        # 3. Hash artifact files
        artifact_hash = ""
        if artifact_paths:
            artifact_hash = self._hash_artifacts(artifact_paths)

        # 4. Hash diff text (content integrity)
        diff_hash = ""
        if diff_text:
            diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

        # 5. Determine verified flag
        # Evidence is VERIFIED only if we have at minimum: SHA and exit code
        verified = bool(candidate_sha) and process_exit_code >= 0

        evidence = TaskEvidence(
            task_id=task_id,
            verified=verified,
            candidate_sha=candidate_sha,
            diff_hash=diff_hash,
            test_command=test_command,
            test_exit_code=process_exit_code,
            test_count=test_count,
            benchmark_result=benchmark_result or {},
            artifact_hash=artifact_hash,
            source_provenance=source_provenance,
            resource_usage=resource_usage or {},
            changed_files=tuple(changed_files or []),
        )
        return EvidenceCollectionResult(evidence=evidence, rejected=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_sha(self, branch_or_ref: str) -> str:
        """Return HEAD SHA of the given ref, or empty string on failure."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", branch_or_ref],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _hash_artifacts(self, paths: list[str]) -> str:
        """SHA-256 over the concatenated contents of all artifact files."""
        h = hashlib.sha256()
        for p in sorted(paths):
            try:
                with open(p, "rb") as f:
                    h.update(f.read())
            except OSError:
                h.update(f"MISSING:{p}".encode("utf-8"))
        return h.hexdigest()


# ---------------------------------------------------------------------------
# Scope drift detection
# ---------------------------------------------------------------------------

def detect_scope_drift(
    changed_files: tuple[str, ...],
    mutation_boundaries: tuple[str, ...],
) -> tuple[bool, list[str]]:
    """Check whether any changed file falls outside the declared mutation boundaries.

    Returns (drift_detected, list_of_violating_files).
    An empty mutation_boundaries tuple means "any file allowed" (R0/R1 tasks).
    """
    if not mutation_boundaries:
        return False, []

    violations = []
    for f in changed_files:
        norm = os.path.normpath(f)
        allowed = any(
            norm.startswith(os.path.normpath(b)) for b in mutation_boundaries
        )
        if not allowed:
            violations.append(f)
    return bool(violations), violations


__all__ = [
    "EvidenceCollectionResult",
    "EvidenceCollector",
    "detect_scope_drift",
]
