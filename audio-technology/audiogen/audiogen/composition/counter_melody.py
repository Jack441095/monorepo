from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

from midi.midi_range_limiter import RANGE_LIMITER

if TYPE_CHECKING:
    from .harmonic_plan import HarmonicPlan


@dataclass(frozen=True)
class CounterMelodyConfig:
    channel: int = 5
    octave_offset: int = 0
    # Only generate inside this bar window (inclusive start, exclusive end).
    # Kept as defaults/fallbacks; short arranged sections adapt this window by role.
    start_bar: int = 8
    end_bar: int = 13
    # Density: roughly notes per bar.
    notes_per_bar: float = 2.0


def _is_strong_beat(t: float) -> bool:
    ph = float(t) % 1.0
    return ph < 1e-6 or abs(ph - 0.5) < 1e-6


def _degree_from_midi(midi: int, root_midi: int, scale_pcs: Sequence[int]) -> Optional[int]:
    rel = (int(midi) - int(root_midi)) % 12
    if rel not in scale_pcs:
        return None
    return int(scale_pcs.index(rel))


def _resolve_counter_window(
    *,
    bars: int,
    cfg: CounterMelodyConfig,
    section_role: Optional[str] = None,
) -> Tuple[int, int]:
    total_bars = max(0, int(bars))
    if total_bars <= 0:
        return 0, 0

    start_bar = max(0, int(cfg.start_bar))
    end_bar = max(start_bar, min(total_bars, int(cfg.end_bar)))
    role = str(section_role or "").strip().lower()

    # Legacy window works for long sections. The problem case is shorter arranged
    # sections (6-8 bars), where bars 8..13 means "never". For those cases, move
    # the counter line into a role-aware response window.
    if start_bar < total_bars and end_bar > start_bar:
        return start_bar, end_bar

    if total_bars <= 2:
        return 0, total_bars

    start_frac, end_frac = {
        "intro": (0.50, 1.00),
        "a": (0.42, 0.92),
        "pre_chorus": (0.26, 0.95),
        "b": (0.18, 0.88),
        "tag": (0.14, 0.92),
        "a_prime": (0.24, 0.90),
        "outro": (0.34, 0.84),
    }.get(role, (0.32, 0.90))

    start_bar = int(round(float(total_bars) * float(start_frac)))
    end_bar = int(round(float(total_bars) * float(end_frac)))
    start_bar = max(0, min(total_bars - 1, start_bar))
    min_span = 2 if total_bars >= 4 else 1
    end_bar = max(start_bar + min_span, end_bar)
    end_bar = min(total_bars, end_bar)
    return int(start_bar), int(end_bar)


def generate_counter_melody_events(
    *,
    emotion,
    chords: List[str],
    roots: List[int],
    bars: int,
    beats_per_bar: float,
    cadence_window: Optional[List[float]] = None,
    lead_events: Optional[List[Tuple]] = None,
    motif_slots: Optional[List[dict]] = None,
    motif_rhythms: Optional[Sequence[float]] = None,
    cfg: CounterMelodyConfig = CounterMelodyConfig(),
    section_role: Optional[str] = None,
    mode: str = "counter",
    strings_hold_beats: float = 3.5,
    strings_velocity_scale: float = 0.92,
) -> List[Tuple]:
    """
    Rule-based sparse counterline:
    - chord tones on strong beats
    - simple neighbor/passing on weak beats
    - avoids cadence bars
    - stays register-separated from the lead by clamping to channel range
    """
    if bars <= 0 or beats_per_bar <= 0 or not roots or not chords:
        return []

    mode_lc = str(mode or "counter").strip().lower()
    scale = list(getattr(emotion, "scale_intervals", []) or [])
    if not scale:
        return []
    scale_pcs = [int(iv) % 12 for iv in scale]

    start_bar, end_bar = _resolve_counter_window(
        bars=int(bars),
        cfg=cfg,
        section_role=section_role,
    )
    if end_bar <= start_bar:
        return []

    # Pick a starting degree from the lead (if available), otherwise tonic.
    deg = 0
    if lead_events:
        try:
            # Use first lead note in the window.
            t0 = float(start_bar) * float(beats_per_bar)
            cand = next((e for e in lead_events if len(e) == 6 and int(e[0]) == 2 and float(e[3]) >= t0), None)
            if cand is not None:
                bar0 = int(float(cand[3]) // float(beats_per_bar))
                root0 = int(roots[bar0]) if 0 <= bar0 < len(roots) else int(roots[0])
                d0 = _degree_from_midi(int(cand[1]), int(root0), scale_pcs)
                if d0 is not None:
                    deg = int(d0)
        except Exception:
            deg = 0

    out: List[Tuple] = []

    # Motif windows (theme statements): drive a more intentional counterline.
    motif_windows: List[Tuple[float, float, str]] = []
    try:
        for t in list(motif_slots or []):
            if not isinstance(t, dict):
                continue
            if str(t.get("motif_id", "") or "") != "theme":
                continue
            v = str(t.get("motif_variant", "") or "")
            t0 = float(t.get("start_beats", 0.0))
            t1 = t0 + float(t.get("length_beats", 0.0))
            if t1 > t0 + 1e-6:
                motif_windows.append((t0, t1, v))
    except Exception:
        motif_windows = []

    def _lead_pitch_at(t: float) -> Optional[int]:
        if not lead_events:
            return None
        for ev in lead_events:
            try:
                if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                    continue
                st = float(ev[3])
                en = st + float(ev[4])
                if st - 1e-6 <= float(t) <= en - 1e-6:
                    if isinstance(ev[1], int):
                        return int(ev[1])
                    if isinstance(ev[5], list) and ev[5] and isinstance(ev[5][0], int):
                        return int(ev[5][0])
            except Exception:
                continue
        return None

    def _counter_midi_from_degree(deg0: int, root: int, octave_shift: int = 0) -> int:
        midi = int(root) + int(scale[int(deg0) % len(scale)]) + int(octave_shift)
        midi = int(RANGE_LIMITER.clamp_note(int(midi), int(cfg.channel)))
        return int(midi)

    def _pick_harmony_degree(lead_deg: int, chord_degs: set[int], *, prefer_sixth: bool) -> int:
        # Prefer 3rd or 6th above the lead (diatonic degree offsets).
        offs = [5, 2] if prefer_sixth else [2, 5]
        for off in offs:
            cand = (int(lead_deg) + int(off)) % 7
            # On strong beats, keep chord tone if possible.
            if cand in chord_degs:
                return int(cand)
        # Otherwise just use nearest chord tone to lead.
        try:
            return int(min(chord_degs, key=lambda cd: min(abs(int(cd) - int(lead_deg)), 7 - abs(int(cd) - int(lead_deg)))))
        except Exception:
            return int(lead_deg)

    def _is_in_motif_window(t: float) -> Optional[str]:
        for t0, t1, v in motif_windows:
            if float(t0) - 1e-6 <= float(t) <= float(t1) + 1e-6:
                return str(v or "")
        return None

    # Build per-bar motif onsets (imitation rhythm) if available.
    motif_onsets_in_bar: List[float] = []
    if motif_rhythms:
        try:
            t = 0.0
            for r in list(motif_rhythms):
                motif_onsets_in_bar.append(float(t))
                t += float(r)
            motif_onsets_in_bar = [o for o in motif_onsets_in_bar if 0.0 - 1e-6 <= o < float(beats_per_bar) - 1e-6]
        except Exception:
            motif_onsets_in_bar = []

    def _clamp_counter_note(midi: int) -> int:
        return int(RANGE_LIMITER.clamp_note(int(midi), int(cfg.channel)))

    def _build_strings_harmony_events() -> List[Tuple]:
        out_strings: List[Tuple] = []
        vel_m = float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0)
        vel_scale = max(0.2, min(1.6, float(strings_velocity_scale)))
        vel = int(max(1, min(127, round(68 * vel_m * vel_scale))))
        hold = max(0.5, min(float(beats_per_bar), float(strings_hold_beats)))
        for bar in range(start_bar, end_bar):
            try:
                if cadence_window and 0 <= bar < len(cadence_window) and float(cadence_window[bar]) >= 0.95:
                    continue
            except Exception:
                pass
            root = int(roots[bar]) if 0 <= bar < len(roots) else int(roots[0])
            chord = chords[bar] if 0 <= bar < len(chords) else chords[0]
            chord_degs = {0, 2, 4}
            try:
                from composition.motif_plan import MotifPlanManager

                chord_degs = set(MotifPlanManager._chord_degrees(MotifPlanManager, chord, root, scale_pcs))  # type: ignore[misc]
            except Exception:
                chord_degs = {0, 2, 4}
            if not chord_degs:
                chord_degs = {0, 2, 4}

            bar_start = float(bar) * float(beats_per_bar)
            lead_pitch = _lead_pitch_at(float(bar_start))
            lead_deg = _degree_from_midi(int(lead_pitch), int(root), scale_pcs) if lead_pitch is not None else None
            if lead_deg is None:
                base_deg = int(min(chord_degs))
            else:
                base_deg = _pick_harmony_degree(int(lead_deg), set(chord_degs), prefer_sixth=bool((bar % 2) == 1))
            if base_deg not in chord_degs:
                try:
                    base_deg = int(min(chord_degs, key=lambda cd: min(abs(int(cd) - int(base_deg)), 7 - abs(int(cd) - int(base_deg)))))
                except Exception:
                    base_deg = int(min(chord_degs))

            # Keep this layer under the lead and under most chord tops.
            midi = _counter_midi_from_degree(int(base_deg), int(root), int(cfg.octave_offset) - 12)
            midi = _clamp_counter_note(int(midi))
            if lead_pitch is not None and int(midi) >= int(lead_pitch) - 2:
                midi = _clamp_counter_note(int(midi) - 12)
            out_strings.append((int(cfg.channel), int(midi), int(vel), float(bar_start), float(hold), [int(midi)]))
        return out_strings

    if mode_lc in {"strings", "strings_harmony", "harmony_strings"}:
        return _build_strings_harmony_events()

    # Simple deterministic grid: 0, 2 (strong), plus one weak pickup optionally.
    for bar in range(start_bar, end_bar):
        try:
            if cadence_window and 0 <= bar < len(cadence_window) and float(cadence_window[bar]) >= 0.95:
                continue
        except Exception:
            pass

        root = int(roots[bar]) if 0 <= bar < len(roots) else int(roots[0])
        chord = chords[bar] if 0 <= bar < len(chords) else chords[0]

        # Approx chord degrees: use simple triad degrees from roman symbol parsing in motif_plan if available.
        # Fallback: tonic triad degrees.
        chord_degs = {0, 2, 4}
        try:
            from composition.motif_plan import MotifPlanManager

            chord_degs = set(MotifPlanManager._chord_degrees(MotifPlanManager, chord, root, scale_pcs))  # type: ignore[misc]
        except Exception:
            chord_degs = {0, 2, 4}

        bar_start = float(bar) * float(beats_per_bar)
        onsets = [0.0, 2.0] if beats_per_bar >= 4.0 else [0.0]
        # Optional weak-beat answer in the middle.
        if float(cfg.notes_per_bar) >= 2.25 and beats_per_bar >= 4.0:
            onsets = [0.0, 1.5, 2.0]
        # Motif imitation: inside motif windows, prefer the hook rhythm as the counter grid.
        if motif_onsets_in_bar:
            try:
                # Only if this bar overlaps a motif window.
                if _is_in_motif_window(float(bar_start) + 1e-6) is not None:
                    onsets = list(motif_onsets_in_bar)
            except Exception:
                pass

        for o in onsets:
            t = bar_start + float(o)
            variant = _is_in_motif_window(float(t))
            lead_pitch = _lead_pitch_at(float(t))
            lead_deg = None
            if lead_pitch is not None:
                try:
                    lead_deg = _degree_from_midi(int(lead_pitch), int(root), scale_pcs)
                except Exception:
                    lead_deg = None
            # choose degree
            if variant is not None and lead_deg is not None:
                # Theme window: harmonize the lead (3rds/6ths), alternating for motion.
                prefer_sixth = bool(int(round(float(o) * 2.0)) % 2 == 1)
                deg = _pick_harmony_degree(int(lead_deg), set(chord_degs), prefer_sixth=prefer_sixth)
            else:
                if _is_strong_beat(t):
                    # nearest chord tone
                    deg = min(chord_degs, key=lambda cd: min(abs(int(cd) - int(deg)), 7 - abs(int(cd) - int(deg))))
                else:
                    # weak beat: neighbor if possible
                    for delta in (-1, 1, -2, 2):
                        cand = (int(deg) + int(delta)) % 7
                        if cand not in chord_degs:
                            deg = int(cand)
                            break

            midi = _counter_midi_from_degree(int(deg), int(root), int(cfg.octave_offset))
            # Avoid near-unison with the lead at the same time by shifting down an octave if needed.
            if lead_pitch is not None:
                try:
                    if abs(int(midi) - int(lead_pitch)) <= 2:
                        midi = _counter_midi_from_degree(int(deg), int(root), int(cfg.octave_offset) - 12)
                except Exception:
                    pass
            vel_m = float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0)
            vel = int(max(1, min(127, round(76 * vel_m))))
            dur = 0.9 if _is_strong_beat(t) else 0.5
            out.append((int(cfg.channel), int(midi), int(vel), float(t), float(dur), [int(midi)]))

    return out


def generate_counter_melody_events_from_harmonic_plan(
    harmonic: "HarmonicPlan",
    *,
    emotion,
    **kwargs,
) -> List[Tuple]:
    """Like :func:`generate_counter_melody_events` using a :class:`~.harmonic_plan.HarmonicPlan` snapshot."""
    from .harmonic_plan import HarmonicPlan as _HP

    if not isinstance(harmonic, _HP):
        raise TypeError("harmonic must be a HarmonicPlan instance")
    harmonic.validate()
    return generate_counter_melody_events(
        emotion=emotion,
        chords=list(harmonic.chords),
        roots=list(harmonic.roots),
        bars=int(harmonic.bars),
        beats_per_bar=float(harmonic.beats_per_bar),
        **kwargs,
    )


def apply_countermelody_script(
    counter_events: List[Tuple],
    *,
    bars: int,
    beats_per_bar: float,
    section_role: Optional[str] = None,
    next_role: Optional[str] = None,
    lead_events: Optional[List[Tuple]] = None,
    phrase_roles: Optional[List[str]] = None,
    cadence_window: Optional[List[float]] = None,
    texture_by_bar: Optional[List[dict]] = None,
    strength: float = 0.72,
) -> List[Tuple]:
    if not counter_events or bars <= 0 or beats_per_bar <= 1e-9:
        return list(counter_events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return list(counter_events)

    role_lc = str(section_role or "").strip().lower()
    next_lc = str(next_role or "").strip().lower()
    phrase_roles = list(phrase_roles or [])
    cadence_window = list(cadence_window or [])
    texture = list(texture_by_bar or [])
    bars_i = int(max(0, int(bars)))
    bpb = float(beats_per_bar)

    lead_counts = [0 for _ in range(bars_i)]
    for ev in list(lead_events or []):
        try:
            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                continue
            bi = int(float(ev[3]) // bpb)
            if 0 <= bi < bars_i:
                lead_counts[bi] += 1
        except Exception:
            continue

    allowed_bars = set(range(bars_i))
    if role_lc in {"a", "verse"}:
        # Let verse counter act as a late answer, not an equal co-lead.
        start = max(0, int(round(float(bars_i) * (0.50 - 0.10 * s))))
        allowed_bars = set(range(start, bars_i))
    elif role_lc == "pre_chorus":
        # Pre-chorus counter should bloom later as the build develops.
        start = max(0, int(round(float(bars_i) * (0.35 + 0.10 * (1.0 - s)))))
        allowed_bars = set(range(start, bars_i))
    elif role_lc in {"b", "chorus", "hook", "tag"}:
        # Leave hook entry open, then answer after it lands.
        start = 1 if bars_i >= 2 else 0
        allowed_bars = set(range(start, bars_i))
    elif role_lc in {"outro"}:
        allowed_bars = set(range(0, max(1, bars_i - 1)))

    if next_lc in {"a", "verse"} and bars_i >= 1:
        # Release into verse: avoid the final bar.
        allowed_bars.discard(int(bars_i - 1))

    filtered: List[Tuple] = []
    for ev in list(counter_events or []):
        try:
            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 5):
                filtered.append(ev)
                continue
            st = float(ev[3])
            bi = int(st // bpb)
            if bi < 0 or bi >= bars_i:
                continue
            if bi not in allowed_bars:
                continue
            if 0 <= bi < len(cadence_window) and float(cadence_window[bi]) >= (0.80 + 0.15 * s):
                continue
            pr = str(phrase_roles[bi] or "").strip().lower() if 0 <= bi < len(phrase_roles) else ""
            if pr in {"cadence"}:
                continue
            if pr in {"opening"} and role_lc in {"a", "verse", "b", "chorus", "hook", "tag"}:
                continue
            if pr in {"answer"} and int(lead_counts[bi]) > 1:
                continue
            if role_lc == "pre_chorus" and bi == 0:
                continue
            if 0 <= bi < len(texture) and isinstance(texture[bi], dict):
                lp = texture[bi].get("layer_presence", {})
                counter_lp = float(lp.get("counter", 1.0) or 1.0) if isinstance(lp, dict) else 1.0
                if counter_lp < (0.30 + 0.12 * (1.0 - s)):
                    continue
            filtered.append(ev)
        except Exception:
            filtered.append(ev)
    return filtered
