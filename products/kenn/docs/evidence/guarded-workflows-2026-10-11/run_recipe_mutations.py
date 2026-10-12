"""Break each recipe guard in isolation and restore the exact source after its regression fails."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
source = root / "products/kenn/apps/backend/src"
recipe = "products/kenn/apps/backend/src/kenn/core/live_recipe.py"
test = "kenn/tests/test_guarded_recipes.py::"
cases = [
    ("parent_target_binding", recipe, '"confirmation": device_confirmation_text(step)', '"confirmation": "omitted"',
     test + "test_recipe_confirmation_binds_guarded_target_semantics_and_readable_values"),
    ("original_object", "products/kenn/apps/backend/src/kenn/core/fake_live.py",
     'any(a is not b for a, b in zip(objects, previous["objects"]))', "False",
     test + "test_replaced_parameter_refuses_before_any_device_write_and_restores_prior_mixer_step"),
    ("undo_retained_observation", recipe, 'self.service.propose_undo(item, session_id=session_id)',
     'self._propose_step(spec, reason=reason, session_id=session_id) if self.service.propose_undo(item, session_id=session_id).get("ok") else {"ok": False}',
     test + "test_guarded_recipe_undo_card_cannot_rebind_after_its_original_object_is_checked"),
    ("undo_project_isolation", recipe, 'if receipt.get("session_id") and receipt["session_id"] != session_id:', "if False:",
     test + "test_mixer_only_recipe_undo_cannot_cross_project_sessions"),
    ("mixer_recovery_post_state", recipe,
     'if current is None or receipt.get("readback") is None or not _values_match(current.get(field), receipt["readback"]):',
     "if False:", test + "test_mixed_recipe_rollback_preserves_manual_mixer_transport_and_target_changes"),
    ("transport_recovery_post_state", recipe, 'if receipt.get("readback") is None or current != receipt["readback"]:',
     "if False:", test + "test_mixed_recipe_rollback_preserves_manual_mixer_transport_and_target_changes"),
]
results = []
for name, relative, old, replacement, node in cases:
    path = root / relative
    original = path.read_bytes()
    assert original.decode().count(old) == 1, name
    try:
        path.write_text(original.decode().replace(old, replacement))
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", node], cwd=source,
            env={**os.environ, "KENN_LIVE_BACKEND": "fake"}, capture_output=True, text=True,
        )
    finally:
        # A crashed test must not leave the mutation in the implementation or the next check.
        path.write_bytes(original)
    result = {
        "guard": name, "source": relative, "test": node, "replacement": replacement,
        "exit_code": run.returncode, "caught": run.returncode == 1 and "FAILED " in run.stdout,
        "source_restored": path.read_bytes() == original, "restored_sha256": hashlib.sha256(original).hexdigest(),
    }
    results.append(result)
    print(name, "caught" if result["caught"] else "NOT CAUGHT", flush=True)
Path(__file__).with_name("recipe-mutations.json").write_text(json.dumps({
    "schema": "kenn.regression_mutations.v1", "synthetic_only": True, "live_writes": 0, "checks": results,
}, indent=2) + "\n")
raise SystemExit(0 if all(row["caught"] and row["source_restored"] for row in results) else 1)
