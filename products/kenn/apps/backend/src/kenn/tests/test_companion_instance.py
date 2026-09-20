from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from kenn.core.companion_instance import (
    CompanionAlreadyRunning,
    CompanionInstanceLock,
    LOCK_SCHEMA,
    default_lock_path,
)


def _hold_lock(path: str, ready: multiprocessing.synchronize.Event, release: multiprocessing.synchronize.Event) -> None:
    lock = CompanionInstanceLock(Path(path))
    lock.acquire(host="127.0.0.1", port=8090)
    ready.set()
    release.wait(timeout=10)
    lock.release()


def test_lock_records_allowlisted_owner_metadata_and_releases(tmp_path: Path) -> None:
    path = tmp_path / "companion.lock"
    lock = CompanionInstanceLock(path)
    metadata = lock.acquire(host="127.0.0.1", port=8090)
    assert metadata == json.loads(path.read_text(encoding="utf-8"))
    assert metadata["schema"] == LOCK_SCHEMA
    assert metadata["pid"] == os.getpid()
    assert metadata["host"] == "127.0.0.1"
    assert metadata["port"] == 8090
    assert "started_at" in metadata
    assert path.stat().st_mode & 0o777 == 0o600
    lock.release()

    successor = CompanionInstanceLock(path)
    successor.acquire(host="localhost", port=8091)
    successor.release()


def test_concurrent_owner_is_rejected_with_pid_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "companion.lock"
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(target=_hold_lock, args=(str(path), ready, release))
    process.start()
    try:
        assert ready.wait(timeout=10)
        contender = CompanionInstanceLock(path)
        with pytest.raises(CompanionAlreadyRunning) as raised:
            contender.acquire(host="127.0.0.1", port=9999)
        assert raised.value.owner["pid"] == process.pid
        assert f"PID {process.pid}" in str(raised.value)
        assert "Stop that exact instance" in str(raised.value)
    finally:
        release.set()
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert process.exitcode == 0


def test_stale_metadata_without_an_owner_is_recovered(tmp_path: Path) -> None:
    path = tmp_path / "companion.lock"
    path.write_text('{"pid": 999999, "started_at": "stale"}\n', encoding="utf-8")
    lock = CompanionInstanceLock(path)
    metadata = lock.acquire(host="127.0.0.1", port=8090)
    assert metadata["pid"] == os.getpid()
    assert metadata["started_at"] != "stale"
    lock.release()


def test_default_path_can_be_overridden_for_isolated_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = tmp_path / "isolated.lock"
    monkeypatch.setenv("KENN_INSTANCE_LOCK_PATH", str(expected))
    assert default_lock_path() == expected.resolve()
