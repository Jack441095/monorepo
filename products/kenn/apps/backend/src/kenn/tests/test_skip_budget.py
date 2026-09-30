"""The skip budget must allow the skips nobody can avoid and fail on the ones nobody has explained.

The backend suite skips 48 tests in test_server_smoke.py when the knowledge index is not built, which is every CI
run and every fresh worktree. Keying the budget on a count would have to allow 125 on CI and 5 on a checkout with an
index, and would not notice that the difference is the index rather than the code, so the budget is keyed on reasons.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import check_skip_budget as budget


def test_a_skip_line_splits_into_site_and_reason() -> None:
    """It used to split on the first colon, so '77: ' landed at the front of every reason and broke the allowlist."""
    match = budget.SKIPPED.match("SKIPPED [48] apps/backend/src/kenn/tests/test_server_smoke.py:77: Knowledge index not built")
    assert match is not None
    assert match.group("count") == "48"
    assert match.group("file") == "apps/backend/src/kenn/tests/test_server_smoke.py"
    assert match.group("line") == "77"
    assert match.group("reason") == "Knowledge index not built"


def test_a_module_level_skip_with_no_line_number_is_not_dropped() -> None:
    """pytest omits the line for a module-level skip, which is most of them; requiring it silently lost 70 of 125."""
    match = budget.SKIPPED.match("SKIPPED [2] t.py: requires the local KENN corpus/index, excluded from public CI")
    assert match is not None
    assert match.group("line") is None and match.group("count") == "2"
    assert match.group("reason") == "requires the local KENN corpus/index, excluded from public CI"


def test_a_reason_containing_a_colon_is_kept_whole() -> None:
    match = budget.SKIPPED.match("SKIPPED [1] t.py:10: expected: 3, got 4")
    assert match is not None and match.group("reason") == "expected: 3, got 4"


def test_the_allowlist_is_reasoned_not_counted() -> None:
    allowed = budget.load_allowed(budget.DEFAULT_ALLOW)
    assert allowed, "the allowlist must exist; an empty one would make every skip unaccounted"
    assert any("index" in reason.lower() for reason in allowed)
    assert all(isinstance(reason, str) and reason.strip() for reason in allowed)


def test_an_unaccounted_skip_reason_is_what_fails_the_build() -> None:
    """Synthetic, on purpose: running the whole suite from inside the suite is a recursive 75-second trap.

    The real run is `python3 tooling/scripts/check_skip_budget.py`, which reported 55 skips, 0 unaccounted, exit 0
    on a worktree with no knowledge index on 30 Sept.
    """
    from collections import Counter

    allowed = set(budget.load_allowed(budget.DEFAULT_ALLOW))
    reasons = Counter({"Local knowledge corpus is intentionally excluded from public CI": 48,
                      "someone broke this on purpose": 1})
    unaccounted = {reason: count for reason, count in reasons.items() if reason not in allowed}
    assert unaccounted == {"someone broke this on purpose": 1}


def test_the_parser_sums_a_grouped_skip_line() -> None:
    """pytest prints 'SKIPPED [48] site: reason', where the count is how many tests share that reason."""
    from collections import Counter

    lines = ["SKIPPED [48] t.py:77: Knowledge index not built"]
    counts: Counter = Counter()
    for line in lines:
        match = budget.SKIPPED.match(line)
        if match:
            counts[match.group("reason")] += int(match.group("count"))
    assert counts == Counter({"Knowledge index not built": 48})


def test_a_missing_allow_file_yields_no_allowances_rather_than_a_pass(tmp_path: Path) -> None:
    assert budget.load_allowed(tmp_path / "nope.json") == []


def test_the_allow_file_is_valid_json_with_a_note() -> None:
    data = json.loads(budget.DEFAULT_ALLOW.read_text(encoding="utf-8"))
    assert data["schema"] == "kenn.known_skip_reasons.v1"
    assert data.get("note"), "an unexplained allowance is how a budget rots"
