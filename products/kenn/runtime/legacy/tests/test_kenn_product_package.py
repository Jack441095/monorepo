"""Stage O1 -- end-to-end test for the KENN-only sellable product package.

Mirrors scripts/eval/packaged_e2e.py's own rigor (build a real archive,
extract it clean, boot the real server, hit real endpoints) but for the
narrower product target: proves the extracted package boots KENN's chat
server and its AudioGen bridge with zero Thursday or business/CRM code
present, not just that the file list looks right.

Slow (real DSP model loading + a real subprocess boot) -- matches the
existing @pytest.mark.slow convention for automix_quality_gate/packaged_e2e
style tests in this suite.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nite_core.release_package import (
    KENN_PRODUCT_MAX_BYTES,
    KENN_PRODUCT_MAX_FILES,
    KENN_PRODUCT_RELEASE_ROOTS,
    ReleasePackageError,
    build_kenn_product_package,
    extract_and_verify_kenn_product,
    personal_path_hits,
    verify_kenn_product_budget,
)

ROOT = Path(__file__).resolve().parent.parent.parent


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_port(port: int, process: subprocess.Popen, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(port):
            return
        if process.poll() is not None:
            raise RuntimeError(f"KENN product server on :{port} exited with {process.returncode}")
        time.sleep(0.2)
    raise RuntimeError(f"KENN product server on :{port} did not become ready")


def test_thursday_and_business_agents_are_never_in_kenn_product_roots() -> None:
    """Fast, no-build sanity check: the root list itself must never name
    thursday or business/agents, independent of the heavier build+boot test
    below."""
    assert "thursday" not in KENN_PRODUCT_RELEASE_ROOTS
    assert not any(root.startswith("server/agents") for root in KENN_PRODUCT_RELEASE_ROOTS)


def test_customer_documents_are_required_package_roots() -> None:
    assert "KENN_PRODUCT_README.md" in KENN_PRODUCT_RELEASE_ROOTS
    assert "THIRD_PARTY_NOTICES.md" in KENN_PRODUCT_RELEASE_ROOTS


def test_kenn_product_roots_never_wholesale_the_audiogen_directory() -> None:
    """P0 fix, 2026-07-12: the roots list must not include the bare
    "studio/audiogen/audiogen" directory -- that ships ~430MB of Jack's
    personal training_data/ and samples/, an egg-info build artifact, and
    reproduce.py (hardcodes a personal /Volumes/... path). Only the granular
    subdirectories/files actually needed by the product should be listed,
    matching RELEASE_ROOTS' own audiogen entries."""
    assert "studio/audiogen/audiogen" not in KENN_PRODUCT_RELEASE_ROOTS
    for leaked in (
        "studio/audiogen/audiogen/training_data",
        "studio/audiogen/audiogen/samples",
        "studio/audiogen/audiogen/reproduce.py",
        "studio/audiogen/audiogen/llm_audiogen_pure_markov.egg-info",
        "studio/audiogen/audiogen/logs",
    ):
        assert leaked not in KENN_PRODUCT_RELEASE_ROOTS
        assert not any(
            root != "studio/audiogen/audiogen" and leaked.startswith(root + "/")
            for root in KENN_PRODUCT_RELEASE_ROOTS
        ), f"{leaked} is reachable via a listed root"


def test_personal_path_scan_rejects_host_specific_paths(tmp_path) -> None:
    safe = tmp_path / "safe.md"
    safe.write_text("Install under /path/to/Audio_Too.\n", encoding="utf-8")
    assert personal_path_hits(tmp_path) == []

    leaked = tmp_path / "leaked.json"
    leaked.write_text(
        '{"model": "/Volumes/Personal_SSD/Audio_Too/models/private.bin"}\n',
        encoding="utf-8",
    )
    assert personal_path_hits(tmp_path) == [
        "leaked.json: /Volumes/Personal_SSD/Audio_Too/models/private.bin"
    ]


@pytest.mark.parametrize(
    "manifest, message",
    [
        (
            {"file_count": KENN_PRODUCT_MAX_FILES + 1, "total_bytes": 1},
            "file budget exceeded",
        ),
        (
            {"file_count": 1, "total_bytes": KENN_PRODUCT_MAX_BYTES + 1},
            "byte budget exceeded",
        ),
    ],
)
def test_kenn_product_budget_rejects_scope_growth(manifest, message) -> None:
    with pytest.raises(ReleasePackageError, match=message):
        verify_kenn_product_budget(manifest)


@pytest.mark.slow
def test_kenn_product_package_boots_and_serves_with_zero_thursday_or_business_agents(tmp_path) -> None:
    archive = tmp_path / "kenn-product.tar.gz"
    manifest = build_kenn_product_package(ROOT, archive)
    assert manifest["file_count"] > 0

    extracted_root, verified = extract_and_verify_kenn_product(archive, tmp_path / "install")
    assert verified["file_count"] == manifest["file_count"]
    assert manifest["file_count"] <= KENN_PRODUCT_MAX_FILES
    assert manifest["total_bytes"] <= KENN_PRODUCT_MAX_BYTES
    assert not (extracted_root / "thursday").exists()
    assert not (extracted_root / "business" / "agents").exists()
    assert (extracted_root / "studio" / "kenn" / "kenn" / "server.py").is_file()
    assert (extracted_root / "scripts" / "automix_local.py").is_file()
    assert (extracted_root / "KENN_PRODUCT_README.md").is_file()
    assert (
        extracted_root
        / "studio"
        / "kenn"
        / "remote_script"
        / "AudioToo_Bridge"
        / "AudioToo_Bridge.py"
    ).is_file()
    assert (extracted_root / "scripts" / "install_ableton_remote_script.py").is_file()
    assert (extracted_root / "THIRD_PARTY_NOTICES.md").is_file()
    packaged_index = extracted_root / "studio" / "kenn" / "kenn" / "data" / "index"
    expected_versions = {
        (packaged_index / pointer).read_text(encoding="ascii").strip()
        for pointer in ("CURRENT", "PREVIOUS")
        if (packaged_index / pointer).is_file()
    }
    packaged_versions = {
        path.name for path in (packaged_index / "versions").iterdir() if path.is_dir()
    }
    assert packaged_versions == expected_versions
    assert not (extracted_root / "scripts" / "find_best_storage.py").exists()
    assert not (
        extracted_root / "studio" / "audio_analysis" / "audio_analysis" / "artifacts"
    ).exists()
    assert personal_path_hits(extracted_root) == []

    port = _available_port()
    process = subprocess.Popen(
        [sys.executable, "studio/kenn/kenn/server.py"],
        cwd=extracted_root,
        env={**os.environ, "KENN_PORT": str(port)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_port(port, process, timeout=60.0)

        import urllib.request

        ask_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=b'{"question": "how do I sidechain bass to the kick?"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(ask_req, timeout=15) as resp:
            assert resp.status == 200

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/audiogen/status", timeout=15) as resp:
            assert resp.status == 200

        # D0.2 -- every DAW-write HTTP route reachable through the packaged
        # archive, not just booting. Found via this exact test 2026-08-06:
        # a strict POST-path allowlist in server.py's do_POST() 404'd all
        # 8 mute/solo/arm/transport/clip/scene routes before they ever
        # reached their handlers -- the chat-driven live verification of
        # those features never caught it because chat calls live_client
        # directly in-process, never through these HTTP routes at all.
        # Expect a clean 403 (daw_control policy gate correctly denying,
        # since AUDIO_TOO_ALLOW_DAW_CONTROL isn't set here) for each --
        # that proves the route resolved and ran its handler without an
        # import-time crash, which is what this test exists to catch.
        import urllib.error

        daw_write_routes = {
            "/api/ableton/osc/volume": {"track_index": 0, "volume": 0.5},
            "/api/ableton/osc/pan": {"track_index": 0, "pan": 0.0},
            "/api/ableton/osc/mute": {"track_index": 0, "muted": True},
            "/api/ableton/osc/solo": {"track_index": 0, "soloed": True},
            "/api/ableton/osc/arm": {"track_index": 0, "armed": True},
            "/api/ableton/osc/undo": {"track_index": 0, "field": "volume", "value": 0.8},
            "/api/ableton/osc/transport/play": {},
            "/api/ableton/osc/transport/stop": {},
            "/api/ableton/osc/tempo": {"bpm": 120.0},
            "/api/ableton/osc/clip/launch": {"track_index": 0, "clip_slot_index": 0},
            "/api/ableton/osc/scene/launch": {"scene_index": 0},
        }
        import json as _json

        for route, body in daw_write_routes.items():
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{route}",
                data=_json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=15)
                raise AssertionError(f"{route} unexpectedly succeeded with no daw_control opt-in")
            except urllib.error.HTTPError as exc:
                assert exc.code == 403, f"{route} returned {exc.code}, expected 403 (import/route crash, not policy denial)"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
