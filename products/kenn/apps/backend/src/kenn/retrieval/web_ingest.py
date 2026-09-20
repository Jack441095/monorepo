"""Fetch public web pages and turn them into draft Ableton training notes.

This does not crawl the whole web. You provide URLs (or a curated pack file).
Content is summarized into draft notes for human review — not pasted verbatim.
"""

from __future__ import annotations

import json
import ipaddress
import re
import socket
import ssl
import time
from html import unescape
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse
from kenn.training.research import (
    NOTES_DIR,
    SOURCES_DIR,
    add_source,
    clean_transcript_text,
    educational_points,
    ensure_files,
    formal_topic,
    now,
    slugify,
    technique_steps,
    top_terms,
    transcript_windows,
)

ROOT = Path(__file__).resolve().parent.parent
WEB_CACHE_DIR = SOURCES_DIR / "web_cache"
WEB_PACK_PATH = SOURCES_DIR / "web_sources.json"
WEB_SUGGESTED_PATH = SOURCES_DIR / "web_sources.suggested.json"
USER_AGENT = "AudioToo-AbletonTipsBot/1.0 (+local research; contact: local)"
FETCH_DELAY_SECONDS = 1.2
MAX_HTML_BYTES = 1_500_000
MIN_TEXT_CHARS = 220
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}

BLOCKED_HOST_SUFFIXES = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "reddit.com",
)

SKIP_PHRASES = (
    "cookie",
    "subscribe",
    "sign up",
    "privacy policy",
    "terms of service",
    "all rights reserved",
)


def is_blocked_url(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return "Invalid URL."
    if not host:
        return "Invalid URL."
    for suffix in BLOCKED_HOST_SUFFIXES:
        if host == suffix or host.endswith(f".{suffix}"):
            return f"Blocked host ({suffix}). Save the page locally or write your own note instead."
    return None


def validate_public_url(url: str) -> str:
    """Reject URLs capable of reaching local, private, or metadata services."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL.") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not supported.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Local or private network URLs are not allowed.")
    if port not in {None, 80, 443}:
        raise ValueError("Only standard HTTP/HTTPS ports are supported.")
    blocked = is_blocked_url(url)
    if blocked:
        raise ValueError(blocked)
    try:
        addresses = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved.") from exc
    if not addresses:
        raise ValueError("URL hostname could not be resolved.")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Local or private network URLs are not allowed.")
    return parsed.geturl()


class PublicOnlyRedirectHandler(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_opener() -> urlrequest.OpenerDirector:
    return urlrequest.build_opener(
        urlrequest.ProxyHandler({}),
        urlrequest.HTTPSHandler(context=ssl_context()),
        PublicOnlyRedirectHandler(),
    )


def read_html_response(response, *, max_bytes: int = MAX_HTML_BYTES) -> tuple[bytes, str]:
    content_type = response.headers.get_content_type().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("URL did not return an HTML document.")
    length_header = response.headers.get("Content-Length", "")
    if length_header:
        try:
            if int(length_header) > max_bytes:
                raise ValueError("Page is too large to process locally.")
        except ValueError as exc:
            if "too large" in str(exc):
                raise
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Page is too large to process locally.")
    return raw, response.headers.get_content_charset() or "utf-8"


def robots_allowed(url: str) -> tuple[bool, str]:
    from urllib.robotparser import RobotFileParser

    validate_public_url(url)
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    try:
        request = urlrequest.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with safe_opener().open(request, timeout=8) as response:
            if response.headers.get_content_type().lower() not in {"text/plain", "text/html"}:
                return True, ""
            raw = response.read(256_001)
            if len(raw) > 256_000:
                return True, ""
        parser.parse(raw.decode("utf-8", errors="replace").splitlines())
        if parser.can_fetch(USER_AGENT, url):
            return True, ""
        return False, f"robots.txt disallows fetching this URL for {USER_AGENT}."
    except (urlerror.URLError, OSError):
        return True, ""


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_html(url: str, timeout: int = 20) -> tuple[str, str]:
    validate_public_url(url)
    allowed, reason = robots_allowed(url)
    if not allowed:
        raise ValueError(reason)

    req = urlrequest.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )
    bounded_timeout = max(1, min(int(timeout), 30))
    with safe_opener().open(req, timeout=bounded_timeout) as response:
        final_url = response.geturl()
        validate_public_url(final_url)
        raw, charset = read_html_response(response)
    return raw.decode(charset, errors="replace"), final_url


def extract_page_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not match:
        return ""
    title = unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
    return re.sub(r"\s+", " ", title).strip()


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)</(p|div|section|article|h[1-6]|li|br|tr|blockquote)>", "\n", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 3:
            continue
        lowered = line.lower()
        if any(phrase in lowered for phrase in SKIP_PHRASES):
            continue
        lines.append(line)
    cleaned = clean_transcript_text("\n".join(lines))
    return cleaned


def default_tags(terms: list[str], extra: str = "") -> str:
    base = ["ableton", "production", "workflow"]
    for term in terms[:8]:
        if term not in base and len(term) > 2:
            base.append(term)
    if extra:
        for part in extra.split(","):
            tag = part.strip().lower()
            if tag and tag not in base:
                base.append(tag)
    return ", ".join(base[:12])


def web_note_template(
    title: str,
    cleaned: str,
    source: dict,
    page_title: str,
    note_type: str = "Web research draft",
    tags: str = "ableton, production",
) -> str:
    terms = top_terms(cleaned)
    topic = formal_topic(terms, title or page_title)
    points = educational_points(cleaned, terms)
    windows = transcript_windows(cleaned, terms, limit=4)
    if windows:
        for window in windows:
            if window not in points:
                points.append(window)
    steps = technique_steps(cleaned) or [
        "Open the source page and confirm the technique still matches your Ableton version.",
        "Recreate the idea in a blank Live Set with one simple sound first.",
        "Rewrite the steps below in your own words before approving this note.",
        "Save any useful settings as a rack or preset if the workflow works for you.",
    ]
    point_text = "\n".join(f"- {point}" for point in points[:8]) or "- Review the cached page and extract the main workflow."
    step_text = "\n".join(f"{index}. {step}" for index, step in enumerate(steps[:6], start=1))
    term_text = ", ".join(terms) or tags
    return f"""# {title}

Type: {note_type}
Tags: {tags}
Status: Draft
Source title: {page_title or source.get('title', '')}
Source creator: {source.get('creator', '')}
Source URL: {source.get('url', '')}
Source ID: {source.get('id', '')}
Web cache: yes

Research reminders:
This draft was generated from a public web page you requested. It is a research summary, not a verbatim copy. Review for accuracy, rewrite in your own words, and approve only if you have the right to use the material.

Short answer:
This lesson focuses on {topic}. Use the source for full context, then keep the final note practical and in your own words.

Key ideas:
{point_text}

Try this:
{step_text}

Why it matters:
Curated web tips expand the local knowledge base, but quality depends on your review. Approved notes are indexed; drafts are not.

Useful terms found:
{term_text}

Personal notes:
Add attribution, version notes (Live 11 vs 12), and anything missing from the page.

Related questions:
- What Ableton devices does this workflow need?
- When should I avoid this technique?
- What should I verify on the original page?
"""


def cache_web_text(url: str, title: str, text: str) -> Path:
    WEB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(title or urlparse(url).path.split("/")[-1] or "web-page")
    path = WEB_CACHE_DIR / f"{slug}.txt"
    suffix = 2
    while path.exists():
        path = WEB_CACHE_DIR / f"{slug}-{suffix}.txt"
        suffix += 1
    header = f"URL: {url}\nFetched: {now()}\nTitle: {title}\n\n"
    path.write_text(header + text, encoding="utf-8")
    return path


def note_exists_for_url(url: str) -> Path | None:
    if not NOTES_DIR.exists():
        return None
    needle = url.strip()
    for note in NOTES_DIR.glob("*.md"):
        try:
            if f"Source URL: {needle}" in note.read_text(encoding="utf-8", errors="replace"):
                return note
        except OSError:
            continue
    return None


def fetch_web_article(
    url: str,
    title: str = "",
    creator: str = "",
    tags: str = "",
    note_type: str = "Web research draft",
    force: bool = False,
) -> dict:
    ensure_files()
    existing_note = note_exists_for_url(url)
    if existing_note and not force:
        return {
            "ok": True,
            "skipped": True,
            "note": existing_note.name,
            "message": f"Note already exists for this URL: {existing_note.name}",
        }

    html, final_url = fetch_html(url)
    page_title = extract_page_title(html)
    cleaned = html_to_text(html)
    if len(cleaned) < MIN_TEXT_CHARS:
        raise ValueError("Could not extract enough readable text from the page.")

    source = add_source(final_url, title or page_title or "Web article", creator, "Imported from web research fetch")
    note_title = title or page_title or "Web Ableton Tip"
    terms = top_terms(cleaned)
    tag_string = tags or default_tags(terms, "tips, workflow")
    cache_web_text(final_url, note_title, cleaned)

    note_path = NOTES_DIR / f"{slugify(note_title)}.md"
    suffix = 2
    while note_path.exists():
        note_path = NOTES_DIR / f"{slugify(note_title)}-{suffix}.md"
        suffix += 1
    note_path.write_text(
        web_note_template(note_title, cleaned, source, page_title, note_type, tag_string),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "skipped": False,
        "url": final_url,
        "source_id": source.get("id"),
        "note": note_path.name,
        "title": note_title,
        "chars": len(cleaned),
        "message": f"Created draft note: {note_path.name}. Review and approve before indexing.",
    }


def load_web_pack() -> list[dict]:
    ensure_files()
    if not WEB_PACK_PATH.exists():
        WEB_PACK_PATH.write_text("[]\n", encoding="utf-8")
    return json.loads(WEB_PACK_PATH.read_text(encoding="utf-8"))


def save_web_pack(entries: list[dict]) -> None:
    WEB_PACK_PATH.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def list_web_pack_entries() -> list[dict]:
    return load_web_pack()


def load_suggested_pack() -> list[dict]:
    if not WEB_SUGGESTED_PATH.exists():
        return []
    return json.loads(WEB_SUGGESTED_PATH.read_text(encoding="utf-8"))


def import_web_pack(limit: int | None = None, force: bool = False, include_suggested: bool = False) -> dict:
    entries = load_web_pack()
    if include_suggested:
        entries = entries + load_suggested_pack()
    if not entries:
        return {"ok": True, "count": 0, "results": [], "message": "No URLs in web_sources.json or web_sources.suggested.json."}

    results: list[dict] = []
    processed = 0
    for entry in entries:
        if limit is not None and processed >= limit:
            break
        url = str(entry.get("url", "")).strip()
        if not url:
            continue
        processed += 1
        if processed > 1:
            time.sleep(FETCH_DELAY_SECONDS)
        try:
            result = fetch_web_article(
                url,
                title=str(entry.get("title", "")),
                creator=str(entry.get("creator", "")),
                tags=str(entry.get("tags", "")),
                note_type=str(entry.get("type", "Web research draft")),
                force=force or str(entry.get("force", "")).lower() in {"1", "true", "yes"},
            )
            result["pack_title"] = entry.get("title", "")
            results.append(result)
        except (ValueError, urlerror.URLError, OSError) as exc:
            results.append({"ok": False, "url": url, "error": str(exc)})

    created = [item for item in results if item.get("ok") and not item.get("skipped")]
    return {
        "ok": True,
        "count": len(created),
        "results": results,
        "message": f"Imported {len(created)} new draft note(s). Review in the control panel or Training_Data_Notes.",
    }
