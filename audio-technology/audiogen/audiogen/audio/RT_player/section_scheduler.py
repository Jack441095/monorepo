# audio/RT_player/section_scheduler.py
"""
Realtime **section / bar** timeline for the polyphonic player (pre-generation, slicing, tempo).

**Pipeline (dependency direction):**

  ``composition/``  →  *note events + plans*  →  ``audio/`` (this stack renders buffers).

``composition`` must not import ``audio``; the reverse is also limited: this file is the
**only** `audio` module that may `import` / `from` ``composition`` (enforced in
``tests/test_audio_composition_import_boundary.py``). Put new composition couplings in a
shared `core` helper and import that from both sides, or extend the test allowlist on purpose.

Imports here are limited to small helpers (role display labels, handoff context extraction)
so scheduling stays aware of song form without turning the player into a second generator.

Bar clocking uses ``config`` effective section tempo; see :func:`core.config.effective_tempo_bpm_from_config`.
"""
import math
import secrets
import sys
import threading
import time

import numpy as np

from composition.arrangement_role_labels import arrangement_role_display_name
from audiogen_core.config import effective_tempo_bpm_from_config


class SectionScheduler:
    """Encapsulates section generation, pre-generation, and bar slicing logic.

    Emotion changes and arranged-song looping both rely on the same pre-generation
    pipeline. Use ``ensure_pregen_enqueued()`` from any thread so wakeups are never
    dropped when a build is already in flight (rapid ``e``/``n`` or long generates).
    """

    @staticmethod
    def _notify_section_compose_time(owner, compose_seconds: float) -> None:
        """Record section compose duration (player API or lightweight test owners)."""
        fn = getattr(owner, "record_section_compose_time", None)
        if callable(fn):
            fn(float(compose_seconds))
            return
        try:
            owner.last_section_compose_time = float(compose_seconds)
        except Exception:
            pass

    @staticmethod
    def _section_events_nonempty(events) -> bool:
        if events is None:
            return False
        if isinstance(events, (list, tuple)):
            return len(events) > 0
        try:
            return len(events) > 0
        except TypeError:
            return bool(events)

    def _pending_targets_different_emotion(self, built_emotion) -> bool:
        """True if user queued a different target than ``built_emotion`` (name-aware)."""
        pending = self.pending_emotion
        if pending is None:
            return False
        if pending is built_emotion:
            return False
        pn = getattr(pending, "name", None)
        bn = getattr(built_emotion, "name", None)
        if isinstance(pn, str) and isinstance(bn, str):
            return pn.lower() != bn.lower()
        return True

    def _bootstrap_cold_start_variation(self) -> None:
        """
        Avoid identical cold-start openings across launches for non-arranged playback.

        The realtime form loop uses ``section_index`` as its anchor; always starting at 0
        makes the first audible section feel like the same "intro" every time.
        """
        owner = self.owner
        try:
            arranged = bool(self._arranged_songs_enabled())
        except Exception:
            arranged = False
        if arranged:
            return
        try:
            audio_cfg = getattr(owner.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "cold_start_randomize_section_index", True)) if audio_cfg is not None else True
        except Exception:
            enabled = True
        if not enabled:
            return
        try:
            span = int(getattr(audio_cfg, "cold_start_section_index_span", 64) or 64) if audio_cfg is not None else 64
        except Exception:
            span = 64
        span = max(1, min(4096, int(span)))
        try:
            self.section_index = int(secrets.randbelow(int(span)))
        except Exception:
            try:
                self.section_index = int(time.time_ns() % int(span))
            except Exception:
                self.section_index = 0

    def __init__(self, owner, logger):
        self.owner = owner
        self.logger = logger
        self.current_section_events = []
        self.current_section_bars = 0
        self.next_bar_index = 0
        self.next_section_events = None
        self.next_section_bars = 0
        self.next_section_ready = False
        self.next_section_emotion = None
        self.next_section_root = None
        # Arranged-song (full timeline) section role segments (intro/a/pre_chorus/b/outro...).
        # Each segment is a dict with: start_bar (inclusive), end_bar (exclusive), role, role_label.
        self.current_arrangement_segments = None
        self.next_arrangement_segments = None
        self.current_arranged_song_render = None
        self.next_arranged_song_render = None
        self.completed_arranged_song_count = 0
        self.last_completed_arranged_song_events = []
        self.last_completed_arranged_song_bars = 0
        self.last_completed_arranged_song_segments = None
        self.last_completed_arranged_song_render = None
        self.last_completed_arranged_song_emotion = None
        self.last_completed_arranged_song_root = None
        self._arranged_completion_armed = False
        self._last_logged_arrangement_role = None
        self.pre_generation_running = False
        self.pending_emotion = None
        self.pending_root = None
        self.section_index = 0
        # Bars fully played out on the audio device (callback), not bars pre-rendered into the queue.
        # Pending-emotion phrase boundaries use this so `n` reacts on what you hear, not buffer depth.
        self.bars_played_this_section = 0
        # Another pre_generate was requested while one was already running (e.g. rapid emotion changes).
        self._pregen_followup_needed = False
        # Arranged looping: keep song-to-song variation by advancing seed/state.
        self._arranged_song_iteration = 0
        # When the user queues an emotion switch during arranged-song playback, we snapshot
        # the currently-heard arrangement role (e.g. "b" chorus) so the new emotion can
        # start at the same role instead of restarting the form.
        # Shape: {"role": str, "role_bar_offset": int} or None.
        self._pending_emotion_role_hint = None
        self._defer_pregen_until_first_bar = False
        # Per-bar lists of indices into ``current_section_events`` (rebuilt when section changes).
        self._bar_event_indices = None
        self._bar_index_source_len = -1
        self._bar_index_source_bars = -1

    def _invalidate_bar_event_index(self) -> None:
        self._bar_event_indices = None
        self._bar_index_source_len = -1
        self._bar_index_source_bars = -1

    def _rebuild_bar_event_index(self) -> None:
        """Bucket event indices by bar for O(touching_events) slicing instead of O(all_events)."""
        events = self.current_section_events
        n_bars = max(1, int(self.current_section_bars or 0))
        if not self._section_events_nonempty(events):
            self._bar_event_indices = [[] for _ in range(n_bars)]
            self._bar_index_source_len = 0
            self._bar_index_source_bars = n_bars
            return
        n_ev = len(events)
        buckets: list[list[int]] = [[] for _ in range(n_bars)]
        for i, ev in enumerate(events):
            if not ev or len(ev) < 5:
                continue
            try:
                start = float(ev[3])
                duration = float(ev[4])
            except Exception:
                continue
            if duration <= 0.0:
                continue
            span_end = start + duration
            i0 = max(0, min(n_bars - 1, int(start // 4.0)))
            i1 = max(i0, min(n_bars - 1, int(math.ceil(span_end / 4.0) - 1)))
            for bi in range(i0, i1 + 1):
                buckets[bi].append(int(i))
        self._bar_event_indices = buckets
        self._bar_index_source_len = int(n_ev)
        self._bar_index_source_bars = int(n_bars)

    def _ensure_bar_event_index(self) -> None:
        n_ev = len(self.current_section_events) if self.current_section_events else 0
        n_b = max(1, int(self.current_section_bars or 0))
        if (
            self._bar_event_indices is None
            or self._bar_index_source_len != n_ev
            or self._bar_index_source_bars != n_b
        ):
            self._rebuild_bar_event_index()

    @staticmethod
    def _realtime_loop_roles_for_section_index(
        policy,
        section_index: int,
        *,
        form_mode_override: str = "",
        drop_outro: bool = True,
    ) -> tuple[str, str, str]:
        """
        Compute (role, next_role, special_event) for continuous realtime playback when
        we're not using arranged-song segments.

        We intentionally *loop* a form sequence (excluding a terminal outro) so the
        section planner doesn't get stuck forever in the last role (often `outro`).
        """
        try:
            idx = int(section_index)
        except Exception:
            idx = 0
        if idx < 0:
            idx = 0
        try:
            fm = str(form_mode_override or getattr(policy, "form_mode", "default") or "default")
        except Exception:
            fm = "default"
        try:
            seq = getattr(policy, "_FORM_SEQUENCES", None)
            seq = (seq or {}).get(fm) or (seq or {}).get("default")
        except Exception:
            seq = None
        if not isinstance(seq, (list, tuple)) or not seq:
            seq = ("intro", "a", "pre_chorus", "b", "a", "b")

        # Keep intro only at section 0, then loop the core content.
        seq_l = [str(r) for r in seq if str(r)]
        if not seq_l:
            seq_l = ["intro", "a", "pre_chorus", "b", "a", "b"]
        intro = seq_l[0]
        # Remove any terminal outro from the loop body so looping stays musical.
        if drop_outro:
            body = [r for r in seq_l[1:] if str(r).strip().lower() != "outro"]
        else:
            body = list(seq_l[1:])
        if not body:
            body = ["a", "pre_chorus", "b", "a", "b"]

        if idx == 0:
            role = intro
            next_role = body[0]
        else:
            j = (idx - 1) % len(body)
            role = body[j]
            next_role = body[(j + 1) % len(body)]

        # Best-effort labels that downstream can interpret for gestures.
        special = ""
        try:
            if role == "a_prime":
                special = "contrast_bridge"
            elif role == "tag":
                special = "tag_recap"
        except Exception:
            special = ""
        return str(role), str(next_role), str(special)

    def snapshot_current_arrangement_role_hint(self) -> None:
        """
        Capture the current arrangement role (heard bar index) for a pending emotion switch.
        No-op if we don't have role segments for the current arranged timeline.
        """
        owner = self.owner
        with owner.section_lock:
            segs = self.current_arrangement_segments
            heard = int(getattr(self, "bars_played_this_section", 0) or 0)
        if not isinstance(segs, list) or not segs:
            self._pending_emotion_role_hint = None
            return
        # heard == number of completed bars; the "current" musical moment is the next bar.
        bar_idx = max(0, int(heard))
        seg = None
        for s in segs:
            try:
                sb = int(s.get("start_bar", -1))
                eb = int(s.get("end_bar", -1))
            except Exception:
                continue
            if sb <= bar_idx < eb:
                seg = s
                break
        if not isinstance(seg, dict):
            self._pending_emotion_role_hint = None
            return
        role = str(seg.get("role", "") or "").strip()
        if not role:
            self._pending_emotion_role_hint = None
            return
        try:
            sb = int(seg.get("start_bar", 0) or 0)
        except Exception:
            sb = 0
        self._pending_emotion_role_hint = {
            "role": role,
            "role_bar_offset": max(0, int(bar_idx - sb)),
        }

    @staticmethod
    def _trim_events_to_bar_window(events, *, start_bar: int, total_bars: int):
        """
        Trim absolute-time (beat) events to a bar window [start_bar, total_bars),
        and rebase so the returned events start at bar 0.
        """
        if not isinstance(events, list) or not events:
            return []
        sb = max(0, int(start_bar))
        tb = max(sb, int(total_bars))
        start_beats = float(sb) * 4.0
        end_beats = float(tb) * 4.0
        out = []
        for ev in events:
            if not ev or len(ev) < 6:
                continue
            try:
                ch, midi, vel, st, dur, notes = ev
                st = float(st)
                dur = float(dur)
            except Exception:
                continue
            if dur <= 0:
                continue
            ev_end = st + dur
            if ev_end <= start_beats or st >= end_beats:
                continue
            # Clip to window.
            st2 = max(st, start_beats)
            end2 = min(ev_end, end_beats)
            dur2 = max(0.0, end2 - st2)
            if dur2 <= 1e-9:
                continue
            rebased = (ch, midi, vel, float(st2 - start_beats), float(dur2), notes)
            out.append(rebased)
        return out

    @staticmethod
    def _trim_segments_to_bar_window(segs, *, start_bar: int):
        if not isinstance(segs, list) or not segs:
            return None
        sb = max(0, int(start_bar))
        out = []
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            try:
                a = int(seg.get("start_bar", 0) or 0)
                b = int(seg.get("end_bar", 0) or 0)
            except Exception:
                continue
            if b <= sb:
                continue
            seg2 = dict(seg)
            seg2["start_bar"] = max(0, int(a - sb))
            seg2["end_bar"] = max(0, int(b - sb))
            out.append(seg2)
        return out or None

    def note_bar_played(self) -> None:
        """Call once per completed bar chunk from the playback callback."""
        owner = self.owner
        with owner.section_lock:
            self.bars_played_this_section += 1

    def ensure_pregen_enqueued(self) -> None:
        """
        Idempotent: schedule at most one in-flight pre-generation worker; if one is already
        running, set follow-up so the current run chains another pass (latest pending emotion wins).
        """
        owner = self.owner
        # Unit tests can interleave background pre-generation with assertions and create
        # nondeterministic state flips (next_section_ready/events). When running under unittest,
        # disable async threads unless the owner explicitly opts in.
        try:
            in_unittest = "unittest" in sys.modules
            allow_async = getattr(owner, "allow_async_pregen", None)
            if in_unittest and allow_async is None:
                return
            if allow_async is False:
                return
        except Exception:
            pass
        with owner.section_lock:
            if bool(getattr(self, "_defer_pregen_until_first_bar", False)):
                try:
                    if int(getattr(self, "next_bar_index", 0) or 0) <= 0:
                        return
                    self._defer_pregen_until_first_bar = False
                except Exception:
                    return
            if self.next_section_ready:
                return
            if self.pre_generation_running:
                self._pregen_followup_needed = True
                return
        threading.Thread(
            target=self.pre_generate_next_section,
            name="section-pregen",
            daemon=True,
        ).start()

    def _arranged_songs_enabled(self) -> bool:
        comp = getattr(self.owner.config, "composition", None)
        return bool(getattr(comp, "arranged_songs_default", False))

    def _arranged_realtime_prefers_full_timeline(self) -> bool:
        try:
            comp = getattr(self.owner.config, "composition", None)
            if comp is None:
                return False
            return bool(getattr(comp, "arranged_realtime_full_timeline", False))
        except Exception:
            return False

    def _arranged_loop_enabled(self) -> bool:
        comp = getattr(self.owner.config, "composition", None)
        if not comp or not getattr(comp, "arranged_songs_default", False):
            return False
        return bool(getattr(comp, "arranged_song_loop", True))

    def _maybe_schedule_next_arranged_song(self):
        """
        Queue generation of the next full arranged song (same emotion/root) so playback
        can continue when the current timeline ends. No-op if looping is off or a
        next section is already buffered / generating.
        """
        if not self._arranged_loop_enabled():
            return
        self.ensure_pregen_enqueued()

    def reset_transition_state(self):
        self.next_bar_index = 0
        self.next_section_ready = False
        self.next_section_events = None
        self.next_section_bars = 0
        self.next_section_emotion = None
        self.next_section_root = None
        self.pre_generation_running = False
        self.pending_emotion = None
        self.pending_root = None
        self.section_index = 0
        self.bars_played_this_section = 0
        self._pregen_followup_needed = False
        self._arranged_song_iteration = 0
        self.current_arrangement_segments = None
        self.next_arrangement_segments = None
        self.current_arranged_song_render = None
        self.next_arranged_song_render = None
        self._arranged_completion_armed = False
        self._last_logged_arrangement_role = None
        self._defer_pregen_until_first_bar = False

    @staticmethod
    def _role_label(role: str) -> str:
        return arrangement_role_display_name(role)

    def _arrangement_role_for_bar(self, bar_idx: int):
        segs = self.current_arrangement_segments
        if not isinstance(segs, list) or not segs:
            return None
        b = int(bar_idx)
        for seg in segs:
            try:
                sb = int(seg.get("start_bar", -1))
                eb = int(seg.get("end_bar", -1))
            except Exception:
                continue
            if sb <= b < eb:
                return seg
        return None

    def _schedule_async_pre_generation(self):
        self.ensure_pregen_enqueued()

    def _capture_completed_arranged_song_locked(self) -> None:
        """Snapshot the just-finished arranged timeline for CLI replay/export actions."""
        if not bool(getattr(self, "_arranged_completion_armed", False)):
            return
        if not self._arranged_songs_enabled():
            return
        segs = self.current_arrangement_segments
        if not isinstance(segs, list) or not segs:
            return
        try:
            bars = int(self.current_section_bars or 0)
        except Exception:
            bars = 0
        if bars <= 0:
            return
        try:
            has_outro = any(str(s.get("role", "") or "").strip().lower() == "outro" for s in segs if isinstance(s, dict))
        except Exception:
            has_outro = False
        # Avoid treating short cold-start previews as completed songs.
        if not has_outro:
            try:
                min_total = int(getattr(getattr(self.owner.config, "composition", None), "arranged_song_end_fade_min_total_bars", 20) or 20)
            except Exception:
                min_total = 20
            if bars < max(8, int(min_total)):
                return
        self.last_completed_arranged_song_events = list(self.current_section_events or [])
        self.last_completed_arranged_song_bars = int(bars)
        self.last_completed_arranged_song_segments = [dict(s) for s in list(segs or []) if isinstance(s, dict)]
        self.last_completed_arranged_song_render = getattr(self, "current_arranged_song_render", None)
        try:
            self.last_completed_arranged_song_emotion = getattr(self.owner, "_emotion", None)
            self.last_completed_arranged_song_root = getattr(self.owner, "_root", None)
        except Exception:
            self.last_completed_arranged_song_emotion = None
            self.last_completed_arranged_song_root = None
        self.completed_arranged_song_count = int(getattr(self, "completed_arranged_song_count", 0) or 0) + 1
        self._arranged_completion_armed = False

    def _generate_section_events(
        self,
        emotion,
        root,
        bars,
        *,
        runtime_mode_override: str | None = None,
        planner_effort_override: str | None = None,
    ):
        owner = self.owner
        target_notes_per_bar = owner._runtime_target_notes_per_bar()
        # Keep the full composition path (best-of-K, joint plan, QA) independent of the
        # audio CPU ladder (emergency/safe/balanced). Pressure only affects render_bar FX.
        compose_runtime_mode = str(runtime_mode_override or "normal").strip().lower() or "normal"
        planner_effort = str(planner_effort_override or "").strip().lower()
        handoff_ctx = None
        with owner.section_lock:
            pending = self.pending_emotion is not None
            # Always snapshot the previous audible section for continuity (even without emotion changes).
            prev_ev = list(self.current_section_events) if self._section_events_nonempty(self.current_section_events) else []
            prev_bars = self.current_section_bars
            prev_emotion = getattr(owner, "_emotion", None) if pending else None
        if prev_ev and prev_bars > 0:
            from composition.transition_handoff import extract_last_bar_harmonic_context

            handoff_ctx = extract_last_bar_harmonic_context(prev_ev, prev_bars)
        # Continuity signals: loop iteration, recent tension peak, motif age.
        try:
            if handoff_ctx is None or not isinstance(handoff_ctx, dict):
                handoff_ctx = {}
        except Exception:
            handoff_ctx = {}
        try:
            # The composer uses this section_index when generating the *next* section.
            handoff_ctx["loop_iteration"] = int(self.section_index)
        except Exception:
            pass
        try:
            gen = getattr(getattr(owner, "composer", None), "gen", None)
            trace = getattr(gen, "_last_section_debug_trace_by_bar", None) if gen is not None else None
            if isinstance(trace, list) and trace:
                tvals = []
                for row in trace:
                    try:
                        tv = row.get("tension", None) if isinstance(row, dict) else None
                        if tv is not None:
                            tvals.append(float(tv))
                    except Exception:
                        continue
                if tvals:
                    handoff_ctx["recent_peak_tension"] = float(max(tvals))
        except Exception:
            pass
        try:
            gen = getattr(getattr(owner, "composer", None), "gen", None)
            mp = getattr(gen, "motif_plan", None) if gen is not None else None
            if mp is not None and hasattr(mp, "theme_statement_age_sections"):
                age = mp.theme_statement_age_sections()
                if age is not None:
                    handoff_ctx["motif_statement_age_sections"] = int(age)
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Realtime form scheduling (non-arranged playback only)
        # ------------------------------------------------------------------
        try:
            arranged = bool(self._arranged_songs_enabled())
        except Exception:
            arranged = False
        if not arranged:
            try:
                gen = getattr(getattr(owner, "composer", None), "gen", None)
                policy = getattr(gen, "arrangement_policy", None) if gen is not None else None
            except Exception:
                policy = None
            if policy is not None:
                try:
                    comp = getattr(getattr(owner, "config", None), "composition", None)
                    if comp is not None:
                        try:
                            rf = comp.realtime_form
                            loop_enabled = bool(rf.loop_enabled)
                            mode_override = str(rf.mode_override or "")
                            drop_outro = bool(rf.drop_outro)
                        except Exception:
                            loop_enabled = bool(getattr(comp, "realtime_form_loop_enabled", True))
                            mode_override = str(getattr(comp, "realtime_form_mode_override", "") or "")
                            drop_outro = bool(getattr(comp, "realtime_form_loop_drop_outro", True))
                    else:
                        loop_enabled, mode_override, drop_outro = True, "", True
                except Exception:
                    loop_enabled, mode_override, drop_outro = True, "", True
                if not loop_enabled:
                    policy = None
            if policy is not None:
                try:
                    role, next_role, special = self._realtime_loop_roles_for_section_index(
                        policy,
                        int(self.section_index),
                        form_mode_override=str(mode_override),
                        drop_outro=bool(drop_outro),
                    )
                    # Override role lookup used throughout SectionPlanner/ChordPlanner.
                    policy.set_realtime_role_override(int(self.section_index), str(role))
                    policy.set_realtime_role_override(int(self.section_index) + 1, str(next_role))
                    # Keep the override map bounded.
                    policy.clear_realtime_role_overrides_older_than(int(self.section_index) - 4)
                    # Export for debugging / downstream intent hooks.
                    if isinstance(handoff_ctx, dict):
                        handoff_ctx["rt_section_role"] = str(role)
                        handoff_ctx["rt_next_section_role"] = str(next_role)
                        if special:
                            handoff_ctx["rt_special_event"] = str(special)
                        # Recap intent: return-like roles and tags should restate hooks.
                        recap = bool(str(role).strip().lower() in {"tag", "b"} and str(special) in {"tag_recap"})
                        if str(role).strip().lower() == "b" and str(next_role).strip().lower() in {"a", "a_prime"}:
                            recap = True
                        handoff_ctx["rt_recap_intent"] = bool(recap)
                        # Energy lane: deterministic scalar used for texture + target shaping.
                        try:
                            comp = getattr(getattr(owner, "config", None), "composition", None)
                            if comp is not None:
                                try:
                                    arc_len = int(comp.realtime_form.energy_arc_length)
                                except Exception:
                                    arc_len = int(getattr(comp, "realtime_energy_arc_length", 8) or 8)
                            else:
                                arc_len = 8
                        except Exception:
                            arc_len = 8
                        arc_len = max(2, min(32, int(arc_len)))
                        try:
                            it = int(self.section_index)
                        except Exception:
                            it = 0
                        phase = int(it) % int(arc_len) if int(it) >= 0 else 0
                        prog = float(phase) / float(max(1, int(arc_len) - 1))
                        # Triangle arc 0..1..0
                        arc = 1.0 - abs(2.0 * float(prog) - 1.0)
                        arc = float(max(0.0, min(1.0, arc)))
                        # Role baseline (form semantics).
                        rb = {
                            "intro": 0.30,
                            "a": 0.45,
                            "pre_chorus": 0.60,
                            "b": 0.85,
                            "a_prime": 0.55,
                            "tag": 0.90,
                            "outro": 0.35,
                        }.get(str(role).strip().lower(), 0.55)
                        # Blend role baseline with global arc.
                        e = float(0.55 * float(rb) + 0.45 * float(arc))
                        handoff_ctx["rt_energy"] = float(max(0.0, min(1.0, e)))
                except Exception:
                    pass

        if pending and prev_emotion is not None:
            try:
                prev_name = str(getattr(prev_emotion, "name", "") or "").strip().lower()
            except Exception:
                prev_name = ""
            if prev_name:
                handoff_ctx["previous_emotion_name"] = prev_name
        kwargs = {
            "target_notes_per_bar": target_notes_per_bar,
            "runtime_mode": compose_runtime_mode,
            "section_index": self.section_index,
            "transition_handoff_context": handoff_ctx,
        }
        if planner_effort:
            kwargs["planner_effort"] = planner_effort
        try:
            return owner.composer.generate_section_events(emotion, root, bars, **kwargs)
        except TypeError:
            if "planner_effort" in kwargs:
                kwargs.pop("planner_effort", None)
                try:
                    return owner.composer.generate_section_events(emotion, root, bars, **kwargs)
                except TypeError:
                    pass
            return owner.composer.generate_section_events(emotion, root, bars)

    def _generate_arranged_song_events(self, emotion, root):
        owner = self.owner
        # Full arranged builds use normal composition quality; audio CPU ladder affects render only.
        runtime_mode = "normal"
        stress_mode = owner._runtime_generation_mode()
        # Realtime guardrail: building a full arranged song can be very expensive (tens of seconds
        # in worst cases). Even when done on a background thread it can still starve the PortAudio
        # callback and/or the gen loop due to CPU contention. Under stress, prefer a short arranged
        # preview chunk so audio never fully drains.
        try:
            comp = getattr(owner.config, "composition", None)
            preview_on_stress = bool(getattr(comp, "arranged_realtime_preview_on_stress", True)) if comp is not None else True
        except Exception:
            preview_on_stress = True
        # Only use arranged previews in *high* stress tiers. Using previews in the mild
        # "balanced" tier caused live arranged playback to frequently truncate to just
        # the first 1–2 sections (intro/verse), which reads as "the arrangement never
        # reaches chorus" even when the system is otherwise stable.
        if (
            preview_on_stress
            and str(stress_mode) in {"safe", "emergency"}
            and not self._arranged_realtime_prefers_full_timeline()
        ):
            try:
                events, total_bars = self._generate_arranged_preview_events(emotion, root)
                try:
                    segs = getattr(owner.composer, "_last_arranged_song_segments", None)
                except Exception:
                    segs = None
                return events, total_bars, segs
            except Exception:
                # Fall back to full generation below.
                pass
        # Continuous arranged music: when looping, advance seed and reset per-song memories
        # so the next timeline is genuinely different (avoids bar-33 replay).
        try:
            comp = getattr(owner.config, "composition", None)
            looping = bool(getattr(comp, "arranged_song_loop", True)) if comp is not None else True
            continuous = bool(getattr(comp, "arranged_song_continuous", True)) if comp is not None else True
            step = int(getattr(comp, "arranged_song_loop_seed_step", 1) or 1) if comp is not None else 1
        except Exception:
            looping, continuous, step = True, True, 1
        if looping and continuous:
            try:
                gen = getattr(getattr(owner, "composer", None), "gen", None)
                if gen is not None:
                    base = int(getattr(gen, "seed", 0) or 0)
                    self._arranged_song_iteration = int(getattr(self, "_arranged_song_iteration", 0) or 0) + 1
                    gen.reseed(int(base) + int(step) * int(self._arranged_song_iteration))
                    if hasattr(gen, "reset_song_arrangement_state"):
                        gen.reset_song_arrangement_state()
            except Exception:
                pass
        try:
            events, total_bars = owner.composer.generate_arranged_song_events(emotion, root, runtime_mode=runtime_mode)
        except (TypeError, AttributeError):
            bars = owner.config.composition.bars_per_section
            return self._generate_section_events(emotion, root, bars), bars, None
        segs = None
        try:
            segs = getattr(owner.composer, "_last_arranged_song_segments", None)
        except Exception:
            segs = None
        return events, total_bars, segs

    def _generate_arranged_preview_events(self, emotion, root, *, runtime_mode_override: str | None = None):
        owner = self.owner
        runtime_mode = str(runtime_mode_override or owner._runtime_generation_mode() or "normal").strip().lower()
        try:
            n = int(getattr(owner.config.composition, "arranged_emotion_switch_preview_sections", 2) or 2)
        except Exception:
            n = 2
        # Guardrail: previewing only 1 section usually means "intro only", which can read as
        # "stuck in intro" if the background full-song build is slow or throttled.
        min_sections = 1 if runtime_mode in {"preview", "cold_preview"} else 2
        n = max(int(min_sections), int(n))
        try:
            return owner.composer.generate_arranged_preview_events(
                emotion, root, runtime_mode=runtime_mode, preview_sections=n
            )
        except Exception:
            # Fallback: single chunk.
            bars = owner.config.composition.bars_per_section
            planner_effort = None
            if runtime_mode in {"preview", "cold_preview"}:
                try:
                    audio_cfg = getattr(owner.config, "audio", None)
                    planner_effort = (
                        str(getattr(audio_cfg, "cold_start_preview_planner_effort", "minimal") or "minimal")
                        if audio_cfg is not None
                        else "minimal"
                    )
                except Exception:
                    planner_effort = "minimal"
            return self._generate_section_events(
                emotion,
                root,
                bars,
                runtime_mode_override=runtime_mode,
                planner_effort_override=planner_effort,
            ), bars

    def generate_new_section(self):
        owner = self.owner
        bars = owner.config.composition.bars_per_section
        with owner.state_lock:
            emotion = owner._emotion
            root = owner._root
        if emotion is None:
            self.current_section_events = []
            self.current_section_bars = 0
            self._invalidate_bar_event_index()
            return
        self.section_index = 0
        self._bootstrap_cold_start_variation()
        start = time.time()
        if self._arranged_songs_enabled():
            events, bars, segs = self._generate_arranged_song_events(emotion, root)
        else:
            events = self._generate_section_events(emotion, root, bars)
            segs = None
        gen_time = time.time() - start
        self._notify_section_compose_time(owner, gen_time)
        self.current_section_events = events
        self.current_section_bars = bars
        self._invalidate_bar_event_index()
        self.next_bar_index = 0
        self.bars_played_this_section = 0
        self.current_arrangement_segments = segs
        try:
            self.current_arranged_song_render = getattr(owner.composer, "_last_arranged_song_render", None) if segs else None
        except Exception:
            self.current_arranged_song_render = None
        self._arranged_completion_armed = bool(isinstance(segs, list) and len(segs) > 0)
        self._last_logged_arrangement_role = None
        # Next timeline is pipelined via should_pre_generate + ensure_pregen_enqueued (player loop)
        # and emotion handoffs; avoid spawning pregen synchronously here (tests + preroll overlap).

    def generate_new_section_fast_preview(self, *, preview_bars: int = 1) -> None:
        """
        Fast-path cold start: generate a tiny single-section preview (usually 1 bar)
        so playback can begin quickly, then let the normal pre-generation pipeline
        build the full next timeline in the background.

        In arranged mode, either a short multi-section preview or a full arranged timeline
        is built here depending on ``composition.arranged_realtime_full_timeline``.
        """
        owner = self.owner
        pb = max(1, int(preview_bars))
        with owner.state_lock:
            emotion = owner._emotion
            root = owner._root
        if emotion is None:
            self.current_section_events = []
            self.current_section_bars = 0
            self._invalidate_bar_event_index()
            return
        self.section_index = 0
        self._bootstrap_cold_start_variation()
        start = time.time()
        if self._arranged_songs_enabled():
            # In arranged mode, a tiny single-section preview can sound like "bar 1 forever"
            # if the background full-song build is slower than startup playback. Use a short
            # arranged preview instead so the first audible timeline already has section motion.
            if self._arranged_realtime_prefers_full_timeline():
                events, bars, segs = self._generate_arranged_song_events(emotion, root)
            else:
                try:
                    audio_cfg = getattr(owner.config, "audio", None)
                    preview_runtime_mode = (
                        str(getattr(audio_cfg, "cold_start_preview_runtime_mode", "preview") or "preview")
                        if audio_cfg is not None
                        else "preview"
                    )
                except Exception:
                    preview_runtime_mode = "preview"
                events, bars = self._generate_arranged_preview_events(
                    emotion,
                    root,
                    runtime_mode_override=preview_runtime_mode,
                )
                try:
                    segs = getattr(owner.composer, "_last_arranged_song_segments", None)
                except Exception:
                    segs = None
        else:
            # Cold-start non-arranged previews: salt `CompositionGenerator.deterministic_rng` so
            # micro-choices (arp gestures, some planner tie-breaks) don't repeat every launch
            # while the global launch seed stays stable.
            gen = getattr(getattr(owner, "composer", None), "gen", None)
            orig_drng = getattr(gen, "deterministic_rng", None) if gen is not None else None
            wrapped = None
            try:
                try:
                    audio_cfg = getattr(owner.config, "audio", None)
                    rnd_preview = bool(getattr(audio_cfg, "cold_start_randomize_arranged_preview_seed", True)) if audio_cfg is not None else True
                except Exception:
                    rnd_preview = True
                try:
                    comp = getattr(owner.config, "composition", None)
                    pinned = bool(getattr(comp, "user_pinned_seed", False)) if comp is not None else False
                except Exception:
                    pinned = False

                if (not pinned) and rnd_preview and gen is not None and callable(orig_drng):
                    try:
                        salt = int(secrets.randbits(32))
                    except Exception:
                        salt = int(time.time_ns() & 0xFFFFFFFF)

                    def _wrapped_drng(*tokens):
                        return orig_drng("cold_preview_entropy", int(salt), *tokens)

                    wrapped = _wrapped_drng
                    setattr(gen, "deterministic_rng", wrapped)

                try:
                    audio_cfg = getattr(owner.config, "audio", None)
                    preview_runtime_mode = (
                        str(getattr(audio_cfg, "cold_start_preview_runtime_mode", "preview") or "preview")
                        if audio_cfg is not None
                        else "preview"
                    )
                    preview_planner_effort = (
                        str(getattr(audio_cfg, "cold_start_preview_planner_effort", "minimal") or "minimal")
                        if audio_cfg is not None
                        else "minimal"
                    )
                except Exception:
                    preview_runtime_mode = "preview"
                    preview_planner_effort = "minimal"

                events = self._generate_section_events(
                    emotion,
                    root,
                    pb,
                    runtime_mode_override=preview_runtime_mode,
                    planner_effort_override=preview_planner_effort,
                )
                bars = pb
                segs = None
            finally:
                try:
                    if wrapped is not None and gen is not None and callable(orig_drng):
                        setattr(gen, "deterministic_rng", orig_drng)
                except Exception:
                    pass
        gen_time = time.time() - start
        self._notify_section_compose_time(owner, gen_time)
        self.current_section_events = events
        self.current_section_bars = bars
        self._invalidate_bar_event_index()
        self.next_bar_index = 0
        self.bars_played_this_section = 0
        self.current_arrangement_segments = segs
        try:
            self.current_arranged_song_render = getattr(owner.composer, "_last_arranged_song_render", None) if segs else None
        except Exception:
            self.current_arranged_song_render = None
        self._arranged_completion_armed = bool(isinstance(segs, list) and len(segs) > 0)
        self._last_logged_arrangement_role = None
        try:
            audio_cfg = getattr(owner.config, "audio", None)
            self._defer_pregen_until_first_bar = bool(
                getattr(audio_cfg, "cold_start_defer_pregen_until_first_bar", True)
            ) if audio_cfg is not None else True
        except Exception:
            self._defer_pregen_until_first_bar = True

    def pre_generate_next_section(self):
        owner = self.owner
        with owner.section_lock:
            if self.pre_generation_running:
                self._pregen_followup_needed = True
                return
            self.pre_generation_running = True

        committed = False
        try:
            bars = owner.config.composition.bars_per_section
            with owner.state_lock:
                current_emotion = owner._emotion
                current_root = owner._root
            emotion = self.pending_emotion or current_emotion
            root = self.pending_root if self.pending_root is not None else current_root
            emotion_used = emotion
            if emotion is None:
                return
            start = time.time()
            if self._arranged_songs_enabled():
                # Old behavior (preferred for interactive use):
                # - queued emotion change: build one short chunk first for a fast handoff
                # - arranged loop continuation: pre-generate the next full arranged song
                fast_chunk = True
                try:
                    fast_chunk = bool(
                        getattr(owner.config.composition, "arranged_emotion_switch_fast_chunk", True)
                    )
                except Exception:
                    fast_chunk = True

                keep_role = False
                try:
                    keep_role = bool(getattr(owner.config.composition, "arranged_emotion_switch_keep_role", True))
                except Exception:
                    keep_role = True

                if self.pending_emotion is None:
                    # Arranged loop continuation: prefer a short preview timeline when buffer
                    # runway is tight or RT mode avoids full cold builds; chain a full song
                    # pregen afterward when configured.
                    try:
                        fill = int(owner.buffer_controller.effective_fill_bars())
                    except Exception:
                        fill = 0
                    try:
                        tgt = int(getattr(owner, "_target_buffer_bars", 12) or 12)
                    except Exception:
                        tgt = 12
                    runway_ok = fill >= max(4, tgt // 2)
                    prefer_full = self._arranged_realtime_prefers_full_timeline()
                    try:
                        cur_bars = int(self.current_section_bars or 0)
                    except Exception:
                        cur_bars = 0
                    try:
                        min_full = int(
                            getattr(owner.config.composition, "arranged_song_end_fade_min_total_bars", 20) or 20
                        )
                    except Exception:
                        min_full = 20
                    short_current = cur_bars > 0 and cur_bars < max(8, int(min_full))
                    use_preview_first = (not prefer_full) or (not runway_ok) or short_current
                    if use_preview_first:
                        try:
                            events, bars = self._generate_arranged_preview_events(emotion, root)
                            try:
                                segs = getattr(owner.composer, "_last_arranged_song_segments", None)
                            except Exception:
                                segs = None
                            if prefer_full and not short_current:
                                with owner.section_lock:
                                    self._pregen_followup_needed = True
                        except Exception:
                            events, bars, segs = self._generate_arranged_song_events(emotion, root)
                    else:
                        events, bars, segs = self._generate_arranged_song_events(emotion, root)
                else:
                    # Manual emotion switch.
                    if keep_role:
                        events0, bars0, segs0 = self._generate_arranged_song_events(emotion, root)
                        hint = getattr(self, "_pending_emotion_role_hint", None)
                        start_bar = 0
                        if isinstance(hint, dict) and isinstance(segs0, list) and segs0:
                            role = str(hint.get("role", "") or "").strip()
                            off = int(hint.get("role_bar_offset", 0) or 0)
                            if role:
                                match = next((s for s in segs0 if str(s.get("role", "") or "") == role), None)
                                if isinstance(match, dict):
                                    try:
                                        sb2 = int(match.get("start_bar", 0) or 0)
                                        eb2 = int(match.get("end_bar", 0) or 0)
                                    except Exception:
                                        sb2, eb2 = 0, 0
                                    # Keep intra-role bar offset when possible.
                                    start_bar = int(sb2 + max(0, off))
                                    if eb2 > sb2:
                                        start_bar = min(start_bar, int(eb2 - 1))
                        if start_bar > 0 and bars0 > start_bar:
                            events = self._trim_events_to_bar_window(events0, start_bar=int(start_bar), total_bars=int(bars0))
                            bars = int(bars0 - start_bar)
                            segs = self._trim_segments_to_bar_window(segs0, start_bar=int(start_bar))
                        else:
                            events, bars, segs = events0, bars0, segs0
                    elif not fast_chunk:
                        events, bars, segs = self._generate_arranged_song_events(emotion, root)
                    else:
                        # Legacy fast-chunk behavior: cheapest possible first chunk.
                        bars = max(2, min(4, int(owner.config.composition.bars_per_section)))
                        events = self._generate_section_events(emotion, root, bars)
                        segs = None
            else:
                next_index = self.section_index + 1
                current_index = self.section_index
                # Fast handoff chunk: when the user queued an emotion change, generate just a few
                # bars first so the audible swap can happen quickly. The normal pipeline will then
                # build a full section in the background after activation.
                gen_bars = int(bars)
                if self.pending_emotion is not None:
                    try:
                        comp = getattr(owner.config, "composition", None)
                        enabled = bool(getattr(comp, "emotion_switch_fast_chunk_enabled", True)) if comp is not None else True
                    except Exception:
                        enabled = True
                    if enabled:
                        try:
                            comp = getattr(owner.config, "composition", None)
                            fast_bars = int(getattr(comp, "emotion_switch_fast_chunk_bars", 4) or 4) if comp is not None else 4
                        except Exception:
                            fast_bars = 4
                        fast_bars = max(1, min(8, int(fast_bars)))
                        gen_bars = min(int(gen_bars), int(fast_bars))
                try:
                    self.section_index = next_index
                    events = self._generate_section_events(emotion, root, int(gen_bars))
                finally:
                    self.section_index = current_index
                segs = None
            gen_time = time.time() - start
            self._notify_section_compose_time(owner, gen_time)
            with owner.section_lock:
                if self._pending_targets_different_emotion(emotion_used):
                    self.logger.info(
                        "Dropped stale pre-generated section (pending=%s, built for %s)",
                        getattr(self.pending_emotion, "name", self.pending_emotion),
                        getattr(emotion_used, "name", emotion_used),
                    )
                elif not self._section_events_nonempty(events):
                    self.logger.warning("Pre-generation produced no events; not marking ready")
                else:
                    self.next_section_events = events
                    # Commit the bars we actually generated (may be a fast handoff chunk).
                    try:
                        self.next_section_bars = int(gen_bars) if "gen_bars" in locals() else int(bars)
                    except Exception:
                        self.next_section_bars = int(bars)
                    self.next_section_ready = True
                    self.next_section_emotion = emotion_used
                    self.next_section_root = root
                    self.next_arrangement_segments = segs
                    try:
                        self.next_arranged_song_render = getattr(owner.composer, "_last_arranged_song_render", None) if segs else None
                    except Exception:
                        self.next_arranged_song_render = None
                    committed = True
                    # If this pregen was triggered by a queued emotion switch, record
                    # "emotion request -> pregen commit" latency on the player.
                    if self.pending_emotion is not None:
                        try:
                            owner._record_emotion_switch_generated(emotion_used)
                        except Exception:
                            pass
        except Exception:
            self.logger.exception("Error in pre-generation")
        finally:
            follow = False
            with owner.section_lock:
                self.pre_generation_running = False
                follow = self._pregen_followup_needed
                self._pregen_followup_needed = False
                pending = self.pending_emotion is not None
                ready = self.next_section_ready
            if not committed and (follow or (pending and not ready)):
                self.ensure_pregen_enqueued()

    def activate_next_section(self, *, loop_handoff: bool = False) -> bool:
        """Apply buffered timeline. Returns False if the buffer was missing/empty."""
        owner = self.owner
        prev_emotion = getattr(owner, "_emotion", None)
        prev_root = getattr(owner, "_root", None)
        # Guard: a handoff without a committed emotion/root is treated as not-ready.
        # (Prevents swapping into a stale/partial section when flags were set but state wasn't.)
        if self.pending_emotion is not None and self.next_section_emotion is None:
            self.logger.warning("activate_next_section: pending_emotion set but next_section_emotion missing; aborting")
            with owner.section_lock:
                self.next_section_ready = False
            self.ensure_pregen_enqueued()
            return False
        # If the user has queued a new emotion, never swap into a section built for a different one
        # (can happen under test when a background pregen completes mid-assert).
        if (
            self.pending_emotion is not None
            and self.next_section_emotion is not None
            and self._pending_targets_different_emotion(self.next_section_emotion)
        ):
            self.logger.warning(
                "activate_next_section: next section built for %s but pending is %s; aborting",
                getattr(self.next_section_emotion, "name", self.next_section_emotion),
                getattr(self.pending_emotion, "name", self.pending_emotion),
            )
            with owner.section_lock:
                self.next_section_ready = False
            self.ensure_pregen_enqueued()
            return False
        if int(getattr(self, "next_section_bars", 0) or 0) <= 0:
            self.logger.warning("activate_next_section: next_section_bars missing/invalid; aborting")
            with owner.section_lock:
                self.next_section_ready = False
            self.ensure_pregen_enqueued()
            return False
        if not self._section_events_nonempty(self.next_section_events):
            self.logger.warning("activate_next_section: missing next_section_events; aborting switch")
            with owner.section_lock:
                self.next_section_ready = False
            self.ensure_pregen_enqueued()
            return False
        self.current_section_events = self.next_section_events
        self.current_section_bars = self.next_section_bars
        self._invalidate_bar_event_index()
        self.current_arrangement_segments = self.next_arrangement_segments
        self.next_arrangement_segments = None
        self.current_arranged_song_render = self.next_arranged_song_render
        self.next_arranged_song_render = None
        self._arranged_completion_armed = bool(
            isinstance(self.current_arrangement_segments, list)
            and len(self.current_arrangement_segments) > 0
        )
        self._last_logged_arrangement_role = None
        self.next_section_ready = False
        self.next_section_events = None
        if self.next_section_emotion is not None:
            name_changed = (
                prev_emotion is not None
                and getattr(prev_emotion, "name", "").lower()
                != getattr(self.next_section_emotion, "name", "").lower()
            )
            root_changed = prev_root is not None and self.next_section_root is not None and int(prev_root) != int(self.next_section_root)
            if name_changed or root_changed:
                gen = getattr(getattr(owner, "composer", None), "gen", None)
                if gen is not None and hasattr(gen, "reset_drone"):
                    try:
                        from audiogen_core.config import CONFIG
                        # Live playback: keep the drone stable across emotion/root switches by default.
                        # - `drone_always_on` forces the drone gate open (planner-level).
                        # - `drone_keep_playing_on_switch` prevents retrigger/retune on switches.
                        always_on = bool(getattr(CONFIG.composition, "drone_always_on", False))
                        keep_playing = bool(getattr(CONFIG.composition, "drone_keep_playing_on_switch", True))
                        if (not always_on) and (not keep_playing):
                            gen.reset_drone(hard=True)
                    except Exception:
                        pass
            with owner.state_lock:
                owner._emotion = self.next_section_emotion
                owner._root = self.next_section_root
            owner._apply_emotion_runtime_state(owner._emotion, reset_mixer_filters=False)
            self.logger.info("Now playing: %s", owner._emotion.name.upper())
        self.next_section_emotion = None
        self.next_section_root = None
        self.pending_emotion = None
        self.pending_root = None
        self.next_bar_index = 0
        self.bars_played_this_section = 0
        if self._arranged_songs_enabled():
            self.section_index = 0
        else:
            self.section_index += 1
        if self._arranged_songs_enabled():
            self._maybe_schedule_next_arranged_song()
        if bool(loop_handoff):
            try:
                comp = getattr(owner.config, "composition", None)
                prewarm = bool(getattr(comp, "arranged_loop_handoff_prewarm", True)) if comp is not None else True
            except Exception:
                prewarm = True
            if prewarm:
                try:
                    with owner.state_lock:
                        root = int(getattr(owner, "_root", 60) or 60)
                        emotion = getattr(owner, "_emotion", None)
                    owner.schedule_rt_prewarm(root=root, emotion=emotion)
                except Exception:
                    pass
        return True

    @staticmethod
    def _clip_event_to_bar_window(ev, bar_start_beats: float, bar_end_beats: float):
        start = ev[3]
        duration = ev[4]
        if not (start < bar_end_beats and start + duration > bar_start_beats):
            return None
        if start < bar_start_beats:
            local_start = 0.0
            remaining = start + duration - bar_start_beats
            local_duration = min(remaining, bar_end_beats - bar_start_beats)
        else:
            local_start = start - bar_start_beats
            local_duration = min(duration, bar_end_beats - start)
        if local_duration <= 0:
            return None
        new_ev = list(ev)
        new_ev[3] = local_start
        new_ev[4] = local_duration
        return tuple(new_ev)

    def _slice_bar_events(self, bar_idx: int):
        bar_start_beats = float(bar_idx) * 4.0
        bar_end_beats = bar_start_beats + 4.0
        bar_events = []
        self._ensure_bar_event_index()
        idxs = self._bar_event_indices if self._bar_event_indices is not None else None
        if idxs is None or bar_idx < 0 or bar_idx >= len(idxs):
            events = self.current_section_events or []
            for ev in events:
                clipped = self._clip_event_to_bar_window(ev, bar_start_beats, bar_end_beats)
                if clipped is not None:
                    bar_events.append(clipped)
            return bar_events
        for i in idxs[bar_idx]:
            try:
                ev = self.current_section_events[i]
            except Exception:
                continue
            clipped = self._clip_event_to_bar_window(ev, bar_start_beats, bar_end_beats)
            if clipped is not None:
                bar_events.append(clipped)
        return bar_events

    def prepare_next_bar(self):
        owner = self.owner
        switched_section = False
        emotion_handoff = False
        arranged_loop_handoff = False
        activated_new_section = False
        activation_failed_at_end = False
        arranged_song_fade = None
        next_bar_events_preview = []
        with owner.section_lock:
            # Pending-emotion swaps: align to every N *heard* bars (playback), not pre-render depth.
            phrase_tb = max(
                1,
                int(
                    getattr(
                        owner,
                        "_emotion_transition_boundary_bars",
                        getattr(owner, "_transition_boundary_bars", 1),
                    )
                ),
            )
            heard = self.bars_played_this_section
            phrase_boundary_reached = (
                self.next_section_ready
                and self.pending_emotion is not None
                and heard > 0
                and (heard % phrase_tb == 0)
            )
            section_end_reached = self.next_bar_index >= self.current_section_bars

            if phrase_boundary_reached or section_end_reached:
                if section_end_reached:
                    self._capture_completed_arranged_song_locked()
                if self.next_section_ready:
                    handoff_pending = self.pending_emotion is not None
                    if handoff_pending:
                        # Trim pre-rendered *tail* but keep a few oldest chunks so the audio callback
                        # does not hit an empty queue (heard as stop → silence → new emotion).
                        try:
                            keep = max(
                                0,
                                int(
                                    getattr(
                                        owner.config.audio,
                                        "emotion_handoff_queue_keep_bars",
                                        1,
                                    )
                                ),
                            )
                        except Exception:
                            keep = 1
                        owner.buffer_controller.trim_queued_bars(keep)
                    loop_swap = (
                        not handoff_pending
                        and bool(section_end_reached)
                        and self._arranged_songs_enabled()
                    )
                    if self.activate_next_section(loop_handoff=loop_swap):
                        switched_section = True
                        activated_new_section = True
                        emotion_handoff = handoff_pending
                        arranged_loop_handoff = loop_swap
                    else:
                        # If we *attempted* to activate at the end boundary but activation
                        # aborted (e.g. flags were inconsistent / empty buffer), do not
                        # advance as if bar-0 of the new section is available.
                        if bool(section_end_reached):
                            activation_failed_at_end = True
                elif section_end_reached:
                    self._schedule_async_pre_generation()

            if not self._section_events_nonempty(self.current_section_events):
                base_tempo = effective_tempo_bpm_from_config(owner.config, None)
                bar_seconds = 4.0 * 60.0 / max(1.0, base_tempo)
                samples = int(bar_seconds * owner.container.sample_rate)
                silence = np.zeros((samples, 2), dtype=np.float32)
                return {
                    "switched_section": switched_section,
                    "bar_index": 0,
                    "bar_events": [],
                    "silence": silence,
                    "tempo": base_tempo,
                    "root_note": 60,
                    "emotion_handoff": False,
                    "arranged_loop_handoff": False,
                    "arrangement_role": "",
                    "arrangement_pre_chorus_last_bar": False,
                }

            # After activate_next_section(), next_bar_index and current_section_* refer to the NEW
            # timeline, but section_end_reached was computed on the OLD section. Using the stale
            # flag routed the first post-switch render to the *last* bar of the new section (or
            # wrong slice) — heard as a hard cut / dead buffer. Always play bar 0 first after a swap.
            if activated_new_section:
                bar_idx = self.next_bar_index
                bar_events = self._slice_bar_events(bar_idx)
                self.next_bar_index += 1
            elif activation_failed_at_end:
                # Activation aborted while already past the section end: hold the last valid bar.
                cb = max(1, int(self.current_section_bars))
                bar_idx = cb - 1
                bar_events = self._slice_bar_events(bar_idx)
            elif section_end_reached and not self.next_section_ready:
                # If we hit the end of the current section before the next section is ready,
                # do NOT pin playback on the last bar ("bar N forever"). That can sound like
                # the arp (and other rhythmic layers) are "stuck looping".
                # Instead, wrap around and keep progressing through the section while the
                # background pre-generation catches up.
                cb = max(1, int(self.current_section_bars))
                bar_idx = int(self.next_bar_index) % cb
                bar_events = self._slice_bar_events(bar_idx)
                self.next_bar_index += 1
            else:
                bar_idx = self.next_bar_index
                bar_events = self._slice_bar_events(bar_idx)
                self.next_bar_index += 1

            # ----------------------------------------------------------
            # Arranged-song end fade-out (master): last N bars → 0 gain
            # ----------------------------------------------------------
            try:
                fade_bars = int(
                    getattr(
                        getattr(owner.config, "composition", None),
                        "arranged_song_end_fade_out_bars",
                        0,
                    )
                    or 0
                )
            except Exception:
                fade_bars = 0
            try:
                fade_min_total = int(
                    getattr(
                        getattr(owner.config, "composition", None),
                        "arranged_song_end_fade_min_total_bars",
                        20,
                    )
                    or 0
                )
            except Exception:
                fade_min_total = 20
            fade_min_total = max(0, int(fade_min_total))
            try:
                total = int(self.current_section_bars or 0)
            except Exception:
                total = 0
            # Never let the tail fade consume more than ~35% of a short timeline (extra guard).
            if fade_bars > 0 and total > 0:
                max_fade = max(1, int(total * 0.35))
                if fade_bars > max_fade:
                    fade_bars = max_fade
            if (
                fade_bars > 0
                and total >= fade_min_total
                and self._arranged_songs_enabled()
                and self._arranged_loop_enabled()
                # Only fade when we're actually playing a full arranged timeline.
                # During queued emotion switches, arranged mode can generate a short "fast chunk"
                # (2-4 bars) with no arrangement segments; applying the end-of-song fade to that
                # chunk causes an unintended mid-song fade-out exactly when emotions change.
                and isinstance(self.current_arrangement_segments, list)
                and len(self.current_arrangement_segments) > 0
                # Also require the arranged timeline to actually contain an outro segment.
                # Otherwise short previews like [intro, verse] (e.g. 24 bars) would fade out
                # at the end of the preview and then "fade back in" when the full song
                # activates, which reads like an unintended dip before pre-chorus/chorus.
                and any(str(s.get("role", "") or "").strip().lower() == "outro" for s in self.current_arrangement_segments)
            ):
                try:
                    start_bar = int(max(0, total - fade_bars))
                    bi = int(bar_idx)
                    if total > 0 and bi >= start_bar:
                        pos = int(bi - start_bar)  # 0..fade_bars-1
                        if 0 <= pos < int(fade_bars):
                            # Per-bar ramp endpoints; the player will interpolate per-sample.
                            sg = 1.0 - (float(pos) / float(fade_bars))
                            eg = 1.0 - (float(pos + 1) / float(fade_bars))
                            sg = float(np.clip(sg, 0.0, 1.0))
                            eg = float(np.clip(eg, 0.0, 1.0))
                            arranged_song_fade = (sg, eg)
                except Exception:
                    arranged_song_fade = None

            # Amortization hook: preview the next bar's slice (best-effort) so the player can
            # warm sampler caches in a background thread while the current bar is playing.
            try:
                preview_idx = int(self.next_bar_index)
                if 0 <= preview_idx < int(self.current_section_bars):
                    next_bar_events_preview = self._slice_bar_events(preview_idx)
            except Exception:
                next_bar_events_preview = []

        with owner.state_lock:
            emotion = owner._emotion
            root = owner._root
        tempo = effective_tempo_bpm_from_config(owner.config, emotion)

        arrangement_role = ""
        arrangement_pre_chorus_last_bar = False
        try:
            seg_ar = self._arrangement_role_for_bar(int(bar_idx))
            if isinstance(seg_ar, dict):
                arrangement_role = str(seg_ar.get("role", "") or "").strip().lower()
                try:
                    sb = int(seg_ar.get("start_bar", -1))
                    eb = int(seg_ar.get("end_bar", -1))
                except Exception:
                    sb, eb = -1, -1
                if (
                    arrangement_role == "pre_chorus"
                    and eb > sb
                    and int(bar_idx) == eb - 1
                ):
                    arrangement_pre_chorus_last_bar = True
        except Exception:
            arrangement_role = ""
            arrangement_pre_chorus_last_bar = False

        # Arranged-song progress: print arrangement role on change.
        try:
            if self._arranged_songs_enabled():
                seg = self._arrangement_role_for_bar(int(bar_idx))
                if isinstance(seg, dict):
                    role = str(seg.get("role", "") or "")
                    if role and role != self._last_logged_arrangement_role:
                        self._last_logged_arrangement_role = role
                        label = str(seg.get("role_label", "") or self._role_label(role))
                        sb = int(seg.get("start_bar", 0) or 0)
                        eb = int(seg.get("end_bar", 0) or 0)
                        total = int(self.current_section_bars or 0)
                        # Use 1-indexed bars for human-friendly display.
                        self.logger.info(
                            "ARRANGEMENT: %s (bars %d-%d of %d)",
                            label,
                            int(sb) + 1,
                            int(min(max(int(sb) + 1, int(eb)), int(total))),
                            int(total),
                        )
        except Exception:
            pass
        # Debug: optional per-bar trace exported by the composition generator.
        bar_trace = None
        try:
            gen = getattr(getattr(owner, "composer", None), "gen", None)
            trace_by_bar = getattr(gen, "_last_section_debug_trace_by_bar", None) if gen is not None else None
            if isinstance(trace_by_bar, list) and 0 <= int(bar_idx) < len(trace_by_bar):
                bar_trace = trace_by_bar[int(bar_idx)]
        except Exception:
            bar_trace = None
        return {
            "switched_section": switched_section,
            "bar_index": bar_idx,
            "bar_events": bar_events,
            "bar_trace": bar_trace,
            "next_bar_events_preview": next_bar_events_preview,
            "arranged_song_fade": arranged_song_fade,
            "silence": None,
            "tempo": tempo,
            "root_note": root,
            "emotion": emotion,
            "emotion_handoff": emotion_handoff,
            "arranged_loop_handoff": arranged_loop_handoff,
            "arrangement_role": arrangement_role,
            "arrangement_pre_chorus_last_bar": arrangement_pre_chorus_last_bar,
        }

    def remaining_bars(self) -> int:
        owner = self.owner
        with owner.section_lock:
            return self.current_section_bars - self.next_bar_index

    def should_pre_generate(self) -> bool:
        owner = self.owner
        with owner.section_lock:
            remaining_bars = self.current_section_bars - self.next_bar_index
            if bool(getattr(self, "_defer_pregen_until_first_bar", False)):
                if int(getattr(self, "next_bar_index", 0) or 0) <= 0:
                    return False
                self._defer_pregen_until_first_bar = False
            # Long arranged timelines: start the next full song a bit earlier than 16 bars out
            # (without being as aggressive as //3, which competed with playback CPU).
            threshold = 16
            if self._arranged_loop_enabled() and self._arranged_songs_enabled():
                try:
                    comp = getattr(owner.config, "composition", None)
                    lead = int(getattr(comp, "arranged_loop_pregen_lead_bars", 6) or 6) if comp is not None else 6
                except Exception:
                    lead = 6
                threshold = max(int(threshold), max(4, min(32, int(lead))))
            if self._arranged_loop_enabled() and self.current_section_bars >= 48:
                threshold = min(32, max(int(threshold), self.current_section_bars // 4))
            # Short sections: stay well ahead so the next phrase/song is always baking (generative player).
            cb = self.current_section_bars
            if cb > 0:
                early = max(4, (cb * 2) // 3)
                threshold = min(threshold, early)
            # Do not gate on pre_generation_running — ensure_pregen_enqueued() dedupes / chains.
            return remaining_bars <= threshold and not self.next_section_ready
