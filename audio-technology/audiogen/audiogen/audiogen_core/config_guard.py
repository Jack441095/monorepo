from __future__ import annotations

import inspect
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional


logger = logging.getLogger(__name__)

_ALLOW_MUTATIONS: ContextVar[bool] = ContextVar("_ALLOW_MUTATIONS", default=False)


@contextmanager
def allow_config_mutations(reason: str = ""):
    tok = _ALLOW_MUTATIONS.set(True)
    try:
        yield
    finally:
        _ALLOW_MUTATIONS.reset(tok)


def _callsite(max_frames: int = 12) -> str:
    try:
        st = inspect.stack()
        # skip: _callsite, _warn, __setattr__
        for fr in st[3 : 3 + max_frames]:
            fn = fr.filename.replace("\\", "/")
            if "/.venv" in fn or "/site-packages/" in fn:
                continue
            return f"{fn}:{fr.lineno} in {fr.function}"
    except Exception:
        pass
    return "unknown"


class GuardProxy:
    """
    Warn-only proxy that logs mutations when not in an allowed context.
    Use by wrapping CONFIG.audio/CONFIG.composition/CONFIG.ai in service mode.
    """

    def __init__(self, obj: Any, *, path: str, warn_only: bool = True):
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_path", str(path))
        object.__setattr__(self, "_warn_only", bool(warn_only))

    def __getattr__(self, item: str) -> Any:
        return getattr(object.__getattribute__(self, "_obj"), item)

    def __setattr__(self, key: str, value: Any) -> None:
        obj = object.__getattribute__(self, "_obj")
        path = object.__getattribute__(self, "_path")
        warn_only = bool(object.__getattribute__(self, "_warn_only"))

        if not bool(_ALLOW_MUTATIONS.get()):
            before: Optional[Any] = None
            try:
                before = getattr(obj, key)
            except Exception:
                before = None
            msg = f"CONFIG drift: {path}.{key} {before!r} -> {value!r} @ {_callsite()}"
            if warn_only:
                logger.warning(msg)
            else:
                raise RuntimeError(msg)
        setattr(obj, key, value)

    def __repr__(self) -> str:  # pragma: no cover
        return f"GuardProxy({object.__getattribute__(self, '_path')})"


def enable_config_guard(config: Any, *, warn_only: bool = True) -> None:
    """Wrap CONFIG sub-objects with GuardProxy."""
    try:
        config.audio = GuardProxy(getattr(config, "audio"), path="audio", warn_only=warn_only)
    except Exception:
        pass
    try:
        config.composition = GuardProxy(getattr(config, "composition"), path="composition", warn_only=warn_only)
    except Exception:
        pass
    try:
        config.ai = GuardProxy(getattr(config, "ai"), path="ai", warn_only=warn_only)
    except Exception:
        pass

