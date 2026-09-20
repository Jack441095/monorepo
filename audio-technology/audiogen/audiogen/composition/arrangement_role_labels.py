"""Human-readable labels for arrangement section roles (logging / UI)."""

from __future__ import annotations

ARRANGEMENT_ROLE_LABELS: dict[str, str] = {
    "intro": "INTRO",
    "a": "VERSE (A)",
    "pre_chorus": "PRE-CHORUS",
    "b": "CHORUS (B)",
    "tag": "TAG",
    "a_prime": "A' (RETURN)",
    "outro": "OUTRO",
}


def arrangement_role_display_name(role: str) -> str:
    r = (role or "").strip().lower()
    return ARRANGEMENT_ROLE_LABELS.get(r, (role or "").upper() if role else "")
