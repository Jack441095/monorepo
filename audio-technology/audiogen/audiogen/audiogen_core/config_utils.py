# core/config_utils.py
# ---------------------------------------------------------------------------
# Lightweight CONFIG accessor helpers.
#
# Replaces the 5-line try/except boilerplate that appears 200+ times:
#
#     try:
#         from audiogen_core.config import CONFIG
#         value = float(getattr(CONFIG.composition, "knob", 0.7) or 0.7)
#     except Exception:
#         value = 0.7
#
# Usage:
#     from audiogen_core.config_utils import cfg
#
#     value = cfg("composition.knob", float, 0.7)
#     enabled = cfg("composition.feature_enabled", bool, True)
# ---------------------------------------------------------------------------
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

T = TypeVar("T")

# Sentinel to distinguish "no default" from None.
_MISSING = object()


def cfg(path: str, cast: type[T], default: T) -> T:
    """Read a CONFIG attribute safely with type coercion.

    Parameters
    ----------
    path : str
        Dot-separated attribute path rooted at CONFIG, e.g.
        ``"composition.melody_style"`` reads ``CONFIG.composition.melody_style``.
    cast : type
        Target type — one of ``int``, ``float``, ``str``, ``bool``.
    default : T
        Fallback value when the attribute is missing, CONFIG fails to import,
        or the raw value is ``None``.

    Returns
    -------
    T
        The resolved value coerced to *cast*, or *default* on any failure.

    Notes
    -----
    * Unlike the old ``getattr(..., default) or default`` idiom, this treats
      ``0``, ``0.0``, ``False``, and ``""`` as legitimate values (not missing).
      Only ``None`` triggers the fallback.
    * Import errors are logged at DEBUG level on first occurrence so they
      don't get swallowed silently.
    """
    try:
        from audiogen_core.config import CONFIG  # type: ignore[import]

        obj: Any = CONFIG
        for part in path.split("."):
            obj = getattr(obj, part, _MISSING)
            if obj is _MISSING:
                return default

        # None means "not set" → use default; otherwise cast.
        if obj is None:
            return default

        # Bool must be checked before int (bool is a subclass of int in Python).
        if cast is bool:
            return cast(obj)  # type: ignore[return-value]
        return cast(obj)  # type: ignore[return-value]

    except ImportError:
        logger.debug("CONFIG import unavailable (path=%s), using default=%r", path, default)
        return default
    except Exception:
        logger.debug("Failed to read CONFIG.%s, using default=%r", path, default, exc_info=True)
        return default


def cfg_optional(path: str, cast: type[T]) -> T | None:
    """Like :func:`cfg` but returns ``None`` when the attribute is absent.

    Useful for optional paths where ``None`` is a valid "not configured" signal.
    """
    try:
        from audiogen_core.config import CONFIG  # type: ignore[import]

        obj: Any = CONFIG
        for part in path.split("."):
            obj = getattr(obj, part, _MISSING)
            if obj is _MISSING:
                return None

        if obj is None:
            return None
        return cast(obj)

    except Exception:
        return None


def project_path(*parts: str | Path) -> Path:
    """Return an absolute path inside the AudioGen project root."""
    return PROJECT_ROOT.joinpath(*(Path(str(part)) for part in parts))


def resolve_project_path(path: str | Path) -> Path:
    """Resolve a user/config path relative to the AudioGen project root.

    Absolute paths and ``~`` paths keep their normal meaning. Existing plain
    relative paths are honored from the caller's current working directory so
    ad hoc sample packs still work. Non-existing relative paths are interpreted
    relative to ``LLM_AudioGen`` so built-in assets and outputs do not depend on
    the launch directory.
    """
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    if p.exists():
        return p.resolve()
    return PROJECT_ROOT / p
