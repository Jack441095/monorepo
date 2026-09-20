from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "apps" / "backend" / "src"))

from kenn.core import tool_registry_defaults  # noqa: E402
from kenn.core import local_mix_review_service  # noqa: E402
from kenn.core.tool_registry import get_tool, register  # noqa: E402
from kenn.core.tool_trigger import detect_tool_trigger  # noqa: E402


def test_explicit_stem_masking_phrases_trigger_analysis() -> None:
    assert detect_tool_trigger("run a stem masking analysis on these") == "run_stem_masking"
    assert detect_tool_trigger("please review masking between these stems") == "run_stem_masking"
    assert detect_tool_trigger("scan my stems for masking") == "run_stem_masking"


def test_question_shaped_stem_masking_request_stays_advice_only() -> None:
    assert detect_tool_trigger("how do I check these stems for masking?") is None
    assert detect_tool_trigger("can you review masking between these stems?") is None


def test_stem_masking_tool_is_analysis_only() -> None:
    tool_registry_defaults.register_defaults()
    tool = get_tool("run_stem_masking")
    assert tool is not None
    assert tool.risk.value == "analysis"
    assert tool.risk.requires_confirmation is False


def test_stem_masking_tool_maps_wav_attachments_to_bounded_labels(monkeypatch) -> None:
    captured: list[tuple[str, bytes]] = []

    def fake_analyze(stems):
        captured.extend(stems)
        return {"ok": True, "stems": [label for label, _payload in stems], "findings": []}

    monkeypatch.setattr(local_mix_review_service, "analyze_stem_masking", fake_analyze)
    tool_registry_defaults.register_defaults()
    result = get_tool("run_stem_masking").handler(
        files=[(b"first", "01_Kick.wav"), (b"second", "08_Bass.wav"), (b"ignored", "notes.txt")],
    )

    assert result == {"ok": True, "stems": ["01_Kick", "08_Bass"], "findings": []}
    assert captured == [("01_Kick", b"first"), ("08_Bass", b"second")]
