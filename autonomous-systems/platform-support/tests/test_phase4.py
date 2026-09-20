"""Phase 4C/4H tests: local runtime lifecycle, IPC security, CLI."""

import json
import os
import pathlib
import socket
import struct

import pytest

from nite_ai.adapters import ProductAdapter
from nite_ai.capabilities import CapabilityRegistry
from nite_ai.cli import main as cli_main
from nite_ai.company_capabilities import register_company_capabilities
from nite_ai.company_store import open_store
from nite_ai.runtime import PROTOCOL_VERSION, LocalRuntime, RuntimeClient


@pytest.fixture
def runtime(tmp_path):
    conn, store = open_store(tmp_path / "company.db")
    adapter = ProductAdapter("nite_ai.company")
    registry = CapabilityRegistry()
    register_company_capabilities(adapter, registry, store)
    # AF_UNIX paths are limited to ~104 chars on macOS — keep it short.
    import tempfile

    sock_dir = tempfile.mkdtemp(prefix="nrt")
    rt = LocalRuntime(adapter, registry, os.path.join(sock_dir, "nite.sock"))
    rt.start()
    yield rt
    rt.shutdown()
    conn.close()
    try:
        os.rmdir(sock_dir)
    except OSError:
        pass


def test_runtime_handshake_lists_capabilities(runtime):
    hs = client_for(runtime).call({"protocol_version": PROTOCOL_VERSION,
                                   "request_id": "h1", "operation": "handshake"})
    assert hs["status"] == "success"
    caps = hs["payload"]["capabilities"]
    assert "company.brief.daily" in caps and "company.approvals.decide" in caps


def client_for(rt):
    return RuntimeClient(rt.socket_path)


def test_runtime_brief_round_trip_preserves_trace(runtime):
    resp = client_for(runtime).call({
        "protocol_version": PROTOCOL_VERSION, "request_id": "b1",
        "operation": "company.brief.daily",
        "payload": {"granted_permissions": ["read"]},
        "trace": {"trace_id": "trace-rt-9"},
    })
    assert resp["status"] == "success"
    assert resp["payload"]["trace_id"] == "trace-rt-9"
    assert "daily_brief" in resp["payload"]["result"]


def test_runtime_permission_denial_structured(runtime):
    resp = client_for(runtime).call({"protocol_version": PROTOCOL_VERSION,
                                     "request_id": "d1",
                                     "operation": "company.approvals.decide",
                                     "payload": {}})
    assert resp["status"] == "failed" and resp["error"]["code"] == "permission_denied"


def test_runtime_protocol_mismatch(runtime):
    resp = client_for(runtime).call({"protocol_version": "0.9", "request_id": "m1",
                                     "operation": "handshake"})
    assert resp["error"]["code"] == "protocol_mismatch"


def test_runtime_unknown_operation_structured(runtime):
    resp = client_for(runtime).call({"protocol_version": PROTOCOL_VERSION,
                                     "request_id": "u1",
                                     "operation": "company.nonexistent",
                                     "payload": {"granted_permissions": ["read"]}})
    assert resp["error"]["code"] == "not_supported"


def test_runtime_malformed_json(runtime):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(10)
    conn.connect(str(runtime.socket_path))
    body = b"{not json"
    conn.sendall(struct.pack(">I", len(body)) + body)
    size_raw = conn.recv(4)
    (size,) = struct.unpack(">I", size_raw)
    resp = json.loads(conn.recv(size))
    conn.close()
    assert resp["error"]["code"] == "malformed_request"


def test_runtime_oversized_request_rejected(runtime):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(10)
    conn.connect(str(runtime.socket_path))
    conn.sendall(struct.pack(">I", 500_000_000))
    size_raw = conn.recv(4)
    (size,) = struct.unpack(">I", size_raw)
    resp = json.loads(conn.recv(size))
    conn.close()
    assert resp["error"]["code"] == "oversized_request"


def _short_sock(tmp_path) -> str:
    import tempfile
    return os.path.join(tempfile.mkdtemp(prefix="nrt"), "nite.sock")


def test_runtime_stale_socket_cleaned(tmp_path):
    conn, store = open_store(tmp_path / "c.db")
    adapter = ProductAdapter("nite_ai.company")
    registry = CapabilityRegistry()
    register_company_capabilities(adapter, registry, store)
    sock_path = pathlib.Path(_short_sock(tmp_path))
    sock_path.write_bytes(b"")  # stale file with no listener
    rt = LocalRuntime(adapter, registry, sock_path)
    rt.start()  # cleans up and starts
    assert rt.socket_path.exists()
    rt.shutdown()
    assert not sock_path.exists()
    conn.close()


def test_runtime_second_instance_refused(tmp_path):
    conn, store = open_store(tmp_path / "c.db")
    adapter = ProductAdapter("nite_ai.company")
    registry = CapabilityRegistry()
    register_company_capabilities(adapter, registry, store)
    sock_path = pathlib.Path(_short_sock(tmp_path))
    rt1 = LocalRuntime(adapter, registry, sock_path)
    rt1.start()
    rt2 = LocalRuntime(adapter, registry, sock_path)
    with pytest.raises(RuntimeError, match="another runtime instance"):
        rt2.start()
    rt1.shutdown()
    conn.close()


def test_runtime_restart_after_shutdown(tmp_path):
    conn, store = open_store(tmp_path / "c.db")
    adapter = ProductAdapter("nite_ai.company")
    registry = CapabilityRegistry()
    register_company_capabilities(adapter, registry, store)
    sock_path = pathlib.Path(_short_sock(tmp_path))
    rt = LocalRuntime(adapter, registry, sock_path)
    rt.start()
    rt.shutdown()
    rt2 = LocalRuntime(adapter, registry, sock_path)
    rt2.start()
    hs = RuntimeClient(sock_path).call({"protocol_version": PROTOCOL_VERSION,
                                        "request_id": "r1", "operation": "handshake"})
    assert hs["status"] == "success"
    rt2.shutdown()
    conn.close()


def test_runtime_socket_owner_only_permissions(runtime):
    assert oct(os.stat(runtime.socket_path).st_mode & 0o777) == "0o600"


# ------------------------------------------------------------------- CLI

def test_cli_handshake_json_and_human(runtime, capsys):
    sock = str(runtime.socket_path)
    assert cli_main(["--socket", sock, "--json", "handshake"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["payload"]["protocol_version"] == PROTOCOL_VERSION
    capsys.readouterr()
    assert cli_main(["--socket", sock, "handshake"]) == 0
    assert "runtime ok" in capsys.readouterr().out


def test_cli_brief_output(runtime, capsys):
    assert cli_main(["--socket", str(runtime.socket_path), "--json", "brief"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["payload"]["result"]["daily_brief"]["brief_date"]


def test_cli_runtime_unavailable(tmp_path, capsys):
    import tempfile

    sock = os.path.join(tempfile.mkdtemp(prefix="nrt"), "missing.sock")  # short path
    assert cli_main(["--socket", sock, "brief"]) == 3


def test_cli_runtime_unavailable_long_socket_path(capsys):
    # AF_UNIX paths are limited to ~104 chars on macOS; connecting to an
    # over-long path raises OSError before any connect attempt. The CLI must
    # still classify this as runtime-unavailable (exit 3), not a protocol error.
    long_sock = os.path.join(os.getcwd(), "x" * 200, "missing.sock")
    assert cli_main(["--socket", long_sock, "brief"]) == 3
    assert "runtime unavailable" in capsys.readouterr().err


def test_cli_unknown_command(runtime, capsys):
    assert cli_main(["--socket", str(runtime.socket_path), "bogus"]) == 2

