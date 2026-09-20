import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("context_preview_plan.py")
SPEC = importlib.util.spec_from_file_location("context_preview_plan", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_tempo_plan_is_reversible_and_key_is_not_guessed():
    payload = {"cards": [{
        "path": "/loop.wav",
        "temporal": {"estimated_tempo_bpm": 120.0, "form_hint": "possibly_loop"},
        "pitch": {"median_f0_hz": 440.0},
    }]}
    result = MODULE.build_plan(payload, target_bpm=90.0, target_key="C")
    row = result["previews"][0]
    assert row["tempo"]["time_stretch_rate"] == 0.75
    assert row["pitch"]["status"] == "unavailable"
    assert result["safety"]["key_inferred_from_median_pitch"] is False
    assert result["safety"]["source_audio_modified"] is False


def test_missing_tempo_and_invalid_transform_fail_closed():
    payload = {"cards": [{"path": "/x.wav", "temporal": {}}]}
    result = MODULE.build_plan(payload, target_bpm=100.0)
    assert result["previews"][0]["tempo"]["status"] == "unavailable"
    try:
        MODULE.build_plan(payload, target_bpm=100.0, pitch_semitones=30.0)
    except ValueError as exc:
        assert "within" in str(exc)
    else:
        raise AssertionError("unsafe pitch shift accepted")
