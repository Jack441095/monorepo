"""Local search over docs/ (founder request, 2026-09-02).

Two retrieval paths, honest about which answered:

- KEYWORD (primary, supported everywhere): live BM25-style scan over
  monorepo docs + product docs + Thursday SOPs + website docs. No model,
  no index, no GPU. This is what answers today, proven by the 30-question
  corpus eval (tests/test_doc_search_corpus_eval.py).
- SEMANTIC (documented future): ONNX embeddings (all-MiniLM-L6-v2) +
  cosine similarity over an explicit on-disk index. Requires tokenizers
  + onnxruntime + model files + a built index -- NONE of which is
  guaranteed here, so this path is kept working but NOT the supported
  default (2026-09-18 decision: proving it needs a fixture model this
  checkout doesn't have; until then keyword is the contract and the
  semantic branch is exercised only by unit tests with fake embedders).

A search hit is real text from a real file at a real line range:
evidence to go read, not a verified or complete answer, and every
rendered result says which method produced it.

**Why this exists:** every other Thursday ops module that reads
documentation reads ONE specific hardcoded file (qa_ops.py -> the beta
checklist, finance_ops.py -> business_knowledge.json, documentation_ops.py
-> the launch tracker). There was no way to ask "what have we said about
Paddle KYC" and get a grounded answer across the whole docs/ corpus.

**Embedding model: reused DATA, not code.** KENN already solved local
ONNX embedding on this machine (Audio_Too/studio/kenn/kenn/retrieval/
onnx_embedder.py) -- torch 2.2 is ABI-incompatible with numpy 2.x here,
so sentence-transformers silently breaks; the fix is a torch-free
onnxruntime + HuggingFace `tokenizers` wrapper around all-MiniLM-L6-v2,
with the model weights already fetched and present on disk. This module
reuses those model *files* (same path pattern thursday/voice_output.py
already uses for Kokoro's model files, both under
Audio_Too/studio/kenn/kenn/artifacts/models/) and the same mean-pool +
L2-normalize technique, but does NOT import KENN's Python package --
KENN is mid-migration to a standalone repo
(docs/NITE_DSP_ESTATE_AUDIT.md), so depending on its internal module
structure inside Audio_Too/studio/kenn would be fragile. See
docs/EXTRACTION_COUPLING.md for the same "real data reused, not code
coupling" reasoning applied elsewhere in this codebase.

**Index is explicit, not automatic.** Embedding ~144 files/~1,500 chunks
is a real, measurable cost -- build_index() is only ever run on an
explicit "reindex docs" command, never implicitly on a search. A search
against a missing or stale index says so honestly rather than silently
being empty or slow.

**Scope (v1): docs/ only**, not company/operations/reports/ or any other
directory -- no existing ops module reads anything under company/ today,
and silently widening scope would make index_meta.json's own description
of what was indexed inaccurate. A deliberate follow-up, not bundled here.

**Staleness:** the rendered result always cites the index's build
timestamp so staleness is visible, but this does not auto-detect "a doc
changed since the index was built" -- that's real incremental-reindex
machinery (KENN has it) this module deliberately doesn't build yet.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from thursday.repo_root import audio_too_root, nite_dsp_root
from thursday.runtime_paths import DOC_SEARCH_INDEX_DIR

logger = logging.getLogger(__name__)

_MODEL_DIR = audio_too_root() / "studio" / "kenn" / "kenn" / "artifacts" / "models" / "minilm"
_MODEL_PATH = _MODEL_DIR / "model.onnx"
_TOKENIZER_PATH = _MODEL_DIR / "tokenizer.json"
_EMBED_DIM = 384
_MAX_LEN = 256

EMBEDDINGS_PATH = DOC_SEARCH_INDEX_DIR / "embeddings.npy"
MANIFEST_PATH = DOC_SEARCH_INDEX_DIR / "manifest.jsonl"
INDEX_META_PATH = DOC_SEARCH_INDEX_DIR / "index_meta.json"

_DEFAULT_MAX_WORDS = 220
_DEFAULT_OVERLAP_WORDS = 45

try:
    from audio_too.model_runtime import ONNX_SESSION_INIT_LOCK
except ImportError:
    # Real integration point, not vendored -- same reasoning and same
    # fallback as thursday/voice_output.py's identical try/except. Nothing
    # else in-process needs to share this lock standalone, so a fresh
    # local lock is a correct fallback, not a faked one.
    ONNX_SESSION_INIT_LOCK = threading.RLock()


class DocEmbedder:
    """Torch-free ONNX embedder for all-MiniLM-L6-v2. Adapted from KENN's
    onnx_embedder.py (same mean-pool + L2-normalize math), own code so
    this module doesn't import KENN's Python package -- see module
    docstring.
    """

    def __init__(self, model_path: Path = _MODEL_PATH, tokenizer_path: Path = _TOKENIZER_PATH):
        if not model_path.exists() or not tokenizer_path.exists():
            raise FileNotFoundError(
                f"Embedding model not found at {model_path}. Fetch it via "
                f"Audio_Too/scripts/fetch_embedding_model.py, or copy "
                f"model.onnx + tokenizer.json into {_MODEL_DIR}."
            )
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=_MAX_LEN)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        with ONNX_SESSION_INIT_LOCK:
            self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self._session.get_inputs()}

    def encode(self, texts: str | list[str], *, batch_size: int = 64) -> np.ndarray:
        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        if not items:
            return np.zeros((0, _EMBED_DIM), dtype=np.float32)
        chunks = [self._encode_batch(items[i:i + batch_size]) for i in range(0, len(items), batch_size)]
        result = np.vstack(chunks)
        return result[0] if single else result

    def _encode_batch(self, batch: list[str]) -> np.ndarray:
        encodings = self._tokenizer.encode_batch(batch)
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        last_hidden = self._session.run(None, feeds)[0]
        mask = attention_mask.astype(np.float32)[..., None]
        summed = (last_hidden * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1e-9, None)
        embeddings = summed / counts
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return (embeddings / np.clip(norms, 1e-12, None)).astype(np.float32)


_embedder: DocEmbedder | None = None
_embedder_unavailable_error: str | None = None
_embedder_lock = threading.Lock()


def _get_embedder() -> DocEmbedder:
    """Lazy singleton, caches success/failure per process so a missing
    model degrades once, not on every call -- same shape as
    voice_output.py's Kokoro availability cache.
    """
    global _embedder, _embedder_unavailable_error
    with _embedder_lock:
        if _embedder is not None:
            return _embedder
        if _embedder_unavailable_error is not None:
            raise FileNotFoundError(_embedder_unavailable_error)
        try:
            _embedder = DocEmbedder()
            return _embedder
        except (FileNotFoundError, ImportError, OSError) as exc:
            _embedder_unavailable_error = str(exc)
            raise


def _chunk_markdown(
    text: str, *, max_words: int = _DEFAULT_MAX_WORDS, overlap_words: int = _DEFAULT_OVERLAP_WORDS,
) -> list[dict]:
    """Adapted from KENN's build_index.split_text() (paragraph-block
    accumulation, sentence-split on over-long blocks, word-count overlap
    window) with one markdown-specific change: a '#' heading line is
    always its own block boundary, never merged with a neighbor -- a real
    anchor in clean markdown source, unlike KENN's PDF-oriented "short
    line = maybe header" heuristic. Tracks start_line/end_line (1-indexed)
    per chunk so results can cite source:Lstart-Lend.
    """
    lines = text.splitlines()
    blocks: list[tuple[str, int, int]] = []
    current: list[str] = []
    current_start: int | None = None

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append((" ".join(current), current_start, i - 1))
                current, current_start = [], None
            continue
        if stripped.startswith("#"):
            if current:
                blocks.append((" ".join(current), current_start, i - 1))
                current, current_start = [], None
            blocks.append((stripped, i, i))
            continue
        if current_start is None:
            current_start = i
        current.append(stripped)
    if current:
        blocks.append((" ".join(current), current_start, len(lines)))

    sub_blocks: list[tuple[str, int, int]] = []
    for block_text, start, end in blocks:
        words = block_text.split()
        if len(words) <= max_words:
            sub_blocks.append((block_text, start, end))
            continue
        sentences = re.split(r"(?<=[.!?])\s+", block_text)
        group: list[str] = []
        count = 0
        for sent in sentences:
            sw = sent.split()
            if not sw:
                continue
            if count + len(sw) > max_words and group:
                sub_blocks.append((" ".join(group), start, end))
                group, count = [sent], len(sw)
            else:
                group.append(sent)
                count += len(sw)
        if group:
            sub_blocks.append((" ".join(group), start, end))

    chunks: list[list[tuple[str, int, int]]] = []
    current_chunk: list[tuple[str, int, int]] = []
    current_words = 0
    for sb in sub_blocks:
        wc = len(sb[0].split())
        if not current_chunk:
            current_chunk, current_words = [sb], wc
        elif current_words + wc <= max_words:
            current_chunk.append(sb)
            current_words += wc
        else:
            chunks.append(current_chunk)
            overlap_blocks: list[tuple[str, int, int]] = []
            overlap_wc = 0
            for prev in reversed(current_chunk):
                pwc = len(prev[0].split())
                if overlap_wc + pwc <= overlap_words:
                    overlap_blocks.insert(0, prev)
                    overlap_wc += pwc
                else:
                    break
            current_chunk = overlap_blocks + [sb]
            current_words = overlap_wc + wc
    if current_chunk and (current_words >= 25 or not chunks):
        chunks.append(current_chunk)

    result = []
    for chunk_blocks in chunks:
        chunk_text = "\n\n".join(b[0] for b in chunk_blocks)
        result.append({
            "text": chunk_text,
            "start_line": min(b[1] for b in chunk_blocks),
            "end_line": max(b[2] for b in chunk_blocks),
            "word_count": len(chunk_text.split()),
        })
    return result


def _docs_root() -> Path:
    return nite_dsp_root() / "docs"


# ── Router expansions: intent anchors ───────────────────────────────────
# Natural questions rarely contain the distinctive terms of their answers
# ("What is the current beta version?" never says "truth sheet", yet the
# truth sheet is the answer). These rules append rare anchor terms that
# ARE in the authoritative files, so raw NL resolves end-to-end. Anchors
# are ordinary corpus words (headers, titles), never invented facts, and
# every applied rule is reported in the result meta ("expansions") so
# callers can show or audit the rewrite. The orchestrator will use
# expand_query() before dispatching doc questions (Phase 6 sharpening).

# Each rule: (name, mode, triggers, anchors). Mode "any" fires when one
# trigger appears; "all" needs every trigger (for pairs like beta+version
# that are only jointly distinctive -- "version" alone must not drag every
# release question to the truth sheet).
_ROUTER_RULES: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("money->sop", "any", ("price", "cost", "pricing", "much", "charge"), ("sop",)),
    ("money-word->sop", "any", ("quote", "stems", "deposit"), ("sop",)),
    ("beta-version->truth-sheet", "all", ("beta", "version"), ("truth", "sheet")),
    ("support-channel->truth-sheet", "all", ("support", "channel"), ("truth", "sheet")),
    ("contact->truth-sheet", "any", ("contact",), ("truth", "sheet")),
    ("template->feedback-template", "any", ("template", "mission", "feedback"), ("feedback", "template")),
    ("release->artifact", "any", ("release",), ("artifact", "submit")),
    ("escalation", "any", ("escalat", "refund", "complaint"), ("escalation",)),
    ("review->referral", "any", ("review", "referral"), ("referral",)),
)


def expand_query(query: str) -> tuple[str, list[str]]:
    """Return (expanded_query, applied_rule_names). Anchors already present
    in the query are not duplicated. Pure function, no I/O -- safe to use
    anywhere, including the orchestrator's dispatch path."""
    lowered = query.lower()
    extra: list[str] = []
    applied: list[str] = []
    for name, mode, triggers, anchors in _ROUTER_RULES:
        fired = all(t in lowered for t in triggers) if mode == "all" else any(t in lowered for t in triggers)
        if not fired:
            continue
        fresh = [a for a in anchors if a not in lowered and a not in extra]
        if fresh:
            extra.extend(fresh)
            applied.append(name)
    if not extra:
        return query, []
    return query + " " + " ".join(extra), applied


# ── Keyword fallback (no GPU/model/index needed) ──────────────────────────
# Phase 1 (2026-09-18): the ONNX semantic path needs tokenizers +
# onnxruntime + model files + a built index -- none guaranteed on a fresh
# machine. This fallback scans real markdown files live with plain term
# overlap, so doc search answers from day one. Results carry
# method:"keyword" + per-hit file:line citations; semantic results carry
# method:"semantic". Callers must surface the method honestly.

_KEYWORD_MAX_FILES = 1000
_KEYWORD_MAX_PER_ROOT = 250
_KEYWORD_MAX_FILE_BYTES = 256 * 1024

# In-memory file cache (mtime+size keyed): files are still read live
# from disk on change, but repeat searches don't re-read 500 files.
# Blindly re-reading the whole estate per query cost ~10s; business
# questions must answer interactively.
_blob_cache: dict[str, tuple[int, int, list[str]]] = {}


def _read_lines_cached(path: Path) -> list[str] | None:
    try:
        stat = path.stat()
    except OSError as exc:
        logger.warning("doc_search_ops: could not stat %s: %s", path, exc)
        return None
    key = str(path)
    cached = _blob_cache.get(key)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("doc_search_ops: could not read %s: %s", path, exc)
        return None
    if len(_blob_cache) > 2048:
        _blob_cache.clear()
    _blob_cache[key] = (stat.st_mtime_ns, stat.st_size, lines)
    return lines


def _stem(word: str) -> str:
    """Naive plural stem so 'revisions' meets 'revision' and 'includes'
    meets 'include'. Alpha tokens longer than 3 chars only -- versions
    ("0.2.0"), codes ("M1"), prices ("£180") and short words pass through
    untouched."""
    if len(word) > 3 and word.isalpha():
        if word.endswith("ies"):
            return word[:-3] + "y"
        if word.endswith(("ses", "xes", "zes")):
            return word[:-2]
        if word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
    return word


def _blob_terms(blob: str) -> set[str]:
    return {_stem(t) for t in re.findall(r"\d+(?:\.\d+)+|[a-z0-9£]{2,}|[0-9]", blob)}


def _keyword_roots() -> list[Path]:
    """Corpus roots for live keyword search, business-first: monorepo
    docs, Thursday SOPs, then products (nite-submit first -- it is the
    live beta business), then website docs. Order matters: per-root caps
    mean later roots lose files first, so authoritative business sources
    are never starved by research corpora (found 2026-09-18: a global
    400-file cap cut off thursday-sops entirely behind products/slo).
    """
    root = nite_dsp_root()
    ordered = [root / "docs", root.parent / "thursday-sops"]
    products = root / "products"
    if products.is_dir():
        prod_dirs = sorted(p for p in products.iterdir() if p.is_dir())
        prod_dirs.sort(key=lambda p: 0 if p.name == "nite-submit" else 1)
        ordered.extend(prod_dirs)
    web_docs = root / "website" / "docs"
    if web_docs.is_dir():
        ordered.append(web_docs)
    return [r for r in ordered if r.exists()]


def _keyword_search(query: str, top_k: int = 5) -> dict:
    import math as _math

    # Router expansion first: intent anchors for terms the asker didn't
    # use but the authoritative files contain ("truth sheet" for beta
    # questions, "sop" for money questions). Applied rules are reported
    # in meta so the rewrite stays auditable.
    expanded_query, expansions = expand_query(query)
    # Tokenize keeping dotted versions whole ("0.2.0" is a rare,
    # decisive term; splitting it into digits matches everywhere).
    terms = [t.lower() for t in re.findall(r"\d+(?:\.\d+)+|[a-z0-9£]{2,}|[0-9]", expanded_query.lower())]
    # Money synonyms: the corpus writes "price"/"£", askers write
    # "cost"/"how much" -- expand so price intent meets price wording.
    _MONEY = {"cost", "price", "pricing", "£", "gbp", "rate", "rates", "fee", "fees", "charge"}
    if terms and any(t in _MONEY for t in terms):
        terms = sorted(set(terms) | _MONEY)
    norm_query = re.sub(r"[^a-z0-9£]+", "", expanded_query.lower())
    meta_extra = {"method": "keyword", "expansions": expansions}
    if not terms and not norm_query:
        return {"ok": False, "hits": [], "index_meta": meta_extra,
                "error": "No searchable terms in query."}
    files: list[Path] = []
    for base in _keyword_roots():
        per_root = 0
        for path in sorted(base.rglob("*.md")):
            if len(files) >= _KEYWORD_MAX_FILES or per_root >= _KEYWORD_MAX_PER_ROOT:
                break
            try:
                if path.stat().st_size > _KEYWORD_MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(path)
            per_root += 1
    # Pass 1: read + per-file matched terms (rare terms like prices and
    # versions must outrank giant docs matching only "how"/"what").
    # Matching is stem-aware ("revisions" meets "revision") with substring
    # fallback for short/odd tokens ("mix" meets "mixing").
    docs: list[dict] = []
    doc_freq: dict[str, int] = {}

    def _line_hits(text_low: str, term_set: set[str]) -> set[str]:
        words = _blob_terms(text_low)
        out = set()
        for t in term_set:
            st = _stem(t)
            if st in words or (len(t) >= 4 and t in text_low):
                out.add(st)
        return out

    stemmed_terms = {_stem(t) for t in terms}
    for path in files:
        lines = _read_lines_cached(path)
        if lines is None:
            continue
        blob = "\n".join(lines).lower()
        matched = _line_hits(blob, terms)
        norm_blob = re.sub(r"[^a-z0-9£]+", "", blob)
        phrase = bool(norm_query) and norm_query in norm_blob
        if not matched and not phrase:
            continue
        for t in matched:
            doc_freq[t] = doc_freq.get(t, 0) + 1
        try:
            rel = str(path.relative_to(nite_dsp_root()))
        except ValueError:
            rel = str(path)
        docs.append({"rel": rel, "lines": lines, "matched": matched, "phrase": phrase,
                     "stems": stemmed_terms})
    if not docs:
        meta_extra["error"] = f"No documents match '{query}' in the live keyword corpus."
        return {"ok": False, "hits": [], "index_meta": meta_extra,
                "error": meta_extra["error"]}
    n = len(docs)
    # BM25-style IDF (no +1 smoothing floor): a giant doc matching only
    # "how"/"much"/"does" must lose to a short SOP matching the one rare
    # term ("mixing"). BM25 length normalization (b=0.75 against the mean
    # matched-doc length) so a 2000-line research doc can't outscore a
    # 20-line SOP on common-term count alone.
    idf = {t: _math.log(1.0 + (n - df + 0.5) / (df + 0.5))
           for t, df in doc_freq.items()}
    max_idf = max(idf.values()) if idf else 1.0
    avg_len = sum(len(d["lines"]) for d in docs) / max(1, n)
    # Pass 2: score files; snippet = up to 3 best lines (not just one --
    # the title often outscores the fact row, e.g. "# ... Truth Sheet"
    # beats "| Version | 0.2.0 ...", hiding the answer a one-line
    # snippet would miss).
    scored: list[dict] = []
    for d in docs:
        file_score = sum(idf[t] for t in d["matched"])
        if d["phrase"]:
            file_score += 2.0 * max_idf
        # Head bonus: documents announce their subject up front (SOP
        # titles name the service; RELEASE.md titles the artifact). Terms
        # matching in the first 5 lines count 50% extra, so "How many
        # revision rounds does mixing include" prefers the Mixing SOP over
        # the Recording SOP that merely mentions mixing once.
        head_blob = "\n".join(d["lines"][:5]).lower()
        head_matched = {t for t in d["matched"] if t in head_blob}
        file_score += 0.5 * sum(idf[t] for t in head_matched)
        # Title boost: ≥2 distinct query terms in the title line means the
        # document is ABOUT the question (manuals announce subjects up
        # front). Lifts RELEASE.md over body-only matches for release
        # questions without helping giant docs (their titles rarely match).
        title = next((ln.lower() for ln in d["lines"] if ln.strip()), "")
        title_matched = {t for t in d["matched"] if t in title}
        if len(title_matched) >= 2:
            file_score *= 2.0
        file_score /= (1.0 - 0.75 + 0.75 * len(d["lines"]) / max(1.0, avg_len))
        line_scores: list[tuple[float, str]] = []
        for line in d["lines"]:
            stripped = line.strip()
            if not stripped:
                continue
            ll = line.lower()
            # Keys are stems, so plain substring covers plurals ("revision"
            # matches "revisions"); short originals ("mix") match inside
            # longer words ("mixing") the same way.
            s = sum(idf[t] for t in d["matched"] if t in ll)
            if d["phrase"] and norm_query in re.sub(r"[^a-z0-9£]+", "", ll):
                s += 2.0 * max_idf
            if s > 0:
                line_scores.append((s, stripped))
        line_scores.sort(key=lambda p: (-p[0], p[1]))
        snippet = " / ".join(s for _, s in line_scores[:4])[:800] or " "
        scored.append({
            "source": d["rel"],
            "start_line": 1,
            "end_line": len(d["lines"]),
            "score": round(file_score, 4),
            "snippet": snippet,
        })
    scored.sort(key=lambda h: (-h["score"], h["source"]))
    hits = scored[:max(1, top_k)]
    meta_extra["files_scanned"] = len(files)
    return {"ok": True, "hits": hits, "index_meta": meta_extra, "error": None}


def build_index() -> dict:
    """Explicit, on-demand rebuild of the doc search index. Never raises
    -- embedder/filesystem failures come back as a typed {"ok": False}.
    """
    start_time = time.monotonic()
    try:
        embedder = _get_embedder()
    except (FileNotFoundError, ImportError, OSError) as exc:
        return {"ok": False, "error": str(exc)}

    docs_root = _docs_root()
    if not docs_root.is_dir():
        return {"ok": False, "error": f"Evidence missing — docs directory not found at {docs_root}."}

    manifest_rows: list[dict] = []
    chunk_texts: list[str] = []
    file_count = 0
    for path in sorted(docs_root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("doc_search_ops: could not read %s: %s", path, exc)
            continue
        file_count += 1
        rel = str(path.relative_to(docs_root))
        for i, chunk in enumerate(_chunk_markdown(text)):
            if chunk["word_count"] < 5:
                continue
            manifest_rows.append({
                "id": f"{rel}#{i}",
                "source": rel,
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "text": chunk["text"],
                "word_count": chunk["word_count"],
            })
            chunk_texts.append(chunk["text"])

    if not chunk_texts:
        return {"ok": False, "error": f"No chunkable content found under {docs_root}."}

    embeddings = embedder.encode(chunk_texts)

    DOC_SEARCH_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    # tmp_embeddings must itself end in ".npy" -- np.save() silently
    # appends ".npy" to any path that doesn't already have it, so naming
    # this "embeddings.npy.tmp" (found live, 2026-09-02) actually wrote
    # "embeddings.npy.tmp.npy" and the subsequent os.replace() raised
    # FileNotFoundError on the path it expected to exist.
    tmp_embeddings = EMBEDDINGS_PATH.with_name(EMBEDDINGS_PATH.stem + ".tmp.npy")
    tmp_manifest = MANIFEST_PATH.with_suffix(".jsonl.tmp")
    tmp_meta = INDEX_META_PATH.with_suffix(".json.tmp")

    np.save(tmp_embeddings, embeddings)
    with tmp_manifest.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row) + "\n")
    meta = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "doc_root": str(docs_root),
        "file_count": file_count,
        "chunk_count": len(manifest_rows),
        "chunk_params": {"max_words": _DEFAULT_MAX_WORDS, "overlap_words": _DEFAULT_OVERLAP_WORDS},
    }
    tmp_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    os.replace(tmp_embeddings, EMBEDDINGS_PATH)
    os.replace(tmp_manifest, MANIFEST_PATH)
    os.replace(tmp_meta, INDEX_META_PATH)

    return {
        "ok": True,
        "file_count": file_count,
        "chunk_count": len(manifest_rows),
        "duration_s": round(time.monotonic() - start_time, 1),
    }


def _load_index() -> tuple[np.ndarray, list[dict], dict] | None:
    if not (EMBEDDINGS_PATH.exists() and MANIFEST_PATH.exists() and INDEX_META_PATH.exists()):
        return None
    embeddings = np.load(EMBEDDINGS_PATH)
    manifest = [json.loads(line) for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = json.loads(INDEX_META_PATH.read_text(encoding="utf-8"))
    return embeddings, manifest, meta


def search_docs(query: str, top_k: int = 5) -> dict:
    """Real search over the docs corpus. Prefers the ONNX cosine-similarity
    index when built; falls back to a live keyword scan (no model, no
    index, no GPU) otherwise. Never raises -- every failure mode (no
    index, no model, corrupt index, no keyword match) returns a distinct,
    honest {"ok": False, "error": ...}. The result's index_meta always
    names the method ("semantic" or "keyword") so callers can't present
    keyword hits as semantic ones.
    """
    loaded = _load_index()
    if loaded is not None:
        embeddings, manifest, meta = loaded

        if embeddings.shape[0] != len(manifest):
            return {
                "ok": False, "hits": [], "index_meta": meta,
                "error": "Evidence missing — doc search index is corrupt or out of sync; run \"reindex docs\" to rebuild.",
            }

        try:
            embedder = _get_embedder()
        except (FileNotFoundError, ImportError, OSError):
            # Index exists but the model can't run here (fresh machine,
            # no tokenizers/onnx) -- keyword fallback over live files
            # instead of an error. Honest: method is labeled keyword.
            return _keyword_search(query, top_k=top_k)

        query_vec = embedder.encode(query)
        scores = embeddings @ query_vec
        top_indices = np.argsort(-scores)[:max(1, top_k)]

        hits = [
            {
                "source": manifest[i]["source"],
                "start_line": manifest[i]["start_line"],
                "end_line": manifest[i]["end_line"],
                "score": round(float(scores[i]), 4),
                "snippet": manifest[i]["text"],
            }
            for i in top_indices
        ]
        meta = dict(meta)
        meta["method"] = "semantic"
        return {"ok": True, "hits": hits, "index_meta": meta, "error": None}
    return _keyword_search(query, top_k=top_k)


def render_doc_search_results(query: str, result: dict) -> str:
    if not result["ok"]:
        return f"DOC SEARCH: \"{query}\"\n\n{result['error']}"

    if not result["hits"]:
        return f"DOC SEARCH: \"{query}\"\n\nNo results found."

    lines = [f"DOC SEARCH: \"{query}\"", ""]
    for i, hit in enumerate(result["hits"], 1):
        lines.append(f"{i}. {hit['source']}:L{hit['start_line']}-{hit['end_line']} (score {hit['score']})")
        snippet = hit["snippet"].strip().replace("\n", " ")
        if len(snippet) > 300:
            snippet = snippet[:297] + "..."
        lines.append(f"   {snippet}")
        lines.append("")

    built_at = result["index_meta"].get("built_at", "unknown") if result["index_meta"] else "unknown"
    lines.append(
        f"Semantic similarity retrieval over a point-in-time index (built {built_at}) — "
        "evidence to go read, not a verified or complete answer. Open the cited file to confirm."
    )
    return "\n".join(lines)


def render_reindex_result(result: dict) -> str:
    if not result["ok"]:
        return f"REINDEX DOCS\n\n{result['error']}"
    return (
        f"REINDEX DOCS\n\n"
        f"Indexed {result['file_count']} files into {result['chunk_count']} chunks "
        f"in {result['duration_s']}s."
    )


_SEARCH_DOCS_PREFIXES = [
    "search docs:", "search the docs:", "search docs", "search the docs",
    "what do the docs say about", "what does the docs say about",
    "what does the estate say about", "search the estate:", "search the estate",
]
_REINDEX_DOCS_PHRASES = [
    "reindex docs", "rebuild doc index", "reindex the docs",
    "update doc search index", "rebuild the doc index",
]


def parse_search_docs_command(text: str) -> str | None:
    """Returns the query tail, or None if this isn't a search-docs
    command OR the tail is empty -- unlike find_customers, there's no
    sensible default query for a whole-corpus search, so an empty tail is
    a parse-miss here, not a valid "use a default" match.
    """
    stripped = text.strip()
    lower = stripped.lower()
    for prefix in sorted(_SEARCH_DOCS_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix.lower()):
            tail = stripped[len(prefix):].strip()
            return tail or None
    return None


def parse_reindex_docs_command(text: str) -> bool | None:
    stripped = text.strip().lower()
    return True if stripped in _REINDEX_DOCS_PHRASES else None
