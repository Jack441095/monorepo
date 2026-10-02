"""The agent tool table once held a Session Doctor tool that applied a whole batch with no confirmation.

Nothing called it, but execute_batch_autonomous confirms its own proposals, so wiring it back into the
tool table would have been a silent write path. It was removed; this keeps it from drifting back.
"""

from __future__ import annotations

import inspect

from kenn import autonomous_agent


def test_no_agent_tool_applies_a_batch_without_asking():
    source = inspect.getsource(autonomous_agent)
    assert "execute_batch_autonomous" not in source
    assert "execute_autonomous" not in source


def test_the_old_auto_remediate_tool_is_gone():
    assert not hasattr(autonomous_agent, "tool_auto_remediate_session_issues")
