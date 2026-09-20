"""Startup drums toggle for generative main.py."""

from __future__ import annotations

import argparse

from audiogen_core.config import CONFIG


def _apply_drums_enabled(config, enabled: bool) -> None:
    from main import _apply_drums_enabled as apply

    apply(config, enabled)


def test_apply_drums_enabled_off():
    _apply_drums_enabled(CONFIG, False)
    sc = CONFIG.audio.chorus_kick_sidechain
    assert sc.enabled is False
    assert sc.kick_enabled is False
    assert sc.sidechain_enabled is False
    assert CONFIG.composition.percussion_lane_enabled is False
    _apply_drums_enabled(CONFIG, True)


def test_resolve_drums_from_args_no_drums():
    from main import _resolve_drums_from_args

    _apply_drums_enabled(CONFIG, True)
    args = argparse.Namespace(drums=None)
    _resolve_drums_from_args(CONFIG, args)
    assert CONFIG.audio.chorus_kick_sidechain.kick_enabled is True


def test_resolve_drums_from_args_no_drums_flag():
    from main import _resolve_drums_from_args

    _apply_drums_enabled(CONFIG, True)
    args = argparse.Namespace(drums=False)
    _resolve_drums_from_args(CONFIG, args)
    assert CONFIG.audio.chorus_kick_sidechain.kick_enabled is False
    _apply_drums_enabled(CONFIG, True)
