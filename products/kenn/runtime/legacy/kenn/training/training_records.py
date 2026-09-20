"""ML-ready record helpers for future KENN classifiers and rerankers.

This module is also the canonical home for KENN's shared JSONL read/write
helpers (``read_jsonl`` / ``write_jsonl`` / ``iter_jsonl_raw``). It was picked
over a standalone ``scripts/`` utility module because it is already the
established shared import target for KENN training tooling on both sides of
the scripts/studio boundary -- see ``scripts/export_kenn_training.py`` and
``scripts/eval/ableton_benchmark.py``, which already import ``write_jsonl``
from here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_features(payload: dict) -> dict:
    sources = payload.get("sources") or []
    top = sources[0] if sources else {}
    return {
        "source_count": len(sources),
        "top_source": str(top.get("source", "")),
        "top_source_label": str(top.get("label", "")),
        "top_source_kind": str(top.get("kind", "")),
        "top_source_score": float(top.get("score", 0) or 0),
        "source_labels": [str(source.get("label", "")) for source in sources[:5]],
        "source_kinds": [str(source.get("kind", "")) for source in sources[:5]],
    }


def answer_record(case: dict, payload: dict, eval_failures: list[str] | None = None) -> dict:
    """Create a stable supervised record from an eval case and answer payload."""
    failures = list(eval_failures or [])
    grounding = payload.get("grounding") or {}
    answer_self_check = payload.get("answer_self_check") or {}
    return {
        "schema": "kenn.answer_record.v1",
        "created_at": iso_now(),
        "case_id": str(case.get("id") or case.get("question") or ""),
        "question": str(case.get("question") or payload.get("question") or ""),
        "expected_topics": list(case.get("topics_must_include") or []),
        "expected_source_terms": list(case.get("source_must_include") or []),
        "route": str(payload.get("route", "")),
        "intent": str(payload.get("intent", "")),
        "topics": list(payload.get("topics") or []),
        "confidence": str(payload.get("confidence", "")),
        "source_quality": str(payload.get("source_quality", "")),
        "intent_guard": str(payload.get("intent_guard", "")),
        "weak_match": bool(payload.get("weak_match")),
        "found": bool(payload.get("found")),
        "used_history": bool(payload.get("used_history")),
        "llm_enhanced": bool(payload.get("llm_enhanced")),
        "answer_chars": len(str(payload.get("answer") or "")),
        "grounding_mode": str(payload.get("grounding_mode", "")),
        "grounding_score": int(grounding.get("score", 0) or 0) if isinstance(grounding, dict) else 0,
        "grounding_warnings": list(grounding.get("warnings") or []) if isinstance(grounding, dict) else [],
        "answer_self_check_score": int(answer_self_check.get("score", 0) or 0) if isinstance(answer_self_check, dict) else 0,
        "answer_self_check_warnings": list(answer_self_check.get("warnings") or []) if isinstance(answer_self_check, dict) else [],
        "eval_passed": not failures,
        "eval_failures": failures,
        **source_features(payload),
    }


def write_jsonl(path: Path, records: list[dict], *, sort_keys: bool = False) -> Path:
    """Write ``records`` to ``path`` as JSON Lines, overwriting any existing file.

    One record per line, UTF-8, real (non-escaped) unicode characters. Pass
    ``sort_keys=True`` for artifacts that get committed or hand-reviewed
    (curated hard negatives, mined candidates, reranker pairs), where stable
    key ordering keeps diffs readable; the default (``False``) preserves
    insertion order, which is what this function's original callers here and
    in ``scripts/export_kenn_training.py`` / ``scripts/eval/ableton_benchmark.py``
    already relied on.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=sort_keys) + "\n")
    return path


class JsonlParseError(ValueError):
    """Raised by :func:`read_jsonl` when a JSONL file has an unparsable line."""


def iter_jsonl_raw(path: Path) -> Iterator[tuple[int, str, dict | None, str | None]]:
    """Low-level line-by-line JSONL scanner shared by every JSONL reader in KENN.

    Yields ``(line_number, raw_line, parsed_row, error)`` for each non-blank
    line in ``path``, in file order, 1-indexed. ``parsed_row`` is ``None`` and
    ``error`` is a short human-readable reason when the line is not valid JSON
    or parses to something other than a JSON object; otherwise ``error`` is
    ``None`` and ``parsed_row`` is the parsed ``dict``. Blank/whitespace-only
    lines are skipped entirely -- that's formatting, not data.

    Yields nothing (not an error) when ``path`` does not exist; callers decide
    whether a missing file matters to them (most treat "no file yet" as "no
    data yet"; ``kenn_validate_hard_negatives.py`` treats it as a hard error
    since a tracked file is expected to exist).

    This generator is the one piece of genuinely duplicated logic across the
    former per-script ``read_jsonl`` copies. What callers *do* with a bad line
    -- raise, count, or collect as a reported error -- is a real behavioral
    difference between call sites and is intentionally left to them; see
    :func:`read_jsonl` for the strict default, and
    ``scripts/eval/kenn_validate_hard_negatives.py`` /
    ``scripts/export_creative_repair_training.py`` for the two call sites that
    deliberately keep a lenient, error-collecting variant because reporting
    malformed rows (rather than crashing on them) is their entire job.
    """
    if not path.exists():
        return
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            parsed = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            yield lineno, raw_line, None, f"invalid JSON: {exc}"
            continue
        if not isinstance(parsed, dict):
            yield lineno, raw_line, None, "row must be a JSON object"
            continue
        yield lineno, raw_line, parsed, None


def read_jsonl(path: Path | None, *, missing_ok: bool = True) -> list[dict]:
    """Canonical strict JSONL reader shared by KENN training/eval tooling.

    This replaces six independent, drifting copies of essentially this
    function (see docs/codebase_scan_12_07.md Section 4.2). Behavior, chosen
    deliberately rather than by majority vote among the old copies:

    - Missing file: returns ``[]`` (when ``missing_ok=True``, the default).
      Most JSONL artifacts here -- benchmark exports, mined hard-negative
      candidates, reranker pair files -- are pipeline outputs that don't
      exist until something has generated them once; a script asking "what
      training data exists so far" should treat "none yet" as an empty
      dataset, not a fatal error. Pass ``missing_ok=False`` when a missing
      file is itself something the caller needs to fail on.
    - Blank/whitespace-only lines: skipped silently. Not a data problem.
    - A malformed line (invalid JSON, or valid JSON that isn't an object):
      RAISES ``JsonlParseError`` naming the file and the exact 1-based line
      number. The copies this replaces disagreed with each other here --
      most silently `continue`d past a bad line (quietly producing a
      dataset with a missing example and no record that it happened),
      one let json.JSONDecodeError propagate uncaught with no file/line
      context attached. Both are worse than failing loudly: a training
      pipeline that silently drops a corrupt example produces a dataset
      that's subtly wrong in a way nobody notices until model quality
      degrades for no visible reason, and an unannotated crash burns time
      figuring out which of several JSONL inputs is the broken one. KENN's
      own retrieval already refuses to guess past a weak match rather than
      quietly degrading; this mirrors that -- a bad line here should stop
      the run and point at exactly where, not corrupt a training run
      silently or crash without saying why.

    Two call sites intentionally do NOT use this strict reader:
    ``kenn_validate_hard_negatives.py`` and
    ``export_creative_repair_training.py`` exist specifically to detect and
    report malformed/reviewable rows as their primary output, not to consume
    clean data -- for them, raising on the first bad line would defeat the
    tool's purpose. They build on the shared :func:`iter_jsonl_raw` scanner
    instead so the actual line-parsing logic still isn't duplicated.
    """
    if path is None or not path.exists():
        if missing_ok:
            return []
        raise FileNotFoundError(f"missing JSONL file: {path}")
    rows: list[dict] = []
    for lineno, _raw_line, parsed, error in iter_jsonl_raw(path):
        if error is not None:
            raise JsonlParseError(f"{path}:{lineno}: {error}")
        rows.append(parsed)  # type: ignore[arg-type]
    return rows
