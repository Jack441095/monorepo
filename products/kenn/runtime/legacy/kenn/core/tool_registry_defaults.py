"""Registers KENN's real audio tools into tool_registry (Phase 3 of
docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md).

Only the three tools that produce new derived output without touching
anything pre-existing are registered here (ANALYSIS risk, no confirmation
gate) -- matches the plan's own reasoning: running a mix review, separating
stems, or rendering an AutoMix pass never overwrites a live session or a
delivered file. Each handler is a thin wrapper over the already-shipped,
already-tested function that does the real work (business/app/
automix_public.py, business/app/stem_separation_bridge.py,
studio/audio_analysis's save_review) -- no DSP/business logic lives here.

Deliberately NOT registered here: "apply an EQ move" in the live Ableton
session. That's a LOCAL_MUTATION per the plan and the registry supports
gating it, but ableton_bridge._handle_mix_revision already ships a working,
immediate-apply conversational-revision feature with no confirmation step.
Registering a second, gated entry point for the same action is a real UX
decision (add friction to something that already works? replace it
entirely? run both?) that needs Jack's call, not something to decide solo --
left as an explicit open item.
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
    *, file_bytes: bytes, filename: str, project_id: str = "", chain_to_automix: bool = False
) -> dict:
    import stem_separation_bridge

    return stem_separation_bridge.enqueue_separation(
        file_bytes, filename, project_id=project_id, chain_to_automix=chain_to_automix
    )


def _run_automix(
    *, files: list[tuple[bytes, str]], genre: str = "pop", project_id: str = ""
) -> dict:
    import automix_public

    return automix_public.start_public_automix(files, genre=genre, project_id=project_id)


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
            name="run_automix",
            description="render an AutoMix pass from the uploaded stems",
            risk=ActionRisk.ANALYSIS,
            handler=_run_automix,
        )
    )
