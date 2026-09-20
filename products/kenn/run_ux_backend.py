#!/usr/bin/env python3
"""Run KENN's HTTP handler for local UX work without model/index warm-up."""

from __future__ import annotations

import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for candidate in (ROOT / "apps" / "backend" / "src", ROOT / "tooling" / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault(
    "KENN_ALLOWED_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173",
)

from kenn.server import Handler  # noqa: E402


def main() -> None:
    host = os.environ.get("KENN_HOST", "127.0.0.1")
    port = int(os.environ.get("KENN_PORT", "8090"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"KENN UX backend running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
