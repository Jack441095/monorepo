#!/usr/bin/env python3
"""Create a privacy-safe KENN support bundle without copying raw logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "kenn.support_bundle.v1"
DIAGNOSTIC_SCHEMA = "kenn.support_diagnostics.v1"
EVENT_FIELDS = ("schema", "receipt_id", "action_id", "action", "status", "verified", "timestamp", "rolled_back", "step_count")


class BundleError(ValueError):
    pass


def _fetch(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise BundleError("endpoint did not return a JSON object")
    return value


def receipts_url(endpoint: str, session_id: str | None = None) -> str:
    query = {"limit": 100}
    if session_id:
        query["session_id"] = session_id
    return endpoint.rstrip("/") + "/api/ableton/receipts?" + urllib.parse.urlencode(query)


def project_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != DIAGNOSTIC_SCHEMA:
        raise BundleError("support endpoint returned an unexpected schema")
    runtime = value.get("runtime") if isinstance(value.get("runtime"), dict) else {}
    checks = value.get("checks") if isinstance(value.get("checks"), dict) else {}
    features = value.get("features") if isinstance(value.get("features"), dict) else {}
    ableton = value.get("ableton") if isinstance(value.get("ableton"), dict) else {}
    return {
        "schema": DIAGNOSTIC_SCHEMA,
        "runtime": {key: runtime.get(key) for key in ("python", "platform", "architecture")},
        "checks": {str(key)[:96]: item for key, item in checks.items() if isinstance(item, bool)},
        "features": {str(key)[:96]: item for key, item in features.items() if isinstance(item, (bool, str))},
        "ableton": {
            "status": ableton.get("status") if ableton.get("status") in {"connected", "offline", "dispatched", "unknown", "not_queried"} else "unknown",
            "snapshot_available": ableton.get("snapshot_available") is True,
            "track_count": ableton.get("track_count") if isinstance(ableton.get("track_count"), int) else None,
        },
    }


def project_events(value: dict[str, Any]) -> list[dict[str, Any]]:
    rows = value.get("receipts")
    if not isinstance(rows, list):
        return []
    projected = []
    for row in rows[:100]:
        receipt = row.get("receipt") if isinstance(row, dict) and isinstance(row.get("receipt"), dict) else {}
        projected.append({key: receipt.get(key) for key in EVENT_FIELDS if key in receipt})
    return projected


def build_payload(*, diagnostics: dict[str, Any], receipts: dict[str, Any], revision: str) -> dict[str, bytes]:
    safe_diagnostics = project_diagnostics(diagnostics)
    safe_events = project_events(receipts)
    files = {
        "diagnostics.json": (json.dumps(safe_diagnostics, indent=2, sort_keys=True) + "\n").encode(),
        "lifecycle-events.json": (json.dumps({"events": safe_events}, indent=2, sort_keys=True) + "\n").encode(),
    }
    manifest = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision[:64],
        "raw_logs_included": False,
        "audio_included": False,
        "project_content_included": False,
        "confirmation_tokens_included": False,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return files


def write_bundle(output: Path, files: dict[str, bytes]) -> None:
    target = output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".kenn-support-", suffix=".zip", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--session-id", help="filter receipt evidence to one local session; never stored in the archive")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    endpoint = args.endpoint.rstrip("/")
    try:
        diagnostics = _fetch(endpoint + "/api/support/diagnostics")
        receipts = _fetch(receipts_url(endpoint, args.session_id))
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        files = build_payload(diagnostics=diagnostics, receipts=receipts, revision=revision)
        write_bundle(args.output, files)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: support bundle not created: {exc}")
        return 2
    print(f"Created privacy-safe support bundle: {args.output.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
