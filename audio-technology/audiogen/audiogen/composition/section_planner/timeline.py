# composition/section_planner/timeline.py
# ---------------------------------------------------------------------------
# Timeline / texture helpers for section planning.
# ---------------------------------------------------------------------------
from typing import Any, Dict, List, Optional

from audiogen_core.config import CONFIG
from audiogen_core.composition_runtime_flags import phrase_length_bars_clamped

from .observability import log_degraded

def _timeline_shape(role: str, bars: int) -> List[float]:
    """Return a simple 0..1 per-bar shape for a role."""
    b = max(1, int(bars))
    r = (role or "").lower()
    if b == 1:
        return [1.0]
    xs = [i / float(b - 1) for i in range(b)]
    if r == "intro":
        return [0.35 + 0.65 * x for x in xs]  # ramp up
    if r == "outro":
        return [1.0 - 0.65 * x for x in xs]  # ramp down
    if r in {"b", "pre_chorus", "tag"}:
        # Peak around the middle (bell-ish).
        return [max(0.0, 1.0 - abs(2.0 * x - 1.0) ** 1.35) for x in xs]
    if r == "a_prime":
        # Slight growth (return section).
        return [0.75 + 0.25 * x for x in xs]
    return [1.0 for _ in xs]


def _make_timeline_targets(
    role: str,
    bars: int,
    curve: Dict[str, Any],
    *,
    emotion: Any = None,
    next_role: Optional[str] = None,
) -> Dict[str, List[float]]:
    b = max(1, int(bars))
    rlc = (role or "").strip().lower()
    shape = _timeline_shape(rlc, b)
    md = float(curve.get("melody_density_mult", 1.0))
    cr = float(curve.get("chord_rhythm_mult", 1.0))
    mp = float(curve.get("motif_prob_mult", 1.0))
    tm = float(curve.get("tension_mult", 1.0))
    # Keep these multipliers bounded so a bad curve edit can't explode generation.
    md = max(0.25, min(2.5, md))
    cr = max(0.25, min(2.5, cr))
    mp = max(0.25, min(2.5, mp))
    tm = max(0.25, min(2.5, tm))

    # ------------------------------------------------------------------
    # Pop section contrast (role-based, RT-safe).
    # Gated behind a config flag so snapshot tests and legacy behavior remain stable.
    # ------------------------------------------------------------------
    try:
        role_contrast_enabled = bool(getattr(CONFIG.composition, "timeline_role_contrast_enabled", True))
    except Exception as exc:
        log_degraded("timeline._make_timeline_targets.role_contrast", exc, section_role=role)
        role_contrast_enabled = True

    chorusish = rlc in {"b", "chorus", "hook", "tag"}
    verseish = rlc in {"a", "verse"}
    prechorus = rlc in {"pre_chorus"}
    if role_contrast_enabled:
        # Chorus-like sections: slightly denser lead + stronger motif statements,
        # but steadier harmony at the hook entry so the melody reads clearly.
        if chorusish:
            md *= 1.10
            mp *= 1.18
            cr *= 1.04
        elif verseish:
            md *= 0.92
            mp *= 0.90
            cr *= 1.06
        elif prechorus:
            # Pre-chorus: build motion and tension toward the end.
            md *= 1.02
            cr *= 1.08
            tm *= 1.06

    # Optional second tier: stronger pop A/B/PC contrast (off by default).
    try:
        pop_s = float(getattr(CONFIG.composition, "pop_arrangement_strength", 0.0) or 0.0)
    except Exception as exc:
        log_degraded("timeline._make_timeline_targets.pop_arrangement", exc, section_role=role)
        pop_s = 0.0
    pop_s = max(0.0, min(1.0, float(pop_s)))
    if pop_s > 1e-6 and role_contrast_enabled:
        if chorusish:
            md *= 1.0 + 0.08 * pop_s
            mp *= 1.0 + 0.10 * pop_s
            cr *= 1.0 + 0.04 * pop_s
        elif verseish:
            md *= 1.0 - 0.10 * pop_s
            mp *= 1.0 - 0.12 * pop_s
            cr *= 1.0 + 0.08 * pop_s
        elif prechorus:
            md *= 1.0 + 0.05 * pop_s
            cr *= 1.0 + 0.04 * pop_s
            tm *= 1.0 + 0.04 * pop_s

    # Re-clamp after role shaping.
    md = max(0.25, min(2.5, md))
    cr = max(0.25, min(2.5, cr))
    mp = max(0.25, min(2.5, mp))
    tm = max(0.25, min(2.5, tm))

    # Emotion anchors: tension arc template (rise/fall/flat/spike) shapes the
    # per-bar tension trajectory, which then drives harmony color, arp expressiveness,
    # and velocity curves.
    tension_shape = list(shape)
    try:
        from data.emotion_anchors import anchors_for_emotion

        arc = str(getattr(anchors_for_emotion(emotion), "tension_arc", "rise") or "rise").lower()
        if b == 1:
            tension_shape = [1.0]
        else:
            xs = [i / float(b - 1) for i in range(b)]
            if arc == "fall":
                tension_shape = [1.0 - 0.80 * x for x in xs]
            elif arc == "flat":
                tension_shape = [0.92 for _ in xs]
            elif arc == "spike":
                # Sharp peak near 2/3, with a calmer start/end.
                # (Closer to anxiety / surprise / fear feel than a smooth bell.)
                try:
                    c = float(getattr(CONFIG.composition, "timeline_tension_spike_center", 0.68) or 0.68)
                    w = float(getattr(CONFIG.composition, "timeline_tension_spike_width", 0.28) or 0.28)
                    p = float(getattr(CONFIG.composition, "timeline_tension_spike_power", 1.45) or 1.45)
                except Exception as exc:
                    log_degraded("timeline.tension_spike_params", exc, section_role=rlc)
                    c, w, p = 0.68, 0.28, 1.45
                w = max(0.08, float(w))
                p = max(0.5, float(p))
                tension_shape = [max(0.0, 1.0 - abs((x - c) / w) ** p) for x in xs]
                # keep edges non-zero so downstream curves don't fully collapse
                tension_shape = [0.35 + 0.65 * float(v) for v in tension_shape]
            else:  # "rise" (default)
                tension_shape = [0.45 + 0.55 * x for x in xs]
    except Exception as exc:
        log_degraded("timeline.tension_shape_from_anchors", exc, section_role=rlc)
        tension_shape = list(shape)

    # ------------------------------------------------------------------
    # 16-bar A/B structure: keep the first half "establishing" and the
    # second half as a modest "answer/development" with stronger cadence prep.
    # This is RT-safe: O(bars) and deterministic.
    # ------------------------------------------------------------------
    cadence_window = [0.0 for _ in range(b)]
    breath_window = [0.0 for _ in range(b)]

    # ------------------------------------------------------------------
    # Phrase plan outputs (RT-safe, deterministic).
    # Gated by config to preserve legacy/snapshot behavior.
    # ------------------------------------------------------------------
    try:
        phrase_targets_enabled = bool(getattr(CONFIG.composition, "timeline_phrase_targets_enabled", True))
    except Exception as exc:
        log_degraded("timeline.phrase_targets_flag", exc, section_role=rlc)
        phrase_targets_enabled = True

    phrase_len = phrase_length_bars_clamped(1, 16)
    phrase_len = max(1, min(16, int(phrase_len)))
    total_phrases = max(1, (b + phrase_len - 1) // phrase_len)

    def _phrase_role(bar_idx: int) -> str:
        phrase_idx = int(bar_idx) // int(phrase_len)
        if total_phrases <= 1 or phrase_idx == 0:
            return "opening"
        if phrase_idx == total_phrases - 1:
            return "cadence"
        if phrase_idx % 2 == 1:
            return "answer"
        return "continuation"

    phrase_role_by_bar = [_phrase_role(i) for i in range(b)]

    cadence_strength_by_bar = [0.0 for _ in range(b)]
    if phrase_targets_enabled:
        role_phrase_end_mult = {
            "intro": 0.86,
            "a": 0.72,
            "pre_chorus": 1.18,
            "b": 1.22,
            "chorus": 1.22,
            "hook": 1.22,
            "tag": 1.16,
            "a_prime": 1.02,
            "outro": 1.28,
        }.get(rlc, 1.0)
        role_penult_mult = {
            "intro": 0.62,
            "a": 0.52,
            "pre_chorus": 0.92,
            "b": 0.82,
            "chorus": 0.82,
            "hook": 0.82,
            "tag": 0.78,
            "a_prime": 0.68,
            "outro": 0.90,
        }.get(rlc, 0.55)
        role_breath_mult = {
            "intro": 0.55,
            "a": 0.48,
            "pre_chorus": 0.82,
            "b": 0.72,
            "chorus": 0.72,
            "hook": 0.72,
            "tag": 0.78,
            "a_prime": 0.62,
            "outro": 0.88,
        }.get(rlc, 0.7)
        for i in range(b):
            bar_in_phrase = int(i) % int(phrase_len)
            is_last_in_phrase = (bar_in_phrase == int(phrase_len) - 1) or (i == b - 1)
            is_penultimate_in_phrase = (bar_in_phrase == int(phrase_len) - 2) and (i < b - 1)
            phrase_role = str(phrase_role_by_bar[i] or "")
            section_last = i == (b - 1)
            section_penult = i == (b - 2)
            if is_last_in_phrase:
                end_mult = float(role_phrase_end_mult)
                if phrase_role in {"opening", "answer"} and rlc in {"a", "intro"} and not section_last:
                    end_mult *= 0.84
                if phrase_role in {"cadence"} or section_last:
                    end_mult *= 1.12 if rlc in {"pre_chorus", "b", "chorus", "hook", "tag", "outro"} else 1.0
                cadence_strength_by_bar[i] = float(max(cadence_strength_by_bar[i], min(1.35, end_mult)))
            elif is_penultimate_in_phrase:
                pen = float(role_penult_mult)
                if phrase_role in {"cadence"} or section_penult:
                    pen *= 1.10 if rlc in {"pre_chorus", "b", "chorus", "hook", "tag", "outro"} else 1.0
                cadence_strength_by_bar[i] = float(max(cadence_strength_by_bar[i], min(1.1, pen)))

            # Breath: encourage small gaps at phrase boundaries.
            for i in range(b):
                if i > 0 and (i % int(phrase_len) == 0):
                    breath_window[i] = max(float(breath_window[i]), 0.7)
                # Leave a little more air before stronger landings, especially
                # pre-chorus -> chorus and chorus/outro phrase endings.
                if i < (b - 1):
                    bar_in_phrase = int(i) % int(phrase_len)
                    is_penultimate_in_phrase = (bar_in_phrase == int(phrase_len) - 2)
                    if is_penultimate_in_phrase:
                        boost = float(role_breath_mult)
                        if i >= (b - 2):
                            boost *= 1.08
                        breath_window[i] = max(float(breath_window[i]), min(1.0, float(boost)))

    if b == 16:
        # Breath at the A->B boundary and at the end (encourages handoffs).
        breath_window[8] = 1.0
        breath_window[15] = 1.0
        # Cadence prep: medium at bars 6-7, strong at bars 14-15.
        cadence_window[6] = 0.5
        cadence_window[7] = 0.5
        cadence_window[14] = 1.0
        cadence_window[15] = 1.0

        # Modest development lift in the second half.
        # Keep bounded so a curve edit can't explode generation.
        try:
            dev = float(curve.get("ab_development_strength", 0.15) or 0.15)
        except Exception as exc:
            log_degraded("timeline.ab_development_strength", exc, section_role=rlc)
            dev = 0.15
        dev = max(0.0, min(0.5, float(dev)))
        dev_motion = 1.0 + 0.80 * float(dev)
        dev_motif = 1.0 + 1.20 * float(dev)
        dev_melody = 1.0 + 0.40 * float(dev)
        for i in range(8, 16):
            shape[i] *= dev_melody
            tension_shape[i] = min(1.0, float(tension_shape[i]) * 1.05)
        cr *= dev_motion
        mp *= dev_motif

    # Merge phrase cadence strength with any special-case cadence window.
    if phrase_targets_enabled:
        for i in range(b):
            try:
                cadence_window[i] = float(max(float(cadence_window[i]), float(cadence_strength_by_bar[i])))
            except Exception as exc:
                log_degraded("timeline.merge_cadence_strength", exc, section_role=rlc, bar_index=i)
        # Role-aware section endings: keep verses more open, push pre-chorus/chorus/outro
        # endings to feel more intentional even in short 4/8-bar sections.
        if b >= 2:
            end_role_boost = {
                "intro": (0.45, 0.82),
                "a": (0.38, 0.68),
                "pre_chorus": (0.88, 1.18),
                "b": (0.76, 1.22),
                "chorus": (0.76, 1.22),
                "hook": (0.76, 1.22),
                "tag": (0.72, 1.16),
                "a_prime": (0.58, 0.98),
                "outro": (0.92, 1.30),
            }.get(rlc, (0.55, 1.0))
            cadence_window[b - 2] = float(max(float(cadence_window[b - 2]), float(end_role_boost[0])))
            cadence_window[b - 1] = float(max(float(cadence_window[b - 1]), float(end_role_boost[1])))
            breath_tail = {
                "intro": 0.40,
                "a": 0.34,
                "pre_chorus": 0.76,
                "b": 0.62,
                "chorus": 0.62,
                "hook": 0.62,
                "tag": 0.66,
                "a_prime": 0.52,
                "outro": 0.84,
            }.get(rlc, 0.55)
            breath_window[b - 2] = float(max(float(breath_window[b - 2]), float(breath_tail)))

    # Phrase-function intent (T/PD/D) per bar, derived from phrase role + cadence emphasis.
    # This is a lightweight "intent bus" for harmony/chord-rhythm modules.
    harmony_function_target_by_bar: List[str] = []
    for i in range(b):
        pr = str(phrase_role_by_bar[i] if i < len(phrase_role_by_bar) else "continuation")
        cad = float(cadence_window[i] if i < len(cadence_window) else 0.0)
        is_last = i == (b - 1)
        is_pen = i == (b - 2)

        if i == 0 or pr == "opening":
            target_fn = "T"
        elif pr == "cadence":
            target_fn = "D"
        else:
            target_fn = "PD"

        if cad >= 0.95 or (is_pen and cad >= 0.55):
            target_fn = "D"

        # Role-aware phrase landing behavior.
        if is_last:
            if rlc in {"pre_chorus"}:
                target_fn = "D"
            elif rlc in {"b", "chorus", "hook", "tag", "outro", "ending"}:
                target_fn = "T"
            elif rlc in {"a", "verse"} and b >= 8:
                target_fn = "PD"
            else:
                target_fn = "T"
        elif (
            pr == "cadence"
            and rlc in {"b", "chorus", "hook", "tag", "outro", "ending"}
            and cad >= 1.10
        ):
            # Strong chorus/outro cadence bars can land to tonic before the final bar.
            target_fn = "T"

        harmony_function_target_by_bar.append(str(target_fn))

    melody_density = [md * float(v) for v in shape]
    chord_rhythm = [(cr * float(v) * (0.85 + 0.35 * float(t))) for v, t in zip(shape, tension_shape)]
    motif_strength = [mp * float(v) for v in shape]
    tension = [tm * max(0.0, min(1.0, float(v))) for v in tension_shape]

    # Arrangement density arcs per lane (0..1), used by texture/orchestration.
    layer_presence_targets: Dict[str, List[float]] = {
        "bass": [],
        "chords": [],
        "melody": [],
        "arp": [],
        "counter": [],
        "percussion": [],
    }
    for i in range(b):
        prog = float(i) / float(max(1, b - 1))
        cad_w = float(cadence_window[i]) if i < len(cadence_window) else 0.0
        br_w = float(breath_window[i]) if i < len(breath_window) else 0.0
        ten = float(tension[i]) if i < len(tension) else 0.85
        role_base = {
            "intro": {"bass": 0.28 + 0.30 * prog, "chords": 0.80, "melody": 0.68 + 0.16 * prog, "arp": 0.42 + 0.24 * prog, "counter": 0.08, "percussion": 0.40 + 0.24 * prog},
            "a": {"bass": 0.70, "chords": 0.84, "melody": 0.92, "arp": 0.40, "counter": 0.14 + 0.08 * prog, "percussion": 0.68},
            "verse": {"bass": 0.70, "chords": 0.84, "melody": 0.92, "arp": 0.40, "counter": 0.14 + 0.08 * prog, "percussion": 0.68},
            "pre_chorus": {"bass": 0.82 + 0.10 * prog, "chords": 0.76 + 0.10 * prog, "melody": 0.88, "arp": 0.68 + 0.14 * prog, "counter": 0.18 + 0.20 * prog, "percussion": 0.82 + 0.08 * prog},
            "b": {"bass": 0.99, "chords": 0.96, "melody": 0.96, "arp": 0.98, "counter": 0.70 + 0.16 * prog, "percussion": 0.96},
            "chorus": {"bass": 0.99, "chords": 0.96, "melody": 0.96, "arp": 0.98, "counter": 0.70 + 0.16 * prog, "percussion": 0.96},
            "hook": {"bass": 0.99, "chords": 0.96, "melody": 0.96, "arp": 0.98, "counter": 0.70 + 0.16 * prog, "percussion": 0.96},
            "tag": {"bass": 0.95, "chords": 0.92, "melody": 0.95, "arp": 0.92, "counter": 0.54 + 0.12 * prog, "percussion": 0.90},
            "a_prime": {"bass": 0.88, "chords": 0.88, "melody": 0.92, "arp": 0.78, "counter": 0.46 + 0.12 * prog, "percussion": 0.78},
            "outro": {"bass": 0.62 - 0.25 * prog, "chords": 0.78 - 0.20 * prog, "melody": 0.66 - 0.24 * prog, "arp": 0.58 - 0.28 * prog, "counter": 0.14 - 0.08 * prog, "percussion": 0.56 - 0.24 * prog},
            "ending": {"bass": 0.62 - 0.25 * prog, "chords": 0.78 - 0.20 * prog, "melody": 0.66 - 0.24 * prog, "arp": 0.58 - 0.28 * prog, "counter": 0.14 - 0.08 * prog, "percussion": 0.56 - 0.24 * prog},
        }.get(rlc, {"bass": 0.82, "chords": 0.84, "melody": 0.90, "arp": 0.74, "counter": 0.30, "percussion": 0.78})
        lane = {k: float(v) for k, v in dict(role_base).items()}
        # Tension lifts rhythmic/ornamental lanes slightly.
        lane["arp"] *= float(0.92 + 0.20 * max(0.0, min(1.0, ten)))
        lane["counter"] *= float(0.90 + 0.25 * max(0.0, min(1.0, ten)))
        # Cadence/breath create space.
        if cad_w >= 0.95:
            lane["arp"] *= 0.78
            lane["counter"] *= 0.70
            lane["chords"] *= 0.90
        if br_w >= 0.50:
            lane["arp"] *= 0.82
            lane["counter"] *= 0.68
            lane["chords"] *= 0.92
            lane["percussion"] *= 0.90
        for lk in layer_presence_targets.keys():
            layer_presence_targets[lk].append(float(max(0.0, min(1.0, lane.get(lk, 1.0)))))
    try:
        perc_on = bool(getattr(CONFIG.composition, "percussion_lane_enabled", True))
    except Exception as exc:
        log_degraded("timeline.percussion_lane_enabled", exc, section_role=rlc)
        perc_on = True
    if not perc_on:
        layer_presence_targets["percussion"] = [0.0 for _ in range(b)]

    phrase_intent_by_bar: List[Dict[str, Any]] = []
    for i in range(b):
        phrase_intent_by_bar.append(
            {
                "bar_index": int(i),
                "phrase_role": str(phrase_role_by_bar[i] if i < len(phrase_role_by_bar) else "continuation"),
                "cadence_strength": float(cadence_window[i] if i < len(cadence_window) else 0.0),
                "harmony_function_target": str(
                    harmony_function_target_by_bar[i] if i < len(harmony_function_target_by_bar) else "PD"
                ),
                "melody_activity_target": float(melody_density[i] if i < len(melody_density) else 1.0),
                "chord_rhythm_target": float(chord_rhythm[i] if i < len(chord_rhythm) else 1.0),
                "percussion_activity_target": float(layer_presence_targets["percussion"][i] if i < len(layer_presence_targets["percussion"]) else 0.8),
            }
        )

    # Hook clarity: chorus/hook bar-0 should be a touch steadier harmonically.
    # Also gated with the role contrast flag to preserve legacy defaults.
    if role_contrast_enabled and chorusish and chord_rhythm:
        chord_rhythm[0] = float(chord_rhythm[0]) * 0.82
        if len(chord_rhythm) >= 2:
            chord_rhythm[1] = float(chord_rhythm[1]) * 0.90
        for i in range(2, len(chord_rhythm)):
            chord_rhythm[i] = float(max(0.82, float(chord_rhythm[i])))

    out = {
        "melody_density": list(melody_density),
        # Let tension arc co-drive chord-hit activity: higher tension -> more rhythmic activity.
        # This feeds HarmonicRhythmModel (hold/half/anticipate/sus) via bar_target.
        "chord_rhythm": list(chord_rhythm),
        "motif_strength": list(motif_strength),
        # Shared tension trajectory (0..~1.25). Consumers should clamp to 0..1.
        "tension": list(tension),
        "cadence_window": list(cadence_window),
        "cadence_strength_by_bar": list(cadence_strength_by_bar),
        "harmony_function_target_by_bar": list(harmony_function_target_by_bar),
        "phrase_intent_by_bar": list(phrase_intent_by_bar),
        "layer_presence_targets": {str(k): list(v) for k, v in dict(layer_presence_targets).items()},
        "breath_window": list(breath_window),
        "phrase_role_by_bar": list(phrase_role_by_bar),
    }
    try:
        trans_on = bool(getattr(CONFIG.composition, "transition_composer_enabled", True))
        trans_strength = float(getattr(CONFIG.composition, "transition_composer_strength", 0.72) or 0.72)
    except Exception as exc:
        log_degraded("timeline.transition_composer_flags", exc, section_role=rlc)
        trans_on = True
        trans_strength = 0.72
    if trans_on:
        out = _apply_transition_composer_targets(
            targets=dict(out),
            role=str(rlc),
            next_role=str(next_role or "").strip().lower(),
            strength=float(trans_strength),
        )
    return out


def _apply_transition_composer_targets(
    *,
    targets: Dict[str, List[float]],
    role: str,
    next_role: str,
    strength: float,
) -> Dict[str, List[float]]:
    out = {}
    for k, v in dict(targets or {}).items():
        kk = str(k)
        if isinstance(v, list):
            out[kk] = list(v)
        elif isinstance(v, dict):
            out[kk] = {
                str(k2): (list(v2) if isinstance(v2, list) else v2)
                for k2, v2 in dict(v).items()
            }
        else:
            out[kk] = v
    r = str(role or "").strip().lower()
    nr = str(next_role or "").strip().lower()
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not nr:
        return out
    try:
        phrase_handoff_on = bool(getattr(CONFIG.composition, "transition_composer_phrase_handoff_enabled", True))
        phrase_handoff_k = float(getattr(CONFIG.composition, "transition_composer_phrase_handoff_strength", 0.82) or 0.82)
    except Exception as exc:
        log_degraded("timeline.phrase_handoff_flags", exc, role=role, next_role=next_role)
        phrase_handoff_on = True
        phrase_handoff_k = 0.82
    phrase_handoff_k = max(0.0, min(1.0, float(phrase_handoff_k)))

    def _boost(key: str, idx: int, mult: float, lo: float, hi: float) -> None:
        arr = list(out.get(key, []) or [])
        if 0 <= int(idx) < len(arr):
            arr[int(idx)] = float(max(lo, min(hi, float(arr[int(idx)]) * float(mult))))
            out[key] = arr

    def _setmax(key: str, idx: int, value: float, lo: float, hi: float) -> None:
        arr = list(out.get(key, []) or [])
        if 0 <= int(idx) < len(arr):
            arr[int(idx)] = float(max(lo, min(hi, max(float(arr[int(idx)]), float(value)))))
            out[key] = arr

    def _set_token(key: str, idx: int, token: str) -> None:
        arr = list(out.get(key, []) or [])
        if 0 <= int(idx) < len(arr):
            arr[int(idx)] = str(token)
            out[key] = arr

    n = max(len(list(out.get("breath_window", []) or [])), len(list(out.get("cadence_window", []) or [])))
    if n <= 0:
        return out
    last = n - 1
    pen = max(0, last - 1)

    if r in {"a", "verse"} and nr == "pre_chorus":
        _setmax("breath_window", pen, 0.46 + 0.22 * s, 0.0, 1.0)
        _boost("tension", pen, 1.04 + 0.10 * s, 0.0, 1.35)
        _boost("tension", last, 1.05 + 0.14 * s, 0.0, 1.35)
        _boost("chord_rhythm", last, 1.02 + 0.08 * s, 0.35, 2.0)
        _boost("motif_strength", last, 1.03 + 0.10 * s, 0.0, 2.0)
    elif r == "pre_chorus" and nr in {"b", "chorus", "hook"}:
        _setmax("breath_window", pen, 0.62 + 0.20 * s, 0.0, 1.0)
        _boost("tension", pen, 1.08 + 0.14 * s, 0.0, 1.35)
        _boost("tension", last, 1.10 + 0.18 * s, 0.0, 1.35)
        _boost("cadence_window", last, 1.0 - 0.10 * s, 0.0, 1.35)
        # Electronic-style pre-drop: last bar strips melodic motion before chorus attack.
        _boost("melody_density", last, 0.26 + 0.18 * (1.0 - s), 0.08, 2.25)
        _boost("motif_strength", pen, 1.06 + 0.12 * s, 0.0, 2.0)
        _set_token("harmony_function_target_by_bar", pen, "D")
        _set_token("harmony_function_target_by_bar", last, "D")
    elif r in {"b", "chorus", "hook"} and nr in {"a", "verse"}:
        _setmax("breath_window", last, 0.54 + 0.18 * s, 0.0, 1.0)
        _boost("tension", pen, 1.0 - 0.06 * s, 0.0, 1.35)
        _boost("tension", last, 1.0 - 0.14 * s, 0.0, 1.35)
        _boost("chord_rhythm", last, 1.0 - 0.10 * s, 0.35, 2.0)
        _boost("motif_strength", last, 1.0 - 0.12 * s, 0.0, 2.0)
        _boost("melody_density", last, 1.0 - 0.10 * s, 0.0, 2.25)
        _set_token("harmony_function_target_by_bar", last, "T")

    if phrase_handoff_on and phrase_handoff_k > 1e-6:
        kh = float(s) * float(phrase_handoff_k)
        # Generic phrase-end polish regardless of role pair.
        _setmax("breath_window", pen, 0.32 + 0.30 * kh, 0.0, 1.0)
        _setmax("cadence_window", last, 0.54 + 0.60 * kh, 0.0, 1.35)
        _boost("motif_strength", pen, 1.0 + 0.10 * kh, 0.0, 2.0)
        _boost("melody_density", last, 1.0 - 0.05 * kh, 0.0, 2.25)
        if nr in {"b", "chorus", "hook"}:
            _set_token("harmony_function_target_by_bar", last, "D")
        elif nr in {"a", "verse", "outro", "ending"}:
            _set_token("harmony_function_target_by_bar", last, "T")
    # Keep phrase_intent rows aligned with any transition-composer edits.
    try:
        pi = list(out.get("phrase_intent_by_bar", []) or [])
        hf = list(out.get("harmony_function_target_by_bar", []) or [])
        cd = list(out.get("cadence_window", []) or [])
        md = list(out.get("melody_density", []) or [])
        ch = list(out.get("chord_rhythm", []) or [])
        for i, row in enumerate(pi):
            if not isinstance(row, dict):
                continue
            if i < len(hf):
                row["harmony_function_target"] = str(hf[i])
            if i < len(cd):
                row["cadence_strength"] = float(cd[i])
            if i < len(md):
                row["melody_activity_target"] = float(md[i])
            if i < len(ch):
                row["chord_rhythm_target"] = float(ch[i])
        out["phrase_intent_by_bar"] = pi
    except Exception as exc:
        log_degraded("timeline.phrase_intent_resync", exc, role=role, next_role=next_role)
    return out


def _make_texture_by_bar(
    *,
    section_role: str,
    bars: int,
    timeline_targets: Optional[Dict[str, List[float]]],
    handoff_ctx: Optional[Dict[str, Any]] = None,
    next_role: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Compute a compact per-bar texture script from role + targets + realtime hints.
    Kept realtime-safe: O(bars), simple math only.
    """
    b = max(0, int(bars))
    targets = timeline_targets or {}
    tension = list(targets.get("tension", []) or [])
    cad = list(targets.get("cadence_window", []) or [])
    breath = list(targets.get("breath_window", []) or [])
    layer_targets = dict(targets.get("layer_presence_targets", {}) or {})

    try:
        drop_k = float(getattr(CONFIG.composition, "texture_drop_strength", 0.0) or 0.0)
    except Exception as exc:
        log_degraded("texture.drop_strength", exc, section_role=section_role)
        drop_k = 0.0
    try:
        reg_k = float(getattr(CONFIG.composition, "texture_register_lift_strength", 0.0) or 0.0)
    except Exception as exc:
        log_degraded("texture.register_lift", exc, section_role=section_role)
        reg_k = 0.0
    try:
        fx_k = float(getattr(CONFIG.composition, "texture_fx_gesture_strength", 0.0) or 0.0)
    except Exception as exc:
        log_degraded("texture.fx_gesture", exc, section_role=section_role)
        fx_k = 0.0

    drop_k = max(0.0, min(1.0, float(drop_k)))
    reg_k = max(0.0, min(1.0, float(reg_k)))
    fx_k = max(0.0, min(1.0, float(fx_k)))

    hctx = handoff_ctx or {}
    try:
        rt_special = str(hctx.get("rt_special_event", "") or "").strip().lower()
    except Exception as exc:
        log_degraded("texture.handoff.rt_special", exc, section_role=section_role)
        rt_special = ""
    try:
        recap_intent = bool(hctx.get("rt_recap_intent", False))
    except Exception as exc:
        log_degraded("texture.handoff.recap_intent", exc, section_role=section_role)
        recap_intent = False
    try:
        rt_energy = hctx.get("rt_energy", None)
        rt_energy = float(rt_energy) if rt_energy is not None else None
    except Exception as exc:
        log_degraded("texture.handoff.rt_energy", exc, section_role=section_role)
        rt_energy = None
    try:
        pivot_strategy = str(hctx.get("handoff_pivot_strategy", "") or "").strip().lower()
    except Exception as exc:
        log_degraded("texture.handoff.pivot_strategy", exc, section_role=section_role)
        pivot_strategy = ""

    r = (section_role or "").strip().lower()
    chorusish = r in {"b", "tag"}
    pre = r in {"pre_chorus"}
    bridgeish = r in {"a_prime"} or rt_special == "contrast_bridge"

    def _clamp01(v: float) -> float:
        return float(max(0.0, min(1.0, float(v))))

    def _slot_layer_presence(
        *,
        role_lc: str,
        progress: float,
        drop_level: float,
        cadence_w: float,
        breath_w: float,
    ) -> Dict[str, float]:
        # Section-role slot orchestration:
        # each layer gets a deterministic per-bar presence target.
        if role_lc == "intro":
            base = {
                "bass": 0.15 + 0.20 * progress,
                "chords": 0.82,
                "melody": 0.52 + 0.12 * progress,
                "arp": 0.32 + 0.26 * progress,
                "counter": 0.06,
            }
        elif role_lc in {"a", "verse"}:
            base = {
                "bass": 0.62,
                "chords": 0.86,
                "melody": 0.93,
                "arp": 0.50,
                "counter": 0.22 + 0.08 * progress,
            }
        elif role_lc in {"pre_chorus"}:
            base = {
                "bass": 0.78 + 0.14 * progress,
                "chords": 0.74 + 0.08 * progress,
                "melody": 0.86 + 0.06 * progress,
                "arp": 0.66 + 0.16 * progress,
                "counter": 0.12 + 0.18 * progress,
            }
        elif role_lc in {"b", "chorus", "hook", "tag"}:
            base = {
                "bass": 0.98,
                "chords": 0.94,
                "melody": 0.96,
                "arp": 0.96,
                "counter": 0.54 + 0.16 * progress,
            }
        elif role_lc in {"a_prime"}:
            base = {
                "bass": 0.88,
                "chords": 0.88,
                "melody": 0.92,
                "arp": 0.78,
                "counter": 0.44 + 0.10 * progress,
            }
        elif role_lc in {"outro", "ending"}:
            base = {
                "bass": 0.56 - 0.24 * progress,
                "chords": 0.80 - 0.20 * progress,
                "melody": 0.62 - 0.24 * progress,
                "arp": 0.60 - 0.28 * progress,
                "counter": 0.12 - 0.08 * progress,
            }
        else:
            base = {
                "bass": 0.82,
                "chords": 0.84,
                "melody": 0.90,
                "arp": 0.74,
                "counter": 0.30,
            }

        # Structural breathing: clear room on cadence/breath bars.
        if cadence_w >= 0.95:
            base["arp"] *= 0.74
            base["counter"] *= 0.68
            base["chords"] *= 0.86
            base["melody"] = min(1.0, float(base["melody"]) * 1.02)
        if breath_w >= 0.50:
            base["arp"] *= 0.76
            base["counter"] *= 0.62
            base["chords"] *= 0.88
        if drop_level > 1e-6:
            mult = max(0.45, 1.0 - 0.70 * float(drop_level))
            base["arp"] *= mult
            base["counter"] *= mult
            base["chords"] *= max(0.55, mult + 0.10)
            base["bass"] *= max(0.65, mult + 0.20)

        return {k: _clamp01(v) for k, v in base.items()}

    out: List[Dict[str, Any]] = []
    for i in range(b):
        t = float(tension[i]) if i < len(tension) and tension[i] is not None else 0.85
        cw = float(cad[i]) if i < len(cad) and cad[i] is not None else 0.0
        bw = float(breath[i]) if i < len(breath) and breath[i] is not None else 0.0
        p = float(i) / float(max(1, b - 1))

        # Drop policy: emphasize breath + pre-chorus lead-in + bridge bar-0 air.
        drop = 0.0
        if bw >= 0.5:
            drop = max(drop, 0.75)
        if pre and i >= max(0, b - 2):
            drop = max(drop, 0.55)
        if bridgeish and i == 0:
            drop = max(drop, 0.60)
        if recap_intent and i == b - 1:
            drop = max(drop, 0.45)
        drop = float(drop) * float(drop_k)
        # Transition-aware adaptation from handoff pivot strategy.
        if pivot_strategy == "pedal":
            drop *= 0.88
        elif pivot_strategy == "dominant_pivot":
            drop *= 0.95
        elif pivot_strategy == "chromatic":
            drop *= 1.06

        # Lead focus: recaps and cadence bars.
        lead_focus = 1.0 if (recap_intent or cw >= 0.95) else (0.6 if chorusish else 0.3)

        # Register lift: chorus/tag lift, keep bridge lower.
        lift = 0
        if chorusish:
            lift = 12
        if bridgeish:
            lift = 0
        lift = int(round(float(lift) * float(reg_k)))

        # FX gestures: space/width/grit correlate with tension and cadences.
        space = float(max(0.0, min(1.0, 0.35 * t + 0.65 * cw))) * float(fx_k)
        width = float(max(0.0, min(1.0, 0.45 * t + 0.55 * (1.0 if chorusish else 0.0)))) * float(fx_k)
        grit = float(max(0.0, min(1.0, 0.25 * t + 0.55 * (1.0 if bridgeish else 0.0)))) * float(fx_k)
        if pivot_strategy == "dominant_pivot":
            width = float(width) * 1.08
            grit = float(grit) * 1.12
        elif pivot_strategy == "pedal":
            space = float(space) * 0.94
            lead_focus = float(lead_focus) * 1.05

        # Energy lane can globally scale gesture intensity (when present).
        if rt_energy is not None:
            e = max(0.0, min(1.0, float(rt_energy)))
            drop = float(drop) * (0.85 + 0.30 * e)
            space = float(space) * (0.85 + 0.30 * e)
            width = float(width) * (0.85 + 0.30 * e)
            grit = float(grit) * (0.85 + 0.30 * e)
            lead_focus = float(lead_focus) * (0.85 + 0.30 * e)

        layer_presence = _slot_layer_presence(
            role_lc=str(r),
            progress=float(p),
            drop_level=float(drop),
            cadence_w=float(cw),
            breath_w=float(bw),
        )
        # Optional per-lane arrangement targets from timeline planning.
        if isinstance(layer_targets, dict):
            for lk in ("bass", "chords", "melody", "arp", "counter"):
                try:
                    arr = list(layer_targets.get(lk, []) or [])
                    tgt = float(arr[i]) if i < len(arr) else 1.0
                    tgt = max(0.0, min(1.0, tgt))
                    layer_presence[lk] = _clamp01(float(layer_presence.get(lk, 1.0)) * float(tgt))
                except Exception as exc:
                    log_degraded("texture.layer_target_blend", exc, section_role=section_role, bar_index=i, layer=lk)

        out.append(
            {
                "bar": int(i),
                "drop_level": float(max(0.0, min(1.0, drop))),
                "lead_focus": float(max(0.0, min(1.0, lead_focus))),
                "register_lift_semitones": int(lift),
                "fx_space_boost": float(max(0.0, min(1.0, space))),
                "fx_width_boost": float(max(0.0, min(1.0, width))),
                "fx_grit_boost": float(max(0.0, min(1.0, grit))),
                "layer_presence": dict(layer_presence),
            }
        )
    try:
        orch_on = bool(getattr(CONFIG.composition, "orchestration_script_enabled", True))
        orch_strength = float(getattr(CONFIG.composition, "orchestration_script_strength", 0.72) or 0.72)
    except Exception as exc:
        log_degraded("texture.orchestration_script_flags", exc, section_role=section_role)
        orch_on = True
        orch_strength = 0.72
    if orch_on:
        out = _apply_orchestration_script(
            texture_rows=list(out),
            role=str(r),
            next_role=str(next_role or "").strip().lower(),
            strength=float(orch_strength),
        )
    return out


def _apply_orchestration_script(
    *,
    texture_rows: List[Dict[str, Any]],
    role: str,
    next_role: str,
    strength: float,
) -> List[Dict[str, Any]]:
    rows = [dict(row or {}) for row in list(texture_rows or [])]
    s = max(0.0, min(1.0, float(strength)))
    r = str(role or "").strip().lower()
    nr = str(next_role or "").strip().lower()
    if s <= 1e-6 or not rows:
        return rows

    def _clamp01(v: float) -> float:
        return float(max(0.0, min(1.0, float(v))))

    def _shape(idx: int, total: int) -> float:
        if total <= 1:
            return 1.0
        return float(idx) / float(max(1, total - 1))

    def _mul_lp(row: Dict[str, Any], layer: str, mult: float) -> None:
        lp = row.get("layer_presence")
        if not isinstance(lp, dict):
            lp = {}
            row["layer_presence"] = lp
        lp[str(layer)] = _clamp01(float(lp.get(str(layer), 1.0) or 1.0) * float(mult))

    n = len(rows)
    last = n - 1
    pen = max(0, last - 1)

    if r in {"a", "verse"}:
        for i, row in enumerate(rows):
            prog = _shape(i, n)
            # Verses should feel staged, not fully open from bar 1.
            if i == 0:
                _mul_lp(row, "arp", 1.0 - 0.42 * s)
                _mul_lp(row, "counter", 1.0 - 0.60 * s)
                _mul_lp(row, "chords", 1.0 - 0.10 * s)
                row["lead_focus"] = _clamp01(float(row.get("lead_focus", 0.0) or 0.0) + 0.10 * s)
            elif prog < 0.45:
                _mul_lp(row, "counter", 1.0 - 0.30 * s)
                _mul_lp(row, "arp", 1.0 - 0.26 * s * (1.0 - prog / 0.45))
            if nr == "pre_chorus" and i >= pen:
                _mul_lp(row, "arp", 1.0 + 0.10 * s)
                _mul_lp(row, "chords", 1.0 + 0.05 * s)

    elif r == "pre_chorus":
        for i, row in enumerate(rows):
            prog = _shape(i, n)
            # Make the build feel staged: start leaner, arrive fuller.
            _mul_lp(row, "bass", 1.0 - 0.10 * s + 0.14 * s * prog)
            _mul_lp(row, "chords", 1.0 - 0.14 * s + 0.22 * s * prog)
            _mul_lp(row, "arp", 1.0 - 0.10 * s + 0.28 * s * prog)
            _mul_lp(row, "counter", 1.0 - 0.36 * s + 0.44 * s * prog)
            if prog < 0.35:
                _mul_lp(row, "melody", 1.0 - 0.04 * s)
            elif prog > 0.70:
                row["fx_width_boost"] = _clamp01(float(row.get("fx_width_boost", 0.0) or 0.0) + 0.10 * s * prog)
                row["fx_space_boost"] = _clamp01(float(row.get("fx_space_boost", 0.0) or 0.0) + 0.06 * s * prog)
        if nr in {"b", "chorus", "hook", "tag"}:
            # Electronic-style impact: last bar drops lead + arp; harmony pad carries into chorus.
            if n >= 2:
                _mul_lp(rows[pen], "melody", 1.0 - 0.14 * s)
                _mul_lp(rows[pen], "arp", 1.0 - 0.20 * s)
            rows[last]["lead_focus"] = _clamp01(float(rows[last].get("lead_focus", 0.0) or 0.0) * (1.0 - 0.55 * s))
            dm = 0.07 + 0.08 * (1.0 - s)
            da = 0.06 + 0.07 * (1.0 - s)
            _mul_lp(rows[last], "melody", dm)
            _mul_lp(rows[last], "arp", da)
            _mul_lp(rows[last], "counter", 1.0 - 0.62 * s)
            _mul_lp(rows[last], "chords", 1.0 + 0.07 * s)
            rows[last]["drop_level"] = _clamp01(max(float(rows[last].get("drop_level", 0.0) or 0.0), 0.65 + 0.30 * s))

    elif r in {"b", "chorus", "hook", "tag"}:
        for i, row in enumerate(rows):
            prog = _shape(i, n)
            # Chorus entry: let the arp announce the hook before every layer crowds in.
            if i == 0:
                _mul_lp(row, "arp", 1.0 + 0.18 * s)
                _mul_lp(row, "melody", 1.0 - 0.08 * s)
                _mul_lp(row, "chords", 1.0 - 0.08 * s)
                _mul_lp(row, "counter", 1.0 - 0.32 * s)
                row["fx_width_boost"] = _clamp01(float(row.get("fx_width_boost", 0.0) or 0.0) + 0.12 * s)
            elif i == 1:
                _mul_lp(row, "arp", 1.0 + 0.10 * s)
                _mul_lp(row, "counter", 1.0 - 0.14 * s)
            # Keep the arp slightly foregrounded through the hook.
            if prog <= 0.5:
                _mul_lp(row, "arp", 1.0 + 0.06 * s)
            if nr in {"a", "verse"} and i >= pen:
                # Controlled release after the chorus.
                _mul_lp(row, "counter", 1.0 - 0.42 * s)
                _mul_lp(row, "arp", 1.0 - 0.18 * s)
                _mul_lp(row, "chords", 1.0 - 0.12 * s)
                _mul_lp(row, "melody", 1.0 - 0.06 * s)
                row["drop_level"] = _clamp01(float(row.get("drop_level", 0.0) or 0.0) + (0.16 if i == pen else 0.24) * s)
                row["lead_focus"] = _clamp01(float(row.get("lead_focus", 0.0) or 0.0) * (1.0 - 0.10 * s))

    return rows
