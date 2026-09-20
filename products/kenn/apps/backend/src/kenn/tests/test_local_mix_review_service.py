from __future__ import annotations

import json
import math
import stat
import struct
import wave

from kenn.core.local_mix_review_service import MAX_REVIEWS, LocalMixReviewService, compare_reference_audio


def _wav_bytes(*, amplitude: float = 0.99, sample_rate: int = 8000, seconds: int = 1, frequency_hz: float = 0.0) -> bytes:
    samples = [
        int(max(-1.0, min(1.0, amplitude * (math.sin(2 * math.pi * frequency_hz * index / sample_rate) if frequency_hz else 1.0))) * 32767)
        for index in range(sample_rate * seconds)
    ]
    payload = struct.pack("<" + "h" * len(samples), *samples)
    from io import BytesIO

    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(payload)
    return output.getvalue()


def test_local_service_creates_metadata_only_review_and_persists_it(tmp_path) -> None:
    runtime = tmp_path / "review-runtime"
    service = LocalMixReviewService(runtime)
    result = service.save_review(_wav_bytes(), "/private/session/master.wav", project_id_override="project-1")

    assert result["ok"] is True
    assert result["status"] == "completed"
    review_id = result["review_id"]
    review = result["review"]
    assert review["review_id"] == review_id
    assert review["source"]["filename"] == "master.wav"
    assert len(review["source"]["sha256"]) == 64
    assert review["audio_retained"] is False
    assert review["storage"] == "metadata_only"
    assert review["evidence"]["schema"] == "kenn.evidence.v1"
    assert review["evidence"]["source"] == "mix_review_upload"
    assert any(fact["name"] == "peak_dbfs" for fact in review["evidence"]["facts"])
    assert any(flag["label"] == "Headroom" for flag in review["flags"])
    assert "/private" not in json.dumps(review, sort_keys=True)

    restored = LocalMixReviewService(runtime)
    status = restored.mix_review_status(review_id)
    assert status["ok"] is True
    assert status["review"]["review_id"] == review_id
    assert restored.list_reviews(limit=1)[0]["review_id"] == review_id


def test_local_service_rejects_invalid_audio_without_creating_review(tmp_path) -> None:
    service = LocalMixReviewService(tmp_path / "runtime")
    result = service.save_review(b"not wav", "bad.wav")
    assert result["ok"] is False
    assert service.list_reviews() == []


def test_local_service_prunes_persisted_reviews_to_newest_bounded_set(tmp_path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    reviews = {
        f"review-{index:04d}": {
            "review_id": f"review-{index:04d}",
            "created_at": f"2026-09-07T00:{index // 60:02d}:{index % 60:02d}+00:00",
        }
        for index in range(MAX_REVIEWS + 3)
    }
    index_path = runtime / "reviews.json"
    index_path.write_text(json.dumps(reviews), encoding="utf-8")

    service = LocalMixReviewService(runtime)

    retained = service.list_reviews(limit=MAX_REVIEWS)
    assert len(retained) == 200  # public listing remains independently capped
    assert service.mix_review_status("review-0000")["ok"] is False
    assert service.mix_review_status("review-0002")["ok"] is False
    assert service.mix_review_status("review-0003")["ok"] is True
    on_disk = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(on_disk) == MAX_REVIEWS
    assert stat.S_IMODE(index_path.stat().st_mode) == 0o600


def test_reference_comparison_is_measured_in_memory_without_retaining_audio() -> None:
    result = compare_reference_audio(
        _wav_bytes(amplitude=0.2, frequency_hz=100), "mix.wav",
        _wav_bytes(amplitude=0.2, frequency_hz=3000), "reference.wav",
    )

    assert result["ok"] is True
    comparison = result["reference_comparison"]
    assert comparison["largest_spectral_difference"]["band"] in {"low", "upper_mid"}
    assert comparison["largest_ltas_difference"]["center_hz"] > 0
    assert comparison["ltas_40_band_deltas"]
    assert comparison["eq_bands"]
    assert comparison["pink_noise_reference"]["status"] == "complete"
    assert comparison["pink_noise_reference"]["largest_deviation"]["center_hz"] > 0
    assert result["audio_retained"] is False
    assert result["storage"] == "in_memory_only"
    assert "audio" not in json.dumps(result).lower().replace("audio_retained", "")


def test_reference_comparison_is_persisted_as_metadata_only_receipt(tmp_path) -> None:
    boundary = "kenn-boundary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="mix"; filename="mix.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + _wav_bytes(amplitude=0.2, frequency_hz=100)
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="reference"; filename="reference.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        + _wav_bytes(amplitude=0.2, frequency_hz=3000)
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    service = LocalMixReviewService(tmp_path / "runtime")
    result = service.handle_multipart_reference(f"multipart/form-data; boundary={boundary}", body)

    assert result["ok"] is True
    assert result["review_id"].startswith("reference-")
    review = service.mix_review_status(result["review_id"])["review"]
    assert review["reference_comparison"]["largest_ltas_difference"]["center_hz"] > 0
    assert review["reference_comparison"]["pink_noise_reference"]["status"] == "complete"
    assert "matching_gains_db" in review["reference_comparison"]
    assert "recommendations" in review["reference_comparison"]
    assert "eq8_preset_adv_base64" in review["reference_comparison"]
    assert review["storage"] == "metadata_only"
    assert review["audio_retained"] is False
    assert "audio" not in json.dumps(review).lower().replace("audio_retained", "")
