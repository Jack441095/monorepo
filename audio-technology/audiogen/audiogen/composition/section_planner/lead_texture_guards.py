"""Lead/arp texture guards for section plans."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from midi.midi_range_limiter import RANGE_LIMITER

from ..section_plan import SectionPlan

def _arp_bed_suppressed_for_section(emotion: Any, owner: Any) -> bool:
    """True when section or song-primary emotion opts out of the arp bed."""
    try:
        from data.emotion_profiles import section_arp_bed_suppressed

        primary = str(getattr(owner, "_song_primary_emotion_name", "") or "")
        return bool(section_arp_bed_suppressed(section_emotion=emotion, primary_emotion_name=primary))
    except Exception:
        return False


def _perceptual_scale_emotion(owner: Any, section_emotion: Any) -> Any:
    """Melody-scale identity follows the song primary emotion when set."""
    try:
        from data.emotion_scales import resolve_perceptual_scale_emotion

        return resolve_perceptual_scale_emotion(
            section_emotion,
            primary_emotion_name=str(getattr(owner, "_song_primary_emotion_name", "") or ""),
        )
    except Exception:
        return section_emotion


def _stabilize_low_flow_lead_harmony(
    plan: SectionPlan,
    *,
    emotion_name: str,
    tempo_multiplier: float,
) -> int:
    """
    For low-flow emotions, keep strong-beat and long lead notes inside the active
    chord more often so the topline reads as belonging to the harmony.
    """
    name = str(emotion_name or "").strip().lower()
    try:
        tempo_m = float(tempo_multiplier)
    except Exception:
        tempo_m = 1.0
    low_flow = name in {
        "sadness",
        "grief",
        "remorse",
        "disappointment",
        "relief",
        "caring",
        "love",
        "admiration",
        "calm",
        "peaceful",
        "serenity",
    } or tempo_m <= 0.72
    if not low_flow:
        return 0
    if not getattr(plan, "melody_events", None) or not getattr(plan, "chosen_chord", None):
        return 0

    try:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        bars = int(getattr(plan, "bars", 0) or 0)
    except Exception:
        return 0
    if bpb <= 1e-6 or bars <= 0:
        return 0

    pcs_by_bar: List[set[int]] = []
    for bi in range(bars):
        pcs: set[int] = set()
        try:
            if bi < len(plan.chosen_chord):
                pcs = {int(n) % 12 for n in (plan.chosen_chord[bi] or []) if isinstance(n, int) and int(n) > 0}
        except Exception:
            pcs = set()
        pcs_by_bar.append(set(pcs))

    def _nearest_with_pc(m: int, pc: int) -> int:
        base = int(m)
        cands = [base + k for k in (-24, -12, 0, 12, 24)]
        best = None
        best_d = 999
        for x in cands:
            x2 = int(x + ((pc - (x % 12)) % 12))
            d = abs(int(x2) - int(base))
            if d < best_d:
                best_d = d
                best = x2
        return int(best if best is not None else base)

    changed = 0
    out = list(plan.melody_events or [])
    eps = 0.08
    for i, ev in enumerate(out):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
            continue
        st = float(ev[3])
        dur = float(ev[4])
        bar = int(st // bpb)
        if bar < 0 or bar >= bars:
            continue
        pcs = pcs_by_bar[bar] if bar < len(pcs_by_bar) else set()
        if not pcs:
            continue
        beat_in_bar = float(st - (bar * bpb))
        on_strong = any(abs(float(beat_in_bar) - sb) <= eps for sb in (0.0, 2.0))
        if not (on_strong or dur >= 1.0):
            continue
        midi0 = int(ev[1])
        if int(midi0) % 12 in pcs:
            continue
        midi1 = int(RANGE_LIMITER.clamp_note(_nearest_with_pc(int(midi0), int(min(list(pcs), key=lambda pc: min(abs(int(pc) - (int(midi0) % 12)), 12 - abs(int(pc) - (int(midi0) % 12)))))), 2))
        if midi1 == midi0:
            continue
        ev2 = list(ev)
        ev2[1] = int(midi1)
        out[i] = tuple(ev2)
        changed += 1
    if changed > 0:
        plan.melody_events = out
    return int(changed)


def _supportive_arp_follow_lead(
    arp_events: List[tuple],
    melody_events: List[tuple],
    *,
    beats_per_bar: float,
    bars: int,
    follow: float,
    rng: Any,
    deterministic_rng: Any = None,
    mask_strength: float = 0.0,
) -> List[tuple]:
    if not arp_events or not melody_events:
        return list(arp_events or [])
    bpb = float(beats_per_bar or 0.0)
    bars_i = int(bars or 0)
    follow = max(0.0, min(1.0, float(follow)))
    mask_strength = max(0.0, min(1.0, float(mask_strength)))
    if bpb <= 1e-9 or bars_i <= 0 or follow <= 1e-6:
        return list(arp_events or [])

    lead_ints: List[Tuple[float, float]] = []
    mel_dur = [0.0 for _ in range(bars_i)]
    for ev in list(melody_events or []):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
            continue
        st = float(ev[3])
        dur = float(ev[4])
        if dur <= 1e-9:
            continue
        en = st + dur
        lead_ints.append((st, en))
        b0 = int(st // bpb)
        b1 = int((en - 1e-9) // bpb)
        for bi in range(max(0, b0), min(bars_i, b1 + 1)):
            seg_s = max(st, float(bi) * bpb)
            seg_e = min(en, float(bi + 1) * bpb)
            if seg_e > seg_s + 1e-9:
                mel_dur[bi] += float(seg_e - seg_s)
    activity = [float(max(0.0, min(1.0, d / bpb))) for d in mel_dur]
    if activity:
        mx = float(max(activity)) if max(activity) > 1e-9 else 1.0
        if mx > 1e-9:
            activity = [float(max(0.0, min(1.0, a / mx))) for a in activity]

    def _overlap_amount(s0: float, e0: float) -> float:
        total = 0.0
        for ls, le in lead_ints:
            if e0 <= ls + 1e-9 or s0 >= le - 1e-9:
                continue
            total += max(0.0, min(e0, le) - max(s0, ls))
        return float(total)

    def _find_gap_start(bar: int, cur_start: float, dur: float) -> Optional[float]:
        bar_start = float(bar) * bpb
        bar_end = float(bar + 1) * bpb
        step = 0.5 if bpb >= 2.0 else max(0.25, bpb / 4.0)
        cands: List[float] = []
        t = bar_start + step
        while t + dur <= bar_end + 1e-9:
            cands.append(float(t))
            t += step
        cands = sorted(
            cands,
            key=lambda x: (
                abs((x - bar_start) - round(x - bar_start)) <= 1e-6,
                abs(float(x) - float(cur_start)),
            ),
        )
        for cand in cands:
            if _overlap_amount(float(cand), float(cand) + float(dur)) <= 1e-6:
                return float(cand)
        return None

    out: List[tuple] = []
    for ev in list(arp_events or []):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
            out.append(ev)
            continue
        ch, midi, vel, st, dur, notes = ev
        t0 = float(st)
        d0 = float(dur)
        bar = int(t0 // bpb) if bpb > 1e-9 else 0
        if bar < 0 or bar >= bars_i or bar >= len(activity):
            out.append(ev)
            continue
        a = float(activity[bar])
        amt = float(follow) * float(a)
        if amt <= 1e-9:
            out.append(ev)
            continue

        beat_in_bar = float(t0 % bpb) if bpb > 1e-9 else 0.0
        near_int = abs(beat_in_bar - round(beat_in_bar)) <= 1e-6
        is_strong = (abs(beat_in_bar - 0.0) <= 1e-6) or (abs(beat_in_bar - 2.0) <= 1e-6)
        is_weak = not near_int
        is_bar_end_anchor = beat_in_bar >= max(0.0, float(bpb) - max(1.0, float(d0) + 0.25))

        overlap_beats = _overlap_amount(float(t0), float(t0) + float(d0))
        overlaps_lead = overlap_beats > 1e-6
        long_lead_overlap = overlaps_lead and overlap_beats >= max(0.45, 0.65 * float(d0))

        st2 = float(t0)
        if overlaps_lead and is_weak:
            gap_start = _find_gap_start(bar, t0, d0)
            if gap_start is not None:
                st2 = float(gap_start)
                overlap_beats = _overlap_amount(float(st2), float(st2) + float(d0))
                overlaps_lead = overlap_beats > 1e-6
                long_lead_overlap = overlaps_lead and overlap_beats >= max(0.45, 0.65 * float(d0))
                if not overlaps_lead:
                    amt = max(0.0, float(amt) - 0.12)

        if overlaps_lead:
            amt = min(1.0, float(amt) + 0.16 + (0.12 if long_lead_overlap else 0.0))
            if is_weak and mask_strength > 1e-6:
                amt = min(1.0, float(amt) + 0.12 * float(mask_strength))

        vscale = max(0.38, 1.0 - 0.46 * float(amt))
        if overlaps_lead and long_lead_overlap and is_weak:
            vscale = max(0.26, 1.0 - 0.62 * float(amt))
        elif not overlaps_lead and a < 0.45 and is_weak:
            vscale = min(1.08, float(vscale) + 0.08)
        if overlaps_lead and is_weak and mask_strength > 1e-6:
            vscale = max(0.24, float(vscale) - 0.10 * float(mask_strength))
        if is_bar_end_anchor:
            # References keep the arp finishing the bar even under the lead.
            # Let this note duck, but keep it audible enough to complete the pattern.
            vscale = max(float(vscale), 0.42)
        vel2 = int(max(1, min(127, round(float(vel) * float(vscale)))))

        drop = False
        if overlaps_lead and is_weak and (not is_bar_end_anchor) and float(amt) >= 0.60:
            try:
                r = (
                    deterministic_rng("arp_density_follow", int(bar), int(round(st2 * 1000.0)))
                    if callable(deterministic_rng)
                    else rng
                )
                p = 0.10 + 0.34 * (float(amt) - 0.60) / 0.40
                if long_lead_overlap:
                    p += 0.12
                if mask_strength > 1e-6:
                    p += 0.10 * float(mask_strength)
                if getattr(r, "random", rng.random)() < max(0.0, min(0.55, float(p))):
                    drop = True
            except Exception:
                drop = False
        if drop and not is_strong and not is_bar_end_anchor:
            continue

        out.append((int(ch), int(midi), int(vel2), float(st2), float(d0), notes))

    return sorted(out, key=lambda ev: (float(ev[3]), int(ev[1]) if isinstance(ev, tuple) and len(ev) >= 2 else 0))

