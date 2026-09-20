"""Thursday Autonomous Commercial Dispatcher.

Main agentic business orchestrator linking composition, multitrack stem export,
AutoMix rendering, LTAS spectrum matching, KENN technical advisor sync,
and client invoice & delivery packaging.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict

from composition.groove_engine import get_groove_config
from composition.neural_phrase_generator import NeuralPhraseGenerator
from audio_analysis.mixdown.mix_decision_engine import MixPlan, BusMixConfig
from audio_analysis.mixdown.ltas_matcher import generate_ltas_match_eq_bands
from kenn.autonomous_agent import KennAutonomousAgent

REPO_ROOT = Path(__file__).resolve().parents[1]
DELIVERY_DIR = REPO_ROOT / "data" / "commercial_deliveries"


def _prototype_not_implemented_response(project_title: str, client_name: str) -> Dict[str, Any]:
    """Fail-closed response for a prototype pipeline that cannot yet perform
    the real work it describes.

    docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md and the
    companion platform master report found that
    ``ThursdayCommercialDispatcher.execute_commercial_job`` reported every
    stage as ``"completed"`` unconditionally: four fixed stem filenames were
    never written to disk, the invoice total ($450.00) and true-peak
    (-1.0 dBTP) were hardcoded literals, and ``master_lufs`` simply echoed
    the input parameter back -- none of it reflected real audio work. If
    this were ever surfaced to a real client as "your job was processed,"
    the output would be fictional. Phase 0 explicitly prohibits building the
    real commercial pipeline in this pass; the safe outcome is to fail
    closed rather than fabricate a completed job.
    """
    return {
        "ok": False,
        "status": "NOT_IMPLEMENTED",
        "reason": "PROTOTYPE_ONLY",
        "owner_review_required": True,
        "client_name": client_name,
        "project_title": project_title,
        "error": (
            "ThursdayCommercialDispatcher is a prototype. It does not render audio, "
            "export stems, run AutoMix, generate an invoice, or produce a client "
            "delivery -- no verifiable work occurred. This path is disabled to prevent "
            "reporting fabricated success. See "
            "docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md (P0-8) for the "
            "full finding; a real implementation is Phase 1+ scope, not this pass."
        ),
    }


class ThursdayCommercialDispatcher:
    """Main Agentic Business Orchestrator for Thursday."""

    def __init__(self):
        self.phrase_generator = NeuralPhraseGenerator()
        self.kenn_agent = KennAutonomousAgent()

    def execute_commercial_job(
        self,
        client_name: str,
        project_title: str,
        genre: str = "pop",
        bpm: int = 120,
        target_lufs: float = -14.0,
    ) -> Dict[str, Any]:
        """Execute complete 5-stage commercial production, mix, compliance, and delivery workflow.

        Parameters
        ----------
        client_name : str
            Name of client or record label.
        project_title : str
            Project title.
        genre : str
            Target musical genre.
        bpm : int
            Tempo in BPM.
        target_lufs : float
            Target integrated LUFS loudness.

        Returns
        -------
        Dict[str, Any]
            A fail-closed ``NOT_IMPLEMENTED``/``PROTOTYPE_ONLY`` manifest.
            This method deliberately does not perform real audio rendering,
            stem export, mixing, invoicing, or delivery -- see
            ``_prototype_not_implemented_response``.
        """
        return _prototype_not_implemented_response(project_title, client_name)

    def _execute_commercial_job_prototype(
        self,
        client_name: str,
        project_title: str,
        genre: str = "pop",
        bpm: int = 120,
        target_lufs: float = -14.0,
    ) -> Dict[str, Any]:
        """The original prototype pipeline, preserved for owner inspection
        and any future real rebuild -- NOT reachable from
        ``execute_commercial_job`` (see docstring there) and NOT wired to
        any HTTP route or service. Every "completed" stage below is
        fabricated: no stem file is written, the invoice total and true-peak
        are hardcoded literals, and ``master_lufs`` merely echoes the input
        parameter. Do not call this directly outside of manual, owner-
        supervised inspection of the prototype.
        """
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        stages = []

        # Stage 1: AudioGen Composition Orchestration
        groove = get_groove_config(genre)
        prompt_events = [{"pitch": 60, "start_tick": 0, "duration_ticks": 240, "velocity": 80}]
        phrase, latency_ms = self.phrase_generator.generate_phrase(prompt_events, num_notes=8, root_pitch=60)

        stages.append({
            "stage": 1,
            "name": "AudioGen Composition",
            "status": "completed",
            "details": f"Generated phrase ({len(phrase)} notes, {int(groove.swing_ratio * 100)}% 16th swing, {latency_ms:.1f}ms latency)",
        })

        # Stage 2: Stem Metadata Export
        stems_meta = {
            "full_drum_bus.wav": "full_drum_bus",
            "bass.wav": "bass",
            "lead_vocal.wav": "vocal",
            "synth_keys.wav": "synth_lead",
        }
        stages.append({
            "stage": 2,
            "name": "Multitrack Stem Export",
            "status": "completed",
            "details": f"Exported {len(stems_meta)} multitrack WAV stems with automix_meta.json roles",
        })

        # Stage 3: AutoMix Decision & Rendering
        mix_plan = MixPlan(
            stems=[],
            bus=BusMixConfig(),
            genre=genre,
            target_lufs=target_lufs,
            apply_masking_corrections=True,
            apply_proactive_crest_reduction=True,
        )
        stages.append({
            "stage": 3,
            "name": "AutoMix DSP Processing",
            "status": "completed",
            "details": f"Mid-Side vocal carving (1.5 kHz) & parallel drum compression applied @ {mix_plan.target_lufs} LUFS",
        })

        # Stage 4: 40-Band LTAS Spectrum Match & KENN Audit Sync
        sample_bands = [-18.0 + (i * 0.1) for i in range(40)]
        eq_recs = generate_ltas_match_eq_bands(sample_bands, genre=genre)

        self.kenn_agent.run_agent_loop(
            user_prompt=f"Audit mix compliance for {genre} project '{project_title}'",
        )

        stages.append({
            "stage": 4,
            "name": "LTAS Spectrum & KENN Audit Sync",
            "status": "completed",
            "details": f"Matched 40-band LTAS spectrum curve; KENN audit executed ({len(eq_recs)} EQ corrections)",
        })

        # Stage 5: Invoice & Commercial Client Delivery Package
        invoice_id = f"INV-{uuid.uuid4().hex[:6].upper()}"
        stages.append({
            "stage": 5,
            "name": "Invoice & Client Delivery Packaging",
            "status": "completed",
            "details": f"Generated Invoice {invoice_id} ($450.00 USD) and commercial delivery manifest",
        })

        job_package = {
            "job_id": job_id,
            "client_name": client_name,
            "project_title": project_title,
            "genre": genre,
            "bpm": bpm,
            "invoice_id": invoice_id,
            "total_fee_usd": 450.00,
            "stages_completed": len(stages),
            "stages": stages,
            "master_lufs": target_lufs,
            "true_peak_dbtp": -1.0,
            "delivery_status": "ready_for_download",
        }

        # Write delivery manifest
        DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
        manifest_file = DELIVERY_DIR / f"{job_id}_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(job_package, f, indent=2)

        return {
            "ok": True,
            "job_id": job_id,
            "client_name": client_name,
            "project_title": project_title,
            "invoice_id": invoice_id,
            "manifest_file": str(manifest_file),
            "summary": (
                f"🚀 Thursday Agentic Orchestrator completed commercial job '{project_title}' for client '{client_name}'.\n"
                f"• All 5 stages completed: Composition -> Stem Export -> AutoMix -> LTAS Match -> Invoice ({invoice_id}).\n"
                f"• Master delivered at {target_lufs} LUFS (-1.0 dBTP ceiling)."
            ),
            "job_package": job_package,
        }
