from __future__ import annotations
from audiogen_core.config import resolve_config

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from audiogen_core.composition_runtime_flags import stable_emotion_velocity_multiplier
from composition.motif_transform import transform_motif_for_slot
from data.melody_motif_profiles import melody_motif_profile_for_emotion
from midi.midi_range_limiter import RANGE_LIMITER


def _harmony_lists_for_motif(plan) -> Tuple[List[str], List[int], int, float]:
    """Prefer ``plan.harmonic_plan`` for chord/root context when the snapshot exists."""
    hp = getattr(plan, "harmonic_plan", None)
    if hp is not None:
        try:
            hp.validate()
            return list(hp.chords), list(hp.roots), int(hp.bars), float(hp.beats_per_bar)
        except Exception:
            pass
    return list(plan.chords or []), list(plan.roots or []), int(plan.bars), float(plan.beats_per_bar)


@dataclass(frozen=True)
class MotifSlot:
    start_beats: float
    length_beats: float
    strength: float = 1.0  # 1.0 = strict copy, <1.0 allows more variation


@dataclass
class SongHookMotif:
    """A motif represented as scale-degree intervals + rhythm durations."""

    intervals: List[int]
    rhythms: List[float]
    # Optional high-level contour label copied from the Markov Motif
    # (e.g. "asc", "desc", "arch", "static"). This lets other parts of
    # the system (like the arpeggiator) react to the same contour.
    contour: str = ""

    def total_beats(self) -> float:
        return float(sum(float(r) for r in self.rhythms))


class MotifPlanManager:
    """
    Phrase-level motif scheduler + renderer.

    Seeds a short song hook motif once, then injects it into later sections at fixed slots.
    This makes melodies feel consistent even when local Markov sampling varies.
    """

    def __init__(self, owner):
        self.owner = owner
        self._theme: Optional[SongHookMotif] = None
        self._contrast: Optional[SongHookMotif] = None
        # Realtime continuity: track how often each role has appeared so we can
        # evolve the hook across loop iterations (statement -> variation -> fragment).
        self._role_occurrences: dict[str, int] = {}
        self._sections_seen: int = 0
        self._last_theme_statement_seen: Optional[int] = None
        self._family_counts: dict[str, int] = {}

    def reset(self) -> None:
        self._theme = None
        self._contrast = None
        self._role_occurrences = {}
        self._sections_seen = 0
        self._last_theme_statement_seen = None
        self._family_counts = {}

    def theme_statement_age_sections(self) -> Optional[int]:
        """
        Return how many generated sections since the last clear theme statement.
        None if we haven't stated the theme yet.
        """
        try:
            last = getattr(self, "_last_theme_statement_seen", None)
            if last is None:
                return None
            return int(max(0, int(self._sections_seen) - int(last)))
        except Exception:
            return None

    def seed_from_library_if_needed(self) -> None:
        """Pick one motif from the Markov MotifLibrary after it's been seeded."""
        if self._theme is not None:
            return
        mg = getattr(self.owner, "melody_gen", None)
        lib = getattr(getattr(mg, "motif", None), "motif_library", None)
        motifs = getattr(lib, "motifs", None) if lib is not None else None
        if not motifs:
            return

        # Choose a "theme" motif (hooky) and an optional "contrast" motif.
        # Theme: prefer variety and medium rhythmic density.
        emotion_name = (
            getattr(getattr(self.owner, "_last_generation_emotion", None), "name", "") or ""
        ).lower()
        profile = melody_motif_profile_for_emotion(emotion_name)
        preferred_contours = [str(v) for v in profile.get("preferred_contours", [])]
        density_target = float(profile.get("density_target", 0.55))
        avg_interval_target = float(profile.get("avg_interval_target", 1.5))
        scored = []
        for m in motifs:
            intervals = list(getattr(m, "intervals", []) or [])
            rhythms = list(getattr(m, "rhythms", []) or [])
            if not intervals or not rhythms:
                continue
            uniq = len(set(int(i) for i in intervals))
            dens = float(getattr(m, "rhythmic_density", 0.5) or 0.5)
            avg_int = float(getattr(m, "avg_interval", 1.0) or 1.0)
            contour = str(getattr(m, "contour", "") or "")
            score = 1.0 + 0.25 * uniq + (1.0 - abs(dens - density_target))
            score += max(0.0, 0.4 - 0.18 * abs(avg_int - avg_interval_target))
            if preferred_contours:
                score *= 1.22 if contour in preferred_contours else 0.86
            if emotion_name and getattr(m, "source_emotion", "") == emotion_name:
                score *= 1.34
            scored.append((score, intervals, rhythms, contour))
        if not scored:
            return
        scored.sort(key=lambda x: x[0], reverse=True)
        _, intervals, rhythms, contour = scored[0]
        self._theme = SongHookMotif(intervals=intervals, rhythms=rhythms, contour=str(contour or ""))
        # Contrast: pick the next-best motif that's actually different.
        for _, iv2, rh2, c2 in scored[1:]:
            if iv2 != intervals or rh2 != rhythms:
                self._contrast = SongHookMotif(
                    intervals=list(iv2),
                    rhythms=list(rh2),
                    contour=str(c2 or ""),
                )
                break

    def theme(self) -> Optional[SongHookMotif]:
        """Return the current shared theme motif (if seeded)."""
        return self._theme

    @staticmethod
    def _contour_from_intervals(intervals: Sequence[int]) -> str:
        vals = [int(v) for v in list(intervals or [])]
        if not vals:
            return "static"
        pos = sum(1 for v in vals if int(v) > 0)
        neg = sum(1 for v in vals if int(v) < 0)
        if pos and neg:
            return "arch"
        if pos:
            return "asc"
        if neg:
            return "desc"
        return "static"

    @staticmethod
    def _snap_hook_duration(value: float) -> float:
        allowed = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
        try:
            v = max(0.25, min(2.0, float(value)))
        except Exception:
            v = 0.5
        return float(min(allowed, key=lambda x: abs(float(x) - float(v))))

    def seed_from_section_plan_if_needed(self, plan, *, role: str = "") -> bool:
        """Fallback theme capture from realized lead melody events.

        This is used when the Markov motif library has no usable motif yet. It
        lets the first verse/chorus lead line become song memory immediately.
        """

        if self._theme is not None:
            return False
        if plan is None:
            return False
        try:
            role_lc = str(role or getattr(plan, "section_role", "") or "").strip().lower()
        except Exception:
            role_lc = ""
        if role_lc in {"intro", "outro"}:
            return False

        scale = list(getattr(getattr(plan, "emotion", None), "scale_intervals", []) or [])
        if not scale:
            return False
        scale_pcs = [int(iv) % 12 for iv in scale]
        try:
            bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
            roots = list(getattr(plan, "roots", []) or [])
            events = sorted(
                list(getattr(plan, "melody_events", []) or []),
                key=lambda ev: float(ev[3]) if isinstance(ev, tuple) and len(ev) == 6 else 0.0,
            )
        except Exception:
            return False
        if not events or not roots:
            return False

        degree_pairs: List[Tuple[int, float, float]] = []
        cap_beats = min(float(bpb) * 4.0, float(getattr(plan, "bars", 4) or 4) * float(bpb))
        for ev in events:
            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                continue
            try:
                st = float(ev[3])
                if st < -1e-6 or st >= cap_beats:
                    continue
                bar = int(st // float(bpb))
                if bar < 0 or bar >= len(roots):
                    continue
                midi = int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
                rel = (int(midi) - (int(roots[bar]) % 12)) % 12
                if rel not in scale_pcs:
                    continue
                degree_pairs.append((int(scale_pcs.index(rel)) % 7, float(ev[4]), float(st)))
            except Exception:
                continue

        try:
            mg = getattr(self.owner, "melody_gen", None)
            motif_len = int(getattr(getattr(getattr(mg, "motif", None), "motif_library", None), "motif_length", 3) or 3)
        except Exception:
            motif_len = 3
        motif_len = max(3, min(6, int(motif_len)))
        if len(degree_pairs) < motif_len + 1:
            return False

        best = None
        best_score = -1e9
        max_start = max(0, len(degree_pairs) - (motif_len + 1))
        for start_i in range(max_start + 1):
            window = degree_pairs[start_i : start_i + motif_len + 1]
            degs = [int(d) for d, _dur, _st in window]
            durs = [self._snap_hook_duration(float(dur)) for _d, dur, _st in window[:-1]]
            intervals = [int(degs[i + 1]) - int(degs[i]) for i in range(motif_len)]
            abs_motion = sum(abs(int(v)) for v in intervals)
            uniq = len(set(degs))
            if abs_motion <= 1 or uniq <= 1:
                continue
            long_count = sum(1 for d in durs if float(d) >= 2.0)
            tiny_count = sum(1 for d in durs if float(d) <= 0.25)
            score = 1.0 + 0.28 * float(uniq) + 0.16 * float(abs_motion)
            score -= 0.22 * float(long_count)
            score -= 0.08 * float(tiny_count)
            score -= 0.04 * float(start_i)
            if role_lc in {"b", "chorus", "hook", "tag"}:
                score += 0.18
            if score > best_score:
                best_score = float(score)
                best = (intervals, durs)

        if best is None:
            return False
        intervals, rhythms = best
        self._theme = SongHookMotif(
            intervals=[int(v) for v in intervals],
            rhythms=[float(v) for v in rhythms],
            contour=self._contour_from_intervals(intervals),
        )
        try:
            setattr(self.owner, "_song_motif_hook_seeded", True)
        except Exception:
            pass
        try:
            bus = {
                "intervals": list(self._theme.intervals),
                "rhythms": list(self._theme.rhythms),
                "contour": str(self._theme.contour),
                "source": "lead_section",
                "role": str(role_lc),
            }
            setattr(self.owner, "_cross_lane_motif_bus", dict(bus))
            sm = getattr(self.owner, "song_memory", None)
            if sm is not None:
                sm.cross_lane_motif_bus = dict(bus)
        except Exception:
            pass
        return True

    @staticmethod
    def _motif_summary(motif: Optional[SongHookMotif]) -> dict:
        if motif is None:
            return {}
        intervals = [int(v) for v in list(getattr(motif, "intervals", []) or [])]
        rhythms = [float(v) for v in list(getattr(motif, "rhythms", []) or [])]
        return {
            "intervals": intervals[:12],
            "rhythms": rhythms[:12],
            "contour": str(getattr(motif, "contour", "") or ""),
            "total_beats": float(sum(float(v) for v in rhythms)),
            "length": int(min(len(intervals), len(rhythms))),
        }

    def development_snapshot(
        self,
        *,
        role: str,
        section_index: int,
        section_variant: str = "",
        motif_id: str = "",
        slot_tags: Optional[Sequence[dict]] = None,
    ) -> dict:
        """Compact, JSON-safe motif lifecycle state for song reports and QA."""
        tags = [dict(t) for t in list(slot_tags or []) if isinstance(t, dict)]
        variants: dict[str, int] = {}
        families: dict[str, int] = {}
        for tag in tags:
            v = str(tag.get("motif_variant", "") or "")
            if v:
                variants[v] = int(variants.get(v, 0) or 0) + 1
            f = str(tag.get("motif_family", "") or "")
            if f:
                families[f] = int(families.get(f, 0) or 0) + 1
        return {
            "section_index": int(section_index),
            "role": str(role or ""),
            "section_variant": str(section_variant or ""),
            "motif_id": str(motif_id or ""),
            "theme": self._motif_summary(self._theme),
            "contrast": self._motif_summary(self._contrast),
            "slot_count": int(len(tags)),
            "slot_starts": [float(t.get("start_beats", 0.0) or 0.0) for t in tags],
            "slot_lengths": [float(t.get("length_beats", 0.0) or 0.0) for t in tags],
            "variants": dict(sorted(variants.items())),
            "families": dict(sorted(families.items())),
            "family_counts_total": dict(sorted((str(k), int(v)) for k, v in self._family_counts.items())),
            "theme_statement_age_sections": self.theme_statement_age_sections(),
        }

    def slots_for_section(self, *, form_mode: str, role: str, bars: int, beats_per_bar: float) -> List[MotifSlot]:
        if bars <= 0 or beats_per_bar <= 0:
            return []

        total_beats = float(bars) * float(beats_per_bar)
        # `pop_ext` has richer, multi-slot scheduling; other forms get a simpler, robust version:
        # - Chorus entry: quote the hook immediately (1–2 bars)
        # - Ending (tag/outro): quote near the end (1–2 bars)
        if str(form_mode) == "pop_ext":
            # Verse: small fragments; Chorus: full motif twice; Tag: full once.
            if role == "a":
                return [
                    MotifSlot(start_beats=0.0, length_beats=min(2.0, total_beats), strength=0.75),
                    MotifSlot(start_beats=min(8.0, max(0.0, total_beats - 2.0)), length_beats=min(2.0, total_beats), strength=0.70),
                ]
            if role == "b":
                return [
                    MotifSlot(start_beats=0.0, length_beats=min(4.0, total_beats), strength=0.98),
                    MotifSlot(start_beats=min(8.0, max(0.0, total_beats - 4.0)), length_beats=min(4.0, total_beats), strength=0.92),
                ]
            if role == "tag":
                return [MotifSlot(start_beats=0.0, length_beats=min(4.0, total_beats), strength=0.9)]
            if role == "a_prime":
                # Return section: restate clearly once (then allow Markov to vary).
                return [MotifSlot(start_beats=0.0, length_beats=min(4.0, total_beats), strength=0.92)]
            return []

        form = str(form_mode or "")
        role = str(role or "")
        chorus_like = role in {"b", "chorus", "hook"}
        ending_like = role in {"tag", "outro", "ending"}
        # 16-bar sections are common in realtime. Make motif scheduling *role-aware*
        # (especially for the `default` form) so we get verse hints + chorus restatement
        # without over-injecting the hook into every section.
        if int(bars) == 16 and form in {"default", "pop", "rondo", "ballad", "wave"}:
            bpb = float(beats_per_bar)
            bar0 = 0.0
            bar8 = 8.0 * bpb
            bar12 = 12.0 * bpb
            # Verse: light hint early + a small answer in the B-half.
            if role in {"a"}:
                return [
                    MotifSlot(start_beats=bar0, length_beats=min(4.0, total_beats), strength=0.72),
                    MotifSlot(start_beats=min(bar8, max(0.0, total_beats - 4.0)), length_beats=min(4.0, total_beats), strength=0.82),
                ]
            # Pre-chorus: set up the hook near the end (lead-in).
            if role in {"pre_chorus"}:
                return [
                    MotifSlot(start_beats=min(bar12, max(0.0, total_beats - 4.0)), length_beats=min(4.0, total_beats), strength=0.86),
                ]
            # Chorus: clear hook restatement at entry + a late quote before cadence.
            if role in {"b", "chorus", "hook"}:
                return [
                    MotifSlot(start_beats=bar0, length_beats=min(8.0, total_beats), strength=0.96),
                    MotifSlot(start_beats=min(bar12, max(0.0, total_beats - 4.0)), length_beats=min(4.0, total_beats), strength=0.92),
                ]
            # Tag/outro handled below; intro gets no forced motif.
            if role in {"intro"}:
                return []
        if int(bars) == 8 and form in {"default", "pop", "rondo", "ballad", "wave"}:
            bpb = float(beats_per_bar)
            bar0 = 0.0
            bar4 = 4.0 * bpb
            bar6 = 6.0 * bpb
            if role in {"a"}:
                return [
                    MotifSlot(start_beats=bar0, length_beats=min(2.0, total_beats), strength=0.74),
                    MotifSlot(start_beats=min(bar4, max(0.0, total_beats - 2.0)), length_beats=min(2.0, total_beats), strength=0.80),
                ]
            if role in {"pre_chorus"}:
                return [
                    MotifSlot(start_beats=min(bar6, max(0.0, total_beats - 4.0)), length_beats=min(4.0, total_beats), strength=0.88),
                ]
            if role in {"b", "chorus", "hook"}:
                return [
                    MotifSlot(start_beats=bar0, length_beats=min(4.0, total_beats), strength=0.95),
                    MotifSlot(start_beats=min(bar4, max(0.0, total_beats - 2.0)), length_beats=min(2.0, total_beats), strength=0.90),
                ]
            if role in {"a_prime"}:
                return [MotifSlot(start_beats=bar0, length_beats=min(4.0, total_beats), strength=0.92)]
            if role in {"intro"}:
                return []
        if chorus_like:
            return [MotifSlot(start_beats=0.0, length_beats=min(8.0, total_beats), strength=0.94)]
        if ending_like:
            start = max(0.0, total_beats - min(8.0, total_beats))
            return [MotifSlot(start_beats=float(start), length_beats=min(8.0, total_beats), strength=0.92)]
        return []

    @staticmethod
    def _degree_from_midi(midi: int, root_midi: int, scale_pcs: Sequence[int]) -> Optional[int]:
        rel = (int(midi) - int(root_midi)) % 12
        if rel not in scale_pcs:
            return None
        return int(scale_pcs.index(rel))

    def _chord_degrees(self, chord_symbol: str, root_midi: int, scale_pcs: Sequence[int]) -> List[int]:
        notes = [n for n in self.owner._chord_symbol_to_notes(chord_symbol, int(root_midi)) if isinstance(n, int)]
        out = []
        for n in notes:
            deg = self._degree_from_midi(int(n), int(root_midi), scale_pcs)
            if deg is not None:
                out.append(deg)
        # Fallback: simple triad degrees if parsing fails.
        out = sorted(set(out))
        return out or [0, 2, 4]

    @staticmethod
    def _is_strong_beat(start_beats: float) -> bool:
        beat_phase = float(start_beats) % 1.0
        return beat_phase < 1e-6 or abs(beat_phase - 0.5) < 1e-6

    def _render_hook_as_events(
        self,
        hook: SongHookMotif,
        *,
        emotion,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float,
        slot: MotifSlot,
        channel: int = 2,
        octave_shift: int = 0,
        start_degree_override: Optional[int] = None,
        answer_mode: bool = False,
        rhythm_override: Optional[Sequence[float]] = None,
    ) -> List[Tuple]:
        scale = list(getattr(emotion, "scale_intervals", []) or [])
        if not scale or bars <= 0:
            return []
        scale_pcs = [int(iv) % 12 for iv in scale]

        # Build a degree sequence from intervals.
        deg = int(start_degree_override) % 7 if start_degree_override is not None else 0
        degrees = []
        for step in hook.intervals:
            deg = (deg + int(step)) % 7
            degrees.append(int(deg))

        rhythms = list(rhythm_override) if rhythm_override is not None else list(hook.rhythms)
        if not degrees or not rhythms:
            return []

        # Role-based variation strength: lower strength -> more fragments/variation.
        length_cap = max(0.5, float(slot.length_beats))
        out: List[Tuple] = []
        t = float(slot.start_beats)
        prev_deg: Optional[int] = None

        # If the override is shorter than the motif degrees, loop it (rhythm cell reuse).
        if len(rhythms) < len(degrees):
            rr = list(rhythms)
            rhythms = [float(rr[i % len(rr)]) for i in range(len(degrees))]

        for d, dur in zip(degrees, rhythms):
            if t >= slot.start_beats + length_cap - 1e-6:
                break
            dur = float(dur)
            if dur <= 0:
                continue
            dur = min(dur, slot.start_beats + length_cap - t)
            bar = int(t // beats_per_bar)
            if bar < 0 or bar >= len(roots) or bar >= len(chords):
                break

            root = int(roots[bar])
            chord = chords[bar]
            chord_degs = self._chord_degrees(chord, root, scale_pcs)

            degree = int(d)
            # Strong beat anchoring: force chord tone.
            if self._is_strong_beat(t):
                degree = min(chord_degs, key=lambda cd: min(abs(cd - degree), 7 - abs(cd - degree)))
            else:
                # Weak beat: allow a neighbor/passing tone that resolves next.
                rng = getattr(self.owner, "rng", random)
                extra = 0.18 if bool(answer_mode) else 0.0
                if prev_deg is not None and rng.random() < (0.25 * (1.0 - float(slot.strength)) + 0.10 + extra):
                    for delta in rng.sample([-1, 1, -2, 2], k=4):
                        cand = (degree + int(delta)) % 7
                        if cand not in chord_degs:
                            degree = cand
                            break

            midi = root + int(scale[degree % len(scale)]) + int(octave_shift)
            midi = RANGE_LIMITER.clamp_note(int(midi), int(channel))
            vel_m = stable_emotion_velocity_multiplier(emotion)
            vel = int(86 * float(vel_m))
            vel = max(1, min(127, vel))
            out.append((int(channel), int(midi), int(vel), float(t), float(dur), [int(midi)]))
            prev_deg = degree
            t += dur

        return out

    def apply_to_section_plan(self, plan, *, role: str, section_index: int = 0) -> None:
        """Mutates plan.melody_events by injecting a theme/contrast motif at scheduled slots."""
        form_mode = getattr(getattr(self.owner, "arrangement_policy", None), "form_mode", "default") or "default"
        self.seed_from_library_if_needed()
        if self._theme is None:
            self.seed_from_section_plan_if_needed(plan, role=role)
        theme = self._theme
        if theme is None:
            return
        contrast = self._contrast

        # Realtime recap intent: when the scheduler marks a recap section, bias strongly
        # toward clear theme statements (even if we'd otherwise use contrast).
        recap_intent = False
        try:
            hctx = getattr(self.owner, "_emotion_transition_handoff_ctx", None) or {}
            if isinstance(hctx, dict):
                recap_intent = bool(hctx.get("rt_recap_intent", False))
        except Exception:
            recap_intent = False

        # Realtime recurrence index for this role (0 = first time we see it this session).
        rkey = str(role or "").strip().lower()
        try:
            seen = int(self._role_occurrences.get(rkey, 0) or 0)
        except Exception:
            seen = 0
        try:
            self._role_occurrences[rkey] = int(seen) + 1
        except Exception:
            pass
        try:
            self._sections_seen = int(getattr(self, "_sections_seen", 0) or 0) + 1
        except Exception:
            self._sections_seen = 0

        slots = self.slots_for_section(
            form_mode=str(form_mode),
            role=str(role),
            bars=int(plan.bars),
            beats_per_bar=float(plan.beats_per_bar),
        )
        if not slots:
            return

        # Phrase-aware snapping: align motif slots to phrase windows when phrase plans exist.
        # This uses the melody generator's PhrasePlanner outputs (phrase_role/cadence intent).
        # phrase_windows: (t0, t1, phrase_role, phrase_id, hook_anchor_degree)
        phrase_windows: List[Tuple[float, float, str, int, Optional[int]]] = []
        try:
            bars_i = int(getattr(plan, "bars", 0) or 0)
            bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
            mg = getattr(self.owner, "melody_gen", None)
            pplans = getattr(mg, "_last_phrase_plans", None) if mg is not None else None
            if bars_i > 0 and bpb > 1e-9 and isinstance(pplans, list) and pplans:
                nphr = max(1, int(len(pplans)))
                for pid, pp in enumerate(list(pplans)):
                    bar_start = int((float(pid) / float(nphr)) * float(bars_i))
                    bar_end = int((float(pid + 1) / float(nphr)) * float(bars_i))
                    if pid == nphr - 1:
                        bar_end = int(bars_i)
                    bar_start = max(0, min(int(bars_i), int(bar_start)))
                    bar_end = max(int(bar_start), min(int(bars_i), int(bar_end)))
                    t0 = float(bar_start) * float(bpb)
                    t1 = float(bar_end) * float(bpb)
                    pr = ""
                    try:
                        pr = str(getattr(pp, "phrase_role", "") or "")
                    except Exception:
                        pr = ""
                    ha = None
                    try:
                        v = getattr(pp, "hook_anchor_degree", None)
                        ha = int(v) if v is not None else None
                    except Exception:
                        ha = None
                    phrase_windows.append((t0, t1, pr, int(pid), ha))
        except Exception:
            phrase_windows = []

        if phrase_windows:
            snapped: List[MotifSlot] = []
            r = str(role or "").strip().lower()
            for slot in list(slots):
                try:
                    st = float(slot.start_beats)
                    # Decide which phrase-role we prefer for this slot.
                    prefer = None
                    if r in {"b", "chorus", "hook"} and st <= 1e-6:
                        prefer = "opening"
                    elif r in {"pre_chorus"}:
                        prefer = "cadence"
                    else:
                        # Late-in-section quotes sound best near cadence phrases.
                        total_beats = float(plan.bars) * float(plan.beats_per_bar)
                        if st >= max(0.0, total_beats - 6.0):
                            prefer = "cadence"

                    candidates = phrase_windows
                    if prefer is not None:
                        c2 = [w for w in phrase_windows if str(w[2] or "").lower() == str(prefer).lower()]
                        if c2:
                            candidates = c2
                    # Choose the nearest phrase start to the requested slot start.
                    best = min(candidates, key=lambda w: abs(float(w[0]) - float(st)))
                    t0, t1, _pr, _pid, _ha = best
                    length_cap = max(0.5, float(t1 - t0))
                    snapped.append(
                        MotifSlot(
                            start_beats=float(t0),
                            length_beats=min(float(slot.length_beats), float(length_cap)),
                            strength=float(slot.strength),
                        )
                    )
                except Exception:
                    snapped.append(slot)
            slots = snapped

        # Decide whether this section should use contrast material (bridge-ish).
        use_contrast = False
        contrast_enabled = resolve_config("composition", "hook_contrast_answer_enabled", True, bool)
        if contrast_enabled:
            try:
                rlc = str(role or "").strip().lower()
            except Exception:
                rlc = ""
            # Primary: a_prime is a contrasting episode / bridge-like section.
            if rlc in {"a_prime"}:
                use_contrast = True
            # Realtime special events can explicitly mark contrast bridges.
            try:
                hctx = getattr(self.owner, "_emotion_transition_handoff_ctx", None) or {}
                if isinstance(hctx, dict):
                    if str(hctx.get("rt_special_event", "") or "").strip().lower() == "contrast_bridge":
                        use_contrast = True
            except Exception:
                pass
        # Recaps always restate the theme (never contrast).
        if recap_intent:
            use_contrast = False
        hook = contrast if (use_contrast and contrast is not None) else theme
        motif_id_for_snapshot = "contrast" if (hook is contrast and contrast is not None) else "theme"

        # Chorus lift: voice motif higher.
        octave_shift = 12 if role == "b" else 0
        if use_contrast:
            # Contrast should feel lower/less "anthemic" than a chorus.
            octave_shift = 0

        # Decide development variant for this section occurrence.
        # 0: statement (clear), 1: variation, 2+: fragment/answer (more developmental).
        # Allow presets/macros to control the evolution speed.
        dev = 0.5
        dev = resolve_config("composition", "hook_development", 0.5, float)
        dev = max(0.0, min(1.0, float(dev)))
        # Song blueprint lifecycle stage can steer hook development deterministically.
        lifecycle_on = resolve_config("composition", "motif_lifecycle_enabled", True, bool)
        lifecycle_strength = resolve_config("composition", "motif_lifecycle_strength", 0.7, float)
        lifecycle_strength = max(0.0, min(1.0, float(lifecycle_strength)))
        bp_stage = ""
        if lifecycle_on and lifecycle_strength > 1e-6:
            try:
                bp_stage = str(getattr(self.owner, "_song_blueprint_motif_stage", "") or "").strip().lower()
            except Exception:
                bp_stage = ""
            if bp_stage in {"introduce", "state"}:
                dev = float((1.0 - lifecycle_strength) * float(dev) + lifecycle_strength * 0.28)
            elif bp_stage in {"build", "develop"}:
                dev = float((1.0 - lifecycle_strength) * float(dev) + lifecycle_strength * 0.54)
            elif bp_stage in {"restate"}:
                dev = float((1.0 - lifecycle_strength) * float(dev) + lifecycle_strength * 0.36)
            elif bp_stage in {"payoff"}:
                dev = float((1.0 - lifecycle_strength) * float(dev) + lifecycle_strength * 0.22)
            elif bp_stage in {"fragment"}:
                dev = float((1.0 - lifecycle_strength) * float(dev) + lifecycle_strength * 0.82)
            elif bp_stage in {"contrast"}:
                use_contrast = bool(contrast is not None)

        if dev <= 0.33:
            # Slow development: repeat statements longer.
            if seen <= 1:
                section_variant = "statement"
            elif seen == 2:
                section_variant = "variation"
            else:
                section_variant = "fragment"
        elif dev >= 0.66:
            # Fast development: move to fragment quickly.
            section_variant = "statement" if seen <= 0 else "fragment"
        else:
            # Default development.
            if seen <= 0:
                section_variant = "statement"
            elif seen == 1:
                section_variant = "variation"
            else:
                section_variant = "fragment"

        # Development can also depend on role: pre-chorus prefers "lead-in" behavior.
        if rkey in {"pre_chorus"} and section_variant != "statement":
            section_variant = "lead_in"
        # Recap intent: force a clear statement so the hook reads as a return.
        if recap_intent and rkey in {"b", "tag"}:
            section_variant = "statement"
        if bp_stage in {"payoff", "restate"} and rkey in {"b", "chorus", "hook", "tag"}:
            section_variant = "statement"
        elif bp_stage in {"fragment"}:
            section_variant = "fragment"
        elif bp_stage in {"build"} and section_variant == "statement":
            section_variant = "lead_in"

        # Adjust slot constraints based on development level.
        adj_slots: List[MotifSlot] = []
        for slot in list(slots):
            try:
                # Higher development lowers copy strength slightly (more variation allowed).
                strength = float(slot.strength) * float(1.0 - 0.25 * dev)
                strength = max(0.55, min(1.0, float(strength)))
                if section_variant in {"fragment", "lead_in"}:
                    # Keep the identity but use shorter quotes.
                    adj_slots.append(
                        MotifSlot(
                            start_beats=float(slot.start_beats),
                            length_beats=max(2.0, min(float(slot.length_beats), 4.0)),
                            strength=float(min(float(strength), 0.85)),
                        )
                    )
                elif section_variant == "variation":
                    adj_slots.append(
                        MotifSlot(
                            start_beats=float(slot.start_beats),
                            length_beats=float(slot.length_beats),
                            strength=float(min(float(strength), 0.90)),
                        )
                    )
                else:
                    adj_slots.append(
                        MotifSlot(
                            start_beats=float(slot.start_beats),
                            length_beats=float(slot.length_beats),
                            strength=float(strength),
                        )
                    )
            except Exception:
                adj_slots.append(slot)
        slots = adj_slots
        # Recap intent: increase copy strength modestly and prefer longer quotes.
        if recap_intent and slots:
            boosted: List[MotifSlot] = []
            for slot in slots:
                try:
                    boosted.append(
                        MotifSlot(
                            start_beats=float(slot.start_beats),
                            length_beats=float(max(float(slot.length_beats), 4.0)),
                            strength=float(max(float(slot.strength), 0.92)),
                        )
                    )
                except Exception:
                    boosted.append(slot)
            slots = boosted

        # Remove lead notes that overlap slot windows, then insert motif notes.
        filtered = []
        for ev in plan.melody_events:
            if len(ev) != 6 or int(ev[0]) != 2:
                filtered.append(ev)
                continue
            s = float(ev[3])
            e = s + float(ev[4])
            overlaps = any(
                s < slot.start_beats + slot.length_beats - 1e-6 and e > slot.start_beats + 1e-6
                for slot in slots
            )
            if not overlaps:
                filtered.append(ev)
        injected = []
        m_chords, m_roots, m_bars, m_bpb = _harmony_lists_for_motif(plan)
        # Record slot metadata on the plan so finalization can tag annotations.
        slot_tags: list[dict] = []
        for si, slot in enumerate(slots):
            # Answer transform: in the B-half restatement slot, preserve rhythm/contour but
            # allow slightly more chord-aware variation and start from the local melody degree.
            try:
                is_answer = int(m_bars) == 16 and float(slot.start_beats) >= float(8.0 * float(m_bpb)) - 1e-6
            except Exception:
                is_answer = False
            slot_variant = "answer" if bool(is_answer) else str(section_variant)
            start_deg = None
            if is_answer and plan.melody_events:
                try:
                    # Find the most recent melody note before the slot and map it to a scale degree.
                    prev = None
                    for ev in plan.melody_events:
                        if len(ev) == 6 and int(ev[0]) == 2 and float(ev[3]) < float(slot.start_beats) - 1e-6:
                            if prev is None or float(ev[3]) > float(prev[3]):
                                prev = ev
                    if prev is not None:
                        t0 = float(prev[3])
                        bar0 = int(t0 // float(m_bpb))
                        bar0 = max(0, min(int(m_bars) - 1, int(bar0)))
                        root0 = int(m_roots[bar0]) if m_roots and bar0 < len(m_roots) else int(plan.root_note)
                        scale = list(getattr(plan.emotion, "scale_intervals", []) or [])
                        scale_pcs = [int(iv) % 12 for iv in scale]
                        start_deg = self._degree_from_midi(int(prev[1]), int(root0), scale_pcs)
                except Exception:
                    start_deg = None

            # Phrase hook anchor: prefer using the phrase planner's hook_anchor_degree
            # at the start of a slot window (musically stable restatements).
            ha_strength = resolve_config("composition", "hook_anchor_degree_strength", 0.0, float)
            ha_strength = max(0.0, min(1.0, float(ha_strength)))
            if phrase_windows and ha_strength > 1e-6:
                try:
                    # Find the phrase window containing this slot start.
                    st0 = float(slot.start_beats)
                    pw = next((w for w in phrase_windows if float(w[0]) - 1e-6 <= st0 < float(w[1]) + 1e-6), None)
                except Exception:
                    pw = None
                if pw is not None:
                    try:
                        ha = pw[4]
                    except Exception:
                        ha = None
                    if ha is not None:
                        # Blend: at low strength keep existing behavior; at high, force hook anchor.
                        try:
                            rng = getattr(self.owner, "rng", random)
                        except Exception:
                            rng = random
                        if float(ha_strength) >= 0.999 or rng.random() < float(ha_strength):
                            start_deg = int(ha) % 7
            # Optional explicit A-material reuse: if the song stored a verse rhythm cell,
            # reuse it in chorus-like roles so the hook reads as a true restatement.
            rhythm_cell = None
            try:
                if str(role) in {"pre_chorus", "b", "chorus", "hook", "a_prime", "tag"}:
                    rhythm_cell = getattr(self.owner, "_song_rhythm_cell", None)
            except Exception:
                rhythm_cell = None
            if rhythm_cell:
                try:
                    rc = [float(x) for x in list(rhythm_cell) if float(x) > 1e-6]
                except Exception:
                    rc = None
                if rc:
                    # Light variation: second slot in chorus rotates the cell by one.
                    try:
                        if float(slot.start_beats) > 1e-6:
                            rc = rc[1:] + rc[:1]
                    except Exception:
                        pass
                    rhythm_cell = rc

            # Motif transform grammar (role + section/slot variant aware).
            t_strength = resolve_config("composition", "hook_transform_strength", 0.0, float)
            # Let lower-copy slots transform slightly more.
            eff_t_strength = float(max(0.0, min(1.0, float(t_strength)))) * float(max(0.0, 1.05 - float(slot.strength)))
            if slot_variant in {"variation", "fragment", "lead_in", "answer"}:
                eff_t_strength = min(1.0, float(eff_t_strength) + 0.12)
            try:
                rrng = getattr(self.owner, "rng", random)
            except Exception:
                rrng = random
            h_intervals, h_rhythms, h_tname = transform_motif_for_slot(
                intervals=list(getattr(hook, "intervals", []) or []),
                rhythms=list(getattr(hook, "rhythms", []) or []),
                role=str(role),
                section_variant=str(section_variant),
                slot_variant=str(slot_variant),
                slot_index=int(si),
                total_slots=int(len(slots)),
                strength=float(eff_t_strength),
                rng=rrng,
            )
            hook_use = SongHookMotif(
                intervals=list(h_intervals or list(getattr(hook, "intervals", []) or [])),
                rhythms=list(h_rhythms or list(getattr(hook, "rhythms", []) or [])),
                contour=str(getattr(hook, "contour", "") or ""),
            )

            injected.extend(
                self._render_hook_as_events(
                    hook_use,
                    emotion=plan.emotion,
                    chords=m_chords,
                    roots=m_roots,
                    bars=m_bars,
                    beats_per_bar=m_bpb,
                    slot=slot,
                    channel=2,
                    octave_shift=octave_shift,
                    start_degree_override=start_deg,
                    answer_mode=bool(is_answer),
                    rhythm_override=rhythm_cell,
                )
            )
            try:
                motif_id = "contrast" if (hook is contrast and contrast is not None) else "theme"
            except Exception:
                motif_id = "theme"
            family_on = resolve_config("composition", "motif_family_tracking_enabled", True, bool)
            family_k = resolve_config("composition", "motif_family_tracking_strength", 0.75, float)
            family_name = "main"
            if family_on:
                try:
                    if str(motif_id) == "contrast":
                        family_name = "contrast"
                    elif str(slot_variant) in {"lead_in", "answer"}:
                        family_name = "answer"
                    elif str(slot_variant) in {"variation", "fragment"} and float(family_k) >= 0.55:
                        family_name = "variation"
                except Exception:
                    family_name = "main"
                self._family_counts[str(family_name)] = int(self._family_counts.get(str(family_name), 0) or 0) + 1
            # Mark a "theme statement" whenever we make a clear entry quote.
            try:
                if str(motif_id) == "theme" and str(slot_variant) == "statement" and float(slot.start_beats) <= 1e-6:
                    self._last_theme_statement_seen = int(self._sections_seen)
            except Exception:
                pass
            family_count = int(self._family_counts.get(str(family_name), 0) or 0)
            slot_tags.append(
                {
                    "channel": 2,
                    "motif_id": str(motif_id),
                    "motif_family": str(family_name),
                    "motif_family_count": int(family_count),
                    "motif_variant": str(slot_variant),
                    "motif_transform": str(h_tname),
                    "start_beats": float(slot.start_beats),
                    "length_beats": float(slot.length_beats),
                }
            )
        try:
            setattr(plan, "_motif_family_counts", dict(self._family_counts))
            setattr(self.owner, "_motif_family_counts", dict(self._family_counts))
        except Exception:
            pass
        try:
            snap = self.development_snapshot(
                role=str(role),
                section_index=int(section_index),
                section_variant=str(section_variant),
                motif_id=str(motif_id_for_snapshot),
                slot_tags=list(slot_tags),
            )
            setattr(plan, "motif_development", dict(snap))
            setattr(self.owner, "_last_section_motif_development", dict(snap))
        except Exception:
            pass
        plan.melody_events = sorted(filtered + injected, key=lambda e: float(e[3]) if len(e) == 6 else 0.0)
        try:
            existing = getattr(plan, "_motif_slot_tags", None)
            if isinstance(existing, list):
                existing.extend(slot_tags)
                setattr(plan, "_motif_slot_tags", existing)
            else:
                setattr(plan, "_motif_slot_tags", list(slot_tags))
        except Exception:
            pass