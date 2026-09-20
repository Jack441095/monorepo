# ai/markov/melody/note_generator/_core.py
"""NoteGenerator core: initialization, small helpers, and generate_phrase."""
import random
import logging
from typing import Dict, List, Optional, Tuple

from audiogen_core.constants import DURATIONS
from data.emotion_anchors import anchors_for_emotion
from data.emotion_melody_priors import emotion_melody_prior_for
from ..tension_model import TensionModelMixin
from ._rhythm import NoteGeneratorRhythmMixin
from ._interval import NoteGeneratorIntervalMixin

logger = logging.getLogger(__name__)

from pathlib import Path
try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

if HAS_TORCH:
    class PhraseGRU(nn.Module):
        def __init__(self, num_emotions: int, pitch_emb_dim: int = 16, dur_emb_dim: int = 16, emotion_emb_dim: int = 8, hidden_size: int = 64, num_layers: int = 2):
            super().__init__()
            self.pitch_embed = nn.Embedding(13, pitch_emb_dim)
            self.dur_embed = nn.Embedding(65, dur_emb_dim)
            self.emotion_embed = nn.Embedding(num_emotions, emotion_emb_dim)

            input_size = pitch_emb_dim + dur_emb_dim + emotion_emb_dim
            self.gru = nn.GRU(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=0.1 if num_layers > 1 else 0.0
            )
            self.pitch_head = nn.Linear(hidden_size, 13)
            self.dur_head = nn.Linear(hidden_size, 65)

        def forward(self, x_pitch: torch.Tensor, x_dur: torch.Tensor, emotion_idx: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            pitch_emb = self.pitch_embed(x_pitch)
            dur_emb = self.dur_embed(x_dur)
            emo_emb = self.emotion_embed(emotion_idx)
            emo_emb_seq = emo_emb.unsqueeze(1).repeat(1, x_pitch.size(1), 1)
            x = torch.cat([pitch_emb, dur_emb, emo_emb_seq], dim=-1)
            out, _ = self.gru(x)
            last_step = out[:, -1, :]
            pitch_logits = self.pitch_head(last_step)
            dur_logits = self.dur_head(last_step)
            return pitch_logits, dur_logits


class NoteGenerator(NoteGeneratorRhythmMixin, NoteGeneratorIntervalMixin, TensionModelMixin):
    """Generates a sequence of notes for a phrase using Markov models and biases."""

    @staticmethod
    def _sanitize_emotion_intensity(value: float) -> float:
        try:
            return max(1e-6, float(value))
        except Exception:
            return 1.0

    @staticmethod
    def _sanitize_max_repetitions(value: int) -> int:
        try:
            return max(1, int(value))
        except Exception:
            return 2

    def __init__(self,
                 markov_models,
                 motif_manager,
                 phrase_planner,
                 rng=random,
                 stepwise_boost_base: float = 5.0,
                 chord_tone_multiplier: float = 15.0,
                 downbeat_chord_multiplier: float = 20.0,
                 max_repetitions: int = 2,
                 repeat_penalty: float = 0.3,
                 emotion_intensity: float = 1.0):
        self.markov = markov_models
        self.motif = motif_manager
        self.planner = phrase_planner
        self.rng = rng
        self.stepwise_boost_base = stepwise_boost_base
        self.chord_tone_multiplier = chord_tone_multiplier
        self.downbeat_chord_multiplier = downbeat_chord_multiplier
        self.max_repetitions = self._sanitize_max_repetitions(max_repetitions)
        self.repeat_penalty = repeat_penalty
        self.emotion_intensity = self._sanitize_emotion_intensity(emotion_intensity)
        self._neural_model = None
        self._neural_emotions = []
        self._emotion_to_idx = {}

    def _degree_to_midi(self, degree: int, root: int, scale_intervals: List[int]) -> int:
        tonic = root - scale_intervals[0]
        while tonic < 48:
            tonic += 12
        while tonic > 72:
            tonic -= 12
        return tonic + scale_intervals[degree % len(scale_intervals)]

    def _bias_rhythm(self, probs: Dict[float, float], emotion=None,
                     on_downbeat: bool = False) -> Dict[float, float]:
        """Apply rhythm biases.  Pass on_downbeat=True on bar/strong-beat boundaries.

        Replaces the old _bias_rhythm_general / _bias_downbeat_durations pair
        which shared ~90 % of their logic.
        """
        if on_downbeat:
            bias_factors = {0.25: 0.05, 0.5: 0.3, 1.0: 2.0, 2.0: 3.0, 4.0: 4.0}
        else:
            bias_factors = {0.25: 0.05, 0.5: 0.5, 1.0: 2.0, 2.0: 3.0, 4.0: 4.0}
            if emotion is not None:
                name = str(getattr(emotion, "name", "") or "").lower()
                if 'sad' in name or 'grief' in name:
                    bias_factors[1.0] *= 2.0
                    bias_factors[2.0] *= 2.0
                    bias_factors[4.0] *= 3.0
                    bias_factors[0.25] *= 0.1
                elif 'joy' in name or 'excitement' in name:
                    bias_factors[0.5] = 1.2
                    bias_factors[0.25] = 0.3
                elif 'calm' in name:
                    bias_factors[0.5] = 0.5
                    bias_factors[1.0] = 2.0
        if emotion is not None:
            prior = emotion_melody_prior_for(str(getattr(emotion, "name", "") or ""))
            for dur in list(bias_factors.keys()):
                try:
                    d = abs(float(dur))
                except Exception:
                    d = 1.0
                if d <= 0.5:
                    bias_factors[dur] *= prior.short_rhythm_mult
                elif d >= 2.0:
                    bias_factors[dur] *= prior.long_rhythm_mult
                else:
                    bias_factors[dur] *= prior.medium_rhythm_mult
            # v012c: admiration still trends short-heavy in diagnostics even after
            # prior tuning; give it a direct long-duration nudge at the sampling layer.
            try:
                en = str(getattr(emotion, "name", "") or "").strip().lower()
            except Exception:
                en = ""
            if en == "admiration":
                # Encourage actual long durations (>=2.0) and suppress very short taps.
                for k in (2.0, 4.0):
                    if k in bias_factors:
                        bias_factors[k] *= 1.55
                    if -k in bias_factors:
                        bias_factors[-k] *= 1.55
                for k in (0.25, 0.5):
                    if k in bias_factors:
                        bias_factors[k] *= 0.72
                    if -k in bias_factors:
                        bias_factors[-k] *= 0.72
        for dur in list(probs.keys()):
            bf = bias_factors.get(dur, None)
            if bf is None:
                bf = bias_factors.get(abs(float(dur)), 1.0)
            probs[dur] *= bf
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}
        return probs

    # Kept as thin aliases so any external callers still work.
    def _bias_rhythm_general(self, probs, emotion=None):
        return self._bias_rhythm(probs, emotion, on_downbeat=False)

    def _bias_downbeat_durations(self, probs, emotion=None):
        return self._bias_rhythm(probs, emotion, on_downbeat=True)

    def _apply_voice_leading_penalty(self,
                                     interval_probs: Dict[int, float],
                                     melody: List[Tuple[int, float]],
                                     current_beat: float,
                                     bass_notes: Optional[List[int]],
                                     beats_per_bar: float = 4.0) -> None:
        if not bass_notes or len(melody) == 0:
            return
        beat_idx = int(current_beat // 0.25)
        if beat_idx >= len(bass_notes):
            return
        current_degree = melody[-1][0]
        for interval in list(interval_probs.keys()):
            if current_degree <= 1 and interval < 0:
                interval_probs[interval] *= 0.5
            if current_degree >= 5 and interval > 0:
                interval_probs[interval] *= 0.7
            if abs(interval) > 2:
                interval_probs[interval] *= 0.8
        total = sum(interval_probs.values())
        if total > 0:
            for k in interval_probs:
                interval_probs[k] /= total

    def _compute_initial_duration(self, start_beat: float, beats_per_bar: float,
                                  emotion, temperature: float, plan=None) -> float:
        rhythm_probs = self.markov.get_rhythm_probs([], temperature)
        if rhythm_probs:
            if start_beat % beats_per_bar < 1e-6:
                rhythm_probs = self._bias_downbeat_durations(rhythm_probs, emotion)
            rhythm_probs = self._apply_phrase_rhythm_bias(
                rhythm_probs,
                plan=plan,
                phrase_pos=0.0,
                current_beat=start_beat,
                beats_per_bar=beats_per_bar,
            )
            ks = sorted(rhythm_probs.keys(), key=repr)
            dur = self.rng.choices(ks, weights=[rhythm_probs[k] for k in ks])[0]
        else:
            dur = DURATIONS[0]
        return dur

    @staticmethod
    def _duration_interval_compat(interval_probs: Dict[int, float], dur: float) -> float:
        """Weighted compatibility of a candidate duration with interval marginal (0..1)."""
        if not interval_probs:
            return 0.5
        short = float(dur) <= 0.5 + 1e-9
        long = float(dur) >= 2.0 - 1e-9
        num = 0.0
        den = 0.0
        for iv, p in interval_probs.items():
            try:
                pf = float(p)
            except Exception:
                continue
            if pf <= 0.0:
                continue
            den += pf
            try:
                a = abs(int(iv))
            except Exception:
                a = 0
            if short:
                w = 1.0 if a <= 1 else (0.25 if a >= 4 else 0.65)
            elif long:
                w = 1.0 if a >= 2 else (0.35 if a == 0 else 0.65)
            else:
                w = 0.85
            num += pf * w
        return float(num / den) if den > 1e-12 else 0.5

    @staticmethod
    def _last_voiced_degree(melody: List[Tuple[int, float]], start_degree: int) -> int:
        for d, _ in reversed(melody):
            try:
                if isinstance(d, int) and int(d) >= 0:
                    return int(d) % 7
            except Exception:
                continue
        return int(start_degree) % 7

    @staticmethod
    def _fit_duration_to_phrase_budget(
        dur: float,
        *,
        current_beat: float,
        phrase_end_beat: Optional[float],
        notes_done: int,
        num_notes: int,
        is_last_note: bool,
    ) -> float:
        """Prevent a final note from absorbing an entire under-filled phrase."""

        try:
            out = float(dur)
        except Exception:
            out = float(DURATIONS[0])
        if out <= 1e-6:
            out = float(DURATIONS[0])
        if phrase_end_beat is None:
            return out
        try:
            remaining = max(0.0, float(phrase_end_beat) - float(current_beat))
        except Exception:
            return out
        if remaining <= 1e-6:
            return float(DURATIONS[0])

        try:
            from audiogen_core.config import CONFIG

            final_cap = float(getattr(CONFIG.composition, "melody_phrase_final_duration_cap", 2.0) or 2.0)
            note_cap = float(getattr(CONFIG.composition, "melody_phrase_note_duration_cap", 2.5) or 2.5)
        except Exception:
            final_cap = 2.0
            note_cap = 2.5
        final_cap = max(0.5, min(4.0, float(final_cap)))
        note_cap = max(0.5, min(4.0, float(note_cap)))

        notes_left_including_this = max(1, int(num_notes) - int(notes_done))
        avg_remaining = float(remaining) / float(notes_left_including_this)
        if bool(is_last_note):
            max_dur = min(float(remaining), max(float(final_cap), min(2.0, float(avg_remaining) * 1.35)))
            return max(float(DURATIONS[0]), min(float(out), float(max_dur)))

        notes_after = max(1, int(notes_left_including_this) - 1)
        max_dur = min(float(remaining), max(float(DURATIONS[0]), min(float(note_cap), float(avg_remaining) * 1.75)))
        min_dur = 0.0
        if avg_remaining >= 1.5 and notes_after <= 4:
            min_dur = min(1.0, float(avg_remaining) * 0.45)
        out = min(float(out), float(max_dur))
        if min_dur > 1e-9:
            out = max(float(out), float(min_dur))
        return max(float(DURATIONS[0]), min(float(out), float(remaining)))

    @staticmethod
    def _last_voiced_note_duration(melody: List[Tuple[int, float]]) -> Optional[float]:
        """Duration of the last voiced note (ignores rest tokens)."""
        for d, dur in reversed(melody):
            try:
                if isinstance(d, int) and int(d) >= 0:
                    return float(dur)
            except Exception:
                continue
        return None
    def _load_neural_model(self) -> bool:
        if not HAS_TORCH:
            return False
        if hasattr(self, "_neural_model") and self._neural_model is not None:
            return True
            
        try:
            root_dir = Path(__file__).resolve().parents[4]
            model_path = root_dir / "training_data" / "active_models" / "phrase_gru.pt"
            if not model_path.exists():
                return False
                
            checkpoint = torch.load(model_path, map_location="cpu")
            config = checkpoint["config"]
            emotions = checkpoint["emotions"]
            state_dict = checkpoint["state_dict"]
            
            model = PhraseGRU(
                num_emotions=config["num_emotions"],
                pitch_emb_dim=config["pitch_emb_dim"],
                dur_emb_dim=config["dur_emb_dim"],
                emotion_emb_dim=config["emotion_emb_dim"],
                hidden_size=config["hidden_size"],
                num_layers=config["num_layers"]
            )
            model.load_state_dict(state_dict)
            model.eval()
            
            self._neural_model = model
            self._neural_emotions = emotions
            self._emotion_to_idx = {name: idx for idx, name in enumerate(emotions)}
            return True
        except Exception as e:
            logger.error(f"Failed to load neural phrase model: {e}")
            self._neural_model = None
            return False

    def _generate_phrase_neural(self,
                                start_degree: int,
                                num_notes: int,
                                plan,
                                temperature: float,
                                emotion,
                                start_beat: float,
                                chords: Optional[List[str]],
                                roots: Optional[List[int]],
                                beats_per_bar: float,
                                chord_weights_per_bar: Optional[List[Dict[int, float]]],
                                beat_positions_out: Optional[List],
                                grid: float,
                                initial_interval_context: Optional[List[int]],
                                initial_rhythm_context: Optional[List[float]],
                                bass_notes: Optional[List[int]],
                                total_beats: int,
                                target_melody_notes: Optional[List[int]],
                                phrase_end_beat: Optional[float] = None,
                                occupied_intervals: Optional[List[Tuple[float, float]]] = None,
                                breath_window_by_bar: Optional[List[float]] = None,
                                bar_intent_by_bar: Optional[List[Dict]] = None,
                                voiced_chords_per_bar: Optional[List[List[int]]] = None) -> Tuple[List[Tuple[int, float]], List[int], List[float]]:
        if num_notes == 0:
            return [], [], []

        scale_iv = list(getattr(emotion, "scale_intervals", []) or [])
        emotion_name = str(getattr(emotion, "name", "") or "")
        emotion_idx = self._emotion_to_idx.get(emotion_name, 0)

        context = []
        if scale_iv and initial_interval_context and initial_rhythm_context:
            curr_deg = start_degree
            degs = [curr_deg]
            for iv in reversed(initial_interval_context):
                curr_deg = curr_deg - iv
                degs.append(curr_deg)
            degs.reverse()
            
            for d, r in zip(degs, initial_rhythm_context):
                p_delta = scale_iv[d % len(scale_iv)]
                ticks = max(1, min(64, int(r * 4)))
                context.append((p_delta, ticks))
                
        if scale_iv:
            init_pitch_delta = scale_iv[start_degree % len(scale_iv)]
        else:
            init_pitch_delta = start_degree % 12
            
        while len(context) < 16:
            context.insert(0, (init_pitch_delta, 4))
            
        context = context[-16:]

        melody = []
        current_beat = start_beat
        
        for note_idx in range(num_notes):
            x_pitch = torch.tensor([[c[0] for c in context]], dtype=torch.long)
            x_dur = torch.tensor([[c[1] for c in context]], dtype=torch.long)
            emo_idx = torch.tensor([emotion_idx], dtype=torch.long)
            
            with torch.no_grad():
                pitch_logits, dur_logits = self._neural_model(x_pitch, x_dur, emo_idx)
                
            pitch_logits = pitch_logits / max(0.1, float(temperature))
            dur_logits = dur_logits / max(0.1, float(temperature))
            
            p_probs = torch.softmax(pitch_logits, dim=-1)
            d_probs = torch.softmax(dur_logits, dim=-1)
            
            p_delta = torch.multinomial(p_probs, 1).item()
            dur_ticks = torch.multinomial(d_probs, 1).item()
            
            if p_delta == 12:
                deg = -1
            else:
                if scale_iv:
                    deg = min(range(len(scale_iv)), key=lambda idx: min(abs(scale_iv[idx] - p_delta), 12 - abs(scale_iv[idx] - p_delta)))
                else:
                    deg = p_delta
                    
            dur_beats = float(dur_ticks) / 4.0
            
            is_last = (note_idx == num_notes - 1)
            dur_beats = self._fit_duration_to_phrase_budget(
                dur_beats,
                current_beat=float(current_beat),
                phrase_end_beat=phrase_end_beat,
                notes_done=note_idx,
                num_notes=num_notes,
                is_last_note=is_last,
            )
            
            melody.append((deg, dur_beats))
            if beat_positions_out is not None:
                beat_positions_out.append(current_beat)
                
            current_beat += dur_beats
            
            context.append((p_delta, max(1, min(64, int(dur_beats * 4)))))
            context = context[-16:]
            
        intervals_so_far = []
        rhythms_so_far = []
        for i in range(len(melody)):
            rhythms_so_far.append(melody[i][1])
            if i > 0:
                d_curr = melody[i][0]
                d_prev = melody[i - 1][0]
                if d_curr >= 0 and d_prev >= 0:
                    intervals_so_far.append(d_curr - d_prev)
                    
        return melody, intervals_so_far, rhythms_so_far

    def generate_phrase(self,
                        start_degree: int,
                        num_notes: int,
                        plan,
                        temperature: float,
                        emotion,
                        start_beat: float,
                        chords: Optional[List[str]],
                        roots: Optional[List[int]],
                        beats_per_bar: float,
                        chord_weights_per_bar: Optional[List[Dict[int, float]]],
                        beat_positions_out: Optional[List],
                        grid: float,
                        initial_interval_context: Optional[List[int]],
                        initial_rhythm_context: Optional[List[float]],
                        bass_notes: Optional[List[int]],
                        total_beats: int,
                        target_melody_notes: Optional[List[int]],
                        phrase_end_beat: Optional[float] = None,
                        occupied_intervals: Optional[List[Tuple[float, float]]] = None,
                        breath_window_by_bar: Optional[List[float]] = None,
                        bar_intent_by_bar: Optional[List[Dict]] = None,
                        voiced_chords_per_bar: Optional[List[List[int]]] = None) -> Tuple[List[Tuple[int, float]], List[int], List[float]]:
        try:
            from audiogen_core.config import CONFIG
            neural_enabled = bool(getattr(CONFIG.composition, "neural_phrase_generator_enabled", False))
        except Exception:
            neural_enabled = False

        if neural_enabled and self._load_neural_model():
            try:
                return self._generate_phrase_neural(
                    start_degree=start_degree,
                    num_notes=num_notes,
                    plan=plan,
                    temperature=temperature,
                    emotion=emotion,
                    start_beat=start_beat,
                    chords=chords,
                    roots=roots,
                    beats_per_bar=beats_per_bar,
                    chord_weights_per_bar=chord_weights_per_bar,
                    beat_positions_out=beat_positions_out,
                    grid=grid,
                    initial_interval_context=initial_interval_context,
                    initial_rhythm_context=initial_rhythm_context,
                    bass_notes=bass_notes,
                    total_beats=total_beats,
                    target_melody_notes=target_melody_notes,
                    phrase_end_beat=phrase_end_beat,
                    occupied_intervals=occupied_intervals,
                    breath_window_by_bar=breath_window_by_bar,
                    bar_intent_by_bar=bar_intent_by_bar,
                    voiced_chords_per_bar=voiced_chords_per_bar,
                )
            except Exception as e:
                logger.error(f"Neural phrase generator failed, falling back to Markov: {e}")

        if num_notes == 0:
            return [], [], []
        if num_notes == 1:
            dur = self._compute_initial_duration(start_beat, beats_per_bar, emotion, temperature, plan=plan)
            if phrase_end_beat is not None:
                remaining = float(phrase_end_beat - start_beat)
                if remaining > 1e-6:
                    dur = min(dur, remaining)
            dur = self._fit_duration_to_phrase_budget(
                dur,
                current_beat=float(start_beat),
                phrase_end_beat=phrase_end_beat,
                notes_done=0,
                num_notes=int(num_notes),
                is_last_note=True,
            )
            if beat_positions_out is not None:
                beat_positions_out.append(start_beat)
            return [(start_degree, dur)], [], [dur]

        initial_interval_context = initial_interval_context or []
        initial_rhythm_context = initial_rhythm_context or []

        # First note
        first_dur = self._compute_initial_duration(start_beat, beats_per_bar, emotion, temperature, plan=plan)
        if phrase_end_beat is not None:
            remaining = float(phrase_end_beat - start_beat)
            if remaining > 1e-6:
                first_dur = min(first_dur, remaining)
        first_dur = self._fit_duration_to_phrase_budget(
            first_dur,
            current_beat=float(start_beat),
            phrase_end_beat=phrase_end_beat,
            notes_done=0,
            num_notes=int(num_notes),
            is_last_note=False,
        )
        melody = [(start_degree, first_dur)]
        if beat_positions_out is not None:
            beat_positions_out.append(start_beat)

        current_beat = start_beat + first_dur
        intervals_so_far = []
        rhythms_so_far = [first_dur]

        # Build occupied onset-step sets/maps from occupied intervals (e.g. arp events).
        # Backwards compatible: accepts [(s,e), ...] but also supports:
        # - (s,e,weight) where weight in 0..1 encodes beat strength / density
        # - (s,e,weight,pcs) where pcs can be int pitch class or iterable of pcs
        occupied_steps: Optional[set[int]] = None
        occupied_step_weights: Optional[Dict[int, float]] = None
        occupied_step_pcs: Optional[Dict[int, set[int]]] = None
        if occupied_intervals:
            try:
                occ = set()
                wmap: Dict[int, float] = {}
                pcmap: Dict[int, set[int]] = {}
                for item in list(occupied_intervals):
                    if item is None:
                        continue
                    try:
                        if isinstance(item, dict):
                            s0 = float(item.get("start", item.get("s")))
                            e0 = float(item.get("end", item.get("e")))
                            w = float(item.get("w", 1.0) or 1.0)
                            pcs_val = item.get("pcs", None)
                        else:
                            seq = list(item)
                            if len(seq) < 2:
                                continue
                            s0 = float(seq[0])
                            e0 = float(seq[1])
                            w = float(seq[2]) if len(seq) >= 3 and seq[2] is not None else 1.0
                            pcs_val = seq[3] if len(seq) >= 4 else None
                    except Exception:
                        continue
                    if e0 <= s0 + 1e-9:
                        continue
                    w = max(0.0, min(1.0, float(w)))
                    # Normalise pitch-class payload.
                    pcs_set: Optional[set[int]] = None
                    if pcs_val is not None:
                        try:
                            if isinstance(pcs_val, (int, float)):
                                pcs_set = {int(pcs_val) % 12}
                            else:
                                pcs_set = {int(x) % 12 for x in (pcs_val or [])}
                        except Exception:
                            pcs_set = None
                    i0 = int(max(0, round(s0 / float(grid))))
                    i1 = int(max(0, round(e0 / float(grid))))
                    for i in range(i0, i1 + 1):
                        ii = int(i)
                        occ.add(ii)
                        wmap[ii] = max(float(wmap.get(ii, 0.0)), float(w))
                        if pcs_set:
                            pcmap.setdefault(ii, set()).update(set(pcs_set))
                occupied_steps = occ if occ else None
                occupied_step_weights = wmap if wmap else None
                occupied_step_pcs = pcmap if pcmap else None
            except Exception:
                occupied_steps = None
                occupied_step_weights = None
                occupied_step_pcs = None

        # Phrase-role scaling: stronger masking on openings/continuations, weaker on answers/cadences.
        try:
            pr = str(getattr(plan, "phrase_role", "") or "").lower()
        except Exception:
            pr = ""
        # Keep openings protected from heavy anti-collision suppression so
        # intro/verse sections still carry a clear topline.
        role_mult = {"opening": 0.90, "continuation": 0.82, "answer": 0.72, "cadence": 0.58}.get(pr, 0.86)
        try:
            from audiogen_core.config import CONFIG

            mask_enabled = bool(getattr(CONFIG.composition, "masking_constraints_runtime_enabled", True))
            mask_strength = float(getattr(CONFIG.composition, "masking_constraints_strength", 0.70))
        except Exception:
            mask_enabled = True
            mask_strength = 0.70
        mask_strength = (max(0.0, min(1.0, float(mask_strength))) * float(role_mult)) if mask_enabled else 0.0
        # When the arp bed provides occupied intervals, treat masking as coexistence guidance:
        # keep the constraint system enabled, but don't let it dominate note/rhythm choices.
        if mask_enabled and float(mask_strength) > 1e-6 and occupied_steps:
            try:
                from audiogen_core.config import CONFIG

                arp_scale = float(
                    getattr(CONFIG.composition, "melody_arp_mask_strength_scale_when_arp_masking", 1.0) or 1.0
                )
            except Exception:
                arp_scale = 1.0
            arp_scale = max(0.0, min(1.0, float(arp_scale)))
            mask_strength = float(max(0.0, min(1.0, float(mask_strength) * float(arp_scale))))

        # Dynamic repetition tracker (n-gram penalty).
        rep_tracker = None
        try:
            from audiogen_core.config import CONFIG

            rep_enabled = bool(getattr(CONFIG.composition, "melody_ngram_penalty_enabled", True))
            rep_window = int(getattr(CONFIG.composition, "melody_ngram_window_tokens", 36) or 36)
            rep_decay = float(getattr(CONFIG.composition, "melody_ngram_decay", 0.92) or 0.92)
            rep_strength = float(getattr(CONFIG.composition, "melody_ngram_penalty_strength", 0.35) or 0.35)
        except Exception:
            rep_enabled = True
            rep_window = 36
            rep_decay = 0.92
            rep_strength = 0.35
        if rep_enabled and float(rep_strength) > 1e-6:
            try:
                from .repetition_tracker import RepetitionTracker

                rep_tracker = RepetitionTracker(
                    window_tokens=int(rep_window),
                    decay=float(rep_decay),
                    strength=float(rep_strength),
                )
                rep_tracker.start(int(start_degree))
                rep_tracker.observe_rhythm(float(first_dur))
            except Exception:
                rep_tracker = None

        try:
            from audiogen_core.config import CONFIG

            _rrt_gen = bool(getattr(CONFIG.composition, "melody_rest_rhythm_tokens_generate_enabled", False))
        except Exception:
            _rrt_gen = False

        while len(melody) < num_notes:
            bar = int(current_beat // beats_per_bar)
            if chords and roots:
                bar = min(bar, len(chords) - 1)

            # Best-effort bar intent row (composition-derived), used as an extra
            # conditioning signal for cadence/function shaping.
            bar_intent = None
            if bar_intent_by_bar and 0 <= int(bar) < len(bar_intent_by_bar):
                row = bar_intent_by_bar[int(bar)]
                bar_intent = row if isinstance(row, dict) else None

            # Optional REST token (consumes one slot; keeps last voiced degree for pitch).
            try:
                from audiogen_core.config import CONFIG

                rest_on = bool(getattr(CONFIG.composition, "melody_generation_rest_tokens_enabled", False))
                rest_p = float(getattr(CONFIG.composition, "melody_rest_token_step_probability", 0.04) or 0.04)
            except Exception:
                rest_on = False
                rest_p = 0.04
            is_last_slot = len(melody) == num_notes - 1
            if (
                rest_on
                and not _rrt_gen
                and rest_p > 1e-9
                and not is_last_slot
                and len(melody) >= 1
                and self.rng.random() < rest_p
            ):
                full_rhythms = initial_rhythm_context + rhythms_so_far
                rhythm_context = full_rhythms[-(self.markov.rhythm.order):]
                full_intervals = initial_interval_context + intervals_so_far
                iv_ctx = full_intervals[-(self.markov.interval.order):]
                dur = self._select_rhythm(
                    rhythm_context,
                    temperature,
                    current_beat,
                    beats_per_bar,
                    emotion,
                    plan=plan,
                    phrase_pos=float(len(melody)) / float(max(1, num_notes)),
                    current_chord=chords[bar] if chords and bar < len(chords) else None,
                    phrase_end_beat=phrase_end_beat,
                    last_interval=(intervals_so_far[-1] if intervals_so_far else (initial_interval_context[-1] if initial_interval_context else None)),
                    occupied_steps=occupied_steps,
                    occupied_step_weights=occupied_step_weights,
                    mask_strength=mask_strength,
                    grid=float(grid),
                    rep_tracker=rep_tracker,
                    breath_window_by_bar=breath_window_by_bar,
                    interval_context_for_joint=iv_ctx,
                    bar_intent=bar_intent,
                    roots=roots,
                )
                try:
                        if float(dur) <= 1e-6:
                            dur = float(DURATIONS[0])
                except Exception:
                    dur = float(DURATIONS[0])
                dur = self._fit_duration_to_phrase_budget(
                    dur,
                    current_beat=float(current_beat),
                    phrase_end_beat=phrase_end_beat,
                    notes_done=len(melody),
                    num_notes=int(num_notes),
                    is_last_note=False,
                )
                melody.append((-1, float(dur)))
                # Do not append a synthetic interval token: interval Markov is trained on
                # voiced steps only; freezing context matches rest-safe training.
                rhythms_so_far.append(float(dur))
                if rep_tracker is not None:
                    try:
                        rep_tracker.observe_rhythm(float(dur))
                    except Exception:
                        pass
                if beat_positions_out is not None:
                    beat_positions_out.append(current_beat)
                current_beat += float(dur)
                continue

            # Motif attempt
            sec_role = (getattr(plan, "section_role", "") or "").lower()
            phr_role = (getattr(plan, "phrase_role", "") or "").lower()
            motif_first_role = sec_role in {"b", "a_prime", "tag"} or (sec_role == "pre_chorus" and phr_role in {"opening", "answer"})
            # Live handoff openings should prioritize “pickup glue” over thematic motif restatement.
            # Motif-first often sounds like an abrupt new song start rather than a transition.
            try:
                from audiogen_core.config import CONFIG
                disable = bool(getattr(CONFIG.composition, "transition_disable_motif_first", True))
                if disable and str(getattr(plan, "phrase_type", "") or "") == "handoff":
                    motif_first_role = False
            except Exception:
                pass
            is_phrase_opening = len(melody) == 1

            # Motif-first openings:
            # If we have motifs in memory, strongly prefer starting the phrase by
            # expanding a motif immediately after the first note. This creates
            # clearer thematic identity in chorus/return sections without changing
            # the underlying Markov model.
            if self.motif.motif_library.motifs and is_phrase_opening and motif_first_role:
                # Hook-safe mode: prioritize a clear motif statement even more strongly.
                # This reduces the chance that chorus openings drift before the hook lands.
                try:
                    from audiogen_core.config import CONFIG
                    hook_safe = bool(getattr(CONFIG.composition, "hook_safe_mode", False))
                except Exception:
                    hook_safe = False
                mult = 2.10 if hook_safe else 1.65
                use_motif = (
                    len(melody) <= num_notes - self.motif.motif_library.motif_length
                    and self.rng.random() < min(0.97, max(0.55 if hook_safe else 0.45, float(self.motif.motif_prob) * float(mult)))
                )
            else:
                use_motif = (
                    self.motif.motif_library.motifs
                    and self.rng.random() < self.motif.motif_prob
                    and len(melody) <= num_notes - self.motif.motif_library.motif_length
                )
            if use_motif and len(melody) >= 1:
                success, new_notes, new_ints, new_rhys, new_beat = self.motif.try_apply_motif(
                    melody, num_notes - len(melody), plan, emotion,
                    chord_weights_per_bar, bar, current_beat, beat_positions_out,
                    current_chord=chords[bar] if chords and bar < len(chords) else "",
                )
                if success:
                    melody.extend(new_notes)
                    intervals_so_far.extend(new_ints)
                    rhythms_so_far.extend(new_rhys)
                    current_beat = new_beat
                    continue

            # Phase 2b: rhythm-first when Markov was trained with signed rest tokens.
            use_rhythm_first = bool(_rrt_gen) and (len(melody) < num_notes - 1)
            if use_rhythm_first:
                full_rhythms_rf = initial_rhythm_context + rhythms_so_far
                rhythm_context_rf = full_rhythms_rf[-(self.markov.rhythm.order):]
                full_intervals_rf = initial_interval_context + intervals_so_far
                interval_context_rf = full_intervals_rf[-(self.markov.interval.order):]
                pos_rf = len(melody) / float(max(1, num_notes))
                # Joint duration×interval rerank: score candidate pairs and softmax-pick one.
                try:
                    from audiogen_core.config import CONFIG

                    jp_on = bool(getattr(CONFIG.composition, "melody_joint_duration_interval_rerank_enabled", True))
                    jp_st = float(getattr(CONFIG.composition, "melody_joint_duration_interval_rerank_strength", 0.85) or 0.85)
                    jp_k = int(getattr(CONFIG.composition, "melody_joint_duration_interval_top_k_durations", 6) or 6)
                    jp_m = int(getattr(CONFIG.composition, "melody_joint_duration_interval_top_m_intervals", 10) or 10)
                    jp_temp = float(getattr(CONFIG.composition, "melody_joint_duration_interval_softmax_temp", 0.65) or 0.65)
                except Exception:
                    jp_on = True
                    jp_st = 0.85
                    jp_k = 6
                    jp_m = 10
                    jp_temp = 0.65
                jp_st = max(0.0, min(1.0, float(jp_st)))
                jp_k = max(1, min(16, int(jp_k)))
                jp_m = max(1, min(24, int(jp_m)))
                jp_temp = max(0.10, min(2.50, float(jp_temp)))

                dur_choice = None
                step_choice = None
                if jp_on and jp_st > 1e-9:
                    try:
                        rhythm_probs = self._rhythm_distribution(
                            rhythm_context_rf,
                            float(temperature),
                            float(current_beat),
                            float(beats_per_bar),
                            emotion,
                            plan=plan,
                            phrase_pos=float(pos_rf),
                            current_chord=chords[bar] if chords and bar < len(chords) else None,
                            phrase_end_beat=phrase_end_beat,
                            last_interval=(
                                intervals_so_far[-1]
                                if intervals_so_far
                                else (initial_interval_context[-1] if initial_interval_context else None)
                            ),
                            occupied_steps=occupied_steps,
                            occupied_step_weights=occupied_step_weights,
                            mask_strength=float(mask_strength),
                            grid=float(grid),
                            rep_tracker=rep_tracker,
                            breath_window_by_bar=breath_window_by_bar,
                            interval_context_for_joint=interval_context_rf,
                            bar_intent=bar_intent,
                        )
                    except Exception:
                        rhythm_probs = {}

                    # Limit to top-K duration candidates (by probability mass).
                    dur_cands = []
                    if rhythm_probs:
                        items = sorted(rhythm_probs.items(), key=lambda kv: -float(kv[1]))[: int(jp_k)]
                        dur_cands = [(float(d), float(p)) for d, p in items if p is not None and float(p) > 0]

                    # Build candidate pairs.
                    cand_pairs = []
                    current_degree_rf = self._last_voiced_degree(melody, start_degree)
                    for dur_val, dur_p in dur_cands:
                        # Allow rest tokens as-is (negative durations). Handle them separately.
                        if float(dur_val) < 0:
                            cand_pairs.append(("rest", float(dur_val), None, float(dur_p)))
                            continue
                        try:
                            int_probs = self._select_interval(
                                interval_context_rf,
                                int(current_degree_rf),
                                melody,
                                float(current_beat),
                                plan,
                                emotion,
                                int(bar),
                                float(pos_rf),
                                chords,
                                roots,
                                chord_weights_per_bar,
                                bass_notes,
                                float(beats_per_bar),
                                int(total_beats),
                                target_melody_notes,
                                float(temperature),
                                rep_tracker=rep_tracker,
                                planned_duration_beats=float(dur_val),
                                occupied_step_weights=occupied_step_weights,
                                occupied_step_pcs=occupied_step_pcs,
                                mask_strength=float(mask_strength),
                                grid=float(grid),
                                phrase_total_notes=num_notes,
                                bar_intent=bar_intent,
                                voiced_chords_per_bar=voiced_chords_per_bar,
                                return_probs=True,
                            )
                        except Exception:
                            int_probs = {}
                        if not isinstance(int_probs, dict) or not int_probs:
                            continue
                        top_int = sorted(int_probs.items(), key=lambda kv: -float(kv[1]))[: int(jp_m)]
                        for iv, ip in top_int:
                            if ip is None or float(ip) <= 0:
                                continue
                            cand_pairs.append(("voiced", float(dur_val), int(iv), float(dur_p) * float(ip)))

                    if cand_pairs:
                        # Softmax pick using a stable scoring objective.
                        import math

                        def _safe_log(x: float) -> float:
                            return math.log(max(1e-12, float(x)))

                        scored = []
                        for kind, dur_val, iv, base_mass in cand_pairs:
                            sc = _safe_log(float(base_mass))
                            if kind == "rest":
                                # mild penalty so rests don't dominate unless rhythm model wants them.
                                sc -= 0.15
                            else:
                                abs_iv = abs(int(iv))
                                # Leap penalty
                                if abs_iv >= 4:
                                    sc -= 0.10 * float(abs_iv - 3)
                                # Chord priority: strong beats want chord tones, especially for longer notes.
                                try:
                                    beat_in_bar = float(current_beat) % float(beats_per_bar)
                                except Exception:
                                    beat_in_bar = 0.0
                                strong = (abs(beat_in_bar - 0.0) < 1e-6) or (abs(beat_in_bar - 2.0) < 1e-6)
                                if strong and chord_weights_per_bar and 0 <= int(bar) < len(chord_weights_per_bar):
                                    chord_tones = set(int(d) % 7 for d in (chord_weights_per_bar[int(bar)] or {}).keys())
                                    nxt = (int(current_degree_rf) + int(iv)) % 7
                                    if chord_tones:
                                        longish = float(dur_val) >= 0.5
                                        if int(nxt) in chord_tones:
                                            sc += (0.45 if longish else 0.28)
                                        else:
                                            sc -= (0.95 if longish else 0.60)
                            # Blend strength (0 => neutral base_mass; 1 => full objective)
                            sc = float(_safe_log(float(base_mass)) + (float(sc) - _safe_log(float(base_mass))) * float(jp_st))
                            scored.append((sc, kind, dur_val, iv))

                        # Softmax over scores
                        msc = max(float(s[0]) for s in scored)
                        ws = []
                        for sc, _k, _d, _iv in scored:
                            ws.append(math.exp((float(sc) - float(msc)) / float(jp_temp)))
                        tot = float(sum(ws))
                        if tot > 1e-12:
                            ws = [float(w) / tot for w in ws]
                            pick_i = self.rng.choices(list(range(len(scored))), weights=ws, k=1)[0]
                            _sc, kind, dur_val, iv = scored[int(pick_i)]
                            if kind == "rest":
                                dur_choice = float(dur_val)
                                step_choice = None
                            else:
                                dur_choice = float(dur_val)
                                step_choice = int(iv)

                # Fallback to legacy rhythm-first if joint rerank didn't pick.
                if dur_choice is None:
                    dur_choice = self._select_rhythm(
                        rhythm_context_rf,
                        temperature,
                        current_beat,
                        beats_per_bar,
                        emotion,
                        plan=plan,
                        phrase_pos=pos_rf,
                        current_chord=chords[bar] if chords and bar < len(chords) else None,
                        phrase_end_beat=phrase_end_beat,
                        last_interval=(
                            intervals_so_far[-1]
                            if intervals_so_far
                            else (initial_interval_context[-1] if initial_interval_context else None)
                        ),
                        occupied_steps=occupied_steps,
                        occupied_step_weights=occupied_step_weights,
                        mask_strength=mask_strength,
                        grid=float(grid),
                        rep_tracker=rep_tracker,
                        breath_window_by_bar=breath_window_by_bar,
                        interval_context_for_joint=interval_context_rf,
                        bar_intent=bar_intent,
                        roots=roots,
                    )
                dur_rf = float(dur_choice)
                try:
                    if float(dur_rf) < 0:
                        dur_abs = abs(float(dur_rf))
                        if dur_abs <= 1e-6:
                            dur_abs = float(DURATIONS[0])
                        melody.append((-1, dur_abs))
                        rhythms_so_far.append(float(dur_rf))
                        if rep_tracker is not None:
                            try:
                                rep_tracker.observe_rhythm(float(dur_rf))
                            except Exception:
                                pass
                        if beat_positions_out is not None:
                            beat_positions_out.append(current_beat)
                        current_beat += dur_abs
                        continue
                except Exception:
                    pass
                dur_rf = float(dur_rf)
                if dur_rf <= 1e-6:
                    dur_rf = float(DURATIONS[0])
                dur_rf = self._fit_duration_to_phrase_budget(
                    dur_rf,
                    current_beat=float(current_beat),
                    phrase_end_beat=phrase_end_beat,
                    notes_done=len(melody),
                    num_notes=int(num_notes),
                    is_last_note=False,
                )
                current_degree_rf = self._last_voiced_degree(melody, start_degree)
                pos_ri = len(melody) / float(max(1, num_notes))
                if step_choice is not None:
                    step_rf = int(step_choice)
                else:
                    step_rf = self._select_interval(
                        interval_context_rf,
                        current_degree_rf,
                        melody,
                        current_beat,
                        plan,
                        emotion,
                        bar,
                        pos_ri,
                        chords,
                        roots,
                        chord_weights_per_bar,
                        bass_notes,
                        beats_per_bar,
                        total_beats,
                        target_melody_notes,
                        temperature,
                        rep_tracker=rep_tracker,
                        planned_duration_beats=float(dur_rf),
                        occupied_step_weights=occupied_step_weights,
                        occupied_step_pcs=occupied_step_pcs,
                        mask_strength=mask_strength,
                        grid=float(grid),
                        phrase_total_notes=num_notes,
                        bar_intent=bar_intent,
                        voiced_chords_per_bar=voiced_chords_per_bar,
                    )
                new_deg_rf = (current_degree_rf + step_rf) % 7
                melody.append((new_deg_rf, dur_rf))
                intervals_so_far.append(step_rf)
                rhythms_so_far.append(dur_rf)
                if rep_tracker is not None:
                    try:
                        rep_tracker.observe_interval(int(step_rf), int(new_deg_rf))
                        rep_tracker.observe_rhythm(float(dur_rf))
                    except Exception:
                        pass
                if beat_positions_out is not None:
                    beat_positions_out.append(current_beat)
                current_beat += dur_rf
                continue

            # Interval selection
            full_intervals = initial_interval_context + intervals_so_far
            interval_context = full_intervals[-(self.markov.interval.order):]
            current_degree = self._last_voiced_degree(melody, start_degree)
            pos = len(melody) / num_notes

            # ── Final-note cadence override ──────────────────────────────
            # On the very last note of the phrase, bypass normal selection
            # and use a near-forced cadence landing.  This gives melodies a
            # clear sense of arrival rather than stopping mid-thought.
            # The cadence zone bias in _select_interval handles all earlier
            # notes; this only fires for the absolute last one.
            is_last_note = (len(melody) == num_notes - 1)
            if is_last_note and hasattr(plan, 'cadence_degree'):
                # Emotion anchors: cadence archetype can choose a different *landing target*
                # for the final note, making endings feel resolved vs suspended vs avoidant.
                try:
                    cadence_style = str(getattr(anchors_for_emotion(emotion), "cadence", "authentic") or "authentic").lower()
                except Exception:
                    cadence_style = "authentic"
                cadence_style = cadence_style if cadence_style in {"authentic", "plagal", "suspended", "avoid"} else "authentic"

                target_deg = int(getattr(plan, "cadence_degree", 0) or 0) % 7
                chord_tones = set()
                try:
                    if chord_weights_per_bar and 0 <= int(bar) < len(chord_weights_per_bar):
                        chord_tones = set(int(d) % 7 for d in (chord_weights_per_bar[int(bar)] or {}).keys())
                except Exception:
                    chord_tones = set()

                if cadence_style in {"suspended", "avoid"}:
                    # Anticipation: if we're near the end of the bar/phrase and a next chord
                    # exists, bias the hanging target using the *next* chord function/tones.
                    ref_bar = int(bar)
                    try:
                        in_last_quarter = (float(current_beat) % float(beats_per_bar)) >= (float(beats_per_bar) * 0.75)
                    except Exception:
                        in_last_quarter = False
                    try:
                        if in_last_quarter and chords and (int(bar) + 1) < len(chords):
                            ref_bar = int(bar) + 1
                            if chord_weights_per_bar and ref_bar < len(chord_weights_per_bar):
                                chord_tones = set(int(d) % 7 for d in (chord_weights_per_bar[ref_bar] or {}).keys())
                    except Exception:
                        ref_bar = int(bar)

                    # Try to land on a "hanging" scale degree rather than the tonic target.
                    # suspended: 2 or 4 (degrees 1 or 3)
                    # avoid: 2 or 7 (degrees 1 or 6)
                    # Make it chord-aware (dominant bars suspend differently).
                    try:
                        func = self.markov.extract_harmonic_function(chords[ref_bar] if chords and ref_bar < len(chords) else "")
                    except Exception:
                        func = "other"
                    is_dom = str(func or "").lower() == "dom"
                    if cadence_style == "suspended":
                        prefs = ([3, 1] if is_dom else [1, 3])
                    else:
                        prefs = ([6, 1] if is_dom else [1, 6])
                    # Prefer a degree that is NOT currently a chord tone (creates suspension),
                    # but fall back safely if all are chord tones.
                    alt = next((d for d in prefs if d not in chord_tones), None)
                    if alt is None:
                        alt = prefs[0]
                    target_deg = int(alt) % 7
                elif cadence_style == "plagal":
                    # Softer landing: still targets the cadence degree, but allow "gentle" approach.
                    target_deg = int(target_deg) % 7

                step = self._select_cadence_final_interval(
                    current_degree,
                    int(target_deg),
                    interval_context,
                    temperature,
                )
            else:
                step = self._select_interval(
                    interval_context, current_degree, melody, current_beat, plan,
                    emotion, bar, pos, chords, roots, chord_weights_per_bar,
                    bass_notes, beats_per_bar, total_beats, target_melody_notes, temperature,
                    rep_tracker=rep_tracker,
                    planned_duration_beats=None,
                    occupied_step_weights=occupied_step_weights,
                    occupied_step_pcs=occupied_step_pcs,
                    mask_strength=mask_strength,
                    grid=float(grid),
                    phrase_total_notes=num_notes,
                    bar_intent=bar_intent,
                    voiced_chords_per_bar=voiced_chords_per_bar,
                )

            # Rhythm selection
            full_rhythms = initial_rhythm_context + rhythms_so_far
            rhythm_context = full_rhythms[-(self.markov.rhythm.order):]
            is_last_note = (len(melody) == num_notes - 1)
            if phrase_end_beat is not None and is_last_note:
                remaining = float(phrase_end_beat - current_beat)
                dur = max(0.0, remaining)
                if dur <= 1e-6:
                    dur = DURATIONS[0]
            else:
                dur = self._select_rhythm(
                    rhythm_context,
                    temperature,
                    current_beat,
                    beats_per_bar,
                    emotion,
                    plan=plan,
                    phrase_pos=pos,
                    current_chord=chords[bar] if chords and bar < len(chords) else None,
                    phrase_end_beat=phrase_end_beat,
                    last_interval=(intervals_so_far[-1] if intervals_so_far else (initial_interval_context[-1] if initial_interval_context else None)),
                    occupied_steps=occupied_steps,
                    occupied_step_weights=occupied_step_weights,
                    mask_strength=mask_strength,
                    grid=float(grid),
                    rep_tracker=rep_tracker,
                    breath_window_by_bar=breath_window_by_bar,
                    interval_context_for_joint=interval_context,
                    bar_intent=bar_intent,
                )
            dur = self._fit_duration_to_phrase_budget(
                dur,
                current_beat=float(current_beat),
                phrase_end_beat=phrase_end_beat,
                notes_done=len(melody),
                num_notes=int(num_notes),
                is_last_note=bool(is_last_note),
            )

            new_degree = (current_degree + step) % 7
            # Guardrail: never emit non-positive durations (can happen when a phrase_end_beat
            # is already passed due to rounding / post-processing shifts).
            try:
                if float(dur) <= 1e-6:
                    dur = float(DURATIONS[0])
            except Exception:
                dur = float(DURATIONS[0])
            melody.append((new_degree, dur))
            intervals_so_far.append(step)
            rhythms_so_far.append(dur)
            if rep_tracker is not None:
                try:
                    rep_tracker.observe_interval(int(step), int(new_degree))
                    rep_tracker.observe_rhythm(float(dur))
                except Exception:
                    pass
            if beat_positions_out is not None:
                beat_positions_out.append(current_beat)
            current_beat += dur

        # Final length correction
        if len(melody) != num_notes:
            logger.warning(f"NoteGenerator generated {len(melody)} notes, expected {num_notes} – correcting")
            if len(melody) < num_notes:
                last = melody[-1] if melody else (start_degree, DURATIONS[0])
                melody.extend([last] * (num_notes - len(melody)))
            else:
                melody = melody[:num_notes]

        return melody, intervals_so_far, rhythms_so_far
