"""Beta invite drafting (founder request, 2026-09-02 — Submit beta is
actively being sent to testers).

Confirmed with the founder: Thursday drafts beta-invite emails for
review and manual sending only. No email-sending capability, no
credentials, no outbound network call of any kind here — this is pure
text composition. Matches the safety rule both the original Ops-upgrade
spec and the beta checklist hold ("hand the exact frozen ZIP directly,"
not automated distribution) and the founder's own explicit choice when
asked how Thursday should send these ("draft-only, you send manually").

Live-reads two real facts from `docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md`'s
Field/Truth tables (Version, Support channel) rather than hardcoding them
-- the exact release SHA is deliberately NOT embedded (it can change
between beta waves and this module has no way to verify which build is
actually being sent in any given email; the founder fills that in when
attaching the real file). Cites the real feedback-template path
(`products/nite-submit/docs/BETA_FEEDBACK_TEMPLATE.md`) rather than
inventing feedback instructions.
"""

from __future__ import annotations

import re
from pathlib import Path

from thursday.ops.ops_intake import parse_structured_command

TRUTH_SHEET_RELATIVE_PATH = "docs/NITE_SUBMIT_LAUNCH_TRUTH_SHEET.md"
FEEDBACK_TEMPLATE_RELATIVE_PATH = "products/nite-submit/docs/BETA_FEEDBACK_TEMPLATE.md"

_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")

_COMMAND_PREFIXES = [
    "draft beta invite:", "draft beta email:", "draft beta invite for",
]
_FIELD_ALIASES = {"name": "recipient_name"}


def parse_draft_beta_invite_command(text: str):
    """Returns (recipient_email, fields) or None if not this command.
    Raises ValueError if the shape matches but no email was given.
    "draft beta invite: jordan@example.com | name: Jordan" or
    "draft beta invite for jordan@example.com".
    """
    return parse_structured_command(text, _COMMAND_PREFIXES, _FIELD_ALIASES, set())


def _nite_dsp_root() -> Path:
    """Same upward-search pattern as qa_ops/documentation_ops/
    shadow_adapters -- search loop delegated to
    thursday.repo_root.search_upward (2026-09-18 audit fix); only the
    target + per-copy fallback live here.
    """
    from thursday.repo_root import search_upward

    here = Path(__file__).resolve()
    found = search_upward(here, (TRUTH_SHEET_RELATIVE_PATH,), depth=6)
    if found is not None:
        return found
    # Fallback depth for this copy's location: autonomous-systems/thursday/
    # thursday/ops/beta_invite_ops.py -> parents[4] is NITE_DSP root
    # (one deeper than Audio_Too/thursday/ops/'s parents[3]).
    return here.parents[4]


def _read_truth_sheet_field(field_name: str) -> str | None:
    """Live-read one row's value from any Field/Truth-shaped or
    similarly-labelled table in the truth sheet, matched by the row's
    first-column label. Returns None (never a guess) if the file or row
    can't be found.
    """
    path = _nite_dsp_root() / TRUTH_SHEET_RELATIVE_PATH
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        m = _TABLE_ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if cells and cells[0].strip().lower() == field_name.strip().lower():
            # Take the last non-empty cell as the value (works for both
            # 2-column Field/Truth tables and 3-column Decision/Answer/
            # Status tables where the middle cell is the actual value --
            # for those, prefer the second cell if there are 3+).
            if len(cells) >= 3:
                return cells[1].strip("` ")
            if len(cells) == 2:
                return cells[1].strip("` ")
    return None


def feedback_template_path() -> Path:
    return _nite_dsp_root() / FEEDBACK_TEMPLATE_RELATIVE_PATH


def draft_beta_invite(recipient_email: str, recipient_name: str = "") -> str:
    version = _read_truth_sheet_field("Version") or "[version — check the truth sheet, not found live]"
    support = _read_truth_sheet_field("Support channel") or "[support email — not found live]"
    feedback_path = feedback_template_path()
    feedback_note = (
        str(feedback_path) if feedback_path.exists()
        else "[feedback template not found on disk — check products/nite-submit/docs/]"
    )

    greeting = f"Hi {recipient_name}," if recipient_name else "Hi,"

    body = f"""DRAFT — NOT SENT. Review and send manually.

To: {recipient_email}
Subject: NITE Submit private beta — a quick favour

{greeting}

I'd like you to try NITE Submit — a small Mac app I've been building
that reads a PDF assignment, spots the student name/ID/module details,
and helps create a correctly named file without uploading anything
anywhere. Everything stays on your Mac.

This build: {version}.

[FOUNDER: attach the exact frozen release ZIP here — do not send the
dirty local checkout. Confirm you're sending the one canonical approved
build before attaching.]

A couple of things to know before you open it:
- It's signed ad-hoc, not through the Mac App Store, so macOS Gatekeeper
  will complain the first time. Right-click the app → Open, rather than
  double-clicking, to get past that safely.
- If anything looks wrong with a file it renames or creates — wrong
  name, wrong location, anything that worries you — stop and tell me
  straight away rather than continuing. That matters more than general
  feedback.
- For everything else, there's a feedback template here (mention if you'd
  like it sent separately): {feedback_note}

Any trouble at all, reply here or to {support}.

Thanks for doing this — really appreciate you taking the time.
"""
    return body
