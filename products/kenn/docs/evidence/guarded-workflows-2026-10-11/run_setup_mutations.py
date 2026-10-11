"""Break setup confirmation boundaries in fake-only checks and restore source bytes after every run."""

import hashlib
from importlib.util import cache_from_source
import json
import os
from pathlib import Path
import subprocess
import sys

root = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
source = root / "products/kenn/apps/backend/src"
frontend = root / "products/kenn/apps/frontend"
service = "products/kenn/apps/backend/src/kenn/core/live_action_service.py"
test = "kenn/tests/test_guarded_device_setup.py::"
# Match the installed arm64 native bindings. The system's x64 Node cannot load this existing dependency tree.
node = os.environ.get("KENN_TEST_NODE", "node")
cases = [
    ("deferred_intent_binding", service,
     'text += "|" + json.dumps(proposal["configuration_specs"], sort_keys=True, separators=(",", ":"), allow_nan=False)',
     "pass", test + "test_insertion_confirmation_binds_its_deferred_configuration_intent"),
    ("same_device_across_configuration_reads", service,
     '                if not checked.get("success"):', '                if False:',
     test + "test_replacement_between_configuration_observations_withholds_the_second_card"),
    ("retained_single_control", service,
     'parameter_name=spec["name"], device_name=device_name, session_id=session_id,\n                observed_parameter_info=info,',
     'parameter_name=spec["name"], device_name=device_name, session_id=session_id,\n                observed_parameter_info=None,',
     test + "test_single_configuration_construction_retains_its_first_observation"),
    ("unique_indexed_control", service,
     'if len(candidates) != 1 or type(candidates[0].get("index")) is not int:', "if False:",
     test + "test_failed_configuration_inspection_keeps_verified_insertion_without_writing_controls[duplicate]"),
    ("binary_enable_semantics", service,
     'if parameter is None or parameter.get("quantized") is not True or [parameter.get("min"), parameter.get("max")] != [0, 1]:',
     "if False:", test + "test_failed_configuration_inspection_keeps_verified_insertion_without_writing_controls[enable_semantics]"),
    ("separate_configuration_apply", service,
     'response["configuration_proposal"] = configuration["proposal"]',
     'response["configuration_proposal"] = configuration["proposal"]\n                from kenn.core.live_recipe import LiveRecipeService\n                LiveRecipeService(self).execute_recipe(configuration["proposal"], confirm_token=configuration["proposal"]["confirmation_token"], session_id=session_id)',
     test + "test_setup_needs_two_applies_and_each_verified_stage_has_its_own_undo"),
    ("api_preserves_next_card", "products/kenn/apps/frontend/src/api/kenn.ts",
     'nextProposal: data.next_proposal as KennActionProposal | undefined,', 'nextProposal: undefined,', "src/api/kenn.test.ts"),
    ("chat_displays_separate_next_card", "products/kenn/apps/frontend/src/composables/useKenn.ts",
     'if (res.nextProposal) {', 'if (false) {', "src/composables/useKenn.test.ts"),
    ("unknown_insertion_receipt", service,
     '"status": "unknown" if outcome_unknown else "failed",', '"status": "failed",',
     test + "test_unobservable_insertion_stays_unknown_without_a_configuration_card_or_retry[lost_ack]"),
    ("unknown_gateway_outcome", "products/kenn/apps/backend/src/kenn/core/live_command.py",
     'outcome_unknown = (result.get("receipt") or {}).get("status") == "unknown"', 'outcome_unknown = False',
     test + "test_unobservable_insertion_stays_unknown_without_a_configuration_card_or_retry[lost_ack]"),
    ("unknown_receipt_survives_logging_failure", "products/kenn/apps/backend/src/kenn/core/live_command.py",
     'uncertain_change = result if result is not None and (result.get("receipt") or {}).get("status") == "unknown" else None',
     'uncertain_change = None',
     test + "test_unobservable_insertion_stays_unknown_without_a_configuration_card_or_retry[bookkeeping_failure]"),
    ("token_only_followup_registration", "products/kenn/apps/backend/src/kenn/routes/daw_command_handler.py",
     'for field in ("proposal", "next_proposal"):', 'for field in ("proposal",):',
     test + "test_token_only_http_client_must_confirm_the_registered_configuration_card_separately"),
    ("no_retry_after_internal_attribute_error", service,
     'except Exception as exc:\n            return self._insertion_failure(proposal, key, f"Live device insertion raised an exception: {exc}", outcome_unknown=True)',
     'except Exception as exc:\n            if isinstance(exc, AttributeError):\n                self.client.create_device(int(proposal["track_index"]), str(proposal["device_name"]))\n            return self._insertion_failure(proposal, key, f"Live device insertion raised an exception: {exc}", outcome_unknown=True)',
     test + "test_unobservable_insertion_stays_unknown_without_a_configuration_card_or_retry[attribute_exception]"),
    ("read_only_insertion_refusal", service,
     'if getattr(self.client, "read_only", False) is True:\n            # An intentionally disabled backend',
     'if False:\n            # An intentionally disabled backend',
     test + "test_read_only_setup_refuses_before_dispatch_and_does_not_claim_an_unknown_write[insertion]"),
    ("read_only_parameter_refusal", service,
     'if getattr(self.client, "read_only", False) is True:\n            # A disabled writer',
     'if False:\n            # A disabled writer',
     test + "test_read_only_setup_refuses_before_dispatch_and_does_not_claim_an_unknown_write[configuration]"),
    ("read_only_backend_declaration", "products/kenn/apps/backend/src/kenn/core/live_backend.py",
     'read_only = True', 'read_only = False',
     "kenn/tests/test_live_backend.py::test_read_only_mcp_backend_enters_kenn_proposal_path_but_cannot_apply"),
]
results = []
for name, relative, old, replacement, node_id in cases:
    path = root / relative
    original = path.read_bytes()
    assert original.decode().count(old) == 1, name
    python_source = path.suffix == ".py"
    bytecode = Path(cache_from_source(str(path))) if python_source else None
    command = ([sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", node_id] if python_source else
               [node, "node_modules/vitest/vitest.mjs", "run", "--maxWorkers=1", node_id])
    try:
        if bytecode:
            # Equal-length mutations can share the original mtime; every Python check must read actual source.
            bytecode.unlink(missing_ok=True)
        path.write_text(original.decode().replace(old, replacement))
        run = subprocess.run(command, cwd=source if python_source else frontend, capture_output=True, text=True,
            env={**os.environ, "KENN_LIVE_BACKEND": "fake", "PYTHONDONTWRITEBYTECODE": "1"})
    finally:
        # A failing test or interrupted subprocess must not leave the mutation in the implementation.
        path.write_bytes(original)
        if bytecode:
            bytecode.unlink(missing_ok=True)
    output = run.stdout + run.stderr
    result = {"guard": name, "source": relative, "test": node_id, "replacement": replacement,
        "exit_code": run.returncode, "caught": run.returncode == 1 and ("FAILED " in output or " FAIL " in output),
        "source_restored": path.read_bytes() == original, "restored_sha256": hashlib.sha256(original).hexdigest()}
    results.append(result)
    print(name, "caught" if result["caught"] else "NOT CAUGHT", flush=True)
Path(__file__).with_name("setup-mutations.json").write_text(json.dumps({
    "schema": "kenn.regression_mutations.v1", "synthetic_only": True, "live_writes": 0, "checks": results,
}, indent=2) + "\n")
raise SystemExit(0 if all(row["caught"] and row["source_restored"] for row in results) else 1)
