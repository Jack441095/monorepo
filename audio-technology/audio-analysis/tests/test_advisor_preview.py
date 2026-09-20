"""Lineaged advisor A/B preview rendering tests."""

from __future__ import annotations

import math

import numpy as np

from audio_analysis.integration.advisor_preview import render_advisor_previews
from audio_analysis.integration.kenn_advisor import CONTRACT_SCHEMA, mix_plan_revision
from audio_analysis.mixdown.mix_decision_engine import BusMixConfig, MixPlan, StemMixConfig


def _plan() -> MixPlan:
    return MixPlan(
        stems=[StemMixConfig(stem_name="vocal.wav", instrument="vocal", gain_db=0.0)],
        bus=BusMixConfig(),
        genre="pop",
        target_lufs=-14.0,
    )


def _proposal(plan: MixPlan, operations: list[dict] | None = None) -> dict:
    return {
        "schema": CONTRACT_SCHEMA,
        "source_plan_revision": mix_plan_revision(plan),
        "model_version": "preview-test",
        "prompt_version": "preview-test",
        "correlation_id": "automix-job:preview-test",
        "operations": operations
        or [
            {
                "stem_id": "vocal.wav",
                "operation": "gain_delta",
                "value": 1.0,
                "unit": "dB",
                "evidence_source_ids": ["source@index:v-test"],
                "confidence": 0.95,
                "reason": "Preview test.",
            }
        ],
    }


def _prepared() -> list[dict]:
    sample_rate = 100
    samples = np.concatenate((np.zeros(100), np.full(200, 0.1), np.zeros(100)))
    return [{"name": "vocal.wav", "samples": samples, "sample_rate": sample_rate}]


def _render(stems, plan, *, ignore_gain: bool = False, loudness_bias: bool = False):
    source = np.asarray(stems[0]["samples"], dtype=np.float64)
    gain = 1.0 if ignore_gain else 10 ** (plan.stems[0].gain_db / 20.0)
    # Random noise proves baseline/candidate receive an identical dither stream.
    audio = source * gain + np.random.uniform(-1e-8, 1e-8, size=len(source))
    measured = -14.0 + (plan.stems[0].gain_db if loudness_bias else 0.0)
    return {
        "mixdown_wav_bytes": b"RIFF" + bytes([round(gain * 10)]),
        "left": audio,
        "right": audio.copy(),
        "measured_lufs": measured,
        "sample_rate": int(stems[0]["sample_rate"]),
    }


def test_preview_uses_dense_window_and_detects_operation_not_dither() -> None:
    plan = _plan()
    process_state = np.random.get_state()
    preview = render_advisor_previews(
        _prepared(),
        plan,
        _proposal(plan),
        render_fn=_render,
        duration_seconds=2.0,
    )
    restored_state = np.random.get_state()
    assert all(np.array_equal(left, right) for left, right in zip(process_state, restored_state))
    assert preview["duration_samples"] == 200
    assert preview["baseline_lufs"] == -14.0
    assert len(preview["candidates"]) == 1
    assert preview["candidates"][0]["rms_delta"] > 0
    assert preview["candidates"][0]["loudness_bias_lu"] == 0.0
    assert preview["rejected"] == []
    assert plan.stems[0].gain_db == 0.0


def test_effectively_identical_candidate_is_not_listening_evidence() -> None:
    plan = _plan()
    preview = render_advisor_previews(
        _prepared(),
        plan,
        _proposal(plan),
        render_fn=lambda stems, candidate_plan: _render(
            stems, candidate_plan, ignore_gain=True
        ),
        duration_seconds=1.0,
    )
    assert preview["candidates"] == []
    assert "effectively identical" in preview["rejected"][0]["reason"]


def test_loudness_biased_candidate_is_rejected() -> None:
    plan = _plan()
    preview = render_advisor_previews(
        _prepared(),
        plan,
        _proposal(plan),
        render_fn=lambda stems, candidate_plan: _render(
            stems, candidate_plan, loudness_bias=True
        ),
        duration_seconds=1.0,
    )
    assert preview["candidates"] == []
    assert "loudness bias" in preview["rejected"][0]["reason"]


def test_non_finite_audio_is_rejected_before_comparison() -> None:
    plan = _plan()

    def invalid_render(stems, candidate_plan):
        result = _render(stems, candidate_plan)
        result["left"][0] = math.nan
        return result

    try:
        render_advisor_previews(
            _prepared(),
            plan,
            _proposal(plan),
            render_fn=invalid_render,
        )
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("non-finite baseline must fail the preview")


def test_real_renderer_produces_loudness_matched_relative_balance_preview() -> None:
    sample_rate = 44_100
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    prepared = [
        {
            "name": "kick.wav",
            "samples": 0.12 * np.sin(2 * np.pi * 80 * time),
            "sample_rate": sample_rate,
        },
        {
            "name": "vocal.wav",
            "samples": 0.08 * np.sin(2 * np.pi * 440 * time),
            "sample_rate": sample_rate,
        },
    ]
    plan = MixPlan(
        stems=[
            StemMixConfig(stem_name="kick.wav", instrument="kick"),
            StemMixConfig(stem_name="vocal.wav", instrument="vocal"),
        ],
        bus=BusMixConfig(),
        genre="pop",
        target_lufs=-14.0,
    )
    preview = render_advisor_previews(
        prepared,
        plan,
        _proposal(plan),
        duration_seconds=1.0,
    )
    assert len(preview["candidates"]) == 1
    candidate = preview["candidates"][0]
    assert abs(candidate["loudness_bias_lu"]) <= 0.5
    assert candidate["rms_delta"] > 1e-4
    assert candidate["render"]["mixdown_wav_bytes"].startswith(b"RIFF")
