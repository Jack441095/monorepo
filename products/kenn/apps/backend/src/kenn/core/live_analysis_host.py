"""Resolve insert evidence against fresh Live names and prepare guarded faders.

This adapter reads session state and creates proposals only. LiveActionService
owns confirmation, identity checks, write/readback, and reversible receipts.
"""

from __future__ import annotations

import math
import re
from typing import Any

from kenn.core.live_action_service import LiveActionService
from kenn.core import volume_law


class AbletonAnalysisHost:
    def __init__(self, client: Any = None):
        if client is None:
            from kenn.ableton_osc_bridge import live_client
            client = live_client
        self.client = client

    def observe(self) -> dict[str, Any]:
        """Read current mixer context; never substitute a cached offline set."""
        try:
            state = self.client.query_session_state(include_mixer=True, force_refresh=True)
        except (OSError, RuntimeError, TimeoutError, TypeError):
            # A backend without fresh-read support cannot justify a Live action.
            return {"status": "offline", "tracks": []}
        if not isinstance(state, dict) or state.get("status") != "connected":
            # Retained topology is useful elsewhere, but would misbind live audio here.
            return {"status": "offline", "tracks": []}
        return state

    def resolve(self, question: str, state: dict[str, Any], source_name: str) -> dict[str, Any]:
        """Select one explicit number, name, or role; ambiguity requires clarification."""
        tracks = [t for t in state.get("tracks", []) if isinstance(t, dict)]
        lowered = question.casefold()
        numbered = set(re.findall(r"\b(?:track|channel)\s+(\d+)\b", lowered))
        if len(numbered) > 1:
            # One insert cannot establish a multi-track comparison or authorize several faders.
            return {"target": None, "reason": "Which single track should I analyse first?"}
        if numbered:
            # People count tracks from 1; Live's OSC indices start at 0.
            candidates = [t for t in tracks if t.get("index") == int(next(iter(numbered))) - 1]
        else:
            candidates = [t for t in tracks if t.get("name") and re.search(
                r"(?<!\w)" + re.escape(str(t["name"]).casefold()) + r"(?!\w)", lowered)]
            if not candidates:
                roles = re.findall(r"\b(kick|bass|drums?|vocals?|synth|instrument|bus|master)\b", lowered)
                # Role words help locate a track, never dictate EQ or compression.
                candidates = [t for t in tracks if any(re.search(
                    r"\b" + re.escape({"drums": "drum", "vocals": "vocal"}.get(role, role)) + r"s?\b", str(t.get("name", "")).casefold())
                    for role in roles)]
                if not roles and re.search(r"\b(?:this|current)\s+(?:track|channel|bus|insert)\b", lowered):
                    candidates = [t for t in tracks if str(t.get("name", "")).casefold() == source_name.casefold()]
        if len(candidates) != 1:
            # Neither an inferred role nor a duplicated host name is an identity.
            names = ", ".join(f"{int(t['index']) + 1}: {t['name']}" for t in candidates)
            return {"target": None, "reason": "Which track number do you mean?" + (f" Matches: {names}." if names else " Send the exact Live track name or number.")}
        target = candidates[0]
        source_matches = [t for t in tracks if str(t.get("name", "")).casefold() == source_name.casefold()]
        matched = len(source_matches) == 1 and source_matches[0].get("index") == target.get("index")
        return {"target": target, "source_matched": matched}

    def propose_reduction(self, target: dict[str, Any], state: dict[str, Any], *, delta_db: float, session_id: str) -> dict[str, Any]:
        """Return an approval-gated, undoable fader proposal or a manual fallback."""
        raw = target.get("volume")
        if not session_id or getattr(self.client, "read_only", False) or not volume_law.law().measured:
            # A missing owner, read-only adapter, or provisional mapping cannot authorize a calibrated fader.
            return {"ok": False, "error": "Use Live's fader manually; confirmed control or its measured dB mapping is unavailable."}
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or not 0.0 <= raw <= 1.0:
            # An unreadable fader must not trigger the service's cached-state fallback.
            return {"ok": False, "error": "Use Live's fader manually; its current value is unavailable."}
        before_db = volume_law.raw_to_db(raw)
        after = volume_law.db_to_raw(before_db + delta_db) if before_db is not None and math.isfinite(before_db) else None
        if after is None:
            # Muted or out-of-table values have no calibrated relative adjustment.
            return {"ok": False, "error": "Use Live's fader manually; this level is outside the measured fader range."}
        return LiveActionService(self.client).propose_track_action(
            "set_volume", track_index=target["index"], track_name=target["name"],
            value=after, observed_state=state, session_id=session_id,
        )
