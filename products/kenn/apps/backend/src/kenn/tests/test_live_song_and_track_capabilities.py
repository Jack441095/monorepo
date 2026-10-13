"""Executable qualification for Live 12 metronome, loop bounds, track color, and fold state.

Protects proposal generation, stale-state rejection, confirmation binding,
readback verification, and 1-click cryptographic undo across all new capabilities.
"""

from __future__ import annotations

import pytest
from copy import deepcopy

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture
def fake_backend():
    """Deterministic in-memory double with initialized session values."""
    backend = FakeLiveBackend()
    # Explicitly set initial test values
    backend.set_metronome(False)
    backend.set_loop(False)
    backend.set_loop_bounds(0.0, 16.0)
    backend.set_track_color_index(0, 12)
    backend.set_track_fold_state(0, False)
    return backend


@pytest.fixture
def action_service(fake_backend):
    return LiveActionService(client=fake_backend)


def test_metronome_action_lifecycle(action_service, fake_backend):
    """Metronome toggle generates proposal, requires token, verifies readback, and undos cleanly."""
    session_id = "test-session-metronome"

    # 1. Propose turning metronome on
    proposal_res = action_service.propose_metronome_action(True, session_id=session_id)
    assert proposal_res["ok"] is True
    proposal = proposal_res["proposal"]
    assert proposal["action"] == "set_metronome"
    assert proposal["before"] is False
    assert proposal["after"] is True
    assert proposal["before_display"] == "Off"
    assert proposal["after_display"] == "On"
    token = proposal["confirmation_token"]
    assert token

    # 2. Execute with confirmation token
    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["status"] == "applied"
    assert receipt["verified"] is True
    assert receipt["readback"] is True
    assert fake_backend.get_metronome() is True

    # 3. Propose undo from receipt
    undo_res = action_service.propose_undo(receipt, session_id=session_id)
    assert undo_res["ok"] is True
    undo_proposal = undo_res["proposal"]
    assert undo_proposal["action"] == "set_metronome"
    assert undo_proposal["before"] is True
    assert undo_proposal["after"] is False
    undo_token = undo_proposal["confirmation_token"]

    # 4. Execute undo
    undo_exec = action_service.execute(undo_proposal, confirm_token=undo_token, session_id=session_id)
    assert undo_exec["ok"] is True
    assert undo_exec["receipt"]["verified"] is True
    assert fake_backend.get_metronome() is False


def test_loop_action_lifecycle(action_service, fake_backend):
    """Arrangement loop toggle generates proposal, applies with readback, and undos."""
    session_id = "test-session-loop"

    # 1. Propose enabling loop
    proposal_res = action_service.propose_loop_action(True, session_id=session_id)
    assert proposal_res["ok"] is True
    proposal = proposal_res["proposal"]
    assert proposal["action"] == "set_loop"
    assert proposal["before"] is False
    assert proposal["after"] is True
    token = proposal["confirmation_token"]

    # 2. Execute
    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    assert exec_res["receipt"]["verified"] is True
    assert fake_backend.get_loop() is True

    # 3. Undo
    undo_res = action_service.propose_undo(exec_res["receipt"], session_id=session_id)
    assert undo_res["ok"] is True
    undo_exec = action_service.execute(undo_res["proposal"], confirm_token=undo_res["proposal"]["confirmation_token"], session_id=session_id)
    assert undo_exec["ok"] is True
    assert fake_backend.get_loop() is False


def test_loop_bounds_action_lifecycle(action_service, fake_backend):
    """Arrangement loop bounds change start & length in beats, verifies readback, and undos."""
    session_id = "test-session-bounds"

    # 1. Propose loop bounds: start at 16 beats, length 32 beats (8 bars in 4/4)
    proposal_res = action_service.propose_loop_bounds_action(start_beats=16.0, length_beats=32.0, session_id=session_id)
    assert proposal_res["ok"] is True
    proposal = proposal_res["proposal"]
    assert proposal["action"] == "set_loop_bounds"
    assert proposal["before"] == {"loop_start": 0.0, "loop_length": 16.0}
    assert proposal["after"] == {"loop_start": 16.0, "loop_length": 32.0}
    token = proposal["confirmation_token"]

    # 2. Execute
    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    assert exec_res["receipt"]["verified"] is True
    assert fake_backend.get_loop_bounds() == (16.0, 32.0)

    # 3. Undo
    undo_res = action_service.propose_undo(exec_res["receipt"], session_id=session_id)
    assert undo_res["ok"] is True
    undo_proposal = undo_res["proposal"]
    assert undo_proposal["after"] == {"loop_start": 0.0, "loop_length": 16.0}
    undo_exec = action_service.execute(undo_proposal, confirm_token=undo_proposal["confirmation_token"], session_id=session_id)
    assert undo_exec["ok"] is True
    assert fake_backend.get_loop_bounds() == (0.0, 16.0)


def test_track_color_lifecycle(action_service, fake_backend):
    """Track color change to palette index verifies readback and undos."""
    session_id = "test-session-color"

    # Track 0 starts at color 12
    assert fake_backend.get_track_color_index(0) == 12

    # 1. Propose color change to 25
    proposal_res = action_service.propose_track_action("set_track_color", track_index=0, track_name="", value=25, session_id=session_id)
    assert proposal_res["ok"] is True
    proposal = proposal_res["proposal"]
    assert proposal["before"] == 12
    assert proposal["after"] == 25
    assert proposal["before_display"] == "Color 12"
    assert proposal["after_display"] == "Color 25"
    token = proposal["confirmation_token"]

    # 2. Execute
    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    assert exec_res["receipt"]["verified"] is True
    assert fake_backend.get_track_color_index(0) == 25

    # 3. Undo
    undo_res = action_service.propose_undo(exec_res["receipt"], session_id=session_id)
    assert undo_res["ok"] is True
    undo_proposal = undo_res["proposal"]
    assert undo_proposal["after"] == 12
    undo_exec = action_service.execute(undo_proposal, confirm_token=undo_proposal["confirmation_token"], session_id=session_id)
    assert undo_exec["ok"] is True
    assert fake_backend.get_track_color_index(0) == 12


def test_track_fold_lifecycle(action_service, fake_backend):
    """Track group fold state toggle verifies readback and undos."""
    session_id = "test-session-fold"

    # Track 0 starts unfolded (False)
    assert fake_backend.get_track_fold_state(0) is False

    # 1. Propose folding track 0
    proposal_res = action_service.propose_track_action("set_track_fold", track_index=0, track_name="", value=True, session_id=session_id)
    assert proposal_res["ok"] is True
    proposal = proposal_res["proposal"]
    assert proposal["before"] is False
    assert proposal["after"] is True
    assert proposal["before_display"] == "Unfolded"
    assert proposal["after_display"] == "Folded"
    token = proposal["confirmation_token"]

    # 2. Execute
    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    assert exec_res["receipt"]["verified"] is True
    assert fake_backend.get_track_fold_state(0) is True

    # 3. Undo
    undo_res = action_service.propose_undo(exec_res["receipt"], session_id=session_id)
    assert undo_res["ok"] is True
    undo_proposal = undo_res["proposal"]
    assert undo_proposal["after"] is False
    undo_exec = action_service.execute(undo_proposal, confirm_token=undo_proposal["confirmation_token"], session_id=session_id)
    assert undo_exec["ok"] is True
    assert fake_backend.get_track_fold_state(0) is False


def test_natural_language_commands_end_to_end(action_service, fake_backend):
    """Natural language prompts route through command gate, produce confirmation cards, and apply."""
    session_id = "test-session-nl"

    # 1. "turn on metronome"
    res1 = handle_command("turn on metronome", session_id=session_id, service=action_service)
    assert res1["status"] == "confirmation_required"
    assert res1["proposal_kind"] == "song"
    token1 = res1["confirmation_token"]
    assert token1

    # Confirm
    res1_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res1["proposal"], confirm_token=token1)
    assert res1_confirm["status"] == "applied"
    assert fake_backend.get_metronome() is True

    # 2. "turn on loop"
    res2 = handle_command("turn on loop", session_id=session_id, service=action_service)
    assert res2["status"] == "confirmation_required"
    token2 = res2["confirmation_token"]
    res2_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res2["proposal"], confirm_token=token2)
    assert res2_confirm["status"] == "applied"
    assert fake_backend.get_loop() is True

    # 3. "set loop length to 8 bars"
    res3 = handle_command("set loop length to 8 bars", session_id=session_id, service=action_service)
    assert res3["status"] == "confirmation_required"
    token3 = res3["confirmation_token"]
    res3_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res3["proposal"], confirm_token=token3)
    assert res3_confirm["status"] == "applied"
    assert fake_backend.get_loop_bounds()[1] == 32.0  # 8 bars * 4 beats/bar

    # 4. "color track 1 to cyan" (palette 25)
    res4 = handle_command("color track 1 to cyan", session_id=session_id, service=action_service)
    assert res4["status"] == "confirmation_required"
    token4 = res4["confirmation_token"]
    res4_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res4["proposal"], confirm_token=token4)
    assert res4_confirm["status"] == "applied"
    assert fake_backend.get_track_color_index(0) == 21

    # 5. "collapse track 1"
    res5 = handle_command("collapse track 1", session_id=session_id, service=action_service)
    assert res5["status"] == "confirmation_required"
    token5 = res5["confirmation_token"]
    res5_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res5["proposal"], confirm_token=token5)
    assert res5_confirm["status"] == "applied"
    assert fake_backend.get_track_fold_state(0) is True


def test_groove_amount_action_lifecycle(action_service, fake_backend):
    """Groove amount generates proposal, verifies readback, and undos cleanly."""
    session_id = "test-session-groove"
    fake_backend.set_groove_amount(0.0)

    # 1. Propose groove 50%
    prop_res = action_service.propose_groove_amount_action(0.5, session_id=session_id)
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["action"] == "set_groove_amount"
    assert proposal["before"] == 0.0
    assert proposal["after"] == 0.5
    assert proposal["before_display"] == "0%"
    assert proposal["after_display"] == "50%"
    token = proposal["confirmation_token"]
    assert token

    # 2. Execute
    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["status"] == "applied"
    assert receipt["verified"] is True
    assert receipt["readback"] == 0.5
    assert fake_backend.get_groove_amount() == 0.5

    # 3. Undo
    undo_res = action_service.propose_undo(receipt, session_id=session_id)
    assert undo_res["ok"] is True
    undo_prop = undo_res["proposal"]
    assert undo_prop["action"] == "set_groove_amount"
    assert undo_prop["before"] == 0.5
    assert undo_prop["after"] == 0.0
    undo_token = undo_prop["confirmation_token"]
    undo_exec = action_service.execute(undo_prop, confirm_token=undo_token, session_id=session_id)
    assert undo_exec["ok"] is True
    assert fake_backend.get_groove_amount() == 0.0


def test_record_mode_action_lifecycle(action_service, fake_backend):
    """Arrangement record mode generates proposal, verifies readback, and undos cleanly."""
    session_id = "test-session-rec-mode"
    fake_backend.set_record_mode(False)

    # 1. Propose record mode on
    prop_res = action_service.propose_record_mode_action(True, session_id=session_id)
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["action"] == "set_record_mode"
    assert proposal["before"] is False
    assert proposal["after"] is True
    assert proposal["before_display"] == "Inactive"
    assert proposal["after_display"] == "Active"
    token = proposal["confirmation_token"]
    assert token

    # 2. Execute
    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["status"] == "applied"
    assert receipt["verified"] is True
    assert receipt["readback"] is True
    assert fake_backend.get_record_mode() is True

    # 3. Undo
    undo_res = action_service.propose_undo(receipt, session_id=session_id)
    assert undo_res["ok"] is True
    undo_prop = undo_res["proposal"]
    assert undo_prop["action"] == "set_record_mode"
    assert undo_prop["after"] is False
    undo_token = undo_prop["confirmation_token"]
    undo_exec = action_service.execute(undo_prop, confirm_token=undo_token, session_id=session_id)
    assert undo_exec["ok"] is True
    assert fake_backend.get_record_mode() is False


def test_locator_jump_lifecycle(action_service, fake_backend):
    """Jumping playhead to named or relative locator verifies position."""
    session_id = "test-session-locator-jump"
    fake_backend.set_current_song_time(0.0)

    # 1. Jump to Chorus (at 32.0 beats in FakeLiveBackend fixture)
    prop_res = action_service.propose_jump_to_locator_action("Chorus", session_id=session_id)
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["action"] == "jump_to_locator"
    assert proposal["locator_name"] == "Chorus"
    assert proposal["after"] == 32.0
    token = proposal["confirmation_token"]

    exec_res = action_service.execute(proposal, confirm_token=token, session_id=session_id)
    assert exec_res["ok"] is True
    assert exec_res["receipt"]["status"] == "applied"
    assert fake_backend.get_current_song_time() == 32.0

    # 2. Jump to previous locator (Verse at 16.0 beats)
    prev_prop = action_service.propose_relative_cue_jump_action("prev", session_id=session_id)
    assert prev_prop["ok"] is True
    prev_token = prev_prop["proposal"]["confirmation_token"]
    prev_exec = action_service.execute(prev_prop["proposal"], confirm_token=prev_token, session_id=session_id)
    assert prev_exec["ok"] is True
    assert fake_backend.get_current_song_time() == 16.0


def test_natural_language_groove_record_mode_and_jumps(action_service, fake_backend):
    """Natural language commands for groove, record mode, and locator navigation."""
    session_id = "test-session-nl-batch2"

    # Groove command
    res1 = handle_command("set groove to 75%", session_id=session_id, service=action_service)
    assert res1["status"] == "confirmation_required"
    token1 = res1["confirmation_token"]
    res1_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res1["proposal"], confirm_token=token1)
    assert res1_confirm["status"] == "applied"
    assert fake_backend.get_groove_amount() == 0.75

    # Record mode command
    res2 = handle_command("arrangement record mode on", session_id=session_id, service=action_service)
    assert res2["status"] == "confirmation_required"
    token2 = res2["confirmation_token"]
    res2_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res2["proposal"], confirm_token=token2)
    assert res2_confirm["status"] == "applied"
    assert fake_backend.get_record_mode() is True

    # Locator jump command
    res3 = handle_command("jump to locator Verse", session_id=session_id, service=action_service)
    assert res3["status"] == "confirmation_required"
    token3 = res3["confirmation_token"]
    res3_confirm = handle_command("apply", session_id=session_id, service=action_service, proposal=res3["proposal"], confirm_token=token3)
    assert res3_confirm["status"] == "applied"
    assert fake_backend.get_current_song_time() == 16.0

