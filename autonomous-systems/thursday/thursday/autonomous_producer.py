"""Thursday Autonomous Producer & Workflow Task Director.

Decomposes high-level natural language instructions into autonomous multi-step audio workflows:
Composition Orchestration (AudioGen) -> Stem Metadata Export -> Mix Decision & Rendering -> LTAS Match.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from audio_analysis.mixdown.mix_decision_engine import MixPlan, BusMixConfig
from audio_analysis.mixdown.ltas_matcher import generate_ltas_match_eq_bands

# composition.neural_phrase_generator imports torch, which is deliberately
# excluded from the shared project venv (the last Intel-macOS torch wheel
# is ABI-incompatible with NumPy 2.x -- see the root requirements.txt's own
# comment on this, and docs/ARCHITECTURE.md's dependency rule #7). This used
# to be a hard, module-level import here, which meant importing this file
# at all -- and therefore importing business/app/routes/thursday_routes.py,
# and therefore starting business/app/server.py -- would crash outright
# whenever torch wasn't cleanly importable in whatever venv happened to be
# active, taking down the entire website with it (confirmed via
# data/logs/website.log: repeated startup crashes on exactly this import
# chain). Deferred to first real use instead, matching the try/except
# ImportError pattern already used everywhere else in this codebase for
# optional cross-domain capabilities (e.g. server.py's `import
# audiogen_bridge`) -- a broken/unavailable autonomous-producer pipeline
# now fails just that one request, not the whole server.


class AutonomousProducerUnavailable(RuntimeError):
    """Raised when the torch-backed composition pipeline can't be loaded."""


def _prototype_not_implemented_response(instruction: str, genre: str, bpm: int) -> Dict[str, Any]:
    """Fail-closed response for a prototype pipeline that cannot yet perform
    the real work it describes.

    docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md and the
    companion platform master report found that
    ``ThursdayTaskDirector.run_autonomous_producer_pipeline`` reported four
    fixed stem filenames that were never written to disk and claimed
    completion of composition/mix/mastering work that never happened. Phase
    0 explicitly prohibits building the real pipeline in this pass; the safe
    outcome is to fail closed rather than fabricate a completed run.
    """
    return {
        "ok": False,
        "status": "NOT_IMPLEMENTED",
        "reason": "PROTOTYPE_ONLY",
        "owner_review_required": True,
        "instruction": instruction,
        "genre": genre,
        "bpm": bpm,
        "error": (
            "ThursdayTaskDirector is a prototype. It does not render audio, export "
            "stems, or produce a real mix -- no verifiable work occurred. This path is "
            "disabled to prevent reporting fabricated success. See "
            "docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md (P0-8) for the "
            "full finding; a real implementation is Phase 1+ scope, not this pass."
        ),
    }


def _load_composition_deps():
    try:
        from composition.groove_engine import get_groove_config
        from composition.neural_phrase_generator import NeuralPhraseGenerator
    except Exception as exc:  # ImportError, or torch's own ABI-mismatch crash
        raise AutonomousProducerUnavailable(
            f"Autonomous producer pipeline is unavailable (composition/torch dependency failed to load: {exc})"
        ) from exc
    return get_groove_config, NeuralPhraseGenerator


class ThursdayTaskDirector:
    """Autonomous Producer Task Director for Thursday."""

    def __init__(self):
        self._get_groove_config, NeuralPhraseGenerator = _load_composition_deps()
        self.phrase_generator = NeuralPhraseGenerator()

    def run_autonomous_producer_pipeline(
        self,
        instruction: str,
        genre: str = "lofi",
        bpm: int = 90,
        output_dir: Path | str | None = None,
    ) -> Dict[str, Any]:
        """Decompose producer goal and execute complete autonomous end-to-end pipeline.

        Parameters
        ----------
        instruction : str
            Producer instruction (e.g. "Create a 90 BPM Lo-Fi beat with 60% swing").
        genre : str
            Target genre style.
        bpm : int
            Tempo in BPM.
        output_dir : Path or str or None
            Output directory for generated multitrack stems.

        Returns
        -------
        Dict[str, Any]
            A fail-closed ``NOT_IMPLEMENTED``/``PROTOTYPE_ONLY`` summary.
            This method deliberately does not perform real audio rendering,
            groove/composition generation, stem export, or mixing -- see
            ``_prototype_not_implemented_response``.
        """
        return _prototype_not_implemented_response(instruction, genre, bpm)

    def _run_autonomous_producer_pipeline_prototype(
        self,
        instruction: str,
        genre: str = "lofi",
        bpm: int = 90,
        output_dir: Path | str | None = None,
    ) -> Dict[str, Any]:
        """The original prototype pipeline, preserved for owner inspection
        and any future real rebuild -- NOT reachable from
        ``run_autonomous_producer_pipeline`` (see docstring there) and NOT
        wired to any HTTP route or service. The stem filenames below are
        never written to disk; nothing here reflects real audio work. Do
        not call this directly outside of manual, owner-supervised
        inspection of the prototype.
        """
        pipeline_steps = []

        # Step 1: Composition & Groove Humanization
        groove_profile = self._get_groove_config(genre)
        prompt_events = [{"pitch": 60, "start_tick": 0, "duration_ticks": 240, "velocity": 80}]
        generated_phrase, latency_ms = self.phrase_generator.generate_phrase(
            prompt_events=prompt_events, num_notes=8, root_pitch=60
        )

        pipeline_steps.append({
            "step": 1,
            "stage": "composition_groove",
            "genre": genre,
            "swing_ratio": groove_profile.swing_ratio,
            "notes_generated": len(generated_phrase),
            "inference_latency_ms": latency_ms,
        })

        # Step 2: AutoMix Metadata Export
        stems_meta = {
            "full_drum_bus.wav": "full_drum_bus",
            "bass.wav": "bass",
            "lead_vocal.wav": "vocal",
            "synth_keys.wav": "synth_lead",
        }

        pipeline_steps.append({
            "step": 2,
            "stage": "automix_metadata_export",
            "stems_mapped": len(stems_meta),
            "roles": list(stems_meta.values()),
        })

        # Step 3: Mix Decision & Rendering Configuration
        mix_plan = MixPlan(
            stems=[],
            bus=BusMixConfig(),
            genre=genre,
            target_lufs=-14.0,
            apply_masking_corrections=True,
            apply_proactive_crest_reduction=True,
        )

        pipeline_steps.append({
            "step": 3,
            "stage": "mix_decision_rendering",
            "target_lufs": mix_plan.target_lufs,
            "mid_side_vocal_carve": True,
            "parallel_drum_compression": True,
        })

        # Step 4: 40-Band LTAS Spectrum Match & Safety Audit
        sample_bands = [-18.0 + (i * 0.1) for i in range(40)]
        eq_recs = generate_ltas_match_eq_bands(sample_bands, genre=genre)

        pipeline_steps.append({
            "step": 4,
            "stage": "ltas_spectrum_matching",
            "eq_recommendations": eq_recs,
            "true_peak_safety_margin_dbtp": -1.0,
        })

        summary = (
            f"🤖 Thursday Autonomous Producer completed 4-stage pipeline for '{instruction}'.\n"
            f"• Genre: {genre.upper()} ({bpm} BPM) with {int(groove_profile.swing_ratio * 100)}% 16th swing.\n"
            f"• AutoMix Mid-Side Lead Vocal Carving & Parallel Drum Compression active.\n"
            f"• Master LTAS 40-band spectrum matched to target curve."
        )

        return {
            "ok": True,
            "instruction": instruction,
            "genre": genre,
            "bpm": bpm,
            "steps_completed": len(pipeline_steps),
            "pipeline_steps": pipeline_steps,
            "summary": summary,
        }
