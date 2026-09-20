from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from ai.markov.base import BaseMarkov


_CONTOURS = ("static", "asc", "arch", "desc")


@dataclass
class ContourPlannerModel:
    """
    Phrase contour chooser conditioned on (emotion, section_role, density).

    This is intentionally lightweight: it behaves well with only hand-authored priors,
    but can be extended later to train from exported phrase-role datasets.
    """

    order: int = 2
    smoothing: float = 0.01
    rng: object = random

    def __post_init__(self) -> None:
        self._models: Dict[str, BaseMarkov] = {}
        for role in ("intro", "verse", "chorus", "bridge", "outro", "other"):
            self._models[role] = BaseMarkov(order=int(self.order), smoothing=float(self.smoothing), rng=self.rng)
        self._train_priors()

    def _train_priors(self) -> None:
        priors = {
            "intro": [
                ["static", "static", "arch", "desc"],
                ["static", "arch", "static", "desc"],
            ],
            "verse": [
                ["static", "arch", "static", "desc"],
                ["static", "static", "arch", "desc"],
                ["static", "arch", "arch", "desc"],
            ],
            "chorus": [
                ["asc", "arch", "asc", "arch"],
                ["asc", "arch", "arch", "asc"],
                ["arch", "asc", "arch", "asc"],
            ],
            "bridge": [
                ["arch", "desc", "arch", "desc"],
                ["desc", "arch", "desc", "arch"],
            ],
            "outro": [
                ["desc", "static", "desc", "static"],
                ["static", "desc", "static", "desc"],
            ],
            "other": [
                ["static", "arch", "static", "desc"],
                ["static", "static", "arch", "desc"],
                ["asc", "arch", "desc", "static"],
            ],
        }
        for role, seqs in priors.items():
            self._models[role].train([list(s) for s in seqs])

    @staticmethod
    def _role_bucket(section_role: Optional[str]) -> str:
        r = (section_role or "").strip().lower()
        if r in {"intro", "verse", "chorus", "bridge", "outro"}:
            return r
        # Common alt names
        if r in {"a", "a1", "a2"}:
            return "verse"
        if r in {"b", "hook"}:
            return "chorus"
        return "other"

    @staticmethod
    def _emotion_bucket(emotion_name: str) -> str:
        n = (emotion_name or "neutral").strip().lower()
        if n in {"grief", "sadness", "remorse", "disappointment"}:
            return "low"
        if n in {"joy", "excitement", "amusement", "optimism", "anger", "curiosity", "surprise"}:
            return "high"
        if n in {"fear", "nervousness", "confusion", "disgust"}:
            return "tense"
        return "mid"

    def next_contour(
        self,
        *,
        emotion_name: str,
        section_role: Optional[str],
        density: float = 1.0,
        history: List[str],
        temperature: float = 1.0,
    ) -> str:
        role = self._role_bucket(section_role)
        emo = self._emotion_bucket(emotion_name)
        m = self._models.get(role) or self._models["other"]
        probs = m.get_probabilities(list(history), temperature=float(temperature))
        # BaseMarkov may return a sparse dict (only symbols seen in-context).
        # Ensure all contour labels exist so downstream weighting can't KeyError.
        base = {c: 1e-6 for c in _CONTOURS}
        try:
            for k, v in dict(probs or {}).items():
                if k in base:
                    base[str(k)] = float(v)
        except Exception:
            pass
        probs = base

        d = max(0.35, min(1.75, float(density)))
        updated = dict(probs)

        # Density: higher => more rising/arch motion, lower => static/desc.
        updated["asc"] *= (0.85 + 0.85 * (d - 1.0))
        updated["arch"] *= (0.95 + 0.70 * (d - 1.0))
        updated["static"] *= (1.10 - 0.55 * (d - 1.0))
        updated["desc"] *= (1.05 - 0.35 * (d - 1.0))

        # Emotion buckets: nudge tendencies.
        if emo == "high":
            updated["asc"] *= 1.20
            updated["arch"] *= 1.12
            updated["desc"] *= 0.88
        elif emo == "low":
            updated["desc"] *= 1.20
            updated["static"] *= 1.12
            updated["asc"] *= 0.82
        elif emo == "tense":
            updated["arch"] *= 1.18
            updated["static"] *= 0.92

        total = float(sum(updated.values()))
        if total <= 0:
            return "static"
        items = sorted(updated.items(), key=lambda kv: kv[0])
        contours, weights = zip(*items)
        rng = getattr(self, "rng", None) or random
        return str(rng.choices(list(contours), weights=list(weights))[0])

