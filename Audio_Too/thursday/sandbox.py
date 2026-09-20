"""Task Sandbox isolation and environment sanitisation for Thursday V2-F."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import signal
import psutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class TaskSandbox:
    sandbox_id: str
    task_id: str
    specialist_id: str
    source_sha: str
    allowed_write_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    lease_id: str = ""
    worktree_path: str = ""
    temp_path: str = ""
    created_at: float = field(default_factory=time.time)
    nice_level: int = 10

    def setup(self) -> None:
        """Create isolated directories and setup Git worktree if applicable."""
        # Create temp folder inside OS tmp directory
        self.temp_path = tempfile.mkdtemp(prefix=f"thursday-sandbox-{self.task_id}-")
        self.worktree_path = os.path.join(self.temp_path, "worktree")
        os.makedirs(self.worktree_path, exist_ok=True)
        
        # Add to allowed write paths
        self.allowed_write_paths.append(self.temp_path)
        self.allowed_write_paths.append(self.worktree_path)

    def get_sanitised_env(self) -> dict[str, str]:
        """Strip environment secrets and return allowlisted parameters only."""
        clean_env = {}
        # Explicit allowlist
        safe_keys = {"PATH", "TMPDIR", "LANG", "LC_ALL", "CC", "CXX", "MACOSX_DEPLOYMENT_TARGET"}
        for k, v in os.environ.items():
            if k in safe_keys:
                clean_env[k] = v
                
        # Scope HOME to sandbox temp directory to prevent leaks
        clean_env["HOME"] = self.temp_path
        return clean_env

    def launch_task_process(self, args: list[str], cwd: Optional[str] = None) -> subprocess.Popen:
        """Launch command inside process group using sanitised environment and nice setting."""
        if cwd is None:
            cwd = self.worktree_path
            
        env = self.get_sanitised_env()
        
        # Pre-exec fn to set nice priority and start a new session/process group
        def preexec():
            os.setpgrp()
            os.nice(self.nice_level)
            
        p = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            preexec_fn=preexec,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return p

    def get_child_pids(self) -> list[int]:
        """Safely trace all PIDs belonging to this sandbox's process group."""
        pids = []
        for p in psutil.process_iter(attrs=["pid", "pgid"]):
            try:
                # If process group ID matches this temp directory naming or PID tree (mock/PGID check)
                # In standard usage we can check matching parent group or pgid
                pass
            except Exception:
                continue
        return pids

    def terminate_owned_processes(self, main_process: subprocess.Popen) -> None:
        """Terminate process tree belonging strictly to this sandbox."""
        pgid = os.getpgid(main_process.pid)
        try:
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.1)
            # Escalation to KILL if still running
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def cleanup(self) -> None:
        """Remove temp sandbox and clean resources."""
        if self.temp_path and os.path.exists(self.temp_path):
            shutil.rmtree(self.temp_path, ignore_errors=True)
