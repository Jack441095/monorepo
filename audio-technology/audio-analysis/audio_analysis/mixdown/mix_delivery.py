"""Delivery pipeline module for automated mixdown system.

Handles:
  1. Versioned packaging of mixdowns (WAV, HTML reports, MD decisions, JSON manifest).
  2. ZIP archive generation for easy user download.

External notification belongs to the application outbox, not this DSP package.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ..integration.report_rendering import report_html
from .mix_validator import verify_render_output
from .stem_prep import write_wav


def _safe_stem_filename(name: str) -> str:
    """Filesystem-safe basename for a per-stem export, preserving readability."""
    base = Path(str(name)).name
    base = base.rsplit(".", 1)[0] if "." in base else base
    cleaned = "".join(c if (c.isalnum() or c in " _-") else "_" for c in base).strip()
    return (cleaned or "stem") + ".wav"


def _atomic_write_verified_wav(wav_bytes: bytes, final_path: Path, render_result: dict) -> dict:
    """Stage 7.5 — atomic, validated write of the rendered master WAV.

    Renders to a temp file in the *same directory* as ``final_path`` (so the
    final ``os.replace`` is an atomic rename on the same filesystem — never a
    cross-device copy), verifies the audio (no clipping, true peak under the
    mix plan's ceiling, plus phase-correlation/dynamic-range/LUFS diagnostics)
    against the in-memory rendered channels, and only then moves it into place.

    If verification fails, the temp file is discarded and a ``RuntimeError``
    is raised — the final path is never touched, so a caller can never observe
    a partially-written or invalid file there.
    """
    final_path = Path(final_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    mix_plan = render_result.get("mix_plan")
    target_lufs = getattr(mix_plan, "target_lufs", None) if mix_plan is not None else None
    ceiling_db = -1.0
    bus_config = getattr(mix_plan, "bus", None) if mix_plan is not None else None
    if bus_config is not None and getattr(bus_config, "limiter_ceiling_db", None) is not None:
        ceiling_db = bus_config.limiter_ceiling_db

    validation = verify_render_output(
        render_result.get("left", []),
        render_result.get("right", []),
        int(render_result.get("sample_rate", 44100)),
        wav_bytes,
        target_lufs=target_lufs,
        measured_lufs=render_result.get("measured_lufs"),
        ceiling_db=ceiling_db,
        expected_num_samples=render_result.get("source_num_samples"),
    )

    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{final_path.name}.", suffix=".tmp", dir=str(final_path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(wav_bytes)
            f.flush()
            os.fsync(f.fileno())

        if not validation["ok"]:
            raise RuntimeError(
                "Rendered mixdown failed validation before write; refusing to publish: "
                + "; ".join(validation["reasons"])
            )

        # Atomic rename — POSIX guarantees this replaces final_path in a single
        # operation; a reader will only ever see the old file or the new one,
        # never a partially-written intermediate state.
        os.replace(tmp_path, final_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return validation


def _encode_additional_format(render_result: dict, audio_format: str) -> bytes:
    """Encode a rendered stereo mix as FLAC or MP3."""
    requested = audio_format.strip().lower()
    if requested == "flac":
        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("FLAC export requires the soundfile package") from exc
        stereo = np.column_stack((render_result["left"], render_result["right"]))
        output = io.BytesIO()
        sf.write(output, stereo, int(render_result["sample_rate"]), format="FLAC", subtype="PCM_24")
        return output.getvalue()

    if requested == "mp3":
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("MP3 export requires ffmpeg")
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "wav",
                "-i",
                "pipe:0",
                "-map_metadata",
                "-1",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "320k",
                "-f",
                "mp3",
                "pipe:1",
            ],
            input=render_result["mixdown_wav_bytes"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"MP3 export failed: {error or 'ffmpeg returned no audio'}")
        return completed.stdout

    raise ValueError(f"Unsupported additional mix format: {audio_format}")


def attribute_flags(flags: list[dict], plan: Any) -> list[dict]:
    """Attribute technical review flags to section, stem, bus, and responsible decision where possible."""
    attributed = []
    
    # Safely extract plan details for matching
    decisions = getattr(plan, "decisions_log", []) or []
    if isinstance(decisions, dict):
        decisions = list(decisions.values())
    stems = getattr(plan, "stems", []) or []
    mono_compat = getattr(plan, "mono_compatibility", {}) or {}
    if not isinstance(mono_compat, dict):
        mono_compat = getattr(mono_compat, "to_dict", lambda: {})()
        if not isinstance(mono_compat, dict):
            mono_compat = {}
            
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        item = dict(flag)
        label = str(item.get("label", ""))
        detail = str(item.get("detail", ""))
        
        # Default attribution values
        section = "entire_song"
        stem = None
        bus = "master"
        responsible_decision = None
        
        # 1. Attribute to stem based on detail / stem names
        for s in stems:
            stem_name = ""
            if isinstance(s, dict):
                stem_name = str(s.get("stem_name", ""))
            else:
                stem_name = str(getattr(s, "stem_name", ""))
            if stem_name and (stem_name.lower() in detail.lower() or stem_name.lower() in label.lower()):
                stem = stem_name
                bus = None
                break
                
        # 2. Section & stem attribution from mono compatibility
        if any(token in label.lower() for token in ("mono", "correlation", "phase", "side channel", "side bass", "mud")):
            sections = mono_compat.get("summed_sections", []) or []
            for sec in sections:
                if isinstance(sec, dict) and sec.get("severity") in ("medium", "high"):
                    section = sec.get("section_id", "entire_song")
                    contributors = sec.get("contributors", []) or []
                    if contributors and not stem:
                        # Find contributor with highest improvement
                        try:
                            worst = max(
                                contributors,
                                key=lambda c: float(c.get("fold_down_improvement_db", 0.0) if isinstance(c, dict) else getattr(c, "fold_down_improvement_db", 0.0))
                            )
                            if isinstance(worst, dict):
                                stem = worst.get("stem_name")
                            else:
                                stem = getattr(worst, "stem_name", None)
                            if stem:
                                bus = None
                        except Exception:
                            pass
                    break
        elif "silence" in label.lower():
            if "intro" in label.lower() or "leading" in label.lower():
                section = "intro"
            elif "tail" in label.lower() or "trailing" in label.lower():
                section = "outro"
                
        # 3. Responsible decision attribution
        keywords = []
        if any(token in label.lower() for token in ("loudness", "lufs", "lra", "compressed", "dynamic", "crest", "spike")):
            keywords = ["loudness", "lufs", "limiter", "compressor", "gain"]
        elif any(token in label.lower() for token in ("headroom", "clipping", "peak")):
            keywords = ["limiter", "ceiling", "threshold", "gain"]
        elif any(token in label.lower() for token in ("build-up", "sub", "harshness", "presence", "top end", "balance", "tonal", "mud")):
            keywords = ["eq", "equalizer", "frequency", "resonance", "cut", "boost"]
        elif any(token in label.lower() for token in ("stereo", "width", "mono", "phase", "side")):
            keywords = ["width", "pan", "stereo", "mono", "phase", "polarity"]
            
        if keywords:
            # Look for the last matching decision line in the decisions log
            for dec in reversed(decisions):
                dec_str = str(dec)
                if any(kw in dec_str.lower() for kw in keywords):
                    if stem and stem.lower() in dec_str.lower():
                        responsible_decision = dec_str
                        break
                    elif not stem:
                        responsible_decision = dec_str
                        break
            if not responsible_decision:
                for dec in reversed(decisions):
                    dec_str = str(dec)
                    if any(kw in dec_str.lower() for kw in keywords):
                        responsible_decision = dec_str
                        break
                        
        item["attribution"] = {
            "section": section,
            "stem": stem,
            "bus": bus,
            "responsible_decision": responsible_decision,
        }
        attributed.append(item)
    return attributed


def package_mixdown_delivery(
    project_id: str,
    render_result: dict,
    output_dir: str | Path,
    recipient_email: str | None = None,
    download_url_template: str | None = None,
    additional_formats: tuple[str, ...] = (),
    correlation_id: str | None = None,
) -> dict:
    """Package the final mixdown, reports, and decision log into a versioned ZIP file.

    Parameters
    ----------
    project_id : str
        The unique project ID.
    render_result : dict
        The dictionary returned by validate_and_correct_mix.
    output_dir : str or Path
        Target directory to store the outputs (e.g. data/mix_outputs).
    recipient_email, download_url_template
        Retained as compatibility metadata. The application layer owns external
        notification through its durable outbox.
    correlation_id : str or None
        The originating request/job's correlation ID (e.g. `business/app`'s
        `automix_jobs.correlation_id`), stamped into the returned delivery
        status so a customer-support trace starting from a job/event log can
        follow it all the way to the actual delivered output — previously
        this function had no correlation-ID awareness at all, so whatever ID
        started the job was silently dropped at the final delivery step
        (docs/audits/2026-07-18-correlation-id-scoping.md). Falls back to a
        project/version-scoped synthesized ID if the caller doesn't have a
        real one (e.g. `scripts/automix_local.py`'s offline dev path, which
        has no job system to inherit from).
    """
    proj_dir = Path(output_dir) / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)

    # 1. Determine next version number
    version = 1
    while (proj_dir / f"mix_package_v{version}.zip").exists():
        version += 1

    resolved_correlation_id = str(correlation_id or "") or f"mixdown:{project_id}:v{version}"

    # Filenames for this version
    wav_filename = f"mixdown_v{version}.wav"
    html_filename = f"mix_report_v{version}.html"
    md_filename = f"mix_decisions_v{version}.md"
    json_filename = f"mix_decisions_v{version}.json"
    zip_filename = f"mix_package_v{version}.zip"

    # Full paths
    wav_path = proj_dir / wav_filename
    html_path = proj_dir / html_filename
    md_path = proj_dir / md_filename
    json_path = proj_dir / json_filename
    zip_path = proj_dir / zip_filename
    additional_paths: dict[str, Path] = {}

    # 2. Write Wav File — atomically, and only after passing validation (Stage 7.5).
    render_validation = _atomic_write_verified_wav(
        render_result["mixdown_wav_bytes"], wav_path, render_result
    )

    for requested_format in dict.fromkeys(item.lower() for item in additional_formats):
        encoded = _encode_additional_format(render_result, requested_format)
        format_path = proj_dir / f"mixdown_v{version}.{requested_format}"
        format_path.write_bytes(encoded)
        additional_paths[requested_format] = format_path

    # 2B. Write per-stem processed WAVs, if the render captured them
    # (mix_and_render_stems(..., capture_stem_audio=True)). Each is the fully
    # processed stem exactly as it summed into the master bus — so a per-stem
    # correction (de-mask, resonance cut) can be auditioned in isolation, where
    # its effect is audible rather than buried in the full mix. 24-bit to match
    # the master, in a stems_v{version}/ subdir alongside the mixdown.
    stem_audio = render_result.get("stem_audio") or {}
    stem_paths: dict[str, Path] = {}
    if stem_audio:
        stems_dir = proj_dir / f"stems_v{version}"
        stems_dir.mkdir(parents=True, exist_ok=True)
        sr_out = int(render_result.get("sample_rate", 44_100))
        for stem_name, channels in stem_audio.items():
            left, right = channels
            stem_wav = write_wav(list(left), list(right), sr_out, bit_depth=24)
            stem_path = stems_dir / _safe_stem_filename(stem_name)
            stem_path.write_bytes(stem_wav)
            stem_paths[str(stem_name)] = stem_path

    # 3. Write HTML report
    report = render_result.get("report", {})

    # Stage 9.5 — attach KENN's cited explanations for the mix plan's key
    # parameter decisions (gain, compression, reverb, width, limiter) so the
    # delivered report shows *why* AutoMix chose them, not just the values.
    # Best-effort: any KENN/index problem must never block mixdown delivery.
    if "kenn_explanations" not in report and render_result.get("mix_plan") is not None:
        try:
            from ..integration.kenn_handoff import annotate_mix_plan_with_kenn
            kenn_explanations = annotate_mix_plan_with_kenn(render_result["mix_plan"])
        except Exception:
            kenn_explanations = []
            logging.getLogger(__name__).warning(
                "KENN parameter explanation annotation failed; delivering report without it",
                exc_info=True,
            )

        # Stage C — same best-effort treatment for dynamic EQ cuts (Stage 9.5's
        # pattern extended to the dynamic EQ stage added 2026-07-09): explains
        # *why* AutoMix pulled down a specific frequency, grounded the same way.
        dynamic_eq_bands = render_result.get("dynamic_eq_bands")
        if dynamic_eq_bands:
            try:
                from ..integration.kenn_handoff import annotate_dynamic_eq_with_kenn
                mix_plan = render_result["mix_plan"]
                genre = getattr(mix_plan, "genre", None) or (
                    mix_plan.get("genre") if isinstance(mix_plan, dict) else None
                )
                kenn_explanations = kenn_explanations + annotate_dynamic_eq_with_kenn(
                    dynamic_eq_bands, genre=genre,
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "KENN dynamic EQ explanation annotation failed; delivering report without it",
                    exc_info=True,
                )

        # Stage 9.6 — same best-effort treatment for master bus EQ bands that
        # carry a stated reason (reference-track matching, verbal-feedback
        # correction, or a diagnostic caller-supplied band): explains *why*
        # that band is on the master bus, grounded the same way.
        mix_plan = render_result["mix_plan"]
        bus = getattr(mix_plan, "bus", None) or (
            mix_plan.get("bus") if isinstance(mix_plan, dict) else None
        )
        bus_eq_bands = getattr(bus, "bus_eq_bands", None) or (
            bus.get("bus_eq_bands") if isinstance(bus, dict) else None
        )
        if bus_eq_bands:
            try:
                from ..integration.kenn_handoff import annotate_bus_eq_bands_with_kenn
                genre = getattr(mix_plan, "genre", None) or (
                    mix_plan.get("genre") if isinstance(mix_plan, dict) else None
                )
                kenn_explanations = kenn_explanations + annotate_bus_eq_bands_with_kenn(
                    bus_eq_bands, genre=genre,
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "KENN bus EQ band explanation annotation failed; delivering report without it",
                    exc_info=True,
                )

        # Stage 9.7 — same best-effort treatment for the masking de-mask and
        # mono-compatibility correction stages: explains *why* AutoMix
        # adjusted a specific stem, grounded the same way. Both are still
        # opt-in/listening-gated stages, so these keys are only present (and
        # non-empty) on renders where the corresponding MixPlan flag was on.
        genre = getattr(mix_plan, "genre", None) or (
            mix_plan.get("genre") if isinstance(mix_plan, dict) else None
        )
        masking_corrections = render_result.get("masking_corrections")
        if masking_corrections:
            try:
                from ..integration.kenn_handoff import annotate_masking_corrections_with_kenn
                kenn_explanations = kenn_explanations + annotate_masking_corrections_with_kenn(
                    masking_corrections, genre=genre,
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "KENN masking correction explanation annotation failed; delivering report without it",
                    exc_info=True,
                )

        mono_compat_corrections = render_result.get("mono_compat_corrections")
        if mono_compat_corrections:
            try:
                from ..integration.kenn_handoff import annotate_mono_compat_corrections_with_kenn
                kenn_explanations = kenn_explanations + annotate_mono_compat_corrections_with_kenn(
                    mono_compat_corrections, genre=genre,
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "KENN mono-compat correction explanation annotation failed; delivering report without it",
                    exc_info=True,
                )

        if kenn_explanations:
            report = {**report, "kenn_explanations": kenn_explanations}

    html_content = report_html(report)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 4. Write MD decisions log
    plan = render_result["mix_plan"]
    md_lines = [
        f"# Automated Mix Decisions — Version {version}",
        "",
        f"**Genre:** {plan.genre}",
        f"**Target Loudness:** {plan.target_lufs} LUFS",
        f"**Final Measured Loudness:** {render_result.get('measured_lufs', 0.0):.1f} LUFS",
        "",
        "## Steps Log",
        "",
    ]
    for step in plan.decisions_log:
        md_lines.append(f"- {step}")
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # 5. Write JSON manifest
    # Serialize Stem configs
    stems_serializable = []
    for s in plan.stems:
        stems_serializable.append({
            "stem_name": s.stem_name,
            "instrument": s.instrument,
            "gain_db": s.gain_db,
            "pan": s.pan,
            "eq_bands": s.eq_bands,
            "compressor": s.compressor,
            "gate": s.gate,
            "reverb_send": s.reverb_send,
            "reverb_type": s.reverb_type,
            "reverb_decay_s": s.reverb_decay_s,
            "delay_send": s.delay_send,
            "stereo_width": s.stereo_width,
            "mono_below_hz": s.mono_below_hz,
            "saturation_drive_db": s.saturation_drive_db,
            "saturation_mix": s.saturation_mix,
        })
    
    bus_config = plan.bus
    bus_serializable = {
        "bus_compressor": bus_config.bus_compressor,
        "bus_eq_bands": bus_config.bus_eq_bands,
        "limiter_ceiling_db": bus_config.limiter_ceiling_db,
        "limiter_threshold_db": bus_config.limiter_threshold_db,
        "saturation_drive_db": bus_config.saturation_drive_db,
        "saturation_mix": bus_config.saturation_mix,
    }

    manifest = {
        "project_id": project_id,
        "correlation_id": resolved_correlation_id,
        "version": version,
        "genre": plan.genre,
        "mix_goal": plan.mix_goal,
        "target_lufs": plan.target_lufs,
        "final_lufs": render_result.get("measured_lufs"),
        "stems": stems_serializable,
        "bus": bus_serializable,
        "decisions_log": plan.decisions_log,
        "musical_roles": plan.musical_roles,
        "arrangement": plan.arrangement,
        "relationships": plan.relationships,
        "mix_graph": getattr(plan, "mix_graph", None),
        "mono_compatibility": plan.mono_compatibility,
        "automation_preview": plan.automation_preview,
        "history": render_result.get("history", []),
        "quality_gate": render_result.get("quality_gate", {}),
        "quality_receipt": render_result.get("quality_receipt"),
        # A bounded, offline receipt from the worker.  This captures elapsed
        # time and peak resident memory for key render stages without exposing
        # machine-specific paths or process identifiers.
        "resource_profile": render_result.get("resource_profile"),
        "delivery_validation": render_validation,
        "kenn_autonomous": bool(render_result.get("kenn_autonomous", False)),
        "kenn_advisor_mode": str(render_result.get("kenn_advisor_mode", "off")),
        "kenn_advisor_shadow": render_result.get("kenn_advisor_shadow"),
        "advisory_flags": attribute_flags(
            render_result.get("report", {}).get("flags", []) if isinstance(render_result.get("report"), dict) else [],
            plan
        ),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # 6. Create ZIP archive
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_f:
        zip_f.write(wav_path, arcname=wav_filename)
        zip_f.write(html_path, arcname=html_filename)
        zip_f.write(md_path, arcname=md_filename)
        zip_f.write(json_path, arcname=json_filename)
        for format_path in additional_paths.values():
            zip_f.write(format_path, arcname=format_path.name)

    delivery_status = {
        "ok": True,
        "correlation_id": resolved_correlation_id,
        "version": version,
        "zip_path": str(zip_path),
        "wav_path": str(wav_path),
        "report_path": str(html_path),
        "decisions_md_path": str(md_path),
        "decisions_json_path": str(json_path),
        "additional_format_paths": {key: str(value) for key, value in additional_paths.items()},
        "stem_paths": {name: str(path) for name, path in stem_paths.items()},
        "email_sent": False,
        "notification_requested": bool(recipient_email and download_url_template),
        "render_validation": render_validation,
    }

    return delivery_status
