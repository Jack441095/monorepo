"""Recall@4 with "Use it when" lines added to each note's first chunk, measured in memory (the index on disk is untouched).

    measure_use_it_when_lines.py none v1 lines.json [--output report.json]

A line set is "none", "v1" (the drafted lines in the review doc) or a JSON file of {note filename: line}. Question sets:
the original fixture, the 125 describe-it questions, and the 228 Qwen-written ones (device_purpose_sealed_qwen8b.json).
"""
import copy, dataclasses, json, re, sys, time
from pathlib import Path
sys.path.insert(0, "tooling/scripts"); sys.path.insert(0, "packages/chat"); sys.path.insert(0, "apps/backend/src")
import numpy as np
from kenn.core.chat_retrieval import load_chunks, load_terms
from kenn.retrieval import retrieval
from kenn.retrieval.build_index import Chunk, build_terms
from evaluate_retrieval_modes import _rank
from eval_chat_coverage import _expects_public_abstention

EVALS = Path("apps/backend/src/kenn/evals")
retrieval.load_source_feedback_scores = lambda: {}
base_chunks, base_terms = load_chunks(), load_terms()
base_emb = retrieval.load_embedding_index()


def question_sets():
    sets = {}
    for name, path in (("original", EVALS / "questions.json"), ("describe_it", EVALS / "device_purpose_retrieval_cases.json")):
        cases = [c for c in json.loads(path.read_text())["cases"] if c.get("source_must_include") and not _expects_public_abstention(c)]
        sets[name] = cases
    sets["sealed_qwen"] = json.loads((EVALS / "device_purpose_sealed_qwen8b.json").read_text())["cases"]
    return sets


def lineset(name):
    if name == "none":
        return {}
    if name == "v1":
        review = Path("docs/reviews/KENN_USE_IT_WHEN_REVIEW_2026-09-25.md").read_text()
        return {f: line.strip() for f, line in re.findall(r"\(`([^`]+\.md)`\)\n\s+Use it when: (.+)", review)}
    return {f: "Use it when: " + line for f, line in json.loads(Path(name).read_text()).items()}


def build(lines):
    chunks = copy.deepcopy(base_chunks)
    emb = base_emb.copy()
    changed = []
    for filename, line in lines.items():
        index = next((i for i, c in enumerate(chunks) if c.get("source") == filename), None)
        if index is None:
            continue
        text = line if line.lower().startswith("use it when") else "Use it when: " + line
        chunks[index]["text"] = chunks[index]["text"].rstrip() + "\n\n" + text
        changed.append(index)
    fields = {f.name for f in dataclasses.fields(Chunk)}
    terms = build_terms([Chunk(**{k: v for k, v in c.items() if k in fields}) for c in chunks])
    inverted = {}
    for doc, counts in enumerate(terms["term_counts"]):
        for term, freq in counts.items():
            inverted.setdefault(term, []).append((doc, freq))
    terms["inverted_index"] = inverted
    if changed:
        emb[changed] = retrieval.embed_chunks([chunks[i] for i in changed])
    return chunks, terms, emb


def score(chunks, terms, emb, cases):
    ranks = []
    for case in cases:
        results = retrieval.hybrid_search(case["question"], chunks, terms, limit=16, embedding_index=emb)
        if case.get("source_any_include"):
            found = [_rank([t], results) for t in case["source_any_include"]]
            rank = min((r for r in found if r is not None), default=None)
        else:
            rank = _rank(list(case["source_must_include"]), results)
        ranks.append(rank)
    n = len(ranks)
    return {"n": n, "recall@4": round(sum(1 for r in ranks if r and r <= 4) / n, 3),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3), "ranks": ranks}


args = sys.argv[1:]
output = Path(args.pop(args.index("--output") + 1)) if "--output" in args else None
args = [a for a in args if a != "--output"]
sets = question_sets()
report = {}
for name in args:
    started = time.time()
    chunks, terms, emb = build(lineset(name))
    report[name] = {s: score(chunks, terms, emb, cases) for s, cases in sets.items()}
    print(name, {s: (r["recall@4"], r["mrr"], r["n"]) for s, r in report[name].items()}, f"{time.time() - started:.0f}s", flush=True)
if output:
    output.write_text(json.dumps(report))
