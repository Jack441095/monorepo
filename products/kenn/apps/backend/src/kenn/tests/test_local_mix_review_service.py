from __future__ import annotations

import hashlib
import json
import math
import stat
import struct
import wave

import pytest

from kenn.core import local_mix_review_service as mix_review
from kenn.core.local_mix_review_service import MAX_REVIEWS, LocalMixReviewService, _review_from_report, compare_reference_audio


def _wav_bytes(*, amplitude: float = 0.99, sample_rate: int = 8000, seconds: int = 1, frequency_hz: float = 0.0, channels: int = 1) -> bytes:
    samples = [
        int(max(-1.0, min(1.0, amplitude * (math.sin(2 * math.pi * frequency_hz * index / sample_rate) if frequency_hz else 1.0))) * 32767)
        for index in range(sample_rate * seconds)
    ]
    interleaved = [sample for sample in samples for _ in range(channels)]
    payload = struct.pack("<" + "h" * len(interleaved), *interleaved)
    from io import BytesIO

    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(payload)
    return output.getvalue()


def _antiphase_wav_bytes(*, amplitude: float = 0.2, sample_rate: int = 8000, seconds: int = 1, frequency_hz: float = 100) -> bytes:
    left = [int(amplitude * math.sin(2 * math.pi * frequency_hz * index / sample_rate) * 32767) for index in range(sample_rate * seconds)]
    payload = struct.pack("<" + "h" * (2 * len(left)), *(sample for value in left for sample in (value, -value)))
    from io import BytesIO

    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(payload)
    return output.getvalue()


def _multipart_upload(parts: list[tuple[str, str, bytes]]) -> tuple[str, bytes]:
    """Encode browser field names while letting regressions vary attachment order and validity."""
    boundary = "kenn-browser-upload"
    body = bytearray()
    for name, filename, payload in parts:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        body.extend(f"--{boundary}\r\n{disposition}\r\n\r\n".encode())
        body.extend(payload)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", bytes(body)


@pytest.mark.parametrize("reference_first", [False, True])
def test_browser_upload_includes_its_attached_reference_in_the_grade(tmp_path, reference_first):
    # The browser already sent both fields, but the handler silently discarded the reference.
    mix = _wav_bytes(amplitude=0.2, frequency_hz=100)
    reference = _wav_bytes(amplitude=0.4, frequency_hz=3000)
    attachments = [("file", "mix.wav", mix), ("reference", "reference.wav", reference)]
    if reference_first:
        attachments.reverse()
    request = _multipart_upload([*attachments, ("mix_goal", "", b"premaster")])
    service = LocalMixReviewService(tmp_path)
    ordinary = service.save_review(mix, "mix.wav", mix_goal="premaster")["review"]

    result = service.handle_multipart_review(*request, project_id_override="project-1")

    assert result["ok"] is True
    review = result["review"]
    assert review["source"]["sha256"] == hashlib.sha256(mix).hexdigest()
    assert review["reference"] == {"filename": "reference.wav", "sha256": hashlib.sha256(reference).hexdigest()}
    assert review["project_id"] == "project-1"
    for key in ("metrics", "findings", "flags", "action_plan", "technical_rating"):
        assert review[key] == ordinary[key]
    ref_part = next(part for part in review["grade"]["parts"] if part["part"] == "reference_match")
    assert ref_part["points"] == review["reference_comparison"]["reference_match_score"]["points"]
    assert ref_part["points_available"] == 30.0  # These mono WAVs supply no stereo comparison.
    assert review["grade"]["points_available"] == ordinary["grade"]["points_available"] + 30.0
    assert review["storage"] == "metadata_only"
    assert review["audio_retained"] is False
    restored = LocalMixReviewService(tmp_path).mix_review_status(result["review_id"])["review"]
    assert restored == review
    assert {path.name for path in tmp_path.iterdir()} == {"reviews.json"}


@pytest.mark.parametrize("filename,payload,error", [
    ("empty.wav", b"", "empty"),
    ("corrupt.wav", b"not WAV audio", "WAV"),
    ("other.mp3", _wav_bytes(), "supported WAV"),
    ("surround.wav", _wav_bytes(channels=4), "only mono or stereo"),
])
def test_invalid_browser_reference_rejects_the_pair_without_saving_a_mix_only_review(tmp_path, filename, payload, error):
    service = LocalMixReviewService(tmp_path)
    request = _multipart_upload([
        ("file", "mix.wav", _wav_bytes()), ("reference", filename, payload),
    ])

    result = service.handle_multipart_review(*request)

    assert result["ok"] is False
    assert error.lower() in result["error"].lower()
    assert service.list_reviews() == []
    assert not (tmp_path / "reviews.json").exists()


def test_browser_reference_keeps_the_per_file_byte_limit(tmp_path):
    service = LocalMixReviewService(tmp_path)
    mix = _wav_bytes()
    service.MAX_UPLOAD_BYTES = len(mix)
    request = _multipart_upload([
        ("file", "mix.wav", mix), ("reference", "long.wav", _wav_bytes(seconds=2)),
    ])

    result = service.handle_multipart_review(*request)

    assert result["ok"] is False
    assert "Reference WAV is too large" in result["error"]
    assert service.list_reviews() == []


@pytest.mark.parametrize("fields", [
    [("reference", "reference.wav")],
    [("file", "mix.mp3"), ("reference", "reference.wav")],
    [("file", "mix.wav"), ("file", "other.wav")],
    [("file", "mix.wav"), ("reference", "first.wav"), ("reference", "second.wav")],
    [("file", "mix.wav"), ("reference", "")],
    [("file", "mix.wav"), ("reference", "first.wav"), ("reference", "")],
    [("file", ""), ("reference", "reference.wav")],
    [("file", "mix.wav"), ("file", "")],
    [("audio", "legacy.wav"), ("file", "")],
])
def test_browser_upload_never_substitutes_a_reference_or_chooses_an_ambiguous_pair(tmp_path, fields):
    # Picking the first valid WAV hid bad mix attachments and reversed reference-first uploads.
    service = LocalMixReviewService(tmp_path)
    request = _multipart_upload([(name, filename, _wav_bytes()) for name, filename in fields])

    assert service.handle_multipart_review(*request)["ok"] is False
    assert service.list_reviews() == []


def test_browser_reference_grade_changes_with_the_reference_and_does_not_leak(tmp_path):
    service = LocalMixReviewService(tmp_path)
    mix = _wav_bytes(amplitude=0.2, frequency_hz=100)

    def upload(reference=None):
        attachments = [("file", "mix.wav", mix)]
        if reference is not None:
            attachments.append(("reference", "reference.wav", reference))
        return service.handle_multipart_review(*_multipart_upload(attachments))["review"]

    matched = upload(mix)
    changed = upload(_wav_bytes(amplitude=0.2, frequency_hz=3000))
    repeated = upload(mix)
    ordinary = upload()

    assert matched["grade"]["points"] > changed["grade"]["points"]
    assert repeated["grade"] == matched["grade"]
    assert all(part["part"] != "reference_match" for part in ordinary["grade"]["parts"])
    assert "reference" not in ordinary and "reference_comparison" not in ordinary


def test_browser_reference_matching_failure_stays_explicit_in_the_saved_grade(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("optional matching unavailable")

    monkeypatch.setattr(mix_review._matching_engine(), "compare_mix_to_reference", unavailable)
    # Stereo correlation is available even when optional loudness dependencies are absent.
    audio = _wav_bytes(amplitude=0.2, frequency_hz=100, channels=2)
    request = _multipart_upload([
        ("file", "mix.wav", audio), ("reference", "reference.wav", audio),
    ])

    result = LocalMixReviewService(tmp_path).handle_multipart_review(*request)

    assert result["ok"] is True
    grade = result["review"]["grade"]
    assert any(part["part"] == "technical_health" for part in grade["parts"])
    reference = next(part for part in grade["ungraded"] if part["part"] == "reference_match")
    assert reference["reason"] == "reference supplied, but reference-match analysis unavailable"
    restored = LocalMixReviewService(tmp_path).mix_review_status(result["review_id"])["review"]
    assert restored["grade"] == grade
    assert restored["reference"]["filename"] == "reference.wav"


def test_legacy_single_file_field_still_produces_an_ordinary_review(tmp_path):
    request = _multipart_upload([("audio", "mix.wav", _wav_bytes())])

    result = LocalMixReviewService(tmp_path).handle_multipart_review(*request)

    assert result["ok"] is True
    assert "reference" not in result["review"]


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


@pytest.mark.parametrize("rms", ["missing", None, True, float("nan"), float("inf"), -float("inf"), 10 ** 1000, -60.0, -60.01])
def test_unqualified_uploaded_review_keeps_provenance_but_withholds_signal_output(rms):
    metrics = {
        "peak_dbfs": -0.1,
        "integrated_lufs": -8.0,
        "rms_dbfs": rms,
    }
    if rms == "missing":
        metrics.pop("rms_dbfs")
    report = {
        "ok": True,
        "timestamp": "2026-10-15T10:00:00Z",
        "analysis_version": "test-v1",
        "input_context": {"format": "wav", "duration_seconds": 2.0, "channel_layout": "stereo"},
        "metrics": metrics,
        "evidence": {"schema": "kenn.evidence.v1", "facts": [{"name": "peak_dbfs", "value": -0.1}]},
        "findings": [{"type": "headroom", "fault_family": "headroom", "detected": True}],
        "action_plan": [{"focus": "headroom"}],
        "technical_rating": "Poor",
        "limitations": "Existing analyzer limits.",
    }

    review = _review_from_report(
        report, review_id="review-test", filename="quiet.wav", source_sha256="a" * 64, project_id="project-1",
        reference_match={"points": 20.0, "points_available": 30.0},
    )

    assert review["status"] == "completed"
    assert review["source"] == {"filename": "quiet.wav", "sha256": "a" * 64}
    assert review["project_id"] == "project-1"
    assert review["input_context"] == report["input_context"]
    assert review["metrics"] == {}
    assert review["evidence"] is None
    assert review["findings"] == [] and review["flags"] == [] and review["action_plan"] == []
    assert review["technical_rating"] == ""
    assert review["signal_limitation"] and "at/below -60 dBFS" in review["signal_limitation"]
    assert review["signal_limitation"] in review["limitations"]
    assert review["grade"]["points"] == 0.0 and review["grade"]["points_available"] == 0.0


def test_legacy_quiet_review_is_sanitized_on_read_without_rewriting_registry(tmp_path):
    legacy = {
        "schema": "kenn.mix_review.local_review.v1",
        "review_id": "review-legacy-quiet",
        "status": "completed",
        "source": {"filename": "quiet.wav", "sha256": "a" * 64},
        "reference": {"filename": "ref.wav", "sha256": "b" * 64},
        "metrics": {"rms_dbfs": -80.0, "peak_dbfs": -0.1, "integrated_lufs": -8.0},
        "evidence": {"facts": [{"name": "peak_dbfs", "value": -0.1}]},
        "findings": [{"type": "legacy_signal_finding"}],
        "flags": [{"label": "Legacy signal flag"}],
        "action_plan": [{"focus": "legacy EQ"}],
        "technical_rating": "Poor",
        "qualified_fault_families": ["headroom"],
        "not_evaluated_fault_families": ["stereo"],
        "reference_comparison": {
            "reference_match_score": {"points": 12.0, "points_available": 30.0},
            "pink_noise_reference": {"largest_deviation": {"center_hz": 80.0}},
            "recommendations": ["legacy EQ move"],
        },
        "grade": {"points": 87.0, "points_available": 100.0},
        "input_context": {"channel_layout": "stereo"},
    }
    index_path = tmp_path / "reviews.json"
    index_path.write_text(json.dumps({legacy["review_id"]: legacy}), encoding="utf-8")
    service = LocalMixReviewService(tmp_path)

    fetched = service.mix_review_status(legacy["review_id"])["review"]
    listed = service.list_reviews()[0]
    exported = json.loads(service.report_json_bytes(legacy["review_id"]))

    for result in (fetched, listed, exported):
        assert result["source"] == legacy["source"]
        assert result["reference"] == legacy["reference"]
        assert result["metrics"] == {} and result["evidence"] is None
        assert result["findings"] == result["flags"] == result["action_plan"] == []
        assert result["technical_rating"] == ""
        assert "reference_comparison" not in result
        assert result["signal_limitation"]
        assert result["grade"]["points"] == result["grade"]["points_available"] == 0.0
    # Fetching old metadata must not silently rewrite the on-disk source record.
    assert json.loads(index_path.read_text(encoding="utf-8"))[legacy["review_id"]] == legacy


def test_legacy_active_review_keeps_signal_fields_on_read(tmp_path):
    active = {
        "schema": "kenn.mix_review.local_review.v1",
        "review_id": "review-legacy-active",
        "status": "completed",
        "metrics": {"rms_dbfs": -12.0, "peak_dbfs": -1.0},
        "findings": [{"type": "headroom"}],
        "reference_comparison": {
            "reference_match_score": {"points": 2.0},
            "dynamics": {"mix": {"rms_dbfs": -12.0}, "reference": {"rms_dbfs": -13.0}},
        },
        "grade": {"points": 80.0},
    }
    (tmp_path / "reviews.json").write_text(json.dumps({active["review_id"]: active}), encoding="utf-8")

    fetched = LocalMixReviewService(tmp_path).mix_review_status(active["review_id"])["review"]

    assert fetched["metrics"] == active["metrics"]
    assert fetched["findings"] == active["findings"]
    assert fetched["reference_comparison"] == active["reference_comparison"]


def test_active_legacy_ordinary_review_with_quiet_reference_keeps_mix_grade_only(tmp_path):
    ordinary = {
        "schema": "kenn.mix_review.local_review.v1",
        "review_id": "review-active-quiet-reference",
        "status": "completed",
        "metrics": {"rms_dbfs": -12.0, "integrated_lufs": -14.0},
        "findings": [{"type": "mix_own_finding"}],
        "reference": {"filename": "quiet.wav", "sha256": "c" * 64},
        "reference_comparison": {
            "reference_match_score": {"points": 12.0, "points_available": 30.0},
            "recommendations": ["stale recommendation"],
        },
        "grade": {
            "points": 40.0,
            "points_available": 60.0,
            "full_marks": 100.0,
            "parts": [
                {"part": "technical_health", "points": 25.0, "points_available": 30.0},
                {"part": "reference_match", "points": "stale", "points_available": None},
            ],
            "ungraded": [],
        },
    }
    (tmp_path / "reviews.json").write_text(json.dumps({ordinary["review_id"]: ordinary}), encoding="utf-8")

    fetched = LocalMixReviewService(tmp_path).mix_review_status(ordinary["review_id"])["review"]

    assert fetched["metrics"] == ordinary["metrics"]
    assert fetched["findings"] == ordinary["findings"]
    assert fetched["reference"] == ordinary["reference"]
    assert "reference_comparison" not in fetched
    assert fetched["grade"]["points"] == 25.0
    assert fetched["grade"]["points_available"] == 30.0
    assert [part["part"] for part in fetched["grade"]["parts"]] == ["technical_health"]
    assert "reference comparison" in fetched["limitations"].lower()


def test_legacy_standalone_quiet_reference_receipt_is_sanitized_on_read(tmp_path):
    legacy = {
        "schema": "kenn.mix_review.reference_comparison.v1",
        "review_id": "reference-legacy-quiet",
        "status": "completed",
        "source_mix": {"filename": "mix.wav", "sha256": "a" * 64},
        "source_reference": {"filename": "quiet.wav", "sha256": "b" * 64},
        "reference_comparison": {
            "reference_match_score": {"points": 12.0, "points_available": 30.0},
            "dynamics": {"mix": {"rms_dbfs": -12.0}, "reference": {"rms_dbfs": -80.0}},
            "recommendations": ["stale EQ"],
            "eq8_preset_adv_base64": "stale-preset",
            "pink_noise_reference": {"deviation_db": 8.0},
        },
        "metrics": {"rms_dbfs": -12.0},
        "evidence": {"facts": [{"name": "rms_dbfs", "value": -12.0}]},
        "findings": [{"type": "stale finding"}],
        "flags": [{"label": "stale flag"}],
        "action_plan": [{"focus": "stale action"}],
        "technical_rating": "stale rating",
        "grade": {
            "points": 43.0,
            "points_available": 60.0,
            "full_marks": 100.0,
            "parts": [
                {"part": "technical_health", "points": 28.0, "points_available": 30.0},
                {"part": "reference_match", "points": 15.0, "points_available": 30.0},
            ],
            "ungraded": [],
        },
        "limitations": ["Old comparison limitation."],
    }
    index_path = tmp_path / "reviews.json"
    index_path.write_text(json.dumps({legacy["review_id"]: legacy}), encoding="utf-8")
    service = LocalMixReviewService(tmp_path)

    fetched = service.mix_review_status(legacy["review_id"])["review"]
    listed = service.list_reviews()[0]
    exported = json.loads(service.report_json_bytes(legacy["review_id"]))
    html_export = service.report_html(legacy["review_id"]).decode("utf-8")

    for result in (fetched, listed, exported):
        assert result["source_mix"] == legacy["source_mix"]
        assert result["source_reference"] == legacy["source_reference"]
        assert "reference_comparison" not in result
        assert not {"metrics", "evidence", "findings", "flags", "action_plan", "technical_rating"} & result.keys()
        assert result["grade"]["points"] == 28.0
        assert result["grade"]["points_available"] == 30.0
        assert [part["part"] for part in result["grade"]["parts"]] == ["technical_health"]
        assert any("both be finite numeric values" in item for item in result["limitations"])
    assert "stale-preset" not in html_export and "stale EQ" not in html_export
    assert json.loads(index_path.read_text(encoding="utf-8"))[legacy["review_id"]] == legacy


def test_legacy_standalone_quiet_mix_drops_grade_when_mix_provenance_is_unqualified(tmp_path):
    legacy = {
        "schema": "kenn.mix_review.reference_comparison.v1",
        "review_id": "reference-legacy-quiet-mix",
        "status": "completed",
        "source_mix": {"filename": "quiet.wav", "sha256": "a" * 64},
        "source_reference": {"filename": "ref.wav", "sha256": "b" * 64},
        "reference_comparison": {
            "reference_match_score": {"points": 10.0, "points_available": 30.0},
            "dynamics": {"mix": {"rms_dbfs": -80.0}, "reference": {"rms_dbfs": -10.0}},
            "eq8_preset_adv_base64": "stale-preset",
        },
        "grade": {"points": 70.0, "points_available": 100.0},
    }
    (tmp_path / "reviews.json").write_text(json.dumps({legacy["review_id"]: legacy}), encoding="utf-8")

    fetched = LocalMixReviewService(tmp_path).mix_review_status(legacy["review_id"])["review"]

    assert fetched["grade"]["points"] == fetched["grade"]["points_available"] == 0.0
    assert fetched["grade"]["parts"] == []
    assert "reference_comparison" not in fetched
    assert fetched["source_mix"] == legacy["source_mix"]


def test_legacy_standalone_missing_reference_rms_keeps_only_proven_mix_grade(tmp_path):
    legacy = {
        "schema": "kenn.mix_review.reference_comparison.v1",
        "review_id": "reference-legacy-missing-rms",
        "status": "completed",
        "source_mix": {"filename": "mix.wav", "sha256": "a" * 64},
        "source_reference": {"filename": "ref.wav", "sha256": "b" * 64},
        "mix_metrics": {"rms_dbfs": -12.0, "integrated_lufs": -14.0},
        "reference_comparison": {"recommendations": ["stale EQ"]},
        "grade": {
            "points": 50.0,
            "points_available": 60.0,
            "full_marks": 100.0,
            "parts": [
                {"part": "technical_health", "points": 25.0, "points_available": 30.0},
                {"part": "reference_match", "points": 25.0, "points_available": 30.0},
            ],
            "ungraded": [],
        },
    }
    (tmp_path / "reviews.json").write_text(json.dumps({legacy["review_id"]: legacy}), encoding="utf-8")

    fetched = LocalMixReviewService(tmp_path).mix_review_status(legacy["review_id"])["review"]

    assert fetched["mix_metrics"] == legacy["mix_metrics"]
    assert fetched["grade"]["points"] == 25.0
    assert fetched["grade"]["points_available"] == 30.0
    assert "reference_comparison" not in fetched


def test_new_standalone_active_mix_quiet_reference_keeps_only_qualified_mix_grade(tmp_path):
    active_mix = _wav_bytes(amplitude=0.2, frequency_hz=100)
    quiet_reference = _wav_bytes(amplitude=0.0005, frequency_hz=3000)
    request = _multipart_upload([
        ("mix", "mix.wav", active_mix),
        ("reference", "quiet-reference.wav", quiet_reference),
    ])

    result = LocalMixReviewService(tmp_path).handle_multipart_reference(*request)
    review = result["review"]

    assert review["source_mix"]["sha256"] == hashlib.sha256(active_mix).hexdigest()
    assert review["source_reference"]["sha256"] == hashlib.sha256(quiet_reference).hexdigest()
    assert review["mix_metrics"]["rms_dbfs"] > -60.0
    assert "reference_comparison" not in review
    assert all(part["part"] != "reference_match" for part in review["grade"]["parts"])
    assert any("reference comparison measurements" in item for item in review["limitations"])


def test_active_standalone_reference_comparison_survives_read_gate(tmp_path, monkeypatch):
    def matching(*_args, **_kwargs):
        return {
            "ok": True,
            "dynamics": {
                "mix": {"rms_dbfs": -12.0},
                "reference": {"rms_dbfs": -13.0},
            },
            "reference_match_score": {"points": 20.0, "points_available": 30.0, "note": "matched"},
            "eq8_preset_adv_base64": "active-preset",
        }

    monkeypatch.setattr(mix_review._matching_engine(), "compare_mix_to_reference", matching)
    active = _wav_bytes(amplitude=0.2, frequency_hz=100)
    reference = _wav_bytes(amplitude=0.2, frequency_hz=3000)
    request = _multipart_upload([("mix", "mix.wav", active), ("reference", "ref.wav", reference)])
    service = LocalMixReviewService(tmp_path)

    result = service.handle_multipart_reference(*request)
    fetched = service.mix_review_status(result["review_id"])["review"]

    assert fetched["reference_comparison"]["eq8_preset_adv_base64"] == "active-preset"
    assert fetched["grade"]["points"] == result["review"]["grade"]["points"]
    assert fetched["source_mix"] == result["review"]["source_mix"]


def test_active_mix_with_quiet_reference_keeps_comparison_limitation(tmp_path):
    audible = _wav_bytes(amplitude=0.2, frequency_hz=100)
    quiet = _wav_bytes(amplitude=0.0005, frequency_hz=3000)

    result = LocalMixReviewService(tmp_path).save_review(
        audible, "mix.wav", reference_audio=(quiet, "quiet-reference.wav"),
    )
    review = result["review"]

    assert review["metrics"]["rms_dbfs"] > -60.0
    assert review["reference"] == {"filename": "quiet-reference.wav", "sha256": hashlib.sha256(quiet).hexdigest()}
    assert "reference RMS" in review["limitations"]


def test_uploaded_review_just_above_significance_floor_keeps_signal_output():
    report = {
        "ok": True,
        "metrics": {"rms_dbfs": -59.99, "peak_dbfs": -0.1},
        "evidence": {"schema": "kenn.evidence.v1", "facts": [{"name": "peak_dbfs", "value": -0.1}]},
        "findings": [{"type": "headroom", "fault_family": "headroom", "detected": True, "severity": "high", "confidence": 0.9}],
        "action_plan": [{"focus": "headroom"}],
        "technical_rating": "Needs headroom",
    }

    review = _review_from_report(
        report, review_id="review-active", filename="active.wav", source_sha256="b" * 64, project_id="",
    )

    assert review["metrics"]["rms_dbfs"] == -59.99
    assert review["evidence"] == report["evidence"]
    assert review["findings"] == report["findings"]
    assert review["flags"][0]["fault_family"] == "headroom"
    assert review["action_plan"] == report["action_plan"]
    assert review["signal_limitation"] is None


def test_local_service_rejects_invalid_audio_without_creating_review(tmp_path) -> None:
    service = LocalMixReviewService(tmp_path / "runtime")
    result = service.save_review(b"not wav", "bad.wav")
    assert result["ok"] is False
    assert service.list_reviews() == []


def test_an_oversized_or_surround_file_says_why_and_leaves_nothing_behind(tmp_path) -> None:
    service = LocalMixReviewService(tmp_path / "runtime")
    service.MAX_UPLOAD_BYTES = 1000
    too_big = service.save_review(_wav_bytes(), "long-master.wav")
    assert too_big["ok"] is False
    assert "MB" in too_big["error"] and "shorter section" in too_big["error"]

    output = __import__("io").BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(4)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x01" * 4 * 8000)
    quad = LocalMixReviewService(tmp_path / "runtime").save_review(output.getvalue(), "quad.wav")
    assert quad["ok"] is False
    assert "only mono or stereo" in quad["error"]
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
    reference_score = comparison["reference_match_score"]
    reference_part = next(p for p in result["grade"]["parts"] if p["part"] == "reference_match")
    assert reference_part["points"] == reference_score["points"]
    assert reference_part["points_available"] == 30.0  # mono sources have neither stereo part to compare
    assert set(reference_part["left_out"]) == {"low_end_mono", "stereo_width"}
    assert result["grade"]["points"] == round(sum(p["points"] for p in result["grade"]["parts"]), 1)


def test_bands_empty_in_both_files_are_not_reported_as_the_largest_difference() -> None:
    # Until 16 Oct 2026 two identical sines 3 dB apart reported a -64.8 dB gap
    # at 15 kHz, where both files hold only rounding noise, and an EQ boost for it.
    result = compare_reference_audio(
        _wav_bytes(amplitude=0.14, frequency_hz=1000, sample_rate=48000), "mix.wav",
        _wav_bytes(amplitude=0.2, frequency_hz=1000, sample_rate=48000), "reference.wav",
    )
    comparison = result["reference_comparison"]
    assert all(abs(row["delta_db"]) < 6.0 for row in comparison["ltas_40_band_deltas"])
    assert abs(comparison["largest_spectral_difference"]["delta_db"] + 3.1) < 0.2
    assert comparison["eq_bands"] == []


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
    # The reference grade must survive the same restart as its source hashes and measured gaps.
    restored = LocalMixReviewService(tmp_path / "runtime").mix_review_status(result["review_id"])["review"]
    assert restored["grade"] == review["grade"]
    assert any(p["part"] == "reference_match" for p in restored["grade"]["parts"])


@pytest.mark.parametrize("response", [None, {"ok": False}, {"ok": True}])
def test_unavailable_reference_matching_leaves_a_partial_grade_with_the_reason(monkeypatch, response):
    def unavailable(*args, **kwargs):
        if response is None:
            # The real adapter also catches an optional engine's import or analysis failure.
            raise RuntimeError("matching unavailable")
        return response

    monkeypatch.setattr(mix_review._matching_engine(), "compare_mix_to_reference", unavailable)
    # Stereo correlation remains measurable even when optional loudness dependencies are absent.
    wav = _wav_bytes(amplitude=0.2, frequency_hz=100, channels=2)

    result = compare_reference_audio(wav, "mix.wav", wav, "reference.wav")

    assert result["ok"] is True
    grade = result["grade"]
    technical = next(p for p in grade["parts"] if p["part"] == "technical_health")
    assert technical["points_available"] > 0.0
    assert all(p["part"] != "reference_match" for p in grade["parts"])
    reference = next(u for u in grade["ungraded"] if u["part"] == "reference_match")
    assert reference["reason"] == "reference supplied, but reference-match analysis unavailable"


def test_silent_reference_is_ungraded_instead_of_a_perfect_match():
    wav = _wav_bytes(amplitude=0.2, frequency_hz=100)

    result = compare_reference_audio(wav, "mix.wav", _wav_bytes(amplitude=0.0), "silent.wav")

    assert result["ok"] is True
    assert result["reference_comparison"]["reference_match_score"]["points_available"] == 0.0
    reference = next(u for u in result["grade"]["ungraded"] if u["part"] == "reference_match")
    assert "reference RMS" in reference["reason"]


@pytest.mark.parametrize("quiet_source", ["mix", "reference"])
def test_near_silent_source_withholds_comparison_metrics_below_the_existing_significance_floor(quiet_source):
    audible = _wav_bytes(amplitude=0.2, frequency_hz=100)
    near_silent = _wav_bytes(amplitude=0.0005, frequency_hz=3000)
    mix = near_silent if quiet_source == "mix" else audible
    reference_audio = near_silent if quiet_source == "reference" else audible

    result = compare_reference_audio(mix, "mix.wav", reference_audio, "quiet-reference.wav")
    comparison = result["reference_comparison"]
    score = comparison["reference_match_score"]

    assert score["points_available"] == 0.0
    assert comparison["largest_spectral_difference"] is None
    assert comparison["ltas_40_band_deltas"] == []
    assert comparison["lufs_delta_db"] is None
    assert comparison["pink_noise_reference"] is None
    assert "matching_gains_db" not in comparison
    reference = next(u for u in result["grade"]["ungraded"] if u["part"] == "reference_match")
    assert f"{quiet_source} RMS" in reference["reason"]
    assert comparison["largest_ltas_difference"] is None
    assert comparison["eq_bands"] == []
    assert not {"tonal_balance_7band", "dynamics", "stereo", "coaching", "recommendations", "eq8_preset_adv_base64"} & comparison.keys()


def test_antiphase_stereo_below_the_scorer_floor_withholds_comparison_details():
    antiphase = _antiphase_wav_bytes()
    audible = _wav_bytes(amplitude=0.2, frequency_hz=100)

    result = compare_reference_audio(antiphase, "mix.wav", audible, "reference.wav")
    comparison = result["reference_comparison"]
    reference = next(u for u in result["grade"]["ungraded"] if u["part"] == "reference_match")

    assert comparison["reference_match_score"]["points_available"] == 0.0
    assert "mix RMS" in reference["reason"]
    assert comparison["largest_spectral_difference"] is None
    assert comparison["largest_ltas_difference"] is None
    assert comparison["ltas_40_band_deltas"] == []
    assert comparison["eq_bands"] == []
    assert comparison["lufs_delta_db"] is None
    assert comparison["pink_noise_reference"] is None
    assert not {"tonal_balance_7band", "matching_gains_db", "dynamics", "stereo", "coaching", "recommendations", "eq8_preset_adv_base64"} & comparison.keys()


def test_reference_points_follow_this_upload_and_do_not_leak_into_another_review(tmp_path):
    # The service has a process-wide engine, but a previous comparison must never supply the next review's points.
    mix = _wav_bytes(amplitude=0.2, frequency_hz=100)
    different = _wav_bytes(amplitude=0.2, frequency_hz=3000)

    matched = compare_reference_audio(mix, "mix.wav", mix, "same.wav")["grade"]
    changed = compare_reference_audio(mix, "mix.wav", different, "different.wav")["grade"]
    repeated = compare_reference_audio(mix, "mix.wav", mix, "same.wav")["grade"]
    ordinary = LocalMixReviewService(tmp_path).save_review(mix, "other.wav")["review"]["grade"]

    assert matched == repeated
    assert matched["points"] > changed["points"]
    assert matched["points_available"] == changed["points_available"]
    assert all(p["part"] != "reference_match" for p in ordinary["parts"])
    assert next(u for u in ordinary["ungraded"] if u["part"] == "reference_match")["reason"] == "no reference track supplied"
