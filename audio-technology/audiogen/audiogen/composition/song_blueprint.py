from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence
from .policies import ArrangementPolicy


@dataclass(frozen=True)
class SectionBlueprint:
    section_index: int
    section_role: str
    motif_stage: str
    cadence_style: str
    cadence_strength_mult: float
    target_register_offset: int
    target_tension: float
    layer_contract: Dict[str, float] = field(default_factory=dict)
    harmony_function_hint: str = ""


@dataclass(frozen=True)
class SongBlueprint:
    form_mode: str
    sections: List[SectionBlueprint]

    def for_section(self, section_index: int) -> SectionBlueprint | None:
        i = int(section_index)
        if 0 <= i < len(self.sections):
            return self.sections[i]
        return None


def _motif_stage_for_role(role: str, section_index: int, section_count: int) -> str:
    r = str(role or "").strip().lower()
    n = max(1, int(section_count))
    i = max(0, min(n - 1, int(section_index)))
    if r in {"intro"}:
        return "introduce"
    if r in {"a", "verse"}:
        return "state" if i <= 1 else "develop"
    if r in {"pre_chorus"}:
        return "build"
    if r in {"b", "chorus", "hook"}:
        return "payoff" if i >= max(1, n - 3) else "restate"
    if r in {"a_prime", "bridge"}:
        return "contrast"
    if r in {"tag"}:
        return "restate"
    if r in {"outro", "ending"}:
        return "fragment"
    return "develop"


def _cadence_style_for_role(role: str) -> str:
    r = str(role or "").strip().lower()
    if r in {"pre_chorus"}:
        return "open"
    if r in {"b", "chorus", "hook", "tag", "outro", "ending"}:
        return "closed"
    if r in {"a_prime", "bridge"}:
        return "deceptive"
    return "authentic"


def _layer_contract_for_role(role: str) -> Dict[str, float]:
    r = str(role or "").strip().lower()
    return {
        "intro": {"bass": 0.62, "chords": 0.86, "melody": 0.78, "arp": 0.52, "counter": 0.22},
        "a": {"bass": 0.84, "chords": 0.88, "melody": 0.90, "arp": 0.64, "counter": 0.40},
        "verse": {"bass": 0.84, "chords": 0.88, "melody": 0.90, "arp": 0.64, "counter": 0.40},
        "pre_chorus": {"bass": 0.92, "chords": 0.86, "melody": 0.80, "arp": 0.90, "counter": 0.54},
        "b": {"bass": 0.96, "chords": 0.92, "melody": 0.88, "arp": 1.00, "counter": 0.72},
        "chorus": {"bass": 0.96, "chords": 0.92, "melody": 0.88, "arp": 1.00, "counter": 0.72},
        "hook": {"bass": 0.96, "chords": 0.92, "melody": 0.88, "arp": 1.00, "counter": 0.72},
        "a_prime": {"bass": 0.90, "chords": 0.92, "melody": 0.84, "arp": 0.82, "counter": 0.58},
        "tag": {"bass": 0.90, "chords": 0.84, "melody": 0.82, "arp": 0.84, "counter": 0.64},
        "outro": {"bass": 0.60, "chords": 0.74, "melody": 0.52, "arp": 0.34, "counter": 0.18},
        "ending": {"bass": 0.60, "chords": 0.74, "melody": 0.52, "arp": 0.34, "counter": 0.18},
    }.get(r, {"bass": 0.85, "chords": 0.85, "melody": 0.80, "arp": 0.70, "counter": 0.45})


def _register_offset_for_role(role: str) -> int:
    r = str(role or "").strip().lower()
    return {
        "intro": -2,
        "a": 0,
        "verse": 0,
        "pre_chorus": 2,
        "b": 4,
        "chorus": 4,
        "hook": 4,
        "a_prime": 2,
        "tag": 3,
        "outro": -4,
        "ending": -4,
    }.get(r, 0)


def _target_tension_for_role(role: str) -> float:
    r = str(role or "").strip().lower()
    return {
        "intro": 0.34,
        "a": 0.52,
        "verse": 0.52,
        "pre_chorus": 0.76,
        "b": 0.88,
        "chorus": 0.88,
        "hook": 0.90,
        "a_prime": 0.74,
        "tag": 0.80,
        "outro": 0.38,
        "ending": 0.32,
    }.get(r, 0.60)


def _harmony_hint_for_role(role: str) -> str:
    r = str(role or "").strip().lower()
    return {
        "intro": "T",
        "a": "PD",
        "verse": "PD",
        "pre_chorus": "D",
        "b": "T",
        "chorus": "T",
        "hook": "T",
        "a_prime": "PD",
        "tag": "D",
        "outro": "T",
        "ending": "T",
    }.get(r, "PD")


def build_song_blueprint(
    sections: Sequence[Any],
    *,
    form_mode: str,
) -> SongBlueprint:
    seq = ArrangementPolicy._FORM_SEQUENCES.get(str(form_mode or "")) or ArrangementPolicy._FORM_SEQUENCES["default"]
    out: List[SectionBlueprint] = []
    n = max(1, len(list(sections or [])))
    for i, _spec in enumerate(list(sections or [])):
        role = str(seq[i] if i < len(seq) else (seq[-1] if seq else "a"))
        cad = _cadence_style_for_role(role)
        out.append(
            SectionBlueprint(
                section_index=int(i),
                section_role=str(role),
                motif_stage=_motif_stage_for_role(role, i, n),
                cadence_style=str(cad),
                cadence_strength_mult=(
                    1.18
                    if cad in {"closed", "authentic"}
                    else (0.90 if cad in {"open"} else (0.96 if cad in {"deceptive"} else 1.0))
                ),
                target_register_offset=int(_register_offset_for_role(role)),
                target_tension=float(_target_tension_for_role(role)),
                layer_contract=dict(_layer_contract_for_role(role)),
                harmony_function_hint=str(_harmony_hint_for_role(role)),
            )
        )
    return SongBlueprint(form_mode=str(form_mode or "default"), sections=out)
