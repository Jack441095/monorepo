from __future__ import annotations

import re


from kenn.retrieval.retrieval import (
    chunk_topics,
    query_topics,
    source_trust_score,
)

from kenn.core.chat_constants import (
    ANSWER_QUALITY_MIN_SCORE,
    ANSWER_MODES,
    count_actionable_steps,
)

from kenn.core.chat_retrieval import (
    detect_intent,
    load_chunks,
    normalized_terms,
    query_intent_terms,
    source_label,
)

from kenn.llm.llm_rewrite import (
    ABSTAIN_PREFIX,
    CLAIM_CITATION_RE,
    model_evidence,
    resolve_context_chars,
)
from kenn.knowledge.reasoning import get_chunk_id


# The evidence set the gate judges against is the set of chunks the model was actually shown, read out of the
# same list the prompt was assembled from. Deriving it here instead is how the gate ends up wider than the model
# in one direction and narrower in the other, and both have been measured on the streaming chat surface with
# kenn-brain-qwen3-8b and the cache off:
#
# Narrow, fixed 2 Oct 2026: the gate read the top 3 while the model read 12, so a figure in chunk #7 was quoted
# back and reported invented. Acceptance fell from 41% (12 of 29) to 27% (4 of 15) — 10 unsupported-measurement
# and 3 fabricated-source rejections, every one of them a chunk the gate had never opened.
#
# Wide, fixed 2 Oct 2026: the gate went back to reading every chunk's text in full while the prompt fitted 2-4
# excerpts into 1200 chars at 400 each. On index v-db8c6334cf63 at the ask path's limit of 16, "send reverb on a
# vocal bus" put 3 excerpts in front of the model and 10 chunks in front of the gate, with 22 measurements in the
# gate's text that the model was never shown. A "3 dB" from the model's training prior was waved through on
# chunk #9. model_evidence() is the one list both sides read, so the seam is gone rather than tested for.
#
# Note what leaving display_results() also fixed: it de-duplicates on (kind, source, page), and all 3204 note
# sections in that index carry page == 0, so every section of one note collapsed into a single slot. The old
# EVIDENCE_SCAN_WINDOW of 12 was a depth in name only — the real depth was 4 to 10. The list below is keyed by
# chunk, so a note's sections stay distinct exactly as they do in the prompt.
#
# The budget needed the same treatment as the list, and it took a second pass to see it. Taking model_evidence()'s
# max_chars default here looked right and was not: the prompt path reads KENN_LLM_CONTEXT_CHARS, so a run that
# pinned it built a shorter block than this list was read at. At 300 chars on index v-db8c6334cf63 the model saw
# 1 excerpt and this gate judged 3 — the same 1-vs-3 gap as the 41% to 27% measurement above with the roles
# reversed. Both sides now take the budget from llm_rewrite.resolve_context_chars(), so an override moves both
# readers or neither, and the threshold below is untouched either way.
def _evidence_chunks(results: list[tuple[float, dict]]) -> list[tuple[float, dict, str]]:
    """(score, chunk, body-as-shown) for every excerpt the model was given, in prompt order."""
    _block, shown = model_evidence(results, source_label, max_chars=resolve_context_chars())
    return shown


def answer_self_check(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str = "",
    timeline_context: str | None = None,
) -> dict:
    if timeline_context:
        return {
            "passed": True,
            "warnings": [],
            "sections": {"short_answer": True, "try_this": True, "check": True, "sources": True},
            "source_topic_match": True,
            "answered_intent": True,
        }
    topics = query_topics(query)
    displayed = _evidence_chunks(results)
    source_backed = bool(displayed)
    source_topic_match = not topics or any(
        chunk_topics(chunk) & set(topics) for _score, chunk, _body in displayed
    )
    answer_terms = normalized_terms(answer)
    intent_terms = query_intent_terms(query) or {
        term for term in normalized_terms(query) if len(term) >= 4
    }
    answered_intent = not intent_terms or bool(answer_terms & intent_terms)
    sections_present = {
        "short_answer": "short answer:" in answer.lower(),
        "try_this": "try this:" in answer.lower(),
        "check": bool(
            re.search(r"\b(listening|live|quality|implementation)?\s*check:", answer.lower())
        ),
        "sources": "sources:" in answer.lower(),
    }
    warnings: list[str] = []
    if not source_backed:
        warnings.append("no displayed sources")
    if not source_topic_match:
        warnings.append("source topics do not match query topics")
    if confidence == "low":
        warnings.append("low confidence")
    if not answered_intent:
        warnings.append("answer may miss exact query terms")
    if route == "unknown":
        warnings.append("unknown route")
    return {
        "passed": not warnings,
        "warnings": warnings,
        "sections": sections_present,
        "source_topic_match": source_topic_match,
        "answered_intent": answered_intent,
    }


def grounding_report(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str,
    timeline_context: str | None = None,
) -> dict:
    if timeline_context:
        return {
            "score": 100,
            "top_source_trust": 1.0,
            "approved_note": True,
            "source_topic_match": True,
            "answered_intent": True,
            "route_known": True,
            "warnings": [],
        }
    displayed = _evidence_chunks(results)
    topics = set(query_topics(query))
    top = displayed[0][1] if displayed else {}
    top_trust = source_trust_score(top) if top else 0.0
    source_topic_match = not topics or any(
        chunk_topics(chunk) & topics for _score, chunk, _body in displayed
    )
    approved_note = any(
        chunk.get("kind") == "note" and source_trust_score(chunk) >= 0.95
        for _score, chunk, _body in displayed
    )
    answer_terms = normalized_terms(answer)
    intent_terms = query_intent_terms(query) or {
        term for term in normalized_terms(query) if len(term) >= 4
    }
    answered_intent = not intent_terms or bool(answer_terms & intent_terms)
    route_known = route not in {"", "unknown", "clarify"}
    score = 0
    score += int(top_trust * 30)
    score += 25 if source_topic_match else 0
    score += 15 if answered_intent else 0
    score += 10 if approved_note else 0
    score += 10 if route_known else 0
    if confidence == "low":
        score -= 20
    warnings: list[str] = []
    if top_trust and top_trust < 0.7:
        warnings.append("low source trust")
    if not source_topic_match:
        warnings.append("source topic mismatch")
    if not answered_intent:
        warnings.append("answer may miss intent")
    if not route_known:
        warnings.append("uncertain route")
    return {
        "score": max(0, min(100, score)),
        "top_source_trust": round(top_trust, 3),
        "approved_note": approved_note,
        "source_topic_match": source_topic_match,
        "answered_intent": answered_intent,
        "route_known": route_known,
        "warnings": warnings,
    }


def grounding_mode(report: dict) -> str:
    score = int(report.get("score", 0) or 0)
    if score >= 75:
        return "strong"
    if score >= 55:
        return "medium"
    return "weak"


# Three defects this pattern carried, found by running real answers against real evidence. A hyphen
# between two numbers is a range, not a sign: "200-400 Hz" read as "-400 Hz", so quoting the range's
# own lower bound was rejected as invented, and "-18 dBFS" lost its sign and could be restated
# "+18 dBFS" and pass. Ranges are rewritten to their endpoints first, leaving the hyphen unambiguous.
# The trailing \b was the third: it cannot match after "%", so percentages escaped the gate entirely.
_RANGE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)"
    r"(\s*(?:hz|khz|db(?:fs|tp)?|ms|%|lufs?|bpm|bits?))(?![a-z0-9])",
    re.IGNORECASE,
)
_MEASUREMENT_RE = re.compile(
    r"(?<![\d.])-?\d+(?:\.\d+)?\s*(?:hz|khz|db(?:fs|tp)?|ms|%|lufs?|bpm|bits?)"
    r"(?![a-z0-9])",
    re.IGNORECASE,
)


def _measurement_is_supported(measurement: str, allowed: set[str]) -> bool:
    """Whether measurement is allowed, treating integer and .0 forms as equivalent.

    Audio engineers write -14 LUFS or -14.0 LUFS interchangeably, and Live meters display decimal true peaks
    like -1.0 dBTP alongside integer bounds like -1 dBTP. Treating -14.0 LUFS as unsupported when the note
    writes -14 LUFS is a formatting mismatch, not an invention. Similarly, true peak ceilings (-1 dBTP)
    are routinely cited in mixing advice as 1 dB or 1.0 dB true peak headroom.
    """
    if measurement in allowed:
        return True
    m_int = re.sub(r"^(-?\d+)\.0([a-z%]+)$", r"\1\2", measurement)
    if m_int in allowed:
        return True
    m_dec = re.sub(r"^(-?\d+)([a-z%]+)$", r"\1.0\2", measurement)
    if m_dec in allowed:
        return True
    # True peak headroom / ceiling equivalence: answers citing 1 dB or 1.0 dB true peak margin against a -1 dBTP ceiling note
    m_db = re.match(r"^(-?\d+(?:\.0)?)db$", measurement)
    if m_db:
        val = m_db.group(1).removesuffix(".0")
        val_pos = val.lstrip("-")
        if any(
            target in allowed
            for target in (
                f"{val}dbtp",
                f"{val}.0dbtp",
                f"-{val_pos}dbtp",
                f"-{val_pos}.0dbtp",
                f"{val_pos}dbtp",
                f"{val_pos}.0dbtp",
            )
        ):
            return True
    return False


def _unsupported_measurements(found: set[str], allowed: set[str]) -> set[str]:
    """Measurements in found that are not permitted by allowed."""
    return {m for m in found if not _measurement_is_supported(m, allowed)}


def _range_interval_measurements(text: str) -> set[str]:
    """Every integer measurement within a small recommended range (e.g. 3-6 dB -> 3, 4, 5, 6 dB).

    When a note recommends setting backing vocals '3-6 dB below the lead', an answer recommending
    '3-5 dB' or '5 dB' is mathematically within the note's guidance. Large spans (> 10) are skipped to avoid
    broad sweeps.
    """
    added: set[str] = set()
    for m in _RANGE_RE.finditer(text):
        low_str, high_str, unit = m.group(1), m.group(2), m.group(3)
        unit_clean = "".join(unit.lower().split())
        try:
            low, high = float(low_str), float(high_str)
            if low.is_integer() and high.is_integer() and 1 <= (high - low) <= 10:
                for val in range(int(low), int(high) + 1):
                    added.add(f"{val}{unit_clean}")
                    added.add(f"{val}.0{unit_clean}")
        except ValueError:
            pass
    return added


def _question_measurements(question: str) -> set[str]:
    """Measurements typed by the producer this turn, handling colloquial audio shorthand.

    Producers routinely type shorthand like 'boosted around 5k', '+0.8 true peak', or '0.0 peak'.
    When the model echoes these exact figures back (e.g. 5 kHz or +0.8 dBTP), it is addressing the
    producer's stated values, not inventing them.
    """
    q = question
    q = re.sub(r"\b(\d+(?:\.\d+)?)\s*k\b", r"\1 kHz", q, flags=re.IGNORECASE)
    q = re.sub(r"\+(\d+(?:\.\d+)?)", r"\1", q)
    q = re.sub(r"\b(\d+(?:\.\d+)?)\s*true\s*peak\b", r"\1 dBTP \1 dB", q, flags=re.IGNORECASE)
    q = re.sub(r"\b(\d+(?:\.\d+)?)\s*peak\b", r"\1 dB", q, flags=re.IGNORECASE)
    return _measurements(q)


def _measurements(text: str) -> set[str]:
    """Each measurement in `text`, keyed so spacing never decides a match.

    The space between number and unit is dropped rather than collapsed: audio writing puts it both ways
    in the same breath ("120 Hz" in a note, "120Hz" from the model), and treating those as two different
    values rejected answers that quoted the note correctly.
    """
    return {
        "".join(m.lower().split())
        for m in _MEASUREMENT_RE.findall(_RANGE_RE.sub(r"\1\3 \2\3", text))
    }


def measurements_in_order(text: str) -> list[str]:
    """The same measurements as _measurements(), spelled as the text spells them, first sighting first.

    This is the list the model is shown as the figures it may use, so it has to come from the gate's own
    regexes: a figure we list and the gate then rejects would be worse than no list at all. A range shows
    as its two ends because that is how the gate reads it, and "200-400 Hz" in the answer still passes.
    """
    seen: dict[str, str] = {}
    rewritten = _RANGE_RE.sub(r"\1\3 \2\3", text)
    for m in _MEASUREMENT_RE.finditer(rewritten):
        # "10,000 Hz" matches as "000 Hz" because the lookbehind only stops at a digit or a dot. The gate reads it
        # that way too, but listing "000 Hz" would invite the model to write it, so we leave the fragment out.
        if re.match(r"\d,", rewritten[max(0, m.start() - 2):m.start()]):
            continue
        seen.setdefault("".join(m.group(0).lower().split()), " ".join(m.group(0).split()))
    return list(seen.values())


# How far after a number a citation still belongs to it. About one clause: "150 ms [#abc123] with a 4:1 ratio"
# is a citation on the 150 ms, while "150 ms is roughly right, set your crossover, and go and read the reverb
# note [#abc123]" is not. Bounded by the next measurement as well, so a citation cannot hop over a number to
# reach the one after it and leave the nearer claim looking uncited.
_CLAIM_LINK_WINDOW_CHARS = 80


def _measurement_spans(text: str) -> list[tuple[str, int, int]]:
    """Every measurement in `text` as (key, start, end), in the order it was written.

    _measurements() returns a set, which is all the aggregate diff needs and too little here: a claim is one
    number attached to one excerpt, so "150 ms" written twice is two claims and has to be counted twice. The
    range rewrite is the same one _measurements() applies, so "200-400 Hz" is claimed at both endpoints rather
    than once as "-400 Hz".

    The rewrite changes offsets, so the citation scan runs on this same rewritten string. A citation is a short
    bracketed hash with no hyphen and no unit inside the closing bracket, so neither regex can match inside one
    and the rewrite cannot slide a citation out from under its number.
    """
    return [
        ("".join(m.group(0).lower().split()), m.start(), m.end())
        for m in _MEASUREMENT_RE.finditer(_RANGE_RE.sub(r"\1\3 \2\3", text))
    ]


def _first_free_citation(
    citations: list[tuple[str, int]], lower: int, upper: int, taken: set[int]
) -> int:
    """Index of the first unclaimed citation starting in [lower, upper), or -1."""
    for index, (_cid, position) in enumerate(citations):
        if index not in taken and lower <= position < upper:
            return index
    return -1


def _claim_citations(answer: str) -> list[dict]:
    """Pair each numeric claim in `answer` with the excerpt id it cites, or "" for none.

    Forward first, then backward for whatever is left over. "150 ms [#abc]" is the form the prompt asks for, but
    a model that leads with its source ("[#abc] 150 ms") is still citing honestly, and one citation is never
    shared between two claims because the index it used is retired.
    """
    text = _RANGE_RE.sub(r"\1\3 \2\3", answer)
    spans = _measurement_spans(text)
    citations = [(m.group(1), m.start()) for m in CLAIM_CITATION_RE.finditer(text)]
    cited = [""] * len(spans)
    taken: set[int] = set()
    for index, (_key, start, end) in enumerate(spans):
        next_start = spans[index + 1][1] if index + 1 < len(spans) else len(text)
        found = _first_free_citation(citations, end, min(next_start, end + _CLAIM_LINK_WINDOW_CHARS), taken)
        if found >= 0:
            taken.add(found)
        cited[index] = citations[found][0] if found >= 0 else ""
    for index, (_key, start, _end) in enumerate(spans):
        if cited[index]:
            continue
        previous_end = spans[index - 1][2] if index else 0
        found = _first_free_citation(
            citations, max(previous_end, start - _CLAIM_LINK_WINDOW_CHARS), start, taken
        )
        if found >= 0:
            taken.add(found)
        cited[index] = citations[found][0] if found >= 0 else ""
    return [
        {"value": key, "cited": bool(cited_id), "cited_chunk": cited_id}
        for (key, _start, _end), cited_id in zip(spans, cited)
    ]


# The two reasons a citation cannot be vouched for, as stable keys rather than sentences, so a caller can group
# on them and this module stays the only place that decides what a failure is called.
_FABRICATED_ATTRIBUTION = "cited excerpt does not contain that value"
_UNSHOWN_CITATION = "excerpt id was never shown to the model"

# Where a number actually lives, read off the shown bodies instead of off the answer. Measured 2 Oct 2026 on the
# 36-item must-abstain set: the model tagged 2 of 11 numeric claims with an excerpt id and wrote an explicit
# "Insufficient context:" line in 5 of 28 answers, answering anyway in 82.1% of them. The validator was not the
# problem -- across all 28 answers it found 0 fabricated attributions and 0 invented chunk ids -- the model simply
# would not comply. So attribution is now arithmetic over data the gate already holds, and the three classes below
# are what makes acceptance provable without judging anything:
#
#   uniquely_attributed   - exactly one shown body holds the number, so the attribution is determined.
#   ambiguously_attributed - two or more hold it. Grounded, but not attributable to one passage.
#   unattributed         - none hold it. The existing unsupported-measurement case, unchanged.
_UNIQUELY_ATTRIBUTED = "uniquely_attributed"
_AMBIGUOUSLY_ATTRIBUTED = "ambiguously_attributed"
_UNATTRIBUTED = "unattributed"

# How the model's own [#id] lines up with the derived holders. Four buckets that sum to total: `agrees` when the
# named excerpt is one of the holders, `misattributes` when it is a shown excerpt that does not hold the number,
# `cites_unshown_id` when the id was never printed at all, and `absent` when the claim carried no citation. The
# last two stay apart on purpose: one is a pointer to the wrong passage and the other is a pointer to nothing,
# and a capture scoring them together would only learn that the model did not comply.
_CITATION_AGREES = "agrees"
_CITATION_MISATTRIBUTES = "misattributes"
_CITATION_CITES_UNSHOWN_ID = "cites_unshown_id"
_CITATION_ABSENT = "absent"


def _attribution_class(holders: list[str]) -> str:
    """Which of the three classes a derived attribution falls in, decided by how many shown bodies hold the value."""
    if len(holders) == 1:
        return _UNIQUELY_ATTRIBUTED
    if not holders:
        return _UNATTRIBUTED
    return _AMBIGUOUSLY_ATTRIBUTED


def _resolve_chunk_id(
    cited_id: str,
    bodies: dict[str, str],
    shown: list[tuple[float, dict, str]],
) -> str | None:
    """Resolve a model's cited excerpt identifier to a shown chunk ID.

    The 4B model frequently truncates 12-char hexadecimal hashes to 11 characters (e.g. [#efac7b4076d]
    instead of [#efac7b4076db]) or makes a single-character typo due to BPE subword tokenization.
    This caused 14 rejections across 9 probe runs for 'cites an excerpt id that was never shown'.
    We resolve:
    1. Exact match against shown chunk IDs.
    2. 1-based ordinal indices (e.g. '1', '2', '3' or 'source1', 'excerpt1').
    3. Unambiguous prefix of at least 6 hex characters matching exactly one shown chunk.
    4. Single-character substitution slip in a 12-char hex string matching exactly one shown chunk.
    """
    if not cited_id:
        return None
    if cited_id in bodies:
        return cited_id

    # 1-based ordinal index or 'source1' / 'excerpt1' alias
    raw_digits = ""
    lower = cited_id.lower()
    if lower.isdigit():
        raw_digits = lower
    elif lower.startswith(("source", "excerpt", "chunk")) and lower[len("source"):].isdigit():
        raw_digits = lower[len("source"):]
    elif lower.startswith("ex") and lower[2:].isdigit():
        raw_digits = lower[2:]

    if raw_digits:
        try:
            idx = int(raw_digits) - 1
            if 0 <= idx < len(shown):
                return get_chunk_id(shown[idx][1])
        except ValueError:
            pass

    # Unambiguous hex prefix (at least 6 characters) or 12+ char string starting with a 12-char ID
    if len(cited_id) >= 6 and all(c in "0123456789abcdefABCDEF" for c in cited_id):
        prefixes = [
            cid for cid in bodies
            if cid.lower().startswith(lower)
            or (len(lower) >= 12 and lower.startswith(cid.lower()))
        ]
        if len(prefixes) == 1:
            return prefixes[0]

        # Single-character slip on 12-character hex ID
        if len(cited_id) == 12:
            slips = [
                cid for cid in bodies
                if len(cid) == 12 and sum(1 for a, b in zip(cid.lower(), lower) if a != b) == 1
            ]
            if len(slips) == 1:
                return slips[0]

    return None


def verify_claim_citations(answer: str, shown: list[tuple[float, dict, str]]) -> dict:
    """Place every number in `answer` on the shown excerpt that holds it, then cross-check the model's own citation.

    Two passes, deliberately in that order. The derived pass asks nothing of the model: it walks the answers text
    once (via _claim_citations and _measurement_spans, which already had to find the claims to pair citations
    with) and then asks which of the shown bodies contain each value. The count of those bodies is the whole
    finding, so traceability no longer depends on an 8B remembering a tag. The citation pass then reads the
    model's `[#id]` markers against the same bodies, which makes them a cross-check: an answer where the two
    disagree is a real misattribution and gets named, rather than being either accepted silently or rejected for
    a missing tag.

    Only the body is read, not the title and source that _gate_evidence_text() also counts, and that asymmetry is
    deliberate: the model is told to cite the excerpt the number came from, and a figure that only ever appeared
    in a note's title was not the excerpt it was reasoning over. It also means a title-only figure reads as
    `unattributed` here while still passing the aggregate unsupported-measurement check, which sees the wider set.

    Uncited claims are counted and returned but do not warn. The aggregate measurement check already rejects any
    number found nowhere in the evidence, the producer's question or the shown notes, so a second warning on the
    same numbers would reject nothing new while dropping every currently-accepted answer until an 8B model has
    learned the rule. The count is what keeps that reversible: promote `uncited` to a warning on the day the
    citation rate justifies it. Same reasoning keeps `ambiguously_attributed` silent -- the number is in the
    evidence, so no existing warning could fire on it.
    """
    bodies: dict[str, str] = {}
    for _score, chunk, body in shown:
        bodies.setdefault(get_chunk_id(chunk), body)
    # One regex pass per shown body rather than one per claim. The derived pass has to look at every body anyway,
    # and the citation check used to rescan a whole body for each cited claim, so this costs less than it did
    # before on any answer with more than one claim.
    body_measurements = {cid: _measurements(body) for cid, body in bodies.items()}
    claims = _claim_citations(answer)
    for claim in claims:
        value, cited_id = claim["value"], claim["cited_chunk"]
        # Prompt order, so the first holder is the excerpt the model saw first.
        holders = [cid for cid in bodies if value in body_measurements[cid]]
        claim["attribution"] = _attribution_class(holders)
        claim["attributed_chunks"] = holders
        resolved_id = _resolve_chunk_id(cited_id, bodies, shown)
        if resolved_id:
            claim["cited_chunk"] = resolved_id
        if not cited_id:
            claim.update(
                verified=False, reason="uncited", citation_relation=_CITATION_ABSENT
            )
        elif not resolved_id:
            claim.update(
                verified=False,
                reason=_UNSHOWN_CITATION,
                citation_relation=_CITATION_CITES_UNSHOWN_ID,
            )
        elif value in body_measurements[resolved_id]:
            claim.update(
                verified=True, reason="", citation_relation=_CITATION_AGREES
            )
        else:
            claim.update(
                verified=False,
                reason=_FABRICATED_ATTRIBUTION,
                citation_relation=_CITATION_MISATTRIBUTES,
            )
    return {
        "total": len(claims),
        "cited": sum(1 for claim in claims if claim["cited"]),
        "verified": sum(1 for claim in claims if claim["verified"]),
        "uncited": sum(1 for claim in claims if not claim["cited"]),
        # The primary signal, and the reason this function exists: every claim is placed by arithmetic, including
        # the 82% the model left without a tag.
        "uniquely_attributed": sum(
            1 for claim in claims if claim["attribution"] == _UNIQUELY_ATTRIBUTED
        ),
        "ambiguously_attributed": sum(
            1 for claim in claims if claim["attribution"] == _AMBIGUOUSLY_ATTRIBUTED
        ),
        "unattributed": sum(
            1 for claim in claims if claim["attribution"] == _UNATTRIBUTED
        ),
        # The cross-check against the derived holders. These four sum to total, so a capture can score how often
        # the model cooperated without any of it changing an accept or a reject.
        "citation_agreed": sum(
            1 for claim in claims if claim["citation_relation"] == _CITATION_AGREES
        ),
        "citation_contradicted": sum(
            1 for claim in claims if claim["citation_relation"] == _CITATION_MISATTRIBUTES
        ),
        "citation_absent": sum(
            1 for claim in claims if claim["citation_relation"] == _CITATION_ABSENT
        ),
        "citation_unshown": sum(
            1 for claim in claims if claim["citation_relation"] == _CITATION_CITES_UNSHOWN_ID
        ),
        "fabricated_attributions": [
            claim for claim in claims if claim["reason"] == _FABRICATED_ATTRIBUTION
        ],
        "unshown_citations": [
            claim for claim in claims if claim["reason"] == _UNSHOWN_CITATION
        ],
        "claims": claims,
    }


def explicit_abstain_gap(answer: str) -> str:
    """The specific fact the model said was missing, or "" when it did not abstain.

    A first-class output rather than a line of prose, because "the context is insufficient" as advice is what a
    model writes when it is unsure and what it skips when it has already filled the gap with a number. All 36
    items in tooling/data/eval_must_abstain_v1.jsonl are meant to produce this line, and 12 of them are
    Related-questions echo attacks where the only overlapping chunk is a list of the note's own question
    phrasings and holds no figure at all.

    The gap has to be named to count. "Insufficient context:" on its own is the model acknowledging a rule
    without obeying it, and returning the gap rather than a boolean is what makes the difference visible.
    """
    for line in answer.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(ABSTAIN_PREFIX.lower()):
            return stripped[len(ABSTAIN_PREFIX):].strip()
    return ""


# 3 words: shortest gap that still says what is missing ("the notes never cover phase"). "more." or "more detail."
# is the model acknowledging the rule without naming anything, which the 7 Oct 2026 review showed a one-word filler
# gap could pass.
ABSTAIN_MIN_GAP_WORDS = 3
# 25 words: the 5 Oct 2026 replay declines were one short clause (the longest about 15 words), so 25 leaves room for
# a longer topic name while a gap that rambles on is the model starting to answer.
ABSTAIN_MAX_GAP_WORDS = 25
_ABSTAIN_KEPT_WARNINGS = {
    "generated answer cites sources not in the retrieved evidence",
    "generated answer names a product that nobody mentioned",
}
# A full stop, "!" or "?" followed by more text: the gap has become two sentences. The final full stop is fine.
_ABSTAIN_SENTENCE_BREAK_RE = re.compile(r"[.!?]\s+\S")
# Signs the "gap" has turned into instruction. A clause that opens with an imperative ("so try", ", use", "set"), a
# file name (fake-note.md) or a unit word is advice or a citation, not a missing topic. The unit words cost an honest
# decline that names a unit ("no attack time in ms"); that goes to the full gate and normally lands on the template,
# which we accept because the alternative is letting a figure ride through on a disclaimer.
#
# That denylist is open-ended: "I'd reach for a slow release" is advice no list of verbs will catch, so a decline
# must also say something is missing (_ABSTAIN_ABSENCE_RE). We did not add a second-clause rejection, because "the
# notes cover EQ Eight but not how to set up a send in Live" is a real decline with two clauses. What can still slip
# through is one line of 25 words or fewer with an absence word, no digit or spelled figure, no product, no source
# and no claimed Live change, which is advice at worst, not a fabricated fact.
_ABSTAIN_INSTRUCTION_RE = re.compile(
    r"(?:^|[,;:\u2014-]\s*|\b(?:so|and|then|but)\s+)"
    r"(?:try|use|set|add|cut|boost|lower|raise|apply|put|pick|go with|see|check)\b"
    r"|\b[\w-]+\.\w{2,4}\b"
    r"|\b(?:ms|milliseconds?|hz|khz|db|dbfs|lufs|percent|to one)\b",
    re.IGNORECASE,
)
# A decline names what is missing, so the gap has to contain an absence word ("do not cover", "nothing on", "but not").
_ABSTAIN_ABSENCE_RE = re.compile(
    r"\b(?:not|no|never|nothing|none|without|missing|lacks?|lacking)\b|n['\u2019]t\b", re.IGNORECASE)
# A figure of any kind in the gap is an answer ("though 150 would suit", "one fifty", "four or five"). Digits and
# spelled numerals both count, so a spelled figure cannot dodge verify_claim_citations(), which only reads digits.
# Bare "one" is left out: it is a pronoun in "differs from a minimum-phase one", and "one fifty" is still caught by
# "fifty". Ableton's "EQ Eight" is blanked first for the same reason. The cost is that a gap naming "a 4B model" or "double-tracking" falls to the full gate and is usually
# swapped for the template.
_EQ_EIGHT_RE = re.compile(r"\beq eight\b", re.IGNORECASE)
_ABSTAIN_FIGURE_RE = re.compile(
    r"\d|\b(?:zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen"
    r"|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|half"
    r"|double|quarter)\b",
    re.IGNORECASE,
)


def whole_reply_abstain_gap(answer: str) -> str:
    """The gap when the whole reply is one "Insufficient context: <gap>" line, else "".

    explicit_abstain_gap() finds the prefix on any line, so a full answer with the prefix tacked on the end, or a
    decline followed by advice, plugin names or a made-up Sources list, would read as a decline. A decline is
    only a decline when nothing else is said: one non-empty line, the exact prefix (case-sensitive, as both
    prompts ask for it) and a gap of at least ABSTAIN_MIN_GAP_WORDS words. Anything else goes through the normal
    gate, which is where advice that happens to mention missing context belongs.
    """
    stripped = answer.strip()
    if "\n" in stripped or not stripped.startswith(ABSTAIN_PREFIX):
        return ""
    gap = stripped[len(ABSTAIN_PREFIX):].strip()
    # Words that carry a letter or digit, so a lone "." or "-" cannot pad a filler gap up to the minimum.
    words = [word for word in gap.split() if any(ch.isalnum() for ch in word)]
    if not ABSTAIN_MIN_GAP_WORDS <= len(words) <= ABSTAIN_MAX_GAP_WORDS:
        return ""
    # One clause naming what is missing. A second sentence, a "so try ..." tail, a file name or a unit is the model
    # answering on the same line as the disclaimer, and that has to meet the full gate like any other answer.
    if _ABSTAIN_SENTENCE_BREAK_RE.search(gap) or _ABSTAIN_INSTRUCTION_RE.search(gap):
        return ""
    if _ABSTAIN_FIGURE_RE.search(_EQ_EIGHT_RE.sub(" ", gap)) or not _ABSTAIN_ABSENCE_RE.search(gap):
        return ""
    return gap


_STRUCTURE_TERMS = {
    "short", "answer", "try", "this", "check", "sources", "source", "step",
    "steps", "first", "then", "use", "using", "based", "notes", "note",
}
_CITED_SOURCE_FILENAME_RE = re.compile(r"\(([\w\-]+\.md)\)")


def _sources_section(answer: str) -> tuple[int, int]:
    """Byte range of the answer's own "Sources:" list, or (-1, -1) when there isn't one."""
    lowered = answer.lower()
    start = lowered.find("sources:")
    if start == -1:
        return -1, -1
    end = lowered.find("you could also ask", start)
    return start, (end if end != -1 else len(answer))


def _cited_source_filenames(answer: str) -> set[str]:
    """Filenames cited in the answer's own "Sources:" bullet list.

    llm_rewrite.py's system prompt tells the model to reproduce the exact
    "Title (filename.md)" labels it was given (source_label()'s format), but
    a small local model doesn't reliably copy them -- it can invent
    plausible-looking filenames instead. Scoped to the Sources: section only
    (not the whole answer) so a legitimate filename mention elsewhere isn't
    misread as a citation.
    """
    start, end = _sources_section(answer)
    if start == -1:
        return set()
    return {m.lower() for m in _CITED_SOURCE_FILENAME_RE.findall(answer[start:end])}


def _prose_without_sources(answer: str) -> str:
    """The answer with its own citation list removed.

    The Sources: line is copied from the labels we handed the model, so its words are guaranteed to
    appear in the evidence. Counting them toward evidence overlap let an answer clear the floor on the
    strength of the citation alone, with nothing in the prose actually drawn from the note.
    """
    start, end = _sources_section(answer)
    if start == -1:
        return answer
    return (answer[:start] + answer[end:]).strip()


_SOURCE_PUNT_RE = re.compile(
    r"\b(mentioned in the sources?|source pages? below|sources? below to verify|"
    r"see the sources? (?:for|below)|check the sources? (?:for|below))\b",
    re.IGNORECASE,
)


def _punts_to_sources(answer: str) -> bool:
    """True if the answer tells the user to go consult "the sources"
    themselves instead of actually synthesizing them.

    Live-tested 2026-08-03: asked "how do i set up a send reverb". The real
    top source (reverb-send-workflow.md) has concrete steps (create a return
    track, 100% wet, high-pass 200-400 Hz, send 10-20%), but the generated
    "Try this:" section was "Open the relevant Ableton view or device
    mentioned in the sources... Use the source pages below to verify the
    exact command or setting name" -- content-free filler that punts the
    actual work back to the user, who can't act on it (the chat UI only
    shows source titles, not their full text). This slipped past the
    evidence-overlap check because other sections of the same answer drew
    real content from a different one of the 3 retrieved sources, keeping
    the aggregate overlap score high enough to pass.
    """
    return bool(_SOURCE_PUNT_RE.search(answer))


# Literal instructional fragments from llm_rewrite.py's SYSTEM_PROMPT_TEMPLATE
# answer-structure spec, e.g. "Short answer: (one punchy paragraph — your
# verdict first, then the reason)". These parenthesized descriptions tell the
# model what to WRITE in each section; they must never appear as the actual
# generated content.
_PROMPT_INSTRUCTION_ECHO_PHRASES = (
    "one punchy paragraph",
    "your verdict first, then the reason",
    "every step must be something jack can do right now in the daw",
    "one paragraph of the underlying engineering principle",
    "bullet list matching the provided source labels",
    "up to 3 short follow-up question bullets",
)


def _echoes_prompt_instructions(answer: str) -> bool:
    """True if the answer echoes its own system-prompt instructions back as
    if they were content.

    Live-tested 2026-08-03: asked "how do i set up a send reverb". The
    generated answer opened with "Short answer: (one punchy paragraph — your
    verdict first, then the reason)" -- qwen2.5:1.5b copied the literal
    parenthesized instruction describing what to write, instead of writing
    it, the same failure already fixed once in the weekly-review admin
    agent (business/agents/Admin/local_agent.py), now showing up in KENN's
    own rewrite path. Slipped past every other check because the rest of
    the same answer (Try this: steps, Why it matters) had strong evidence
    overlap with real note content.
    """
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _PROMPT_INSTRUCTION_ECHO_PHRASES)


# A chat answer is advice; only the Live command path changes the set, and only after Apply. A model that writes
# "I've turned the bass down 2 dB" is handing the user a receipt for something never happened, so that answer is
# thrown away and the template is used. Checked against 122 Qwen answers from the Stage 1 comparison: no false hits
# on the auxiliary forms ("I'd cut", "you'll want to set" are advice and don't match).
#
# The auxiliary-only version missed the plainer past tense, which is what a small local model actually writes:
# "I lowered the bass by 2 dB" claims exactly as much as "I have lowered the bass by 2 dB" and slipped through on
# 25 of 29 realistic phrasings. Hence the second branch. Bare "I" takes the whole verb list, "set" and "cut"
# included, because the two errors are not symmetric: a missed claim shows the producer a receipt for a change
# that never happened, while a false positive only falls back to the template. The advice forms stay clean anyway,
# because no modal can reach either branch: "I'd set" is stopped by the apostrophe, and "I would set",
# "I will set" and "I'll set" are stopped by no modal being in the verb list.
_CHANGE_VERBS = (
    r"turned|set|muted|unmuted|soloed|unsoloed|panned|lowered|raised|boosted|cut|added|inserted|loaded|"
    r"applied|changed|adjusted|renamed|created|removed|deleted|moved|made|dropped|bypassed|armed|disarmed|"
    r"assigned|duplicated|copied|imported|exported|recorded|sent|wrote|replaced|swapped|nudged|faded|chopped|"
    r"routed|quantized|disabled|enabled|started|stopped|saved|cleared|reset|unlinked|grouped|ungrouped|"
    r"selected|deselected|automated|opened|closed"
)
_LIVE_CHANGE_CLAIM_RE = re.compile(
    # "I've turned", "I have set", "I just muted", "I now lowered", "I've gone ahead and set"
    rf"\bI(?:'ve|\u2019ve| have| just| now| already)\s+(?:just\s+|now\s+|gone ahead and\s+|already\s+)?"
    rf"(?:{_CHANGE_VERBS})\b"
    # Plain past tense with no auxiliary: "I lowered the bass by 2 dB", "I muted the kick", "I set the send to 15%"
    rf"|\bI\s+(?:then\s+|also\s+|went ahead and\s+)?(?:{_CHANGE_VERBS})\b"
    # "Done." and "Done - the send is set up." The delimiter used to be mandatory, so "Done - ..." missed.
    rf"|^\s*done\b",
    re.I | re.M,
)


def claims_live_change(answer: str) -> bool:
    return bool(_LIVE_CHANGE_CLAIM_RE.search(answer))


# Long enough to hold the longest single match either guard regex can produce, so a match that begins in the
# previous token is still seen whole. "I have gone ahead and quantized" is 32 characters and is the longest
# _LIVE_CHANGE_CLAIM_RE form; a range like "200 - 400 Hz" plus its unit is under 20.
_STREAM_GUARD_CONTEXT_CHARS = 48


def _guard_tail(window: str) -> str:
    """The last `_STREAM_GUARD_CONTEXT_CHARS` of `window`, never starting inside a word.

    Cutting mid-number is the one way this guard could invent a rejection: "0 ms" lifted out of "150 ms" reads
    as a measurement the finished answer does not contain, and a conservative false positive throws away an
    answer that was good. Backing up to the previous whitespace keeps "200-400 Hz" and "-1 dBTP" whole, which
    is also what the range rewrite needs.
    """
    tail = window[-_STREAM_GUARD_CONTEXT_CHARS:]
    cut = len(window) - len(tail)
    while cut > 0 and not window[cut - 1].isspace():
        cut -= 1
    return window[cut:]


class StreamedAnswerGuard:
    """Per-token check on streamed prose, for the two rejection causes that are safe to catch early.

    The full gate costs 1.16 ms median / 1.87 ms max of text work on the 29 answers captured 2 Oct 2026, which is
    why the streaming path used to discard every token and show the producer nothing until generation AND the gate
    had both finished. We cannot make that gate incremental, but two of its eight warnings are prefix-sound:

    - unsupported measurements, because the accepted side of `_measurements(answer) - accepted` (the shown
      evidence, the producer's question and the shown notes in full, see _accepted_measurements) is fixed before
      the first token while the answer side only grows;
    - claims_live_change, because a regex match inside a prefix is still a match inside the finished answer.

    The other three are not: evidence_overlap divides by an answer_terms set that grows with every token, and
    answer_quality_report and grounding_mode need the whole answer. None of those three fired in either 2 Oct 2026
    run of 29 queries, so the streaming path leaves them to the authoritative gate at the end.

    This guard runs on a short window rather than the accumulated text: re-scanning the whole answer per token would
    cost the 1.16 ms full pass once per token, while 48 characters of carry plus one token is a few microseconds.
    The window is a substring of the prefix, so a match in it is a match in the answer.
    """

    def __init__(self, allowed_measurements: set[str]) -> None:
        self._allowed = allowed_measurements
        self._carry = ""

    def check(self, token: str) -> dict | None:
        """None while the text is still defensible, else why we stopped streaming it."""
        window = self._carry + token
        # "-6 dB" is also the front half of "-6 dBFS" and "-0.3 dBTP", and the model's tokenizer splits right
        # after the dB. Judging the window there cut two good answers on 2 Oct 2026 (the sources had -6 dBFS and
        # -0.3 dBTP). The carry keeps the text, so the next token's window sees the whole unit.
        judged = window[:-2] if window.lower().endswith("db") else window
        leaked = _unsupported_measurements(_measurements(judged), self._allowed)
        if leaked:
            return {
                "warning": (
                    "streamed generation introduced unsupported measurements: "
                    + ", ".join(sorted(leaked))
                ),
                "unsupported_measurements": sorted(leaked),
            }
        if claims_live_change(window):
            return {
                "warning": "streamed generation claims it changed the Live set",
                "unsupported_measurements": [],
            }
        self._carry = _guard_tail(window)
        return None


def _gate_evidence_text(
    shown: list[tuple[float, dict, str]],
    timeline_context: str | None = None,
    additional_evidence_text: str | None = None,
) -> str:
    """The exact text the gate judges an answer's numbers against.

    Streamed generation needs this before the answer exists, so it lives in one place and both readers call it.
    """
    evidence_text = " ".join(
        " ".join(
            (
                str(chunk.get("title") or ""),
                str(chunk.get("source") or ""),
                # The body the prompt carried, not chunk["text"]. Title and source are in the prompt too, inside
                # the label attribute of the same <source_excerpt>, so this set stays a subset of what the model
                # read. Reading the raw text instead is what let the gate vouch for numbers from chunks #7 to #10.
                body,
            )
        )
        for _score, chunk, body in shown
    )
    if timeline_context:
        evidence_text = f"{evidence_text} {timeline_context}"
    if additional_evidence_text:
        evidence_text = f"{evidence_text} {additional_evidence_text}"
    return evidence_text


def _shown_note_text(shown: list[tuple[float, dict, str]]) -> str:
    """Every section of every note that a shown excerpt was cut from, as one string. Manual pages are left out."""
    sources = {
        str(chunk.get("source"))
        for _score, chunk, _body in shown
        if chunk.get("kind") == "note" and chunk.get("source")
    }
    if not sources:
        # Only manual pages or nothing were shown, so there is no note to widen to and the excerpts stand alone.
        return ""
    # The shown chunks' own full text goes in as well as the index's copy. A result list built outside
    # load_chunks() (a test, or an index reloaded after the search ran) would otherwise lose its own sections.
    texts = [str(chunk.get("text") or "") for _score, chunk, _body in shown if chunk.get("kind") == "note"]
    # load_chunks() is cached, but picking out the sections by source is a fresh pass over all of them every call.
    # On v-5f6964698b76 (3974 chunks) that pass took 0.1 ms and the measurement pass over the four largest notes
    # (22,664 chars) 0.85 ms, measured 10 Oct 2026 with a bench running. The gate runs at most three times per
    # answer, and the answer takes seconds to generate, so an index by source would be a cache nobody needs.
    texts += [
        str(chunk.get("text") or "")
        for chunk in load_chunks()
        if chunk.get("source") in sources and chunk.get("kind") == "note"
    ]
    return " ".join(texts)


# The gate used to accept only the figures in the shown excerpts. The 8 Oct 2026 bench refused 116 figures over 12
# runs (kenn-evaluation-data/2026-10-08-refused-figures). Of those, 20 were in the producer's own question and 23
# were in a shown note but past the 400-character excerpt. On main's held-out run, 6 of 15 rejected answers had
# every refused figure in one of those two places.
# Examples: eq-kick-bass-phase asks about a cancel "around 60 Hz", and all 8 answers that said 60 Hz back were
# refused. loud-streaming-targets wrote the note's -1 dBTP and was refused 3 runs out of 3.
#
# This does not reopen the 2 Oct "wide" bug described above _evidence_chunks. There, a "3 dB" passed on chunk #9,
# which the model was never shown. Here the extra figures come only from notes the model saw part of. Manual pages
# are left out because every manual chunk shares one source, and "the whole manual" would accept almost any Hz.
#
# The question is the producer's words this turn, passed in separately, and not the `query` every other check
# reads. On a follow-up that query is search_query_with_history(): earlier turns, a Mix Review context turn, the
# turn being corrected, trimmed of a subject or a 'not' but with their figures intact. Taking figures from it would let "and the guitars?" after "cut 300 Hz on the
# bass by 4 dB?" pass 300 Hz and 4 dB for the guitars, and a Mix Review turn would pass -7.9 LUFS the producer
# never typed (read-only review of this branch, 10 Oct 2026).
#
# Four costs we accept:
# - The context is not checked. The note may give the same number for something else, for example -18 dBFS as a
#   gain-staging target where the answer uses -18 dB as a threshold.
# - A producer's proposed setting echoed back as advice ("should I boost 5 kHz by 3 dB?" "yes, 3 dB") now passes.
# - So does a figure the producer rules out ("no, not 300 Hz, I meant 2 kHz"). An answer that says 300 Hz there
#   is most often saying "not 300 Hz", and the gate cannot tell either way without reading the sentence.
# - The prompt's allowed-figures list in llm_rewrite does not grow to match. A bare number from a section the model
#   never read has no sentence saying what it measures, so the gate stays wider than the list, never narrower.
#
# Only the measurement check widens. Overlap and product checks still read evidence_text alone, and the query is
# still kept out of overlap (see the comment in generated_answer_validation). verify_claim_citations still reads the
# excerpts only: a whole-note figure tagged with an excerpt id is still a misattribution, because the model cannot
# have read it in that excerpt. So is a question figure tagged that way, so the widening helps untagged claims only.
def _accepted_measurements(
    question: str, shown: list[tuple[float, dict, str]], evidence_text: str
) -> set[str]:
    """Every measurement an answer may carry: those in the evidence text, the producer's question, and the shown notes in full."""
    shown_note_text = _shown_note_text(shown)
    return (
        _measurements(evidence_text)
        | _range_interval_measurements(evidence_text)
        | _question_measurements(question)
        | _measurements(shown_note_text)
        | _range_interval_measurements(shown_note_text)
    )


def evidence_measurements(
    results: list[tuple[float, dict]],
    *,
    question: str,
    timeline_context: str | None = None,
    additional_evidence_text: str | None = None,
) -> set[str]:
    """Every measurement the gate will accept in an answer, keyed the way the gate keys them.

    The streamed guard is built from this, so it has to take the same question the final gate is called with, or a
    figure the producer typed would stop the stream that the final gate would have let through.
    """
    shown = _evidence_chunks(results)
    return _accepted_measurements(
        question, shown, _gate_evidence_text(shown, timeline_context, additional_evidence_text)
    )


# Third-party plugin makers and products the model tends to reach for. A closed list on purpose: it is a tripwire
# for the 3 Oct case (a low-end question answered with FabFilter Pro-Q3, Pro-D2 and Timeless nobody had mentioned),
# not a catalogue. Ableton's own devices are not here. Bare "waves" is a word, so only the Waves product names count.
_PRODUCT_FAMILIES = {
    "fabfilter": re.compile(
        r"\bfab[- ]?filter\b|\bpro[- ]?(?:q|c|l|r|mb|ds|g|d)[- ]?\d\b|\bpro-(?:q|c|l|r|mb|ds|g)\b"
        r"|\btimeless[ -]?\d?\b|\bsaturn[ -]?\d\b|\btwin[ -]?\d\b|\bvolcano\b"
    ),
    "waves": re.compile(r"\bwaves (?:audio|ssl|api|cla|renaissance|rcomp|c[1-6]|l[1-3]|q10|tune)\b|\bwaveshell\b"),
    "izotope": re.compile(r"\bi?zotope\b|\bozone ?\d*\b|\bneutron ?\d*\b|\bnectar ?\d*\b|\brx ?\d+\b"),
    "soundtoys": re.compile(r"\bsoundtoys\b|\bdecapitator\b|\becho ?boy\b"),
    "valhalla": re.compile(r"\bvalhalla\b|\bvintage ?verb\b|\bvalhalla ?room\b|\bvalhalla ?shimmer\b"),
    "universal audio": re.compile(r"\buad\b|\buniversal audio\b"),
    "slate": re.compile(r"\bslate digital\b|\bvirtual mix ?rack\b"),
    "plugin alliance": re.compile(r"\bplugin alliance\b|\bbrainworx\b|\bbx[_ ]?digital\b"),
    "native instruments": re.compile(r"\bnative instruments\b|\bkontakt\b|\bmassive x\b|\breaktor\b"),
    "serum": re.compile(r"\bxfer\b|\bserum\b"),
    "omnisphere": re.compile(r"\bomnisphere\b|\bspectrasonics\b"),
    "sylenth": re.compile(r"\bsylenth ?\d?\b"),
    "oeksound": re.compile(r"\boeksound\b|\bsoothe ?2?\b"),
    "sonnox": re.compile(r"\bsonnox\b"),
    "softube": re.compile(r"\bsoftube\b"),
    "cableguys": re.compile(r"\bcableguys\b|\bshaperbox\b|\bvolumeshaper\b"),
    "arturia": re.compile(r"\barturia\b"),
    "celemony": re.compile(r"\bcelemony\b|\bmelodyne\b"),
}


# 4 Oct 2026 review: "a timeless pad sound", "an ozone layer of pads" and "soothe harsh vocals" were taken for plug-in
# names and got the no-manual line. Only the question side is scrubbed; the list above still catches a bare
# "Timeless" the model writes into an answer.
_PRODUCT_WORD_AS_ENGLISH_RE = re.compile(
    r"\btimeless\b(?![ -]?\d)|\bvolcano\b(?![ -]?\d)|\bozone layers?\b|\bsoothe\b(?= (?:the|my|harsh|it|that|this)\b)"
)


def names_a_product(query: str) -> str:
    """The plugin maker the question mentions, or "" when it names none from the list above."""
    text = _PRODUCT_WORD_AS_ENGLISH_RE.sub(" ", query.lower())
    return next((family for family, pattern in _PRODUCT_FAMILIES.items() if pattern.search(text)), "")


def text_mentions_product(family: str, text: str) -> bool:
    return bool(_PRODUCT_FAMILIES[family].search(text.lower()))


def names_only_a_product(query: str) -> bool:
    """True when the message is a plugin brand or product and nothing else, such as "fab filter".

    Left to routing it matches the generic word ("filter") and the answer describes a plugin the notes never
    covered; it needs a question back instead.
    """
    text = query.lower()
    if not any(pattern.search(text) for pattern in _PRODUCT_FAMILIES.values()):
        return False
    for pattern in _PRODUCT_FAMILIES.values():
        text = pattern.sub(" ", text)
    leftover = re.sub(r"\b(?:the|a|an|plug-?ins?)\b", " ", re.sub(r"[^\w\s]+", " ", text))
    return not leftover.split()


def unasked_product_names(answer: str, query: str, evidence_text: str = "") -> list[str]:
    """Plugin makers the answer names that neither the question nor the notes do.

    A model that has been told nothing about a brand is inventing the claim that the brand does the job, and
    the user then goes looking for a plugin they may not own. Brands the user brought up, or the retrieved
    notes mention, are fine to use.
    """
    support = f"{query} {evidence_text}".lower()
    answer = answer.lower()
    return sorted(
        family
        for family, pattern in _PRODUCT_FAMILIES.items()
        if pattern.search(answer) and not pattern.search(support)
    )


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(\d])")
_LINE_MARKER_RE = re.compile(r"^(\s*(?:[-*•]|\d+[.)])\s+)")
_NUMBERED_LINE_RE = re.compile(r"^(\s*)\d+([.)]\s)")
_HEADING_LINE_RE = re.compile(r"^\s*(?:#{1,4}\s+\S|[A-Z][A-Za-z' ]{2,40}:\s*$)")
# Past this much loss the answer is no longer the one the model wrote, so the template stands instead.
_SALVAGE_MIN_KEPT_SHARE = 0.6
_SALVAGE_MIN_WORDS = 30


_INLINE_STEP_RE = re.compile(r"^((?:[A-Z][A-Za-z' ]{2,30}:\s*)?)(\d+)([.)]\s)")


def _join_step_numbers(sentences: list[str]) -> list[str]:
    """Put a bare "2." back on the sentence it numbers; the split cuts between the two."""
    joined: list[str] = []
    carry = ""
    for sentence in sentences:
        if re.fullmatch(r"(?:[A-Z][A-Za-z' ]{2,30}:\s*)?\d+[.)]", sentence):
            carry = f"{carry}{sentence} "
            continue
        joined.append(carry + sentence)
        carry = ""
    return joined


_LABEL_RE = re.compile(r"^([A-Z][A-Za-z' ]{2,30}:\s*)")


def _keep_label(sentences: list[str], survivors: list[str]) -> list[str]:
    """Hand a dropped sentence's "Try this:" label to the first sentence that stays."""
    if not survivors or sentences[0] in survivors:
        return survivors
    label = _LABEL_RE.match(sentences[0])
    if label and not _LABEL_RE.match(survivors[0]):
        return [label.group(1) + survivors[0]] + survivors[1:]
    return survivors


def _renumber_inline_steps(sentences: list[str]) -> list[str]:
    """Steps written inline on one line ("1. ... 2. ... 3. ...") count again from 1 once one is gone."""
    count = 0
    renumbered = []
    for sentence in sentences:
        step = _INLINE_STEP_RE.match(sentence)
        if step:
            count += 1
            sentence = f"{step.group(1)}{count}{step.group(3)}{sentence[step.end():]}"
        renumbered.append(sentence)
    return renumbered


def drop_unsupported_sentences(answer: str, unsupported: list[str]) -> str:
    """The answer without the sentences that carry a measurement the notes do not, or "" if too little is left.

    4 Oct 2026: 9 to 12 of about 41 background answers a run were rejected for one invented number, and the
    rest of the answer was fine. Cutting the sentence keeps the gate's promise (no number reaches the user
    that the notes lack) without throwing away the answer. The caller must validate the result again; this
    only edits.
    """
    bad = set(unsupported)
    if not bad:
        return ""
    # Cut the capped ending first. Cut after, the last full stop could be the "2." of a step whose sentence we
    # had just dropped, and a salvaged answer too short for end_on_a_whole_sentence went out mid-word.
    answer = _cut_to_a_whole_sentence(answer)
    kept_lines: list[str] = []
    dropped_a_step = False
    for line in answer.split("\n"):
        if not (_measurements(line) & bad):
            kept_lines.append(line)
            continue
        marker = _LINE_MARKER_RE.match(line)
        prefix = marker.group(1) if marker else ""
        sentences = _join_step_numbers(_SENTENCE_SPLIT_RE.split(line[len(prefix):]))
        survivors = [s for s in sentences if not (_measurements(s) & bad)]
        if len(survivors) < len(sentences):
            survivors = _renumber_inline_steps(_keep_label(sentences, survivors))
        if survivors:
            kept_lines.append(prefix + " ".join(survivors))
        elif _NUMBERED_LINE_RE.match(line):
            dropped_a_step = True

    # A heading whose body went with the sentence would read as an empty section.
    cleaned: list[str] = []
    for index, line in enumerate(kept_lines):
        if _HEADING_LINE_RE.match(line):
            following = next((l for l in kept_lines[index + 1:] if l.strip()), "")
            if not following or _HEADING_LINE_RE.match(following):
                continue
        cleaned.append(line)

    if dropped_a_step:
        count = 0
        for index, line in enumerate(cleaned):
            if _HEADING_LINE_RE.match(line):
                count = 0
            numbered = _NUMBERED_LINE_RE.match(line)
            if numbered:
                count += 1
                cleaned[index] = f"{numbered.group(1)}{count}{numbered.group(2)}{line[numbered.end():]}"

    trimmed = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()
    before = len(_prose_without_sources(answer).split())
    after = len(_prose_without_sources(trimmed).split())
    if after < _SALVAGE_MIN_WORDS or after < before * _SALVAGE_MIN_KEPT_SHARE:
        return ""
    return trimmed


# The three shapes below are every way a refused figure sat beside a step, rather than in it, across the 12 probe
# runs of 10 Oct 2026. Each is cut phrase and all, so the step that held it stays. Anything else (a figure that is
# the object of the step, "set the preamp so the input is at -18 dBFS") still costs its sentence: without the
# figure that step says nothing.
#
# A bracket or dash aside only goes when it opens on an example marker. Unmarked, the same brackets hold the
# step's own figure or its limit, "Set the threshold (-18 dB)" or "push the depth (never past 10 dB)", and cutting
# those shipped a different instruction through the gate in review on 11 Oct. All the bracket saves in the v3
# runs opened on "e.g."; the marker costs us one save across the 12 runs, an unmarked "(above 1 kHz)".
#
# The marker is not enough on its own: "(e.g., never past 10 dB)" is still a limit, so an aside with a limit or
# condition word stays too. A marked value with no such word ("Set the threshold (e.g., -18 dB)") does go, and the
# step reads "Set the threshold": vaguer, but the model offered the figure as an example, and that beats losing
# the step to the sentence drop. The apostrophe in "n't" is either kind, because the model writes the curly one
# more often than the straight (34 to 14 across the 479 probe answers of 10 Oct).
#
# An example also has to end on its figure. Whatever follows the figure inside the aside is either a qualifier
# that makes it a limit after all ("10 dB or less", "2 kHz tops") or the model already writing its next step
# ("— like one at 2 kHz, then key it from the kick —", a comma splice the third review on 11 Oct shipped with
# "key it from the kick" gone). Every one of the 13 saves in the 12 probe runs ends on its figure.
#
# Ending on a figure is not enough either, because the run-on can end on one of its own: "— like one at 2 kHz,
# then key it from the kick at 6 dB —" and "(say, 10 dB or less, ideally 6 dB)" both did in the fourth review on
# 11 Oct. So the only comma an example may hold is the one straight after its marker ("e.g., 300 Hz"); a later
# comma means a second clause and the aside stays. None of the 13 saves has a second comma.
_EXAMPLE_MARKER = r"(?:(?:like|such as|for example|for instance|say)\b|e\.g\.)"
# "or less", "tops", "no greater than" and "keep/hold/limit it to" came from the fourth review: each turns the
# figure after it into a bound, "(e.g., 3 dB or less around 300 Hz)" ends on a figure and is still a limit.
_LIMIT_WORDS_RE = re.compile(
    r"\b(?:never|not|no \w+er|only|if|unless|under|over|past|above|below|beyond|within|at least|at most"
    r"|at the most|up to|as much as|less than|more than|exceed\w*"
    r"|or (?:less|lower|more|higher|fewer)|tops|max(?:imum)?|min(?:imum)?|cap(?:s|ped|ping)?|ceiling|stop at"
    r"|keep\w*|hold\w*|limit\w*)\b|n[’']t\b|[<>≤≥]",
    re.IGNORECASE,
)
# A joining word starts a second clause just as the comma does: "— like one at 2 kHz and key it from the kick at
# 6 dB —" still shipped as "...on the bass bus not the snare" in the fifth review on 11 Oct, with "then" the same.
# "or" is off the list because "e.g., 100 Hz or 120 Hz" is two examples, not a second step; none of the 13 saves
# has any of these words.
_JOINS_A_CLAUSE_RE = re.compile(r"\b(?:and|then|while|plus|with|but)\b", re.IGNORECASE)
# The word before the aside can need it as its object: "keep the depth under (e.g., 10 dB) so..." would ship as
# "keep the depth under so...", and "Set the threshold to (e.g., -18 dB) on the bus" as "to on the bus". The hedges
# and joiners at the end ("Aim for roughly (e.g., -14 LUFS) on the master", "-14 LUFS or (e.g., -16 LUFS)") came
# from the fourth review: the step reads as garbled rather than wrong, but it is no better than the sentence drop.
_LEADS_INTO_ASIDE_RE = re.compile(
    r"\b(?:to|at|by|of|for|from|under|over|below|above|than|around|near|about|past|beyond|between|within|is|are|be"
    r"|into|onto|toward|towards|roughly|approximately|just|or|and)[ \t]*$",
    re.IGNORECASE,
)
# "apply a linear-phase EQ to the low-mid range (e.g., 100–300 Hz) to check..." The 60-character limit keeps us to
# a short aside; a longer bracket is a clause of its own and goes with its sentence instead.
_BRACKET_ASIDE_RE = re.compile(rf"[ \t]*\((?={_EXAMPLE_MARKER},?[^(),\n]*\))([^()\n]{{1,60}})\)", re.IGNORECASE)
# "...exceeds a threshold—like a narrow resonance at 3500 Hz—without affecting other moments." The aside stops at
# a sentence end, or "— like one at 2 kHz. Then key it from the kick — not the snare —" ran on to the next
# sentence's dash and took "key it from the kick" with it (the same with ";", ":" and "…" in the 11 Oct review).
# A comma stops it too, except the one straight after the marker that "say, 3 kHz" needs (see the run-on above).
# Brackets, quotes and markdown stars stop it as well, because a step marker "2)",
# a citation or a bold heading inside an aside means we are already in the next step. The one full stop allowed
# is a decimal point between digits, "2.5 kHz", not "Hz.2 key it"; an "e.g." partway in ends the aside, which only
# costs a save. Each dash closes only on its own kind, and never on one with a number straight after it, signed
# or not, because that is the dash inside a range: "— like at 3 kHz or the 200 – 400 Hz —", "the -18 – -6 dBFS".
# An en dash only counts with spaces round it, because unspaced it is the one inside "100–300 Hz".
_ASIDE_BODY = r"(?:[^\n.!?;:…,()\[\]\"“”*]|(?<=\d)\.(?=\d))"
_DASH_EXAMPLE_RE = re.compile(
    rf"[ \t]*—[ \t]*({_EXAMPLE_MARKER},?{_ASIDE_BODY}{{1,80}}?)[ \t]*—(?![ \t]*[-+−]?\d)[ \t]*"
    rf"|[ \t]+–[ \t]+({_EXAMPLE_MARKER},?{_ASIDE_BODY}{{1,80}}?)[ \t]+–(?![ \t]*[-+−]?\d)[ \t]*",
    re.IGNORECASE,
)
# "apply a high-pass filter at around 100 Hz to reduce the effect" is still an instruction without the frequency,
# because a high- or low-pass says what it does on its own. A cut, boost, bell or notch does not: "Boost at 5 kHz."
# would come out as "Boost.", so those keep their figure and go to the sentence drop. Only a frequency introduced
# by at/around/near is cut ("set it to 100 Hz" makes the figure the instruction), and the lookahead stops at the
# next clause so "at 100 Hz by 3 dB", where the place and the amount go together, is left alone. "to" only starts
# a clause when no number follows, hedged or signed: "at 30 Hz to about 40 Hz depending on..." is a range and
# "at 100 Hz to -12 dB per octave" a slope, neither of which we can cut cleanly, so the sentence drop takes them.
# Nor does a clause that limits the figure, "at 100 Hz, but no higher" or "at 100 Hz and not above": without the
# figure it limits nothing. The lookahead only knows those joiners, so the cut also checks the rest of the sentence
# and the start of the next for a bound: "at 100 Hz, max." shipped as "Set the high-pass, max." and "at 100 Hz.
# No higher." left "No higher." pointing at nothing in the fourth review. That check has its own short list rather
# than the aside one, because "under", "if" or "keep" anywhere later in a sentence ("to keep the low end clean")
# is usually about something else. "or so" is on it too: not a bound, but "Set the high-pass or so" says nothing.
# A negated move ("don't high-pass at 100 Hz on the bass") reads wider once its figure goes; none of the 12 runs
# had one, so we have not guarded it.
_PLACED_FIGURE_RE = re.compile(
    r"\b(?P<move>(?:high|low)[- ]?pass(?:[ \t]+filter)?|hpf|lpf)"
    r"(?P<place>[ \t]+(?:at|around|near)[ \t]+(?:(?:around|about|roughly|approximately)[ \t]+)?"
    r"(?:\d+(?:\.\d+)?[ \t]*(?:k?hz)?[ \t]*(?:[–-]|to)[ \t]*)?\d+(?:\.\d+)?[ \t]*k?hz)"
    r"(?![ \t]*,?[ \t]*(?:but|or|and[ \t]+(?:no|not|never)|no|not|never)\b)"
    r"(?=[ \t]+(?:to\b(?![ \t]*(?:(?:around|about|roughly|approximately)[ \t]+)?[-+−]?\d)"
    r"|(?:on|for|in|so|and|with|before|after|if|when|until)\b)"
    r"|[ \t]*[,.;:)\[]|[ \t]*$)",
    re.IGNORECASE | re.MULTILINE,
)
# A decimal point does not end the sentence; the trailing \s* steps over to the start of the next one.
_REST_OF_SENTENCE_RE = re.compile(r"((?:[^.!?\n]|(?<=\d)\.(?=\d))*)[.!?]*\s*")
# "at the very most", "ceiling", "upper limit", "stop there" and the "go" forms ("don't go higher", ". Go no
# higher.") came from the fifth review, each shipping its bound with no figure in front of it.
_BOUND_AFTER_FIGURE_RE = re.compile(
    r"\b(?:max(?:imum)?|min(?:imum)?|at (?:the )?(?:very )?(?:most|least)|tops|or (?:less|lower|more|higher|so)"
    r"|ceiling|(?:upper|lower) limit|stop there"
    r"|(?:no|not|nothing|never)[ \t]+(?:\w+er|above|below|past|beyond|over|under)"
    r"|(?:do(?:n[’']t|[ \t]+not)[ \t]+)?go[ \t]+(?:no[ \t]+)?(?:\w+er|above|below|past|beyond|over|under))\b",
    re.IGNORECASE,
)


def _excise_illustrative_figures(answer: str, unsupported: set[str]) -> str:
    """The answer with every aside or placement that holds an unsupported figure cut out; the rest untouched."""

    def holds_a_refused_figure(phrase: str) -> bool:
        return bool(_measurements(phrase) & unsupported)

    def an_example_to_cut(m: re.Match, aside: str) -> bool:
        figures = list(_MEASUREMENT_RE.finditer(aside))
        return (
            holds_a_refused_figure(aside)
            and bool(figures)
            and figures[-1].end() == len(aside.rstrip())
            and not _LIMIT_WORDS_RE.search(aside)
            and not _JOINS_A_CLAUSE_RE.search(aside)
            # endpos makes "$" in the pattern mean the start of this aside.
            and not _LEADS_INTO_ASIDE_RE.search(m.string, 0, m.start())
        )

    def a_bound_follows(m: re.Match) -> bool:
        # Anywhere in the rest of this sentence, or as the first words of the next one.
        rest = _REST_OF_SENTENCE_RE.match(m.string, m.end())
        return bool(_BOUND_AFTER_FIGURE_RE.search(rest.group(1)) or _BOUND_AFTER_FIGURE_RE.match(m.string, rest.end()))

    def dash_aside(m: re.Match) -> str:
        # Group 1 is an em-dash aside, group 2 a spaced en-dash one; only one of them took part.
        if not an_example_to_cut(m, m.group(1) or m.group(2)):
            return m.group(0)
        # The two dashes stood between words, so one space has to stay, unless punctuation follows.
        follows = m.string[m.end():m.end() + 1]
        return "" if not follows or follows in ",.;:!?)" else " "

    answer = _BRACKET_ASIDE_RE.sub(lambda m: "" if an_example_to_cut(m, m.group(1)) else m.group(0), answer)
    answer = _DASH_EXAMPLE_RE.sub(dash_aside, answer)
    return _PLACED_FIGURE_RE.sub(
        lambda m: m.group("move")
        if holds_a_refused_figure(m.group("place")) and not a_bound_follows(m)
        else m.group(0),
        answer,
    )


def salvage_unsupported_figures(answer: str, unsupported: list[str]) -> str:
    """The answer without the figures the notes lack, or "" if that cannot be done and leave enough answer.

    11 Oct 2026: replayed over the 12 probe runs of 10 Oct, drop_unsupported_sentences saved none of the 32
    answers refused for a figure. 19 had too little left, and the other 13 lost a step or the Check line and fell
    under the quality floor, often when the figure was only an example in brackets or a frequency on a filter move.
    Those asides are cut first; a figure still standing after that takes its sentence with it, as before. The
    caller must validate the result again; this only edits.
    """
    bad = set(unsupported)
    excised = _excise_illustrative_figures(answer, bad)
    left = sorted(_measurements(excised) & bad)
    if not left:
        # Every refused figure sat in an aside. When none was in the text at all (or `unsupported` was empty)
        # nothing changed, and we hand back "" as drop_unsupported_sentences does, so the caller never re-judges
        # an unchanged answer.
        return excised if excised != answer else ""
    # drop_unsupported_sentences measures its kept-share floor against the excised text, not the original, so the
    # asides already cut do not count as loss. With several gone the shipped answer can be well under 60% of what
    # the model wrote (49 of 100 words in one review case on 11 Oct). We accept that: what went first was examples,
    # the floor still guards the steps, and the gate judges the result again.
    return drop_unsupported_sentences(excised, left)


_WHOLE_SENTENCE_RE = re.compile(r".*[.!?](?=\s|$)", re.DOTALL)
# A cut right after "3." (or "Try this: 1.") leaves the marker looking like a finished sentence.
_DANGLING_STEP_RE = re.compile(r"(?:(?<=[.!?\]:])[ \t]+|\n[ \t]*)\d{1,2}[.)]$")


def _cut_to_a_whole_sentence(answer: str) -> str:
    start, _end = _sources_section(answer)
    body, tail = (answer[:start], answer[start:]) if start != -1 else (answer, "")
    body = body.rstrip()
    trimmed = body
    if trimmed and trimmed[-1] not in '.!?)]"':
        split_at = trimmed.rfind("\n") + 1
        marker = _LINE_MARKER_RE.match(trimmed[split_at:])
        lead = marker.end() if marker else 0
        whole = _WHOLE_SENTENCE_RE.match(trimmed[split_at + lead:])
        trimmed = trimmed[: split_at + lead] + whole.group(0) if whole else trimmed[:split_at].rstrip()
    # The last full stop is often the one in "2." of the step the cap cut off, so the marker goes after the cut,
    # and so does a "Try this:" left with no step under it.
    trimmed = _DANGLING_STEP_RE.sub("", trimmed).rstrip()
    last_line = trimmed[trimmed.rfind("\n") + 1:]
    if _HEADING_LINE_RE.match(last_line):
        trimmed = trimmed[: len(trimmed) - len(last_line)].rstrip()
    if trimmed == body:
        return answer
    return f"{trimmed}\n\n{tail}" if tail else trimmed


def end_on_a_whole_sentence(answer: str) -> str:
    """The answer with a half-written last sentence cut off, or the answer itself when it ends cleanly.

    4 Oct 2026: with the 128-token cap 25 of 27 accepted background answers stopped mid-word on their last
    line ("...while having a tighter, more sustained"). The last line goes back to its last full stop, or goes
    altogether when it has none. Nothing is added, so the gate has less to judge, never more; the caller
    still validates the result.
    """
    trimmed = _cut_to_a_whole_sentence(answer)
    if trimmed == answer:
        return answer
    before = len(_prose_without_sources(answer).split())
    after = len(_prose_without_sources(trimmed).split())
    if after < _SALVAGE_MIN_WORDS or after < before * _SALVAGE_MIN_KEPT_SHARE:
        return answer
    return trimmed


def generated_answer_validation(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str,
    answer_mode: str,
    timeline_context: str | None = None,
    additional_evidence_text: str | None = None,
    question: str = "",
) -> dict:
    """Gate generated prose against the same evidence used for retrieval.

    This is deliberately deterministic and provider-independent, so local,
    remote, sync, streaming, and voice generation cannot select different
    standards. Failed generated text is discarded before it reaches a caller.

    `question` is the producer's words this turn, as typed; its figures are accepted in the answer. It is not
    `query`, which is history-expanded on a follow-up (see _accepted_measurements). Left empty, no figure is
    accepted on the question's say-so, which is the stricter gate.
    """
    grounding = grounding_report(
        query,
        results,
        answer,
        route=route,
        confidence=confidence,
        timeline_context=timeline_context,
    )
    quality = answer_quality_report(
        query,
        results,
        answer,
        route=route,
        confidence=confidence,
        answer_mode=answer_mode,
        grounding=grounding,
        timeline_context=timeline_context,
    )
    # Read the evidence list once and hand the same one to every check below, so the measurements, the overlap
    # score and the citation check cannot end up scored against different sets.
    shown = _evidence_chunks(results)
    evidence_text = _gate_evidence_text(shown, timeline_context, additional_evidence_text)
    # The query is deliberately not part of the evidence set. This overlap check answers one question:
    # is the answer built out of the notes we retrieved? Folding the query in would let a model pass by
    # echoing the words of the question back, which is the one thing a synthesised answer always does.
    # Whether the answer engages the question is already covered by `answered_intent` in grounding_report.
    evidence_terms = normalized_terms(evidence_text)
    answer_terms = normalized_terms(_prose_without_sources(answer)) - _STRUCTURE_TERMS
    overlap = (
        len(answer_terms & evidence_terms) / len(answer_terms)
        if answer_terms
        else 0.0
    )
    unsupported_measurements = sorted(
        _unsupported_measurements(
            _measurements(answer),
            _accepted_measurements(question, shown, evidence_text),
        )
    )
    # The labels the model was actually given, so a citation is only fabricated if the filename was not on
    # screen. Derived from the same shown list, not from what retrieval could have supplied.
    displayed_filenames = {
        str(chunk.get("source") or "").lower()
        for _score, chunk, _body in shown
        if chunk.get("source")
    }
    cited_filenames = _cited_source_filenames(answer)
    fabricated_sources = sorted(cited_filenames - displayed_filenames)
    unasked_products = unasked_product_names(answer, query, evidence_text)
    punts_to_sources = _punts_to_sources(answer)
    echoes_prompt = _echoes_prompt_instructions(answer)
    claims_change = claims_live_change(answer)
    # Which shown excerpt each number belongs to, derived rather than asked for, so it holds on the 82% of
    # answers where the model wrote no citation at all; plus whether the model's own tag agreed. Read from the
    # same shown list as the aggregate check above, so a claim can never be placed against a chunk the model
    # never read.
    citations = verify_claim_citations(answer, shown)
    # An abstain is only an abstain if the whole reply is one line that names the gap and asserts no number.
    # "Insufficient context: ... we would want a note on the 48 kHz setting" has already answered, and a reply
    # that carries advice or a Sources list after the line is an answer with a disclaimer, so both go through every
    # check below like any other answer and the prefix costs them nothing. abstain_gap stays the loose reading
    # (what the model said was missing, wherever it said it) so capture rows still show it for those replies.
    abstain_gap = explicit_abstain_gap(answer)
    abstained = bool(whole_reply_abstain_gap(answer)) and not citations["total"]
    warnings = []
    # The eight conditions below are unchanged and keep their order, so route_latency_report.py still groups on
    # the same first warning. The two claim-level conditions are appended after them for the same reason: a report
    # that has been reading these eight buckets for a week should not have them reshuffled underneath it.
    if claims_change:
        warnings.append("generated answer claims it changed the Live set")
    if unsupported_measurements:
        warnings.append("generated answer introduced unsupported measurements")
    if fabricated_sources:
        warnings.append("generated answer cites sources not in the retrieved evidence")
    if punts_to_sources:
        warnings.append("generated answer punts to the sources instead of synthesizing them")
    if echoes_prompt:
        warnings.append("generated answer echoes its own system prompt instructions")
    if len(answer_terms) >= 8 and overlap < 0.16:
        warnings.append("generated answer has insufficient evidence overlap")
    if grounding_mode(grounding) == "weak":
        warnings.append("generated answer has weak grounding")
    if int(quality.get("score", 0) or 0) < ANSWER_QUALITY_MIN_SCORE:
        warnings.append("generated answer is below the quality threshold")
        # Aggregate first: route_latency_report.py groups on the first warning, so specifics ahead would split it.
        warnings.extend(str(w) for w in (quality.get("warnings") or []))
    if citations["fabricated_attributions"]:
        warnings.append(
            "generated answer attributes a measurement to an excerpt that does not contain it"
        )
    if citations["unshown_citations"]:
        warnings.append("generated answer cites an excerpt id that was never shown")
    if unasked_products:
        warnings.append("generated answer names a product that nobody mentioned")
    # A named-gap abstain is a correct refusal, not a failed answer, and it is the one input the eight conditions
    # above do not gate. A single "Insufficient context: <gap>" line has no Short answer section, fewer than two
    # steps and no verification line, so the quality threshold would reject the correct behaviour while the flag
    # records exactly what the model was told it was missing. Grounding and quality are still computed and still
    # returned below, so the branch hides nothing, and it costs nothing in claim coverage: an abstain carries no
    # number by construction, so verify_claim_citations() has nothing to check. A live-change claim is the one
    # thing an abstain is not allowed to excuse — "Insufficient context: ..." next to "I muted the hats" is a
    # false receipt dressed as a refusal, and that is the one rejection in the 29-query runs that was not a number.
    # The two warnings kept below are not about the missing structure: a one-line decline that names a plugin
    # nobody mentioned or a source that was not shown is the model reaching outside the notes, and it is rejected.
    if abstained and not claims_change:
        warnings = [w for w in warnings if w in _ABSTAIN_KEPT_WARNINGS]
    return {
        "accepted": not warnings,
        "warnings": warnings,
        "unsupported_measurements": unsupported_measurements,
        "fabricated_sources": fabricated_sources,
        "unasked_products": unasked_products,
        "punts_to_sources": punts_to_sources,
        "echoes_prompt_instructions": echoes_prompt,
        "claims_live_change": claims_change,
        "evidence_overlap": round(overlap, 3),
        "abstained": abstained,
        "abstain_gap": abstain_gap,
        "claim_citations": citations,
        "grounding": grounding,
        "quality": quality,
    }


MODE_BOUNDARY_REQUIREMENTS = {
    "ableton_steps": {
        "marker": "in live:",
        "terms": ("ableton", "live"),
        "match": "any",
        "warning": "ableton mode lacks Live safety boundary",
    },
    "client_delivery": {
        "marker": "scope boundary:",
        "terms": ("quote", "delivery", "client"),
        "match": "any",
        "warning": "client-delivery mode lacks scope boundary",
    },
    "dialogue_cleanup": {
        "marker": "dialogue check:",
        "terms": ("artifact", "intelligibility", "room tone", "noise"),
        "match": "any",
        "warning": "dialogue-cleanup mode lacks artifact boundary",
    },
    "game_audio_implementation": {
        "marker": "implementation check:",
        "terms": ("memory", "voice", "streaming", "sync", "state"),
        "match": "any",
        "warning": "game-audio mode lacks runtime tradeoff",
    },
    "mastering_safety": {
        "marker": "mastering boundary:",
        "terms": ("loudness", "balance", "true peak"),
        "match": "all",
        "warning": "mastering mode lacks loudness boundary",
    },
    "mix_diagnosis": {
        "marker": ("symptom and likely cause:", "diagnosis first:"),
        "terms": ("matched loudness",),
        "match": "any",
        "warning": "mix-diagnosis mode lacks symptom-first structure",
    },
}


def mode_boundary_requirement_met(answer_mode: str, lowered_answer: str) -> tuple[bool, str]:
    requirement = MODE_BOUNDARY_REQUIREMENTS.get(answer_mode)
    if not requirement:
        return True, ""
    terms = tuple(requirement["terms"])
    markers = requirement["marker"]
    if isinstance(markers, str):
        markers = (markers,)
    if not any(str(marker) in lowered_answer for marker in markers):
        return False, str(requirement["warning"])
    if requirement.get("match") == "all":
        ok = all(term in lowered_answer for term in terms)
    else:
        ok = any(term in lowered_answer for term in terms)
    return ok, "" if ok else str(requirement["warning"])


def answer_quality_report(
    query: str,
    results: list[tuple[float, dict]],
    answer: str,
    *,
    route: str,
    confidence: str,
    answer_mode: str,
    grounding: dict,
    timeline_context: str | None = None,
) -> dict:
    """Cheap deterministic judge for answer shape and grounding."""
    lowered = answer.lower()
    displayed = _evidence_chunks(results)
    numbered_steps = count_actionable_steps(answer)
    sections = {
        "short_answer": any(
            marker in lowered
            for marker in (
                "short answer:",
                "direct solution is:",
                "main recommendation:",
                "recommended production technique:",
                "direct advice:",
                "to address your query directly:",
                "symptom and likely cause:",
                "the concept:",
                "the reasoning:",
                "why this works:",
                "diagnosis first:",
            )
        ),
        "try_this": (
            "try this:" in lowered
            or "try this in your session:" in lowered
            or "try it:" in lowered
            or "to apply this:" in lowered
            or "step-by-step" in lowered
            or "correction steps" in lowered
            or "try this workflow" in lowered
            or "concrete steps" in lowered
            or numbered_steps >= 2
        ),
        "sources": "sources:" in lowered,
        "check": bool(
            re.search(
                r"\b(listening|live|quality|implementation|delivery|dialogue|mastering|revision|understanding|verification)?\s*check:|\bverification:",
                lowered,
            )
        ),
    }
    warnings: list[str] = []
    score = int(grounding.get("score", 0) or 0)
    score = min(score, 82)
    if timeline_context:
        score = 95
    if answer_mode == "studio_dialogue" or route in {"conversation", "production_dialogue"}:
        # Studio dialogue is measured by depth and coherence, not checklist headings
        if len(answer.split()) >= 20:
            score = max(score, 75)
    else:
        if not sections["short_answer"]:
            warnings.append("missing short answer section")
            score -= 10
        if not sections["try_this"]:
            warnings.append("missing steps section")
            score -= 12
        if numbered_steps < 2:
            warnings.append("fewer than two actionable steps")
            score -= 12
        else:
            score += min(numbered_steps, 5) * 2

    # The Sources: section is intentionally hidden unless the user asks for
    # it (chat_answer.py's asks_for_sources() gate, 2026-08-05) -- don't
    # penalize an ordinary answer for correctly omitting it. Duplicated
    # here rather than imported to avoid a circular import (chat_answer.py
    # already imports from this module); keep the term set in sync with
    # chat_answer.asks_for_sources().
    query_asks_for_sources = any(
        term in query.lower()
        for term in (
            "source", "sources", "reference", "references", "citation",
            "citations", "link", "links", "where is this from", "prove", "origin",
        )
    )
    if query_asks_for_sources and not sections["sources"]:
        warnings.append("missing sources section")
        score -= 10
    if not sections["check"]:
        warnings.append("missing verification check")
        score -= 8
    first_move_markers = (
        "first move:",
        "first move in live:",
        "first implementation move:",
        "first mastering move:",
        "first revision move:",
        "first cleanup move:",
        "symptom and likely cause:",
        "here are the steps:",
        "try this in your session:",
    )
    if any(marker in lowered for marker in first_move_markers):
        score += 4
    boundary_ok, boundary_warning = mode_boundary_requirement_met(answer_mode, lowered)
    if boundary_ok and answer_mode in MODE_BOUNDARY_REQUIREMENTS:
        score += 4
    elif boundary_warning:
        warnings.append(boundary_warning)
        score -= 6
    if not displayed and not timeline_context:
        if answer_mode != "studio_dialogue" and route not in {"conversation", "production_dialogue"}:
            warnings.append("no displayed sources")
            score -= 20
    if confidence == "low":

        warnings.append("low confidence")
        score -= 20
    if answer_mode not in ANSWER_MODES:
        warnings.append("unknown answer mode")
        score -= 8
    source_labels = " ".join(source_label(chunk).lower() for _score, chunk, _body in displayed)
    if (
        answer_mode == "ableton_steps"
        and "ableton" not in lowered
        and "live" not in lowered
        and "ableton" not in source_labels
    ):
        warnings.append("ableton mode lacks Ableton/Live grounding")
        score -= 8
    if (
        answer_mode == "mix_review_followup"
        and "mix review" not in lowered
        and not timeline_context
    ):
        warnings.append("mix review mode lacks review context")
        score -= 8
    if answer_mode == "game_audio_implementation" and not any(
        term in lowered for term in ("wwise", "game", "middleware", "engine")
    ):
        warnings.append("game-audio mode lacks implementation context")
        score -= 8
    return {
        "score": max(0, min(100, score)),
        "mode": answer_mode,
        "warnings": warnings,
        "sections": sections,
        "actionable_steps": numbered_steps,
    }


def should_use_llm_rewrite(
    query: str,
    route: str,
    confidence: str,
    grounding: dict,
    quality: dict,
    answer_mode: str,
) -> bool:
    # Deliberately no "trusted context" escape hatch keyed on the query text. A query is producer-supplied,
    # so a prefix in it is a producer-supplied bypass: typing the marker used to switch this on with a weak
    # template answer, before the confidence, grounding and quality checks below. Host-supplied context
    # arrives as `timeline_context`, which is a real argument and cannot be forged from the request body.
    if confidence not in {"high", "medium"}:
        return False
    if route in {"out_of_scope", "clarify", "conversation", "audiogen"}:
        return False
    if grounding_mode(grounding) == "weak":
        return False
    # Lowered threshold: LLM can improve even medium-quality drafts (was 62)
    if int(quality.get("score", 0) or 0) < 50:
        return False
    intent = detect_intent(query)
    # Always rewrite for these modes — they benefit most from polished prose
    if answer_mode in {
        "deep_explanation",
        "mix_review_followup",
        "client_delivery",
        "mix_diagnosis",
        "ableton_steps",
        "studio_dialogue",
    }:
        return True
    if intent in {"why", "explain"}:
        return True
    # Removed the 90-character length gate — short queries also benefit
    return True



def calibrate_answer_for_grounding(answer: str, report: dict) -> str:
    mode = grounding_mode(report)
    if mode == "medium":
        prefix = "Based on the closest local notes, treat this as a practical starting point rather than a final verdict."
        if answer.startswith(prefix):
            return answer
        return f"{prefix}\n\n{answer}"
    return answer


def mode_signature(mode: str, confidence: str = "medium") -> dict[str, str]:
    """Return the opener, tone markers, and distinctive phrasing for each answer mode.

    Each mode has its own 'signature' — the opener label, the kind of language it uses,
    and its distinctive framing. This gives the user a sense of a consistent personality
    that approaches different topics differently.
    """
    signatures = {
        "mix_diagnosis": {
            "opener": "→ Let's trace the symptom.",
            "section_tag": " Diagnosis:",
            "closing": "→ Try that change, then tell me if the symptom shifted or stayed. That tells us what to try next.",
            "confidence_high": "Here is what I would check first:",
            "confidence_medium": "Based on the notes, start here:",
            "confidence_low": "I am matching a few sources — treat this as a starting point:",
        },
        "ableton_steps": {
            "opener": "→ Hands-on. Live workflow:",
            "section_tag": " In Live:",
            "closing": "→ Try it on a duplicate track, then A/B. If this is not what you needed, I can walk through the routing or device setup.",
            "confidence_high": "Here is the exact Ableton setup:",
            "confidence_medium": "The notes suggest this workflow in Live:",
            "confidence_low": "This is what I found in the indexed sources for Live:",
        },
        "client_delivery": {
            "opener": "→ Before you send that file:",
            "section_tag": " Delivery:",
            "closing": "→ Confirm the details with the client before exporting. If they need stems or a specific format, I can help set that up.",
            "confidence_high": "Here is what I would send:",
            "confidence_medium": "Based on the references, check these before sending:",
            "confidence_low": "The sources are thin — verify these with the client:",
        },
        "deep_explanation": {
            "opener": "→ Here is the reasoning behind this.",
            "section_tag": " Why:",
            "closing": "→ Apply the idea to one small element in your session — that will turn the theory into a listening decision.",
            "confidence_high": "The concept works like this:",
            "confidence_medium": "Here is how the technique fits into the session:",
            "confidence_low": "This is what the sources suggest, but test it before depending on it:",
        },
        "dialogue_cleanup": {
            "opener": "→ Cleanup path for dialogue:",
            "section_tag": " Dialogue:",
            "closing": "→ Listen at normal speech level on headphones. The edit should disappear into the track.",
            "confidence_high": "Here is the dialogue chain I would build:",
            "confidence_medium": "Start with these steps for the dialogue:",
            "confidence_low": "Approach this conservatively — the sources are limited:",
        },
        "game_audio_implementation": {
            "opener": "→ Implementation path in middleware:",
            "section_tag": " Implementation:",
            "closing": "→ Test in engine context with repeated triggers and realistic playback levels.",
            "confidence_high": "Here is the implementation route:",
            "confidence_medium": "Based on the notes, start with:",
            "confidence_low": "The indexed sources are limited — verify against engine docs:",
        },
        "mastering_safety": {
            "opener": "→ Mastering checks:",
            "section_tag": " Mastering:",
            "closing": "→ Level-match before/after, check true peak, then listen quietly and on a small speaker.",
            "confidence_high": "Here is the mastering path I would follow:",
            "confidence_medium": "The standards suggest this approach:",
            "confidence_low": "Approach with caution — the sources are limited:",
        },
        "mix_review_followup": {
            "opener": "→ Revision check:",
            "section_tag": " Revision:",
            "closing": "→ Make one focused change, export, and compare against the previous version.",
            "confidence_high": "Based on the review data:",
            "confidence_medium": "The review suggests starting here:",
            "confidence_low": "The review data is limited — trust your ears first:",
        },
        "quick_fix": {
            "opener": "→ Quick move:",
            "section_tag": "",
            "closing": "→ Compare before/after at the same loudness. If this does not help, I can walk through a deeper approach.",
            "confidence_high": "Try this:",
            "confidence_medium": "Based on the notes, try:",
            "confidence_low": "Quick suggestion from the indexed sources — verify it:",
        },
        "studio_dialogue": {
            "opener": "→ In the studio:",
            "section_tag": " Studio Insight:",
            "closing": "→ Trust what your monitors and meters tell you, and let me know if you want to audition a specific move in the session.",
            "confidence_high": "Here is the engineering reality:",
            "confidence_medium": "Based on standard studio practice:",
            "confidence_low": "Here is how to think about this in the session:",
        },
    }
    return signatures.get(mode, signatures["quick_fix"])
