from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _clip(x: float, lo: float, hi: float) -> float:
    v = _f(x, 0.0)
    return float(lo if v < lo else hi if v > hi else v)


def _s(x: Any) -> str:
    try:
        return str(x)
    except Exception:
        return ""


@dataclass(frozen=True)
class AuditIssue:
    kind: str
    where: str
    message: str
    severity: str = "warn"  # info|warn|error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": str(self.kind),
            "where": str(self.where),
            "message": str(self.message),
            "severity": str(self.severity),
        }


def normalize_progression(prog: Iterable[Any]) -> List[str]:
    out: List[str] = []
    for ch in list(prog or []):
        s = _s(ch).strip()
        if not s:
            continue
        # Normalize some accidental dataset artifacts.
        s = s.replace(" ", "")
        # Common unicode degree symbols to ascii-ish tokens
        s = s.replace("°", "dim").replace("ø", "dim")
        out.append(s)
    return out


def normalize_progression_pool(pool: Iterable[Iterable[Any]]) -> List[List[str]]:
    out: List[List[str]] = []
    for prog in list(pool or []):
        p = normalize_progression(prog)
        if len(p) >= 2:
            out.append(p)
    return out


def _token_counts(chord_or_prog_text: str) -> Dict[str, int]:
    """
    Lightweight lexical counts used for "pop readability" heuristics.
    We intentionally do not attempt full functional analysis here; the dataset uses
    roman-ish symbols and extension tags.
    """
    t = (str(chord_or_prog_text or "")).lower()
    return {
        "bii": t.count("bii"),
        "borrowed": t.count("bii") + t.count("biii") + t.count("bvi") + t.count("bvii") + t.count("#iv") + t.count("#v"),
        "dim": t.count("dim") + t.count("°") + t.count("ø"),
        "aug": t.count("aug") + t.count("+"),
        "altered9": t.count("b9") + t.count("#9"),
        "sharp11": t.count("#11"),
        "sus": t.count("sus"),
        "maj_ext": t.count("maj9") + t.count("maj13") + t.count("6/9") + t.count("69") + t.count("add9"),
        "min_ext": t.count("min9") + t.count("min11") + t.count("min13") + t.count("min69") + t.count("min6"),
    }


def _tension_score_from_counts(c: Dict[str, int]) -> float:
    # Tuned for pop: borrowed colors are allowed, but bII/dim/aug/altered9 are "strong signals".
    return float(
        1.25 * c.get("bii", 0)
        + 0.9 * c.get("dim", 0)
        + 0.75 * c.get("aug", 0)
        + 0.55 * c.get("altered9", 0)
        + 0.25 * c.get("sharp11", 0)
    )


def _closest_mode_name(scale_intervals: Iterable[int]) -> Tuple[str, float]:
    """
    Return (mode_name, similarity) where similarity is 0..1 (1 = exact match).
    Matches against SCALES_AND_MODES in data/music_theory.
    """
    try:
        from data.music_theory import SCALES_AND_MODES
    except Exception:
        return ("<unknown>", 0.0)
    target = sorted({int(x) % 12 for x in (list(scale_intervals or []))})
    if not target:
        return ("<unknown>", 0.0)
    best = ("<unknown>", 0.0)
    tgt = set(target)
    for name, meta in dict(SCALES_AND_MODES or {}).items():
        ints = sorted({int(x) % 12 for x in (meta.get("intervals") or [])})
        if not ints:
            continue
        s = set(ints)
        inter = len(tgt & s)
        union = len(tgt | s)
        sim = float(inter / max(1, union))
        if sim > best[1]:
            best = (str(name), sim)
    return best


def _scale_conflict_rate_for_pool(
    pool: Iterable[Iterable[Any]],
    *,
    scale_intervals: Iterable[int],
) -> float:
    """
    Estimate how often chord tones fall outside the emotion scale (0..1).
    This matters because runtime may quantize notes to the scale.
    """
    try:
        from data.chord_parser import chord_symbol_to_intervals, parse_chord_symbol
        from data.music_theory import ROMAN_TO_SCALE_DEGREE
    except Exception:
        return 0.0
    scale_list = [int(x) % 12 for x in (list(scale_intervals or []))]
    scale = set(scale_list)
    if not scale or not scale_list:
        return 0.0

    def _roman_root_pc(sym: str) -> Optional[int]:
        """
        Compute roman root pitch-class using the emotion's own scale_intervals.
        This avoids the "major-only" roman-to-semitone mapping which incorrectly
        flags natural-minor VII, etc.
        """
        try:
            parsed = parse_chord_symbol(str(sym))
        except Exception:
            return None
        try:
            if not bool(parsed.is_roman()):
                return None
        except Exception:
            return None
        root = str(getattr(parsed, "root", "") or "").strip()
        if not root:
            return None
        accidental = ""
        numerals = root
        if root[0] in ("b", "#"):
            accidental = root[0]
            numerals = root[1:]
        numerals = numerals.upper()
        deg = ROMAN_TO_SCALE_DEGREE.get((accidental + numerals), None)
        if deg is None:
            # Try without accidental for safety.
            deg = ROMAN_TO_SCALE_DEGREE.get(numerals, None)
        if deg is None:
            return None
        base = int(scale_list[int(deg) % len(scale_list)]) % 12
        if accidental == "b":
            base = (base - 1) % 12
        elif accidental == "#":
            base = (base + 1) % 12
        return int(base)
    total = 0
    out = 0
    for prog in list(pool or []):
        p = normalize_progression(prog)
        for sym in p:
            try:
                root_pc = _roman_root_pc(str(sym))
                if root_pc is None:
                    # Non-roman or unparseable: assume tonic-relative 0 (best-effort).
                    root_pc = 0
                ints = [int(i) % 12 for i in chord_symbol_to_intervals(str(sym))]
            except Exception:
                continue
            pcs = {(int(root_pc) + i) % 12 for i in ints}
            for pc in pcs:
                total += 1
                if pc not in scale:
                    out += 1
    return float(out / max(1, total))


def emotion_harmony_metrics(emotion: Any) -> Dict[str, Any]:
    """
    Compute a compact set of harmony metrics for an EmotionProfile-like object.
    This is designed for human QA and lightweight regression tests.
    """
    name = (_s(getattr(emotion, "name", "")) or "").strip().lower() or "<unknown>"
    pool = getattr(emotion, "chord_progressions", None) or []
    cads = getattr(emotion, "cadence_progressions", None) or []
    scale_intervals = getattr(emotion, "scale_intervals", None) or []

    mode, mode_sim = _closest_mode_name(scale_intervals)
    tonic_rate = tonic_end_rate(pool)
    cadence_tonic_rate = tonic_end_rate(cads)
    scale_conflict = _scale_conflict_rate_for_pool(pool, scale_intervals=scale_intervals)

    # Pop readability metrics (counts per chord symbol tokenization).
    chord_txt = " ".join(" ".join(normalize_progression(p)) for p in list(pool or []))
    counts = _token_counts(chord_txt)
    tension = _tension_score_from_counts(counts)
    n_chords = max(1, len([ch for prog in list(pool or []) for ch in normalize_progression(prog)]))

    # Normalize tension to "per 16 chords" so budgets are easier to interpret.
    tension_per_16 = float(tension * (16.0 / float(n_chords)))

    return {
        "name": name,
        "mode": mode,
        "mode_similarity": float(mode_sim),
        "tonic_end_rate": float(tonic_rate),
        "cadence_tonic_end_rate": float(cadence_tonic_rate),
        "scale_conflict_rate": float(scale_conflict),
        "tension_per_16_chords": float(tension_per_16),
        "token_counts": dict(counts),
    }


def _pop_budget_for_emotion(name: str) -> Dict[str, float]:
    """
    Pop/EDM-oriented heuristic budgets. These are intentionally soft; they trigger warnings,
    not hard errors (tests can assert looser thresholds for non-core emotions).
    """
    n = (name or "").strip().lower()
    ultra_tense = n in {"fear", "disgust"}
    # Tense emotions may tolerate more out-of-scale tones (alterations, dim).
    tense = n in {"anger", "fear", "nervousness", "disgust", "confusion", "surprise", "annoyance", "disapproval"}
    sad = n in {"sadness", "grief", "remorse", "disappointment", "embarrassment"}
    bright = n in {"joy", "excitement", "amusement", "optimism", "pride", "approval"}
    warm = n in {"love", "gratitude", "caring", "admiration", "relief"}

    # These are "warn" thresholds.
    #
    # Note: the in-repo emotion datasets include several mode-forward palettes
    # (e.g. dorian/lydian/whole-tone) that intentionally exceed stricter pop
    # heuristics. Keep budgets loose enough that the audit remains a *typo / empty
    # pool* safety net rather than a creative constraint.
    max_scale_conflict = 0.20 if bright or warm else 0.22 if sad else 0.45 if tense else 0.30
    # Fear/disgust are intentionally extreme even in pop; allow higher tension without failing the audit.
    max_tension_per_16 = 11.0 if ultra_tense else 6.0 if tense else 3.6 if sad else 3.0 if bright else 3.2
    min_tonic_auth = 0.22  # authentic should have some tonic endings available
    max_tonic_avoid = 0.45
    return {
        "max_scale_conflict_rate": float(max_scale_conflict),
        "max_tension_per_16_chords": float(max_tension_per_16),
        "min_tonic_end_rate_for_authentic": float(min_tonic_auth),
        "max_tonic_end_rate_for_avoid": float(max_tonic_avoid),
    }


def audit_progression_pool(pool: Iterable[Iterable[Any]], *, where: str) -> List[AuditIssue]:
    issues: List[AuditIssue] = []
    pool_n = list(pool or [])
    if not pool_n:
        issues.append(AuditIssue("empty_pool", where, "Progression pool is empty", severity="error"))
        return issues
    for i, prog in enumerate(pool_n):
        p = normalize_progression(prog)
        if len(p) < 2:
            issues.append(AuditIssue("short_progression", f"{where}[{i}]", f"Too short: {p!r}"))
            continue
        txt = " ".join(p).lower()
        # Aggressive harmonic tokens that can dominate output if overrepresented.
        t = 0
        t += txt.count("bii")
        t += txt.count("dim") + txt.count("aug") + txt.count("+")
        t += txt.count("b9") + txt.count("#9")
        if t >= 5:
            issues.append(
                AuditIssue(
                    "high_tension_progression",
                    f"{where}[{i}]",
                    f"Many tension tokens ({t}): {p!r}",
                )
            )
    return issues


def tonic_end_rate(pool: Iterable[Iterable[Any]]) -> float:
    """
    Fraction of progressions whose final chord looks like a tonic function (I/i…).
    This is a lightweight proxy for “resolution / closure” useful for emotion QA.
    """
    pool_n = list(pool or [])
    total = 0
    tonic = 0
    for prog in pool_n:
        p = normalize_progression(prog)
        if len(p) < 2:
            continue
        total += 1
        last = (p[-1] or "").strip()
        if last.startswith("I") or last.startswith("i"):
            tonic += 1
    return float(tonic / max(1, total))


def normalize_emotion_scalars(emotion: Any) -> Tuple[float, float, float]:
    """Return (tempo_mult, velocity_mult, density) after safe clamping."""
    try:
        from audiogen_core.config import CONFIG

        lo_t = float(getattr(CONFIG.composition, "data_clamp_tempo_mult_min", 0.35))
        hi_t = float(getattr(CONFIG.composition, "data_clamp_tempo_mult_max", 2.0))
        lo_d = float(getattr(CONFIG.composition, "data_clamp_density_min", 0.15))
        hi_d = float(getattr(CONFIG.composition, "data_clamp_density_max", 1.0))
    except Exception:
        lo_t, hi_t, lo_d, hi_d = 0.35, 2.0, 0.15, 1.0
    tempo = _clip(_f(getattr(emotion, "tempo_multiplier", 1.0), 1.0), lo_t, hi_t)
    vel = _clip(_f(getattr(emotion, "velocity_multiplier", 1.0), 1.0), 0.50, 1.50)
    dens = _clip(_f(getattr(emotion, "density", 0.5), 0.5), lo_d, hi_d)
    return tempo, vel, dens


def normalize_arrangement_curve(curve: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp curve scalars to prevent outlier data from causing harsh output."""
    c = dict(curve or {})
    try:
        from audiogen_core.config import CONFIG

        cm0 = float(getattr(CONFIG.composition, "data_curve_clamp_chord_motion_min", 0.70))
        cm1 = float(getattr(CONFIG.composition, "data_curve_clamp_chord_motion_max", 1.45))
        cr0 = float(getattr(CONFIG.composition, "data_curve_clamp_chord_rhythm_min", 0.75))
        cr1 = float(getattr(CONFIG.composition, "data_curve_clamp_chord_rhythm_max", 1.35))
        md0 = float(getattr(CONFIG.composition, "data_curve_clamp_melody_density_min", 0.45))
        md1 = float(getattr(CONFIG.composition, "data_curve_clamp_melody_density_max", 1.55))
        ad0 = float(getattr(CONFIG.composition, "data_curve_clamp_arp_density_min", 0.0))
        ad1 = float(getattr(CONFIG.composition, "data_curve_clamp_arp_density_max", 1.65))
        sd0 = float(getattr(CONFIG.composition, "data_curve_clamp_section_dynamic_min", 0.85))
        sd1 = float(getattr(CONFIG.composition, "data_curve_clamp_section_dynamic_max", 1.12))
    except Exception:
        cm0, cm1, cr0, cr1, md0, md1, ad0, ad1, sd0, sd1 = 0.70, 1.45, 0.75, 1.35, 0.45, 1.55, 0.0, 1.65, 0.85, 1.12

    if "chord_motion_mult" in c:
        c["chord_motion_mult"] = _clip(_f(c.get("chord_motion_mult"), 1.0), cm0, cm1)
    if "chord_rhythm_mult" in c:
        c["chord_rhythm_mult"] = _clip(_f(c.get("chord_rhythm_mult"), 1.0), cr0, cr1)
    if "melody_density_mult" in c:
        c["melody_density_mult"] = _clip(_f(c.get("melody_density_mult"), 1.0), md0, md1)
    if "arp_density_mult" in c:
        c["arp_density_mult"] = _clip(_f(c.get("arp_density_mult"), 1.0), ad0, ad1)
    if "section_dynamic" in c:
        c["section_dynamic"] = _clip(_f(c.get("section_dynamic"), 1.0), sd0, sd1)
    return c


def audit_emotion(emotion: Any) -> List[AuditIssue]:
    issues: List[AuditIssue] = []
    name = (_s(getattr(emotion, "name", "")) or "").strip().lower() or "<unknown>"
    tempo, vel, dens = normalize_emotion_scalars(emotion)

    # Flag extreme inputs (even if clamped downstream).
    raw_t = _f(getattr(emotion, "tempo_multiplier", 1.0), 1.0)
    raw_d = _f(getattr(emotion, "density", 0.5), 0.5)
    # The runtime may intentionally soften extreme tempo multipliers for playback
    # and form-length stability. Audit only flags genuinely invalid source data.
    if raw_t < 0.35 or raw_t > 2.00:
        issues.append(AuditIssue("tempo_out_of_range", f"emotion:{name}", f"tempo_multiplier={raw_t} clamped→{tempo}"))
    if raw_d != dens:
        issues.append(AuditIssue("density_out_of_range", f"emotion:{name}", f"density={raw_d} clamped→{dens}"))
    if vel <= 0.6 or vel >= 1.35:
        issues.append(AuditIssue("velocity_extreme", f"emotion:{name}", f"velocity_multiplier={vel}"))

    pool = getattr(emotion, "chord_progressions", None) or []
    issues.extend(audit_progression_pool(pool, where=f"emotion:{name}.chord_progressions"))

    # Duplicate progression detection (normalized) — duplicates reduce variety and can hide mistakes.
    try:
        norm = [tuple(normalize_progression(p)) for p in list(pool or [])]
        seen = {}
        dups = 0
        for idx, t in enumerate(norm):
            if len(t) < 2:
                continue
            if t in seen:
                dups += 1
                if dups <= 8:
                    issues.append(
                        AuditIssue(
                            "duplicate_progression",
                            f"emotion:{name}.chord_progressions[{idx}]",
                            f"Duplicate of [{seen[t]}]: {list(t)!r}",
                        )
                    )
            else:
                seen[t] = idx
    except Exception:
        pass

    # Cadence progressions sanity (2-chord cadences are expected).
    cads = getattr(emotion, "cadence_progressions", None)
    if cads is not None:
        if not isinstance(cads, list) or not cads:
            issues.append(AuditIssue("cadence_progressions_empty", f"emotion:{name}.cadence_progressions", "Cadence list is empty"))
        else:
            for i, prog in enumerate(list(cads)[:12]):
                p = normalize_progression(prog)
                if len(p) < 2:
                    issues.append(
                        AuditIssue(
                            "cadence_progression_short",
                            f"emotion:{name}.cadence_progressions[{i}]",
                            f"Too short: {p!r}",
                        )
                    )

    # Cadence intent vs data: warn when progression pools drift away from the intended closure feel.
    cadence = ""
    try:
        from data.emotion_anchors import anchors_for_emotion

        cadence = str(getattr(anchors_for_emotion(emotion), "cadence", "") or "").strip().lower()
    except Exception:
        cadence = ""
    if cadence:
        tr = tonic_end_rate(pool)
        # Avoidant emotions (fear/grief/etc.) should not constantly end on tonic symbols.
        if cadence == "avoid" and tr > 0.45:
            issues.append(
                AuditIssue(
                    "tonic_end_rate_high",
                    f"emotion:{name}.chord_progressions",
                    f"cadence=avoid but tonic_end_rate={tr:.2f} (consider more non-tonic endings)",
                )
            )
        # Authentic emotions should have at least some tonic closure available.
        if cadence == "authentic" and tr < 0.20:
            issues.append(
                AuditIssue(
                    "tonic_end_rate_low",
                    f"emotion:{name}.chord_progressions",
                    f"cadence=authentic but tonic_end_rate={tr:.2f} (may feel perpetually unresolved)",
                )
            )

    # Pop/EDM harmony heuristics (warnings): scale conflict + tension budgets.
    try:
        m = emotion_harmony_metrics(emotion)
        b = _pop_budget_for_emotion(name)
        if float(m.get("scale_conflict_rate", 0.0)) > float(b["max_scale_conflict_rate"]):
            issues.append(
                AuditIssue(
                    "scale_conflict_high",
                    f"emotion:{name}.scale_intervals",
                    f"scale_conflict_rate={m['scale_conflict_rate']:.2f} exceeds pop budget {b['max_scale_conflict_rate']:.2f} (mode≈{m.get('mode')}, sim={m.get('mode_similarity'):.2f})",
                )
            )
        if float(m.get("tension_per_16_chords", 0.0)) > float(b["max_tension_per_16_chords"]):
            issues.append(
                AuditIssue(
                    "tension_high",
                    f"emotion:{name}.chord_progressions",
                    f"tension_per_16_chords={m['tension_per_16_chords']:.2f} exceeds pop budget {b['max_tension_per_16_chords']:.2f}",
                )
            )
        if cadence == "authentic" and float(m.get("tonic_end_rate", 0.0)) < float(b["min_tonic_end_rate_for_authentic"]):
            issues.append(
                AuditIssue(
                    "tonic_end_rate_low",
                    f"emotion:{name}.chord_progressions",
                    f"cadence=authentic but tonic_end_rate={m['tonic_end_rate']:.2f} < {b['min_tonic_end_rate_for_authentic']:.2f}",
                )
            )
        if cadence == "avoid" and float(m.get("tonic_end_rate", 0.0)) > float(b["max_tonic_end_rate_for_avoid"]):
            issues.append(
                AuditIssue(
                    "tonic_end_rate_high",
                    f"emotion:{name}.chord_progressions",
                    f"cadence=avoid but tonic_end_rate={m['tonic_end_rate']:.2f} > {b['max_tonic_end_rate_for_avoid']:.2f}",
                )
            )
    except Exception:
        pass

    sets = getattr(emotion, "arrangement_chord_sets", None) or {}
    if isinstance(sets, dict):
        allowed_roles = {"intro", "a", "pre_chorus", "b", "a_prime", "tag", "outro"}
        for role, p in sorted(sets.items(), key=lambda kv: str(kv[0])):
            role_l = str(role or "").strip().lower()
            if role_l and role_l not in allowed_roles:
                issues.append(
                    AuditIssue(
                        "unknown_section_role",
                        f"emotion:{name}.arrangement_chord_sets[{role}]",
                        f"Unknown role '{role}' (expected one of {sorted(allowed_roles)!r})",
                    )
                )
            issues.extend(audit_progression_pool(p, where=f"emotion:{name}.arrangement_chord_sets[{role}]"))
            # Role coverage + cadence alignment per role pool.
            if p is None or not list(p or []):
                issues.append(
                    AuditIssue(
                        "empty_role_pool",
                        f"emotion:{name}.arrangement_chord_sets[{role}]",
                        "Role pool is empty (will fall back to chord_progressions)",
                    )
                )
            if cadence:
                rr = tonic_end_rate(p)
                if cadence == "avoid" and rr > 0.55:
                    issues.append(
                        AuditIssue(
                            "tonic_end_rate_high",
                            f"emotion:{name}.arrangement_chord_sets[{role}]",
                            f"cadence=avoid but tonic_end_rate={rr:.2f} in role pool",
                        )
                    )
                # Only enforce tonic availability for roles that typically “land” the harmony.
                closure_roles = {"b", "a_prime", "tag", "outro"}
                if cadence == "authentic" and role_l in closure_roles and rr < 0.10:
                    issues.append(
                        AuditIssue(
                            "tonic_end_rate_low",
                            f"emotion:{name}.arrangement_chord_sets[{role}]",
                            f"cadence=authentic but tonic_end_rate={rr:.2f} in role pool",
                        )
                    )
    return issues


def audit_all_emotions(emotions: Iterable[Any]) -> List[AuditIssue]:
    issues: List[AuditIssue] = []
    for e in list(emotions or []):
        issues.extend(audit_emotion(e))
    return issues


def print_emotion_harmony_report(emotions: Iterable[Any], *, top_n: int = 999) -> None:
    rows = [emotion_harmony_metrics(e) for e in list(emotions or [])]
    # Sort by "risk": scale conflict then tension.
    rows.sort(key=lambda r: (float(r.get("scale_conflict_rate", 0.0)), float(r.get("tension_per_16_chords", 0.0))), reverse=True)
    n = min(int(top_n), len(rows))
    for r in rows[:n]:
        name = str(r.get("name", ""))
        mode = str(r.get("mode", ""))
        sim = float(r.get("mode_similarity", 0.0))
        scr = float(r.get("scale_conflict_rate", 0.0))
        ten = float(r.get("tension_per_16_chords", 0.0))
        tr = float(r.get("tonic_end_rate", 0.0))
        cr = float(r.get("cadence_tonic_end_rate", 0.0))
        print(f"{name:15s} mode={mode:14s} sim={sim:0.2f} scale_conflict={scr:0.2f} tension/16={ten:0.2f} tonic_end={tr:0.2f} cadence_tonic_end={cr:0.2f}")


def _main() -> int:
    # Minimal CLI entrypoint:
    #   python -m data.audit
    #   python -m data.audit --top 10
    import argparse

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--top", type=int, default=999, help="Show top N by harmony risk")
    ap.add_argument("--issues", action="store_true", help="Also print audit issues")
    args = ap.parse_args()

    from data.music_data import EMOTIONS

    print_emotion_harmony_report(EMOTIONS, top_n=int(args.top))
    if bool(args.issues):
        issues = audit_all_emotions(EMOTIONS)
        if issues:
            print("\nIssues:")
        for it in issues:
            print(f"- [{it.severity}] {it.kind} @ {it.where}: {it.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
