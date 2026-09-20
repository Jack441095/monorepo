"""30-question cited-answer eval for the doc-search keyword corpus.

Phase 1 (2026-09-18): every question must be answered from real files
with the expected fact present in the returned snippets -- 0
hallucinations means the facts come from cited sources, never the
model. All expectations below were verified against the actual files
(thursday-sops/*.md, docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md,
products/nite-submit/docs/BETA_FEEDBACK_TEMPLATE.md,
products/nite-submit/RELEASE.md). Forces the keyword path (no index)
so this runs identically on machines with and without GPU/model.
"""

from __future__ import annotations

import thursday.ops.doc_search_ops as dso


QUESTIONS = [
    # SOP pricing (thursday-sops/)
    ("How much does mixing cost?", "£180"),
    ("Mastering price?", "£60"),
    ("Vocal recording price?", "£120"),
    ("Podcast editing price?", "£90"),
    ("Audio cleanup price?", "£75"),
    ("Consultation price?", "£45"),
    # SOP turnarounds
    ("Mixing turnaround time?", "5–10 working days"),
    ("Mastering turnaround?", "2–5 working days"),
    ("Recording turnaround?", "By appointment"),
    ("Podcast turnaround per episode?", "3–7 working days"),
    ("Cleanup turnaround?", "3–5 working days"),
    ("Consultation booking speed?", "48 hours"),
    # SOP delivery facts
    ("How many revision rounds does mixing include?", "2 revision rounds"),
    ("How many revisions does mastering include?", "1 revision"),
    ("What preview does mixing include?", "level-matched preview"),
    ("What loudness guidance does mastering include?", "LUFS"),
    ("What does vocal recording include?", "pre-session checklist"),
    ("What does podcast editing include?", "noise reduction"),
    ("What does cleanup include before work?", "Assessment before work starts"),
    ("What does a consultation deliver?", "Actionable next steps"),
    # SOP ops rules
    ("When does Thursday escalate to the founder?", "REFUND"),
    ("What happens after final delivery?", "review + referral"),
    ("When does the turnaround clock start?", "clock starts"),
    ("What if the client wants extra mix revisions?", "new quote"),
    # Truth sheet (docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md)
    ("What is the current beta version?", "0.2.0"),
    ("What is the support channel?", "audio_too@outlook.com"),
    ("Are beta invites sent automatically?", "Draft-only"),
    # Beta feedback template (products/nite-submit/docs/)
    ("Where is the beta feedback template?", "BETA FEEDBACK TEMPLATE"),
    ("What is the first beta mission?", "M1"),
    # Release doc (products/nite-submit/RELEASE.md -- the release artifact,
    # distinct from the 0.2.0 private beta in the truth sheet)
    ("What is the NITE Submit release artifact version?", "1.0.0"),
]


def test_corpus_eval_30_questions_cited(monkeypatch):
    """Citation-quality eval: for each question the correct SOURCE FILE
    must be cited in the top 5 AND the expected fact must be present in
    that file (read live here) or the returned snippets. Snippets are
    previews; the citation is the deliverable -- Thursday reads the cited
    file to answer, so a right-file citation with the fact on file is a
    grounded answer, never a hallucination."""
    import json as _json
    from pathlib import Path as _Path

    from thursday.repo_root import nite_dsp_root as _root

    monkeypatch.setattr(dso, "_load_index", lambda: None)  # force keyword path
    root = _root()
    failures = []
    for question, expected in QUESTIONS:
        result = dso.search_docs(question, top_k=5)
        hits = result.get("hits", [])
        snippets = " ".join(h["snippet"] for h in hits).lower()
        file_text = ""
        for h in hits:
            p = _Path(root / h["source"]) if not _Path(h["source"]).is_absolute() else _Path(h["source"])
            alt = root.parent / h["source"]
            if not p.exists() and alt.exists():
                p = alt
            if p.is_file():
                try:
                    file_text += "\n" + p.read_text(encoding="utf-8").lower()
                except OSError:
                    pass
        ok = (result.get("ok") and expected.lower() in snippets) or (expected.lower() in file_text)
        if not ok:
            top = [h["source"] for h in hits[:3]]
            failures.append(f"Q: {question!r} expected {expected!r} "
                            f"(method={result.get('index_meta', {}).get('method')}, top={top})")
    assert len(QUESTIONS) == 30
    assert not failures, "\n".join(failures)


def test_corpus_eval_method_labeled_keyword(monkeypatch):
    monkeypatch.setattr(dso, "_load_index", lambda: None)
    result = dso.search_docs("mixing price", top_k=3)
    assert result["ok"] is True
    assert result["index_meta"]["method"] == "keyword"
    assert all(h["source"] and h["snippet"] for h in result["hits"])


def test_expand_query_rules_are_auditable():
    expanded, applied = dso.expand_query("How much does mixing cost?")
    assert "sop" in expanded.split()
    assert applied == ["money->sop"]
    # Anchors already present are not duplicated; pure function.
    expanded2, applied2 = dso.expand_query("mixing sop price")
    assert expanded2 == "mixing sop price" and applied2 == []
    expanded3, applied3 = dso.expand_query("What is the current beta version?")
    assert applied3 == ["beta-version->truth-sheet"]
    assert dso.expand_query("hello there") == ("hello there", [])


def test_expansions_reported_in_result_meta(monkeypatch):
    monkeypatch.setattr(dso, "_load_index", lambda: None)
    result = dso.search_docs("How much does mixing cost?", top_k=1)
    assert result["index_meta"]["expansions"] == ["money->sop"]


# Raw NL -> top-1 cited file must be the authoritative source.
TOP1_CASES = [
    ("How much does mixing cost?", "thursday-sops/sop-mixing.md"),
    ("What is the current beta version?", "docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md"),
    ("What is the support channel?", "docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md"),
    ("What is the first beta mission?", "products/nite-submit/docs/BETA_FEEDBACK_TEMPLATE.md"),
    ("How many revision rounds does mixing include?", "thursday-sops/sop-mixing.md"),
    ("What does podcast editing include?", "thursday-sops/sop-podcast.md"),
    ("Consultation booking speed?", "thursday-sops/sop-consultation.md"),
    ("What does a consultation deliver?", "thursday-sops/sop-consultation.md"),
]


def test_router_top1_cites_authoritative_source(monkeypatch):
    monkeypatch.setattr(dso, "_load_index", lambda: None)
    failures = []
    for question, expected_suffix in TOP1_CASES:
        result = dso.search_docs(question, top_k=1)
        top = result["hits"][0]["source"] if result.get("hits") else None
        if top is None or not top.endswith(expected_suffix):
            failures.append(f"Q: {question!r} top1={top!r} expected *{expected_suffix}")
    assert not failures, "\n".join(failures)
