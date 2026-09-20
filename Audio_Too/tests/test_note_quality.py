from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.training.note_quality import validate_note_for_approval  # noqa: E402


def test_complete_note_passes_approval_gate() -> None:
    result = validate_note_for_approval(
        """# Gain Staging

Type: Recording workflow
Tags: gain, recording, headroom
Source: Studio practice
Reviewed: 2026-07-01

Short answer:
Leave safe peak headroom.

Try this:
1. Test the loudest passage.

Why it matters:
It prevents converter clipping.

Related questions:
- How loud should I record?
- Can I lower the fader instead?
"""
    )
    assert result == {"ok": True, "errors": [], "warnings": []}


def test_decorated_section_heading_is_recognized() -> None:
    # 2026-08-06: automix-compression-ratios.md's real "Try this" heading is
    # "Try this -- the default ratios by instrument (before genre
    # modifiers):", not bare "Try this:". The old exact-line pattern here
    # flagged it (and ~10 other genuinely well-formed, long-approved notes)
    # as missing the section entirely -- found running knowledge-audit.
    # chat_formatting.py::section_lines() already tolerates this same
    # decorated-heading style; this mirrors that fix.
    result = validate_note_for_approval(
        """# Compression Ratios

Type: AutoMix decision logic
Tags: automix, compression, ratio
Source: mix_rules.py
Reviewed: 2026-07-09

Short answer:
Every instrument gets a default compressor ratio.

Try this -- the default ratios by instrument (before genre modifiers):
1. Kick: 4:1.
2. Snare: 3.5:1.

Why it matters:
Firmer control on percussive low end keeps the mix consistent.

Related questions:
- Why does kick ratio change between genres?
"""
    )
    assert result == {"ok": True, "errors": [], "warnings": []}


def test_body_prose_ending_in_colon_does_not_truncate_section() -> None:
    # 2026-08-06: the stop-boundary matched ANY line of just letters/spaces
    # ending in a colon -- including ordinary prose ending a sentence with a
    # colon before a list, not just real section headings. Found on
    # jack-export-specs.md, a real note wrongly flagged as having no Short
    # answer despite visibly having one, because its second body line
    # ("...depending on the client type:") was mistaken for a new heading.
    result = validate_note_for_approval(
        """# Export Specs

Type: Personal studio workflow
Tags: export, wav, mp3
Source: Studio practice
Reviewed: 2026-07-07

Short answer:
There are two distinct export configurations depending on the client type:
1. Streaming release: WAV, 24-bit, 44.1kHz.
2. Client preview: MP3, 320kbps.

Try this:
1. Open the export dialog.

Why it matters:
Format choice affects quality and delivery speed.

Related questions:
- What format should I export?
"""
    )
    assert result == {"ok": True, "errors": [], "warnings": []}


def test_placeholder_draft_cannot_be_approved() -> None:
    result = validate_note_for_approval(
        """# Draft
Type: Workflow
Tags: draft, audio, mixing
Short answer:
Write the practical idea in your own words.
Try this:
1. Test.
Why it matters:
Test.
Related questions:
- What next?
"""
    )
    assert result["ok"] is False
    assert any("placeholder" in error.lower() for error in result["errors"])
