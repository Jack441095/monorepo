from __future__ import annotations

from kenn.core.audiogen_artifacts import SCHEMA, midi_import_payload, midi_preview_metadata, safe_artifact_metadata, validate_artifact_metadata
from kenn.core.audiogen_midi import artifact_from_event_payload
from kenn.core.audiogen_context import build_live_generation_context
from kenn.server_payloads import public_audiogen_result


def _midi(**overrides: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "artifact_id": "midi-1",
        "kind": "midi",
        "sha256": "a" * 64,
        "note_count": 48,
        "lowest_note": 36,
        "highest_note": 84,
        "bars": 16,
        "bpm": 124.0,
        "key": "A Minor",
        "path": "/private/path/should-not-be-forwarded.mid",
    }
    artifact.update(overrides)
    return artifact


def test_valid_midi_metadata_is_safe_and_bounded() -> None:
    result = validate_artifact_metadata(_midi())
    assert result["ok"] is True
    assert result["schema"] == SCHEMA

    safe = safe_artifact_metadata(_midi())
    assert safe["kind"] == "midi"
    assert safe["validation"]["ok"] is True
    assert "path" not in safe
    assert safe["preview"]["status"] == "unavailable"


def test_invalid_midi_metadata_fails_closed() -> None:
    result = validate_artifact_metadata(
        _midi(lowest_note=140, highest_note=20, bpm=999, sha256="not-a-digest")
    )
    assert result["ok"] is False
    assert any("lowest_note" in error for error in result["errors"])
    assert any("bpm" in error for error in result["errors"])
    assert any("sha256" in error for error in result["errors"])


def test_missing_optional_midi_metadata_is_a_warning_not_a_claim() -> None:
    result = validate_artifact_metadata({"kind": "midi"})
    assert result["ok"] is True
    assert result["warnings"]


def test_unknown_artifact_kind_is_rejected() -> None:
    result = validate_artifact_metadata({"kind": "live_import_command"})
    assert result["ok"] is False


def test_public_audiogen_result_keeps_safe_artifact_provenance() -> None:
    result = public_audiogen_result({"ok": True, "artifact": _midi(path="/private/file.mid")})
    assert result["artifact"]["validation"]["ok"] is True
    assert "path" not in result["artifact"]


def test_midi_import_payload_requires_bounded_events_and_explicit_length() -> None:
    artifact = _midi(
        note_count=2,
        length_beats=4,
        notes=[
            {"pitch": 60, "start_time": 0, "duration": 1, "velocity": 100},
            {"pitch": 67, "start_time": 2, "duration": 1, "velocity": 90},
        ],
    )
    imported = midi_import_payload(artifact)
    assert imported["ok"] is True
    assert imported["source_artifact_sha256"].startswith("sha256:")
    assert imported["length"] == 4.0
    assert len(imported["notes"]) == 2


def test_midi_import_payload_rejects_note_outside_clip() -> None:
    imported = midi_import_payload(_midi(
        length_beats=2,
        notes=[{"pitch": 60, "start_time": 1.5, "duration": 1, "velocity": 100}],
    ))
    assert imported["ok"] is False
    assert any("extends beyond" in error for error in imported["errors"])


def test_midi_preview_is_bounded_and_explicitly_not_audio_playback() -> None:
    preview = midi_preview_metadata(_midi(
        bars=2,
        length_beats=8,
        notes=[
            {"pitch": 60, "start_time": 0, "duration": 1, "velocity": 100},
            {"pitch": 67, "start_time": 4, "duration": 2, "velocity": 80},
        ],
    ))
    assert preview["status"] == "ready"
    assert preview["note_density_per_bar"] == 1.0
    assert preview["onset_count"] == 2
    assert preview["pitch_class_histogram"][0] == 1
    assert preview["pitch_class_histogram"][7] == 1
    assert preview["audition"]["status"] == "not_rendered"
    assert "not rendered or played" in preview["audition"]["limitation"]


def test_audiogen_symbolic_events_become_a_digest_bound_midi_artifact() -> None:
    result = artifact_from_event_payload({
        "ok": True,
        "bars": 1,
        "beats_per_bar": 4,
        "section_duration_beats": 4.0,
        "events": [{
            "midi": 72,
            "notes": [72, 76],
            "start_beats": 0.0,
            "duration_beats": 0.5,
            "velocity": 106,
        }],
    }, artifact_id="audiogen-midi-test")
    assert result["ok"] is True
    artifact = result["artifact"]
    assert artifact["kind"] == "midi"
    assert artifact["sha256"].startswith("sha256:")
    assert len(artifact["notes"]) == 2
    safe = safe_artifact_metadata(artifact)
    assert safe["preview"]["status"] == "ready"
    assert safe["preview"]["audition"]["available"] is False


def test_audiogen_live_context_reports_tempo_without_retiming() -> None:
    context, error = build_live_generation_context(
        {
            "status": "connected",
            "tempo": 120.0,
            "signature_numerator": 4,
            "signature_denominator": 4,
            "root_note": 0,
            "scale_name": "Major",
            "selected_track_index": 1,
            "tracks": [{"index": 1, "name": "Bass MIDI", "devices": []}],
        },
        track_index=1,
        track_name="Bass MIDI",
        source_bpm=124.0,
    )
    assert error is None
    assert context is not None
    assert context["tempo_relationship"] == "different"
    assert context["timing_action"] == "preserve_symbolic_beats"
    assert context["adaptation"] == "none_required"
    assert context["time_signature"] == {"numerator": 4, "denominator": 4}
    assert context["live_key"] == {"root_note": 0, "scale_name": "Major"}
    assert "did not retime" in context["limitations"][0]


def test_audiogen_live_context_requires_exact_track_and_reports_unknown_source_tempo() -> None:
    context, error = build_live_generation_context(
        {
            "status": "connected",
            "tempo": 120.0,
            "signature_numerator": 4,
            "signature_denominator": 4,
            "root_note": 0,
            "scale_name": "Major",
            "tracks": [{"index": 1, "name": "Bass MIDI", "devices": []}],
        },
        track_index=1,
        track_name="Bass MIDI",
    )
    assert error is None
    assert context is not None
    assert context["tempo_relationship"] == "unknown"
    assert context["source_tempo_bpm"] is None

    missing, missing_error = build_live_generation_context(
        {"status": "connected", "tempo": 120.0, "tracks": []},
        track_index=1,
        track_name="Bass MIDI",
    )
    assert missing is None
    assert "not present exactly once" in (missing_error or "")
