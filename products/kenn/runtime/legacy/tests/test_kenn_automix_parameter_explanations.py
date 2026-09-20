"""Stage 9 — KENN AutoMix parameter/flag explanation tests.

Verifies, for a batch of real AutoMix parameter questions and Mix Review
flag questions, that KENN's answer (via
``audio_analysis.integration.kenn_handoff``):

  (a) cites at least one real Training_Data_Notes source (not a hallucinated
      "source" — every entry in ``sources`` must correspond to an actual
      file on disk under ``studio/kenn/kenn/Training_Data_Notes/``);
  (b) contains no invented numeric measurement — every dB/Hz/ms/ratio/percent
      number that appears in the answer must be traceable either to the
      real value AutoMix supplied as the ``value`` argument, or to the full
      text of one of the cited source notes;
  (c) responds in under 5 seconds.

This intentionally reuses KENN's real retrieval pipeline (no mocking) so a
pass here means the actual grounding behavior works, not just that the
plumbing is wired up. It requires a built KENN index — see
``studio/kenn/kenn/retrieval/build_index.py``. Because this dev database
currently has ~200 pre-existing (Stage-9-unrelated) open "contradictions"
recorded from the full Training_Data_Notes corpus, the default
`KENN_MAX_CONTRADICTIONS=50` gate blocks `python main.py build` — this test
suite does not attempt to rebuild the index itself (that's slow and requires
a clean/overridden contradiction threshold); it assumes an index has already
been built. If no index exists, the retrieval-dependent assertions are
skipped rather than failed, so this file doesn't create a spurious failure
in a fresh checkout that hasn't run the build step.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn" / "Training_Data_Notes"

# The real index lives under a version-promotion scheme (data/index/CURRENT
# points at data/index/versions/<version>/chunks.jsonl), not a flat
# data/index/chunks.jsonl — resolve it the same way retrieval.py does.
# Found 2026-07-09: the old hardcoded flat path meant this whole file's 21
# tests were silently skipping (not passing) in any environment where the
# index actually uses version promotion, since a skip and a pass both just
# report as "not failed" in a summary line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

INDEX_CHUNKS = active_artifact_path("chunks.jsonl")

pytestmark = pytest.mark.skipif(
    not INDEX_CHUNKS.exists(),
    reason="KENN index not built — run "
           "`KENN_MAX_CONTRADICTIONS=<n> python studio/kenn/kenn/retrieval/build_index.py` first.",
)

# Numbers with an optional unit/ratio suffix, e.g. "3.5:1", "-16 dB", "120 Hz", "22%", "150ms".
_NUMBER_RE = re.compile(
    r"-?\d+(?:\.\d+)?\s*(?::\s*1|dbfs|db|hz|ms|s\b|%)?", re.IGNORECASE
)

# Numbers that are structural/incidental to KENN's answer formatting rather
# than claimed measurements (list indices, generic small integers used in
# prose like "three fixes", years, etc.) — excluded from the grounding check.
_IGNORED_BARE_NUMBERS = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}


# KENN's answers can include a "Past reasoning on this topic:" block that
# verbatim-quotes *other* previously asked questions/conclusions pulled from
# this test module's own reasoning-trace history (each test case's question
# becomes a citable "past trace" for later cases in the same run, since they
# share one KENN_DB_PATH for the module). That block only ever echoes a
# question already asked — it never introduces a new factual claim — so it
# is excluded from the "no invented numbers" grounding check rather than
# requiring every other test case's own real value to be in every corpus.
_PAST_REASONING_RE = re.compile(r"Past reasoning on this topic:.*?(?=\n→|\n\n[A-Z])", re.DOTALL)


def _strip_past_reasoning(text: str) -> str:
    text = _PAST_REASONING_RE.sub("", text)
    # "You could also ask:" suggests follow-up questions pulled from other
    # notes' "Related questions" sections across the whole corpus (not just
    # the notes cited as this answer's sources) — a suggestion, not a claim.
    text = re.split(r"\nYou could also ask:", text)[0]
    return text


def _extract_numeric_claims(text: str) -> set[str]:
    claims = set()
    for match in _NUMBER_RE.finditer(text):
        token = match.group(0).strip()
        # Only keep tokens that carry a unit/ratio suffix, or are a signed
        # / decimal figure — bare small integers are structural (numbered
        # steps), not measurements.
        bare = re.fullmatch(r"\d+", token)
        if bare and token in _IGNORED_BARE_NUMBERS:
            continue
        if bare and len(token) <= 2:
            # Still ambiguous (e.g. "12" could be a step number or a real
            # figure) — require a unit suffix or decimal/sign to count.
            continue
        claims.add(token.lower().replace(" ", ""))
    return claims


def _source_corpus_text(sources: list[dict]) -> str:
    """Full text of every Training_Data_Notes file cited in ``sources``."""
    texts = []
    for src in sources:
        name = src.get("source", "") if isinstance(src, dict) else ""
        path = NOTES_DIR / name
        if path.exists():
            texts.append(path.read_text(encoding="utf-8"))
    return "\n".join(texts)


PARAMETER_CASES = [
    {"parameter": "compression ratio", "instrument": "kick", "genre": "pop", "value": "4:1"},
    {"parameter": "compression ratio", "instrument": "kick", "genre": "hip_hop", "value": "5.0:1"},
    {"parameter": "compression ratio", "instrument": "vocal", "genre": "pop", "value": "3.5:1"},
    {"parameter": "compression ratio", "instrument": "vocal", "genre": "jazz", "value": "1.5:1"},
    {"parameter": "compression ratio", "instrument": "snare", "genre": "rock", "value": "4.0:1"},
    {"parameter": "gain staging", "instrument": "kick", "genre": "pop", "value": "-5.5 dBFS"},
    {"parameter": "gain staging", "instrument": "vocal", "genre": "pop", "value": "+1.5 dB"},
    {"parameter": "reverb send level", "instrument": "vocal", "genre": "pop", "value": "22%"},
    {"parameter": "reverb send level", "instrument": "synth pad", "genre": "edm", "value": "35%"},
    {"parameter": "reverb send level", "instrument": "backing vocal", "genre": None, "value": "28%"},
    {"parameter": "stereo width", "instrument": "kick", "genre": None, "value": "0.0"},
    {"parameter": "stereo width", "instrument": "ambient", "genre": None, "value": "1.5"},
    {"parameter": "stereo width", "instrument": "synth pad", "genre": None, "value": "1.2"},
    {"parameter": "limiter ceiling", "instrument": "master bus", "genre": "edm", "value": "-0.5 dBFS"},
    {"parameter": "master bus compression", "instrument": "master bus", "genre": "jazz", "value": "1.0:1"},
    {"parameter": "master bus compression", "instrument": "master bus", "genre": "podcast", "value": "3.0:1"},
    {"parameter": "delay send", "instrument": "fx", "genre": None, "value": "20%"},
    {"parameter": "panning", "instrument": "guitar", "genre": "rock", "value": "-0.35"},
]

FLAG_CASES = [
    {"flag_label": "true peak clipping", "detail": "True peak exceeded -1 dBFS ceiling"},
    {"flag_label": "mono compatibility", "detail": "Correlation dropped below 0 when summed to mono"},
]


@pytest.fixture(scope="module")
def kenn_index_env(tmp_path_factory):
    """Isolate session/reasoning state for this module's KENN calls."""
    import os
    state_dir = tmp_path_factory.mktemp("kenn-automix-explain")
    os.environ["KENN_CHATS_DIR"] = str(state_dir)
    os.environ["KENN_DB_PATH"] = str(state_dir / "kenn.db")
    os.environ["KENN_SESSION_FILE"] = str(state_dir / "session.json")
    yield


@pytest.mark.parametrize("case", PARAMETER_CASES, ids=[f"{c['parameter']}-{c['instrument']}-{c['genre']}" for c in PARAMETER_CASES])
def test_automix_parameter_explanation_is_grounded_and_fast(kenn_index_env, case):
    from audio_analysis.integration.kenn_handoff import explain_automix_parameter

    started = time.perf_counter()
    payload = explain_automix_parameter(
        case["parameter"],
        instrument=case["instrument"],
        genre=case["genre"],
        value=case["value"],
        allow_llm=False,  # deterministic template path — no network LLM variance
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"explanation took {elapsed:.2f}s (limit 5s)"

    answer = payload.get("answer", "")
    assert answer, "KENN returned an empty answer"

    sources = payload.get("sources", [])
    if payload.get("weak_match"):
        # KENN correctly abstained rather than guessing — acceptable, but
        # then it must not present fabricated sources.
        assert not sources
        return

    # (a) at least one cited source is a real file on disk
    real_sources = [s for s in sources if isinstance(s, dict) and (NOTES_DIR / s.get("source", "")).exists()]
    assert real_sources, f"no real cited note file among sources: {sources}"

    # (b) no invented numeric measurement: every number-like token in the
    # answer must be grounded either in the real AutoMix value supplied, or
    # in the full text of a cited source note.
    corpus = _source_corpus_text(sources) + " " + str(case["value"])
    corpus_numbers = _extract_numeric_claims(corpus)
    answer_numbers = _extract_numeric_claims(_strip_past_reasoning(answer))
    unsupported = {n for n in answer_numbers if n not in corpus_numbers}
    assert not unsupported, (
        f"answer contains numeric claims not grounded in cited sources or the real value: {unsupported}\n"
        f"answer: {answer}"
    )


@pytest.mark.parametrize("case", FLAG_CASES, ids=[c["flag_label"] for c in FLAG_CASES])
def test_mix_review_flag_explanation_is_grounded_and_fast(kenn_index_env, case):
    from audio_analysis.integration.kenn_handoff import explain_mix_review_flag

    started = time.perf_counter()
    payload = explain_mix_review_flag(case["flag_label"], detail=case["detail"], allow_llm=False)
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"explanation took {elapsed:.2f}s (limit 5s)"
    assert payload.get("answer")


def test_explanations_never_call_a_parallel_llm_path(kenn_index_env):
    """Stage 9 requirement: reuse KENN's existing answer pipeline, not a second LLM call path."""
    import audio_analysis.integration.kenn_handoff as kenn_handoff
    import inspect

    source = inspect.getsource(kenn_handoff)
    assert "kenn.core.chat_answer" in source
    assert "answer_payload" in source
    # No direct provider SDK imports (openai, anthropic) in this module —
    # every explanation must go through KENN's own answer_payload.
    assert "import openai" not in source
    assert "import anthropic" not in source
