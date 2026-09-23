from kenn.llm import llm_rewrite

CFG = {"model": "qwen2.5:1.5b"}
MESSAGES = [{"role": "system", "content": "planner"}, {"role": "user", "content": "Mute the drums."}]


def test_plain_calls_keep_their_existing_key() -> None:
    assert llm_rewrite._cache_key(CFG, MESSAGES) == llm_rewrite._cache_key(CFG, MESSAGES, None)


def test_output_contract_separates_cached_answers() -> None:
    plain = llm_rewrite._cache_key(CFG, MESSAGES)
    json_mode = llm_rewrite._cache_key(CFG, MESSAGES, {"json_mode": True, "json_schema": None, "answer_mode": "command"})
    schema_a = llm_rewrite._cache_key(CFG, MESSAGES, {"json_mode": True, "json_schema": {"type": "object"},
                                                      "answer_mode": "command"})
    schema_b = llm_rewrite._cache_key(CFG, MESSAGES, {"json_mode": True, "json_schema": {"type": "array"},
                                                      "answer_mode": "command"})
    assert len({plain, json_mode, schema_a, schema_b}) == 4
