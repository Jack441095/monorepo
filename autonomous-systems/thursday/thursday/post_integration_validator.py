"""Post-integration validator for Thursday V2-H.

Runs independently of pre-integration QA. Does NOT reuse pre-integration
test state. Verifies the actual integrated branch state is as expected.

A failed post-integration QA triggers V2-G rollback via SharedExecutor
semantics, completing in FAILED_SAFE state.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PostQAStatus(str, Enum):
    PASS        = "PASS"
    FAIL        = "FAIL"
    ERROR       = "ERROR"    # Could not run validation


@dataclass
class PostIntegrationResult:
    status:           PostQAStatus
    target_sha:       str = ""
    actual_sha:       str = ""
    sha_match:        bool = False
    test_exit_code:   int = -1
    test_stdout:      str = ""
    test_stderr:      str = ""
    worktree_clean:   bool = False
    findings:         list[str] = field(default_factory=list)
    elapsed_seconds:  float = 0.0

    @property
    def integration_confirmed(self) -> bool:
        return (
            self.status == PostQAStatus.PASS
            and self.sha_match
            and self.worktree_clean
        )


class PostIntegrationValidator:
    """Post-integration validation — runs fresh after V2-G SharedExecutor.

    Parameters
    ----------
    repo_path : str | Path
        Git repository root.
    """

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def validate(
        self,
        *,
        expected_sha: str,
        target_branch: str,
        post_test_cmd: tuple[str, ...] = (),
        timeout: float = 120.0,
    ) -> PostIntegrationResult:
        """Validate the post-integration state of target_branch.

        Checks:
          1. Actual HEAD SHA matches expected_sha (expected commit landed)
          2. Working tree is clean (no untracked/dirty files)
          3. Test suite passes (if post_test_cmd provided)
        """
        start = time.monotonic()
        findings: list[str] = []

        # ---- Step 1: Resolve actual HEAD SHA ----
        actual_sha = self._resolve_sha(target_branch)
        sha_match = bool(actual_sha) and actual_sha == expected_sha
        if not sha_match:
            findings.append(
                f"SHA mismatch after integration: expected {expected_sha[:12]}…, "
                f"actual {actual_sha[:12] if actual_sha else '<unresolvable>'}…"
            )

        # ---- Step 2: Worktree cleanliness ----
        worktree_clean = self._is_worktree_clean()
        if not worktree_clean:
            findings.append("Working tree is dirty after integration — unexpected untracked or modified files.")

        # ---- Step 3: Run post-integration test suite (fresh process) ----
        test_exit_code = -1
        test_stdout = ""
        test_stderr = ""
        if post_test_cmd:
            test_exit_code, test_stdout, test_stderr = self._run_cmd(
                list(post_test_cmd), timeout=timeout
            )
            if test_exit_code != 0:
                findings.append(
                    f"Post-integration test suite failed (exit {test_exit_code}). "
                    f"stderr: {test_stderr[-512:]!r}"
                )

        # ---- Determine status ----
        if not sha_match:
            status = PostQAStatus.FAIL
        elif post_test_cmd and test_exit_code != 0:
            status = PostQAStatus.FAIL
        elif not worktree_clean:
            # Non-clean worktree is a warning but not necessarily a hard fail
            findings.append("WARNING: Worktree is not clean post-integration.")
            status = PostQAStatus.PASS
        else:
            status = PostQAStatus.PASS

        return PostIntegrationResult(
            status=status,
            target_sha=expected_sha,
            actual_sha=actual_sha,
            sha_match=sha_match,
            test_exit_code=test_exit_code,
            test_stdout=test_stdout[-2048:],
            test_stderr=test_stderr[-2048:],
            worktree_clean=worktree_clean,
            findings=findings,
            elapsed_seconds=time.monotonic() - start,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_sha(self, branch: str) -> str:
        result = subprocess.run(
            ["git", "rev-parse", f"refs/heads/{branch}"],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""

    def _is_worktree_clean(self) -> bool:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        return result.stdout.strip() == ""

    def _run_cmd(self, cmd: list[str], timeout: float) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout}s"
        except Exception as exc:
            return -2, "", str(exc)


__all__ = [
    "PostQAStatus",
    "PostIntegrationResult",
    "PostIntegrationValidator",
]
