"""Public, data-backed answers about Audio_Too services (not the studio tips LM)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_PATH = ROOT / "business_knowledge.json"

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "is",
        "it",
        "do",
        "i",
        "my",
        "me",
        "you",
        "we",
        "what",
        "how",
        "much",
        "does",
        "can",
        "about",
        "with",
        "your",
    }
)


def load_knowledge() -> dict:
    if not KNOWLEDGE_PATH.exists():
        raise FileNotFoundError(f"Missing {KNOWLEDGE_PATH.name}")
    return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1}


def score_item(query_tokens: set[str], keywords: list[str], extra_text: str = "") -> float:
    keys = set(keywords) | tokenize(extra_text)
    if not keys or not query_tokens:
        return 0.0
    overlap = query_tokens & keys
    return len(overlap) + 0.25 * sum(1 for term in overlap if len(term) > 5)


def validate_question(payload: dict) -> str:
    if str(payload.get("company_website", "")).strip():
        raise ValueError("Invalid request.")
    question = str(payload.get("question", "")).strip()
    if len(question) < 3:
        raise ValueError("Question must be at least 3 characters.")
    if len(question) > 500:
        raise ValueError("Question must be 500 characters or fewer.")
    return question


def format_offering(item: dict) -> str:
    price = item.get("price_from_gbp")
    price_line = f"From £{int(price)}." if price is not None else ""
    turnaround = str(item.get("turnaround", "")).strip()
    includes = item.get("includes") or []
    lines = [str(item.get("summary", "")).strip(), price_line, f"Turnaround: {turnaround}" if turnaround else ""]
    if includes:
        lines.append("Includes: " + "; ".join(str(x) for x in includes[:4]))
    return "\n".join(line for line in lines if line).strip()


def answer_question(question: str) -> dict:
    data = load_knowledge()
    query_tokens = tokenize(question)
    disclaimer = str(data.get("disclaimer", "")).strip()

    scored: list[tuple[float, str, dict]] = []

    for offering in data.get("offerings", []):
        score = score_item(
            query_tokens,
            list(offering.get("keywords") or []),
            f"{offering.get('name', '')} {offering.get('summary', '')}",
        )
        if score > 0:
            scored.append((score, "offering", offering))

    for faq in data.get("faqs", []):
        score = score_item(
            query_tokens,
            list(faq.get("keywords") or []),
            f"{faq.get('question', '')} {faq.get('answer', '')}",
        )
        if score > 0:
            scored.append((score, "faq", faq))

    scored.sort(key=lambda row: row[0], reverse=True)

    if not scored or scored[0][0] < 1.0:
        return {
            "ok": True,
            "confidence": "low",
            "answer": (
                "I can help with services, indicative pricing, stem handoff, revisions, and turnaround. "
                "Try asking about mixing, mastering, or how to get a quote — or send a project enquiry below."
            ),
            "sources": [],
            "disclaimer": disclaimer,
            "cta": "enquiry",
        }

    best_score, kind, item = scored[0]
    confidence = "high" if best_score >= 2.5 else "medium"

    if kind == "offering":
        title = str(item.get("name", "Service"))
        body = format_offering(item)
        sources = [{"type": "offering", "id": item.get("id"), "title": title}]
    else:
        title = str(item.get("question", "FAQ"))
        body = str(item.get("answer", "")).strip()
        sources = [{"type": "faq", "id": item.get("id"), "title": title}]

    return {
        "ok": True,
        "confidence": confidence,
        "answer": f"{title}\n\n{body}",
        "sources": sources,
        "disclaimer": disclaimer,
        "cta": "enquiry",
    }


def public_catalog() -> dict:
    data = load_knowledge()
    offerings = []
    for item in data.get("offerings", []):
        offerings.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "summary": item.get("summary"),
                "price_from_gbp": item.get("price_from_gbp"),
                "turnaround": item.get("turnaround"),
            }
        )
    return {
        "ok": True,
        "disclaimer": data.get("disclaimer", ""),
        "contact_email": data.get("contact_email", ""),
        "offerings": offerings,
        "suggested_questions": [
            "How much does mixing cost?",
            "How should I send stems?",
            "How many revisions are included?",
            "What turnaround should I expect?",
        ],
    }
