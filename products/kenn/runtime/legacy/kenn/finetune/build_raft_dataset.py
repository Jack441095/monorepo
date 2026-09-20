#!/usr/bin/env python3
"""Phase 10.1 — Build a RAFT (Retrieval-Augmented Fine-Tuning) dataset.

Generates training examples where each prompt contains:
  - 1 correct source chunk (the "oracle" chunk that answers the question)
  - 2 distractor chunks (randomly sampled, topic-adjacent but wrong)

The training answer includes a chain-of-thought preamble that explicitly shows
the model identifying and ignoring distractors before answering from the correct
chunk. This teaches the local SML to discriminate relevant from irrelevant
context, drastically reducing hallucination from off-topic retrieval results.

Usage:
    python KENN/finetune/build_raft_dataset.py
    python KENN/finetune/build_raft_dataset.py --output KENN/artifacts/training/kenn_raft.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

KENN_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = KENN_DIR.parent
DEFAULT_INPUT = KENN_DIR / "artifacts" / "training" / "kenn_session_training.jsonl"
DEFAULT_OUTPUT = KENN_DIR / "artifacts" / "training" / "kenn_raft.jsonl"

# How many distractor chunks to include alongside the oracle chunk
NUM_DISTRACTORS = 2

# Minimum context length (characters) to be considered a valid chunk
MIN_CHUNK_LENGTH = 30

# Chain-of-thought template for the training answer
COT_TEMPLATE = (
    "Let me identify the relevant source material.\n\n"
    "Source 1: {source1_summary}\n"
    "Source 2: {source2_summary}\n"
    "Source 3: {source3_summary}\n\n"
    "The question asks about {question_topic}. "
    "Source {oracle_idx} directly addresses this topic. "
    "Sources {distractor_idxs} discuss {distractor_topics} which are "
    "not directly relevant to the question.\n\n"
    "Based on Source {oracle_idx}:\n\n"
    "{answer}"
)

# Fallback template for when chain-of-thought components can't be fully built
SIMPLE_COT_TEMPLATE = (
    "Looking at the provided sources, Source {oracle_idx} is the most relevant "
    "to this question. The other sources cover different topics.\n\n"
    "Based on the relevant source:\n\n"
    "{answer}"
)


def load_training_records(path: Path) -> list[dict]:
    """Load the existing training JSONL and extract records with context."""
    records = []
    if not path.exists():
        print(f"Warning: {path} not found. Run export_training_data.py first.")
        return records

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            q = record.get("question", "").strip()
            c = record.get("context", "").strip()
            a = record.get("answer", "").strip()

            if q and c and a and len(c) >= MIN_CHUNK_LENGTH:
                records.append(record)

    return records


def _extract_chunk_pool(records: list[dict]) -> list[str]:
    """Extract a pool of unique context chunks from all records."""
    chunks = set()
    for r in records:
        context = r.get("context", "")
        # Split multi-chunk contexts into individual chunks
        parts = context.split("\n\n")
        for part in parts:
            part = part.strip()
            if len(part) >= MIN_CHUNK_LENGTH:
                chunks.add(part)
    return list(chunks)


def _summarize_chunk(chunk: str, max_len: int = 60) -> str:
    """Create a short summary of a chunk for the CoT preamble."""
    # Take the first sentence or first N characters
    first_line = chunk.split("\n")[0].strip()
    if len(first_line) > max_len:
        return first_line[:max_len - 3] + "..."
    return first_line


def _extract_topic(question: str) -> str:
    """Extract a rough topic phrase from the question."""
    # Simple heuristic: strip common prefixes
    q = question.strip().rstrip("?").strip()
    for prefix in ["what is", "how do", "how to", "why does", "can you explain",
                    "explain", "what are", "how does", "tell me about", "describe"]:
        if q.lower().startswith(prefix):
            q = q[len(prefix):].strip()
            break
    return q[:80] if q else question[:80]


def build_raft_examples(records: list[dict], chunk_pool: list[str], seed: int = 42) -> list[dict]:
    """Build RAFT training examples with oracle + distractor chunks.

    For each training record:
      1. The oracle chunk is the record's original context
      2. Two distractors are randomly sampled from the chunk pool
      3. The chunks are shuffled into a random order
      4. A chain-of-thought answer is generated that identifies the oracle
    """
    rng = random.Random(seed)
    examples = []

    for record in records:
        question = record["question"]
        oracle_context = record["context"].strip()
        answer = record["answer"]

        # Sample distractors that are different from the oracle
        available_distractors = [
            c for c in chunk_pool
            if c != oracle_context and c not in oracle_context
        ]

        if len(available_distractors) < NUM_DISTRACTORS:
            # Not enough unique distractors — skip this example
            continue

        distractors = rng.sample(available_distractors, NUM_DISTRACTORS)

        # Build the 3 chunks and shuffle them
        chunks = [oracle_context] + distractors
        chunk_labels = ["oracle"] + ["distractor"] * NUM_DISTRACTORS

        # Shuffle with consistent label tracking
        combined = list(zip(chunks, chunk_labels))
        rng.shuffle(combined)
        chunks, labels = zip(*combined)

        # Find the oracle's position (1-indexed for human readability)
        oracle_idx = labels.index("oracle") + 1
        distractor_idxs = [str(i + 1) for i in range(3) if labels[i] == "distractor"]

        # Build the context block
        context_block = ""
        for i, chunk in enumerate(chunks):
            context_block += f"[Source {i + 1}]\n{chunk}\n\n"

        # Build chain-of-thought answer
        summaries = [_summarize_chunk(c) for c in chunks]
        question_topic = _extract_topic(question)
        distractor_topics_list = [
            _extract_topic(summaries[int(idx) - 1])
            for idx in distractor_idxs
        ]
        distractor_topics = " and ".join(distractor_topics_list) if distractor_topics_list else "other topics"

        try:
            cot_answer = COT_TEMPLATE.format(
                source1_summary=summaries[0],
                source2_summary=summaries[1],
                source3_summary=summaries[2],
                question_topic=question_topic,
                oracle_idx=oracle_idx,
                distractor_idxs=" and ".join(distractor_idxs),
                distractor_topics=distractor_topics,
                answer=answer,
            )
        except (IndexError, KeyError):
            cot_answer = SIMPLE_COT_TEMPLATE.format(
                oracle_idx=oracle_idx,
                answer=answer,
            )

        # Build the full training example
        example = {
            "question": question,
            "context": context_block.strip(),
            "answer": cot_answer,
            "oracle_position": oracle_idx,
            "route": record.get("route", ""),
            "confidence": record.get("confidence", "medium"),
            "is_raft": True,
        }
        examples.append(example)

    return examples


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build RAFT dataset with distractor chunks for SML training."
    )
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT,
        help="Path to the source training JSONL (from export_training_data.py)."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Path to write the RAFT training JSONL."
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility."
    )
    args = parser.parse_args()

    print(f"Loading base training records from {args.input}...")
    records = load_training_records(args.input)
    print(f"Loaded {len(records)} valid training records.")

    if not records:
        print("No records to process. Run export_training_data.py first.")
        return 1

    chunk_pool = _extract_chunk_pool(records)
    print(f"Extracted {len(chunk_pool)} unique context chunks for distractor sampling.")

    examples = build_raft_examples(records, chunk_pool, seed=args.seed)
    print(f"Generated {len(examples)} RAFT training examples.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Successfully wrote RAFT dataset to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
