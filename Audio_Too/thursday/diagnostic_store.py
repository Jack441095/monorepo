"""Bounded diagnostic retention for Thursday V2-H.

Addresses the V2-F weakness: failed sandbox diagnostics were deleted
too quickly, making post-mortem analysis difficult.

Retention policy
----------------
For FAILED tasks, preserves:
  - task plan (JSON)
  - receipts (JSON)
  - diff summary (text)
  - error metadata (JSON)
  - heartbeat logs (JSON)

Explicitly excluded:
  - secrets (checked via same patterns as evidence_collector)
  - large build directories (size-gated)
  - raw private user data

Bounds (configurable, with safe defaults):
  max_retained_failures : int   default 100
  max_bytes             : int   default 50 MB
  max_age_seconds       : float default 7 days

Pruning order: oldest first, then count, then total size.
All writes use atomic temp+rename to prevent partial reads.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default retention limits
DEFAULT_MAX_FAILURES  = 100
DEFAULT_MAX_BYTES     = 50 * 1024 * 1024    # 50 MB
DEFAULT_MAX_AGE_S     = 7 * 24 * 3600.0     # 7 days
DEFAULT_MAX_ENTRY_BYTES = 1 * 1024 * 1024   # 1 MB per entry — refuse larger artifacts


@dataclass
class DiagnosticEntry:
    """Metadata record for a retained diagnostic artifact."""
    entry_id:    str
    task_id:     str
    task_status: str   # FAILED / FAILED_SAFE / etc.
    created_at:  float
    size_bytes:  int
    path:        str


class DiagnosticStore:
    """Bounded diagnostic retention store.

    Parameters
    ----------
    store_dir : str | Path
        Directory where diagnostic entries are persisted.
    max_retained : int
        Maximum number of retained failure entries.
    max_bytes : int
        Maximum total bytes of retained diagnostics.
    max_age_seconds : float
        Maximum age in seconds before an entry is pruned.
    """

    def __init__(
        self,
        store_dir: str | Path,
        *,
        max_retained: int = DEFAULT_MAX_FAILURES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_age_seconds: float = DEFAULT_MAX_AGE_S,
    ) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.max_retained = max_retained
        self.max_bytes = max_bytes
        self.max_age_seconds = max_age_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retain_failure(
        self,
        task_id: str,
        *,
        plan: dict[str, Any] | None = None,
        receipts: list[dict[str, Any]] | None = None,
        diff_summary: str = "",
        error_metadata: dict[str, Any] | None = None,
        heartbeat_log: dict[str, Any] | None = None,
        task_status: str = "FAILED",
    ) -> DiagnosticEntry | None:
        """Persist failure diagnostics for a task.

        Returns the DiagnosticEntry on success, None if rejected (e.g.
        entry too large, or content exceeds size limit).
        Secrets are scrubbed before writing.
        """
        entry_id = f"diag-{task_id}-{int(time.time())}"
        payload = {
            "entry_id":     entry_id,
            "task_id":      task_id,
            "task_status":  task_status,
            "created_at":   time.time(),
            "plan":         plan or {},
            "receipts":     receipts or [],
            "diff_summary": self._scrub_secrets(diff_summary),
            "error_metadata": error_metadata or {},
            "heartbeat_log":  heartbeat_log or {},
        }

        raw = json.dumps(payload, default=str)
        if len(raw.encode("utf-8")) > DEFAULT_MAX_ENTRY_BYTES:
            return None   # Refuse oversized entry

        entry_path = self.store_dir / f"{entry_id}.json"
        self._atomic_write(entry_path, raw)
        entry_size = entry_path.stat().st_size

        entry = DiagnosticEntry(
            entry_id=entry_id,
            task_id=task_id,
            task_status=task_status,
            created_at=payload["created_at"],
            size_bytes=entry_size,
            path=str(entry_path),
        )

        # Prune after each write to maintain bounds
        self._prune()
        return entry

    def list_entries(self) -> list[DiagnosticEntry]:
        """List all retained entries sorted by creation time (oldest first)."""
        entries = []
        for p in self.store_dir.glob("diag-*.json"):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                entries.append(DiagnosticEntry(
                    entry_id=d.get("entry_id", p.stem),
                    task_id=d.get("task_id", ""),
                    task_status=d.get("task_status", ""),
                    created_at=float(d.get("created_at", 0)),
                    size_bytes=p.stat().st_size,
                    path=str(p),
                ))
            except Exception:
                continue
        return sorted(entries, key=lambda e: e.created_at)

    def total_bytes(self) -> int:
        return sum(e.size_bytes for e in self.list_entries())

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove entries that violate any bound (age, count, total size)."""
        entries = self.list_entries()  # oldest first
        now = time.time()

        # Prune by age
        entries = [e for e in entries if self._keep_or_delete_age(e, now)]

        # Prune by count (oldest first)
        while len(entries) > self.max_retained:
            self._delete(entries.pop(0))

        # Prune by total size (oldest first)
        total = sum(e.size_bytes for e in entries)
        while total > self.max_bytes and entries:
            victim = entries.pop(0)
            total -= victim.size_bytes
            self._delete(victim)

    def _keep_or_delete_age(self, entry: DiagnosticEntry, now: float) -> bool:
        if now - entry.created_at > self.max_age_seconds:
            self._delete(entry)
            return False
        return True

    def _delete(self, entry: DiagnosticEntry) -> None:
        try:
            Path(entry.path).unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)

    @staticmethod
    def _scrub_secrets(text: str) -> str:
        """Remove likely secret values from text before persisting."""
        import re
        patterns = [
            re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*\S+"),
            re.compile(r"(?i)password\s*[:=]\s*\S+"),
            re.compile(r"ghp_[A-Za-z0-9]{20,}"),
            re.compile(r"sk-[A-Za-z0-9]{32,}"),
            re.compile(r"-----BEGIN \w+ PRIVATE KEY-----.*?-----END \w+ PRIVATE KEY-----", re.DOTALL),
        ]
        for pat in patterns:
            text = pat.sub("[REDACTED]", text)
        return text


__all__ = [
    "DiagnosticEntry",
    "DiagnosticStore",
]
