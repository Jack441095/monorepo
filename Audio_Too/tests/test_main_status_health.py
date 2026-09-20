"""Regression test for main.py's status health check.

A wedged server (bound to its port but returning empty replies under memory
pressure) fooled the old TCP-only `port_open` status check into reporting
"online". `http_healthy`/`_service_state` do a real HTTP probe so status can
distinguish healthy, wedged, and offline. See the 2026-07-08 hub-won't-load
incident (memory pressure from a concurrent MLX job wedged the web server).
"""

from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _WedgedServer:
    """Accepts connections then closes them with no reply — the failure mode."""

    def __init__(self, port: int) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(5)
        self._stop = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except OSError:
                break

    def close(self) -> None:
        self._stop = True
        self.sock.close()


def test_offline_when_nothing_bound() -> None:
    port = _free_port()
    assert main.port_open(port) is False
    assert main.http_healthy(port, "/") is False
    assert main._service_state(port, "/") == "offline"


def test_wedged_server_is_not_reported_online() -> None:
    port = _free_port()
    server = _WedgedServer(port)
    try:
        # The old TCP-only check would pass here — that was the bug.
        assert main.port_open(port) is True
        # The HTTP probe must see through it.
        assert main.http_healthy(port, "/") is False
        assert main._service_state(port, "/") == "bound but NOT responding (wedged?)"
    finally:
        server.close()


def test_healthy_http_server_is_online() -> None:
    import http.server

    port = _free_port()
    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        assert main.http_healthy(port, "/") is True
        assert main._service_state(port, "/") == "online"
    finally:
        httpd.shutdown()
