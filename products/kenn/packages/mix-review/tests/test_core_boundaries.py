import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import core  # noqa: E402


def test_runtime_must_be_external(tmp_path):
    try:
        core.MixReviewBoundary(ROOT, ROOT / ".runtime", 100, frozenset({".wav"}))
    except ValueError:
        pass
    else:
        raise AssertionError("product-local runtime was accepted")


def test_boundary_is_memory_only_and_hashes_source(tmp_path):
    audio = tmp_path / "mix.wav"
    audio.write_bytes(b"fixture")
    boundary = core.MixReviewBoundary(ROOT, tmp_path / "runtime", 100, frozenset({".wav"}))
    receipt = boundary.analyze_path(
        audio,
        validate=lambda payload, name: {"ok": True},
        analyze=lambda payload, **kwargs: {"ok": True, "metrics": {"crest_factor_db": 12, "integrated_lufs": -14}},
    )
    assert receipt["status"] == "completed"
    assert receipt["storage"] == "memory_only"
    assert receipt["source"]["sha256"]
    assert not (tmp_path / "runtime").exists()


def test_semantics_are_deterministic_and_bounded():
    assert core.classify_mix_style({"integrated_lufs": -8, "crest_factor_db": 6})["label"] == "loudness-war-leaning"
    plan = core.next_revision_plan({"action_plan": [{"focus": "Bass", "action": "Check the low end."}]})
    assert len(plan["steps"]) == 1
    assert "Loudness" in core.deterministic_critique({"metrics": {"integrated_lufs": -14, "crest_factor_db": 10}})
