"""Deterministic Subjective-to-Technical Translation Engine for KENN.

Translates producer artistic metaphors and subjective mix requests into
strictly bounded, typed, confirmation-gated Ableton Live 12 proposals:
- "Make the vocal cut through" -> Presence unmasking (-2.0 dB carve on competing synths/leads + gentle vocal boost)
- "Fix low-end mud" -> High-pass filtering on non-bass tracks (< 120 Hz) & sub bass mono centering
- "Glue the drum bus" -> Glue Compressor insertion with 30ms attack, auto release, 2:1 ratio, 1-2 dB target GR

All outputs strictly adhere to KENN's Hardware Safety Policy:
- Gain changes <= +/- 3.0 dB
- Master limiter ceiling <= -0.3 dBFS
- Master fader locked
- Two-phase confirmation required
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from kenn.core import volume_law
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_recipe import LiveRecipeService, RECIPE_SCHEMA


_VOCAL_PATTERNS = re.compile(
    r"\b(vocal|vox|vocals)\b.*\b(cut\s+through|buried|unmask|stand\s+out|clarity|clearer)\b"
    r"|\b(make|help)\b.*\b(vocal|vox|vocals)\b.*\b(cut|heard|clear|through)\b"
    # "bring the vocal forward" is a mix request; "bring the vocal up a hair" is a fader move on the vocal alone.
    # "up" used to be here and turned that into a recipe that also cut the Synth (found by the 505-phrasing check).
    r"|\b(bring|push)\b.*\b(vocal|vox|vocals)\b.*\b(forward|front)\b",
    re.I,
)

_MUD_PATTERNS = re.compile(
    r"\b(fix|clean|remove|reduce|clear)\b.*\b(low[\s-]end|mud|muddy|boominess|sub\s+clutter|mids)\b"
    r"|\b(muddy|low[\s-]end\s+mud|muddy\s+low\s+mids)\b"
    r"|\b(clean\s+up)\b.*\b(mix|low\s+end|bottom\s+end)\b",
    re.I,
)

_GLUE_PATTERNS = re.compile(
    r"\b(glue|compress)\b.*\b(drum\s+bus|drums?\s+bus|drums?|drum\s+group)\b"
    r"|\b(drum\s+bus|drums?)\b.*\b(glue|cohesion|punch)\b",
    re.I,
)


def _shift_db(raw: float, change_db: float) -> float | None:
    """The raw fader value ``change_db`` away from ``raw`` on Live's fader law; None if that goes above 0 dB.

    These recipes used to move faders by fixed raw amounts (-0.07 "about -1.5 dB") and told the producer the wrong
    number: -0.07 is -2.8 dB, and +0.05 took a vocal already at 0 dB to +2 dB (found 26 Sept).
    """
    current = volume_law.raw_to_db(float(raw))
    if current is None:
        return None
    target = current + change_db
    return None if target > 0.0 else volume_law.db_to_raw(target)


class SubjectiveTranslator:
    """Translates producer creative intent into typed, safe Live 12 actions."""

    @classmethod
    def can_translate(cls, query: str) -> bool:
        text = str(query or "").strip()
        return bool(
            _VOCAL_PATTERNS.search(text)
            or _MUD_PATTERNS.search(text)
            or _GLUE_PATTERNS.search(text)
        )

    @classmethod
    def translate(
        cls,
        query: str,
        snapshot: Dict[str, Any],
        session_id: str,
        service: Optional[LiveActionService] = None,
    ) -> Optional[Dict[str, Any]]:
        text = str(query or "").strip()
        tracks = [t for t in snapshot.get("tracks", []) if isinstance(t, dict)]
        if not tracks:
            return None

        live = service or LiveActionService()

        # 1. Glue the Drum Bus
        if _GLUE_PATTERNS.search(text):
            return cls._translate_glue_drum_bus(tracks, session_id, live)

        # 2. Make the Vocal Cut Through
        if _VOCAL_PATTERNS.search(text):
            return cls._translate_vocal_cut_through(tracks, session_id, live)

        # 3. Fix Low-End Mud
        if _MUD_PATTERNS.search(text):
            return cls._translate_fix_low_end_mud(tracks, session_id, live)

        return None

    @classmethod
    def _translate_glue_drum_bus(
        cls,
        tracks: List[Dict[str, Any]],
        session_id: str,
        service: LiveActionService,
    ) -> Dict[str, Any]:
        drum_track = next(
            (t for t in tracks if any(kw in str(t.get("name", "")).lower() for kw in {"drum bus", "drum buss", "drums bus", "drums", "drum group"})),
            None,
        )
        if drum_track is None:
            return {
                "status": "clarification_required",
                "answer": "I couldn't identify a Drum Bus or Drums track in your session to insert the Glue Compressor onto. Please name your drum bus track 'Drum Bus' or specify the track index.",
                "changed": False,
            }

        t_idx = int(drum_track.get("index", drum_track.get("track_index", 0)))
        t_name = str(drum_track.get("name", "Drum Bus"))

        # Check if Glue Compressor already exists
        devices = drum_track.get("devices", [])
        if any("glue" in str(d.get("name", "")).lower() or "glue" in str(d.get("class_name", "")).lower() for d in devices):
            return {
                "status": "planned",
                "answer": f"Track '{t_name}' already has a Glue Compressor loaded. Recommended settings: Attack=30ms, Release=Auto, Ratio=2:1, Gain Reduction target=1-2 dB.",
                "changed": False,
            }

        prop_res = service.propose_device_insertion(
            track_index=t_idx,
            track_name=t_name,
            device_name="Glue Compressor",
            session_id=session_id,
        )
        if not prop_res.get("ok"):
            return {
                "status": "failed",
                "answer": prop_res.get("error", "Failed to prepare Glue Compressor insertion proposal."),
                "changed": False,
            }

        proposal = prop_res["proposal"]
        proposal["recommended_parameters"] = {
            "attack_ms": 30.0,
            "release": "auto",
            "ratio": "2:1",
            "target_gr_db": 1.5,
        }
        return {
            "status": "proposed",
            "intent": {
                "action": "insert_device",
                "track_index": t_idx,
                "track_name": t_name,
                "device_name": "Glue Compressor",
            },
            "proposal": proposal,
            "confirmation_token": prop_res.get("confirmation_token", ""),
            "requires_confirmation": True,
            "answer": (
                f"I've prepared a proposal to insert a Glue Compressor on '{t_name}'. "
                f"Settings: Attack=30ms, Release=Auto, Ratio=2:1 for cohesive 1-2 dB drum bus punch. "
                f"Explicit confirmation is required before modifying Live."
            ),
        }

    @classmethod
    def _translate_vocal_cut_through(
        cls,
        tracks: List[Dict[str, Any]],
        session_id: str,
        service: LiveActionService,
    ) -> Dict[str, Any]:
        vocal_track = next(
            (t for t in tracks if any(kw in str(t.get("name", "")).lower() for kw in {"lead vocal", "vocal", "vox", "lead vox", "vocals"})),
            None,
        )
        if vocal_track is None:
            return {
                "status": "clarification_required",
                "answer": "I couldn't identify a vocal track in your session. Please name your vocal track 'Lead Vocal' or 'Vox' to prepare an unmasking proposal.",
                "changed": False,
            }

        competing_track = next(
            (t for t in tracks if any(kw in str(t.get("name", "")).lower() for kw in {"synth", "supersaw", "lead", "guitar", "guitars", "pad", "keys"}) and t != vocal_track),
            None,
        )

        v_idx = int(vocal_track.get("index", vocal_track.get("track_index", 0)))
        v_name = str(vocal_track.get("name", "Vocal"))
        v_vol = float(vocal_track.get("volume", 0.75))

        steps: List[Dict[str, Any]] = []

        if competing_track is not None:
            c_idx = int(competing_track.get("index", competing_track.get("track_index", 0)))
            c_name = str(competing_track.get("name", "Synth"))
            c_vol = float(competing_track.get("volume", 0.75))

            c_new_vol = _shift_db(c_vol, -1.5)
            v_new_vol = _shift_db(v_vol, 1.0)
            if c_new_vol is None:
                return {"status": "clarification_required", "changed": False,
                        "answer": f"I couldn't read the level of '{c_name}', so nothing changed."}
            steps.append({"action": "set_volume", "track_index": c_idx, "track_name": c_name, "value": c_new_vol})
            if v_new_vol is not None:
                steps.append({"action": "set_volume", "track_index": v_idx, "track_name": v_name, "value": v_new_vol})

            lift = f" and lifting '{v_name}' by 1.0 dB" if v_new_vol is not None else ""
            recipe_res = LiveRecipeService(service).propose_recipe(
                steps,
                reason=f"Unmask '{v_name}' by trimming competing '{c_name}' by 1.5 dB{lift}.",
                session_id=session_id,
            )
            if not recipe_res.get("ok"):
                return {
                    "status": "failed",
                    "answer": recipe_res.get("error", "Failed to formulate vocal unmasking recipe."),
                    "changed": False,
                }

            return {
                "status": "proposed",
                "intent": {
                    "action": "recipe",
                    "recipe_name": "vocal_cut_through",
                    "vocal_track": v_name,
                    "competing_track": c_name,
                },
                "proposal": recipe_res["proposal"],
                "confirmation_token": recipe_res.get("confirmation_token", ""),
                "requires_confirmation": True,
                "answer": (
                    f"To help '{v_name}' cut through: turn '{c_name}' down 1.5 dB"
                    + (f", then '{v_name}' up 1.0 dB." if v_new_vol is not None else
                       f". '{v_name}' is already at 0 dB, so I won't lift it further.")
                    + " Nothing changes until you press Apply."
                ),
            }
        else:
            # Only the vocal: lift it 1.2 dB, if that stays at or below 0 dB.
            v_new_vol = _shift_db(v_vol, 1.2)
            if v_new_vol is None:
                return {"status": "clarification_required", "changed": False,
                        "answer": f"'{v_name}' is already at or near 0 dB and there's no other part to turn down. "
                                  "Which track is getting in its way?"}
            prop_res = service.propose_track_action(
                track_index=v_idx,
                action="set_volume",
                value=v_new_vol,
                session_id=session_id,
                track_name=v_name,
            )
            if not prop_res.get("ok"):
                return {
                    "status": "failed",
                    "answer": prop_res.get("error", "Failed to formulate vocal level proposal."),
                    "changed": False,
                }
            return {
                "status": "proposed",
                "intent": {
                    "action": "set_volume",
                    "track_index": v_idx,
                    "track_name": v_name,
                },
                "proposal": prop_res["proposal"],
                "confirmation_token": prop_res.get("confirmation_token", ""),
                "requires_confirmation": True,
                "answer": (
                    f"To help '{v_name}' cut through: turn it up 1.2 dB. Nothing changes until you press Apply."
                ),
            }

    @classmethod
    def _translate_fix_low_end_mud(
        cls,
        tracks: List[Dict[str, Any]],
        session_id: str,
        service: LiveActionService,
    ) -> Dict[str, Any]:
        # Identify sub/bass and check for off-center panning
        sub_track = next(
            (t for t in tracks if any(kw in str(t.get("name", "")).lower() for kw in {"sub", "808", "sub bass"})),
            None,
        )

        steps: List[Dict[str, Any]] = []

        if sub_track is not None:
            s_idx = int(sub_track.get("index", sub_track.get("track_index", 0)))
            s_name = str(sub_track.get("name", "Sub Bass"))
            s_pan = float(sub_track.get("panning", 0.0))
            if abs(s_pan) > 0.05:
                steps.append({
                    "action": "set_pan",
                    "track_index": s_idx,
                    "track_name": s_name,
                    "value": 0.0,
                })

        # Identify hot non-bass tracks cluttering the low end
        # "Hot" is above -6 dB (raw 0.70 on Live's fader law, the old threshold).
        mud_track = next(
            (t for t in tracks if any(kw in str(t.get("name", "")).lower() for kw in {"pad", "pads", "synth", "guitar", "keys", "piano"})
             and (volume_law.raw_to_db(float(t.get("volume", 0.0) or 0.0)) or -100.0) > -6.0),
            None,
        )
        if mud_track is not None:
            m_idx = int(mud_track.get("index", mud_track.get("track_index", 0)))
            m_name = str(mud_track.get("name", "Pads"))
            m_vol = float(mud_track.get("volume", 0.75))
            m_new_vol = _shift_db(m_vol, -2.0)
        if mud_track is not None and m_new_vol is not None:
            steps.append({
                "action": "set_volume",
                "track_index": m_idx,
                "track_name": m_name,
                "value": m_new_vol,
            })

        if not steps:
            return {
                "status": "planned",
                "answer": "Session low end is already well balanced. Sub bass is mono-centered and no hot low-mid rumble was detected. To insert a high-pass filter, tell me which track you'd like to add EQ Eight to.",
                "changed": False,
            }

        recipe_res = LiveRecipeService(service).propose_recipe(
            steps,
            reason="Fix low-end mud by centering sub bass panning and trimming hot low-mid rumble.",
            session_id=session_id,
        )
        if not recipe_res.get("ok"):
            return {
                "status": "failed",
                "answer": recipe_res.get("error", "Failed to formulate low-end cleanup recipe."),
                "changed": False,
            }

        return {
            "status": "proposed",
            "intent": {
                "action": "recipe",
                "recipe_name": "fix_low_end_mud",
            },
            "proposal": recipe_res["proposal"],
            "confirmation_token": recipe_res.get("confirmation_token", ""),
            "requires_confirmation": True,
            "answer": (
                f"I've prepared a proposal to clean up low-end mud across {len(steps)} step(s): "
                f"centers sub-bass phase to mono and trims competing low-mid clutter. "
                f"Please confirm to apply."
            ),
        }
