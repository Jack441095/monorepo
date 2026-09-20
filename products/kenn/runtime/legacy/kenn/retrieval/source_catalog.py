"""Curated PDF and web source recommendations for Ableton training research."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "Training_Data_PDF"
PDF_CATALOG_PATH = ROOT / "Training_Data_Sources" / "pdf_sources.json"
WEB_SUGGESTED_PATH = ROOT / "Training_Data_Sources" / "web_sources.suggested.json"

WORD_RE = re.compile(r"[a-z0-9]{3,}")


def load_pdf_catalog() -> list[dict]:
    if not PDF_CATALOG_PATH.exists():
        return []
    return json.loads(PDF_CATALOG_PATH.read_text(encoding="utf-8"))


def load_web_suggested() -> list[dict]:
    if not WEB_SUGGESTED_PATH.exists():
        return []
    return json.loads(WEB_SUGGESTED_PATH.read_text(encoding="utf-8"))


def installed_pdfs() -> set[str]:
    if not PDF_DIR.exists():
        return set()
    return {path.name for path in PDF_DIR.glob("*.pdf")}


def tokenize(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def score_item(query_tokens: set[str], item: dict) -> int:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("topics", "")),
            str(item.get("tags", "")),
            str(item.get("notes", "")),
            str(item.get("url", "")),
        ]
    ).lower()
    item_tokens = tokenize(haystack)
    return len(query_tokens & item_tokens)


def suggest_sources(query: str, *, limit: int = 8) -> dict:
    query_tokens = tokenize(query)
    if not query_tokens:
        query_tokens = {"ableton", "workflow"}

    pdf_hits: list[tuple[int, dict]] = []
    for entry in load_pdf_catalog():
        score = score_item(query_tokens, entry)
        if score > 0:
            pdf_hits.append((score, entry))
    pdf_hits.sort(key=lambda pair: pair[0], reverse=True)

    web_hits: list[tuple[int, dict]] = []
    for entry in load_web_suggested():
        score = score_item(query_tokens, entry)
        if score > 0:
            web_hits.append((score, entry))
    web_hits.sort(key=lambda pair: pair[0], reverse=True)

    present = installed_pdfs()
    pdfs = []
    for score, entry in pdf_hits[:limit]:
        filename = entry.get("filename", "")
        pdfs.append(
            {
                "score": score,
                "title": entry.get("title"),
                "filename": filename,
                "installed": filename in present if filename else False,
                "how_to_obtain": entry.get("how_to_obtain", ""),
                "license": entry.get("license", ""),
                "priority": entry.get("priority", "medium"),
            }
        )

    articles = []
    for score, entry in web_hits[:limit]:
        articles.append(
            {
                "score": score,
                "title": entry.get("title"),
                "url": entry.get("url"),
                "tags": entry.get("tags", ""),
            }
        )

    return {
        "query": query,
        "pdfs": pdfs,
        "articles": articles,
        "installed_pdfs": sorted(present),
    }


def research_plan(query: str) -> str:
    data = suggest_sources(query)
    lines = [
        f"Research plan for: {query}",
        "",
        "Installed PDFs in Training_Data_PDF/:",
    ]
    if data["installed_pdfs"]:
        for name in data["installed_pdfs"]:
            lines.append(f"- {name}")
    else:
        lines.append("- (none yet)")

    lines.extend(["", "Recommended PDFs to add (download manually, then ./ableton build):"])
    if data["pdfs"]:
        for item in data["pdfs"]:
            status = "installed" if item["installed"] else "missing"
            lines.append(f"- [{status}] {item['title']} → {item['filename']}")
            lines.append(f"    Obtain: {item['how_to_obtain']}")
            lines.append(f"    License: {item['license']} · priority: {item['priority']}")
    else:
        lines.append("- No catalog match. Add entries to pdf_sources.json.")

    lines.extend(["", "Ableton blog articles to import as draft notes:"])
    if data["articles"]:
        for item in data["articles"]:
            lines.append(f"- {item['title']}")
            lines.append(f"    {item['url']}")
            lines.append(f"    ./ableton fetch-web \"{item['url']}\" \"title: {item['title']}\"")
    else:
        lines.append("- No suggested URL match. Add to web_sources.suggested.json.")

    lines.extend(
        [
            "",
            "Workflow:",
            "1. PDFs → copy into KENN/Training_Data_PDF/ → ./ableton build (reference only, noisy).",
            "2. Articles → ./ableton fetch-web <url> → review note → ./ableton approve-note …",
            "3. Your teaching → hand-written Approved note (best for client answers).",
            "4. YouTube → add-source + local .txt transcript → paraphrase-transcript (never scrape YouTube).",
        ]
    )
    return "\n".join(lines)
