"""Registers KENN's real audio tools into tool_registry (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md).

Only the four tools that produce new derived output without touching
anything pre-existing are registered here (ANALYSIS risk, no confirmation
gate) -- matches the plan's own reasoning: running a mix review, analyzing
stem masking, separating stems, or rendering an AutoMix pass never overwrites
a live session or a delivered file. Each handler is a thin wrapper over the
already-shipped, already-tested function that does the real work (business/app/
automix_public.py, business/app/stem_separation_bridge.py,
studio/audio_analysis's save_review) -- no DSP/business logic lives here.

The Live device-parameter tool is registered as a LOCAL_MUTATION and delegates
to `LiveActionService`, which fronts the planner/executor proposal contract.
No registry handler is allowed to perform an immediate Ableton write.
"""

from __future__ import annotations

from kenn.core.tool_registry import ActionRisk, ToolDef, register


def _run_mix_review(*, file_bytes: bytes, filename: str, project_id: str = "", **kwargs) -> dict:
    from audio_analysis.mix_review import mix_review

    return mix_review.save_review(
        file_bytes=file_bytes,
        filename=filename,
        project_id=project_id,
        background=True,
        **kwargs,
    )


def _run_stem_separation(
    *, file_bytes: bytes = b"", filename: str = "", project_id: str = "", chain_to_automix: bool = False, **kwargs
) -> dict:
    return {
        "ok": False,
        "error": "Stem separation is excluded from the KENN Public Beta release.",
        "status": "unavailable",
    }


def _run_stem_masking(*, files: list[tuple[bytes, str]], **kwargs) -> dict:
    """Analyze explicit attached WAV stems without retaining their bytes."""
    from pathlib import Path

    from kenn.core.local_mix_review_service import analyze_stem_masking

    stems = [
        (Path(filename).stem[:96], bytes(file_bytes))
        for file_bytes, filename in files
        if isinstance(file_bytes, (bytes, bytearray)) and str(filename).lower().endswith(".wav")
    ]
    if len(stems) < 2:
        return {"ok": False, "error": "Attach at least 2 WAV stems to analyze masking between them."}
    return analyze_stem_masking(stems)


def _run_automix(**kwargs) -> dict:
    return {
        "ok": False,
        "error": "AutoMix is excluded from the KENN Public Beta release.",
        "status": "unavailable",
    }



def _set_ableton_device_parameter(
    *, proposal: dict, confirm_token: str = "", session_id: str = "default_session", **kwargs
) -> dict:
    from kenn.core.live_action_service import LiveActionService

    service = LiveActionService()
    return service.execute_device_action(proposal, confirm_token=confirm_token, session_id=session_id)


def register_defaults() -> None:
    """Idempotent -- register() overwrites by name, safe to call more than
    once (e.g. once per test, once at real server startup)."""
    register(
        ToolDef(
            name="run_mix_review",
            description="run a mix review on the uploaded track",
            risk=ActionRisk.ANALYSIS,
            handler=_run_mix_review,
        )
    )
    register(
        ToolDef(
            name="run_stem_separation",
            description="separate the uploaded track into stems",
            risk=ActionRisk.ANALYSIS,
            handler=_run_stem_separation,
        )
    )
    register(
        ToolDef(
            name="run_stem_masking",
            description="analyze frequency-band competition between the attached WAV stems",
            risk=ActionRisk.ANALYSIS,
            handler=_run_stem_masking,
        )
    )
    register(
        ToolDef(
            name="run_automix",
            description="render an AutoMix pass from the uploaded stems",
            risk=ActionRisk.ANALYSIS,
            handler=_run_automix,
        )
    )
    register(
        ToolDef(
            name="set_ableton_device_parameter",
            description="apply a confirmed parameter adjustment to an Ableton Live device",
            risk=ActionRisk.LOCAL_MUTATION,
            handler=_set_ableton_device_parameter,
        )
    )
