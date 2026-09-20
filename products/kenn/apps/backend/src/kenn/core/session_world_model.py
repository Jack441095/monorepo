"""KENN Session World Model: Semantic Track Role Graph & Bounded Session Delta Stream.

Translates raw Ableton Live Object Model (LOM) session snapshots into a semantic
production world model, identifying track musical roles, frequency band ownership,
masking relationships, and acoustic priority conflicts, while providing bounded
immutable session deltas for deliberative planning and live context tracking.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from kenn.core.session_context import build_session_context

DELTA_SCHEMA = "kenn.session_world_delta.v1"
MAX_EVENTS = 256

# Semantic Track Roles
ROLE_KICK = "kick"
ROLE_SUB_BASS = "sub_bass"
ROLE_MID_BASS = "mid_bass"
ROLE_SNARE = "snare"
ROLE_HIHATS = "hihats"
ROLE_DRUMS_BUS = "drums_bus"
ROLE_LEAD_VOCAL = "lead_vocal"
ROLE_BACKING_VOCAL = "backing_vocal"
ROLE_SYNTH_LEAD = "synth_lead"
ROLE_PADS_REVERB = "pads_reverb"
ROLE_FX_RISER = "fx_riser"
ROLE_GENERIC = "generic"

ALL_ROLES = (
    ROLE_KICK,
    ROLE_SUB_BASS,
    ROLE_MID_BASS,
    ROLE_SNARE,
    ROLE_HIHATS,
    ROLE_DRUMS_BUS,
    ROLE_LEAD_VOCAL,
    ROLE_BACKING_VOCAL,
    ROLE_SYNTH_LEAD,
    ROLE_PADS_REVERB,
    ROLE_FX_RISER,
    ROLE_GENERIC,
)


def _indexed(items: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        int(item["index"]): item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("index"), int)
    }


def _event(kind: str, subject: str, before: Any, after: Any) -> dict[str, Any]:
    return {"kind": kind, "subject": subject[:256], "before": before, "after": after}


def _classification_summary(items: Any) -> list[dict[str, Any]]:
    """Keep classifier deltas useful without returning arbitrary payloads."""
    result: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        ood = item.get("out_of_distribution") if isinstance(item.get("out_of_distribution"), dict) else {}
        result.append({
            "audio_sha256": str(item.get("audio_sha256") or "")[:71],
            "selected_label": str(item.get("selected_label") or "")[:96],
            "selected_source": str(item.get("selected_source") or "")[:32],
            "confidence_band": str(item.get("confidence_band") or "")[:16],
            "ood_status": str(ood.get("status") or "")[:32],
        })
        if len(result) >= 32:
            break
    return result


def _compare_indexed(
    events: list[dict[str, Any]],
    *,
    label: str,
    previous: Any,
    current: Any,
    fields: tuple[str, ...],
) -> None:
    old = _indexed(previous)
    new = _indexed(current)
    for index in sorted(old.keys() - new.keys()):
        events.append(_event(f"{label}_removed", f"{label}:{index}", old[index], None))
    for index in sorted(new.keys() - old.keys()):
        events.append(_event(f"{label}_added", f"{label}:{index}", None, new[index]))
    for index in sorted(old.keys() & new.keys()):
        for field in fields:
            if old[index].get(field) != new[index].get(field):
                kind = f"{label}_renamed" if field == "name" else f"{label}_{field}_changed"
                events.append(_event(
                    kind,
                    f"{label}:{index}:{field}",
                    old[index].get(field),
                    new[index].get(field),
                ))


def diff_session_contexts(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    revision: int,
) -> dict[str, Any]:
    """Return bounded semantic changes between two sanitized contexts."""
    if previous is None:
        events = [_event("world_initialized", "session", None, current.get("snapshot_fingerprint"))]
        previous_fingerprint = None
    else:
        events: list[dict[str, Any]] = []
        previous_fingerprint = previous.get("snapshot_fingerprint")
        old_transport = previous.get("transport") if isinstance(previous.get("transport"), dict) else {}
        new_transport = current.get("transport") if isinstance(current.get("transport"), dict) else {}
        for field in sorted(set(old_transport) | set(new_transport)):
            if old_transport.get(field) != new_transport.get(field):
                events.append(_event(
                    "transport_changed", f"transport:{field}",
                    old_transport.get(field), new_transport.get(field),
                ))

        _compare_indexed(
            events,
            label="track",
            previous=previous.get("tracks"),
            current=current.get("tracks"),
            fields=("name", "type", "volume", "pan", "muted", "soloed", "armed", "routing", "sends", "clip_slots", "arrangement_clips", "devices"),
        )
        _compare_indexed(
            events,
            label="scene",
            previous=previous.get("scenes"),
            current=current.get("scenes"),
            fields=("name",),
        )
        _compare_indexed(
            events,
            label="locator",
            previous=previous.get("locators"),
            current=current.get("locators"),
            fields=("name", "time_beats"),
        )
        _compare_indexed(
            events,
            label="return_track",
            previous=previous.get("return_tracks"),
            current=current.get("return_tracks"),
            fields=("name", "devices"),
        )
        if previous.get("master_track") != current.get("master_track"):
            events.append(_event(
                "master_track_changed", "master_track",
                previous.get("master_track"), current.get("master_track"),
            ))
        for field, kind in (
            ("producer_preferences", "producer_preferences_changed"),
            ("episodic_outcomes", "episodic_outcomes_changed"),
        ):
            if previous.get(field) != current.get(field):
                events.append(_event(kind, field, previous.get(field), current.get(field)))
        if previous.get("audio_classifications") != current.get("audio_classifications"):
            events.append(_event(
                "audio_classifications_changed", "audio_classifications",
                _classification_summary(previous.get("audio_classifications")),
                _classification_summary(current.get("audio_classifications")),
            ))

    truncated = len(events) > MAX_EVENTS
    bounded = events[:MAX_EVENTS]
    return {
        "schema": DELTA_SCHEMA,
        "revision": revision,
        "previous_fingerprint": previous_fingerprint,
        "snapshot_fingerprint": current.get("snapshot_fingerprint"),
        "observed_at": current.get("observed_at"),
        "changed": bool(bounded),
        "event_count": len(bounded),
        "events": bounded,
        "truncated": truncated,
        "read_only": True,
    }


@dataclass
class TrackSemanticNode:
    """Semantic abstraction of a single DAW track."""

    index: int
    name: str
    role: str
    confidence: float
    devices: List[str] = field(default_factory=list)
    has_eq: bool = False
    has_compressor: bool = False
    has_sidechain: bool = False
    volume: float = 0.85
    panning: float = 0.0
    is_group: bool = False
    parent_group_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "role": self.role,
            "confidence": round(self.confidence, 2),
            "devices": self.devices,
            "has_eq": self.has_eq,
            "has_compressor": self.has_compressor,
            "has_sidechain": self.has_sidechain,
            "volume": self.volume,
            "panning": self.panning,
            "is_group": self.is_group,
            "parent_group_index": self.parent_group_index,
        }


@dataclass
class FrequencyBandAllocation:
    """Frequency range allocation and priority."""

    band_name: str
    freq_range_hz: Tuple[float, float]
    primary_roles: List[str]
    assigned_tracks: List[int] = field(default_factory=list)
    potential_intruders: List[int] = field(default_factory=list)


@dataclass
class SemanticConflict:
    """Detected musical or acoustic clash between session elements."""

    code: str
    severity: str  # "critical", "medium", "advisory"
    track_indices: List[int]
    description: str
    suggested_action: str
    proposed_param_change: Optional[Dict[str, Any]] = None


class SessionWorldModel:
    """Combines semantic track role understanding with bounded session context deltas."""

    ROLE_PATTERNS: List[Tuple[str, List[str], float]] = [
        # (Role, list of regex patterns, confidence)
        (ROLE_KICK, [r"\bkick\b", r"\bbd\b", r"\b808\s*kick\b", r"\bdrop\s*kick\b"], 0.95),
        (ROLE_SUB_BASS, [r"\bsub\b", r"\bsub\s*bass\b", r"\b808\b", r"\breese\s*sub\b", r"\bsine\s*sub\b"], 0.90),
        (ROLE_MID_BASS, [r"\bbass\b", r"\bneuro\b", r"\bwobble\b", r"\bdonk\b", r"\bfm\s*bass\b", r"\bgrowl\b"], 0.85),
        (ROLE_SNARE, [r"\bsnare\b", r"\bclap\b", r"\brim\b", r"\bsnap\b"], 0.90),
        (ROLE_HIHATS, [r"\bhat\b", r"\bhihat\b", r"\boh\b", r"\bch\b", r"\bcymbal\b", r"\bride\b", r"\bshaker\b", r"\btops\b"], 0.85),
        (ROLE_DRUMS_BUS, [r"\bdrum\b", r"\bdrums\b", r"\bdrum\s*bus\b", r"\bbeats\b", r"\bpercussion\b", r"\bperc\b"], 0.85),
        (ROLE_LEAD_VOCAL, [r"\blead\s*vox\b", r"\bvocal\s*lead\b", r"\bmain\s*vox\b", r"\bvox\b", r"\bvocal\b", r"\bhook\b"], 0.90),
        (ROLE_BACKING_VOCAL, [r"\bbacking\b", r"\bdouble\b", r"\badlib\b", r"\bharmony\b", r"\bharmonies\b", r"\bchant\b"], 0.85),
        (ROLE_SYNTH_LEAD, [r"\blead\b", r"\bsupersaw\b", r"\bpluck\b", r"\barp\b", r"\bchords\b", r"\bsynth\b", r"\bpoly\b"], 0.80),
        (ROLE_PADS_REVERB, [r"\bpad\b", r"\batmosphere\b", r"\btexture\b", r"\bambient\b", r"\breverb\b", r"\bdelay\b"], 0.85),
        (ROLE_FX_RISER, [r"\bfx\b", r"\bsweep\b", r"\briser\b", r"\bdownlifter\b", r"\bimpact\b", r"\bcrash\b", r"\bwhite\s*noise\b"], 0.85),
    ]

    def __init__(self, *, session_id: str = ""):
        self.session_id = str(session_id or "").strip()[:128]
        self._context: dict[str, Any] | None = None
        self._delta: dict[str, Any] | None = None
        self._revision = 0
        self._lock = Lock()

    def observe(
        self,
        *,
        snapshot: dict[str, Any] | None = None,
        plugin_frames: Iterable[dict[str, Any]] = (),
        mix_review_receipts: Iterable[dict[str, Any]] = (),
        audiogen_jobs: Iterable[dict[str, Any]] = (),
        automix_receipts: Iterable[dict[str, Any]] = (),
        audio_classifications: Iterable[dict[str, Any]] = (),
        audition_feedback: Iterable[dict[str, Any]] = (),
        device_matrix: dict[str, Any] | None = None,
        producer_preferences: Iterable[dict[str, Any]] = (),
        episodic_outcomes: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        context = build_session_context(
            snapshot=snapshot,
            session_id=self.session_id,
            plugin_frames=plugin_frames,
            mix_review_receipts=mix_review_receipts,
            audiogen_jobs=audiogen_jobs,
            automix_receipts=automix_receipts,
            audio_classifications=audio_classifications,
            audition_feedback=audition_feedback,
            device_matrix=device_matrix,
            producer_preferences=producer_preferences,
            episodic_outcomes=episodic_outcomes,
        )
        with self._lock:
            self._revision += 1
            delta = diff_session_contexts(self._context, context, revision=self._revision)
            self._context = deepcopy(context)
            self._delta = deepcopy(delta)
        return {"context": context, "delta": delta}

    def current_context(self) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._context)

    def latest_delta(self) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._delta)

    def observe_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Record an already-sanitized context without rebuilding it."""
        if not isinstance(context, dict):
            raise ValueError("context must be an object")
        with self._lock:
            self._revision += 1
            delta = diff_session_contexts(self._context, context, revision=self._revision)
            self._context = deepcopy(context)
            self._delta = deepcopy(delta)
            return {"context": deepcopy(context), "delta": deepcopy(delta)}

    @classmethod
    def infer_role(
        cls,
        track_name: str,
        devices: List[str],
        spectral_centroid_hz: Optional[float] = None,
        is_drum_rack: bool = False,
    ) -> Tuple[str, float]:
        """Infer track musical role from track name, active Live 12 device inventory, and spectral centroid."""
        normalized = track_name.lower().strip()

        # 1. Check explicit regex patterns against track name (highest confidence)
        for role, patterns, conf in cls.ROLE_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, normalized):
                    return role, conf

        # 2. Multimodal device inventory & parameter fingerprinting
        device_names_lower = [d.lower() for d in devices]

        if is_drum_rack or any("drum rack" in d or "drum sampler" in d for d in device_names_lower):
            return ROLE_DRUMS_BUS, 0.88

        if any("drum bus" in d for d in device_names_lower):
            return ROLE_DRUMS_BUS, 0.85

        if any("simpler" in d or "sampler" in d for d in device_names_lower):
            if any(term in normalized for term in ("kick", "bd", "808")):
                return ROLE_KICK, 0.85
            if any(term in normalized for term in ("snare", "clap", "rim")):
                return ROLE_SNARE, 0.85
            if any(term in normalized for term in ("hat", "shaker", "top")):
                return ROLE_HIHATS, 0.85

        if any("roar" in d for d in device_names_lower):
            # Roar is typically deployed on aggressive bass, drum crush, or vocal drive
            if "bass" in normalized or (spectral_centroid_hz and spectral_centroid_hz < 400.0):
                return ROLE_MID_BASS, 0.85
            return ROLE_SYNTH_LEAD, 0.70

        if any("operator" in d or "drift" in d for d in device_names_lower):
            if "bass" in normalized or "sub" in normalized or (spectral_centroid_hz and spectral_centroid_hz < 150.0):
                return ROLE_SUB_BASS, 0.85
            # Operator/Drift alone does not prove a lead role. Keep an
            # unlabelled track conservative until its name or spectrum gives
            # us stronger evidence.
            if any(term in normalized for term in ("lead", "synth", "keys", "chord", "pad")):
                return ROLE_SYNTH_LEAD, 0.75
            return ROLE_GENERIC, 0.30

        if any("meld" in d or "wavetable" in d or "analog" in d or "collision" in d for d in device_names_lower):
            if spectral_centroid_hz and spectral_centroid_hz < 250.0:
                return ROLE_MID_BASS, 0.75
            return ROLE_SYNTH_LEAD, 0.80

        # 3. Spectral Centroid Acoustic Hinting (if available)
        if spectral_centroid_hz is not None:
            if spectral_centroid_hz < 90.0:
                return ROLE_SUB_BASS, 0.75
            elif spectral_centroid_hz < 220.0:
                return ROLE_MID_BASS, 0.70
            elif spectral_centroid_hz > 6500.0:
                return ROLE_HIHATS, 0.70

        return ROLE_GENERIC, 0.30

    @classmethod
    def build_session_graph(cls, session_state: Dict[str, Any]) -> List[TrackSemanticNode]:
        """Transform raw LOM session state tracks into TrackSemanticNodes."""
        nodes: List[TrackSemanticNode] = []
        raw_tracks = session_state.get("tracks", [])

        for t in raw_tracks:
            idx = int(t.get("index", len(nodes)))
            name = str(t.get("name", f"Track {idx}"))
            raw_devices = t.get("devices", [])
            dev_names = [d.get("name", "") if isinstance(d, dict) else str(d) for d in raw_devices]

            role, conf = cls.infer_role(name, dev_names)

            has_eq = any("eq" in d.lower() for d in dev_names)
            has_comp = any("comp" in d.lower() or "glue" in d.lower() for d in dev_names)
            has_sidechain = any("sidechain" in d.lower() for d in dev_names)

            node = TrackSemanticNode(
                index=idx,
                name=name,
                role=role,
                confidence=conf,
                devices=dev_names,
                has_eq=has_eq,
                has_compressor=has_comp,
                has_sidechain=has_sidechain,
                volume=float(t.get("volume", 0.85)),
                panning=float(t.get("panning", t.get("pan", 0.0))),
                is_group=bool(t.get("is_foldable", False)),
                parent_group_index=t.get("group_track_index"),
            )
            nodes.append(node)

        return nodes

    @classmethod
    def frequency_priority_matrix(cls) -> List[FrequencyBandAllocation]:
        """Return the standard reference priority allocation across frequency bands."""
        return [
            FrequencyBandAllocation(
                band_name="Sub Bass",
                freq_range_hz=(20.0, 90.0),
                primary_roles=[ROLE_SUB_BASS, ROLE_KICK],
            ),
            FrequencyBandAllocation(
                band_name="Punch & Body",
                freq_range_hz=(90.0, 250.0),
                primary_roles=[ROLE_KICK, ROLE_SNARE, ROLE_MID_BASS],
            ),
            FrequencyBandAllocation(
                band_name="Low Mids (Warmth & Mud Risk)",
                freq_range_hz=(250.0, 800.0),
                primary_roles=[ROLE_SNARE, ROLE_LEAD_VOCAL, ROLE_SYNTH_LEAD],
            ),
            FrequencyBandAllocation(
                band_name="Presence & Articulation",
                freq_range_hz=(2000.0, 5000.0),
                primary_roles=[ROLE_LEAD_VOCAL, ROLE_SYNTH_LEAD, ROLE_SNARE],
            ),
            FrequencyBandAllocation(
                band_name="Air & Brilliance",
                freq_range_hz=(8000.0, 20000.0),
                primary_roles=[ROLE_HIHATS, ROLE_FX_RISER, ROLE_LEAD_VOCAL],
            ),
        ]

    @classmethod
    def build_world_model(cls, session_state: Dict[str, Any], meters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Construct a complete semantic analysis of the Ableton Live session."""
        nodes = cls.build_session_graph(session_state)
        bands = cls.frequency_priority_matrix()
        conflicts: List[SemanticConflict] = []

        roles_map: Dict[str, List[int]] = {r: [] for r in ALL_ROLES}
        for n in nodes:
            roles_map[n.role].append(n.index)

        # 1. Sub Bass & Kick Collisions
        kick_tracks = roles_map[ROLE_KICK]
        sub_tracks = roles_map[ROLE_SUB_BASS]

        if kick_tracks and sub_tracks:
            bands[0].assigned_tracks.extend(kick_tracks)
            bands[0].assigned_tracks.extend(sub_tracks)

            sub_node = nodes[sub_tracks[0]]
            if not sub_node.has_sidechain and not sub_node.has_compressor:
                conflicts.append(
                    SemanticConflict(
                        code="SUB_KICK_COLLISION_RISK",
                        severity="critical",
                        track_indices=[kick_tracks[0], sub_tracks[0]],
                        description=f"Sub Bass ({sub_node.name}) and Kick ({nodes[kick_tracks[0]].name}) both occupy 20-90 Hz without detected sidechain ducking.",
                        suggested_action="Add Live 12 Compressor to Sub Bass sidechained to Kick track.",
                    )
                )

        # 2. Low-Mid Mud Accumulation
        mud_intruders: List[int] = []
        for n in nodes:
            if n.role in (ROLE_SYNTH_LEAD, ROLE_PADS_REVERB, ROLE_BACKING_VOCAL, ROLE_GENERIC):
                if not n.has_eq:
                    mud_intruders.append(n.index)

        if len(mud_intruders) >= 2:
            bands[2].potential_intruders.extend(mud_intruders)
            conflicts.append(
                SemanticConflict(
                    code="LOW_MID_MUD_ACCUMULATION",
                    severity="medium",
                    track_indices=mud_intruders[:3],
                    description=f"Multiple melodic tracks ({[nodes[i].name for i in mud_intruders[:3]]}) lack high-pass filtering in the 150-350 Hz range.",
                    suggested_action="Insert EQ Eight and apply high-pass filter (cut below 120-180 Hz) to non-bass elements.",
                )
            )

        # 3. Vocal Corridor Masking
        vocal_tracks = roles_map[ROLE_LEAD_VOCAL]
        synth_tracks = roles_map[ROLE_SYNTH_LEAD]
        if vocal_tracks and synth_tracks:
            bands[2].assigned_tracks.extend(vocal_tracks)
            bands[2].potential_intruders.extend(synth_tracks)
            conflicts.append(
                SemanticConflict(
                    code="VOCAL_PRESENCE_MASKING",
                    severity="advisory",
                    track_indices=[vocal_tracks[0], synth_tracks[0]],
                    description=f"Lead Vocal ({nodes[vocal_tracks[0]].name}) and Synths ({nodes[synth_tracks[0]].name}) compete in the 2-5 kHz clarity band.",
                    suggested_action="Apply a gentle 1.5-2.0 dB bell dip at 3 kHz on synths or sidechain dynamic EQ.",
                )
            )

        arrangement = cls.infer_arrangement_sections(session_state)
        harmonics = cls.harmonic_context(session_state)

        return {
            "status": "success",
            "total_tracks": len(nodes),
            "semantic_nodes": [n.to_dict() for n in nodes],
            "roles_inventory": {r: len(indices) for r, indices in roles_map.items() if indices},
            "frequency_bands": [
                {
                    "band": b.band_name,
                    "range_hz": b.freq_range_hz,
                    "primary_roles": b.primary_roles,
                    "assigned_tracks": b.assigned_tracks,
                    "intruders": b.potential_intruders,
                }
                for b in bands
            ],
            "conflicts": [
                {
                    "code": c.code,
                    "severity": c.severity,
                    "track_indices": c.track_indices,
                    "description": c.description,
                    "suggested_action": c.suggested_action,
                }
                for c in conflicts
            ],
            "arrangement_sections": arrangement,
            "harmonic_context": harmonics,
            "recommendation_summary": f"Detected {len(conflicts)} acoustic/frequency allocation opportunities across {len(nodes)} tracks.",
        }

    analyze = build_world_model

    @classmethod
    def infer_arrangement_sections(cls, session_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Infer arrangement song sections from locators or scene names."""
        sections: List[Dict[str, Any]] = []
        locators = session_state.get("locators", [])
        tracks = session_state.get("tracks", [])

        # Calculate clip density across tracks if available
        active_clip_count = 0
        total_clips = 0
        for t in tracks:
            clip_slots = t.get("clip_slots", [])
            for cs in clip_slots:
                total_clips += 1
                if cs.get("has_clip"):
                    active_clip_count += 1
        density_ratio = (active_clip_count / max(total_clips, 1)) if total_clips > 0 else 0.50

        if locators:
            sorted_locs = sorted(locators, key=lambda l: float(l.get("time", l.get("bar", 1.0))))
            for idx, loc in enumerate(sorted_locs):
                name = str(loc.get("name", "")).strip()
                bar = float(loc.get("time", loc.get("bar", 1.0)))
                norm_name = name.lower()
                next_bar = float(sorted_locs[idx + 1].get("time", sorted_locs[idx + 1].get("bar", bar + 16.0))) if idx + 1 < len(sorted_locs) else bar + 16.0
                bar_span = max(1.0, next_bar - bar)


                # Estimate section kind and target dynamic energy
                if "intro" in norm_name:
                    kind, energy = "intro", 0.35
                elif "verse" in norm_name:
                    kind, energy = "verse", 0.50
                elif "build" in norm_name or "pre" in norm_name:
                    kind, energy = "build", 0.75
                elif "drop" in norm_name or "chorus" in norm_name:
                    kind, energy = "drop", 1.00
                elif "break" in norm_name:
                    kind, energy = "breakdown", 0.40
                elif "outro" in norm_name:
                    kind, energy = "outro", 0.30
                else:
                    kind, energy = "section", 0.60

                sections.append({
                    "name": name or f"Section at Bar {bar:.0f}",
                    "kind": kind,
                    "start_bar": bar,
                    "bar_length": bar_span,
                    "target_energy": energy,
                    "clip_density": round(density_ratio, 2),
                })
            return sections

        # Fallback to scenes
        scenes = session_state.get("scenes", [])
        for idx, sc in enumerate(scenes, start=1):
            name = str(sc.get("name", f"Scene {idx}")).strip()
            norm = name.lower()
            if "intro" in norm:
                kind, energy = "intro", 0.35
            elif "drop" in norm or "chorus" in norm:
                kind, energy = "drop", 1.00
            elif "verse" in norm:
                kind, energy = "verse", 0.50
            else:
                kind, energy = "scene", 0.60
            sections.append({
                "name": name,
                "kind": kind,
                "index": idx,
                "target_energy": energy,
                "clip_density": round(density_ratio, 2),
            })

        if not sections:
            sections = [
                {
                    "name": "Full Arrangement",
                    "kind": "master",
                    "start_bar": 1.0,
                    "bar_length": 64.0,
                    "target_energy": 0.80,
                    "clip_density": round(density_ratio, 2),
                }
            ]

        return sections

    @classmethod
    def harmonic_context(cls, session_state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract global musical key, mode, scale, and tempo context with MIDI note inference."""
        tempo = float(session_state.get("tempo", 120.0))
        root_note = str(session_state.get("root_note", session_state.get("scale_root", "C"))).strip()
        scale_name = str(session_state.get("scale_name", session_state.get("scale", "Minor"))).strip()
        signature_num = int(session_state.get("signature_numerator", 4))
        signature_denom = int(session_state.get("signature_denominator", 4))

        # Check if session has active MIDI notes for neural scale detection
        detected_scale_info: Optional[Dict[str, Any]] = None
        midi_notes_corpus = []
        for track in session_state.get("tracks", []):
            for clip_slot in track.get("clip_slots", []):
                notes = clip_slot.get("notes", [])
                if notes:
                    midi_notes_corpus.extend(notes)

        if midi_notes_corpus:
            try:
                from kenn.core.generative_midi import detect_scale_from_notes
                detected_scale_info = detect_scale_from_notes(midi_notes_corpus)
                if detected_scale_info.get("confidence", 0.0) >= 0.55:
                    root_note = detected_scale_info["root"]
                    scale_name = detected_scale_info["scale"].capitalize()
            except Exception:
                pass

        res = {
            "tempo_bpm": tempo,
            "root_note": root_note,
            "scale_name": scale_name,
            "key_signature": f"{root_note} {scale_name}",
            "time_signature": f"{signature_num}/{signature_denom}",
        }
        if detected_scale_info:
            res["scale_detection"] = detected_scale_info
        return res


__all__ = [
    "DELTA_SCHEMA",
    "MAX_EVENTS",
    "SessionWorldModel",
    "diff_session_contexts",
    "ROLE_KICK",
    "ROLE_SUB_BASS",
    "ROLE_MID_BASS",
    "ROLE_SNARE",
    "ROLE_HIHATS",
    "ROLE_DRUMS_BUS",
    "ROLE_LEAD_VOCAL",
    "ROLE_BACKING_VOCAL",
    "ROLE_SYNTH_LEAD",
    "ROLE_PADS_REVERB",
    "ROLE_FX_RISER",
    "ROLE_GENERIC",
    "ALL_ROLES",
    "TrackSemanticNode",
    "FrequencyBandAllocation",
    "SemanticConflict",
]
