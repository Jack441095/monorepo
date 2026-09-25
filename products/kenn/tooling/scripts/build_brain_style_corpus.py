#!/usr/bin/env python3
"""Build a style fine-tune set for KENN's chat brain from its own accepted answers (Stage 1).

There are no human-reviewed "ideal" KENN answers yet, so this doesn't try to teach the model new facts. It teaches
it to write the answers KENN already accepts: grounded in the retrieved notes, with sources, no invented numbers and
no claims of having changed the set. Two steps, both on the GPU box against Ollama:

    questions  the brain writes producer questions for a sample of KENN's notes. Anything close to a question in the
               chat or retrieval evaluation sets is dropped, so the before/after comparison stays honest.
    answers    each question goes through KENN's real answer path (answer_payload) with the brain on, a few times.
               The first answer KENN's own gate accepted becomes a training example, recorded as the exact messages
               the model saw plus what it wrote.

    build_brain_style_corpus.py questions --base-url http://127.0.0.1:11437/v1 --model kenn-brain-qwen3-8b --out q.jsonl
    build_brain_style_corpus.py answers --base-url ... --model ... --questions q.jsonl --out data_brain1/
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(KENN_ROOT / "apps" / "backend" / "src"), str(KENN_ROOT / "tooling"), str(KENN_ROOT / "tooling" / "scripts")]
EVALS = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "evals"


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {"the", "a", "an", "to", "of", "in", "on", "i", "my", "is", "how", "what", "do", "and", "for", "it"}


def evaluation_questions() -> list[set[str]]:
    """Every question KENN is scored on, as word sets (a near-copy leaks as surely as an exact one)."""
    found = []
    for path in EVALS.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cases = data.get("cases", data) if isinstance(data, dict) else data
        for case in cases if isinstance(cases, list) else []:
            if isinstance(case, dict) and case.get("question"):
                found.append(_words(str(case["question"])))
    return found


def too_close(question: str, held_out: list[set[str]]) -> bool:
    words = _words(question)
    return any(words and other and len(words & other) / len(words | other) >= 0.6 for other in held_out)


def _chat(base_url: str, model: str, prompt: str, temperature: float) -> str:
    import urllib.request

    body = {"model": model, "stream": False, "think": False, "options": {"temperature": temperature, "num_predict": 600},
            "messages": [{"role": "user", "content": prompt}]}
    root = base_url.rstrip("/").removesuffix("/v1")
    request = urllib.request.Request(f"{root}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(request, timeout=300).read())["message"]["content"]


def questions(args: argparse.Namespace) -> int:
    from kenn.core.chat_retrieval import load_chunks

    by_source: dict[str, list[dict]] = {}
    for chunk in load_chunks():
        if chunk.get("kind") == "note":
            by_source.setdefault(str(chunk.get("source")), []).append(chunk)
    sources = sorted(by_source)
    random.Random(args.seed).shuffle(sources)
    held_out = evaluation_questions()
    out, kept, dropped = [], 0, 0
    for source in sources[: args.notes]:
        chunks = by_source[source]
        note = "\n".join(str(c.get("text") or "") for c in chunks)[:1500]
        prompt = (f"Here is a note from a music production assistant's knowledge base:\n\n{note}\n\n"
                  f"Write {args.per_note} different questions an Ableton Live producer might ask that this note answers. "
                  "Write them the way producers really ask: short, practical, sometimes informal. One per line, no "
                  "numbering, nothing else.")
        try:
            text = _chat(args.base_url, args.model, prompt, 0.8)
        except Exception as exc:  # one bad note shouldn't stop the batch
            print(f"skip {source}: {exc}", file=sys.stderr)
            continue
        for line in text.splitlines():
            question = re.sub(r"^\s*(?:[-*\d.)]+\s*)", "", line).strip().strip('"')
            if len(question) < 12 or not question.endswith("?") and len(question.split()) < 4:
                continue
            if too_close(question, held_out):
                dropped += 1
                continue
            out.append({"question": question, "note": source})
            kept += 1
    Path(args.out).write_text("".join(json.dumps(row) + "\n" for row in out), encoding="utf-8")
    print(f"{kept} questions from {min(args.notes, len(sources))} notes; {dropped} dropped as too close to an eval question")
    return 0


def answers(args: argparse.Namespace) -> int:
    os.environ.update({"KENN_USE_MLX": "0", "KENN_LLM_CACHE": "0", "AUDIO_TOO_LLM_TIMEOUT": "120", "KENN_LLM_ENABLED": "1",
                       "KENN_LLM_PROVIDER": "ollama", "KENN_LLM_BASE_URL": args.base_url, "KENN_LLM_MODEL": args.model,
                       "KENN_LLM_THINK": "off"})
    from kenn.core import session_memory
    from kenn.core.chat_answer import answer_payload
    from kenn.core.chat_grounding import claims_live_change
    from kenn.llm import llm_rewrite

    # Each question is a fresh conversation: the semantic answer cache would hand back an earlier answer.
    session_memory.get_semantic_cache_hit = lambda *_a, **_k: None
    session_memory.save_to_semantic_cache = lambda *_a, **_k: None

    from kenn.core import chat_answer

    # Record the messages the model saw and what enhance() returned: the model's text after KENN's lint and with
    # its Sources block, which is what the user would read and what we want the model to write itself.
    seen: list[tuple[list[dict], str]] = []
    prompts: list[list[dict]] = []
    original_completion, original_enhance = llm_rewrite._chat_completion, chat_answer.llm_enhance_answer

    def recording_completion(messages, task, **kwargs):
        if task == "rewrite":
            prompts.append([dict(m) for m in messages])
        return original_completion(messages, task, **kwargs)

    def recording_enhance(*a, **k):
        text = original_enhance(*a, **k)
        if text and prompts:
            seen.append((prompts[-1], text))
        return text

    llm_rewrite._chat_completion = recording_completion
    chat_answer.llm_enhance_answer = recording_enhance
    rows = [json.loads(line) for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()]
    examples, tried = [], 0
    for number, row in enumerate(rows):
        for attempt in range(args.samples):
            seen.clear()
            prompts.clear()
            tried += 1
            try:
                payload = answer_payload(row["question"])
            except Exception as exc:
                print(f"skip {row['question'][:60]!r}: {exc}", file=sys.stderr)
                break
            answer = str(payload.get("answer") or "")
            # Accepted means KENN showed the model's answer, not the template; the gate already checked grounding.
            if not payload.get("llm_enhanced") or not seen or "sources:" not in answer.lower() or claims_live_change(answer):
                continue
            messages, final = seen[-1]
            examples.append({"messages": [*messages, {"role": "assistant", "content": final.strip()}],
                             "question": row["question"], "note": row.get("note")})
            break
        if number % 25 == 0:
            print(f"{number}/{len(rows)} questions, {len(examples)} examples kept, {tried} tries", flush=True)
    random.Random(args.seed).shuffle(examples)
    cut = max(1, len(examples) // 10)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "valid.jsonl").write_text("".join(json.dumps({"messages": e["messages"]}) + "\n" for e in examples[:cut]), encoding="utf-8")
    (out / "train.jsonl").write_text("".join(json.dumps({"messages": e["messages"]}) + "\n" for e in examples[cut:]), encoding="utf-8")
    (out / "examples.jsonl").write_text("".join(json.dumps(e) + "\n" for e in examples), encoding="utf-8")
    print(f"DONE {len(examples)} examples from {len(rows)} questions ({tried} tries): {len(examples) - cut} train, {cut} valid")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="step", required=True)
    for name in ("questions", "answers"):
        step = sub.add_parser(name)
        step.add_argument("--base-url", required=True)
        step.add_argument("--model", required=True)
        step.add_argument("--out", required=True)
        step.add_argument("--seed", type=int, default=0)
    sub.choices["questions"].add_argument("--notes", type=int, default=300)
    sub.choices["questions"].add_argument("--per-note", type=int, default=2)
    sub.choices["answers"].add_argument("--questions", required=True)
    sub.choices["answers"].add_argument("--samples", type=int, default=2)
    args = parser.parse_args()
    return questions(args) if args.step == "questions" else answers(args)


if __name__ == "__main__":
    raise SystemExit(main())
