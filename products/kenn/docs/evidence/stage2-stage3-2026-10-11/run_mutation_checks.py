"""Break one safety condition at a time, require its regression to fail, and restore exact source bytes."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
src = root / 'products/kenn/apps/backend/src'
python = sys.executable
cases = [
 ('confirmation_display', 'products/kenn/apps/backend/src/kenn/core/parameter_contract.py', '"before_label", "after_label", "before_display", "after_display",', '"before_label", "after_label",', 'kenn/tests/test_parameter_targets.py::test_confirmation_refuses_tampered_identity_units_and_before_state'),
 ('original_object_identity', 'products/kenn/apps/backend/src/kenn/core/fake_live.py', 'any(a is not b for a, b in zip(objects, previous["objects"]))', 'False', 'kenn/tests/test_parameter_targets.py::test_apply_refuses_identical_replacements_and_stale_topology'),
 ('sparse_index_uniqueness', 'products/kenn/apps/backend/src/kenn/core/parameter_contract.py', 'return matches[0] if len(matches) == 1 else None', 'return matches[0] if matches else None', 'kenn/tests/test_parameter_targets.py::test_partial_metadata_and_duplicate_indices_cannot_resolve_by_position'),
 ('quantized_raw_options', 'products/kenn/apps/backend/src/kenn/core/parameter_contract.py', 'elif parameter.get("quantized") is True and value not in {current, low, high}:', 'elif False:', 'kenn/tests/test_parameter_targets.py::test_unqualified_chooser_does_not_invent_contiguous_intermediate_raw_values'),
 ('review_wrong_outcome', 'products/kenn/tooling/scripts/adjudicate_human_review.py', 'verdict = "wrong" if "wrong" in outcomes else "clarify"', 'verdict = "correct"', 'kenn/tests/test_captured_review_contract.py::test_accepted_but_wrong_answer_and_disagreement_remain_wrong'),
 ('review_packet_binding', 'products/kenn/tooling/scripts/adjudicate_human_review.py', 'form.get("packet_id") != packet.get("packet_id")', 'False', 'kenn/tests/test_captured_review_contract.py::test_partial_reports_reject_foreign_or_malformed_forms'),
 ('eligible_denominator', 'products/kenn/tooling/scripts/measure_chat_latency.py', '"eligible": sum(r["eligible"] for r in rows)', '"eligible": sum(r["eligible"] and r["delivery"] == "accepted" for r in rows)', 'kenn/tests/test_measure_chat_latency.py::test_all_delivery_outcomes_stay_in_the_eligible_denominator_with_unknown_paint_time'),

 ('undo_original_observation', 'products/kenn/apps/backend/src/kenn/core/live_action_service.py', '                    observed_parameter_info=parameters,', '', 'kenn/tests/test_parameter_targets.py::test_undo_cannot_rebind_to_a_replacement_after_its_identity_checked_read'),
 ('qualified_undo_labels', 'products/kenn/apps/backend/src/kenn/core/live_control_planner.py', ' or display_unit == "choice"', '', 'kenn/tests/test_parameter_targets.py::test_undo_uses_qualified_choice_labels_when_host_only_exposes_raw_bounds'),
 ('duplicate_device_clarification', 'products/kenn/apps/backend/src/kenn/core/live_intent_rules/device_rules.py', 'if len(named) > 1:', 'if False:', 'kenn/tests/test_stage23_conversation_journeys.py::test_five_turn_duplicate_device_clarification_corrected_target_revision_and_apply'),
 ('production_setup_refusal', 'products/kenn/apps/backend/src/kenn/core/live_action_service.py', 'if getattr(self.client, "requires_guarded_parameter_targets", False):\n            # Setup still', 'if False:\n            # Setup still', 'kenn/tests/test_parameter_targets.py::test_guarded_production_backends_refuse_legacy_recipe_compound_and_recovery_writes'),
 ('actual_handler_registration', 'products/kenn/integrations/ableton-osc/abletonosc/song.py', '        self.parameter_targets = register_parameter_targets(self.osc_server, self.song)', '', 'kenn/tests/test_parameter_target_transport.py::test_real_registration_serialization_and_lost_ack_readback'),


 ('production_recipe_refusal', 'products/kenn/apps/backend/src/kenn/core/live_recipe.py', 'if getattr(self.client, "requires_guarded_parameter_targets", False) and any(', 'if False and any(', 'kenn/tests/test_parameter_targets.py::test_guarded_production_backends_refuse_legacy_recipe_compound_and_recovery_writes'),


 ('selected_duplicate_track_context', 'products/kenn/apps/backend/src/kenn/core/session_context.py', 'state["last_track_index"] = track_index if type(track_index) is int else None', 'state["last_track_index"] = None', 'kenn/tests/test_stage23_conversation_journeys.py::test_five_turn_other_compressor_lists_devices_from_the_selected_duplicate_track'),

]
results = []
for name, relative, old, new, test in cases:
    path = root / relative
    original = path.read_bytes()
    source = original.decode()
    assert source.count(old) == (2 if name == "review_packet_binding" else 1), (name, source.count(old))
    log = Path('/tmp') / f'kenn-stage23-mutation-{name}.txt'
    # Sources are restored even when pytest crashes; this runner belongs in an isolated checkout.
    try:
        path.write_text(source.replace(old, new))
        with log.open('w') as out:
            run = subprocess.run([str(python), '-m', 'pytest', '-q', '-p', 'no:randomly', test], cwd=src, env={**os.environ, 'KENN_LIVE_BACKEND': 'fake'}, stdout=out, stderr=subprocess.STDOUT)
    finally:
        path.write_bytes(original)
    result = {'guard': name, 'source': relative, 'test': test, 'mutant': new, 'exit_code': run.returncode, 'killed': run.returncode == 1 and 'FAILED ' in log.read_text(), 'source_restored': path.read_bytes() == original, 'restored_sha256': hashlib.sha256(original).hexdigest()}
    results.append(result)
    print(name, 'caught' if result['killed'] else 'NOT CAUGHT', flush=True)
Path(__file__).with_name("mutation-results.json").write_text(json.dumps({'schema':'kenn.regression_mutations.v1', 'synthetic_only':True, 'live_writes':0, 'checks':results}, indent=2)+'\n')
raise SystemExit(0 if all(row['killed'] and row['source_restored'] for row in results) else 1)
