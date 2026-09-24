"""Shared query parsing and ranking helpers for the Audio Engineering LM.

Hybrid retrieval: BM25 keyword search + embedding-based semantic search
using a local sentence-transformer model (all-MiniLM-L6-v2, 384 dim).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from kenn.retrieval.index_store import active_artifact_path, active_version_dir, active_version_id, promote_index

WORD_RE = re.compile(r"[a-zA-Z0-9_+#.-]{2,}")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HARD_NEGATIVES_PATH = ROOT / "artifacts" / "training" / "kenn_hard_negatives.jsonl"
HARD_NEGATIVES_PATH = DEFAULT_HARD_NEGATIVES_PATH
CURATED_HARD_NEGATIVES_PATH = ROOT / "evals" / "curated_hard_negatives.jsonl"


# ---------------------------------------------------------------------------
# Hybrid embedding retrieval (sentence-transformers, 384 dim)
# ---------------------------------------------------------------------------

INDEX_DIR = Path(__file__).resolve().parent.parent / "data" / "index"
EMBEDDINGS_PATH = INDEX_DIR / "embeddings.npy"

_embedding_model = None
_embedding_model_error: str | None = None
_embedding_index: np.ndarray | None = None  # shape (num_chunks, 384)
_embedding_index_version: str = ""
_embedding_index_error: str | None = None
logger = logging.getLogger(__name__)


def _get_embedding_model():
    """Lazy-load the embedding model without requiring network access.

    KENN is offline-first. By default SentenceTransformer may only use files
    already present in the Hugging Face cache. Set
    ``KENN_ALLOW_MODEL_DOWNLOAD=1`` explicitly when a download is intended.
    A failed load is cached so every query does not repeat a slow model probe.
    """
    global _embedding_model, _embedding_model_error
    if _embedding_model is None:
        if _embedding_model_error:
            raise RuntimeError(_embedding_model_error)
        try:
            # Torch-free ONNX backend (see onnx_embedder.py). sentence-transformers
            # pulls in Torch, which is ABI-incompatible with NumPy 2.x on this
            # platform and silently disabled the whole embedding path.
            from .onnx_embedder import OnnxEmbedder

            _embedding_model = OnnxEmbedder()
        except Exception as exc:
            _embedding_model_error = f"Embedding model unavailable: {exc}"
            raise RuntimeError(_embedding_model_error) from exc
    return _embedding_model


def reset_embedding_model() -> None:
    """Clear the cached embedding model/load failure (primarily for rebuilds/tests)."""
    global _embedding_model, _embedding_model_error
    _embedding_model = None
    _embedding_model_error = None


def load_embedding_index() -> np.ndarray | None:
    """Load the pre-computed embedding matrix from disk."""
    global _embedding_index, _embedding_index_version, _embedding_index_error
    if _embedding_index is not None:
        return _embedding_index
    version_id = active_version_id(INDEX_DIR)
    embeddings_path = active_artifact_path("embeddings.npy", INDEX_DIR)
    if not embeddings_path.exists():
        _embedding_index_error = f"embedding index does not exist: {embeddings_path}"
        logger.warning(
            "%s; retrieval mode is explicitly BM25-only until the index is rebuilt",
            _embedding_index_error,
        )
        _embedding_index = None
        _embedding_index_version = version_id
        return None
    try:
        _embedding_index = np.load(str(embeddings_path), allow_pickle=False)
        _embedding_index_version = version_id
        _embedding_index_error = None
    except Exception as exc:
        _embedding_index_error = f"embedding index failed to load: {exc!r}"
        logger.warning(
            "%s; retrieval mode is explicitly BM25-only until the index is repaired",
            _embedding_index_error,
        )
        return None
    return _embedding_index


def unload_embedding_index() -> None:
    """Free the embedding index from memory (e.g. after index rebuild)."""
    global _embedding_index, _embedding_index_version, _embedding_index_error
    _embedding_index = None
    _embedding_index_version = ""
    _embedding_index_error = None


def retrieval_status(index_dir: Path | None = None) -> dict:
    """Return a side-effect-free description of the effective retrieval mode.

    The status deliberately does not load the embedding model. A semantic
    index on disk is only a configured capability; hybrid retrieval is marked
    active after both the index and model have actually loaded in this
    process. This prevents health responses from claiming semantic retrieval
    merely because a filename exists.
    """
    selected_dir = Path(index_dir) if index_dir is not None else INDEX_DIR
    version_dir = active_version_dir(selected_dir)
    artifact_dir = version_dir or selected_dir
    chunks_path = artifact_dir / "chunks.jsonl"
    terms_path = artifact_dir / "terms.json"
    embeddings_path = artifact_dir / "embeddings.npy"
    lexical_available = chunks_path.is_file() and terms_path.is_file()
    semantic_index_available = embeddings_path.is_file()

    if not lexical_available:
        active_mode = "unavailable"
        fallback_reason = "lexical_index_missing"
    elif not semantic_index_available:
        active_mode = "bm25_only"
        fallback_reason = "embedding_index_missing"
    elif _embedding_index_error:
        active_mode = "bm25_only"
        fallback_reason = "embedding_index_load_failed"
    elif _embedding_model_error:
        active_mode = "bm25_only"
        fallback_reason = "embedding_model_unavailable"
    elif _embedding_index is not None and _embedding_model is not None:
        active_mode = "hybrid"
        fallback_reason = None
    else:
        active_mode = "bm25_only"
        fallback_reason = "semantic_runtime_not_warmed"

    return {
        "schema": "kenn.retrieval_status.v1",
        "available": lexical_available,
        "active_mode": active_mode,
        "configured_mode": "hybrid" if semantic_index_available else "bm25_only",
        "lexical_index_available": lexical_available,
        "semantic_index_available": semantic_index_available,
        "semantic_model_state": (
            "ready"
            if _embedding_model is not None
            else "unavailable"
            if _embedding_model_error
            else "not_loaded"
        ),
        "degraded": active_mode != "hybrid",
        "fallback_reason": fallback_reason,
        "index_version": version_dir.name if version_dir is not None else "legacy",
    }


def update_embedding_index(new_chunks: list[dict]) -> np.ndarray:
    """Incrementally update the embedding index with new chunks.

    Computes embeddings for the new chunks and appends them to the existing
    index on disk. Much faster than a full rebuild for a single note addition.

    Args:
        new_chunks: List of chunk dicts (with 'title', 'source', 'text', 'id').

    Returns:
        The updated full embedding matrix.
    """
    chunks_path = active_artifact_path("chunks.jsonl", INDEX_DIR)
    current_chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    known_ids = {str(chunk.get("id") or "") for chunk in current_chunks}
    appended = [chunk for chunk in new_chunks if str(chunk.get("id") or "") not in known_ids]
    all_chunks = [*current_chunks, *appended]
    existing = load_embedding_index()
    existing_count = int(existing.shape[0]) if existing is not None else 0
    if existing_count > len(all_chunks):
        raise ValueError("Embedding index has more rows than the active chunk bundle.")
    missing_chunks = all_chunks[existing_count:]
    if missing_chunks:
        missing_embeddings = embed_chunks(missing_chunks, batch_size=32)
        updated = (
            np.concatenate([existing, missing_embeddings], axis=0)
            if existing is not None
            else missing_embeddings
        )
    elif existing is not None:
        updated = existing
    else:
        updated = embed_chunks(all_chunks)

    from kenn.retrieval.build_index import Chunk, build_terms

    fields = set(Chunk.__dataclass_fields__)
    typed_chunks = [
        Chunk(**{key: value for key, value in chunk.items() if key in fields})
        for chunk in all_chunks
    ]
    terms = build_terms(typed_chunks)
    promote_index(all_chunks, terms, updated, index_dir=INDEX_DIR)
    unload_embedding_index()
    return updated


def embed_text(text: str) -> np.ndarray:
    """Embed a single query string into a 384-dim vector."""
    return _get_embedding_model().encode(text, normalize_embeddings=True)


def embed_chunks(chunks: list[dict], *, batch_size: int = 128) -> np.ndarray:
    """Embed a list of chunk dicts using their 'text' field.

    Returns a (num_chunks, 384) float32 numpy array.
    """
    model = _get_embedding_model()
    texts = [
        " ".join([
            str(chunk.get("title", "")),
            str(chunk.get("source", "")),
            str(chunk.get("text", "")),
        ])
        for chunk in chunks
    ]
    all_embs: list[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_embs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_embs.append(batch_embs)
    return np.concatenate(all_embs, axis=0).astype(np.float32)


def save_embedding_index(embeddings: np.ndarray) -> None:
    """Promote embeddings together with matching chunks, terms, and metadata."""
    chunks_path = active_artifact_path("chunks.jsonl", INDEX_DIR)
    terms_path = active_artifact_path("terms.json", INDEX_DIR)
    chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    terms = json.loads(terms_path.read_text(encoding="utf-8"))
    manifest_metadata = None
    current_dir = active_version_dir(INDEX_DIR)
    if current_dir is not None:
        try:
            manifest = json.loads((current_dir / "manifest.json").read_text(encoding="utf-8"))
            build_metadata = manifest.get("build")
            if isinstance(build_metadata, dict):
                manifest_metadata = build_metadata
        except (OSError, json.JSONDecodeError):
            manifest_metadata = None
    # The embeddings come from the model on disk now, not from whatever was
    # present when the BM25 build ran (a BM25-only build records blank hashes).
    from kenn.retrieval.onnx_embedder import embedding_model_identity

    manifest_metadata = {**(manifest_metadata or {}), "embedding_model": embedding_model_identity()}
    promote_index(chunks, terms, embeddings, index_dir=INDEX_DIR, manifest_metadata=manifest_metadata)
    global _embedding_index, _embedding_index_version
    _embedding_index = embeddings
    _embedding_index_version = active_version_id(INDEX_DIR)


def cosine_similarity_scores(query_emb: np.ndarray, index: np.ndarray) -> np.ndarray:
    """Cosine similarity = dot product for L2-normalised vectors."""
    return np.dot(index, query_emb)

def hybrid_search(
    query: str,
    chunks: list[dict],
    terms: dict,
    limit: int = 8,
    *,
    embedding_index: np.ndarray | None = None,
) -> list[tuple[float, dict]]:
    """Hybrid search: BM25 scores boosted by embedding cosine similarity.

    Embedding cosine similarity adds a boost to the raw BM25 scores so the
    score magnitude stays comparable (MIN_RELEVANT_SCORE = 4.0 still works).

    Falls back to pure BM25 if no embedding index is available.
    """
    bm25_results = bm25_search(query, chunks, terms, limit=max(limit * 3, 60), rerank=False)
    if not bm25_results:
        return []

    emb_index = embedding_index if embedding_index is not None else load_embedding_index()
    if emb_index is None:
        # load_embedding_index() already warns on the specific cause
        # (missing file vs. load failure) -- nothing new to say here.
        return bm25_results[:limit]
    if emb_index.shape[0] != len(chunks):
        print(f"WARNING: embedding index has {emb_index.shape[0]} rows but {len(chunks)} chunks are "
              f"loaded (stale/mismatched index version?) -- falling back to BM25-only for this query")
        return bm25_results[:limit]

    try:
        query_emb = embed_text(query)
    except Exception as exc:
        # A precomputed index can exist on a machine that does not currently
        # have the model cached. Retrieval must still work via local BM25.
        print(f"WARNING: embed_text failed ({exc!r}) -- falling back to BM25-only for this query")
        return bm25_results[:limit]
    cosine_scores = cosine_similarity_scores(query_emb, emb_index)

    # 3.5 Query-dependent hybrid weights & per-query normalisation
    query_terms = expanded_query_terms(query)
    idf = terms.get("idf", {})
    query_idfs = [float(idf.get(t, 0.0)) for t in query_terms if t in idf]
    max_query_idf = max(query_idfs) if query_idfs else 0.0
    is_rare_query = max_query_idf > 4.5

    # Scale embedding boost relative to BM25 score magnitude
    bm25_top_score = bm25_results[0][0]


    # Generic queries get more embedding weight; specific rare queries get damped embedding boost
    emb_factor = 0.40 if not is_rare_query else 0.18
    emb_weight = max(emb_factor * bm25_top_score, 3.0)

    chunk_id_to_idx = {chunk.get("id", ""): i for i, chunk in enumerate(chunks)}

    bm25_scores_dict: dict[int, float] = {}
    for score, chunk in bm25_results:
        chunk_idx = chunk_id_to_idx.get(chunk.get("id", ""))
        if chunk_idx is not None:
            bm25_scores_dict[chunk_idx] = score

    # Also check cosine-top candidates that BM25 might have missed
    top_cos_indices = set(np.argsort(-cosine_scores)[:limit * 2].tolist())
    for idx in top_cos_indices:
        if idx not in bm25_scores_dict:
            # Give a baseline BM25 proxy score
            bm25_scores_dict[idx] = bm25_top_score * 0.08

    # Normalise cosine scores to [0, 1] for hybrid fusion
    cos_min, cos_max = float(cosine_scores.min()), float(cosine_scores.max())
    cos_range = cos_max - cos_min if cos_max > cos_min else 1.0
    cos_norm = (cosine_scores - cos_min) / cos_range

    hybrid_scores: list[tuple[float, int]] = []
    for chunk_idx, bm25_score in bm25_scores_dict.items():
        cos_score = float(cos_norm[chunk_idx])
        # Embedding adds up to ~20% boost to BM25 score
        boosted = bm25_score + (emb_weight * cos_score * 0.25)
        hybrid_scores.append((boosted, chunk_idx))

    hybrid_scores.sort(reverse=True)
    results = [(score, chunks[idx]) for score, idx in hybrid_scores[: max(limit, 40)]]
    return rerank_results(query, results)[:limit]




def _chunk_index(chunks: list[dict], target: dict) -> int | None:
    """Find the index of a chunk in the list by matching its 'id'."""
    target_id = target.get("id", "")
    for i, chunk in enumerate(chunks):
        if chunk.get("id") == target_id:
            return i
    return None




STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "are", "you", "can", "will", "live",
    "ableton", "page", "using", "use", "used", "into", "when", "your", "have", "has", "not",
    "set", "also", "one", "two", "new", "all", "any", "its", "more", "less", "view", "clip",
    "how", "what", "why", "does", "do", "did", "should", "would", "could", "about", "help",
    "make", "get", "need", "want", "work", "works", "working", "process", "processing",
    # Common function words missing above — their absence let notes match on
    # zero real content overlap (e.g. "poem about cats" matched a note via the
    # single shared word "me"; see docs/KENN_THURSDAY_CONVERSATION_AUDIT_2026-07-08.md).
    "of", "me", "my", "is", "in", "on", "to", "it", "as", "at", "be", "or", "an", "a",
    "i", "we", "us", "our", "if", "so", "but", "just", "please", "tell", "write", "say",
}

TOPIC_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ableton_link": ("ableton link", "link audio", "link session", "link peer", "start stop sync", "link"),
    "bass": ("bass", "bas", "sub", "sub-bass", "subbass", "low-end", "low end", "808", "subwoofer", "muddy", "rumble", "boominess", "boomy", "weight", "lows"),
    "drums": ("drum", "drums", "kick", "kik", "snare", "hat", "hihat", "hi-hat", "percussion", "clap", "drum rack", "layer", "layering"),
    "mixing": ("mix", "mixing", "balance", "level", "gain", "eq", "equal", "pan", "panning", "bus", "glue", "fader", "gain staging", "gain-staging", "volume", "headroom", "stems", "aux", "send", "return", "pre-fader", "post-fader", "attenuate"),
    "mastering": ("master", "premaster", "mastering", "loudness", "limiter", "clipper", "true peak", "final"),
    "vocals": ("vocal", "vocals", "voice", "singer", "lyric", "comping", "tuning", "pitch correction", "double", "doubles", "adlib", "adlibs", "sibilance", "sibilant", "harshness", "harsh", "deesser", "de-esser", "comp", "presence", "air", "intelligibility", "mud", "plosive", "plosives", "autotune", "auto-tune", "vocalist", "throat", "whisper", "breath", "delisp", "delisper", "ess"),
    "delay": ("delay", "echo", "feedback", "repitch", "fade mode"),
    "stereo_width": ("wide", "width", "widen", "widening", "stereo", "doubler", "microshift", "haas", "mono compatibility", "mid side", "mid-side", "centre", "centred", "center", "centered"),
    "depth": ("depth", "front", "back", "behind", "space", "ambience", "ambiance", "pre-delay", "predelay", "throw", "throws"),
    "compression": ("compress", "compression", "compressor", "glue", "dynamics", "sidechain", "sidechane", "side chain", "duck", "ratio", "threshold"),
    "transients": ("transient", "transients", "punch", "attack", "snap", "smack", "impact"),
    "saturation": ("saturat", "distort", "drive", "warmth", "harmonic", "saturator", "pedal", "soft clip", "tape"),
    "automation": ("automation", "automate", "envelope", "lfo", "modulation", "macro", "clip envelope", "max for live", "max4live", "m4l", "amxd"),
    "cpu": ("cpu", "overload", "glitch", "crackl", "buffer", "latency", "performance", "overload"),
    "warp": ("warp", "warping", "tempo", "time-stretch", "marker", "warp marker"),
    "freeze": ("freeze", "flatten", "bounce", "render", "resample"),
    "reverb": ("reverb", "room", "plate", "hall", "space", "send", "return"),
    "eq": ("eq", "eq eight", "eq8", "equalizer", "high-pass", "high pass", "low-pass", "muddy", "low mid", "low-mid", "harsh", "sibilance", "sibilant", "resonance", "notch", "shelf", "cut", "boost", "rumble", "frequency", "frequencies", "masking", "midrange", "filter", "filters", "curves", "boominess", "boomy", "tilt", "carve", "roll-off", "rolloff", "parametric", "graphic eq", "dynamic eq"),
    "export": ("export", "stem", "stems", "bounce", "render", "delivery", "wav"),
    "routing": ("route", "routing", "group", "bus", "send", "return", "track", "chain selector"),
    "midi": ("midi", "clip", "note", "velocity", "groove", "quantize"),
    "arrangement": ("arrangement", "arrange", "timeline", "locator", "marker", "section", "song structure", "shortcut", "shortcuts", "build up", "build-up", "drop", "tension", "release"),
    "sound_design": ("sound design", "synth", "simpler", "operator", "fm", "wavetable", "serum"),
    "podcast": ("podcast", "dialogue", "speech", "episode", "interview", "voiceover"),
    "revision": ("revision", "revisions", "feedback", "v2", "round", "client notes"),
    "delivery": ("deliver", "delivery", "handoff", "send", "client", "final files", "preview"),
    "pricing": ("price", "pricing", "quote", "quoting", "rate", "rates", "charge", "cost", "budget", "scope", "package", "deposit"),
    "recording": ("record", "recording", "microphone", "input", "punch", "take"),
    "game_audio": ("game audio", "wwise", "fmod", "unity audio", "unreal audio", "soundbank", "sound bank", "soundbanks", "interactive music", "stinger", "ambience loop", "game build", "combat audio", "footstep", "footsteps"),
    # A bare "switch" is not enough to identify Wwise: Live's Rack Chain
    # Selector also switches chains/plugins. Wwise questions still classify
    # through explicit middleware vocabulary (Wwise, RTPC, game sync, Unreal,
    # etc.) or the broader game-audio topic. Keeping this ambiguous word here
    # made an exact Ableton Chain Selector question rank footstep Switch notes
    # above the matching approved Ableton note.
    "wwise": ("wwise", "audiokinetic", "rtpc", "game parameter", "game sync", "game object", "soundbank", "soundbanks", "sound bank", "middleware", "setrtpcvalue", "bank load", "virtual voice", "voice count", "transition segment", "music segment"),
    "loudness": ("lufs", "loudness", "ebu", "r128", "true peak", "dbtp", "normalization", "normalisation"),
    "monitoring": ("monitor", "monitoring", "headroom", "calibration", "reference level", "room", "phone", "car", "speaker", "speakers", "playback", "sonarworks", "crossfeed", "headphones", "earbuds", "monitors"),
    "translation": ("translation", "translate", "car", "phone", "earbuds", "small speakers", "reference", "mono", "systems", "headphones", "club", "boombox", "car test", "mono check", "check translation", "auratone", "headphones", "earbuds", "mixcube", "studio monitor", "monitors", "monocompatibility"),
    "acoustics": ("acoustic", "acoustics", "phase", "polarity", "room treatment", "reflection"),
    "mix_review": ("mix review", "spectrum", "spectral", "analyser", "analyzer", "crest", "rms", "peak", "meter", "metrics", "fletcher"),
}

TOPIC_CONFLICTS: dict[str, tuple[str, ...]] = {
    "bass": ("drum pattern", "choke group", "midi clip", "anthem drums", "drum rack basics"),
    "drums": ("vocal mixing", "mastering chain", "warp marker", "vocal comp"),
    "vocals": ("kick drum", "drum rack", "808"),
    "stereo_width": ("de-ess", "sibilance", "threshold", "ratio"),
    "depth": ("drum rack", "warp marker"),
    "reverb": ("warp marker", "midi clip"),
    "export": ("warp", "warping"),
    "automation": ("drum rack", "warp marker"),
    "cpu": ("warp", "midi clip"),
}


@lru_cache(maxsize=8192)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    """Tokenize immutable text once per process.

    Chat ranking revisits the same query and chunk text across BM25 scoring,
    reranking, intent guards, and answer formatting.  Returning a tuple keeps
    the cache value immutable while the public wrapper preserves the original
    list return type for callers that rely on it.
    """
    return tuple(word.lower() for word in WORD_RE.findall(text) if word.lower() not in STOPWORDS)


def tokenize(text: str) -> list[str]:
    return list(_tokenize_cached(str(text)))


def normalized_text(text: str) -> str:
    return " ".join(tokenize(text))


_COMMON_INFLECTION_SUFFIXES = {
    "", "s", "es", "e", "ed", "ing", "ion", "ions", "er", "ers", "y", "ier", "iest", "or", "ors", "r", "st", "n", "ning"
}


def term_matches(text: str, term: str) -> bool:
    """Word-boundary-safe matching for single-word terms; substring
    matching only for multi-word phrases (specific enough that an
    accidental substring collision is unlikely).

    Live-tested 2026-08-03: "ca you help me with bass compression" got
    tagged with an unrelated "vocals" topic, which fed into a Sidechain
    Bass To Kick answer instead of general bass compression. Root cause:
    "vocals"'s synonym list includes "comp" (short for "vocal comping"),
    a single word at exactly 4 characters -- one over the old boundary-
    check cutoff of len(needle) <= 3, so it fell through to the naive
    substring check below, and "comp" is literally the first four letters
    of "compression". The length cutoff was never actually about safety at
    a specific length; it was accidentally gating which single words got
    protected. Boundary-matching every single-word term (not just short
    ones) closes this whole class of "isNeedleActuallyAWordHere" bug.

    To allow valid inflectional matches for word stems (e.g. "saturat" matching
    "saturating", "compress" matching "compression", "wide" matching "wider"),
    we check if the remaining characters of the matched word form a standard
    inflection suffix.
    """
    lowered = text.lower()
    needle = term.lower()
    if re.fullmatch(r"[a-z0-9+#.-]+", needle):
        pattern = rf"\b{re.escape(needle)}([a-z0-9]*)\b"
        matches = re.findall(pattern, lowered)
        return any(suffix in _COMMON_INFLECTION_SUFFIXES for suffix in matches)
    return needle in lowered


@lru_cache(maxsize=4096)
def _query_topics_cached(query: str) -> tuple[str, ...]:
    lowered = query.lower()
    ableton_link_intent = any(
        term_matches(lowered, phrase)
        for phrase in ("ableton link", "link audio", "link session", "link peer", "start stop sync")
    )
    topics: list[str] = []
    for topic, terms in TOPIC_SYNONYMS.items():
        # "send" is deliberately present in several general audio topics,
        # but in "Does Ableton Link send audio?" it describes Link Audio,
        # not a mixer send, reverb return, routing bus, or client delivery.
        # Preserve the explicit product intent instead of expanding that one
        # ambiguous verb into dozens of unrelated retrieval terms.
        if ableton_link_intent and topic in {"mixing", "reverb", "routing", "delivery"}:
            continue
        if any(term_matches(lowered, term) for term in terms):
            topics.append(topic)
    return tuple(topics)


def query_topics(query: str) -> list[str]:
    """Return topic labels while reusing the process-local classifier result."""
    return list(_query_topics_cached(str(query)))


def hard_negative_cache_key_for(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (str(path), 0, 0)
    return (str(path), stat.st_mtime_ns, stat.st_size)


def hard_negative_cache_key() -> tuple[str, int, int]:
    return hard_negative_cache_key_for(HARD_NEGATIVES_PATH)


@lru_cache(maxsize=8)
def _load_hard_negatives_cached(path: str, _mtime_ns: int, _size: int) -> tuple[dict, ...]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    records: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return tuple(records)


def load_hard_negatives() -> tuple[dict, ...]:
    records = list(_load_hard_negatives_cached(*hard_negative_cache_key()))
    if HARD_NEGATIVES_PATH == DEFAULT_HARD_NEGATIVES_PATH:
        records.extend(_load_hard_negatives_cached(*hard_negative_cache_key_for(CURATED_HARD_NEGATIVES_PATH)))
    return tuple(records)


def hard_negative_penalty(query: str, chunk: dict) -> float:
    negatives = load_hard_negatives()
    if not negatives:
        return 1.0
    query_terms = set(tokenize(query))
    if not query_terms:
        return 1.0
    chunk_source = str(chunk.get("source", "")).lower()
    chunk_label = " ".join(str(chunk.get(key, "")) for key in ("title", "source")).lower()
    for record in negatives:
        negative_source = str(record.get("negative_source") or "").lower()
        negative_label = str(record.get("negative_source_label") or "").lower()
        if negative_source and negative_source not in chunk_source and negative_source not in chunk_label:
            continue
        if negative_label and negative_label not in chunk_label and negative_source not in chunk_source:
            continue
        negative_terms = set(tokenize(str(record.get("question") or "")))
        if not negative_terms:
            continue
        overlap = len(query_terms & negative_terms) / max(1, len(query_terms | negative_terms))
        if normalized_text(query) == normalized_text(str(record.get("question") or "")):
            return 0.18
        if overlap >= 0.68:
            return 0.35
    return 1.0


def source_trust_score(chunk: dict) -> float:
    """Trust prior for source type and review status, independent of query relevance."""
    kind = str(chunk.get("kind", "")).lower()
    source = str(chunk.get("source", "")).lower()
    text_head = str(chunk.get("text", ""))[:600].lower()
    if kind == "note":
        if str(chunk.get("evidence_class") or "") == "youtube_transcript":
            if re.search(r"^status:\s*approved\b", text_head, flags=re.M):
                return 0.90
            return 0.78
        if re.search(r"^status:\s*approved\b", text_head, flags=re.M):
            return 1.0
        if "status: draft" in text_head or "status: unmarked" in text_head:
            return 0.68
        return 0.88
    if source.startswith(("live", "ebu-")) or "manual" in source:
        return 0.78
    if source.endswith(".pdf"):
        return 0.68
    return 0.55


def source_trust_multiplier(chunk: dict) -> float:
    return 0.94 + (0.12 * source_trust_score(chunk))


def expanded_query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for topic in query_topics(query):
        terms.extend(TOPIC_SYNONYMS[topic])
    terms.extend(tokenize(query))
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


@lru_cache(maxsize=8192)
def _extract_tags_cached(text: str) -> frozenset[str]:
    tags: set[str] = set()
    for line in text.splitlines()[:20]:
        if line.lower().startswith("tags:"):
            for part in line.split(":", 1)[1].split(","):
                tag = part.strip().lower()
                if tag:
                    tags.add(tag)
    return frozenset(tags)


def extract_tags(text: str) -> set[str]:
    return set(_extract_tags_cached(str(text)))


@lru_cache(maxsize=8192)
def _chunk_topics_cached(title: str, source: str, text_head: str, tags_text: str) -> frozenset[str]:
    combined = " ".join([title, source, text_head, tags_text]).lower()
    hits: set[str] = set()
    for topic, terms in TOPIC_SYNONYMS.items():
        if any(term_matches(combined, term) for term in terms):
            hits.add(topic)
    return frozenset(hits)


def chunk_topics(chunk: dict) -> set[str]:
    if chunk.get("topics"):
        return set(chunk["topics"])
    text = str(chunk.get("text", ""))
    return set(
        _chunk_topics_cached(
            str(chunk.get("title", "")),
            str(chunk.get("source", "")),
            text[:1200],
            " ".join(extract_tags(text)),
        )
    )


def warm_metadata_cache(chunks: list[dict]) -> None:
    """Precompute cached chunk metadata so the first real query is not slow."""
    for chunk in chunks:
        chunk_topics(chunk)


def topic_relevance_multiplier(chunk: dict, topics: list[str]) -> float:
    if not topics:
        return 1.0
    chunk_hits = chunk_topics(chunk)
    query_set = set(topics)
    overlap = query_set & chunk_hits
    if overlap:
        bonus = 0.55 * len(overlap)
        if chunk.get("kind") == "note":
            bonus += 0.25
        return 1.0 + bonus

    combined = f"{chunk.get('title', '')} {chunk.get('text', '')}".lower()
    for topic in topics:
        for conflict in TOPIC_CONFLICTS.get(topic, ()):
            if conflict in combined:
                return 0.2
    return 0.45


def bm25_search(
    query: str,
    chunks: list[dict],
    terms: dict,
    limit: int = 8,
    *,
    rerank: bool = True,
    allowed: Callable[[dict], bool] | None = None,
) -> list[tuple[float, dict]]:
    query_terms = expanded_query_terms(query)
    if not query_terms:
        return []

    idf = terms["idf"]
    lengths = terms["lengths"]
    avg_len = float(terms.get("avg_len") or 1)
    topics = query_topics(query)
    k1 = 1.5
    b = 0.75

    inverted = terms.get("inverted_index")
    candidate_scores: dict[int, float] = {}

    if inverted:
        for term in query_terms:
            term_idf = float(idf.get(term, 0.0))
            if not term_idf:
                continue
            postings = inverted.get(term)
            if not postings:
                continue
            for doc_idx, freq in postings:
                length = lengths[doc_idx] or 1
                denom = freq + k1 * (1 - b + b * (length / avg_len))
                score_contribution = term_idf * ((freq * (k1 + 1)) / denom)
                candidate_scores[doc_idx] = candidate_scores.get(doc_idx, 0.0) + score_contribution
    else:
        # Fallback to linear scan if inverted index not present
        term_counts = terms["term_counts"]
        for index, counts in enumerate(term_counts):
            score = 0.0
            for term in query_terms:
                freq = counts.get(term, 0)
                if not freq:
                    continue
                term_idf = float(idf.get(term, 0.0))
                denom = freq + k1 * (1 - b + b * ((lengths[index] or 1) / avg_len))
                score += term_idf * ((freq * (k1 + 1)) / denom)
            if score > 0:
                candidate_scores[index] = score

    scores: list[tuple[float, int]] = []
    for doc_idx, score in candidate_scores.items():
        if score <= 0:
            continue
        if allowed is not None and not allowed(chunks[doc_idx]):
            continue
        score *= topic_relevance_multiplier(chunks[doc_idx], topics)
        score *= tag_overlap_boost(chunks[doc_idx], query_terms, topics)
        if chunks[doc_idx].get("kind") == "note":
            score *= 1.15
        score *= source_trust_multiplier(chunks[doc_idx])
        _ct = chunk_topics(chunks[doc_idx])
        if (_ct & {"wwise", "game_audio"} or "wwise" in str(chunks[doc_idx].get("source", "")).lower()) and not (set(topics) & {"wwise", "game_audio"}):
            score *= 0.08
        scores.append((score, doc_idx))

    scores.sort(reverse=True)
    candidates = [(score, chunks[index]) for score, index in scores[: max(limit, 80)]]
    # rerank=False for hybrid_search's internal call: it merges these raw BM25
    # scores with an embedding boost and reranks the unified candidate set
    # itself exactly once. Reranking here too used to compound
    # source_trust_multiplier (3x) and hard_negative_penalty (2x) for any
    # chunk that reached the hybrid path via BM25, while chunks reached only
    # through hybrid_search's cosine-only backfill got just the one pass —
    # two different chunks answering the same query ended up on different
    # scoring scales. See docs/CODEBASE_AUDIT_2026-07-06.md.
    if not rerank:
        return candidates[:limit]
    return rerank_results(query, candidates)[:limit]


_feedback_scores_cache: dict[str, float] | None = None
_feedback_scores_cache_time: float = 0.0
_FEEDBACK_CACHE_TTL_SEC: float = 300.0


def load_source_feedback_scores() -> dict[str, float]:
    """Load feedback-based quality scores for all sources in sqlite DB.


    Returns a dict mapping source file/note title to a quality multiplier.
    """
    global _feedback_scores_cache, _feedback_scores_cache_time
    import time
    now = time.time()
    if _feedback_scores_cache is not None and now - _feedback_scores_cache_time < _FEEDBACK_CACHE_TTL_SEC:
        return _feedback_scores_cache

    db_file = Path(__file__).resolve().parents[4] / "data" / "audio_too.db"
    if not db_file.exists():
        return {}


    scores = {}
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_file), timeout=5.0)
        conn.row_factory = sqlite3.Row


        # Check if table exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='demo_feedback'")
        if not cursor.fetchone():
            conn.close()
            return {}


        rows = conn.execute("SELECT rating, sources_json FROM demo_feedback").fetchall()
        conn.close()


        stats: dict[str, dict[str, int]] = {}
        for row in rows:
            rating = str(row["rating"]).lower()
            try:
                sources = json.loads(row["sources_json"] or "[]")
            except Exception:
                continue


            for src in sources:
                src_name = src.get("source") or src.get("title") or src.get("label")
                if not src_name:
                    continue
                if src_name not in stats:
                    stats[src_name] = {"useful": 0, "not_useful": 0}
                if rating == "useful":
                    stats[src_name]["useful"] += 1
                elif rating == "not_useful":
                    stats[src_name]["not_useful"] += 1


        # Compute feedback multiplier (Bayesian average style)
        for src_name, counts in stats.items():
            u = counts["useful"]
            d = counts["not_useful"]
            s_fb = (u - d) / (u + d + 2.0)
            # Yields values between 0.70 (very poor) and 1.30 (very helpful)
            scores[src_name] = round(1.0 + 0.3 * s_fb, 3)

        _feedback_scores_cache = scores
        _feedback_scores_cache_time = now
    except Exception as e:
        print(f"Warning loading source feedback scores: {e}")

    return scores


RERANKER_MODEL_PATH = ROOT / "artifacts" / "training" / "kenn_reranker_model.json"
_RERANKER_WORD_RE = re.compile(r"[a-z0-9]+")
_QUERY_TOKEN_ALIASES = {"sidechane": "sidechain", "bas": "bass", "kik": "kick"}
_reranker_model: dict | None = None
_reranker_model_loaded = False


def _load_reranker_model() -> dict | None:
    """Load the trained source-reranker (kenn_reranker_train.py), once.

    Pure linear model (sigmoid over 9 hand-computed features) — no torch or
    any ML framework needed at inference, just arithmetic, even though the
    model was trained with a torch backend. Returns None if the artifact is
    missing, OR if KENN_RERANKER_MODEL_ENABLED isn't set to 1 — measured
    (via scripts/eval/ableton_benchmark.py) to actively regress 3 real
    benchmark cases when applied by default. Root cause: its by-far dominant
    weight is on `inverse_rank` (4.86, vs 0.2-2.3 for every other feature).
    The 340-pair training set had a baseline (existing rank order) that was
    ALREADY perfect (top1=1.0, mrr=1.0 — see kenn_reranker_metrics.json), so
    there was no training signal that ever rewarded overriding the existing
    top pick; the model degenerated into "trust and amplify whatever's
    already ranked #1." That's harmless when rank 1 is already right and
    actively harmful when it isn't, since it widens the gap instead of
    correcting it — confirmed directly: disabling this call is what fixes
    the 3 regressed cases, not any other change. Needs retraining against a
    harder dataset (cases where the existing rank order is imperfect) with a
    real top1/MRR delta over baseline before it's safe to enable by default.
    """
    global _reranker_model, _reranker_model_loaded
    if _reranker_model_loaded:
        return _reranker_model
    _reranker_model_loaded = True
    if os.environ.get("KENN_RERANKER_MODEL_ENABLED", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        _reranker_model = None
        return _reranker_model
    try:
        data = json.loads(RERANKER_MODEL_PATH.read_text(encoding="utf-8"))
        weights = [float(w) for w in data["weights"]]
        if len(weights) == 9:
            _reranker_model = {"weights": weights}
    except Exception:
        _reranker_model = None
    return _reranker_model


def _reranker_tokens(text: str) -> set[str]:
    return {token for token in _RERANKER_WORD_RE.findall(str(text).lower()) if len(token) > 2}


def _reranker_features(
    query_tokens: set[str],
    source_label_text: str,
    source_kind: str,
    topics: list[str],
    rank: int,
) -> list[float]:
    """Mirrors scripts/eval/kenn_reranker_train.py::features() exactly — the
    weights were fit against this exact feature order/formula."""
    source_tokens = _reranker_tokens(source_label_text)
    topic_terms = {str(t).replace("_", " ").lower() for t in topics}
    overlap = len(query_tokens & source_tokens)
    union = len(query_tokens | source_tokens)
    label_lower = source_label_text.lower()
    return [
        1.0,
        overlap / max(1, len(query_tokens)),
        overlap / max(1, union),
        1.0 / max(1.0, float(rank)) if rank > 0 else 0.0,
        1.0 if ".md" in label_lower else 0.0,
        1.0 if "pdf" in label_lower else 0.0,
        1.0 if source_kind == "note" else 0.0,
        1.0 if any(topic and topic in label_lower for topic in topic_terms) else 0.0,
        min(1.0, len(source_tokens) / 12.0),
    ]


def _reranker_probability(
    query_tokens: set[str], source_label_text: str, source_kind: str, topics: list[str], rank: int
) -> float | None:
    model = _load_reranker_model()
    if model is None:
        return None
    features = _reranker_features(query_tokens, source_label_text, source_kind, topics, rank)
    z = sum(w * f for w, f in zip(model["weights"], features))
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _chunk_source_label(chunk: dict) -> str:
    """Matches kenn.core.chat_retrieval.source_label() — kept as a local
    copy to avoid a circular import (chat_retrieval imports this module)."""
    if chunk.get("kind") == "note":
        return f"{chunk.get('title') or chunk.get('source')} ({chunk.get('source')})"
    return f"{chunk.get('source', '')}, page {chunk.get('page', '')}"


def rerank_results(query: str, results: list[tuple[float, dict]]) -> list[tuple[float, dict]]:
    """Second-pass ranking that rewards exact intent overlap and penalizes broad false positives."""
    if not results:
        return []

    feedback_scores = load_source_feedback_scores()

    topics = query_topics(query)
    topic_set = set(topics)
    query_terms = {_QUERY_TOKEN_ALIASES.get(term, term) for term in tokenize(query)}
    query_lower = query.lower()
    reranker_query_tokens = _reranker_tokens(query)
    reranked: list[tuple[float, dict]] = []
    for rank, (score, chunk) in enumerate(results, start=1):
        chunk_text = " ".join(
            str(chunk.get(key, ""))
            for key in ("title", "source", "text")
            if chunk.get(key)
        ).lower()
        title_tag_text = " ".join(
            [
                str(chunk.get("title", "")),
                str(chunk.get("source", "")),
                " ".join(extract_tags(chunk.get("text", ""))),
            ]
        ).lower()
        chunk_terms = set(tokenize(chunk_text))
        title_tag_terms = set(tokenize(title_tag_text))
        title_identity_terms = set(tokenize(" ".join([
            str(chunk.get("title", "")), str(chunk.get("source", ""))
        ])))
        chunk_topic_set = chunk_topics(chunk)
        lexical_overlap = len(query_terms & chunk_terms)
        title_tag_overlap = len(query_terms & title_tag_terms)
        topic_overlap = len(topic_set & chunk_topic_set)
        adjusted = score
        adjusted *= 1.0 + min(0.08 * lexical_overlap, 0.48)
        adjusted *= 1.0 + min(0.18 * title_tag_overlap, 0.9)
        # A concise source title is stronger intent evidence than repeated
        # vocabulary in a long body chunk. This bounded boost prevents broad
        # manuals/notes from crowding out a note explicitly named for the
        # user's problem, while requiring at least two exact intent tokens so
        # generic one-word title matches do not move.
        title_identity_overlap = len(query_terms & title_identity_terms)
        if title_identity_overlap >= 2:
            adjusted *= 1.0 + min(0.28 * title_identity_overlap, 0.84)
        if topics:
            if topic_overlap:
                adjusted *= 1.0 + min(0.18 * topic_overlap, 0.72)
            else:
                adjusted *= 0.68
        if chunk.get("kind") == "note":
            adjusted *= 1.08
        for term in sorted(query_terms, key=len, reverse=True):
            if len(term) >= 5 and term in chunk_text:
                adjusted *= 1.04
                break
        for topic in topics:
            for conflict in TOPIC_CONFLICTS.get(topic, ()):
                if conflict in chunk_text and conflict not in query_lower:
                    adjusted *= 0.45
                    break
        adjusted *= source_trust_multiplier(chunk)
        adjusted *= hard_negative_penalty(query, chunk)
        # Approved notes frequently include an exact user-facing question in
        # their related-questions section.  Treat that as stronger evidence
        # than broad shared middleware vocabulary (for example, RTPC versus
        # a footstep-switch note), while still leaving normal ranking intact.
        normalized_query = normalized_text(query)
        if normalized_query and normalized_query in normalized_text(chunk_text):
            adjusted *= 2.0
        # RTPC is a narrow implementation concept.  A source that names it
        # should outrank a broadly related Unity/Wwise troubleshooting note.
        if "rtpc" in query_terms and "rtpc" in title_tag_terms:
            adjusted *= 1.8
        # Wwise/game-audio notes share generic terms (sample rate, memory,
        # CPU, profiling) with music production queries.  Demote them hard
        # when the query has no game-audio or Wwise intent.
        _is_game_chunk = "wwise" in str(chunk.get("source", "")).lower() or chunk_topic_set & {"wwise", "game_audio"}
        _query_wants_game = topic_set & {"wwise", "game_audio"}
        if _is_game_chunk and not _query_wants_game:
            adjusted *= 0.08


        # Apply feedback quality multiplier dynamically
        src_name = chunk.get("source")
        if src_name in feedback_scores:
            adjusted *= feedback_scores[src_name]
        title_name = chunk.get("title")
        if title_name in feedback_scores:
            adjusted *= feedback_scores[title_name]

        # Trained reranker (scripts/eval/kenn_reranker_train.py) — a gentle
        # nudge, not a dominant factor: its own validation metrics show 0.0
        # top1/MRR delta over trusting the existing rank order on its (small,
        # already-saturated) 340-pair eval set, so there's no evidence it
        # improves ranking quality. Wired in anyway since it's harmless at
        # this weight and the model was fully trained and sitting unused;
        # revisit the blend weight once a real eval set can show a delta.
        reranker_prob = _reranker_probability(
            reranker_query_tokens, _chunk_source_label(chunk), str(chunk.get("kind", "")), topics, rank
        )
        if reranker_prob is not None:
            adjusted *= 1.0 + (reranker_prob - 0.5) * 0.3

        reranked.append((adjusted, chunk))
    # Apply supervised topic feedback before the caller truncates this larger
    # candidate pool to its public limit.  Keeping this in the shared reranker
    # lets feedback promote a previously lower-ranked candidate into the final
    # result set instead of merely swapping already-selected results.
    try:
        from kenn.core.feedback_signals import apply_feedback_boost
        reranked = apply_feedback_boost(reranked)
    except Exception:
        # Retrieval must remain usable when the optional feedback store is
        # unavailable or malformed.
        pass
    reranked.sort(key=lambda item: item[0], reverse=True)
    return reranked


def tag_overlap_boost(chunk: dict, query_terms: list[str], topics: list[str]) -> float:
    tags = set(chunk["tags"]) if chunk.get("tags") else extract_tags(chunk.get("text", ""))
    if not tags:
        return 1.0
    hits = sum(1 for term in query_terms if term in tags)
    topic_tag_hits = sum(1 for topic in topics if topic in tags or any(s in tags for s in TOPIC_SYNONYMS.get(topic, ())))
    bonus = 0.12 * hits + 0.2 * topic_tag_hits
    return 1.0 + min(bonus, 0.65)


def best_sentence(text: str, topics: list[str], focus_terms: Iterable[str]) -> str:
    cleaned = " ".join(text.replace("\n", " ").split())
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    needles = [term.lower() for term in focus_terms]
    for topic in topics:
        needles.extend(TOPIC_SYNONYMS.get(topic, ()))
    for sentence in sentences:
        lowered = sentence.lower()
        if len(sentence) < 20:
            continue
        if any(needle in lowered for needle in needles):
            return sentence.strip()
    for sentence in sentences:
        if len(sentence) >= 40 and not re.fullmatch(r"[\d.\s]+", sentence):
            return sentence.strip()
    return sentences[0].strip() if sentences else cleaned[:240]
