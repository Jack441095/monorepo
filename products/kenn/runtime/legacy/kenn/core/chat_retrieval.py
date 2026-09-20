from __future__ import annotations

import json
import re
import textwrap
from functools import lru_cache
from pathlib import Path


from kenn.retrieval.retrieval import (
    chunk_topics,
    extract_tags,
    query_topics,
    source_trust_score,
    tokenize,
    warm_metadata_cache,
)
from kenn.retrieval.index_store import active_version_dir

from kenn.core.chat_constants import (
    CHUNKS_PATH,
    INTENT_GUARD_TERMS,
    MIN_RELEVANT_SCORE,
    OUT_OF_SCOPE_TERMS,
    ROUTE_MEMORY_PATH,
    TERMS_PATH,
    TERM_ALIASES,
)

_multipliers_cache: dict | None = None
_multipliers_mtime: float = 0.0


@lru_cache(maxsize=1)
def _load_index_bundle() -> tuple[list[dict], dict]:
    version_dir = active_version_dir(CHUNKS_PATH.parent)
    chunks_path = (version_dir / "chunks.jsonl") if version_dir else CHUNKS_PATH
    terms_path = (version_dir / "terms.json") if version_dir else TERMS_PATH
    if not chunks_path.exists() or not terms_path.exists():
        raise SystemExit("Index not found. Run: python main.py build")
    with chunks_path.open("r", encoding="utf-8") as handle:
        chunks = [json.loads(line) for line in handle if line.strip()]
    terms = json.loads(terms_path.read_text(encoding="utf-8"))
    inverted = {}
    term_counts = terms.get("term_counts", [])
    for doc_idx, counts in enumerate(term_counts):
        for term, freq in counts.items():
            if freq > 0:
                inverted.setdefault(term, []).append((doc_idx, freq))
    terms["inverted_index"] = inverted
    return chunks, terms


def load_chunks() -> list[dict]:
    return _load_index_bundle()[0]


def load_terms() -> dict:
    return _load_index_bundle()[1]


load_chunks.cache_clear = _load_index_bundle.cache_clear  # type: ignore[attr-defined]
load_terms.cache_clear = _load_index_bundle.cache_clear  # type: ignore[attr-defined]
load_chunks.cache_info = _load_index_bundle.cache_info  # type: ignore[attr-defined]
load_terms.cache_info = _load_index_bundle.cache_info  # type: ignore[attr-defined]


def search(query: str, chunks: list[dict], terms: dict, limit: int = 8, *, history: list | None = None) -> list[tuple[float, dict]]:
    from kenn.retrieval import retrieval as retrieval_api

    emb_idx = retrieval_api.load_embedding_index()
    if emb_idx is not None:
        results = retrieval_api.hybrid_search(
            query, chunks, terms, limit=limit, embedding_index=emb_idx
        )
        if history and results:
            results = _multi_turn_boost(query, results, history)
    else:
        results = retrieval_api.bm25_search(query, chunks, terms, limit=limit)

    # Apply calibrated multipliers
    global _multipliers_cache, _multipliers_mtime
    multipliers_file = Path(__file__).resolve().parent.parent / "artifacts" / "calibrated_confidence_multipliers.json"
    if multipliers_file.exists() and results:
        try:
            mtime = multipliers_file.stat().st_mtime
            if _multipliers_cache is None or mtime > _multipliers_mtime:
                with multipliers_file.open("r", encoding="utf-8") as f:
                    _multipliers_cache = json.load(f)
                _multipliers_mtime = mtime
            multipliers = _multipliers_cache

            from kenn.core.chat_routing import route_query  # local import: chat_routing depends on this module
            route = route_query(query, history)
            route_mult = multipliers.get("routes", {}).get(route, 1.0)
            
            calibrated_results = []
            for score, chunk in results:
                chunk_topics = chunk.get("topics") or []
                topic_mults = [multipliers.get("topics", {}).get(t, 1.0) for t in chunk_topics]
                topic_mult = sum(topic_mults) / len(topic_mults) if topic_mults else 1.0
                calibrated_results.append((score * route_mult * topic_mult, chunk))
            
            results = sorted(calibrated_results, key=lambda x: x[0], reverse=True)
        except Exception:
            pass

    # Apply feedback-driven boosts from user thumbs-up/down ratings
    try:
        from kenn.core.feedback_signals import apply_feedback_boost
        results = apply_feedback_boost(results)
    except Exception:
        pass

    return results


def _multi_turn_boost(
    query: str,
    results: list[tuple[float, dict]],
    history: list | None,
    *,
    boost_factor: float = 1.15,
) -> list[tuple[float, dict]]:
    """Boost results that match the semantic context of prior conversation turns.

    When a follow-up query (e.g. 'and what about the kick?') is vague, this
    gives a small score multiplier to chunks whose topics overlap with topics
    mentioned in prior turns.
    """
    if not history:
        return results
    from kenn.retrieval.retrieval import query_topics
    # Collect topics from prior user turns
    prior_topics: set[str] = set()
    for turn in history:
        if isinstance(turn, dict) and turn.get("role") == "user":
            content = str(turn.get("content", ""))
            prior_topics.update(query_topics(content))
    if not prior_topics:
        return results

    boosted: list[tuple[float, dict]] = []
    for score, chunk in results:
        chunk_topics_set = set(chunk.get("topics") or [])
        overlap = prior_topics & chunk_topics_set
        if overlap:
            score *= boost_factor
        boosted.append((score, chunk))
    boosted.sort(reverse=True)
    return boosted


def warm_index() -> None:
    chunks = load_chunks()
    load_terms()
    warm_metadata_cache(chunks)
    try:
        from kenn.retrieval.retrieval import load_embedding_index, _get_embedding_model
        emb_idx = load_embedding_index()
        if emb_idx is not None:
            print(f"  Embedding index loaded ({emb_idx.shape[1]} dim, {emb_idx.shape[0]} chunks)")
        # Warm the embedding model so the first query doesn't pay the load penalty
        _get_embedding_model()
    except Exception as exc:
        print(f"  WARNING: embedding index/model warm-up failed ({exc!r}) -- "
              f"retrieval will silently fall back to BM25-only for this process's lifetime")


def route_memory_cache_key() -> tuple[str, int, int]:
    try:
        stat = ROUTE_MEMORY_PATH.stat()
    except OSError:
        return (str(ROUTE_MEMORY_PATH), 0, 0)
    return (str(ROUTE_MEMORY_PATH), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=8)
def _load_route_memory_cached(path: str, _mtime_ns: int, _size: int) -> tuple[dict, ...]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    records: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return tuple(records)


def load_route_memory() -> tuple[dict, ...]:
    return _load_route_memory_cached(*route_memory_cache_key())


def route_memory_match(query: str) -> dict | None:
    records = load_route_memory()
    if not records:
        return None
    query_terms = set(tokenize(query))
    normalized = " ".join(tokenize(query))
    for record in records:
        memory_question = str(record.get("question") or "")
        memory_terms = set(tokenize(memory_question))
        if not memory_terms:
            continue
        if normalized and normalized == " ".join(tokenize(memory_question)):
            return record
        overlap = len(query_terms & memory_terms) / max(1, len(query_terms | memory_terms))
        if overlap >= 0.72:
            return record
    return None


def chunk_is_catalog_boilerplate(chunk: dict) -> bool:
    if chunk.get("kind") == "note":
        return False
    preview = str(chunk.get("text", ""))[:400]
    return "Category:" in preview and "Title:" in preview and "Topics:" in preview


def prefer_note_over_manual(
    note_item: tuple[float, dict],
    manual_item: tuple[float, dict],
    topics: list[str],
) -> bool:
    note_score, note_chunk = note_item
    manual_score, _manual_chunk = manual_item
    if note_chunk.get("kind") != "note":
        return False
    if topics and not (chunk_topics(note_chunk) & set(topics)) and note_score < MIN_RELEVANT_SCORE:
        return False
    if manual_score > note_score * 1.85:
        return False
    if note_score >= manual_score * 0.7:
        return True
    return note_score >= MIN_RELEVANT_SCORE and manual_score < MIN_RELEVANT_SCORE + 3


def results_are_weak(query: str, results: list[tuple[float, dict]]) -> bool:
    if not results:
        return True
    query_terms = set(tokenize(query))
    if query_terms & OUT_OF_SCOPE_TERMS:
        return True
    top_score, top_chunk = results[0]
    if top_score < MIN_RELEVANT_SCORE:
        return True
    topics = query_topics(query)
    if not topics:
        displayed = display_results(query, results, 1)
        if not displayed:
            return True
        _score, primary = displayed[0]
        if primary.get("kind") == "note":
            return note_query_affinity(query, primary) == 0
        return False
    if chunk_topics(top_chunk) & set(topics):
        return False
    for _, chunk in results[:8]:
        if chunk.get("kind") == "note" and chunk_topics(chunk) & set(topics):
            return False
    return True


def query_is_out_of_scope(query: str) -> bool:
    lowered = query.lower()
    if "relationship advice" in lowered or "relationship help" in lowered or "relationship tip" in lowered:
        return True
    return bool(set(tokenize(query)) & OUT_OF_SCOPE_TERMS)


def source_label(chunk: dict) -> str:
    if chunk.get("kind") == "note":
        return f"{chunk.get('title') or chunk.get('source')} ({chunk.get('source')})"
    return f"{chunk['source']}, page {chunk['page']}"


def normalized_terms(text: str) -> set[str]:
    terms = set(tokenize(text))
    out = set(terms)
    for term in terms:
        if term in TERM_ALIASES:
            out.add(TERM_ALIASES[term])
        if len(term) > 4 and term.endswith("ies"):
            out.add(term[:-3] + "y")
        if len(term) > 5 and term.endswith("ing"):
            out.add(term[:-3])
        if len(term) > 4 and term.endswith("es"):
            out.add(term[:-2])
        if len(term) > 3 and term.endswith("s"):
            out.add(term[:-1])
    return out


def chunk_search_terms(chunk: dict) -> set[str]:
    tag_text = (
        " ".join(chunk["tags"])
        if chunk.get("tags")
        else " ".join(extract_tags(chunk.get("text", "")))
    )
    return normalized_terms(
        " ".join(str(chunk.get(key, "")) for key in ("title", "source", "text") if chunk.get(key))
        + " "
        + tag_text
    )


def query_intent_terms(query: str) -> set[str]:
    """Important exact-intent words that should be visible in matched notes."""
    terms = normalized_terms(query)
    topics = set(query_topics(query))
    guarded: set[str] = set()
    for topic in topics:
        guarded.update(terms & INTENT_GUARD_TERMS.get(topic, set()))
    return {term for term in guarded if len(term) >= 3}


def note_query_affinity(query: str, chunk: dict) -> int:
    """Prefer notes whose title/tags match the user's exact words, not just broad topics."""
    query_terms = normalized_terms(query)
    if not query_terms:
        return 0
    title_terms = normalized_terms(f"{chunk.get('title', '')} {chunk.get('source', '')}")
    tag_terms: set[str] = set()
    tags = chunk["tags"] if chunk.get("tags") else extract_tags(chunk.get("text", ""))
    for tag in tags:
        tag_terms.update(normalized_terms(tag))
    title_hits = query_terms & title_terms
    tag_hits = query_terms & tag_terms
    score = (3 * len(title_hits)) + (2 * len(tag_hits))
    query_lower = query.lower()

    tags_str = (
        " ".join(chunk["tags"])
        if chunk.get("tags")
        else " ".join(extract_tags(chunk.get("text", "")))
    )
    chunk_hint = " ".join(
        [
            str(chunk.get("title", "")),
            str(chunk.get("source", "")),
            tags_str,
        ]
    ).lower()
    if re.search(r"\b(s|t)\s+sounds?\b|\bsibil", query_lower) and (
        "de-ess" in chunk_hint or "deess" in chunk_hint or "sibilance" in chunk_hint
    ):
        score += 10
    if re.search(r"\b(s|t)\s+sounds?\b|\bsibil", query_lower) and (
        "vocal-deessing" in chunk_hint or "de-essing and sibilance" in chunk_hint
    ):
        score += 25
    # A request to preserve brightness while controlling general harshness is
    # broader than a sibilance-only problem. Prefer the dedicated workflow,
    # which first distinguishes sibilance, upper-mid bite, distortion, and
    # over-compression before selecting de-essing or dynamic EQ. Without this
    # tie-breaker the de-essing note wins on generic vocal/harsh tag overlap
    # and the answer incorrectly treats every bright/harsh vocal as sibilance.
    if (
        "vocal" in query_lower
        and "harsh" in query_lower
        and re.search(r"\b(bright|brightness|smooth)\b", query_lower)
        and ("harsh-vocal-fix" in chunk_hint or "harsh vocal fix" in chunk_hint)
    ):
        score += 35
    if (
        "boxy" in query_lower
        and "vocal" in query_lower
        and ("boxy-vocal" in chunk_hint or "boxy vocal" in chunk_hint or "low mids" in chunk_hint)
    ):
        score += 45
    if (
        "boxy" in query_lower
        and "vocal" in query_lower
        and ("harsh-vocal" in chunk_hint or "de-essing" in chunk_hint or "sibilance" in chunk_hint)
    ):
        score -= 12
    if (
        "mono" in query_lower
        and re.search(r"\b(disappear|cancel|phase|polarity)\b", query_lower)
        and ("phase" in chunk_hint or "polarity" in chunk_hint or "cancellation" in chunk_hint)
    ):
        score += 10
    if (
        "mono" in query_lower
        and re.search(r"\b(disappear|cancel|phase|polarity)\b", query_lower)
        and ("phase-and-polarity" in chunk_hint)
    ):
        score += 25
    if (
        re.search(r"\b(order|chain|workflow)\b", query_lower)
        and "mix" in query_lower
        and ("mixing-chain-order" in chunk_hint or "mixing chain order" in chunk_hint)
    ):
        score += 25
    if (
        "clip" in query_lower
        and "automation" in query_lower
        and (
            "clip-automation" in chunk_hint
            or "clip automation" in chunk_hint
            or "clip envelope" in chunk_hint
        )
    ):
        score += 35
    if (
        "kick" in query_lower
        and "bass" in query_lower
        and re.search(r"\b(work|mud|low|phase|together)\b", query_lower)
        and ("kick-bass-balance" in chunk_hint or "kick bass balance" in chunk_hint)
    ):
        score += 40
    if "kick" in query_lower and "bass" in query_lower and "drum-layering" in chunk_hint:
        score -= 8
    # Conflicting target-loudness advice is a delivery/normalization question,
    # not primarily a request for Jack's clipper settings. Anchor the answer in
    # the streaming-loudness workflow so it recommends a level-matched
    # reference, translation, limiter safety, and normalization context before
    # suggesting a genre-specific LUFS number.
    if (
        "lufs" in query_lower
        and re.search(r"\b(louder|loudness|target|person|another)\b", query_lower)
        and (
            "mastering-streaming-loudness" in chunk_hint
            or "mastering for streaming loudness" in chunk_hint
        )
    ):
        score += 40
    # Combat sound dropouts must be routed to the voice and memory budget note.
    # A boss fight/combat scenario with dropping out or vanishing sounds needs
    # to be directed to the deliberate budgeting workflow rather than simple volume
    # changes.
    if (
        any(w in query_lower for w in ("vanish", "drop out", "dropout", "disappear", "missing", "boss fight", "heavy combat"))
        and ("wwise" in query_lower or "game" in query_lower)
        and (
            "wwise-combat-voice-memory-budget" in chunk_hint
            or "combat voice and memory budget" in chunk_hint
            or "wwise combat sounds drop out" in chunk_hint
        )
    ):
        score += 35
    return score


def note_rank_key(
    query: str, topics: list[str], item: tuple[float, dict]
) -> tuple[float, int, float]:
    score, chunk = item
    overlap = len(chunk_topics(chunk) & set(topics)) if topics else 1
    tags = chunk["tags"] if chunk.get("tags") else extract_tags(chunk.get("text", ""))
    tag_hits = sum(1 for tag in tags if any(topic in tag for topic in topics))
    affinity = note_query_affinity(query, chunk)
    return (score + (affinity * 30) + ((overlap + tag_hits) * 5), affinity, score)


def display_results(
    query: str, results: list[tuple[float, dict]], limit: int = 3
) -> list[tuple[float, dict]]:
    if not results:
        return []
    topics = query_topics(query)
    notes = [(score, chunk) for score, chunk in results if chunk.get("kind") == "note"]
    manuals = [(score, chunk) for score, chunk in results if chunk.get("kind") != "note"]

    selected: list[tuple[float, dict]] = []
    if notes:
        notes.sort(key=lambda item: note_rank_key(query, topics, item), reverse=True)
        if manuals and prefer_note_over_manual(notes[0], manuals[0], topics):
            selected.append(notes[0])
            if len(selected) < limit:
                selected.extend(manuals[: limit - len(selected)])
        else:
            if (
                manuals
                and manuals[0][0] > notes[0][0]
                and not chunk_is_catalog_boilerplate(manuals[0][1])
            ):
                selected.append(manuals[0])
                if len(selected) < limit:
                    selected.extend(notes[: limit - len(selected)])
            else:
                selected.append(notes[0])
                if len(selected) < limit:
                    selected.extend(manuals[: limit - len(selected)])
    else:
        selected.extend(manuals[:limit])
    deduped: list[tuple[float, dict]] = []
    seen: set[tuple[str, str, int]] = set()
    for item in [*selected, *results]:
        _score, chunk = item
        key = (
            str(chunk.get("kind", "manual")),
            str(chunk.get("source", "")),
            int(chunk.get("page", 0)),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped[:limit]


def intent_guard_status(query: str, results: list[tuple[float, dict]]) -> str:
    """Return whether displayed results match the user's specific intent, not only a broad topic."""
    required = query_intent_terms(query)
    if not required:
        return "not_needed"
    displayed = display_results(query, results, 3)
    if not displayed:
        return "weak"
    for _score, chunk in displayed:
        if chunk.get("kind") != "note":
            continue
        if required & chunk_search_terms(chunk):
            return "strong"
    return "weak"


def intent_guard_failed(query: str, results: list[tuple[float, dict]]) -> bool:
    return intent_guard_status(query, results) == "weak"


def result_payload(query: str, results: list[tuple[float, dict]], limit: int = 3) -> list[dict]:
    payload = []
    for score, chunk in display_results(query, results, limit):
        payload.append(
            {
                "score": round(score, 3),
                "source": chunk["source"],
                "page": chunk.get("page", 0),
                "kind": chunk.get("kind", "manual"),
                "title": chunk.get("title", ""),
                "trust_score": round(source_trust_score(chunk), 3),
                "label": source_label(chunk),
                "text": textwrap.shorten(
                    chunk["text"].replace("\n", " "), width=750, placeholder="..."
                ),
            }
        )
    return payload


def detect_intent(query: str) -> str:
    lowered = query.lower().strip()
    if "glitch effect" in lowered or "glitchy" in lowered:
        return "steps"
    if any(
        word in lowered
        for word in ("fix", "problem", "wrong", "thin", "muddy", "crack", "why does")
    ):
        return "troubleshooting"
    if lowered.startswith(("how", "how do", "how can")):
        return "steps"
    if lowered.startswith(("what", "what is", "what are")):
        return "explain"
    if lowered.startswith(("why", "why is", "why do")):
        return "why"
    return "general"


def diagnostic_reason(query: str, results: list[tuple[float, dict]], weak_match: bool) -> str:
    if not results:
        return "No indexed chunks matched the query."
    if intent_guard_failed(query, results):
        return "Intent guard rejected the top sources as too broad or off-topic."
    if results_are_weak(query, results):
        return "Retrieval scores were too weak for a reliable grounded answer."
    return "Answer grounded from the highest-ranked local sources."
