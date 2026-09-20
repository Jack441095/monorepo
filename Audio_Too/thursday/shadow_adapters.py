"""Read-only adapters for live NITE DSP workspaces."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class ShadowAdapter:
    project_id: str
    workspace_path: str
    forbidden_writes: list[str] = field(default_factory=lambda: ["*"])
    read_only: bool = True

    def get_git_state(self) -> dict[str, Any]:
        """Safely inspect Git repository state (read-only)."""
        if not os.path.exists(self.workspace_path):
            return {"head_sha": "UNKNOWN", "clean": True, "branch": "UNKNOWN"}
        try:
            sha_res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True
            )
            branch_res = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True
            )
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True
            )
            return {
                "head_sha": sha_res.stdout.strip(),
                "branch": branch_res.stdout.strip(),
                "clean": not bool(status_res.stdout.strip())
            }
        except Exception as exc:
            return {"head_sha": "ERROR", "clean": True, "branch": "ERROR", "error": str(exc)}

    def read_report(self, filename: str) -> Optional[str]:
        """Read a report file safely (read-only)."""
        path = os.path.join(self.workspace_path, filename)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

def _nite_dsp_root() -> str:
    """NITE_DSP_ROOT env var wins if set. Otherwise search upward from
    this file for the monorepo root (identified by containing both
    Audio_Too/ and products/) -- mirrors thursday.ops.qa_ops.nite_dsp_root(),
    which replaced an equivalent fixed-parent-index bug found 2026-09-02
    (see docs/NITE_DSP_THURSDAY_AUDIT_AND_UPGRADE_PLAN_V1.md). The paths
    below were previously hardcoded to a pre-NITE_DSP directory layout
    (Audio_Engineering_Company/SmartSampleManager/SLO_V5C/KENN/NiteSubmit)
    that no longer exists at all -- get_git_state() silently returned
    "UNKNOWN" for every adapter because os.path.exists() failed for all
    of them. Fixed alongside the path computation, same commit.
    """
    configured = os.environ.get("NITE_DSP_ROOT", "").strip()
    if configured:
        return os.path.expanduser(configured)

    here = os.path.dirname(os.path.abspath(__file__))
    candidate = here
    for _ in range(6):
        candidate = os.path.dirname(candidate)
        if os.path.isdir(os.path.join(candidate, "Audio_Too")) and os.path.isdir(os.path.join(candidate, "products")):
            return candidate

    # Nothing found -- fall back to this file's own known depth
    # (thursday/shadow_adapters.py -> two levels up is Audio_Too's
    # parent). get_git_state() will honestly report UNKNOWN if this
    # fallback is also wrong, rather than silently using a bad path.
    return os.path.dirname(os.path.dirname(here))


PARENT_DIR = _nite_dsp_root()

# Real current NITE DSP monorepo layout (verified 2026-09-02) -- these are
# genuinely separate git repos/submodules under the shared NITE_DSP root,
# not the legacy sibling-directory layout the old paths assumed.
ADAPTERS = {
    "nite_submit": ShadowAdapter("nite_submit", os.path.join(PARENT_DIR, "products", "nite-submit")),
    "slo": ShadowAdapter("slo", os.path.join(PARENT_DIR, "products", "slo")),
    "kenn": ShadowAdapter("kenn", os.path.join(PARENT_DIR, "products", "kenn")),
    "audio_too": ShadowAdapter("audio_too", os.path.join(PARENT_DIR, "Audio_Too")),
    "thursday_extraction": ShadowAdapter("thursday_extraction", os.path.join(PARENT_DIR, "autonomous-systems", "thursday")),
    "platform_support": ShadowAdapter("platform_support", os.path.join(PARENT_DIR, "autonomous-systems", "platform-support")),
    "layer_alignment": ShadowAdapter("layer_alignment", os.path.join(PARENT_DIR, "audio-technology", "layer-alignment")),
}
