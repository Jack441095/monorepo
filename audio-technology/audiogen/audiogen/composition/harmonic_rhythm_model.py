from __future__ import annotations
from audiogen_core.config import resolve_config

import random
from dataclasses import dataclass
from typing import Dict, List

from ai.markov.base import BaseMarkov


_ACTIONS = ("hold", "half", "anticipate", "sus")


@dataclass
class HarmonicRhythmModel:
    """
    Lightweight bar-level harmonic rhythm chooser.

    Produces one of: hold | half | anticipate | sus
    The caller maps these actions to chord-hit emissions.
    """

    order: int = 2
    smoothing: float = 0.01
    rng: object = random

    def __post_init__(self) -> None:
        self._models: Dict[str, BaseMarkov] = {}
        for role in ("opening", "continuation", "answer", "cadence"):
            m = BaseMarkov(order=int(self.order), smoothing=float(self.smoothing), rng=self.rng)
            self._models[role] = m
        self._train_priors()

    def _train_priors(self) -> None:
        # Hand-authored priors (small) that behave musically even without datasets.
        priors = {
            "opening": [
                ["hold", "hold", "half", "hold"],
                ["hold", "hold", "hold", "hold"],
                ["hold", "half", "hold", "hold"],
            ],
            "continuation": [
                ["half", "hold", "anticipate", "hold"],
                ["half", "hold", "half", "hold"],
                ["anticipate", "hold", "half", "hold"],
            ],
            "answer": [
                ["hold", "anticipate", "hold", "half"],
                ["half", "hold", "anticipate", "hold"],
                ["hold", "half", "anticipate", "hold"],
            ],
            "cadence": [
                ["hold", "hold", "hold", "hold"],
                ["half", "hold", "hold", "hold"],
                ["hold", "hold", "half", "hold"],
            ],
        }
        for role, seqs in priors.items():
            self._models[role].train([list(s) for s in seqs])

    @staticmethod
    def _clamp_role(role: str) -> str:
        r = (role or "").strip().lower()
        return r if r in {"opening", "continuation", "answer", "cadence"} else "continuation"

    def next_action(
        self,
        *,
        role: str,
        history: List[str],
        temperature: float = 1.0,
        bar_target: float = 1.0,
        motif_strength: float = 0.0,
        tension: float = 0.85,
        cadence_strength: float = 0.0,
        harmony_function_target: str = "",
        emotion_name: str = "",
        section_role: str = "",
        allow_sus: bool = False,
        cadence_style: str = "authentic",
    ) -> str:
        """
        bar_target (≈ chord_rhythm_target) scales rhythmic intensity:
        <1 prefers holds, >1 prefers splits/anticipations.
        """
        r = self._clamp_role(role)
        m = self._models.get(r) or self._models["continuation"]
        probs = m.get_probabilities(list(history), temperature=float(temperature))
        # BaseMarkov may return sparse dict (only symbols seen in-context).
        # Ensure all actions exist so downstream scaling can't KeyError.
        base = {a: 1e-6 for a in _ACTIONS}
        try:
            for k, v in dict(probs or {}).items():
                if k in base:
                    base[str(k)] = float(v)
        except Exception:
            pass
        updated = base

        t = max(0.45, min(1.75, float(bar_target)))
        # Intensify or relax.
        updated["hold"] *= max(0.25, 1.35 - 0.7 * (t - 1.0))
        updated["half"] *= max(0.35, 1.0 + 0.55 * (t - 1.0))
        updated["anticipate"] *= max(0.35, 1.0 + 0.75 * (t - 1.0))
        updated["sus"] *= 0.35 if not allow_sus else max(0.35, 0.9 + 0.35 * (t - 1.0))

        # Hook support: when motif strength is high, favor steadier harmonic rhythm
        # (less anticipation/sus) so the hook reads clearly against the harmony.
        try:
            ms = float(motif_strength)
        except Exception:
            ms = 0.0
        ms = max(0.0, min(1.0, ms))
        if ms > 1e-6:
            updated["hold"] *= (1.0 + 0.55 * ms)
            updated["half"] *= (1.0 + 0.20 * ms)
            updated["anticipate"] *= max(0.25, 1.0 - 0.55 * ms)
            updated["sus"] *= max(0.25, 1.0 - 0.45 * ms)

        # Tension control: clamp harmonic rhythm volatility at low tension, allow more
        # motion at high tension (but motif strength still stabilizes hooks).
        ht = resolve_config("composition", "harmony_tension", None)
        sens = float(getattr(ht, "harmonic_rhythm_sensitivity", 0.0) or 0.0) if ht is not None else 0.0
        sens = max(0.0, min(1.0, float(sens)))
        if sens > 1e-6:
            try:
                ten = float(tension)
            except Exception:
                ten = 0.85
            ten = max(0.0, min(1.35, float(ten)))
            # Normalize to 0..1-ish (where 0.85 is "mid").
            t01 = max(0.0, min(1.0, (float(ten) - 0.45) / 0.90))
            # Low tension -> steady; high tension -> allow anticipate/sus.
            steady = 1.0 + float(sens) * (0.85 - 0.55 * t01)
            motion = 1.0 + float(sens) * (0.20 + 0.80 * t01)
            updated["hold"] *= max(0.25, float(steady))
            updated["half"] *= max(0.25, 0.95 * float(steady) + 0.15 * float(motion))
            updated["anticipate"] *= max(0.20, float(motion))
            if allow_sus:
                updated["sus"] *= max(0.20, 0.85 * float(motion))

        # Phrase-intent cadence control:
        # as cadence strength rises, prefer steadier articulation over anticipations.
        try:
            cad = float(cadence_strength)
        except Exception:
            cad = 0.0
        cad = max(0.0, min(1.35, float(cad)))
        if cad > 1e-6:
            updated["hold"] *= max(0.25, 1.0 + 0.58 * float(cad))
            updated["half"] *= max(0.25, 1.0 + 0.24 * float(cad))
            updated["anticipate"] *= max(0.15, 1.0 - 0.60 * float(cad))
            updated["sus"] *= max(0.15, 1.0 - 0.50 * float(cad))

        tf = str(harmony_function_target or "").strip().upper()
        if tf == "T":
            updated["hold"] *= max(0.25, 1.18 + 0.16 * float(cad))
            updated["half"] *= max(0.20, 0.96 + 0.08 * float(cad))
            updated["anticipate"] *= 0.74
            updated["sus"] *= 0.72
        elif tf == "D":
            updated["hold"] *= 1.05
            updated["half"] *= max(0.25, 1.08 + 0.12 * float(cad))
            updated["anticipate"] *= max(0.20, 0.90 - 0.18 * float(cad))
        elif tf == "PD":
            updated["hold"] *= 0.94
            updated["half"] *= 1.10
            updated["anticipate"] *= max(0.20, 1.02 - 0.12 * float(cad))

        # Style profile bias (defaults no-op unless markov_style_strength > 0).
        from audiogen_core.composition_runtime_flags import markov_style_strength

        s = markov_style_strength()
        if s > 1e-6:
            try:
                from composition.markov_style_profiles import style_profile_for_emotion_and_role

                prof = style_profile_for_emotion_and_role(str(emotion_name or ""), str(section_role or ""))
                # 0..1: map to a motion scalar around 1.0 (lower => steadier, higher => more motion).
                allow = max(0.0, min(1.0, float(getattr(prof, "harmony_motion_allowance", 0.5) or 0.5)))
                motion = 0.85 + 0.60 * float(allow)   # 0.85..1.45
                steady = 1.55 - 0.60 * float(allow)   # 0.95..1.55
                # Blend toward profile by strength.
                motion = 1.0 + (float(motion) - 1.0) * float(s)
                steady = 1.0 + (float(steady) - 1.0) * float(s)
                updated["hold"] *= max(0.25, float(steady))
                updated["half"] *= max(0.25, 0.85 * float(steady) + 0.15 * float(motion))
                updated["anticipate"] *= max(0.20, float(motion))
                if allow_sus:
                    updated["sus"] *= max(0.20, 0.92 * float(motion))
            except Exception:
                pass

        # Cadence archetype bias:
        # - authentic: favor holds at phrase ends (clear resolution)
        # - plagal: gentle motion, slight hold bias
        # - suspended: favor sus/anticipate over hard holds
        # - avoid: de-emphasize finality; favor anticipate/half, reduce hold
        cs = (cadence_style or "authentic").strip().lower()
        if cs not in {"authentic", "plagal", "suspended", "avoid"}:
            cs = "authentic"
        # Apply most strongly when the phrase role is cadence.
        if r == "cadence":
            if cs == "authentic":
                updated["hold"] *= 1.25
                updated["anticipate"] *= 0.85
                updated["sus"] *= 0.85
            elif cs == "plagal":
                updated["hold"] *= 1.12
                updated["half"] *= 1.05
            elif cs == "suspended":
                updated["hold"] *= 0.85
                # Make the "not quite resolved yet" feel audible.
                updated["anticipate"] *= 1.85
                updated["sus"] *= (2.25 if allow_sus else 0.95)
                # Cadence priors rarely include these actions; enforce a small floor.
                updated["anticipate"] = max(updated["anticipate"], updated["hold"] * 0.06)
                if allow_sus:
                    updated["sus"] = max(updated["sus"], updated["hold"] * 0.08)
            elif cs == "avoid":
                updated["hold"] *= 0.72
                # Avoid cadence finality: more motion into the next bar.
                updated["half"] *= 1.25
                updated["anticipate"] *= 2.15
                updated["sus"] *= (1.25 if allow_sus else 0.90)
                updated["anticipate"] = max(updated["anticipate"], updated["hold"] * 0.10)
                if allow_sus:
                    updated["sus"] = max(updated["sus"], updated["hold"] * 0.06)

        total = float(sum(updated.values()))
        if total <= 0:
            return "hold"
        items = sorted(updated.items(), key=lambda kv: kv[0])
        symbols, weights = zip(*items)
        rng = getattr(self, "rng", None) or random
        return str(rng.choices(list(symbols), weights=list(weights))[0])