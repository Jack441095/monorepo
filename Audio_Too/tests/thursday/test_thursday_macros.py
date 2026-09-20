"""Tests for thursday/macros — previously zero test coverage.

docs/CODEBASE_AUDIT_2026-07-06.md verified the macro engine was silently
broken: each step's `service:` YAML field is a registry service id (e.g.
"week_ahead"), but it was being passed straight into the orchestrator's NLU
`handle_func`, which scores it against trigger *phrases* like "week ahead" —
a raw underscored key never matches, so most macro steps silently misrouted
or fell through to "not sure I caught that."
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "business" / "agents"))

from thursday import client as api  # noqa: E402
from thursday.macros import MACROS_DIR, load_macros, execute_macro  # noqa: E402
from thursday.registry import build_services  # noqa: E402


def test_every_shipped_macro_service_step_is_a_real_registry_id() -> None:
    """Guard against the exact bug found: a macro step naming a service id
    that doesn't exist in the registry would silently misroute forever."""
    services = build_services(api)
    macros = load_macros()
    assert macros, f"expected at least one macro in {MACROS_DIR}"

    for macro in macros:
        for step in macro.steps:
            if step.is_service() and "{{" not in step.service:
                assert step.service in services, (
                    f"macro {macro.name!r} step service {step.service!r} is not "
                    "a registered Thursday service id"
                )


def test_execute_macro_invokes_registry_service_directly_not_via_nlu(monkeypatch) -> None:
    """Regression test for the verified bug: a macro step naming a real
    service id must call that service's action directly, never fall back to
    the free-text NLU handle_func (which can't route an underscored key)."""
    called_handle_func_with: list[str] = []

    def fake_handle_func(text: str, _session: dict) -> str:
        called_handle_func_with.append(text)
        return "should not be reached"

    monkeypatch.setattr(api, "week_ahead", lambda: "Nothing due this week.")

    macro = next(m for m in load_macros() if m.name == "Weekly Summary")
    results = execute_macro(macro, fake_handle_func, {"context": {}}, {}, trigger_text="weekly summary")

    assert not called_handle_func_with, (
        "a real registered service id must not be routed through the NLU "
        f"handle_func fallback, but it was called with: {called_handle_func_with}"
    )
    assert any("Nothing due this week." in str(r) for r in results)
    assert results[-1] == "That's your week. Enjoy the weekend!"


def test_execute_macro_falls_back_to_handle_func_for_unknown_service_id() -> None:
    """A hypothetical free-text macro step (not a registered service id)
    should keep working via the old NLU-routed path."""
    from thursday.macros import Macro

    macro = Macro(
        "Unregistered Step Test",
        {
            "description": "test",
            "triggers": {"phrase": "unregistered step test"},
            "steps": [{"service": "definitely not a real service id"}],
        },
    )

    def fake_handle_func(text: str, _session: dict) -> str:
        return f"handled: {text}"

    results = execute_macro(macro, fake_handle_func, {"context": {}}, {}, trigger_text="unregistered step test")
    assert results == ["handled: definitely not a real service id"]
