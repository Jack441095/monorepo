"""Polite, provenance-first crawler for approved audio-production sources.

The default output stores metadata and short extractive summaries only. Raw
pages never enter Git and are only retained when a source explicitly permits
it. This crawler deliberately does not bypass access controls or anti-bot
systems.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .models import DocumentRecord, SourceSpec

USER_AGENT = "KENN-knowledge-ingest/1.0 (+source-aware; contact repository owner)"
SECRET_RE = re.compile(r"(?:BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY|sshpass|srd123456)", re.I)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}")
STOPWORDS = {
    "about", "after", "also", "because", "before", "between", "could",
    "from", "have", "into", "more", "only", "other", "over", "their",
    "there", "these", "they", "this", "through", "using", "when", "with",
    "would", "your",
}


def canonical_url(url: str) -> str:
    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return parsed._replace(scheme=scheme, netloc=host, path=path, fragment="").geturl()


def allowed_url(url: str, source: SourceSpec) -> bool:
    normalized = canonical_url(url)
    return any(normalized.startswith(canonical_url(prefix)) for prefix in source.allowed_prefixes)


def _visible_text(raw_html: str, base_url: str) -> tuple[str, str, list[str]]:
    """Extract title, visible text, and links without requiring bs4."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.I | re.S)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1))).strip() if title_match else ""
    cleaned = re.sub(r"<(script|style|nav|footer|header|noscript|svg)[^>]*>.*?</\1>", " ", raw_html, flags=re.I | re.S)
    links = [html.unescape(urljoin(base_url, href)) for href in re.findall(r"<a[^>]+href=[\"']([^\"']+)", cleaned, re.I)]
    text = re.sub(r"<[^>]+>", " ", cleaned)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text, links


def summarize(text: str, limit: int = 650) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chosen: list[str] = []
    size = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 40:
            continue
        if size + len(sentence) + 1 > limit:
            break
        chosen.append(sentence)
        size += len(sentence) + 1
        if len(chosen) >= 3:
            break
    if chosen:
        return " ".join(chosen)
    return text[:limit].strip()


def concepts(text: str, topics: Iterable[str]) -> list[str]:
    counts: dict[str, int] = {}
    for word in WORD_RE.findall(text.lower()):
        if word in STOPWORDS or len(word) < 4:
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts, key=lambda word: (-counts[word], word))
    result = list(dict.fromkeys([*topics, *ranked[:12]]))
    return result[:20]


def quality_score(title: str, text: str, source: SourceSpec) -> float:
    score = 0.2 * min(len(text) / 4000, 1.0)
    score += 0.2 if title else 0.0
    score += 0.2 if source.tier == 1 else 0.12
    score += 0.2 if source.license != "unknown" else 0.0
    score += 0.2 if len(text.split()) >= 150 else 0.0
    return round(min(score, 1.0), 3)


def load_registry(path: Path) -> list[SourceSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SourceSpec.from_dict(item) for item in payload["sources"]]


def robots_for(url: str, cache: dict[str, RobotFileParser]) -> RobotFileParser:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in cache:
        parser = RobotFileParser(f"{origin}/robots.txt")
        try:
            request = Request(
                f"{origin}/robots.txt",
                headers={"User-Agent": USER_AGENT},
            )
            with urlopen(request, timeout=10.0) as response:
                body = response.read().decode("utf-8", errors="replace")
            parser.parse(body.splitlines())
        except (OSError, URLError, TimeoutError):
            parser.parse([])
        cache[origin] = parser
    return cache[origin]


def fetch(url: str, request_headers: dict[str, str] | None = None, timeout: float = 25.0) -> tuple[int, dict[str, str], bytes]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}
    headers.update(request_headers or {})
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return response.status, {key.lower(): value for key, value in response.headers.items()}, response.read()


def fetch_with_retry(url: str, conditional_headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    """Fetch with bounded retries for transient failures and rate limits."""
    for attempt in range(3):
        try:
            return fetch(url, conditional_headers)
        except HTTPError as exc:
            if exc.code == 304:
                return 304, {key.lower(): value for key, value in exc.headers.items()}, b""
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2.0 ** attempt
            except ValueError:
                delay = 2.0 ** attempt
            time.sleep(min(30.0, max(1.0, delay)))
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(min(15.0, 2.0 ** attempt))
    raise RuntimeError("unreachable retry state")


def load_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_records(output_dir: Path, source: SourceSpec, records: list[dict], state: dict[str, dict[str, object]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{source.source_id}.jsonl"
    source_records: dict[str, dict] = {}
    if out_file.exists():
        for line in out_file.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                source_records[item["canonical_url"]] = item
            except (KeyError, json.JSONDecodeError):
                continue
    for record in records:
        source_records[record["canonical_url"]] = record
    with out_file.open("w", encoding="utf-8") as handle:
        for record in sorted(source_records.values(), key=lambda value: value["canonical_url"]):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest_path = output_dir / "manifest.jsonl"
    merged: dict[tuple[str, str], dict] = {}
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                merged[(item["source_id"], item["canonical_url"])] = item
            except (KeyError, json.JSONDecodeError):
                continue
    for record in records:
        merged[(record["source_id"], record["canonical_url"])] = {
            key: record[key]
            for key in ("source_id", "canonical_url", "content_hash", "license", "retrieved_at", "quality_score", "status")
        }
    with manifest_path.open("w", encoding="utf-8") as handle:
        for item in sorted(merged.values(), key=lambda value: (value["source_id"], value["canonical_url"])):
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    (output_dir / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def crawl(source: SourceSpec, limit: int | None, dry_run: bool, output_dir: Path) -> dict[str, int | str]:
    queue = deque(canonical_url(url) for url in source.seed_urls)
    seen: set[str] = set()
    content_hashes: set[str] = set()
    robots_cache: dict[str, RobotFileParser] = {}
    records: list[dict] = []
    state_path = output_dir / "state.json"
    state = load_state(state_path) if not dry_run else {}
    errors = 0
    blocked = 0
    pages = 0
    blocked_streak = 0
    target = min(limit, source.max_pages) if limit else source.max_pages

    while queue and pages < target:
        url = queue.popleft()
        if url in seen or not allowed_url(url, source):
            continue
        seen.add(url)
        if not robots_for(url, robots_cache).can_fetch(USER_AGENT, url):
            blocked += 1
            blocked_streak += 1
            if blocked_streak >= 3:
                break
            continue
        if pages:
            time.sleep(max(0.5, source.delay_seconds))
        pages += 1
        try:
            conditional = {}
            if url in state:
                if state[url].get("etag"):
                    conditional["If-None-Match"] = state[url]["etag"]
                if state[url].get("last_modified"):
                    conditional["If-Modified-Since"] = state[url]["last_modified"]
            status, headers, body = fetch_with_retry(url, conditional)
            if status == 304:
                blocked_streak = 0
                for cached_link in state.get(url, {}).get("links", []):
                    candidate = canonical_url(cached_link)
                    if allowed_url(candidate, source) and candidate not in seen:
                        queue.append(candidate)
                continue
            if status in {403, 429}:
                blocked += 1
                blocked_streak += 1
                if blocked_streak >= 3:
                    break
                continue
            blocked_streak = 0
            content_type = headers.get("content-type", "")
            if "html" not in content_type and not url.endswith("/"):
                continue
            raw = body.decode("utf-8", errors="replace")
            if SECRET_RE.search(raw):
                errors += 1
                continue
            title, text, links = _visible_text(raw, url)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in content_hashes or len(text) < 120:
                continue
            content_hashes.add(digest)
            discovered_links: list[str] = []
            state[url] = {
                "etag": headers.get("etag", ""),
                "last_modified": headers.get("last-modified", ""),
                "content_hash": digest,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "links": discovered_links,
            }
            record = DocumentRecord(
                source_id=source.source_id,
                canonical_url=url,
                title=title or url,
                publisher=source.publisher,
                source_tier=source.tier,
                license=source.license,
                terms_url=source.terms_url,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                published_at=None,
                content_hash=digest,
                language="en",
                topics=[source.source_id],
                summary=summarize(text),
                key_concepts=concepts(text, [source.source_id]),
                citations=[url],
                raw_storage_allowed=source.raw_storage_allowed,
                quality_score=quality_score(title, text, source),
                text_chars=len(text),
            )
            records.append(record.as_dict())
            if source.follow_links:
                for link in links:
                    candidate = canonical_url(link)
                    if allowed_url(candidate, source) and candidate not in seen:
                        discovered_links.append(candidate)
                        queue.append(candidate)
        except HTTPError as exc:
            if exc.code in {403, 429}:
                blocked += 1
                blocked_streak += 1
                if blocked_streak >= 3:
                    break
            else:
                errors += 1
        except (URLError, TimeoutError, UnicodeError, OSError):
            errors += 1

    if not dry_run:
        write_records(output_dir, source, records, state)

    return {"source_id": source.source_id, "pages_attempted": pages, "accepted": len(records), "blocked": blocked, "errors": errors, "queued_remaining": len(queue), "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path(__file__).with_name("registry.json"))
    parser.add_argument("--source", action="append", help="source_id to crawl; repeatable")
    parser.add_argument("--limit", type=int, help="maximum pages per source for a pilot")
    parser.add_argument("--dry-run", action="store_true", help="fetch and score without writing records")
    parser.add_argument("--output-dir", type=Path, default=Path("local_data/knowledge_ingest"))
    args = parser.parse_args(argv)
    sources = load_registry(args.registry)
    if args.source:
        wanted = set(args.source)
        sources = [source for source in sources if source.source_id in wanted]
        if not sources:
            parser.error("no requested source_id exists in the registry")
    results = [crawl(source, args.limit, args.dry_run, args.output_dir) for source in sources]
    print(json.dumps({"sources": results}, indent=2))
    return 0 if all(result["errors"] == 0 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
