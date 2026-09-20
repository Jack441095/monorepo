from __future__ import annotations

import json
from pathlib import Path
import torch


class FakeTokenizer:
    eos_token_id = 99

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize is False
        assert add_generation_prompt is True
        return "SYSTEM " + messages[1]["content"] + " ASSISTANT"

    def __call__(self, text, *, add_special_tokens=False):
        assert add_special_tokens is False
        return {"input_ids": list(range(1, len(text.split()) + 1))}

    def decode(self, ids):
        return " ".join("tok" for _ in ids)


class VocabTokenizer:
    """Word<->id tokenizer so tests can trace exactly which words survive
    truncation, distinguishing the head of the context from its tail."""
    eos_token_id = 99

    def __init__(self):
        self._vocab: dict[str, int] = {}

    def _id_for(self, word: str) -> int:
        return self._vocab.setdefault(word, len(self._vocab) + 1)

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize is False
        assert add_generation_prompt is True
        return "SYSTEM " + messages[1]["content"] + " ASSISTANT"

    def __call__(self, text, *, add_special_tokens=False):
        assert add_special_tokens is False
        return {"input_ids": [self._id_for(w) for w in text.split()]}

    def decode(self, ids):
        rev = {v: k for k, v in self._vocab.items()}
        return " ".join(rev.get(i, "?") for i in ids)


def test_dataset_masks_prompt_and_preserves_answer(tmp_path: Path) -> None:
    from studio.kenn.kenn.finetune.finetune_lora import QADataset

    path = tmp_path / "training.jsonl"
    path.write_text(
        json.dumps(
            {
                "question": "How should I EQ this?",
                "context": " ".join(["context"] * 100),
                "answer": "cut mud then compare",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    row = QADataset(path, FakeTokenizer(), max_length=12)[0]
    supervised = [label for label in row["labels"] if label != -100]

    assert len(row["input_ids"]) == 12
    assert supervised == [1, 2, 3, 4, FakeTokenizer.eos_token_id]
    assert row["labels"][:7] == [-100] * 7


def test_dataset_truncates_context_head_not_prompt_tail(tmp_path: Path) -> None:
    """Regression test for the LoRA grounding bug (docs/BACKLOG.md): when the
    context is too long to fit, the dataset must truncate the CONTEXT text
    itself (keeping its head — titles/tags lead each note) rather than right-
    truncating the fully rendered prompt. Right-truncation used to discard
    the "Context:" header and nearly the whole context block, leaving 90% of
    the real training corpus trained on question-only -> answer pairs, which
    is why the fine-tuned model ignored retrieved context at inference.
    """
    path = tmp_path / "training.jsonl"
    context = "HEAD " + "filler " * 30 + "TAIL"
    path.write_text(
        json.dumps({"question": "question", "context": context, "answer": "answer"}) + "\n",
        encoding="utf-8",
    )

    from studio.kenn.kenn.finetune.finetune_lora import QADataset

    tokenizer = VocabTokenizer()
    row = QADataset(path, tokenizer, max_length=20)[0]

    head_id = tokenizer._id_for("HEAD")
    tail_id = tokenizer._id_for("TAIL")
    context_label_id = tokenizer._id_for("Context:")

    assert context_label_id in row["input_ids"], "the 'Context:' header must survive truncation"
    assert head_id in row["input_ids"], "the head of the context must survive truncation"
    assert tail_id not in row["input_ids"], "only the tail should be dropped when context overflows"
