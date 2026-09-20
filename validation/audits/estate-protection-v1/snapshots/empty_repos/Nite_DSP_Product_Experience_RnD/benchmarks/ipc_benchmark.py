"""Measure the existing NITE local runtime over a temporary Unix socket.

The platform source is imported read-only. The temporary SQLite store and
socket are deleted on exit. This measures transport overhead only, not model
inference or product DSP work.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[2] / "Nite_DSP" / "Nite_DSP_AI_Platform"
sys.path.insert(0, str(PLATFORM))

from nite_ai.adapters import ProductAdapter  # noqa: E402
from nite_ai.capabilities import CapabilityRegistry  # noqa: E402
from nite_ai.company_capabilities import register_company_capabilities  # noqa: E402
from nite_ai.company_store import open_store  # noqa: E402
from nite_ai.runtime import PROTOCOL_VERSION, LocalRuntime, RuntimeClient  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "ipc_results.json"
REPEATS = 100


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="px-ipc-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        connection, store = open_store(temporary_path / "company.db")
        adapter = ProductAdapter("px-benchmark")
        registry = CapabilityRegistry()
        register_company_capabilities(adapter, registry, store)
        runtime = LocalRuntime(adapter, registry, temporary_path / "nite.sock")
        runtime.start()
        client = RuntimeClient(runtime.socket_path, timeout=5.0)
        handshake = client.call({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "px-handshake",
            "operation": "handshake",
        })
        request = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "px-brief",
            "operation": "company.brief.daily",
            "payload": {"granted_permissions": ["read"]},
            "trace": {"trace_id": "px-trace"},
        }
        latencies = []
        for index in range(REPEATS):
            request["request_id"] = f"px-brief-{index}"
            started = time.perf_counter_ns()
            response = client.call(request)
            latencies.append((time.perf_counter_ns() - started) / 1_000_000)
            if response.get("status") != "success":
                raise RuntimeError(f"runtime request failed: {response}")
        socket_mode = oct(os.stat(runtime.socket_path).st_mode & 0o777)
        runtime.shutdown()
        connection.close()

    result = {
        "version": "px-local-ipc-v1",
        "environment": "Existing nite_ai.LocalRuntime; temporary SQLite store; macOS Unix socket",
        "repeats": REPEATS,
        "handshake": {
            "status": handshake.get("status"),
            "capability_count": len(handshake.get("payload", {}).get("capabilities", [])),
        },
        "socket_mode": socket_mode,
        "roundtrip_ms": {
            "median": round(statistics.median(latencies), 4),
            "p95": round(sorted(latencies)[int(REPEATS * 0.95) - 1], 4),
            "max": round(max(latencies), 4),
        },
        "limitations": [
            "The payload is a small company.brief.daily request, not an audio model call.",
            "Does not measure cold-start, concurrent clients, or model inference.",
        ],
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
