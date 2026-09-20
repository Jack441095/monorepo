#!/usr/bin/env python3
"""Read-only health and queue audit for the local SLO labeller servers."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


VERSION = "local_labeller_audit_v1"


def fetch_meta(port: int, timeout: float = 2.0) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/meta"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read())
        return {"port": port, "reachable": True, "meta": payload, "error": None}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"port": port, "reachable": False, "meta": None, "error": str(exc)}


def summarize(ports: list[int]) -> dict[str, Any]:
    servers = [fetch_meta(port) for port in ports]
    return {
        "record_type": "slo_local_labeller_audit",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "generated_epoch": time.time(),
        "servers": servers,
        "summary": {
            "n_servers": len(servers),
            "n_reachable": sum(server["reachable"] for server in servers),
            "total_queued": sum((server["meta"] or {}).get("total", 0) for server in servers),
            "total_done": sum((server["meta"] or {}).get("done", 0) for server in servers),
        },
        "safety": {
            "read_only": True,
            "servers_restarted": False,
            "labels_modified": False,
            "source_audio_modified": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ports", nargs="+", type=int, default=[8751, 8752, 8753, 8754])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.ports)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
