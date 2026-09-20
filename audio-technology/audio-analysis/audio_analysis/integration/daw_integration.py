"""DAW session export for AutoMix (Stage 9.3).

Exports a rendered ``MixPlan`` (see ``mixdown/mix_decision_engine.py``) to an
Ableton Live Set (``.als``) — gzip-compressed XML, matching the on-disk
format Ableton Live itself writes. Cubase track archive export is lower
priority and is not implemented here (see module docstring at the bottom for
the honest scope note).

Verification caveat
--------------------
There is no Ableton Live install available in this environment, so this
module cannot be verified by a real Live import round-trip. What *is*
verified (see ``tests/test_daw_integration.py``):

- The exported bytes gunzip to well-formed XML (``xml.etree.ElementTree``
  parses it without error).
- The document root and structure match the documented shape of Ableton's
  Live Set XML schema as observed in this repo's own existing gzip'd Ableton
  XML (``integration/ableton_exports.py``'s ``<Ableton MajorVersion=...
  Creator="Ableton Live 11">`` wrapper) and Ableton's publicly documented
  Live Set format: a versioned ``<Ableton>`` root wrapping a ``<LiveSet>``
  with ``<Tracks>``, per-track ``<AudioTrack>``/``<MidiTrack>`` elements
  each carrying a ``<Name><EffectiveName Value="..."/></Name>``, a
  ``<DeviceChain>`` with a ``<Mixer>`` (``<Volume><Manual Value="..."/>``,
  ``<Pan><Manual Value="..."/>``) and a nested ``<DeviceChain><Devices>``
  list holding device XML blocks (``Eq8``, ``Compressor2``) whose parameter
  shape mirrors the same ``<On Value=.../><Bands>...`` pattern already used
  by ``ableton_exports.generate_correction_rack``.
- Track count, names, gain/pan values, and device parameter values in the
  exported XML match the input ``MixPlan`` exactly (round-tripped by
  re-parsing the XML in the test, not by opening the file in Live).

This is *not* a substitute for opening the file in Ableton Live 12 and
confirming it imports — that verification step could not be performed here.
"""

from __future__ import annotations

import dataclasses
import gzip
from typing import Any
from xml.sax.saxutils import escape as _xml_escape


def _as_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return dict(obj)
    return {}


def _pan_to_live_pan(pan: float) -> float:
    """AutoMix pan is -1.0..+1.0 (left..right); Ableton's Pan Manual value uses the same range."""
    return max(-1.0, min(1.0, float(pan)))


def _db_to_live_volume(db: float) -> float:
    """Ableton's Volume Manual value is a normalized [0, 1] fader position, not
    raw linear gain — unity (0 dB) sits at ~0.85, the reverse-engineered
    reference point used by ALS-generation tools, with position 1.0 reached
    a few dB above unity. Clamped so a generated session never asks Ableton
    to load an out-of-range fader value."""
    linear = 10 ** (float(db) / 20.0)
    return max(0.0, min(1.0, 0.85 * linear))


_EQ8_BAND_MODE = {
    "highpass": 1,
    "lowshelf": 2,
    "peaking": 2,
    "highshelf": 3,
    "lowpass": 4,
    "notch": 5,
}


def _eq8_device_xml(eq_bands: list[dict], device_id: int) -> str:
    """Render up to 8 EQ bands from a StemMixConfig/BusMixConfig onto an Eq8 device."""
    bands_xml = []
    for index in range(8):
        if index < len(eq_bands):
            band = eq_bands[index]
            freq = float(band.get("frequency", 1000.0))
            gain = float(band.get("gain_db", 0.0))
            q = float(band.get("q", 0.707))
            mode = _EQ8_BAND_MODE.get(str(band.get("type", "peaking")), 2)
            on = "true"
        else:
            freq, gain, q, mode, on = 1000.0, 0.0, 0.707, 2, "false"
        bands_xml.append(
            f"""				<Band id="{index}">
					<On Value="{on}" />
					<Mode Value="{mode}" />
					<Frequency Value="{freq:.3f}" />
					<Gain Value="{gain:.3f}" />
					<Q Value="{q:.3f}" />
				</Band>"""
        )
    return f"""			<Eq8 Id="{device_id}">
				<On Value="{'true' if eq_bands else 'false'}" />
				<IsExpanded Value="true" />
				<Bands>
{chr(10).join(bands_xml)}
				</Bands>
			</Eq8>"""


def _compressor_device_xml(compressor: dict | None, device_id: int) -> str:
    if not compressor:
        return ""
    ratio = float(compressor.get("ratio", 2.0))
    attack = float(compressor.get("attack_ms", 10.0))
    release = float(compressor.get("release_ms", 100.0))
    threshold = float(compressor.get("threshold_db", -12.0))
    makeup = float(compressor.get("makeup_gain_db", 0.0))
    return f"""			<Compressor2 Id="{device_id}">
				<On Value="true" />
				<IsExpanded Value="true" />
				<Ratio Value="{ratio:.3f}" />
				<AttackTime Value="{attack:.3f}" />
				<ReleaseTime Value="{release:.3f}" />
				<Threshold Value="{threshold:.3f}" />
				<MakeupGain Value="{makeup:.3f}" />
			</Compressor2>"""


def _reverb_send_xml(send_level: float) -> str:
    return f"""			<SendPreBool Value="false" />
			<Send Id="0">
				<Manual Value="{max(0.0, min(1.0, float(send_level))):.3f}" />
			</Send>"""


def _track_xml(stem: dict, track_id: int, device_id_start: int) -> str:
    name = _xml_escape(str(stem.get("stem_name") or stem.get("instrument") or f"Track {track_id}"))
    gain_db = float(stem.get("gain_db", 0.0))
    pan = _pan_to_live_pan(float(stem.get("pan", 0.0)))
    volume_linear = _db_to_live_volume(gain_db)
    eq_bands = stem.get("eq_bands") or []
    compressor = stem.get("compressor")

    device_id = device_id_start
    devices = []
    eq_xml = _eq8_device_xml(eq_bands, device_id)
    devices.append(eq_xml)
    device_id += 1
    comp_xml = _compressor_device_xml(compressor, device_id)
    if comp_xml:
        devices.append(comp_xml)
        device_id += 1

    return f"""		<AudioTrack Id="{track_id}">
			<Name>
				<EffectiveName Value="{name}" />
				<UserName Value="{name}" />
			</Name>
			<Freeze Value="false" />
			<DeviceChain>
				<Mixer>
					<Volume>
						<Manual Value="{volume_linear:.6f}" />
					</Volume>
					<Pan>
						<Manual Value="{pan:.6f}" />
					</Pan>
					<Sends>
{_reverb_send_xml(float(stem.get("reverb_send", 0.0)))}
					</Sends>
				</Mixer>
				<DeviceChain>
					<Devices>
{chr(10).join(devices)}
					</Devices>
				</DeviceChain>
			</DeviceChain>
		</AudioTrack>"""


def _master_track_xml(bus: dict) -> str:
    bus_eq_bands = bus.get("bus_eq_bands") or []
    bus_compressor = bus.get("bus_compressor")
    devices = [_eq8_device_xml(bus_eq_bands, 900)]
    comp_xml = _compressor_device_xml(bus_compressor, 901)
    if comp_xml:
        devices.append(comp_xml)
    ceiling = float(bus.get("limiter_ceiling_db", -1.0))
    devices.append(
        f"""			<Limiter Id="902">
				<On Value="true" />
				<Ceiling Value="{ceiling:.3f}" />
			</Limiter>"""
    )
    return f"""		<MasterTrack>
			<Name>
				<EffectiveName Value="Master" />
			</Name>
			<DeviceChain>
				<Mixer>
					<Volume>
						<Manual Value="1.0" />
					</Volume>
				</Mixer>
				<DeviceChain>
					<Devices>
{chr(10).join(devices)}
					</Devices>
				</DeviceChain>
			</DeviceChain>
		</MasterTrack>"""


def build_als_xml(mix_plan: Any, *, project_name: str = "AutoMix Session") -> str:
    """Render a MixPlan (StemMixConfig list + BusMixConfig) as Ableton Live Set XML.

    Accepts either the real ``MixPlan`` dataclass (from
    ``mixdown/mix_decision_engine.py``) or an equivalent plain dict with
    ``stems``/``bus``/``genre``/``target_lufs`` keys — this keeps the
    exporter usable both from the render pipeline and from tests without a
    circular import on the mixdown package.
    """
    plan = _as_dict(mix_plan) if not hasattr(mix_plan, "stems") else {
        "stems": [_as_dict(s) for s in mix_plan.stems],
        "bus": _as_dict(mix_plan.bus),
        "genre": mix_plan.genre,
        "target_lufs": mix_plan.target_lufs,
        "mix_goal": getattr(mix_plan, "mix_goal", ""),
    }
    stems = plan.get("stems") or []
    bus = _as_dict(plan.get("bus"))

    track_blocks = []
    device_id = 0
    for index, stem in enumerate(stems):
        stem_dict = _as_dict(stem) if not isinstance(stem, dict) else stem
        track_blocks.append(_track_xml(stem_dict, track_id=index + 1, device_id_start=device_id))
        device_id += 2

    tracks_xml = "\n".join(track_blocks)
    master_xml = _master_track_xml(bus)
    project_name_escaped = _xml_escape(str(project_name))
    genre = _xml_escape(str(plan.get("genre", "")))
    target_lufs = plan.get("target_lufs")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Ableton MajorVersion="5" MinorVersion="12.0_12000" SchemaChangeCount="3" Creator="Audio Too AutoMix Exporter" Revision="0">
	<LiveSet>
		<Tracks>
{tracks_xml}
		</Tracks>
{master_xml}
		<Annotation Value="Exported by Audio Too AutoMix. Project: {project_name_escaped}. Genre: {genre}. Target LUFS: {target_lufs}." />
	</LiveSet>
</Ableton>
"""
    return xml


def als_bytes_for_delivery(mix_plan: Any, *, project_name: str = "AutoMix Session") -> bytes:
    """Render a MixPlan to gzip-compressed Ableton Live Set (.als) bytes."""
    xml = build_als_xml(mix_plan, project_name=project_name)
    return gzip.compress(xml.encode("utf-8"))


def export_als(mix_plan: Any, out_path, *, project_name: str = "AutoMix Session"):
    """Render a MixPlan to .als and write it to ``out_path``. Returns the path."""
    from pathlib import Path

    out_path = Path(out_path)
    out_path.write_bytes(als_bytes_for_delivery(mix_plan, project_name=project_name))
    return out_path


def validate_als_bytes(als_bytes: bytes) -> dict:
    """Structural validation: gunzip + well-formed XML + expected root shape.

    Returns a report dict rather than raising, so callers (and tests) can
    inspect *why* a structural check failed instead of only getting a
    traceback. This is the honest, verifiable substitute for a real Ableton
    Live import test (which this environment cannot perform).
    """
    import xml.etree.ElementTree as ET

    report: dict[str, Any] = {"ok": False, "errors": [], "checks": {}}
    try:
        xml_bytes = gzip.decompress(als_bytes)
    except OSError as exc:
        report["errors"].append(f"not valid gzip: {exc}")
        return report

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        report["errors"].append(f"not well-formed XML: {exc}")
        return report

    if root.tag != "Ableton":
        report["errors"].append(f"root element is '{root.tag}', expected 'Ableton'")
    if not root.get("MajorVersion") or not root.get("Creator"):
        report["errors"].append("root <Ableton> is missing MajorVersion/Creator attributes")

    live_set = root.find("LiveSet")
    if live_set is None:
        report["errors"].append("missing <LiveSet> under <Ableton>")
    else:
        tracks = live_set.find("Tracks")
        if tracks is None:
            report["errors"].append("missing <Tracks> under <LiveSet>")
        else:
            report["checks"]["audio_track_count"] = len(tracks.findall("AudioTrack"))
        master = live_set.find("MasterTrack")
        report["checks"]["has_master_track"] = master is not None
        report["checks"]["master_has_limiter"] = (
            master is not None and master.find(".//Limiter") is not None
        )

    report["ok"] = not report["errors"]
    return report


# ── Cubase track archive (lower priority; not implemented) ──────────────
#
# Cubase's track archive format (.trackarchive) is a proprietary binary/XML
# hybrid without a public schema, and was explicitly deprioritized in the
# Stage 9 task brief ("Cubase track archive is lower priority, do it only
# if Ableton export is solid"). It is intentionally not implemented in this
# module; ``export_als``/``build_als_xml`` above are the complete DAW export
# surface for this stage.
