"""Raw render activity must survive transient normalization and handoff."""

from copy import deepcopy
import io
import math
import struct
import wave

import pytest

from audio_analysis.integration.handoff import kenn_handoff
from audio_analysis.mix_review.review_workflow import _attach_transient_preservation


def _transient() -> dict:
    return {
        "preservation_score": 0.42, "matched_event_count": 18, "profile": " Smearing ",
        "activity": {"schema": "kenn.transient_preservation.activity.v1", "pre_rms_dbfs": -18.0, "post_rms_dbfs": -14.0},
    }


def _handoff(transient):
    return kenn_handoff({"transient_preservation": transient})["analysis_evidence"]["transient_preservation"]


def test_active_transient_handoff_is_bounded_and_isolated():
    transient = _transient()
    transient["profile"] = " " + "x" * 200 + " "
    transient["activity"]["samples"] = [0.1] * 20
    before = deepcopy(transient)
    result = _handoff(transient)
    assert result == {"score": 0.42, "matched_event_count": 18, "profile": "x" * 160, "activity": {
        "schema": "kenn.transient_preservation.activity.v1", "pre_rms_dbfs": -18.0, "post_rms_dbfs": -14.0,
    }}
    result["activity"]["pre_rms_dbfs"] = -99
    assert transient == before


@pytest.mark.parametrize("section", [None, False, [], "cached claim", {}, {"preservation_score": 0.9}])
def test_present_unqualified_transient_section_retains_abstention_marker(section):
    # Presence lets the backend suppress cached prose from legacy comparisons.
    assert _handoff(section) == {}


def test_absent_transient_does_not_create_a_comparison():
    assert "transient_preservation" not in kenn_handoff({})["analysis_evidence"]


def test_handoff_exposes_measured_legacy_rms_under_backend_activity_key():
    # The backend accepts rms_dbfs, while analyze_wav historically names it estimate.
    result = kenn_handoff({"metrics": {"rms_dbfs_estimate": -18.0}, "transient_preservation": _transient()})
    assert result["metrics"]["rms_dbfs"] == -18.0
    assert result["analysis_evidence"]["transient_preservation"]["score"] == 0.42


@pytest.mark.parametrize("canonical", [-60.0, -80.0, None, True])
def test_explicit_canonical_rms_cannot_be_overridden_by_louder_legacy_rms(canonical):
    result = kenn_handoff({"metrics": {"rms_dbfs": canonical, "rms_dbfs_estimate": -18.0}})
    assert result["metrics"]["rms_dbfs"] == canonical


def test_handoff_does_not_manufacture_rms_from_peak():
    assert kenn_handoff({"metrics": {"peak_dbfs": -1.0}})["metrics"]["rms_dbfs"] is None


@pytest.mark.parametrize("source", ["pre_rms_dbfs", "post_rms_dbfs"])
@pytest.mark.parametrize("level", [-60.0, -60.001, True, "-18", None, float("nan"), float("inf"), 10**400])
def test_either_unqualified_raw_render_withholds_transient_summary(source, level):
    transient = _transient()
    transient["activity"][source] = level
    assert _handoff(transient) == {}


@pytest.mark.parametrize("field,value", [
    ("preservation_score", value) for value in [True, None, "0.4", -0.001, 1.001, float("nan"), float("inf"), 10**400]
] + [("matched_event_count", value) for value in [True, 0, -1, 1.0, "18"]]
  + [("profile", value) for value in [None, " ", False]])
def test_malformed_transient_summary_cannot_be_published(field, value):
    transient = _transient()
    transient[field] = value
    assert _handoff(transient) == {}


@pytest.mark.parametrize("score", [0.0, 1.0])
def test_transient_score_endpoints_and_just_active_sources_are_valid(score):
    transient = _transient()
    transient["preservation_score"] = score
    transient["activity"].update(pre_rms_dbfs=-59.999, post_rms_dbfs=-59.999)
    assert _handoff(transient)["score"] == score


def _decoded(rms=0.1, rate=8000):
    return {"samples": [0.1] * 4096, "sample_rate": rate, "analysis_sample_rate": rate, "true_rms": rms}


def _attach_with_decoded(monkeypatch, pre, post):
    import audio_analysis.analysis_core.transient_groove as groove
    import audio_analysis.utils.audio_io_api as audio_io

    monkeypatch.setattr(audio_io, "decode_audio_bytes", lambda data, name: {"wav_bytes": data})
    monkeypatch.setattr(audio_io, "read_wav_mono", lambda data: pre if data == b"pre" else post)
    calls = []
    monkeypatch.setattr(groove, "transient_preservation", lambda *args: calls.append(args) or {
        "preservation_score": 0.42, "matched_event_count": 18, "profile": "Smearing",
    })
    report = {}
    _attach_transient_preservation(report, b"post", "mix.wav", b"pre")
    return report, calls


def test_attachment_reuses_decoded_raw_rms_before_normalized_transient_analysis(monkeypatch):
    report, calls = _attach_with_decoded(monkeypatch, _decoded(0.1), _decoded(0.01))
    assert len(calls) == 1
    assert report["transient_preservation"]["activity"] == {
        "schema": "kenn.transient_preservation.activity.v1", "pre_rms_dbfs": -20.0, "post_rms_dbfs": -40.0,
    }
    assert _handoff(report["transient_preservation"])["score"] == 0.42


@pytest.mark.parametrize("side", ["pre", "post"])
@pytest.mark.parametrize("rms", [0, 0.001, 0.000999, True, None, float("nan"), float("inf")])
def test_quiet_or_missing_raw_rms_skips_normalized_comparison(monkeypatch, side, rms):
    pre, post = _decoded(), _decoded()
    (pre if side == "pre" else post)["true_rms"] = rms
    report, calls = _attach_with_decoded(monkeypatch, pre, post)
    assert calls == []
    assert _handoff(report["transient_preservation"]) == {}


def test_incompatible_analysis_rates_abstain_without_pairing_onset_times(monkeypatch):
    report, calls = _attach_with_decoded(monkeypatch, _decoded(rate=8000), _decoded(rate=11025))
    assert calls == []
    assert report["transient_preservation"] == {}


def test_antiphase_stereo_raw_mono_is_quiet_before_transient_normalization(monkeypatch):
    # Existing true_rms measures (L+R)/2, so opposite channels are not active mono.
    import audio_analysis.analysis_core.transient_groove as groove
    import audio_analysis.utils.audio_io_api as audio_io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        frames = [int(8000 * math.sin(2 * math.pi * 200 * i / 8000)) for i in range(8192)]
        wav.writeframes(b"".join(struct.pack("<hh", value, -value) for value in frames))
    monkeypatch.setattr(audio_io, "decode_audio_bytes", lambda data, name: {"wav_bytes": data})
    monkeypatch.setattr(groove, "transient_preservation", lambda *args: pytest.fail("quiet mono reached normalized analysis"))
    report = {}
    _attach_transient_preservation(report, buffer.getvalue(), "mix.wav", buffer.getvalue())
    assert report["transient_preservation"] == {}
