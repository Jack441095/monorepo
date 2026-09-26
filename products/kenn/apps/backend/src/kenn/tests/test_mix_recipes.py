"""Named mix recipes: a clear mix intention becomes a small, exact, confirmable set of changes."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture()
def ask(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    return lambda text: handle_command(text, session_id=f"recipe-{tmp_path.name}", service=LiveActionService(FakeLiveBackend()))


def _steps(result):
    return result["proposal"]["steps"]


def _db_change(step):
    return volume_law.raw_to_db(step["after"]) - volume_law.raw_to_db(step["before"])


def test_room_for_the_kick_turns_the_bass_down_a_real_one_and_a_half_db(ask) -> None:
    for phrasing in ("make room for the kick", "the kick and bass are fighting"):
        (step,) = _steps(ask(phrasing))
        assert step["track_name"] == "Bass" and _db_change(step) == pytest.approx(-1.5, abs=0.05)


def test_vocal_space_sends_the_vocal_to_the_reverb_and_the_delay(ask) -> None:
    steps = _steps(ask("give the vocal some space"))
    assert {(s["return_track_name"], s["after"]) for s in steps} == {("A-Reverb", 0.15), ("B-Delay", 0.08)}


def test_vocal_space_finds_the_reverb_when_the_snapshot_has_no_returns(ask, monkeypatch, tmp_path) -> None:
    # The real bridge's session snapshot leaves return_tracks empty; on 26 Sept 2026 that made "give the vocal some
    # space" say the demo set had no reverb return.
    class RealShapedLive(FakeLiveBackend):
        def query_session_state(self, *args, **kwargs):
            return {**super().query_session_state(*args, **kwargs), "return_tracks": []}

    result = handle_command("give the vocal some space", session_id=f"recipe-{tmp_path.name}",
                            service=LiveActionService(RealShapedLive()))
    assert {s["return_track_name"] for s in _steps(result)} == {"A-Reverb", "B-Delay"}


def test_drums_forward_lifts_the_drum_bus_and_never_past_zero(ask) -> None:
    (step,) = _steps(ask("bring the drums forward"))
    assert step["track_name"] == "Drum Bus" and _db_change(step) == pytest.approx(1.5, abs=0.05)
    assert volume_law.raw_to_db(step["after"]) <= 0.0


def test_an_already_centred_low_end_changes_nothing(ask) -> None:
    result = ask("make the low end mono")
    assert result["status"] == "clarification_required" and "already centred" in result["answer"]


def test_a_vague_volume_request_is_not_a_recipe(ask) -> None:
    # "too loud" names no amount: KENN asks, as the phrasing gate expects, rather than picking one.
    assert ask("the hats are too loud").get("proposal") is None


def test_push_back_turns_down_and_adds_reverb(ask) -> None:
    fader, send = _steps(ask("push the synth back"))
    assert fader["track_name"] == "Synth" and _db_change(fader) == pytest.approx(-1.5, abs=0.05)
    assert send["return_track_name"] == "A-Reverb" and send["after"] == 0.15


def test_sit_behind_moves_only_the_first_track(ask) -> None:
    steps = _steps(ask("put the synth behind the vocal"))
    assert {s["track_name"] for s in steps} == {"Synth"}
    assert _db_change(steps[0]) == pytest.approx(-2.0, abs=0.05)


def test_compressor_recipes_work_in_real_decibels_on_the_existing_compressor(ask) -> None:
    for phrasing, track in (("tighten the drum bus", "Drum Bus"), ("tame the vocal peaks", "Lead Vocal")):
        (step,) = _steps(ask(phrasing))
        assert step["track_name"] == track and step["action"] == "set_device_parameter"
        assert step["after"] < step["before"]


def test_a_compressor_recipe_asks_when_there_is_no_compressor() -> None:
    from kenn.core import mix_recipes

    built = mix_recipes.RECIPES[[r.name for r in mix_recipes.RECIPES].index("vocal_peaks")].build(
        mix_recipes.Set([{"name": "Lead Vocal", "index": 0, "devices": []}], []), None)
    assert isinstance(built, str) and "no Compressor" in built


def test_rhythm_section_solos_kick_snare_and_bass(ask) -> None:
    assert {s["track_name"] for s in _steps(ask("solo the rhythm section"))} == {"Kick", "Snare / Clap", "Bass"}


def test_a_recipe_that_would_change_nothing_says_so(ask) -> None:
    result = ask("dry up the vocal")  # the demo vocal has no sends yet
    assert result.get("proposal") is None and "nothing to change" in result["answer"]


def test_taking_the_reverb_off_leaves_the_delay_alone(ask) -> None:
    from kenn.core import mix_recipes

    recipe = mix_recipes.match("take the reverb off the snare")
    s = mix_recipes.Set([{"name": "Snare / Clap", "index": 1}], [{"name": "A-Reverb", "index": 0}, {"name": "B-Delay", "index": 1}])
    commands, _summary = recipe.build(s, recipe.pattern.search("take the reverb off the snare"))
    assert commands == ["send the Snare / Clap to the A-Reverb at 0%"]


def test_there_are_fifteen_named_recipes() -> None:
    from kenn.core import mix_recipes
    from kenn.core import subjective_translator  # noqa: F401 (the original three live there)

    assert len(mix_recipes.RECIPES) + 3 >= 15


def test_clearing_the_solos_unsolos_only_what_is_soloed(ask) -> None:
    ask("solo the rhythm section")  # a proposal only; nothing is soloed in the set yet
    assert "Nothing is soloed" in ask("unsolo everything")["answer"]
    from kenn.core import mix_recipes

    recipe = mix_recipes.match("clear the solos")
    s = mix_recipes.Set([{"name": "Kick", "index": 0, "soloed": True}, {"name": "Bass", "index": 4, "soloed": False}], [])
    commands, _summary = recipe.build(s, None)
    assert commands == ["unsolo Kick"]


def test_a_recipe_asks_which_track_when_a_role_matches_several() -> None:
    # Two basses: "make room for the kick" must not pick one of them for the producer.
    from kenn.core import mix_recipes

    recipe = mix_recipes.match("make room for the kick")
    s = mix_recipes.Set([{"name": "Kick", "index": 0, "volume": 0.5}, {"name": "Bass", "index": 1, "volume": 0.5},
                         {"name": "Sub Bass", "index": 2, "volume": 0.5}], [])
    built = recipe.build(s, None)
    assert isinstance(built, str) and "'Bass' or 'Sub Bass'" in built


def test_mono_low_end_asks_rather_than_centring_only_some() -> None:
    from kenn.core import mix_recipes

    recipe = mix_recipes.match("make the low end mono")
    tracks = [{"name": n, "index": i, "pan": 0.3} for i, n in enumerate(["Kick", "Bass", "Sub", "808", "Kick 2"])]
    built = recipe.build(mix_recipes.Set(tracks, []), None)
    assert isinstance(built, str) and "at most three" in built
