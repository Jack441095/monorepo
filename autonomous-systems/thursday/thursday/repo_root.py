"""Shared upward-search helpers for locating the NITE DSP monorepo root, and
the retired Audio_Too tree for the integrations that still name it.

A number of modules were written against Audio_Too's live integrations
(app.db, the Ableton bridge, Kokoro's model files under studio/kenn,
scripts/action_policy, etc). Audio_Too was removed from the monorepo on
18 Oct 2026; its last state is the tag ``archive/audio-too-final``. Most of
those integrations were already dead before that (business/ had been
renamed server/, the .venv and the audio_too package were gone), so
Thursday is parked rather than running: the modules still import, and the
calls that reach into Audio_Too fail with FileNotFoundError /
ModuleNotFoundError instead of finding a wrong path.

An upward search for the monorepo root is used instead of a fixed
``Path(__file__).parents[N]`` because this file used to exist in two copies
at different depths (Audio_Too/thursday/ and autonomous-systems/thursday/),
and a fixed index was right in only one of them.
"""

from __future__ import annotations

import os
from pathlib import Path


def nite_dsp_root() -> Path:
    """NITE_DSP_ROOT env var wins if set. Otherwise search upward from this
    file for the monorepo root (identified by containing both products/
    and autonomous-systems/; until 18 Oct 2026 the second marker was
    Audio_Too/). Bounded to 8 levels so a misconfigured environment
    fails with a clear wrong-but-findable fallback rather than walking to
    filesystem root.
    """
    configured = os.environ.get("NITE_DSP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()

    here = Path(__file__).resolve()
    for candidate in list(here.parents)[:8]:
        if (candidate / "products").is_dir() and (candidate / "autonomous-systems").is_dir():
            return candidate

    # Nothing found -- fall back to this file's own known depth
    # (autonomous-systems/thursday/thursday/repo_root.py -> parents[3]).
    # Callers will fail honestly (FileNotFoundError / ModuleNotFoundError)
    # rather than silently using a wrong path, since this guess almost
    # certainly won't contain the real monorepo layout either if the
    # search above found nothing.
    return here.parents[3]


def audio_too_root() -> Path:
    """AUDIO_TOO_ROOT env var wins if set. Otherwise Audio_Too/ inside
    nite_dsp_root(), which no longer exists after the 18 Oct 2026 removal,
    so every path built from it reports missing. To bring the legacy
    integrations back for a one-off, check out ``archive/audio-too-final``
    in a worktree and point AUDIO_TOO_ROOT at its Audio_Too/.
    """
    configured = os.environ.get("AUDIO_TOO_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    return nite_dsp_root() / "Audio_Too"


def search_upward(anchor: Path, targets: tuple[str, ...], depth: int = 8,
                   require_all: bool = False) -> Path | None:
    """Shared content-aware upward search (added 2026-09-18 to end the
    per-module `_nite_dsp_root` duplication found in the hard audit).

    qa_ops / beta_invite_ops / documentation_ops / finance_ops /
    shadow_adapters each carried their own copy of this loop with a
    per-copy `parents[N]` fallback. The loop is identical in every copy;
    only the target relative path(s) and the fallback depth differ, so
    those stay with the caller: this returns the first ancestor of
    `anchor` containing any of `targets` (file or directory), or None.
    With require_all=True (shadow_adapters' products+autonomous-systems markers)
    the ancestor must contain every target. Callers keep their own
    fallback + honest "Evidence missing" behavior. NITE_DSP_ROOT env var
    still wins when set.

    `anchor` (not this file) is the search start, so monkeypatched
    `__file__` in tests resolves from the caller's location.
    """
    configured = os.environ.get("NITE_DSP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()

    here = anchor.resolve()
    parents = [here] if here.is_dir() else list(here.parents)
    for candidate in parents[:depth]:
        hits = [(candidate / rel).exists() for rel in targets]
        if require_all and all(hits):
            return candidate
        if not require_all and any(hits):
            return candidate
    return None
