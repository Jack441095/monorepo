"""Integration tests for Thursday Autonomous Producer Task Director."""

from __future__ import annotations

import pytest

import thursday.autonomous_producer as autonomous_producer
from thursday.autonomous_producer import AutonomousProducerUnavailable, ThursdayTaskDirector


def test_thursday_autonomous_producer_pipeline_fails_closed():
    """Phase-0 P0-8 (docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md):
    run_autonomous_producer_pipeline() previously reported a complete
    4-stage pipeline unconditionally, including four fixed stem filenames
    that were never written to disk -- no real composition, mixing, or
    audio work occurred. This is a deliberate behavioural change, not a
    regression: the method must now fail closed (NOT_IMPLEMENTED/
    PROTOTYPE_ONLY) rather than fabricate a completed run."""
    director = ThursdayTaskDirector()
    instruction = "Create a 90 BPM Lo-Fi Hip Hop track with 60% swing and export AutoMix stems"

    res = director.run_autonomous_producer_pipeline(
        instruction=instruction, genre="lofi", bpm=90
    )

    assert res["ok"] is False
    assert res["status"] == "NOT_IMPLEMENTED"
    assert res["reason"] == "PROTOTYPE_ONLY"
    assert res["owner_review_required"] is True
    assert res["instruction"] == instruction
    assert "pipeline_steps" not in res
    assert "steps_completed" not in res


def test_prototype_producer_pipeline_is_preserved_but_not_reachable():
    """The original fabricated-output implementation is kept for owner
    inspection / a future real rebuild, but must not be reachable from the
    public method."""
    director = ThursdayTaskDirector()
    assert hasattr(director, "_run_autonomous_producer_pipeline_prototype")
    prototype_res = director._run_autonomous_producer_pipeline_prototype(
        instruction="internal QA only", genre="lofi", bpm=90
    )
    public_res = director.run_autonomous_producer_pipeline(
        instruction="internal QA only", genre="lofi", bpm=90
    )
    assert prototype_res["ok"] is True
    assert "pipeline_steps" in prototype_res
    assert public_res["ok"] is False
    assert "pipeline_steps" not in public_res


def test_module_imports_without_touching_composition_or_torch():
    """The regression this whole module was rewritten to fix: importing
    thursday.autonomous_producer (and therefore thursday_routes.py, and
    therefore business/app/server.py) must never require torch/composition
    to be importable -- data/logs/website.log showed this exact import
    chain crashing the entire website server outright. Proven implicitly
    by every other test in this file even collecting, but asserted
    explicitly here: the composition imports are not at module scope."""
    import inspect

    source = inspect.getsource(autonomous_producer)
    # _load_composition_deps() is where the real (deferred) imports live and
    # is defined before the class, so split before that function, not before
    # the class -- splitting on the class would leave the deferred-loader's
    # own `from composition import ...` lines miscounted as module-level.
    module_level_source = source.split("def _load_composition_deps")[0]
    assert "import composition" not in module_level_source
    assert "from composition" not in module_level_source


def test_construction_raises_a_clean_error_when_composition_deps_are_unavailable(monkeypatch):
    def _boom():
        raise AutonomousProducerUnavailable(
            "Autonomous producer pipeline is unavailable (composition/torch dependency failed to load: simulated)"
        )

    monkeypatch.setattr(autonomous_producer, "_load_composition_deps", _boom)

    with pytest.raises(AutonomousProducerUnavailable, match="unavailable"):
        ThursdayTaskDirector()


def test_load_composition_deps_wraps_a_real_import_failure(monkeypatch):
    """Exercises the real _load_composition_deps() function itself (not a
    mock replacing it), proving it actually converts an ImportError into
    the catchable AutonomousProducerUnavailable exception."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("composition"):
            raise ImportError(f"simulated missing module: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(AutonomousProducerUnavailable, match="unavailable"):
        autonomous_producer._load_composition_deps()
