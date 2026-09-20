"""Build and verify a relocatable Audio_Too release candidate archive."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "audio_too.release_package.v1"
MANIFEST_NAME = "release-manifest.json"

# Stage O1 -- the sellable, customer-facing product: KENN's own chat server
# plus the local/CLI AutoMix and AudioGen DSP libraries. No Thursday, no
# business/CRM/invoicing data, no web upload/job-queue UI (see
# scripts/automix_local.py). Verified 2026-07-12 by actually booting
# kenn/server.py (chat + AudioGen bridge) with nothing else present --
# every entry below was found necessary by a real import error, not
# guessed from reading source.
KENN_PRODUCT_SCHEMA = "audio_too.kenn_product_package.v1"
# The customer bundle deliberately remains bounded.  The live plug-in and
# The reviewed product manifest is now 1,016 files after
# studio/kenn/kenn/core/{agent_contracts,diagnostic_framework,diagnostic_state,
# evidence}.py (typed diagnostic-agent contracts, P1 roadmap work) were
# added under the already-wholesale-included "studio/kenn/kenn/core" root.
# Retain a deliberately small two-file maintenance margin so the packaging
# gate still catches accidental dependency creep instead of silently
# dropping features.
KENN_PRODUCT_MAX_FILES = 1_018
KENN_PRODUCT_MAX_BYTES = 250_000_000
KENN_PRODUCT_RELEASE_ROOTS = (
    "main.py",
    "README.md",
    "KENN_PRODUCT_README.md",
    "THIRD_PARTY_NOTICES.md",
    "LICENSE",
    ".python-version",
    "pyproject.toml",
    "requirements.txt",
    "audio_too",
    "scripts",
    "studio/audio_analysis/audio_analysis",
    # Granular, not a wholesale "studio/audiogen/audiogen" -- that directory
    # also contains ~430MB of Jack's personal training_data/ and samples/,
    # plus a build egg-info dir and reproduce.py (hardcodes a personal
    # absolute macOS volume path). Kept in exact sync with RELEASE_ROOTS' own
    # audiogen entries below so the product package never ships more than
    # Jack's own internal bundle does. Verified 2026-07-12.
    "studio/audiogen/audiogen/ai",
    "studio/audiogen/audiogen/audio",
    "studio/audiogen/audiogen/composition",
    "studio/audiogen/audiogen/core",
    "studio/audiogen/audiogen/data",
    "studio/audiogen/audiogen/docs",
    "studio/audiogen/audiogen/midi",
    "studio/audiogen/audiogen/presets",
    "studio/audiogen/audiogen/runner",
    "studio/audiogen/audiogen/sampler",
    "studio/audiogen/audiogen/scripts",
    "studio/audiogen/audiogen/tools",
    "studio/audiogen/audiogen/training",
    "studio/audiogen/audiogen/utils",
    "studio/audiogen/audiogen/app_controller.py",
    "studio/audiogen/audiogen/gui_scene_adapter.py",
    "studio/audiogen/audiogen/main.py",
    "studio/audiogen/audiogen/main_llm.py",
    "studio/audiogen/audiogen/main_llm_chorus_only.py",
    "studio/audiogen/audiogen/main_render_full_song.py",
    "studio/audiogen/audiogen/pyproject.toml",
    "studio/agents/MixReview",
    "studio/kenn/kenn/README.md",
    "studio/kenn/kenn/TESTER_DEMO.md",
    "studio/kenn/kenn/__init__.py",
    # Five top-level kenn/ modules missing until found live 2026-08-05 by
    # actually booting the packaged server: kenn/core/chat_answer.py
    # imports orchestrator.py unconditionally at module load, so its
    # absence crashed the packaged server on startup outright. The other
    # four are lazily imported inside request handlers/startup hooks (most
    # guarded by try/except) so they wouldn't crash boot, but would either
    # silently degrade (mixing_doctor) or 500 at runtime the moment a
    # customer actually hit that feature (ableton_osc_bridge,
    # audio_dev_agent, autonomous_agent) -- same class of bug as
    # orchestrator.py, just not loud enough to fail this test until now.
    "studio/kenn/kenn/ableton_osc_bridge.py",
    "studio/kenn/kenn/audio_dev_agent.py",
    "studio/kenn/kenn/autonomous_agent.py",
    "studio/kenn/kenn/mixing_doctor.py",
    "studio/kenn/kenn/orchestrator.py",
    "studio/kenn/kenn/plugin_handoff.py",
    "studio/kenn/kenn/plugin_actions.py",
    "studio/kenn/kenn/project_analysis.py",
    "studio/kenn/kenn/adaptive",
    "studio/kenn/kenn/core",
    "studio/kenn/kenn/evals",
    "studio/kenn/kenn/finetune",
    "studio/kenn/kenn/knowledge",
    "studio/kenn/kenn/llm",
    "studio/kenn/kenn/m4l",
    "studio/kenn/kenn/retrieval",
    "studio/kenn/kenn/static",
    "studio/kenn/kenn/training",
    "studio/kenn/kenn/Training_Data_Notes",
    "studio/kenn/kenn/Training_Data_Sources",
    "studio/kenn/kenn/Training_Data_Transcripts",
    "studio/kenn/kenn/data/index",
    "studio/kenn/kenn/artifacts/models/minilm",
    "studio/kenn/kenn/artifacts/models/kokoro",
    "studio/kenn/kenn/main.py",
    "studio/kenn/kenn/server.py",
    "studio/kenn/kenn/server_rate_limit.py",
    "studio/kenn/kenn/server_payloads.py",
    "studio/kenn/kenn/requirements.txt",
    # The actual Ableton Remote Script (ships alongside
    # scripts/install_ableton_remote_script.py, already covered by the
    # blanket "scripts" root above) -- missing until 2026-08-06, which left
    # a customer with no path to installing live DAW control at all,
    # independent of the ableton_osc_bridge.py import-boot bug above.
    "studio/kenn/remote_script",
    # The small, self-contained slice of business/app that kenn/server.py's
    # chat + AudioGen-bridge integration actually needs -- proven necessary
    # by booting the server in isolation, not assumed. No CRM/invoicing/
    # portfolio-data files, only the code (db.py's schema/migrations are
    # generic; a customer's own install gets its own fresh, empty database).
    "server/app/request_validation.py",
    "server/app/db.py",
    "server/app/event_store.py",
    "server/app/idempotency.py",
    "server/app/api_schemas.py",
    "server/app/audiogen_job_store.py",
    "server/app/artifact_store.py",
    "server/app/portfolio_ops.py",
    "server/app/audiogen_bridge.py",
    "server/app/migrations",
)

RELEASE_ROOTS = (
    "main.py",
    "audio-too",
    "ableton",
    "agent",
    "README.md",
    "LICENSE",
    "docs/commands.md",
    ".env.example",
    ".python-version",
    "pyproject.toml",
    "requirements.txt",
    "audio_too",
    "scripts",
    "server/app",
    "server/agents",
    "thursday",
    "studio/audio_analysis/audio_analysis",
    "studio/agents/MixReview",
    "studio/kenn/kenn/README.md",
    "studio/kenn/kenn/TESTER_DEMO.md",
    "studio/kenn/kenn/__init__.py",
    # Five top-level kenn/ modules missing until found live 2026-08-05 by
    # actually booting the packaged server: kenn/core/chat_answer.py
    # imports orchestrator.py unconditionally at module load, so its
    # absence crashed the packaged server on startup outright. The other
    # four are lazily imported inside request handlers/startup hooks (most
    # guarded by try/except) so they wouldn't crash boot, but would either
    # silently degrade (mixing_doctor) or 500 at runtime the moment a
    # customer actually hit that feature (ableton_osc_bridge,
    # audio_dev_agent, autonomous_agent) -- same class of bug as
    # orchestrator.py, just not loud enough to fail this test until now.
    "studio/kenn/kenn/ableton_osc_bridge.py",
    "studio/kenn/kenn/audio_dev_agent.py",
    "studio/kenn/kenn/autonomous_agent.py",
    "studio/kenn/kenn/mixing_doctor.py",
    "studio/kenn/kenn/orchestrator.py",
    "studio/kenn/kenn/plugin_handoff.py",
    "studio/kenn/kenn/plugin_actions.py",
    "studio/kenn/kenn/project_analysis.py",
    "studio/kenn/kenn/adaptive",
    "studio/kenn/kenn/core",
    "studio/kenn/kenn/evals",
    "studio/kenn/kenn/finetune",
    "studio/kenn/kenn/knowledge",
    "studio/kenn/kenn/llm",
    "studio/kenn/kenn/m4l",
    "studio/kenn/kenn/retrieval",
    "studio/kenn/kenn/static",
    "studio/kenn/kenn/training",
    "studio/kenn/kenn/Training_Data_Notes",
    "studio/kenn/kenn/Training_Data_Sources",
    "studio/kenn/kenn/Training_Data_Transcripts",
    "studio/kenn/kenn/data/index",
    "studio/kenn/kenn/artifacts/models/minilm",
    "studio/kenn/kenn/artifacts/models/kokoro",
    "studio/kenn/kenn/main.py",
    "studio/kenn/kenn/server.py",
    "studio/kenn/kenn/server_rate_limit.py",
    "studio/kenn/kenn/server_payloads.py",
    "studio/kenn/kenn/requirements.txt",
    "studio/kenn/remote_script",
    "studio/audiogen/audiogen/ai",
    "studio/audiogen/audiogen/audio",
    "studio/audiogen/audiogen/composition",
    "studio/audiogen/audiogen/core",
    "studio/audiogen/audiogen/data",
    "studio/audiogen/audiogen/docs",
    "studio/audiogen/audiogen/midi",
    "studio/audiogen/audiogen/presets",
    "studio/audiogen/audiogen/runner",
    "studio/audiogen/audiogen/sampler",
    "studio/audiogen/audiogen/scripts",
    "studio/audiogen/audiogen/tools",
    "studio/audiogen/audiogen/training",
    "studio/audiogen/audiogen/utils",
    "studio/audiogen/audiogen/app_controller.py",
    "studio/audiogen/audiogen/gui_scene_adapter.py",
    "studio/audiogen/audiogen/main.py",
    "studio/audiogen/audiogen/main_llm.py",
    "studio/audiogen/audiogen/main_llm_chorus_only.py",
    "studio/audiogen/audiogen/main_render_full_song.py",
    "studio/audiogen/audiogen/pyproject.toml",
    "studio/audiogen/audiogen/pytest.ini",
    "studio/audiogen/audiogen/requirements-dev.lock",
)

_IGNORED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".cache",
    ".venv",
}
_PRIVATE_PREFIXES = (
    "server/agents/Admin/outputs/",
    "server/agents/Admin/projects/",
    "server/agents/Marketing/campaigns/",
    "server/agents/Marketing/leads/",
    "server/agents/Marketing/outputs/",
    "server/agents/Shared/backups/",
    "server/agents/Shared/data/",
    "server/agents/Shared/exports/",
    "thursday/alerts/",
    "thursday/analytics/",
    "thursday/sessions/",
    "thursday/user_data/",
    "studio/agents/MixReview/data/",
    # Generated benchmark reports contain host-specific model paths and have
    # no runtime value. Model weights live under KENN's separate, explicitly
    # allowlisted artifacts/models roots and are not covered by this prefix.
    "studio/audio_analysis/audio_analysis/artifacts/",
    # Obsolete private storage helper with Jack's local volume names. It has
    # no call sites and must not enter either release target through the broad
    # scripts root.
    "scripts/find_best_storage.py",
    # Dev-only diagnostic/eval tooling (blind-listening prep, reference-track
    # comparisons, profiling scripts). Not part of the product's runtime path
    # and not meant for customer distribution -- excluded wholesale rather
    # than relying on each new script under here to remember to use relative
    # paths (2026-07-18, found via the personal-path privacy scan).
    "scripts/eval/",
)
_IGNORED_SUFFIXES = (
    ".pyc", ".pyo", ".db", ".db-wal", ".db-shm", ".log",
    # Compiled native-kernel build artifacts (dsp_engine/native/*_kernel.cpp) --
    # platform/arch-specific, git-ignored in the source repo, built on demand
    # by the loader. Shipping a stale/wrong-platform .dylib in the package
    # would be worse than not shipping one at all. Found 2026-07-30 when a
    # rebuild swept freshly-compiled kernels into the package unfiltered.
    ".dylib", ".so",
)
_TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".jsonl", ".md", ".py", ".sh", ".txt", ".toml", ".yaml", ".yml"}
# Keep path-prefix literals split so this verifier does not flag its own
# source when release_package.py is (correctly) included in the archive.
_PERSONAL_PATH_PATTERNS = (
    re.compile(r"/(?:Us" r"ers|Vol" r"umes)/(?!\.\.\.(?:[/\s]|$))[^\r\n\"`<>]+"),
    re.compile(r"/ho" r"me/(?!\.\.\.(?:[/\s]|$))[^\r\n\"`<>]+"),
    re.compile(r"[A-Za-z]:\\Us" r"ers\\[^\r\n\"`<>]+"),
)


class ReleasePackageError(RuntimeError):
    """Raised when a package is incomplete, corrupt, or unsafe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(relative: Path) -> bool:
    value = relative.as_posix()
    return (
        any(part in _IGNORED_PARTS for part in relative.parts)
        or value == ".env"
        or value == "thursday/.last_briefing.txt"
        or value.endswith(_IGNORED_SUFFIXES)
        or any(
            value == prefix.rstrip("/") or value.startswith(prefix)
            for prefix in _PRIVATE_PREFIXES
        )
    )


def personal_path_hits(root: Path) -> list[str]:
    """Return text files containing host-specific absolute user/volume paths."""
    hits: list[str] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.suffix.lower() not in _TEXT_SUFFIXES or path.stat().st_size > 5_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _PERSONAL_PATH_PATTERNS:
            for match in pattern.finditer(text):
                hits.append(f"{path.relative_to(root).as_posix()}: {match.group(0)}")
    return hits


def verify_kenn_product_budget(manifest: dict) -> None:
    """Fail when the customer artifact grows beyond its reviewed scope."""
    file_count = int(manifest.get("file_count") or 0)
    total_bytes = int(manifest.get("total_bytes") or 0)
    if file_count > KENN_PRODUCT_MAX_FILES:
        raise ReleasePackageError(
            f"KENN product file budget exceeded: {file_count} > {KENN_PRODUCT_MAX_FILES}"
        )
    if total_bytes > KENN_PRODUCT_MAX_BYTES:
        raise ReleasePackageError(
            f"KENN product byte budget exceeded: {total_bytes} > {KENN_PRODUCT_MAX_BYTES}"
        )


def _copy_root(repo_root: Path, relative: Path, stage: Path) -> None:
    source = repo_root / relative
    if not source.exists():
        raise ReleasePackageError(f"Required release path is missing: {relative}")
    if source.is_file():
        if not _excluded(relative):
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return
    if relative.as_posix() == "studio/kenn/kenn/data/index":
        _copy_active_index_versions(source, stage / relative)
        return
    for path in sorted(source.rglob("*")):
        item_relative = path.relative_to(repo_root)
        if _excluded(item_relative):
            continue
        target = stage / item_relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file() and not path.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _copy_active_index_versions(source: Path, target: Path) -> None:
    """Package only active/rollback index bundles, never developer history."""
    target.mkdir(parents=True, exist_ok=True)
    for name in ("README.md", "CURRENT", "PREVIOUS"):
        path = source / name
        if path.is_file():
            shutil.copy2(path, target / name)
    current = source / "CURRENT"
    if not current.is_file():
        raise ReleasePackageError("KENN index CURRENT pointer is missing")
    version_ids: list[str] = []
    for pointer_name in ("CURRENT", "PREVIOUS"):
        pointer = source / pointer_name
        if not pointer.is_file():
            continue
        version_id = pointer.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", version_id):
            raise ReleasePackageError(f"KENN index {pointer_name} pointer is invalid")
        if version_id not in version_ids:
            version_ids.append(version_id)
    for version_id in version_ids:
        version_dir = source / "versions" / version_id
        if not version_dir.is_dir():
            raise ReleasePackageError(f"KENN index version is missing: {version_id}")
        for path in sorted(item for item in version_dir.rglob("*") if item.is_file()):
            relative = path.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def _manifest(stage: Path, *, schema: str = SCHEMA) -> dict:
    files = []
    for path in sorted(item for item in stage.rglob("*") if item.is_file()):
        relative = path.relative_to(stage).as_posix()
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "mode": path.stat().st_mode & 0o777,
            }
        )
    current = stage / "studio/kenn/kenn/data/index/CURRENT"
    return {
        "schema": schema,
        "created_at": datetime.now(UTC).isoformat(),
        "python": "3.12",
        "index_version": current.read_text(encoding="utf-8").strip(),
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }


def _build(repo_root: Path, archive_path: Path, *, roots: tuple[str, ...], schema: str) -> dict:
    repo_root = repo_root.resolve()
    archive_path = archive_path.resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audio-too-release-") as temp:
        stage = Path(temp) / "Audio_Too"
        stage.mkdir()
        for relative in roots:
            _copy_root(repo_root, Path(relative), stage)
        manifest = _manifest(stage, schema=schema)
        (stage / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pending = archive_path.with_suffix(archive_path.suffix + ".tmp")
        pending.unlink(missing_ok=True)
        # Model weights are already densely encoded; maximum gzip effort adds
        # substantial release time for little size benefit.
        with tarfile.open(pending, "w:gz", compresslevel=1) as archive:
            archive.add(stage, arcname="Audio_Too")
        os.replace(pending, archive_path)
    return manifest


def build_package(repo_root: Path, archive_path: Path) -> dict:
    """Build an atomic package containing code/models but no private runtime data.

    This is Jack's own full-system redeploy bundle (website + business +
    Thursday + KENN + AudioGen) -- see build_kenn_product_package() for the
    separate, narrower, customer-facing product package (Stage O1).
    """
    return _build(repo_root, archive_path, roots=RELEASE_ROOTS, schema=SCHEMA)


def build_kenn_product_package(repo_root: Path, archive_path: Path) -> dict:
    """Build the sellable, customer-facing KENN + DSP product package
    (Stage O1) -- KENN's chat server plus local/CLI AutoMix and AudioGen,
    no Thursday, no business/CRM data, no web upload/job-queue UI.
    """
    manifest = _build(
        repo_root,
        archive_path,
        roots=KENN_PRODUCT_RELEASE_ROOTS,
        schema=KENN_PRODUCT_SCHEMA,
    )
    try:
        verify_kenn_product_budget(manifest)
    except ReleasePackageError:
        archive_path.unlink(missing_ok=True)
        raise
    return manifest


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise ReleasePackageError(f"Unsafe package member: {member.name}")
    return members


def extract_and_verify(
    archive_path: Path, destination: Path, *, expected_schema: str = SCHEMA
) -> tuple[Path, dict]:
    """Extract a package safely and verify every manifested byte and mode."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(destination, members=_safe_members(archive), filter="data")
    root = destination / "Audio_Too"
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ReleasePackageError("Release manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != expected_schema:
        raise ReleasePackageError("Unsupported release manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != manifest.get("file_count"):
        raise ReleasePackageError("Release manifest file count is invalid")
    if sum(int(entry.get("bytes") or 0) for entry in files) != manifest.get("total_bytes"):
        raise ReleasePackageError("Release manifest total byte count is invalid")
    for entry in files:
        path = root / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ReleasePackageError(f"Packaged file is missing: {entry['path']}")
        if _sha256(path) != entry["sha256"]:
            raise ReleasePackageError(f"Packaged checksum failed: {entry['path']}")
    forbidden = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and _excluded(path.relative_to(root))
    ]
    if forbidden:
        raise ReleasePackageError(f"Private/runtime files entered package: {forbidden[:3]}")
    return root, manifest


def extract_and_verify_kenn_product(archive_path: Path, destination: Path) -> tuple[Path, dict]:
    """extract_and_verify(), scoped to the KENN product package's schema,
    plus a defense-in-depth check that Thursday and business/CRM data never
    entered this package -- not just relying on KENN_PRODUCT_RELEASE_ROOTS
    never listing them.
    """
    root, manifest = extract_and_verify(archive_path, destination, expected_schema=KENN_PRODUCT_SCHEMA)
    verify_kenn_product_budget(manifest)
    if (root / "thursday").exists():
        raise ReleasePackageError("Thursday must never appear in the KENN product package")
    if (root / "business" / "agents").exists():
        raise ReleasePackageError("server/agents must never appear in the KENN product package")
    for required_document in ("KENN_PRODUCT_README.md", "THIRD_PARTY_NOTICES.md"):
        if not (root / required_document).is_file():
            raise ReleasePackageError(
                f"Required customer package document is missing: {required_document}"
            )
    path_hits = personal_path_hits(root)
    if path_hits:
        raise ReleasePackageError(
            f"Personal absolute paths entered the KENN product package: {path_hits[:3]}"
        )
    return root, manifest
