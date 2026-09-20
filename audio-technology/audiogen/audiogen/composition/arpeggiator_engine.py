# composition/arpeggiator_engine.py — realtime Arpeggiator; curves live in data/arp_curve_defaults.py.
from __future__ import annotations
from audiogen_core.config import resolve_config

import random
from typing import Any, Dict, List, Optional, Tuple

from composition.motif_plan import SongHookMotif
from composition.phrase_intent import PhraseIntent
from audiogen_core.composition_runtime_flags import (
    phrase_length_bars_clamped,
    stable_emotion_dynamics_enabled,
    stable_emotion_velocity_multiplier,
    tension_trajectory_params,
)
from data.arp_curve_defaults import CONTOUR_TO_ARP_MODE, arp_mode_for_role, arp_profile_for_emotion, normalize_arp_mode
from data.music_data import EmotionProfile
from midi.midi_range_limiter import RANGE_LIMITER

from .harmonic_plan import HarmonicPlan


def _force_arp_midi_differs_from_prev(
    prev: Optional[int],
    cur: int,
    *,
    tones_step_in: List[int],
    lane_fallback: int,
    channel_i: int,
) -> int:
    """
    Consecutive emitted arp MIDI pitches must never match. Expand the candidate pool
    by octave shifts of chord tones (and as a last resort, small chromatic nudges).
    """
    if prev is None or int(cur) != int(prev):
        return int(cur)
    pool: List[int] = []
    for t in list(tones_step_in or []):
        try:
            pool.append(int(t))
        except Exception:
            continue
    uniq = sorted({int(x) for x in pool})
    if not uniq:
        try:
            uniq = [int(RANGE_LIMITER.clamp_note(int(lane_fallback), int(channel_i)))]
        except Exception:
            uniq = [60]
    expanded: List[int] = []
    seen_e: set[int] = set()
    for p in uniq:
        for delta in (0, 12, -12, 24, -24, 36, -36):
            try:
                c = int(RANGE_LIMITER.clamp_note(int(p) + int(delta), int(channel_i)))
            except Exception:
                c = int(p) + int(delta)
            if int(c) == int(prev):
                continue
            if int(c) not in seen_e:
                seen_e.add(int(c))
                expanded.append(int(c))
    cur_i = int(cur)
    if expanded:
        return int(min(expanded, key=lambda n: (abs(int(n) - cur_i), abs(int(n) - int(prev)))))
    for d in range(1, 13):
        for sgn in (-1, 1):
            try:
                c2 = int(RANGE_LIMITER.clamp_note(int(prev) + int(sgn * d), int(channel_i)))
            except Exception:
                c2 = int(prev) + int(sgn * d)
            if int(c2) != int(prev):
                return int(c2)
    return int(cur)


def repair_arp_consecutive_same_midi(
    events: List[Tuple],
    *,
    channel: int = 3,
    chord_notes_by_bar: Optional[List[List[int]]] = None,
    beats_per_bar: float = 4.0,
) -> List[Tuple]:
    """
    Ensure a monophonic arpeggiator line never plays the same MIDI pitch twice in a row.
    Default channel is 3 (arp bed); channel 2 is used for arp-style melody-lane generation.
    Events are processed in chronological order by start beat.
    """
    if not events:
        return events
    ch_i = int(channel)
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    ordered = sorted(events, key=lambda e: float(e[3]) if (isinstance(e, tuple) and len(e) >= 4) else 0.0)
    out: List[Tuple] = []
    prev_m: Optional[int] = None
    for ev in ordered:
        if not isinstance(ev, tuple) or len(ev) != 6 or int(ev[0]) != ch_i:
            out.append(ev)
            continue
        ch, midi, vel, st, dur, notes = ev
        try:
            m = int(notes[0]) if isinstance(notes, list) and notes else int(midi)
        except Exception:
            out.append(ev)
            continue
        tones_seed: List[int] = []
        try:
            bi = int(float(st) // bpb)
            if chord_notes_by_bar and 0 <= bi < len(chord_notes_by_bar):
                row = chord_notes_by_bar[bi]
                if isinstance(row, list):
                    tones_seed.extend(int(x) for x in row if isinstance(x, int))
        except Exception:
            pass
        if prev_m is not None and int(m) == int(prev_m):
            if not tones_seed:
                tones_seed = [int(prev_m) + d for d in (-12, 0, 12, -24, 24)]
            m = _force_arp_midi_differs_from_prev(
                int(prev_m),
                int(m),
                tones_step_in=list(tones_seed),
                lane_fallback=int(m),
                channel_i=ch_i,
            )
        nm = int(m)
        nnotes = list(notes) if isinstance(notes, list) else [nm]
        if nnotes:
            nnotes[0] = nm
        out.append((int(ch), int(nm), int(vel), float(st), float(dur), nnotes))
        prev_m = int(nm)
    return out


class Arpeggiator:
    """Generate directional arp events from chord tones."""

    def __init__(self, owner):
        self.owner = owner

    def _voiced_tones_completed_with_symbol(
        self,
        *,
        chord: str,
        root: int,
        voiced: List[int],
        lane_center: int,
        channel: int,
        lane_half_width: int,
    ) -> List[int]:
        """
        Ensure the arp tone pool includes every pitch class implied by `chord`,
        while still tracking the realized voicing pitches when possible.

        This prevents "random subset" feelings when voicings are sparse (e.g. shells)
        but the harmony symbol carries extensions.
        """
        voiced2 = [int(n) for n in (voiced or []) if isinstance(n, int)]
        if not voiced2:
            return []
        try:
            sym = [int(n) for n in self.owner._chord_symbol_to_notes(chord, int(root)) if isinstance(n, int)]
        except Exception:
            sym = []
        pcs_v = {int(n) % 12 for n in voiced2}
        pcs_s = {int(n) % 12 for n in sym} if sym else set()
        missing = sorted(int(pc) for pc in (pcs_s - pcs_v)) if pcs_s else []
        if not missing:
            return voiced2

        lo = int(lane_center) - int(lane_half_width)
        hi = int(lane_center) + int(lane_half_width)
        base_oct = (int(lane_center) // 12) * 12
        extras: List[int] = []
        for pc in missing:
            cands = [base_oct + int(pc) + 12 * k for k in (-2, -1, 0, 1, 2)]
            in_lane = [n for n in cands if int(lo) <= int(n) <= int(hi)]
            pick = self._nearest_in_register(in_lane or cands, int(lane_center))
            extras.append(int(pick))

        merged = list(voiced2) + list(extras)
        merged = sorted({RANGE_LIMITER.clamp_note(int(n), int(channel)) for n in merged})
        return merged or voiced2

    @staticmethod
    def _arp_speed_multiplier_for_emotion(emotion: EmotionProfile) -> float:
        name = (getattr(emotion, "name", "") or "").lower()
        profile = arp_profile_for_emotion(name)
        if profile.get("speed_mult") is not None:
            return max(0.72, min(1.28, float(profile["speed_mult"])))
        tempo_m = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
        vel_m = stable_emotion_velocity_multiplier(emotion)
        dens = float(getattr(emotion, "density", 1.0) or 1.0)
        energy = (tempo_m + vel_m + dens) / 3.0

        t = (energy - 0.8) / 0.4
        base = 0.75 + 0.60 * max(0.0, min(1.0, t))

        if name in {"excitement", "joy", "amusement", "optimism", "surprise", "pride"}:
            base += 0.12
        elif name in {"sadness", "grief", "remorse", "fear", "disappointment"}:
            base -= 0.12

        return max(0.72, min(1.28, float(base)))

    @staticmethod
    def _nearest_in_register(options: List[int], target: int) -> int:
        if not options:
            return int(target)
        return int(min(options, key=lambda n: abs(int(n) - int(target))))

    def _chord_tones_in_lane(
        self,
        chord: str,
        root: int,
        *,
        lane_center: int,
        channel: int,
        lane_half_width: int = 12,
        voiced_chord: Optional[List[int]] = None,
        tones_source: str = "pcs_lane",
    ) -> List[int]:
        tones: List[int] = []
        source = str(tones_source or "").strip().lower()
        if voiced_chord and source == "voiced":
            # Prefer the exact voiced chord pitches as the primary tone pool,
            # then optionally octave-shift them into the lane for rhythmic stability.
            tones = self._voiced_tones_completed_with_symbol(
                chord=str(chord),
                root=int(root),
                voiced=[int(n) for n in voiced_chord if isinstance(n, int)],
                lane_center=int(lane_center),
                channel=int(channel),
                lane_half_width=int(lane_half_width),
            )
        elif voiced_chord:
            # Default: use the chosen voicing to determine pitch classes (so inversion/spread
            # affects the arp color), while still expanding into a lane around
            # `lane_center` for rhythmic stability.
            tones = self._voiced_tones_completed_with_symbol(
                chord=str(chord),
                root=int(root),
                voiced=[int(n) for n in voiced_chord if isinstance(n, int)],
                lane_center=int(lane_center),
                channel=int(channel),
                lane_half_width=int(lane_half_width),
            )
        elif source in {"chord_pcs", "chord"}:
            # Strict chord-tone pool: ensure *all* chord pitch classes are present,
            # mapped into the arp lane with minimal octave drift.
            try:
                raw = [int(n) for n in self.owner._chord_symbol_to_notes(chord, int(root)) if isinstance(n, int)]
            except Exception:
                raw = []
            if not raw:
                return [RANGE_LIMITER.clamp_note(int(lane_center), int(channel))]
            lo = int(lane_center) - int(lane_half_width)
            hi = int(lane_center) + int(lane_half_width)
            pcs = sorted({int(n) % 12 for n in raw})
            base_oct = (int(lane_center) // 12) * 12
            lane_notes: List[int] = []
            for pc in pcs:
                cands = [base_oct + int(pc) + 12 * k for k in (-2, -1, 0, 1, 2)]
                in_lane = [n for n in cands if int(lo) <= int(n) <= int(hi)]
                pick = self._nearest_in_register(in_lane or cands, int(lane_center))
                lane_notes.append(int(pick))
            lane_notes = sorted({RANGE_LIMITER.clamp_note(int(n), int(channel)) for n in lane_notes})
            return lane_notes or [RANGE_LIMITER.clamp_note(int(lane_center), int(channel))]
        else:
            tones = [int(n) for n in self.owner._chord_symbol_to_notes(chord, int(root)) if isinstance(n, int)]
        if not tones:
            return [RANGE_LIMITER.clamp_note(int(lane_center), int(channel))]

        lo = int(lane_center) - int(lane_half_width)
        hi = int(lane_center) + int(lane_half_width)
        pcs = sorted({int(n) % 12 for n in tones})
        base_oct = (int(lane_center) // 12) * 12
        expanded: List[int] = []
        if source == "voiced" and voiced_chord:
            # Expand actual chord tones by octave shifts (preserve voicing pitch classes).
            for n in tones:
                for k in (-2, -1, 0, 1, 2):
                    expanded.append(int(n) + 12 * k)
        else:
            for pc in pcs:
                for k in (-2, -1, 0, 1, 2):
                    expanded.append(base_oct + pc + 12 * k)

        lane = [n for n in expanded if lo <= n <= hi]
        if not lane:
            closest = self._nearest_in_register(expanded, int(lane_center))
            lane = [closest]

        lane = sorted({RANGE_LIMITER.clamp_note(int(n), int(channel)) for n in lane})

        # Arp register guardrail: keep arp tones in the preferred mid band when possible.
        # Without this, the expanded lane can include lower-octave chord tones that
        # cause the arp to hover at the bottom of its range (perceptually “stuck low”).
        if int(channel) == 3 and lane:
            try:
                info = RANGE_LIMITER.get_range_info(3) or {}
                pref_min = int(info.get("preferred_min", 60))
                pref_max = int(info.get("preferred_max", 74))
            except Exception:
                pref_min, pref_max = 60, 74
            band = [int(n) for n in lane if int(pref_min) <= int(n) <= int(pref_max)]
            if len(band) >= 2:
                # Keep multiple tones so the arp can't collapse into a single repeated pitch.
                lane = sorted(set(band))
            elif band:
                # If the preferred band only contains one tone, keep it but also keep
                # at least one nearby alternative tone from the original lane.
                keep = int(band[0])
                alt = None
                try:
                    alt = next((n for n in lane if int(n) != keep), None)
                except Exception:
                    alt = None
                lane = [keep] + ([int(alt)] if alt is not None else [])
                lane = sorted(set(lane))
            else:
                # Fallback: do not hard-collapse to a single tone; keep the closest few.
                ordered = sorted(lane, key=lambda n: abs(int(n) - int(lane_center)))
                lane = sorted(set(ordered[: max(2, min(4, len(ordered)))]))
        return lane or [RANGE_LIMITER.clamp_note(int(lane_center), int(channel))]

    @staticmethod
    def _build_mode_cycle(tones: List[int], arp_mode: str) -> List[int]:
        tones = sorted({int(n) for n in tones})
        if len(tones) <= 1:
            return tones
        if arp_mode == "down":
            return list(reversed(tones))
        if arp_mode == "updown":
            return tones + tones[-2:0:-1]
        if arp_mode == "updown_excl":
            # Ableton-like Up&Down where endpoints are not repeated:
            # C E G -> C E G E (no repeated C or G)
            # With 2 tones, it just alternates without duplicating endpoints.
            if len(tones) <= 2:
                return tones + tones[-2::-1]
            return tones + tones[-2:0:-1]
        if arp_mode == "downup":
            down = list(reversed(tones))
            return down + down[-2:0:-1]
        if arp_mode == "converge":
            cycle: List[int] = []
            left = 0
            right = len(tones) - 1
            while left <= right:
                cycle.append(tones[left])
                if right != left:
                    cycle.append(tones[right])
                left += 1
                right -= 1
            return cycle
        if arp_mode == "diverge":
            cycle = []
            n = len(tones)
            if n % 2 == 1:
                center = n // 2
                cycle.append(tones[center])
                for offset in range(1, center + 1):
                    cycle.append(tones[center - offset])
                    cycle.append(tones[center + offset])
                return cycle

            upper = n // 2
            lower = upper - 1
            cycle.extend([tones[lower], tones[upper]])
            step = 1
            while lower - step >= 0 or upper + step < n:
                if lower - step >= 0:
                    cycle.append(tones[lower - step])
                if upper + step < n:
                    cycle.append(tones[upper + step])
                step += 1
            return cycle
        return tones

    @staticmethod
    def _build_motif_cycle(
        tones: List[int],
        *,
        lane_center: int,
        motif_hook: Optional[SongHookMotif],
        section_role: Optional[str],
        emotion_name: str,
        bar_index: int,
        strength: float,
        drng,
    ) -> Optional[List[int]]:
        """
        Derive a tone ordering from the shared hook motif contour.

        The goal is to preserve the arp's chord-tone lane while letting the
        melodic motif's interval pattern influence how we walk that lane:
        - project motif intervals into a circular index walk over `tones`
        - optionally invert/retrograde the walk for call/response roles
        - keep behaviour deterministic via the owner's deterministic_rng
        """
        if not tones or motif_hook is None:
            return None
        try:
            intervals = list(getattr(motif_hook, "intervals", []) or [])
        except Exception:
            intervals = []
        if not intervals:
            return None
        try:
            contour = str(getattr(motif_hook, "contour", "") or "").lower()
        except Exception:
            contour = ""
        role = str(section_role or "").strip().lower()
        s = max(0.0, min(1.0, float(strength)))
        if s <= 1e-6:
            return None

        # Decide transform mode in a deterministic, lightweight way.
        try:
            r = drng("arp_motif_cycle", int(bar_index), str(role), str(emotion_name), str(contour)) if callable(drng) else random.Random(
                hash(("arp_motif_cycle", bar_index, role, emotion_name, contour)) & 0xFFFFFFFF
            )
        except Exception:
            r = random
        invert = False
        retro = False
        # Chorus / hook: prefer direct or sequence-like feel.
        if role in {"b", "chorus", "hook"}:
            if getattr(r, "random", random.random)() < 0.25 * s:
                retro = True
        # A-prime / tag: lean more toward inverted/answer shapes.
        elif role in {"a_prime", "tag"}:
            if getattr(r, "random", random.random)() < 0.55 * s:
                invert = True
            if getattr(r, "random", random.random)() < 0.40 * s:
                retro = True
        else:
            if getattr(r, "random", random.random)() < 0.30 * s:
                invert = True

        ivs = list(intervals)
        if invert:
            ivs = [-int(i) for i in ivs]
        if retro:
            ivs = list(reversed(ivs))

        n_tones = max(1, len(tones))
        # Map motif stepwalk onto tone indices (circular, to preserve contour).
        idx = 0
        visited: List[int] = []
        for step in ivs:
            try:
                idx = (idx + int(step)) % n_tones
            except Exception:
                continue
            if idx not in visited:
                visited.append(idx)

        # Ensure we visit all tones in the lane at least once; order unvisited
        # by proximity to the lane center to keep register sensible.
        remaining = [i for i in range(n_tones) if i not in visited]
        if remaining:
            try:
                ordered_remaining = sorted(
                    remaining,
                    key=lambda j: abs(int(tones[j]) - int(lane_center)),
                )
            except Exception:
                ordered_remaining = remaining
            visited.extend(ordered_remaining)

        cycle = [int(tones[i]) for i in visited if 0 <= i < n_tones]
        return cycle or None

    @staticmethod
    def _expand_cycle(cycle: List[int], steps: int) -> List[int]:
        if not cycle:
            return []
        return [int(cycle[i % len(cycle)]) for i in range(max(0, int(steps)))]

    @staticmethod
    def _rotate_cycle_to_note(cycle: List[int], prev_note: Optional[int]) -> List[int]:
        if prev_note is None or not cycle:
            return list(cycle)
        best_rot = 0
        best_cost = float("inf")
        for rot in range(len(cycle)):
            first = cycle[rot]
            cost = abs(int(first) - int(prev_note))
            if cost < best_cost:
                best_cost = cost
                best_rot = rot
        return cycle[best_rot:] + cycle[:best_rot]

    def _resolve_mode(
        self,
        *,
        requested_mode: Optional[str],
        phrase_contours: Optional[List[str]],
        bar: int,
        bars: int,
        section_role: Optional[str],
        emotion_name: str = "",
    ) -> str:
        if requested_mode:
            return normalize_arp_mode(requested_mode)
        if phrase_contours:
            phrase_len = max(1, int(round(float(bars) / max(1, len(phrase_contours)))))
            phrase_idx = min(len(phrase_contours) - 1, bar // phrase_len)
            contour = (phrase_contours[phrase_idx] or "").strip().lower()
            mapped = CONTOUR_TO_ARP_MODE.get(contour)
            if mapped:
                return normalize_arp_mode(mapped)
        if emotion_name:
            profile = arp_profile_for_emotion(str(emotion_name))
            mode = profile.get("mode")
            if mode:
                return normalize_arp_mode(str(mode))
        form_mode = getattr(getattr(self.owner, "arrangement_policy", None), "form_mode", "default")
        return arp_mode_for_role(section_role or "", form_mode=form_mode)

    def generate_from_harmonic_plan(
        self,
        emotion: EmotionProfile,
        harmonic: HarmonicPlan,
        target_notes_per_bar: float,
        phrase_contours: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Tuple]:
        """Same as :meth:`generate_from_chords` but takes a frozen :class:`HarmonicPlan` snapshot."""
        harmonic.validate()
        voiced = kwargs.pop("voiced_chords", None)
        if voiced is None:
            voiced = harmonic.voiced_chords_as_lists()
        return self.generate_from_chords(
            emotion,
            list(harmonic.chords),
            list(harmonic.roots),
            int(harmonic.bars),
            float(harmonic.beats_per_bar),
            float(target_notes_per_bar),
            phrase_contours,
            voiced_chords=voiced,
            **kwargs,
        )

    def generate_from_chords(
        self,
        emotion: EmotionProfile,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        target_notes_per_bar: float,
        phrase_contours: Optional[List[str]] = None,
        *,
        phrase_intents: Optional[List[PhraseIntent]] = None,
        channel: int = 2,
        velocity_scale: float = 1.0,
        chosen_lane: Optional[List[int]] = None,
        voiced_chords: Optional[List[List[int]]] = None,
        lead_events: Optional[List[Tuple]] = None,
        swing: float = 0.0,
        lead_ducking: float = 0.65,
        arp_mode: Optional[str] = None,
        section_role: Optional[str] = None,
        arp_plan: Optional[Dict[str, Any]] = None,
        motif_hook: Optional[SongHookMotif] = None,
    ) -> List[Tuple]:
        # Stage-1 PhraseIntent bus: currently advisory/no-op here.
        # (Later stages will use this to drive onset policy, dialogue slots, and harmony roles.)
        del phrase_intents
        if bars <= 0 or beats_per_bar <= 0:
            return []

        emotion_name = (getattr(emotion, "name", "") or "").lower()
        profile = arp_profile_for_emotion(emotion_name)
        # Default arp harmonic policy: cycle through all chord tones (no random subsets).
        # A section/role arp_plan can still override `tones_source`.
        use_all = resolve_config("composition", "arp_use_all_chord_tones_enabled", True, bool)
        if use_all and not (arp_plan and arp_plan.get("tones_source") is not None):
            arp_plan = dict(arp_plan or {})
            arp_plan["tones_source"] = "chord_pcs"
        target_override = None
        try:
            if arp_plan and arp_plan.get("target_notes_per_bar") is not None:
                target_override = float(arp_plan.get("target_notes_per_bar"))
        except Exception:
            target_override = None
        if target_override is None:
            target_override = profile.get("target_notes_per_bar")
        tnpb = float(target_override) if target_override is not None else float(target_notes_per_bar)
        # Allow section-level density scaling (e.g. verse vs chorus) while still using
        # emotion-tuned base targets. This is intentionally multiplicative so it composes
        # with per-emotion profiles rather than replacing them.
        try:
            if arp_plan and arp_plan.get("density_mult") is not None:
                dm = float(arp_plan.get("density_mult") or 1.0)
                dm = max(0.25, min(2.0, float(dm)))
                tnpb *= float(dm)
        except Exception:
            pass
        tnpb = max(4.0, min(16.0, tnpb))
        speed_mult = self._arp_speed_multiplier_for_emotion(emotion)
        tnpb_eff = tnpb * speed_mult
        tnpb_eff = max(4.0, min(16.0, tnpb_eff))
        # Default: steady 16ths for the arp bed (density is still clamped to 16).
        # Allow explicit per-section overrides via `arp_plan["target_notes_per_bar"]`.
        if int(channel) == 3 and not (arp_plan and arp_plan.get("target_notes_per_bar") is not None):
            tnpb_eff = 16.0
        # 4 notes/bar = quarter notes, 8 = eighths, 16 = sixteenths.
        grid = 0.25 if tnpb_eff >= 12.0 else (0.5 if tnpb_eff >= 6.0 else 1.0)
        # Per-emotion override: force a musically consistent grid (e.g. 16ths for high energy).
        # This is applied before `arp_plan["grid"]` so section/role-level overrides can win.
        if profile.get("grid") is not None:
            try:
                grid = float(profile["grid"])
            except Exception:
                pass
        # Section/role override: highest priority (lets verse/chorus feel differ).
        if arp_plan and arp_plan.get("grid") is not None:
            try:
                grid = float(arp_plan["grid"])
            except Exception:
                pass
        # Arp default: when no explicit profile/plan grid is provided, prefer a 16th-note
        # quantization grid so even sparse arps still "read" as arpeggios (density is
        # still controlled by target_notes_per_bar/active steps).
        if int(channel) == 3 and profile.get("grid") is None and not (arp_plan and arp_plan.get("grid") is not None):
            grid = 0.25
        # Guardrail: emotion-driven arp timing must stay musically clear (1/8 or 1/16 only).
        # Snap any computed/overridden value into {0.25, 0.5}.
        try:
            g = float(grid)
            if g < 0.375:
                grid = 0.25
            else:
                grid = 0.5
        except Exception:
            grid = 0.25
        grid = max(0.125, min(2.0, float(grid)))
        steps_per_bar = max(1, int(round(float(beats_per_bar) / float(grid))))

        # Density is controlled by notes-per-bar; `grid` is quantization resolution.
        desired_notes_per_bar = int(round(float(tnpb_eff)))
        desired_notes_per_bar = max(1, min(int(steps_per_bar), int(desired_notes_per_bar)))

        # Choose which step indices in the bar should be active (base pattern).
        # This may be further refined per-bar (e.g. groove-link) later.
        active_steps: set[int] = set()
        try:
            if desired_notes_per_bar >= int(steps_per_bar):
                active_steps = set(range(int(steps_per_bar)))
            else:
                step_interval = float(steps_per_bar) / float(desired_notes_per_bar)
                for i in range(int(desired_notes_per_bar)):
                    s = int(round(float(i) * step_interval))
                    s = max(0, min(int(steps_per_bar) - 1, int(s)))
                    active_steps.add(int(s))
                # Always anchor downbeat.
                active_steps.add(0)
                # If rounding collapsed too much, fill evenly.
                while len(active_steps) < int(desired_notes_per_bar):
                    best = None
                    best_d = -1
                    for s in range(int(steps_per_bar)):
                        if s in active_steps:
                            continue
                        d = min(abs(int(s) - int(t)) for t in active_steps) if active_steps else 999
                        if d > best_d:
                            best_d = d
                            best = s
                    if best is None:
                        break
                    active_steps.add(int(best))
        except Exception:
            active_steps = set(range(int(steps_per_bar)))
        # Motif memory: accent arp hits on the hook rhythm grid, so arp + melody feel related.
        motif_steps: Optional[set[int]] = None
        if motif_hook is not None:
            try:
                onsets = []
                t = 0.0
                for r in list(getattr(motif_hook, "rhythms", []) or []):
                    onsets.append(float(t))
                    t += float(r)
                # Keep only within one bar; map to step indices.
                motif_steps = set()
                for o in onsets:
                    if o < -1e-6 or o >= float(beats_per_bar) - 1e-6:
                        continue
                    motif_steps.add(int(round(float(o) / float(grid))))
            except Exception:
                motif_steps = None

        vel_m = stable_emotion_velocity_multiplier(emotion)
        base_velocity = int(60 * float(vel_m))
        dens = 0.0 if stable_emotion_dynamics_enabled() else float(getattr(emotion, "density", 0.0) or 0.0)
        velocity = int(
            max(
                1,
                min(
                    127,
                    round(
                        base_velocity
                        * (1.0 + float(dens) * 0.3)
                        * float(velocity_scale)
                    ),
                ),
            )
        )
        base_velocity_final = int(velocity)

        # Reference-style feel: arps usually have a clear pulse with subtle accents.
        # Keep this lightweight and deterministic-ish so it reads like "performance",
        # not random jitter.
        # Defaults that propagate the "reference recipe" across all emotions:
        # derive light accent/syncopation/octave motion from emotion energy unless overridden.
        tempo_m = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
        dens_m = 0.0 if stable_emotion_dynamics_enabled() else float(getattr(emotion, "density", 0.0) or 0.0)
        energy = (tempo_m + float(vel_m) + float(dens_m)) / 3.0
        # Normalize energy into 0..1-ish band (0.75..1.20).
        e01 = max(0.0, min(1.0, (float(energy) - 0.75) / 0.45))

        accent_strength = 0.06 + 0.12 * e01
        try:
            if profile.get("accent_strength") is not None:
                accent_strength = float(profile["accent_strength"])  # type: ignore[assignment]
        except Exception:
            pass
        try:
            if arp_plan and arp_plan.get("accent_strength") is not None:
                accent_strength = float(arp_plan.get("accent_strength"))
        except Exception:
            pass
        accent_strength = max(0.0, min(0.35, float(accent_strength)))

        octave_reach_prob = 0.06 + 0.16 * e01
        try:
            if profile.get("octave_reach_prob") is not None:
                octave_reach_prob = float(profile["octave_reach_prob"])  # type: ignore[assignment]
        except Exception:
            pass
        try:
            if arp_plan and arp_plan.get("octave_reach_prob") is not None:
                octave_reach_prob = float(arp_plan.get("octave_reach_prob"))
        except Exception:
            pass
        octave_reach_prob = max(0.0, min(0.45, float(octave_reach_prob)))
        # Arp bed (channel 3): allow octave reaches by default (Ableton-like), but
        # keep them controllable via composition config.
        if int(channel) == 3:
            oct_on = resolve_config("composition", "arp_octave_reach_enabled", True, bool)
            oct_st = resolve_config("composition", "arp_octave_reach_strength", 1.0, float)
            oct_st = max(0.0, min(3.0, float(oct_st)))
            octave_reach_prob = float(octave_reach_prob) * float(oct_st) if oct_on else 0.0
            octave_reach_prob = max(0.0, min(0.45, float(octave_reach_prob)))

        syncopation_prob = 0.04 + 0.18 * e01
        try:
            if profile.get("syncopation_prob") is not None:
                syncopation_prob = float(profile["syncopation_prob"])  # type: ignore[assignment]
        except Exception:
            pass
        try:
            if arp_plan and arp_plan.get("syncopation_prob") is not None:
                syncopation_prob = float(arp_plan.get("syncopation_prob"))
        except Exception:
            pass
        syncopation_prob = max(0.0, min(0.45, float(syncopation_prob)))
        if int(channel) == 3 and not (arp_plan and arp_plan.get("syncopation_prob") is not None):
            syncopation_prob = 0.0

        events: List[Tuple] = []
        prev_note: Optional[int] = None
        total_beats = float(bars) * float(beats_per_bar)

        lead_intervals: List[Tuple[float, float, int]] = []
        if lead_events:
            for ev in lead_events:
                if not ev or len(ev) != 6:
                    continue
                try:
                    st = float(ev[3])
                    en = st + float(ev[4])
                    notes = ev[5]
                    p = int(notes[0]) if notes and isinstance(notes, list) else int(ev[1])
                except Exception:
                    continue
                if en > st + 1e-6:
                    lead_intervals.append((st, en, p))

        def lead_pcs_active_at(t: float) -> Tuple[Optional[int], set[int]]:
            """
            Return (lead_pitch, lead_pitch_classes_active).
            lead_pitch is a best-effort representative pitch; pcs is the union of active PCs.
            """
            pitch = None
            pcs: set[int] = set()
            for s, e, p in lead_intervals:
                if t + 1e-9 >= s and t <= e - 1e-9:
                    pcs.add(int(p) % 12)
                    if pitch is None:
                        pitch = int(p)
            return pitch, pcs

        def choose_non_clashing_tone(tones: List[int], lead_pcs: set[int], target: int) -> int:
            """
            Keep arp present without jumping to extreme registers:
            - prefer tones near `target` register
            - avoid sitting on the lead pitch class(es) when possible
            """
            if not tones:
                return int(target)
            # prefer candidates close to target register
            ordered = sorted(tones, key=lambda n: abs(int(n) - int(target)))
            # choose the closest tone whose pitch class differs from the active lead PCs
            for n in ordered:
                if (int(n) % 12) not in set(int(x) % 12 for x in (lead_pcs or set())):
                    return int(n)
            return int(ordered[0])

        def choose_alternative_tone(tones: List[int], avoid_note: int, target: int) -> int:
            """
            Choose a chord tone different from `avoid_note`, preferring proximity to `target`.
            Used to prevent same-note repeats in steady arp beds.
            """
            if not tones:
                return int(target)
            avoid = int(avoid_note)
            ordered = sorted(tones, key=lambda n: abs(int(n) - int(target)))
            for n in ordered:
                if int(n) != avoid:
                    return int(n)
            # Collapsed lane: every listed tone equals `avoid`. Try octave shifts in-range.
            base = int(ordered[0])
            for delta in (12, -12, 24, -24, 36, -36):
                try:
                    c = int(RANGE_LIMITER.clamp_note(int(base) + int(delta), int(channel)))
                except Exception:
                    c = int(base) + int(delta)
                if int(c) != int(avoid):
                    return int(c)
            return int(ordered[0])

        def ensure_multi_tone_pool(tones: List[int], *, channel_i: int) -> List[int]:
            """
            Guarantee we have at least 2 distinct candidate pitches.
            Range clamping and narrow lanes can collapse a chord into 1 pitch; when that
            happens the arp can only repeat. We add octave-shifted alternatives in-range.
            """
            uniq = sorted({int(n) for n in (tones or [])})
            if len(uniq) >= 2:
                return uniq
            if not uniq:
                return []
            base = int(uniq[0])
            cand = {
                int(base),
                int(RANGE_LIMITER.clamp_note(base + 12, int(channel_i))),
                int(RANGE_LIMITER.clamp_note(base - 12, int(channel_i))),
                int(RANGE_LIMITER.clamp_note(base + 24, int(channel_i))),
                int(RANGE_LIMITER.clamp_note(base - 24, int(channel_i))),
            }
            out = sorted({int(n) for n in cand})
            return out

        for bar in range(int(bars)):
            if bar >= len(chords) or bar >= len(roots):
                break

            # Phrase role (continuation/cadence/etc). Used for harmonic-rhythm following
            # decisions and Markov action conditioning.
            role = "continuation"
            try:
                phrase_len = phrase_length_bars_clamped(1, 16)
                role = str(
                    self.owner.chord_utils.phrase_role(
                        int(bar),
                        int(bars),
                        phrase_length=int(phrase_len),
                    )
                    or "continuation"
                )
            except Exception:
                role = "continuation"

            # Harmonic-rhythm aware arp: optionally follow intra-bar harmony timing
            # (half / anticipate / triple) so the arp moves with chord comping.
            follow_hr = resolve_config("composition", "arp_follow_harmonic_rhythm_enabled", True, bool)
            follow_strength = resolve_config("composition", "arp_follow_harmonic_rhythm_strength", 0.85, float)
            ant_beats = resolve_config("composition", "arp_anticipation_beats", 0.5, float)
            follow_strength = max(0.0, min(1.0, float(follow_strength)))
            ant_beats = max(0.25, min(1.5, float(ant_beats)))

            if arp_plan and arp_plan.get("lane_center_by_bar") is not None:
                try:
                    lane_center = int(list(arp_plan["lane_center_by_bar"])[bar])
                except Exception:
                    lane_center = int(chosen_lane[bar]) if chosen_lane and bar < len(chosen_lane) else 72
            else:
                lane_center = int(chosen_lane[bar]) if chosen_lane and bar < len(chosen_lane) else 72
            # Arp channel: keep a tighter, steadier register so it doesn't run away above the lead.
            lane_half_width = 12
            if int(channel) == 3:
                try:
                    info = RANGE_LIMITER.get_range_info(3) or {}
                    pref_min = int(info.get("preferred_min", 60))
                    pref_max = int(info.get("preferred_max", 81))
                    lane_center = int(max(pref_min, min(pref_max, int(lane_center))))
                except Exception:
                    lane_center = int(lane_center)
                lane_half_width = 7
            if arp_plan and arp_plan.get("lane_half_width") is not None:
                try:
                    lane_half_width = int(arp_plan["lane_half_width"])
                except Exception:
                    pass

            # Shared tension trajectory can push arp expressiveness on peak bars.
            t_enabled, t_strength = tension_trajectory_params()
            tbar = 1.0
            if t_enabled and t_strength > 1e-6 and arp_plan and arp_plan.get("tension_by_bar") is not None:
                try:
                    tb = float(list(arp_plan.get("tension_by_bar") or [])[bar])
                    tb = max(0.0, min(1.25, tb))
                    # Map to a gentle multiplier.
                    tbar = 0.85 + 0.55 * (tb / 1.25)
                    # Apply strength as exponent for smoother blending.
                    tbar = float(tbar) ** float(t_strength)
                except Exception:
                    tbar = 1.0

            accent_bar = float(accent_strength) * float(tbar)
            accent_bar = max(0.0, min(0.45, float(accent_bar)))
            sync_bar = max(0.0, min(0.55, float(syncopation_prob) * float(tbar)))
            oct_bar = max(0.0, min(0.60, float(octave_reach_prob) * float(tbar)))
            lane_half_width = max(1, min(24, int(lane_half_width)))

            tones = self._chord_tones_in_lane(
                chords[bar],
                int(roots[bar]),
                lane_center=lane_center,
                channel=channel,
                lane_half_width=lane_half_width,
                voiced_chord=(voiced_chords[bar] if voiced_chords and bar < len(voiced_chords) else None),
                tones_source=str((arp_plan or {}).get("tones_source", "pcs_lane") or "pcs_lane"),
            )
            if len(tones) == 1:
                base = int(tones[0])
                tones = sorted(
                    {
                        base,
                        RANGE_LIMITER.clamp_note(base + 12, int(channel)),
                        RANGE_LIMITER.clamp_note(base - 12, int(channel)),
                    }
                )

            def _tones_for_idx(idx: int) -> List[int]:
                if idx < 0 or idx >= len(chords) or idx >= len(roots):
                    return []
                ts = self._chord_tones_in_lane(
                    chords[idx],
                    int(roots[idx]),
                    lane_center=lane_center,
                    channel=channel,
                    lane_half_width=lane_half_width,
                    voiced_chord=(voiced_chords[idx] if voiced_chords and idx < len(voiced_chords) else None),
                    tones_source=str((arp_plan or {}).get("tones_source", "pcs_lane") or "pcs_lane"),
                )
                if len(ts) == 1:
                    base = int(ts[0])
                    ts = sorted(
                        {
                            base,
                            RANGE_LIMITER.clamp_note(base + 12, int(channel)),
                            RANGE_LIMITER.clamp_note(base - 12, int(channel)),
                        }
                    )
                return list(ts)

            if arp_plan and arp_plan.get("mode_by_bar") is not None:
                try:
                    mode = normalize_arp_mode(str(list(arp_plan["mode_by_bar"])[bar]))
                except Exception:
                    mode = None
            else:
                mode = None
            mode = mode or self._resolve_mode(
                requested_mode=arp_mode,
                phrase_contours=phrase_contours,
                bar=bar,
                bars=bars,
                section_role=section_role,
                emotion_name=emotion_name,
            )

            # Default: keep arp mode stable (classic consistent bed).
            # Only vary modes when explicitly enabled by config.
            allow_mode_var = False
            allow_mode_var = resolve_config("composition", "arp_allow_mode_variation_enabled", False, bool)
            if allow_mode_var and (not arp_plan or arp_plan.get("mode_by_bar") is None) and not arp_mode:
                try:
                    drng = getattr(self.owner, "deterministic_rng", None)
                    r = drng("arp_mode", int(bar), str(mode), str(section_role or ""), str(emotion_name)) if callable(drng) else random.Random(hash((bar, mode, section_role, emotion_name)) & 0xFFFFFFFF)
                except Exception:
                    r = random
                if float(e01) > 1e-6 and getattr(r, "random", random.random)() < (0.18 + 0.22 * float(e01)):
                    vocab = ["up", "down", "updown", "converge", "diverge"]
                    try:
                        pick = vocab[int(getattr(r, "randrange", random.randrange)(0, len(vocab)))]
                    except Exception:
                        pick = vocab[0]
                    mode = normalize_arp_mode(str(pick))
            # Optional motif-driven tone ordering: when a SongHookMotif is present
            # and coupling is enabled, let the motif contour steer how we walk the lane.
            motif_cycle: Optional[List[int]] = None
            coupling_enabled = resolve_config("composition", "arp_motif_coupling_enabled", True, bool)
            coupling_strength = resolve_config("composition", "arp_motif_coupling_strength", 0.6, float)
            def _sequence_for(tones_i: List[int], *, bar_index: int) -> List[int]:
                cyc: List[int]
                mc: Optional[List[int]] = None
                if coupling_enabled and motif_hook is not None:
                    try:
                        drng = getattr(self.owner, "deterministic_rng", None)
                    except Exception:
                        drng = None
                    mc = self._build_motif_cycle(
                        tones_i,
                        lane_center=lane_center,
                        motif_hook=motif_hook,
                        section_role=section_role,
                        emotion_name=emotion_name,
                        bar_index=int(bar_index),
                        strength=coupling_strength,
                        drng=drng,
                    )
                cyc = list(mc or self._build_mode_cycle(tones_i, mode))
                if rotate:
                    cyc = self._rotate_cycle_to_note(cyc, prev_note)
                return list(self._expand_cycle(cyc, steps_per_bar))

            if coupling_enabled and motif_hook is not None:
                try:
                    drng = getattr(self.owner, "deterministic_rng", None)
                except Exception:
                    drng = None
                motif_cycle = self._build_motif_cycle(
                    tones,
                    lane_center=lane_center,
                    motif_hook=motif_hook,
                    section_role=section_role,
                    emotion_name=emotion_name,
                    bar_index=bar,
                    strength=coupling_strength,
                    drng=drng,
                )

            cycle = motif_cycle or self._build_mode_cycle(tones, mode)
            rotate = True
            if arp_plan and arp_plan.get("rotate_to_prev") is not None:
                try:
                    rotate = bool(arp_plan["rotate_to_prev"])
                except Exception:
                    rotate = True
            if rotate:
                cycle = self._rotate_cycle_to_note(cycle, prev_note)
            sequence = self._expand_cycle(cycle, steps_per_bar)

            # Decide which chord-index each arp step should follow within this bar.
            chord_idx_by_step = [int(bar) for _ in range(int(steps_per_bar))]
            if (
                follow_hr
                and follow_strength > 1e-6
                and (bar + 1) < len(chords)
                and (bar + 1) < len(roots)
                and role not in {"cadence"}
            ):
                action = None
                try:
                    if arp_plan and arp_plan.get("harmonic_rhythm_action_by_bar") is not None:
                        a = list(arp_plan.get("harmonic_rhythm_action_by_bar") or [])
                        action = str(a[bar]) if bar < len(a) else None
                except Exception:
                    action = None
                if action is None and hasattr(self.owner, "harmonic_rhythm_model"):
                    try:
                        drng = getattr(self.owner, "deterministic_rng", None)
                        rhr = drng("arp_hr", int(bar), str(section_role or ""), str(emotion_name)) if callable(drng) else random
                    except Exception:
                        rhr = random
                    try:
                        hist = getattr(self, "_hr_hist", [])
                        hist = list(hist) if isinstance(hist, list) else []
                    except Exception:
                        hist = []
                    try:
                        msb = list((arp_plan or {}).get("motif_strength_by_bar") or [])
                        ms = float(msb[bar]) if bar < len(msb) else 0.0
                    except Exception:
                        ms = 0.0
                    try:
                        tenb = list((arp_plan or {}).get("tension_by_bar") or [])
                        ten = float(tenb[bar]) if bar < len(tenb) else 0.85
                    except Exception:
                        ten = 0.85
                    try:
                        crb = list((arp_plan or {}).get("chord_rhythm_by_bar") or [])
                        bt = float(crb[bar]) if bar < len(crb) else 1.0
                    except Exception:
                        bt = 1.0
                    try:
                        csb = list((arp_plan or {}).get("cadence_strength_by_bar") or [])
                        cs = float(csb[bar]) if bar < len(csb) else 0.0
                    except Exception:
                        cs = 0.0
                    try:
                        hfb = list((arp_plan or {}).get("harmony_function_target_by_bar") or [])
                        hf = str(hfb[bar]).strip().upper() if bar < len(hfb) else ""
                    except Exception:
                        hf = ""
                    if not hf:
                        if str(role or "") == "cadence":
                            hf = "D"
                        elif int(bar) == 0:
                            hf = "T"
                        else:
                            hf = "PD"
                    a2 = self.owner.harmonic_rhythm_model.next_action(
                        role=str(role),
                        history=list(hist)[-2:],
                        temperature=1.0,
                        bar_target=float(bt),
                        motif_strength=float(ms),
                        tension=float(ten),
                        cadence_strength=float(cs),
                        harmony_function_target=str(hf),
                        emotion_name=str(emotion_name or ""),
                        section_role=str(section_role or ""),
                        allow_sus=False,
                        cadence_style="authentic",
                    )
                    if getattr(rhr, "random", random.random)() < float(follow_strength):
                        action = str(a2)
                    hist = (list(hist) + [str(a2)])[-6:]
                    setattr(self, "_hr_hist", hist)
                act = str(action or "").strip().lower()
                if act == "half":
                    for step_i in range(int(steps_per_bar)):
                        if int(step_i) >= int(steps_per_bar) // 2:
                            chord_idx_by_step[int(step_i)] = int(bar + 1)
                elif act == "anticipate":
                    n_early = max(1, int(round(float(ant_beats) / float(grid))))
                    for step_i in range(int(steps_per_bar)):
                        if int(step_i) >= int(steps_per_bar) - int(n_early):
                            chord_idx_by_step[int(step_i)] = int(bar + 1)
                elif act == "triple" and (bar + 2) < len(chords) and (bar + 2) < len(roots):
                    for step_i in range(int(steps_per_bar)):
                        if int(step_i) >= (2 * int(steps_per_bar)) // 3:
                            chord_idx_by_step[int(step_i)] = int(bar + 2)
                        elif int(step_i) >= int(steps_per_bar) // 3:
                            chord_idx_by_step[int(step_i)] = int(bar + 1)

            # Cache tones + per-step sequences per chord index used in this bar.
            tones_cache: Dict[int, List[int]] = {}
            seq_cache: Dict[int, List[int]] = {}
            for idx in sorted(set(int(x) for x in chord_idx_by_step)):
                ts = _tones_for_idx(int(idx))
                if not ts:
                    continue
                tones_cache[int(idx)] = list(ts)
                seq_cache[int(idx)] = _sequence_for(list(ts), bar_index=int(idx))

            allow_color = bool(getattr(emotion, "scale_intervals", None))
            # If the user wants a strict chord-tone arpeggiator, disable non-chord "color" tones.
            if not resolve_config("composition", "arp_non_chord_tones_enabled", False, bool):
                allow_color = False
            scale_intervals = list(getattr(emotion, "scale_intervals", []) or [])
            scale_pcs = {int(iv) % 12 for iv in scale_intervals} if scale_intervals else set()

            bar_start = float(bar) * float(beats_per_bar)
            # Per-bar groove-link (optional): derive a bar-specific active-step set
            # from the melody phrase rhythm template onsets.
            active_steps_bar: set[int] = set(active_steps or set())
            try:
                # Stage-2 rhythm cells: if a per-bar onset step pattern is provided,
                # prefer it as the active-step set for this bar.
                if arp_plan and arp_plan.get("onset_steps_by_bar") is not None:
                    try:
                        by_bar = list(arp_plan.get("onset_steps_by_bar") or [])
                        if bar < len(by_bar) and isinstance(by_bar[bar], list):
                            steps = [int(s) for s in (by_bar[bar] or []) if isinstance(s, int)]
                            if steps:
                                active_steps_bar = set(int(s) for s in steps if 0 <= int(s) < int(steps_per_bar))
                                active_steps_bar.add(0)
                    except Exception:
                        pass

                groove_strength = 0.0
                groove_mode = "complement"
                groove_steps: Optional[set[int]] = None
                if arp_plan and arp_plan.get("melody_onsets_by_bar") is not None:
                    groove_strength = resolve_config("composition", "arp_melody_groove_link_strength", 0.0, float)
                    groove_mode = resolve_config("composition", "arp_groove_link_mode", 'complement')
                    groove_strength = max(0.0, min(1.0, float(groove_strength)))
                    if groove_strength > 1e-6:
                        try:
                            by_bar = list(arp_plan.get("melody_onsets_by_bar") or [])
                            if bar < len(by_bar) and isinstance(by_bar[bar], list):
                                groove_steps = {int(s) for s in (by_bar[bar] or [])}
                        except Exception:
                            groove_steps = None

                use_groove = False
                if groove_steps and groove_strength > 1e-6:
                    try:
                        drng = getattr(self.owner, "deterministic_rng", None)
                        r = (
                            drng("arp_groove_link", int(bar), str(section_role or ""), str(emotion_name))
                            if callable(drng)
                            else random.Random(
                                hash(("arp_groove_link", bar, section_role, emotion_name)) & 0xFFFFFFFF
                            )
                        )
                        use_groove = getattr(r, "random", random.random)() < groove_strength
                    except Exception:
                        use_groove = False

                if use_groove and groove_steps is not None:
                    mode = str(groove_mode or "complement").strip().lower()
                    if mode not in {"mirror", "complement"}:
                        mode = "complement"
                    if mode == "mirror":
                        pool = [s for s in sorted(groove_steps) if 0 <= int(s) < int(steps_per_bar)]
                    else:
                        pool = [s for s in range(int(steps_per_bar)) if int(s) not in groove_steps]
                    if not pool:
                        pool = list(range(int(steps_per_bar)))

                    # Rebuild the bar-active steps from the pool (same note budget).
                    active_steps_bar = set()
                    if desired_notes_per_bar >= int(steps_per_bar):
                        active_steps_bar = set(range(int(steps_per_bar)))
                    else:
                        step_interval = float(len(pool)) / float(max(1, int(desired_notes_per_bar)))
                        for i in range(int(desired_notes_per_bar)):
                            j = int(round(float(i) * step_interval))
                            j = max(0, min(len(pool) - 1, int(j)))
                            active_steps_bar.add(int(pool[j]))
                        active_steps_bar.add(0)
                        while len(active_steps_bar) < int(desired_notes_per_bar):
                            # Prefer remaining groove steps in mirror mode.
                            if mode == "mirror":
                                rem = [s for s in pool if int(s) not in active_steps_bar]
                                if rem:
                                    active_steps_bar.add(int(rem[0]))
                                    continue
                            best = None
                            best_d = -1
                            for s in range(int(steps_per_bar)):
                                if s in active_steps_bar:
                                    continue
                                d = min(abs(int(s) - int(t)) for t in active_steps_bar) if active_steps_bar else 999
                                if d > best_d:
                                    best_d = d
                                    best = s
                            if best is None:
                                break
                            active_steps_bar.add(int(best))
            except Exception:
                active_steps_bar = set(active_steps or set())
            # Lead occupancy map on the arp grid (precompute per bar).
            lead_pcs_by_step: List[set[int]] = []
            if lead_intervals:
                for step_i in range(int(steps_per_bar)):
                    t = bar_start + float(step_i) * float(grid)
                    _lp, pcs = lead_pcs_active_at(float(t))
                    lead_pcs_by_step.append(set(int(x) % 12 for x in (pcs or set())))
            else:
                lead_pcs_by_step = [set() for _ in range(int(steps_per_bar))]

            # If hard 16th quantization is enabled, avoid timing offsets/swing inside the arp.
            quantize_hard = False
            next_bar_hint_p = 0.0
            quantize_hard = resolve_config("composition", "quantize_16th_enabled", False, bool)
            next_bar_hint_p = resolve_config("composition", "arp_next_bar_last_step_hint_prob", 0.0, float)
            next_bar_hint_p = max(0.0, min(1.0, float(next_bar_hint_p)))

            for step in range(steps_per_bar):
                if active_steps_bar and int(step) not in active_steps_bar:
                    continue
                start = bar_start + float(step) * float(grid)
                if start >= total_beats - 1e-9:
                    break

                idx = int(chord_idx_by_step[int(step)]) if 0 <= int(step) < len(chord_idx_by_step) else int(bar)
                tones_step = tones_cache.get(int(idx)) or tones
                tones_step = ensure_multi_tone_pool(list(tones_step), channel_i=int(channel))
                seq_step = seq_cache.get(int(idx)) or sequence
                note = int(seq_step[step % len(seq_step)]) if seq_step else int(tones_step[0] if tones_step else lane_center)
                # Hard guard: never repeat the exact same pitch twice in a row.
                # This keeps the arp reading like an Ableton-style arpeggiator walking chord tones.
                if prev_note is not None and int(note) == int(prev_note) and tones_step:
                    note = choose_alternative_tone(list(tones_step), avoid_note=int(prev_note), target=int(note))
                # Avoid getting stuck repeating the exact same pitch for long stretches
                # (can happen when tone pools collapse due to lane guardrails or lead-avoidance).
                try:
                    if prev_note is not None and int(note) == int(prev_note):
                        rep = int(getattr(self, "_debug_repeat_note_count", 0) or 0) + 1
                    else:
                        rep = 0
                    setattr(self, "_debug_repeat_note_count", int(rep))
                except Exception:
                    rep = 0
                if rep >= 2 and tones_step:
                    # Pick the closest alternative in the lane that isn't the exact same pitch.
                    try:
                        alts = [int(n) for n in tones_step if int(n) != int(note)]
                        if alts:
                            note = int(self._nearest_in_register(alts, int(note)))
                    except Exception:
                        pass
                is_weak = (step % max(1, int(round(1.0 / grid)))) != 0
                rng = getattr(self.owner, "rng", random)

                # Dynamic accents: emphasize bar downbeat (and beat 3 lightly), tuck offbeats.
                # This helps the arp read as a driven "bed" like the reference renders.
                v = float(base_velocity_final)
                if accent_bar > 1e-6:
                    bar_pos = float(start - bar_start)
                    near_int = abs(bar_pos - round(bar_pos)) <= 1e-6
                    if near_int:
                        beat_i = int(round(bar_pos))
                        if beat_i == 0:
                            v *= (1.0 + accent_bar)
                        elif beat_i == 2:
                            v *= (1.0 + 0.55 * accent_bar)
                        else:
                            v *= (1.0 + 0.25 * accent_bar)
                    else:
                        v *= (1.0 - 0.40 * accent_bar)
                # Motif accent: strengthen hits that land on motif rhythm onsets.
                if motif_steps and int(step) in motif_steps:
                    v *= (1.0 + 0.65 * accent_bar)
                step_velocity = int(max(1, min(127, round(v))))
                dur = float(grid)

                # Syncopation: a little "push/pull" so 16ths feel like a performed arp bed.
                # - on weak steps: occasionally play slightly late + shorten duration
                # - on strong beats: very occasionally drop a hit (creates breathing room)
                if (not quantize_hard) and sync_bar > 1e-6 and grid <= 0.5:
                    bar_pos = float(start - bar_start)
                    near_int = abs(bar_pos - round(bar_pos)) <= 1e-6
                    if near_int and rng.random() < (0.22 * sync_bar):
                        # sparse skip on strong beats
                        continue
                    if (not near_int) and rng.random() < sync_bar:
                        start = start + (grid * 0.12)
                        dur = max(grid * 0.65, grid - (grid * 0.18))

                # Monophonic + portamento: ensure slight overlaps so MonophonicRenderer
                # treats successive notes as legato and applies glide.
                if int(channel) == 3:
                    # Keep overlap subtle (avoid smearing): 8ths/16ths get a tiny tail.
                    # Also cap to <1 beat so we don't cross barlines heavily.
                    dur = min(float(beats_per_bar) * 0.99, max(dur, float(grid) * 1.06))

                lead_pcs = lead_pcs_by_step[step] if step < len(lead_pcs_by_step) else set()
                lead_pitch, _pcs = lead_pcs_active_at(float(start))
                duck = max(0.0, min(1.0, float(lead_ducking)))
                if (lead_pitch is not None or lead_pcs) and duck > 1e-6:
                    # Instead of dropping notes (audible "ducking"), keep rhythm constant and
                    # apply a light level reduction. Optionally avoid clashing pitch classes.
                    note_before = int(note)
                    avoid_pcs = False
                    avoid_pcs = resolve_config("composition", "arp_avoid_lead_pitch_classes_enabled", False, bool)
                    if avoid_pcs:
                        note = choose_non_clashing_tone(list(tones_step), set(lead_pcs or set()), int(note))
                    clashed = (int(note_before) % 12) in set(lead_pcs or set())
                    # Only skip hits when we'd otherwise clash and we're on weak steps.
                    if clashed and is_weak and rng.random() < (duck * 0.22):
                        continue
                    step_velocity = int(max(1, round(float(step_velocity) * (1.0 - 0.28 * duck))))

                if allow_color and is_weak and rng.random() < 0.14 and scale_pcs:
                    for delta in rng.sample([-2, -1, 1, 2], k=4):
                        cand = int(note) + int(delta)
                        if (cand % 12) in scale_pcs and (cand % 12) not in {t % 12 for t in tones}:
                            note = RANGE_LIMITER.clamp_note(cand, int(channel))
                            break

                if (
                    next_bar_hint_p > 1e-9
                    and step == steps_per_bar - 1
                    and bar + 1 < len(chords)
                    and rng.random() < next_bar_hint_p
                ):
                    next_lane = int(chosen_lane[bar + 1]) if chosen_lane and (bar + 1) < len(chosen_lane) else lane_center
                    next_voiced = (
                        voiced_chords[bar + 1]
                        if voiced_chords and (bar + 1) < len(voiced_chords)
                        else None
                    )
                    next_tones = self._chord_tones_in_lane(
                        chords[bar + 1],
                        int(roots[bar + 1]),
                        lane_center=next_lane,
                        channel=channel,
                        voiced_chord=next_voiced,
                        tones_source=str((arp_plan or {}).get("tones_source", "pcs_lane") or "pcs_lane"),
                    )
                    note = self._nearest_in_register(next_tones, int(note))

                # Sometimes: turn the arp into a bar-length sustained tonic/fifth note (+octave),
                # anchored from the last scanned chord tone register.
                if int(channel) == 3 and int(step) == 0:
                    tf_on = resolve_config("composition", "arp_tonic_fifth_drone_note_enabled", False, bool)
                    tf_p = resolve_config("composition", "arp_tonic_fifth_drone_note_prob", 0.0, float)
                    tf_oct = resolve_config("composition", "arp_tonic_fifth_drone_note_octave_semitones", 12, int)
                    tf_p = max(0.0, min(1.0, float(tf_p)))
                    if tf_on and tf_p > 1e-9 and rng.random() < tf_p:
                        try:
                            root_m = int(roots[bar]) if bar < len(roots) else int(roots[-1])
                        except Exception:
                            root_m = int(roots[0]) if roots else 60
                        tonic_pc = int(root_m) % 12
                        fifth_pc = (int(root_m) + 7) % 12
                        base = int(note) + int(tf_oct)
                        # Pick nearest note to base whose PC is tonic or fifth.
                        cands = []
                        for k in range(-2, 3):
                            for pc in (tonic_pc, fifth_pc):
                                # Align candidate to requested pitch class near base.
                                cand0 = int(base) + int((pc - (base % 12)) % 12)
                                cand1 = cand0 - 12
                                cands.extend([cand0 + 12 * k, cand1 + 12 * k])
                        pick = int(min(cands, key=lambda n: abs(int(n) - int(base)))) if cands else int(base)
                        note = int(RANGE_LIMITER.clamp_note(int(pick), int(channel)))
                        # Last the full chord (bar) length from this onset.
                        dur = float(max(float(dur), float(beats_per_bar) - float(start - bar_start)))

                # Occasional octave reach (especially helpful on 16ths): makes the arp feel
                # more "produced" like the references without changing harmony.
                if steps_per_bar >= 8 and rng.random() < oct_bar:
                    up = RANGE_LIMITER.clamp_note(int(note) + 12, int(channel))
                    down = RANGE_LIMITER.clamp_note(int(note) - 12, int(channel))
                    # Prefer up-octave on weak steps, down-octave on strong steps (keeps grounding).
                    cand = up if is_weak else down
                    # Only take it if it doesn't collapse to same note (range clamp).
                    if int(cand) != int(note):
                        note = int(cand)

                if self.owner.global_scale is not None:
                    # Important: the arp is already derived from chord tones.
                    # Quantizing it again to a (sometimes overly strict) global scale can
                    # collapse different chord tones into the same pitch, making the arp
                    # repeat one note. For the arp channel, prefer preserving chord tones.
                    if int(channel) != 3:
                        note = int(self.owner._quantize_to_scale(int(note), emotion))
                    note = RANGE_LIMITER.clamp_note(int(note), int(channel))
                    # Re-apply no-repeat guard *after* clamp/quantize (quantization can collapse tones).
                    if prev_note is not None and int(note) == int(prev_note) and tones_step:
                        alt = choose_alternative_tone(list(tones_step), avoid_note=int(prev_note), target=int(note))
                        if int(channel) != 3:
                            alt = int(self.owner._quantize_to_scale(int(alt), emotion))
                        alt = RANGE_LIMITER.clamp_note(int(alt), int(channel))
                        if int(alt) != int(note):
                            note = int(alt)

                swing_amt = max(0.0, min(0.18, float(swing)))
                if (not quantize_hard) and swing_amt > 1e-6 and grid <= 0.5 and (step % 2 == 1):
                    start = start + (grid * swing_amt)
                if int(channel) in (2, 3):
                    note = int(
                        _force_arp_midi_differs_from_prev(
                            prev_note,
                            int(note),
                            tones_step_in=list(tones_step),
                            lane_fallback=int(lane_center),
                            channel_i=int(channel),
                        )
                    )
                events.append((int(channel), int(note), int(step_velocity), float(start), float(dur), [int(note)]))
                prev_note = int(note)

        if int(channel) in (2, 3) and events:
            return repair_arp_consecutive_same_midi(
                events,
                channel=int(channel),
                chord_notes_by_bar=None,
                beats_per_bar=float(beats_per_bar),
            )
        return events