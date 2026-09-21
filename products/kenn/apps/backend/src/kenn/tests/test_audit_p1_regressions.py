"""Regression coverage for P1 defects found in the KENN product audit."""

from __future__ import annotations

import socket
import struct
import threading

import pytest

import kenn.core.confirmation as confirmation
from kenn.ableton_osc_bridge import AbletonOSCClient
from kenn.abletonosc_protocol import (
    MAX_OSC_BUNDLE_DEPTH,
    MAX_OSC_PACKET_BYTES,
    OSCProtocolError,
    decode_packet,
    encode_message,
)
from kenn.core.generative_midi import (
    apply_audiogen_groove,
    detect_scale_from_notes,
    generate_audiogen_bassline,
    generate_chord_progression,
    generate_drum_pattern,
    generate_euclidean_rhythm,
)
from kenn.core.live_action_service import LiveActionService
from kenn.routes.midi_handler import (
    handle_post_midi_bassline,
    handle_post_midi_detect_scale,
    handle_post_midi_groove,
)
from kenn.server import Handler


class _JSONHandler:
    def __init__(self) -> None:
        self.status: int | None = None
        self.payload: dict | None = None

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def _assert_valid_notes(notes: list[dict], clip_length: float) -> None:
    assert notes
    assert all(0 <= note["pitch"] <= 127 for note in notes)
    assert all(1 <= note["velocity"] <= 127 for note in notes)
    assert all(note["start_time"] >= 0 and note["duration"] > 0 for note in notes)
    assert all(note["start_time"] + note["duration"] <= clip_length + 1e-9 for note in notes)


def test_generators_reject_nonfinite_out_of_range_and_unbounded_inputs() -> None:
    with pytest.raises(ValueError, match="pitch"):
        generate_euclidean_rhythm(4, 8, pitch=200)
    with pytest.raises(ValueError, match="steps"):
        generate_euclidean_rhythm(1, 0)
    with pytest.raises(ValueError, match="beats_per_chord"):
        generate_chord_progression(beats_per_chord=float("nan"))
    with pytest.raises(ValueError, match="MIDI pitch"):
        generate_chord_progression(octave=9, voicing="spread")
    with pytest.raises(ValueError, match="bars"):
        generate_drum_pattern(bars=10_000)
    with pytest.raises(ValueError, match="note 0 pitch"):
        detect_scale_from_notes([{"pitch": "not-a-pitch"}])


def test_frontend_midi_route_contracts_are_reachable_and_bounded() -> None:
    bass_handler = _JSONHandler()
    handle_post_midi_bassline(
        bass_handler,
        {"scale": "F:minor", "style": "rolling_16th", "bars": 2},
    )
    assert bass_handler.status == 200
    assert bass_handler.payload is not None
    _assert_valid_notes(bass_handler.payload["notes"], 8.0)
    assert bass_handler.payload["notes"][0]["pitch"] == 41

    groove_handler = _JSONHandler()
    handle_post_midi_groove(
        groove_handler,
        {
            "notes": [{"pitch": 41, "start_time": 0.25, "duration": 0.2, "velocity": 100}],
            "template": "lofi_swing",
            "swing_pct": 35,
            "laidback_ms": 6,
            "jitter_pct": 15,
        },
    )
    assert groove_handler.status == 200
    assert groove_handler.payload is not None
    _assert_valid_notes(groove_handler.payload["notes"], 4096.0)

    bad_handler = _JSONHandler()
    handle_post_midi_detect_scale(bad_handler, {"notes": [{"pitch": 999}]})
    assert bad_handler.status == 400
    assert bad_handler.payload and bad_handler.payload["ok"] is False


def test_groove_and_bassline_aliases_preserve_valid_midi() -> None:
    source = [{"pitch": 36, "start_time": 0.25, "duration": 0.2, "velocity": 100}]
    humanized = apply_audiogen_groove(
        source,
        groove_template="edm_shuffle",
        swing_pct=50,
        laidback_ms=-5,
        velocity_jitter_pct=10,
        seed=7,
    )
    _assert_valid_notes(humanized, 4096.0)
    for style in ("rolling_16th", "syncopated_groove", "sub_punch", "offbeat_stab"):
        _assert_valid_notes(
            generate_audiogen_bassline(root="F", scale_name="minor", style=style, bars=1, octave=2),
            4.0,
        )


def _bundle(child: bytes) -> bytes:
    return b"#bundle\x00" + (b"\x00" * 8) + struct.pack(">i", len(child)) + child


def test_osc_decoder_rejects_oversized_and_excessively_nested_packets() -> None:
    with pytest.raises(OSCProtocolError, match="exceeds"):
        decode_packet(b"x" * (MAX_OSC_PACKET_BYTES + 1))

    packet = encode_message("/live/test", [1])
    for _ in range(MAX_OSC_BUNDLE_DEPTH + 1):
        packet = _bundle(packet)
    with pytest.raises(OSCProtocolError, match="nesting"):
        decode_packet(packet)


def test_batch_transport_drops_ambiguous_unidentified_replies() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(1.0)
        received: list[tuple[str, list]] = []
        address: tuple[str, int] | None = None
        try:
            while len(received) < 2:
                raw, address = server.recvfrom(65_507)
                received.extend(decode_packet(raw))
            assert address is not None
            # Same response address, no echoed track index: neither reply can
            # safely be associated with request [0] or request [1].
            server.sendto(encode_message("/live/track/get/volume", [0.25]), address)
            server.sendto(encode_message("/live/track/get/volume", [0.75]), address)
        finally:
            stop.set()
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = AbletonOSCClient(send_port=port, recv_port=0, query_timeout=0.1)
    try:
        responses = client._request_responses_many([
            ("/live/track/get/volume", [0]),
            ("/live/track/get/volume", [1]),
        ])
        assert responses == [None, None]
    finally:
        client.close()
        stop.wait(1.0)
        thread.join(timeout=1.0)


def test_mutation_snapshots_force_fresh_live_state() -> None:
    class _FreshClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def query_session_state(self, **kwargs) -> dict:
            self.calls.append(kwargs)
            return {"status": "connected", "tracks": []}

    fake = _FreshClient()
    assert LiveActionService(fake).snapshot() == {"status": "connected", "tracks": []}
    assert fake.calls == [{"include_mixer": True, "force_refresh": True}]

    client = AbletonOSCClient(defer_bind=True)
    calls: list[dict] = []
    client.query_session_state = lambda **kwargs: calls.append(kwargs) or {  # type: ignore[method-assign]
        "status": "connected",
        "tracks": [],
    }
    try:
        client.query_session_topology()
        assert calls == [{"include_mixer": False, "force_refresh": True}]
    finally:
        client.close()


def test_confirmation_replay_registry_fails_closed_at_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = set(confirmation._USED_TOKENS)
    confirmation._USED_TOKENS.clear()
    monkeypatch.setattr(confirmation, "MAX_USED_TOKENS", 2)
    kwargs = {"session_id": "bounded", "service_id": "test", "text": "mutate"}
    try:
        first, _ = confirmation.issue_confirmation(**kwargs)
        second, _ = confirmation.issue_confirmation(**kwargs)
        third, _ = confirmation.issue_confirmation(**kwargs)
        assert confirmation.consume_confirmation(first, **kwargs)
        assert confirmation.consume_confirmation(second, **kwargs)
        assert not confirmation.consume_confirmation(third, **kwargs)
        assert not confirmation.consume_confirmation(first, **kwargs)
        assert len(confirmation._USED_TOKENS) == 2
    finally:
        confirmation._USED_TOKENS.clear()
        confirmation._USED_TOKENS.update(previous)


def test_http_body_write_treats_client_disconnect_as_normal_closure() -> None:
    class _DisconnectedStream:
        def write(self, _body: bytes) -> None:
            raise BrokenPipeError("client left")

        def flush(self) -> None:
            raise AssertionError("flush must not run after a failed write")

    class _HandlerStub:
        wfile = _DisconnectedStream()
        close_connection = False

    handler = _HandlerStub()
    assert Handler._write_body(handler, b"payload", flush=True) is False
    assert handler.close_connection is True
