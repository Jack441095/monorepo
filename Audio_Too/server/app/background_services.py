"""Start KENN and the Automix worker as background threads/services.

Extracted out of server.py (the composition root, kept under a strict line
budget by tests/test_architecture_boundaries.py::test_composition_root_remains_reduced)
so that process-startup wiring for these two services doesn't count against it.
"""

from __future__ import annotations

import socket
import threading
from http.server import ThreadingHTTPServer


def start_background_services() -> None:
    """Start KENN and the Automix worker in background threads in this process."""
    from app.server_config import HOST as CONFIG_HOST

    kenn_port = 8090

    def is_port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex((CONFIG_HOST, port)) == 0

    if is_port_open(kenn_port):
        print(f"[server] KENN server already running on port {kenn_port}.", flush=True)
    else:
        print(f"[server] Starting KENN server on port {kenn_port} in background...", flush=True)

        def run_kenn() -> None:
            try:
                import kenn.server

                kenn.server.warm_index()
                try:
                    from kenn.mixing_doctor import start_mixing_doctor

                    start_mixing_doctor()
                except Exception as exc:
                    print(f"WARNING: failed to start mixing doctor: {exc}", flush=True)
                kenn_server = ThreadingHTTPServer((kenn.server.HOST, kenn.server.PORT), kenn.server.Handler)
                kenn_server.daemon_threads = True
                kenn_server.serve_forever()
            except Exception as e:
                print(f"Error in background KENN server: {e}", flush=True)

        threading.Thread(target=run_kenn, name="BackgroundKENN", daemon=True).start()

    print("[server] Starting Automix worker in background...", flush=True)
    try:
        from app.automix_worker import start_automix_worker

        start_automix_worker()
    except Exception as e:
        print(f"Error starting background Automix worker: {e}", flush=True)
