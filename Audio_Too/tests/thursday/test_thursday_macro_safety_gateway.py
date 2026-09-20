"""Phase-0 P0-B regression: macro execution must not bypass the confirmation
gateway.

docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md (P0-6) and
docs/audits/2026-08-20-thursday-platform-master-report.md found that
`thursday/macros/__init__.py` called `service_def.action()` directly, gated
only by a keyword heuristic over the service id string (`_service_may_mutate`)
-- never through `request_risk()`/the HMAC confirmation-token system -- and
that macro "confirmation" was a bare
`text.lower().startswith("confirm <macro name>")` string match: no signature,
no session binding, no expiry, trivially satisfied by anyone who could type
that phrase. Any LOCAL_MUTATION/EXTERNAL_COMMUNICATION/DESTRUCTIVE macro step
could run with zero real authorization.

These tests exercise the real end-to-end dispatch path
(`thursday.orchestrator.handle()`), the same entry point a real chat turn
uses, with a synthetic macro whose steps map to real registry service ids
(codebase_edit / drafts / codebase_git) so `request_risk()` classifies them
deterministically regardless of trigger wording.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from thursday import session_manager
from thursday.macros import Macro
from thursday.orchestrator import handle
from thursday.registry.core import ServiceDef


def _service(service_id: str, name: str, action) -> ServiceDef:
    return ServiceDef(name=name, description=f"{name} test service", action=action)


def _macro(trigger_phrase: str, macro_name: str, service_id: str) -> Macro:
    return Macro(
        macro_name,
        {
            "description": "test",
            "triggers": {"phrase": trigger_phrase},
            "requires": [],
            "steps": [
                {"say": "Starting."},
                {"service": service_id},
                {"say": "Done."},
            ],
        },
    )


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setattr(session_manager, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_manager, "SESSION_FILE", tmp_path / ".session")
    monkeypatch.setenv("THURSDAY_CONFIRMATION_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("THURSDAY_ACTION_RECEIPTS_DB", str(tmp_path / "receipts.sqlite3"))
    return tmp_path


def _patch_registry_and_macro(monkeypatch, service_id, service_name, action, macro):
    services = {service_id: _service(service_id, service_name, action)}
    monkeypatch.setattr("thursday.registry.build_services", lambda api: services)
    monkeypatch.setattr("thursday.macros.__init__.load_macros", lambda: [macro])


def test_local_mutation_macro_step_cannot_execute_without_confirmation(isolated_env, monkeypatch):
    action = MagicMock(return_value="edited the file")
    macro = _macro("run gated edit macro", "Gated Edit Macro", "codebase_edit")
    _patch_registry_and_macro(monkeypatch, "codebase_edit", "Codebase Edit", action, macro)

    session = session_manager.get_or_create_session("macro-mutation")
    response = handle("run gated edit macro", session=session)

    assert action.call_count == 0, "LOCAL_MUTATION macro step ran without confirmation"
    assert "local_mutation" in response
    assert "confirm " in response.lower()


def test_external_communication_macro_step_cannot_execute_without_confirmation(isolated_env, monkeypatch):
    action = MagicMock(return_value="draft sent")
    macro = _macro("run gated send macro", "Gated Send Macro", "drafts")
    _patch_registry_and_macro(monkeypatch, "drafts", "Drafts", action, macro)

    session = session_manager.get_or_create_session("macro-external")
    # "send" (not "pending"/"list"/"show") -> EXTERNAL_COMMUNICATION per request_risk.
    response = handle("run gated send macro", session=session)

    assert action.call_count == 0, "EXTERNAL_COMMUNICATION macro step ran without confirmation"
    assert "external_communication" in response


def test_destructive_macro_step_cannot_execute_without_confirmation(isolated_env, monkeypatch):
    action = MagicMock(return_value="force pushed")
    macro = _macro("run gated push --force macro", "Gated Force Push Macro", "codebase_git")
    _patch_registry_and_macro(monkeypatch, "codebase_git", "Codebase Git", action, macro)

    session = session_manager.get_or_create_session("macro-destructive")
    response = handle("run gated push --force macro", session=session)

    assert action.call_count == 0, "DESTRUCTIVE macro step ran without confirmation"
    assert "destructive" in response


def test_confirmed_macro_executes_exactly_once(isolated_env, monkeypatch):
    action = MagicMock(return_value="edited the file")
    macro = _macro("run gated edit macro", "Gated Edit Macro", "codebase_edit")
    _patch_registry_and_macro(monkeypatch, "codebase_edit", "Codebase Edit", action, macro)

    session = session_manager.get_or_create_session("macro-confirm-once")
    pause = handle("run gated edit macro", session=session)
    assert action.call_count == 0

    token = pause.split("confirm ")[-1].strip()
    completed = handle(f"confirm {token}", session=session)

    assert action.call_count == 1
    assert "edited the file" in completed
    assert "Done." in completed  # the step after the confirmed one still ran


def test_replayed_macro_confirmation_does_not_duplicate_side_effect(isolated_env, monkeypatch):
    action = MagicMock(return_value="edited the file")
    macro = _macro("run gated edit macro", "Gated Edit Macro", "codebase_edit")
    _patch_registry_and_macro(monkeypatch, "codebase_edit", "Codebase Edit", action, macro)

    session = session_manager.get_or_create_session("macro-replay")
    pause = handle("run gated edit macro", session=session)
    token = pause.split("confirm ")[-1].strip()

    first = handle(f"confirm {token}", session=session)
    second = handle(f"confirm {token}", session=session)

    assert action.call_count == 1, "replayed confirmation re-ran the mutating step"
    assert "edited the file" in first
    # The second call finds no live pending confirmation for the (now
    # consumed) token and falls back to the completed action receipt --
    # same replay-safety contract as the non-macro confirmation paths.
    assert second == first


def test_tampered_macro_confirmation_token_is_rejected(isolated_env, monkeypatch):
    """A one-character-flipped token is not a dict-key match for the pending
    confirmation (nor for any completed receipt), so it is rejected exactly
    like an unrecognized/never-issued token -- the same "There is no pending
    action to confirm." wording the non-macro single-step and multi-step
    plan paths already use for this case (see
    tests/thursday/test_thursday_confirmation.py). Crucially, the mutating
    step must not run."""
    action = MagicMock(return_value="edited the file")
    macro = _macro("run gated edit macro", "Gated Edit Macro", "codebase_edit")
    _patch_registry_and_macro(monkeypatch, "codebase_edit", "Codebase Edit", action, macro)

    session = session_manager.get_or_create_session("macro-invalid-token")
    pause = handle("run gated edit macro", session=session)
    token = pause.split("confirm ")[-1].strip()

    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    response = handle(f"confirm {tampered}", session=session)

    assert action.call_count == 0
    assert "no pending action to confirm" in response.lower()

    # The real token must still work afterward -- the tampering attempt must
    # not have disturbed the genuine pending confirmation.
    completed = handle(f"confirm {token}", session=session)
    assert action.call_count == 1
    assert "edited the file" in completed


def test_confirmation_does_not_leak_across_different_macros(isolated_env, monkeypatch):
    """A confirmation token issued for one macro's step must not resume a
    different macro even if both are pending in the same session."""
    action_a = MagicMock(return_value="A ran")
    action_b = MagicMock(return_value="B ran")
    macro_a = _macro("run gated edit macro a", "Gated Edit Macro A", "codebase_edit")
    macro_b = _macro("run gated edit macro b", "Gated Edit Macro B", "codebase_git")

    services = {
        "codebase_edit": _service("codebase_edit", "Codebase Edit", action_a),
        "codebase_git": _service("codebase_git", "Codebase Git", action_b),
    }
    monkeypatch.setattr("thursday.registry.build_services", lambda api: services)
    monkeypatch.setattr("thursday.macros.__init__.load_macros", lambda: [macro_a, macro_b])

    session = session_manager.get_or_create_session("macro-cross-token")
    pause_a = handle("run gated edit macro a", session=session)
    token_a = pause_a.split("confirm ")[-1].strip()

    # Confirming macro A's token must not be usable to run macro B's step.
    monkeypatch.setattr("thursday.macros.__init__.load_macros", lambda: [macro_a, macro_b])
    completed = handle(f"confirm {token_a}", session=session)

    assert action_a.call_count == 1
    assert action_b.call_count == 0
    assert "A ran" in completed


def test_read_only_macro_step_still_runs_without_confirmation(isolated_env, monkeypatch):
    """Baseline: a non-mutating step must not be blocked by the new gate."""
    action = MagicMock(return_value="analysis complete")
    macro = _macro("run gated analysis macro", "Gated Analysis Macro", "audio_analysis")
    _patch_registry_and_macro(monkeypatch, "audio_analysis", "Audio Analysis", action, macro)

    session = session_manager.get_or_create_session("macro-read-only")
    response = handle("run gated analysis macro", session=session)

    assert action.call_count == 1
    assert "analysis complete" in response


def test_macro_and_direct_dispatch_agree_on_confirmation_requirement(isolated_env, monkeypatch):
    """Equivalence: the same (service_id, text) pair must require confirmation
    identically whether reached via a normal single-step request or via a
    macro step -- proving the macro path converges on the same
    `request_risk()` gate, not a separate/weaker one."""
    from thursday.registry import request_risk

    direct_risk = request_risk("codebase_edit", "run gated edit macro")
    macro = _macro("run gated edit macro", "Gated Edit Macro", "codebase_edit")
    action = MagicMock(return_value="edited the file")
    _patch_registry_and_macro(monkeypatch, "codebase_edit", "Codebase Edit", action, macro)

    session = session_manager.get_or_create_session("macro-equivalence")
    response = handle("run gated edit macro", session=session)

    assert direct_risk.requires_confirmation is True
    assert action.call_count == 0
    assert "confirm " in response.lower()
