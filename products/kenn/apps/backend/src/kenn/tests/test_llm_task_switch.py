from kenn.llm import llm_rewrite


def test_command_planner_can_be_enabled_without_chat_llm(monkeypatch) -> None:
    for name in ("KENN_LLM_ENABLED", "AUDIO_TOO_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KENN_LLM_ENABLED_COMMAND", "1")
    assert llm_rewrite.config("command")["enabled"] is True
    assert llm_rewrite.config("rewrite")["enabled"] is False
    assert llm_rewrite.config("route")["enabled"] is False


def test_global_switch_still_applies_when_no_task_switch_is_set(monkeypatch) -> None:
    monkeypatch.delenv("KENN_LLM_ENABLED_COMMAND", raising=False)
    monkeypatch.setenv("KENN_LLM_ENABLED", "1")
    assert llm_rewrite.config("command")["enabled"] is True and llm_rewrite.config("rewrite")["enabled"] is True
    monkeypatch.setenv("KENN_LLM_ENABLED_COMMAND", "0")
    assert llm_rewrite.config("command")["enabled"] is False and llm_rewrite.config("rewrite")["enabled"] is True
