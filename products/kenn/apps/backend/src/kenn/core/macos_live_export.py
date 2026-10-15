"""Run the explicitly configured experimental macOS export helper without a shell."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
from threading import Event
import time
from typing import Any, Mapping


class MacOSLiveExportHelper:
    """Provide a synchronous scan exporter; normal construction never launches a helper.

    The caller owns source confirmation and the private job directory. No default
    path, PATH lookup or browser-provided executable can become a write authority.
    """

    def __init__(self, executable: Path, *, enabled: bool = False, supervised_test: bool = False) -> None:
        self.executable = Path(executable)
        self.enabled = enabled
        self.supervised_test = supervised_test

    def __call__(self, request: Mapping[str, Any], cancel_event: Event) -> dict[str, Any]:
        return self.export(request, cancel_event)

    def export(self, request: Mapping[str, Any], cancel_event: Event) -> dict[str, Any]:
        """Return one bounded receipt; an uncertain launched helper never proves closure."""
        if not self.enabled or not self.supervised_test:
            # No helper was launched, so this adapter cannot have opened a Live writer.
            return _receipt(request, "unavailable", "experimental_export_disabled", closed=True)
        if sys.platform != "darwin":
            # Other platforms have no approved AX implementation and never fall back to keystrokes.
            return _receipt(request, "unavailable", "unsupported_platform", closed=True)
        try:
            payload, parent, timeout = _validated_request(request)
            executable = self.executable
            if not executable.is_absolute() or executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
                raise ValueError("The helper must be a fixed absolute executable file.")
        except (OSError, ValueError, TypeError, KeyError):
            # Validation failed before process creation; there is no helper-owned writer.
            return _receipt(request, "unavailable", "invalid_helper_request", closed=True)
        if cancel_event.is_set():
            # Cancellation before launch is the only cancelled result that needs no writer inspection.
            return _receipt(request, "cancelled", "cancel_requested", closed=True)
        environment = dict(os.environ)
        environment["KENN_EXPERIMENTAL_LIVE_EXPORT"] = "1"
        try:
            process = subprocess.Popen(
                [str(executable), "--supervised-test"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment,
                shell=False, close_fds=True,
            )
        except OSError:
            # Popen failed before execution; no helper could have opened an export dialog.
            return _receipt(request, "unavailable", "helper_launch_failed", closed=True)

        output = bytearray()
        selector = selectors.DefaultSelector()
        reason: str | None = None
        deadline = time.monotonic() + timeout
        cancellation_deadline: float | None = None
        try:
            assert process.stdin is not None and process.stdout is not None
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "input")
            selector.register(process.stdout, selectors.EVENT_READ, "output")
            sent = 0
            while selector.get_map():
                now = time.monotonic()
                if cancel_event.is_set() and cancellation_deadline is None:
                    # The marker is scoped to the already validated private directory; the helper owns dialog cancellation.
                    marker_fd = os.open(parent / "cancel.requested", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                    os.close(marker_fd)
                    cancellation_deadline = now + 2.0  # Two seconds lets the helper acknowledge cooperative cancellation.
                if now >= deadline or (cancellation_deadline is not None and now >= cancellation_deadline):
                    reason = "helper_timeout" if now >= deadline else "cancel_unacknowledged"
                    break
                for key, _ in selector.select(timeout=0.05):  # 50 ms polling bounds cancellation without a busy loop.
                    if key.data == "input":
                        try:
                            sent += os.write(key.fd, payload[sent:sent + 4_096])
                        except BrokenPipeError:
                            # A rejected request may close stdin early; its bounded stdout still contains the receipt.
                            sent = len(payload)
                        if sent == len(payload):
                            selector.unregister(key.fileobj)
                            process.stdin.close()
                    else:
                        chunk = os.read(key.fd, min(8_192, 65_537 - len(output)))
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            output.extend(chunk)
                            if len(output) > 65_536:  # A receipt is capped at 64 KiB, including diagnostics.
                                reason = "helper_output_limit"
                                break
                if reason:
                    break
            if reason is None:
                try:
                    process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    reason = "helper_timeout"
        except (OSError, ValueError):
            # Pipe or marker failure after launch leaves Live's writer state unknown.
            reason = "helper_transport_failed"
        finally:
            selector.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.0)  # One second bounds helper teardown, not Live's renderer.
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        # Even an unresponsive helper teardown cannot establish Live writer closure.
                        reason = "helper_teardown_failed"
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
        if reason:
            # Killing a helper does not stop a renderer it may already have started inside Live.
            return _receipt(request, "cancelled" if cancel_event.is_set() else "unavailable", reason, closed=False)
        try:
            receipt = json.loads(output)
            if process.returncode != 0 or not _matching_receipt(request, receipt):
                raise ValueError("Untrusted helper receipt.")
        except (ValueError, TypeError, UnicodeError):
            # A missing, malformed or foreign receipt cannot authorize publication or audio deletion.
            return _receipt(request, "unavailable", "invalid_helper_receipt", closed=False)
        return receipt


def _validated_request(request: Mapping[str, Any]) -> tuple[bytes, Path, int]:
    if request.get("schema") != "kenn.live_export_request.v1" or request.get("action") != "export":
        raise ValueError("Invalid request schema or action.")
    pid, timeout = request.get("live_pid"), request.get("timeout_seconds")
    if type(pid) is not int or not 0 < pid <= 2_147_483_647 or type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError("Invalid process identifier or bounded timeout.")
    title = request.get("expected_window_title")
    if not isinstance(title, str) or not title or len(title.encode()) > 512 or any(ord(char) < 32 for char in title):
        raise ValueError("An exact bounded window title is required.")
    for field in ("render_start", "render_length"):
        if not isinstance(request.get(field), str) or not re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", request[field]):
            raise ValueError("An explicit arrangement range is required.")
    if int(request["render_start"].split(".")[0]) == 0 or not any(int(part) for part in request["render_length"].split(".")):
        raise ValueError("The explicit arrangement range must have a positive start and length.")
    if type(request.get("sample_rate")) is not int or request.get("sample_rate") != 48_000:
        raise ValueError("Only 48000 Hz is qualified.")
    path = Path(request["output_path"])
    parent = path.parent
    info = parent.lstat()
    if not path.is_absolute() or path.name != "kenn-analysis.wav" or str(path) != request["output_path"] or parent.resolve() != parent:
        raise ValueError("The job output must be an exact canonical path.")
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700 or path.exists() or path.is_symlink():
        raise ValueError("The output directory must be private, owned and fresh.")
    for entry in parent.iterdir():
        item = entry.lstat()
        if entry.name not in {"manifest.json", "receipt.json", "cancel.requested"} or not stat.S_ISREG(item.st_mode) or item.st_nlink != 1 or item.st_uid != os.getuid() or item.st_size > 65_536:
            raise ValueError("Unexpected job directory content.")
    payload = json.dumps(dict(request), separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > 16_384:
        raise ValueError("The request exceeds 16 KiB.")
    return payload, parent, timeout


def _matching_receipt(request: Mapping[str, Any], receipt: Any) -> bool:
    if not isinstance(receipt, dict) or receipt.get("schema") != "kenn.live_export_receipt.v1":
        return False  # Unknown protocol cannot describe this invocation's writer state.
    if receipt.get("status") not in {"completed", "failed", "cancelled", "unavailable"} or type(receipt.get("writer_closed")) is not bool or type(receipt.get("channels")) is not int or receipt.get("channels") != 2:
        return False  # Missing closure/channel evidence fails closed even for an unavailable result.
    return all(type(receipt.get(key)) is type(request.get(key)) and receipt.get(key) == request.get(key) for key in ("live_pid", "output_path", "render_start", "render_length", "sample_rate"))


def _receipt(request: Mapping[str, Any], status: str, code: str, *, closed: bool) -> dict[str, Any]:
    return {"schema": "kenn.live_export_receipt.v1", "status": status, "writer_closed": closed,
            "channels": 2, "error_code": code,
            **{key: request.get(key) for key in ("live_pid", "output_path", "render_start", "render_length", "sample_rate")}}
