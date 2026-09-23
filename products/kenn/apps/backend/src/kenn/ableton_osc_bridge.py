"""KENN's client for the upstream AbletonOSC Remote Script.

This module deliberately speaks standard OSC rather than the former
KENN-specific JSON-over-UDP dialect. AbletonOSC listens on UDP 11000 and
returns query replies to UDP 11001. KENN's proposal, confirmation, stale
state, readback, and receipt layers remain above this transport.
"""

from __future__ import annotations

import logging
import socket
import json
import time
from threading import Lock
from threading import Event, Lock, Thread
from typing import Any, Dict, Iterable, List, Optional

from kenn.abletonosc_protocol import OSCProtocolError, decode_packet, encode_message

logger = logging.getLogger(__name__)

DEFAULT_LIVE_OSC_HOST = "127.0.0.1"
DEFAULT_LIVE_OSC_PORT = 11000
DEFAULT_RESPONSE_PORT = 11001
DEFAULT_QUERY_TIMEOUT = 0.75
CAPABILITY_SCHEMA = "kenn.abletonosc_capabilities.v1"
DEVICE_MATRIX_SCHEMA = "kenn.ableton_device_matrix.v1"

# These labels describe KENN's qualification boundary, not every device Live
# may expose.  A candidate is visible and inspectable but cannot be called
# qualified until a disposable real-Live write/readback/replay/undo run is
# recorded for that family.
DEVICE_FAMILY_PROFILES = {
    "EQ Eight": {"qualification": "qualified", "next_control": "existing parameter / bounded EQ band"},
    "Compressor": {"qualification": "qualified", "next_control": "existing parameter"},
    "Utility": {"qualification": "qualified", "next_control": "existing parameter"},
    # Glue Compressor/Saturator/Auto Filter/Drum Buss/Hybrid Reverb/Echo each
    # passed a real-Live reversible-parameter qualification (2026-09-05/06,
    # see docs/reports/ABLETON_ASSISTANT_CURRENT_STATE.md) and are in
    # DEVICE_INSERTION_ALLOWLIST in core/live_action_service.py -- this dict
    # had fallen behind that and still called them "candidate", the same
    # class of staleness already fixed in READ_ENDPOINTS/WRITE_ENDPOINTS and
    # ABLETON_LIVE_SUPPORT_MATRIX.json.
    "Glue Compressor": {"qualification": "qualified", "next_control": "existing parameter"},
    "Saturator": {"qualification": "qualified", "next_control": "existing parameter"},
    "Auto Filter": {"qualification": "qualified", "next_control": "existing parameter"},
    "Drum Buss": {"qualification": "qualified", "next_control": "existing parameter"},
    "Hybrid Reverb": {"qualification": "qualified", "next_control": "existing parameter"},
    "Echo": {"qualification": "qualified", "next_control": "existing parameter"},
    "Roar": {"qualification": "qualified", "next_control": "existing parameter / drive / routing"},
    "Meld": {"qualification": "qualified", "next_control": "existing parameter / macro"},
    "Multiband Dynamics": {"qualification": "qualified", "next_control": "existing parameter / crossover"},
}

# This is the explicit endpoint contract used by KENN's guarded service.  It
# is intentionally separate from liveness: a timeout cannot silently turn an
# unqualified OSC address into a supported mutation.
READ_ENDPOINTS = (
    "/live/song/get/num_tracks",
    "/live/song/get/track_names",
    "/live/track/get/num_devices",
    "/live/track/get/devices/name",
    "/live/track/get/has_midi_input",
    "/live/track/get/output_meter_level",
    "/live/track/get/output_meter_right",
    "/live/track/get/send",
    "/live/track/get/input_routing_type",
    "/live/track/get/input_routing_channel",
    "/live/track/get/output_routing_type",
    "/live/track/get/output_routing_channel",
    "/live/track/get/volume",
    "/live/track/get/panning",
    "/live/track/get/mute",
    "/live/track/get/solo",
    "/live/track/get/arm",
    "/live/track/get/is_grouped",
    "/live/track/get/is_foldable",
    "/live/track/get/group_track",
    "/live/track/get/clips/name",
    "/live/track/get/clips/length",
    "/live/track/get/clips/color",
    "/live/track/get/arrangement_clips/name",
    "/live/track/get/arrangement_clips/length",
    "/live/track/get/arrangement_clips/start_time",
    "/live/track/get/arrangement_clips",
    "/live/rack/get/macros",
    "/live/device/get/name",
    "/live/device/get/parameters/name",
    "/live/device/get/parameters/value",
    "/live/device/get/parameters/min",
    "/live/device/get/parameters/max",
    "/live/device/get/parameters/is_quantized",
    "/live/device/get/parameter/value_string",
    "/live/clip_slot/get/has_clip",
    "/live/clip/get/name",
    "/live/clip/get/is_midi_clip",
    "/live/clip/get/length",
    "/live/clip/get/notes",
    "/live/clip_slot/get/is_playing",
    "/live/clip_slot/get/is_triggered",
    "/live/scene/get/is_triggered",
    "/live/song/get/is_playing",
    "/live/song/get/current_song_time",
    "/live/song/get/num_scenes",
    "/live/song/get/scenes/name",
    "/live/song/get/cue_points",
    "/live/song/get/num_return_tracks",
    "/live/song/get/return_track_names",
    "/live/song/get/return_track_devices",
    "/live/song/get/signature_numerator",
    "/live/song/get/signature_denominator",
    "/live/song/get/root_note",
    "/live/song/get/scale_name",
    "/live/song/get/tempo",
    "/live/view/get/selected_track",
    "/live/view/get/selected_track_kind",
    "/live/kenn/version",
    "/live/kenn/get/bus_mixer",
    "/live/kenn/get/device_tree",
    "/live/kenn/get/device_parameters",
    "/live/view/get/selected_device",
    "/live/view/get/selected_scene",
    "/live/track/get/meters",
    "/live/m4l/get/parameters",
)
WRITE_ENDPOINTS = (
    "/live/track/set/volume",
    "/live/track/set/panning",
    "/live/track/set/mute",
    "/live/track/set/solo",
    "/live/track/set/arm",
    "/live/track/set/name",
    "/live/track/set/send",
    "/live/track/set/output_routing",
    "/live/track/set/input_routing",
    "/live/track/set/freeze",
    "/live/track/import_sample",
    "/live/song/create_audio_track",
    "/live/song/create_midi_track",
    "/live/song/create_return_track",
    "/live/song/create_group_track",
    "/live/song/set/return_track_name",
    "/live/song/start_playing",
    "/live/song/stop_playing",
    "/live/song/set/tempo",
    "/live/scene/fire",
    "/live/device/set/parameter/value",
    "/live/track/insert_device",
    "/live/track/delete_device",
    "/live/rack/map_macro",
    "/live/rack/store_variation",
    "/live/rack/recall_variation",
    "/live/clip_slot/create_clip",
    "/live/clip_slot/delete_clip",
    "/live/clip/duplicate_to_arrangement",
    "/live/clip/duplicate_loop",
    "/live/clip/set_automation",
    "/live/clip/set_modulation",
    "/live/clip/set/name",
    "/live/clip/set/warp_mode",
    "/live/clip/set/pitch_coarse",
    "/live/clip_slot/fire",
    "/live/clip_slot/stop",
    "/live/clip/add/notes",
    "/live/clip/remove/notes",
    "/live/song/cue_point/add_or_delete",
    "/live/song/cue_point/set/name",
    "/live/browser/load_preset",
    "/live/master/enforce_safety_limiter",
    "/live/view/set/selected_track",
    "/live/view/set/selected_device",
    "/live/clip_slot/duplicate_clip_to",
)


def _strip_prefix(args: Iterable[Any], count: int) -> list[Any]:
    values = list(args)
    return values[count:] if len(values) >= count else []


def _single_value(args: Iterable[Any], expected_index: int | None = None) -> Any:
    values = list(args)
    if expected_index is not None and len(values) >= 2:
        try:
            if int(values[0]) == expected_index:
                return values[1]
        except (TypeError, ValueError):
            pass
    return values[-1] if values else None


class AbletonOSCClient:
    """Thread-safe standard OSC client for AbletonOSC."""

    def __init__(
        self,
        host: str = DEFAULT_LIVE_OSC_HOST,
        send_port: int = DEFAULT_LIVE_OSC_PORT,
        recv_port: int = DEFAULT_RESPONSE_PORT,
        query_timeout: float = DEFAULT_QUERY_TIMEOUT,
        defer_bind: bool = False,
        enable_circuit_breaker: bool = False,
    ):
        self.host = host
        self.send_port = int(send_port)
        self.recv_port = int(recv_port)
        self.query_timeout = max(0.05, float(query_timeout))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # AbletonOSC's documented reply port is fixed at 11001. A port of 0
        # is useful only for local protocol tests whose fake server replies to
        # the source address; production always uses 11001.
        self._bound = False
        if not defer_bind:
            self._bind_socket()
        self._next_id = 0
        self.last_exchange: Optional[Dict[str, Any]] = None
        self._exchange_lock = Lock()
        self._request_addresses: dict[int, str] = {}
        # Keep-alive watchdog & circuit breaker state
        self._connection_state: str = "disconnected"
        self._missed_heartbeats: int = 0
        self._max_missed_heartbeats: int = 2
        self._last_successful_heartbeat: float = 0.0
        self._circuit_breaker_enabled: bool = enable_circuit_breaker
        # A fresh client starts "disconnected" before any datagram has been
        # exchanged. The breaker must not mistake first contact for an outage:
        # it short-circuits only after at least one real attempt was made.
        self._transport_attempted = False
        self._watchdog_thread: Optional[Thread] = None
        self._watchdog_stop_event: Optional[Event] = None
        self._watchdog_lock = Lock()
        self._cached_session_state: Optional[Dict[str, Any]] = None
        self._cached_session_state_time: float = 0.0
        self._cached_session_state_include_mixer: Optional[bool] = None
        self._cached_session_state_include_meters: Optional[bool] = None
        self._cache_ttl_seconds: float = 1.5

    def _note_transport_success(self) -> None:
        """Record that Live answered, whatever the high-level call decides.

        Any genuine AbletonOSC reply proves the transport is alive. Without
        this, a breaker-enabled client would stay "disconnected" through a
        multi-batch snapshot even while every reply arrives, because only
        ping()/probe() previously marked success.
        """
        with self._watchdog_lock:
            self._missed_heartbeats = 0
            self._last_successful_heartbeat = time.monotonic()
            self._connection_state = "connected"

    def _bind_socket(self) -> bool:
        if self._bound:
            return True
        try:
            self.socket.bind((DEFAULT_LIVE_OSC_HOST, self.recv_port))
            self._bound = True
            return True
        except OSError as exc:
            logger.error("Could not bind AbletonOSC reply port %s: %s", self.recv_port, exc)
            return False

    def close(self) -> None:
        self.stop_watchdog()
        with self._exchange_lock:
            try:
                self.socket.close()
            except OSError:
                pass

    @property
    def connection_state(self) -> str:
        with self._watchdog_lock:
            return self._connection_state

    @property
    def is_connected(self) -> bool:
        with self._watchdog_lock:
            return self._connection_state == "connected"

    @property
    def circuit_breaker_enabled(self) -> bool:
        with self._watchdog_lock:
            return self._circuit_breaker_enabled

    @circuit_breaker_enabled.setter
    def circuit_breaker_enabled(self, value: bool) -> None:
        with self._watchdog_lock:
            self._circuit_breaker_enabled = bool(value)

    def ping(self, *, timeout: float = 0.5) -> bool:
        """Lightweight heartbeat ping to verify Live companion responsiveness."""
        res = self._query_args("/live/song/get/num_tracks", timeout=timeout, bypass_circuit_breaker=True)
        with self._watchdog_lock:
            if res is not None and len(res) > 0:
                self._missed_heartbeats = 0
                self._last_successful_heartbeat = time.monotonic()
                self._connection_state = "connected"
                return True
            else:
                self._missed_heartbeats += 1
                if self._missed_heartbeats >= self._max_missed_heartbeats:
                    self._connection_state = "disconnected"
                else:
                    self._connection_state = "degraded"
                return False

    def start_watchdog(self, interval: float = 2.5, timeout: float = 0.5) -> None:
        """Start background keep-alive watchdog thread."""
        with self._watchdog_lock:
            if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
                return
            self._watchdog_stop_event = Event()
            stop_event = self._watchdog_stop_event

            def _watchdog_loop() -> None:
                while not stop_event.is_set():
                    try:
                        self.ping(timeout=timeout)
                    except Exception as exc:
                        logger.debug("Watchdog ping error: %s", exc)
                    stop_event.wait(interval)

            self._watchdog_thread = Thread(target=_watchdog_loop, daemon=True, name="AbletonOSC-Watchdog")
            self._watchdog_thread.start()

    def stop_watchdog(self) -> None:
        """Stop background keep-alive watchdog thread."""
        with self._watchdog_lock:
            if self._watchdog_stop_event is not None:
                self._watchdog_stop_event.set()
            if self._watchdog_thread is not None:
                self._watchdog_thread.join(timeout=1.0)
                self._watchdog_thread = None
                self._watchdog_stop_event = None

    def get_connection_status(self) -> Dict[str, Any]:
        """Return structured connection and watchdog diagnostics."""
        with self._watchdog_lock:
            return {
                "state": self._connection_state,
                "host": self.host,
                "port": self.send_port,
                "recv_port": self.recv_port,
                "last_successful_heartbeat": self._last_successful_heartbeat,
                "missed_heartbeats": self._missed_heartbeats,
                "circuit_breaker_enabled": self._circuit_breaker_enabled,
                "last_exchange": self.last_exchange,
            }

    def _record_exchange(
        self,
        *,
        address: str,
        request_id: Optional[int],
        response: Optional[Dict[str, Any]],
        started: float,
    ) -> None:
        self.last_exchange = {
            "transport": "abletonosc",
            "address": address,
            "request_id": request_id,
            # Standard OSC has no request IDs. Keep this field for receipt
            # compatibility, but make its absence explicit.
            "response_id": None,
            "response_address": response.get("address") if response else None,
            "response_ok": response is not None,
            "round_trip_ms": round((time.monotonic() - started) * 1000.0, 3),
        }

    def _next_request_id(self, address: str) -> int:
        self._next_id += 1
        self._request_addresses[self._next_id] = address
        return self._next_id

    def send_command(self, address: str, args: Optional[List[Any]] = None) -> Optional[int]:
        """Send a standard OSC message and return KENN's local exchange ID."""
        if not self._bind_socket():
            return None
        request_id = self._next_request_id(address)
        try:
            self.socket.sendto(encode_message(address, args or []), (self.host, self.send_port))
            self._transport_attempted = True
            return request_id
        except (OSError, OSCProtocolError) as exc:
            logger.error("Failed to send AbletonOSC message %s: %s", address, exc)
            self._request_addresses.pop(request_id, None)
            return None

    def _receive_response(self, address: str, timeout: float) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            remaining = max(0.001, deadline - time.monotonic())
            self.socket.settimeout(remaining)
            try:
                data, _ = self.socket.recvfrom(65507)
            except socket.timeout:
                return None
            except OSError as exc:
                logger.debug("AbletonOSC receive failed: %s", exc)
                return None
            try:
                packets = decode_packet(data)
            except OSCProtocolError as exc:
                logger.warning("Ignoring malformed AbletonOSC reply: %s", exc)
                continue
            for response_address, args in packets:
                if response_address == address:
                    return {"address": response_address, "args": args}
        return None

    def receive_response(self, timeout: float = 1.0, expected_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Receive the reply for a previously sent OSC query."""
        address = self._request_addresses.get(expected_id or self._next_id, "")
        if not address:
            return None
        response = self._receive_response(address, timeout)
        if expected_id is not None:
            self._request_addresses.pop(expected_id, None)
        return response

    def _request_response(
        self,
        address: str,
        args: Optional[List[Any]] = None,
        *,
        timeout: Optional[float] = None,
        bypass_circuit_breaker: bool = False,
    ) -> tuple[Optional[int], Optional[Dict[str, Any]]]:
        if (
            self._circuit_breaker_enabled
            and not bypass_circuit_breaker
            and self._transport_attempted
            and self.connection_state == "disconnected"
        ):
            return None, None
        with self._exchange_lock:
            started = time.monotonic()
            request_id = self.send_command(address, args)
            if request_id is None:
                self._record_exchange(address=address, request_id=None, response=None, started=started)
                return None, None
            response = self._receive_response(address, timeout or self.query_timeout)
            self._request_addresses.pop(request_id, None)
            self._record_exchange(address=address, request_id=request_id, response=response, started=started)
            if response is not None:
                self._note_transport_success()
            return request_id, response

    def _send_only(self, address: str, args: Optional[List[Any]] = None) -> bool:
        self._cached_session_state = None
        self._cached_session_state_time = 0.0
        self._cached_session_state_include_mixer = None
        self._cached_session_state_include_meters = None
        with self._exchange_lock:
            started = time.monotonic()
            request_id = self.send_command(address, args)
            self._request_addresses.pop(request_id or -1, None)
            self._record_exchange(address=address, request_id=request_id, response=None, started=started)
            return request_id is not None

    @staticmethod
    def _response_args(response: Optional[Dict[str, Any]]) -> list[Any]:
        return list(response.get("args", [])) if response else []

    def _query_args(
        self,
        address: str,
        args: Optional[List[Any]] = None,
        *,
        timeout: Optional[float] = None,
        bypass_circuit_breaker: bool = False,
    ) -> Optional[list[Any]]:
        _, response = self._request_response(
            address, args, timeout=timeout, bypass_circuit_breaker=bypass_circuit_breaker
        )
        return self._response_args(response) if response is not None else None

    def _request_responses_many(
        self,
        requests: list[tuple[str, Optional[List[Any]]]],
        *,
        timeout: Optional[float] = None,
        bypass_circuit_breaker: bool = False,
    ) -> list[Optional[Dict[str, Any]]]:
        """Send independent read-only queries together and preserve request order.

        AbletonOSC replies on one UDP port, and a session snapshot can require
        dozens of independent properties.  Serialising those queries makes
        the latency roughly ``query_count * timeout`` in a slow Live set.
        This bounded batch sends the same standard OSC messages, then matches
        replies by address and echoed index arguments.  It is used only for
        reads; mutation calls retain the existing one-message path.
        """
        if not requests:
            return []
        if (
            self._circuit_breaker_enabled
            and not bypass_circuit_breaker
            and self._transport_attempted
            and self.connection_state == "disconnected"
        ):
            return [None] * len(requests)
        with self._exchange_lock:
            started = time.monotonic()
            pending: list[dict[str, Any]] = []
            for request_index, (address, args) in enumerate(requests):
                request_id = self.send_command(address, args)
                if request_id is not None:
                    pending.append({
                        "id": request_id,
                        "index": request_index,
                        "address": address,
                        "args": list(args or []),
                    })
            sent = list(pending)

            responses: list[Optional[Dict[str, Any]]] = [None] * len(requests)
            if len(pending) == len(requests):
                deadline = time.monotonic() + max(0.0, timeout or self.query_timeout)
                self.socket.settimeout(max(0.001, deadline - time.monotonic()))
                try:
                    while pending and time.monotonic() < deadline:
                        self.socket.settimeout(max(0.001, deadline - time.monotonic()))
                        try:
                            data, _ = self.socket.recvfrom(65507)
                        except socket.timeout:
                            break
                        except OSError as exc:
                            logger.debug("AbletonOSC batch receive failed: %s", exc)
                            break
                        try:
                            packets = decode_packet(data)
                        except OSCProtocolError as exc:
                            logger.warning("Ignoring malformed AbletonOSC batch reply: %s", exc)
                            continue
                        for response_address, response_args in packets:
                            candidates = [
                                item for item in pending if item["address"] == response_address
                            ]
                            if not candidates:
                                continue
                            # AbletonOSC has no transport request id. Indexed
                            # replies normally echo their request arguments;
                            # accept a response only when that echo identifies
                            # one request, or the address itself is unique.
                            # Arrival-order attribution can apply track N's
                            # value to track M and is therefore forbidden.
                            echoed = [
                                item for item in candidates
                                if item["args"]
                                and len(response_args) >= len(item["args"])
                                and response_args[: len(item["args"])] == item["args"]
                            ]
                            if len(echoed) == 1:
                                match = echoed[0]
                            elif len(candidates) == 1:
                                match = candidates[0]
                            else:
                                logger.warning(
                                    "Ignoring ambiguous AbletonOSC batch reply for %s; "
                                    "request arguments were not echoed",
                                    response_address,
                                )
                                continue
                            responses[match["index"]] = {
                                "address": response_address,
                                "args": list(response_args),
                            }
                            pending.remove(match)
                finally:
                    for item in sent:
                        self._request_addresses.pop(item["id"], None)
                    self.last_exchange = {
                        "transport": "abletonosc",
                        "address": "batch",
                        "request_id": None,
                        "response_id": None,
                        "response_address": next(
                            (response["address"] for response in responses if response is not None), None
                        ),
                        "response_ok": any(response is not None for response in responses),
                        "round_trip_ms": round((time.monotonic() - started) * 1000.0, 3),
                    }
                    if any(response is not None for response in responses):
                        self._note_transport_success()
            else:
                for item in sent:
                    self._request_addresses.pop(item["id"], None)
            return responses

    def _query_many(self, requests: list[tuple[str, Optional[List[Any]]]]) -> list[Optional[list[Any]]]:
        return [self._response_args(response) if response is not None else None for response in self._request_responses_many(requests)]

    def _query_many_bypassing_breaker(self, requests: list[tuple[str, Optional[List[Any]]]]) -> list[Optional[list[Any]]]:
        return [
            self._response_args(response) if response is not None else None
            for response in self._request_responses_many(requests, bypass_circuit_breaker=True)
        ]

    def _track_scalar(self, address: str, track_index: int) -> Any:
        args = self._query_args(address, [int(track_index)])
        return _single_value(args or [], int(track_index)) if args is not None else None

    def _device_values(self, address: str, track_index: int, device_index: int) -> Optional[list[Any]]:
        args = self._query_args(address, [int(track_index), int(device_index)])
        return _strip_prefix(args or [], 2) if args is not None else None

    def probe_connection(self) -> Dict[str, Any]:
        """Perform the lightweight read-only probe used by the UI Test button.

        A full session snapshot intentionally reads every supported track and
        device property, so it is too expensive to use as a liveness check and
        can make overlapping UI requests look like a dead companion.  The
        standard song-level count and name queries are sufficient to prove
        that AbletonOSC is reachable while leaving exact command planning on
        the full snapshot path.
        """
        with self._watchdog_lock:
            self._connection_state = "reconnecting"
        # Both reads are independent and neither respects the circuit breaker
        # (the whole point of a probe is to test a connection the breaker may
        # have already given up on), so they go out as one batch.  This used
        # to run the same two queries twice -- once before the "reconnecting"
        # transition, with both results immediately overwritten by the
        # bypassing pair below -- which cost the UI Test button two wasted
        # round trips, up to 2 x query_timeout against a stalled Live.
        num_tracks_args, names = self._query_many_bypassing_breaker([
            ("/live/song/get/num_tracks", None),
            ("/live/song/get/track_names", None),
        ])
        if not num_tracks_args or names is None:
            with self._watchdog_lock:
                self._missed_heartbeats += 1
                self._connection_state = "disconnected"
            return {
                "status": "offline",
                "host": self.host,
                "port": self.send_port,
                "error": "No standard AbletonOSC response; select AbletonOSC in Live's Control Surface settings.",
            }
        try:
            count = int(num_tracks_args[0])
        except (TypeError, ValueError):
            with self._watchdog_lock:
                self._missed_heartbeats += 1
                self._connection_state = "disconnected"
            return {"status": "offline", "host": self.host, "port": self.send_port}
        if count < 0 or len(names) < count:
            with self._watchdog_lock:
                self._missed_heartbeats += 1
                self._connection_state = "disconnected"
            return {
                "status": "offline",
                "host": self.host,
                "port": self.send_port,
                "error": "AbletonOSC returned an incomplete track-name probe.",
            }
        with self._watchdog_lock:
            self._missed_heartbeats = 0
            self._last_successful_heartbeat = time.monotonic()
            self._connection_state = "connected"
        return {
            "status": "connected",
            "host": self.host,
            "port": self.send_port,
            "track_count": count,
            "track_names": [str(value) for value in names[:count]],
        }

    def capability_report(self) -> Dict[str, Any]:
        """Return a declared endpoint contract plus a read-only liveness probe.

        The endpoint list is KENN's explicit allow-list; the probe only reports
        whether the installed AbletonOSC runtime is reachable.  Callers must
        still use ``LiveActionService`` for every write and must not infer
        write support from a timeout or from this report alone.
        """
        probe = self.probe_connection()
        return {
            "schema": CAPABILITY_SCHEMA,
            "transport": "AbletonOSC",
            "protocol": "OSC",
            "host": self.host,
            "send_port": self.send_port,
            "response_port": self.recv_port,
            "status": probe.get("status", "offline"),
            "connected": probe.get("status") == "connected",
            "track_count": probe.get("track_count"),
            "track_names": probe.get("track_names", []),
            "endpoints": {
                "read": list(READ_ENDPOINTS),
                "write": list(WRITE_ENDPOINTS),
            },
            "write_boundary": {
                "confirmation_required": True,
                "service": "LiveActionService",
                "readback_required": True,
                "replay_rejection": True,
            },
            **({"error": probe["error"]} if probe.get("error") else {}),
        }

    def device_matrix_report(self, *, include_parameters: bool = True) -> Dict[str, Any]:
        """Inventory exact Live devices and their readable parameters.

        This is deliberately read-only.  ``qualified`` means the family is
        covered by KENN's captured real-Live evidence; ``candidate`` means it
        is the next bounded qualification target; and ``unqualified`` means
        KENN has not made a claim about that device.  No label here grants a
        write permission.
        """
        topology = self.query_session_topology()
        if topology.get("status") != "connected":
            return {
                "schema": DEVICE_MATRIX_SCHEMA,
                "status": "offline",
                "connected": False,
                "transport": "AbletonOSC",
                "entries": [],
                "families": {
                    name: {"qualification": profile["qualification"], "next_control": profile["next_control"]}
                    for name, profile in DEVICE_FAMILY_PROFILES.items()
                },
                **({"error": topology.get("error")} if topology.get("error") else {}),
            }

        entries: list[dict[str, Any]] = []
        observed_names: set[str] = set()
        for track in topology.get("tracks", []):
            if not isinstance(track, dict):
                continue
            for device in track.get("devices", []) or []:
                if not isinstance(device, dict):
                    continue
                name = str(device.get("name", ""))
                observed_names.add(name)
                profile = DEVICE_FAMILY_PROFILES.get(name)
                entry: dict[str, Any] = {
                    "track_index": track.get("index"),
                    "track_name": track.get("name", ""),
                    "device_index": device.get("index"),
                    "device_name": name,
                    "qualification": profile["qualification"] if profile else "unqualified",
                    "next_control": profile["next_control"] if profile else "no qualification claim",
                }
                if include_parameters:
                    info = self.get_device_parameters(int(track["index"]), int(device["index"]))
                    entry["parameter_probe"] = {
                        "success": bool(info.get("success")),
                        "parameter_count": len(info.get("parameters", [])) if info.get("success") else 0,
                        "parameters": info.get("parameters", []) if info.get("success") else [],
                        **({"error": info.get("error")} if info.get("error") else {}),
                    }
                entries.append(entry)

        return {
            "schema": DEVICE_MATRIX_SCHEMA,
            "status": "connected",
            "connected": True,
            "transport": "AbletonOSC",
            "entries": entries,
            "observed_families": sorted(observed_names),
            "missing_candidate_families": sorted(
                name for name, profile in DEVICE_FAMILY_PROFILES.items()
                if profile["qualification"] == "candidate" and name not in observed_names
            ),
            "families": {
                name: {"qualification": profile["qualification"], "next_control": profile["next_control"]}
                for name, profile in DEVICE_FAMILY_PROFILES.items()
            },
            "write_boundary": {
                "report_is_read_only": True,
                "writes_still_require": ["exact identity", "confirmation", "stale check", "readback", "receipt"],
            },
        }

    def query_session_state(
        self, *, include_mixer: bool = True, include_meters: bool = False, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Build KENN's snapshot shape from standard AbletonOSC queries."""
        now = time.monotonic()
        if (
            not force_refresh
            and self._cached_session_state is not None
            and (now - self._cached_session_state_time) < self._cache_ttl_seconds
            # ``None`` preserves compatibility with callers/tests that seed a
            # cache snapshot directly; snapshots produced by this client use
            # explicit scope booleans so topology data cannot satisfy a full
            # mixer request.
            and (not include_mixer or self._cached_session_state_include_mixer is not False)
            and (not include_meters or self._cached_session_state_include_meters is not False)
        ):
            return dict(self._cached_session_state)

        # Independent reads, so they share one batch: a round trip saved on
        # the success path, and one query_timeout rather than two before an
        # unresponsive Live can be reported as offline.
        num_tracks_args, names = self._query_many([
            ("/live/song/get/num_tracks", None),
            ("/live/song/get/track_names", None),
        ])
        if not num_tracks_args or names is None:
            with self._watchdog_lock:
                self._missed_heartbeats += 1
                self._connection_state = "disconnected"
            return {
                "status": "offline",
                "host": self.host,
                "port": self.send_port,
                "tracks": [],
                "scenes": [],
                "error": "No standard AbletonOSC response; select AbletonOSC in Live's Control Surface settings.",
            }
        try:
            count = int(num_tracks_args[0])
        except (TypeError, ValueError):
            return {"status": "offline", "host": self.host, "port": self.send_port, "tracks": [], "scenes": []}
        track_names = [str(value) for value in names[:count]]
        if len(track_names) != count:
            return {
                "status": "offline",
                "host": self.host,
                "port": self.send_port,
                "tracks": [],
                "scenes": [],
                "error": "AbletonOSC returned an incomplete track-name snapshot.",
            }

        batched_requests: list[tuple[str, Optional[List[Any]]]] = []
        meter_requests: list[tuple[str, Optional[List[Any]]]] = []
        for track_index in range(count):
            batched_requests.extend([
                ("/live/track/get/num_devices", [track_index]),
                ("/live/track/get/devices/name", [track_index]),
            ])
            if include_mixer:
                batched_requests.extend(
                    (f"/live/track/get/{osc_name}", [track_index])
                    for osc_name in ("volume", "panning", "mute", "solo", "arm")
                )
            if include_meters:
                meter_requests.extend(
                    (f"/live/track/get/{osc_name}", [track_index])
                    for osc_name in ("output_meter_level", "output_meter_right")
                )
        if include_mixer:
            batched_requests.extend([
                ("/live/song/get/scenes/name", None),
                ("/live/song/get/tempo", None),
                ("/live/song/get/signature_numerator", None),
                ("/live/song/get/signature_denominator", None),
                ("/live/song/get/root_note", None),
                ("/live/song/get/scale_name", None),
                ("/live/song/get/is_playing", None),
                ("/live/view/get/selected_track", None),
            ])
        batched_values = self._query_many(batched_requests)
        # Meter packets are advisory and some AbletonOSC/Live combinations do
        # not answer every channel.  Keeping them in the identity/mixer batch
        # made the shared reply socket wait its full 750ms timeout, blocking
        # pings and command planning behind optional telemetry.  Read meters
        # separately with a short bounded window; missing values stay absent.
        meter_values = [
            self._response_args(response) if response is not None else None
            for response in self._request_responses_many(meter_requests, timeout=0.1)
        ]
        batch_index = 0
        tracks: list[dict[str, Any]] = []
        for track_index, track_name in enumerate(track_names):
            device_count_args = batched_values[batch_index]
            device_names = batched_values[batch_index + 1]
            batch_index += 2
            if device_count_args is None or device_names is None:
                return {
                    "status": "offline",
                    "host": self.host,
                    "port": self.send_port,
                    "tracks": [],
                    "scenes": [],
                    "error": f"AbletonOSC returned an incomplete device snapshot for track {track_index}.",
                }
            try:
                device_count = int(_single_value(device_count_args, track_index))
            except (TypeError, ValueError):
                return {"status": "offline", "host": self.host, "port": self.send_port, "tracks": [], "scenes": []}
            names_for_track = [str(value) for value in _strip_prefix(device_names, 1)[:device_count]]
            if len(names_for_track) != device_count:
                return {
                    "status": "offline",
                    "host": self.host,
                    "port": self.send_port,
                    "tracks": [],
                    "scenes": [],
                    "error": f"AbletonOSC returned an incomplete device-name snapshot for track {track_index}.",
                }
            track: dict[str, Any] = {
                "index": track_index,
                "name": track_name,
                "devices": [{"index": index, "name": name} for index, name in enumerate(names_for_track)],
            }
            if include_mixer:
                for key, osc_name in (
                    ("volume", "volume"),
                    ("pan", "panning"),
                    ("muted", "mute"),
                    ("soloed", "solo"),
                    ("armed", "arm"),
                ):
                    value_args = batched_values[batch_index]
                    batch_index += 1
                    value = _single_value(value_args or [], track_index) if value_args is not None else None
                    if value is not None:
                        track[key] = value
            tracks.append(track)

        if include_meters:
            meter_index = 0
            for track_index, track in enumerate(tracks):
                for key in ("output_meter_level", "output_meter_right"):
                    value_args = meter_values[meter_index] if meter_index < len(meter_values) else None
                    meter_index += 1
                    value = _single_value(value_args or [], track_index) if value_args is not None else None
                    if value is not None:
                        track[key] = value

        scene_names = batched_values[batch_index] or [] if include_mixer else []
        tempo_args = batched_values[batch_index + 1] or [] if include_mixer else []
        signature_numerator_args = batched_values[batch_index + 2] or [] if include_mixer else []
        signature_denominator_args = batched_values[batch_index + 3] or [] if include_mixer else []
        root_note_args = batched_values[batch_index + 4] or [] if include_mixer else []
        scale_name_args = batched_values[batch_index + 5] or [] if include_mixer else []
        playing_args = batched_values[batch_index + 6] or [] if include_mixer else []
        selected_args = batched_values[batch_index + 7] or [] if include_mixer else []
        selected_index = selected_args[0] if selected_args else None
        selected_kind = None
        if isinstance(selected_index, (int, float)) and int(selected_index) < 0:
            # The patched Remote Script answers -1 when a return or master
            # track is selected; ask which one instead of reporting nothing.
            selected_index = None
            kind_args = self._query_args("/live/view/get/selected_track_kind")
            if kind_args and len(kind_args) >= 3:
                selected_kind = {"kind": str(kind_args[0]), "index": int(kind_args[1]), "name": str(kind_args[2])}
        result = {
            "status": "connected",
            "host": self.host,
            "port": self.send_port,
            "tracks": tracks,
            "scenes": [{"index": index, "name": str(name)} for index, name in enumerate(scene_names)],
            "tempo": tempo_args[0] if tempo_args else None,
            "signature_numerator": signature_numerator_args[0] if signature_numerator_args else None,
            "signature_denominator": signature_denominator_args[0] if signature_denominator_args else None,
            "root_note": root_note_args[0] if root_note_args else None,
            "scale_name": str(scale_name_args[0]) if scale_name_args else None,
            "is_playing": bool(playing_args[0]) if playing_args else None,
            "selected_track_index": selected_index,
            "selected_track_kind": selected_kind,
            "return_tracks": [],
            "master_track": None,
        }
        self._cached_session_state = result
        self._cached_session_state_time = time.monotonic()
        self._cached_session_state_include_mixer = include_mixer
        self._cached_session_state_include_meters = include_meters
        # A complete snapshot proves Live is reachable, exactly like a probe.
        # Without this, a breaker-enabled client would stay "disconnected"
        # forever even while every query succeeds.
        with self._watchdog_lock:
            self._missed_heartbeats = 0
            self._last_successful_heartbeat = time.monotonic()
            self._connection_state = "connected"
        return result

    def query_session_topology(self) -> Dict[str, Any]:
        """Return a fresh track/device identity snapshot without mixer reads."""
        return self.query_session_state(include_mixer=False, force_refresh=True)

    def get_scene_names(self) -> List[str]:
        """Read exact scene names/count without the full mixer/transport batch.

        ``query_session_state(include_mixer=False)`` (the fast topology path
        command parsing uses) skips scenes along with tempo/transport, since
        they were originally batched together for round-trip efficiency.
        Scenes are identity data like track names, not a mixer value, so a
        scene-referencing command needs this separate, still-cheap fetch.
        """
        args = self._query_args("/live/song/get/scenes/name") or []
        return [str(value) for value in args]

    def get_current_song_time(self) -> Optional[float]:
        """Read the exact Live playhead position in beats."""
        args = self._query_args("/live/song/get/current_song_time")
        if args is None or not args:
            return None
        try:
            value = float(_single_value(args))
        except (TypeError, ValueError):
            return None
        return value if value >= 0.0 else None

    def get_locators(self) -> List[Dict[str, Any]]:
        """Read the song's cue points as stable name/time identities.

        AbletonOSC exposes cue points as a flat ``name, time`` sequence.  The
        returned index is only an observation aid; callers should bind writes
        to the name and beat position because Live may reorder cue points.
        """
        locators, _available = self.get_locators_with_status()
        return locators

    def get_locators_with_status(self) -> tuple[List[Dict[str, Any]], bool]:
        """Read cue points and distinguish an empty list from no response."""
        args = self._query_args("/live/song/get/cue_points")
        if args is None:
            return [], False
        locators: List[Dict[str, Any]] = []
        for position in range(0, len(args) - 1, 2):
            name, beat = args[position], args[position + 1]
            if not isinstance(beat, (int, float)) or isinstance(beat, bool):
                continue
            locators.append({"index": len(locators), "name": str(name), "time_beats": float(beat)})
        return locators, True

    def remove_locator(self, name: str, time_beats: float) -> bool:
        """Remove one exact cue point at the stopped current playhead.

        AbletonOSC exposes cue-point mutation as a toggle.  This helper makes
        the destructive half safe by requiring the current cursor, time, and
        name to identify exactly one existing cue before issuing the toggle.
        It never moves the playhead on behalf of the caller.
        """
        cursor = self.get_current_song_time()
        if cursor is None or abs(float(cursor) - float(time_beats)) > 1e-4:
            return False
        locators, available = self.get_locators_with_status()
        if not available:
            return False
        matches = [
            locator for locator in locators
            if str(locator.get("name", "")) == str(name)
            and isinstance(locator.get("time_beats"), (int, float))
            and abs(float(locator["time_beats"]) - float(time_beats)) <= 1e-4
        ]
        if len(matches) != 1:
            return False
        if not self._send_only("/live/song/cue_point/add_or_delete"):
            return False
        after, after_available = self.get_locators_with_status()
        if not after_available:
            return False
        return not any(
            str(locator.get("name", "")) == str(name)
            and isinstance(locator.get("time_beats"), (int, float))
            and abs(float(locator["time_beats"]) - float(time_beats)) <= 1e-4
            for locator in after
        )

    def add_locator(self, name: str) -> bool:
        """Add and name a cue point at Live's current song position.

        Ableton's ``set_or_delete_cue`` method is intentionally exposed only
        as an add operation here.  The service layer refuses to call it when
        a cue already exists at the cursor, preventing the toggle endpoint
        from silently deleting user content.  Live adds the cue with its own
        default label, so this method reads the newly-created cue at the
        stopped cursor and then applies the requested exact name.
        """
        if not self._send_only("/live/song/cue_point/add_or_delete"):
            return False
        cursor = self.get_current_song_time()
        locators, available = self.get_locators_with_status()
        if cursor is None or not available:
            return False
        matches = [
            locator for locator in locators
            if isinstance(locator.get("time_beats"), (int, float))
            and abs(float(locator["time_beats"]) - float(cursor)) <= 1e-4
        ]
        if len(matches) != 1:
            return False
        try:
            index = int(matches[0]["index"])
        except (KeyError, TypeError, ValueError):
            return False
        return self._send_only("/live/song/cue_point/set/name", [index, str(name)])

    def get_return_tracks(self) -> List[Dict[str, Any]]:
        """Real return-track identity: exact name and device chain per
        return track (e.g. "A-Reverb" -> ["Reverb"]).

        Return tracks were previously unreadable at all through this bridge
        (``query_session_state``'s ``return_tracks`` field was always an
        empty placeholder) -- the vendored AbletonOSC fork gained
        ``/live/song/get/num_return_tracks``, ``/live/song/get/return_track_names``,
        and ``/live/song/get/return_track_devices`` (2026-09-06) specifically
        to close that gap. Like ``get_scene_names``, this is a separate,
        opt-in fetch rather than part of the fast topology path, since most
        commands don't reference a send/return at all.
        """
        return_tracks, _available = self._get_return_tracks_observation()
        return return_tracks

    def get_return_tracks_with_status(self) -> tuple[List[Dict[str, Any]], bool]:
        """Return return-track identity and whether the readback was available.

        An empty list is a valid Live observation, so structural callers must
        not use ``get_return_tracks()`` alone to distinguish an empty set from
        a missing or timed-out Remote Script endpoint.
        """
        return self._get_return_tracks_observation()

    def _get_return_tracks_observation(self) -> tuple[List[Dict[str, Any]], bool]:
        """Return return-track data plus whether Live answered the count read.

        An empty list is a valid observation for a set with no returns.  It
        must not also stand for an unsupported or timed-out endpoint: callers
        using the richer read-only snapshot need to preserve that distinction.
        """
        count_args = self._query_args("/live/song/get/num_return_tracks")
        if count_args is None:
            return [], False
        count = int(count_args[0]) if count_args else 0
        names = self._query_args("/live/song/get/return_track_names")
        if names is None:
            return [], False
        result: List[Dict[str, Any]] = []
        for index in range(count):
            name = str(names[index]) if index < len(names) else ""
            device_args = self._query_args("/live/song/get/return_track_devices", [index]) or []
            devices = [str(value) for value in device_args[1:]] if device_args else []
            result.append({"index": index, "name": name, "devices": devices})
        return result, True

    def query_session_understanding(self) -> Dict[str, Any]:
        """Read a bounded, evidence-only picture of the current Live set.

        This is deliberately separate from :meth:`query_session_state` and
        its fast topology variant.  Routing, sends, and clip inventory are
        valuable for explanation and planning context, but cost more OSC
        round trips and must never make an ordinary control proposal slower.
        The method performs no Live mutation and leaves unavailable fields
        absent rather than inferring them.
        """
        state = self.query_session_state(include_meters=True)
        if state.get("status") != "connected":
            return state

        raw_returns, return_tracks_available = self._get_return_tracks_observation()
        # ``query_session_state`` predates return-track enumeration and uses
        # [] as a legacy placeholder.  The richer path has an explicit
        # observation, so discard that placeholder before deciding whether a
        # real empty list was observed or the endpoint was unavailable.
        state.pop("return_tracks", None)
        return_tracks = [
            {
                "index": item["index"],
                "name": item["name"],
                "devices": [
                    {"index": device_index, "name": device_name}
                    for device_index, device_name in enumerate(item.get("devices") or [])
                ],
            }
            for item in raw_returns
        ]
        if return_tracks_available:
            state["return_tracks"] = return_tracks

        tracks = [item for item in state.get("tracks", []) if isinstance(item, dict)]
        requests: list[tuple[str, Optional[List[Any]]]] = [
            ("/live/view/get/selected_scene", None),
            ("/live/view/get/selected_device", None),
            ("/live/song/get/cue_points", None),
        ]
        for track in tracks:
            index = track.get("index")
            if not isinstance(index, int):
                continue
            requests.extend(
                (address, [index])
                for address in (
                    "/live/track/get/input_routing_type",
                    "/live/track/get/input_routing_channel",
                    "/live/track/get/output_routing_type",
                    "/live/track/get/output_routing_channel",
                    "/live/track/get/is_grouped",
                    "/live/track/get/is_foldable",
                    "/live/track/get/group_track",
                    "/live/track/get/clips/name",
                    "/live/track/get/clips/length",
                    "/live/track/get/clips/color",
                    "/live/track/get/arrangement_clips/name",
                    "/live/track/get/arrangement_clips/length",
                    "/live/track/get/arrangement_clips/start_time",
                )
            )
            requests.extend(("/live/track/get/send", [index, item["index"]]) for item in return_tracks)
        values = self._query_many(requests)
        cursor = 0
        selected_scene = values[cursor]
        cursor += 1
        if selected_scene:
            state["selected_scene_index"] = selected_scene[0]
        selected_device = values[cursor]
        cursor += 1
        if selected_device and len(selected_device) >= 2:
            try:
                selected_device_track_index = int(selected_device[0])
                selected_device_index = int(selected_device[1])
            except (TypeError, ValueError):
                selected_device_track_index = None
                selected_device_index = None
            if selected_device_track_index is not None and selected_device_index is not None:
                state["selected_device_track_index"] = selected_device_track_index
                state["selected_device_index"] = selected_device_index
                selected_device_track = next(
                    (item for item in tracks if item.get("index") == selected_device_track_index), None
                )
                selected_device_items = selected_device_track.get("devices") if selected_device_track else []
                if isinstance(selected_device_items, list) and 0 <= selected_device_index < len(selected_device_items):
                    selected_device_item = selected_device_items[selected_device_index]
                    state["selected_device_name"] = (
                        str(selected_device_item.get("name", ""))
                        if isinstance(selected_device_item, dict)
                        else str(selected_device_item)
                    )
        cue_point_args = values[cursor]
        cursor += 1
        locators: list[dict[str, Any]] = []
        for position in range(0, len(cue_point_args or []) - 1, 2):
            name, beat = cue_point_args[position], cue_point_args[position + 1]
            if not isinstance(beat, (int, float)) or isinstance(beat, bool):
                continue
            locators.append({"index": len(locators), "name": str(name), "time_beats": float(beat)})
        if cue_point_args is not None:
            state["locators"] = locators
        capability_flags = {
            "return_tracks": return_tracks_available,
            "groups": False,
            "selected_scene": selected_scene is not None,
            "selected_device": selected_device is not None,
            "locators": cue_point_args is not None,
            "routing": False,
            "session_clip_inventory": False,
            "arrangement_clip_inventory": False,
            "track_sends": False,
        }
        for track in tracks:
            index = track.get("index")
            if not isinstance(index, int):
                continue
            routing_values = values[cursor:cursor + 4]
            cursor += 4
            capability_flags["routing"] = capability_flags["routing"] or any(value is not None for value in routing_values)
            for key, args in zip(
                ("input_routing_type", "input_routing_channel", "output_routing_type", "output_routing_channel"),
                routing_values,
            ):
                value = _single_value(args or [], index)
                if value is not None:
                    track[key] = str(value)
            grouped_args, foldable_args, group_track_args = values[cursor:cursor + 3]
            cursor += 3
            if grouped_args is not None or foldable_args is not None or group_track_args is not None:
                capability_flags["groups"] = True
            grouped = _single_value(grouped_args or [], index)
            foldable = _single_value(foldable_args or [], index)
            group_track = _single_value(group_track_args or [], index)
            if grouped is not None:
                track["is_grouped"] = bool(grouped)
            if foldable is not None:
                track["is_foldable"] = bool(foldable)
            if isinstance(group_track, int) and not isinstance(group_track, bool) and group_track >= 0:
                track["group_track_index"] = group_track
            names_args, lengths_args, colors_args, arrangement_names_args, arrangement_lengths_args, arrangement_starts_args = values[cursor:cursor + 6]
            cursor += 6
            if any(value is not None for value in (names_args, lengths_args, colors_args)):
                capability_flags["session_clip_inventory"] = True
                names = _strip_prefix(names_args or [], 1)
                lengths = _strip_prefix(lengths_args or [], 1)
                colors = _strip_prefix(colors_args or [], 1)
                slot_count = max(len(names), len(lengths), len(colors))
                track["clip_slots"] = [
                    {
                        "index": slot_index,
                        "has_clip": names[slot_index] is not None if slot_index < len(names) else False,
                        **({"name": str(names[slot_index])} if slot_index < len(names) and names[slot_index] is not None else {}),
                        **({"length": lengths[slot_index]} if slot_index < len(lengths) and lengths[slot_index] is not None else {}),
                        **({"color": colors[slot_index]} if slot_index < len(colors) and colors[slot_index] is not None else {}),
                    }
                    for slot_index in range(slot_count)
                ]
            if any(value is not None for value in (arrangement_names_args, arrangement_lengths_args, arrangement_starts_args)):
                capability_flags["arrangement_clip_inventory"] = True
                arrangement_names = _strip_prefix(arrangement_names_args or [], 1)
                arrangement_lengths = _strip_prefix(arrangement_lengths_args or [], 1)
                arrangement_starts = _strip_prefix(arrangement_starts_args or [], 1)
                arrangement_count = max(len(arrangement_names), len(arrangement_lengths), len(arrangement_starts))
                track["arrangement_clips"] = [
                    {
                        "index": clip_index,
                        **({"name": str(arrangement_names[clip_index])} if clip_index < len(arrangement_names) and arrangement_names[clip_index] is not None else {}),
                        **({"length_beats": float(arrangement_lengths[clip_index])} if clip_index < len(arrangement_lengths) and isinstance(arrangement_lengths[clip_index], (int, float)) and not isinstance(arrangement_lengths[clip_index], bool) else {}),
                        **({"start_time_beats": float(arrangement_starts[clip_index])} if clip_index < len(arrangement_starts) and isinstance(arrangement_starts[clip_index], (int, float)) and not isinstance(arrangement_starts[clip_index], bool) else {}),
                    }
                    for clip_index in range(arrangement_count)
                ]
            sends: list[dict[str, Any]] = []
            for return_track in return_tracks:
                args = values[cursor]
                cursor += 1
                # ``get/send`` echoes both identifiers: ``track_index,
                # send_index, value``.  Do not let the echoed send index be
                # mistaken for a gain value (unlike one-identifier track
                # properties above).
                send_values = _strip_prefix(args or [], 2)
                value = send_values[-1] if send_values else None
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    sends.append({
                        "index": return_track["index"],
                        "return_track_index": return_track["index"],
                        "return_track_name": return_track["name"],
                        "value": float(value),
                    })
            if return_tracks_available and all(value is not None for value in values[cursor - len(return_tracks):cursor]):
                capability_flags["track_sends"] = True
                track["sends"] = sends
        tracks_by_index = {
            item.get("index"): item for item in tracks
            if isinstance(item.get("index"), int)
        }
        for track in tracks:
            group_track_index = track.get("group_track_index")
            group_track = tracks_by_index.get(group_track_index)
            if isinstance(group_track, dict):
                track["group_track_name"] = str(group_track.get("name", ""))
        state["understanding_detail"] = "routing_sends_clip_inventory_groups"
        state["understanding_capabilities"] = capability_flags
        state["read_only"] = True
        return state

    def get_tracks(self) -> Dict[str, Any]:
        state = self.query_session_state()
        result = {"success": state.get("status") == "connected", "tracks": state.get("tracks", [])}
        if state.get("error"):
            result["error"] = state["error"]
        return result

    def set_selected_track(self, track_index: int) -> bool:
        """Focus one exact track in Live's current view."""
        if int(track_index) < 0:
            return False
        return self._send_only("/live/view/set/selected_track", [int(track_index)])

    def _kenn_json(self, address: str, args: list[Any]) -> dict[str, Any]:
        values = self._query_args(address, args)
        if not values:
            return {"success": False, "error": "The running AbletonOSC does not answer this KENN read; deploy and reload it."}
        try:
            payload = json.loads(str(values[-1]))
        except (TypeError, ValueError):
            return {"success": False, "error": "AbletonOSC returned an unreadable KENN payload."}
        if not isinstance(payload, dict):
            return {"success": False, "error": "AbletonOSC returned an unexpected KENN payload."}
        if payload.get("error"):
            return {"success": False, **payload}
        return {"success": True, **payload}

    def get_bus_mixer(self, kind: str, index: int = -1) -> dict[str, Any]:
        """Mixer and device names for a return track (``kind='return'``) or the master."""
        return self._kenn_json("/live/kenn/get/bus_mixer", [str(kind), int(index)])

    def get_device_tree(self, kind: str, index: int = -1) -> dict[str, Any]:
        """Device chain for a track, return, or master, including rack chains (depth 3)."""
        return self._kenn_json("/live/kenn/get/device_tree", [str(kind), int(index)])

    def get_bus_device_parameters(self, kind: str, index: int, device_index: int) -> dict[str, Any]:
        """Every parameter of one device with display string and automation state."""
        return self._kenn_json("/live/kenn/get/device_parameters", [str(kind), int(index), int(device_index)])

    def get_remote_script_version(self) -> dict[str, Any]:
        """Deploy stamp of the running AbletonOSC (see tooling/scripts/deploy_abletonosc.py)."""
        values = self._query_args("/live/kenn/version")
        if not values:
            return {"success": False, "error": "The running AbletonOSC has no KENN version endpoint; deploy and reload it."}
        content_hash = str(values[0])
        if content_hash == "unstamped":
            return {"success": False, "error": "The running AbletonOSC was not installed by KENN's deploy tool."}
        return {"success": True, "content_hash": content_hash,
                "git_commit": str(values[1]) if len(values) > 1 else "",
                "deployed_at": str(values[2]) if len(values) > 2 else ""}

    def get_selected_device(self) -> dict[str, Any]:
        """Read the exact selected track/device pair from Live's view."""
        values = self._query_args("/live/view/get/selected_device")
        if not values or len(values) < 2:
            return {"success": False, "error": "AbletonOSC returned no exact selected device."}
        try:
            track_index, device_index = int(values[0]), int(values[1])
        except (TypeError, ValueError):
            return {"success": False, "error": "AbletonOSC returned an invalid selected-device identity."}
        if track_index < 0 or device_index < 0:
            return {"success": False, "error": "No device on a regular track is selected in Live."}
        return {"success": True, "track_index": track_index, "device_index": device_index}

    def set_selected_device(self, track_index: int, device_index: int) -> bool:
        """Focus one exact device in one exact Live track."""
        if int(track_index) < 0 or int(device_index) < 0:
            return False
        return self._send_only("/live/view/set/selected_device", [int(track_index), int(device_index)])

    def get_track_send(self, track_index: int, send_index: int) -> Optional[float]:
        """Real, exact send level (0.0-1.0 normalized) from one track to one
        return track, addressed by the return track's positional index
        (send 0 -> return track 0, etc. -- the same mapping Ableton itself
        uses for its per-track send sliders)."""
        values = self._device_values("/live/track/get/send", int(track_index), int(send_index))
        if not values:
            return None
        try:
            return float(values[0])
        except (TypeError, ValueError):
            return None

    def set_track_send(self, track_index: int, send_index: int, value: float) -> bool:
        return self._send_only("/live/track/set/send", [int(track_index), int(send_index), float(value)])

    def get_track_has_midi_input(self, track_index: int) -> Optional[bool]:
        value = self._track_scalar("/live/track/get/has_midi_input", int(track_index))
        return None if value is None else bool(value)

    def _send_track_property(self, name: str, track_index: int, value: Any) -> bool:
        return self._send_only(f"/live/track/set/{name}", [int(track_index), value])

    def set_track_volume(self, track_index: int, volume: float) -> bool:
        return self._send_track_property("volume", track_index, max(0.0, min(1.0, float(volume))))

    def set_track_pan(self, track_index: int, pan: float) -> bool:
        return self._send_track_property("panning", track_index, max(-1.0, min(1.0, float(pan))))

    def set_track_mute(self, track_index: int, muted: bool) -> bool:
        return self._send_track_property("mute", track_index, bool(muted))

    def set_track_solo(self, track_index: int, soloed: bool) -> bool:
        return self._send_track_property("solo", track_index, bool(soloed))

    def set_track_arm(self, track_index: int, armed: bool) -> bool:
        return self._send_track_property("arm", track_index, bool(armed))

    def set_track_name(self, track_index: int, name: str) -> bool:
        """Set one exact Live track name through AbletonOSC."""
        return self._send_track_property("name", track_index, str(name))

    def set_device_parameter(self, track_index: int, device_index: int, parameter_index: int, value: float) -> bool:
        return self._send_only("/live/device/set/parameter/value", [int(track_index), int(device_index), int(parameter_index), float(value)])

    def get_device_parameters(self, track_index: int, device_index: int) -> Dict[str, Any]:
        batched = self._query_many([
            ("/live/device/get/parameters/name", [int(track_index), int(device_index)]),
            ("/live/device/get/parameters/value", [int(track_index), int(device_index)]),
            ("/live/device/get/parameters/min", [int(track_index), int(device_index)]),
            ("/live/device/get/parameters/max", [int(track_index), int(device_index)]),
            ("/live/device/get/parameters/is_quantized", [int(track_index), int(device_index)]),
            ("/live/device/get/name", [int(track_index), int(device_index)]),
        ])
        names = _strip_prefix(batched[0] or [], 2) if batched[0] is not None else None
        values = _strip_prefix(batched[1] or [], 2) if batched[1] is not None else None
        minimums = _strip_prefix(batched[2] or [], 2) if batched[2] is not None else None
        maximums = _strip_prefix(batched[3] or [], 2) if batched[3] is not None else None
        quantized = _strip_prefix(batched[4] or [], 2) if batched[4] is not None else None
        device_name_args = batched[5]
        if names is None or values is None or minimums is None or maximums is None or device_name_args is None:
            return {"success": False, "error": "No complete response from AbletonOSC for that device."}
        device_name = str(_single_value(device_name_args) or f"Device {device_index}")
        parameters: list[dict[str, Any]] = []
        for index, name in enumerate(names):
            value = values[index] if index < len(values) else None
            minimum = minimums[index] if index < len(minimums) else 0.0
            maximum = maximums[index] if index < len(maximums) else 1.0
            parameter = {
                "index": index,
                "name": str(name),
                "value": value,
                "min": minimum,
                "max": maximum,
                "readable": value is not None,
            }
            # Older/custom AbletonOSC installs may not expose the optional
            # quantization list. Preserve the existing response shape there;
            # the upstream handler reports it when available.
            if quantized is not None and index < len(quantized):
                parameter["quantized"] = bool(quantized[index])
            parameters.append(parameter)
        return {"success": True, "device_name": device_name, "parameters": parameters}

    def get_device_parameter(self, track_index: int, device_index: int, parameter_index: int) -> Dict[str, Any]:
        info = self.get_device_parameters(track_index, device_index)
        if not info.get("success"):
            return info
        parameters = info.get("parameters", [])
        if parameter_index < 0 or parameter_index >= len(parameters):
            return {"success": False, "error": "Parameter index out of range"}
        return {"success": True, "device_name": info.get("device_name", ""), "parameter": parameters[parameter_index]}

    def get_device_parameter_value_string(
        self, track_index: int, device_index: int, parameter_index: int
    ) -> Dict[str, Any]:
        """Read Ableton's UI-formatted value for one device parameter.

        The bulk parameter API exposes normalized/raw values and ranges. The
        value-string endpoint is the standard AbletonOSC read that shows the
        same units Ableton displays, so keep it targeted and opt-in rather than
        adding one extra OSC round trip per parameter to every matrix request.
        """
        if min(int(track_index), int(device_index), int(parameter_index)) < 0:
            return {"success": False, "error": "indices must be non-negative"}
        args = self._query_args(
            "/live/device/get/parameter/value_string",
            [int(track_index), int(device_index), int(parameter_index)],
        )
        if args is None or len(args) < 4:
            return {"success": False, "error": "No value-string response from AbletonOSC."}
        return {
            "success": True,
            "track_index": int(track_index),
            "device_index": int(device_index),
            "parameter_index": int(parameter_index),
            "value_string": str(args[-1]),
        }

    def load_clip(self, track_index: int, clip_slot_index: int, file_path: str) -> bool:
        return self._send_only("/live/clip/load", [int(track_index), int(clip_slot_index), str(file_path)])

    def launch_clip(self, track_index: int, clip_slot_index: int) -> bool:
        return self._send_only("/live/clip_slot/fire", [int(track_index), int(clip_slot_index)])

    def stop_clip(self, track_index: int, clip_slot_index: int) -> bool:
        return self._send_only("/live/clip_slot/stop", [int(track_index), int(clip_slot_index)])

    def get_clip_playback_state(self, track_index: int, clip_slot_index: int) -> Dict[str, Any]:
        """Read the exact Session View clip's playback flags.

        AbletonOSC exposes these as clip reads rather than acknowledgements for
        ``fire``/``stop``.  KENN therefore treats this readback as the only
        evidence that a supervised audition actually started or stopped.
        """
        track_index = int(track_index)
        clip_slot_index = int(clip_slot_index)
        if min(track_index, clip_slot_index) < 0:
            return {"success": False, "error": "track and clip-slot indices must be non-negative"}
        playing_args = self._query_args("/live/clip_slot/get/is_playing", [track_index, clip_slot_index])
        triggered_args = self._query_args("/live/clip_slot/get/is_triggered", [track_index, clip_slot_index])
        if playing_args is None or triggered_args is None:
            return {"success": False, "error": "Incomplete clip playback readback from AbletonOSC."}
        return {
            "success": True,
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "is_playing": bool(_single_value(playing_args)),
            "is_triggered": bool(_single_value(triggered_args)),
        }

    def get_transport_state(self) -> Dict[str, Any]:
        """Read the song transport state as corroborating Live evidence."""
        args = self._query_args("/live/song/get/is_playing")
        if args is None:
            return {"success": False, "error": "No transport readback from AbletonOSC."}
        return {"success": True, "is_playing": bool(_single_value(args))}

    def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> Dict[str, Any]:
        """Read one exact Session View clip slot and its bounded MIDI notes."""
        track_index = int(track_index)
        clip_slot_index = int(clip_slot_index)
        if min(track_index, clip_slot_index) < 0:
            return {"success": False, "error": "track and clip-slot indices must be non-negative"}
        has_args = self._query_args("/live/clip_slot/get/has_clip", [track_index, clip_slot_index])
        if has_args is None:
            return {"success": False, "error": "No clip-slot response from AbletonOSC."}
        has_clip = bool(_single_value(has_args))
        result: Dict[str, Any] = {
            "success": True,
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "has_clip": has_clip,
            "is_midi_clip": False,
            "length": 0.0,
            "notes": [],
        }
        if not has_clip:
            return result
        midi_args = self._query_args("/live/clip/get/is_midi_clip", [track_index, clip_slot_index])
        length_args = self._query_args("/live/clip/get/length", [track_index, clip_slot_index])
        note_args = self._query_args("/live/clip/get/notes", [track_index, clip_slot_index])
        if midi_args is None or length_args is None or note_args is None:
            return {**result, "success": False, "error": "Incomplete MIDI clip readback from AbletonOSC."}
        result["is_midi_clip"] = bool(_single_value(midi_args))
        try:
            result["length"] = float(_single_value(length_args))
        except (TypeError, ValueError):
            return {**result, "success": False, "error": "AbletonOSC returned an invalid clip length."}
        values = list(note_args)
        if len(values) >= 2 and values[0] == track_index and values[1] == clip_slot_index:
            values = values[2:]
        if len(values) % 5:
            return {**result, "success": False, "error": "AbletonOSC returned malformed MIDI note data."}
        notes: list[dict[str, Any]] = []
        for offset in range(0, len(values), 5):
            pitch, start_time, duration, velocity, mute = values[offset:offset + 5]
            notes.append({
                "pitch": int(pitch),
                "start_time": float(start_time),
                "duration": float(duration),
                "velocity": int(velocity),
                "mute": bool(mute),
            })
        result["notes"] = notes
        return result

    def get_clip_slot_state(self, track_index: int, clip_slot_index: int) -> Dict[str, Any]:
        """Read one exact Session View slot for MIDI or audio duplication.

        Audio clip content is intentionally not read here: AbletonOSC exposes
        stable identity metadata (name, type, length), while the audio bytes
        remain owned by Live. MIDI notes are included because they are safely
        inspectable and make post-duplication verification substantially
        stronger.
        """
        track_index = int(track_index)
        clip_slot_index = int(clip_slot_index)
        if min(track_index, clip_slot_index) < 0:
            return {"success": False, "error": "track and clip-slot indices must be non-negative"}
        has_args = self._query_args("/live/clip_slot/get/has_clip", [track_index, clip_slot_index])
        if has_args is None:
            return {"success": False, "error": "No clip-slot response from AbletonOSC."}
        result: Dict[str, Any] = {
            "success": True,
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "has_clip": bool(_single_value(has_args)),
        }
        if not result["has_clip"]:
            return {**result, "clip_name": "", "is_midi_clip": False, "length": 0.0, "notes": []}
        name_args = self._query_args("/live/clip/get/name", [track_index, clip_slot_index])
        midi_args = self._query_args("/live/clip/get/is_midi_clip", [track_index, clip_slot_index])
        length_args = self._query_args("/live/clip/get/length", [track_index, clip_slot_index])
        if name_args is None or midi_args is None or length_args is None:
            return {**result, "success": False, "error": "Incomplete clip identity readback from AbletonOSC."}
        try:
            length = float(_single_value(length_args))
        except (TypeError, ValueError):
            return {**result, "success": False, "error": "AbletonOSC returned an invalid clip length."}
        result.update({
            "clip_name": str(_single_value(name_args) or ""),
            "is_midi_clip": bool(_single_value(midi_args)),
            "length": length,
            "notes": [],
        })
        if not result["is_midi_clip"]:
            return result
        note_args = self._query_args("/live/clip/get/notes", [track_index, clip_slot_index])
        if note_args is None:
            return {**result, "success": False, "error": "Incomplete MIDI note readback from AbletonOSC."}
        values = list(note_args)
        if len(values) >= 2 and values[0] == track_index and values[1] == clip_slot_index:
            values = values[2:]
        if len(values) % 5:
            return {**result, "success": False, "error": "AbletonOSC returned malformed MIDI note data."}
        result["notes"] = [
            {
                "pitch": int(values[offset]),
                "start_time": float(values[offset + 1]),
                "duration": float(values[offset + 2]),
                "velocity": int(values[offset + 3]),
                "mute": bool(values[offset + 4]),
            }
            for offset in range(0, len(values), 5)
        ]
        return result

    def create_midi_clip(self, track_index: int, clip_slot_index: int, length: float) -> bool:
        return self._send_only(
            "/live/clip_slot/create_clip",
            [int(track_index), int(clip_slot_index), float(length)],
        )

    def create_midi_track(self, insertion_index: int = -1) -> bool:
        """Request one MIDI track through AbletonOSC's standard Song API.

        AbletonOSC exposes ``Song.create_midi_track`` as a fire-and-forget
        method, so the guarded service must verify the new track by reading
        the post-write topology and ``has_midi_input``.  ``-1`` is accepted
        by AbletonOSC as append-to-end. KENN's guarded service uses this
        sentinel after binding the expected resulting index in its proposal.
        """
        insertion_index = int(insertion_index)
        if insertion_index < -1:
            return False
        return self._send_only("/live/song/create_midi_track", [insertion_index])

    def create_audio_track(self, insertion_index: int = -1) -> bool:
        """Request one audio track through AbletonOSC's standard Song API.

        ``-1`` is AbletonOSC's append-to-end sentinel. The guarded service
        verifies the resulting topology and confirms that Live reports no MIDI
        input for the new track before returning success.
        """
        insertion_index = int(insertion_index)
        if insertion_index < -1:
            return False
        return self._send_only("/live/song/create_audio_track", [insertion_index])

    def create_return_track(self) -> bool:
        """Append one return track through AbletonOSC's Song API.

        The endpoint is fire-and-forget; callers must verify the resulting
        return-track count and identity through ``get_return_tracks``.
        """
        return self._send_only("/live/song/create_return_track", [])

    def set_return_track_name(self, return_track_index: int, name: str) -> bool:
        """Set one exact return-track name through the vendored Remote Script."""
        if int(return_track_index) < 0 or not str(name).strip():
            return False
        return self._send_only("/live/song/set/return_track_name", [int(return_track_index), str(name)])

    def add_midi_notes(self, track_index: int, clip_slot_index: int, notes: list[dict[str, Any]]) -> bool:
        args: list[Any] = [int(track_index), int(clip_slot_index)]
        for note in notes:
            args.extend([
                int(note["pitch"]),
                float(note["start_time"]),
                float(note["duration"]),
                int(note["velocity"]),
                bool(note.get("mute", False)),
            ])
        return self._send_only("/live/clip/add/notes", args)

    def remove_all_midi_notes(self, track_index: int, clip_slot_index: int) -> bool:
        """Remove all notes from one exact MIDI clip.

        The vendored Remote Script treats ``/live/clip/remove/notes`` with no
        range arguments as an all-notes removal. Callers must bind and verify
        the current note set before using this structural edit.
        """
        return self._send_only("/live/clip/remove/notes", [int(track_index), int(clip_slot_index)])

    def delete_midi_clip(self, track_index: int, clip_slot_index: int) -> bool:
        return self._send_only("/live/clip_slot/delete_clip", [int(track_index), int(clip_slot_index)])

    def delete_clip(self, track_index: int, clip_slot_index: int) -> bool:
        """Delete either a MIDI or audio clip from one exact Session slot."""
        return self._send_only("/live/clip_slot/delete_clip", [int(track_index), int(clip_slot_index)])

    def duplicate_clip_to(
        self,
        source_track_index: int,
        source_clip_slot_index: int,
        target_track_index: int,
        target_clip_slot_index: int,
    ) -> bool:
        """Ask AbletonOSC to duplicate one clip into an empty target slot."""
        values = [
            int(source_track_index), int(source_clip_slot_index),
            int(target_track_index), int(target_clip_slot_index),
        ]
        if min(values) < 0:
            return False
        return self._send_only("/live/clip_slot/duplicate_clip_to", values)

    def set_clip_name(self, track_index: int, clip_slot_index: int, name: str) -> bool:
        """Set one exact Session View clip's name."""
        track_index = int(track_index)
        clip_slot_index = int(clip_slot_index)
        clean_name = str(name).strip()
        if min(track_index, clip_slot_index) < 0 or not clean_name:
            return False
        return self._send_only("/live/clip/set/name", [track_index, clip_slot_index, clean_name[:128]])

    def import_sample_to_clip_slot(self, track_index: int, clip_slot_index: int, absolute_path: str) -> Dict[str, Any]:
        """Import one real audio file from disk into one exact, empty clip slot.

        Depends on ``/live/track/import_sample`` in the vendored AbletonOSC
        fork (added 2026-09-06, closing the "confirmed blocked" Live sample
        import gap -- see docs/reports/ABLETON_ASSISTANT_CURRENT_STATE.md). The
        Remote Script finds the file through Ableton's own Browser tree
        (registering its containing folder as a Place if not already
        browsable), loads it, and reports the real created clip's name back
        -- this call never guesses whether the import succeeded.
        """
        args = self._query_args(
            "/live/track/import_sample",
            [int(track_index), int(clip_slot_index), str(absolute_path)],
            timeout=15.0,
        )
        if args is None or len(args) < 3:
            return {"success": False, "error": "No response from AbletonOSC."}
        echoed_track, echoed_slot, success_flag, *rest = args
        message = str(rest[0]) if rest else ""
        if not bool(success_flag):
            return {"success": False, "error": message or "AbletonOSC reported the import failed."}
        return {"success": True, "clip_name": message}

    def launch_scene(self, scene_index: int) -> bool:
        return self._send_only("/live/scene/fire", [int(scene_index)])

    def stop_clip_slot(self, track_index: int, clip_slot_index: int) -> bool:
        return self._send_only("/live/clip_slot/stop", [int(track_index), int(clip_slot_index)])

    def get_scene_playback_state(self, scene_index: int) -> Dict[str, Any]:
        """Best-effort post-fire readback for one exact scene.

        Ableton's Scene object has no stable "is_playing" property (only its
        clips do); ``is_triggered`` is the same class of transient signal
        already trusted for clip-slot audition readback elsewhere in this
        client. This is the only observable evidence that a scene fire was
        actually received by Live.
        """
        scene_index = int(scene_index)
        if scene_index < 0:
            return {"success": False, "error": "scene index must be non-negative"}
        triggered_args = self._query_args("/live/scene/get/is_triggered", [scene_index])
        if triggered_args is None:
            return {"success": False, "error": "Incomplete scene playback readback from AbletonOSC."}
        return {
            "success": True,
            "scene_index": scene_index,
            "is_triggered": bool(_single_value(triggered_args)),
        }

    def create_scene(self, name: str = "") -> Dict[str, Any]:
        before = self._query_args("/live/song/get/num_scenes") or []
        if not self._send_only("/live/song/create_scene", [-1]):
            return {"success": False, "error": "Not connected to AbletonOSC"}
        index = int(before[0]) if before and isinstance(before[0], (int, float)) else -1
        if name and index >= 0:
            self._send_only("/live/scene/set/name", [index, str(name)])
        return {"success": True, "scene_index": index, "scene_name": str(name)}

    def insert_device_with_result(self, track_index: int, device_name: str, insertion_index: int) -> Dict[str, Any]:
        """Use AbletonOSC's open insert-device extension endpoint.

        The upstream AbletonOSC master exposes the object-model transport but
        device insertion is supplied by its `insert_device` extension. KENN
        keeps this operation confirmation-gated above the client.
        """
        _, response = self._request_response(
            "/live/track/insert_device",
            [int(track_index), str(device_name), int(insertion_index)],
        )
        if response is None:
            return {"success": False, "error": "No response from AbletonOSC; install the insert_device extension."}
        args = self._response_args(response)
        created_index = args[-1] if args else insertion_index
        if isinstance(created_index, (int, float)) and int(created_index) < 0:
            return {"success": False, "error": f"AbletonOSC could not find device '{device_name}'."}
        return {"success": True, "track_index": int(track_index), "device_index": int(created_index), "device_name": str(device_name)}

    def create_device(self, track_index: int, device_name: str) -> bool:
        return bool(self.insert_device_with_result(track_index, device_name, 0).get("success"))

    def remove_device_with_result(self, track_index: int, device_index: int, device_name: str) -> Dict[str, Any]:
        if not self._send_only("/live/track/delete_device", [int(track_index), int(device_index)]):
            return {"success": False, "error": "Could not send device removal to AbletonOSC."}
        return {"success": True, "track_index": int(track_index), "device_index": int(device_index), "device_name": str(device_name)}

    def configure_sidechain(self, bass_track_index: int, kick_track_index: int) -> bool:
        logger.warning("Sidechain configuration is not part of the standard AbletonOSC contract yet.")
        return False

    def start_playback(self) -> bool:
        return self._send_only("/live/song/start_playing")

    def stop_playback(self) -> bool:
        return self._send_only("/live/song/stop_playing")

    def set_tempo(self, bpm: float) -> bool:
        return self._send_only("/live/song/set/tempo", [max(20.0, min(999.0, float(bpm)))])

    def duplicate_clip_to_arrangement(self, track_index: int, clip_slot_index: int, destination_time_beats: float) -> bool:
        """Duplicate a Session View clip into the Arrangement timeline at the specified beat."""
        return self._send_only(
            "/live/clip/duplicate_to_arrangement",
            [int(track_index), int(clip_slot_index), float(destination_time_beats)],
        )

    def set_clip_automation(
        self,
        track_index: int,
        clip_slot_index: int,
        device_index: int,
        parameter_index: int,
        points: list[dict[str, Any]],
    ) -> bool:
        """Write automation envelope points into a Session View clip."""
        return self._send_only(
            "/live/clip/set_automation",
            [int(track_index), int(clip_slot_index), int(device_index), int(parameter_index), points],
        )

    def get_arrangement_clips(self, track_index: int) -> list[dict[str, Any]]:
        """Query all clips present in a track's Arrangement timeline."""
        args = self._query_args("/live/track/get/arrangement_clips", [int(track_index)])
        if args is None:
            return []
        # When returned as array or JSON payload in bridge
        if isinstance(args, list) and len(args) == 1 and isinstance(args[0], list):
            return args[0]
        return list(args) if isinstance(args, list) else []

    def create_group_track(self, insertion_index: int = -1) -> bool:
        """Create a native Group Track (sub-mix bus) in the Live Song."""
        return self._send_only("/live/song/create_group_track", [int(insertion_index)])

    def map_rack_macro(self, track_index: int, device_index: int, macro_index: int, target_param_index: int) -> bool:
        """Map a Rack macro to a target parameter."""
        return self._send_only(
            "/live/rack/map_macro",
            [int(track_index), int(device_index), int(macro_index), int(target_param_index)],
        )

    def get_rack_macros(self, track_index: int, device_index: int) -> list[dict[str, Any]]:
        """Query macro knobs on a Rack device."""
        args = self._query_args("/live/rack/get/macros", [int(track_index), int(device_index)])
        if args is None:
            return []
        if isinstance(args, list) and len(args) == 1 and isinstance(args[0], list):
            return args[0]
        return list(args) if isinstance(args, list) else []

    def set_track_output_routing(self, track_index: int, routing_type: str) -> bool:
        """Set track audio output routing."""
        return self._send_only("/live/track/set/output_routing", [int(track_index), str(routing_type)])

    def set_track_input_routing(self, track_index: int, routing_type: str) -> bool:
        """Set track audio input routing."""
        return self._send_only("/live/track/set/input_routing", [int(track_index), str(routing_type)])

    def set_track_freeze(self, track_index: int, frozen: bool) -> bool:
        """Freeze or unfreeze track to manage CPU load."""
        return self._send_only("/live/track/set/freeze", [int(track_index), bool(frozen)])

    def store_rack_variation(self, track_index: int, device_index: int) -> bool:
        """Store the current Macro parameter state as a new Rack Macro Variation snapshot."""
        return self._send_only("/live/rack/store_variation", [int(track_index), int(device_index)])

    def recall_rack_variation(self, track_index: int, device_index: int, variation_index: int) -> bool:
        """Recall a stored Rack Macro Variation snapshot by index."""
        return self._send_only("/live/rack/recall_variation", [int(track_index), int(device_index), int(variation_index)])

    def get_track_realtime_meters(self, track_index: int) -> dict[str, Any]:
        """Read instantaneous post-fader meter values (left and right channel)."""
        args = self._query_args("/live/track/get/meters", [int(track_index)])
        if args is None:
            return {"track_index": track_index, "output_meter_left": None, "output_meter_right": None}
        if isinstance(args, dict):
            return args
        if isinstance(args, list) and len(args) == 1 and isinstance(args[0], dict):
            return args[0]
        return {"track_index": track_index, "output_meter_left": None, "output_meter_right": None}

    def launch_clip(self, track_index: int, clip_slot_index: int) -> bool:
        """Fire/launch a Session View clip slot."""
        return self._send_only("/live/clip_slot/fire", [int(track_index), int(clip_slot_index)])

    def stop_clip(self, track_index: int, clip_slot_index: int) -> bool:
        """Stop a playing Session View clip slot."""
        return self._send_only("/live/clip_slot/stop", [int(track_index), int(clip_slot_index)])

    def delete_clip_slot(self, track_index: int, clip_slot_index: int) -> bool:
        """Delete clip in slot (must be confirmation gated)."""
        return self._send_only("/live/clip_slot/delete_clip", [int(track_index), int(clip_slot_index)])

    def duplicate_loop(self, track_index: int, clip_slot_index: int) -> bool:
        """Duplicate loop length of a Session View clip."""
        return self._send_only("/live/clip/duplicate_loop", [int(track_index), int(clip_slot_index)])

    def set_clip_warp_mode(self, track_index: int, clip_slot_index: int, warp_mode: int) -> bool:
        """Set warp mode (0: Beats, 1: Tones, 2: Texture, 3: Re-Pitch, 4: Complex, 5: Complex Pro)."""
        return self._send_only("/live/clip/set/warp_mode", [int(track_index), int(clip_slot_index), int(warp_mode)])

    def set_clip_pitch_coarse(self, track_index: int, clip_slot_index: int, semitones: int) -> bool:
        """Set clip coarse transpose in semitones (-48 to +48)."""
        return self._send_only("/live/clip/set/pitch_coarse", [int(track_index), int(clip_slot_index), int(semitones)])

    def load_browser_preset(self, track_index: int, preset_name: str) -> dict[str, Any]:
        """Load an Ableton device or rack preset (.adv/.adg) via browser."""
        args = self._query_args("/live/browser/load_preset", [int(track_index), str(preset_name)])
        if args is None:
            return {"success": False, "error": "No response from AbletonOSC bridge."}
        if isinstance(args, dict):
            return args
        if isinstance(args, list) and len(args) == 1 and isinstance(args[0], dict):
            return args[0]
        return {"success": True, "track_index": track_index, "preset_name": preset_name}


# Do not claim UDP 11001 during module import. This makes CLI tools and test
# runners safe to import while a companion process is already running; the
# production singleton binds lazily on its first exchange.  Operators can
# explicitly select the read-only Control Deck MCP backend; a bad MCP
# configuration fails closed and never silently falls back to OSC.
from kenn.core.live_backend_factory import create_live_backend


live_client = create_live_backend(
    lambda: AbletonOSCClient(defer_bind=True, enable_circuit_breaker=True)
)


__all__ = [
    "AbletonOSCClient", "live_client", "CAPABILITY_SCHEMA", "DEVICE_MATRIX_SCHEMA",
    "DEVICE_FAMILY_PROFILES", "READ_ENDPOINTS", "WRITE_ENDPOINTS",
]
