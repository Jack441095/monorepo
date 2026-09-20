from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[2]
PATH = ROOT / "scripts" / "kenn_knowledge_audit.py"
SPEC = importlib.util.spec_from_file_location("kenn_knowledge_audit", PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _write(path: Path, *, status: str = "Approved", source: str = "Studio practice") -> None:
    path.write_text(
        f"""# Vocal Control

Type: Mixing technique
Tags: vocal, compression, mixing
Status: {status}
Source: {source}
Reviewed: 2026-07-01

Short answer:
Control the performance before compressing it.

Try this:
1. Ride clip gain first.

Why it matters:
It keeps compression predictable.

Related questions:
- How do I control vocal peaks?
- Should I automate vocals first?
""",
        encoding="utf-8",
    )


def test_build_report_counts_approved_prompts_and_coverage(tmp_path) -> None:
    _write(tmp_path / "vocal.md")
    report = audit.build_report(tmp_path)
    assert report["summary"]["approved"] == 1
    assert report["summary"]["note_training_prompts"] == 3
    assert report["coverage"]["vocals"] == 1
    assert report["summary"]["errors"] == 0


def test_approved_note_missing_sections_is_an_error(tmp_path) -> None:
    (tmp_path / "bad.md").write_text(
        "# Bad\n\nType: Test\nTags: one\nStatus: Approved\n",
        encoding="utf-8",
    )
    report = audit.build_report(tmp_path)
    assert report["summary"]["errors"] >= 4
    assert "approved note missing Short answer section" in report["notes"][0]["errors"]


def test_decorated_section_heading_is_recognized(tmp_path) -> None:
    # 2026-08-06: automix-compression-ratios.md's real "Try this" heading is
    # "Try this -- the default ratios by instrument (before genre
    # modifiers):", not bare "Try this:". This audit was flagging that
    # (and ~10 other genuinely well-formed, long-approved notes) as missing
    # the section entirely.
    (tmp_path / "decorated.md").write_text(
        """# Compression Ratios

Type: AutoMix decision logic
Tags: automix, compression, ratio
Status: Approved
Source: mix_rules.py
Reviewed: 2026-07-09

Short answer:
Every instrument gets a default compressor ratio.

Try this -- the default ratios by instrument (before genre modifiers):
1. Kick: 4:1.

Why it matters:
Firmer control on percussive low end keeps the mix consistent.

Related questions:
- Why does kick ratio change between genres?
- What about snare?
""",
        encoding="utf-8",
    )
    report = audit.build_report(tmp_path)
    assert report["summary"]["errors"] == 0
    assert report["notes"][0]["errors"] == []


def test_body_prose_ending_in_colon_does_not_truncate_section(tmp_path) -> None:
    # 2026-08-06: same fix as note_quality.py -- a body sentence ending in a
    # colon before a list ("...depending on the client type:") was mistaken
    # for a new section heading, truncating Short answer to empty.
    (tmp_path / "export.md").write_text(
        """# Export Specs

Type: Personal studio workflow
Tags: export, wav, mp3
Status: Approved
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
- When should I use MP3 instead of WAV?
""",
        encoding="utf-8",
    )
    report = audit.build_report(tmp_path)
    assert report["summary"]["errors"] == 0
    assert report["notes"][0]["errors"] == []


def test_duplicate_related_questions_are_reported(tmp_path) -> None:
    _write(tmp_path / "one.md")
    _write(tmp_path / "two.md")
    report = audit.build_report(tmp_path)
    assert report["summary"]["duplicate_related_questions"] == 2
