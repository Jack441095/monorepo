"""Deterministic, capability-aware analysis of the Live session snapshot.

This is deliberately separate from chat and the HTTP server.  It is the
shared boundary between the Ableton bridge and present/future analysers: a
field is only represented when the bridge supplied it, and unavailable data
is reported as a limitation instead of guessed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


@dataclass(frozen=True)
class ProjectDevice:
    index: int
    name: str
    is_active: bool | None = None


@dataclass(frozen=True)
class ProjectTrack:
    index: int
    name: str
    volume: float | None
    pan: float | None
    muted: bool
    soloed: bool
    armed: bool
    devices: tuple[ProjectDevice, ...] = ()
    is_group: bool = False
    group_name: str | None = None
    session_clip_count: int | None = None
    arrangement_clip_count: int | None = None
    output_meter_level: float | None = None
    output_meter_right: float | None = None
    color: int | None = None
    inferred_role: str | None = None


@dataclass(frozen=True)
class ProjectBus:
    index: int
    name: str
    volume: float | None
    pan: float | None
    devices: tuple[ProjectDevice, ...] = ()
    output_meter_level: float | None = None
    output_meter_right: float | None = None


@dataclass(frozen=True)
class NormalizedProject:
    status: str
    tempo: float | None
    is_playing: bool | None
    tracks: tuple[ProjectTrack, ...]
    scenes: tuple[dict[str, Any], ...]
    selected_track_index: int | None
    return_tracks: tuple[ProjectBus, ...]
    master_track: ProjectBus | None
    available_capabilities: tuple[str, ...]
    unavailable_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class Recommendation:
    title: str
    category: str
    severity: str
    confidence: float
    description: str
    reason: str
    suggestedAction: str
    canAutoFix: bool = False
    requiresConfirmation: bool = True
    track_indices: tuple[int, ...] = field(default_factory=tuple)

    def payload(self) -> dict[str, Any]:
        result = asdict(self)
        result["track_indices"] = list(self.track_indices)
        return result


_GENERIC_TRACK_NAME = re.compile(r"^(?:track|audio|midi)\s*\d*$", re.I)
_ROLE_WORDS = (
    ("drums", ("drum", "kick", "snare", "hat", "perc", "clap")),
    ("bass", ("bass", "sub", "808")),
    ("vocal", ("vocal", "vox", "lead vocal", "adlib")),
    ("keys", ("piano", "keys", "pad", "chord")),
    ("lead", ("lead", "melody", "pluck")),
    ("fx", ("fx", "riser", "impact", "noise", "transition")),
)


def detect_project_analysis_request(question: str) -> str | None:
    """Classify only requests that need the deterministic Live snapshot."""
    lowered = question.lower()
    if any(phrase in lowered for phrase in ("clean up this project", "organise this project", "organize this project", "organise my ", "organize my ", "find unused tracks", "project manager")):
        return "project_manager"
    if any(phrase in lowered for phrase in ("which plugins are using the most cpu", "plugin optimizer", "optimise plugins", "optimize plugins")):
        return "plugin_optimizer"
    # A broad mix-diagnosis question belongs to KENN's evidence-aware chat
    # path, where plug-in/Mix Review audio facts can be considered.  The Live
    # project analyser only has structural data, so intercepting "what is
    # wrong with my mix?" here produced a misleading project report instead
    # of an honest audio-diagnosis boundary.
    if any(phrase in lowered for phrase in ("project doctor", "project health", "mix health", "is my low end balanced", "analyse low end", "analyze low end")):
        return "project_health"
    if any(phrase in lowered for phrase in ("analyse arrangement", "analyze arrangement", "arrangement assistant", "why does my drop feel weak", "section more interesting")):
        return "arrangement"
    if "make this more interesting" in lowered or "creative suggestions" in lowered:
        return "creative"
    return None


def infer_track_role(name: str) -> str | None:
    lowered = name.lower()
    for role, words in _ROLE_WORDS:
        if any(word in lowered for word in words):
            return role
    return None


def normalize_session(session: dict[str, Any] | None) -> NormalizedProject:
    """Convert the bridge snapshot to a stable, typed project representation."""
    session = session or {}
    tracks = []
    for position, raw in enumerate(session.get("tracks") or []):
        index = int(raw.get("index", position))
        name = str(raw.get("name") or "").strip()
        devices = tuple(
            ProjectDevice(
                int(device.get("index", device_position)), str(device.get("name") or "").strip(),
                device.get("is_active") if isinstance(device.get("is_active"), bool) else None,
            )
            for device_position, device in enumerate(raw.get("devices") or [])
        )
        tracks.append(ProjectTrack(
            index=index, name=name, volume=_optional_float(raw.get("volume")),
            pan=_optional_float(raw.get("pan")), muted=bool(raw.get("muted")),
            soloed=bool(raw.get("soloed")), armed=bool(raw.get("armed")), devices=devices,
            is_group=bool(raw.get("is_group")), group_name=_optional_name(raw.get("group_name")),
            session_clip_count=_optional_int(raw.get("session_clip_count")),
            arrangement_clip_count=_optional_int(raw.get("arrangement_clip_count")),
            output_meter_level=_optional_float(raw.get("output_meter_level")),
            output_meter_right=_optional_float(raw.get("output_meter_right")),
            color=_optional_int(raw.get("color")),
            inferred_role=infer_track_role(name),
        ))
    return NormalizedProject(
        status=str(session.get("status") or "unknown"), tempo=_optional_float(session.get("tempo")),
        is_playing=session.get("is_playing") if isinstance(session.get("is_playing"), bool) else None,
        tracks=tuple(tracks), scenes=tuple(session.get("scenes") or []),
        selected_track_index=_optional_int(session.get("selected_track_index")),
        return_tracks=tuple(_normalize_bus(raw, index) for index, raw in enumerate(session.get("return_tracks") or [])),
        master_track=_normalize_bus(session["master_track"], 0) if isinstance(session.get("master_track"), dict) else None,
        available_capabilities=("track_names", "mixer_state", "device_names", "device_active_state", "scenes", "tempo", "transport", "track_groups", "clip_presence", "returns", "master"),
        unavailable_capabilities=(
            "clip_content", "clip_types", "routing", "sends_returns_master",
            "device_cpu", "plugin_latency", "automation", "arrangement_sections",
            "audio_spectrum", "loudness", "stereo_width", "phase_measurement",
        ),
    )


def analyze_project_manager(project: NormalizedProject) -> list[Recommendation]:
    """Produce safe, structural recommendations from fields actually present."""
    recommendations: list[Recommendation] = []
    generic_tracks = [track for track in project.tracks if not track.name or _GENERIC_TRACK_NAME.match(track.name)]
    for track in generic_tracks:
        label = track.name or f"Track {track.index + 1}"
        role_hint = f"; it may be a {track.inferred_role} track" if track.inferred_role else ""
        recommendations.append(Recommendation(
            title=f"Name {label}", category="organisation", severity="info", confidence=0.98,
            description=f"'{label}' uses Ableton's generic naming pattern{role_hint}.",
            reason="Clear names make navigation, handoff, and later analysis more reliable.",
            suggestedAction="Preview a descriptive name before applying it.", track_indices=(track.index,),
        ))
    by_name: dict[str, list[ProjectTrack]] = {}
    for track in project.tracks:
        normalized_name = " ".join(track.name.lower().split())
        if normalized_name and not _GENERIC_TRACK_NAME.match(track.name):
            by_name.setdefault(normalized_name, []).append(track)
    for duplicate_tracks in by_name.values():
        if len(duplicate_tracks) > 1:
            names = ", ".join(track.name for track in duplicate_tracks)
            recommendations.append(Recommendation(
                title=f"Review duplicate track names: {duplicate_tracks[0].name}", category="organisation",
                severity="warning", confidence=0.95,
                description=f"{len(duplicate_tracks)} tracks share the name '{names}'.",
                reason="They may be intentional layers, but identical names make them hard to distinguish.",
                suggestedAction="Preview unique names or confirm that these are intentional layers.",
                track_indices=tuple(track.index for track in duplicate_tracks),
            ))
    # Similarity is deliberately limited to names.  This is not a duplicate-
    # audio detector because the bridge has no clip/sample content.
    similar_pairs: list[tuple[ProjectTrack, ProjectTrack]] = []
    named_tracks = [track for track in project.tracks if track.name and not _GENERIC_TRACK_NAME.match(track.name)]
    for position, left in enumerate(named_tracks):
        left_terms = _name_terms(left.name)
        for right in named_tracks[position + 1:]:
            if " ".join(left.name.lower().split()) == " ".join(right.name.lower().split()):
                continue
            right_terms = _name_terms(right.name)
            if left_terms and right_terms and len(left_terms & right_terms) / min(len(left_terms), len(right_terms)) >= 0.5:
                similar_pairs.append((left, right))
    for left, right in similar_pairs[:5]:
        recommendations.append(Recommendation(
            title=f"Review similarly named tracks: {left.name} / {right.name}",
            category="organisation", severity="info", confidence=0.65,
            description="Their names share most meaningful words.",
            reason="This may describe intentional layers; the current bridge cannot compare their audio or MIDI content.",
            suggestedAction="Confirm their roles and use clearer layer names or a common colour/group if useful.",
            track_indices=(left.index, right.index),
        ))
    role_tracks: dict[str, list[ProjectTrack]] = {}
    for track in project.tracks:
        if track.inferred_role:
            role_tracks.setdefault(track.inferred_role, []).append(track)
    for role, tracks in role_tracks.items():
        if len(tracks) >= 3:
            recommendations.append(Recommendation(
                title=f"Consider grouping {role} tracks", category="organisation", severity="info", confidence=0.65,
                description=f"{len(tracks)} tracks are likely {role} elements based on their names.",
                reason="A group can make navigation and bus processing easier; this is a suggestion, not a detected fault.",
                suggestedAction="Preview a group and colour assignment before creating it.",
                track_indices=tuple(track.index for track in tracks),
            ))
            if any(track.color is None for track in tracks):
                recommendations.append(Recommendation(
                    title=f"Consider a shared colour for {role}", category="organisation", severity="info", confidence=0.55,
                    description=f"{len(tracks)} likely {role} tracks could be easier to scan with a consistent colour.",
                    reason="The role is inferred from names, so this is a presentation suggestion only.",
                    suggestedAction="Preview a colour assignment before applying it.",
                    track_indices=tuple(track.index for track in tracks),
                ))
    for track in project.tracks:
        if track.session_clip_count is not None and track.arrangement_clip_count is not None:
            if track.session_clip_count == 0 and track.arrangement_clip_count == 0:
                recommendations.append(Recommendation(
                    title=f"Review empty track: {track.name or f'Track {track.index + 1}'}",
                    category="organisation", severity="info", confidence=0.82,
                    description="No Session View or Arrangement View clips were reported on this track.",
                    reason="It may be a deliberate recording, routing, or placeholder track; clip presence alone cannot prove it is unused.",
                    suggestedAction="Confirm its purpose before hiding, deleting, or repurposing it.",
                    track_indices=(track.index,),
                ))
        inactive_devices = [device.name for device in track.devices if device.is_active is False]
        if inactive_devices:
            recommendations.append(Recommendation(
                title=f"Review inactive devices on {track.name or f'Track {track.index + 1}'}",
                category="organisation", severity="info", confidence=0.9,
                description=f"Inactive device(s): {', '.join(inactive_devices)}.",
                reason="They may be deliberate A/B options; their processing is currently bypassed.",
                suggestedAction="Confirm whether to retain, reactivate, or remove them manually.",
                track_indices=(track.index,),
            ))
    return recommendations


def project_manager_report(session: dict[str, Any] | None) -> dict[str, Any]:
    project = normalize_session(session)
    recommendations = analyze_project_manager(project)
    return {
        "ok": project.status == "connected",
        "status": project.status,
        "summary": {"track_count": len(project.tracks), "recommendation_count": len(recommendations)},
        "recommendations": [item.payload() for item in recommendations],
        "available_data": list(project.available_capabilities),
        "unavailable_data": list(project.unavailable_capabilities),
    }


def analyze_project_doctor(project: NormalizedProject) -> list[Recommendation]:
    """Health checks supported by structural and instantaneous meter state.

    A Live output meter is not a true-peak, LUFS, or spectral measurement,
    so meter findings are deliberately phrased as a momentary observation.
    """
    recommendations: list[Recommendation] = []
    soloed = [track for track in project.tracks if track.soloed]
    if soloed:
        recommendations.append(Recommendation(
            title="Tracks remain soloed", category="project_health", severity="warning", confidence=0.99,
            description=f"{len(soloed)} track(s) are currently soloed.",
            reason="Solo state can unintentionally hide parts of the project during playback or review.",
            suggestedAction="Confirm the solos are intentional before clearing them.",
            track_indices=tuple(track.index for track in soloed),
        ))
    for track in project.tracks:
        readings = [value for value in (track.output_meter_level, track.output_meter_right) if value is not None]
        if readings and max(readings) >= 0.98:
            recommendations.append(Recommendation(
                title=f"Check headroom on {track.name or f'Track {track.index + 1}'}",
                category="mix_health", severity="warning", confidence=0.75,
                description="Its latest Live output-meter reading is close to the meter ceiling.",
                reason="This is an instantaneous post-fader reading, not proof of clipping or a true-peak measurement.",
                suggestedAction="Play the loudest section and inspect the meter/true-peak meter before adjusting gain.",
                track_indices=(track.index,),
            ))
    if project.master_track is not None:
        master_levels = [
            level for level in (project.master_track.output_meter_level, project.master_track.output_meter_right)
            if level is not None
        ]
        if master_levels and max(master_levels) >= 0.98:
            recommendations.append(Recommendation(
                title="Check master headroom", category="mix_health", severity="warning", confidence=0.78,
                description="The latest master output-meter reading is close to the meter ceiling.",
                reason="This is an instantaneous Live meter observation, not proof of true-peak clipping.",
                suggestedAction="Play the loudest section and verify true peak before changing master gain or limiting.",
            ))
    return recommendations


def analyze_plugin_optimizer(project: NormalizedProject) -> list[Recommendation]:
    """Device-state recommendations without pretending to know CPU or latency."""
    recommendations: list[Recommendation] = []
    by_device: dict[str, list[ProjectTrack]] = {}
    device_labels: dict[str, str] = {}
    for track in project.tracks:
        for device in track.devices:
            if device.name:
                by_device.setdefault(device.name.lower(), []).append(track)
                device_labels.setdefault(device.name.lower(), device.name)
    for name, tracks in by_device.items():
        if len(tracks) >= 4:
            recommendations.append(Recommendation(
                title=f"Review repeated device: {device_labels[name]}",
                category="plugin_optimisation", severity="info", confidence=0.7,
                description=f"'{name}' appears on {len(tracks)} tracks.",
                reason="Repeated processing can be intentional; CPU cost and latency are not available from this bridge.",
                suggestedAction="Compare instances manually and consider shared bus processing where artistically appropriate.",
                track_indices=tuple(track.index for track in tracks),
            ))
    return recommendations


def analyze_arrangement(project: NormalizedProject) -> list[Recommendation]:
    """Offer Session View structure suggestions from scene names/clip density.

    This is intentionally not an Arrangement View analyser: the bridge has
    no timeline, clip duration, waveform, or automation data.
    """
    recommendations: list[Recommendation] = []
    unnamed = [scene for scene in project.scenes if not str(scene.get("name") or "").strip()]
    if unnamed:
        recommendations.append(Recommendation(
            title="Name Session View scenes", category="arrangement", severity="info", confidence=0.98,
            description=f"{len(unnamed)} scene(s) have no name.",
            reason="Named scenes make it easier to reason about sections and transitions without changing musical content.",
            suggestedAction="Preview descriptive section names such as Intro, Build, Drop, or Break.",
        ))
    densities = [
        (int(scene.get("index", position)), int(scene.get("active_clip_count", 0)))
        for position, scene in enumerate(project.scenes)
        if scene.get("active_clip_count") is not None
    ]
    if len(densities) >= 2:
        minimum = min(count for _index, count in densities)
        maximum = max(count for _index, count in densities)
        if maximum - minimum >= 4:
            recommendations.append(Recommendation(
                title="Review Session View density changes", category="arrangement", severity="info", confidence=0.8,
                description=f"The populated-scene count ranges from {minimum} to {maximum} active clips.",
                reason="This indicates a structural contrast, not whether a section is good or bad.",
                suggestedAction="Audition transitions and decide whether the contrast supports the intended energy curve.",
            ))
    return recommendations


def creative_suggestions_for_selected_track(project: NormalizedProject) -> list[Recommendation]:
    """Give multiple non-destructive ideas for the track selected in Live."""
    selected = next((track for track in project.tracks if track.index == project.selected_track_index), None)
    if selected is None:
        return []
    role = selected.inferred_role or "selected"
    ideas = {
        "drums": ("Add a sparse fill before a transition", "Vary one percussion rhythm every 4 or 8 bars", "Automate a short filtered or reverbed accent into the next section"),
        "bass": ("Try a brief octave or rhythm variation at the end of a phrase", "Use a short filter movement only at section transitions", "Create a call-and-response layer above the main bass phrase"),
        "vocal": ("Try a selective delay throw on one phrase", "Create a restrained call-and-response ad-lib", "Automate reverb send into a transition, then return to the dry lead"),
        "fx": ("Shape a transition with a filtered rise or fall", "Try stereo movement above the low end only", "Use a short silence or reverse accent before an impact"),
    }.get(role, ("Vary one rhythmic detail at the end of a phrase", "Try a subtle filter or send movement at a section boundary", "Add a call-and-response layer, then compare it against the original"))
    return [
        Recommendation(
            title=f"Creative option: {idea}", category="creative", severity="info", confidence=0.55,
            description=f"Idea for '{selected.name or f'Track {selected.index + 1}'}' ({role} role inferred from its name).",
            reason="This is a creative option, not a detected problem or a claim about the track's audio content.",
            suggestedAction="Preview it on a duplicate or undoable change, then A/B against the original.",
            track_indices=(selected.index,),
        )
        for idea in ideas
    ]


def project_health_report(session: dict[str, Any] | None) -> dict[str, Any]:
    project = normalize_session(session)
    recommendations = [
        *analyze_project_manager(project),
        *analyze_project_doctor(project),
        *analyze_plugin_optimizer(project),
    ]
    return {
        "ok": project.status == "connected",
        "status": project.status,
        "summary": {"track_count": len(project.tracks), "recommendation_count": len(recommendations)},
        "recommendations": [item.payload() for item in recommendations],
        "available_data": list(project.available_capabilities),
        "unavailable_data": list(project.unavailable_capabilities),
    }


def format_analysis_answer(kind: str, report: dict[str, Any]) -> str:
    """Present deterministic findings without handing interpretation to a prompt."""
    if report.get("status") != "connected":
        return "I need an active Ableton connection before I can analyse the current project."
    recommendations = report.get("recommendations") or []
    if not recommendations:
        message = "I found no structural issues in the currently available Ableton data. This does not measure audio quality, CPU, routing, or arrangement detail."
        if kind == "project_health" and "audio_spectrum" in report.get("unavailable_data", []):
            message += " Low-end balance, masking, LUFS, and stereo measurements need an uploaded/rendered audio analysis; Live's current bridge only provides structural state and instantaneous meters."
        return message
    heading = {
        "project_manager": "Project organisation suggestions",
        "plugin_optimizer": "Plugin and device review",
        "project_health": "Project health findings",
        "arrangement": "Session View arrangement suggestions",
        "creative": "Creative options for the selected Live track",
    }.get(kind, "Project analysis")
    lines = [f"{heading}:"]
    for item in recommendations[:6]:
        lines.append(f"- {item['title']}: {item['description']} {item['suggestedAction']}")
    if "device_cpu" in report.get("unavailable_data", []):
        lines.append("CPU and plug-in latency are not exposed by the current Ableton bridge, so I have not estimated them.")
    if kind == "project_health" and "audio_spectrum" in report.get("unavailable_data", []):
        lines.append("Low-end balance, masking, LUFS, and stereo measurements need an uploaded/rendered audio analysis; Live's current bridge only provides structural state and instantaneous meters.")
    return "\n".join(lines)


def recommendations_from_mix_review(review: dict[str, Any] | None) -> list[Recommendation]:
    """Adapt measured uploaded-audio findings to the common contract.

    A review is evidence about an uploaded/rendered file, never about the
    current Live session.  The source distinction prevents a stale bounce
    from being presented as live-meter data.
    """
    review = review or {}
    recommendations: list[Recommendation] = []
    for flag in review.get("flags") or []:
        if not isinstance(flag, dict):
            continue
        label = str(flag.get("label") or "Measured mix finding").strip()
        detail = str(flag.get("detail") or flag.get("message") or "").strip()
        confidence_value = str(flag.get("confidence") or "medium").lower()
        confidence = {"high": 0.9, "medium": 0.7, "low": 0.5}.get(confidence_value, 0.6)
        severity = {"high": "critical", "critical": "critical", "medium": "warning", "low": "info"}.get(
            str(flag.get("severity") or "").lower(), "warning"
        )
        recommendations.append(Recommendation(
            title=label, category="mix_health", severity=severity, confidence=confidence,
            description=detail or "Detected in the uploaded audio analysis.",
            reason="This finding is based on a measured uploaded/rendered audio file, not the live Ableton session.",
            suggestedAction="Review the related Mix Review action plan and confirm changes by ear.",
        ))
    comparison = review.get("reference_comparison") if isinstance(review.get("reference_comparison"), dict) else {}
    largest = comparison.get("largest_spectral_difference") if isinstance(comparison.get("largest_spectral_difference"), dict) else {}
    band = str(largest.get("band") or "").strip()
    if band:
        delta = largest.get("delta_db", largest.get("delta"))
        amount = f" ({float(delta):+.1f} dB)" if isinstance(delta, (int, float)) else ""
        recommendations.append(Recommendation(
            title=f"Compare {band.replace('_', ' ')} with reference", category="reference", severity="info", confidence=0.8,
            description=f"The uploaded mix/reference comparison found its largest spectral difference in {band.replace('_', ' ')}{amount}.",
            reason="The comparison uses the supplied reference file; it is not a genre-target assumption.",
            suggestedAction="Level-match, audition the relevant section, and preview any EQ move before applying it.",
        ))
    return recommendations


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_name(value: Any) -> str | None:
    value = str(value or "").strip()
    return value or None


def _name_terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 1 and not term.isdigit()}


def _normalize_bus(raw: dict[str, Any], default_index: int) -> ProjectBus:
    devices = tuple(
        ProjectDevice(
            int(device.get("index", position)), str(device.get("name") or "").strip(),
            device.get("is_active") if isinstance(device.get("is_active"), bool) else None,
        )
        for position, device in enumerate(raw.get("devices") or [])
    )
    return ProjectBus(
        index=_optional_int(raw.get("index")) if _optional_int(raw.get("index")) is not None else default_index,
        name=str(raw.get("name") or "").strip(), volume=_optional_float(raw.get("volume")),
        pan=_optional_float(raw.get("pan")), devices=devices,
        output_meter_level=_optional_float(raw.get("output_meter_level")),
        output_meter_right=_optional_float(raw.get("output_meter_right")),
    )
