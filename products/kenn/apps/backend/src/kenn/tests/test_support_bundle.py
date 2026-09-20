from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "build_support_bundle.py"
module = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("support_bundle", SCRIPT))
assert spec.loader
spec.loader.exec_module(module)


def _diagnostics() -> dict:
    return {"schema": module.DIAGNOSTIC_SCHEMA, "runtime": {"python": "3.13", "platform": "Darwin", "architecture": "arm64", "private": "/Users/person"},
            "checks": {"knowledge": True, "path": "/secret"}, "features": {"chat": True},
            "ableton": {"status": "connected", "snapshot_available": True, "track_count": 4, "tracks": ["Secret Song"]}}


def test_bundle_projection_excludes_sensitive_receipt_and_diagnostic_fields() -> None:
    secret = "confirm.super-secret"; private = "/Users/person/Client/song.als"
    files = module.build_payload(diagnostics=_diagnostics(), receipts={"receipts": [{"session_id": "client-name", "receipt": {
        "schema": "receipt", "receipt_id": "r1", "action": "set_parameter", "status": "success", "verified": True,
        "confirmation_token": secret, "target": {"path": private}, "error": "Client song failed"}}]}, revision="a" * 40)
    rendered = b"".join(files.values()).decode()
    assert secret not in rendered and private not in rendered and "client-name" not in rendered and "Secret Song" not in rendered
    assert "r1" in rendered and '"raw_logs_included": false' in rendered


def test_unexpected_diagnostic_schema_fails_closed() -> None:
    with pytest.raises(module.BundleError, match="unexpected schema"):
        module.project_diagnostics({"schema": "attacker.schema", "path": "/private"})


def test_receipt_url_can_filter_one_session_without_persisting_it() -> None:
    url = module.receipts_url("http://127.0.0.1:8090", "pilot session/1")
    assert url.endswith("limit=100&session_id=pilot+session%2F1")


def test_zip_is_owner_only_and_hashes_match(tmp_path: Path) -> None:
    files = module.build_payload(diagnostics=_diagnostics(), receipts={"receipts": []}, revision="b" * 40)
    output = tmp_path / "bundle.zip"; module.write_bundle(output, files)
    assert output.stat().st_mode & 0o777 == 0o600
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for name, digest in manifest["files"].items():
            import hashlib
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        assert set(archive.namelist()) == {"manifest.json", "diagnostics.json", "lifecycle-events.json"}
