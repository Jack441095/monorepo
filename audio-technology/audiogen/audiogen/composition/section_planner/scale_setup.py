# composition/section_planner/scale_setup.py
"""Per-section global scale derivation for emotion-scale quantization."""
from __future__ import annotations

from typing import Any

from .build_context import SectionBuildSnapshot
from .observability import log_degraded


def apply_derived_global_scale(
    owner: Any,
    emotion: Any,
    root_note: int,
    snapshot: SectionBuildSnapshot,
) -> None:
    """
    Set `owner.global_scale` from emotion chord pools or scale_intervals.
    Mirrors previous `build_section` logic; no-op if quantization disabled or user scale set.
    """
    force_q = snapshot.force_emotion_scale_quantization
    derive = snapshot.derive_emotion_scale_from_chords
    user_gs = snapshot.user_global_scale_intervals
    try:
        if force_q and user_gs is None:
            if derive:
                from data.music_data import get_root

                root_pc = int(root_note) % 12
                pcs = set()
                pools = []
                pools.append(list(getattr(emotion, "chord_progressions", []) or []))
                pools.append(list(getattr(emotion, "cadence_progressions", []) or []))
                sets = getattr(emotion, "arrangement_chord_sets", None) or {}
                if isinstance(sets, dict):
                    for _role, pool in sets.items():
                        pools.append(list(pool or []))
                for pool in pools:
                    for prog in list(pool or []):
                        for sym in list(prog or []):
                            s = str(sym or "").strip()
                            if not s:
                                continue
                            try:
                                chord_root = int(root_note) + int(get_root(s))
                                notes = owner._chord_symbol_to_notes(s, int(chord_root))
                                pcs.update(int(n) % 12 for n in (notes or []) if isinstance(n, int))
                            except Exception:
                                continue
                if pcs:
                    owner.global_scale = sorted({(int(pc) - int(root_pc)) % 12 for pc in pcs})
                else:
                    owner.global_scale = list(getattr(emotion, "scale_intervals", []) or [])
            else:
                owner.global_scale = list(getattr(emotion, "scale_intervals", []) or [])
            try:
                setattr(owner, "_global_scale_is_derived", True)
            except Exception:
                pass
    except Exception as exc:
        log_degraded("apply_derived_global_scale", exc)
        pass
