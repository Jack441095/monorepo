"""Unit tests for the mix delivery module.

Verifies that the delivery pipeline packages WAV, HTML, MD, and JSON outputs into a ZIP file,
and correctly increments version numbers on subsequent renders.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import numpy as np

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_delivery import package_mixdown_delivery
from audio_analysis.mixdown.stem_prep import write_wav


def test_delivery_packaging():
    sample_rate = 44100
    duration_samples = 1000

    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-10.0, rms_dbfs=-22.0, crest_factor_db=12.0),
    ]

    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    plan.musical_roles = [{
        "schema": "audio-too.musical-role.v1",
        "stem_name": "kick.wav",
        "role": "rhythmic_anchor",
        "priority": "support",
        "confidence": 0.84,
        "ambiguous": False,
    }]
    plan.arrangement = {
        "schema": "audio-too.arrangement.v1",
        "duration_seconds": 1.0,
        "sections": [],
    }
    plan.relationships = [{
        "schema": "audio-too.relationship.v1",
        "relationship_id": "rel-001",
        "applies_automatically": False,
    }]
    plan.mono_compatibility = {
        "schema": "audio-too.mono-compatibility.v1",
        "status": "pass",
        "measured_stereo_stems": 1,
        "applies_automatically": False,
    }
    plan.automation_preview = {
        "schema": "audio-too.automation-preview.v1",
        "status": "no_safe_moves",
        "moves": [],
        "applies_automatically": False,
        "production_processing_enabled": False,
    }

    # Mock render result
    mock_render_result = {
        "mixdown_wav_bytes": write_wav(
            np.zeros(duration_samples).tolist(),
            np.zeros(duration_samples).tolist(),
            sample_rate,
            bit_depth=24,
        ),
        "left": np.zeros(duration_samples),
        "right": np.zeros(duration_samples),
        "sample_rate": sample_rate,
        "measured_lufs": -14.0,
        "mix_plan": plan,
        "history": [{"iteration": 1, "measured_lufs": -14.0, "technical_score": 85}],
        "resource_profile": {
            "schema": "automix.resource_profile.v1",
            "stages": [{"stage": "validated", "elapsed_ms": 125.0, "peak_rss_bytes": 1048576}],
        },
        "quality_receipt": {
            "schema": "automix.quality_receipt.v1",
            "verification_available": True,
            "measured_deltas": {"integrated_lufs": 1.0},
        },
        "report": {
            "integrated_lufs": -14.0,
            "momentary_max_lufs": -12.0,
            "short_term_max_lufs": -13.0,
            "loudness_range_lu": 4.0,
            "flags": [],
            "metrics": {},
        }
    }



    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir)
        project_id = "test_proj_123"

        # 1. First package run -> v1
        status = package_mixdown_delivery(
            project_id=project_id,
            render_result=mock_render_result,
            output_dir=output_path,
            recipient_email=None,
            additional_formats=("flac", "mp3"),
        )

        assert status["ok"]
        assert status["version"] == 1
        
        proj_dir = output_path / project_id
        assert (proj_dir / "mixdown_v1.wav").exists()
        assert (proj_dir / "mix_report_v1.html").exists()
        assert (proj_dir / "mix_decisions_v1.json").exists()
        assert (proj_dir / "mix_package_v1.zip").exists()
        assert (proj_dir / "mixdown_v1.flac").read_bytes().startswith(b"fLaC")
        assert (proj_dir / "mixdown_v1.mp3").stat().st_size > 100
        manifest = json.loads((proj_dir / "mix_decisions_v1.json").read_text())
        assert manifest["musical_roles"] == plan.musical_roles
        assert manifest["arrangement"] == plan.arrangement
        assert manifest["relationships"] == plan.relationships
        assert manifest["mono_compatibility"] == plan.mono_compatibility
        assert manifest["automation_preview"] == plan.automation_preview
        assert manifest["resource_profile"] == mock_render_result["resource_profile"]
        assert manifest["quality_receipt"] == mock_render_result["quality_receipt"]

        import zipfile
        with zipfile.ZipFile(proj_dir / "mix_package_v1.zip") as package:
            assert {"mixdown_v1.flac", "mixdown_v1.mp3"}.issubset(package.namelist())

        # 2. Second package run -> v2
        status_v2 = package_mixdown_delivery(
            project_id=project_id,
            render_result=mock_render_result,
            output_dir=output_path,
            recipient_email=None,
        )

        assert status_v2["ok"]
        assert status_v2["version"] == 2
        assert (proj_dir / "mixdown_v2.wav").exists()
        assert (proj_dir / "mix_package_v2.zip").exists()


def test_manifest_records_kenn_autonomous_flag():
    """Stage H: the delivered JSON manifest must record whether the job ran
    with the opt-in autonomous KENN advisor, so Thursday/the client can
    report on it -- default is false when the render_result doesn't set it."""
    sample_rate = 44100
    duration_samples = 1000
    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
    ]
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    base_render_result = {
        "mixdown_wav_bytes": write_wav(
            np.zeros(duration_samples).tolist(),
            np.zeros(duration_samples).tolist(),
            sample_rate,
            bit_depth=24,
        ),
        "left": np.zeros(duration_samples),
        "right": np.zeros(duration_samples),
        "sample_rate": sample_rate,
        "measured_lufs": -14.0,
        "mix_plan": plan,
        "history": [],
        "report": {
            "integrated_lufs": -14.0,
            "momentary_max_lufs": -12.0,
            "short_term_max_lufs": -13.0,
            "loudness_range_lu": 4.0,
            "flags": [],
            "metrics": {},
        },
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir)

        package_mixdown_delivery(
            project_id="kenn-flag-default",
            render_result=base_render_result,
            output_dir=output_path,
        )
        manifest_default = json.loads(
            (output_path / "kenn-flag-default" / "mix_decisions_v1.json").read_text()
        )
        assert manifest_default["delivery_validation"]["ok"] is True
        assert manifest_default["delivery_validation"]["hard_failures"] == []
        assert "quality_gate" in manifest_default
        assert manifest_default["kenn_autonomous"] is False
        assert manifest_default["kenn_advisor_mode"] == "off"

        render_result_with_kenn = {**base_render_result, "kenn_autonomous": True}
        package_mixdown_delivery(
            project_id="kenn-flag-enabled",
            render_result=render_result_with_kenn,
            output_dir=output_path,
        )
        manifest_enabled = json.loads(
            (output_path / "kenn-flag-enabled" / "mix_decisions_v1.json").read_text()
        )
        assert manifest_enabled["kenn_autonomous"] is True


def test_correlation_id_defaults_to_a_synthesized_id_when_none_given():
    """docs/audits/2026-07-18-correlation-id-scoping.md: package_mixdown_delivery
    previously had no correlation-ID awareness at all -- whatever ID started
    a job was silently dropped at the final delivery step. Callers with no
    real ID to give (e.g. scripts/automix_local.py's offline dev path) get a
    project/version-scoped synthesized one instead of an empty/missing field."""
    sample_rate = 44100
    duration_samples = 1000
    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
    ]
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    render_result = {
        "mixdown_wav_bytes": write_wav(
            np.zeros(duration_samples).tolist(),
            np.zeros(duration_samples).tolist(),
            sample_rate,
            bit_depth=24,
        ),
        "left": np.zeros(duration_samples),
        "right": np.zeros(duration_samples),
        "sample_rate": sample_rate,
        "measured_lufs": -14.0,
        "mix_plan": plan,
        "history": [],
        "report": {
            "integrated_lufs": -14.0,
            "momentary_max_lufs": -12.0,
            "short_term_max_lufs": -13.0,
            "loudness_range_lu": 4.0,
            "flags": [],
            "metrics": {},
        },
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir)

        status = package_mixdown_delivery(
            project_id="corr-id-default",
            render_result=render_result,
            output_dir=output_path,
        )
        assert status["correlation_id"] == "mixdown:corr-id-default:v1"
        manifest = json.loads(
            (output_path / "corr-id-default" / "mix_decisions_v1.json").read_text()
        )
        assert manifest["correlation_id"] == "mixdown:corr-id-default:v1"


def test_correlation_id_propagates_a_real_caller_supplied_id():
    """A real caller (e.g. business/app/automix_worker.py's automix_jobs.correlation_id)
    must see its own ID come back unchanged, in both the returned status and
    the delivered manifest -- this is the actual gap the plan item names:
    'propagate the correlation ID ... through ... rendering outputs.'"""
    sample_rate = 44100
    duration_samples = 1000
    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
    ]
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    render_result = {
        "mixdown_wav_bytes": write_wav(
            np.zeros(duration_samples).tolist(),
            np.zeros(duration_samples).tolist(),
            sample_rate,
            bit_depth=24,
        ),
        "left": np.zeros(duration_samples),
        "right": np.zeros(duration_samples),
        "sample_rate": sample_rate,
        "measured_lufs": -14.0,
        "mix_plan": plan,
        "history": [],
        "report": {
            "integrated_lufs": -14.0,
            "momentary_max_lufs": -12.0,
            "short_term_max_lufs": -13.0,
            "loudness_range_lu": 4.0,
            "flags": [],
            "metrics": {},
        },
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir)

        status = package_mixdown_delivery(
            project_id="corr-id-real",
            render_result=render_result,
            output_dir=output_path,
            correlation_id="automix-job:abc123",
        )
        assert status["correlation_id"] == "automix-job:abc123"
        manifest = json.loads(
            (output_path / "corr-id-real" / "mix_decisions_v1.json").read_text()
        )
        assert manifest["correlation_id"] == "automix-job:abc123"


def test_manifest_distinguishes_shadow_from_autonomous_apply():
    sample_rate = 44100
    plan = generate_mix_plan(
        [StemProfile(name="kick.wav", instrument="kick")],
        masking_results=None,
        genre="pop",
        target_lufs=-14.0,
    )
    render_result = {
        "mixdown_wav_bytes": write_wav([0.0] * 100, [0.0] * 100, sample_rate, bit_depth=24),
        "left": np.zeros(100),
        "right": np.zeros(100),
        "sample_rate": sample_rate,
        "measured_lufs": -14.0,
        "mix_plan": plan,
        "history": [],
        "report": {"flags": [], "metrics": {}},
        "kenn_autonomous": False,
        "kenn_advisor_mode": "shadow",
        "kenn_advisor_shadow": {
            "artifact_id": "art_shadow_test",
            "status": "valid",
            "operation_count": 1,
            "operations": [
                {
                    "stem_id": "kick.wav",
                    "operation": "gain_delta",
                    "value": -1.0,
                    "unit": "dB",
                    "evidence_source_ids": ["gain-note@index:v-test"],
                    "confidence": 0.95,
                    "reason": "Grounded shadow suggestion.",
                }
            ],
        },
    }
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir)
        package_mixdown_delivery("kenn-shadow", render_result, output_path)
        manifest = json.loads(
            (output_path / "kenn-shadow" / "mix_decisions_v1.json").read_text()
        )
    assert manifest["kenn_autonomous"] is False
    assert manifest["kenn_advisor_mode"] == "shadow"
    assert manifest["kenn_advisor_shadow"]["artifact_id"] == "art_shadow_test"
    assert manifest["kenn_advisor_shadow"]["operations"][0]["operation"] == "gain_delta"


def test_advisory_flags_attribution():
    sample_rate = 44100
    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="synth_lead.wav", instrument="synth", peak_dbfs=-10.0, rms_dbfs=-22.0, crest_factor_db=12.0),
    ]
    plan = generate_mix_plan(profiles, masking_results=None, genre="pop", target_lufs=-14.0)
    plan.decisions_log = [
        "Gain staging: anchor set to kick.wav",
        "EQ adjustment for low-mid buildup on synth_lead.wav",
        "Limiter ceiling set to -1.30 dBTP",
    ]
    plan.mono_compatibility = {
        "schema": "audio-too.mono-compatibility.v1",
        "status": "warning",
        "measured_stereo_stems": 2,
        "summed_sections": [
            {
                "section_id": "Chorus",
                "severity": "high",
                "contributors": [
                    {
                        "stem_name": "synth_lead.wav",
                        "fold_down_improvement_db": 4.5,
                    }
                ],
            }
        ],
    }

    mock_render_result = {
        "mixdown_wav_bytes": write_wav([0.0] * 100, [0.0] * 100, sample_rate, bit_depth=24),
        "left": np.zeros(100),
        "right": np.zeros(100),
        "sample_rate": sample_rate,
        "measured_lufs": -14.0,
        "mix_plan": plan,
        "history": [],
        "report": {
            "flags": [
                {
                    "severity": "high",
                    "label": "Low headroom",
                    "detail": "Peak level is above -1.0 dBFS.",
                },
                {
                    "severity": "high",
                    "label": "Mono risk",
                    "detail": "Stereo correlation is low.",
                },
            ]
        },
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir)
        package_mixdown_delivery("test-attribution", mock_render_result, output_path)
        manifest = json.loads(
            (output_path / "test-attribution" / "mix_decisions_v1.json").read_text()
        )

    assert "advisory_flags" in manifest
    advisory = manifest["advisory_flags"]
    assert len(advisory) == 2

    # Verify Low headroom attribution
    hr_flag = next(f for f in advisory if f["label"] == "Low headroom")
    assert hr_flag["attribution"]["bus"] == "master"
    assert hr_flag["attribution"]["stem"] is None
    assert "limiter" in hr_flag["attribution"]["responsible_decision"].lower()

    # Verify Mono risk attribution
    mono_flag = next(f for f in advisory if f["label"] == "Mono risk")
    assert mono_flag["attribution"]["section"] == "Chorus"
    assert mono_flag["attribution"]["stem"] == "synth_lead.wav"
    assert (
        mono_flag["attribution"]["responsible_decision"] is None
        or "polarity" in mono_flag["attribution"]["responsible_decision"].lower()
        or "phase" in mono_flag["attribution"]["responsible_decision"].lower()
    )
