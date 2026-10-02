"""Intent-to-handler table for the KENN MCP facade.

Order is the order the original ``_dispatch`` if/elif chain checked its
conditions in.  Every condition there was an exact name equality, so no two
intents could ever both match and a dict lookup is exactly equivalent to the
chain -- including the refusal for a name that is not in here.
"""

from __future__ import annotations

from typing import Any, Callable

from kenn.core.mcp import (
    assistant,
    audiogen,
    audition,
    diagnostics,
    knowledge,
    live_confirmation,
    live_proposals,
    live_reads,
    producer_memory,
    sample_library,
    session_intelligence,
    session_review,
)


Handler = Callable[[Any, dict[str, Any]], dict[str, Any]]


# Two intents share one handler because the chain served them from a single
# `if name in {...}` condition: binding an AutoMix job and refreshing it are
# the same read of the same job.
HANDLERS: dict[str, Handler] = {
    "live_snapshot": session_review.live_snapshot,
    "live_plugin_review": session_review.live_plugin_review,
    "realtime_session_review": session_review.realtime_session_review,
    "live_arrangement_analysis": session_review.live_arrangement_analysis,
    "realtime_mix_recommendations": session_review.realtime_mix_recommendations,
    "compare_realtime_mix_review": session_review.compare_realtime_mix_review,
    "live_midi_clip": live_reads.live_midi_clip,
    "live_clip_slot": live_reads.live_clip_slot,
    "duplicate_clip_proposal": live_proposals.duplicate_clip_proposal,
    "rename_clip_proposal": live_proposals.rename_clip_proposal,
    "live_devices": live_reads.live_devices,
    "live_parameters": live_reads.live_parameters,
    "live_parameter_display": live_reads.live_parameter_display,
    "live_parameter_profile": live_reads.live_parameter_profile,
    "compare_live_devices": live_reads.compare_live_devices,
    "create_live_proposal": live_proposals.create_live_proposal,
    "create_live_recipe_proposal": live_proposals.create_live_recipe_proposal,
    "create_mix_review_recipe_proposal": live_proposals.create_mix_review_recipe_proposal,
    "apply_live_proposal": live_confirmation.apply_live_proposal,
    "create_clip_audition_proposal": audition.create_clip_audition_proposal,
    "create_clip_audition_from_receipt": audition.create_clip_audition_from_receipt,
    "record_audition_feedback": audition.record_audition_feedback,
    "audition_feedback": audition.audition_feedback,
    "create_audition_revision_brief": audition.create_audition_revision_brief,
    "undo_live_receipt": live_confirmation.undo_live_receipt,
    "live_receipts": live_confirmation.live_receipts,
    "kenn_capabilities": live_reads.kenn_capabilities,
    "live_device_matrix": live_reads.live_device_matrix,
    "search_sample_library": sample_library.search_sample_library,
    "analyze_sample_library_entry": sample_library.analyze_sample_library_entry,
    "find_similar_samples": sample_library.find_similar_samples,
    "import_sample_to_live": sample_library.import_sample_to_live,
    "ask_audio_engineering_question": knowledge.ask_audio_engineering_question,
    "audiogen_artifact": audiogen.audiogen_artifact,
    "queue_assistant_audiogen_job": audiogen.queue_assistant_audiogen_job,
    "refresh_assistant_audiogen_job": audiogen.refresh_assistant_audiogen_job,
    "bind_assistant_automix_job": audiogen.bind_assistant_automix_job,
    "refresh_assistant_automix_job": audiogen.bind_assistant_automix_job,
    "generate_audiogen_audio_candidate": audiogen.generate_audiogen_audio_candidate,
    "compare_audiogen_audio_candidates": audiogen.compare_audiogen_audio_candidates,
    "create_midi_clip_from_artifact": audiogen.create_midi_clip_from_artifact,
    "generate_audiogen_midi_revision_proposal": audiogen.generate_audiogen_midi_revision_proposal,
    "generate_audiogen_midi_proposal": audiogen.generate_audiogen_midi_proposal,
    "mix_review_recommendations": session_review.mix_review_recommendations,
    "launch_clip_proposal": live_proposals.launch_clip_proposal,
    "launch_scene_proposal": live_proposals.launch_scene_proposal,
    "clip_warp_pitch_proposal": live_proposals.clip_warp_pitch_proposal,
    "duplicate_loop_proposal": live_proposals.duplicate_loop_proposal,
    "create_midi_clip_proposal": live_proposals.create_midi_clip_proposal,
    "update_midi_clip_proposal": live_proposals.update_midi_clip_proposal,
    "kenn_session_doctor": session_intelligence.kenn_session_doctor,
    "kenn_generate_midi_pattern": knowledge.kenn_generate_midi_pattern,
    "kenn_search_knowledge": knowledge.kenn_search_knowledge,
    "kenn_context": session_intelligence.kenn_context,
    "kenn_context_delta": session_intelligence.kenn_context_delta,
    "producer_profile": producer_memory.producer_profile,
    "record_producer_preference": producer_memory.record_producer_preference,
    "forget_producer_preference": producer_memory.forget_producer_preference,
    "clear_producer_profile": producer_memory.clear_producer_profile,
    "record_supervised_session_outcome": producer_memory.record_supervised_session_outcome,
    "supervised_session_outcome_summary": producer_memory.supervised_session_outcome_summary,
    "kenn_session_intelligence": session_intelligence.kenn_session_intelligence,
    "start_production_diagnosis": diagnostics.start_production_diagnosis,
    "record_diagnostic_test_result": diagnostics.record_diagnostic_test_result,
    "plan_assistant_goal": assistant.plan_assistant_goal,
    "plan_assistant_task": assistant.plan_assistant_task,
    "start_assistant_task": assistant.start_assistant_task,
    "resume_assistant_task": assistant.resume_assistant_task,
    "replan_assistant_task": assistant.replan_assistant_task,
    "record_assistant_observation": assistant.record_assistant_observation,
    "record_assistant_user_response": assistant.record_assistant_user_response,
    "record_assistant_live_receipt": assistant.record_assistant_live_receipt,
}
