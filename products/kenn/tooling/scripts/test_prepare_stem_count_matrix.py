from __future__ import annotations

import json
from pathlib import Path

import pytest

from prepare_stem_count_matrix import prepare_matrix


def _manifest(tmp_path: Path, license_label: str) -> Path:
    root = tmp_path / "assets"
    root.mkdir()
    payload = {
        "version": 1,
        "root": str(root),
        "tracks": {
            "mix": [
                {"path": "mix/01.wav", "sha256": "a", "license": license_label},
                {"path": "mix/02.wav", "sha256": "b", "license": license_label},
            ]
        },
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def _count_manifest(tmp_path: Path, count: int) -> Path:
    root = tmp_path / "count-assets"
    root.mkdir()
    entries = [
        {
            "path": f"stems/stem-{index:03d}.wav",
            "sha256": f"{index:064x}",
            "size_bytes": index,
            "license": "generated-internal",
        }
        for index in range(count)
    ]
    manifest = tmp_path / "count-manifest.json"
    manifest.write_text(
        json.dumps({"version": 1, "root": str(root), "tracks": {"mix": entries}}),
        encoding="utf-8",
    )
    return manifest


def test_rights_gate_accepts_explicitly_owned_entries(tmp_path: Path) -> None:
    result = prepare_matrix(
        _manifest(tmp_path, "owned"),
        track="mix",
        counts=(1,),
        require_rights_cleared=True,
    )
    assert result["rights_cleared"] is True
    assert result["rights_cleared_required"] is True


def test_rights_gate_rejects_unverified_vendor_pack(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rights-cleared gate failed"):
        prepare_matrix(
            _manifest(tmp_path, "TODO-vendor-pack"),
            track="mix",
            counts=(1,),
            require_rights_cleared=True,
        )


def test_custom_rights_label_requires_explicit_opt_in(tmp_path: Path) -> None:
    result = prepare_matrix(
        _manifest(tmp_path, "studio-owned-contract-2026"),
        track="mix",
        counts=(1,),
        require_rights_cleared=True,
        rights_cleared_licenses=frozenset({"studio-owned-contract-2026"}),
    )
    assert result["rights_cleared"] is True


def test_default_matrix_covers_the_full_one_to_sixty_four_stem_contract(tmp_path: Path) -> None:
    result = prepare_matrix(
        _count_manifest(tmp_path, 64),
        track="mix",
        require_rights_cleared=True,
        rights_cleared_licenses=frozenset({"generated-internal"}),
    )
    assert result["requested_stem_counts"] == [1, 8, 16, 32, 64]
    assert [len(row["files"]) for row in result["matrix"]] == [1, 8, 16, 32, 64]
    assert result["available_wav_stems"] == 64
    assert result["rights_cleared"] is True
