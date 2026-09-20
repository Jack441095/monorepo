"""The optional AudioGen provider has an explicit, quiet beta boundary."""

from __future__ import annotations

import builtins

from kenn.core.chat_routing import audio_generation_payload


def test_normal_knowledge_query_does_not_import_optional_audiogen(monkeypatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "audiogen_bridge":
            raise AssertionError("ordinary knowledge query tried to import AudioGen")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert audio_generation_payload("What is Ableton Link?") is None


def test_generation_request_reports_unavailable_provider_explicitly(monkeypatch) -> None:
    original_import = builtins.__import__

    def missing_provider(name, *args, **kwargs):
        if name == "audiogen_bridge":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    import sys
    monkeypatch.delitem(sys.modules, "audiogen_bridge", raising=False)
    monkeypatch.setattr(builtins, "__import__", missing_provider)

    result = audio_generation_payload("Generate a dark music loop")

    assert result is not None
    assert result["found"] is False
    assert result["route"] == "audiogen_unavailable"
    assert "not generated or changed any audio" in result["answer"]
