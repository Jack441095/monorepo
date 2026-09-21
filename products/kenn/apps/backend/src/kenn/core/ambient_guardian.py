"""KENN Proactive Ambient Studio Guardian Daemon.

Passively monitors session state and real-time meter telemetry in the background,
evaluating headroom drift (> -0.3 dBFS) and 40-band ERB psychoacoustic frequency
collisions without requiring prompt requests.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from kenn.core.session_world_model import SessionWorldModel
from kenn.core.acoustic_calibration import AcousticCalibrationLoop
from kenn.core.live_recipe import RECIPE_SCHEMA


class AmbientStudioGuardian:
    """Proactive background acoustic auditor and safety sentinel."""

    def __init__(self) -> None:
        self._latest_status: Dict[str, Any] = {
            "status": "healthy",
            "connected": False,
            "headroom_safe": True,
            "peak_dbfs": -6.0,
            "crest_db": 12.0,
            "stereo_correlation": 0.85,
            "active_clashes_count": 0,
            "clashes": [],
            "frequency_zones": {
                "sub": {"name": "Sub (20-60 Hz)", "status": "clean", "owner": "Sub Bass"},
                "punch": {"name": "Punch (60-250 Hz)", "status": "clean", "owner": "Kick"},
                "mud": {"name": "Mud (250-500 Hz)", "status": "clean", "owner": "None"},
                "presence": {"name": "Presence (2-5 kHz)", "status": "clean", "owner": "Lead Vocal"},
                "air": {"name": "Air (8-20 kHz)", "status": "clean", "owner": "Master"},
            },
            "advisories": [],
            "staged_proposal": None,
            "confirmation_token": "",
            "updated_at": time.time(),
        }

    def evaluate_session(
        self,
        session_snapshot: Dict[str, Any],
        meters: Optional[Dict[str, Any]] = None,
        session_id: str = "ambient-guardian",
    ) -> Dict[str, Any]:
        """Evaluates active session snapshot and meters, producing acoustic health and staged recipes."""
        tracks = session_snapshot.get("tracks", [])
        if not tracks:
            self._latest_status["connected"] = False
            self._latest_status["status"] = "offline"
            return self._latest_status

        meters = meters or {}
        peak_dbfs = float(meters.get("peak_dbfs", -4.2))
        crest_db = float(meters.get("crest_db", 10.5))
        stereo_corr = float(meters.get("stereo_correlation", 0.82))
        headroom_safe = peak_dbfs <= -0.3

        world_model = SessionWorldModel.build_world_model(session_snapshot, meters=meters)
        calib_loop = AcousticCalibrationLoop()
        baseline = calib_loop.capture_baseline(session_id, session_snapshot)
        clashes = calib_loop.diagnose_clashes(baseline)

        # Update frequency zones status
        zones = {
            "sub": {"name": "Sub (20-60 Hz)", "status": "clean", "owner": "Sub Bass"},
            "punch": {"name": "Punch (60-250 Hz)", "status": "clean", "owner": "Kick"},
            "mud": {"name": "Mud (250-500 Hz)", "status": "clean", "owner": "Pads/Instruments"},
            "presence": {"name": "Presence (2-5 kHz)", "status": "clean", "owner": "Lead Vocal"},
            "air": {"name": "Air (8-20 kHz)", "status": "clean", "owner": "High Percussion"},
        }
        advisories: List[str] = []

        if not headroom_safe:
            advisories.append(f"Headroom warning: Peak level {peak_dbfs:.2f} dBFS exceeds safety ceiling (-0.3 dBFS).")

        for c in clashes:
            freq = c.get("frequency_hz", 100.0)
            masker = c.get("masker_name", "Masker")
            victim = c.get("victim_name", "Victim")
            if freq < 60:
                zones["sub"]["status"] = "clashing"
                advisories.append(f"Sub-bass clash at {freq:.0f} Hz ({masker} masking {victim})")
            elif freq < 250:
                zones["punch"]["status"] = "clashing"
                advisories.append(f"Low-end punch collision at {freq:.0f} Hz ({masker} masking {victim})")
            elif freq < 500:
                zones["mud"]["status"] = "clashing"
                advisories.append(f"Low-mid mud accumulation at {freq:.0f} Hz ({masker} masking {victim})")
            elif freq < 5000:
                zones["presence"]["status"] = "clashing"
                advisories.append(f"Vocal presence masking at {freq:.0f} Hz ({masker} masking {victim})")

        staged_proposal = None
        confirmation_token = ""
        if clashes or not headroom_safe:
            recipe_result = calib_loop.formulate_calibration_recipe(
                baseline,
                clashes,
                objective="Ambient Studio Guardian: Automatic mix unmasking and headroom protection",
            )
            if recipe_result.get("ok") and recipe_result.get("proposal"):
                staged_proposal = recipe_result["proposal"]
                confirmation_token = recipe_result.get("confirmation_token", "")
                if not confirmation_token:
                    confirmation_token = f"guardian_{hashlib.sha256(f'{session_id}_{len(clashes)}_{peak_dbfs}'.encode()).hexdigest()[:20]}"
                    staged_proposal["confirmation_token"] = confirmation_token

        overall_status = "healthy"
        if not headroom_safe or len(clashes) >= 2:
            overall_status = "advisory"
        elif len(clashes) == 1:
            overall_status = "caution"

        self._latest_status = {
            "status": overall_status,
            "connected": True,
            "headroom_safe": headroom_safe,
            "peak_dbfs": peak_dbfs,
            "crest_db": crest_db,
            "stereo_correlation": stereo_corr,
            "active_clashes_count": len(clashes),
            "clashes": clashes,
            "frequency_zones": zones,
            "advisories": advisories,
            "staged_proposal": staged_proposal,
            "confirmation_token": confirmation_token,
            "updated_at": time.time(),
        }
        return self._latest_status

    def get_status(self) -> Dict[str, Any]:
        """Returns the cached ambient studio guardian health snapshot."""
        return self._latest_status


_guardian: Optional[AmbientStudioGuardian] = None


def get_ambient_guardian() -> AmbientStudioGuardian:
    global _guardian
    if _guardian is None:
        _guardian = AmbientStudioGuardian()
    return _guardian
