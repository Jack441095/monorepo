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

from kenn.core import native_fft

# Bound per-file decode/analysis work; a bulk scan never calls this path,
# so this only bounds one on-demand request, not the whole library.
MAX_ANALYSIS_SECONDS = 60.0
MIN_ANALYSIS_SECONDS = 0.5
# We read at most 64 MiB of a WAV: 60 s of stereo 32-bit float at up to
# 139 kHz. The native decoder takes the truncated data chunk as it is, so a
# longer or wider file is analysed on its first part instead of read whole.
_MAX_WAV_READ_BYTES = 64 * 1024 * 1024
# The native key/tempo kernel refuses rates under 8 kHz (a header declaring
# 2 Hz once looped it forever) or above 768 kHz (a 60 MHz header allocated
# ~5 GB); a real sample is never outside that range, so abstain.
_MIN_SAMPLE_RATE_HZ = 8000
_MAX_SAMPLE_RATE_HZ = 768000
_KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# Krumhansl-Kessler key profiles, index 0 = tonic.
_MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

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
    ``scan_sample_library`` or ``search_samples``. Key detection reports the
    tonic pitch class only, not a major/minor mode: on labelled loops the
    profile match confuses relative and parallel keys often enough that the
    mode is not worth claiming.
    """
    import numpy as np

    if not path.is_file():
        return None, "sample file was not found on disk"
    if not native_fft.available():
        return None, "the native DSP extension is not built or is disabled"
    decoded = _decode_mono(path)
    if isinstance(decoded, str):
        return None, decoded
    mono, rate = decoded
    if rate < _MIN_SAMPLE_RATE_HZ:
        return None, f"the file declares a {rate} Hz sample rate, below the {_MIN_SAMPLE_RATE_HZ} Hz key/tempo minimum"
    if rate > _MAX_SAMPLE_RATE_HZ:
        return None, f"the file declares a {rate} Hz sample rate, above the {_MAX_SAMPLE_RATE_HZ} Hz key/tempo maximum"
    mono = mono[: int(rate * MAX_ANALYSIS_SECONDS)]
    if mono.size < rate * MIN_ANALYSIS_SECONDS:
        return None, f"audio is shorter than the {MIN_ANALYSIS_SECONDS}s minimum for reliable BPM/key estimation"
    if not np.isfinite(mono).all():
        # One NaN in a float WAV poisoned the chroma and came out as a
        # confident "C" (adversary review, 17 Oct 2026).
        return None, "the audio contains NaN or infinite samples"

    features = native_fft.key_tempo_features(mono, rate)
    if features is None:
        # available() is true but the loaded extension predates
        # key_tempo_features: a stale build, as bit us on 17 Oct.
        return None, "the native DSP extension is out of date and has no key/tempo analysis"
    # BPM and key are reported independently: a sustained tone has a clear
    # pitch class but no discoverable beat, and a pure percussion hit is the
    # opposite -- neither missing dimension should suppress the other.
    result: dict[str, Any] = {}
    if features["tempo_bpm"]:
        result["estimated_bpm"] = round(float(features["tempo_bpm"]), 1)
    tonic = _profile_tonic(features["chroma"])
    if tonic is not None:
        result["estimated_key_pitch_class"] = _KEY_NAMES[tonic]

    if not result:
        return None, "neither a stable tempo nor a clear pitch class could be estimated from this audio"
    result["analysis_seconds"] = round(mono.size / rate, 1)
    return result, None


def _decode_mono(path: Path) -> tuple[Any, int] | str:
    """Return ``(mono float32 samples, rate)`` for one WAV or AIFF file, or the reason it could not be decoded."""
    import numpy as np

    with path.open("rb") as handle:
        payload = handle.read(_MAX_WAV_READ_BYTES)
    is_aiff = path.suffix.lower() in {".aif", ".aiff"}
    decoded = native_fft.decode_pcm(payload, allow_aiff=is_aiff)
    if decoded is None:
        # The native decoder reads mono or stereo 16/24/32-bit PCM and 32-bit
        # float WAV/AIFF/AIFC; 8-bit, multichannel, compressed, empty or
        # malformed files land here, and abstaining is the honest answer.
        container = "AIFF" if is_aiff else "WAV"
        return f"this {container} could not be decoded (mono or stereo 16/24/32-bit PCM or float only)"
    channels = decoded["channels"]
    mono = channels[0] if len(channels) == 1 else np.mean(np.stack(channels), axis=0, dtype=np.float32)
    return mono, int(decoded["sample_rate"])


def _profile_tonic(chroma: list[float]) -> int | None:
    """Return the tonic pitch class of the best-correlated major or minor key profile, or None for flat chroma."""
    import numpy as np

    values = np.asarray(chroma, dtype=np.float64)
    if float(values.max() - values.min()) <= 0.0:
        # Silence or a perfectly flat spectrum has no correlation to rank.
        return None
    # The profile match beat the plain chroma peak on 488 labelled sample-pack
    # loops, 142/250 tonics right against 100 (17 Oct 2026, the receipt in
    # docs/research/CPP_DSP_KEY_TEMPO_RECEIPT.md), because the strongest
    # pitch class in a loop is often the fifth or the third, not the tonic.
    best = max(
        (float(np.corrcoef(values, np.roll(profile, tonic))[0, 1]), tonic)
        for tonic in range(12)
        for profile in (_MAJOR_PROFILE, _MINOR_PROFILE)
    )
    return best[1]


__all__ = [
    "AUDIO_EXTENSIONS",
    "SampleEntry",
    "analyze_sample_audio",
    "library_root",
    "resolve_sample",
    "scan_sample_library",
    "search_samples",
]
