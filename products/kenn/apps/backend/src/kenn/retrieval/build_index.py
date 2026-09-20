#!/usr/bin/env python3
"""Build a local searchable knowledge base from training PDFs and notes.

Indexes Ableton manuals, audio-engineering standards, and other curated PDFs.

This uses only pypdf plus the Python standard library. The search index is a
hybrid BM25 + embedding index (all-MiniLM-L6-v2 for semantic search).
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pypdf import PdfReader

from kenn.retrieval.retrieval import extract_tags, tokenize
from kenn.retrieval.index_store import promote_index

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "Training_Data_PDF"
PDF_CATALOG = ROOT / "Training_Data_Sources" / "pdf_sources.json"
NOTES_DIR = ROOT / "Training_Data_Notes"
INDEX_DIR = ROOT / "data" / "index"
CHUNKS_PATH = INDEX_DIR / "chunks.jsonl"
TERMS_PATH = INDEX_DIR / "terms.json"
INDEX_SCHEMA = "kenn.retrieval_index.v2"


@dataclass
class Chunk:
    id: str
    source: str
    page: int
    text: str
    kind: str = "manual"
    title: str = ""
    section: str = ""
    tags: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    evidence_class: str = ""
    source_creator: str = ""
    source_title: str = ""
    transcript_file: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest_metadata(
    indexed_files: list[tuple[Path, str]], *, include_local_manuals: bool = False,
) -> dict:
    from kenn.retrieval.onnx_embedder import embedding_model_identity

    sources = []
    for path, kind in sorted(indexed_files, key=lambda item: item[0].as_posix()):
        relative = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        sources.append({"path": relative, "kind": kind, "sha256": _sha256(path)})
    return {
        "index_schema": INDEX_SCHEMA,
        "source_manifest": {"count": len(sources), "sources": sources},
        "embedding_model": embedding_model_identity(),
        "parameters": {
            "pdf_chunk_max_words": 220,
            "pdf_chunk_overlap_words": 45,
            "embedding_normalize": True,
            "include_local_manuals": include_local_manuals,
        },
    }


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str, max_words: int = 220, overlap: int = 45) -> list[str]:
    # 1. First, split the page text into logical blocks (paragraphs or list items).
    # Since pypdf page text often has single newlines for line wraps, we reconstruct paragraphs.
    lines = text.splitlines()
    blocks = []
    current_block = []


    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            continue


        # Check if line looks like a header, list item, or metadata line
        is_list_or_header = (
            stripped.startswith(("-", "*", "+", "•")) or
            re.match(r"^\d+[\.\)]", stripped) or # number list like "1." or "1)"
            stripped.isupper() or # header all caps
            len(stripped) < 40 # short line, could be header or end of paragraph
        )


        if is_list_or_header:
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            blocks.append(stripped)
        else:
            current_block.append(stripped)


    if current_block:
        blocks.append(" ".join(current_block))

    # 2. Now we have a list of blocks. Some blocks might still be very long (e.g. a huge paragraph).
    # We split large blocks into sentences to avoid giant blocks.
    sub_blocks = []
    for block in blocks:
        block_words = block.split()
        if len(block_words) <= max_words:
            sub_blocks.append(block)
        else:
            sentences = re.split(r"(?<=[.!?])\s+", block)
            current_sent_group = []
            current_count = 0
            for sent in sentences:
                sent_words = sent.split()
                if not sent_words:
                    continue
                if current_count + len(sent_words) > max_words:
                    if current_sent_group:
                        sub_blocks.append(" ".join(current_sent_group))
                    current_sent_group = [sent]
                    current_count = len(sent_words)
                else:
                    current_sent_group.append(sent)
                    current_count += len(sent_words)
            if current_sent_group:
                sub_blocks.append(" ".join(current_sent_group))

    # 3. Group these sub_blocks into chunks with a sliding window of block-level overlap.
    chunks = []
    if not sub_blocks:
        return []


    current_chunk = []
    current_words = 0


    for block in sub_blocks:
        block_len = len(block.split())
        if not current_chunk:
            current_chunk.append(block)
            current_words = block_len
        elif current_words + block_len <= max_words:
            current_chunk.append(block)
            current_words += block_len
        else:
            chunks.append("\n\n".join(current_chunk))


            # Form the start of the next chunk using overlap blocks from the end of current_chunk
            overlap_blocks = []
            overlap_words = 0
            for prev_block in reversed(current_chunk):
                prev_len = len(prev_block.split())
                if overlap_words + prev_len <= overlap:
                    overlap_blocks.insert(0, prev_block)
                    overlap_words += prev_len
                else:
                    break


            current_chunk = overlap_blocks + [block]
            current_words = overlap_words + block_len


    if current_chunk and (len(" ".join(current_chunk).split()) >= 25 or not chunks):
        chunks.append("\n\n".join(current_chunk))


    return chunks


def note_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def note_status(text: str) -> str:
    for line in text.splitlines()[:20]:
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip().lower()
    return "unmarked"


def should_index_note(text: str) -> bool:
    status = note_status(text)
    return status in {"", "approved", "unmarked"}


def pdf_catalog_meta() -> dict[str, dict]:
    if not PDF_CATALOG.exists():
        return {}
    import json

    meta: dict[str, dict] = {}
    for entry in json.loads(PDF_CATALOG.read_text(encoding="utf-8")):
        filename = (entry.get("filename") or "").strip()
        if filename:
            meta[filename] = entry
    return meta


def should_index_pdf(catalog_entry: dict | None, *, include_local_manuals: bool = False) -> bool:
    """Require an explicit local opt-in for licensed product manuals."""
    entry = catalog_entry or {}
    policy = str(entry.get("index_policy", "index")).strip().lower()
    if policy == "reference_only":
        return False
    if policy == "local_opt_in":
        return include_local_manuals
    return True


def pdf_evidence_class(catalog_entry: dict | None) -> str:
    """Classify only catalog-declared official manuals as authoritative."""
    entry = catalog_entry or {}
    category = str(entry.get("category") or "").strip().lower()
    title_and_tags = f"{entry.get('title') or ''} {entry.get('tags') or ''}".lower()
    if category == "ableton" and "manual" in title_and_tags:
        return "official_ableton_manual"
    return "reference_document"


def iter_pdf_chunks(pdf_path: Path, *, catalog_entry: dict | None = None) -> list[Chunk]:
    entry = catalog_entry or {}
    category = entry.get("category", "reference")
    tag_line = entry.get("tags", "")
    topic_line = entry.get("topics", "")
    display_title = entry.get("title") or pdf_path.stem.replace("-", " ").title()
    evidence_class = pdf_evidence_class(entry)
    reader = PdfReader(str(pdf_path))
    chunks: list[Chunk] = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        for chunk_index, part in enumerate(split_text(text), start=1):
            boosted = (
                f"Category: {category}\nTitle: {display_title}\n"
                f"Tags: {tag_line}\nTopics: {topic_line}\n\n{part}"
            )
            chunks.append(
                Chunk(
                    id=f"{pdf_path.stem}-p{page_index}-c{chunk_index}",
                    source=pdf_path.name,
                    page=page_index,
                    text=boosted,
                    kind="manual",
                    title=display_title,
                    evidence_class=evidence_class,
                )
            )
    return chunks


def section_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    found = False
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if found and parts:
                break
            continue
        if stripped.lower().rstrip(":") == heading.lower().rstrip(":"):
            found = True
            continue
        if found and re.match(
            r"^(short answer|try this|why it matters|common mistakes|when this does not apply|related questions|tags|type|status):",
            stripped,
            re.I,
        ):
            break
        if found:
            parts.append(stripped)
    return "\n".join(parts).strip()


def iter_note_chunks(note_path: Path) -> list[Chunk]:
    raw = clean_text(note_path.read_text(encoding="utf-8"))
    if not should_index_note(raw):
        return []
    title = note_title(raw, note_path.stem.replace("-", " ").title())
    tags = " ".join(sorted(extract_tags(raw)))
    def metadata_value(label: str) -> str:
        match = re.search(rf"^{re.escape(label)}:\s*(.+?)\s*$", raw, flags=re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip() if match and match.group(1).strip() else ""

    source_creator = metadata_value("Source creator")
    source_title = metadata_value("Source title")
    transcript_file = metadata_value("Transcript file")
    evidence = "youtube_transcript" if transcript_file else "curated_kenn_note"
    provenance = ""
    if source_creator or source_title or transcript_file:
        provenance = (
            f"Source creator: {source_creator}\n"
            f"Source title: {source_title}\n"
            f"Transcript file: {transcript_file}\n"
            "Provenance: reviewed producer technique derived from a local transcript; advisory, not official Ableton documentation."
        )
    chunks: list[Chunk] = []
    for index, heading in enumerate(
        ("Short answer", "Try this", "Why it matters", "Common mistakes", "When this does not apply", "Related questions"),
        start=1,
    ):
        body = section_body(raw, heading)
        if not body:
            continue
        chunks.append(
            Chunk(
                id=f"{note_path.stem}-note-{index}",
                source=note_path.name,
                page=0,
                text=f"# {title}\nType: note\nStatus: Approved\nTags: {tags}\n{provenance}\nSection: {heading}\n{heading}:\n{body}",
                kind="note",
                title=title,
                section=heading,
                evidence_class=evidence,
                source_creator=source_creator,
                source_title=source_title,
                transcript_file=transcript_file,
            )
        )
    if chunks:
        return chunks
    return [
        Chunk(
            id=f"{note_path.stem}-note-c1",
            source=note_path.name,
            page=0,
            text=raw,
            kind="note",
            title=title,
            evidence_class=evidence,
            source_creator=source_creator,
            source_title=source_title,
            transcript_file=transcript_file,
        )
    ]


def build_terms(chunks: list[Chunk]) -> dict:
    doc_freq: Counter[str] = Counter()
    term_counts: list[dict[str, int]] = []
    lengths: list[int] = []

    for chunk in chunks:
        boosted_text = chunk.text
        if chunk.kind == "note":
            tags = " ".join(extract_tags(chunk.text))
            section = chunk.section or "note"
            boosted_text = (
                f"{chunk.title} {chunk.title} {tags} {tags} {section} "
                f"practical tip workflow troubleshooting beginner approved {chunk.text}"
            )
        counts = Counter(tokenize(boosted_text))
        term_counts.append(dict(counts))
        lengths.append(sum(counts.values()) or 1)
        doc_freq.update(counts.keys())

    total_docs = len(chunks)
    idf = {
        term: math.log(1 + (total_docs - freq + 0.5) / (freq + 0.5))
        for term, freq in doc_freq.items()
    }
    return {
        "version": 3,
        "total_docs": total_docs,
        "avg_len": sum(lengths) / max(1, len(lengths)),
        "lengths": lengths,
        "term_counts": term_counts,
        "idf": idf,
    }


def build_index(
    pdf_dir: Path = PDF_DIR, notes_dir: Path = NOTES_DIR, *, include_local_manuals: bool = False,
) -> list[Chunk]:
    import os
    # ── Contradiction Verification Pass ──
    try:
        from kenn.knowledge import scan_for_contradictions
        print("Running knowledge contradiction verification pass...")
        open_contradictions = scan_for_contradictions(notes_dir)


        max_allowed = int(os.environ.get("KENN_MAX_CONTRADICTIONS", "50"))
        if len(open_contradictions) > max_allowed:
            print("\n" + "="*80)
            print(f"CRITICAL ERROR: Index rebuild blocked. {len(open_contradictions)} open contradictions detected (limit: {max_allowed}).")
            print("Please resolve contradictions using './ableton resolve-contradiction <id> ...'")
            print("Open Contradictions:")
            for c in open_contradictions[:10]:
                print(f"- [{c['contradiction_id'][:8]}] {c['description']}")
            if len(open_contradictions) > 10:
                print(f"... and {len(open_contradictions) - 10} more.")
            print("="*80 + "\n")
            raise SystemExit(f"Index rebuild blocked due to {len(open_contradictions)} open contradictions.")
        elif open_contradictions:
            print(f"Warning: {len(open_contradictions)} open contradictions detected. Indexing allowed (threshold: {max_allowed}).")
    except SystemExit:
        raise
    except Exception as e:
        print(f"Warning: Contradiction verification scan encountered an error: {e}. Proceeding anyway...")

    pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []
    notes = sorted(notes_dir.glob("*.md")) if notes_dir.exists() else []
    if not pdfs and not notes:
        raise SystemExit(f"No PDFs or notes found in {pdf_dir} or {notes_dir}")

    all_chunks: list[Chunk] = []
    indexed_files: list[tuple[Path, str]] = []
    skipped_notes = 0
    for note in notes:
        print(f"Reading note {note.name}...")
        note_chunks = iter_note_chunks(note)
        if note_chunks:
            print(f"  {len(note_chunks)} chunks")
            indexed_files.append((note, "note"))
        else:
            skipped_notes += 1
            print("  skipped: not approved")
        all_chunks.extend(note_chunks)
    catalog = pdf_catalog_meta()
    skipped_pdfs = 0
    skipped_local_manuals = 0
    for pdf in pdfs:
        entry = catalog.get(pdf.name) or {}
        if not should_index_pdf(entry, include_local_manuals=include_local_manuals):
            skipped_pdfs += 1
            if str(entry.get("index_policy", "")).strip().lower() == "local_opt_in":
                skipped_local_manuals += 1
                print(f"Skipping PDF {pdf.name}: local manual requires --include-local-manuals")
            else:
                print(f"Skipping PDF {pdf.name}: reference-only; use reviewed paraphrased notes")
            continue
        print(f"Reading PDF {pdf.name}...")
        pdf_chunks = iter_pdf_chunks(pdf, catalog_entry=entry)
        print(f"  {len(pdf_chunks)} chunks")
        all_chunks.extend(pdf_chunks)
        if pdf_chunks:
            indexed_files.append((pdf, "manual"))

    if not all_chunks:
        raise SystemExit("No text chunks were extracted. The PDFs may be image-only scans.")

    from kenn.retrieval.retrieval import chunk_topics
    for chunk in all_chunks:
        chunk.tags = sorted(extract_tags(chunk.text))
        chunk.topics = sorted(chunk_topics(asdict(chunk)))

    terms = build_terms(all_chunks)

    # Build embedding index for semantic search.  A BM25-only build is useful
    # on a hot laptop while a GPU rebuild is pending; it remains fully
    # provenance-aware and can be promoted atomically like an embedded build.
    embeddings = None
    skip_embeddings = os.environ.get("KENN_SKIP_EMBEDDINGS", "").strip().lower() in {"1", "true", "yes"}
    if skip_embeddings:
        print("Skipping embedding index (KENN_SKIP_EMBEDDINGS is enabled); using BM25 retrieval.")
    else:
        try:
            print("Building embedding index (all-MiniLM-L6-v2)...")
            from kenn.retrieval.retrieval import embed_chunks
            chunk_dicts = [asdict(c) for c in all_chunks]
            embeddings = embed_chunks(chunk_dicts)
            print(f"  {embeddings.shape[0]} embeddings x {embeddings.shape[1]} dim built")
        except ImportError:
            print("  sentence-transformers not available — skipping embedding index")
        except Exception as exc:
            print(f"  Embedding index failed: {exc} — continuing with BM25 only")

    chunk_dicts = [asdict(chunk) for chunk in all_chunks]
    version_id = promote_index(
        chunk_dicts,
        terms,
        embeddings,
        index_dir=INDEX_DIR,
        manifest_metadata=build_manifest_metadata(indexed_files, include_local_manuals=include_local_manuals),
    )
    from kenn.retrieval.retrieval import unload_embedding_index

    unload_embedding_index()

    old_model = INDEX_DIR / "tfidf.pkl"
    if old_model.exists():
        old_model.unlink()

    print(f"Built index version {version_id} with {len(all_chunks)} chunks")
    print(f"Notes:  {len(notes) - skipped_notes} indexed, {skipped_notes} skipped")
    print(f"PDFs:   {len(pdfs) - skipped_pdfs} indexed, {skipped_pdfs} skipped ({skipped_local_manuals} local manual opt-in)")
    print(f"Index:  {INDEX_DIR / 'versions' / version_id}")
    return all_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Ableton tips local knowledge index")
    parser.add_argument("--pdf-dir", type=Path, default=PDF_DIR, help="Folder containing PDF source files")
    parser.add_argument("--notes-dir", type=Path, default=NOTES_DIR, help="Folder containing markdown notes")
    parser.add_argument(
        "--include-local-manuals", action="store_true",
        help="Index locally held manuals marked local_opt_in; never downloads, copies, or redistributes them.",
    )
    args = parser.parse_args()
    build_index(args.pdf_dir, args.notes_dir, include_local_manuals=args.include_local_manuals)
    try:
        from kenn.core.suggestions import reset_pool_cache

        reset_pool_cache()
    except ImportError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
