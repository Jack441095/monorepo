from audiogen_core.config import resolve_config
# composition/engine.py
# Project module `engine` (composition).

# engine.py

import contextlib
import copy
import hashlib
import logging
import random
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ai.markov import ChordMarkov, GlobalChordMarkov, MelodyGenerator
from audiogen_core.composition_runtime_flags import stable_emotion_velocity_multiplier
from data.emotion_melody_parameters import EMOTION_MELODY_PARAMS
from data.music_data import EmotionProfile
from midi.midi_range_limiter import RANGE_LIMITER

from .bass_engine import BassEngine
from .chord_planner import ChordPlanner
from .chord_utils import ChordUtils
from .contour_planner_model import ContourPlannerModel
from .event_pipeline import EventPipeline
from .harmonic_rhythm_model import HarmonicRhythmModel
from .harmony_manager import CompositionHarmonyManager
from .markov_backoff import blend_with_backoff, entropy_bits, top_k
from .melody_factory import MelodyFactory
from .melody_manager import CompositionMelodyManager
from .mixins import CachingMixin, PerformanceMixin
from .motif_plan import MotifPlanManager
from .policies import ArrangementPolicy, MelodyGenerationPolicy
from .protocols import MarkovChain, MelodyMarkovModelSet
from .retrained_markov_loader import (
    get_chord_retrain_config,
    get_melody_retrain_config,
    load_chord_retrained_pickle,
    load_melody_retrained_pickle,
)
from .section_plan import SectionPlan
from .section_planner import SectionPlanner
from .song_memory import SongMemory
from .voice_leading_engine import VoiceLeadingEngine

logger = logging.getLogger(__name__)


class CompositionGenerator(
    PerformanceMixin,
    CachingMixin,
):
    # N-gram harmony models (`ai.markov.chord`, retrained pickloads, etc.).
    chord_markov: MarkovChain
    chord_markov_bucket: MarkovChain
    global_chord_markov: Optional[MarkovChain]
    global_chord_markov_bucket: Optional[MarkovChain]

    MODAL_INTERCHANGE_MAJOR = {
        "bII": "Db", "bIII": "Eb", "iv": "Fm", "bVI": "Ab", "bVII": "Bb", "ii°": "Ddim",
    }
    MODAL_INTERCHANGE_MINOR = {
        "IV": "F", "V": "G", "bVI": "Ab", "bVII": "Bb", "VII": "G#dim",
    }
    SECONDARY_DOMINANTS = {
        "ii": "V/ii", "iii": "V/iii", "IV": "V/IV", "V": "V/V", "vi": "V/vi",
        "VII": "V/VII", "ii7": "V7/ii", "iii7": "V7/iii", "IVmaj7": "V7/IV",
        "V7": "V7/V", "vi7": "V7/vi", "VII7": "V7/VII",
    }
    CHORD_FUNCTION_WEIGHTS = {
        'maj': {'maj': 1.0, 'min': 1.2, 'dom': 1.5, 'dim': 0.5, 'aug': 0.3, 'sus': 0.8},
        # Stronger min → dom models ii→V motion toward cadences.
        'min': {'maj': 1.2, 'min': 1.0, 'dom': 1.45, 'dim': 0.6, 'aug': 0.4, 'sus': 0.7},
        'dom': {'maj': 2.0, 'min': 0.8, 'dom': 0.7, 'dim': 0.4, 'aug': 0.5, 'sus': 0.9},
        'dim': {'maj': 0.8, 'min': 0.9, 'dom': 1.1, 'dim': 0.5, 'aug': 0.3, 'sus': 0.6},
        'aug': {'maj': 1.1, 'min': 0.7, 'dom': 1.2, 'dim': 0.4, 'aug': 0.5, 'sus': 0.5},
        'sus': {'maj': 1.3, 'min': 1.1, 'dom': 1.4, 'dim': 0.5, 'aug': 0.4, 'sus': 0.6},
    }

    def _build_chord_candidate_weights(self,
                                       markov_probs: dict,
                                       simplified_vocab: List[str],
                                       history: List[str],
                                       repeat_penalty: float,
                                       bar_in_phrase: int,
                                       phrase_length: int,
                                       force_change: bool = False) -> Tuple[List[str], List[float]]:
        return self.chord_planner.build_chord_candidate_weights(
            markov_probs, simplified_vocab, history, repeat_penalty,
            bar_in_phrase, phrase_length, force_change=force_change
        )

    def _sample_next_simplified_chord(self,
                                      context: List[str],
                                      simplified_vocab: List[str],
                                      history: List[str],
                                      temperature: float,
                                      repeat_penalty: float,
                                      bar_in_phrase: int,
                                      phrase_length: int,
                                      force_change: bool = False,
                                      greedy: bool = False) -> str:
        return self.chord_planner.sample_next_simplified_chord(
            context, simplified_vocab, history, temperature,
            repeat_penalty, bar_in_phrase, phrase_length,
            force_change=force_change, greedy=greedy
        )

    def __init__(self,
                use_substitutions: bool = True,
                substitution_prob: float = 0.3,
                num_variations: int = 3,
                use_global_model: bool = True,
                global_blend_weight: float = 0.3,
                humanize: bool = True,
                phrases_per_section: int = 4,
                use_extensions: bool = True,
                extension_prob: float = 0.3,
                use_modal_interchange: bool = False,
                interchange_prob: float = 0.2,
                use_secondary_dominants: bool = True,
                secondary_dominant_prob: float = 0.15,
                embellishment_prob: float = 0.2,
                motif_variation_prob: float = 0.3,
                enforce_melody_climax: bool = False,
                bass_density: float = 2.0,
                bass_style: str = 'simple',
                use_voice_leading: bool = True,
                enable_perf_monitoring: bool = False,
                global_scale: Optional[List[int]] = None,
                use_config_global_scale: bool = True,
                humanization_probability: float = 0.3,
                chord_repeat_penalty: float = 0.3,
                max_chord_repeats: int = 2,
                force_change_prob: float = 0.2,
                ambient_chord_hold_bars: int = 1,
                *,
                chord_markov: Optional[MarkovChain] = None,
                chord_markov_bucket: Optional[MarkovChain] = None,
                global_chord_markov: Optional[MarkovChain] = None,
                global_chord_markov_bucket: Optional[MarkovChain] = None,
                melody_markov_model: Optional[MelodyMarkovModelSet] = None,
                skip_markov_retrain_load: bool = False,
                skip_chord_markov_pool_training: Optional[bool] = None):
        """
        Optional Markov injection (tests / alternate backends):

        Pass concrete chain instances to bypass default ``ChordMarkov`` / ``GlobalChordMarkov``
        construction; pass ``melody_markov_model`` to bind after ``MelodyGenerator`` init.
        ``skip_markov_retrain_load`` skips pickle loads from CONFIG paths.
        ``skip_chord_markov_pool_training``: default True if any chord model was injected,
        else follows CONFIG and retrained-load state.
        """

        PerformanceMixin.__init__(self, enable_perf_monitoring=enable_perf_monitoring)
        CachingMixin.__init__(self)

        self.use_substitutions = use_substitutions
        self.substitution_prob = substitution_prob
        self.num_variations = num_variations
        self.use_global_model = use_global_model
        self.global_blend_weight = global_blend_weight if use_global_model else 0.0
        self.humanize = humanize
        self.humanization_probability = humanization_probability
        self.phrases_per_section = phrases_per_section
        self.use_voice_leading = use_voice_leading

        self.use_extensions = use_extensions
        self.extension_prob = extension_prob
        self.use_modal_interchange = use_modal_interchange
        self.interchange_prob = interchange_prob
        self.use_secondary_dominants = use_secondary_dominants
        self.secondary_dominant_prob = secondary_dominant_prob

        self.embellishment_prob = embellishment_prob
        self.motif_variation_prob = motif_variation_prob
        self.enforce_melody_climax = enforce_melody_climax

        self.bass_density = bass_density
        self.bass_style = bass_style

        gs = global_scale
        self.global_scale = gs
        self.chord_repeat_penalty = chord_repeat_penalty
        self.max_chord_repeats = max_chord_repeats
        self.force_change_prob = force_change_prob
        self.ambient_chord_hold_bars = max(1, int(ambient_chord_hold_bars))
        self.voice_leading_beam_width = 10
        # Realtime effort scaling: cap voice-leading search cost first.
        eff = resolve_config("composition", "realtime_effort", 'full')
        if eff == "minimal":
            self.voice_leading_beam_width = min(int(self.voice_leading_beam_width), 4)
        elif eff == "balanced":
            self.voice_leading_beam_width = min(int(self.voice_leading_beam_width), 8)
        self._chord_validation_cache = {}
        self.arrangement_policy = ArrangementPolicy()
        self.melody_policy = MelodyGenerationPolicy()
        self.event_pipeline = EventPipeline()
        self.seed: Optional[int] = None
        # By default keep using module-level `random` for backwards compatibility
        # (tests and some call sites monkeypatch `random.random`).
        self.rng = random
        try:
            self.event_pipeline.set_rng(self.rng)
        except Exception:
            pass
        self.chord_utils = ChordUtils(self)
        self.chord_planner = ChordPlanner(self)
        self.harmony_manager = CompositionHarmonyManager(self)
        self.bass_engine = BassEngine(self)
        self.voice_leading_engine = VoiceLeadingEngine(self, beam_width=self.voice_leading_beam_width)
        self.melody_factory = MelodyFactory(self)
        self.melody_manager = CompositionMelodyManager(self)
        self.melody_runtime = self.melody_manager.runtime
        self.melody_planner = self.melody_manager.planner
        self.section_planner = SectionPlanner(self)

        # Provide deterministic RNGs to the event pipeline for groove/microtiming.
        try:
            self.event_pipeline.set_deterministic_rng_provider(self.deterministic_rng)
        except Exception:
            pass

        with self.perf_monitor.measure("init_markov"):
            backoff = 0.7
            backoff = resolve_config("composition", "markov_backoff_decay", 0.7, float)
            self.chord_markov = (
                chord_markov
                if chord_markov is not None
                else ChordMarkov(order=3, smoothing=0.01, backoff_decay=backoff)
            )
            # Backoff model used when degree-aware tokens are enabled.
            # When disabled, this remains unused and does not affect output.
            self.chord_markov_bucket = (
                chord_markov_bucket
                if chord_markov_bucket is not None
                else ChordMarkov(order=3, smoothing=0.01, backoff_decay=backoff)
            )
            if use_global_model:
                self.global_chord_markov = (
                    global_chord_markov
                    if global_chord_markov is not None
                    else GlobalChordMarkov(order=3, smoothing=0.01, backoff_decay=backoff)
                )
                self.global_chord_markov_bucket = (
                    global_chord_markov_bucket
                    if global_chord_markov_bucket is not None
                    else GlobalChordMarkov(order=3, smoothing=0.01, backoff_decay=backoff)
                )
            else:
                self.global_chord_markov = None
                self.global_chord_markov_bucket = None
            self.chord_markov_role_models = {}
            # `self.rng` is intentionally the module-level `random` by default for test
            # monkeypatch compatibility, but modules can't be deep-copied/pickled.
            # Keep the melody Markov generator on a copyable RNG instance unless reseeded.
            melody_rng = self.rng if isinstance(self.rng, random.Random) else random.Random()
            self.melody_gen = MelodyGenerator(
                interval_order=6,
                rhythm_order=4,
                phrase_order=2,
                smoothing=0.01,
                motif_length=3,
                # More memorable lead defaults:
                # - higher motif insertion probability
                # - lower motif variation (more literal restatements)
                # - fewer embellishments + slightly fewer rests (clearer "song-like" line)
                # - more phrase-level repetition (A/A' / call-response)
                motif_prob=0.72,
                embellishment_prob=0.10,
                motif_variation_prob=0.25,
                enforce_climax=self.enforce_melody_climax,
                emotion_intensity=1.2,
                stepwise_boost_base=8.0,
                chord_tone_multiplier=25.0,
                downbeat_chord_multiplier=35.0,
                enforce_chord_tones_prob=0.98,
                enforce_phrase_structure_prob=0.85,
                rest_prob=0.10,
                phrase_repetition_prob=0.42,
                use_rejection_sampling=False,
                rejection_max_attempts=3,
                use_chord_conditioned_markov=True,
                phrase_gap_prob=0.62,
                phrase_gap_duration=1.0,
                rng=melody_rng,
            )
            # Training-derived per-emotion phrase models were purged; keep a stable
            # empty mapping so runtime code can fall back to the base phrase Markov.
            self.emotion_phrase_models: Dict[str, Any] = {}
            # State for optional retrained melody Markov hot-reload (mtime polling).
            self._retrained_melody_markov_path_loaded: str = ""
            self._retrained_melody_markov_mtime_ns: Optional[int] = None
            self._retrained_melody_markov_next_check_monotonic: float = 0.0
            # Optional: load retrained melody Markov model from pickle. When async-load is
            # enabled (realtime), do it on a background thread so construction doesn't block
            # ~6s on the 196MB unpickle; the first sections use the default melody path and
            # upgrade to the retrained model once the load lands.
            if not skip_markov_retrain_load:
                if bool(resolve_config("composition", "melody_retrained_markov_async_load", False, bool)):
                    self._start_async_melody_markov_load()
                else:
                    self._try_load_retrained_melody_markov(hot_reload=False)

            # State for optional retrained chord Markov hot-reload (mtime polling).
            self._retrained_chord_markov_path_loaded: str = ""
            self._retrained_chord_markov_mtime_ns: Optional[int] = None
            self._retrained_chord_markov_next_check_monotonic: float = 0.0
            self._retrained_chord_markov_loaded_ok: bool = False
            # Optional: load retrained chord Markov bundle from pickle.
            if not skip_markov_retrain_load:
                self._try_load_retrained_chord_markov(hot_reload=False)

            if melody_markov_model is not None:
                self._bind_melody_markov_model(melody_markov_model)

        _injected_any_chord = (
            chord_markov is not None
            or chord_markov_bucket is not None
            or global_chord_markov is not None
            or global_chord_markov_bucket is not None
        )
        if skip_chord_markov_pool_training is None:
            skip_pool_train = bool(_injected_any_chord)
        else:
            skip_pool_train = bool(skip_chord_markov_pool_training)

        # Populate chord Markov probabilities from the in-repo chord progression pools.
        # This keeps chord sampling aligned with the curated “dataset” in `data/music_data.py`.
        train_enabled = resolve_config("composition", "chord_markov_train_from_pools", True, bool)
        if (
            train_enabled
            and not bool(getattr(self, "_retrained_chord_markov_loaded_ok", False))
            and not skip_pool_train
        ):
            try:
                self._train_chord_markovs_from_emotion_pools()
            except Exception:
                logger.debug("Chord Markov pool training failed", exc_info=True)

        self.runtime_generation_mode = "normal"
        self.recent_section_chord_signatures = deque(maxlen=6)
        self.recent_section_openings = deque(maxlen=8)
        self.recent_phrase_contour_signatures = deque(maxlen=8)
        self.recent_melody_openings = deque(maxlen=8)
        self._last_generated_phrase_contours = []
        self.song_memory = SongMemory(max_recent_sections=8)
        # Cross-song memory: remember the *opening* chord signature of the last rendered song
        # per emotion, so regenerating another song in the same emotion doesn't reuse the same
        # progression backbone again.
        #
        # Intentionally NOT cleared by `reset_song_arrangement_state()` since that is called
        # at the start of each new song render.
        self.last_song_opening_chord_signature_by_emotion: Dict[str, Tuple[str, ...]] = {}

        self._drone_event = None
        self._drone_root_locked = None   # set once on first section, never changed
        self._drone_emitted = False      # True once the event has been sent to the player
        self._emotion_transition_handoff_ctx: Optional[Dict[str, Any]] = None
        self._song_motif_hook_seeded: bool = False
        self._bass_motif_families: Dict[str, str] = {}
        self.motif_plan = MotifPlanManager(self)
        self.harmonic_rhythm_model = HarmonicRhythmModel(rng=getattr(self, "rng", None) or random)
        self.contour_planner_model = ContourPlannerModel(rng=getattr(self, "rng", None) or random)

        # Optional deterministic seed from CONFIG (best-effort).
        seed = resolve_config("composition", "seed", None)
        if seed is not None:
            self.reseed(int(seed))

    def _bind_melody_markov_model(self, markov_model: Optional[MelodyMarkovModelSet]) -> bool:
        """
        Wire a replacement melody Markov model set into MelodyGenerator runtime references.

        Returns True on success; False when the model is incompatible.
        """
        mg = getattr(self, "melody_gen", None)
        if mg is None or markov_model is None:
            return False
        try:
            mg.markov = markov_model
            mg.interval_markov = markov_model.interval
            mg.rhythm_markov = markov_model.rhythm
            mg.phrase_markov = markov_model.phrase
            if hasattr(mg, "note_gen") and mg.note_gen is not None:
                mg.note_gen.markov = markov_model
            return True
        except Exception:
            logger.debug("Failed to bind melody Markov model", exc_info=True)
            return False

    @staticmethod
    def _retrained_emotion_family(name: str) -> str:
        n = (name or "").strip().lower()
        if not n:
            return "neutral"
        if any(k in n for k in ("grief", "sad", "remorse", "disappointment", "melanch")):
            return "sad"
        if any(k in n for k in ("calm", "relax", "peace", "serene")):
            return "calm"
        if any(k in n for k in ("fear", "nervous", "anxiety", "tense", "confus")):
            return "tense"
        if any(k in n for k in ("anger", "rage", "furious")):
            return "angry"
        if any(k in n for k in ("joy", "excite", "optim", "amuse", "pride")):
            return "energetic"
        if any(k in n for k in ("love", "caring", "gratitude", "relief", "approval")):
            return "warm"
        if any(k in n for k in ("surprise", "realization", "curiosity")):
            return "curious"
        return "neutral"

    def _select_retrained_melody_markov(self, emotion: Optional[EmotionProfile]) -> Optional[MelodyMarkovModelSet]:
        name = ""
        try:
            name = str(getattr(emotion, "name", "") or "").strip().lower()
        except Exception:
            name = ""
        if name:
            models = getattr(self, "_retrained_melody_markov_emotion_models", {}) or {}
            if isinstance(models, dict) and name in models:
                return models.get(name)
        family = self._retrained_emotion_family(name)
        fam_models = getattr(self, "_retrained_melody_markov_family_models", {}) or {}
        if isinstance(fam_models, dict) and family in fam_models:
            return fam_models.get(family)
        return getattr(self, "_retrained_melody_markov_global_model", None)

    def _apply_retrained_melody_markov_for_emotion(self, emotion: Optional[EmotionProfile]) -> None:
        model = self._select_retrained_melody_markov(emotion)
        if model is None:
            return
        if model is getattr(self, "_retrained_melody_markov_current_model", None):
            return
        if self._bind_melody_markov_model(model):
            self._retrained_melody_markov_current_model = model

    def _start_async_melody_markov_load(self) -> None:
        """Load the retrained melody bundle on a background daemon thread (realtime startup
        speedup). Populates the model fields without binding; the generation thread binds
        via ``_apply_retrained_melody_markov_for_emotion`` once the fields are present."""
        import threading

        def _worker():
            try:
                self._try_load_retrained_melody_markov(hot_reload=False, bind=False)
            except Exception:
                logger.debug("Async retrained melody Markov load failed", exc_info=True)

        try:
            t = threading.Thread(target=_worker, name="melody-markov-async-load", daemon=True)
            t.start()
            self._melody_markov_async_load_thread = t
        except Exception:
            # If the thread can't start, fall back to a synchronous load so behavior is
            # never worse than the blocking default.
            logger.debug("Could not start async melody Markov load; loading synchronously", exc_info=True)
            self._try_load_retrained_melody_markov(hot_reload=False)

    def _try_load_retrained_melody_markov(self, *, hot_reload: bool, bind: bool = True) -> None:
        """
        Best-effort startup load of a retrained Melody MarkovModelSet pickle.

        ``bind=False`` (used by the async loader) populates the model fields without binding
        them into the live MelodyGenerator -- binding then happens on the generation thread
        via ``_apply_retrained_melody_markov_for_emotion``, avoiding a cross-thread swap of
        the multi-attribute markov references mid-note-generation.

        Training ↔ serving contract (details in ``core.markov_serving_contract`` and
        ``composition.retrained_markov_loader``):
        enable/path/hot-reload keys are ``CONFIG_MELODY_RETRAINED_*`` on ``CONFIG.composition``.
        The pickle path is read from ``CONFIG_MELODY_RETRAINED_MARKOV_PATH``; optional reload
        uses mtime with interval ``CONFIG_MELODY_RETRAINED_HOT_RELOAD_INTERVAL_S``.
        Accepted payloads: bare ``MarkovModelSet``, or a bundle dict whose ``kind`` equals
        ``MELODY_MARKOV_BUNDLE_KIND``. After load, read ``order``, ``smoothing``, and
        ``backoff_decay`` from each ``BaseMarkov`` chain (no separate tokenizer-version string).
        """
        cfg = get_melody_retrain_config()
        enabled, raw_path, reload_on, reload_iv = (
            cfg.enabled,
            cfg.raw_path,
            cfg.reload_on,
            cfg.reload_interval_s,
        )
        if not enabled or not raw_path:
            return
        if hot_reload and not reload_on:
            return

        now_mono = float(time.monotonic())
        if hot_reload:
            if now_mono < float(getattr(self, "_retrained_melody_markov_next_check_monotonic", 0.0) or 0.0):
                return
            reload_iv = max(0.05, float(reload_iv))
            self._retrained_melody_markov_next_check_monotonic = now_mono + reload_iv

        p = Path(raw_path).expanduser()
        if not p.exists() or not p.is_file():
            if not hot_reload:
                logger.warning("Retrained melody Markov file not found: %s", str(p))
            return
        try:
            st = p.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(float(st.st_mtime) * 1e9)))
        except Exception:
            mtime_ns = None

        if hot_reload:
            try:
                loaded_path = str(getattr(self, "_retrained_melody_markov_path_loaded", "") or "")
                loaded_mtime = getattr(self, "_retrained_melody_markov_mtime_ns", None)
            except Exception:
                loaded_path = ""
                loaded_mtime = None
            if loaded_path == str(p) and loaded_mtime is not None and mtime_ns is not None and int(loaded_mtime) == int(mtime_ns):
                return

        loaded = load_melody_retrained_pickle(p, hot_reload=hot_reload)
        if loaded is None:
            return
        loaded_model, emotion_models, family_models = loaded

        self._retrained_melody_markov_global_model = loaded_model
        self._retrained_melody_markov_emotion_models = emotion_models
        self._retrained_melody_markov_family_models = family_models
        if not bind:
            # Async path: fields are populated (single atomic reference assignments); the
            # generation thread binds via _apply_retrained_melody_markov_for_emotion. Record
            # the loaded path/mtime so the (default-off) per-section hot-reload sees the file
            # as already-loaded and never triggers a duplicate blocking load.
            self._retrained_melody_markov_path_loaded = str(p)
            self._retrained_melody_markov_mtime_ns = int(mtime_ns) if mtime_ns is not None else None
            logger.info("Loaded retrained melody Markov model (async, deferred bind): %s", str(p))
            return
        if self._bind_melody_markov_model(loaded_model):
            self._retrained_melody_markov_current_model = loaded_model
            self._retrained_melody_markov_path_loaded = str(p)
            self._retrained_melody_markov_mtime_ns = int(mtime_ns) if mtime_ns is not None else None
            if hot_reload:
                logger.info("Hot-reloaded retrained melody Markov model: %s", str(p))
            else:
                logger.info("Loaded retrained melody Markov model: %s", str(p))

    def _try_load_retrained_chord_markov(self, *, hot_reload: bool) -> None:
        """
        Best-effort startup/hot-reload of a retrained chord Markov bundle pickle.

        Training ↔ serving contract (details in ``core.markov_serving_contract`` and
        ``composition.retrained_markov_loader``):
        enable/path/hot-reload keys are ``CONFIG_CHORD_RETRAINED_*`` on ``CONFIG.composition``.
        Path from ``CONFIG_CHORD_RETRAINED_MARKOV_PATH``; reload cadence from
        ``CONFIG_CHORD_RETRAINED_HOT_RELOAD_INTERVAL_S``. Bundle dict ``kind`` must equal
        ``CHORD_MARKOV_BUNDLE_KIND``. Per-chain hyperparameters ``order``, ``smoothing``, and
        ``backoff_decay`` live on ``BaseMarkov`` instances inside ``degree`` / ``bucket`` maps.
        """
        cfg = get_chord_retrain_config()
        enabled, raw_path, reload_on, reload_iv = (
            cfg.enabled,
            cfg.raw_path,
            cfg.reload_on,
            cfg.reload_interval_s,
        )
        if not enabled or not raw_path:
            return
        if hot_reload and not reload_on:
            return

        now_mono = float(time.monotonic())
        if hot_reload:
            if now_mono < float(getattr(self, "_retrained_chord_markov_next_check_monotonic", 0.0) or 0.0):
                return
            reload_iv = max(0.05, float(reload_iv))
            self._retrained_chord_markov_next_check_monotonic = now_mono + reload_iv

        p = Path(raw_path).expanduser()
        if not p.exists() or not p.is_file():
            if not hot_reload:
                logger.warning("Retrained chord Markov file not found: %s", str(p))
            return
        try:
            st = p.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(float(st.st_mtime) * 1e9)))
        except Exception:
            mtime_ns = None

        if hot_reload:
            try:
                loaded_path = str(getattr(self, "_retrained_chord_markov_path_loaded", "") or "")
                loaded_mtime = getattr(self, "_retrained_chord_markov_mtime_ns", None)
            except Exception:
                loaded_path = ""
                loaded_mtime = None
            if loaded_path == str(p) and loaded_mtime is not None and mtime_ns is not None and int(loaded_mtime) == int(mtime_ns):
                return

        parts = load_chord_retrained_pickle(p, hot_reload=hot_reload)
        if parts is None:
            return
        degree, bucket, global_degree, global_bucket = parts

        if degree is not None:
            self.chord_markov = degree
        if bucket is not None:
            self.chord_markov_bucket = bucket
        if getattr(self, "global_chord_markov", None) is not None and global_degree is not None:
            self.global_chord_markov = global_degree
        if getattr(self, "global_chord_markov_bucket", None) is not None and global_bucket is not None:
            self.global_chord_markov_bucket = global_bucket

        self._retrained_chord_markov_loaded_ok = True
        self._retrained_chord_markov_path_loaded = str(p)
        self._retrained_chord_markov_mtime_ns = int(mtime_ns) if mtime_ns is not None else None
        if hot_reload:
            logger.info("Hot-reloaded retrained chord Markov model: %s", str(p))
        else:
            logger.info("Loaded retrained chord Markov model: %s", str(p))

    def reseed(self, seed: int) -> None:
        """
        Set deterministic seed for composition-level randomness.

        We seed both the generator-local RNG (preferred) and Python's module-level
        RNG as a best-effort to cover legacy call sites that still use `random`.
        """
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        try:
            self.event_pipeline.set_rng(self.rng)
        except Exception:
            pass
        # Keep Markov melody generator modules in sync with the new RNG.
        try:
            if hasattr(self, "melody_gen") and getattr(self.melody_gen, "rng", None) is not self.rng:
                self.melody_gen.rng = self.rng
            if hasattr(self, "melody_gen") and hasattr(self.melody_gen, "note_gen"):
                self.melody_gen.note_gen.rng = self.rng
            if hasattr(self, "melody_gen") and hasattr(self.melody_gen, "motif"):
                self.melody_gen.motif.rng = self.rng
            if hasattr(self, "melody_gen") and hasattr(self.melody_gen, "post"):
                try:
                    self.melody_gen.post.rng = self.rng
                except Exception:
                    pass
            # Markov core models (interval/rhythm/phrase + contour/role variants).
            mk = getattr(getattr(self, "melody_gen", None), "markov", None)
            if mk is not None:
                for m in (getattr(mk, "interval", None), getattr(mk, "rhythm", None), getattr(mk, "phrase", None)):
                    if m is not None and hasattr(m, "rng"):
                        m.rng = self.rng
                cim = getattr(mk, "contour_interval_models", None) or {}
                for _k, m in getattr(cim, "items", lambda: [])():
                    if m is not None and hasattr(m, "rng"):
                        m.rng = self.rng
                rim = getattr(mk, "role_interval_models", None) or {}
                for _k, m in getattr(rim, "items", lambda: [])():
                    if m is not None and hasattr(m, "rng"):
                        m.rng = self.rng
            # Chord Markov models.
            for m in (getattr(self, "chord_markov", None), getattr(self, "global_chord_markov", None)):
                if m is not None and hasattr(m, "rng"):
                    m.rng = self.rng
        except Exception:
            pass
        try:
            from audiogen_core.repro import seed_everything

            seed_everything(self.seed)
        except Exception:
            # Fallback for minimal environments.
            try:
                random.seed(self.seed)
            except Exception:
                pass

    def deterministic_rng(self, *tokens: Any) -> random.Random:
        """
        Deterministic RNG for micro-choices (timing/comping/etc.) keyed by the current
        composition seed + provided tokens.
        """
        base = int(self.seed) if getattr(self, "seed", None) is not None else 0
        h = hashlib.blake2b(digest_size=8)
        h.update(str(base).encode("utf-8", errors="ignore"))
        for t in tokens:
            h.update(b"|")
            h.update(str(t).encode("utf-8", errors="ignore"))
        s64 = int.from_bytes(h.digest(), "little", signed=False)
        return random.Random(int(s64))

    def chord_markov_probabilities(
        self,
        context: List[str],
        temperature: float,
        *,
        bar_index: Optional[int] = None,
        section_role: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Return chord Markov probabilities with optional degree-aware backoff.

        - When `CONFIG.composition.harmony_markov_use_degree_tokens` is False (default),
          this is equivalent to `self.chord_markov.get_probabilities(...)`.
        - When True, `self.chord_markov` is treated as the degree-aware model and
          `self.chord_markov_bucket` as the fallback bucket model; we blend them.
        """
        use_degree = resolve_config("composition", "harmony_markov_use_degree_tokens", False, bool)
        alpha = resolve_config("composition", "harmony_markov_degree_backoff_blend", 0.35, float)
        dbg = resolve_config("composition", "harmony_markov_debug_trace_enabled", False, bool)
        alpha = max(0.0, min(1.0, float(alpha)))

        # Always compute primary probs (bucket-only by default).
        primary = {}
        try:
            primary = self.chord_markov.get_probabilities(list(context or []), float(temperature))
        except Exception:
            primary = {}
        if not use_degree:
            out0 = dict(primary or {})
            if dbg:
                self._maybe_record_harmony_markov_debug(
                    out0,
                    temperature=float(temperature),
                    use_degree_tokens=False,
                    backoff_alpha=float(alpha),
                    bar_index=bar_index,
                    section_role=section_role,
                )
            return out0

        # Backoff: compute bucket probs from bucketized context.
        try:
            bucket_ctx = [self.chord_planner._token_bucket(t) for t in list(context or [])]
        except Exception:
            bucket_ctx = list(context or [])
        fallback = {}
        try:
            fallback_model = getattr(self, "chord_markov_bucket", None)
            if fallback_model is not None:
                fallback = fallback_model.get_probabilities(bucket_ctx, float(temperature))
        except Exception:
            fallback = {}

        if not primary:
            out1 = dict(fallback or {})
            if dbg:
                self._maybe_record_harmony_markov_debug(
                    out1,
                    temperature=float(temperature),
                    use_degree_tokens=True,
                    backoff_alpha=float(alpha),
                    bar_index=bar_index,
                    section_role=section_role,
                )
            return out1
        if not fallback or alpha <= 1e-9:
            out2 = dict(primary)
            if dbg:
                self._maybe_record_harmony_markov_debug(
                    out2,
                    temperature=float(temperature),
                    use_degree_tokens=True,
                    backoff_alpha=float(alpha),
                    bar_index=bar_index,
                    section_role=section_role,
                )
            return out2
        # Blend toward bucket model while preserving degree-token identity.  A raw
        # probability union would reintroduce bare bucket tokens into degree mode;
        # instead, distribute each bucket's fallback mass across matching degree
        # tokens according to the primary within-bucket ratios.
        primary_by_bucket: Dict[str, List[Tuple[str, float]]] = {}
        for tok, prob in dict(primary).items():
            try:
                b = self.chord_planner._token_bucket(str(tok))
            except Exception:
                b = str(tok)
            primary_by_bucket.setdefault(str(b), []).append((str(tok), float(prob)))
        out = {}
        for bucket, items in primary_by_bucket.items():
            bucket_total = sum(max(0.0, float(v)) for _, v in items)
            fallback_mass = max(0.0, float(fallback.get(bucket, 0.0) or 0.0))
            for tok, prob in items:
                share = (float(prob) / bucket_total) if bucket_total > 1e-12 else (1.0 / float(max(1, len(items))))
                out[str(tok)] = ((1.0 - float(alpha)) * float(prob)) + (float(alpha) * fallback_mass * float(share))
        # If the degree model has no representative for a fallback bucket, keep
        # that bucket as a final safety valve.
        for bucket, prob in dict(fallback).items():
            if str(bucket) not in primary_by_bucket:
                out[str(bucket)] = out.get(str(bucket), 0.0) + float(alpha) * max(0.0, float(prob))
        total = float(sum(out.values()))
        if total > 1e-12:
            out = {k: float(v) / total for k, v in out.items() if float(v) > 0.0}
        else:
            out = blend_with_backoff(dict(primary), dict(fallback), alpha=float(alpha))
        if dbg:
            self._maybe_record_harmony_markov_debug(
                out,
                temperature=float(temperature),
                use_degree_tokens=True,
                backoff_alpha=float(alpha),
                bar_index=bar_index,
                section_role=section_role,
            )
        return out

    def _maybe_record_harmony_markov_debug(
        self,
        probs: Dict[str, float],
        *,
        temperature: float,
        use_degree_tokens: bool,
        backoff_alpha: float,
        bar_index: Optional[int],
        section_role: Optional[str],
    ) -> None:
        """
        Best-effort debug capture of Markov chord distribution (does not affect sampling).
        Stored on the generator so SectionPlanner can export it in `debug_trace_by_bar`.
        """
        if bar_index is None:
            return
        try:
            bi = int(bar_index)
        except Exception:
            return
        if bi < 0:
            return
        try:
            # Compute entropy (base-2) and top-k tokens.
            top = top_k(dict(probs or {}), k=5)
            ent = entropy_bits(dict(probs or {}))
        except Exception:
            top = []
            ent = 0.0
        try:
            trace = getattr(self, "_debug_harmony_markov_trace_by_bar", None)
        except Exception:
            trace = None
        if not isinstance(trace, list):
            trace = []
        while len(trace) <= bi:
            trace.append({})
        trace[bi] = {
            "enabled": True,
            "use_degree_tokens": bool(use_degree_tokens),
            "backoff_alpha": float(backoff_alpha),
            "temperature": float(temperature),
            "section_role": str(section_role or ""),
            "entropy_bits": float(ent),
            "top5": [(k, float(v)) for k, v in list(top)],
        }
        try:
            setattr(self, "_debug_harmony_markov_trace_by_bar", trace)
        except Exception:
            pass

    def _train_chord_markovs_from_emotion_pools(self) -> None:
        """
        Train chord Markov(s) from the in-repo emotion chord progression pools.

        This makes the chord Markov probabilities reflect the curated progressions in
        `data/music_data.py` (EmotionProfile.chord_progressions + cadence_progressions).
        It is lightweight and safe to run at startup.
        """
        try:
            from data.music_data import EMOTIONS
            from data.training_corpus import get_chord_sequences
        except Exception:
            return
        # Degree token corpus (will serialize to buckets when degree tokens are disabled).
        names = tuple(str(getattr(e, "name", "") or "").strip().lower() for e in list(EMOTIONS or []) if getattr(e, "name", None))
        sequences, weights = get_chord_sequences(names, token_mode="degree", include_cadences=True)
        bucket_sequences, bucket_weights = get_chord_sequences(names, token_mode="bucket", include_cadences=True)
        if not sequences and not bucket_sequences:
            return

        try:
            if sequences:
                self.chord_markov.train(sequences, sequence_weights=weights)
        except Exception:
            pass
        # Train bucket model (always), used for backoff when degree tokens are enabled.
        try:
            if bucket_sequences:
                self.chord_markov_bucket.train(bucket_sequences, sequence_weights=bucket_weights)
        except Exception:
            pass
        if self.global_chord_markov is not None:
            try:
                if sequences:
                    self.global_chord_markov.train(sequences, sequence_weights=weights)
            except Exception:
                pass
        if self.global_chord_markov_bucket is not None:
            try:
                if bucket_sequences:
                    self.global_chord_markov_bucket.train(bucket_sequences, sequence_weights=bucket_weights)
            except Exception:
                pass

    @staticmethod
    def _config_ai_value(name: str, default):
        return resolve_config("ai", name, default)
    @contextlib.contextmanager
    def temporary_settings(self, **overrides: Any) -> Iterator[None]:
        """
        Temporarily override generator attributes during a generation call.

        This avoids leaving the `CompositionGenerator` in a partially-mutated state
        if section generation is ever run concurrently (e.g. background pre-gen).
        """
        previous: Dict[str, Any] = {}
        missing = object()
        try:
            for name, value in overrides.items():
                previous[name] = getattr(self, name, missing)
                setattr(self, name, value)
            yield
        finally:
            for name, old in previous.items():
                if old is missing:
                    try:
                        delattr(self, name)
                    except Exception:
                        # Best-effort: attribute may not be deletable; restore by ignoring.
                        pass
                else:
                    setattr(self, name, old)

    @contextlib.contextmanager
    def snapshot_settings(self, *names: str) -> Iterator[None]:
        """
        Snapshot/restore a set of attributes without changing them upfront.

        Use this when a call site performs multiple mutations over time and we
        still want a clean rollback even if an exception occurs.
        """
        previous: Dict[str, Any] = {}
        missing = object()
        try:
            for name in names:
                previous[name] = getattr(self, name, missing)
            yield
        finally:
            for name, old in previous.items():
                if old is missing:
                    try:
                        delattr(self, name)
                    except Exception:
                        pass
                else:
                    setattr(self, name, old)

    # ------------------------------------------------------------------
    # Cache reset
    # ------------------------------------------------------------------
    def reset_caches(self):
        self._chord_validation_cache.clear()
        self.chord_utils.chord_symbol_to_notes_cached.cache_clear()

    def reset_song_arrangement_state(self) -> None:
        """Clear per-song state (call before a new arranged timeline)."""
        self._song_motif_hook_seeded = False
        self._chorus_hook_memory = None
        try:
            self.song_memory.reset()
        except Exception:
            pass
        self._bass_motif_families = {}
        self.motif_plan.reset()
        # Clear short-term recency memory so the same seed replays identically.
        for name in (
            "recent_section_openings",
            "recent_section_chord_signatures",
            "recent_melody_openings",
            "recent_phrase_contour_signatures",
        ):
            try:
                v = getattr(self, name, None)
                if v is not None and hasattr(v, "clear"):
                    v.clear()
            except Exception:
                pass
        # Reset Markov melody per-song memories (phrase repetition + extracted motifs).
        try:
            mg = getattr(self, "melody_gen", None)
            if mg is not None and hasattr(mg, "phrase_memory"):
                pm = getattr(mg, "phrase_memory", None)
                if isinstance(pm, dict):
                    pm.clear()
            mm = getattr(getattr(mg, "motif", None), "motif_library", None)
            motifs = getattr(mm, "motifs", None) if mm is not None else None
            if isinstance(motifs, list):
                motifs.clear()
        except Exception:
            pass

    def try_seed_first_verse_motif_hook(self, plan: SectionPlan, section_index: int) -> None:
        """
        Force-add one motif from the opening of the first `a` section into the library
        so returns do not depend on repeated patterns (MotifLibrary min_occurrences).
        """
        if getattr(self, "_song_motif_hook_seeded", False):
            return
        seq = self.arrangement_policy._FORM_SEQUENCES.get(self.arrangement_policy.form_mode)
        if not seq:
            seq = self.arrangement_policy._FORM_SEQUENCES["default"]
        try:
            first_a = next(i for i, r in enumerate(seq) if r == "a")
        except StopIteration:
            return
        if section_index != first_a:
            return
        emotion = plan.emotion
        scale = getattr(emotion, "scale_intervals", None) or []
        if not scale:
            return
        beats_per_bar = float(plan.beats_per_bar)
        cap_beat = min(beats_per_bar * 2.0, float(plan.bars) * beats_per_bar)
        scale_pcs = [int(iv) % 12 for iv in scale]
        _hp = getattr(plan, "harmonic_plan", None)
        if _hp is not None:
            try:
                _hp.validate()
                roots = list(_hp.roots)
                chords = list(_hp.chords)
            except Exception:
                roots = plan.roots
                chords = plan.chords
        else:
            roots = plan.roots
            chords = plan.chords
        ml = int(self.melody_gen.motif.motif_library.motif_length)
        degree_pairs: List[Tuple[int, float]] = []
        for ev in plan.melody_events:
            if len(ev) != 6 or int(ev[0]) != 2:
                continue
            start = float(ev[3])
            if start >= cap_beat:
                break
            bar = int(start // beats_per_bar)
            if bar >= len(roots):
                continue
            midi = ev[1]
            if not isinstance(midi, int):
                continue
            root = int(roots[bar])
            pc = int(midi) % 12
            root_pc = root % 12
            rel_pc = (pc - root_pc) % 12
            if rel_pc not in scale_pcs:
                continue
            degree = scale_pcs.index(rel_pc)
            degree_pairs.append((degree, float(ev[4])))
        # Need ml+1 degrees to form ml intervals.
        if len(degree_pairs) < (ml + 1):
            return
        intervals = [degree_pairs[i + 1][0] - degree_pairs[i][0] for i in range(ml)]
        rhythms = [degree_pairs[i][1] for i in range(ml)]
        ctx = list(chords[: ml + 1]) if len(chords) >= ml + 1 else None
        added = self.melody_gen.motif.motif_library.add_motif(
            intervals,
            rhythms,
            source_emotion=emotion.name.lower(),
            chord_context=ctx,
            chord_degrees=None,
        )
        if not added:
            # Fallback: if the extracted opening is too trivial to pass the motif
            # library filters (common with repeated degrees / long holds), seed a
            # slightly more "shaped" hook by widening the window and nudging the
            # final step to create motion. This gives later sections something
            # concrete to recall.
            try:
                if len(degree_pairs) >= ml + 2:
                    seed = degree_pairs[: ml + 1]
                    intervals2 = [seed[i + 1][0] - seed[i][0] for i in range(ml)]
                    rhythms2 = [seed[i][1] for i in range(ml)]
                    if sum(abs(i) for i in intervals2) <= 1:
                        intervals2[-1] = intervals2[-1] + (1 if intervals2[-1] >= 0 else -1)
                    added = self.melody_gen.motif.motif_library.add_motif(
                        intervals2,
                        rhythms2,
                        source_emotion=emotion.name.lower(),
                        chord_context=list(chords[: ml + 1]) if len(chords) >= ml + 1 else None,
                        chord_degrees=None,
                    )
            except Exception:
                added = False
        if added:
            self._song_motif_hook_seeded = True

    def register_section_memory(
        self,
        chords: List[str],
        phrase_contours: List[str],
        melody_events: List[Tuple],
    ) -> None:
        if chords:
            chord_signature = tuple(chords[: min(4, len(chords))])
            self.recent_section_chord_signatures.append(chord_signature)
            self.recent_section_openings.append(self._simplify_chord_for_markov(chords[0]))
            # If this is the first section of the current song, remember its opening signature
            # per emotion so the next song in the same emotion can avoid reusing it.
            try:
                sm = getattr(self, "song_memory", None)
                sec_idx = getattr(sm, "last_section_index", None) if sm is not None else None
                if sec_idx is None:
                    # Fallback: some call sites may not use SongMemory.
                    plan = getattr(self, "_last_section_plan", None)
                    sec_idx = getattr(plan, "section_index", None) if plan is not None else None
                if int(sec_idx) == 0:
                    emo = getattr(self, "_last_generation_emotion", None)
                    emo_name = str(getattr(emo, "name", "") or "").strip().lower()
                    if emo_name:
                        self.last_song_opening_chord_signature_by_emotion[str(emo_name)] = tuple(chord_signature)
            except Exception:
                pass
        if phrase_contours:
            self.recent_phrase_contour_signatures.append(tuple(phrase_contours))
        if melody_events:
            opening_notes = tuple(
                int(event[1])
                for event in melody_events[:3]
                if len(event) == 6 and isinstance(event[1], int)
            )
            if opening_notes:
                self.recent_melody_openings.append(opening_notes)

        # Motif carryover: extract motifs from the generated lead melody and
        # add them to the motif library so later sections can recall them.
        # This works even when melody generation is event-based (midi notes),
        # by converting back into scale degrees per bar.
        try:
            if chords and melody_events and hasattr(self, "melody_gen"):
                emotion = getattr(self, "_emotion_for_last_section", None)
                if emotion is None:
                    # Best-effort: infer from last used melody emotion
                    emotion = getattr(self, "_last_generation_emotion", None)
                # If we can't infer, skip; runtime path will usually have it set.
                if emotion is not None and getattr(emotion, "scale_intervals", None):
                    beats_per_bar = 4.0
                    scale = list(emotion.scale_intervals)
                    scale_pcs = [iv % 12 for iv in scale]
                    # Reconstruct roots as pitch classes if needed (caller often passes symbolic chords only).
                    roots = [60 + 0] * len(chords)
                    if hasattr(self, "chord_planner") and hasattr(self.chord_planner, "owner"):
                        pass

                    # Attempt to use stored roots from last plan if present.
                    last_roots = getattr(self, "_last_section_roots", None)
                    if isinstance(last_roots, list) and len(last_roots) >= len(chords):
                        roots = last_roots[: len(chords)]

                    degree_melody = []
                    chord_ctx = []
                    for ev in melody_events:
                        if len(ev) != 6:
                            continue
                        channel, midi, _, start, dur, _ = ev
                        if channel != 2:
                            continue
                        if not isinstance(midi, int):
                            continue
                        bar = int(float(start) // beats_per_bar)
                        if bar < 0 or bar >= len(roots):
                            continue
                        root = int(roots[bar])
                        pc = int(midi) % 12
                        root_pc = root % 12
                        # Find closest scale degree for this pitch class relative to root.
                        rel_pc = (pc - root_pc) % 12
                        if rel_pc not in scale_pcs:
                            continue
                        degree = scale_pcs.index(rel_pc)
                        degree_melody.append((degree, float(dur)))
                        chord_ctx.append(chords[bar])

                    if len(degree_melody) >= 4:
                        self.melody_gen.motif.extract_from_melody(
                            degree_melody,
                            source_emotion=getattr(emotion, "name", "neutral").lower(),
                            chord_sequence=chord_ctx if len(chord_ctx) == len(degree_melody) else None,
                        )
        except Exception:
            logger.debug("Motif carryover extraction failed", exc_info=True)

    def apply_emotion_ranges_for_generation(self, emotion: EmotionProfile):
        # Single shared MIDI map for all emotions (sample-pack consistency); not read from music_data.
        del emotion
        RANGE_LIMITER.reset_to_defaults()

    # ------------------------------------------------------------------
    # Training hooks (purged in simplified project)
    # ------------------------------------------------------------------
    def train_for_emotion(self, emotion: EmotionProfile) -> None:
        """
        No-op in the simplified project.

        The original codebase supported dataset/training-assisted behaviors that
        precomputed per-emotion phrase models. We intentionally run pure Markov
        generation only now, but SectionPlanner still calls this hook.
        """
        del emotion
        return None

    @staticmethod
    def get_emotion_melody_params(emotion: EmotionProfile):
        """
        Return per-emotion melody generator parameters, with a small dynamic scaling
        layer so the "emotion feel" stays distinct even when global settings change.
        """
        base = dict(EMOTION_MELODY_PARAMS.get(getattr(emotion, "name", "").lower(), {}) or {})

        # Dynamic scaling: make higher-energy emotions express their interval/rhythm
        # biases a bit more strongly, and lower-energy ones slightly more gently.
        try:
            tempo_m = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
            dens = float(getattr(emotion, "density", 0.5) or 0.5)
        except Exception:
            tempo_m, dens = 1.0, 0.5
        tempo_m = max(0.5, min(2.0, float(tempo_m)))
        dens = max(0.2, min(1.0, float(dens)))
        energy01 = ((tempo_m - 0.5) / (2.0 - 0.5) + (dens - 0.2) / (1.0 - 0.2)) / 2.0
        energy01 = max(0.0, min(1.0, float(energy01)))

        # Emotion intensity drives the exponent on EMOTION_INTERVAL_BIAS / EMOTION_RHYTHM_BIAS
        # inside NoteGenerator; keep it bounded.
        try:
            ei = float(base.get("emotion_intensity", 1.0) or 1.0)
        except Exception:
            ei = 1.0
        ei *= (0.90 + 0.40 * float(energy01))
        base["emotion_intensity"] = float(max(0.8, min(2.8, ei)))

        # Cadence archetype: "avoid/suspended" should tolerate more non-chord tones
        # (otherwise the melody reads too resolved / "happy" even over tense harmony).
        try:
            from data.emotion_anchors import anchors_for_emotion

            cad = str(getattr(anchors_for_emotion(emotion), "cadence", "authentic") or "authentic").lower()
        except Exception:
            cad = "authentic"
        if cad in {"avoid", "suspended"}:
            try:
                base["enforce_chord_tones_prob"] = float(base.get("enforce_chord_tones_prob", 0.9) or 0.9) * 0.90
            except Exception:
                pass
            try:
                base["embellishment_prob"] = float(base.get("embellishment_prob", 0.2) or 0.2) * 0.90
            except Exception:
                pass
            try:
                base["repeat_penalty"] = float(base.get("repeat_penalty", 0.1) or 0.1) * 1.10
            except Exception:
                pass

        # Clamp probabilities if they exist.
        for k in ("motif_prob", "rest_prob", "enforce_phrase_structure_prob", "embellishment_prob", "enforce_chord_tones_prob", "phrase_repetition_prob", "motif_variation_prob"):
            if k in base:
                try:
                    base[k] = float(max(0.0, min(1.0, float(base[k]))))
                except Exception:
                    pass

        return base

    # ------------------------------------------------------------------
    # Chord simplification and restoration
    # ------------------------------------------------------------------
    def _simplify_chord_for_markov(self, chord: str) -> str:
        if 'maj' in chord:
            return 'maj'
        elif 'min' in chord or (len(chord) > 1 and chord[1] == 'm' and chord[0] != 'M'):
            return 'min'
        elif 'dim' in chord or 'ø' in chord or '°' in chord:
            return 'dim'
        elif 'aug' in chord or '+' in chord:
            return 'aug'
        elif 'sus' in chord:
            return 'sus'
        else:
            return 'dom'

    def _restore_chord_extension(self, base_chord: str, emotion_name: str) -> str:
        return self.chord_planner.restore_chord_extension(base_chord, emotion_name)

    @staticmethod
    def _midi_to_note_name(midi: int) -> str:
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        return notes[midi % 12]

    # ------------------------------------------------------------------
    # Global scale helpers
    # ------------------------------------------------------------------
    def _get_melody_emotion(self, emotion: EmotionProfile) -> EmotionProfile:
        return self.melody_manager.get_melody_emotion(emotion)

    def _quantize_to_scale(self, midi_note: int, emotion: EmotionProfile) -> int:
        scale_intervals = self.global_scale if self.global_scale is not None else emotion.scale_intervals
        # `scale_intervals` are defined relative to the section root/tonic (0..11),
        # not absolute pitch classes. Quantization must therefore offset by the
        # current section root pitch class, otherwise non-C roots drift "out of key".
        try:
            tonic_pc = int(getattr(self, "_section_root_pc", 0)) % 12
        except Exception:
            tonic_pc = 0
        scale_pcs = [int((tonic_pc + int(interval)) % 12) for interval in (scale_intervals or [])]
        note_pc = midi_note % 12
        closest_pc = min(scale_pcs, key=lambda pc: min(abs(note_pc - pc), 12 - abs(note_pc - pc)))
        diff = (closest_pc - note_pc) % 12
        if diff > 6:
            diff -= 12
        quantized = midi_note + diff
        return max(21, min(108, quantized))

    def _quantize_notes(self, notes: List[int], emotion: EmotionProfile) -> List[int]:
        return [self._quantize_to_scale(n, emotion) for n in notes]

    # ------------------------------------------------------------------
    # Humanization
    # ------------------------------------------------------------------
    def _clamp_event_payload(self, channel: int, notes):
        return self.event_pipeline.clamp_event_payload(channel, notes)

    def _validate_events(self, events: List[Tuple]) -> List[Tuple]:
        return self.event_pipeline.validate_events(events)

    def _humanize_events(self, events, humanization, scale=1.0, probability=None):
        if probability is None:
            probability = self.humanization_probability
        with self.perf_monitor.measure("humanize_events"):
            return self.event_pipeline.humanize_events(events, humanization, probability)

    def _voice_leading_cost(
        self,
        prev_notes,
        curr_notes,
        parallel_penalty: float = 50.0,
        crossing_penalty: float = 30.0,
        large_leap_penalty: float = 10.0,
        step_reward: float = -2.0,
        common_tone_reward: float = -3.0,
    ) -> float:
        return self.voice_leading_engine.voice_leading_cost(
            prev_notes,
            curr_notes,
            parallel_penalty,
            crossing_penalty,
            large_leap_penalty,
            step_reward,
            common_tone_reward,
        )

    def _get_possible_notes_for_part(
        self,
        part: str,
        chord: str,
        root: int,
        prev_notes: Optional[List[int]] = None,
    ):
        return self.voice_leading_engine.get_possible_notes_for_part(part, chord, root, prev_notes)

    def _enumerate_combinations(self, possibilities):
        return self.voice_leading_engine.enumerate_combinations(possibilities)

    def _optimise_voice_leading_global(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float = 4.0,
    ) -> Tuple[List[int], List[List[int]], List[int], List[int]]:
        return self.voice_leading_engine.optimise_global(chords, roots, bars, beats_per_bar)

    def _compute_voice_leading_per_bar(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        beats_per_bar: float = 4.0,
    ) -> Tuple[List[int], List[List[int]], List[int], List[int]]:
        chosen_bass = []
        chosen_chord = []
        chosen_melody = []
        chosen_harmony = []
        prev_notes = None

        for bar in range(bars):
            chord = chords[bar]
            root = roots[bar]

            if bar == 0:
                chord_notes = self._chord_voicing(chord, root, style='closed', prev_notes=None)
                bass_note = self._get_bass_chord_tones(chord, root)[0]
                all_notes = self._chord_symbol_to_notes(chord, root)
                melody_opts = [n for n in all_notes if n >= 60] or all_notes
                harmony_opts = [n for n in all_notes if 48 <= n < 72] or all_notes
                melody_note = melody_opts[-1] if melody_opts else root + 12
                harmony_note = harmony_opts[1] if len(harmony_opts) > 1 else root + 7
                prev_notes = {
                    'bass': [bass_note],
                    'chord': chord_notes,
                    'melody': [melody_note],
                    'harmony': [harmony_note],
                }
            else:
                possibilities = {}
                for part in ['bass', 'chord', 'melody', 'harmony']:
                    possibilities[part] = self._get_possible_notes_for_part(
                        part, chord, root, prev_notes.get(part)
                    )

                best_cost = float('inf')
                best_choice = None
                for comb in self._enumerate_combinations(possibilities):
                    cost = self._voice_leading_cost(prev_notes, comb)
                    if cost < best_cost:
                        best_cost = cost
                        best_choice = comb

                bass_note = best_choice['bass'][0]
                chord_notes = best_choice['chord']
                melody_note = best_choice['melody'][0]
                harmony_note = best_choice['harmony'][0]
                prev_notes = best_choice

            chosen_bass.append(bass_note)
            chosen_chord.append(chord_notes)
            chosen_melody.append(melody_note)
            chosen_harmony.append(harmony_note)

        return chosen_bass, chosen_chord, chosen_melody, chosen_harmony

    def _mel_durs(self, emo_name: str) -> List[float]:
        return self.melody_factory.mel_durs(emo_name)

    def _extract_root_and_quality(self, symbol: str) -> Tuple[str, str]:
        return self.chord_utils.extract_root_and_quality(symbol)

    def _chord_symbol_to_intervals(self, symbol: str) -> List[int]:
        return self.chord_utils.chord_symbol_to_intervals(symbol)

    def _validate_chord_symbol(self, symbol: str) -> bool:
        return self.chord_utils.validate_chord_symbol(symbol)

    def _apply_substitutions_to_progression(self, prog: List[str], prob: float) -> List[str]:
        return self.chord_utils.apply_substitutions_to_progression(prog, prob)

    def _chord_symbol_to_notes(self, symbol: str, root: int) -> List[int]:
        return self.chord_utils.chord_symbol_to_notes(symbol, root)

    def _chord_quality(self, symbol: str) -> str:
        return self.chord_utils.chord_quality(symbol)

    def _apply_voicing_style(self, intervals: List[int], style: str) -> List[int]:
        return self.chord_utils.apply_voicing_style(intervals, style)

    def _inversions(self, intervals: List[int], root: int, register: int = 4) -> List[List[int]]:
        return self.chord_utils.inversions(intervals, root, register)

    def _best_inversion(self, inversions: List[List[int]], prev_notes: List[int]) -> List[int]:
        return self.chord_utils.best_inversion(inversions, prev_notes)

    def _chord_voicing(
        self,
        symbol: str,
        root: int,
        style: str = 'closed',
        prev_notes: Optional[List[int]] = None,
        current_bass_note: Optional[int] = None,
        register: int = 4,
    ) -> List[int]:
        return self.chord_utils.chord_voicing(
            symbol, root, style=style, prev_notes=prev_notes,
            current_bass_note=current_bass_note, register=register
        )

    def _chord_voicing_with_voice_leading(
        self,
        symbol: str,
        root: int,
        prev_notes,
        style: str = 'closed',
    ) -> List[int]:
        return self.chord_utils.chord_voicing_with_voice_leading(symbol, root, prev_notes, style)

    def _blend_probabilities(self, markov_probs: dict, trans_probs: dict, weight: float) -> dict:
        return self.chord_utils.blend_probabilities(markov_probs, trans_probs, weight)

    def _find_best_note_numpy(self, upper_octave_notes: List[int], target_pc: int) -> int:
        return self.chord_utils.find_best_note_numpy(upper_octave_notes, target_pc)

    def _get_emotion_chord_vocabulary(self, emotion) -> set:
        return self.chord_utils.get_emotion_chord_vocabulary(emotion)

    def _apply_extension(self, chord: str, emotion) -> str:
        return self.chord_utils.apply_extension(chord, emotion)

    def _add_extensions(self, chords: List[str], emotion) -> List[str]:
        return self.chord_utils.add_extensions(chords, emotion)

    def _apply_modal_interchange(self, chords: List[str], emotion, key_mode: str = "major") -> List[str]:
        return self.chord_utils.apply_modal_interchange(chords, emotion, key_mode)

    def _add_secondary_dominants(self, chords: List[str], emotion) -> List[str]:
        return self.chord_utils.add_secondary_dominants(chords, emotion)

    def _apply_advanced_harmony(self, chords: List[str], emotion) -> List[str]:
        return self.chord_utils.apply_advanced_harmony(chords, emotion)

    def _mel_npb(self, emo_name: str) -> int:
        return self.melody_factory.mel_npb(emo_name)

    def _chord_degrees(self, chord: str, scale_len: int) -> Tuple[int, int, int, int]:
        return self.melody_factory.chord_degrees(chord, scale_len)

    def _mel_arpeggio_up(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_arpeggio_up(prog, scale_len, emo_name)

    def _mel_arpeggio_down(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_arpeggio_down(prog, scale_len, emo_name)

    def _mel_scale_run_up(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_scale_run_up(prog, scale_len, emo_name)

    def _mel_scale_run_down(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_scale_run_down(prog, scale_len, emo_name)

    def _mel_neighbor_ornament(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_neighbor_ornament(prog, scale_len, emo_name)

    def _mel_long_short(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_long_short(prog, scale_len, emo_name)

    def _mel_motivic_sequence(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_motivic_sequence(prog, scale_len, emo_name)

    def _mel_rocking_pedal(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_rocking_pedal(prog, scale_len, emo_name)

    def _mel_call_answer(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_call_answer(prog, scale_len, emo_name)

    def _mel_with_rests(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_with_rests(prog, scale_len, emo_name)

    def _mel_rhythmic_ostinato(self, prog, scale_len, emo_name):
        return self.melody_factory.mel_rhythmic_ostinato(prog, scale_len, emo_name)

    def _create_artificial_melodies(
        self, emotion: EmotionProfile
    ) -> Tuple[List[List[Tuple[int, float]]], List[List[str]], List[List[str]]]:
        cached = self._artificial_melody_cache.get(emotion.name)
        if cached is None:
            cached = self.melody_factory.create_artificial_melodies(emotion)
            self._artificial_melody_cache[emotion.name] = copy.deepcopy(cached)
        return copy.deepcopy(cached)

    # ------------------------------------------------------------------
    # Main generation
    # ------------------------------------------------------------------
    def generate_section(self,
                         emotion: EmotionProfile,
                         root_note: int = 60,
                         bars: int = 8,
                         key_changes: Optional[List[Tuple[int, int]]] = None,
                         temperature: float = 0.7,
                         target_notes_per_bar: float = 6.0,
                         melody_style: str = 'auto',
                         humanization_scale: float = 1.0,
                         chord_progression: Optional[List[str]] = None,
                         melody_styles: Optional[List[Tuple[int, str]]] = None,
                         section_index: int = 0,
                         transition_handoff_context: Optional[Dict[str, Any]] = None) -> List[Tuple]:
        prev = self._emotion_transition_handoff_ctx
        self._emotion_transition_handoff_ctx = transition_handoff_context
        try:
            # Optional low-overhead mtime-based hot-reload of retrained melody Markov.
            self._try_load_retrained_melody_markov(hot_reload=True)
            with self.perf_monitor.measure("generate_section_total"):
                return self.section_planner.build_section(
                    emotion=emotion,
                    root_note=root_note,
                    bars=bars,
                    key_changes=key_changes,
                    temperature=temperature,
                    target_notes_per_bar=target_notes_per_bar,
                    melody_style=melody_style,
                    humanization_scale=humanization_scale,
                    chord_progression=chord_progression,
                    melody_styles=melody_styles,
                    section_index=section_index,
                )
        finally:
            self._emotion_transition_handoff_ctx = prev

    def _prepare_section_events(self,
                                plan: SectionPlan,
                                temperature: float,
                                target_notes_per_bar: float,
                                melody_style: str,
                                melody_styles: Optional[List[Tuple[int, str]]],
                                section_index: int = 0) -> SectionPlan:
        return self.section_planner.prepare_section_events(
            plan,
            temperature,
            target_notes_per_bar,
            melody_style,
            melody_styles,
            section_index=section_index,
        )

    def _finalize_section_events(self,
                                 plan: SectionPlan,
                                 humanization_scale: float) -> SectionPlan:
        return self.section_planner.finalize_section_events(plan, humanization_scale)

    # ------------------------------------------------------------------
    # Chord progression generation (with anti‑stuck measures)
    # ------------------------------------------------------------------
    def _generate_bass_events(self,
                              chords: List[str],
                              roots: List[int],
                              bars: int,
                              beats_per_bar: float,
                              chosen_bass: List[int],
                              emotion: EmotionProfile) -> List[Tuple]:
        return self.harmony_manager.generate_bass_events(
            chords, roots, bars, beats_per_bar, chosen_bass, emotion
        )

    def _generate_chord_events(self,
                            chords: List[str],
                            roots: List[int],
                            bars: int,
                            beats_per_bar: float,
                            chosen_chord: List[List[int]],
                            emotion: EmotionProfile,
                            section_role: Optional[str] = None,
                            chord_rhythm_mult: float = 1.0,
                            chord_motion_mult: float = 1.0) -> List[Tuple]:
        return self.harmony_manager.generate_chord_events(
            chords, roots, bars, beats_per_bar, chosen_chord, emotion,
            section_role=section_role,
            chord_rhythm_mult=chord_rhythm_mult,
            chord_motion_mult=chord_motion_mult,
        )

    def _generate_melody_events(self,
                                emotion: EmotionProfile,
                                chords: List[str],
                                roots: List[int],
                                bars: int,
                                beats_per_bar: float,
                                temperature: float,
                                target_notes_per_bar: float,
                                melody_style: str,
                                melody_styles: Optional[List[Tuple[int, str]]],
                                chosen_bass: List[int],
                                chosen_melody: List[int],
                                chosen_chord: Optional[List[List[int]]] = None) -> List[Tuple]:
        from .harmonic_plan import HarmonicPlan

        hp = HarmonicPlan(
            chords=list(chords),
            roots=list(roots),
            bars=int(bars),
            beats_per_bar=float(beats_per_bar),
            chosen_bass=list(chosen_bass),
            chosen_melody=list(chosen_melody),
            chosen_chord=[list(row) for row in (chosen_chord or [])],
        )
        return self.melody_manager.generate_melody_events_from_harmonic_plan(
            emotion,
            hp,
            temperature,
            target_notes_per_bar,
            melody_style,
            melody_styles,
        )

    def _generate_melody_by_blocks(self,
                                   emotion: EmotionProfile,
                                   chords: List[str],
                                   roots: List[int],
                                   bars: int,
                                   beats_per_bar: float,
                                   temperature: float,
                                   target_notes_per_bar: float,
                                   melody_styles: List[Tuple[int, str]],
                                   chosen_melody: List[int],
                                   bass_notes_per_sixteenth: Optional[List[int]],
                                   total_quarter_beats: int) -> List[Tuple]:
        return self.melody_manager.generate_melody_by_blocks(
            emotion, chords, roots, bars, beats_per_bar, temperature,
            target_notes_per_bar, melody_styles, chosen_melody,
            bass_notes_per_sixteenth, total_quarter_beats
        )

    def _clamp_to_bass_register(self, midi_note: int) -> int:
        return self.bass_engine.clamp_to_bass_register(midi_note)

    def _get_bass_chord_tones(self, chord: str, root: int) -> List[int]:
        return self.bass_engine.get_bass_chord_tones(chord, root)

    def _generate_bass_line(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        emotion: EmotionProfile,
        beats_per_bar: float = 4.0,
        density: float = 1.0,
        base_style: str = 'simple',
        debug: bool = False,
    ) -> List[Tuple[int, float, float]]:
        return self.bass_engine.generate_bass_line(
            chords, roots, bars, emotion, beats_per_bar, density, base_style, debug
        )

    def _smooth_bass_line(
        self,
        events: List[Tuple[int, float, float]],
        chords: List[str],
        roots: List[int],
        beats_per_bar: float,
    ) -> List[Tuple[int, float, float]]:
        return self.bass_engine.smooth_bass_line(events, chords, roots, beats_per_bar)

    def _bass_note_to_events(
        self,
        bass_notes: List[Tuple[int, float, float]],
        channel: int = 0,
        velocity: int = 80,
    ) -> List[Tuple]:
        return self.bass_engine.bass_note_to_events(bass_notes, channel, velocity)

    def _get_drone_event(self, root_note: int, emotion: EmotionProfile,
                         beats_per_bar: float) -> Optional[Tuple]:
        always_on = resolve_config("composition", "drone_always_on", False, bool)
        fixed_midi = resolve_config("composition", "drone_fixed_midi", None)
        if (emotion.name.lower() == "relief") and not always_on:
            return None

        if self._drone_root_locked is None:
            # First call: lock the pitch and build the event
            locked = root_note
            # If user requested a fixed pitch, respect it.
            try:
                if fixed_midi is not None:
                    locked = int(fixed_midi)
            except Exception:
                locked = root_note
            # Otherwise, optionally quantize only at lock time (never changes later).
            if fixed_midi is None and self.global_scale is not None:
                locked = self._quantize_to_scale(locked, emotion)
            self._drone_root_locked = locked
            vel_m = stable_emotion_velocity_multiplier(emotion)
            drone_velocity = int(80 * vel_m)
            drone_duration = 1_000_000 * beats_per_bar   # effectively infinite
            # FIX: use locked as the midi field (was hardcoded 0 = C-2)
            self._drone_event = (4, locked, drone_velocity, 0.0,
                                 drone_duration, [locked])
            logger.info(
                f"Drone locked to MIDI {locked} — will not change with emotion or key."
            )

        if self._drone_emitted:
            # Already playing — don't send a second note-on
            return None

        self._drone_emitted = True
        return self._drone_event

    def reset_drone(self, *, hard: bool = False):
        self._drone_emitted = False
        if hard:
            self._drone_event = None
            self._drone_root_locked = None
            logger.info("Drone reset: root/payload cleared for next emotion or key.")
        else:
            logger.info("Drone re-arm: will re-emit on next section (pitch unchanged).")