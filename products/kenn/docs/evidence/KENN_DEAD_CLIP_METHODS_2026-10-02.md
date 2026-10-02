# Unreachable clip methods — 2 October 2026

This records a bounded cleanup under A3 in [KENN_PLAN.md](../../KENN_PLAN.md).
It does not claim that the rest of the codebase has no dead code.

`AbletonOSCClient` defined `launch_clip` and `stop_clip` twice in the same class.
The later definitions replaced the earlier methods during class construction.
Their bodies used the same OSC endpoints and argument conversions; the later
definitions additionally carry the existing docstrings.

An AST duplicate-method check and caller/registry search confirmed that callers
in `tier2_tier3_actions.py`, `clip_audition_service.py` and tests resolve the final
public definitions. Neither early method had a decorator or registration side
effect. Removing their six lines preserves the public methods and their behavior.
Other apparently unused public methods and duplicate packaging were retained
because those checks did not establish that they were unreachable.

From `products/kenn/apps/backend/src`, this scoped command passed 39 tests in
35.11 s:

```sh
../.venv/bin/python -m pytest -q -p no:randomly kenn/tests/test_ableton_osc_bridge.py kenn/tests/test_tier2_control_expansion.py kenn/tests/test_clip_audition_service.py
```

Tests use mocks and FakeLiveBackend. No dependency, permission, model or running
Live session changed. The local log is
`/tmp/kenn-dead-clip-methods-2026-10-02.log`.

Changed files, relative to `products/kenn`:

- `apps/backend/src/kenn/ableton_osc_bridge.py`: removes the two early overridden
  methods; the final definitions remain.
- `docs/evidence/KENN_DEAD_CLIP_METHODS_2026-10-02.md`: this receipt.
- `KENN_PLAN.md`: records this verified deletion and keeps further cleanup open.
