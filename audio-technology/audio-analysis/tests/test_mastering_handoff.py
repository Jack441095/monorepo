"""Stage 11.3 — mastering handoff: bundle fields are all real, not stubbed.

Builds a real synthetic mix through the actual render pipeline, packages
it through the real ``mix_delivery.package_mixdown_delivery``, and asserts
every field in the resulting mastering-handoff bundle traces back to that
real data (stem prints match the actual MixPlan, loudness specs match the
render's real measured numbers, delivered file paths match files that
actually exist on disk, and mastering-target numbers match the config
module's documented industry figures).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from audio_analysis.export.mastering_handoff import build_mastering_handoff
from audio_analysis.export.mastering_targets import get_mastering_target
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_delivery import package_mixdown_delivery
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
from audio_analysis.mixdown.mix_validator import verify_render_output
from audio_analysis.mixdown.stem_classifier import StemProfile

INDEX_CHUNKS = (
    Path(__file__).resolve().parent.parent.parent
    / "studio" / "kenn" / "kenn" / "data" / "index" / "chunks.jsonl"
)


def _real_render_result(genre: str = "rock", target_lufs: float = -14.0) -> dict:
    sample_rate = 44100
    duration_samples = 44100
    t = np.linspace(0, 1.0, duration_samples, endpoint=False)
    kick = np.sin(2.0 * np.pi * 60.0 * t) * 0.6
    guitar = np.sin(2.0 * np.pi * 660.0 * t) * 0.35

    prepared_stems = [
        {"name": "kick.wav", "samples": kick.tolist(), "sample_rate": sample_rate},
        {"name": "guitar.wav", "samples": guitar.tolist(), "sample_rate": sample_rate},
    ]
    profiles = [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0),
        StemProfile(name="guitar.wav", instrument="guitar", peak_dbfs=-8.0, rms_dbfs=-20.0, crest_factor_db=12.0),
    ]
    plan = generate_mix_plan(profiles, masking_results=None, genre=genre, target_lufs=target_lufs)
    return mix_and_render_stems(prepared_stems, plan)


@pytest.fixture(scope="module", autouse=True)
def kenn_state_isolation(tmp_path_factory):
    import os
    state_dir = tmp_path_factory.mktemp("kenn-mastering-handoff")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


@pytest.fixture(scope="module")
def real_render():
    return _real_render_result()


@pytest.fixture(scope="module")
def real_delivery(real_render):
    with tempfile.TemporaryDirectory() as tmp_dir:
        status = package_mixdown_delivery(
            project_id="proj_handoff_test",
            render_result=real_render,
            output_dir=tmp_dir,
        )
        yield status, tmp_dir


def test_stem_prints_match_the_real_mix_plan(real_render):
    handoff = build_mastering_handoff(real_render, project_id="proj_stub_check")
    plan = real_render["mix_plan"]

    printed_names = {s["stem_name"] for s in handoff["stem_prints"]}
    plan_names = {s.stem_name for s in plan.stems}
    assert printed_names == plan_names
    assert printed_names == {"kick.wav", "guitar.wav"}

    for printed in handoff["stem_prints"]:
        matching = next(s for s in plan.stems if s.stem_name == printed["stem_name"])
        assert printed["gain_db"] == matching.gain_db
        assert printed["pan"] == matching.pan
        assert printed["stereo_width"] == matching.stereo_width
        assert printed["mono_below_hz"] == matching.mono_below_hz


def test_loudness_specs_match_real_measured_render_values(real_render):
    handoff = build_mastering_handoff(real_render)
    specs = handoff["loudness_specs"]

    assert specs["measured_integrated_lufs"] == real_render["measured_lufs"]
    assert specs["target_lufs"] == real_render["mix_plan"].target_lufs

    # Cross-check true peak/crest factor against an independent call to the
    # same validator the delivery pipeline gates on -- must match exactly
    # since build_mastering_handoff calls the identical function.
    independent = verify_render_output(
        np.asarray(real_render["left"], dtype=np.float64),
        np.asarray(real_render["right"], dtype=np.float64),
        int(real_render["sample_rate"]),
        real_render["mixdown_wav_bytes"],
        target_lufs=real_render["mix_plan"].target_lufs,
        measured_lufs=real_render["measured_lufs"],
        ceiling_db=real_render["mix_plan"].bus.limiter_ceiling_db,
    )
    assert specs["true_peak_dbtp"] == independent["metrics"]["true_peak_dbtp"]
    assert specs["crest_factor_db"] == independent["metrics"]["crest_factor_db"]
    assert specs["pre_release_validation_ok"] == independent["ok"]


@pytest.mark.parametrize("context", ["streaming", "cd", "vinyl", "broadcast"])
def test_mastering_target_section_matches_config_module(real_render, context):
    handoff = build_mastering_handoff(real_render, target_context=context)
    expected = get_mastering_target(context)
    assert handoff["mastering_target"]["context"] == context
    assert handoff["mastering_target"]["integrated_lufs_target"] == expected.integrated_lufs_target
    assert handoff["mastering_target"]["true_peak_ceiling_dbtp"] == expected.true_peak_ceiling_dbtp
    assert handoff["mastering_target"]["citation"] == expected.citation


def test_unknown_target_context_raises_with_valid_options(real_render):
    with pytest.raises(ValueError, match="Unknown mastering context"):
        build_mastering_handoff(real_render, target_context="cassette")


def test_delivered_files_reference_real_files_on_disk(real_delivery, real_render):
    status, tmp_dir = real_delivery
    handoff = build_mastering_handoff(
        real_render, delivery_status=status, project_id="proj_handoff_test"
    )
    delivered = handoff["delivered_files"]

    assert delivered["version"] == status["version"]
    assert delivered["wav_path"] == status["wav_path"]
    assert Path(delivered["wav_path"]).exists()
    assert Path(delivered["zip_path"]).exists()
    assert Path(delivered["report_path"]).exists()


def test_decisions_log_is_the_real_automix_log_not_empty(real_render):
    handoff = build_mastering_handoff(real_render)
    assert handoff["decisions_log"] == real_render["mix_plan"].decisions_log
    assert len(handoff["decisions_log"]) > 0


def test_mastering_notes_passthrough_and_no_default_placeholder(real_render):
    handoff = build_mastering_handoff(real_render, mastering_notes="Client wants a warmer low end.")
    assert handoff["mastering_notes"] == "Client wants a warmer low end."

    handoff_default = build_mastering_handoff(real_render)
    assert handoff_default["mastering_notes"] == ""


@pytest.mark.skipif(not INDEX_CHUNKS.exists(), reason="KENN index not built")
def test_kenn_rationale_bundle_is_real_grounded_output(real_render):
    handoff = build_mastering_handoff(real_render, allow_llm=False)
    assert handoff["kenn_rationale"], "expected at least one KENN explanation"
    for item in handoff["kenn_rationale"]:
        assert item["answer"]
        # Every entry either cites a real source or is legitimately empty
        # (abstained) -- never a fabricated source list.
        for src in item["sources"]:
            assert isinstance(src, dict)
            assert src.get("source")


def test_missing_mix_plan_raises_clear_error():
    with pytest.raises(ValueError, match="mix_plan"):
        build_mastering_handoff({"left": [0.0], "right": [0.0], "sample_rate": 44100})
