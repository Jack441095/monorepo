"""Tests for Thursday Phase 5: Low-Latency Duplex Voice & Multimodal Visual Inspector."""



from thursday.multimodal import (
    VisualInspectionResult,
    inspect_image,
    is_image_path,
)
from thursday.resolver import resolve_request
from thursday.voice import StreamingVoicePipeline


def test_is_image_path():
    assert is_image_path("screenshot.png") is True
    assert is_image_path("invoice.pdf") is True
    assert is_image_path("audio.wav") is False
    assert is_image_path("notes.txt") is False


def test_inspect_image_daw_screenshot(tmp_path):
    img = tmp_path / "daw_session.png"
    img.write_text("mock image data")

    result = inspect_image(img, goal_hint="check tracks")

    assert isinstance(result, VisualInspectionResult)
    assert result.inspection_type == "daw_screenshot"
    assert "DAW multitrack" in result.summary
    assert result.detected_features["mixer_channels_visible"] is True


def test_inspect_image_spectrum_analyzer(tmp_path):
    img = tmp_path / "spectrum_analyzer_eq.png"
    img.write_text("mock image data")

    result = inspect_image(img)

    assert result.inspection_type == "spectrum_analyzer"
    assert "Frequency spectrum" in result.summary
    assert "low_end_tilt_db" in result.detected_features


def test_resolver_multimodal_integration(tmp_path):
    img = tmp_path / "invoice_jordan.jpg"
    img.write_text("mock invoice data")

    text = f"Check this {img}"
    resolved_text, resolved_entities = resolve_request(text, {})

    assert "multimodal_inspection" in resolved_entities
    assert resolved_entities["inspection_type"] == "invoice_document"


def test_streaming_voice_pipeline():
    pipeline = StreamingVoicePipeline(target_latency_ms=250.0)
    assert pipeline.push_audio_chunk(b"chunk1") is False  # inactive

    pipeline.start()
    assert pipeline.push_audio_chunk(b"chunk1") is True
    assert pipeline.push_audio_chunk(b"chunk2") is True

    c1 = pipeline.get_next_chunk(timeout=0.1)
    assert c1 == b"chunk1"

    c2 = pipeline.get_next_chunk(timeout=0.1)
    assert c2 == b"chunk2"

    pipeline.stop()
    assert pipeline.push_audio_chunk(b"chunk3") is False
