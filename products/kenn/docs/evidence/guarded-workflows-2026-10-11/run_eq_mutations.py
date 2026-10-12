"""Break each compound EQ boundary and restore the exact source after its regression fails."""

import hashlib
from importlib.util import cache_from_source
import json
import os
from pathlib import Path
import subprocess
import sys

root = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
source = root / "products/kenn/apps/backend/src"
service = "products/kenn/apps/backend/src/kenn/core/live_action_service.py"
planner = "products/kenn/apps/backend/src/kenn/core/live_control_planner.py"
test = "kenn/tests/test_guarded_eq_workflows.py::"
cases = [
    ("same_band", service, 'if not re.fullmatch(r"[1-8][AB]", band) or (\n                frequency_parameter.get("name")',
     'if False and (\n                frequency_parameter.get("name")',
     test + "test_compound_eq_refuses_an_observed_gain_from_another_band"),
    ("native_gain_bounds_shared", planner,
     'if profile and profile.device_name == "EQ Eight" and profile.parameter_name == "Gain" and (',
     'if False and (', test + "test_single_eq_gain_cards_refuse_the_same_unqualified_host_range"),
    ("relative_gain_before_state", service, 'not _values_match(child.get("before"), previous["value"])',
     "False", test + "test_compound_eq_does_not_rebase_gain_when_it_moves_during_planning"),
    ("same_device_across_observations", service, 'if not checked.get("success"):',
     "if False:", test + "test_compound_eq_refuses_replacement_between_its_two_guarded_observations"),
    ("retained_observations_after_check", service, '                    observed_parameter_info=info,',
     '                    observed_parameter_info=None,', test + "test_compound_eq_proposal_never_rediscovers_after_validating_its_original_observation"),
]
results = []
for name, relative, old, replacement, node in cases:
    path = root / relative
    original = path.read_bytes()
    assert original.decode().count(old) == 1, name
    bytecode = Path(cache_from_source(str(path)))
    try:
        # Equal-length mutations can share a one-second mtime with restored code. Read source, not stale bytecode.
        bytecode.unlink(missing_ok=True)
        path.write_text(original.decode().replace(old, replacement))
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", node], cwd=source,
            env={**os.environ, "KENN_LIVE_BACKEND": "fake", "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True,
        )
    finally:
        # A failed subprocess must not leave a broken guard in the next check or the implementation.
        path.write_bytes(original)
        bytecode.unlink(missing_ok=True)
    result = {
        "guard": name, "source": relative, "test": node, "replacement": replacement,
        "exit_code": run.returncode, "caught": run.returncode == 1 and "FAILED " in run.stdout,
        "source_restored": path.read_bytes() == original, "restored_sha256": hashlib.sha256(original).hexdigest(),
    }
    results.append(result)
    print(name, "caught" if result["caught"] else "NOT CAUGHT", flush=True)
Path(__file__).with_name("eq-mutations.json").write_text(json.dumps({
    "schema": "kenn.regression_mutations.v1", "synthetic_only": True, "live_writes": 0, "checks": results,
}, indent=2) + "\n")
raise SystemExit(0 if all(row["caught"] and row["source_restored"] for row in results) else 1)
