"""Engineering / release hygiene (Thursday Ops upgrade, phase 7).

Chosen over the remaining named agent types after finding that the
"release branch hygiene" building block the spec asks for already
existed here -- thursday/shadow_adapters.py's ShadowAdapter.get_git_state()
-- but its ADAPTERS registry was still hardcoded to a pre-NITE_DSP
directory layout (Audio_Engineering_Company/SmartSampleManager/SLO_V5C/
KENN/NiteSubmit) that no longer exists, so it silently returned "UNKNOWN"
for everything, always. Fixed the path resolution first (same commit),
then built this module as a thin, real-evidence report over it -- the
same shape as qa_ops.py: read live state, never cache or guess.

Deliberately not codebase Q&A or implementation planning -- that's
thursday.brain's job (LLM-backed, a different kind of feature with a
different risk profile). This module answers exactly one narrow,
deterministic question per repo: is the working tree clean, and is it on
the branch it's supposed to be on. Nothing here inspects file contents,
runs tests, or makes a judgment call about code quality.
"""

from __future__ import annotations

from thursday import shadow_adapters


def release_hygiene_check() -> str:
    lines = ["RELEASE HYGIENE CHECK", ""]
    dirty_count = 0
    unknown_count = 0

    for name, adapter in shadow_adapters.ADAPTERS.items():
        state = adapter.get_git_state()
        branch = state.get("branch", "UNKNOWN")
        clean = state.get("clean", True)
        sha = state.get("head_sha", "UNKNOWN")

        if branch in ("UNKNOWN", "ERROR"):
            unknown_count += 1
            lines.append(f"  {name}: UNKNOWN — workspace not found or not a git repo ({adapter.workspace_path})")
            continue

        short_sha = sha[:10] if len(sha) >= 10 else sha
        status = "clean" if clean else "UNCOMMITTED CHANGES"
        if not clean:
            dirty_count += 1
        lines.append(f"  {name}: [{branch}] {short_sha} — {status}")

    lines.append("")
    lines.append(
        f"{len(shadow_adapters.ADAPTERS) - dirty_count - unknown_count}/"
        f"{len(shadow_adapters.ADAPTERS)} clean, {dirty_count} with uncommitted "
        f"changes, {unknown_count} unreachable."
    )
    lines.append("")
    lines.append(
        "This is real-time git status only (branch, HEAD SHA, working-tree "
        "cleanliness) -- not a code review, not a test run, not a claim "
        "about what the uncommitted changes actually are. Read the diff "
        "before assuming a dirty workspace is safe to leave or a clean one "
        "is safe to build from."
    )

    return "\n".join(lines)
