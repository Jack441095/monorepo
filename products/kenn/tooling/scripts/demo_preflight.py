#!/usr/bin/env python3
"""Fast, individually runnable pre-flight checks for the KENN investor demo."""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


PRODUCT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_PATH = PRODUCT_ROOT / "tooling" / "demo_session_fixture.json"
sys.path.insert(0, str(PRODUCT_ROOT / "apps" / "backend" / "src"))


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    elapsed_ms: float


class DemoPreflight:
    def __init__(
        self,
        base_url: str,
        *,
        expected_tracks: list[str],
        required_devices: dict[str, list[str]] | None = None,
        allow_mutations: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.expected_tracks = expected_tracks
        self.required_devices = required_devices or {}
        self.allow_mutations = allow_mutations
        self._session: dict[str, Any] | None = None

    def _request(self, path: str, payload: dict[str, Any] | None = None, *, timeout: float = 2.0) -> tuple[dict[str, Any], float]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json"} if payload is not None else {},
            method="POST" if payload is not None else "GET",
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
        return body, (time.perf_counter() - started) * 1000.0

    def _check(self, name: str, operation: Callable[[], str]) -> CheckResult:
        started = time.perf_counter()
        try:
            detail = operation()
            return CheckResult(name, True, detail, round((time.perf_counter() - started) * 1000.0, 1))
        except Exception as exc:
            return CheckResult(name, False, self._friendly_failure(exc), round((time.perf_counter() - started) * 1000.0, 1))

    def _friendly_failure(self, exc: Exception) -> str:
        """Return operator guidance without leaking transport/runtime details."""
        if isinstance(exc, urllib.error.HTTPError):
            return "A KENN endpoint reported that it is unavailable — check the server log, then retry."
        if isinstance(exc, (urllib.error.URLError, ConnectionError)):
            return f"KENN isn't responding at {self.base_url} — start the server and retry."
        if isinstance(exc, (TimeoutError, OSError)) and "tim" in str(exc).casefold():
            return "KENN did not respond within the demo timeout — check the server and Live connection."
        if isinstance(exc, json.JSONDecodeError):
            return "KENN returned an unreadable response — restart the server before the demo."
        if isinstance(exc, RuntimeError) and str(exc).strip():
            return str(exc).strip()
        return "This preflight check could not complete safely — inspect the KENN server log, then retry."

    def _live_session(self) -> dict[str, Any]:
        if self._session is None:
            self._session, _ = self._request("/api/ableton/osc/session?detail=topology")
        return self._session

    def server_health(self) -> str:
        body, _ = self._request("/api/health")
        if body.get("ok") is not True:
            raise RuntimeError("KENN server health endpoint did not report ready.")
        return "server health endpoint is ready"

    def ableton_ping(self) -> str:
        body, elapsed = self._request("/api/ableton/ping", timeout=1.0)
        if body.get("connected") is not True:
            raise RuntimeError("Ableton Live isn't responding — check the OSC connection.")
        if elapsed >= 100.0:
            raise RuntimeError(f"OSC ping took {elapsed:.1f}ms; demo budget is under 100ms.")
        return f"Ableton connected; ping {elapsed:.1f}ms"

    def demo_session(self) -> str:
        state = self._live_session()
        tracks = [str(item.get("name") or "") for item in state.get("tracks") or [] if isinstance(item, dict)]
        missing = [name for name in self.expected_tracks if name not in tracks]
        if missing:
            raise RuntimeError("Demo session mismatch; missing tracks: " + ", ".join(missing))
        if not 8 <= len(tracks) <= 16:
            raise RuntimeError(f"Expected 8-16 demo tracks, found {len(tracks)}.")
        return f"{len(tracks)} tracks; expected names present"

    def retrieval_index(self) -> str:
        body, _ = self._request("/api/health")
        status = ((body.get("subsystems") or {}).get("knowledge_index") or {})
        if status.get("available") is not True:
            raise RuntimeError("Retrieval index is not loaded.")
        return f"retrieval mode {status.get('active_mode', 'available')}"

    def daw_control(self) -> str:
        enabled = os.getenv("KENN_ALLOW_DAW_CONTROL", "").strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            raise RuntimeError("DAW control is disabled; set KENN_ALLOW_DAW_CONTROL=1 after reviewing the safety boundary.")
        body, _ = self._request("/api/ableton/capabilities")
        boundary = body.get("write_boundary") or {}
        if boundary.get("confirmation_required") is not True or boundary.get("readback_required") is not True:
            raise RuntimeError("Ableton capability report does not prove confirmation and readback enforcement.")
        return "DAW control enabled with confirmation and readback"

    def session_qa(self) -> str:
        expected = len(self._live_session().get("tracks") or [])
        body, _ = self._request("/api/ableton/command", {"session_id": "demo-preflight-qa", "command": "How many tracks do I have?", "deterministic_only": True})
        if body.get("track_count") != expected or body.get("answer_mode") != "session_question":
            raise RuntimeError("Session Q&A did not return the grounded track count.")
        return f"grounded track count returned {expected}"

    def device_control(self) -> str:
        tracks = self._live_session().get("tracks") or []
        if self.required_devices:
            for track_name, expected_devices in self.required_devices.items():
                track = next(
                    (item for item in tracks if isinstance(item, dict) and str(item.get("name")) == track_name),
                    None,
                )
                if track is None:
                    raise RuntimeError(f"The demo fixture track '{track_name}' is not present.")
                visible = [
                    str(item.get("name") or "")
                    for item in track.get("devices") or []
                    if isinstance(item, dict)
                ]
                missing = [name for name in expected_devices if name not in visible]
                if missing:
                    raise RuntimeError(
                        f"I can see '{track_name}', but it is missing: {', '.join(missing)}. "
                        f"Visible devices: {', '.join(visible) or 'none'}."
                    )
        matches = [
            (track, device)
            for track in tracks if isinstance(track, dict)
            for device in track.get("devices") or [] if isinstance(device, dict) and str(device.get("name")) == "EQ Eight"
        ]
        if not matches:
            raise RuntimeError("I can't find EQ Eight in the demo session; load it on the bass track.")
        track, device = matches[0]
        body, _ = self._request(f"/api/ableton/osc/device-parameters?track_index={track['index']}&device_index={device.get('index', 0)}")
        if body.get("success") is not True:
            raise RuntimeError("EQ Eight is visible but its parameters did not resolve.")
        return f"EQ Eight resolved on {track.get('name', 'track')}"

    def audio_analysis(self) -> str:
        from kenn.core.audio_analysis import analyze_wav

        stream = io.BytesIO()
        with wave.open(stream, "wb") as handle:
            handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(8000)
            handle.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 220 * i / 8000))) for i in range(8000)))
        result = analyze_wav(stream.getvalue(), filename="preflight.wav")
        if result.get("ok") is not True:
            raise RuntimeError("Audio analyzer rejected its known-good WAV fixture.")
        return f"audio analyzer completed in {result.get('runtime_ms', 0)}ms"

    def frontend(self) -> str:
        request = urllib.request.Request(self.base_url + "/")
        with urllib.request.urlopen(request, timeout=2.0) as response:
            if response.status != 200 or b"<" not in response.read(512):
                raise RuntimeError("Frontend did not return an HTML page.")
        return "frontend reachable"

    def latency(self) -> str:
        _body, elapsed = self._request("/api/ableton/command", {"session_id": "demo-preflight-latency", "command": "How many tracks do I have?", "deterministic_only": True})
        if elapsed >= 500.0:
            raise RuntimeError(f"Command round-trip took {elapsed:.1f}ms; budget is under 500ms.")
        return f"command round-trip {elapsed:.1f}ms"

    def undo_roundtrip(self) -> str:
        if not self.allow_mutations:
            raise RuntimeError("Undo round-trip requires --allow-mutations; no Live change was attempted.")
        tracks = self._live_session().get("tracks") or []
        if not tracks:
            raise RuntimeError("No track is available for the reversible probe.")
        track = tracks[0]
        current = float(track.get("pan", 0.0) or 0.0)
        target = -0.2 if current >= 0 else 0.2
        session_id = f"demo-preflight-undo-{uuid.uuid4().hex}"
        command = f"pan track 1 {target:g}"
        planned, _ = self._request("/api/ableton/command", {"session_id": session_id, "command": command, "deterministic_only": True})
        proposal = planned.get("proposal") or {}
        applied, _ = self._request("/api/ableton/command", {"session_id": session_id, "proposal": proposal, "confirm_token": proposal.get("confirmation_token"), "idempotency_key": proposal.get("action_id")})
        if applied.get("status") != "applied" or (applied.get("receipt") or {}).get("verified") is not True:
            raise RuntimeError("Reversible pan probe did not apply with verified readback.")
        undo, _ = self._request("/api/ableton/command", {"session_id": session_id, "command": "undo", "deterministic_only": True})
        inverse = undo.get("proposal") or {}
        reverted, _ = self._request("/api/ableton/command", {"session_id": session_id, "proposal": inverse, "confirm_token": inverse.get("confirmation_token"), "idempotency_key": inverse.get("action_id")})
        if reverted.get("status") != "applied" or (reverted.get("receipt") or {}).get("verified") is not True:
            raise RuntimeError("Undo proposal did not restore the original value with verified readback.")
        return "set + exact undo round-trip verified"

    def checks(self) -> dict[str, Callable[[], str]]:
        return {
            "ableton_ping": self.ableton_ping, "demo_session": self.demo_session,
            "server_health": self.server_health, "retrieval_index": self.retrieval_index,
            "daw_control": self.daw_control, "session_qa": self.session_qa,
            "device_control": self.device_control, "audio_analysis": self.audio_analysis,
            "undo_roundtrip": self.undo_roundtrip, "frontend": self.frontend, "latency": self.latency,
        }

    def run(self, selected: list[str]) -> list[CheckResult]:
        checks = self.checks()
        return [self._check(name, checks[name]) for name in selected]


def load_fixture(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Load the bounded demo-set contract used by preflight."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    tracks = payload.get("tracks") if isinstance(payload, dict) else None
    if not isinstance(tracks, list) or not 8 <= len(tracks) <= 16:
        raise ValueError("The demo fixture must define 8-16 named tracks.")
    names: list[str] = []
    required: dict[str, list[str]] = {}
    for item in tracks:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise ValueError("Every demo fixture track needs a non-empty name.")
        name = str(item["name"]).strip()
        if name in names:
            raise ValueError(f"The demo fixture repeats track name '{name}'.")
        names.append(name)
        devices = item.get("required_devices") or []
        if not isinstance(devices, list) or any(not str(value).strip() for value in devices):
            raise ValueError(f"Track '{name}' has an invalid required_devices list.")
        if devices:
            required[name] = [str(value).strip() for value in devices]
    return names, required


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    parser.add_argument("--expected-track", action="append", default=[])
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--check", action="append", choices=list(DemoPreflight("", expected_tracks=[]).checks()))
    parser.add_argument("--allow-mutations", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    fixture_tracks, required_devices = load_fixture(args.fixture)
    expected_tracks = args.expected_track or fixture_tracks
    runner = DemoPreflight(
        args.url,
        expected_tracks=expected_tracks,
        required_devices=required_devices,
        allow_mutations=args.allow_mutations,
    )
    selected = args.check or list(runner.checks())
    started = time.perf_counter()
    results = runner.run(selected)
    elapsed = time.perf_counter() - started
    if args.json:
        print(json.dumps({"results": [asdict(item) for item in results], "elapsed_seconds": elapsed}, indent=2))
    else:
        print("KENN Demo Pre-Flight Check\n" + "=" * 27)
        for item in results:
            symbol = "✓" if item.passed else "x"
            print(f"[{symbol}] {item.name}: {item.detail} ({item.elapsed_ms:.1f}ms)")
        passed = sum(item.passed for item in results)
        print(f"\n{passed}/{len(results)} checks passed in {elapsed:.2f}s" + (" — ready for demo" if passed == len(results) and elapsed < 30 else ""))
    return 0 if all(item.passed for item in results) and elapsed < 30 else 1


if __name__ == "__main__":
    raise SystemExit(main())
