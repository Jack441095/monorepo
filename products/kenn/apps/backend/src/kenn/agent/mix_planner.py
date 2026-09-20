"""Autonomous Chain-of-Thought Mix Planner for KENN.

Decomposes complex, multi-objective audio engineering requests into an ordered,
executable Directed Acyclic Graph (DAG) of recipe steps:
1. Diagnostics & telemetry verification
2. Surgical corrections (EQ notch, resonance carving, de-essing)
3. Bus & routing dynamics (sidechain ducking, parallel glue)
4. Master processing (limiting ceiling clamp, LUFS target)
5. Loudness-matched A/B verification
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from kenn.audio_telemetry import AudioTelemetryFrame, get_telemetry_manager


@dataclass
class MixStep:
    id: str
    name: str
    track: str
    plugin: str
    action: str
    params: Dict[str, Any]
    why: str
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"  # "pending", "ready", "executing", "completed"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MixPlan:
    plan_id: str
    goal: str
    steps: List[MixStep]
    telemetry_snapshot: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "telemetry_snapshot": self.telemetry_snapshot,
        }


class MixPlanner:
    """Generates structured DAG mix plans based on user intent and live audio telemetry."""

    def create_plan(
        self,
        query: str,
        telemetry: Optional[AudioTelemetryFrame] = None,
        context: str = "",
    ) -> MixPlan:
        """Analyze query and telemetry to produce a multi-step DAG plan."""
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        q_lower = query.lower()

        if telemetry is None:
            telemetry = get_telemetry_manager().get_latest()

        steps: List[MixStep] = []
        step_idx = 1

        # 1. Telemetry Diagnostic Step
        if telemetry:
            anomalies = get_telemetry_manager().diagnose_anomalies(telemetry)
            if anomalies:
                steps.append(
                    MixStep(
                        id=f"step_{step_idx}_diag",
                        name="Telemetry Diagnostic Check",
                        track="Master",
                        plugin="Live Metrics Engine",
                        action="verify_telemetry",
                        params={
                            "true_peak": telemetry.true_peak_dbtp,
                            "integrated_lufs": telemetry.integrated_lufs,
                            "anomalies": anomalies,
                        },
                        why=f"Identified {len(anomalies)} mix anomalies before applying processing.",
                        depends_on=[],
                    )
                )
                step_idx += 1

        # 2. Vocal / Mud Carving
        if any(w in q_lower for w in ("mud", "box", "vocal", "clarity", "250", "300", "resonance")):
            prev_id = steps[-1].id if steps else ""
            steps.append(
                MixStep(
                    id=f"step_{step_idx}_surgical_eq",
                    name="Carve Low-Mid Boxiness",
                    track="Vocal",
                    plugin="Ableton EQ Eight / FabFilter Pro-Q 3",
                    action="set_param",
                    params={"band": 3, "filter_type": "bell", "freq_hz": 310, "gain_db": -2.5, "q": 2.2},
                    why="Cleans up room resonance and proximity effect mud without hollowing fundamental tone.",
                    depends_on=[prev_id] if prev_id else [],
                )
            )
            step_idx += 1

        # 3. Sibilance / De-Essing
        if any(w in q_lower for w in ("harsh", "sibilance", "deess", "de-ess", "bright")):
            prev_id = steps[-1].id if steps else ""
            steps.append(
                MixStep(
                    id=f"step_{step_idx}_deess",
                    name="Dynamic De-Essing",
                    track="Vocal",
                    plugin="De-Esser / Dynamic EQ",
                    action="set_param",
                    params={"freq_hz": 6200, "threshold_db": -18.0, "range_db": -4.0, "mode": "split_band"},
                    why="Tames piercing 's' and 't' consonants transparently on loud vocal passages.",
                    depends_on=[prev_id] if prev_id else [],
                )
            )
            step_idx += 1

        # 4. Sidechain Routing
        if any(w in q_lower for w in ("sidechain", "kick", "bass", "duck", "pump")):
            prev_id = steps[-1].id if steps else ""
            steps.append(
                MixStep(
                    id=f"step_{step_idx}_sidechain",
                    name="Sidechain Kick-to-Bass Ducking",
                    track="Bass",
                    plugin="Ableton Compressor",
                    action="route_sidechain",
                    params={"source_track": "Kick", "attack_ms": 2.0, "release_ms": 75.0, "ratio": 4.0},
                    why="Carves immediate pocket for kick transient, letting both sub elements hit clean.",
                    depends_on=[prev_id] if prev_id else [],
                )
            )
            step_idx += 1

        # 5. Master True Peak & Limiter Ceiling Clamp
        if any(w in q_lower for w in ("master", "limit", "ceiling", "loudness", "lufs", "clip")) or (telemetry and telemetry.true_peak_dbtp > -0.2):
            prev_id = steps[-1].id if steps else ""
            steps.append(
                MixStep(
                    id=f"step_{step_idx}_limiter_ceiling",
                    name="Clamp True Peak Ceiling",
                    track="Master",
                    plugin="Ableton Limiter / FabFilter Pro-L 2",
                    action="clamp_ceiling",
                    params={"ceiling_dbtp": -1.0, "lookahead_ms": 1.5, "oversampling": "4x"},
                    why="Prevents inter-sample clipping on streaming lossy codecs (Spotify/Apple Music).",
                    depends_on=[prev_id] if prev_id else [],
                )
            )
            step_idx += 1

        # 6. Final Loudness-Matched A/B Audition Step
        prev_id = steps[-1].id if steps else ""
        steps.append(
            MixStep(
                id=f"step_{step_idx}_audition",
                name="Zero-Bias Loudness-Matched A/B Audition",
                track="Master",
                plugin="KENN Audition Engine",
                action="audition_ab",
                params={"loudness_match": True, "tolerance_lu": 0.1},
                why="Compare the processed mix directly against original with equal loudness to verify sonic improvements.",
                depends_on=[prev_id] if prev_id else [],
            )
        )

        return MixPlan(
            plan_id=plan_id,
            goal=query,
            steps=steps,
            telemetry_snapshot=telemetry.to_dict() if telemetry else None,
        )


_planner = MixPlanner()


def get_mix_planner() -> MixPlanner:
    return _planner
