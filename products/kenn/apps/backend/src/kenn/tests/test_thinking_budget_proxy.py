import scripts.thinking_budget_proxy as proxy


def test_suffix_selects_no_think_or_budget_and_leaves_plain_models_alone() -> None:
    nothink = proxy.SUFFIX.match("deepseek-r1:7b@nothink")
    assert nothink and nothink.group("model") == "deepseek-r1:7b" and nothink.group("nothink")
    budget = proxy.SUFFIX.match("qwen3.5:4b@think128")
    assert budget and budget.group("model") == "qwen3.5:4b" and budget.group("budget") == "128"
    assert proxy.SUFFIX.match("qwen2.5:7b-instruct") is None


def test_r1_template_puts_system_after_bos_and_opens_think_block() -> None:
    prompt = proxy.render([{"role": "system", "content": "SYS"}, {"role": "user", "content": "Mute drums."}],
                          proxy.family("deepseek-r1:1.5b"))
    assert prompt == "<｜begin▁of▁sentence｜>SYS<｜User｜>Mute drums.<｜Assistant｜><think>\n"


def test_qwen_template_uses_chatml_and_opens_think_block() -> None:
    prompt = proxy.render([{"role": "system", "content": "SYS"}, {"role": "user", "content": "Mute drums."}],
                          proxy.family("qwen3.5:2b"))
    assert prompt == ("<|im_start|>system\nSYS<|im_end|>\n<|im_start|>user\nMute drums.<|im_end|>\n"
                      "<|im_start|>assistant\n<think>\n")
