"""Shared upward-search helpers for locating the NITE DSP monorepo root and
Audio_Too within it.

A number of modules need Audio_Too's real, live integrations (app.db, the
Ableton bridge, Kokoro's model files under studio/kenn, scripts/
action_policy, etc). Historically each computed that path itself with a
fixed ``Path(__file__).resolve().parent.parent`` -- correct only by
coincidence, because Audio_Too/thursday/X.py's parent.parent happens to
equal Audio_Too/. This extraction (autonomous-systems/thursday) lives one
level deeper AND is a *sibling* of Audio_Too, not an ancestor -- no amount
of ".parent" from here ever reaches it. An upward search for the shared
NITE_DSP root (same pattern as thursday.shadow_adapters._nite_dsp_root())
is the only fix that's correct unmodified from both copies, which is what
lets this file be identical in Audio_Too/thursday/ and here rather than
needing a per-copy fallback-depth divergence like the ops/ modules.
"""

from __future__ import annotations

import os
from pathlib import Path


def nite_dsp_root() -> Path:
    """NITE_DSP_ROOT env var wins if set. Otherwise search upward from this
    file for the monorepo root (identified by containing both Audio_Too/
    and products/). Bounded to 8 levels so a misconfigured environment
    fails with a clear wrong-but-findable fallback rather than walking to
    filesystem root.
    """
    configured = os.environ.get("NITE_DSP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()

    here = Path(__file__).resolve()
    for candidate in list(here.parents)[:8]:
        if (candidate / "Audio_Too").is_dir() and (candidate / "products").is_dir():
            return candidate

    # Nothing found -- fall back to this file's own known depth in
    # Audio_Too/thursday/ (parents[1]). Callers relying on real Audio_Too
    # integrations will fail honestly (FileNotFoundError / ModuleNotFoundError)
    # rather than silently using a wrong path, since this guess almost
    # certainly won't contain the real monorepo layout either if the
    # search above found nothing.
    return here.parents[1]


def audio_too_root() -> Path:
    """AUDIO_TOO_ROOT env var wins if set. Otherwise Audio_Too/ inside
    nite_dsp_root().
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
    With require_all=True (shadow_adapters' Audio_Too+products markers)
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
