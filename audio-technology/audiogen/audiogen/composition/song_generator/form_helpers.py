# composition/song_generator/form_helpers.py
# Leaf helpers shared by the arrangement-form generators in `forms.py`:
# emotion-arc coloring, root-motion arcs, per-role melody density targets,
# and bar-count scaling. No dependency on any other song_generator mixin.

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from audiogen_core.config import resolve_config
from data.emotion_aliases import canonical_emotion_name

from ..policies import ArrangementPolicy
from .models import SongSectionSpec


class FormHelpersMixin:
    """Emotion-arc, root-motion, and density-target helpers used by form generators."""

    @classmethod
    def _apply_emotion_arc(
        cls,
        base_emotion_name: str,
        arrangement_form: str,
        specs: Sequence[SongSectionSpec],
    ) -> List[SongSectionSpec]:
        """Apply the user-selected emotion to every section (no role-based arc coloring).

        Section contrast comes from arrangement roles (intro/verse/chorus), density curves,
        and root motion — not from swapping to adjacent emotions per section.
        """
        _ = arrangement_form  # retained for call-site compatibility across forms
        base = canonical_emotion_name(base_emotion_name)
        if not specs:
            return []
        return [
            SongSectionSpec(
                emotion_name=str(base),
                bars=int(spec.bars),
                root_note=int(spec.root_note),
                temperature=float(spec.temperature),
                target_notes_per_bar=float(spec.target_notes_per_bar),
                melody_style=str(spec.melody_style),
            )
            for spec in (specs or [])
        ]

    @staticmethod
    def _apply_root_motion_arc(
        arrangement_form: str,
        specs: Sequence[SongSectionSpec],
    ) -> List[SongSectionSpec]:
        seq = ArrangementPolicy._FORM_SEQUENCES.get(arrangement_form) or ArrangementPolicy._FORM_SEQUENCES["default"]
        if not specs:
            return []

        base_root = int(specs[0].root_note)
        current_root = base_root
        out: List[SongSectionSpec] = []
        role_counts: Dict[str, int] = {}
        for idx, spec in enumerate(specs):
            role = seq[idx] if idx < len(seq) else seq[-1]
            prev_role = seq[idx - 1] if idx > 0 and (idx - 1) < len(seq) else ""
            role_counts[role] = int(role_counts.get(role, 0)) + 1
            occurrence = int(role_counts[role])
            if idx == 0:
                current_root = base_root
            elif role == "pre_chorus":
                # Keep the lift audible, but avoid the old +5 "gear shift" that could
                # make verse -> pre and pre -> chorus transitions feel too abrupt.
                if arrangement_form in {"default", "swing", "pop", "pop_ext"}:
                    current_root = base_root + 2
                else:
                    current_root = base_root + 5
            elif role == "b":
                # In verse/pre/chorus forms, keep the chorus on the lifted pre-chorus root
                # instead of snapping straight back to tonic. This reads as a smoother
                # arrival while the section contrast comes from density/register/arp.
                if arrangement_form in {"default", "swing", "pop", "pop_ext"} and prev_role == "pre_chorus":
                    current_root = current_root
                elif arrangement_form in {"default", "swing", "pop", "pop_ext"} and occurrence >= 2:
                    current_root = base_root + 2
                else:
                    current_root = base_root
            elif role == "a_prime":
                current_root = base_root + 2
            elif role == "tag":
                current_root = base_root + 7
            elif role == "outro":
                current_root = base_root
            elif role == "a" and idx > 0:
                if arrangement_form in {"default", "swing"} and occurrence >= 2:
                    # Second verse gets a darker submediant turn. It creates long-form
                    # harmonic development without breaking the familiar chorus lift.
                    current_root = base_root - 3
                else:
                    current_root = base_root

            out.append(
                SongSectionSpec(
                    emotion_name=str(spec.emotion_name),
                    bars=int(spec.bars),
                    root_note=int(current_root),
                    temperature=float(spec.temperature),
                    target_notes_per_bar=float(spec.target_notes_per_bar),
                    melody_style=str(spec.melody_style),
                )
            )

        # Optional late-song modulation / lift (highest risk; guarded + deterministic).
        # A small upward shift into the final chorus can reduce sameness without randomness.
        mod_enabled = resolve_config("composition", "modulation_enabled", True, bool)
        lift = resolve_config("composition", "modulation_lift_semitones", 2, int)
        prob = resolve_config("composition", "modulation_probability", 0.35, float)
        prob = max(0.0, min(1.0, float(prob)))
        lift = int(max(-5, min(7, int(lift))))
        if mod_enabled and lift != 0 and prob > 1e-6 and arrangement_form in {"default", "dialogue (call and response)", "swing"}:
            try:
                # Deterministic decision so arranged previews/songs are repeatable.
                import random as _rnd

                rr = _rnd.Random(int(base_root) * 1009 + len(out) * 917 + (1 if arrangement_form == "default" else 3))
                if rr.random() < float(prob):
                    idx_last_b = None
                    for i in range(len(out) - 1, -1, -1):
                        role = seq[i] if i < len(seq) else seq[-1]
                        if role == "b":
                            idx_last_b = i
                            break
                    if idx_last_b is not None and idx_last_b >= 1:
                        # Apply lift to final chorus and any immediate tag following it.
                        for j in range(int(idx_last_b), min(len(out), int(idx_last_b) + 2)):
                            role = seq[j] if j < len(seq) else seq[-1]
                            if role not in {"b", "tag"}:
                                continue
                            spec0 = out[j]
                            new_root = int(spec0.root_note) + int(lift)
                            # Guardrail: keep in a sane musical register.
                            if 36 <= int(new_root) <= 84:
                                out[j] = SongSectionSpec(
                                    emotion_name=str(spec0.emotion_name),
                                    bars=int(spec0.bars),
                                    root_note=int(new_root),
                                    temperature=float(spec0.temperature),
                                    target_notes_per_bar=float(spec0.target_notes_per_bar),
                                    melody_style=str(spec0.melody_style),
                                )
            except Exception:
                pass
        return out

    @staticmethod
    def _default_form_role_targets(emotion_name: str) -> Tuple[float, float, float, float, float, float, float]:
        """Role melody targets tuned from full-song audits for ambient-pop pacing."""

        name = canonical_emotion_name(emotion_name)
        targets = [3.8, 5.0, 5.7, 6.4, 4.7, 6.6, 3.0]
        if name in {"sadness", "grief", "remorse", "relief", "disappointment", "caring"}:
            targets = [3.2, 4.2, 4.9, 5.7, 3.9, 5.9, 2.6]
        elif name in {"confusion", "curiosity", "embarrassment", "nervousness", "fear"}:
            targets = [3.5, 4.7, 5.5, 6.1, 4.4, 6.2, 2.8]
        elif name in {"joy", "amusement", "excitement", "pride", "optimism", "approval"}:
            targets = [4.0, 5.4, 6.1, 7.0, 5.1, 7.2, 3.2]
        return tuple(float(x) for x in targets)  # type: ignore[return-value]

    @staticmethod
    def _bars_scaled(base: int, mult: float, minimum: int = 4) -> int:
        return max(minimum, int(round(float(base) * mult)))
