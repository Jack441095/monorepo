"""Product-owned, local-only boundary around Audio_Too's AutoMix pipeline.

This module is intentionally not a web route. It provides a narrow contract
for an explicitly human-approved local render while keeping the implementation
in the read-only Audio_Too repository.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

SERVICE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_ROOT.parents[2]
AUDIO_TOO_ROOT = Path(
    os.environ.get("KENN_AUDIO_TOO_ROOT", str(REPO_ROOT / "Audio_Too"))
).expanduser().resolve()
RUNTIME_ROOT = Path(
    os.environ.get("KENN_AUTOMIX_RUNTIME_DIR", str(SERVICE_ROOT / ".runtime"))
).expanduser().resolve()

SCHEMA = "kenn.automix.local_receipt.v1"
AUDIO_SUFFIXES = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}
_SAFE_PROJECT_ID = re.compile(r"[^A-Za-z0-9._-]+")
_ENGINE_RUNNER: Callable[..., dict] | None = None


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _safe_project_id(project_id: str) -> str:
    value = _SAFE_PROJECT_ID.sub("-", str(project_id)).strip("-.")
    return value[:80] or "local-mix"


def _find_stems(stems_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(stems_dir.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in AUDIO_SUFFIXES
        and not path.name.startswith(".")
        and not path.name.startswith("._")
    ]


def _load_engine_runner() -> Callable[..., dict]:
    global _ENGINE_RUNNER
    if _ENGINE_RUNNER is not None:
        return _ENGINE_RUNNER

    script_path = AUDIO_TOO_ROOT / "scripts" / "automix_local.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"AutoMix engine entry point not found: {script_path}")

    os.environ.setdefault("AUDIO_TOO_LLM_ENABLED", "0")
    sys.path.insert(0, str(AUDIO_TOO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("kenn_audio_too_automix_local", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load AutoMix engine entry point: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ENGINE_RUNNER = module.run_local_automix
    return _ENGINE_RUNNER


def _base_receipt(
    *,
    status: str,
    stems_dir: Path,
    project_id: str,
    approved: bool,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "project_id": project_id,
        "engine": "Audio_Too/scripts/automix_local.py::run_local_automix",
        "audio_uploaded": False,
        "external_network": False,
        "storage": "local_output_only",
        "human_approval": approved,
        "stems_dir": str(stems_dir),
        "output_dir": None,
        "source": {"files": [], "sha256": {}},
    }


def _delivery_summary(delivery: dict[str, Any]) -> dict[str, Any]:
    """Keep the receipt to delivery metadata, never audio or report contents."""
    allowed = {
        "ok",
        "project_id",
        "version",
        "zip_path",
        "wav_path",
        "manifest_path",
        "report_path",
        "delivery_dir",
        "spectrum_comparison_path",
    }
    return {key: delivery[key] for key in allowed if key in delivery}


def run_approved_local_automix(
    stems_dir: Path,
    *,
    approved: bool = False,
    genre: str = "pop",
    target_lufs: float | None = None,
    project_id: str = "local-mix",
    output_dir: Path | None = None,
    apply_masking: bool = False,
    apply_mono_compat_correction: bool = False,
    apply_proactive_crest_reduction: bool = False,
    bass_boost_db: float = 0.0,
) -> dict[str, Any]:
    """Run the existing local AutoMix pipeline behind an approval gate.

    The adapter intentionally exposes only conservative, already-supported
    controls. Reference matching, stem export, correction payloads, and other
    higher-risk options remain available only through the underlying local
    engineering CLI until separately reviewed.
    """
    source_dir = Path(stems_dir).expanduser().resolve()
    safe_id = _safe_project_id(project_id)
    receipt = _base_receipt(
        status="rejected", stems_dir=source_dir, project_id=safe_id, approved=approved
    )

    if not source_dir.is_dir():
        receipt["error"] = f"stems directory not found: {source_dir}"
        return receipt

    stem_paths = _find_stems(source_dir)
    if not stem_paths:
        receipt["error"] = f"no audio stems found in {source_dir}"
        return receipt

    receipt["source"] = {
        "files": [path.name for path in stem_paths],
        "sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in stem_paths
        },
    }

    if not approved:
        receipt["status"] = "awaiting_human_approval"
        receipt["error"] = "explicit approved=True is required before a local render"
        return receipt

    destination = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else (RUNTIME_ROOT / "outputs" / safe_id).resolve()
    )
    if _inside(destination, AUDIO_TOO_ROOT):
        receipt["error"] = "output_dir must be outside the read-only Audio_Too checkout"
        return receipt
    if _inside(destination, source_dir):
        receipt["error"] = "output_dir must not be inside the source stems directory"
        return receipt

    receipt["output_dir"] = str(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        delivery = _load_engine_runner()(
            source_dir,
            genre=genre,
            target_lufs=target_lufs,
            output_dir=destination,
            project_id=safe_id,
            apply_masking=apply_masking,
            apply_mono_compat_correction=apply_mono_compat_correction,
            apply_proactive_crest_reduction=apply_proactive_crest_reduction,
            bass_boost_db=bass_boost_db,
        )
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = str(exc)
        return receipt

    receipt["status"] = "completed"
    receipt["delivery"] = _delivery_summary(delivery)
    return receipt
