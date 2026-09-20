from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_ROMAN_RE = re.compile(r"^([#b]?)([ivIV]+)")


@dataclass(frozen=True)
class ChordToken:
    """
    Lightweight, stable chord token for Markov / corpus use.

    This intentionally avoids heavy parsing in hot paths. We only extract:
    - `degree`: roman degree when present (e.g. 'bVII', 'iv', '#V'), else None
    - `bucket`: simplified bucket ('maj'|'min'|'dom'|'dim'|'aug'|'sus')
    """

    bucket: str
    degree: Optional[str] = None

    def serialize(self, *, use_degree: bool) -> str:
        if use_degree and self.degree:
            return f"{self.degree}:{self.bucket}"
        return str(self.bucket or "")

    def bucketize(self) -> str:
        return str(self.bucket or "")

    @staticmethod
    def token_bucket(token: str) -> str:
        t = str(token or "").strip()
        if ":" in t:
            return t.split(":", 1)[1].strip() or t
        return t

    @staticmethod
    def token_degree(token: str) -> str:
        t = str(token or "").strip()
        if ":" in t:
            return t.split(":", 1)[0].strip()
        return ""

    @classmethod
    def from_symbol(cls, chord_symbol: str, *, bucket: str) -> "ChordToken":
        s = str(chord_symbol or "").strip()
        deg = None
        m = _ROMAN_RE.match(s)
        if m:
            acc, nums = m.groups()
            # Preserve accidental as-is ('b'/'#') and preserve numeral case (i vs I).
            deg = f"{acc}{nums}"
        return cls(bucket=str(bucket or ""), degree=(str(deg) if deg else None))

