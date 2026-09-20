"""Bounded, provenance-safe cache for immutable audio analysis results."""

from __future__ import annotations

from collections import OrderedDict
import copy
import hashlib
import threading
from typing import Callable

_MAX_ENTRIES = 8
_lock = threading.RLock()
_cache: OrderedDict[tuple[str, str], dict] = OrderedDict()


def analysis_cache_key(
    file_bytes: bytes,
    *,
    mix_goal: str,
    phon_level: float,
    light: bool,
    include_bands: bool,
    target_config_fingerprint: str = "",
) -> tuple[str, str]:
    """Return a cache key whose profile includes every output-affecting option.

    ``target_config_fingerprint`` must reflect the exact goal-targets config
    in effect (e.g. a hash of the editable targets file). Without it, editing
    the targets config and re-analysing identical audio would silently
    return a stale cached result computed under the old config.
    """
    source_hash = "sha256:" + hashlib.sha256(file_bytes).hexdigest()
    profile = (
        f"mix_review:{'light' if light else 'full'}:goal={mix_goal}:"
        f"phon={float(phon_level):.3f}:bands={bool(include_bands)}:"
        f"targets={target_config_fingerprint}:v1"
    )
    return source_hash, profile


def get_or_analyze(
    file_bytes: bytes,
    *,
    filename: str,
    mix_goal: str,
    phon_level: float,
    light: bool,
    include_bands: bool,
    analyze: Callable[[], dict],
    target_config_fingerprint: str = "",
) -> dict:
    """Return a deep-copied result keyed by source bytes and exact profile.

    The cache has no persistence and never crosses the source hash/profile
    boundary. This intentionally favours evidence freshness and isolation
    over an aggressive cache hit rate.
    """
    key = analysis_cache_key(
        file_bytes, mix_goal=mix_goal, phon_level=phon_level, light=light,
        include_bands=include_bands, target_config_fingerprint=target_config_fingerprint,
    )
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            result = copy.deepcopy(cached)
            _mark_result(result, filename=filename, hit=True, key=key)
            return result

    result = analyze()
    if not isinstance(result, dict) or not result.get("ok"):
        return result
    with _lock:
        _cache[key] = copy.deepcopy(result)
        _cache.move_to_end(key)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)
    _mark_result(result, filename=filename, hit=False, key=key)
    return result


def _refresh_nested_filenames(value: object, filename: str) -> None:
    """Overwrite every nested ``filename`` key throughout the result tree.

    Some report sections (e.g. the Ableton repair-chain export) bake the
    filename in at analysis time rather than reading it live from
    ``metrics``. On a cache hit those nested copies would otherwise keep
    whichever filename was passed in when the entry was first computed.
    """
    if isinstance(value, dict):
        if "filename" in value:
            value["filename"] = filename
        for nested in value.values():
            _refresh_nested_filenames(nested, filename)
    elif isinstance(value, list):
        for item in value:
            _refresh_nested_filenames(item, filename)


def _mark_result(result: dict, *, filename: str, hit: bool, key: tuple[str, str]) -> None:
    _refresh_nested_filenames(result, filename)
    result["analysis_cache"] = {
        "schema": "audio-too.analysis-cache.v1",
        "hit": hit,
        "source_hash": key[0],
        "analysis_profile": key[1],
    }


def clear_analysis_cache() -> None:
    """Clear ephemeral entries; used by tests and process lifecycle hooks."""
    with _lock:
        _cache.clear()
