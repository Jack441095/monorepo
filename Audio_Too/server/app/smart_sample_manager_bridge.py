"""Bounded bridge for the Smart Sample Manager JUCE plugin.

Unlike AudioGen or KENN, this has no HTTP server or CLI entry point at all —
it's a VST3/AU plugin that runs inside a DAW's process. "Status" here just
means "is it built and installed where a DAW would find it", which is the
closest analogue to AudioGen's filesystem-based readiness check.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
SSM_ROOT = REPO_ROOT / "studio" / "vst3_plugins" / "SmartSampleManager"

INSTALLED_VST3 = Path.home() / "Library" / "Audio" / "Plug-Ins" / "VST3" / "Smart Sample Manager.vst3"
INSTALLED_AU = Path.home() / "Library" / "Audio" / "Plug-Ins" / "Components" / "Smart Sample Manager.component"


def status() -> dict:
    installed = INSTALLED_VST3.exists() or INSTALLED_AU.exists()
    return {
        "ok": installed,
        "root": str(SSM_ROOT),
        "has_source": SSM_ROOT.exists() and (SSM_ROOT / "CMakeLists.txt").exists(),
        "installed_vst3": INSTALLED_VST3.exists(),
        "installed_au": INSTALLED_AU.exists(),
    }
