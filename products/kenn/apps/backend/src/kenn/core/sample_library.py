"""Bounded, read-only local sample-library indexing and search.

KENN points at one explicitly approved local folder
(``KENN_SAMPLE_LIBRARY_ROOT``) and indexes filenames and folder structure
only in the bulk scan below -- no audio file is opened, analyzed, or hashed
by content there. A sample suggestion from that scan is a fourth evidence
category, distinct from Mix Review's measured findings and AudioGen's
generated material: it is a library reference, always advisory, and never
claimed to be measured or generated. No raw filesystem path is ever
returned to a caller; entries are addressed by an opaque id resolved back
to a path only inside this module.

``analyze_sample_audio`` below is a separate, explicit, per-file exception
to that "filenames only" rule: given one sample's opaque id, it decodes the
audio (bounded duration) and returns a real measured BPM/key estimate. It
is opt-in only -- never invoked by the bulk scan or by ``search_samples``
-- so the 28k-file library stays fast, and the result is honestly labelled
as measured evidence, not a filename-derived tag.

Importing a chosen sample into Live remains a separate, confirmation-gated
capability. ``SampleImportService`` resolves an opaque id back to an approved
path, and the vendored AbletonOSC endpoint creates the audio clip in one exact
empty Session slot with readback. Search and browse in this module stay
read-only.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # Optional, heavier dependency; abstain honestly when absent.
    import librosa as _librosa
except ImportError:
    _librosa = None

# Bound per-file decode/analysis work; a bulk scan never calls this path,
# so this only bounds one on-demand request, not the whole library.
MAX_ANALYSIS_SECONDS = 60.0
MIN_ANALYSIS_SECONDS = 0.5
_KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

AUDIO_EXTENSIONS = frozenset({".wav", ".aif", ".aiff"})
_IGNORED_NAMES = frozenset({".DS_Store"})
DEFAULT_MAX_FILES = 50_000

# Deliberately simple substring tags, not a full classifier: this is
# filename/folder-derived metadata, not a measured or inferred property of
# the audio content itself.
_TAG_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kick", ("kick",)),
    ("snare", ("snare", "clap")),
    ("hihat", ("hihat", "hi-hat", "hi hat", "hat")),
    ("percussion", ("perc", "percussion", "conga", "bongo", "tom", "shaker")),
    ("drum_loop", ("break", "groove", "loop", "drum")),
    ("bass", ("bass", "sub", "808")),
    ("vocal", ("vocal", "vox", "acapella", "adlib")),
    ("synth", ("synth", "lead", "pluck", "arp")),
    ("pad", ("pad", "atmosphere", "ambient", "drone")),
    ("guitar", ("guitar", "gtr")),
    ("piano", ("piano", "keys", "rhodes")),
    ("fx", ("fx", "riser", "impact", "sweep", "transition", "noise")),
    ("one_shot", ("one shot", "one-shot", "oneshot", "hit")),
)


def _tags_from_text(text: str) -> set[str]:
    lowered = text.lower()
    return {tag for tag, words in _TAG_WORDS if any(word in lowered for word in words)}


def _entry_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SampleEntry:
    relative_path: str
    filename: str
    pack: str
    extension: str
    size_bytes: int
    tags: frozenset[str]

    @property
    def id(self) -> str:
        return _entry_id(self.relative_path)

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "pack": self.pack,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "tags": sorted(self.tags),
        }


def library_root() -> Path | None:
    configured = os.getenv("KENN_SAMPLE_LIBRARY_ROOT", "").strip()
    if not configured:
        return None
    root = Path(configured).expanduser()
    return root if root.is_dir() else None


def scan_sample_library(root: str | Path, *, max_files: int = DEFAULT_MAX_FILES) -> list[SampleEntry]:
    """Bounded, read-only scan of one explicitly approved folder.

    Only filenames/folder structure are used as metadata -- no audio file
    is opened or analyzed. Truncates at ``max_files`` rather than silently
    sampling, so a caller can tell the scan was incomplete.
    """
    root_path = Path(root)
    entries: list[SampleEntry] = []
    if not root_path.is_dir():
        return entries
    for path in sorted(root_path.rglob("*")):
        if len(entries) >= max_files:
            break
        if not path.is_file():
            continue
        if path.name in _IGNORED_NAMES or path.name.startswith("."):
            continue
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            continue
        relative = path.relative_to(root_path)
        pack = relative.parts[0] if len(relative.parts) > 1 else ""
        tags = frozenset(_tags_from_text(path.stem) | _tags_from_text(pack))
        entries.append(SampleEntry(
            relative_path=str(relative),
            filename=path.name,
            pack=pack,
            extension=path.suffix.lower(),
            size_bytes=size_bytes,
            tags=tags,
        ))
    return entries


def search_samples(entries: list[SampleEntry], query: str, *, limit: int = 10) -> list[SampleEntry]:
    """Rank entries by tag/token overlap with the query.

    Advisory library reference only; a higher score means more filename/
    folder text matched the request, never that the sample was measured or
    that it will sound a particular way.
    """
    if limit <= 0:
        return []
    query_tags = _tags_from_text(query)
    query_terms = {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 1}
    scored: list[tuple[float, int, SampleEntry]] = []
    for index, entry in enumerate(entries):
        score = 2.0 * len(query_tags & entry.tags)
        haystack = f"{entry.filename} {entry.pack}".lower()
        haystack_terms = {term for term in re.findall(r"[a-z0-9]+", haystack) if len(term) > 1}
        score += len(query_terms & haystack_terms)
        if score > 0:
            scored.append((score, index, entry))
    # Stable by original scan order among equal scores (index as tiebreaker),
    # not insertion-order-dependent sort instability.
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [entry for _score, _index, entry in scored[:limit]]


def resolve_sample(entries: list[SampleEntry], sample_id: str) -> SampleEntry | None:
    return next((entry for entry in entries if entry.id == sample_id), None)


def analyze_sample_audio(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Real, on-demand BPM/key estimate for one sample file.

    Returns ``(result, abstain_reason)`` -- exactly one is ``None``. This
    decodes real audio (bounded to ``MAX_ANALYSIS_SECONDS``), unlike the
    filename/folder-only bulk scan above, so it is never called from
    ``scan_sample_library`` or ``search_samples``. Key detection reports a
    pitch-class only (chroma-energy peak), not a major/minor mode -- that
    would need a separate key-profile classifier this module does not have,
    so it is deliberately not claimed.
    """
    if _librosa is None:
        return None, "the optional librosa dependency is not installed"
    if not path.is_file():
        return None, "sample file was not found on disk"
    try:
        y, sr = _librosa.load(str(path), sr=None, mono=True, duration=MAX_ANALYSIS_SECONDS)
    except Exception as exc:
        return None, f"librosa failed to decode this file: {exc}"
    if y.size == 0 or (sr and y.size < sr * MIN_ANALYSIS_SECONDS):
        return None, f"audio is shorter than the {MIN_ANALYSIS_SECONDS}s minimum for reliable BPM/key estimation"

    # BPM and key are estimated independently: a sustained tone has a clear
    # pitch class but no discoverable beat, and a pure percussion hit is the
    # opposite -- neither missing dimension should suppress the other.
    result: dict[str, Any] = {}
    try:
        tempo, _beat_frames = _librosa.beat.beat_track(y=y, sr=sr)
        tempo_value = float(tempo.item() if hasattr(tempo, "item") else tempo)
        if tempo_value > 0:
            result["estimated_bpm"] = round(tempo_value, 1)
    except Exception:
        pass  # beat tracking is best-effort; absence of the field is the honest signal
    try:
        chroma = _librosa.feature.chroma_cqt(y=y, sr=sr)
        mean_chroma = chroma.mean(axis=1)
        if float(mean_chroma.max()) > 0:
            result["estimated_key_pitch_class"] = _KEY_NAMES[int(mean_chroma.argmax()) % 12]
    except Exception:
        pass

    if not result:
        return None, "neither a stable tempo nor a clear pitch class could be estimated from this audio"
    result["analysis_seconds"] = round(min(MAX_ANALYSIS_SECONDS, y.size / sr) if sr else 0.0, 1)
    return result, None


__all__ = [
    "AUDIO_EXTENSIONS",
    "SampleEntry",
    "analyze_sample_audio",
    "library_root",
    "resolve_sample",
    "scan_sample_library",
    "search_samples",
]
